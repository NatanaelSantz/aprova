"""Notificações do sistema (a "janelinha" no canto da tela), mesmo com o Aprova minimizado.

- Windows: notificação da Central de Notificações, com o nome e o ícone do Aprova. Clicar nela
  (ou no botão) abre o endereço aprova://atualizar, que leva o app para a frente com a atualização.
- macOS: Central de Notificações (osascript). Linux: notify-send, se existir.

É sempre melhor esforço: se o sistema não deixar, o aviso continua aparecendo dentro do app.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from . import config

APP_ID = "NatanaelSantz.Aprova"
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW


def registrar_app_windows(icone: Path | None = None) -> bool:
    """Diz ao Windows o nome e o ícone das notificações do Aprova (só no usuário atual, sem admin)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        icone = icone or (config.ASSETS_DIR / "icon.png")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Aprova")
            winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, str(icone))
            winreg.SetValueEx(k, "ShowInSettings", 0, winreg.REG_DWORD, 1)
        return True
    except OSError:
        return False


def xml_toast(titulo: str, texto: str, link: str = "", botao: str = "") -> str:
    acao = f" activationType=\"protocol\" launch={quoteattr(link)}" if link else ""
    acoes = (
        f"<actions><action content={quoteattr(botao)} activationType=\"protocol\" arguments={quoteattr(link)}/></actions>"
        if link and botao
        else ""
    )
    return (
        f"<toast{acao}><visual><binding template=\"ToastGeneric\">"
        f"<text>{escape(titulo[:120])}</text><text>{escape(texto[:250])}</text>"
        f"</binding></visual>{acoes}</toast>"
    )


def comando_windows(titulo: str, texto: str, link: str = "", botao: str = "") -> list[str]:
    xml = xml_toast(titulo, texto, link, botao).replace("'", "''")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('{xml}');"
        "$t = New-Object Windows.UI.Notifications.ToastNotification $x;"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}').Show($t)"
    )
    codificado = base64.b64encode(script.encode("utf-16-le")).decode()
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", codificado]


def mostrar(titulo: str, texto: str, link: str = "", botao: str = "") -> bool:
    """Mostra a notificação. Devolve False se este sistema não tem como (o app avisa por dentro)."""
    try:
        if sys.platform == "win32":
            registrar_app_windows()
            subprocess.Popen(comando_windows(titulo, texto, link, botao), creationflags=SEM_JANELA,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if sys.platform == "darwin":
            def aspas(s: str) -> str:
                return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

            subprocess.Popen(["osascript", "-e", f"display notification {aspas(texto[:250])} with title {aspas(titulo[:120])}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if shutil.which("notify-send"):
            icone = config.ASSETS_DIR / "icon.png"
            subprocess.Popen(["notify-send", "--app-name=Aprova", f"--icon={icone}", titulo[:120], texto[:250]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except OSError:
        pass
    return False
