"""Em que aparelho o Aprova está rodando: computador (Windows, Mac, Linux) ou celular (Android, iPhone).

O mesmo código vira o app do computador e o do celular (empacotado com `flet build apk` / `flet build ipa`).
O app empacotado do Flet avisa o sistema pela variável FLET_PLATFORM ("android" ou "ios") e dá uma pasta
privada para os dados em FLET_APP_STORAGE_DATA. No celular ficam desligadas as coisas que só existem no
computador: janela e barra do Windows, atualizador pelo GitHub, voz por programa do sistema, notificação
do Windows, abrir pasta no Explorer e o "Usar no celular" (servidor na rede de casa).
"""

from __future__ import annotations

import os
from pathlib import Path

# APROVA_SIMULAR_CELULAR=android|ios: roda no computador como se fosse o app do celular (testes e prints)
SISTEMA = (os.environ.get("FLET_PLATFORM") or os.environ.get("APROVA_SIMULAR_CELULAR") or "").strip().lower()
ANDROID = SISTEMA == "android"
IOS = SISTEMA == "ios"
CELULAR = ANDROID or IOS

NOMES = {"android": "Android", "ios": "iPhone"}


def nome() -> str:
    """Nome do aparelho para mostrar na tela ("Android", "iPhone" ou "computador")."""
    return NOMES.get(SISTEMA, "computador")


def pasta_dados() -> Path | None:
    """No celular, a pasta privada do app (o Flet dá o caminho); no computador, None (fica a pasta .aprova)."""
    if not CELULAR:
        return None
    base = os.environ.get("FLET_APP_STORAGE_DATA")
    return Path(base) / "aprova" if base else None


def pasta_downloads_padrao() -> Path:
    """Onde o navegador costuma salvar os downloads. No celular o app não enxerga essa pasta: usa a dele."""
    dados = pasta_dados()
    return dados / "downloads" if dados else Path.home() / "Downloads"
