"""Enche a biblioteca com as provas de um concurso.

Junta, numa lista só, as provas de todas as edições e cargos encontrados
(site oficial da banca, outras páginas de banca achadas na internet e,
se você quiser, PDFs soltos de outros sites). Depois baixa e importa
uma por uma, com o gabarito oficial de cada cargo.

De cada cargo entra só um caderno: os outros tipos (2, 3, 4) têm as mesmas
questões em outra ordem.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, fontes, importador
from .db import assinatura
from .pci import ErroRede

MENORES = {"de", "da", "do", "das", "dos", "e", "em", "para", "a", "o", "na", "no"}


def bonito(texto: str) -> str:
    """'DESENVOLVIMENTO DE SOFTWARE' -> 'Desenvolvimento de Software'."""
    if not texto or not texto.isupper():
        return texto
    return " ".join(w if w in MENORES else w.capitalize() for w in texto.lower().split())


def ano_de(*textos: str) -> str:
    for t in textos:
        m = re.search(r"\b(20\d\d)\b", t or "")
        if m:
            return m.group(1)
    for t in textos:  # slug do tipo dataprev26
        m = re.search(r"[a-z](\d\d)/?$", (t or "").lower())
        if m and 10 <= int(m.group(1)) <= 40:
            return "20" + m.group(1)
    return ""


def nome_curto(nome: str) -> str:
    """'Concurso Público para a Empresa ... - DATAPREV' -> 'Dataprev'."""
    partes = re.split(r"\s+[-–]\s+", nome or "")
    curto = partes[-1] if len(partes) > 1 else partes[0]
    curto = re.sub(r"(?i)^(concurso|processo seletivo)(\s+p[úu]blico)?(\s+nacional)?(\s+unificado)?(\s+(para|do|da|de))?(\s+(o|a))?\s+", "", curto)
    curto = re.sub(r"\s*\b20\d\d\b\s*", " ", curto).strip(" -–")
    if re.fullmatch(r"\d*", curto):
        curto = re.sub(r"\s*\b20\d\d\b\s*", " ", nome or "").strip()
    if curto.isupper() and len(curto) > 4:
        curto = curto.title()
    return curto or nome


@dataclass
class Item:
    prova: fontes.Achado
    gabarito: fontes.Achado | None
    edicao: str  # "Dataprev 2026"
    banca: str
    ano: str
    cargo: str
    oficial: bool = True
    ja_tem: bool = False
    marcado: bool = True

    @property
    def chave(self) -> str:
        return self.prova.url


@dataclass
class Plano:
    termo: str
    itens: list[Item] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def edicoes(self) -> list[str]:
        vistas: list[str] = []
        for it in self.itens:
            if it.edicao not in vistas:
                vistas.append(it.edicao)
        return vistas


def planejar(central: fontes.Centralizador, banco, termo: str, resultado: fontes.Resultado | None = None, progresso=None) -> Plano:
    """Monta a lista de provas para baixar: todas as edições e cargos que der para achar."""

    def passo(f, t):
        if progresso:
            progresso(f, t)

    termo = termo.strip()
    plano = Plano(termo=termo)
    if resultado is None:
        resultado = central.buscar(termo, lambda f, t: passo(f * 0.6, t), incluir_pci=False)
    plano.avisos += resultado.avisos
    achados = list(resultado.oficiais)
    paginas: dict[str, tuple[str, str, str]] = {}  # url -> (edição, banca, ano)
    for p in resultado.paginas_oficiais:
        ano = ano_de(p.nome, p.url)
        paginas[p.url] = (f"{nome_curto(p.nome)} {ano}".strip(), p.banca, ano)

    # edições anteriores no site oficial
    if not termo.startswith("http"):
        passo(0.65, "Procurando edições anteriores…")
        try:
            edicoes = central.edicoes(termo)
        except ErroRede as e:
            edicoes = []
            plano.avisos.append(f"Edições anteriores: {e}")
        for i, c in enumerate(edicoes):
            if c.url in paginas:
                continue
            ano = ano_de(c.nome, c.url)
            paginas[c.url] = (f"{nome_curto(c.nome)} {ano}".strip(), c.banca, ano)
            passo(0.65 + 0.3 * (i + 1) / max(len(edicoes), 1), f"Lendo {paginas[c.url][0]}…")
            try:
                achados += central.arquivos_da_pagina(c.url, c.banca or "FGV")
            except ErroRede as e:
                plano.avisos.append(f"{paginas[c.url][0]}: {e}")

    unicos: dict[str, fontes.Achado] = {}
    for a in achados:
        unicos.setdefault(a.url, a)
    for g in fontes.agrupar_por_cargo([a for a in unicos.values() if a.oficial]):
        edicao, banca, ano = paginas.get(g["pagina"], ("", "", ""))
        a = g["cadernos"][0]
        if not edicao:
            ano = ano_de(a.titulo, a.url, termo)
            edicao = f"{nome_curto(termo)} {ano}".strip() if not termo.startswith("http") else (ano or "Página colada")
            banca = a.fonte.replace(" (site oficial)", "")
        plano.itens.append(
            Item(
                prova=a,
                gabarito=g["gabarito"],
                edicao=edicao,
                banca=banca,
                ano=ano,
                cargo=bonito(g["cargo"]),
                ja_tem=any(banco.prova_por_origem(x.url) for x in g["cadernos"]),
            )
        )
    # PDFs de outros sites (sem gabarito garantido): entram desmarcados
    for a in resultado.web:
        if a.tipo != "prova":
            continue
        ano = ano_de(a.titulo, a.url, termo)
        plano.itens.append(
            Item(
                prova=a,
                gabarito=None,
                edicao="Outros sites",
                banca="",
                ano=ano,
                cargo=a.titulo,
                oficial=False,
                ja_tem=banco.prova_por_origem(a.url) is not None,
                marcado=False,
            )
        )
    for it in plano.itens:
        if it.ja_tem:
            it.marcado = False
    # mais recentes primeiro; dentro da edição, por cargo
    ordem_ed = {e: i for i, e in enumerate(sorted({i.edicao for i in plano.itens if i.oficial}, key=lambda e: ano_de(e), reverse=True))}
    plano.itens.sort(key=lambda i: (not i.oficial, ordem_ed.get(i.edicao, 99), i.cargo))
    passo(1, "Pronto")
    return plano


@dataclass
class Relatorio:
    provas: int = 0
    questoes: int = 0
    novas: int = 0
    repetidas: int = 0
    com_gabarito: int = 0
    cartao: int = 0
    falhas: list[str] = field(default_factory=list)
    prova_ids: list[int] = field(default_factory=list)
    interrompido: bool = False


def _nome_arquivo(url: str, padrao: str) -> str:
    nome = Path(url.split("?")[0]).name or padrao
    return nome if nome.lower().endswith(".pdf") else nome + ".pdf"


def coletar(banco, ajustes, pci, plano: Plano, itens: list[Item], progresso=None, parar=lambda: False) -> Relatorio:
    """Baixa e importa os itens escolhidos. `parar()` interrompe entre uma prova e outra."""
    rel = Relatorio()
    pasta = config.CACHE_DIR / "downloads" / f"lote-{int(time.time())}"
    gabaritos: dict[str, Path | None] = {}
    conhecidas = {assinatura(q) for q in banco.banco_de_questoes(unicas=False)}
    total = len(itens) or 1
    for n, it in enumerate(itens):
        if parar():
            rel.interrompido = True
            break

        def passo(f, texto, n=n, it=it):
            if progresso:
                progresso((n + f) / total, f"{n + 1} de {len(itens)} · {it.cargo} ({it.edicao}) · {texto}")

        try:
            passo(0.05, "baixando a prova…")
            pdf = pci.baixar(it.prova.url, pasta / f"{n:03d}-{_nome_arquivo(it.prova.url, 'prova.pdf')}")
            gab = None
            if it.gabarito:
                if it.gabarito.url not in gabaritos:
                    passo(0.2, "baixando o gabarito…")
                    nome = _nome_arquivo(it.gabarito.url, "gabarito.pdf")
                    if "gab" not in nome.lower():
                        nome = "gabarito-" + nome
                    try:
                        gabaritos[it.gabarito.url] = pci.baixar(it.gabarito.url, pasta / f"g{len(gabaritos):02d}-{nome}")
                    except ErroRede:
                        gabaritos[it.gabarito.url] = None
                gab = gabaritos[it.gabarito.url]
            meta = {
                "titulo": f"{it.cargo} — {it.edicao}" if it.oficial else it.cargo,
                "cargo": it.prova.cargo or it.cargo,
                "caderno": it.prova.caderno,
                "orgao": it.edicao if it.oficial else plano.termo,
                "banca": it.banca,
                "ano": it.ano,
                "origem_url": it.prova.url,
            }
            res = importador.importar(banco, ajustes, pdf, gab, meta, usar_ia=False, progresso=lambda f, t: passo(0.3 + 0.65 * f, t.lower()))
        except ErroRede as e:
            rel.falhas.append(f"{it.cargo} ({it.edicao}): {e}")
            continue
        except Exception as e:  # noqa: BLE001 - um PDF estranho não pode derrubar o lote
            config.registrar(f"coleta: falhou {it.prova.url}: {type(e).__name__}: {e}")
            rel.falhas.append(f"{it.cargo} ({it.edicao}): não consegui ler o PDF")
            continue
        rel.provas += 1
        rel.prova_ids.append(res["prova_id"])
        if res["modo"] == "cartao":
            rel.cartao += 1
        for q in banco.questoes(res["prova_id"]):
            if not q.get("enunciado"):
                continue
            rel.questoes += 1
            rel.com_gabarito += bool(q.get("gabarito"))
            sig = assinatura(q)
            if sig in conhecidas:
                rel.repetidas += 1
            else:
                conhecidas.add(sig)
                rel.novas += 1
    if progresso:
        progresso(1, "Pronto")
    return rel
