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


def _questoes_da_disciplina(banco, disciplina: str, prova_id: int | None = None) -> list[dict]:
    """Questões boas de uma disciplina: da biblioteca toda (sem repetidas) ou de uma prova só."""
    from .montador import problema

    base = banco.banco_de_questoes(unicas=prova_id is None)
    return [q for q in base if q["disciplina"] == disciplina and (prova_id is None or q["prova_id"] == prova_id) and not problema(q)]


def preparar_treino(banco, disciplina: str, quantidade: int = 10, prova_id: int | None = None, titulo: str = "") -> int | None:
    """Treino rápido (ou mini prova) de uma disciplina com questões da biblioteca.

    Primeiro as que você nunca fez; as que esperam o dia da revisão ficam por último.
    Com `prova_id`, só as questões daquela prova (ex.: Conhecimentos Específicos do seu cargo)."""
    from .montador import Historico, _incompleta

    pool = _questoes_da_disciplina(banco, disciplina, prova_id)
    if not pool:
        return None
    hist = Historico(banco)
    random.shuffle(pool)
    pool.sort(key=lambda q: (_incompleta(q), *hist.nivel(q)))
    pid = banco.prova_interna(ORIGEM_TREINO, titulo or f"Treino de {disciplina}")
    banco.salvar_questoes(pid, _copias(pool[: max(1, quantidade)]))
    banco.atualizar_prova(pid, orgao="", banca="")
    return pid


def opcoes_mini_prova(banco, disciplina: str) -> dict:
    """O que a biblioteca tem para a mini prova de uma disciplina.

    {"total", "novas", "provas": [{"prova_id", "titulo", "questoes", "novas"}]}: "novas" são as que você nunca fez.
    """
    from .montador import Historico, problema

    hist = Historico(banco)
    todas = _questoes_da_disciplina(banco, disciplina)
    por_prova: dict[int, dict] = {}
    for q in banco.banco_de_questoes(unicas=False):
        if q["disciplina"] != disciplina or problema(q):
            continue
        p = por_prova.setdefault(q["prova_id"], {"prova_id": q["prova_id"], "titulo": q["prova_titulo"] or "Prova sem nome", "questoes": 0, "novas": 0})
        p["questoes"] += 1
        p["novas"] += 0 if hist.ja_vista(q) else 1
    return {
        "total": len(todas),
        "novas": sum(1 for q in todas if not hist.ja_vista(q)),
        "provas": sorted(por_prova.values(), key=lambda p: (-p["questoes"], p["titulo"])),
    }


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
