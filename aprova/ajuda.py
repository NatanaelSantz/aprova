"""Ajuda por questão: sempre pesquisa na internet e monta uma dica.

Sem chave da API do Claude, a dica combina a estratégia da disciplina com os
trechos mais relevantes encontrados na busca. Com a chave, o Claude lê a questão,
pesquisa e escreve uma explicação com as fontes.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from . import config, disciplinas

PARADAS = set(
    """a o os as um uma uns umas de da do das dos em no na nos nas por pelo pela pelos pelas para com sem
    sob sobre entre que qual quais quando como onde se ao aos à às e ou mas nem é são foi ser estar está
    estão seu sua seus suas este esta estes estas esse essa isso isto aquele aquela assinale alternativa
    alternativas correta corretamente incorreta afirmar afirmativa afirmativas texto acordo segundo
    considere seguinte seguintes item itens julgue questão questões opção abaixo acima respeito assim
    mais menos muito pode podem deve devem também ainda já não sim""".split()
)


def palavras_chave(texto: str, limite: int = 10) -> list[str]:
    vistos: list[str] = []
    for tok in re.findall(r"[\wÀ-ú$%º°-]+", texto):
        t = tok.strip("-").lower()
        if len(t) < 4 and not re.fullmatch(r"\d+%?|art|cf|lei|ctrl", t):
            continue
        if t in PARADAS or t in vistos:
            continue
        vistos.append(t)
        if len(vistos) >= limite:
            break
    return vistos


def montar_consulta(questao: dict) -> str:
    chaves = palavras_chave(questao.get("enunciado", ""), 9)
    if len(chaves) < 4:
        alts = " ".join((questao.get("alternativas") or {}).values())
        chaves += [k for k in palavras_chave(alts, 6) if k not in chaves]
    disc = questao.get("disciplina") or ""
    if disc and disc not in ("Geral", "Conhecimentos Específicos"):
        chaves.append(disc.lower())
    return " ".join(chaves[:12]) + " concurso"


def chave_cache(questao: dict, modo: str) -> str:
    base = json.dumps([questao.get("enunciado"), questao.get("alternativas"), modo], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(base.encode()).hexdigest()


# Buscadores usados pela biblioteca ddgs. Primeiro tenta alguns em paralelo;
# se nenhum responder, tenta um por vez (cada um pode estar bloqueando naquele momento).
BUSCADORES = ("duckduckgo", "brave", "mojeek", "bing", "yahoo", "google", "startpage", "yandex")


class BuscaIndisponivel(Exception):
    """Nenhum buscador respondeu."""


def _normalizar(brutos) -> list[dict]:
    saida, vistos = [], set()
    for r in brutos or []:
        url = r.get("href") or r.get("url") or ""
        if not url or url in vistos:
            continue
        vistos.add(url)
        saida.append({"titulo": (r.get("title") or url).strip(), "url": url, "trecho": (r.get("body") or "").strip()})
    return saida


def pesquisar_web(consulta: str, max_resultados: int = 6, enciclopedia: bool = True, limite_s: float = 30) -> list[dict]:
    """Busca na web. Devolve [{'titulo','url','trecho'}].

    Lista vazia = os buscadores responderam, mas sem resultados.
    BuscaIndisponivel = nenhum buscador respondeu (sem internet ou bloqueio).
    """
    if config.FIXTURES_DIR:
        from .pci import slugify

        especifico = Path(config.FIXTURES_DIR) / f"busca-{slugify(consulta)}.json"
        p = especifico if especifico.exists() else Path(config.FIXTURES_DIR) / "busca.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))[:max_resultados]
    import time

    from ddgs import DDGS

    inicio = time.monotonic()
    primeiros = list(BUSCADORES[:4])
    random.shuffle(primeiros)
    tentativas = [",".join(primeiros)] + list(BUSCADORES) + (["wikipedia"] if enciclopedia else [])
    erros: list[str] = []
    respondeu = False
    for backend in tentativas:
        if time.monotonic() - inicio > limite_s and (respondeu or erros):
            break
        try:
            brutos = DDGS(timeout=8).text(
                consulta, region="br-pt", safesearch="moderate", max_results=max_resultados, backend=backend
            )
        except Exception as e:  # noqa: BLE001 - cada buscador falha de um jeito
            msg = str(e)
            if "no results" in msg.lower():
                respondeu = True
            else:
                erros.append(f"{backend}: {type(e).__name__}: {msg[:160]}")
            continue
        resultados = _normalizar(brutos)
        if resultados:
            return resultados[:max_resultados]
        respondeu = True
    if erros:
        config.registrar(f"busca '{consulta}' sem resposta: " + " | ".join(erros))
    if respondeu:
        return []
    raise BuscaIndisponivel(erros[0] if erros else "sem resposta")


def _frases(texto: str) -> list[str]:
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if len(f.strip()) > 40]


def dica_local(questao: dict, resultados: list[dict]) -> str:
    disc = questao.get("disciplina") or "Geral"
    estrategia = disciplinas.DICAS_POR_DISCIPLINA.get(disc, disciplinas.DICAS_POR_DISCIPLINA["Geral"])
    chaves = set(palavras_chave(questao.get("enunciado", "") + " " + " ".join((questao.get("alternativas") or {}).values()), 25))
    melhores: list[tuple[int, str, str]] = []
    for r in resultados:
        for f in _frases(r.get("trecho", "")):
            pts = len(chaves & set(palavras_chave(f, 40)))
            if pts:
                melhores.append((pts, f, r.get("titulo", "")))
    melhores.sort(key=lambda x: x[0], reverse=True)
    partes = [f"**Como pensar:** {estrategia}"]
    usados = set()
    trechos = []
    for _, f, fonte in melhores:
        if f in usados:
            continue
        usados.add(f)
        trechos.append(f"- {f} _({fonte})_")
        if len(trechos) == 3:
            break
    if trechos:
        partes.append("**O que as fontes dizem sobre o tema:**\n" + "\n".join(trechos))
    return "\n\n".join(partes)


def obter_ajuda(questao: dict, modo: str, ajustes, banco=None, resposta_usuario: str | None = None) -> dict:
    """modo: 'dica' (não revela a resposta) ou 'explicacao' (pode revelar).

    Devolve {'texto': markdown, 'fontes': [{'titulo','url'}], 'consulta': str,
             'via': 'claude'|'busca', 'aviso': str|None}
    """
    chave = chave_cache(questao, modo)
    if banco is not None and modo == "dica":
        salvo = banco.ajuda_salva(chave)
        if salvo:
            return salvo
    consulta = montar_consulta(questao)
    aviso = None
    try:
        resultados = pesquisar_web(consulta)
    except Exception as e:  # sem internet, bloqueio do buscador etc.
        resultados = []
        config.registrar(f"ajuda: busca falhou: {type(e).__name__}: {e}")
        aviso = "Os buscadores não responderam agora. Confira a internet e tente de novo em alguns minutos."
    fontes = [{"titulo": r["titulo"], "url": r["url"]} for r in resultados]
    api_key = ajustes.chave_claude if ajustes is not None else ""
    if api_key:
        try:
            from . import ia

            texto, fontes_ia = ia.explicar(
                questao,
                resultados,
                modo=modo,
                api_key=api_key,
                modelo=ajustes["claude_modelo"],
                resposta_usuario=resposta_usuario,
            )
            vistos = {f["url"] for f in fontes_ia}
            todas = fontes_ia + [f for f in fontes if f["url"] not in vistos]
            dados = {"texto": texto, "fontes": todas[:8], "consulta": consulta, "via": "claude", "aviso": aviso}
            if banco is not None and modo == "dica":
                banco.salvar_ajuda(chave, dados)
            return dados
        except Exception as e:
            aviso = f"O Claude não respondeu ({type(e).__name__}: {str(e)[:120]}). Mostrando a dica da busca."
    texto = dica_local(questao, resultados)
    if modo == "explicacao" and questao.get("explicacao"):
        texto = f"**Explicação:** {questao['explicacao']}\n\n" + texto
    dados = {"texto": texto, "fontes": fontes, "consulta": consulta, "via": "busca", "aviso": aviso}
    if banco is not None and modo == "dica" and resultados:
        banco.salvar_ajuda(chave, dados)
    return dados


def tirar_duvida(questao: dict, pergunta: str, historico: list[dict], ajustes) -> dict:
    """Pergunta livre sobre a questão. Sempre pesquisa na internet.

    Devolve {'texto', 'fontes', 'via', 'aviso'}.
    """
    chaves = palavras_chave(questao.get("enunciado", ""), 5)
    consulta = f"{pergunta} {' '.join(chaves)}".strip()[:200]
    aviso = None
    try:
        resultados = pesquisar_web(consulta)
    except Exception as e:  # noqa: BLE001
        resultados = []
        config.registrar(f"dúvida: busca falhou: {type(e).__name__}: {e}")
        aviso = "Os buscadores não responderam agora."
    fontes = [{"titulo": r["titulo"], "url": r["url"]} for r in resultados]
    api_key = ajustes.chave_claude if ajustes is not None else ""
    if api_key:
        try:
            from . import ia

            texto, fontes_ia = ia.responder_duvida(questao, pergunta, historico, api_key, ajustes["claude_modelo"], resultados)
            vistos = {f["url"] for f in fontes_ia}
            return {"texto": texto, "fontes": (fontes_ia + [f for f in fontes if f["url"] not in vistos])[:8], "via": "claude", "aviso": aviso}
        except Exception as e:  # noqa: BLE001
            aviso = f"O Claude não respondeu ({type(e).__name__}). Mostrando o que achei na internet."
    termos = set(palavras_chave(pergunta + " " + questao.get("enunciado", ""), 25))
    trechos: list[tuple[int, str, str]] = []
    for r in resultados:
        for f in _frases(r.get("trecho", "")):
            pts = len(termos & set(palavras_chave(f, 40)))
            if pts:
                trechos.append((pts, f, r.get("titulo", "")))
    trechos.sort(key=lambda x: x[0], reverse=True)
    if trechos:
        linhas = []
        for _, f, fonte in trechos:
            if all(f not in x for x in linhas):
                linhas.append(f"- {f} _({fonte})_")
            if len(linhas) == 4:
                break
        texto = "**O que encontrei sobre a sua dúvida:**\n" + "\n".join(linhas)
    elif resultados:
        texto = "Não achei um trecho que responda direto. Veja as páginas abaixo, elas tratam do assunto."
    else:
        texto = "Não consegui pesquisar agora. Tente de novo em alguns minutos."
    if not api_key:
        texto += "\n\n_Com a chave do Claude em Ajustes, a resposta vem explicada para a sua pergunta._"
    return {"texto": texto, "fontes": fontes[:6], "via": "busca", "aviso": aviso}
