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
CORES_OLHOS = [("#5A3A28", "Castanhos"), ("#24232B", "Pretos"), ("#3B7AD4", "Azuis"), ("#3E9A5E", "Verdes"), ("#B37B2A", "Mel"),
               ("#8C97A8", "Cinzas"), ("#E9EEF6", "Brancos"), ("#8A5CD6", "Roxos"), ("#C8414A", "Vermelhos")]
CORES_ROUPA = [("#2340A8", "Azul Aprova"), ("#C2413A", "Vermelho"), ("#2E8B57", "Verde"), ("#E2B42F", "Amarelo"), ("#6E4BB8", "Roxo"),
               ("#E07B2C", "Laranja"), ("#D9578C", "Rosa"), ("#16928E", "Turquesa"), ("#6B7280", "Cinza"), ("#2A2D3A", "Preto"), ("#EFEFEF", "Branco")]

CORES_CALCA = [("#2F3B5C", "Jeans"), ("#2A2D3A", "Preta"), ("#6B7280", "Cinza"), ("#C9B48C", "Bege"), ("#6B4A2E", "Marrom"),
               ("#4A5D3A", "Verde-oliva"), ("#EDEDED", "Branca")]

CABELOS = [("curto", "Curto"), ("lateral", "Repartido de lado"), ("espetado", "Espetado"), ("moicano", "Moicano"), ("longo", "Longo"),
           ("franja", "Chanel"), ("coque", "Coque"), ("rabo", "Rabo de cavalo"), ("chiquinhas", "Maria-chiquinha"), ("trancas", "Tranças"),
           ("cacheado", "Cacheado"), ("afro", "Black power"), ("careca", "Careca")]
BARBAS = [("nenhuma", "Sem barba"), ("por_fazer", "Por fazer"), ("bigode", "Bigode"), ("cavanhaque", "Cavanhaque"), ("cheia", "Barba cheia")]
OLHOS = [("normal", "Normal"), ("feliz", "Feliz"), ("determinado", "Determinado"), ("sonolento", "Sonolento"), ("piscadinha", "Piscadinha")]
BOCAS = [("sorriso", "Sorriso"), ("sorrisao", "Sorrisão"), ("neutra", "Séria"), ("lingua", "Língua de fora"), ("surpresa", "Surpresa")]
MARCAS = [("nenhuma", "Nada"), ("sardas", "Sardas"), ("pinta", "Pinta"), ("corado", "Bochecha corada"), ("curativo", "Curativo")]
ROUPAS = [("moletom", "Moletom"), ("camiseta", "Camiseta"), ("regata", "Regata"), ("jaqueta", "Jaqueta"), ("vestido", "Vestido"),
          ("terno", "Terno"), ("toga", "Toga"), ("farda", "Farda"), ("jaleco", "Jaleco"), ("manto", "Manto de mago"), ("armadura", "Armadura")]
ACESSORIOS = [("nenhum", "Nenhum"), ("bone", "Boné"), ("gorro", "Gorro"), ("capelo", "Capelo de formatura"), ("coroa", "Coroa"), ("tiara", "Tiara"),
              ("chapeu", "Chapéu de mago"), ("viking", "Capacete viking"), ("fone", "Fone"), ("laco", "Laço"), ("flor", "Flor"),
              ("gato", "Orelhas de gato"), ("aureola", "Auréola"), ("faixa", "Faixa")]
OCULOS = [("nenhum", "Sem óculos"), ("redondo", "Redondo"), ("quadrado", "Quadrado"), ("meia", "Meia armação"), ("escuro", "Escuro"),
          ("coracao", "Coração"), ("monoculo", "Monóculo"), ("visor", "Visor")]
CORES_OCULOS = [("#2A2A36", "Preto"), ("#6B4A2E", "Tartaruga"), ("#D9A21C", "Dourado"), ("#B9BFC9", "Prata"), ("#C2413A", "Vermelho"),
                ("#2F6BD8", "Azul"), ("#E56FA5", "Rosa"), ("#F2F2F2", "Branco")]
EXTRAS = [("nenhum", "Nada"), ("cachecol", "Cachecol"), ("medalha", "Medalha"), ("gravata", "Gravata-borboleta"), ("colar", "Colar"),
          ("capa", "Capa de herói"), ("mochila", "Mochila")]
ITENS = [("nenhum", "Nada"), ("livro", "Livro"), ("vade", "Vade Mecum"), ("lapis", "Lápis gigante"), ("marcatexto", "Marca-texto"),
         ("cafe", "Café"), ("diploma", "Diploma"), ("trofeu", "Troféu"), ("espada", "Espada"), ("cajado", "Cajado")]
CORPOS = [("magro", "Magro"), ("medio", "Médio"), ("forte", "Forte"), ("gordinho", "Gordinho")]
CENARIOS = [("biblioteca", "Biblioteca"), ("floresta", "Floresta"), ("noite", "Noite na cidade"), ("castelo", "Castelo"), ("sala", "Sala de aula")]

CATEGORIAS = {"corpo": CORPOS, "cabelo": CABELOS, "barba": BARBAS, "olhos": OLHOS, "boca": BOCAS, "marca": MARCAS, "roupa": ROUPAS, "acessorio": ACESSORIOS, "oculos": OCULOS, "extra": EXTRAS, "item": ITENS,
              "cenario": CENARIOS}
CORES = {"pele": PELES, "cor_cabelo": CORES_CABELO, "cor_olhos": CORES_OLHOS, "cor_roupa": CORES_ROUPA, "cor_calca": CORES_CALCA,
         "cor_oculos": CORES_OCULOS}

PADRAO = {"v": 1, "corpo": "medio", "pele": 1, "cabelo": "curto", "cor_cabelo": 1, "barba": "nenhuma", "olhos": "normal", "cor_olhos": 0,
          "boca": "sorriso", "marca": "nenhuma", "roupa": "moletom", "cor_roupa": 0, "cor_calca": 0,
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
    cfg["corpo"] = rnd.choice(["magro", "medio", "medio", "medio", "forte", "gordinho"])
    if rnd.random() < 0.7:
        cfg["barba"] = "nenhuma"
    if rnd.random() < 0.6:
        cfg["boca"] = "sorriso"
    if rnd.random() < 0.7:
        cfg["marca"] = "nenhuma"
    if rnd.random() < 0.5:
        cfg["cor_calca"] = 0
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
    "regata": {
        24: ".....cSSSSc.....",
        25: ".ssccccccccccss.",
        26: ".SsccccccccccsS.",
        27: ".SsccccccccccsS.",
    },
    "jaqueta": {
        24: "....CCwwwwCC....",
        25: ".ccccCwwwwCcccc.",
        26: ".CcccCwwwwCcccC.",
        27: ".CcccCwwwwCcccC.",
        28: ".sscccwwwwcccss.",
        29: ".ssCccwwwwcccss.",
        30: "...CccwwwwccC...",
    },
    "toga": {
        24: "....cwwSSwwc....",
        25: "cccccwwwwwwccccc",
        26: "cCccccwwwwccccCc",
        27: "cCcccccwwcccccCc",
        28: ".ssccccccccccss.",
        29: ".ssCcccccccccss.",
        30: "...cccccccccc...",
        31: "...cccccccccc...",
        32: "...cccccccccc...",
        33: "..cCccccccccCc..",
        34: "..CCCCCCCCCCCC..",
    },
    "farda": {
        24: "....CcSSSScC....",
        25: ".CCccccSSccccCC.",
        26: ".CcccCCccCCcccC.",
        27: ".CcccACccCCcccC.",
        28: ".ssccccccccccss.",
        29: ".ssCcccccccccss.",
        30: "...BBBBAABBBB...",
    },
    "jaleco": {
        24: "....wwcSScww....",
        25: ".wwwwwccccwwwww.",
        26: ".wwwwwccccwwwww.",
        27: ".wwwAwccccwwwww.",
        28: ".sswwwccccwwwss.",
        29: ".sswwwccccwwwss.",
        30: "...wwwccccwww...",
        31: "...www....www...",
        32: "...www....www...",
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
    "lateral": {
        10: ".....hhhhhhh....",
        11: "...hhhhhhhhhhh..",
        12: "..hhhhLLhhhhhhh.",
        13: "..hhhhhhhhhhhhh.",
        14: "..hhhhhhhhhhhhh.",
        15: "..hH.hhhhhhhHhh.",
        16: "..h......hhhHhh.",
        17: "..h.........Hh..",
    },
    "moicano": {  # "z" = lateral raspada (pele com sombra do cabelo)
        5: "......hh........",
        6: ".....hhhh.......",
        7: "......hhhh......",
        8: ".....hhhhh......",
        9: "......hhhhh.....",
        10: ".....hhhhhh.....",
        11: "....zzhhhhzz....",
        12: "...zzzhhLhzzz...",
        13: "..zzzzzhhhzzzz..",
        14: "..zzzzzzzzzzzz..",
        15: "..z..........z..",
    },
    "chiquinhas": {
        11: "....hhhhhhhh....",
        12: "...hhLLhhhhhh...",
        13: ".dhhhhhhhhhhhhd.",
        14: ".dhhhhhhhhhhhhd.",
        15: "..hhHhhhhhhHhh..",
        16: "..hH........Hh..",
        17: "..h..........h..",
    },
    "trancas": {
        11: "....hhhhhhhh....",
        12: "...hhLLhhhhhh...",
        13: "..hhhhhhhhhhhh..",
        14: "..hhhhhhhhhhhh..",
        15: "..hhhhhHhhhhhh..",
        16: "..hh........hh..",
        17: ".hh..........hh.",
        18: ".hH..........Hh.",
        19: ".hh..........hh.",
        20: ".Hh..........hH.",
        21: ".hh..........hh.",
        22: ".hH..........Hh.",
        23: "..hh........hh..",
        24: "..Hh........hH..",
        25: "..hh........hh..",
        26: "..hH........Hh..",
        27: "..dd........dd..",
        28: "..hh........hh..",
    },
    "afro": {
        8: "....hhhhhhhh....",
        9: "..hhhhhhhhhhhh..",
        10: ".hhhhhLLhhhhhhh.",
        11: ".hhhhhhhhhhhhhh.",
        12: "hhhhhhhhhhhhhhhh",
        13: "hhhhhhhhhhhhhhhh",
        14: "hhhhhhhhhhhhhhhh",
        15: "hhHhhhHhhHhhHhhh",
        16: "hhh..........hhh",
        17: "hH............hh",
        18: "hh............Hh",
        19: ".hh..........hh.",
        20: "..h..........h..",
    },
    "careca": {},
}

CABELO_ATRAS = {
    "afro": {
        6: ".....hhhhhh.....",
        7: "...hhhhHhhhhh...",
        8: "..hhhhhhhhhHhh..",
        9: ".hhhhhhhhhhhhhh.",
        **{y: ("hhhhhhhhhhhhhhhh" if y % 3 else "Hhhhhhhhhhhhhhhh" if y % 2 else "hhhhhhhhhhhhhhhH") for y in range(10, 20)},
        20: ".hhhhhhhhhhhhhh.",
        21: "..hhhhhhhhhhhh..",
        22: "....hhhhhhhh....",
    },
    "chiquinhas": ({  # 20 colunas (a partir de x = 6): os rabinhos saem dos lados da cabeça
        12: "..hh............hh..",
        13: ".hhhh..........hhhh.",
        14: ".hHhh..........hhHh.",
        15: "hhhh............hhhh",
        16: "hHh..............hHh",
        17: "hhh..............hhh",
        18: "hh................hh",
        19: "hH................Hh",
        20: ".h................h.",
    }, 6),
    "lateral": {13: "..............h.", 14: "..............h."},
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
    "redondo": {"lente": [(x, y, "a") for x, y in _retangulo(23, 33, 29, 40, cantos=False)],
                "extras": [(30, 35, "a"), (31, 34, "a"), (32, 34, "a"), (33, 35, "a"), (21, 35, "a"), (22, 35, "a"), (41, 35, "a"), (42, 35, "a")]},
    "quadrado": {"lente": [(x, y, "a") for x, y in _retangulo(23, 33, 29, 40)],
                 "extras": [(30, 35, "a"), (31, 35, "a"), (32, 35, "a"), (33, 35, "a"), (21, 35, "a"), (22, 35, "a"), (41, 35, "a"), (42, 35, "a")]},
    "meia": {"lente": [(x, 33, "a") for x in range(23, 30)] + [(23, 34, "a"), (29, 34, "a"), (23, 35, "a"), (29, 35, "a")],
             "extras": [(30, 34, "a"), (31, 34, "a"), (32, 34, "a"), (33, 34, "a"), (21, 34, "a"), (22, 34, "a"), (41, 34, "a"), (42, 34, "a")]},
    "escuro": {"lente": [(x, y, "A") for x, y in _cheio(23, 34, 29, 39)] + [(x, 33, "a") for x in range(23, 30)] + [(24, 36, "g"), (25, 35, "g")],
               "extras": [(30, 34, "a"), (31, 34, "a"), (32, 34, "a"), (33, 34, "a"), (21, 34, "a"), (22, 34, "a"), (41, 34, "a"), (42, 34, "a")]},
    "coracao": {"lente": [(22 + i, 34 + j, ch) for j, linha in enumerate(_CORACAO) for i, ch in enumerate(linha) if ch != "."] + [(24, 35, "g")],
                "extras": []},
    "monoculo": {"so_direita": True, "lente": [(x, y, "a") for x, y in _retangulo(23, 33, 29, 40, cantos=False)],
                 "extras": [(40, 41, "c"), (41, 43, "c"), (41, 45, "c"), (42, 47, "c"), (41, 49, "c")]},
    "visor": {"lente": [], "extras": [(x, y, "A") for x, y in _cheio(21, 34, 42, 39)] + [(x, 33, "a") for x in range(20, 44)]
              + [(x, 40, "a") for x in range(20, 44)] + [(20, y, "a") for y in range(34, 40)] + [(43, y, "a") for y in range(34, 40)]
              + [(x, 36, "g") for x in range(23, 29)]},
}
LENTES = {"escuro": "#1C2030", "coracao": "#F06A9E", "visor": "#3FD0E6"}
OLHO_X, OLHO_Y, BOCA_Y = (24, 35), 34, 41  # na grade final: olhos de 5 x 6 e a boca
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
    "vade": ({24: "iiiiij", 25: "iIIIij", 26: "iiiiij", 27: "iKKKij", 28: "iiiiij", 29: "iiiiij", 30: "iIIIij", 31: "iiiiij"}, 21),
    "marcatexto": ({20: "k.", 21: "kk", 22: "jj", **{y: "iI" for y in range(23, 29)}, 29: "jj"}, 21),
    "diploma": ({**{y: "jJ" for y in range(21, 31)}, 25: "rr", 26: "rR", 31: ".r"}, 21),
    "trofeu": ({21: "iiiii", 22: "iJiii", 23: "iiiii", 24: ".iii.", 25: "..i..", 26: "..i..", 27: ".III.", 28: ".jjj."}, 20),
}
CORES_ITEM = {
    "livro": {"i": "#B83A3A", "I": "#E8C15A", "j": "#F4EAD2"},
    "lapis": {"k": "#3B3B44", "j": "#E9C796", "i": "#F2C230", "I": "#D9A21C", "g": "#B9BFC9", "r": "#E7849A"},
    "cafe": {"i": "#F4F1EA", "j": "#6B3E26"},
    "espada": {"j": "#C9D1DC", "J": "#F4F7FB", "i": "#D9A21C", "I": "#7A4E2D"},
    "cajado": {"j": "#5CC8E8", "J": "#E6FBFF", "i": "#8A5A34"},
    "vade": {"i": "#1E4E8C", "I": "#E8C15A", "K": "#F4EAD2", "j": "#F4EAD2"},
    "marcatexto": {"k": "#C6F03A", "j": "#2A2D3A", "i": "#E6F542", "I": "#C9D62E"},
    "diploma": {"j": "#F6EFDD", "J": "#E2D6B8", "r": "#C2413A", "R": "#8A2A2A"},
    "trofeu": {"i": "#F2C230", "J": "#FFF0A8", "I": "#C9962A", "j": "#5A3E2B"},
}

# ---------------------------------------------------------------- tipo de corpo
# Os moldes do tronco e das pernas foram desenhados no corpo largo ("gordinho"). Os outros corpos tiram
# colunas do meio do tronco e das pernas (na linha de 16 colunas) e centralizam de novo, então toda roupa,
# capa e mochila serve em qualquer corpo. As colunas 1-2 e 13-14 são os braços: eles chegam para dentro.
# Cada corpo: (primeira linha, última linha, "tira" ou "dobra", colunas). "dobra" repete as colunas (fica mais largo).
OPERACOES_CORPO = {
    "magro": [(23, 30, "tira", {3, 4, 11, 12}), (31, 39, "tira", {4, 11})],
    "medio": [(23, 30, "tira", {4, 11}), (31, 39, "tira", {4, 11})],
    "forte": [(24, 24, "dobra", {4, 11}), (28, 30, "tira", {4, 11}), (31, 39, "tira", {4, 11})],  # ombro largo, cintura fina
    "gordinho": [(30, 39, "dobra", {4, 11})],  # barriga e pernas mais cheias
}
SOMBRA_CORPO = {"magro": 19, "medio": 21, "forte": 23, "gordinho": 26}


def _operacao(y: int, corpo: str) -> tuple[str, set]:
    for de, ate, tipo, cols in OPERACOES_CORPO.get(corpo, []):
        if de <= y <= ate:
            return tipo, cols
    return "", set()


def _tira(y: int, corpo: str) -> set:
    tipo, cols = _operacao(y, corpo)
    return cols if tipo == "tira" else set()


def recuo(y: int, corpo: str) -> int:
    """Quanto o braço (ou a mão, ou o que ela segura) chega para dentro nesta linha (negativo: para fora)."""
    tipo, cols = _operacao(y, corpo)
    n = sum(1 for c in cols if c < 8)
    return n if tipo == "tira" else -n if tipo == "dobra" else 0


def _alargar(linha: str, dobra: set) -> str:
    """Repete as colunas e corta as pontas vazias (se a linha já vai até a borda, fica como está)."""
    if len(linha) != 16:
        return linha
    esq = sum(1 for c in dobra if c < 8)
    dir_ = len(dobra) - esq
    if linha[:esq].strip(". ") or linha[16 - dir_:].strip(". "):
        return linha
    novo = "".join(ch * (2 if i in dobra else 1) for i, ch in enumerate(linha))
    return novo[esq: len(novo) - dir_]


def _estreitar(linha: str, tira: set, juntar: bool = False) -> str:
    """Tira as colunas e centraliza de novo. juntar: o que estava numa coluna tirada (alça, borda) passa para a vizinha."""
    if not tira or len(linha) != 16:
        return linha
    ch = list(linha)
    if juntar:
        for c in sorted(tira, key=lambda c: abs(c - 7.5)):
            if ch[c] in ". ":
                continue
            passo = 1 if c < 8 else -1
            viz = c + passo
            while viz in tira:
                viz += passo
            if 0 <= viz < 16 and ch[viz] in ". ":
                ch[viz] = ch[c]
    resto = "".join(x for i, x in enumerate(ch) if i not in tira)
    esq = sum(1 for c in tira if c < 8)
    return "." * esq + resto + "." * (len(tira) - esq)


def _moldar(molde: dict, corpo: str, juntar: bool = False) -> dict:
    """O molde (linhas de 16 colunas) no tipo de corpo escolhido."""
    saida = {}
    for y, l in molde.items():
        tipo, cols = _operacao(y, corpo)
        saida[y] = _estreitar(l, cols, juntar) if tipo == "tira" else _alargar(l, cols) if tipo == "dobra" else l
    return saida


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
    calca = _rgb(CORES_CALCA[cfg.get("cor_calca", 0)][0])
    claro = _luz(calca) > 0.7
    return {
        "s": pele, "S": _escura(pele, 0.16), "r": _mistura(pele, (255, 110, 130), 0.42),
        "h": cab, "H": _escura(cab, 0.28), "L": cab,  # o brilho do cabelo é feito na grade final
        "e": _rgb(CORES_OLHOS[cfg["cor_olhos"]][0]), "w": (255, 255, 255, 255), "m": (128, 52, 58, 255),
        "c": roupa, "C": _escura(roupa, 0.22) if _luz(roupa) > 0.2 else _clara(roupa, 0.12), "d": _rgb(detalhe),
        "A": _rgb("#C9D1DC"), "p": calca, "P": _escura(calca, 0.12 if claro else 0.25), "b": _rgb("#5A3E2B"), "B": _rgb("#3F2A1D"),
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

    corpo = cfg.get("corpo", "medio")

    # costas: capa e mochila; cabelo de trás
    if extra in EXTRA_MOLDES and EXTRA_MOLDES[extra][1]:
        _pintar(img, mat, _moldar(EXTRA_MOLDES[extra][1], corpo, juntar=True), _cores_extra(cfg, pal), M_EXTRA, dy=d)
    pal_cabelo = {**pal, "d": _rgb("#E0507E"), "z": _mistura(pal["s"], pal["h"], 0.32)}  # "d" = elástico, "z" = raspado
    if cfg["cabelo"] in CABELO_ATRAS:
        atras = CABELO_ATRAS[cfg["cabelo"]]
        molde_atras, x_atras = atras if isinstance(atras, tuple) else (atras, 8)
        _pintar(img, mat, _moldar(molde_atras, corpo, juntar=True), pal_cabelo, M_CABELO, x0=x_atras, dy=d, desde_y=corta)

    # corpo: pernas fixas, tronco acompanha a respiração
    pernas = _moldar({y: l for y, l in CORPO.items() if y >= 31}, corpo)
    tronco = _moldar({y: l for y, l in CORPO.items() if y < 31}, corpo)
    roupa = _moldar(ROUPA_MOLDES.get(cfg["roupa"], {}), corpo)
    _pintar(img, mat, pernas, pal, MAT_CORPO)
    _pintar(img, mat, {y: l for y, l in roupa.items() if y >= 31}, pal, MAT_CORPO)
    roupa_cima = {y: l for y, l in roupa.items() if y < 31}
    if braco:
        # some com o braço de baixo do lado que levanta
        def sem_esq(y, l):
            n = 2 + recuo(y, corpo)
            return "." * n + l[n:] if y >= 25 else l

        def sem_dir(y, l):
            n = 14 - recuo(y, corpo)
            return l[:n] + "." * (16 - n) if y >= 25 else l

        tronco = {y: sem_esq(y, l) for y, l in tronco.items()}
        roupa_cima = {y: sem_esq(y, l) for y, l in roupa_cima.items()}
        if braco == "dois":
            tronco = {y: sem_dir(y, l) for y, l in tronco.items()}
            roupa_cima = {y: sem_dir(y, l) for y, l in roupa_cima.items()}
    _pintar(img, mat, tronco, pal, MAT_CORPO, dy=d)
    _pintar(img, mat, roupa_cima, pal, MAT_CORPO, dy=d)

    px, pm = img.load(), mat.load()
    if braco:
        manga = "s" if cfg["roupa"] == "vestido" else "c"
        lados = [BRACO_ACIMA_ESQ] + ([BRACO_ACIMA_DIR] if braco == "dois" else [])
        # corpo mais estreito: o ombro chega para dentro e o braço sobe em diagonal; a mão fica do lado da cabeça
        k = recuo(25, corpo)
        for lado in lados:
            sinal = 1 if lado is BRACO_ACIMA_ESQ else -1
            pontos = []
            for (x, y), ch in lado:
                x -= 1 if aceno and lado is BRACO_ACIMA_ESQ and y <= 20 else 0
                if y >= 23:  # ombro: estica da posição antiga até o ombro novo
                    pontos += [(x + sinal * j, y, ch) for j in range(k + 1)]
                else:
                    pontos.append((x, y, ch))
            for xx, y, ch in pontos:
                if cfg["roupa"] == "armadura" and ch == "s":
                    px[xx, y + d], pm[xx, y + d] = pal["A"], M_METAL
                else:
                    letra = manga if ch == "c" else "s"
                    px[xx, y + d], pm[xx, y + d] = pal[letra], MAT_CORPO[letra]
    k_mao = recuo(28, corpo)
    if cfg["roupa"] == "armadura" and not braco:
        for x in (9 + k_mao, 10 + k_mao, 21 - k_mao, 22 - k_mao):
            for y in (28, 29):
                px[x, y + d], pm[x, y + d] = pal["A"], M_METAL

    # pescoço (cachecol, medalha...), cabeça, cabelo, acessório, óculos
    if extra in EXTRA_MOLDES and EXTRA_MOLDES[extra][0]:
        _pintar(img, mat, _moldar(EXTRA_MOLDES[extra][0], corpo, juntar=True), _cores_extra(cfg, pal), M_EXTRA, dy=d)
    _pintar(img, mat, CABECA, pal, MAT_CORPO, dy=d)
    _pintar(img, mat, _moldar(CABELO_FRENTE.get(cfg["cabelo"], {}), corpo, juntar=True), pal_cabelo, M_CABELO, dy=d, desde_y=corta)
    if acess in ACESSORIO_MOLDES:
        _pintar(img, mat, ACESSORIO_MOLDES[acess][0], _cores_camada(CORES_ACESSORIO[acess], pal), M_ACESS, dy=d)

    # item na mão (some quando os dois braços estão para cima)
    item = cfg["item"]
    if item in ITEM_MOLDES and braco != "dois":
        molde, x0 = ITEM_MOLDES[item]
        _pintar(img, mat, molde, {k: _rgb(v) for k, v in CORES_ITEM[item].items()}, M_ITEM, x0=x0 - k_mao, dy=d)
        if item == "cafe" and vapor:
            for i, (x, y) in enumerate(((23, 24), (24, 23), (23, 22))):
                if (vapor + i) % 3:
                    xx = x + (vapor % 2) - k_mao
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
LUZ_DO_LADO = {M_ROUPA, M_CALCA, M_BOTA, M_CABELO, M_EXTRA}


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
            if novo == c and m in LUZ_DO_LADO and me != m and x and orig[i - 1][3] == 0:
                novo = _clara(c, 0.12)  # luz vinda da esquerda: dá volume
            if m == M_ROUPA and mb == M_PELE and y > 50 + d2:
                novo = _escura(c, 0.2)  # punho da manga e barra da roupa
            if m == M_BOTA and mc != M_BOTA and me != M_BOTA:
                novo = _clara(c, 0.3)  # brilho na ponta do sapato
            if m in (M_ROUPA, M_EXTRA) and 48 + d2 <= y <= 49 + d2 and 24 <= x <= 39:
                novo = _escura(novo, 0.1)  # sombra que a cabeça faz nos ombros
            if m == M_PELE and y == 46 + d2 and 26 <= x <= 37:
                novo = _escura(c, 0.12)  # sombra embaixo do queixo
            if novo != c:
                out[i] = novo[:4] + (m,)

    # brilho do cabelo: uma faixa clara que acompanha o topo da cabeça, do lado da luz
    for x in range(20, 37):
        if (x - 20) % 6 == 5:
            continue  # o brilho vem em mechas, com um vão entre elas
        topo = next((y for y in range(0, 44) if orig[y * L + x][4] == M_CABELO), None)
        if topo is None:
            continue
        for yy, t in ((topo + 2, 0.3), (topo + 3, 0.18)):
            i = yy * L + x
            if orig[i][4] == M_CABELO and orig[i + L][4] == M_CABELO:
                out[i] = _clara(orig[i], t + (0.14 if (x - 20) % 6 == 1 and yy == topo + 2 else 0))[:4] + (M_CABELO,)
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

    branco_olho = _luz(e) > 0.8  # olhos brancos: a pupila vira um cinza e o brilho fica azulado
    iris_alto = _escura(e, 0.35)
    pupila = _escura(e, 0.45 if branco_olho else 0.72)
    iris_baixo = _clara(e, 0.42) if not branco_olho else _mistura(e, (170, 190, 220, 255), 0.35)
    brilho = (255, 255, 255, 255) if not branco_olho else (150, 200, 255, 255)
    faisca = _clara(e, 0.8) if not branco_olho else (255, 255, 255, 255)
    # olho de 5 x 6 (estilo chibi): cílio grosso, íris com sombra em cima, pupila, brilho grande e faísca
    # "." = deixa a pele; o lado de fora de cada olho ganha a pontinha do cílio
    OLHO = ["KKKKK", "WWAAA", "WAPPA", "ePPPe", "ePPFe", ".LLL."]
    cores_olho = {"K": cilio, "W": brilho, "A": iris_alto, "P": pupila, "e": e, "F": faisca, "L": iris_baixo}

    def olho_aberto(x0, y0, fora, desde=0):
        for dy, linha in enumerate(OLHO):
            if dy < desde:
                continue
            for k, ch in enumerate(linha):
                if ch != ".":
                    pinta(x0 + k, y0 + dy, cores_olho[ch])
        pinta(fora, y0 - 1 + desde, cilio)
        pinta(fora, y0 + desde, cilio)

    def fechado(x0, y0, fora, feliz):
        if feliz:  # ^ ^
            for dx, dy in ((0, 4), (1, 3), (2, 2), (3, 3), (4, 4), (-1, 5) if fora < x0 else (5, 5)):
                pinta(x0 + dx, y0 + dy, cilio)
        else:  # piscando: uma linha com a pontinha do cílio
            for k in range(5):
                pinta(x0 + k, y0 + 4, cilio)
            pinta(fora, y0 + 3, cilio)

    if not cfg["oculos"] in OCULOS_COBREM_OLHOS:
        for x0, lado in ((OLHO_X[0], -1), (OLHO_X[1], 1)):
            y0 = OLHO_Y + d2
            fora = x0 - 1 if lado < 0 else x0 + 5
            if piscando:
                fechado(x0, y0, fora, False)
                continue
            if estilo == "feliz" or (estilo == "piscadinha" and lado > 0):
                fechado(x0, y0, fora, True)
                if estilo == "piscadinha":
                    for dx in (1, 2, 3):
                        pinta(x0 + dx, y0 - 2, _mistura(sobrancelha, pele, 0.3))
                continue
            if estilo == "sonolento":  # pálpebra pesada: só a metade de baixo do olho aparece
                for k in range(5):
                    pinta(x0 + k, y0, _escura(pele, 0.08))
                    pinta(x0 + k, y0 + 1, _escura(pele, 0.14))
                    pinta(x0 + k, y0 + 2, cilio)
                olho_aberto(x0, y0, fora, desde=3)
                pinta(fora, y0 + 3, pele)
                pinta(fora, y0 + 2, cilio)
                for dx in range(5):
                    pinta(x0 + dx, y0 - 2, _mistura(sobrancelha, pele, 0.5))
                continue
            olho_aberto(x0, y0, fora)
            if estilo == "determinado":
                pts = ((-1, -3), (0, -3), (1, -3), (2, -2), (3, -2), (4, -1)) if lado < 0 else ((0, -1), (1, -2), (2, -2), (3, -3), (4, -3), (5, -3))
                for dx, dy in pts:
                    pinta(x0 + dx, y0 + dy, sobrancelha)
            else:  # sobrancelha em arco, suave
                arco = ((-1, -2), (0, -3), (1, -3), (2, -3), (3, -3)) if lado < 0 else ((1, -3), (2, -3), (3, -3), (4, -3), (5, -2))
                for dx, dy in arco:
                    pinta(x0 + dx, y0 + dy, _mistura(sobrancelha, pele, 0.35))

    # barba e bigode (antes das bochechas e da boca, que ficam por cima)
    barba = cfg.get("barba", "nenhuma")
    pelo = pal["h"] if cfg["cabelo"] != "careca" else _rgb("#3B2A20")
    pelo_escuro = _escura(pelo, 0.25)
    com_barba: set = set()
    yb = BOCA_Y  # linha da boca

    def na_barba(x, y):
        yy = y - d2
        return ((yy >= yb - 4 and (x <= 22 or x >= 41)) or (yy >= yb - 1 and (x <= 25 or x >= 38))
                or (yy == yb + 1 and (x <= 28 or x >= 35)) or yy >= yb + 2)

    def bigode(cor):
        for x in range(28, 36):
            pinta(x, yb - 1 + d2, cor)
            com_barba.add((x, yb - 1 + d2))
        for x in (28, 29, 34, 35):
            pinta(x, yb + d2, cor)
            com_barba.add((x, yb + d2))

    if barba in ("cheia", "por_fazer"):
        for y in range(34 + d2, 49 + d2):
            for x in range(18, 46):
                if orig[y * L + x][4] != M_PELE or not na_barba(x, y):
                    continue
                if barba == "cheia":
                    baixo = orig[(y + 1) * L + x][4] != M_PELE
                    pinta(x, y, pelo_escuro if baixo else pelo)
                    com_barba.add((x, y))
                else:  # por fazer: sombra leve com pontinhos espalhados
                    pinta(x, y, _mistura(pele, pelo, 0.36 if (3 * x + 5 * y) % 7 == 0 else 0.14))
        if barba == "cheia":
            bigode(pelo)
    elif barba in ("bigode", "cavanhaque"):
        bigode(pelo)
        if barba == "cavanhaque":
            for y, xs in ((yb + 3, range(30, 34)), (yb + 4, range(30, 34)), (yb + 5, range(31, 33))):
                for x in xs:
                    pinta(x, y + d2, pelo if y < yb + 5 else pelo_escuro)
                    com_barba.add((x, y + d2))

    # bochechas (embaixo e por fora dos olhos), detalhes do rosto e nariz
    marca = cfg.get("marca", "nenhuma")
    rosado = pal["r"]
    bochechas = [(21, 40), (23, 40), (22, 41), (40, 40), (42, 40), (41, 41)]
    if marca == "corado":
        bochechas += [(20, 41), (24, 41), (21, 42), (23, 42), (22, 40), (39, 41), (43, 41), (40, 42), (42, 42), (41, 40)]
        rosado = _mistura(pal["r"], (232, 90, 110, 255), 0.35)
    for x, y in bochechas:
        if (x, y + d2) not in com_barba:
            pinta(x, y + d2, rosado)
    if marca == "sardas":
        for x, y in ((21, 41), (23, 42), (25, 41), (22, 43), (38, 41), (40, 42), (42, 41), (41, 43)):
            if (x, y + d2) not in com_barba:
                pinta(x, y + d2, _escura(pele, 0.24))
    elif marca == "pinta":
        pinta(38, 43 + d2, _escura(pele, 0.55))
    elif marca == "curativo":
        fita, borda, gaze = _rgb("#F2CF96"), _rgb("#C9965A"), _rgb("#FFF4DE")
        for x, y, cor in ((20, 40, borda), (21, 40, fita), (22, 40, fita), (23, 40, borda),
                          (19, 41, borda), (20, 41, fita), (21, 41, gaze), (22, 41, gaze), (23, 41, fita), (24, 41, borda),
                          (20, 42, borda), (21, 42, fita), (22, 42, fita), (23, 42, borda)):
            pinta(x, y + d2, cor)
    if (31, yb - 1 + d2) not in com_barba:
        pinta(31, yb - 1 + d2, _escura(pele, 0.12))
        pinta(32, yb - 1 + d2, _escura(pele, 0.06))

    # boca
    boca, lingua = pal["m"], (232, 112, 122, 255)
    y0 = yb + d2
    tipo_boca = "sorrisao" if alegre else cfg.get("boca", "sorriso")
    if tipo_boca == "sorrisao":
        for k in range(4):
            pinta(30 + k, y0, boca)
        for k, cor in enumerate((boca, lingua, lingua, boca)):
            pinta(30 + k, y0 + 1, cor)
        pinta(31, y0 + 2, boca)
        pinta(32, y0 + 2, boca)
    elif tipo_boca == "neutra":
        for k in range(4):
            pinta(30 + k, y0 + 1, boca)
    elif tipo_boca == "surpresa":
        for x, y in ((31, y0), (32, y0), (30, y0 + 1), (33, y0 + 1), (31, y0 + 2), (32, y0 + 2)):
            pinta(x, y, boca)
        pinta(31, y0 + 1, _escura(boca, 0.45))
        pinta(32, y0 + 1, _escura(boca, 0.45))
    else:
        for x, y in ((30, y0), (31, y0 + 1), (32, y0 + 1), (33, y0)):
            pinta(x, y, boca)
        if tipo_boca == "lingua":
            pinta(32, y0 + 2, lingua)
            pinta(33, y0 + 2, _escura(lingua, 0.15))
            pinta(32, y0 + 3, _escura(lingua, 0.1))

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
        deslocamentos = (11,) if dados.get("so_direita") else (0, 11)
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


def _sombra_pulo(kw: dict, corpo: str = "medio") -> Image.Image:
    return _sombra(SOMBRA_CORPO.get(corpo, 22) - min(12, 2 * kw.get("pulo", 0)))


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
            q.alpha_composite(_sombra_pulo(kw, cfg["corpo"]), (x, 0))
            q.alpha_composite(b, (x, 0))
        else:
            q = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
            q.alpha_composite(_sombra_pulo(kw, cfg["corpo"]))
            q.alpha_composite(b)
        quadros.append((_ampliar(q, escala), dur))
    return _webp(quadros)


def membro(cfg: dict, semente: str, escala: int = 1) -> bytes:
    """O boneco de uma pessoa na sala da turma (64 x 80 por escala, fundo transparente, com gesto próprio)."""
    cfg = validar(cfg)
    quadros = []
    for kw, dur in _sequencia_membro(semente):
        q = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        q.alpha_composite(_sombra_pulo(kw, cfg["corpo"]))
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
    caixa = (12, 14, 52, 54)
    topo = boneco(cfg).getbbox()  # cabelo alto (black power, moicano) ou chapéu: o recorte sobe para caber
    if topo and topo[1] < 15:
        y0 = max(4, topo[1] - 1)
        caixa = (12, y0, 52, y0 + 40)

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
