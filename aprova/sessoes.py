"""Sessões rápidas montadas pelo app: revisão espaçada, treino de uma disciplina
e o "próximo estudo" sugerido na tela Início."""

from __future__ import annotations

import random
from datetime import date

from . import analise

ORIGEM_REVISAO = "aprova://revisao"
ORIGEM_TREINO = "aprova://simulado/treino"


def _copias(questoes: list[dict]) -> list[dict]:
    saida = []
    for i, q in enumerate(questoes, start=1):
        ref = q.get("ref") or f"{q['prova_id']}:{q['numero']}"
        saida.append(
            {
                "numero": i,
                "enunciado": q["enunciado"],
                "texto_base": q.get("texto_base") or "",
                "alternativas": q["alternativas"],
                "gabarito": q.get("gabarito"),
                "explicacao": q.get("explicacao") or "",
                "disciplina": q.get("disciplina") or "Geral",
                "tipo": q.get("tipo") or "ME",
                "fonte": q.get("fonte") or (f"{q['prova_titulo']}, questão {q['numero']}" if q.get("prova_titulo") else ""),
                "ref": ref,
                "pagina": 0,
            }
        )
    return saida


def preparar_revisao(banco, disciplina: str | None = None, todas: bool = False, limite: int = 30) -> int | None:
    """Monta a sessão de revisão (as questões que venceram hoje). Devolve o id da prova ou None."""
    questoes = banco.revisao_questoes(disciplina, todas, limite)
    if not questoes:
        return None
    titulo = f"Revisão de {date.today():%d/%m}" + (f" · {disciplina}" if disciplina else "")
    pid = banco.prova_interna(ORIGEM_REVISAO, titulo)
    banco.salvar_questoes(pid, _copias(questoes))
    return pid


def preparar_treino(banco, disciplina: str, quantidade: int = 10) -> int | None:
    """Treino rápido de uma disciplina com questões da biblioteca (primeiro as que você nunca fez)."""
    from .montador import Historico, _incompleta, problema

    pool = [q for q in banco.banco_de_questoes() if q["disciplina"] == disciplina and not problema(q)]
    if not pool:
        return None
    hist = Historico(banco)
    random.shuffle(pool)
    pool.sort(key=lambda q: (_incompleta(q), *hist.nivel(q)))  # nunca vistas primeiro; as que esperam a revisão por último
    pid = banco.prova_interna(ORIGEM_TREINO, f"Treino de {disciplina}")
    banco.salvar_questoes(pid, _copias(pool[:quantidade]))
    banco.atualizar_prova(pid, orgao="", banca="")
    return pid


def proximo_estudo(banco) -> dict | None:
    """O que estudar agora: revisão vencida > ponto fraco > disciplina que mais cai."""
    rev = banco.revisao_resumo()
    if rev["pendentes"]:
        n = rev["pendentes"]
        return {
            "tipo": "revisao",
            "titulo": "Revisão do dia",
            "detalhe": (f"{n} questões que você errou estão" if n != 1 else "1 questão que você errou está") + " no dia de revisar. Revisar no tempo certo fixa o conteúdo.",
            "acao": "Começar revisão",
        }
    des = analise.resumo_desempenho(banco)
    disponiveis = {q["disciplina"] for q in banco.banco_de_questoes()}
    for d in des["fracas"]:
        if d["chave"] in disponiveis:
            return {
                "tipo": "treino",
                "disciplina": d["chave"],
                "titulo": d["chave"],
                "detalhe": f"Seu ponto mais fraco agora: você acerta {d['taxa'] * 100:.0f}% das questões. Um treino de 10 questões ajuda.",
                "acao": "Treinar 10 questões",
            }
    for p in banco.prioridades(3):
        if p["disciplina"] in disponiveis:
            return {
                "tipo": "treino",
                "disciplina": p["disciplina"],
                "titulo": p["disciplina"],
                "detalhe": f"É {p['peso'] * 100:.0f}% das provas da sua biblioteca. Comece por aqui.",
                "acao": "Treinar 10 questões",
            }
    return None
