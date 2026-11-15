"""Conquistas: marcos de estudo que destravam roupas e acessórios do personagem.

Tudo é medido no que está neste aparelho (questões, tempo, simulados, revisão, edital). Um item
trancado não pode ser escolhido no criador do personagem até a conquista sair; quem já usava o item
antes desta versão continua com ele. As conquistas já comemoradas ficam nos ajustes ("conquistas_vistas").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from . import edital

SIMULADO_MIN = 20  # questões para um simulado contar como "nota alta"


@dataclass(frozen=True)
class Conquista:
    chave: str
    nome: str
    descricao: str  # o que fazer, no imperativo ("Resolva 500 questões")
    meta: int
    medir: Callable[[dict], int]  # recebe os números medidos e devolve quanto já foi
    destrava: tuple[str, str]  # (categoria do avatar, valor)
    premio: str  # nome do item, para mostrar
    unidade: str = ""  # "h" para horas


def _h(s: int) -> int:
    return int(s // 3600)


CONQUISTAS: list[Conquista] = [
    Conquista("primeiro_simulado", "Primeiro simulado", "Termine um simulado", 1, lambda n: n["simulados"], ("acessorio", "viking"), "Capacete viking"),
    Conquista("questoes_100", "Cem questões", "Resolva 100 questões", 100, lambda n: n["questoes"], ("item", "lapis"), "Lápis gigante"),
    Conquista("sequencia_7", "Semana inteira", "Estude 7 dias seguidos", 7, lambda n: n["sequencia_max"], ("extra", "capa"), "Capa de herói"),
    Conquista("horas_10", "Dez horas", "Some 10 horas de estudo", 10, lambda n: _h(n["segundos"]), ("item", "cafe"), "Café", "h"),
    Conquista("nota_alta", "Nota alta", f"Acerte 90% num simulado de {SIMULADO_MIN} questões ou mais", 90, lambda n: n["melhor_nota"], ("acessorio", "capelo"), "Capelo de formatura", "%"),
    Conquista("questoes_500", "Quinhentas questões", "Resolva 500 questões", 500, lambda n: n["questoes"], ("extra", "medalha"), "Medalha"),
    Conquista("horas_50", "Cinquenta horas", "Some 50 horas de estudo", 50, lambda n: _h(n["segundos"]), ("item", "espada"), "Espada", "h"),
    Conquista("dominadas_50", "Memória de elefante", "Domine 50 questões na revisão", 50, lambda n: n["dominadas"], ("acessorio", "aureola"), "Auréola"),
    Conquista("simulados_10", "Dez simulados", "Termine 10 simulados", 10, lambda n: n["simulados"], ("item", "trofeu"), "Troféu"),
    Conquista("edital_metade", "Metade do edital", "Estude metade do edital verticalizado", 50, lambda n: n["edital_pct"], ("item", "cajado"), "Cajado", "%"),
    Conquista("edital_disciplina", "Disciplina fechada", "Complete uma disciplina inteira do edital", 1, lambda n: n["edital_disciplinas"], ("acessorio", "chapeu"), "Chapéu de mago"),
    Conquista("sequencia_30", "Um mês sem falhar", "Estude 30 dias seguidos", 30, lambda n: n["sequencia_max"], ("acessorio", "coroa"), "Coroa"),
    Conquista("questoes_2000", "Duas mil questões", "Resolva 2.000 questões", 2000, lambda n: n["questoes"], ("item", "diploma"), "Diploma"),
    Conquista("horas_200", "Duzentas horas", "Some 200 horas de estudo", 200, lambda n: _h(n["segundos"]), ("roupa", "armadura"), "Armadura", "h"),
]
POR_CHAVE = {c.chave: c for c in CONQUISTAS}
TRANCADOS: dict[tuple[str, str], Conquista] = {c.destrava: c for c in CONQUISTAS}


def medir(banco, aj) -> dict:
    """Os números de onde saem as conquistas (uma consulta de cada, leve)."""
    est = banco.estatisticas()
    tempo = banco.tempo_por_dia(date(2000, 1, 1))
    simulados = [t for t in banco.tentativas(limite=100000) if t.get("modo") == "simulado" and t.get("total")]
    melhor = max((100 * t["acertos"] / t["total"] for t in simulados if t["total"] >= SIMULADO_MIN), default=0)
    seq_max = max(est["sequencia"], int(aj.get("sequencia_max") or 0))
    if seq_max > int(aj.get("sequencia_max") or 0):
        aj.set("sequencia_max", seq_max)  # a maior sequência fica guardada: perder a sequência não tira a conquista
    ed = aj.get("edital")
    pct = discs = 0
    if edital.valido(ed):
        pct = int(edital.progresso(ed)["fracao"] * 100)
        discs = sum(1 for i in range(len(ed["disciplinas"])) if edital.progresso(ed, so=i)["fracao"] >= 1)
    return {
        "questoes": est["respondidas"],
        "segundos": sum(tempo.values()),
        "sequencia_max": seq_max,
        "simulados": len(simulados),
        "melhor_nota": int(melhor),
        "dominadas": banco.revisao_resumo()["dominadas"],
        "edital_pct": pct,
        "edital_disciplinas": discs,
    }


def avaliar(banco, aj) -> list[dict]:
    """[{"conquista", "valor", "feita"}] na ordem da lista (as mais fáceis primeiro)."""
    n = medir(banco, aj)
    saida = []
    for c in CONQUISTAS:
        v = min(int(c.medir(n)), c.meta)
        saida.append({"conquista": c, "valor": v, "feita": v >= c.meta})
    return saida


def feitas(banco, aj) -> set[str]:
    return {a["conquista"].chave for a in avaliar(banco, aj) if a["feita"]}


def destravados(banco, aj) -> set[tuple[str, str]]:
    return {POR_CHAVE[k].destrava for k in feitas(banco, aj)}


def trancado(categoria: str, valor: str, abertos: set[tuple[str, str]], cfg_atual: dict | None = None) -> Conquista | None:
    """A conquista que falta para usar este item, ou None se está liberado (ou a pessoa já o usa)."""
    c = TRANCADOS.get((categoria, valor))
    if c is None or (categoria, valor) in abertos:
        return None
    if cfg_atual and cfg_atual.get(categoria) == valor:
        return None  # já usava antes de existirem conquistas: fica
    return c


def novas(banco, aj) -> list[Conquista]:
    """Conquistas feitas que ainda não foram comemoradas (e marca como vistas)."""
    vistas = set(aj.get("conquistas_vistas") or [])
    agora = feitas(banco, aj)
    if not vistas and aj.get("conquistas_vistas") is None:
        # primeira vez nesta versão: o que já estava feito não vira uma enxurrada de avisos
        aj.set("conquistas_vistas", sorted(agora))
        return []
    recentes = [POR_CHAVE[k] for k in CONQUISTAS_ORDEM if k in agora and k not in vistas]
    if recentes:
        aj.set("conquistas_vistas", sorted(vistas | agora))
    return recentes


CONQUISTAS_ORDEM = [c.chave for c in CONQUISTAS]
