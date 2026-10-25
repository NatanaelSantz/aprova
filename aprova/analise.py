"""Números do Painel: tempo de estudo, dias da semana e desempenho.

Funções puras sobre o banco, sem Flet, para ficarem fáceis de testar.
"""

from __future__ import annotations

from datetime import date, timedelta

DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_LONGOS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MIN_SEGUNDOS_DIA = 5 * 60  # abaixo disso (e sem questões) o dia não conta como "estudado"
MIN_AMOSTRA = 5  # questões mínimas para classificar uma disciplina


def inicio_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def fmt_duracao(segundos: int) -> str:
    m = int(round((segundos or 0) / 60))
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def dias_planejados(texto: str) -> list[int]:
    dias = sorted({int(x) for x in str(texto or "").split(",") if x.strip().isdigit() and 0 <= int(x) <= 6})
    return dias or [0, 1, 2, 3, 4]


def resumo_tempo(
    banco, hoje: date | None = None, meta_horas: float = 10, planejados: list[int] | None = None, inicio: date | None = None
) -> dict:
    """`inicio`: dia em que você começou a usar as metas. Dias antes dele não contam contra você."""
    hoje = hoje or date.today()
    planejados = planejados if planejados is not None else [0, 1, 2, 3, 4]
    meta_semana = int(float(meta_horas or 0) * 3600)
    meta_dia = meta_semana // len(planejados) if planejados else 0
    meta_dias = len(planejados)
    semana0 = inicio_semana(hoje)
    desde = semana0 - timedelta(weeks=11)
    tempo = banco.tempo_por_dia(desde)
    questoes = banco.dias_com_questoes(desde)

    def estudou(d: date) -> bool:
        k = d.isoformat()
        return tempo.get(k, 0) >= MIN_SEGUNDOS_DIA or questoes.get(k, 0) > 0

    semana = []
    for i in range(7):
        d = semana0 + timedelta(days=i)
        semana.append(
            {
                "dia": d,
                "rotulo": DIAS_CURTOS[i],
                "segundos": tempo.get(d.isoformat(), 0),
                "questoes": questoes.get(d.isoformat(), 0),
                "estudou": estudou(d),
                "hoje": d == hoje,
                "futuro": d > hoje,
                "antes": bool(inicio and d < inicio),
                "meta": meta_dia if i in planejados and not (inicio and d < inicio) else 0,
            }
        )
    for x in semana:
        if x["antes"]:
            x["situacao"] = "extra" if x["segundos"] else "antes"
        elif x["meta"]:
            x["situacao"] = "cumprida" if x["segundos"] >= x["meta"] else ("hoje" if x["hoje"] else ("futuro" if x["futuro"] else "abaixo"))
        else:
            x["situacao"] = "extra" if x["segundos"] else "folga"
    total_semana = sum(x["segundos"] for x in semana)
    previsto_ate_ontem = sum(x["meta"] for x in semana if x["dia"] < hoje)
    saldo = total_semana - previsto_ate_ontem
    # semana em que você começou: a meta é proporcional aos dias que restavam
    proporcional = bool(inicio and semana0 < inicio <= semana0 + timedelta(days=6))
    if proporcional:
        meta_semana = sum(x["meta"] for x in semana)
        meta_dias = sum(1 for x in semana if x["meta"])
    dias_semana = sum(1 for x in semana if x["estudou"])
    passada0 = semana0 - timedelta(weeks=1)
    total_passada = sum(tempo.get((passada0 + timedelta(days=i)).isoformat(), 0) for i in range(7))

    # sequência de dias seguidos
    seq = 0
    d = hoje if estudou(hoje) else hoje - timedelta(days=1)
    while d >= desde and estudou(d):
        seq += 1
        d -= timedelta(days=1)

    # últimas 12 semanas (mapa de calor) e 8 semanas (barras)
    semanas = []
    for w in range(11, -1, -1):
        s0 = semana0 - timedelta(weeks=w)
        dias = [s0 + timedelta(days=i) for i in range(7)]
        semanas.append(
            {
                "inicio": s0,
                "dias": [{"dia": x, "segundos": tempo.get(x.isoformat(), 0), "estudou": estudou(x), "futuro": x > hoje} for x in dias],
                "segundos": sum(tempo.get(x.isoformat(), 0) for x in dias),
                "dias_estudados": sum(1 for x in dias if estudou(x) and x <= hoje),
            }
        )

    # em quais dias da semana você estuda (últimas 8 semanas completas + a atual)
    por_dia_semana = []
    for i in range(7):
        ocorrencias = [semana0 - timedelta(weeks=w) + timedelta(days=i) for w in range(8)]
        ocorrencias = [x for x in ocorrencias if x <= hoje]
        vezes = sum(1 for x in ocorrencias if estudou(x))
        seg = sum(tempo.get(x.isoformat(), 0) for x in ocorrencias)
        por_dia_semana.append(
            {
                "rotulo": DIAS_CURTOS[i],
                "nome": DIAS_LONGOS[i],
                "vezes": vezes,
                "de": len(ocorrencias),
                "media_segundos": seg / len(ocorrencias) if ocorrencias else 0,
            }
        )

    ultimas4 = [x for s in semanas[-4:] for x in s["dias"] if x["estudou"]]
    media_dia = sum(x["segundos"] for x in ultimas4) / len(ultimas4) if ultimas4 else 0
    return {
        "semana": semana,
        "total_semana": total_semana,
        "total_passada": total_passada,
        "dias_semana": dias_semana,
        "meta_dias": meta_dias,
        "meta_segundos": meta_semana,
        "meta_dia": meta_dia,
        "progresso": min(1.0, total_semana / meta_semana) if meta_semana else (1.0 if total_semana else 0.0),
        "saldo": saldo,
        "previsto_ate_ontem": previsto_ate_ontem,
        "proporcional": proporcional,
        "inicio": inicio,
        "sequencia": seq,
        "semanas": semanas,
        "por_dia_semana": por_dia_semana,
        "media_dia": media_dia,
        "por_disciplina": banca_tempo_disciplina(banco, semana0 - timedelta(weeks=3)),
        "hoje_segundos": tempo.get(hoje.isoformat(), 0),
    }


def banca_tempo_disciplina(banco, desde: date) -> list[tuple[str, int]]:
    return [x for x in banco.tempo_por_disciplina(desde) if x[1] >= 60]


def classificar(taxa: float | None, n: int) -> str:
    if taxa is None or n < MIN_AMOSTRA:
        return "poucos"
    if taxa >= 0.7:
        return "forte"
    if taxa >= 0.5:
        return "atencao"
    return "fraco"


ROTULOS = {"forte": "Forte", "atencao": "Atenção", "fraco": "Precisa melhorar", "poucos": "Poucos dados"}


def resumo_desempenho(banco, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    disc = banco.desempenho_por("disciplina")
    for d in disc:
        d["nivel"] = classificar(d["taxa"], d["respondidas"])
    ordem = {"fraco": 0, "atencao": 1, "forte": 2, "poucos": 3}
    disc.sort(key=lambda d: (ordem[d["nivel"]], d["taxa"]))
    total = sum(d["respondidas"] for d in disc)
    acertos = sum(d["acertos"] for d in disc)

    # evolução: últimas 8 semanas
    semana0 = inicio_semana(hoje)
    respostas = banco.respostas_corrigidas(semana0 - timedelta(weeks=7))
    semanas = []
    for w in range(7, -1, -1):
        s0 = semana0 - timedelta(weeks=w)
        s1 = s0 + timedelta(days=7)
        dessa = [r for r in respostas if s0.isoformat() <= r["dia"] < s1.isoformat()]
        n = len(dessa)
        a = sum(1 for r in dessa if r["correta"])
        semanas.append({"inicio": s0, "respondidas": n, "acertos": a, "taxa": a / n if n else None})
    atual, anterior = semanas[-1], semanas[-2]
    variacao = None
    if atual["taxa"] is not None and anterior["taxa"] is not None:
        variacao = atual["taxa"] - anterior["taxa"]

    def limpar(lista: list[dict], vazio: str) -> list[dict]:
        for x in lista:
            x["nome"] = x["chave"] or vazio
            x["nivel"] = classificar(x["taxa"], x["respondidas"])
        return lista

    return {
        "respondidas": total,
        "acertos": acertos,
        "taxa": acertos / total if total else None,
        "disciplinas": disc,
        "fortes": [d for d in disc if d["nivel"] == "forte"],
        "fracas": [d for d in disc if d["nivel"] in ("fraco", "atencao")],
        "semanas": semanas,
        "variacao": variacao,
        "semana_respondidas": atual["respondidas"],
        "bancas": limpar(banco.desempenho_por("banca"), "Sem banca (simulados e revisão)"),
        "concursos": limpar(banco.desempenho_por("orgao"), "Outras provas"),
    }
