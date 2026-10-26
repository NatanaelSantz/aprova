"""Figurinhas do Aprova (desenhos próprios, em assets/figurinhas/<id>.png).

A mensagem guarda só o id; cada app mostra o desenho que tem. Para criar ou mudar, edite
ferramentas/gerar_figurinhas.py e rode o script.
"""

from __future__ import annotations

from pathlib import Path

from . import config

FIGURINHAS: list[tuple[str, str]] = [
    ("bora-estudar", "Bora estudar!"),
    ("passei", "Passei!"),
    ("gabaritei", "Gabaritei"),
    ("foco-total", "Foco total"),
    ("cafe-lei-seca", "Café + lei seca"),
    ("revisao-em-dia", "Revisão em dia"),
    ("simulado-hoje", "Simulado hoje?"),
    ("valeu", "Valeu!"),
    ("kkkk", "kkkkk"),
    ("socorro-rlm", "Socorro, RLM"),
    ("forca", "Força!"),
    ("aprovado", "Aprovado"),
]
LEGENDAS = dict(FIGURINHAS)


def caminho(ident: str) -> Path | None:
    """Arquivo da figurinha (None se este app não conhece; ex.: figurinha nova de uma versão mais nova)."""
    if ident not in LEGENDAS:
        return None
    p = config.ASSETS_DIR / "figurinhas" / f"{ident}.png"
    return p if p.exists() else None
