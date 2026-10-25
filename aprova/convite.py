"""Convite por link para os grupos.

O link é uma página na internet (https), porque WhatsApp, Instagram e TikTok só deixam clicar em links assim:
    https://natanaelsantz.github.io/aprova/convite/?g=DATAPREV-7A2F

A página abre o app pelo endereço aprova://grupo/DATAPREV-7A2F (registrado no Windows na primeira vez que o
Aprova abre) e também copia o link: se a pessoa ainda não tem o app, ao instalar e abrir ele encontra o convite
na área de transferência e oferece entrar no grupo. Ninguém precisa digitar código.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from . import config

BASE_PADRAO = "https://natanaelsantz.github.io/aprova/convite/"
ESQUEMA = "aprova"
_CODIGO = r"([A-Za-z0-9][A-Za-z0-9-]{3,23})"
_PADROES = [
    re.compile(r"[?&#]g=" + _CODIGO + r"(?![A-Za-z0-9-])"),
    re.compile(ESQUEMA + r"://grupo/" + _CODIGO, re.I),
    re.compile(r"/convite/" + _CODIGO + r"(?![A-Za-z0-9-])"),
]
ARQ_PENDENTE = "convite_pendente.json"
ARQ_VIVO = "app.vivo"
VIVO_S = 75  # o app em execução marca presença a cada 30 s


def base_convite(cfg: dict | None = None) -> str:
    base = str((cfg or {}).get("convite") or BASE_PADRAO).strip()
    return base if base.endswith(("/", "=", "?")) else base + "/"


def link(codigo: str, cfg: dict | None = None) -> str:
    return f"{base_convite(cfg)}?g={codigo.strip().upper()}"


def link_app(codigo: str) -> str:
    return f"{ESQUEMA}://grupo/{codigo.strip().upper()}"


def extrair_codigo(texto: str | None) -> str | None:
    """Acha o código do grupo num link de convite (página ou aprova://). Texto qualquer devolve None."""
    if not texto or len(texto) > 2000:
        return None
    for padrao in _PADROES:
        m = padrao.search(texto)
        if m:
            return m.group(1).upper()
    return None


def eh_convite(texto: str | None) -> bool:
    """Só considera textos que são mesmo um convite do Aprova (evita pegar qualquer '?g=' da área de transferência)."""
    if not texto:
        return False
    t = texto.lower()
    return ("aprova" in t and ("/convite" in t or f"{ESQUEMA}://grupo/" in t)) and extrair_codigo(texto) is not None


def mensagem(nome: str, url: str) -> str:
    return f"Bora estudar junto? Entra no meu grupo “{nome}” no Aprova (app de estudo para concursos). É só abrir o link: {url}"


def links_compartilhar(nome: str, url: str) -> dict[str, str]:
    texto = mensagem(nome, url)
    return {
        "whatsapp": "https://wa.me/?text=" + quote(texto),
        "telegram": "https://t.me/share/url?url=" + quote(url) + "&text=" + quote(f"Bora estudar junto? Entra no meu grupo “{nome}” no Aprova."),
        "email": "mailto:?subject=" + quote(f"Convite: grupo {nome} no Aprova") + "&body=" + quote(texto),
    }


# ---------------------------------------------------------------------- convite chegando por aprova://


def guardar_pendente(codigo: str, origem: str = "link") -> None:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (config.DATA_DIR / ARQ_PENDENTE).write_text(json.dumps({"codigo": codigo, "origem": origem, "quando": time.time()}), encoding="utf-8")
    except OSError:
        pass


def pegar_pendente() -> dict | None:
    """Lê e apaga o convite deixado por um clique no link (convites com mais de 1 dia são ignorados)."""
    arq = config.DATA_DIR / ARQ_PENDENTE
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        arq.unlink()
    except OSError:
        pass
    if not isinstance(dados, dict) or not dados.get("codigo") or time.time() - float(dados.get("quando") or 0) > 86400:
        return None
    return dados


def marcar_vivo() -> None:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (config.DATA_DIR / ARQ_VIVO).write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def parar_vivo() -> None:
    """O app fechou: o próximo clique num convite abre o app de novo."""
    try:
        (config.DATA_DIR / ARQ_VIVO).unlink()
    except OSError:
        pass


def outro_app_aberto() -> bool:
    try:
        return time.time() - (config.DATA_DIR / ARQ_VIVO).stat().st_mtime < VIVO_S
    except OSError:
        return False


def registrar_protocolo(raiz: Path) -> bool:
    """Faz o Windows abrir o Aprova quando alguém clica num endereço aprova://… (só no usuário atual, sem admin)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" and exe.with_name("pythonw.exe").exists() else exe
        comando = f'"{pyw}" "{raiz / "iniciar.pyw"}" "%1"'
        icone = raiz / "assets" / "aprova.ico"
        base = rf"Software\Classes\{ESQUEMA}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Aprova")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(icone))
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, comando)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------- imagem para Stories / TikTok


def imagem_stories(nome: str, codigo: str, url: str, destino: Path) -> Path:
    """Imagem 1080x1920 com o nome do grupo e um QR code do link (para Stories do Instagram e TikTok)."""
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1080, 1920
    branco, ouro = (255, 255, 255), (226, 176, 74)
    # fundo em degradê do azul do app até o azul-escuro
    faixa = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), (20, 33, 61)), Image.new("RGB", (w, h), (35, 64, 168)), faixa)
    d = ImageDraw.Draw(img)
    fontes = config.ASSETS_DIR / "fonts"

    def fonte(nome_arq: str, tam: int):
        try:
            return ImageFont.truetype(str(fontes / nome_arq), tam)
        except OSError:
            return ImageFont.load_default()

    titulo = fonte("Fraunces.ttf", 96)
    grande = fonte("Fraunces.ttf", 74)
    texto = fonte("AtkinsonHyperlegible-Regular.ttf", 44)
    negrito = fonte("AtkinsonHyperlegible-Bold.ttf", 46)

    def centro(y: int, s: str, f, cor):
        caixa = d.textbbox((0, 0), s, font=f)
        d.text(((w - (caixa[2] - caixa[0])) // 2, y), s, font=f, fill=cor)
        return caixa[3] - caixa[1]

    def quebrar(s: str, f, largura: int) -> list[str]:
        linhas, atual = [], ""
        for palavra in s.split():
            teste = (atual + " " + palavra).strip()
            if d.textbbox((0, 0), teste, font=f)[2] <= largura:
                atual = teste
            else:
                if atual:
                    linhas.append(atual)
                atual = palavra
        return linhas + ([atual] if atual else [])

    try:
        icone = Image.open(config.ASSETS_DIR / "icon.png").convert("RGBA").resize((150, 150))
        img.paste(icone, ((w - 150) // 2, 150), icone)
    except OSError:
        pass
    centro(330, "Aprova", titulo, branco)
    centro(460, "estudo para concursos", texto, (216, 223, 247))
    centro(620, "Vem estudar comigo no grupo", texto, branco)
    y = 700
    for linha in quebrar(nome, grande, w - 160)[:3]:
        centro(y, linha, grande, branco)
        y += 96
    # QR code num cartão branco
    qr = qrcode.QRCode(border=2, box_size=14)
    qr.add_data(url)
    qr.make(fit=True)
    q = qr.make_image(fill_color="#14213D", back_color="white").convert("RGB").resize((560, 560))
    topo = max(y + 60, 900)
    d.rounded_rectangle([(w - 640) // 2, topo, (w + 640) // 2, topo + 640], radius=40, fill=branco)
    img.paste(q, ((w - 560) // 2, topo + 40))
    y = topo + 690
    centro(y, "Aponte a câmera ou toque no link", texto, branco)
    centro(y + 70, f"código {codigo}", negrito, ouro)
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "PNG")
    return destino
