"""Caminhos, ajustes do usuário e constantes do app."""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
from pathlib import Path

from . import plataforma

APP_NOME = "Aprova"

RAIZ = Path(__file__).resolve().parent.parent
ASSETS_DIR = RAIZ / "assets"

# no celular, a pasta privada do app (o Flet dá o caminho); no computador, a pasta .aprova do usuário
DATA_DIR = Path(os.environ.get("APROVA_DATA") or plataforma.pasta_dados() or Path.home() / ".aprova")
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
    "pasta_downloads": str(plataforma.pasta_downloads_padrao()),
    "meta_horas_semana": 10,  # horas de estudo por semana
    "dias_planejados": "0,1,2,3,4",  # dias da semana em que você planeja estudar (0 = segunda)
    "cronometro_inicio": 0,  # cronômetro de estudo em andamento (timestamp)
    "cronometro_atividade": "",
    "tempo_migrado": False,
    "metas_desde": "",  # dia em que as metas começaram a contar (dias antes não contam contra você)
    "grupo_atual": "",  # último grupo aberto na tela Grupos
    "forum_vistos": {},  # grupo -> data da última mensagem vista (para contar as novas)
    "plano_ativo": {},  # plano de estudo de um grupo que a pessoa está usando
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


# ---------------------------------------------------------------- segredos no ajustes.json
# A chave da API e o login guardado não ficam em texto puro: no Windows são cifrados com a proteção
# de dados do próprio Windows (DPAPI), presa à conta do usuário naquele computador. Copiado para outro
# computador (ou outra conta), o segredo não abre: é só digitar a chave / entrar de novo.
SEGREDOS = {"claude_api_key", "ranking_refresh"}
PREFIXO_CIFRADO = "dpapi:"


def _dpapi(dados: bytes, cifrar: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(dados, len(dados))
    entrada = Blob(len(dados), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    saida = Blob()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    funcao = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
    sem_janela = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if not funcao(ctypes.byref(entrada), None, None, None, None, sem_janela, ctypes.byref(saida)):
        raise OSError("DPAPI recusou")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(saida.pbData, ctypes.c_void_p))  # type: ignore[attr-defined]


def proteger(texto: str) -> str:
    """Cifra um segredo para guardar no ajustes.json (no Windows). Fora do Windows, fica como está."""
    if not texto or not isinstance(texto, str) or texto.startswith(PREFIXO_CIFRADO) or sys.platform != "win32":
        return texto
    try:
        return PREFIXO_CIFRADO + base64.b64encode(_dpapi(texto.encode("utf-8"), True)).decode("ascii")
    except Exception as e:  # noqa: BLE001 - sem a proteção, guarda como antes
        registrar(f"segredo: não cifrou ({type(e).__name__}: {e})")
        return texto


def revelar(valor) -> str:
    """Volta um segredo guardado para o texto. Cifrado em outro computador ou conta: vazio (pede de novo)."""
    if not isinstance(valor, str) or not valor.startswith(PREFIXO_CIFRADO):
        return valor
    if sys.platform != "win32":
        return ""
    try:
        return _dpapi(base64.b64decode(valor[len(PREFIXO_CIFRADO):]), False).decode("utf-8")
    except Exception as e:  # noqa: BLE001
        registrar(f"segredo: não abriu ({type(e).__name__}), vai pedir de novo")
        return ""


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
        # segredos guardados em texto puro (versões antigas): cifra agora
        if sys.platform == "win32" and any(
            isinstance(self._dados.get(k), str) and self._dados.get(k) and not self._dados[k].startswith(PREFIXO_CIFRADO) for k in SEGREDOS
        ):
            with self._lock:
                for k in SEGREDOS:
                    if isinstance(self._dados.get(k), str):
                        self._dados[k] = proteger(self._dados[k])
                try:
                    self._salvar()
                except OSError:
                    pass

    def __getitem__(self, chave: str):
        valor = self._dados.get(chave, PADROES.get(chave))
        return revelar(valor) if chave in SEGREDOS else valor

    def get(self, chave: str, padrao=None):
        valor = self._dados.get(chave, padrao)
        return revelar(valor) if chave in SEGREDOS else valor

    def set(self, chave: str, valor) -> None:
        if chave in SEGREDOS and isinstance(valor, str):
            valor = proteger(valor)
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
        return (self.get("claude_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


class AjustesMemoria(Ajustes):
    """Mesma interface de Ajustes, mas só na memória (sessões abertas pelo celular)."""

    def __init__(self, inicial: dict | None = None):
        self.caminho = None
        self._lock = threading.Lock()
        self._dados = dict(PADROES)
        self._dados.update(inicial or {})

    def _salvar(self) -> None:
        pass
