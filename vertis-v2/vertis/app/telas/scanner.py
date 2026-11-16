"""
TELA "PAGAR CONTA COM FOTO" — scanner com homografia
===================================================
Problema que resolve: contas de luz, água e celular pagas em dia AJUDAM O
SCORE (calibração do crédito responsável). O cliente fotografa a conta;
a foto sai torta; o app CORRIGE A PERSPECTIVA e ele confere os dados.

Passo a passo (computação gráfica):
  1. Detectar os 4 cantos da folha (cor do fundo × cor da folha).
  2. O cliente ajusta os cantos com o dedo. Enquanto arrasta, aparece uma
     LUPA: um RECORTE da textura ampliado (escala) para ver o canto exato.
  3. HOMOGRAFIA (transformação projetiva 3x3) + INTERPOLAÇÃO BILINEAR
     → a conta vira um retângulo reto e legível (cg/homografia.py).
  4. O cliente confere valor e vencimento e paga: conta paga em dia = score.
"""
import math
import os
from datetime import date

import numpy as np
from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.factory import Factory
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import ListProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivy.utils import platform

import servidor
from cg import homografia, raster
from tema import CORES, rgba
from telas.componentes import CampoData, CampoDinheiro, TelaVertis, aviso

EXEMPLO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "conta_exemplo.jpg")
DADOS_EXEMPLO = {"beneficiario": "Energia elétrica", "valor": 127.43, "vencimento": "10/12/2026"}
MAX_LADO = 1600   # fotos grandes do celular são reduzidas (memória e velocidade)

Builder.load_string("""
<TelaScanner>:
    BoxLayout:
        orientation: 'vertical'
        BarraTopo:
            titulo: 'Pagar conta com foto'
            voltar: True
            destino_voltar: 'conta'
        ScrollView:
            id: rolagem
            do_scroll_x: False
            bar_width: dp(3)
            BoxLayout:
                id: conteudo
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                padding: dp(16), dp(12), dp(16), dp(18)
                spacing: dp(12)
        BarraNavegacao:
            atual: 'conta'
""")


def carregar_imagem(caminho):
    """Arquivo → (matriz NumPy RGBA com a linha 0 EMBAIXO, textura do Kivy)."""
    im = CoreImage(caminho, keep_data=True)
    t = im.texture
    fmt = t.colorfmt
    canais = 4 if fmt in ("rgba", "bgra") else 3
    arr = np.frombuffer(t.pixels, np.uint8).reshape(t.height, t.width, -1)
    if arr.shape[2] == 3:
        arr = np.dstack([arr, np.full(arr.shape[:2], 255, np.uint8)])
    if fmt.startswith("bgr"):
        arr = arr[..., [2, 1, 0, 3]]
    if t.uvsize[1] < 0:                   # textura guardada de cabeça para baixo
        arr = arr[::-1]
    passo = max(1, int(math.ceil(max(arr.shape[:2]) / MAX_LADO)))
    arr = np.ascontiguousarray(arr[::passo, ::passo])
    return arr, raster.para_textura(arr)


class EditorCantos(Widget):
    """Mostra a foto e 4 alças arrastáveis. Coordenadas dos cantos: pixels da IMAGEM."""
    textura = ObjectProperty(None, allownone=True)
    tamanho_img = ListProperty([1, 1])
    cantos = ListProperty([])

    def __init__(self, **kw):
        super().__init__(**kw)
        self._arrastando = None
        self.bind(pos=self._desenhar, size=self._desenhar, textura=self._desenhar, cantos=self._desenhar)

    # mapeamento imagem ↔ tela (escala + translação: transformação 2D)
    def _ajuste(self):
        iw, ih = self.tamanho_img
        esc = min(self.width / iw, self.height / ih)
        # (centro calculado na mão: center_x do Kivy pode estar desatualizado durante o redimensionamento)
        cx, cy = self.x + self.width / 2, self.y + self.height / 2
        return esc, cx - iw * esc / 2, cy - ih * esc / 2

    def img_para_tela(self, p):
        esc, ox, oy = self._ajuste()
        return ox + p[0] * esc, oy + p[1] * esc

    def tela_para_img(self, x, y):
        esc, ox, oy = self._ajuste()
        iw, ih = self.tamanho_img
        return min(iw - 1, max(0, (x - ox) / esc)), min(ih - 1, max(0, (y - oy) / esc))

    def _desenhar(self, *_):
        self.canvas.clear()
        if self.textura is None or len(self.cantos) != 4:
            return
        esc, ox, oy = self._ajuste()
        iw, ih = self.tamanho_img
        tela = [self.img_para_tela(p) for p in self.cantos]
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=self.textura, pos=(ox, oy), size=(iw * esc, ih * esc))
            Color(*rgba(CORES["amarelo"], 0.18))                 # área selecionada (leque de triângulos)
            vert = []
            for x, y in tela:
                vert += [x, y, 0, 0]
            Mesh(vertices=vert, indices=[0, 1, 2, 3], mode="triangle_fan")
            Color(*rgba(CORES["amarelo"]))
            Line(points=[c for p in tela for c in p], close=True, width=dp(1.6))
            for i, (x, y) in enumerate(tela):
                r = dp(13) if i == self._arrastando else dp(10)
                Color(1, 1, 1, 1)
                Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))
                Color(*rgba(CORES["amarelo"]))
                Line(circle=(x, y, r), width=dp(2))
            if self._arrastando is not None:
                self._lupa(*self.cantos[self._arrastando])

    def _lupa(self, px, py):
        """LUPA: recorta um pedaço da textura em volta do canto e mostra AMPLIADO (escala 4x)."""
        iw, ih = self.tamanho_img
        meio = 22 / self._ajuste()[0]                # metade do pedaço, em pixels da imagem
        u0, u1 = (px - meio) / iw, (px + meio) / iw
        v0, v1 = (py - meio) / ih, (py + meio) / ih
        lado = dp(110)
        x, y = self.x + dp(6), self.top - lado - dp(6)
        Color(*rgba(CORES["grafite"]))
        Rectangle(pos=(x - 2, y - 2), size=(lado + 4, lado + 4))
        Color(1, 1, 1, 1)
        Rectangle(texture=self.textura, pos=(x, y), size=(lado, lado), tex_coords=[u0, v0, u1, v0, u1, v1, u0, v1])
        Color(*rgba(CORES["amarelo"]))
        Line(points=[x + lado / 2, y, x + lado / 2, y + lado], width=1)
        Line(points=[x, y + lado / 2, x + lado, y + lado / 2], width=1)

    def on_touch_down(self, t):
        if not self.collide_point(*t.pos) or len(self.cantos) != 4:
            return super().on_touch_down(t)
        dist = [math.dist(t.pos, self.img_para_tela(p)) for p in self.cantos]
        i = int(np.argmin(dist))
        if dist[i] > dp(40):
            return super().on_touch_down(t)
        self._arrastando = i
        t.grab(self)
        self._desenhar()
        return True

    def on_touch_move(self, t):
        if t.grab_current is self:
            novos = list(self.cantos)
            novos[self._arrastando] = self.tela_para_img(*t.pos)
            self.cantos = novos
            return True
        return super().on_touch_move(t)

    def on_touch_up(self, t):
        if t.grab_current is self:
            t.ungrab(self)
            self._arrastando = None
            self._desenhar()
            return True
        return super().on_touch_up(t)


def _texto(texto, tam=14, cor=None, alinhar="left"):
    rot = Label(text=texto, markup=True, font_size=sp(tam), color=cor or rgba(CORES["texto"]),
                halign=alinhar, valign="middle", size_hint_y=None)
    rot.bind(width=lambda w, v: setattr(w, "text_size", (v, None)), texture_size=lambda w, v: setattr(w, "height", v[1]))
    return rot


class TelaScanner(TelaVertis):
    _img = None
    _textura = None
    _exemplo = False

    def on_pre_enter(self, *_):
        if self._img is None:
            self.etapa_foto()

    # ------------------------------------------------------------ etapa 1: escolher a foto
    def etapa_foto(self):
        box = self.ids.conteudo
        box.clear_widgets()
        painel = Factory.Painel(orientation="vertical", size_hint_y=None, spacing=dp(10))
        painel.bind(minimum_height=painel.setter("height"))
        painel.add_widget(_texto("[b]Conta de luz, água ou celular paga em dia ajuda o seu score[/b]", 15))
        painel.add_widget(_texto("É o histórico que você JÁ TEM, mesmo sem nunca ter tido cartão. "
                                 "Tire uma foto da conta: o app corrige a perspectiva e você confere os dados.",
                                 12, rgba(CORES["texto2"])))
        for texto, acao, tipo in (("Usar a foto de exemplo", self.usar_exemplo, "BotaoVertis"),
                                  ("Escolher foto da galeria", self.escolher_foto, "BotaoContorno")):
            b = getattr(Factory, tipo)(text=texto)
            b.bind(on_release=lambda *_, a=acao: a())
            painel.add_widget(b)
        box.add_widget(painel)
        manual = Factory.BotaoLink(text="Digitar os dados sem foto")
        manual.bind(on_release=lambda *_: self._manual())
        box.add_widget(manual)

    def _manual(self):
        app = App.get_running_app()
        app.ir("conta")
        app.root.get_screen("conta").pagar_conta_manual()

    def usar_exemplo(self):
        self._exemplo = True
        self._abrir(EXEMPLO)

    def escolher_foto(self):
        self._exemplo = False
        if platform == "android":
            try:
                from android.permissions import Permission, request_permissions
                request_permissions([Permission.READ_MEDIA_IMAGES, Permission.READ_EXTERNAL_STORAGE])
            except Exception:
                pass
            try:
                from plyer import filechooser
                filechooser.open_file(on_selection=lambda sel: sel and self._abrir(sel[0]),
                                      filters=[["Imagens", "*.jpg", "*.jpeg", "*.png"]])
                return
            except Exception as e:
                aviso(f"Não consegui abrir a galeria: {e}", erro=True)
                return
        # no computador: seletor de arquivos do próprio Kivy
        janela = ModalView(size_hint=(0.95, 0.8))
        caixa = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        seletor = FileChooserListView(path=os.path.expanduser("~"), filters=["*.jpg", "*.jpeg", "*.png", "*.JPG"])
        botao = Factory.BotaoVertis(text="Abrir foto")

        def abrir(*_):
            if seletor.selection:
                janela.dismiss()
                self._abrir(seletor.selection[0])
        botao.bind(on_release=abrir)
        seletor.bind(on_submit=lambda *a: abrir())
        caixa.add_widget(seletor)
        caixa.add_widget(botao)
        janela.add_widget(caixa)
        janela.open()

    def _abrir(self, caminho):
        try:
            self._img, self._textura = carregar_imagem(caminho)
        except Exception as e:
            aviso(f"Não consegui abrir a imagem: {e}", erro=True)
            return
        self.etapa_cantos(detectar=True)

    # ------------------------------------------------------------ etapa 2: ajustar os cantos
    def etapa_cantos(self, detectar=False):
        h, w = self._img.shape[:2]
        cantos = None
        if detectar:
            cantos = homografia.detectar_cantos(self._img)
        if not cantos:
            cantos = getattr(self, "_cantos", None) or [(w * 0.1, h * 0.1), (w * 0.9, h * 0.1),
                                                        (w * 0.9, h * 0.9), (w * 0.1, h * 0.9)]
        box = self.ids.conteudo
        box.clear_widgets()
        box.add_widget(_texto("[b]Confira os 4 cantos da conta[/b]", 15))
        box.add_widget(_texto("O app achou os cantos sozinho. Se precisar, arraste as bolinhas até as pontas "
                              "da folha (aparece uma lupa para ajudar).", 12, rgba(CORES["texto2"])))
        self.editor = EditorCantos(size_hint_y=None, height=dp(400), textura=self._textura,
                                   tamanho_img=[w, h], cantos=[list(c) for c in cantos])
        box.add_widget(self.editor)
        linha = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        for texto, acao in (("Detectar de novo", lambda: self.etapa_cantos(detectar=True)),
                            ("Trocar foto", self.etapa_foto)):
            b = Factory.BotaoContorno(text=texto, height=dp(44))
            b.bind(on_release=lambda *_, a=acao: a())
            linha.add_widget(b)
        box.add_widget(linha)
        corrigir = Factory.BotaoVertis(text="Corrigir perspectiva")
        corrigir.bind(on_release=lambda *_: self.corrigir())
        box.add_widget(corrigir)

    # ------------------------------------------------------------ etapa 3: imagem corrigida + pagamento
    def corrigir(self):
        c = [tuple(p) for p in self.editor.cantos]
        self._cantos = c
        # tamanho do retângulo final = média dos lados do quadrilátero
        larg = (math.dist(c[0], c[1]) + math.dist(c[3], c[2])) / 2
        alt = (math.dist(c[0], c[3]) + math.dist(c[1], c[2])) / 2
        esc = min(1.0, 900 / max(larg, alt))
        larg, alt = max(50, int(larg * esc)), max(50, int(alt * esc))
        saida, H = homografia.retificar(self._img, c, larg, alt)
        tex = raster.para_textura(saida)

        box = self.ids.conteudo
        box.clear_widgets()
        box.add_widget(_texto("[b]Conta corrigida[/b]", 15))
        imagem = Widget(size_hint_y=None, height=dp(380))

        def desenhar(w, *_):
            w.canvas.clear()
            e = min(w.width / larg, w.height / alt)
            with w.canvas:
                Color(1, 1, 1, 1)
                Rectangle(texture=tex, pos=(w.x + (w.width - larg * e) / 2, w.y + (w.height - alt * e) / 2), size=(larg * e, alt * e))
        imagem.bind(pos=desenhar, size=desenhar)
        box.add_widget(imagem)

        painel = Factory.Painel(orientation="vertical", size_hint_y=None, spacing=dp(4))
        painel.bind(minimum_height=painel.setter("height"))
        painel.add_widget(_texto("[b]Matriz de homografia H[/b] (da foto para o retângulo)", 13))
        mat = Label(text=homografia.formatar(H), font_name="RobotoMono-Regular", font_size=sp(11),
                    color=rgba(CORES["dourado_claro"]), size_hint_y=None, height=dp(56))
        painel.add_widget(mat)
        painel.add_widget(_texto("Cada pixel do retângulo pergunta à matriz de onde ele vem na foto "
                                 "(x = x'/w', y = y'/w') e mistura os 4 pixels vizinhos (interpolação bilinear).",
                                 11, rgba(CORES["texto2"])))
        box.add_widget(painel)

        form = Factory.Painel(orientation="vertical", size_hint_y=None, spacing=dp(6))
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(_texto("[b]Confira os dados da conta[/b]", 15))
        if self._exemplo:
            self.nota_exemplo = _texto("Preenchido com os dados da conta de exemplo. Confira na imagem acima.", 11,
                                       rgba(CORES["texto2"]))
            form.add_widget(self.nota_exemplo)
        dados = DADOS_EXEMPLO if self._exemplo else {"beneficiario": "Energia elétrica", "valor": 0, "vencimento": ""}
        form.add_widget(Factory.Rotulo(text="Qual conta?"))
        self.campo_conta = Factory.Opcoes(text=dados["beneficiario"],
                                          values=["Energia elétrica", "Água e esgoto", "Celular / internet", "Gás"])
        form.add_widget(self.campo_conta)
        form.add_widget(Factory.Rotulo(text="Valor"))
        self.campo_valor = CampoDinheiro(hint_text="R$ 0,00")
        self.campo_valor.definir(dados["valor"])
        form.add_widget(self.campo_valor)
        form.add_widget(Factory.Rotulo(text="Vencimento"))
        self.campo_venc = CampoData(hint_text="DD/MM/AAAA")
        self.campo_venc.text = dados["vencimento"]
        form.add_widget(self.campo_venc)
        pagar = Factory.BotaoVertis(text="Pagar conta")
        pagar.bind(on_release=lambda *_: self.pagar())
        form.add_widget(pagar)
        box.add_widget(form)
        if self._exemplo:
            servidor.get("/me/resumo", ao_receber=self._vencimento_da_simulacao)
        refazer = Factory.BotaoLink(text="Ajustar os cantos de novo")
        refazer.bind(on_release=lambda *_: self.etapa_cantos(detectar=False))
        box.add_widget(refazer)
        self.ids.rolagem.scroll_y = 1

    def _vencimento_da_simulacao(self, r):
        """Modo demonstração: se o relógio da simulação já passou do vencimento impresso
        na conta de exemplo, usamos 'hoje da simulação + 10 dias' (senão ela sairia como atrasada)."""
        hoje = date.fromisoformat(str(r["data_simulada"])[:10])
        if hoje > date(2026, 12, 10):
            venc = date.fromordinal(hoje.toordinal() + 10)
            self.campo_venc.text = venc.strftime("%d/%m/%Y")
            self.nota_exemplo.text = (f"Conta de exemplo. No modo demonstração o relógio da simulação está em "
                                      f"{hoje:%d/%m/%Y}, então o vencimento foi ajustado para {venc:%d/%m/%Y}.")

    def pagar(self):
        valor = self.campo_valor.valor
        if valor <= 0:
            aviso("Informe o valor da conta", erro=True)
            return
        venc = None
        d = "".join(ch for ch in self.campo_venc.text if ch.isdigit())
        if len(d) == 8:
            try:
                venc = date(int(d[4:]), int(d[2:4]), int(d[:2])).isoformat()
            except ValueError:
                aviso("Data de vencimento inválida", erro=True)
                return

        def pago(r):
            if r.get("em_dia"):
                aviso(f"Conta paga em dia! Ela conta a favor do seu score (agora {r['score']}).")
            else:
                aviso(f"Conta paga, mas depois do vencimento. Score: {r['score']}.", erro=True)
            self._img = None
            app = App.get_running_app()
            app.ir("conta")
        servidor.post("/contas/pagar", {"beneficiario": self.campo_conta.text, "valor": valor, "vencimento": venc},
                      ao_receber=pago, ao_falhar=lambda m: aviso(m, erro=True))
