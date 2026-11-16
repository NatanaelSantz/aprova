"""Destaque do site: um aviso caprichado dentro do app (por exemplo, vídeo novo mostrando as funções novas).

Vem no versao.json do site, no campo "destaque". Assim dá para avisar todo mundo sem lançar versão nova:

    "destaque": {
      "id": "video-novidades-1-33",
      "titulo": "Tem vídeo novo no Aprova!",
      "texto": "Em 2 minutos e meio: as funções novas e os atalhos que você já tem.",
      "fala": "Saiu vídeo novo! Bora ver?",
      "itens": ["Edital verticalizado", "Simulado da turma", "Conquistas"],
      "botao": "Assistir o vídeo",
      "link": "https://natanaelsantz.github.io/aprova/?video=novidades#videos",
      "ate": "2026-12-31"
    }

O app mostra a janela uma vez e deixa um cartão no Início até a pessoa assistir ou fechar.
Para avisar de novo, basta trocar o "id". Só abre links do site do Aprova.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date

from . import atualizar

SITE = "https://natanaelsantz.github.io/aprova/"
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,59}")


def _limpo(valor, limite: int) -> str:
    return " ".join(str(valor or "").split())[:limite]


def ler(d, hoje: date | None = None) -> dict | None:
    """Confere o destaque que veio do site. Devolve None se faltar algo, se o link não for do site ou se já venceu."""
    if not isinstance(d, dict):
        return None
    ident = str(d.get("id") or "")
    link = str(d.get("link") or "")
    titulo = _limpo(d.get("titulo"), 80)
    if not _ID.fullmatch(ident) or not titulo or not link.startswith(SITE) or any(ch in link for ch in ' "<>\\'):
        return None
    ate = str(d.get("ate") or "")
    if ate:
        try:
            if date.fromisoformat(ate) < (hoje or date.today()):
                return None
        except ValueError:
            return None
    itens = d.get("itens") if isinstance(d.get("itens"), list) else []
    return {
        "id": ident,
        "titulo": titulo,
        "texto": _limpo(d.get("texto"), 240),
        "fala": _limpo(d.get("fala"), 60),
        "itens": [x for x in (_limpo(i, 40) for i in itens) if x][:6],
        "botao": _limpo(d.get("botao"), 30) or "Ver agora",
        "link": link,
        **({"ate": ate} if ate else {}),
    }


def buscar(url: str = atualizar.URL_VERSAO, timeout: float = 8) -> dict | None:
    """Lê o destaque do versao.json do site (um arquivinho de 1 KB). Lança erro se não der para consultar."""
    dados = json.loads(atualizar._baixar(url + f"?t={int(time.time() // 600)}", timeout, limite=64 * 1024).decode("utf-8"))
    return ler(dados.get("destaque")) if isinstance(dados, dict) else None
