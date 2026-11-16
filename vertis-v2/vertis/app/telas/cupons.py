"""
TELA "MEUS CUPONS" — cupom inteligente, raspadinha e holograma
=============================================================
  • Cupom do mês: escolhido pela API pelos gastos ESSENCIAIS do cliente
    (mercado, transporte, saúde...). O app mostra o MOTIVO.
  • Raspadinha (cg/raspadinha.py): rasterização + composição alfa.
    Não é sorteio: só revela o que já foi decidido.
  • Selo holográfico (cg/holograma.py): mapa de normais + iluminação por
    pixel que reage à inclinação do celular (ou ao mouse no computador).
    Um print fica parado — o caixa percebe a cópia.
  • Modo caixa: confere a ASSINATURA do cupom na API (anti-fraude).
"""
from kivy.app import App
from kivy.clock import Clock
from kivy.factory import Factory
from kivy.graphics import Color, RoundedRectangle
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

import servidor
from cg import holograma, raster
from cg.holograma import SeloHolografico
from cg.raspadinha import Raspadinha
from tema import CORES, rgba
from telas.componentes import TelaVertis, aviso
from telas.formulario import abrir_formulario

Builder.load_string("""
#:import rgba tema.rgba
#:import CORES tema.CORES

<SeloEstatico>:
    canvas:
        Color:
            rgba: 1, 1, 1, (1 if root.ativo else 0.35)
        Rectangle:
            texture: root.textura
            pos: self.center_x - min(self.width, self.height) / 2, self.center_y - min(self.width, self.height) / 2
            size: min(self.width, self.height), min(self.width, self.height)

<CupomCartao>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(84)
    padding: dp(12), dp(10)
    spacing: dp(12)
    canvas.before:
        Color:
            rgba: (1, 1, 1, 1) if self.state == 'normal' else rgba(CORES['cinza_claro'])
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
        Color:
            rgba: rgba(CORES['borda'])
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(14))
            width: 1
    SeloEstatico:
        size_hint_x: None
        width: dp(56)
        ativo: root.ativo
    BoxLayout:
        orientation: 'vertical'
        Label:
            text: '[b]' + root.titulo + '[/b]'
            markup: True
            font_size: sp(14)
            color: rgba(CORES['texto']) if root.ativo else rgba(CORES['texto2'])
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            shorten: True
            shorten_from: 'right'
        Label:
            text: root.detalhe
            font_size: sp(11)
            color: rgba(CORES['texto2'])
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            shorten: True
            shorten_from: 'right'
    Label:
        text: root.status
        font_size: sp(11)
        bold: True
        color: rgba(CORES['verde']) if root.ativo else rgba(CORES['texto2'])
        size_hint_x: None
        width: dp(66)
        text_size: self.size
        halign: 'right'
        valign: 'middle'

<TelaCupons>:
    BoxLayout:
        orientation: 'vertical'
        BarraTopo:
            titulo: 'Meus cupons'
            voltar: True
            destino_voltar: 'loja'
        ScrollView:
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
            atual: 'conquistas'
""")

_textura_selo = {}


def textura_selo_estatico():
    """Selo pré-renderizado para a lista (o selo AO VIVO fica só no detalhe, que é mais caro)."""
    if "t" not in _textura_selo:
        _textura_selo["t"] = raster.para_textura(holograma.renderizar(110, -0.45, 0.35))
    return _textura_selo["t"]


class SeloEstatico(Widget):
    textura = ObjectProperty(None, allownone=True)
    ativo = BooleanProperty(True)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.textura = textura_selo_estatico()


class CupomCartao(ButtonBehavior, BoxLayout):
    titulo = StringProperty("")
    detalhe = StringProperty("")
    status = StringProperty("")
    ativo = BooleanProperty(True)


def _texto(texto, tam=14, cor=None, negrito=False, alinhar="left", altura=None):
    rot = Label(text=texto, markup=True, font_size=sp(tam), bold=negrito, color=cor or rgba(CORES["texto"]),
                halign=alinhar, valign="middle", size_hint_y=None)
    rot.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
             texture_size=lambda w, v: setattr(w, "height", altura or v[1]))
    return rot


class DetalheCupom(ModalView):
    """Cupom aberto: selo holográfico AO VIVO + código + modo caixa."""

    def __init__(self, c, **kw):
        super().__init__(size_hint=(0.92, None), height=dp(590) if c.get("motivo") else dp(520),
                         background="", background_color=(0, 0, 0, 0),
                         overlay_color=(0.05, 0.06, 0.08, 0.6), **kw)
        self.c = c
        caixa = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(8))
        with caixa.canvas.before:
            Color(1, 1, 1, 1)
            fundo = RoundedRectangle(radius=[dp(22)])
        caixa.bind(pos=lambda w, *_: setattr(fundo, "pos", w.pos), size=lambda w, *_: setattr(fundo, "size", w.size))
        self.selo = SeloHolografico(size_hint_y=None, height=dp(180), resolucao=200)
        caixa.add_widget(self.selo)
        caixa.add_widget(_texto("Incline o celular: o selo muda de cor. Um print de tela fica parado. "
                                "(No computador, mova o mouse.)", 11, rgba(CORES["texto2"]), alinhar="center"))
        caixa.add_widget(_texto(f"[b]{c['titulo']}[/b]", 18, alinhar="center"))
        caixa.add_widget(_texto(c.get("parceiro") or "", 12, rgba(CORES["texto2"]), alinhar="center"))
        codigo = Label(text=f"[b]{c.get('codigo') or ''}[/b]", markup=True, font_size=sp(26),
                       font_name="RobotoMono-Regular", color=rgba(CORES["texto"]), size_hint_y=None, height=dp(40))
        caixa.add_widget(codigo)
        caixa.add_widget(_texto(f"Válido até {servidor.data_br(c.get('valido_ate'))}", 12, rgba(CORES["texto2"]),
                                alinhar="center"))
        if c.get("motivo"):
            caixa.add_widget(_texto(f"[b]Por que este cupom?[/b] {c['motivo']}", 12, rgba(CORES["dourado_claro"])))
        caixa.add_widget(Widget())
        linha = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        self.b_normais = Factory.BotaoContorno(text="Ver mapa de normais", height=dp(44))
        self.b_normais.bind(on_release=self._alternar_normais)
        caixa_b = Factory.BotaoVertis(text="Modo caixa: validar", height=dp(44))
        caixa_b.bind(on_release=lambda *_: self._validar())
        linha.add_widget(self.b_normais)
        linha.add_widget(caixa_b)
        caixa.add_widget(linha)
        fechar = Factory.BotaoLink(text="Fechar")
        fechar.bind(on_release=lambda *_: self.dismiss())
        caixa.add_widget(fechar)
        self.add_widget(caixa)

    def _alternar_normais(self, *_):
        self.selo.mostrar_normais = not self.selo.mostrar_normais
        self.b_normais.text = "Ver holograma" if self.selo.mostrar_normais else "Ver mapa de normais"

    def _validar(self):
        def r(res):
            if res["valido"]:
                aviso(f"Caixa: {res['motivo']} (assinatura {res['assinatura_inicio']}…)")
            else:
                aviso(f"Caixa: {res['motivo']}", erro=True)
        servidor.get(f"/cupons/validar/{self.c['codigo']}?assinatura={self.c.get('assinatura') or ''}",
                     ao_receber=r, ao_falhar=lambda m: aviso(m, erro=True))

    def on_dismiss(self):
        self.selo.parar()


class TelaCupons(TelaVertis):

    def on_pre_enter(self, *_):
        self.carregar()

    def carregar(self):
        servidor.get("/cupons", ao_receber=self._preencher, ao_falhar=lambda m: aviso(m, erro=True))

    # ------------------------------------------------------------ montagem da tela
    def _preencher(self, lista):
        box = self.ids.conteudo
        box.clear_widgets()
        do_mes = next((c for c in lista if c["origem"] == "inteligente" and c["status"] in ("oculto", "revelado")), None)

        box.add_widget(_texto("[b]Cupom do mês[/b]", 16))
        if do_mes is None:
            box.add_widget(_texto("A Vértis olha os seus gastos ESSENCIAIS (mercado, transporte, saúde, educação, "
                                  "contas) e escolhe o desconto que mais faz você economizar. Um por mês.",
                                  12, rgba(CORES["texto2"])))
            b = Factory.BotaoVertis(text="Gerar meu cupom do mês")
            b.bind(on_release=lambda *_: servidor.post("/cupons/do-mes", {}, ao_receber=lambda r: self.carregar(),
                                                       ao_falhar=lambda m: aviso(m, erro=True)))
            box.add_widget(b)
        elif do_mes["status"] == "oculto":
            box.add_widget(self._raspadinha(do_mes))
            box.add_widget(_texto("Escolhido pelos seus gastos essenciais. [b]Não é sorteio[/b]: "
                                  "a raspadinha só revela o que já foi decidido.", 11, rgba(CORES["texto2"])))
        else:
            box.add_widget(self._cartao(do_mes))

        ativos = [c for c in lista if c["status"] == "revelado" and c is not do_mes]
        antigos = [c for c in lista if c["status"] in ("usado", "expirado")]
        if ativos:
            box.add_widget(_texto("[b]Vales da loja[/b]", 16))
            for c in ativos:
                box.add_widget(self._cartao(c))
        if antigos:
            box.add_widget(_texto("[b]Usados e vencidos[/b]", 16))
            for c in antigos:
                box.add_widget(self._cartao(c))
        if not ativos and not antigos and do_mes is None:
            box.add_widget(_texto("Troque seus pontos na loja para ganhar vales.", 12, rgba(CORES["texto2"])))
        como = Factory.BotaoLink(text="Como o cupom inteligente funciona?")
        como.bind(on_release=lambda *_: self.como_funciona())
        box.add_widget(como)

    def _cartao(self, c):
        status = {"revelado": "ATIVO", "usado": "usado", "expirado": "vencido"}.get(c["status"], c["status"])
        detalhe = c.get("parceiro") or ""
        if c["origem"] == "inteligente" and c.get("economia_estimada"):
            detalhe = f"{detalhe}  •  economia de até {servidor.reais(c['economia_estimada'])}"
        w = CupomCartao(titulo=c["titulo"], detalhe=detalhe or "Vértis", status=status, ativo=c["status"] == "revelado")
        if c["status"] == "revelado":
            w.bind(on_release=lambda *_: DetalheCupom(c).open())
        return w

    def _raspadinha(self, c):
        """Conteúdo do cupom EMBAIXO + camada prateada (Raspadinha) EM CIMA."""
        area = FloatLayout(size_hint_y=None, height=dp(190))
        fundo = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(4),
                          pos_hint={"x": 0, "y": 0}, size_hint=(1, 1))
        with fundo.canvas.before:
            Color(*rgba(CORES["amarelo_suave"]))
            r = RoundedRectangle(radius=[dp(16)])
        fundo.bind(pos=lambda w, *_: setattr(r, "pos", w.pos), size=lambda w, *_: setattr(r, "size", w.size))
        titulo = _texto("", 20, negrito=True, alinhar="center")
        parceiro = _texto("", 12, rgba(CORES["texto2"]), alinhar="center")
        motivo = _texto("", 12, rgba(CORES["dourado_claro"]), alinhar="center")
        fundo.add_widget(Widget())
        for w in (titulo, parceiro, motivo):
            fundo.add_widget(w)
        fundo.add_widget(Widget())
        area.add_widget(fundo)
        camada = Raspadinha(pos_hint={"x": 0, "y": 0}, size_hint=(1, 1))
        area.add_widget(camada)
        self._raspadinha_atual = camada

        def primeiro_toque(*_):
            # o cliente começou a raspar: a API registra a revelação e manda o conteúdo
            def revelado(cupom):
                titulo.text = f"[b]{cupom['titulo']}[/b]"
                parceiro.text = f"{cupom.get('parceiro') or ''}  •  código {cupom['codigo']}"
                motivo.text = cupom.get("motivo") or ""
            servidor.post(f"/cupons/{c['id']}/revelar", {}, ao_receber=revelado,
                          ao_falhar=lambda m: aviso(m, erro=True))

        def revelou(*_):
            aviso("Cupom revelado! Toque nele para ver o selo holográfico.")
            Clock.schedule_once(lambda dt: self.carregar(), 1.4)
        camada.bind(on_primeiro_toque=primeiro_toque, on_revelar=revelou)
        return area

    def como_funciona(self):
        servidor.get("/cupons/por-que", ao_receber=lambda r: abrir_formulario(
            "Como o cupom inteligente funciona", [], "Entendi", lambda _v: None, explicacao=(
                "1. A API soma seus gastos dos últimos 60 dias por categoria.\n"
                "2. Só entram categorias ESSENCIAIS (nada de estimular compra por impulso).\n"
                "3. Para cada uma, calcula a economia: gasto × desconto, até o teto.\n"
                f"4. Fica o que mais economiza. Hoje seria: {r['cupom']}.\n\n"
                "Segurança: cada cupom tem uma ASSINATURA digital (HMAC). No caixa, a loja confere "
                "a assinatura; e o selo holográfico, que muda de cor ao inclinar o celular, "
                "denuncia um print copiado.")),
            ao_falhar=lambda m: aviso(m, erro=True))
