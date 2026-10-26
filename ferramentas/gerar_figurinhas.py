"""Desenha as figurinhas do Aprova (PNG com fundo transparente, contorno branco de adesivo).

Uso: python ferramentas/gerar_figurinhas.py   → assets/figurinhas/<id>.png
As figurinhas são desenhos próprios do Aprova (sem imagens de terceiros).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from aprova.figurinhas import FIGURINHAS  # noqa: E402

FONTES = RAIZ / "assets" / "fonts"
DESTINO = RAIZ / "assets" / "figurinhas"
G = 1024  # desenha grande e reduz (bordas lisas)
FINAL = 320

TINTA = (35, 64, 168)
TINTA_FUNDA = (20, 33, 61)
AMARELO = (255, 225, 106)
VERDE = (29, 127, 83)
VERDE_CLARO = (126, 214, 160)
CORAL = (232, 96, 76)
VERMELHO = (184, 58, 51)
PAPEL = (250, 248, 242)
GRAFITE = (20, 28, 51)
CAFE = (122, 79, 48)
BRANCO = (255, 255, 255)


def fraunces(tam: int, peso: int = 900, suave: int = 100) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTES / "Fraunces.ttf"), tam)
    try:
        f.set_variation_by_axes([min(144, tam // 4), peso, suave, 0])
    except Exception:  # noqa: BLE001
        pass
    return f


def atkinson(tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTES / "AtkinsonHyperlegible-Bold.ttf"), tam)


def texto_centro(d: ImageDraw.ImageDraw, xy, txt: str, fonte, cor, contorno=0, cor_contorno=BRANCO, espaco=0.0):
    linhas = txt.split("\n")
    alturas = [d.textbbox((0, 0), l, font=fonte)[3] - d.textbbox((0, 0), l, font=fonte)[1] for l in linhas]
    total = sum(alturas) + int(espaco * (len(linhas) - 1))
    y = xy[1] - total / 2
    for l, h in zip(linhas, alturas):
        caixa = d.textbbox((0, 0), l, font=fonte)
        w = caixa[2] - caixa[0]
        d.text((xy[0] - w / 2 - caixa[0], y - caixa[1]), l, font=fonte, fill=cor, stroke_width=contorno, stroke_fill=cor_contorno)
        y += h + espaco


def caber(d: ImageDraw.ImageDraw, txt: str, fabrica, largura: int, tam: int) -> ImageFont.FreeTypeFont:
    while tam > 20:
        f = fabrica(tam)
        maior = max(d.textbbox((0, 0), l, font=f)[2] - d.textbbox((0, 0), l, font=f)[0] for l in txt.split("\n"))
        if maior <= largura:
            return f
        tam -= 6
    return fabrica(tam)


def adesivo(desenho: Image.Image) -> Image.Image:
    """Contorno branco grosso (recorte de adesivo) e sombra suave."""
    alfa = desenho.split()[3]
    borda = alfa.filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.GaussianBlur(2))
    borda = borda.point(lambda v: 255 if v > 90 else 0)
    sombra = borda.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.32))
    base = Image.new("RGBA", desenho.size, (0, 0, 0, 0))
    base.paste(Image.new("RGBA", desenho.size, (20, 28, 51, 255)), (0, 14), sombra)
    base.paste(Image.new("RGBA", desenho.size, BRANCO + (255,)), (0, 0), borda)
    base.alpha_composite(desenho)
    return base


def novo():
    im = Image.new("RGBA", (G, G), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def balao(d, caixa, cor, ponta="esquerda"):
    x0, y0, x1, y1 = caixa
    d.rounded_rectangle(caixa, radius=120, fill=cor)
    if ponta == "esquerda":
        d.polygon([(x0 + 140, y1 - 40), (x0 + 90, y1 + 120), (x0 + 300, y1 - 30)], fill=cor)
    else:
        d.polygon([(x1 - 140, y1 - 40), (x1 - 90, y1 + 120), (x1 - 300, y1 - 30)], fill=cor)


def lapis(d, cx, cy, ang=-35, tam=300):
    """Lápis simples (corpo amarelo, ponta de grafite)."""
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    px, py = -uy, ux
    l, w = tam, tam * 0.16

    def p(t, s):
        return (cx + ux * t + px * s, cy + uy * t + py * s)

    d.polygon([p(-l / 2, -w), p(l / 2 - 60, -w), p(l / 2 - 60, w), p(-l / 2, w)], fill=AMARELO)
    d.polygon([p(l / 2 - 60, -w), p(l / 2 + 40, 0), p(l / 2 - 60, w)], fill=(236, 200, 160))
    d.polygon([p(l / 2 + 10, -w * 0.3), p(l / 2 + 40, 0), p(l / 2 + 10, w * 0.3)], fill=GRAFITE)
    d.polygon([p(-l / 2 - 40, -w), p(-l / 2, -w), p(-l / 2, w), p(-l / 2 - 40, w)], fill=CORAL)


def bolinhas(d, x, y, marcada: int, raio=34, passo=96, n=5, cor=TINTA):
    for i in range(n):
        cx = x + i * passo
        if i == marcada:
            d.ellipse((cx - raio, y - raio, cx + raio, y + raio), fill=cor)
        else:
            d.ellipse((cx - raio, y - raio, cx + raio, y + raio), outline=cor, width=10)


# ---------------------------------------------------------------- cada figurinha

def bora_estudar():
    im, d = novo()
    balao(d, (90, 170, 934, 700), TINTA)
    f = caber(d, "Bora\nestudar!", lambda t: fraunces(t), 700, 230)
    texto_centro(d, (512, 430), "Bora\nestudar!", f, BRANCO, espaco=10)
    lapis(d, 760, 820, ang=-30, tam=360)
    return im


def passei():
    im, d = novo()
    pontos = []
    for i in range(32):
        r = 430 if i % 2 == 0 else 330
        a = math.pi * 2 * i / 32 - math.pi / 2
        pontos.append((512 + r * math.cos(a), 512 + r * math.sin(a)))
    d.polygon(pontos, fill=VERDE)
    for cx, cy, cor in ((180, 170, AMARELO), (860, 210, CORAL), (840, 830, AMARELO), (170, 820, TINTA), (900, 520, TINTA)):
        d.ellipse((cx - 34, cy - 34, cx + 34, cy + 34), fill=cor)
    f = caber(d, "PASSEI!", lambda t: fraunces(t), 600, 220)
    texto_centro(d, (512, 512), "PASSEI!", f, BRANCO)
    return im


def gabaritei():
    im, d = novo()
    d.rounded_rectangle((170, 90, 854, 760), radius=46, fill=PAPEL)
    for linha in range(5):
        y = 190 + linha * 118
        d.text((215, y - 40), str(linha + 1), font=atkinson(70), fill=(150, 156, 170))
        bolinhas(d, 330, y, marcada=(linha * 2 + 1) % 5)
    d.rounded_rectangle((110, 740, 914, 940), radius=40, fill=AMARELO)
    f = caber(d, "Gabaritei", lambda t: fraunces(t), 740, 170)
    texto_centro(d, (512, 838), "Gabaritei", f, GRAFITE)
    return im


def foco_total():
    im, d = novo()
    for i, cor in enumerate((CORAL, BRANCO, CORAL, BRANCO, CORAL)):
        r = 400 - i * 78
        d.ellipse((512 - r, 470 - r, 512 + r, 470 + r), fill=cor)
    d.line((300, 250, 512, 470), fill=TINTA_FUNDA, width=28)
    d.polygon([(512, 470), (455, 440), (480, 410)], fill=TINTA_FUNDA)
    d.rounded_rectangle((120, 760, 904, 950), radius=40, fill=TINTA)
    f = caber(d, "Foco total", lambda t: fraunces(t), 720, 160)
    texto_centro(d, (512, 852), "Foco total", f, BRANCO)
    return im


def cafe_lei_seca():
    im, d = novo()
    # caneca
    d.rounded_rectangle((250, 300, 680, 760), radius=60, fill=CAFE)
    d.ellipse((620, 400, 860, 640), outline=CAFE, width=60)
    d.rounded_rectangle((280, 330, 650, 400), radius=30, fill=(80, 50, 30))
    for x in (360, 460, 560):
        d.arc((x - 40, 120, x + 40, 280), start=90, end=270, fill=(150, 156, 170), width=22)
        d.arc((x - 40, 40, x + 40, 200), start=270, end=90, fill=(150, 156, 170), width=22)
    d.rounded_rectangle((110, 700, 914, 970), radius=40, fill=AMARELO)
    f = caber(d, "Café +\nlei seca", lambda t: fraunces(t), 680, 100)
    texto_centro(d, (512, 836), "Café +\nlei seca", f, GRAFITE, espaco=14)
    return im


def revisao_em_dia():
    im, d = novo()
    d.ellipse((192, 90, 832, 730), fill=VERDE)
    d.line([(350, 420), (470, 545), (690, 290)], fill=BRANCO, width=80, joint="curve")
    d.rounded_rectangle((100, 700, 924, 970), radius=40, fill=TINTA)
    f = caber(d, "Revisão\nem dia", lambda t: fraunces(t), 700, 100)
    texto_centro(d, (512, 836), "Revisão\nem dia", f, BRANCO, espaco=14)
    return im


def simulado_hoje():
    im, d = novo()
    d.ellipse((222, 150, 802, 730), fill=PAPEL)
    d.ellipse((222, 150, 802, 730), outline=TINTA, width=46)
    d.rounded_rectangle((452, 70, 572, 150), radius=18, fill=TINTA)
    for i in range(12):
        a = math.pi * 2 * i / 12
        d.line((512 + 230 * math.cos(a), 440 + 230 * math.sin(a), 512 + 265 * math.cos(a), 440 + 265 * math.sin(a)), fill=TINTA_FUNDA, width=16)
    d.line((512, 440, 512, 270), fill=CORAL, width=30)
    d.line((512, 440, 640, 500), fill=TINTA_FUNDA, width=30)
    d.ellipse((490, 418, 534, 462), fill=TINTA_FUNDA)
    d.rounded_rectangle((100, 740, 924, 950), radius=40, fill=CORAL)
    f = caber(d, "Simulado hoje?", lambda t: fraunces(t), 760, 130)
    texto_centro(d, (512, 845), "Simulado hoje?", f, BRANCO)
    return im


def valeu():
    im, d = novo()
    # coração com duas curvas
    d.ellipse((150, 160, 530, 540), fill=CORAL)
    d.ellipse((494, 160, 874, 540), fill=CORAL)
    d.polygon([(170, 420), (854, 420), (512, 860)], fill=CORAL)
    d.rounded_rectangle((210, 290, 814, 510), radius=50, fill=CORAL)
    f = caber(d, "Valeu!", lambda t: fraunces(t), 520, 210)
    texto_centro(d, (512, 470), "Valeu!", f, BRANCO)
    return im


def kkkk():
    im, d = novo()
    balao(d, (80, 220, 944, 720), AMARELO, ponta="direita")
    f = caber(d, "kkkkk", lambda t: fraunces(t, 900, 100), 760, 260)
    texto_centro(d, (512, 460), "kkkkk", f, GRAFITE)
    return im


def socorro_rlm():
    im, d = novo()
    balao(d, (90, 170, 934, 720), TINTA_FUNDA)
    f = caber(d, "Socorro,\nRLM", lambda t: fraunces(t), 680, 200)
    texto_centro(d, (512, 440), "Socorro,\nRLM", f, AMARELO, espaco=8)
    for x, y, t in ((800, 820, "?"), (880, 700, "!"), (720, 900, "?")):
        texto_centro(d, (x, y), t, fraunces(150), CORAL)
    return im


def forca():
    im, d = novo()
    raio = [(560, 60), (300, 520), (480, 520), (400, 960), (760, 420), (560, 420), (680, 60)]
    d.polygon(raio, fill=AMARELO)
    d.line(raio + [raio[0]], fill=(214, 168, 30), width=14)
    d.rounded_rectangle((140, 600, 884, 820), radius=40, fill=TINTA)
    f = caber(d, "Força!", lambda t: fraunces(t), 640, 190)
    texto_centro(d, (512, 708), "Força!", f, BRANCO)
    return im


def aprovado():
    im, d = novo()
    camada = Image.new("RGBA", (G, G), (0, 0, 0, 0))
    c = ImageDraw.Draw(camada)
    c.rounded_rectangle((90, 330, 934, 690), radius=40, fill=PAPEL)
    c.rounded_rectangle((90, 330, 934, 690), radius=40, outline=VERMELHO, width=26)
    c.rounded_rectangle((130, 370, 894, 650), radius=26, outline=VERMELHO, width=10)
    f = caber(c, "APROVADO", lambda t: fraunces(t, 900, 0), 700, 170)
    texto_centro(c, (512, 510), "APROVADO", f, VERMELHO)
    im.alpha_composite(camada.rotate(-12, resample=Image.BICUBIC, center=(512, 510)))
    return im


DESENHOS = {
    "bora-estudar": bora_estudar,
    "passei": passei,
    "gabaritei": gabaritei,
    "foco-total": foco_total,
    "cafe-lei-seca": cafe_lei_seca,
    "revisao-em-dia": revisao_em_dia,
    "simulado-hoje": simulado_hoje,
    "valeu": valeu,
    "kkkk": kkkk,
    "socorro-rlm": socorro_rlm,
    "forca": forca,
    "aprovado": aprovado,
}


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for ident, _legenda in FIGURINHAS:
        im = adesivo(DESENHOS[ident]())
        caixa = im.getbbox()
        if caixa:
            # centraliza num quadrado com margem
            recorte = im.crop(caixa)
            lado = max(recorte.size) + 40
            quadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
            quadro.paste(recorte, ((lado - recorte.width) // 2, (lado - recorte.height) // 2))
            im = quadro
        im.resize((FINAL, FINAL), Image.LANCZOS).save(DESTINO / f"{ident}.png", optimize=True)
        print("ok", ident)


if __name__ == "__main__":
    main()
