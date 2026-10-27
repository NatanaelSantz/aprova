"""Falas do personagem: o boneco do Início conversa com quem estuda.

Tudo fica só neste computador (nos ajustes da conta), nunca vai para o servidor: as frases
que a pessoa escreve são texto livre. O servidor guarda só as escolhas do desenho do boneco.

{nome} nas frases vira o nome que a pessoa escolheu ("Vamos estudar, {nome}!" -> "Vamos estudar, Natanael!").
Sem nome, a vírgula e o {nome} somem ("Vamos estudar!").
"""

from __future__ import annotations

import random
import re

TIPOS = [
    ("motivacao", "Motivação"),
    ("engracadas", "Engraçadas"),
    ("dicas", "Dicas de estudo"),
    ("lembretes", "Lembretes do dia"),
]

INTERVALOS = [(12, "A cada 12 s"), (30, "A cada 30 s"), (90, "A cada 1 min e meio"), (0, "Só quando abro o app")]

# (frase, gesto): o gesto é a animação que o boneco faz enquanto fala ("" = nenhum)
FRASES: dict[str, list[tuple[str, str]]] = {
    "motivacao": [
        ("Vamos estudar, {nome}!", "aceno"),
        ("Bora, {nome}! Um passo de cada vez.", ""),
        ("Cada questão de hoje é um ponto a mais na prova, {nome}.", ""),
        ("Constância vence talento. Bora manter o ritmo!", ""),
        ("Você está mais perto da aprovação do que ontem, {nome}.", ""),
        ("Foco, {nome}! Essa vaga tem o seu nome.", "pulo"),
        ("Estudou ontem? Estuda hoje. Simples assim.", ""),
        ("Eu acredito em você, {nome}. Agora é só acreditar também!", "aceno"),
        ("Meu sonho é ver o seu nome no Diário Oficial.", ""),
        ("Um bloco de 25 minutos agora e o dia já valeu.", ""),
    ],
    "engracadas": [
        ("Eu estudaria por você, {nome}, mas eu sou feito de pixels.", ""),
        ("A banca não vai se corrigir sozinha. Bora!", ""),
        ("Psiu, {nome}... o celular pode esperar. A vaga não.", ""),
        ("Mais uma questão e eu faço uma dancinha. Combinado?", "danca"),
        ("Crase não é bicho de sete cabeças. É de oito.", ""),
        ("Se estudar fosse fácil, a concorrência seria um por vaga.", ""),
        ("Sem café eu viro pixel morto. E você, já tomou o seu?", ""),
        ("Já bebeu água hoje? Cérebro hidratado acerta mais.", ""),
        ("Errar aqui é treino. Errar na prova é que não pode!", ""),
        ("O Vade Mecum pesa, mas a posse pesa mais no bolso.", "pulo"),
        ("Procrastinar? Hoje não. Amanhã... também não!", ""),
        ("Eu ensaiei uma dança pra quando você passar. Olha só!", "danca"),
    ],
    "dicas": [
        ("Dica: revise amanhã o que você errou hoje.", ""),
        ("Dica: leia o enunciado até o fim antes das alternativas.", ""),
        ("Dica: questões antigas da banca são o melhor mapa da prova.", ""),
        ("Dica: 5 minutos de pausa a cada 25 deixam a cabeça leve.", ""),
        ("Dica: marque a lei seca com o marca-texto. Ajuda a lembrar.", ""),
        ("Dica: no modo estudo, a explicação aparece na hora.", ""),
        ("Dica: na dúvida entre duas, procure a palavra que generaliza demais.", ""),
    ],
}

PADRAO = {"ligado": True, "nome": "", "tipos": ["motivacao", "engracadas", "dicas", "lembretes"], "minhas": [], "intervalo": 30}
MAX_FRASES, MAX_TAMANHO = 30, 90  # frases próprias: quantas e de que tamanho


def validar(d) -> dict:
    """Ajustes das falas sempre num formato conhecido (o arquivo pode estar velho ou mexido)."""
    d = d if isinstance(d, dict) else {}
    tipos_validos = {t for t, _ in TIPOS}
    tipos = [t for t in (d.get("tipos") if isinstance(d.get("tipos"), list) else PADRAO["tipos"]) if t in tipos_validos]
    minhas = d.get("minhas") if isinstance(d.get("minhas"), list) else []
    minhas = [m.strip()[:MAX_TAMANHO] for m in minhas if isinstance(m, str) and m.strip()][:MAX_FRASES]
    intervalo = d.get("intervalo", PADRAO["intervalo"])
    return {
        "ligado": bool(d.get("ligado", PADRAO["ligado"])),
        "nome": str(d.get("nome") or "").strip()[:30],
        "tipos": tipos,
        "minhas": minhas,
        "intervalo": intervalo if intervalo in {i for i, _ in INTERVALOS} else PADRAO["intervalo"],
    }


def linhas_para_frases(texto: str) -> list[str]:
    """O que a pessoa escreveu (uma frase por linha) vira a lista de frases próprias."""
    return validar({"minhas": (texto or "").splitlines()})["minhas"]


def formatar(frase: str, nome: str) -> str:
    """Troca {nome} pelo nome. Sem nome: tira ", {nome}" / "{nome}, " e arruma os espaços."""
    nome = (nome or "").strip()
    if nome:
        return frase.replace("{nome}", nome)
    s = re.sub(r",\s*\{nome\}", "", frase)
    s = re.sub(r"\{nome\}\s*,\s*", "", s)
    s = s.replace("{nome}", "")
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s[:1].upper() + s[1:] if s else s


def do_dia(ctx: dict) -> list[tuple[str, str]]:
    """Lembretes que dependem do dia: revisão esperando, meta de hoje, sequência, hora.

    ctx: hora (0-23), revisao (questões para revisar hoje), meta_hoje e feito_hoje (segundos), sequencia (dias),
    dias_prova e concurso (Meu concurso, quando tem data)."""
    falas: list[tuple[str, str]] = []
    hora = ctx.get("hora", 12)
    n = ctx.get("revisao", 0)
    if n:
        falas.append((f"Tem {n} quest{'ões' if n != 1 else 'ão'} te esperando na revisão, {{nome}}.", ""))
    meta, feito = ctx.get("meta_hoje", 0), ctx.get("feito_hoje", 0)
    if meta and feito >= meta:
        falas.append(("Meta do dia cumprida! Hoje eu danço!", "danca"))
    elif meta and not feito:
        falas.append((f"A meta de hoje é {_hm(meta)}. Que tal começar agora, {{nome}}?", ""))
    elif meta:
        falas.append((f"Faltam {_hm(meta - feito)} pra meta de hoje. Tá quase!", ""))
    dias, concurso = ctx.get("dias_prova"), ctx.get("concurso") or "concurso"
    if isinstance(dias, int) and dias >= 0:
        if dias == 0:
            falas.append((f"Hoje é a prova do {concurso}! Respira fundo e vai com tudo, {{nome}}!", "pulo"))
        elif dias == 1:
            falas.append((f"Amanhã é a prova do {concurso}. Revisão leve e cama cedo, {{nome}}!", ""))
        elif dias <= 30:
            falas.append((f"Faltam {dias} dias para a prova do {concurso}. Reta final, {{nome}}!", "pulo"))
        else:
            falas.append((f"Faltam {dias} dias para a prova do {concurso}. Cada dia conta, {{nome}}.", ""))
    seq = ctx.get("sequencia", 0)
    if seq >= 3:
        falas.append((f"{seq} dias seguidos estudando! Não quebra a corrente, hein.", "pulo"))
    if hora >= 23 or hora < 5:
        falas.append(("Já é tarde, {nome}. Revisa um pouquinho e vai dormir, combinado?", ""))
    elif hora < 9:
        falas.append(("Bom dia, {nome}! Café e uma questãozinha?", "aceno"))
    elif 12 <= hora < 14:
        falas.append(("Hora do almoço! Depois, uma revisão leve cai bem.", ""))
    return falas


def _hm(segundos: int) -> str:
    h, m = divmod(max(0, int(segundos)) // 60, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def todas(cfg: dict, ctx: dict | None = None) -> list[tuple[str, str]]:
    """Todas as frases que podem sair agora (de acordo com os tipos escolhidos e as frases próprias)."""
    cfg = validar(cfg)
    lista: list[tuple[str, str]] = []
    for tipo in cfg["tipos"]:
        if tipo == "lembretes":
            lista += do_dia(ctx or {})
        else:
            lista += FRASES.get(tipo, [])
    lista += [(m, "") for m in cfg["minhas"]]
    return lista


def escolher(cfg: dict, ctx: dict | None = None, anterior: str | None = None, rnd: random.Random | None = None,
             nome_padrao: str = "") -> tuple[str, str] | None:
    """Uma frase pronta (com o nome) e o gesto dela; nunca repete a anterior quando há outra. None se não há frase."""
    cfg = validar(cfg)
    lista = todas(cfg, ctx)
    if not lista:
        return None
    rnd = rnd or random.Random()
    nome = cfg["nome"] or nome_padrao
    # as frases próprias e os lembretes do dia aparecem mais (são os mais pessoais)
    pessoais = set(do_dia(ctx or {})) | {(m, "") for m in cfg["minhas"]}
    pesos = [3 if item in pessoais else 1 for item in lista]
    for _ in range(8):
        frase, gesto = rnd.choices(lista, weights=pesos)[0]
        texto = formatar(frase, nome)
        if texto != anterior or len(lista) == 1:
            return texto, gesto
    return texto, gesto
