"""Caminhos, ajustes do usuário e constantes do app."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

APP_NOME = "Aprova"

RAIZ = Path(__file__).resolve().parent.parent
ASSETS_DIR = RAIZ / "assets"

DATA_DIR = Path(os.environ.get("APROVA_DATA", Path.home() / ".aprova"))
PROVAS_DIR = DATA_DIR / "provas"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "aprova.db"
AJUSTES_PATH = DATA_DIR / "ajustes.json"

# Quando definido, o app lê páginas do PCI e resultados de busca a partir desta
# pasta em vez da internet (usado nos testes automáticos).
FIXTURES_DIR = os.environ.get("APROVA_FIXTURES")

PADROES = {
    "nome": "",
    "tema": "claro",  # claro | escuro | sepia
    "fonte_escala": 1.0,  # multiplica o tamanho do texto das questões
    "entrelinha": 1.55,
    "voz_velocidade": 0,  # -5 (lenta) a +5 (rápida)
    "pausa_olhos": True,
    "pausa_minutos": 20,
    "regiao": "sudeste",
    "claude_api_key": "",
    "claude_modelo": "claude-haiku-5-5",
    "pasta_downloads": str(Path.home() / "Downloads"),
    "meta_horas_semana": 10,  # horas de estudo por semana
    "dias_planejados": "0,1,2,3,4",  # dias da semana em que você planeja estudar (0 = segunda)
    "cronometro_inicio": 0,  # cronômetro de estudo em andamento (timestamp)
    "cronometro_atividade": "",
    "tempo_migrado": False,
    "metas_desde": "",  # dia em que as metas começaram a contar (dias antes não contam contra você)
}


LOG_PATH = DATA_DIR / "aprova.log"


def registrar(msg: str) -> None:
    """Anota um erro no aprova.log (pasta .aprova) para facilitar o diagnóstico."""
    import datetime

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 300_000:
            LOG_PATH.write_text(LOG_PATH.read_text(encoding="utf-8", errors="ignore")[-100_000:], encoding="utf-8")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def garantir_pastas() -> None:
    for p in (DATA_DIR, PROVAS_DIR, CACHE_DIR):
        p.mkdir(parents=True, exist_ok=True)


class Ajustes:
    """Ajustes persistidos em JSON. Seguro para uso entre threads."""

    def __init__(self, caminho: Path = AJUSTES_PATH):
        self.caminho = caminho
        self._lock = threading.Lock()
        self._dados = dict(PADROES)
        try:
            if caminho.exists():
                self._dados.update(json.loads(caminho.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def __getitem__(self, chave: str):
        return self._dados.get(chave, PADROES.get(chave))

    def get(self, chave: str, padrao=None):
        return self._dados.get(chave, padrao)

    def set(self, chave: str, valor) -> None:
        with self._lock:
            self._dados[chave] = valor
            self._salvar()

    def _salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._dados, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.caminho)

    @property
    def chave_claude(self) -> str:
        return (self._dados.get("claude_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
