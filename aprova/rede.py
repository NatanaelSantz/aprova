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


def endereco_celular(porta: int = PORTA_CELULAR) -> str:
    return f"http://{ip_local()}:{porta}"


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

    @property
    def ativo(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ligar(self, porta: int = PORTA_CELULAR) -> str:
        if not self.ativo:
            env = dict(os.environ, FLET_FORCE_WEB_SERVER="1")
            flags = 0x08000000 if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(
                [sys.executable, str(config.RAIZ / "main.py"), "--web", "--porta", str(porta), "--sem-navegador"],
                cwd=str(config.RAIZ),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        return endereco_celular(porta)

    def desligar(self) -> None:
        if self.ativo:
            self._proc.terminate()
        self._proc = None
