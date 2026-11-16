"""
MODELAGEM 3D PROCEDURAL — os objetos da vitrine da loja
======================================================
Conteúdo da disciplina: definição de objetos e cenas 3D.

Uma MALHA (mesh) é:
  • uma lista de VÉRTICES (pontos x, y, z)
  • uma lista de TRIÂNGULOS (cada um = 3 índices de vértices)
  • uma NORMAL por vértice (vetor perpendicular à superfície → iluminação)
  • uma COR por vértice

Não usamos arquivos de modelo prontos: cada objeto é CALCULADO a partir de
formas básicas (caixa, cilindro, toro), com seno e cosseno — e depois
juntado. Ex.: o fone = meio toro (arco) + 2 cilindros (conchas).

Arestas "duras" (caixa) têm vértices repetidos por face (normal reta);
superfícies "lisas" (cilindro, toro) compartilham vértices (normal suave).
"""
import math

import numpy as np

from cg import transformacoes as tf


def _rgb(cor):
    cor = cor.lstrip("#")
    return [int(cor[i:i + 2], 16) / 255 for i in (0, 2, 4)]


class Malha:
    def __init__(self):
        self.v, self.n, self.c, self.f = [], [], [], []

    def _base(self):
        return len(self.v)

    def juntar(self, outra: "Malha", matriz=None):
        """Acrescenta outra malha (opcionalmente transformada por uma matriz 4x4)."""
        base = self._base()
        v = np.asarray(outra.v, float)
        n = np.asarray(outra.n, float)
        if matriz is not None:
            v = tf.aplicar3d(matriz, v)
            n = n @ tf.matriz_normal(matriz)[:3, :3].T
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
        self.v += v.tolist()
        self.n += n.tolist()
        self.c += list(outra.c)
        self.f += [(a + base, b + base, c + base) for a, b, c in outra.f]
        return self

    # ---------------------------------------------------------- saída
    def arrays(self):
        v = np.asarray(self.v, np.float32)
        n = np.asarray(self.n, np.float32)
        c = np.asarray(self.c, np.float32)
        f = np.asarray(self.f, np.int32)
        # Garante a ORIENTAÇÃO dos triângulos (sentido anti-horário visto de fora):
        # se a normal geométrica aponta contra as normais dos vértices, inverte.
        geo = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        media = n[f[:, 0]] + n[f[:, 1]] + n[f[:, 2]]
        inverter = (geo * media).sum(axis=1) < 0
        f[inverter] = f[inverter][:, [0, 2, 1]]
        return v, n, c, f

    def arestas(self):
        """Pares de vértices de cada aresta (para o modo aramado / wireframe)."""
        pares = set()
        for a, b, c in self.f:
            for p, q in ((a, b), (b, c), (c, a)):
                pares.add((min(p, q), max(p, q)))
        return [i for par in sorted(pares) for i in par]


# =====================================================================
# Formas básicas
# =====================================================================
def caixa(sx, sy, sz, cor, centro=(0, 0, 0)) -> Malha:
    """Paralelepípedo: 6 faces, cada uma com 4 vértices próprios (normal reta)."""
    m = Malha()
    rgb = _rgb(cor)
    cx, cy, cz = centro
    meia = (sx / 2, sy / 2, sz / 2)
    for eixo in range(3):
        for sinal in (-1, 1):
            normal = [0, 0, 0]
            normal[eixo] = sinal
            u, w = (eixo + 1) % 3, (eixo + 2) % 3
            base = m._base()
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = [0.0, 0.0, 0.0]
                p[eixo] = sinal * meia[eixo]
                p[u] = a * meia[u]
                p[w] = b * meia[w]
                m.v.append([p[0] + cx, p[1] + cy, p[2] + cz])
                m.n.append(normal)
                m.c.append(rgb)
            m.f += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return m


def cilindro(raio, altura, cor, segmentos=28, tampas=True, cor_tampa=None) -> Malha:
    """Cilindro em pé (eixo y). Lateral: x = r·cos θ, z = r·sen θ."""
    m = Malha()
    rgb, rgb_t = _rgb(cor), _rgb(cor_tampa or cor)
    h = altura / 2
    for i in range(segmentos):
        t = 2 * math.pi * i / segmentos
        x, z = math.cos(t), math.sin(t)
        for y in (-h, h):
            m.v.append([raio * x, y, raio * z])
            m.n.append([x, 0, z])
            m.c.append(rgb)
    for i in range(segmentos):
        a, b = 2 * i, 2 * ((i + 1) % segmentos)
        m.f += [(a, a + 1, b + 1), (a, b + 1, b)]
    if tampas:
        for y, ny in ((-h, -1), (h, 1)):
            centro = m._base()
            m.v.append([0, y, 0]); m.n.append([0, ny, 0]); m.c.append(rgb_t)
            for i in range(segmentos):
                t = 2 * math.pi * i / segmentos
                m.v.append([raio * math.cos(t), y, raio * math.sin(t)]); m.n.append([0, ny, 0]); m.c.append(rgb_t)
            for i in range(segmentos):
                m.f.append((centro, centro + 1 + i, centro + 1 + (i + 1) % segmentos))
    return m


def toro(R, r, cor, seg_grande=32, seg_pequeno=12, arco=2 * math.pi) -> Malha:
    """Toro ("rosquinha") no plano xy:
       P(θ, φ) = ((R + r·cos φ)·cos θ, (R + r·cos φ)·sen θ, r·sen φ)
    arco < 2π gera só um pedaço (ex.: a haste do fone é meio toro)."""
    m = Malha()
    rgb = _rgb(cor)
    fechado = arco >= 2 * math.pi - 1e-6
    n_aneis = seg_grande if fechado else seg_grande + 1
    for i in range(n_aneis):
        th = arco * i / seg_grande
        for j in range(seg_pequeno):
            ph = 2 * math.pi * j / seg_pequeno
            nx, ny, nz = math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph)
            m.v.append([(R + r * math.cos(ph)) * math.cos(th), (R + r * math.cos(ph)) * math.sin(th), r * math.sin(ph)])
            m.n.append([nx, ny, nz])
            m.c.append(rgb)
    for i in range(seg_grande):
        i2 = (i + 1) % n_aneis
        for j in range(seg_pequeno):
            j2 = (j + 1) % seg_pequeno
            a, b = i * seg_pequeno + j, i2 * seg_pequeno + j
            c, d = i2 * seg_pequeno + j2, i * seg_pequeno + j2
            m.f += [(a, b, c), (a, c, d)]
    return m


# =====================================================================
# Objetos da loja (cada um = formas básicas + transformações)
# =====================================================================
T, Rx, Ry, Rz, S = tf.translacao3d, tf.rotacao_x, tf.rotacao_y, tf.rotacao_z, tf.escala3d


def celular(cor="#2B2F36") -> Malha:
    m = Malha()
    m.juntar(caixa(1.0, 1.95, 0.12, cor))
    m.juntar(caixa(0.88, 1.7, 0.02, "#1D4ED8", centro=(0, 0.04, 0.065)))        # tela
    m.juntar(caixa(0.5, 0.22, 0.01, "#F5B700", centro=(0, 0.45, 0.077)))        # "app Vértis" na tela
    m.juntar(cilindro(0.08, 0.03, "#111318", 16), T(0.28, 0.75, -0.07) @ Rx(math.pi / 2))   # câmera
    return m


def cartao_transporte(cor="#1E8E4E") -> Malha:
    m = Malha()
    m.juntar(caixa(1.7, 1.07, 0.05, cor))
    m.juntar(caixa(1.7, 0.18, 0.012, "#FFFFFF", centro=(0, 0.22, 0.031)))     # faixa branca
    m.juntar(cilindro(0.16, 0.012, "#F5B700", 20), T(-0.55, -0.22, 0.031) @ Rx(math.pi / 2))  # símbolo
    return m


def livro(cor="#0E7490") -> Malha:
    m = Malha()
    m.juntar(caixa(1.25, 1.7, 0.06, cor, centro=(0, 0, 0.17)))      # capa da frente
    m.juntar(caixa(1.25, 1.7, 0.06, cor, centro=(0, 0, -0.17)))     # capa de trás
    m.juntar(caixa(0.08, 1.7, 0.4, cor, centro=(-0.62, 0, 0)))      # lombada
    m.juntar(caixa(1.17, 1.62, 0.28, "#F3F4F6", centro=(0.03, 0, 0)))   # páginas
    m.juntar(caixa(0.7, 0.14, 0.01, "#F5B700", centro=(0.05, 0.45, 0.205)))  # título
    return m


def sacola(cor="#D99A00") -> Malha:
    m = Malha()
    m.juntar(caixa(1.3, 1.25, 0.6, cor, centro=(0, -0.25, 0)))
    m.juntar(caixa(1.32, 0.12, 0.62, "#8A6400", centro=(0, 0.3, 0)))        # dobra
    for z in (0.18, -0.18):                                                  # alças (meio toro)
        m.juntar(toro(0.32, 0.035, "#2B2F36", 16, 8, arco=math.pi), T(0, 0.36, z))
    return m


def fone(cor="#2B2F36") -> Malha:
    """Haste = meio toro; conchas = cilindros deitados. As pontas da haste
    ENTRAM nas conchas: ótimo para ver o z-buffer resolvendo a interseção
    (e o algoritmo do pintor errando)."""
    m = Malha()
    m.juntar(toro(0.82, 0.07, cor, 28, 10, arco=math.pi), T(0, -0.15, 0))
    for x in (-0.82, 0.82):
        m.juntar(cilindro(0.34, 0.26, "#F5B700", 28, cor_tampa=cor), T(x, -0.32, 0) @ Rz(math.pi / 2))
        m.juntar(cilindro(0.26, 0.1, "#111318", 24), T(x * 0.86, -0.32, 0) @ Rz(math.pi / 2))   # almofada
    return m


def mochila(cor="#F5B700") -> Malha:
    m = Malha()
    m.juntar(caixa(1.2, 1.5, 0.55, cor))
    m.juntar(caixa(0.9, 0.6, 0.22, "#D99A00", centro=(0, -0.35, 0.37)))      # bolso
    m.juntar(caixa(0.9, 0.05, 0.02, "#2B2F36", centro=(0, -0.05, 0.48)))     # zíper
    m.juntar(toro(0.22, 0.05, "#2B2F36", 14, 8, arco=math.pi), T(0, 0.75, 0))  # alça de mão
    for x in (-0.35, 0.35):                                                   # alças das costas
        m.juntar(caixa(0.14, 1.2, 0.06, "#2B2F36", centro=(x, 0, -0.31)))
    return m


def moeda(cor="#F5B700") -> Malha:
    m = Malha()
    m.juntar(cilindro(0.9, 0.18, cor, 40, cor_tampa="#FFD24D"), Rx(math.pi / 2))
    for z in (0.09, -0.09):
        m.juntar(toro(0.78, 0.04, "#D99A00", 40, 8), T(0, 0, z))
    return m


MODELOS = {"celular": celular, "cartao_transporte": cartao_transporte, "livro": livro, "sacola": sacola,
           "fone": fone, "mochila": mochila, "moeda": moeda}


def construir(nome: str, cor: str | None = None) -> Malha:
    f = MODELOS.get(nome, moeda)
    return f(cor) if cor else f()
