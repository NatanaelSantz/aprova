"""Card da semana: uma imagem com o resumo do estudo para mandar no WhatsApp ou postar nos Stories.

Mostra horas, questões, acerto, dias estudados (as barras dos sete dias), sequência, o concurso e o
personagem. Só números de estudo: nada de e-mail nem nome completo. 1080 x 1350 (cabe no feed e,
com margem, nos Stories).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from . import analise, config

DIAS = ["S", "T", "Q", "Q", "S", "S", "D"]
SITE = "natanaelsantz.github.io/aprova"


def dados_semana(banco, semana: date | None = None, nome: str = "", concurso: str = "") -> dict:
    """Os números que vão no card (a semana de segunda a domingo que contém 'semana', por padrão a atual)."""
    hoje = date.today()
    seg = analise.inicio_semana(semana or hoje)
    fim = seg + timedelta(days=7)
    tempo = banco.tempo_por_dia(seg)
    questoes_dia = banco.dias_com_questoes(seg)
    resp = [r for r in banco.respostas_corrigidas(seg) if r["dia"] < fim.isoformat()]
    dias = []
    for i in range(7):
        d = seg + timedelta(days=i)
        k = d.isoformat()
        s = tempo.get(k, 0) if k < fim.isoformat() else 0
        dias.append({"rotulo": DIAS[i], "segundos": s, "estudou": s >= analise.MIN_SEGUNDOS_DIA or questoes_dia.get(k, 0) > 0, "futuro": d > hoje})
    acertos = sum(1 for r in resp if r["correta"])
    return {
        "inicio": seg,
        "fim": seg + timedelta(days=6),
        "segundos": sum(d["segundos"] for d in dias),
        "questoes": len(resp),
        "acertos": acertos,
        "taxa": acertos / len(resp) if resp else None,
        "dias": dias,
        "dias_estudados": sum(1 for d in dias if d["estudou"]),
        "sequencia": banco.estatisticas()["sequencia"],
        "nome": (nome or "").strip()[:30],
        "concurso": (concurso or "").strip()[:40],
    }


def horas(segundos: int) -> str:
    m = int(segundos) // 60
    return f"{m} min" if m < 60 else f"{m // 60}h{m % 60:02d}"


def _periodo(d: dict) -> str:
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    a, b = d["inicio"], d["fim"]
    if a.month == b.month:
        return f"{a.day} a {b.day} de {meses[b.month - 1]}"
    return f"{a.day} {meses[a.month - 1]} a {b.day} {meses[b.month - 1]}"


def frase(d: dict) -> str:
    """Uma linha de incentivo que combina com a semana (vai no card e na legenda)."""
    if d["dias_estudados"] >= 6:
        return "Semana praticamente completa. Isso é constância."
    if d["segundos"] >= 10 * 3600:
        return "Mais de dez horas de estudo numa semana só."
    if d["taxa"] is not None and d["taxa"] >= 0.8 and d["questoes"] >= 30:
        return "Acerto alto num bom volume de questões."
    if d["sequencia"] >= 7:
        return f"{d['sequencia']} dias seguidos sem falhar."
    if d["dias_estudados"] >= 3:
        return "Mais uma semana somando. Rumo à aprovação."
    if d["segundos"] > 0 or d["questoes"] > 0:
        return "Começou. Semana que vem a gente aumenta."
    return "Toda semana é uma chance de começar."


def legenda(d: dict) -> str:
    """Texto para colar junto com a imagem."""
    partes = [f"Minha semana no Aprova ({_periodo(d)}): {horas(d['segundos'])} de estudo"]
    if d["questoes"]:
        partes.append(f"{d['questoes']} questões" + (f" com {d['taxa'] * 100:.0f}% de acerto" if d["taxa"] is not None else ""))
    partes.append(f"{d['dias_estudados']} de 7 dias")
    if d["sequencia"] >= 3:
        partes.append(f"{d['sequencia']} dias seguidos")
    return ", ".join(partes) + f". {frase(d)} https://{SITE}"


def imagem_semana(d: dict, cfg_boneco: dict | None, destino: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1080, 1350
    branco, ouro, claro = (255, 255, 255), (226, 176, 74), (216, 223, 247)
    azul_escuro = (20, 33, 61)
    faixa = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), azul_escuro), Image.new("RGB", (w, h), (35, 64, 168)), faixa).convert("RGBA")
    # as caixas translúcidas vão numa camada à parte (desenhar com alfa direto na imagem não mistura as cores)
    camada = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    dr = ImageDraw.Draw(img)
    fontes = config.ASSETS_DIR / "fonts"

    def fonte(nome_arq: str, tam: int):
        try:
            return ImageFont.truetype(str(fontes / nome_arq), tam)
        except OSError:
            return ImageFont.load_default()

    titulo = fonte("Fraunces.ttf", 78)
    numero = fonte("Fraunces.ttf", 150)
    medio = fonte("Fraunces.ttf", 64)
    texto = fonte("AtkinsonHyperlegible-Regular.ttf", 38)
    pequeno = fonte("AtkinsonHyperlegible-Regular.ttf", 30)
    negrito = fonte("AtkinsonHyperlegible-Bold.ttf", 40)

    def largura_de(s: str, f) -> int:
        cx = dr.textbbox((0, 0), s, font=f)
        return cx[2] - cx[0]

    def centro(y: int, s: str, f, cor, x0: int = 0, x1: int = w):
        dr.text((x0 + (x1 - x0 - largura_de(s, f)) // 2, y), s, font=f, fill=cor)

    # cabeçalho
    try:
        icone = Image.open(config.ASSETS_DIR / "icon.png").convert("RGBA").resize((88, 88))
        img.paste(icone, (72, 64), icone)
    except OSError:
        pass
    dr.text((180, 62), "Aprova", font=fonte("Fraunces.ttf", 60), fill=branco)
    dr.text((182, 134), "minha semana de estudo", font=pequeno, fill=claro)
    periodo = _periodo(d)
    dr.text((w - 72 - largura_de(periodo, texto), 92), periodo, font=texto, fill=claro)

    # quem e para quê
    y = 230
    if d["nome"] or d["concurso"]:
        linha = " · ".join(x for x in (d["nome"], d["concurso"]) if x)
        dr.text((72, y), linha, font=negrito, fill=ouro)
        y += 60

    # o número grande: horas
    dr.text((72, y + 10), horas(d["segundos"]), font=numero, fill=branco)
    dr.text((76, y + 190), "de estudo na semana", font=texto, fill=claro)

    # o boneco à direita, grande
    if cfg_boneco:
        try:
            from . import avatar

            b = avatar.boneco(cfg_boneco, alegre=True, braco="aceno", aceno=1)
            b = b.resize((b.width * 5, b.height * 5), Image.NEAREST)
            img.paste(b, (w - 72 - b.width, y - 70), b)
        except Exception:  # noqa: BLE001 - sem boneco, o card sai do mesmo jeito
            pass

    # três caixas: questões, acerto, dias
    y = 560
    caixas = [
        (str(d["questoes"]), "questões"),
        (f"{d['taxa'] * 100:.0f}%" if d["taxa"] is not None else "—", "de acerto"),
        (f"{d['dias_estudados']}/7", "dias"),
    ]
    lw, gap = 296, 24
    x = 72
    for valor, rotulo in caixas:
        dc.rounded_rectangle([x, y, x + lw, y + 190], radius=28, fill=(255, 255, 255, 34))
        centro(y + 26, valor, medio, branco, x, x + lw)
        centro(y + 124, rotulo, pequeno, claro, x, x + lw)
        x += lw + gap

    # os sete dias em barras
    y = 790
    dr.text((72, y), "Dia a dia", font=negrito, fill=branco)
    topo, base = y + 70, y + 270
    maior = max([dd["segundos"] for dd in d["dias"]] + [1800])
    bw, bgap = 108, 30
    x = 72
    for dd in d["dias"]:
        alt = int((base - topo - 10) * dd["segundos"] / maior) if dd["segundos"] else 0
        if alt:
            dr.rounded_rectangle([x, base - alt, x + bw, base], radius=14, fill=ouro if dd["estudou"] else (255, 255, 255, 255))
        else:
            dc.rounded_rectangle([x, base - 10, x + bw, base], radius=5, fill=(255, 255, 255, 60 if not dd["futuro"] else 30))
        if dd["segundos"]:
            centro(base - max(alt, 10) - 44, horas(dd["segundos"]), pequeno, claro, x, x + bw)
        centro(base + 14, dd["rotulo"], negrito, branco if dd["estudou"] else claro, x, x + bw)
        x += bw + bgap

    # sequência e frase
    img = Image.alpha_composite(img, camada)
    dr = ImageDraw.Draw(img)
    y = 1150
    if d["sequencia"] >= 2:
        dr.text((72, y), f"{d['sequencia']} dias seguidos", font=negrito, fill=ouro)
        y += 54
    dr.text((72, y), frase(d), font=texto, fill=branco)

    # rodapé
    dr.text((72, h - 70), SITE, font=pequeno, fill=claro)
    gratis = "app gratuito de estudo para concursos"
    dr.text((w - 72 - largura_de(gratis, pequeno), h - 70), gratis, font=pequeno, fill=claro)

    destino.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(destino, "PNG")
    return destino
