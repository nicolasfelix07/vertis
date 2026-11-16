"""
VITRINE 3D DA LOJA — o pipeline gráfico completo
===============================================
Conteúdo da disciplina reunido:

  MODELAGEM        cg/malhas.py monta o objeto (vértices, triângulos, normais)
  TRANSFORMAÇÕES   modelo = Rx · Ry · S (girar com o dedo, "pop" ao trocar de item)
  CÂMERA (vista)   translação que afasta o objeto da câmera
  PROJEÇÃO         perspectiva no formato OpenGL (cg/transformacoes.py)
  ILUMINAÇÃO       Blinn-Phong por pixel (ou Gouraud por vértice) — cg/vitrine.glsl
  VISIBILIDADE     Z-BUFFER da placa de vídeo  ×  ALGORITMO DO PINTOR (ordenar
                   triângulos do mais longe para o mais perto, na CPU)
  ANTIALIASING     superamostragem: desenhamos numa imagem 2x maior e reduzimos

As matrizes são calculadas em Python/NumPy e enviadas para a placa de vídeo,
que só executa as contas que escrevemos no shader.
"""
import math
import os

import numpy as np
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import (Callback, ClearBuffers, ClearColor, Color, Ellipse, Fbo, Mesh, Rectangle)
from kivy.graphics.opengl import GL_DEPTH_TEST, glDisable, glEnable
from kivy.graphics.transformation import Matrix
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget

from cg import malhas, transformacoes as tf

SHADER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vitrine.glsl")
FORMATO = [(b"v_pos", 3, "float"), (b"v_normal", 3, "float"), (b"v_cor", 3, "float")]
SUPERAMOSTRAGEM = 2          # antialiasing: desenha 2x maior e reduz
DIST_CAMERA = 4.2


def para_kivy(m: np.ndarray) -> Matrix:
    """NumPy (linha × coluna) → Matrix do Kivy (o OpenGL lê por colunas)."""
    k = Matrix()
    k.set(flat=[float(x) for x in np.asarray(m, float).T.flatten()])
    return k


class Vitrine3D(Widget):
    modelo = StringProperty("moeda")
    cor = StringProperty("")
    zbuffer = BooleanProperty(True)        # False = algoritmo do pintor
    por_pixel = BooleanProperty(True)      # True = Phong, False = Gouraud
    aramado = BooleanProperty(False)
    girar_sozinho = BooleanProperty(True)
    angulo_x = NumericProperty(-0.35)
    angulo_y = NumericProperty(0.5)
    escala = NumericProperty(1.0)
    sombra = BooleanProperty(True)

    def __init__(self, **kw):
        super().__init__(**kw)
        self._fbo = None
        self._dados = None
        self._arrastando = False
        self._parado = 0.0
        with self.canvas:
            self._cor_sombra = Color(0, 0, 0, 0.10)
            self._sombra = Ellipse()
            Color(1, 1, 1, 1)
            self._ret = Rectangle()
        self.bind(size=self._recriar, pos=self._posicionar, modelo=self._trocar_modelo, cor=self._trocar_modelo,
                  aramado=self._atualizar_indices, sombra=self._posicionar)
        self._carregar_malha()
        self._evento = Clock.schedule_interval(self._quadro, 1 / 30)

    # ------------------------------------------------------------- malha
    def _carregar_malha(self):
        m = malhas.construir(self.modelo, self.cor or None)
        v, n, c, f = m.arrays()
        self._v, self._f = v, f
        self._centro_tri = (v[f[:, 0]] + v[f[:, 1]] + v[f[:, 2]]) / 3
        self._vertices = np.hstack([v, n, c]).astype(np.float32).flatten().tolist()
        self._tri = f.flatten().tolist()
        self._arestas = m.arestas()
        # tamanho do objeto → escala para caber na vitrine
        self._ajuste = 1.25 / max(0.6, float(np.abs(v).max()))
        if self._fbo is not None:
            self._mesh.vertices = self._vertices
            self._atualizar_indices()

    def _trocar_modelo(self, *_):
        self._carregar_malha()
        self.angulo_x, self.angulo_y = -0.3, 0.55   # ângulo bom para mostrar o item
        self.escala = 0.05            # TRANSFORMAÇÃO DE ESCALA animada: o item "pula" na tela
        Animation(escala=1.0, d=0.55, t="out_back").start(self)

    def _atualizar_indices(self, *_):
        if self._fbo is None:
            return
        if self.aramado:
            self._mesh.mode = "lines"
            self._mesh.indices = self._arestas
        else:
            self._mesh.mode = "triangles"
            self._mesh.indices = self._tri

    # ------------------------------------------------------------- Fbo (imagem fora da tela)
    def _recriar(self, *_):
        w, h = int(self.width * SUPERAMOSTRAGEM), int(self.height * SUPERAMOSTRAGEM)
        if w < 8 or h < 8:
            return
        lado = min(w, h, 1400)
        self._fbo = Fbo(size=(lado, lado), with_depthbuffer=True)
        self._fbo.shader.source = SHADER
        with self._fbo:
            self._cb_profundidade = Callback(self._ligar_profundidade)
            ClearColor(0, 0, 0, 0)
            ClearBuffers(clear_color=True, clear_depth=True)
            self._mesh = Mesh(vertices=self._vertices, indices=self._tri, fmt=FORMATO, mode="triangles")
            Callback(lambda *_: glDisable(GL_DEPTH_TEST))
        self._atualizar_indices()
        self._posicionar()

    def _ligar_profundidade(self, *_):
        if self.zbuffer:
            glEnable(GL_DEPTH_TEST)     # Z-BUFFER LIGADO: a placa de vídeo compara a profundidade de cada pixel
        else:
            glDisable(GL_DEPTH_TEST)    # PINTOR: vale o que foi desenhado por último

    def _posicionar(self, *_):
        lado = min(self.width, self.height)
        self._ret.size = (lado, lado)
        self._ret.pos = (self.x + (self.width - lado) / 2, self.y + (self.height - lado) / 2)
        self._sombra.size = (lado * 0.55, lado * 0.07)
        self._sombra.pos = (self.x + self.width / 2 - lado * 0.275, self.y + lado * 0.04)
        self._cor_sombra.a = 0.10 if self.sombra else 0

    # ------------------------------------------------------------- matrizes
    def matriz_modelo(self) -> np.ndarray:
        s = self._ajuste * self.escala
        return tf.compor(tf.rotacao_x(self.angulo_x), tf.rotacao_y(self.angulo_y), tf.escala3d(s))

    def _quadro(self, dt):
        if self._fbo is None:
            return
        if not self._arrastando:
            self._parado += dt
            if self.girar_sozinho and self._parado > 1.5:
                self.angulo_y += dt * 0.7
        M = self.matriz_modelo()
        V = tf.translacao3d(0, 0, -DIST_CAMERA)
        P = tf.perspectiva_opengl(math.radians(38), 1.0, 0.5, 20)
        f = self._fbo
        f["modelo"] = para_kivy(M)
        f["vista"] = para_kivy(V)
        f["projecao"] = para_kivy(P)
        f["normal_mat"] = para_kivy(V @ tf.matriz_normal(M))
        f["luz"] = (-0.45, 0.65, 0.75)
        f["por_pixel"] = 1.0 if self.por_pixel else 0.0

        if not self.zbuffer and not self.aramado:
            # ALGORITMO DO PINTOR: ordena os triângulos do mais LONGE para o mais PERTO
            z = tf.aplicar3d(V @ M, self._centro_tri)[:, 2]
            ordem = np.argsort(z)                     # z mais negativo = mais longe
            self._mesh.indices = self._f[ordem].flatten().tolist()
        elif not self.aramado and self._mesh.indices != self._tri:
            self._mesh.indices = self._tri

        f.ask_update()
        f.draw()
        self._ret.texture = f.texture

    # ------------------------------------------------------------- toque
    def on_touch_down(self, t):
        if self.collide_point(*t.pos):
            t.grab(self)
            self._arrastando = True
            return True
        return super().on_touch_down(t)

    def on_touch_move(self, t):
        if t.grab_current is self:
            self.angulo_y += t.dx * 0.012
            self.angulo_x = max(-1.3, min(1.3, self.angulo_x - t.dy * 0.012))
            return True
        return super().on_touch_move(t)

    def on_touch_up(self, t):
        if t.grab_current is self:
            t.ungrab(self)
            self._arrastando = False
            self._parado = 0
            return True
        return super().on_touch_up(t)

    def parar(self):
        self._evento.cancel()

    def retomar(self):
        self._evento.cancel()
        self._evento = Clock.schedule_interval(self._quadro, 1 / 30)
