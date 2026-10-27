"""Confere se o Aprova ainda consegue ler os sites de onde vêm os concursos e as provas.

O Aprova lê páginas do PCI Concursos e da FGV Conhecimento. Se um desses sites mudar o jeito
da página, a aba Concursos (ou a busca de provas) para de funcionar para todo mundo, sem aviso.
Este script abre os sites de verdade e falha (código 1) se algo não vier como o app espera.

O robô .github/workflows/sites.yml roda isto todo dia: quando falha, o GitHub manda um e-mail
para o dono do repositório, e dá para consertar antes que os usuários percebam.

Uso:  python ferramentas/conferir_sites.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# cache numa pasta temporária: a conferência sempre lê a página de agora
os.environ.setdefault("APROVA_DATA", tempfile.mkdtemp(prefix="aprova-sites-"))

from aprova.fontes import Centralizador  # noqa: E402
from aprova.pci import ClientePCI  # noqa: E402

problemas: list[str] = []


def conferir(nome: str, ok: bool, detalhe: str = "") -> bool:
    print(f"{'ok   ' if ok else 'FALHOU'} {nome}{(': ' + detalhe) if detalhe else ''}")
    if not ok:
        problemas.append(nome)
    return ok


def main() -> int:
    from aprova import config

    cli = ClientePCI(cache_dir=config.CACHE_DIR, fixtures=config.FIXTURES_DIR)

    # 1. aba Concursos: lista de inscrições abertas
    try:
        abertos = cli.concursos_abertos("sudeste")
    except Exception as e:  # noqa: BLE001
        abertos = []
        conferir("PCI: concursos abertos", False, f"{type(e).__name__}: {e}")
    else:
        completos = [c for c in abertos if c.nome and c.url]
        com_prazo = [c for c in abertos if c.prazo_fim]
        if conferir("PCI: concursos abertos", len(abertos) >= 5, f"{len(abertos)} concursos"):
            conferir("PCI: nome e link de cada concurso", len(completos) >= 0.8 * len(abertos), f"{len(completos)} de {len(abertos)}")
            conferir("PCI: prazo de inscrição", len(com_prazo) >= 0.5 * len(abertos), f"{len(com_prazo)} de {len(abertos)} com prazo")

    # 2. página de um concurso (edital)
    if abertos:
        try:
            ed = cli.edital(abertos[0].url)
            conferir("PCI: página do concurso", bool(ed.titulo), ed.titulo[:70])
        except Exception as e:  # noqa: BLE001
            conferir("PCI: página do concurso", False, f"{type(e).__name__}: {e}")

    # 3. aba Provas: busca e arquivos de uma prova
    try:
        itens, _, slug = cli.buscar_provas("escrevente")
    except Exception as e:  # noqa: BLE001
        itens = []
        conferir("PCI: busca de provas", False, f"{type(e).__name__}: {e}")
    else:
        conferir("PCI: busca de provas", len(itens) >= 1, f"{len(itens)} provas ({slug})")
    if itens:
        try:
            arquivos, _ = cli.arquivos_prova(itens[0].url)
            conferir("PCI: arquivos da prova", len(arquivos) >= 1, f"{len(arquivos)} arquivos em {itens[0].cargo[:50]}")
        except Exception as e:  # noqa: BLE001
            conferir("PCI: arquivos da prova", False, f"{type(e).__name__}: {e}")

    # 4. site oficial da FGV (aba Nas bancas e busca central)
    try:
        fgv = Centralizador(cli).concursos_fgv(paginas=1)
        conferir("FGV: lista de concursos", len(fgv) >= 1, f"{len(fgv)} concursos")
    except Exception as e:  # noqa: BLE001
        conferir("FGV: lista de concursos", False, f"{type(e).__name__}: {e}")

    if problemas:
        print(f"\n{len(problemas)} problema(s). Algum site mudou: confira o aprova/pci.py ou o aprova/fontes.py.")
        return 1
    print("\nTudo certo: os sites continuam do jeito que o Aprova lê.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
