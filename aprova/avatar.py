"""Personagem do Aprova: um bonequinho em pixel art, estilo RPG, montado em camadas.

O personagem é só uma configuração pequena (cores e estilos), por exemplo
{"pele": 2, "cabelo": "curto", "roupa": "moletom", "item": "livro", ...}. Ela vai para o
servidor (perfis.avatar) e cada computador desenha o boneco a partir dela, então ninguém
manda imagem: só escolhas de uma lista fechada.

Desenho: uma grade de 32 x 40 pixels. Cada parte (cabeça, cabelo, roupa, acessório, item)
é um molde em texto, onde cada letra é uma cor. No fim, o contorno escuro é posto em volta
de tudo e a imagem é ampliada sem borrar (cada pixel vira um quadradinho).

Animações (WebP animado, que o app mostra sozinho): parado (respira e pisca), aceno,
pulo e o "lobby", que mistura os três como nas telas de espera dos jogos.
"""

from __future__ import annotations

import hashlib
import io
import random
import time

from PIL import Image

W, H = 32, 40
CONTORNO = (31, 26, 46, 255)

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
ACESSORIOS = [("nenhum", "Nenhum"), ("oculos", "Óculos"), ("bone", "Boné"), ("fone", "Fone"), ("laco", "Laço"), ("coroa", "Coroa"), ("chapeu", "Chapéu de mago")]
ITENS = [("nenhum", "Nada"), ("livro", "Livro"), ("lapis", "Lápis gigante"), ("cafe", "Café"), ("espada", "Espada"), ("cajado", "Cajado")]
CENARIOS = [("biblioteca", "Biblioteca"), ("floresta", "Floresta"), ("noite", "Noite na cidade"), ("castelo", "Castelo"), ("sala", "Sala de aula")]

CATEGORIAS = {"cabelo": CABELOS, "olhos": OLHOS, "roupa": ROUPAS, "acessorio": ACESSORIOS, "item": ITENS, "cenario": CENARIOS}
CORES = {"pele": PELES, "cor_cabelo": CORES_CABELO, "cor_olhos": CORES_OLHOS, "cor_roupa": CORES_ROUPA}

PADRAO = {"v": 1, "pele": 1, "cabelo": "curto", "cor_cabelo": 1, "olhos": "normal", "cor_olhos": 0, "roupa": "moletom", "cor_roupa": 0,
          "acessorio": "nenhum", "item": "livro", "cenario": "biblioteca", "usar_foto": False, "foto": 0, "t": 0}


def validar(cfg) -> dict:
    """Só passa o que o app conhece. Serve para o que vem do servidor (de outras pessoas) e para o que vem do disco."""
    saida = dict(PADRAO)
    if not isinstance(cfg, dict):
        return saida
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
    21: "...sSssssssSs...",
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
    "careca": {
        13: "......LL........",
    },
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

ACESSORIO_MOLDES = {
    "oculos": ({16: ".....aa..aa.....", 17: "....a..aa..a....", 18: "....a..aa..a....", 19: ".....aa..aa....."}, 99),
    "bone": ({10: "....aaaaaaaa....", 11: "...aaaaaaaaaa...", 12: "..aaaaaAAaaaaa..", 13: "..aaaaaaaaaaaa..", 14: ".dddddddddddddd."}, 15),
    "fone": ({10: "....aaaaaaaa....", 11: "...a........a...", 12: "..a..........a..", 13: ".a............a.", 14: ".a............a.",
              15: ".a............a.", 16: "AA............AA", 17: "AA............AA", 18: "AA............AA", 19: "AA............AA"}, 0),
    "laco": ({9: ".........aa.aa..", 10: ".........aaAaa..", 11: "..........a.a..."}, 0),
    "coroa": ({7: "....a..aa..a....", 8: "....aa.aa.aa....", 9: "....aaaAAaaa....", 10: "....aaaaaaaa...."}, 0),
    "chapeu": ({0: "..........a.....", 1: ".........aa.....", 2: "........aaa.....", 3: ".......aaaa.....", 4: "......aaAaa.....",
                5: "......aaaaaa....", 6: ".....aaaaaaa....", 7: ".....aaaaaaaa...", 8: "....aaaAaaaaa...", 9: "....aaaaaaaaa...",
                10: "...dddddddddd...", 11: ".aaaaaaaaaaaaaa.", 12: "aaaaaaaaaaaaaaaa"}, 13),
}
CORES_ACESSORIO = {
    "oculos": {"a": "#3A4258"},
    "bone": {"a": None, "A": "#FFFFFF", "d": None},  # cor da roupa
    "fone": {"a": "#3A3F4E", "A": None},
    "laco": {"a": "#E0507E", "A": "#B8325E"},
    "coroa": {"a": "#F2C230", "A": "#D94040"},
    "chapeu": {"a": "#4B3A9A", "A": "#FFD84D", "d": "#E8C15A"},
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
        "s": pele, "S": _escura(pele, 0.16), "r": _mistura(pele, (255, 110, 130), 0.35),
        "h": cab, "H": _escura(cab, 0.28), "L": _clara(cab, 0.32) if _luz(cab) < 0.8 else _escura(cab, 0.1),
        "e": _rgb(CORES_OLHOS[cfg["cor_olhos"]][0]), "w": (255, 255, 255, 255), "m": (128, 52, 58, 255),
        "c": roupa, "C": _escura(roupa, 0.22) if _luz(roupa) > 0.2 else _clara(roupa, 0.12), "d": _rgb(detalhe),
        "A": _rgb("#C9D1DC"), "p": _rgb("#2F3B5C"), "P": _rgb("#232C46"), "b": _rgb("#5A3E2B"), "B": _rgb("#3F2A1D"),
    }


def _pintar(img: Image.Image, molde: dict, paleta: dict, x0: int = 8, dy: int = 0, ate_y: int | None = None, desde_y: int | None = None) -> None:
    px = img.load()
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


def _olhos(img: Image.Image, cfg: dict, pal: dict, dy: int, fechado: bool, alegre: bool) -> None:
    px = img.load()
    e, w = pal["e"], pal["w"]
    estilo = "feliz" if alegre else cfg["olhos"]

    def p(x, y, c):
        if 0 <= y + dy < H:
            px[x, y + dy] = c

    for x0 in (13, 17):
        if fechado:
            p(x0, 18, _escura(pal["s"], 0.55))
            p(x0 + 1, 18, _escura(pal["s"], 0.55))
        elif estilo == "feliz":
            # "^": três pixels, o do meio mais alto
            x = x0 - 1 if x0 == 13 else x0
            p(x, 18, e)
            p(x + 1, 17, e)
            p(x + 2, 18, e)
        else:
            p(x0, 17, w)
            p(x0 + 1, 17, e)
            p(x0, 18, e)
            p(x0 + 1, 18, e)
            if estilo == "determinado":
                p(x0, 16, pal["H"] if cfg["cabelo"] != "careca" else _escura(pal["s"], 0.4))
                p(x0 + 1, 16, pal["H"] if cfg["cabelo"] != "careca" else _escura(pal["s"], 0.4))
    # bochechas e boca
    p(12, 19, pal["r"])
    p(19, 19, pal["r"])
    if alegre:
        p(15, 20, pal["m"])
        p(16, 20, pal["m"])
        p(15, 21, pal["r"])
        p(16, 21, pal["m"])
    else:
        p(15, 20, pal["m"])
        p(16, 20, pal["m"])


def _contorno(img: Image.Image) -> Image.Image:
    src = img.load()
    out = img.copy()
    dst = out.load()
    for y in range(H):
        for x in range(W):
            if src[x, y][3]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and src[nx, ny][3]:
                    dst[x, y] = CONTORNO
                    break
    return out


def boneco(cfg: dict, respira: int = 0, piscando: bool = False, braco: str = "", aceno: int = 0, alegre: bool = False,
           pulo: int = 0, vapor: int = 0) -> Image.Image:
    """Um quadro do personagem (32 x 40, fundo transparente, com contorno).

    respira: 0/1 (o tronco desce um pixel); braco: "", "aceno" ou "dois"; pulo: pixels para cima."""
    cfg = validar(cfg)
    pal = _paleta(cfg)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = respira  # deslocamento do tronco e da cabeça

    acess = cfg["acessorio"]
    corta = ACESSORIO_MOLDES[acess][1] if acess in ACESSORIO_MOLDES else 0

    # cabelo de trás
    if cfg["cabelo"] in CABELO_ATRAS:
        _pintar(img, CABELO_ATRAS[cfg["cabelo"]], pal, dy=d, desde_y=corta if corta and corta < 90 else None)

    # corpo: pernas fixas, tronco acompanha a respiração
    pernas = {y: l for y, l in CORPO.items() if y >= 31}
    tronco = {y: l for y, l in CORPO.items() if y < 31}
    roupa = ROUPA_MOLDES.get(cfg["roupa"], {})
    _pintar(img, pernas, pal)
    _pintar(img, {y: l for y, l in roupa.items() if y >= 31}, pal)
    if braco:
        # some com o braço de baixo do lado que levanta
        tronco = {y: (".." + l[2:] if y >= 25 else l) for y, l in tronco.items()}
        if braco == "dois":
            tronco = {y: (l[:14] + ".." if y >= 25 else l) for y, l in tronco.items()}
    _pintar(img, tronco, pal, dy=d)
    roupa_cima = {y: l for y, l in roupa.items() if y < 31}
    if braco:
        roupa_cima = {y: (".." + l[2:] if y >= 25 else l) for y, l in roupa_cima.items()}
        if braco == "dois":
            roupa_cima = {y: (l[:14] + ".." if y >= 25 else l) for y, l in roupa_cima.items()}
    _pintar(img, roupa_cima, pal, dy=d)

    px = img.load()
    if braco:
        manga = "s" if cfg["roupa"] == "vestido" else "c"
        for (x, y), ch in BRACO_ACIMA_ESQ:
            xx = x - (1 if aceno and y <= 20 else 0)
            px[xx, y + d] = pal[manga if ch == "c" else "s"] if cfg["roupa"] != "armadura" or ch == "c" else pal["A"]
        if braco == "dois":
            for (x, y), ch in BRACO_ACIMA_DIR:
                px[x, y + d] = pal[manga if ch == "c" else "s"] if cfg["roupa"] != "armadura" or ch == "c" else pal["A"]
    if cfg["roupa"] == "armadura" and not braco:
        for x in (9, 10, 21, 22):
            for y in (28, 29):
                px[x, y + d] = pal["A"]

    # cabeça, rosto, cabelo, acessório
    _pintar(img, CABECA, pal, dy=d)
    _olhos(img, cfg, pal, d, piscando, alegre)
    _pintar(img, CABELO_FRENTE.get(cfg["cabelo"], {}), pal, dy=d, desde_y=corta if corta and corta < 90 else None)
    if acess in ACESSORIO_MOLDES:
        cores = {k: (_rgb(v) if v else pal["c"]) for k, v in CORES_ACESSORIO[acess].items()}
        if acess == "bone":
            cores["d"] = _escura(pal["c"], 0.3)
        _pintar(img, ACESSORIO_MOLDES[acess][0], cores, dy=d)

    # item na mão (some quando os dois braços estão para cima)
    item = cfg["item"]
    if item in ITEM_MOLDES and braco != "dois":
        molde, x0 = ITEM_MOLDES[item]
        _pintar(img, molde, {k: _rgb(v) for k, v in CORES_ITEM[item].items()}, x0=x0, dy=d)
        if item == "cafe" and vapor:
            for i, (x, y) in enumerate(((23, 24), (24, 23), (23, 22))):
                if (vapor + i) % 3:
                    px[x + (vapor % 2), y + d] = (255, 255, 255, 170)

    img = _contorno(img)
    if pulo:
        sobe = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sobe.paste(img, (0, -pulo), img)
        img = sobe
    return img


def _sombra(largura: int) -> Image.Image:
    s = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = s.load()
    meio = W / 2
    for x in range(W):
        if abs(x + 0.5 - meio) <= largura / 2:
            px[x, 37] = (20, 16, 32, 70)
            if abs(x + 0.5 - meio) <= largura / 2 - 1.5:
                px[x, 38] = (20, 16, 32, 55)
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


# ---------------------------------------------------------------- saída

def _webp(quadros: list[tuple[Image.Image, int]]) -> bytes:
    b = io.BytesIO()
    imgs = [q for q, _ in quadros]
    imgs[0].save(b, "WEBP", save_all=True, append_images=imgs[1:], duration=[d for _, d in quadros], loop=0, lossless=True, method=4)
    return b.getvalue()


def _ampliar(img: Image.Image, escala: int) -> Image.Image:
    return img.resize((img.width * escala, img.height * escala), Image.NEAREST)


def animacao(cfg: dict, anim: str = "lobby", escala: int = 6, cenario: bool = True) -> bytes:
    """WebP animado do personagem. Com cenário: 64 x 40 pixels de cena com o boneco no meio."""
    cfg = validar(cfg)
    seq = SEQUENCIAS.get(anim, SEQUENCIAS["parado"])(cfg)
    sombra = _sombra(12)
    quadros = []
    for i, (kw, dur) in enumerate(seq):
        b = boneco(cfg, **kw)
        s = _sombra(12 - min(6, kw.get("pulo", 0))) if kw.get("pulo") else sombra
        if cenario:
            fundo = _cenario(cfg["cenario"], 64, i)
            fundo.alpha_composite(s, (16, 0))
            fundo.alpha_composite(b, (16, 0))
            q = fundo
        else:
            q = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            q.alpha_composite(s)
            q.alpha_composite(b)
        quadros.append((_ampliar(q, escala), dur))
    return _webp(quadros)


def membro(cfg: dict, semente: str, escala: int = 3) -> bytes:
    """O boneco de uma pessoa na sala da turma (fundo transparente, com gesto próprio)."""
    cfg = validar(cfg)
    quadros = []
    for kw, dur in _sequencia_membro(semente):
        q = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        q.alpha_composite(_sombra(12 - min(6, kw.get("pulo", 0))))
        q.alpha_composite(boneco(cfg, **kw))
        quadros.append((_ampliar(q, escala), dur))
    return _webp(quadros)


def cenario_png(nome: str, largura: int = 64, escala: int = 3, quadros: int = 1) -> bytes:
    """O cenário sozinho (para a sala da turma). Com quadros > 1, sai animado (estrelas, tocha)."""
    nome = nome if nome in {c[0] for c in CENARIOS} else "biblioteca"
    if quadros <= 1:
        b = io.BytesIO()
        _ampliar(_cenario(nome, largura, 0), escala).save(b, "PNG")
        return b.getvalue()
    return _webp([(_ampliar(_cenario(nome, largura, i), escala), 150) for i in range(quadros)])


def rosto(cfg: dict, escala: int = 4, piscar: bool = True) -> bytes:
    """Busto do personagem (cabeça e ombros) para as listas: fundo transparente, com uma piscada de vez em quando."""
    cfg = validar(cfg)
    caixa = (6, 7, 26, 27) if cfg["acessorio"] != "chapeu" else (6, 1, 26, 21)

    def recorte(img):
        return _ampliar(img.crop(caixa), escala)

    aberto = recorte(boneco(cfg))
    if not piscar:
        b = io.BytesIO()
        aberto.save(b, "PNG")
        return b.getvalue()
    return _webp([(aberto, 3200), (recorte(boneco(cfg, piscando=True)), 130), (aberto, 2400), (recorte(boneco(cfg, piscando=True)), 120)])


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
