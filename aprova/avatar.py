"""Personagem do Aprova: um bonequinho em pixel art, estilo RPG, montado em camadas.

O personagem é só uma configuração pequena (cores e estilos), por exemplo
{"pele": 2, "cabelo": "curto", "roupa": "moletom", "item": "livro", ...}. Ela vai para o
servidor (perfis.avatar) e cada computador desenha o boneco a partir dela, então ninguém
manda imagem: só escolhas de uma lista fechada.

Desenho em duas etapas:
1. o boneco é montado numa grade de 32 x 40 com moldes em texto (cada letra é uma cor e um
   material: pele, cabelo, roupa, metal, acessório, óculos, item...);
2. a grade é dobrada para 64 x 80 com o EPX (que arredonda as diagonais sem borrar) e ganha os
   detalhes finos: olhos com íris, brilho e cílios, boca, bochechas, fios e brilho no cabelo,
   sombra e luz nas roupas, sombra do cabelo na testa e um contorno colorido de 1 pixel.
No fim, a imagem é ampliada sem borrar (cada pixel vira um quadradinho).

Animações (WebP animado, que o app mostra sozinho): parado (respira e pisca), aceno,
pulo e o "lobby", que mistura os três como nas telas de espera dos jogos.
"""

from __future__ import annotations

import hashlib
import io
import random
import time
from functools import lru_cache

from PIL import Image

W, H = 32, 40  # grade de montagem
W2, H2 = 64, 80  # grade final (com os detalhes)
CONTORNO = (31, 26, 46, 255)

# materiais (para sombrear e detalhar cada parte do jeito certo)
M_VAZIO, M_PELE, M_CABELO, M_ROUPA, M_CALCA, M_BOTA, M_METAL, M_ACESS, M_OCULOS, M_ITEM, M_EXTRA, M_ROSTO = range(12)
MAT_CORPO = {"s": M_PELE, "S": M_PELE, "r": M_PELE, "c": M_ROUPA, "C": M_ROUPA, "d": M_ROUPA, "w": M_ROUPA, "p": M_CALCA, "P": M_CALCA,
             "b": M_BOTA, "B": M_BOTA, "A": M_METAL, "h": M_CABELO, "H": M_CABELO, "L": M_CABELO, "e": M_ROSTO, "m": M_ROSTO}

# ---------------------------------------------------------------- opções

PELES = [("#FFE1C8", "Clara"), ("#F4C7A1", "Pêssego"), ("#E2A97E", "Morena clara"), ("#C38A5E", "Morena"), ("#9A6542", "Morena escura"), ("#6A4430", "Escura")]
CORES_CABELO = [("#2B2B35", "Preto"), ("#4B2F22", "Castanho escuro"), ("#7B4A2C", "Castanho"), ("#C25A2B", "Ruivo"), ("#E7C064", "Loiro"),
                ("#ECE4D3", "Platinado"), ("#9AA0AA", "Grisalho"), ("#3D6BD6", "Azul"), ("#E56FA5", "Rosa"), ("#40A57A", "Verde"), ("#7C51C8", "Roxo")]
CORES_OLHOS = [("#5A3A28", "Castanhos"), ("#24232B", "Pretos"), ("#3B7AD4", "Azuis"), ("#3E9A5E", "Verdes"), ("#B37B2A", "Mel")]
CORES_ROUPA = [("#2340A8", "Azul Aprova"), ("#C2413A", "Vermelho"), ("#2E8B57", "Verde"), ("#E2B42F", "Amarelo"), ("#6E4BB8", "Roxo"),
               ("#E07B2C", "Laranja"), ("#D9578C", "Rosa"), ("#16928E", "Turquesa"), ("#6B7280", "Cinza"), ("#2A2D3A", "Preto"), ("#EFEFEF", "Branco")]

CABELOS = [("curto", "Curto"), ("espetado", "Espetado"), ("longo", "Longo"), ("franja", "Chanel"), ("coque", "Coque"),
           ("rabo", "Rabo de cavalo"), ("cacheado", "Cacheado"), ("careca", "Careca")]
OLHOS = [("normal", "Normal"), ("feliz", "Feliz"), ("determinado", "Determinado")]
ROUPAS = [("moletom", "Moletom"), ("camiseta", "Camiseta"), ("vestido", "Vestido"), ("terno", "Terno"), ("manto", "Manto de mago"), ("armadura", "Armadura")]
ACESSORIOS = [("nenhum", "Nenhum"), ("bone", "Boné"), ("gorro", "Gorro"), ("capelo", "Capelo de formatura"), ("coroa", "Coroa"), ("tiara", "Tiara"),
              ("chapeu", "Chapéu de mago"), ("viking", "Capacete viking"), ("fone", "Fone"), ("laco", "Laço"), ("flor", "Flor"),
              ("gato", "Orelhas de gato"), ("aureola", "Auréola"), ("faixa", "Faixa")]
OCULOS = [("nenhum", "Sem óculos"), ("redondo", "Redondo"), ("quadrado", "Quadrado"), ("meia", "Meia armação"), ("escuro", "Escuro"),
          ("coracao", "Coração"), ("monoculo", "Monóculo"), ("visor", "Visor")]
CORES_OCULOS = [("#2A2A36", "Preto"), ("#6B4A2E", "Tartaruga"), ("#D9A21C", "Dourado"), ("#B9BFC9", "Prata"), ("#C2413A", "Vermelho"),
                ("#2F6BD8", "Azul"), ("#E56FA5", "Rosa"), ("#F2F2F2", "Branco")]
EXTRAS = [("nenhum", "Nada"), ("cachecol", "Cachecol"), ("medalha", "Medalha"), ("gravata", "Gravata-borboleta"), ("colar", "Colar"),
          ("capa", "Capa de herói"), ("mochila", "Mochila")]
ITENS = [("nenhum", "Nada"), ("livro", "Livro"), ("lapis", "Lápis gigante"), ("cafe", "Café"), ("espada", "Espada"), ("cajado", "Cajado")]
CENARIOS = [("biblioteca", "Biblioteca"), ("floresta", "Floresta"), ("noite", "Noite na cidade"), ("castelo", "Castelo"), ("sala", "Sala de aula")]

CATEGORIAS = {"cabelo": CABELOS, "olhos": OLHOS, "roupa": ROUPAS, "acessorio": ACESSORIOS, "oculos": OCULOS, "extra": EXTRAS, "item": ITENS,
              "cenario": CENARIOS}
CORES = {"pele": PELES, "cor_cabelo": CORES_CABELO, "cor_olhos": CORES_OLHOS, "cor_roupa": CORES_ROUPA, "cor_oculos": CORES_OCULOS}

PADRAO = {"v": 1, "pele": 1, "cabelo": "curto", "cor_cabelo": 1, "olhos": "normal", "cor_olhos": 0, "roupa": "moletom", "cor_roupa": 0,
          "acessorio": "nenhum", "oculos": "nenhum", "cor_oculos": 0, "extra": "nenhum", "item": "livro", "cenario": "biblioteca",
          "usar_foto": False, "foto": 0, "t": 0}


def validar(cfg) -> dict:
    """Só passa o que o app conhece. Serve para o que vem do servidor (de outras pessoas) e para o que vem do disco."""
    saida = dict(PADRAO)
    if not isinstance(cfg, dict):
        return saida
    if cfg.get("acessorio") == "oculos" and "oculos" not in cfg:  # 1.14.0: os óculos eram um acessório
        cfg = {**cfg, "acessorio": "nenhum", "oculos": "redondo", "cor_oculos": 0}
    for chave, opcoes in CATEGORIAS.items():
        v = cfg.get(chave)
        if isinstance(v, str) and v in {o[0] for o in opcoes}:
            saida[chave] = v
    for chave, lista in CORES.items():
        v = cfg.get(chave)
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(lista):
            saida[chave] = v
    saida["usar_foto"] = cfg.get("usar_foto") is True
    for chave in ("foto", "t"):
        v = cfg.get(chave)
        saida[chave] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 10**11 else 0
    if not saida["foto"]:
        saida["usar_foto"] = False
    return saida


def tem_personagem(cfg) -> bool:
    return isinstance(cfg, dict) and bool(cfg.get("t"))


def sortear(semente: str | None = None) -> dict:
    """Um personagem aleatório (sempre o mesmo para a mesma semente)."""
    rnd = random.Random(int(hashlib.sha256(semente.encode()).hexdigest()[:12], 16) if semente else None)
    cfg = dict(PADRAO)
    for chave, opcoes in CATEGORIAS.items():
        cfg[chave] = rnd.choice(opcoes)[0]
    for chave, lista in CORES.items():
        cfg[chave] = rnd.randrange(len(lista))
    if rnd.random() < 0.45:
        cfg["acessorio"] = "nenhum"
    if rnd.random() < 0.6:
        cfg["oculos"] = "nenhum"
    if rnd.random() < 0.55:
        cfg["extra"] = "nenhum"
    return cfg


def chave_cache(cfg: dict, *extra) -> str:
    base = {k: v for k, v in validar(cfg).items() if k not in ("t", "foto", "usar_foto")}
    return hashlib.sha1(repr((sorted(base.items()), extra)).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- cores

def _rgb(h: str) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _mistura(a, b, t: float):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


def _escura(c, t=0.2):
    return _mistura(c, (20, 16, 32), t)


def _clara(c, t=0.25):
    return _mistura(c, (255, 255, 255), t)


def _luz(c) -> float:
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


# ---------------------------------------------------------------- moldes (x de 8 a 23 quando a linha tem 16 colunas)
# cada molde: {y: "linha"}; "." é vazio. As letras viram cores na paleta da camada.

CABECA = {
    12: "....ssssssss....",
    13: "...ssssssssss...",
    14: "..ssssssssssss..",
    15: "..ssssssssssss..",
    16: "..ssssssssssss..",
    17: ".ssssssssssssss.",
    18: ".ssssssssssssss.",
    19: "..ssssssssssss..",
    20: "..ssssssssssss..",
    21: "...ssssssssss...",
    22: "....ssssssss....",
}

CORPO = {
    23: "......SSSS......",
    24: "....cccSScccc...",
    25: ".cccccccccccccc.",
    26: ".CccccccccccccC.",
    27: ".CccccccccccccC.",
    28: ".ssccccccccccss.",
    29: ".ssCcccccccccss.",
    30: "...CccccccccC...",
    31: "....pppppppp....",
    32: "....pppPPppp....",
    33: "....ppp..ppp....",
    34: "....pPp..pPp....",
    35: "...bbbb..bbbb...",
    36: "...BbbB..BbbB...",
}

ROUPA_MOLDES = {
    "camiseta": {
        24: "....ccSSSScc....",
        25: ".cccccSSccccccc.",
        26: ".CccccccccccccC.",
        27: ".ssccccccccccss.",
    },
    "moletom": {
        23: "....CC....CC....",
        24: "....ccCSSCcc....",
        25: ".ccccdcccdccccc.",
        26: ".CcccdcccdccccC.",
        27: ".CccccccccccccC.",
        28: ".ssccCCCCCCccss.",
        29: ".ssCcCccccCccss.",
    },
    "vestido": {
        24: "....ccSSSScc....",
        25: ".SScccccccccSS..",
        26: ".SSccccccccccSS.",
        27: ".SsccccccccccsS.",
        30: "...cCcccccccc...",
        31: "...cccccccccc...",
        32: "..cccccccccccc..",
        33: "..CCCCCCCCCCCC..",
        34: "....sSs..sSs....",
    },
    "terno": {
        24: "....ccwwwwcc....",
        25: ".ccccwwddwwcccc.",
        26: ".CcccwwddwwcccC.",
        27: ".CcccwwddwwcccC.",
        28: ".sscccwddwcccss.",
        29: ".ssCcccwwccccss.",
        31: "....CCCCCCCC....",
        32: "....CCCCCCCC....",
        33: "....CCC..CCC....",
        34: "....CCC..CCC....",
    },
    "manto": {
        24: "....ccdSSdcc....",
        25: "ccccccdccdcccccc",
        26: "cCcccccddcccccCc",
        27: "cCcccccddcccccCc",
        28: ".ssccccddcccccs.",
        29: ".ssCcccddccccss.",
        30: "...CccccddcccC..",
        31: "...ccccddcccc...",
        32: "...ccccddcccc...",
        33: "..cCcccddccccc..",
        34: "..dddddddddddd..",
    },
    "armadura": {
        24: "..AAAcccccAAA...",
        25: ".AAAAcAAAAcAAAA.",
        26: ".CAccAAAAAAccAC.",
        27: ".CccAAAAAAAAccC.",
        28: ".AAccAAAAAAccAA.",
        29: ".AACcAAAAAAccAA.",
        30: "...dddddddddd...",
    },
}

CABELO_FRENTE = {
    "curto": {
        11: "....hhhhhhhh....",
        12: "...hhLLhhhhhh...",
        13: "..hhhhhhhhhhhh..",
        14: "..hhhhhhhhhhhh..",
        15: "..hhHhhhhhHhhh..",
        16: "..hH.H....H.Hh..",
        17: "..h..........h..",
    },
    "espetado": {
        8: "......h...h.....",
        9: ".....hh..hh.h...",
        10: "...h.hhh.hhhh...",
        11: "...hhhhhhhhhh.h.",
        12: "..hhhLLhhhhhhh..",
        13: ".hhhhhhhhhhhhhh.",
        14: "..hhhhhhhhhhhh..",
        15: "..hhh.hhH.hhhh..",
        16: "..hH...h....Hh..",
        17: "..h..........h..",
    },
    "longo": {
        11: "....hhhhhhhh....",
        12: "...hhhLLhhhhh...",
        13: "..hhhhhhhhhhhh..",
        14: "..hhhhhhhhhhhh..",
        15: "..hhhhH.hhhhhh..",
        16: "..hhh......hhh..",
        17: "..hh........hh..",
        18: "..hh........hh..",
        19: "..hH........Hh..",
        20: "..H..........H..",
    },
    "franja": {
        11: "....hhhhhhhh....",
        12: "...hhLLhhhhhh...",
        13: "..hhhhhhhhhhhh..",
        14: "..hhhhhhhhhhhh..",
        15: "..hHhhHhhHhhHh..",
        16: "..hh........hh..",
        17: ".hhh........hhh.",
        18: ".hhh........hhh.",
        19: ".hhH........Hhh.",
        20: ".hH..........Hh.",
    },
    "coque": {
        7: "......hhhh......",
        8: ".....hhLhhh.....",
        9: ".....hhhhhh.....",
        10: "......HHHH......",
        11: "....hhhhhhhh....",
        12: "...hhLLhhhhhh...",
        13: "..hhhhhhhhhhhh..",
        14: "..hhhhhhhhhhhh..",
        15: "..hhHhhhhhHhhh..",
        16: "..hh........hh..",
        17: "..h..........h..",
    },
    "rabo": {
        11: "....hhhhhhhh....",
        12: "...hhLLhhhhhh...",
        13: "..hhhhhhhhhhhh..",
        14: "..hhhhhhhhhhhh..",
        15: "..hhhHhhhhhHhh..",
        16: "..hh.H.....Hhh..",
        17: "..h..........h..",
    },
    "cacheado": {
        12: "..hhHhhhHhhhHh..",
        13: "..hHhhHhhhHhhh..",
        14: "..hhh.hhhh.hhh..",
        15: "..hH..h..h..Hh..",
    },
    "careca": {},
}

CABELO_ATRAS = {
    "longo": {**{13: ".hhhhhhhhhhhhhh."}, **{y: ".hh..........hh." for y in range(14, 28)}, 28: ".HH..........HH."},
    "franja": {y: ".h............h." for y in range(13, 21)},
    "rabo": {12: "..............h.", 13: ".............hhh", **{y: "..............hH" for y in range(14, 22)}, 22: "..............H."},
    "cacheado": {
        7: ".....hhhhhh.....",
        8: "...hhhHhhhhhh...",
        9: "..hhhhhhhHhhhh..",
        10: ".hhHhhhhhhhhhhh.",
        11: ".hhhhhhHhhhhhHh.",
        **{y: "hhhhhhhhhhhhhhhh" if y % 3 else "hHhhhhhhhhhhhhHh" for y in range(12, 21)},
        21: ".hhHhhhhhhhhHhh.",
        22: "..hh........hh..",
    },
}

# acessórios da cabeça: (molde, corta) — corta = some o cabelo acima desta linha (o chapéu cobre)
ACESSORIO_MOLDES = {
    "bone": ({10: "....aaaaaaaa....", 11: "...aaaaaaaaaa...", 12: "..aaaaaAAaaaaa..", 13: "..aaaaaaaaaaaa..", 14: ".dddddddddddddd."}, 15),
    "gorro": ({6: ".......dd.......", 7: "......dddd......", 8: ".....aaaaaa.....", 9: "....aaaaaaaa....", 10: "...aaaaaaaaaa...",
               11: "..aaaaaaaaaaaa..", 12: "..AAAAAAAAAAAA..", 13: "..AAAAAAAAAAAA.."}, 14),
    "capelo": ({8: "...aaaaaaaaaa...", 9: ".aaaaaAaaaaaaaa.", 10: "...aaaaaaaaaa..d", 11: "....aaaaaaaa...d", 12: "...............d",
                13: "..............dd"}, 11),
    "coroa": ({7: "....a..aa..a....", 8: "....aa.aa.aa....", 9: "....aaaAAaaa....", 10: "....aaaaaaaa...."}, 0),
    "tiara": ({9: ".......AA.......", 10: "......aAAa......", 11: ".....aaaaaa....."}, 0),
    "chapeu": ({0: "..........a.....", 1: ".........aa.....", 2: "........aaa.....", 3: ".......aaaa.....", 4: "......aaAaa.....",
                5: "......aaaaaa....", 6: ".....aaaaaaa....", 7: ".....aaaaaaaa...", 8: "....aaaAaaaaa...", 9: "....aaaaaaaaa...",
                10: "...dddddddddd...", 11: ".aaaaaaaaaaaaaa.", 12: "aaaaaaaaaaaaaaaa"}, 13),
    "viking": ({6: "a..............a", 7: "a..............a", 8: "aa............aa", 9: ".aa..AAAAAA..aa.", 10: "..aAAAAAAAAAAa..",
                11: "..AAAAAAAAAAAA..", 12: "..dddddddddddd.."}, 13),
    "fone": ({10: "....aaaaaaaa....", 11: "...a........a...", 12: "..a..........a..", 13: ".a............a.", 14: ".a............a.",
              15: ".a............a.", 16: "AA............AA", 17: "AA............AA", 18: "AA............AA", 19: "AA............AA"}, 0),
    "laco": ({9: ".........aa.aa..", 10: ".........aaAaa..", 11: "..........a.a..."}, 0),
    "flor": ({10: ".............a..", 11: "............aAa.", 12: ".............a..", 13: "............d..."}, 0),
    "gato": ({7: "..a..........a..", 8: "..aa........aa..", 9: "..aAa......aAa..", 10: "..aAAa....aAAa.."}, 0),
    "aureola": ({4: "....aaaaaaaa....", 5: "...a........a...", 6: "....aaaaaaaa...."}, 0),
    "faixa": ({14: "..aaaaaaaaaaaaa.", 15: "..AAAAAAAAAAAAaa", 16: "..............a."}, 0),
}
CORES_ACESSORIO = {  # None = cor da roupa; "h" = cor do cabelo
    "bone": {"a": None, "A": "#FFFFFF", "d": None},
    "gorro": {"a": None, "A": None, "d": "#F4F4F4"},
    "capelo": {"a": "#262A3A", "A": "#4A5068", "d": "#F2C230"},
    "coroa": {"a": "#F2C230", "A": "#D94040"},
    "tiara": {"a": "#E8C15A", "A": "#E05A8C"},
    "chapeu": {"a": "#4B3A9A", "A": "#FFD84D", "d": "#E8C15A"},
    "viking": {"a": "#EDE3C6", "A": "#B9BFC9", "d": "#C9962A"},
    "fone": {"a": "#3A3F4E", "A": None},
    "laco": {"a": "#E0507E", "A": "#B8325E"},
    "flor": {"a": "#F28DB2", "A": "#FFD84D", "d": "#3E9A5E"},
    "gato": {"a": "h", "A": "#F29CB2"},
    "aureola": {"a": "#FFE27A"},
    "faixa": {"a": "#C2413A", "A": "#962F2A"},
}

# óculos: desenhados na grade final (64 x 80), com linhas de 1 pixel em volta dos olhos.
# Cada molde: lista de (x, y, parte) para o olho da esquerda (o da direita é o mesmo 8 pixels ao lado)
# e extras (ponte, hastes). Partes: "a" armação, "A" lente que cobre o olho, "g" brilho, "c" corrente.
def _retangulo(x0, y0, x1, y1, cantos=True):
    pts = []
    for x in range(x0, x1 + 1):
        for y in (y0, y1):
            if cantos or x not in (x0, x1):
                pts.append((x, y))
    for y in range(y0 + 1, y1):
        pts += [(x0, y), (x1, y)]
    return pts


def _cheio(x0, y0, x1, y1):
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


_CORACAO = [".aa..aa.", "aAAaaAAa", "aAAAAAAa", ".aAAAAa.", "..aAAa..", "...aa..."]
OCULOS_HD = {
    "redondo": {"lente": [(x, y, "a") for x, y in _retangulo(25, 33, 30, 38, cantos=False)],
                "extras": [(31, 35, "a"), (32, 35, "a"), (23, 34, "a"), (24, 34, "a"), (39, 34, "a"), (40, 34, "a")]},
    "quadrado": {"lente": [(x, y, "a") for x, y in _retangulo(25, 33, 30, 38)],
                 "extras": [(31, 34, "a"), (32, 34, "a"), (23, 34, "a"), (24, 34, "a"), (39, 34, "a"), (40, 34, "a")]},
    "meia": {"lente": [(x, 33, "a") for x in range(25, 31)] + [(25, 34, "a"), (30, 34, "a")],
             "extras": [(31, 34, "a"), (32, 34, "a"), (23, 34, "a"), (24, 34, "a"), (39, 34, "a"), (40, 34, "a")]},
    "escuro": {"lente": [(x, y, "A") for x, y in _cheio(25, 34, 30, 37)] + [(x, 33, "a") for x in range(25, 31)] + [(26, 35, "g"), (27, 34, "g")],
               "extras": [(31, 34, "a"), (32, 34, "a"), (23, 34, "a"), (24, 34, "a"), (39, 34, "a"), (40, 34, "a")]},
    "coracao": {"lente": [(24 + i, 33 + j, ch) for j, linha in enumerate(_CORACAO) for i, ch in enumerate(linha) if ch != "."] + [(26, 34, "g")],
                "extras": []},
    "monoculo": {"so_direita": True, "lente": [(x, y, "a") for x, y in _retangulo(25, 33, 30, 38, cantos=False)],
                 "extras": [(39, 38, "c"), (39, 40, "c"), (40, 42, "c"), (40, 44, "c"), (39, 46, "c")]},
    "visor": {"lente": [], "extras": [(x, y, "A") for x, y in _cheio(24, 34, 39, 37)] + [(x, 33, "a") for x in range(23, 41)]
              + [(x, 38, "a") for x in range(23, 41)] + [(23, y, "a") for y in range(34, 38)] + [(40, y, "a") for y in range(34, 38)]
              + [(x, 35, "g") for x in range(26, 31)]},
}
LENTES = {"escuro": "#1C2030", "coracao": "#F06A9E", "visor": "#3FD0E6"}
OCULOS_COBREM_OLHOS = {"escuro", "coracao", "visor"}

# pescoço e costas: (na frente, atrás do corpo)
EXTRA_MOLDES = {
    "cachecol": ({23: "....aaaaaaaa....", 24: "....aAaAaAaA....", 25: ".....aA.........", 26: ".....Aa.........", 27: ".....aA........."}, {}),
    "medalha": ({24: ".....A....A.....", 25: "......A..A......", 26: ".......AA.......", 27: "......aaaa......", 28: "......aaaa......",
                 29: ".......aa......."}, {}),
    "gravata": ({24: ".....aaAAaa.....", 25: "......a..a......"}, {}),
    "colar": ({24: "....a......a....", 25: ".....a....a.....", 26: "......aAAa......"}, {}),
    "capa": ({24: ".......dd......."},
             {24: "...aaaaaaaaaa...", 25: "..aaaaaaaaaaaa..", **{y: ".aaaaaaaaaaaaaa." for y in range(26, 34)}, 34: "aaaaaaaaaaaaaaaa",
              35: "AAAAAAAAAAAAAAAA"}),
    "mochila": ({**{y: "....a......a...." for y in range(24, 30)}}, {**{y: "a..............a" for y in range(25, 31)}}),
}
CORES_EXTRA = {
    "cachecol": {"a": None, "A": "#F4F4F4"},  # None = cor que contrasta com a roupa
    "medalha": {"a": "#F2C230", "A": "#2F6BD8"},
    "gravata": {"a": "#C2413A", "A": "#962F2A"},
    "colar": {"a": "#E8C15A", "A": "#3FB0E6"},
    "capa": {"a": "#B83A3A", "A": "#8A2A2A", "d": "#F2C230"},
    "mochila": {"a": "#7A4E2D"},
}

# itens: (molde, x inicial)
ITEM_MOLDES = {
    "livro": ({26: "iiiij", 27: "iIiij", 28: "iiiij", 29: "iiiij", 30: "iiiij"}, 21),
    "lapis": ({13: "k.", 14: "jj", 15: "jj", **{y: "iI" for y in range(16, 28)}, 30: "gg", 31: "rr"}, 21),
    "cafe": ({26: "jjjj.", 27: "iiiii", 28: "iiii.i", 29: "iiiiii", 30: "iiii."}, 22),
    "espada": ({**{y: ".jJ.." for y in range(12, 26)}, 11: "..J..", 26: "iiiii", 27: ".II..", 28: ".II..", 29: ".II..", 30: "..i.."}, 21),
    "cajado": ({8: ".jJ.", 9: "jJjj", 10: "jjjj", 11: ".jj.", **{y: "..i." for y in range(12, 37)}}, 21),
}
CORES_ITEM = {
    "livro": {"i": "#B83A3A", "I": "#E8C15A", "j": "#F4EAD2"},
    "lapis": {"k": "#3B3B44", "j": "#E9C796", "i": "#F2C230", "I": "#D9A21C", "g": "#B9BFC9", "r": "#E7849A"},
    "cafe": {"i": "#F4F1EA", "j": "#6B3E26"},
    "espada": {"j": "#C9D1DC", "J": "#F4F7FB", "i": "#D9A21C", "I": "#7A4E2D"},
    "cajado": {"j": "#5CC8E8", "J": "#E6FBFF", "i": "#8A5A34"},
}

# braço levantado (para o aceno e para o pulo): pixels de manga ("c") e mão ("s")
BRACO_ACIMA_ESQ = [((9, 24), "c"), ((9, 23), "c"), ((8, 22), "c"), ((8, 21), "c"), ((7, 20), "s"), ((8, 20), "s"), ((7, 19), "s"), ((8, 19), "s")]
BRACO_ACIMA_DIR = [((22, 24), "c"), ((22, 23), "c"), ((23, 22), "c"), ((23, 21), "c"), ((23, 20), "s"), ((24, 20), "s"), ((23, 19), "s"), ((24, 19), "s")]


def _paleta(cfg: dict) -> dict[str, tuple]:
    pele = _rgb(PELES[cfg["pele"]][0])
    cab = _rgb(CORES_CABELO[cfg["cor_cabelo"]][0])
    roupa = _rgb(CORES_ROUPA[cfg["cor_roupa"]][0])
    detalhe = {
        "moletom": "#F4F4F4", "manto": "#E8C15A", "armadura": "#7A4E2D",
        "terno": "#C2413A" if cfg["cor_roupa"] not in (1, 6) else "#2340A8",
    }.get(cfg["roupa"], "#F4F4F4")
    return {
        "s": pele, "S": _escura(pele, 0.16), "r": _mistura(pele, (255, 110, 130), 0.42),
        "h": cab, "H": _escura(cab, 0.28), "L": cab,  # o brilho do cabelo é feito na grade final
        "e": _rgb(CORES_OLHOS[cfg["cor_olhos"]][0]), "w": (255, 255, 255, 255), "m": (128, 52, 58, 255),
        "c": roupa, "C": _escura(roupa, 0.22) if _luz(roupa) > 0.2 else _clara(roupa, 0.12), "d": _rgb(detalhe),
        "A": _rgb("#C9D1DC"), "p": _rgb("#2F3B5C"), "P": _rgb("#232C46"), "b": _rgb("#5A3E2B"), "B": _rgb("#3F2A1D"),
    }


def _cores_camada(tabela: dict, pal: dict) -> dict:
    """Cores de um acessório: None = cor da roupa (um tom mais escuro para "A"), "h" = cor do cabelo."""
    saida = {}
    for k, v in tabela.items():
        if v is None:
            saida[k] = pal["c"] if k != "A" else _escura(pal["c"], 0.25)
        elif v == "h":
            saida[k] = pal["h"]
        else:
            saida[k] = _rgb(v)
    return saida


def _cores_extra(cfg: dict, pal: dict) -> dict:
    cores = _cores_camada(CORES_EXTRA.get(cfg["extra"], {}), pal)
    if cfg["extra"] == "cachecol":
        cores["a"] = _rgb("#16928E") if cfg["cor_roupa"] in (1, 5, 6, 3) else _rgb("#C2413A")
    return cores


def _pintar(img: Image.Image, mat: Image.Image, molde: dict, paleta: dict, material, x0: int = 8, dy: int = 0,
            ate_y: int | None = None, desde_y: int | None = None) -> None:
    px, pm = img.load(), mat.load()
    for y, linha in molde.items():
        if ate_y is not None and y >= ate_y:
            continue
        if desde_y is not None and y < desde_y:
            continue
        yy = y + dy
        if not 0 <= yy < H:
            continue
        for i, ch in enumerate(linha):
            if ch in ". ":
                continue
            cor = paleta.get(ch)
            x = x0 + i
            if cor is not None and 0 <= x < W:
                px[x, yy] = cor
                pm[x, yy] = material if isinstance(material, int) else material.get(ch, M_ROUPA)


def _base(cfg: dict, respira: int = 0, braco: str = "", aceno: int = 0, vapor: int = 0):
    """Monta o boneco na grade 32 x 40 (cores e materiais), ainda sem rosto e sem contorno."""
    pal = _paleta(cfg)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mat = Image.new("L", (W, H), 0)
    d = respira  # o tronco e a cabeça descem um pixel ao respirar
    acess = cfg["acessorio"]
    corta = (ACESSORIO_MOLDES[acess][1] if acess in ACESSORIO_MOLDES else 0) or None
    extra = cfg["extra"]

    # costas: capa e mochila; cabelo de trás
    if extra in EXTRA_MOLDES and EXTRA_MOLDES[extra][1]:
        _pintar(img, mat, EXTRA_MOLDES[extra][1], _cores_extra(cfg, pal), M_EXTRA, dy=d)
    if cfg["cabelo"] in CABELO_ATRAS:
        _pintar(img, mat, CABELO_ATRAS[cfg["cabelo"]], pal, M_CABELO, dy=d, desde_y=corta)

    # corpo: pernas fixas, tronco acompanha a respiração
    pernas = {y: l for y, l in CORPO.items() if y >= 31}
    tronco = {y: l for y, l in CORPO.items() if y < 31}
    roupa = ROUPA_MOLDES.get(cfg["roupa"], {})
    _pintar(img, mat, pernas, pal, MAT_CORPO)
    _pintar(img, mat, {y: l for y, l in roupa.items() if y >= 31}, pal, MAT_CORPO)
    roupa_cima = {y: l for y, l in roupa.items() if y < 31}
    if braco:
        # some com o braço de baixo do lado que levanta
        tronco = {y: (".." + l[2:] if y >= 25 else l) for y, l in tronco.items()}
        roupa_cima = {y: (".." + l[2:] if y >= 25 else l) for y, l in roupa_cima.items()}
        if braco == "dois":
            tronco = {y: (l[:14] + ".." if y >= 25 else l) for y, l in tronco.items()}
            roupa_cima = {y: (l[:14] + ".." if y >= 25 else l) for y, l in roupa_cima.items()}
    _pintar(img, mat, tronco, pal, MAT_CORPO, dy=d)
    _pintar(img, mat, roupa_cima, pal, MAT_CORPO, dy=d)

    px, pm = img.load(), mat.load()
    if braco:
        manga = "s" if cfg["roupa"] == "vestido" else "c"
        lados = [BRACO_ACIMA_ESQ] + ([BRACO_ACIMA_DIR] if braco == "dois" else [])
        for lado in lados:
            for (x, y), ch in lado:
                xx = x - (1 if aceno and lado is BRACO_ACIMA_ESQ and y <= 20 else 0)
                if cfg["roupa"] == "armadura" and ch == "s":
                    px[xx, y + d], pm[xx, y + d] = pal["A"], M_METAL
                else:
                    letra = manga if ch == "c" else "s"
                    px[xx, y + d], pm[xx, y + d] = pal[letra], MAT_CORPO[letra]
    if cfg["roupa"] == "armadura" and not braco:
        for x in (9, 10, 21, 22):
            for y in (28, 29):
                px[x, y + d], pm[x, y + d] = pal["A"], M_METAL

    # pescoço (cachecol, medalha...), cabeça, cabelo, acessório, óculos
    if extra in EXTRA_MOLDES and EXTRA_MOLDES[extra][0]:
        _pintar(img, mat, EXTRA_MOLDES[extra][0], _cores_extra(cfg, pal), M_EXTRA, dy=d)
    _pintar(img, mat, CABECA, pal, MAT_CORPO, dy=d)
    _pintar(img, mat, CABELO_FRENTE.get(cfg["cabelo"], {}), pal, M_CABELO, dy=d, desde_y=corta)
    if acess in ACESSORIO_MOLDES:
        _pintar(img, mat, ACESSORIO_MOLDES[acess][0], _cores_camada(CORES_ACESSORIO[acess], pal), M_ACESS, dy=d)

    # item na mão (some quando os dois braços estão para cima)
    item = cfg["item"]
    if item in ITEM_MOLDES and braco != "dois":
        molde, x0 = ITEM_MOLDES[item]
        _pintar(img, mat, molde, {k: _rgb(v) for k, v in CORES_ITEM[item].items()}, M_ITEM, x0=x0, dy=d)
        if item == "cafe" and vapor:
            for i, (x, y) in enumerate(((23, 24), (24, 23), (23, 22))):
                if (vapor + i) % 3:
                    xx = x + (vapor % 2)
                    px[xx, y + d], pm[xx, y + d] = (255, 255, 255, 255), M_ROSTO
    return img, mat, pal


VAZIO5 = (0, 0, 0, 0, 0)


def _rgba(img: Image.Image) -> list[tuple]:
    """Os pixels RGBA como lista de tuplas (sem o getdata, que vai sair do Pillow)."""
    b = img.convert("RGBA").tobytes()
    return [tuple(b[i:i + 4]) for i in range(0, len(b), 4)]


def _epx(cores: list, w: int, h: int) -> list:
    """Dobra a grade (EPX/Scale2x): cada pixel vira 4 e as diagonais ficam arredondadas, sem borrar."""
    w2 = 2 * w
    out = [VAZIO5] * (4 * w * h)
    for y in range(h):
        base = y * w
        for x in range(w):
            P = cores[base + x]
            A = cores[base - w + x] if y else VAZIO5
            B = cores[base + x + 1] if x + 1 < w else VAZIO5
            C = cores[base + x - 1] if x else VAZIO5
            D = cores[base + w + x] if y + 1 < h else VAZIO5
            p1 = A if (C == A and C != D and A != B) else P
            p2 = B if (A == B and A != C and B != D) else P
            p3 = C if (D == C and D != B and C != A) else P
            p4 = D if (B == D and B != A and D != C) else P
            o = 2 * y * w2 + 2 * x
            out[o], out[o + 1], out[o + w2], out[o + w2 + 1] = p1, p2, p3, p4
    return out


SOMBREIA = {M_PELE, M_CABELO, M_ROUPA, M_CALCA, M_BOTA, M_METAL, M_ACESS, M_ITEM, M_EXTRA}
BRILHA = {M_CABELO, M_ROUPA, M_METAL, M_ACESS, M_ITEM, M_EXTRA}
CONTORNO_INTERNO = {M_ITEM, M_ACESS, M_EXTRA}


def _detalhar(px: list, cfg: dict, pal: dict, d2: int, piscando: bool, alegre: bool) -> list:
    """Na grade 64 x 80: luz e sombra, fios de cabelo, rosto (olhos, boca, bochechas) e contorno colorido."""
    L, A_ = W2, H2
    orig = px
    out = list(px)

    # luz de cima, sombra embaixo e à direita; contorno fino entre item/acessório e o resto
    for y in range(A_):
        for x in range(L):
            i = y * L + x
            r, g, b, a, m = orig[i]
            if not a or m in (M_ROSTO, M_OCULOS):
                continue
            c = (r, g, b, a)
            mb = orig[i + L][4] if y + 1 < A_ else 0
            md = orig[i + 1][4] if x + 1 < L else 0
            mc = orig[i - L][4] if y else 0
            me = orig[i - 1][4] if x else 0
            novo = c
            if m in CONTORNO_INTERNO and any(n not in (0, m, M_ROSTO) for n in (mb, md, mc, me)):
                novo = _mistura(c, CONTORNO, 0.42)
            elif m in SOMBREIA and (mb != m or md != m):
                novo = _escura(c, 0.13)
            elif m in BRILHA and mc == 0:
                novo = _clara(c, 0.18)
            if m == M_PELE and mc == M_CABELO:
                novo = _escura(c, 0.2)  # sombra do cabelo na testa
            if m == M_CABELO and mc == M_CABELO and mb == M_CABELO and (x + 2 * y) % 9 == 0:
                novo = _escura(novo, 0.12)  # fios
            if m == M_ROUPA and 56 + d2 <= y <= 61 + d2 and x % 2 == 0 and y % 2 == 0:
                novo = _escura(novo, 0.06)  # sombra pontilhada na barriga
            if novo != c:
                out[i] = novo[:4] + (m,)

    # brilho do cabelo: uma faixa clara que acompanha o topo da cabeça, do lado da luz
    for x in range(21, 35):
        topo = next((y for y in range(0, 44) if orig[y * L + x][4] == M_CABELO), None)
        if topo is None:
            continue
        for yy in (topo + 2, topo + 3):
            i = yy * L + x
            if orig[i][4] == M_CABELO and orig[i + L][4] == M_CABELO:
                out[i] = _clara(out[i], 0.24)[:4] + (M_CABELO,)
    if cfg["cabelo"] == "careca":
        for y in (26 + d2, 27 + d2):
            for x in range(25, 30):
                i = y * L + x
                if orig[i][4] == M_PELE and (y == 26 + d2 or 26 <= x <= 28):
                    out[i] = _clara(pal["s"], 0.35)[:4] + (M_PELE,)

    def pinta(x, y, cor, so_pele=True):
        if 0 <= x < L and 0 <= y < A_:
            i = y * L + x
            if so_pele and orig[i][4] not in (M_PELE, M_ROSTO):
                return
            out[i] = cor[:4] + (M_ROSTO,)

    pele = pal["s"]
    e = pal["e"]
    cilio = _mistura(CONTORNO, e, 0.15)
    estilo = "feliz" if alegre else cfg["olhos"]
    sobrancelha = pal["H"] if cfg["cabelo"] != "careca" else _escura(pele, 0.45)
    if not cfg["oculos"] in OCULOS_COBREM_OLHOS:
        for x0, lado in ((26, -1), (34, 1)):
            y0 = 34 + d2
            fora = x0 - 1 if lado < 0 else x0 + 4
            if piscando:
                for k in range(4):
                    pinta(x0 + k, y0 + 2, cilio)
                pinta(fora, y0 + 2, cilio)
                continue
            if estilo == "feliz":
                for dx, dy in ((-1, 3), (0, 2), (1, 1), (2, 1), (3, 2), (4, 3)):
                    pinta(x0 + dx, y0 + dy, cilio)
                continue
            for k in range(4):
                pinta(x0 + k, y0, cilio)
            pinta(fora, y0 - 1, cilio)
            for k, cor in enumerate(((255, 255, 255, 255), e, e, e)):
                pinta(x0 + k, y0 + 1, cor)
            for k, cor in enumerate((e, _escura(e, 0.6), _escura(e, 0.6), e)):
                pinta(x0 + k, y0 + 2, cor)
            for k in range(4):
                pinta(x0 + k, y0 + 3, _clara(e, 0.32))
            if estilo == "determinado":
                pts = ((-1, -2), (0, -2), (1, -2), (2, -1), (3, -1)) if lado < 0 else ((0, -1), (1, -1), (2, -2), (3, -2), (4, -2))
                for dx, dy in pts:
                    pinta(x0 + dx, y0 + dy, sobrancelha)
            else:
                for dx in (1, 2):
                    pinta(x0 + dx, y0 - 2, _mistura(sobrancelha, pele, 0.45))
    # bochechas, nariz e boca
    for x, y in ((23, 38), (25, 38), (24, 39), (38, 38), (40, 38), (39, 39)):
        pinta(x, y + d2, pal["r"])
    pinta(31, 39 + d2, _escura(pele, 0.12))
    boca, lingua = pal["m"], (232, 112, 122, 255)
    y0 = 40 + d2
    if alegre:
        for k in range(4):
            pinta(30 + k, y0, boca)
        for k, cor in enumerate((boca, lingua, lingua, boca)):
            pinta(30 + k, y0 + 1, cor)
        pinta(31, y0 + 2, boca)
        pinta(32, y0 + 2, boca)
    else:
        for x, y in ((30, y0), (31, y0 + 1), (32, y0 + 1), (33, y0)):
            pinta(x, y, boca)

    # óculos (linhas finas na grade final), por cima dos olhos
    oc = cfg["oculos"]
    if oc in OCULOS_HD:
        arm = _rgb(CORES_OCULOS[cfg["cor_oculos"]][0])
        if oc == "monoculo" and cfg["cor_oculos"] == 0:
            arm = _rgb("#D9A21C")
        lente = _rgb(LENTES.get(oc, "#1C2030"))
        cores = {"a": arm, "A": lente, "g": (255, 255, 255, 255), "c": _clara(arm, 0.2)}
        if oc == "coracao":
            cores["a"] = _escura(lente, 0.25) if cfg["cor_oculos"] in (0, 6) else arm
        dados = OCULOS_HD[oc]
        deslocamentos = (8,) if dados.get("so_direita") else (0, 8)
        pontos = [(x + dx, y, p) for dx in deslocamentos for x, y, p in dados["lente"]] + list(dados["extras"])
        for x, y, parte in pontos:
            yy = y + d2
            if 0 <= x < L and 0 <= yy < A_ and orig[yy * L + x][3]:
                out[yy * L + x] = cores[parte][:4] + (M_OCULOS,)

    # contorno colorido de 1 pixel: escuro embaixo e à direita, tom da peça em cima e à esquerda
    final = list(out)
    for y in range(A_):
        for x in range(L):
            i = y * L + x
            if out[i][3]:
                continue
            escuro = False
            vizinho = None
            if y and out[i - L][3]:
                escuro = True
            if x and out[i - 1][3]:
                escuro = True
            if not escuro:
                if y + 1 < A_ and out[i + L][3]:
                    vizinho = out[i + L]
                elif x + 1 < L and out[i + 1][3]:
                    vizinho = out[i + 1]
                if vizinho is None:
                    continue
            cor = CONTORNO if escuro else _mistura(vizinho, CONTORNO, 0.68)
            final[i] = cor[:4] + (M_VAZIO,)
    return final


@lru_cache(maxsize=2048)
def _boneco_cache(chave_cfg: tuple, chave_kw: tuple) -> Image.Image:
    cfg, kw = dict(chave_cfg), dict(chave_kw)
    img, mat, pal = _base(cfg, kw.get("respira", 0), kw.get("braco", ""), kw.get("aceno", 0), kw.get("vapor", 0))
    cores = [c + (m,) for c, m in zip(_rgba(img), mat.tobytes())]
    cores = [c if c[3] else VAZIO5 for c in cores]
    hd = _detalhar(_epx(cores, W, H), cfg, pal, 2 * kw.get("respira", 0), kw.get("piscando", False), kw.get("alegre", False))
    saida = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    saida.putdata([p[:4] for p in hd])
    pulo = 2 * kw.get("pulo", 0)
    if pulo:
        sobe = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        sobe.paste(saida, (0, -pulo), saida)
        saida = sobe
    return saida


def boneco(cfg: dict, respira: int = 0, piscando: bool = False, braco: str = "", aceno: int = 0, alegre: bool = False,
           pulo: int = 0, vapor: int = 0) -> Image.Image:
    """Um quadro do personagem (64 x 80, fundo transparente, com contorno). Não altere a imagem devolvida (fica guardada).

    respira: 0/1 (o tronco desce); braco: "", "aceno" ou "dois"; pulo: quanto sobe (em pixels da grade de montagem)."""
    cfg = validar(cfg)
    kw = {"respira": respira, "piscando": piscando, "braco": braco, "aceno": aceno, "alegre": alegre, "pulo": pulo,
          "vapor": vapor % 6 if cfg["item"] == "cafe" else 0}
    return _boneco_cache(tuple(sorted(cfg.items())), tuple(sorted(kw.items())))


def _sombra(largura: int) -> Image.Image:
    """Sombra no chão, embaixo dos pés (largura em pixels da grade final)."""
    s = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    px = s.load()
    meio = W2 / 2
    for x in range(W2):
        dist = abs(x + 0.5 - meio)
        if dist <= largura / 2:
            px[x, 75] = (20, 16, 32, 64)
        if dist <= largura / 2 - 3:
            px[x, 76] = (20, 16, 32, 46)
    return s


# ---------------------------------------------------------------- animações

def _quadros_parado(cfg, n_ciclos=1):
    seq = []
    for _ in range(n_ciclos):
        for i in range(12):
            seq.append((dict(respira=1 if 4 <= i < 8 else 0, piscando=(i == 10), vapor=i), 120))
    return seq


def _quadros_aceno(cfg):
    seq = [(dict(braco="aceno", aceno=i % 2, alegre=True, vapor=i), 150) for i in range(8)]
    return seq


def _quadros_pulo(cfg):
    altura = [0, 2, 4, 5, 5, 4, 2, 0]
    seq = [(dict(respira=1, alegre=True), 110)]
    for i, h in enumerate(altura[1:-1]):
        seq.append((dict(braco="dois", pulo=h, alegre=True), 80))
    seq.append((dict(respira=1, alegre=True), 110))
    seq.append((dict(alegre=True), 160))
    return seq


SEQUENCIAS = {
    "parado": lambda c: _quadros_parado(c, 1),
    "aceno": lambda c: _quadros_parado(c, 1)[:4] + _quadros_aceno(c) + _quadros_parado(c, 1)[:6],
    "pulo": lambda c: _quadros_pulo(c) + _quadros_pulo(c) + _quadros_parado(c, 1)[:6],
    "lobby": lambda c: _quadros_parado(c, 3) + _quadros_aceno(c) + _quadros_parado(c, 2) + _quadros_pulo(c) + _quadros_parado(c, 1),
}


def _sequencia_membro(semente: str):
    """Para a sala da turma: cada pessoa faz a sua dança em hora diferente (todas com a mesma duração)."""
    rnd = random.Random(semente)
    gesto = rnd.choice(["aceno", "pulo", "aceno"])
    antes = rnd.randrange(0, 4)
    base = _quadros_parado(None, 5)  # 60 quadros, 7,2 s
    extra = _quadros_aceno(None) if gesto == "aceno" else _quadros_pulo(None)
    i = antes * 12
    seq = base[:i] + extra + base[i + len(extra):]
    return seq[: len(base)]


# ---------------------------------------------------------------- cenários (64 x 40)

def _cenario(nome: str, largura: int = 64, quadro: int = 0) -> Image.Image:
    img = Image.new("RGBA", (largura, H), (0, 0, 0, 255))
    px = img.load()
    rnd = random.Random(nome)

    def ret(x0, y0, x1, y1, cor):
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(largura, x1)):
                px[x, y] = cor

    if nome == "biblioteca":
        ret(0, 0, largura, H, _rgb("#EADFC6"))
        for prateleira in (6, 17):
            ret(0, prateleira + 8, largura, prateleira + 10, _rgb("#8A5A34"))
            x = 1
            while x < largura - 2:
                larg = rnd.choice((2, 2, 3))
                alt = rnd.choice((6, 7, 8))
                cor = _rgb(rnd.choice(["#B83A3A", "#2340A8", "#2E8B57", "#E2B42F", "#6E4BB8", "#16928E", "#E07B2C"]))
                ret(x, prateleira + 8 - alt, x + larg, prateleira + 8, cor)
                ret(x, prateleira + 8 - alt + 1, x + larg, prateleira + 8 - alt + 2, _clara(cor, 0.35))
                x += larg + (1 if rnd.random() < 0.25 else 0)
        ret(0, 30, largura, H, _rgb("#9B6B43"))
        for x in range(0, largura, 8):
            ret(x, 30, x + 1, H, _rgb("#875A36"))
        ret(0, 30, largura, 31, _rgb("#B88457"))
    elif nome == "floresta":
        for y in range(H):
            ret(0, y, largura, y + 1, _mistura(_rgb("#9ED3F5"), _rgb("#E6F6FF"), y / 30))
        for i in range(largura // 9 + 2):
            cx = i * 9 + rnd.randrange(-2, 3)
            for y in range(10, 30):
                meia = max(0, (y - 10) // 2)
                ret(cx - meia, y, cx + meia + 1, y + 1, _rgb("#7FBF8A"))
        for i in range(largura // 14 + 2):
            cx = i * 14 + 5 + rnd.randrange(-2, 3)
            ret(cx - 1, 22, cx + 1, 31, _rgb("#6E4A2D"))
            for y in range(8, 24):
                meia = max(1, (y - 6) // 2)
                ret(cx - meia, y, cx + meia, y + 1, _rgb("#3E8F55") if y % 4 else _rgb("#357C49"))
        ret(0, 30, largura, H, _rgb("#5DAA5B"))
        ret(0, 30, largura, 31, _rgb("#78C26E"))
        for i in range(6):
            x = rnd.randrange(largura)
            ret(x, 33 + rnd.randrange(5), x + 1, 34 + rnd.randrange(5), _rgb(rnd.choice(["#FFD84D", "#F28DB2", "#FFFFFF"])))
    elif nome == "noite":
        for y in range(H):
            ret(0, y, largura, y + 1, _mistura(_rgb("#141B36"), _rgb("#2C3A6B"), y / 34))
        for i in range(largura // 3):
            x, y = rnd.randrange(largura), rnd.randrange(22)
            if (i + quadro // 3) % 5:
                px[x, y] = (255, 255, 255, 255) if i % 3 else (255, 230, 150, 255)
        mx = largura - 12
        for y in range(4, 12):
            for x in range(mx - 4, mx + 4):
                if (x - mx + 0.5) ** 2 + (y - 8 + 0.5) ** 2 <= 14:
                    px[x, y] = _rgb("#F6E7A1")
        x = 0
        while x < largura:
            larg, alt = rnd.randrange(5, 10), rnd.randrange(8, 18)
            ret(x, 30 - alt, x + larg, 30, _rgb("#0E1428"))
            for jy in range(30 - alt + 2, 29, 3):
                for jx in range(x + 1, x + larg - 1, 2):
                    if rnd.random() < 0.35 and jx < largura:
                        px[jx, jy] = _rgb("#FFD84D")
            x += larg + 1
        ret(0, 30, largura, H, _rgb("#1C2440"))
        ret(0, 30, largura, 31, _rgb("#2A3560"))
    elif nome == "castelo":
        ret(0, 0, largura, H, _rgb("#8E95A6"))
        for y in range(0, 30, 4):
            ret(0, y, largura, y + 1, _rgb("#767D8F"))
            off = 0 if (y // 4) % 2 else 4
            for x in range(off, largura, 8):
                ret(x, y, x + 1, y + 4, _rgb("#767D8F"))
        for i, cx in enumerate(range(8, largura, 24)):
            cor = _rgb(["#B83A3A", "#2340A8", "#2E8B57"][i % 3])
            ret(cx, 4, cx + 7, 18, cor)
            ret(cx + 3, 7, cx + 4, 13, _rgb("#F2C230"))
            for k in range(3):
                ret(cx + k, 18 + k, cx + 7 - k, 19 + k, cor)
        for cx in range(20, largura, 24):
            ret(cx, 12, cx + 2, 18, _rgb("#6E4A2D"))
            chama = ["#FFD84D", "#F29B38", "#E25A2A"]
            alt = 3 + (quadro // 2) % 2
            for k in range(alt):
                ret(cx, 12 - k - 1, cx + 2, 12 - k, _rgb(chama[min(k, 2)]))
        ret(0, 30, largura, H, _rgb("#5F6474"))
        for x in range(0, largura, 6):
            ret(x, 30, x + 1, H, _rgb("#545868"))
        ret(0, 30, largura, 31, _rgb("#727788"))
    else:  # sala de aula
        ret(0, 0, largura, H, _rgb("#DCE6F2"))
        ret(4, 4, largura - 4, 22, _rgb("#6E4A2D"))
        ret(5, 5, largura - 5, 21, _rgb("#2F5D47"))
        giz = _rgb("#EAF2EC")
        for x, y in ((9, 9), (10, 9), (11, 9), (9, 10), (11, 10), (9, 11), (10, 11), (11, 11), (9, 12), (11, 12), (9, 13), (11, 13),
                     (14, 11), (13, 11), (15, 11), (14, 10), (14, 12)):
            px[x, y] = giz
        for linha in range(3):
            fim = largura - 9 - linha * 6
            for x in range(20, fim):
                if (x + linha) % 5 != 4:
                    px[x, 9 + linha * 3] = _mistura(giz, _rgb("#2F5D47"), 0.4)
        ret(0, 30, largura, H, _rgb("#B88A5A"))
        for x in range(0, largura, 7):
            ret(x, 30, x + 1, H, _rgb("#A27648"))
        ret(0, 30, largura, 31, _rgb("#CFA06E"))
    return img


@lru_cache(maxsize=256)
def _cenario_hd(nome: str, largura: int = 64, quadro: int = 0) -> Image.Image:
    """O cenário na grade final (dobrado com o EPX). Não altere a imagem devolvida (fica guardada)."""
    base = _cenario(nome, largura, quadro)
    cores = [c + (0,) for c in _rgba(base)]
    hd = _epx(cores, largura, H)
    img = Image.new("RGBA", (2 * largura, H2))
    img.putdata([p[:4] for p in hd])
    return img


def _quadro_cena(nome: str, largura: int, i: int) -> Image.Image:
    """Só a noite (estrelas) e o castelo (tochas) mexem; os outros cenários são parados."""
    q = i % 15 if nome == "noite" else (i % 4 if nome == "castelo" else 0)
    return _cenario_hd(nome, largura, q)


# ---------------------------------------------------------------- saída

def _webp(quadros: list[tuple[Image.Image, int]]) -> bytes:
    b = io.BytesIO()
    imgs = [q for q, _ in quadros]
    imgs[0].save(b, "WEBP", save_all=True, append_images=imgs[1:], duration=[d for _, d in quadros], loop=0, lossless=True, method=4)
    return b.getvalue()


def _ampliar(img: Image.Image, escala: int) -> Image.Image:
    return img if escala == 1 else img.resize((img.width * escala, img.height * escala), Image.NEAREST)


def _sombra_pulo(kw: dict) -> Image.Image:
    return _sombra(24 - min(12, 2 * kw.get("pulo", 0)))


def animacao(cfg: dict, anim: str = "lobby", escala: int = 2, cenario: bool = True, largura: int = 64) -> bytes:
    """WebP animado do personagem (cada pixel da grade final vira escala x escala).

    Com cenário: (2 x largura) x 80 com o boneco no meio; sem cenário: 64 x 80, fundo transparente."""
    cfg = validar(cfg)
    seq = SEQUENCIAS.get(anim, SEQUENCIAS["parado"])(cfg)
    x = largura - W2 // 2
    quadros = []
    for i, (kw, dur) in enumerate(seq):
        b = boneco(cfg, **kw)
        if cenario:
            q = _quadro_cena(cfg["cenario"], largura, i).copy()
            q.alpha_composite(_sombra_pulo(kw), (x, 0))
            q.alpha_composite(b, (x, 0))
        else:
            q = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
            q.alpha_composite(_sombra_pulo(kw))
            q.alpha_composite(b)
        quadros.append((_ampliar(q, escala), dur))
    return _webp(quadros)


def membro(cfg: dict, semente: str, escala: int = 1) -> bytes:
    """O boneco de uma pessoa na sala da turma (64 x 80 por escala, fundo transparente, com gesto próprio)."""
    cfg = validar(cfg)
    quadros = []
    for kw, dur in _sequencia_membro(semente):
        q = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        q.alpha_composite(_sombra_pulo(kw))
        q.alpha_composite(boneco(cfg, **kw))
        quadros.append((_ampliar(q, escala), dur))
    return _webp(quadros)


def cenario_png(nome: str, largura: int = 64, escala: int = 1, quadros: int = 1) -> bytes:
    """O cenário sozinho, (2 x largura) x 80 por escala. Com quadros > 1, sai animado (estrelas, tochas)."""
    nome = nome if nome in {c[0] for c in CENARIOS} else "biblioteca"
    if quadros <= 1:
        b = io.BytesIO()
        _ampliar(_cenario_hd(nome, largura, 0), escala).save(b, "PNG")
        return b.getvalue()
    return _webp([(_ampliar(_quadro_cena(nome, largura, i), escala), 150) for i in range(quadros)])


def rosto(cfg: dict, escala: int = 1, piscar: bool = True) -> bytes:
    """Busto (cabeça e ombros) para as listas: 40 x 40 por escala, fundo transparente, com uma piscada de vez em quando."""
    cfg = validar(cfg)
    caixa = (12, 14, 52, 54) if cfg["acessorio"] not in ("chapeu", "aureola") else (12, 4, 52, 44)

    def recorte(img):
        return _ampliar(img.crop(caixa), escala)

    aberto = recorte(boneco(cfg))
    if not piscar:
        b = io.BytesIO()
        aberto.save(b, "PNG")
        return b.getvalue()
    fechado = recorte(boneco(cfg, piscando=True))
    return _webp([(aberto, 3200), (fechado, 130), (aberto, 2400), (fechado, 120)])


def cor_fundo(cfg: dict) -> str:
    """Cor de fundo do círculo do busto (um tom claro da roupa)."""
    c = _rgb(CORES_ROUPA[validar(cfg)["cor_roupa"]][0])
    m = _mistura(c, (255, 255, 255), 0.78)
    return "#%02X%02X%02X" % m[:3]


def preparar_foto(dados: bytes, lado: int = 256) -> bytes:
    """Foto de perfil: recorta o meio em quadrado, diminui e tira os metadados (WebP pequeno)."""
    from PIL import ImageOps

    if not dados or len(dados) > 20 * 1024 * 1024:
        raise ValueError("A foto precisa ter até 20 MB.")
    img = Image.open(io.BytesIO(dados))
    img.load()
    img = ImageOps.exif_transpose(img).convert("RGB")
    lado_min = min(img.size)
    if lado_min < 32:
        raise ValueError("A foto é pequena demais.")
    x0, y0 = (img.width - lado_min) // 2, (img.height - lado_min) // 2
    img = img.crop((x0, y0, x0 + lado_min, y0 + lado_min)).resize((lado, lado), Image.LANCZOS)
    b = io.BytesIO()
    img.save(b, "WEBP", quality=82, method=5)
    return b.getvalue()


def agora() -> int:
    return int(time.time())
