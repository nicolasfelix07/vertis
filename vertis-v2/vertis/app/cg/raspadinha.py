"""
RASPADINHA — revelar o cupom com o dedo
======================================
Conteúdos da disciplina:
  • RASTERIZAÇÃO: cada movimento do dedo é um segmento de reta grosso que
    "apaga" pixels de uma MÁSCARA (calculamos a distância de cada pixel
    ao segmento, como na trilha de ascensão).
  • ANTIALIASING: a borda do traço recebe cobertura parcial (0 a 1),
    então o risco fica liso, sem serrilhado.
  • COMPOSIÇÃO ALFA: a camada prateada é desenhada por cima do cupom
    com transparência = máscara. Onde o dedo passou, alfa = 0.
  • Contamos os pixels raspados: passou de 55%, revela o resto.

⚠️ NÃO É SORTEIO: o cupom já foi escolhido pela API (pelos gastos do
cliente). A raspadinha só REVELA. Para um público com pouca renda,
mecânicas de sorte parecem jogo de azar — e a Vértis não faz isso.
"""
import numpy as np
from kivy.animation import Animation
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.widget import Widget

from cg import raster

ESCALA_MASCARA = 0.5          # a máscara tem metade da resolução (mais rápido no celular)
LIMIAR_REVELAR = 0.55


def _texto_rgba(texto, tamanho, cor):
    """Rasteriza um texto (Kivy) e devolve como matriz NumPy RGBA."""
    r = CoreLabel(text=texto, font_size=tamanho, bold=True, color=cor)
    r.refresh()
    t = r.texture
    img = np.frombuffer(t.pixels, np.uint8).reshape(t.height, t.width, 4)
    return img[::-1] if t.uvsize[1] < 0 else img       # texturas de texto vêm de cabeça para baixo


class Raspadinha(Widget):
    progresso = NumericProperty(0.0)
    raspada = BooleanProperty(False)
    raio = NumericProperty(dp(16))
    __events__ = ("on_primeiro_toque", "on_revelar")

    def __init__(self, **kw):
        super().__init__(**kw)
        self._mascara = None
        self._ultimo = None
        self._comecou = False
        with self.canvas.after:
            self._cor = Color(1, 1, 1, 1)
            self._ret = Rectangle()
        self.bind(size=self._criar, pos=self._posicionar)

    # ------------------------------------------------------------ camada prateada
    def _criar(self, *_):
        w, h = int(self.width * ESCALA_MASCARA), int(self.height * ESCALA_MASCARA)
        if w < 4 or h < 4 or self.raspada:
            return
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        rng = np.random.default_rng(7)
        # prata = degradê + ruído fino + listras diagonais (tonalização procedural)
        base = 0.72 + 0.12 * (yy / h) + 0.05 * np.sin((xx + yy) * 0.35) + rng.normal(0, 0.03, (h, w))
        cor = np.dstack([base * 0.97, base * 0.98, base * 1.02])
        img = (np.clip(cor, 0, 1) * 255).astype(np.uint8)
        txt = _texto_rgba("RASPE AQUI", sp(26) * ESCALA_MASCARA, (0.35, 0.37, 0.42, 1))
        sub = _texto_rgba("o seu cupom já foi escolhido pelos seus gastos", sp(13) * ESCALA_MASCARA,
                          (0.35, 0.37, 0.42, 1))
        for t, dy in ((txt, 0.08), (sub, -0.16)):
            th, tw = t.shape[:2]
            if tw < w and th < h:
                x0, y0 = (w - tw) // 2, int(h / 2 + dy * h - th / 2)
                a = t[..., 3:4] / 255.0
                img[y0:y0 + th, x0:x0 + tw] = (img[y0:y0 + th, x0:x0 + tw] * (1 - a) + t[..., :3] * a).astype(np.uint8)
        self._cor_img = img
        self._mascara = np.ones((h, w), np.float32)
        self._atualizar()
        self._posicionar()

    def _posicionar(self, *_):
        self._ret.pos, self._ret.size = self.pos, self.size

    def _atualizar(self):
        rgba = np.dstack([self._cor_img, (self._mascara * 255).astype(np.uint8)])
        self._ret.texture = raster.para_textura(rgba)

    # ------------------------------------------------------------ raspar
    def raspar(self, x0, y0, x1, y1):
        """Rasteriza um segmento grosso (do ponto anterior ao atual) na máscara."""
        if self._mascara is None or self.raspada:
            return
        e = ESCALA_MASCARA
        a = np.array([(x0 - self.x) * e, (y0 - self.y) * e])
        b = np.array([(x1 - self.x) * e, (y1 - self.y) * e])
        r = self.raio * e
        h, w = self._mascara.shape
        xa, xb = int(max(0, min(a[0], b[0]) - r - 1)), int(min(w, max(a[0], b[0]) + r + 2))
        ya, yb = int(max(0, min(a[1], b[1]) - r - 1)), int(min(h, max(a[1], b[1]) + r + 2))
        if xa >= xb or ya >= yb:
            return
        yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32) + 0.5
        ab = b - a
        l2 = max(float(ab @ ab), 1e-6)
        t = np.clip(((xx - a[0]) * ab[0] + (yy - a[1]) * ab[1]) / l2, 0, 1)
        d = np.hypot(xx - (a[0] + t * ab[0]), yy - (a[1] + t * ab[1]))
        cobertura = np.clip(r - d + 0.5, 0, 1)                    # antialiasing da borda do traço
        regiao = self._mascara[ya:yb, xa:xb]
        np.minimum(regiao, 1 - cobertura, out=regiao)
        self.progresso = float((self._mascara < 0.5).mean())       # fração de pixels raspados
        self._atualizar()
        if self.progresso >= LIMIAR_REVELAR:
            self.revelar_tudo()

    def revelar_tudo(self):
        if self.raspada:
            return
        self.raspada = True
        anim = Animation(a=0, d=0.5)
        anim.bind(on_complete=lambda *_: self.dispatch("on_revelar"))
        anim.start(self._cor)

    def on_touch_down(self, t):
        if self.collide_point(*t.pos) and not self.raspada:
            t.grab(self)
            self._ultimo = t.pos
            if not self._comecou:
                self._comecou = True
                self.dispatch("on_primeiro_toque")
            self.raspar(*t.pos, *t.pos)
            return True
        return super().on_touch_down(t)

    def on_touch_move(self, t):
        if t.grab_current is self:
            self.raspar(*self._ultimo, *t.pos)
            self._ultimo = t.pos
            return True
        return super().on_touch_move(t)

    def on_touch_up(self, t):
        if t.grab_current is self:
            t.ungrab(self)
            return True
        return super().on_touch_up(t)

    def on_primeiro_toque(self):
        pass

    def on_revelar(self):
        pass
