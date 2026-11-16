"""
SCANNER DE CONTAS — TRANSFORMAÇÃO PROJETIVA (HOMOGRAFIA)
========================================================
Problema que resolve: contas de luz, água e celular pagas em dia AJUDAM O
SCORE (é o histórico que quem nunca teve cartão já tem). Mas a foto da
conta tirada com o celular sai TORTA: a folha vira um trapézio.

Solução: uma HOMOGRAFIA — a transformação projetiva que leva os 4 cantos
do trapézio da foto para os 4 cantos de um retângulo. É uma matriz 3x3
em coordenadas homogêneas:

        [x']   [h11 h12 h13] [u]          x = x' / w'
        [y'] = [h21 h22 h23] [v]    →     y = y' / w'      (divisão por w!)
        [w']   [h31 h32  1 ] [1]

São 8 incógnitas; cada canto dá 2 equações → 4 cantos = 8 equações.
Resolvemos o sistema linear com NumPy.

Para montar a imagem corrigida fazemos o MAPEAMENTO INVERSO: para cada
pixel (u, v) do retângulo final, a matriz diz de onde ele vem na foto
(x, y) — e como (x, y) quase nunca cai bem no centro de um pixel, fazemos
INTERPOLAÇÃO BILINEAR (a mesma ideia do mapeamento de textura).

Bônus: DETECÇÃO AUTOMÁTICA DOS CANTOS — aprendemos a cor da mesa pela borda
da foto, separamos o que é "folha" e pegamos os pontos extremos.
"""
import numpy as np


def calcular_homografia(origem, destino) -> np.ndarray:
    """Matriz H (3x3) que leva cada ponto de `origem` ao ponto correspondente de `destino`."""
    A, b = [], []
    for (x, y), (u, v) in zip(origem, destino):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(b, float))
    return np.append(h, 1.0).reshape(3, 3)


def aplicar(H, pontos) -> np.ndarray:
    p = np.asarray(pontos, float)
    hom = np.hstack([p, np.ones((len(p), 1))]) @ H.T
    return hom[:, :2] / hom[:, 2:3]          # divisão por w (é isto que faz a "perspectiva")


def retificar(imagem: np.ndarray, cantos, largura: int, altura: int):
    """imagem: matriz (altura, largura, 4) com a linha 0 EMBAIXO (padrão do Kivy).
    cantos: (inf-esq, inf-dir, sup-dir, sup-esq) em pixels da imagem.
    Devolve (imagem_corrigida, H)."""
    retangulo = [(0, 0), (largura - 1, 0), (largura - 1, altura - 1), (0, altura - 1)]
    H = calcular_homografia(retangulo, cantos)          # MAPEAMENTO INVERSO: saída → foto
    v, u = np.mgrid[0:altura, 0:largura].astype(np.float64)
    den = H[2, 0] * u + H[2, 1] * v + H[2, 2]
    x = (H[0, 0] * u + H[0, 1] * v + H[0, 2]) / den
    y = (H[1, 0] * u + H[1, 1] * v + H[1, 2]) / den
    # INTERPOLAÇÃO BILINEAR: mistura os 4 pixels vizinhos conforme a distância
    hi, wi = imagem.shape[:2]
    x = np.clip(x, 0, wi - 1.001)
    y = np.clip(y, 0, hi - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    img = imagem.astype(np.float32)
    topo = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    baixo = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    saida = topo * (1 - fy) + baixo * fy
    saida[..., 3] = 255
    return saida.astype(np.uint8), np.linalg.inv(H)      # devolve H no sentido foto → retângulo


def _otsu(cinza: np.ndarray) -> float:
    """Limiar de Otsu: o tom que melhor separa os pixels em 2 grupos (folha × mesa)."""
    hist, _ = np.histogram(cinza, bins=256, range=(0, 256))
    total = cinza.size
    soma_total = np.dot(np.arange(256), hist)
    melhor, limiar, peso_f, soma_f = 0, 128, 0, 0
    for t in range(256):
        peso_f += hist[t]
        if peso_f == 0 or peso_f == total:
            continue
        soma_f += t * hist[t]
        m_f = soma_f / peso_f
        m_b = (soma_total - soma_f) / (total - peso_f)
        entre = peso_f * (total - peso_f) * (m_f - m_b) ** 2
        if entre > melhor:
            melhor, limiar = entre, t
    return limiar


def detectar_cantos(imagem: np.ndarray):
    """Acha os 4 cantos da folha sobre a mesa.
    1) Aprende a COR DO FUNDO olhando a borda da foto (a folha não encosta na borda).
    2) Pixel cuja cor é bem diferente do fundo = folha (vale para folha branca e para o
       cabeçalho colorido da conta).
    3) Limpa o ruído e pega os pontos extremos: o canto inferior-esquerdo é o que tem
       a MENOR soma x + y, o superior-direito a MAIOR, e assim por diante."""
    passo = max(1, max(imagem.shape[:2]) // 400)      # trabalha numa versão reduzida (mais rápido)
    peq = imagem[::passo, ::passo, :3].astype(np.float32)
    h, w = peq.shape[:2]
    m = max(2, int(min(h, w) * 0.03))
    borda = np.concatenate([peq[:m].reshape(-1, 3), peq[-m:].reshape(-1, 3),
                            peq[:, :m].reshape(-1, 3), peq[:, -m:].reshape(-1, 3)])
    media, desvio = borda.mean(axis=0), borda.std(axis=0) + 8
    distancia = np.sqrt((((peq - media) / desvio) ** 2).sum(axis=2))
    folha = distancia > 3.0
    if folha.mean() < 0.05:                            # fundo parecido com a folha: tenta pelo brilho
        cinza = peq @ np.array([0.299, 0.587, 0.114])
        folha = cinza > _otsu(cinza)
    viz = folha.copy()                                  # erosão: só fica pixel cercado de "folha"
    for dy in (-2, 0, 2):
        for dx in (-2, 0, 2):
            viz &= np.roll(np.roll(folha, dy, 0), dx, 1)
    ys, xs = np.nonzero(viz)
    if len(xs) < 50:
        return None
    s, d = xs + ys, xs - ys        # y cresce para CIMA (padrão do Kivy)
    inf_esq = (xs[np.argmin(s)], ys[np.argmin(s)])
    sup_dir = (xs[np.argmax(s)], ys[np.argmax(s)])
    inf_dir = (xs[np.argmax(d)], ys[np.argmax(d)])
    sup_esq = (xs[np.argmin(d)], ys[np.argmin(d)])
    return [(float(x * passo), float(y * passo)) for x, y in (inf_esq, inf_dir, sup_dir, sup_esq)]


def formatar(H) -> str:
    H = H / H[2, 2]
    return "\n".join("[ " + "  ".join(f"{v:9.4f}" for v in linha) + " ]" for linha in H)
