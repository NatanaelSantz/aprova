"""Monta simulados com o número de questões e a distribuição por disciplina do concurso.

As questões vêm, nesta ordem:
1. das provas da sua biblioteca que combinam com o concurso (órgão, banca ou cargo);
2. das outras provas da biblioteca, se você permitir;
3. de questões novas criadas pela IA no estilo da banca (opcional, precisa da chave do Claude).
"""

from __future__ import annotations

import random
import unicodedata
from datetime import datetime

MODELOS: dict[str, dict] = {
    "Dataprev 2026 (FGV) — 70 questões": {
        "filtro": "Dataprev",
        "banca": "FGV",
        "disciplinas": [
            ("Língua Portuguesa", 12),
            ("Língua Inglesa", 12),
            ("Raciocínio Lógico", 5),
            ("Atualidades", 6),
            ("Segurança da Informação", 5),
            ("Conhecimentos Específicos", 30),
        ],
    },
}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def combina(q: dict, filtro: str) -> bool:
    if not filtro.strip():
        return True
    alvo = _norm(" ".join(str(q.get(k) or "") for k in ("prova_titulo", "orgao", "banca", "cargo")))
    return all(p in alvo for p in _norm(filtro).split())


def contar_disponiveis(questoes: list[dict], filtro: str, usar_outras: bool) -> dict[str, int]:
    cont: dict[str, int] = {}
    for q in questoes:
        if usar_outras or combina(q, filtro):
            cont[q["disciplina"]] = cont.get(q["disciplina"], 0) + 1
    return cont


def exemplos_para(todas: list[dict], disciplina: str, filtro: str = "", banca: str = "", n: int = 16) -> list[dict]:
    """Questões reais da biblioteca que servem de modelo para a IA (mesmo concurso, senão mesma banca)."""
    mesmas = [q for q in todas if q["disciplina"] == disciplina and combina(q, filtro)] if filtro.strip() else []
    if len(mesmas) < 4 and banca:
        mesmas += [q for q in todas if q["disciplina"] == disciplina and _norm(banca) in _norm(q.get("banca") or "") and q not in mesmas]
    if len(mesmas) < 4:
        mesmas += [q for q in todas if q["disciplina"] == disciplina and q not in mesmas]
    com_gab = [q for q in mesmas if q.get("gabarito")] or mesmas
    random.shuffle(com_gab)
    return com_gab[:n]


def gerar_lote_ia(banco, ajustes, filtro: str, banca: str, distribuicao: list[tuple[str, int]], progresso=None) -> dict:
    """Cria uma prova só com questões inéditas da IA, no estilo das provas do concurso na biblioteca."""
    from . import ia

    todas = banco.banco_de_questoes()
    feitas: list[dict] = []
    faltas: dict[str, int] = {}
    total = sum(n for _, n in distribuicao) or 1
    feito = 0
    for disc, n in distribuicao:
        if n <= 0:
            continue
        if progresso:
            progresso(feito / total, f"Criando {n} questões de {disc} com base nas provas…")
        try:
            novas = ia.gerar_questoes(
                disc, n, ajustes.chave_claude, ajustes["claude_modelo"], banca=banca, concurso=filtro,
                exemplos=exemplos_para(todas, disc, filtro, banca),
            )
        except Exception as e:  # noqa: BLE001
            novas = []
            faltas[f"{disc} ({type(e).__name__})"] = n
        for q in novas:
            q["fonte"] = f"Inédita (IA) no estilo {banca or filtro or 'de concurso'}"
        feitas += novas
        if len(novas) < n:
            faltas.setdefault(disc, n - len(novas))
        feito += n
    if not feitas:
        return {"prova_id": None, "total": 0, "faltas": faltas}
    for i, q in enumerate(feitas, start=1):
        q["numero"] = i
        q["pagina"] = 0
    pid = banco.criar_prova(
        titulo=f"Questões inéditas — {filtro or banca or 'IA'} ({datetime.now():%d/%m})",
        cargo="",
        orgao=filtro,
        banca=banca,
        ano=str(datetime.now().year),
        origem_url=f"aprova://ia/{datetime.now():%Y%m%d%H%M%S}",
        modo="questoes",
    )
    banco.salvar_questoes(pid, feitas)
    if progresso:
        progresso(1.0, "Pronto")
    return {"prova_id": pid, "total": len(feitas), "faltas": faltas}


def distribuicao_do_concurso(banco, filtro: str, total: int = 20) -> list[tuple[str, int]]:
    """Distribuição proporcional às provas reais do concurso na biblioteca."""
    cont: dict[str, int] = {}
    for q in banco.banco_de_questoes():
        if combina(q, filtro) and not str(q.get("origem_url", "")).startswith("aprova://"):
            cont[q["disciplina"]] = cont.get(q["disciplina"], 0) + 1
    soma = sum(cont.values())
    if not soma:
        return []
    dist = [(d, max(1, round(total * n / soma))) for d, n in sorted(cont.items(), key=lambda x: -x[1])]
    return dist


def _escolher(pool: list[dict], n: int, acertadas: set, ja: set) -> list[dict]:
    livres = [q for q in pool if (q["prova_id"], q["numero"]) not in ja]
    random.shuffle(livres)
    # primeiro as que você ainda não acertou
    livres.sort(key=lambda q: (q["prova_id"], q["numero"]) in acertadas)
    return livres[:n]


def montar(
    banco,
    ajustes,
    nome: str,
    distribuicao: list[tuple[str, int]],
    filtro: str = "",
    banca: str = "",
    usar_outras: bool = True,
    usar_ia: bool = False,
    assuntos: str = "",
    progresso=None,
) -> dict:
    """Cria a prova do simulado no banco. Devolve um resumo do que foi montado."""

    def passo(f, t):
        if progresso:
            progresso(f, t)

    todas = banco.banco_de_questoes()
    acertadas = banco.acertadas()
    usadas: set = set()
    escolhidas: list[dict] = []
    faltas: dict[str, int] = {}
    da_biblioteca = geradas = 0
    total = sum(n for _, n in distribuicao) or 1
    feito = 0
    for disc, n in distribuicao:
        if n <= 0:
            continue
        passo(feito / total * 0.9, f"Separando {disc}…")
        mesmas = [q for q in todas if q["disciplina"] == disc and combina(q, filtro)]
        grupo = _escolher(mesmas, n, acertadas, usadas)
        if len(grupo) < n and usar_outras and filtro.strip():
            outras = [q for q in todas if q["disciplina"] == disc and not combina(q, filtro)]
            grupo += _escolher(outras, n - len(grupo), acertadas, usadas)
        for q in grupo:
            usadas.add((q["prova_id"], q["numero"]))
            escolhidas.append(
                {
                    "enunciado": q["enunciado"],
                    "texto_base": q.get("texto_base") or "",
                    "alternativas": q["alternativas"],
                    "gabarito": q.get("gabarito"),
                    "explicacao": q.get("explicacao") or "",
                    "disciplina": disc,
                    "tipo": q.get("tipo") or "ME",
                    "fonte": f"{q['prova_titulo']}, questão {q['numero']}",
                    "ref": q.get("ref") or f"{q['prova_id']}:{q['numero']}",
                }
            )
        da_biblioteca += len(grupo)
        falta = n - len(grupo)
        if falta and usar_ia and ajustes is not None and ajustes.chave_claude:
            passo(feito / total * 0.9, f"Criando {falta} questões de {disc} com IA…")
            from . import ia

            try:
                novas = ia.gerar_questoes(
                    disc,
                    falta,
                    ajustes.chave_claude,
                    ajustes["claude_modelo"],
                    banca=banca,
                    concurso=filtro,
                    assuntos=assuntos,
                    exemplos=exemplos_para(todas, disc, filtro, banca),
                )
            except Exception as e:  # noqa: BLE001
                novas = []
                faltas[f"{disc} (IA: {type(e).__name__})"] = falta
                falta = 0
            for q in novas:
                q["fonte"] = f"Criada por IA no estilo {banca or 'de concurso'}"
                escolhidas.append(q)
            geradas += len(novas)
            falta -= len(novas)
        if falta > 0:
            faltas[disc] = falta
        feito += n
    if not escolhidas:
        return {"prova_id": None, "total": 0, "da_biblioteca": 0, "geradas": 0, "faltas": faltas}
    for i, q in enumerate(escolhidas, start=1):
        q["numero"] = i
        q["pagina"] = 0
    passo(0.95, "Salvando o simulado…")
    prova_id = banco.criar_prova(
        titulo=nome or f"Simulado {datetime.now():%d/%m}",
        cargo="",
        orgao=filtro,
        banca=banca,
        ano=str(datetime.now().year),
        origem_url=f"aprova://simulado/{datetime.now():%Y%m%d%H%M%S}",
        modo="questoes",
    )
    banco.salvar_questoes(prova_id, escolhidas)
    passo(1.0, "Pronto")
    return {
        "prova_id": prova_id,
        "total": len(escolhidas),
        "da_biblioteca": da_biblioteca,
        "geradas": geradas,
        "faltas": faltas,
    }
