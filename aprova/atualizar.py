"""Atualização automática do Aprova.

1. O app consulta https://natanaelsantz.github.io/aprova/versao.json (uma vez a cada 12 horas).
2. Se houver versão nova, a pessoa toca em "Atualizar": o .zip é baixado do GitHub e preparado
   na pasta .aprova/atualizacao (nada do app muda enquanto ele está aberto).
3. Ao reabrir, o iniciar.pyw copia os arquivos novos por cima da pasta do app, guardando uma
   cópia dos antigos, e reinstala as bibliotecas só se o requirements.txt mudou.

Os estudos ficam na pasta .aprova do usuário e nunca são tocados. Este módulo usa só a biblioteca
padrão do Python, para o iniciar.pyw poder usá-lo antes de o app abrir.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

URL_VERSAO = "https://natanaelsantz.github.io/aprova/versao.json"
NAO_SUBSTITUIR = {".venv", ".git", "ranking.json", "__pycache__", ".pytest_cache"}
PASTA = "atualizacao"


class ErroAtualizacao(Exception):
    pass


def versao_tupla(v: str) -> tuple[int, ...]:
    partes = re.findall(r"\d+", str(v or ""))[:4]
    return tuple(int(p) for p in partes) or (0,)


def mais_nova(remota: str, local: str) -> bool:
    return versao_tupla(remota) > versao_tupla(local)


def _baixar(url: str, timeout: float, progresso=None, limite: int = 80 * 1024 * 1024) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": "Aprova-atualizador", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(pedido, timeout=timeout) as resp:  # noqa: S310 - URL fixa do app
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while True:
            pedaco = resp.read(64 * 1024)
            if not pedaco:
                break
            buf.write(pedaco)
            if buf.tell() > limite:
                raise ErroAtualizacao("O arquivo da atualização é grande demais.")
            if progresso:
                progresso(buf.tell(), total)
        return buf.getvalue()


def verificar(versao_atual: str, url: str = URL_VERSAO, timeout: float = 8) -> dict | None:
    """Devolve os dados da versão nova ({versao, notas, zip, data}) ou None se já está na última."""
    try:
        dados = json.loads(_baixar(url + f"?t={int(time.time() // 600)}", timeout).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ErroAtualizacao("Não deu para procurar atualização agora. Confira a internet.") from e
    if not isinstance(dados, dict) or not dados.get("versao") or not str(dados.get("zip", "")).startswith("https://"):
        raise ErroAtualizacao("A informação de versão veio incompleta.")
    if not mais_nova(dados["versao"], versao_atual):
        return None
    notas = dados.get("notas") or []
    return {"versao": str(dados["versao"]), "data": str(dados.get("data") or ""), "notas": [str(n) for n in notas][:12], "zip": dados["zip"]}


def _versao_no_zip(z: zipfile.ZipFile, raiz_zip: str) -> str:
    try:
        texto = z.read(raiz_zip + "aprova/__init__.py").decode("utf-8", "replace")
    except KeyError as e:
        raise ErroAtualizacao("O arquivo baixado não é o Aprova.") from e
    m = re.search(r'__version__\s*=\s*"([^"]+)"', texto)
    return m.group(1) if m else ""


def preparar(info: dict, dados: Path, versao_atual: str, progresso=None, conteudo: bytes | None = None) -> str:
    """Baixa o .zip da versão nova e deixa os arquivos prontos em dados/atualizacao/novo.

    Devolve a versão preparada. A troca dos arquivos acontece ao reabrir o app (aplicar_pendente)."""
    base = dados / PASTA
    novo = base / "novo"
    conteudo = conteudo if conteudo is not None else _baixar(info["zip"], 60, progresso)
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as e:
        raise ErroAtualizacao("O download veio corrompido. Tente de novo.") from e
    nomes = z.namelist()
    principais = [n for n in nomes if n.endswith("main.py") and n.count("/") <= 1]
    if not principais:
        raise ErroAtualizacao("O arquivo baixado não é o Aprova.")
    raiz_zip = principais[0][: -len("main.py")]
    versao = _versao_no_zip(z, raiz_zip)
    if not mais_nova(versao, versao_atual):
        raise ErroAtualizacao(f"O arquivo baixado é da versão {versao or '?'}, que não é mais nova que a sua.")
    if novo.exists():
        shutil.rmtree(novo)
    novo.mkdir(parents=True)
    alvo_resolvido = novo.resolve()
    for nome in nomes:
        if not nome.startswith(raiz_zip) or nome.endswith("/"):
            continue
        rel = nome[len(raiz_zip):]
        if not rel or rel.split("/")[0] in NAO_SUBSTITUIR or "__pycache__" in rel.split("/"):
            continue
        destino = (novo / rel).resolve()
        if alvo_resolvido not in destino.parents:  # nada de caminhos com ../
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(z.read(nome))
    (base / "pronta.json").write_text(json.dumps({"versao": versao, "de": versao_atual, "quando": time.time()}), encoding="utf-8")
    return versao


def pendente(dados: Path) -> dict | None:
    try:
        return json.loads((dados / PASTA / "pronta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def aplicar_pendente(raiz: Path, dados: Path) -> str | None:
    """Copia a versão preparada por cima da pasta do app (chamado pelo iniciar.pyw, com o app fechado)."""
    info = pendente(dados)
    base = dados / PASTA
    novo = base / "novo"
    if not info or not novo.is_dir():
        return None
    copia = base / "anterior" / str(info.get("de") or "antiga")
    for arq in sorted(novo.rglob("*")):
        if not arq.is_file():
            continue
        rel = arq.relative_to(novo)
        destino = raiz / rel
        if destino.exists():
            (copia / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, copia / rel)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arq, destino)
    shutil.rmtree(novo, ignore_errors=True)
    # guarda só as 2 cópias mais recentes das versões anteriores
    anteriores = sorted((d for d in (base / "anterior").iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True) if (base / "anterior").is_dir() else []
    for velha in anteriores[2:]:
        shutil.rmtree(velha, ignore_errors=True)
    try:
        (base / "pronta.json").unlink()
    except OSError:
        pass
    (base / "ultima.json").write_text(json.dumps({"versao": info.get("versao"), "de": info.get("de"), "quando": time.time()}), encoding="utf-8")
    return str(info.get("versao") or "")
