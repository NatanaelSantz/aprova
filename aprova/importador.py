"""Importa PDFs de prova/gabarito para o banco local."""

from __future__ import annotations

import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import config, pdfprova
from .pci import slugify


def parece_gabarito(pdf: Path) -> bool:
    nome = pdf.name.lower()
    if "gab" in nome or "resposta" in nome:
        return True
    try:
        if pdfprova.contar_paginas(pdf) > 4:
            return False
        return len(pdfprova.ler_gabarito_pdf(pdf)) >= 10 and not pdfprova.extrair_questoes(pdf).aproveitavel
    except Exception:
        return False


def separar_arquivos(pdfs: list[Path]) -> tuple[Path | None, Path | None]:
    """De uma lista de PDFs, escolhe (prova, gabarito)."""
    prova = gab = None
    for p in pdfs:
        if gab is None and parece_gabarito(p):
            gab = p
        elif prova is None:
            prova = p
    if prova is None and gab is not None and len(pdfs) == 1:
        prova, gab = gab, None
    return prova, gab


def importar(
    banco,
    ajustes,
    pdf_prova: Path,
    pdf_gabarito: Path | None = None,
    meta: dict | None = None,
    usar_ia: bool = False,
    progresso=None,
) -> dict:
    meta = dict(meta or {})
    titulo = meta.get("titulo") or re.sub(r"[-_]+", " ", pdf_prova.stem).strip().capitalize()
    pasta = config.PROVAS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(titulo)[:40] or 'prova'}"
    pasta.mkdir(parents=True, exist_ok=True)
    destino_prova = pasta / ("prova.pdf")
    shutil.copy2(pdf_prova, destino_prova)
    destino_gab = None
    if pdf_gabarito:
        destino_gab = pasta / "gabarito.pdf"
        shutil.copy2(pdf_gabarito, destino_gab)

    def passo(frac: float, texto: str):
        if progresso:
            progresso(frac, texto)

    passo(0.1, "Lendo o texto da prova…")
    paginas = pdfprova.contar_paginas(destino_prova)
    resultado = pdfprova.extrair_questoes(destino_prova)
    aviso = None
    questoes = [q.__dict__.copy() for q in resultado.questoes]
    via = "leitura"
    if not resultado.tem_texto:
        aviso = "Este PDF é uma imagem digitalizada: não dá para ler o texto. Use o cartão-resposta ao lado das páginas."
        questoes = []
    elif not resultado.aproveitavel and usar_ia and ajustes.chave_claude:
        passo(0.3, "Pedindo ao Claude para organizar as questões…")
        from . import ia

        try:
            questoes = ia.extrair_questoes(
                pdfprova.ler_paginas(destino_prova),
                ajustes.chave_claude,
                ajustes["claude_modelo"],
                progresso=lambda f: passo(0.3 + 0.5 * f, "Organizando as questões…"),
            )
            via = "claude"
        except Exception as e:  # noqa: BLE001
            aviso = f"O Claude não conseguiu ler a prova ({type(e).__name__}). Ficou a leitura automática."
    if questoes and via == "leitura" and not resultado.aproveitavel:
        aviso = (
            "A leitura automática ficou incompleta nesta prova. Você pode fazer a prova pelo "
            "cartão-resposta, olhando as páginas originais."
        )
    n = len(questoes)

    passo(0.85, "Procurando o gabarito…")
    gabarito: dict[int, str] = {}
    if destino_gab:
        gabarito = pdfprova.ler_gabarito_pdf(destino_gab, n or None, meta.get("cargo", ""), meta.get("caderno", ""))
    if questoes:
        for q in questoes:
            q["gabarito"] = gabarito.get(q["numero"])
    modo = "questoes" if questoes and (resultado.aproveitavel or via == "claude") else "cartao"
    prova_id = banco.criar_prova(
        titulo=titulo,
        cargo=meta.get("cargo", ""),
        orgao=meta.get("orgao", ""),
        banca=meta.get("banca", ""),
        ano=meta.get("ano", ""),
        origem_url=meta.get("origem_url", ""),
        pdf_prova=str(destino_prova),
        pdf_gabarito=str(destino_gab or ""),
        paginas=paginas,
        modo=modo,
    )
    if questoes:
        banco.salvar_questoes(prova_id, questoes)
    elif gabarito:
        banco.definir_gabarito(prova_id, gabarito)
    passo(1.0, "Pronto")
    return {
        "prova_id": prova_id,
        "n_questoes": n or len(gabarito),
        "n_gabarito": len(gabarito),
        "modo": modo,
        "aviso": aviso,
        "via": via,
    }


def procurar_baixados(nomes: list[str], pasta: Path, desde: float) -> list[Path]:
    """Procura na pasta de downloads os PDFs com esses nomes (inclui 'arquivo (1).pdf')."""
    achados: list[Path] = []
    if not pasta.exists():
        return achados
    bases = {Path(n).stem.lower(): n for n in nomes}
    for p in sorted(pasta.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            if p.stat().st_mtime < desde - 120:
                continue
        except OSError:
            continue
        stem = re.sub(r"\s*\(\d+\)$", "", p.stem).lower()
        if stem in bases and all(a.name != p.name for a in achados):
            achados.append(p)
    return achados


def aguardar_estavel(p: Path, segundos: float = 1.0) -> bool:
    """True quando o arquivo parou de crescer (download terminou)."""
    try:
        t1 = p.stat().st_size
        time.sleep(segundos)
        return t1 > 0 and p.stat().st_size == t1
    except OSError:
        return False
