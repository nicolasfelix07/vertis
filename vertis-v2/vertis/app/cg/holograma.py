"""
SELO HOLOGRÁFICO DO CUPOM — iluminação por pixel com MAPA DE NORMAIS
===================================================================
Problema que resolve: um PRINT do cupom pode ser copiado e usado por outra
pessoa. O selo verdadeiro muda de cor quando o celular inclina (como o
holograma de uma nota de dinheiro); um print fica parado.

Como funciona (conteúdos da disciplina):
 1. MAPA DE ALTURA: desenhamos o relevo do selo com funções matemáticas
    (ondas concêntricas, raios e o logo da Vértis em alto-relevo).
 2. MAPA DE NORMAIS: a normal de cada pixel vem da inclinação do relevo
    (derivadas): N = normalizar(−dh/dx, −dh/dy, 1).
    É a técnica "normal mapping": parece 3D sem ter geometria 3D.
 3. ILUMINAÇÃO POR PIXEL a cada quadro, usando a inclinação do aparelho
    como direção do olhar (V):
       • cor iridescente = matiz que depende de N·V e da posição (difração)
       • brilho especular = (R·V)^n
 4. ANTIALIASING na borda: cobertura parcial dos pixels do contorno.

No celular a inclinação vem do ACELERÔMETRO; no computador, do MOUSE.
"""
import math
import time

import numpy as np
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.widget import Widget
from kivy.utils import platform

from cg import raster

_cache = {}


def mapa_de_normais(n: int):
    """Relevo do selo → normais por pixel. Calculado uma vez e guardado."""
    if n in _cache:
        return _cache[n]
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    x = (x + 0.5) / n * 2 - 1          # coordenadas de −1 a 1
    y = (y + 0.5) / n * 2 - 1
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    altura = 0.03 * np.sin(26 * r) + 0.02 * np.sin(18 * th) * (r > 0.6)
    # logo da Vértis: 3 barras crescentes em alto-relevo (bordas suaves)
    for i, (cx, h) in enumerate(((-0.32, 0.30), (0.0, 0.48), (0.32, 0.68))):
        bx = np.clip((0.11 - np.abs(x - cx)) / 0.05, 0, 1)
        by = np.clip((h / 2 - np.abs(y - (-0.42 + h / 2))) / 0.05, 0, 1)
        altura += 0.22 * bx * by
    altura += 0.12 * np.clip((0.06 - np.abs(r - 0.86)) / 0.03, 0, 1)      # aro
    gy, gx = np.gradient(altura, 2 / n)                                       # derivadas do relevo
    N = np.dstack([-gx * 0.9, -gy * 0.9, np.ones_like(altura)])
    N /= np.linalg.norm(N, axis=2, keepdims=True)
    borda = np.clip((0.97 - r) * n / 2, 0, 1)                                 # antialiasing do contorno
    _cache[n] = (N, x, y, borda)
    return _cache[n]


def hsv_para_rgb(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    escolha = [np.stack(c, axis=-1) for c in ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))]
    saida = np.zeros(h.shape + (3,), np.float32)
    for k in range(6):
        saida = np.where((i == k)[..., None], escolha[k], saida)
    return saida


def renderizar(n: int, incl_x: float, incl_y: float, mostrar_normais=False) -> np.ndarray:
    N, x, y, borda = mapa_de_normais(n)
    if mostrar_normais:     # visualização clássica: normal (−1…1) → cor (0…1)
        return (np.dstack([N * 0.5 + 0.5, borda]) * 255).astype(np.uint8)
    V = np.array([incl_x * 0.9, incl_y * 0.9, 1.0])
    V /= np.linalg.norm(V)
    ndotv = N @ V
    # DIFRAÇÃO (holograma): a cor depende do ângulo de visão e da posição no selo
    matiz = (ndotv * 2.2 + (x * incl_x + y * incl_y) * 0.9 + 0.25 * np.hypot(x, y) + 0.15 * incl_x) % 1.0
    arco_iris = hsv_para_rgb(matiz, np.full_like(matiz, 0.75), np.full_like(matiz, 1.0))
    L = np.array([-0.3, 0.5, 1.0]) / np.linalg.norm([-0.3, 0.5, 1.0])
    ndotl = np.clip(N @ L, 0, 1)
    R = 2 * ndotl[..., None] * N - L                       # vetor refletido
    especular = np.clip(R @ V, 0, 1) ** 28
    prata = 0.55 + 0.35 * ndotl
    cor = prata[..., None] * 0.3 + arco_iris * 0.7 * (0.55 + 0.45 * ndotl[..., None]) + especular[..., None] * 0.9
    return (np.dstack([np.clip(cor, 0, 1), borda]) * 255).astype(np.uint8)


class SeloHolografico(Widget):
    mostrar_normais = BooleanProperty(False)
    ao_vivo = BooleanProperty(True)
    resolucao = NumericProperty(180)
    incl_x = NumericProperty(0.0)
    incl_y = NumericProperty(0.0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._alvo = [0.0, 0.0]
        self._ultimo_mouse = None
        self._ultima_mudanca = time.time()
        self._acelerometro = None
        if platform == "android":
            try:
                from plyer import accelerometer
                accelerometer.enable()
                self._acelerometro = accelerometer
            except Exception:
                self._acelerometro = None
        with self.canvas:
            Color(1, 1, 1, 1)
            self._ret = Rectangle()
        self.bind(pos=self._posicionar, size=self._posicionar, mostrar_normais=lambda *_: self._desenhar())
        self._evento = Clock.schedule_interval(self._quadro, 1 / 30)

    def _posicionar(self, *_):
        lado = min(self.width, self.height)
        self._ret.size = (lado, lado)
        self._ret.pos = (self.x + (self.width - lado) / 2, self.y + (self.height - lado) / 2)
        self._desenhar()

    def _ler_inclinacao(self):
        if self._acelerometro is not None:
            a = self._acelerometro.acceleration
            if a and a[0] is not None:
                self._alvo = [max(-1, min(1, -a[0] / 6)), max(-1, min(1, -a[1] / 6 + 0.6))]
                return
        mx, my = Window.mouse_pos                    # no computador: o mouse "inclina" o selo
        if self._ultimo_mouse != (mx, my):
            self._ultimo_mouse = (mx, my)
            self._ultima_mudanca = time.time()
            self._alvo = [max(-1, min(1, (mx / max(Window.width, 1)) * 2 - 1)),
                          max(-1, min(1, (my / max(Window.height, 1)) * 2 - 1))]
        elif time.time() - self._ultima_mudanca > 3:  # sem mexer: balança sozinho (bom no projetor)
            t = time.time()
            self._alvo = [0.8 * math.sin(t * 0.9), 0.6 * math.sin(t * 1.3)]

    def _quadro(self, dt):
        if not self.ao_vivo or self.width < 4:
            return
        self._ler_inclinacao()
        # suaviza o movimento (interpolação linear em direção ao alvo)
        self.incl_x += (self._alvo[0] - self.incl_x) * 0.18
        self.incl_y += (self._alvo[1] - self.incl_y) * 0.18
        self._desenhar()

    def _desenhar(self):
        n = int(self.resolucao)
        self._ret.texture = raster.para_textura(renderizar(n, self.incl_x, self.incl_y, self.mostrar_normais))

    def on_touch_move(self, t):
        if self.collide_point(*t.pos):
            self._alvo = [max(-1, min(1, (t.x - self.center_x) / (self.width / 2))),
                          max(-1, min(1, (t.y - self.center_y) / (self.height / 2)))]
            self._ultima_mudanca = time.time()
        return super().on_touch_move(t)

    def parar(self):
        self._evento.cancel()
        if self._acelerometro is not None:
            try:
                self._acelerometro.disable()
            except Exception:
                pass
