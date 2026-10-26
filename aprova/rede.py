"""Acesso pelo celular: endereço na rede local, QR code e servidor web do app."""

from __future__ import annotations

import io
import os
import socket
import subprocess
import sys

from . import config

PORTA_CELULAR = 8550


def ip_local() -> str:
    """IP do computador na rede Wi-Fi/cabo (não envia nada pela rede)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


CHAVE_ENV = "APROVA_WEB_CHAVE"


def nova_chave() -> str:
    """Código secreto do acesso pelo navegador: sem ele, quem está no mesmo Wi-Fi não abre o seu Aprova."""
    import secrets

    return secrets.token_urlsafe(12)


def endereco_celular(porta: int = PORTA_CELULAR, chave: str = "") -> str:
    return f"http://{ip_local()}:{porta}" + (f"/?k={chave}" if chave else "")


def acesso_liberado(client_ip: str | None, rota: str | None, chave: str | None) -> bool:
    """No modo web, abre para quem está neste computador ou chegou pelo endereço com o código (QR code)."""
    import hmac
    from urllib.parse import parse_qs, urlparse

    ip = (client_ip or "").strip()
    if ip in ("127.0.0.1", "::1", "localhost") or ip.startswith("::ffff:127."):
        return True
    if not chave:
        return False
    k = (parse_qs(urlparse(rota or "").query).get("k") or [""])[0]
    return hmac.compare_digest(k.encode(), chave.encode())


def qr_png(texto: str) -> bytes | None:
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#14213D", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class ServidorCelular:
    """Roda uma segunda cópia do app em modo web, para abrir no navegador do celular."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self.chave = ""

    @property
    def ativo(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ligar(self, porta: int = PORTA_CELULAR) -> str:
        if not self.ativo:
            self.chave = nova_chave()  # um código novo cada vez que o acesso é ligado
            env = dict(os.environ, FLET_FORCE_WEB_SERVER="1", **{CHAVE_ENV: self.chave})
            flags = 0x08000000 if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(
                [sys.executable, str(config.RAIZ / "main.py"), "--web", "--porta", str(porta), "--sem-navegador"],
                cwd=str(config.RAIZ),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        return endereco_celular(porta, self.chave)

    def endereco(self, porta: int = PORTA_CELULAR) -> str:
        return endereco_celular(porta, self.chave)

    def desligar(self) -> None:
        if self.ativo:
            self._proc.terminate()
        self._proc = None
        self.chave = ""
