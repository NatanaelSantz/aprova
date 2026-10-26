"""Monta simulados com o número de questões e a distribuição por disciplina do concurso.

As questões vêm, nesta ordem:
1. das provas da sua biblioteca que combinam com o concurso (órgão, banca ou cargo);
2. das outras provas da biblioteca, se você permitir;
3. de questões novas criadas pela IA no estilo da banca (opcional, precisa da chave do Claude).
"""

from __future__ import annotations

import random
import re
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


class Historico:
    """O que você já fez com cada questão, para o simulado não ficar repetitivo.

    A mesma questão em provas diferentes (ex.: o Português igual para todos os cargos) conta junto,
    pela assinatura do enunciado. Ordem de escolha:
      0. nunca respondida;
      1. respondida e ainda não acertada (a que foi respondida há mais tempo primeiro);
      2. já acertada (também a mais antiga primeiro);
      3. errada e esperando o dia da Revisão: só entra se faltar questão.
    """

    def __init__(self, banco):
        hist = banco.historico_questoes()
        revisao = banco.em_revisao()
        self.por_sig: dict[str, dict] = {}
        self.revisao: set[str] = set()
        if not hist and not revisao:
            return
        for q in banco.banco_de_questoes(unicas=False):
            k = (q["prova_id"], q["numero"])
            sig = q.get("assinatura") or ""
            if k in hist:
                h, atual = hist[k], self.por_sig.get(sig)
                if atual is None:
                    self.por_sig[sig] = dict(h)
                else:
                    atual["acertou"] = atual["acertou"] or h["acertou"]
                    atual["vista"] = max(atual["vista"], h["vista"])
                    atual["vezes"] += h["vezes"]
            if k in revisao:
                self.revisao.add(sig)

    def nivel(self, q: dict) -> tuple[int, str]:
        sig = q.get("assinatura") or ""
        if sig in self.revisao:
            return 3, ""
        h = self.por_sig.get(sig)
        if not h:
            return 0, ""
        return (2 if h["acertou"] else 1), h["vista"]

    def ja_vista(self, q: dict) -> bool:
        return self.nivel(q)[0] > 0


_FIGURA = re.compile(r"\b(observe|veja|analise|considere|conforme|de acordo com)\b[^.?!]{0,40}\b(figura|imagem|gr[aá]fico|charge|tirinha|mapa|ilustra[cç][aã]o)\b", re.I)


def problema(q: dict) -> str:
    """Por que uma questão não serve para o simulado ("" se está boa).

    PDF mal lido gera questão "esquisita": letras separadas, texto cortado, alternativas faltando ou
    repetidas. Essas ficam de fora (a IA pode criar outras no lugar)."""
    enunciado = re.sub(r"\s+", " ", str(q.get("enunciado") or "")).strip()
    if len(enunciado) < 25:
        return "enunciado curto demais"
    if "\ufffd" in enunciado or len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", enunciado)) > 0:
        return "texto com caracteres quebrados"
    palavras = enunciado.split()
    soltas = sum(1 for w in palavras if len(w) == 1 and w.isalpha() and w.lower() not in "aeiouéàóô")
    if len(palavras) >= 8 and soltas / len(palavras) > 0.3:
        return "letras separadas (PDF mal lido)"
    alts = q.get("alternativas") or {}
    if not isinstance(alts, dict):
        return "alternativas inválidas"
    if (q.get("tipo") or "ME") == "CE":
        return ""
    textos = [re.sub(r"\s+", " ", str(v or "")).strip().lower() for v in alts.values()]
    if len(textos) < 3:
        return "faltam alternativas"
    if sum(1 for t in textos if not t) > 0:
        return "alternativa vazia"
    if len(set(textos)) < len(textos):
        return "alternativas repetidas"
    gab = str(q.get("gabarito") or "").strip().upper()
    if gab and gab != "*" and gab not in {str(k).upper() for k in alts}:
        return "gabarito não bate com as alternativas"
    return ""


def _incompleta(q: dict) -> bool:
    """Serve, mas fica para o fim: sem gabarito (não dá para corrigir) ou depende de figura que não veio."""
    return not q.get("gabarito") or bool(_FIGURA.search(str(q.get("enunciado") or "")))


def _escolher(pool: list[dict], n: int, hist: Historico, ja: set) -> list[dict]:
    livres = [q for q in pool if (q["prova_id"], q["numero"]) not in ja and q.get("assinatura") not in ja and not problema(q)]
    random.shuffle(livres)  # empate (ex.: todas nunca vistas) fica na sorte
    livres.sort(key=lambda q: (_incompleta(q), *hist.nivel(q)))
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
    hist = Historico(banco)
    usadas: set = set()
    escolhidas: list[dict] = []
    faltas: dict[str, int] = {}
    repetidas: dict[str, int] = {}
    da_biblioteca = geradas = 0
    total = sum(n for _, n in distribuicao) or 1
    feito = 0
    for disc, n in distribuicao:
        if n <= 0:
            continue
        passo(feito / total * 0.9, f"Separando {disc}…")
        mesmas = [q for q in todas if q["disciplina"] == disc and combina(q, filtro)]
        grupo = _escolher(mesmas, n, hist, usadas)
        if usar_outras and filtro.strip() and (len(grupo) < n or any(hist.ja_vista(q) for q in grupo)):
            # do concurso faltou ou só sobrou repetida: completa (ou troca) com questão nova de outras provas
            outras = [q for q in todas if q["disciplina"] == disc and not combina(q, filtro)]
            candidatas = grupo + _escolher(outras, n, hist, usadas | {q.get("assinatura") for q in grupo})
            candidatas.sort(key=lambda q: hist.nivel(q)[0])  # mantém a ordem dentro de cada nível
            grupo = candidatas[:n]
        falta = n - len(grupo)
        repetidas_aqui = [q for q in grupo if hist.ja_vista(q)]
        novas: list[dict] = []
        pedir = falta + len(repetidas_aqui)
        if pedir and usar_ia and ajustes is not None and ajustes.chave_claude:
            # a IA completa o que faltou e troca as que você já viu por questões novas no estilo da banca
            passo(feito / total * 0.9, f"Criando {pedir} questões novas de {disc} com IA…")
            from . import ia

            try:
                novas = ia.gerar_questoes(
                    disc,
                    pedir,
                    ajustes.chave_claude,
                    ajustes["claude_modelo"],
                    banca=banca,
                    concurso=filtro,
                    assuntos=assuntos,
                    exemplos=exemplos_para(todas, disc, filtro, banca),
                )[:pedir]
            except Exception as e:  # noqa: BLE001
                novas = []
                if falta:
                    faltas[f"{disc} (IA: {type(e).__name__})"] = falta
                    falta = 0
            novas = [q for q in novas if not problema(q)]  # a IA também não passa questão quebrada
            sobra = len(novas) - falta
            if sobra > 0:  # sai primeiro a mais "batida" (o grupo está do menos para o mais visto)
                sair = repetidas_aqui[::-1][:sobra]
                grupo = [q for q in grupo if all(q is not x for x in sair)]
        vistas = sum(1 for q in grupo if hist.ja_vista(q))
        if vistas:
            repetidas[disc] = vistas
        for q in grupo:
            usadas.add((q["prova_id"], q["numero"]))
            usadas.add(q.get("assinatura"))
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
        for q in novas:
            q["fonte"] = f"Criada por IA no estilo {banca or 'de concurso'}"
            q["disciplina"] = disc
            escolhidas.append(q)
        geradas += len(novas)
        falta = n - len(grupo) - len(novas)
        if falta > 0 and not any(k.startswith(f"{disc} (IA:") for k in faltas):
            faltas[disc] = falta
        feito += n
    if not escolhidas:
        return {"prova_id": None, "total": 0, "da_biblioteca": 0, "geradas": 0, "faltas": faltas, "repetidas": repetidas}
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
        "repetidas": repetidas,  # por disciplina: questões que você já tinha visto
    }
