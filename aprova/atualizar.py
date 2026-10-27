"""Atualização automática do Aprova.

1. O app consulta https://natanaelsantz.github.io/aprova/versao.json (uma vez a cada 12 horas).
2. Se houver versão nova, a pessoa toca em "Atualizar": o .zip é baixado do GitHub e preparado
   na pasta .aprova/atualizacao (nada do app muda enquanto ele está aberto).
3. Ao reabrir, o iniciar.pyw copia os arquivos novos por cima da pasta do app, guardando uma
   cópia dos antigos, e reinstala as bibliotecas só se o requirements.txt mudou.
4. Quando a janela do app aparece, ele confirma que a versão nova abriu (confirmar). Se ela não abrir
   (erro ao abrir ou duas tentativas sem confirmar), o iniciar.pyw volta para a versão anterior
   (voltar) e essa versão é pulada até sair outra mais nova.

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
# de onde o .zip da atualização pode vir (o repositório do Aprova no GitHub)
ZIP_PERMITIDO = re.compile(r"^https://(github\.com|codeload\.github\.com)/NatanaelSantz/aprova/", re.I)


def zip_confiavel(url: str) -> bool:
    import os

    if os.environ.get("APROVA_ATUALIZACAO_URL"):  # testes e servidor próprio de quem mantém o app
        return str(url).startswith(("https://", "http://127.0.0.1", "http://localhost"))
    return bool(ZIP_PERMITIDO.match(str(url or "")))
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


def verificar(versao_atual: str, url: str = URL_VERSAO, timeout: float = 8, pasta: Path | None = None) -> dict | None:
    """Devolve os dados da versão nova ({versao, notas, zip, data}) ou None se já está na última.

    Com `pasta` (a pasta de dados), ignora a versão que não abriu neste computador (pulada) até sair uma mais nova."""
    try:
        dados = json.loads(_baixar(url + f"?t={int(time.time() // 600)}", timeout).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ErroAtualizacao("Não deu para procurar atualização agora. Confira a internet.") from e
    if not isinstance(dados, dict) or not dados.get("versao") or not zip_confiavel(str(dados.get("zip", ""))):
        raise ErroAtualizacao("A informação de versão veio incompleta.")
    if not mais_nova(dados["versao"], versao_atual):
        return None
    if pasta is not None and str(dados["versao"]) == versao_pulada(pasta):
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
    if conteudo is None and not zip_confiavel(str(info.get("zip") or "")):
        raise ErroAtualizacao("O endereço da atualização não é o do Aprova.")
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
    if copia.exists():  # sobra de uma troca antiga para a mesma versão: começa limpa
        shutil.rmtree(copia, ignore_errors=True)
    criados: list[str] = []  # arquivos que não existiam (somem se precisar voltar)
    for arq in sorted(novo.rglob("*")):
        if not arq.is_file():
            continue
        rel = arq.relative_to(novo)
        destino = raiz / rel
        if destino.exists():
            (copia / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, copia / rel)
        else:
            criados.append(rel.as_posix())
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
    _gravar(base / "ultima.json", {"versao": info.get("versao"), "de": info.get("de"), "quando": time.time(),
                                   "confirmada": False, "tentativas": 0, "criados": criados})
    return str(info.get("versao") or "")


# ---------------------------------------------------------------- volta automática

TENTATIVAS = 2  # aberturas sem a janela aparecer antes de voltar para a versão anterior


def _gravar(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados), encoding="utf-8")
    tmp.replace(caminho)


def ultima(dados: Path) -> dict:
    try:
        d = json.loads((dados / PASTA / "ultima.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def em_teste(dados: Path) -> bool:
    """A última atualização ainda não abriu nenhuma vez? (as antigas, sem a marca, contam como confirmadas)"""
    u = ultima(dados)
    return bool(u) and u.get("confirmada") is False and not u.get("voltou")


def confirmar(dados: Path) -> None:
    """O app abriu na versão nova: ela fica (chamado quando a janela aparece)."""
    u = ultima(dados)
    if u and u.get("confirmada") is False:
        try:
            _gravar(dados / PASTA / "ultima.json", {**u, "confirmada": True})
        except OSError:
            pass


def contar_abertura(dados: Path) -> bool:
    """Chamado pelo iniciar.pyw antes de abrir o app. True = a versão nova já falhou demais: hora de voltar."""
    u = ultima(dados)
    if not em_teste(dados):
        return False
    if int(u.get("tentativas") or 0) >= TENTATIVAS:
        return True
    _gravar(dados / PASTA / "ultima.json", {**u, "tentativas": int(u.get("tentativas") or 0) + 1})
    return False


def versao_pulada(dados: Path) -> str:
    try:
        return str(json.loads((dados / PASTA / "pular.json").read_text(encoding="utf-8")).get("versao") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def voltar(raiz: Path, dados: Path) -> str | None:
    """Desfaz a última atualização: devolve os arquivos da versão anterior e pula a versão que não abriu.

    Devolve a versão para a qual voltou (ou None se não há o que desfazer)."""
    u = ultima(dados)
    base = dados / PASTA
    de = str(u.get("de") or "")
    copia = base / "anterior" / (de or "antiga")
    if not em_teste(dados) or not copia.is_dir():
        return None
    raiz_resolvida = raiz.resolve()
    for rel in u.get("criados") or []:
        alvo = (raiz / rel).resolve()
        if raiz_resolvida in alvo.parents and alvo.is_file():
            try:
                alvo.unlink()
            except OSError:
                pass
    for arq in sorted(copia.rglob("*")):
        if arq.is_file():
            destino = raiz / arq.relative_to(copia)
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(arq, destino)
    _gravar(base / "pular.json", {"versao": u.get("versao"), "quando": time.time()})
    _gravar(base / "ultima.json", {**u, "voltou": True, "quando_voltou": time.time()})
    return de or None
