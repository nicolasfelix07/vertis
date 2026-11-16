"""
TELA DA LOJA DE PONTOS — vitrine 3D
==================================
Problema que resolve: o cliente troca pontos sem saber direito o que está
levando. Aqui ele GIRA o item em 3D antes de decidir.

Computação gráfica nesta tela:
  • cg/malhas.py      → cada item é um objeto 3D montado por código
  • cg/vitrine3d.py   → pipeline gráfico: matrizes, projeção, Z-BUFFER, Phong
  • animação da troca → o item "voa" até o canto numa CURVA DE BÉZIER,
                        diminuindo (translação + escala a cada quadro)
"""
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.graphics import Color, Rectangle
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, DictProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget

import servidor
from cg import raster
from telas.componentes import TelaVertis, aviso
from telas.formulario import abrir_formulario

Builder.load_string("""
#:import rgba tema.rgba
#:import CORES tema.CORES
#:import servidor servidor

<CartaoItemLoja>:
    orientation: 'vertical'
    size_hint: None, None
    size: dp(118), dp(100)
    padding: dp(10), dp(10)
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: (1, 1, 1, 1) if not root.selecionado else rgba(CORES['amarelo_suave'])
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
        Color:
            rgba: rgba(CORES['amarelo']) if root.selecionado else rgba(CORES['borda'])
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(14))
            width: 1.6 if root.selecionado else 1
    Widget:
        size_hint_y: None
        height: dp(16)
        canvas:
            Color:
                rgba: rgba(root.cor)
            Ellipse:
                pos: self.x, self.y
                size: dp(14), dp(14)
    Label:
        text: root.nome
        font_size: sp(12)
        bold: True
        color: rgba(CORES['texto'])
        text_size: self.width, None
        halign: 'left'
        valign: 'top'
        size_hint_y: None
        height: dp(34)
        shorten: False
        max_lines: 2
    Label:
        text: servidor.milhar(root.pontos) + ' pts'
        font_size: sp(12)
        bold: True
        color: rgba(CORES['dourado_claro']) if root.pode else rgba(CORES['texto2'])
        text_size: self.size
        halign: 'left'
        valign: 'middle'

<TelaLoja>:
    BoxLayout:
        orientation: 'vertical'
        BarraTopo:
            titulo: 'Loja de pontos'
            voltar: True
            destino_voltar: 'conquistas'
            Label:
                text: '[b]' + servidor.milhar(root.saldo) + '[/b] pts'
                markup: True
                font_size: sp(14)
                color: rgba(CORES['dourado_claro'])
                size_hint_x: None
                width: self.texture_size[0] + dp(8)
        ScrollView:
            do_scroll_x: False
            bar_width: dp(3)
            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                padding: dp(16), dp(12), dp(16), dp(18)
                spacing: dp(12)
                Painel:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: dp(290)
                    Vitrine3D:
                        id: vitrine
                    TextoPequeno:
                        text: 'Arraste para girar  •  objeto 3D desenhado pelo próprio app'
                        halign: 'center'
                        font_size: sp(11)
                Painel:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(4)
                    Texto:
                        text: '[b]' + servidor.campo(root.item, 'nome', padrao='') + '[/b]'
                        font_size: sp(18)
                    TextoPequeno:
                        text: root.linha_parceiro
                    Texto:
                        text: servidor.campo(root.item, 'descricao', padrao='')
                        font_size: sp(13)
                    Widget:
                        size_hint_y: None
                        height: dp(4)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(10)
                        Label:
                            text: '[b]' + servidor.milhar(servidor.campo(root.item, 'custo_pontos', padrao=0)) + '[/b] pts'
                            markup: True
                            font_size: sp(20)
                            color: rgba(CORES['texto'])
                            size_hint_x: None
                            width: dp(110)
                            text_size: self.size
                            halign: 'left'
                            valign: 'middle'
                        BotaoVertis:
                            text: root.texto_botao
                            disabled: not root.pode
                            opacity: 1 if root.pode else 0.55
                            on_release: root.confirmar()
                Texto:
                    text: '[b]Escolha uma recompensa[/b]'
                    font_size: sp(15)
                ScrollView:
                    do_scroll_y: False
                    size_hint_y: None
                    height: dp(104)
                    bar_width: dp(2)
                    BoxLayout:
                        id: carrossel
                        size_hint_x: None
                        width: self.minimum_width
                        spacing: dp(10)
                        padding: 0, dp(2)
                Painel:
                    orientation: 'horizontal'
                    size_hint_y: None
                    height: dp(76)
                    spacing: dp(12)
                    Icone:
                        icone: 'cupom'
                        size_hint_x: None
                        width: dp(30)
                    BoxLayout:
                        orientation: 'vertical'
                        Texto:
                            text: '[b]Cupom do mês[/b]'
                            font_size: sp(14)
                        TextoPequeno:
                            text: 'Escolhido pelos seus gastos essenciais. Não é sorteio.'
                            font_size: sp(11)
                    BotaoContorno:
                        text: 'Abrir'
                        size_hint: None, None
                        size: dp(76), dp(38)
                        pos_hint: {'center_y': .5}
                        on_release: app.ir('cupons')
                BotaoLink:
                    text: 'Como a vitrine 3D funciona?'
                    on_release: root.como_funciona()
        BarraNavegacao:
            atual: 'conquistas'
""")


class CartaoItemLoja(ButtonBehavior, BoxLayout):
    nome = StringProperty("")
    pontos = NumericProperty(0)
    cor = StringProperty("#F5B700")
    pode = BooleanProperty(False)
    selecionado = BooleanProperty(False)
    indice = NumericProperty(0)


class VooBezier(Widget):
    """O item "voa" até o canto: posição = curva de Bézier B(t), tamanho = escala (1 − 0,8t)."""

    def __init__(self, textura, origem, destino, lado, ao_terminar=None, **kw):
        super().__init__(**kw)
        ox, oy = origem
        dx, dy = destino
        controle1 = (ox + (dx - ox) * 0.1, oy + dp(220))           # sobe primeiro...
        controle2 = (dx - dp(40), dy + dp(60))                      # ...e desce no destino
        self.pontos = raster.bezier_cubica(origem, controle1, controle2, destino, 40)
        self.lado, self.t, self.ao_terminar = lado, 0.0, ao_terminar
        with self.canvas:
            Color(1, 1, 1, 1)
            self.ret = Rectangle(texture=textura)
        self._ev = Clock.schedule_interval(self._passo, 1 / 60)

    def _passo(self, dt):
        self.t = min(1.0, self.t + dt / 0.9)
        x, y = self.pontos[int(self.t * (len(self.pontos) - 1))]
        lado = self.lado * (1 - 0.8 * self.t)
        self.ret.pos, self.ret.size = (x - lado / 2, y - lado / 2), (lado, lado)
        if self.t >= 1:
            self._ev.cancel()
            Window.remove_widget(self)
            if self.ao_terminar:
                self.ao_terminar()


class TelaLoja(TelaVertis):
    itens = ListProperty([])
    item = DictProperty({})
    saldo = NumericProperty(0)
    pode = BooleanProperty(False)
    texto_botao = StringProperty("Trocar")
    linha_parceiro = StringProperty("")
    _selecionado = 0

    def on_pre_enter(self, *_):
        self.ids.vitrine.retomar()
        self.carregar()

    def on_leave(self, *_):
        self.ids.vitrine.parar()

    def carregar(self):
        servidor.get("/loja/itens", ao_receber=self._preencher, ao_falhar=lambda m: aviso(m, erro=True))

    def _preencher(self, r):
        self.saldo = r["saldo_pontos"]
        self.itens = r["itens"]
        caixa = self.ids.carrossel
        caixa.clear_widgets()
        for i, it in enumerate(self.itens):
            c = CartaoItemLoja(nome=it["nome"], pontos=it["custo_pontos"], cor=it["cor_hex"], pode=it["pode_trocar"],
                               indice=i)
            c.bind(on_release=lambda w: self.selecionar(w.indice))
            caixa.add_widget(c)
        if self.itens:
            self.selecionar(min(self._selecionado, len(self.itens) - 1))

    def selecionar(self, i):
        self._selecionado = i
        it = self.itens[i]
        self.item = it
        for c in self.ids.carrossel.children:
            c.selecionado = (c.indice == i)
        v = self.ids.vitrine
        v.cor = it["cor_hex"]
        v.modelo = it["modelo_3d"]
        partes = [p for p in (it.get("parceiro"), it.get("categoria")) if p]
        self.linha_parceiro = "  •  ".join(partes)
        self.pode = bool(it["pode_trocar"])
        self.texto_botao = "Trocar" if self.pode else f"Faltam {servidor.milhar(it['faltam'])} pts"

    def confirmar(self):
        it = self.item
        abrir_formulario(f"Trocar {servidor.milhar(it['custo_pontos'])} pontos?", [], "Trocar",
                         lambda _v: self.trocar(),
                         explicacao=f"{it['nome']}\n{it.get('descricao') or ''}\n\n"
                                    f"Seu saldo vai de {servidor.milhar(self.saldo)} para "
                                    f"{servidor.milhar(self.saldo - it['custo_pontos'])} pontos.")

    def trocar(self):
        def feito(r):
            v = self.ids.vitrine
            origem = v.to_window(*v.center)
            destino = (Window.width - dp(48), Window.height - dp(28))

            def fim():
                if r["tipo"] == "cashback":
                    aviso(f"{servidor.reais(r['valor_reais'])} de cashback na sua conta!")
                else:
                    aviso("Troca feita! Seu vale está em Meus cupons.")
                self.carregar()
                App.get_running_app().mostrar_novidades()
            Window.add_widget(VooBezier(v._ret.texture, origem, destino, min(v.width, v.height) * 0.8, fim))
        servidor.post("/loja/trocar", {"item_id": self.item["id"]}, ao_receber=feito,
                      ao_falhar=lambda m: aviso(m, erro=True))

    def como_funciona(self):
        abrir_formulario("Como a vitrine 3D funciona", [], "Entendi", lambda _v: None, explicacao=(
            "1. MODELAGEM: cada item é montado por código com formas básicas (caixa, cilindro, toro), "
            "calculadas com seno e cosseno. Ex.: o fone é meio toro + 2 cilindros.\n"
            "2. TRANSFORMAÇÕES: ao arrastar, a matriz do modelo (Rx · Ry · S) muda.\n"
            "3. PROJEÇÃO EM PERSPECTIVA: o que está longe fica menor.\n"
            "4. Z-BUFFER: em cada pixel, só aparece a superfície mais perto da câmera.\n"
            "5. ILUMINAÇÃO DE PHONG: o brilho é calculado pixel a pixel na placa de vídeo.\n"
            "6. ANTIALIASING: desenhamos 2x maior e reduzimos (superamostragem).\n"
            "Compare com o algoritmo do pintor na aba Lab CG."))
