"""Boneco v2: o personagem desenhado direto numa grade de 128 x 160 (o dobro de pixels do v1).

Estilo (pedido do Natan, a partir de exemplos em pixel art): proporção chibi (a cabeça é quase metade da altura),
contorno escuro em volta de cada peça, cabelo com volume, textura e brilho, barba com textura, olhos com
branco, íris e brilho, óculos de armação grossa, tênis branco e sombreamento em três tons (luz quente em cima e
à esquerda, sombra fria embaixo e à direita).

O desenho é feito com formas (elipses, polígonos, máscaras) numa camada de cor e outra de "material" (pele,
cabelo, roupa...). Depois vêm a luz e sombra por material, o rosto e o contorno. As escolhas do criador
(cfg) são as mesmas do v1 (aprova/avatar.py).
"""


from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from . import avatar as av

W, H = 128, 160
CX = 64
CHAO = 152  # sola do tênis

# materiais (os mesmos números do v1) + os que só existem aqui
M_VAZIO, M_PELE, M_CABELO, M_ROUPA, M_CALCA, M_BOTA, M_METAL, M_ACESS, M_OCULOS, M_ITEM, M_EXTRA, M_ROSTO = range(12)
M_BARBA, M_SOLA, M_DETALHE, M_MANGA = 12, 13, 14, 15

# quem fica na frente de quem: o contorno entre duas peças é desenhado do lado da peça de trás
FRENTE = {M_OCULOS: 10, M_ACESS: 9, M_CABELO: 8, M_BARBA: 8, M_ITEM: 8, M_EXTRA: 7, M_DETALHE: 7, M_MANGA: 6.5, M_ROUPA: 6,
          M_PELE: 5, M_CALCA: 4, M_SOLA: 3, M_BOTA: 3, M_METAL: 6}

CONTORNO = (24, 18, 34, 255)

# medidas do corpo por tipo (meia largura): ombro, cintura, quadril, braço e perna
CORPO = {
    "magro": {"ombro": 22, "cintura": 17, "quadril": 17, "braco": 8, "perna": 9},
    "medio": {"ombro": 25, "cintura": 20, "quadril": 20, "braco": 9, "perna": 10},
    "forte": {"ombro": 29, "cintura": 22, "quadril": 21, "braco": 11, "perna": 11},
    "gordinho": {"ombro": 28, "cintura": 27, "quadril": 25, "braco": 10, "perna": 12},
}

# cabeça (superelipse) e rosto
CAB_CY, CAB_RX, CAB_RY = 51, 24, 25
OLHO_Y, OLHO_DX = 56, 10
BOCA_Y = 69
OMBRO_Y = 80
CINTURA_Y = 119


def _hex(h: str):
    return av._rgb(h)


def mistura(a, b, t):
    return av._mistura(a, b, t)


def escura(c, t):
    return av._escura(c, t)


def clara(c, t):
    return av._clara(c, t)


def fria(c, t):
    return av._fria(c, t)


def quente(c, t):
    return av._quente(c, t)


class Lousa:
    """Uma camada de cor e uma de material, do mesmo tamanho, desenhadas juntas."""

    def __init__(self):
        self.cor = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.mat = Image.new("L", (W, H), 0)
        self._dc = ImageDraw.Draw(self.cor)
        self._dm = ImageDraw.Draw(self.mat)
        self.pc = self.cor.load()
        self.pm = self.mat.load()
        self.rel = [[0.0] * W for _ in range(H)]  # relevo extra (cachos, fios, dobras), somado ao volume da peça
        self.relmat = [[-1] * W for _ in range(H)]  # de que peça é o relevo (o que for pintado por cima não herda)

    def relevo(self, caixa, f):
        """Soma relevo f(x, y) nos pixels já pintados da caixa (f devolve None para não mexer)."""
        x0, y0, x1, y1 = caixa
        for y in range(max(0, y0), min(H, y1 + 1)):
            for x in range(max(0, x0), min(W, x1 + 1)):
                v = f(x, y)
                if v is not None:
                    self.rel[y][x] = v
                    self.relmat[y][x] = self.pm[x, y]

    def elipse(self, caixa, cor, mat):
        self._dc.ellipse(caixa, fill=cor)
        self._dm.ellipse(caixa, fill=mat)

    def poligono(self, pts, cor, mat):
        self._dc.polygon(pts, fill=cor)
        self._dm.polygon(pts, fill=mat)

    def ret(self, caixa, cor, mat, raio=0):
        if raio:
            self._dc.rounded_rectangle(caixa, raio, fill=cor)
            self._dm.rounded_rectangle(caixa, raio, fill=mat)
        else:
            self._dc.rectangle(caixa, fill=cor)
            self._dm.rectangle(caixa, fill=mat)

    def linha(self, pts, cor, mat, largura=1):
        self._dc.line(pts, fill=cor, width=largura)
        self._dm.line(pts, fill=mat, width=largura)

    def p(self, x, y, cor, mat=None):
        if 0 <= x < W and 0 <= y < H:
            self.pc[x, y] = cor[:4] if len(cor) == 4 else cor + (255,)
            if mat is not None:
                self.pm[x, y] = mat

    def mascara(self, caixa, dentro, cor, mat):
        """Pinta os pixels da caixa para os quais dentro(x, y) é verdadeiro (cor pode ser função de x, y)."""
        x0, y0, x1, y1 = caixa
        for y in range(max(0, y0), min(H, y1 + 1)):
            for x in range(max(0, x0), min(W, x1 + 1)):
                if dentro(x, y):
                    self.pc[x, y] = cor(x, y) if callable(cor) else cor
                    self.pm[x, y] = mat

    def tem(self, x, y, *mats):
        return 0 <= x < W and 0 <= y < H and self.pc[x, y][3] and (not mats or self.pm[x, y] in mats)



# ---------------------------------------------------------------------------------------- formas

def na_cabeca(x, y, folga=0.0):
    """Superelipse da cabeça, com o queixo mais estreito."""
    dy = (y + 0.5 - CAB_CY) / (CAB_RY + folga)
    rx = CAB_RX + folga
    if dy > 0:
        rx *= 1 - 0.22 * dy * dy
    dx = (x + 0.5 - CX) / rx
    return abs(dx) ** 2.4 + abs(dy) ** 2.4 <= 1


def _paleta(cfg):
    pele = _hex(av.PELES[cfg["pele"]][0])
    cab = _hex(av.CORES_CABELO[cfg["cor_cabelo"]][0])
    roupa = _hex(av.CORES_ROUPA[cfg["cor_roupa"]][0])
    calca = _hex(av.CORES_CALCA[cfg.get("cor_calca", 0)][0])
    return {
        "pele": pele, "cab": cab, "cab_l": quente(clara(cab, 0.35), 0.15),
        "olho": _hex(av.CORES_OLHOS[cfg["cor_olhos"]][0]),
        "roupa": roupa, "roupa_e": escura(roupa, 0.25) if av._luz(roupa) > 0.18 else clara(roupa, 0.12), "calca": calca,
        "tenis": (240, 241, 246, 255), "sola": (170, 176, 192, 255),
    }


# ---------------------------------------------------------------------------------------- corpo

def _medidas(cfg):
    return CORPO.get(cfg["corpo"], CORPO["medio"])


def _bracos(t: Lousa, cfg, pal, m, d, mat=M_PELE, cor=None, ate=None):
    """Os dois braços caídos ao lado do corpo, com o cotovelo um pouco para fora; ate = até onde desenhar (manga)."""
    cor = cor or pal["pele"]
    o, b = m["ombro"], m["braco"]
    for lado in (-1, 1):
        def X(v):
            return CX + lado * v
        pts = [(X(o - 5), OMBRO_Y + d), (X(o + 1), OMBRO_Y + 3 + d), (X(o + 3), 101 + d), (X(o + 1), 116 + d),
               (X(o - b + 2), 116 + d), (X(o - b + 2), 101 + d), (X(o - b + 1), 90 + d)]
        if ate is not None:  # só o pedaço de cima (a manga)
            corte = ate + d
            pts = [(X(o - 5), OMBRO_Y - 1 + d), (X(o + 1), OMBRO_Y + 2 + d), (X(o + 3), corte), (X(o - b + 1), corte), (X(o - b + 1), 90 + d)]
        t.poligono(pts, cor, mat)
        if ate is None:  # mão
            hx = CX + lado * (o - b / 2 + 2)
            t.elipse((hx - 5, 113 + d, hx + 5, 123 + d), pal["pele"], M_PELE)


def _corpo(t: Lousa, cfg, pal, d: int):
    """Tênis, calça, tronco e braços (d = quanto o tronco desce ao respirar)."""
    m = _medidas(cfg)
    calca = pal["calca"]
    q, perna = m["quadril"], m["perna"]
    # calça: duas pernas retas e largas, unidas em cima
    for lado in (-1, 1):
        x_fora = CX + lado * (q + 1)
        t.poligono([(CX, CINTURA_Y - 2 + d), (x_fora - lado, CINTURA_Y - 2 + d), (x_fora, 144), (CX + lado * 1, 144), (CX + lado * 1, 127 + d)],
                   calca, M_CALCA)
    # tênis
    for lado in (-1, 1):
        cx = CX + lado * (q // 2 + 1)
        t.ret((cx - 9, 141, cx + 9, CHAO), pal["tenis"], M_BOTA, raio=5)
        t.ret((cx - 9, CHAO - 3, cx + 9, CHAO), pal["sola"], M_SOLA, raio=2)
        for k in (-3, 0, 3):  # cadarço
            t.p(cx + k - lado, 143, (90, 96, 112, 255), M_DETALHE)
    # tronco
    o, c = m["ombro"], m["cintura"]
    t.poligono([(CX - o + 6, OMBRO_Y - 1 + d), (CX + o - 6, OMBRO_Y - 1 + d), (CX + o - 1, OMBRO_Y + 4 + d), (CX + o, 92 + d),
                (CX + c, CINTURA_Y + 1 + d), (CX - c, CINTURA_Y + 1 + d), (CX - o, 92 + d), (CX - o + 1, OMBRO_Y + 4 + d)], pal["roupa"], M_ROUPA)
    return m


def _dobras(t: Lousa, m, d):
    """Dobras da roupa: rugas que saem da axila e uma na cintura (só relevo; a luz desenha)."""
    def f(x, y):
        if t.pm[x, y] != M_ROUPA:
            return None
        yy = y - d
        dx = abs(x + 0.5 - CX)
        v = 0.0
        for k in (0, 7):
            alvo = m["ombro"] - 6 - (yy - 92 - k) * 0.55
            if 92 + k <= yy <= 112 + k and abs(dx - alvo) < 1.2:
                v = -0.5
        if CINTURA_Y - 4 <= yy <= CINTURA_Y - 3:
            v = -0.35
        return v

    t.relevo((CX - 32, 88 + d, CX + 32, CINTURA_Y + 2 + d), f)


def _roupa(t: Lousa, cfg, pal, m, d: int):
    """Mangas, gola e detalhes da roupa (por cima do tronco e dos braços)."""
    roupa, esc = pal["roupa"], pal["roupa_e"]
    tipo = cfg["roupa"]
    o, b = m["ombro"], m["braco"]
    curta = tipo in ("camiseta",)
    sem = tipo in ("regata", "vestido")
    if not sem:
        _bracos(t, cfg, pal, m, d, M_MANGA, roupa, ate=97 if curta else 113)
        for lado in (-1, 1):  # barra da manga
            y = (97 if curta else 113) + d
            for x in range(min(CX + lado * (o - b + 1), CX + lado * (o + 3)), max(CX + lado * (o - b + 1), CX + lado * (o + 3)) + 1):
                if t.tem(x, y - 1, M_MANGA):
                    t.p(x, y - 1, esc, M_MANGA)
                    if not curta:
                        t.p(x, y - 2, esc, M_MANGA)
    _dobras(t, m, d)
    if tipo == "camiseta":
        t.elipse((CX - 9, 74 + d, CX + 9, 86 + d), esc, M_ROUPA)  # gola careca
        t.elipse((CX - 7, 73 + d, CX + 7, 83 + d), pal["pele"], M_PELE)
        if av._luz(roupa) < 0.3:  # estampa pequena no peito, como no exemplo
            ex, ey = CX + 10, 93 + d
            dourado, ouro_e = _hex("#E2B42F"), _hex("#A87A12")
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    r = math.hypot(dx, dy)
                    if 2.6 <= r <= 4.2 or r <= 1.1:
                        t.p(ex + dx, ey + dy, dourado if dy < 1 else ouro_e, M_DETALHE)
    elif tipo == "sueter":
        t.poligono([(CX - 7, OMBRO_Y - 4 + d), (CX + 7, OMBRO_Y - 4 + d), (CX, 92 + d)], pal["pele"], M_PELE)  # decote em V
        t.linha([(CX - 8, OMBRO_Y - 4 + d), (CX, 93 + d), (CX + 8, OMBRO_Y - 4 + d)], esc, M_ROUPA, 2)
        t.ret((CX - m["cintura"], CINTURA_Y - 3 + d, CX + m["cintura"], CINTURA_Y + 1 + d), esc, M_ROUPA)  # barra canelada
    elif tipo == "moletom":
        # capuz caído em volta do pescoço, cordões e bolso canguru
        t.elipse((CX - 13, 73 + d, CX + 13, 89 + d), esc, M_ROUPA)
        t.elipse((CX - 7, 73 + d, CX + 7, 83 + d), pal["pele"], M_PELE)
        branco = (238, 238, 240, 255)
        for lado in (-1, 1):
            t.linha([(CX + lado * 4, 85 + d), (CX + lado * 5, 98 + d)], branco, M_DETALHE)
        t.ret((CX - 12, 104 + d, CX + 12, 116 + d), esc, M_ROUPA, raio=3)
        t.ret((CX - m["cintura"], CINTURA_Y - 3 + d, CX + m["cintura"], CINTURA_Y + 1 + d), esc, M_ROUPA)
    else:
        t.elipse((CX - 8, 74 + d, CX + 8, 84 + d), pal["pele"], M_PELE)


def _pescoco_cabeca(t: Lousa, cfg, pal, d: int):
    pele = pal["pele"]
    t.ret((CX - 7, 70 + d, CX + 7, 84 + d), pele, M_PELE)
    for lado in (-1, 1):  # orelhas
        ex = CX + lado * (CAB_RX + 1)
        t.elipse((ex - 4, 48 + d, ex + 4, 61 + d), pele, M_PELE)
    t.mascara((CX - CAB_RX - 1, CAB_CY - CAB_RY - 1 + d, CX + CAB_RX + 1, CAB_CY + CAB_RY + 1 + d),
              lambda x, y: na_cabeca(x, y - d), pele, M_PELE)
    for lado in (-1, 1):  # dentro da orelha
        ex = CX + lado * (CAB_RX + 2)
        for y in range(52, 58):
            t.p(ex, y + d, fria(escura(pele, 0.18), 0.1), M_ROSTO)


# ---------------------------------------------------------------------------------------- cabelo

def _bolinhas(caixa, passo, raio, envelope, semente):
    """Centros de cachos numa grade com sorteio leve (sempre o mesmo para o mesmo cabelo)."""
    import random

    rnd = random.Random(semente)
    x0, y0, x1, y1 = caixa
    centros = []
    for j, y in enumerate(range(y0, y1 + 1, passo)):
        for x in range(x0 + (passo // 2 if j % 2 else 0), x1 + 1, passo):
            cx, cy = x + rnd.uniform(-1.2, 1.2), y + rnd.uniform(-1.2, 1.2)
            if envelope(cx, cy):
                centros.append((cx, cy, raio * rnd.uniform(0.85, 1.15)))
    return centros


def _pintar_cachos(t: Lousa, centros, cor, mat, sobre=None):
    """Cada cacho é um domo: o relevo dá o volume e a luz faz o resto. A borda fica ondulada."""
    for cx, cy, r in centros:
        for y in range(int(cy - r) - 1, int(cy + r) + 2):
            for x in range(int(cx - r) - 1, int(cx + r) + 2):
                dd = (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2
                if dd <= r * r and (sobre is None or sobre(x, y)) and 0 <= x < W and 0 <= y < H:
                    domo = math.sqrt(max(0.0, 1 - dd / (r * r)))
                    if t.pm[x, y] != mat or not t.pc[x, y][3] or t.relmat[y][x] != mat or domo > t.rel[y][x]:
                        t.p(x, y, cor, mat)
                        t.rel[y][x] = domo
                        t.relmat[y][x] = mat


def _fios(x, yy):
    """Relevo de cabelo liso ou ondulado: mechas largas e fios finos, seguindo a onda."""
    u = (x + 0.5 - CX) + 3.2 * math.sin(yy / 7.0)
    return 0.55 * (0.5 + 0.5 * math.cos(2 * math.pi * u / 11)) + 0.25 * (0.5 + 0.5 * math.cos(2 * math.pi * u / 3.7))



def _cabelo_atras(t: Lousa, cfg, pal, d: int):
    tipo = cfg["cabelo"]
    cab = pal["cab"]
    if tipo == "longo":
        def dentro(x, y):
            yy = y - d
            if yy < 20 or yy > 126:
                return False
            if yy < 46 and not na_cabeca(x, yy, 5 + (yy - 20) * 0.12):
                return False
            onda = 1.8 * math.sin(yy / 3.4) + 1.4 * math.sin(yy / 8.0)
            largura = 33 + onda if yy > 54 else 28 + (yy - 20) * 0.15 + onda * 0.5
            if yy > 112:
                largura -= (yy - 112) * 1.5
            return abs(x + 0.5 - CX) <= largura

        t.mascara((CX - 40, 18 + d, CX + 40, 128 + d), dentro, escura(cab, 0.15), M_CABELO)
        t.relevo((CX - 40, 18 + d, CX + 40, 128 + d), lambda x, y: _fios(x, y - d) if t.tem(x, y, M_CABELO) else None)


def _cabelo_frente(t: Lousa, cfg, pal, d: int):
    tipo = cfg["cabelo"]
    cab = pal["cab"]
    semente = hash((tipo, cfg["cor_cabelo"])) & 0xFFFF
    if tipo == "degrade":
        def envelope(cx, cy):
            yy = cy - d
            dx, dy = (cx - CX) / 25, (yy - 30) / 11
            return dx * dx + dy * dy <= 1 and yy <= 37

        centros = _bolinhas((CX - 26, 16 + d, CX + 26, 40 + d), 4, 3.0, envelope, semente)
        _pintar_cachos(t, centros, cab, M_CABELO)
        t.mascara((CX - CAB_RX, 22 + d, CX + CAB_RX, 37 + d),
                  lambda x, y: na_cabeca(x, y - d) and y - d <= 36 and not t.tem(x, y, M_CABELO), escura(cab, 0.18), M_CABELO)
        # laterais raspadas: pele com a sombra do cabelo, escurecendo para cima, com o canto da testa reto
        pele = pal["pele"]

        def lado(x, y):
            yy = y - d
            dx = abs(x + 0.5 - CX)
            return 33 < yy <= 54 and dx >= 18 and na_cabeca(x, yy) and not t.tem(x, y, M_CABELO)

        def cor_lado(x, y):
            yy = y - d
            f = max(0.0, min(1.0, (53 - yy) / 18))
            k = 0.12 + 0.68 * f
            if (x + y) % 2 and 0.25 < f < 0.75:
                k -= 0.14
            return mistura(pele, escura(cab, 0.05), max(0.0, k))

        t.mascara((CX - CAB_RX - 1, 33 + d, CX + CAB_RX + 1, 55 + d), lado, cor_lado, M_PELE)
    elif tipo == "longo":
        def topo(x, y):
            yy = y - d
            dx = x + 0.5 - CX
            if not na_cabeca(x, yy, 4):
                return False
            if yy <= 32:
                return True
            if dx >= 17 or dx <= -19:  # laterais, descendo junto do rosto
                return yy <= 52
            # franja de lado: sai da risca (à direita) e cai em diagonal sobre a testa até perto do olho esquerdo
            if dx > 5:
                return False
            fundo = 33 + (5 - dx) * 0.55 + 1.6 * math.sin(dx / 2.2)
            return yy <= fundo

        t.mascara((CX - 30, 16 + d, CX + 30, 53 + d), topo, cab, M_CABELO)

        def mechas(x, y):
            yy = y - d
            if not (36 <= yy <= 116):
                return False
            dx = abs(x + 0.5 - CX)
            onda = 1.8 * math.sin(yy / 3.6) + 1.2 * math.sin(yy / 7.5)
            centro = 23 + (yy - 36) * 0.11 + onda
            meia = 5.5 if yy < 102 else 5.5 - (yy - 102) * 0.4
            return abs(dx - centro) <= meia

        t.mascara((CX - 40, 36 + d, CX + 40, 117 + d), mechas, cab, M_CABELO)
        t.relevo((CX - 40, 14 + d, CX + 40, 128 + d), lambda x, y: _fios(x, y - d) if t.tem(x, y, M_CABELO) else None)
        cl = pal["cab_l"]
        for y in range(60 + d, 128 + d):  # reflexo caramelo descendo pelas pontas
            for x in range(CX - 40, CX + 41):
                if t.tem(x, y, M_CABELO) and t.rel[y][x] > 0.6:
                    t.p(x, y, mistura(t.pc[x, y], cl, min(0.55, (y - d - 60) / 70)), M_CABELO)
    elif tipo in ("curto", "lateral"):
        def topo(x, y):
            yy = y - d
            return yy <= 36 and na_cabeca(x, yy, 2.5) or (yy <= 45 and na_cabeca(x, yy, 1) and abs(x + 0.5 - CX) >= 21)

        t.mascara((CX - 30, 18 + d, CX + 30, 46 + d), topo, cab, M_CABELO)
        t.relevo((CX - 30, 18 + d, CX + 30, 46 + d), lambda x, y: _fios(x, y - d) * 0.7 if t.tem(x, y, M_CABELO) else None)


# ---------------------------------------------------------------------------------------- barba

def _barba(t: Lousa, cfg, pal, d: int, boca_pts):
    tipo = cfg.get("barba", "nenhuma")
    if tipo == "nenhuma":
        return
    cab = pal["cab"] if cfg["cabelo"] != "careca" else _hex("#3B2A20")
    labios = set()
    for x, y in boca_pts:
        for ax, ay in ((x, y), (x - 1, y), (x + 1, y), (x, y + 1), (x - 1, y + 1), (x + 1, y + 1), (x, y - 1), (x, y + 2)):
            labios.add((ax, ay))
    if tipo == "cheia":
        def dentro(x, y):
            yy = y - d
            if (x, y) in labios:
                return False
            dx = abs(x + 0.5 - CX)
            if dx >= 20 and 46 <= yy:  # costeleta, saindo do cabelo
                return na_cabeca(x, yy)
            linha = 60 + max(0.0, 20 - dx) * 0.45
            if yy < linha and not (BOCA_Y - 4 <= yy and dx <= 8):
                return False
            if not na_cabeca(x, yy):
                if dx > 18:
                    return False
                return yy <= 80 - (dx / 18) ** 2 * 5
            return True

        t.mascara((CX - CAB_RX - 1, 45 + d, CX + CAB_RX + 1, 85 + d), dentro, cab, M_BARBA)
        centros = _bolinhas((CX - CAB_RX, 44 + d, CX + CAB_RX, 86 + d), 3, 1.9, lambda cx, cy: t.tem(int(cx), int(cy), M_BARBA),
                            hash(("barba", cfg["cor_cabelo"])) & 0xFFFF)
        _pintar_cachos(t, centros, cab, M_BARBA, sobre=lambda x, y: t.tem(x, y, M_BARBA))
    elif tipo in ("bigode", "cavanhaque"):
        t.mascara((CX - 9, BOCA_Y - 4 + d, CX + 9, BOCA_Y - 1 + d),
                  lambda x, y: (x, y) not in labios and abs(x + 0.5 - CX) <= 9 - (BOCA_Y - 1 + d - y), cab, M_BARBA)
        if tipo == "cavanhaque":
            t.mascara((CX - 5, BOCA_Y + 3 + d, CX + 5, BOCA_Y + 11 + d),
                      lambda x, y: (x, y) not in labios and abs(x + 0.5 - CX) <= 5 - max(0, y - d - BOCA_Y - 8), cab, M_BARBA)
    elif tipo == "por_fazer":
        def dentro(x, y):
            yy = y - d
            dx = abs(x + 0.5 - CX)
            return yy >= 58 + max(0.0, 22 - dx) * 0.48 and na_cabeca(x, yy) and (x, y) not in labios and t.tem(x, y, M_PELE)

        t.mascara((CX - CAB_RX, 56 + d, CX + CAB_RX, 80 + d), dentro,
                  lambda x, y: mistura(pal["pele"], cab, 0.3 if (3 * x + 5 * y) % 5 == 0 else 0.13), M_PELE)


VOLUME = {M_MANGA: 5, M_PELE: 9, M_CABELO: 7, M_BARBA: 5, M_ROUPA: 7, M_CALCA: 6, M_BOTA: 4, M_SOLA: 2, M_METAL: 4, M_ACESS: 4, M_ITEM: 3,
          M_EXTRA: 4}
LUZ = (-0.55, -0.75, 0.62)  # de cima, da esquerda e da frente
_n = math.sqrt(sum(v * v for v in LUZ))
LUZ = tuple(v / _n for v in LUZ)
# tons por peça: (sombra funda, sombra, base, luz, brilho) como deslocamentos de cor (frio na sombra, quente na luz)
TONS = {M_MANGA: (-0.4, -0.2, 0.0, 0.14, 0.26), M_PELE: (-0.34, -0.17, 0.0, 0.1, 0.18), M_CABELO: (-0.42, -0.22, 0.0, 0.2, 0.42), M_BARBA: (-0.4, -0.2, 0.0, 0.16, 0.3),
        M_ROUPA: (-0.4, -0.2, 0.0, 0.14, 0.26), M_CALCA: (-0.38, -0.2, 0.0, 0.14, 0.24), M_BOTA: (-0.3, -0.14, 0.0, 0.0, 0.06),
        M_SOLA: (-0.25, -0.12, 0.0, 0.0, 0.0)}


def _profundidade(mat):
    """Distância (aprox.) de cada pixel até a borda da própria peça (chanfro 1 / 1,4), dentro de cada material."""
    inf = 99.0
    d = [[0.0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            m = mat[y][x]
            if m < 0:
                continue
            borda = x == 0 or y == 0 or x == W - 1 or y == H - 1 or mat[y][x - 1] != m or mat[y][x + 1] != m or mat[y - 1][x] != m or mat[y + 1][x] != m
            d[y][x] = 1.0 if borda else inf
    for y in range(1, H):
        for x in range(1, W - 1):
            if d[y][x] > 1:
                m = mat[y][x]
                for nx, ny, w in ((x - 1, y, 1.0), (x, y - 1, 1.0), (x - 1, y - 1, 1.4), (x + 1, y - 1, 1.4)):
                    if mat[ny][nx] == m and d[ny][nx] + w < d[y][x]:
                        d[y][x] = d[ny][nx] + w
    for y in range(H - 2, -1, -1):
        for x in range(W - 2, 0, -1):
            if d[y][x] > 1:
                m = mat[y][x]
                for nx, ny, w in ((x + 1, y, 1.0), (x, y + 1, 1.0), (x + 1, y + 1, 1.4), (x - 1, y + 1, 1.4)):
                    if mat[ny][nx] == m and d[ny][nx] + w < d[y][x]:
                        d[y][x] = d[ny][nx] + w
    return d


def _sombrear(t: Lousa):
    """Volume de cada peça: a altura cresce da borda para dentro (como uma almofada) e soma o relevo (cachos,
    fios, dobras); a luz de cima à esquerda escolhe um de cinco tons, com a sombra puxando para o frio."""
    pc, pm, rel = t.pc, t.pm, t.rel
    mat = [[pm[x, y] if pc[x, y][3] else -1 for x in range(W)] for y in range(H)]
    prof = _profundidade(mat)
    alt = [[0.0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            m = mat[y][x]
            if m < 0 or m not in VOLUME:
                continue
            r = VOLUME[m]
            k = min(prof[y][x], r) / r
            extra = rel[y][x] if t.relmat[y][x] == m else 0.0
            alt[y][x] = math.sqrt(max(0.0, 1 - (1 - k) ** 2)) * r * 0.9 + extra * r * 0.5
    orig = [[pc[x, y] for x in range(W)] for y in range(H)]
    for y in range(H):
        for x in range(W):
            m = mat[y][x]
            if m < 0 or m not in TONS:
                continue

            def h(nx, ny):
                if 0 <= nx < W and 0 <= ny < H and mat[ny][nx] == m:
                    return alt[ny][nx]
                return 0.0

            gx = (h(x + 1, y) - h(x - 1, y)) / 2
            gy = (h(x, y + 1) - h(x, y - 1)) / 2
            nx_, ny_, nz_ = -gx, -gy, 1.0
            n = math.sqrt(nx_ * nx_ + ny_ * ny_ + nz_ * nz_)
            luz = (nx_ * LUZ[0] + ny_ * LUZ[1] + nz_ * LUZ[2]) / n
            # contato: embaixo de uma peça que está na frente, fica escuro
            acima = mat[y - 1][x] if y else -1
            if acima >= 0 and acima != m and FRENTE.get(acima, 0) > FRENTE.get(m, 0):
                luz -= 0.35
            elif y > 1 and mat[y - 2][x] >= 0 and mat[y - 2][x] != m and FRENTE.get(mat[y - 2][x], 0) > FRENTE.get(m, 0):
                luz -= 0.18
            tons = TONS[m]
            plano = LUZ[2]  # luz numa superfície de frente
            if luz < plano - 0.42:
                k = tons[0]
            elif luz < plano - 0.16:
                k = tons[1]
            elif luz < plano + 0.12:
                k = tons[2]
            elif luz < plano + 0.3:
                k = tons[3]
            else:
                k = tons[4]
            c = orig[y][x]
            if k > 0 and av._luz(c) < 0.3:
                pc[x, y] = mistura(c, (150, 160, 190, 255), k * 0.9)  # preto: a luz vira um cinza azulado
            else:
                pc[x, y] = quente(c, k) if k > 0 else fria(c, -k) if k < 0 else c


def _contornar(t: Lousa):
    """Contorno escuro: por fora de tudo e entre as peças (do lado da peça de trás)."""
    pc, pm = t.pc, t.pm
    cor = [[pc[x, y] for x in range(W)] for y in range(H)]
    mat = [[pm[x, y] if pc[x, y][3] else -1 for x in range(W)] for y in range(H)]
    for y in range(H):
        for x in range(W):
            m = mat[y][x]
            viz = [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            if m < 0:
                cheios = [cor[vy][vx] for vx, vy in viz if 0 <= vx < W and 0 <= vy < H and mat[vy][vx] >= 0]
                if cheios:
                    pc[x, y] = mistura(cheios[0], CONTORNO, 0.82)
                continue
            if m in (M_ROSTO, M_DETALHE):
                continue
            for vx, vy in viz:
                if 0 <= vx < W and 0 <= vy < H:
                    n = mat[vy][vx]
                    if n >= 0 and n != m and n not in (M_ROSTO,) and FRENTE.get(n, 0) > FRENTE.get(m, 0):
                        if m == M_PELE and n == M_BARBA:
                            continue  # a barba nasce da pele, sem risco
                        pc[x, y] = mistura(cor[y][x], CONTORNO, 0.62)
                        break



# ---------------------------------------------------------------------------------------- rosto

def _olho(t: Lousa, ex, ey, pal, estilo, lado):
    iris = pal["olho"]
    cilio = (30, 22, 32, 255)
    branco = (250, 250, 252, 255)
    if estilo == "feliz" or (estilo == "piscadinha" and lado > 0):
        for dx in range(-3, 4):
            dy = -int(2 - abs(dx) * 0.6)
            t.p(ex + dx, ey + dy, cilio, M_ROSTO)
            t.p(ex + dx, ey + dy + 1, cilio, M_ROSTO)
        return
    grande = estilo == "grandes"
    rx, ry = (4.6, 5.6) if grande else (3.2, 3.2)
    topo = -int(ry) + (2 if estilo == "sonolento" else 0)
    # branco
    for dy in range(topo, int(ry) + 1):
        for dx in range(-5, 6):
            if (dx / rx) ** 2 + ((dy + 0.5) / ry) ** 2 <= 1:
                t.p(ex + dx, ey + dy, branco, M_ROSTO)
    # íris (escura em cima, clara embaixo) e pupila
    irx, iry = (3.2, 4.8) if grande else (2.3, 3.0)
    for dy in range(topo, int(ry) + 1):
        for dx in range(-4, 5):
            if (dx / irx) ** 2 + ((dy + 0.3) / iry) ** 2 <= 1:
                k = (dy - topo) / (2 * ry)
                t.p(ex + dx, ey + dy, mistura(escura(iris, 0.45), clara(iris, 0.3), k), M_ROSTO)
    for dy in (-1, 0, 1) if grande else (-1, 0):
        for dx in (-1, 0, 1) if grande else (0,):
            t.p(ex + dx, ey + dy, escura(iris, 0.72), M_ROSTO)
    t.p(ex - 1, ey - 2, branco, M_ROSTO)
    if grande:
        t.p(ex - 2, ey - 2, branco, M_ROSTO)
        t.p(ex - 2, ey - 3, branco, M_ROSTO)
        t.p(ex - 1, ey - 3, branco, M_ROSTO)
        t.p(ex + 1, ey + 2, mistura(branco, iris, 0.35), M_ROSTO)
    # cílio de cima, mais grosso no meio, com a pontinha para fora
    for dx in range(-int(rx), int(rx) + 1):
        y = ey + topo - (0 if abs(dx) >= int(rx) else 1)
        t.p(ex + dx, y, cilio, M_ROSTO)
        if grande and abs(dx) <= 2:
            t.p(ex + dx, y - 1, cilio, M_ROSTO)
    t.p(ex + lado * (int(rx) + 1), ey + topo - 1, cilio, M_ROSTO)
    if grande:
        t.p(ex + lado * (int(rx) + 2), ey + topo - 2, cilio, M_ROSTO)
    if estilo == "determinado":
        for dx in range(-int(rx), int(rx) + 1):
            if dx * lado < 0:
                t.p(ex + dx, ey + topo, cilio, M_ROSTO)


def _rosto(t: Lousa, cfg, pal, d: int, piscando: bool, alegre: bool):
    estilo = "feliz" if (alegre or piscando) else cfg["olhos"]
    pele = pal["pele"]
    sob = escura(pal["cab"], 0.1) if cfg["cabelo"] != "careca" else escura(pele, 0.45)
    for lado in (-1, 1):
        ex = CX + lado * OLHO_DX
        _olho(t, ex, OLHO_Y + d, pal, estilo, lado)
        # sobrancelha grossa, na cor do cabelo, mais alta no meio
        for dx in range(-5, 6):
            sobe = 1 if -2 <= dx * lado <= 2 else 0
            if cfg["olhos"] == "determinado":
                sobe = 1 if dx * lado > 1 else 0
            y = OLHO_Y - 8 - sobe + d
            if t.tem(ex + dx, y, M_PELE, M_CABELO):
                t.p(ex + dx, y, sob, M_ROSTO)
                if abs(dx) <= 4 and t.tem(ex + dx, y + 1, M_PELE):
                    t.p(ex + dx, y + 1, sob, M_ROSTO)
    # nariz: sombra do lado direito e embaixo, brilho em cima
    for x, y in ((CX + 1, 60), (CX + 1, 61), (CX + 1, 62), (CX - 1, 63), (CX, 63), (CX + 1, 63), (CX + 2, 62)):
        if t.tem(x, y + d, M_PELE):
            t.p(x, y + d, fria(escura(pele, 0.14), 0.12), M_ROSTO)
    t.p(CX - 1, 61 + d, quente(pele, 0.2), M_ROSTO)
    # bochechas
    corado = cfg.get("marca") == "corado"
    if corado or cfg.get("barba", "nenhuma") != "cheia":
        forca = 0.42 if corado else 0.22
        for lado in (-1, 1):
            bx = CX + lado * 16
            for dy in (-1, 0, 1):
                for dx in range(-4, 5):
                    y = 63 + dy + d
                    if dx * dx / 16 + dy * dy / 2.2 <= 1 and t.tem(bx + dx, y, M_PELE):
                        t.p(bx + dx, y, mistura(t.pc[bx + dx, y], (240, 110, 130, 255), forca), M_ROSTO)


def _boca(cfg, alegre: bool, d: int):
    """Pontos da boca (x, y, cor) para o tipo escolhido."""
    tipo = "sorrisao" if alegre else cfg.get("boca", "sorriso")
    y0 = BOCA_Y + d
    escuro, lingua = (110, 40, 52, 255), (232, 112, 122, 255)
    pts = []
    if tipo == "sorriso":
        for dx in range(-4, 5):
            pts.append((CX + dx, y0 + (1 if abs(dx) <= 2 else 0) - (1 if abs(dx) == 4 else 0), escuro))
        for dx in range(-2, 3):  # lábio de baixo, um tom rosado
            pts.append((CX + dx, y0 + 2, (196, 112, 116, 255)))
    elif tipo == "sorrisao":
        for dx in range(-5, 6):
            pts.append((CX + dx, y0 - (1 if abs(dx) == 5 else 0), escuro))
        for dy in (1, 2, 3):
            for dx in range(-4 + dy, 5 - dy):
                pts.append((CX + dx, y0 + dy, lingua if dy >= 2 and abs(dx) <= 1 else escuro))
    elif tipo == "neutra":
        for dx in range(-3, 4):
            pts.append((CX + dx, y0 + 1, escuro))
    elif tipo == "surpresa":
        for dy in range(-1, 4):
            for dx in range(-2, 3):
                if dx * dx / 5 + (dy - 1.2) ** 2 / 5 <= 1:
                    pts.append((CX + dx, y0 + dy, escuro))
    else:  # língua de fora
        for dx in range(-4, 5):
            pts.append((CX + dx, y0 + (1 if abs(dx) <= 2 else 0), escuro))
        for dy in (2, 3, 4):
            for dx in (0, 1, 2):
                pts.append((CX + dx, y0 + dy, lingua))
    return pts


# ---------------------------------------------------------------------------------------- óculos e colar

def _oculos(t: Lousa, cfg, pal, d: int):
    tipo = cfg.get("oculos", "nenhum")
    if tipo == "nenhum":
        return
    arm = _hex(av.CORES_OCULOS[cfg["cor_oculos"]][0])
    y_haste = OLHO_Y - 3 + d
    for lado in (-1, 1):
        ex, ey = CX + lado * OLHO_DX, OLHO_Y + d
        x0, x1, y0, y1 = ex - 8, ex + 8, ey - 6, ey + 5
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                borda = x <= x0 + 1 or x >= x1 - 1 or y <= y0 + 1 or y >= y1 - 1
                if (x in (x0, x1)) and (y in (y0, y1)):
                    continue
                if borda:
                    t.p(x, y, clara(arm, 0.3) if (y == y0 and x0 + 2 <= x <= x1 - 5) else arm, M_OCULOS)
                elif (x - x0) + (y - y0) == 5 and y <= y0 + 3:
                    t.p(x, y, mistura(t.pc[x, y], (255, 255, 255, 255), 0.6), t.pm[x, y])
                else:
                    t.p(x, y, mistura(t.pc[x, y], (170, 200, 235, 255), 0.1), t.pm[x, y])
        fim = CX + lado * (CAB_RX + 1)
        for x in range(min(x1 + 1, fim) if lado > 0 else fim, (fim + 1) if lado > 0 else x0):
            t.p(x, y_haste, arm, M_OCULOS)
            t.p(x, y_haste + 1, arm, M_OCULOS)
    for x in range(CX - 3, CX + 4):  # ponte
        t.p(x, OLHO_Y - 3 + d, arm, M_OCULOS)
        t.p(x, OLHO_Y - 2 + d, arm, M_OCULOS)


def _colar(t: Lousa, cfg, pal, d: int):
    if cfg.get("extra") != "colar":
        return
    prata, sombra = (226, 230, 240, 255), (140, 146, 164, 255)
    for i in range(0, 23):
        a = math.pi * i / 22
        x = int(round(CX - 9 * math.cos(a)))
        y = int(round(80 + d + 6 * math.sin(a)))
        t.p(x, y, prata if i % 2 == 0 else sombra, M_DETALHE)


# ---------------------------------------------------------------------------------------- quadro

@lru_cache(maxsize=1024)
def _quadro(chave_cfg: tuple, respira: int, piscando: bool, alegre: bool) -> Image.Image:
    cfg = dict(chave_cfg)
    pal = _paleta(cfg)
    d = 1 if respira else 0
    t = Lousa()
    _cabelo_atras(t, cfg, pal, d)
    m = _corpo(t, cfg, pal, d)
    _bracos(t, cfg, pal, m, d)
    _roupa(t, cfg, pal, m, d)
    _pescoco_cabeca(t, cfg, pal, d)
    boca = _boca(cfg, alegre, d)
    _barba(t, cfg, pal, d, [(x, y) for x, y, _ in boca])
    _cabelo_frente(t, cfg, pal, d)
    _colar(t, cfg, pal, d)
    _sombrear(t)
    _rosto(t, cfg, pal, d, piscando, alegre)
    for x, y, cor in boca:
        t.p(x, y, cor, M_ROSTO)
    _oculos(t, cfg, pal, d)
    _contornar(t)
    return t.cor


EXTRAS_V2 = {"cabelo": ["degrade"], "olhos": ["grandes"], "roupa": ["sueter"]}


def boneco(cfg: dict, respira: int = 0, piscando: bool = False, alegre: bool = False) -> Image.Image:
    base = av.validar({k: v for k, v in cfg.items() if not (k in EXTRAS_V2 and v in EXTRAS_V2[k])})
    for k, novos in EXTRAS_V2.items():  # opções novas do v2 que o v1 ainda não conhece
        if cfg.get(k) in novos:
            base[k] = cfg[k]
    return _quadro(tuple(sorted(base.items())), respira, piscando, alegre)
