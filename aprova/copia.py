"""Cópia de segurança dos estudos: um arquivo .aprova (um .zip) com tudo o que só existe neste computador.

Vai na cópia: o banco de estudos (provas importadas e as questões delas, respostas, revisão, metas,
tempo, dúvidas, lembretes, favoritos), os ajustes, os PDFs marcados e as figurinhas próprias.
Não vão: a chave da IA e o login guardado (segredos ficam só neste computador) e os PDFs originais
das provas (dá para baixar de novo; as questões já estão no banco).

Além da cópia que a pessoa salva onde quiser, o app faz sozinho uma cópia por semana na pasta
.aprova/copias (guarda as 4 últimas). Antes de restaurar, ele guarda uma cópia do que existe agora.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__, config

EXTENSAO = ".aprova"
MANIFESTO = "copia.json"
PASTA_AUTO = "copias"
GUARDAR_AUTO = 4
INTERVALO_AUTO_S = 7 * 24 * 3600
# o que não vai na cópia: segredos (presos a este computador) e coisas do momento
FORA_DOS_AJUSTES = config.SEGREDOS | {"cronometro_inicio", "cronometro_atividade", "pasta_downloads"}


class ErroCopia(Exception):
    pass


def nome_sugerido(agora: datetime | None = None) -> str:
    return f"Aprova-copia-{(agora or datetime.now()):%Y-%m-%d}{EXTENSAO}"


def _resumo_banco(caminho: Path) -> dict:
    con = sqlite3.connect(caminho)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not ok or not {"provas", "questoes", "tentativas", "respostas"} <= tabelas:
            raise ErroCopia("O banco de estudos dentro da cópia está danificado.")
        return {
            "provas": con.execute("SELECT COUNT(*) FROM provas WHERE origem_url NOT LIKE 'aprova://%'").fetchone()[0],
            "respondidas": con.execute("SELECT COUNT(*) FROM respostas WHERE resposta IS NOT NULL").fetchone()[0],
        }
    finally:
        con.close()


def criar(pasta: Path, destino: Path, banco=None, motivo: str = "manual") -> dict:
    """Grava a cópia dos estudos da pasta de dados `pasta` em `destino`. Devolve o resumo da cópia.

    `banco`: o Banco aberto (a foto do banco é tirada com ele, sem fechar o app)."""
    pasta, destino = Path(pasta), Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        foto = Path(tmp) / "aprova.db"
        alvo = sqlite3.connect(foto)
        try:
            if banco is not None:
                with banco._lock:
                    banco._con.backup(alvo)
            elif (pasta / "aprova.db").exists():
                origem = sqlite3.connect(pasta / "aprova.db")
                try:
                    origem.backup(alvo)
                finally:
                    origem.close()
            else:
                raise ErroCopia("Ainda não há estudos para copiar.")
        finally:
            alvo.close()
        resumo = _resumo_banco(foto)
        ajustes = {}
        try:
            ajustes = json.loads((pasta / "ajustes.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        ajustes = {k: v for k, v in ajustes.items() if k not in FORA_DOS_AJUSTES}
        manifesto = {"app": "Aprova", "versao": __version__, "criada_em": datetime.now().isoformat(timespec="seconds"),
                     "motivo": motivo, **resumo}
        parcial = destino.with_name(destino.name + ".parcial")
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFESTO, json.dumps(manifesto, ensure_ascii=False, indent=1))
            z.write(foto, "aprova.db")
            z.writestr("ajustes.json", json.dumps(ajustes, ensure_ascii=False, indent=1))
            for sub in ("marcados", "figurinhas"):
                base = pasta / sub
                if base.is_dir():
                    for arq in sorted(base.rglob("*")):
                        if arq.is_file() and not arq.name.endswith(".tmp"):
                            z.write(arq, f"{sub}/{arq.relative_to(base).as_posix()}")
        parcial.replace(destino)
    return manifesto


def ler(arquivo: Path) -> dict:
    """Confere a cópia e devolve o resumo dela ({criada_em, versao, provas, respondidas})."""
    try:
        with zipfile.ZipFile(arquivo) as z:
            manifesto = json.loads(z.read(MANIFESTO).decode("utf-8"))
            if not isinstance(manifesto, dict) or manifesto.get("app") != "Aprova" or "aprova.db" not in z.namelist():
                raise ErroCopia("Esse arquivo não é uma cópia de segurança do Aprova.")
            with tempfile.TemporaryDirectory() as tmp:
                z.extract("aprova.db", tmp)
                manifesto.update(_resumo_banco(Path(tmp) / "aprova.db"))
            return manifesto
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        raise ErroCopia("Esse arquivo não é uma cópia de segurança do Aprova (ou está incompleto).") from e


def restaurar(arquivo: Path, pasta: Path, banco, ajustes) -> dict:
    """Troca os estudos desta pasta pelos da cópia (antes, guarda uma cópia do que existe agora).

    O banco aberto recebe o conteúdo da cópia sem precisar fechar o app. Os segredos e a conta deste
    computador continuam os de agora. Devolve o resumo da cópia restaurada."""
    pasta = Path(pasta)
    resumo = ler(arquivo)
    antes = pasta / PASTA_AUTO / f"antes-de-restaurar-{datetime.now():%Y-%m-%d-%H%M%S}{EXTENSAO}"
    try:
        criar(pasta, antes, banco, motivo="antes de restaurar")
    except ErroCopia:
        pass  # sem estudos ainda: nada a guardar
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(arquivo) as z:
        z.extract("aprova.db", tmp)
        origem = sqlite3.connect(Path(tmp) / "aprova.db")
        try:
            with banco._lock:
                origem.backup(banco._con)
        finally:
            origem.close()
        banco.migrar()  # cópia feita numa versão mais antiga: completa o que falta
        # ajustes: os da cópia, menos o que é deste computador
        try:
            vindos = json.loads(z.read("ajustes.json").decode("utf-8"))
        except (KeyError, ValueError):
            vindos = {}
        for k, v in (vindos or {}).items():
            if k not in FORA_DOS_AJUSTES and not k.startswith("ranking_"):
                ajustes._dados[k] = v
        ajustes.set("copia_restaurada_em", datetime.now().isoformat(timespec="seconds"))
        # PDFs marcados e figurinhas: junta com o que já existe (o índice dos marcados aponta para esta pasta)
        for nome in z.namelist():
            if not nome.startswith(("marcados/", "figurinhas/")) or nome.endswith("/") or ".." in nome.split("/"):
                continue
            if nome in ("marcados/indice.json", "figurinhas/indice.json"):
                continue
            alvo = pasta / nome
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(z.read(nome))
        _juntar_indice_marcados(z, pasta)
        _juntar_indice_figurinhas(z, pasta)
    return resumo


def _juntar_indice_marcados(z: zipfile.ZipFile, pasta: Path) -> None:
    try:
        vindos = json.loads(z.read("marcados/indice.json").decode("utf-8"))
    except (KeyError, ValueError):
        return
    arq = pasta / "marcados" / "indice.json"
    try:
        atuais = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        atuais = {}
    for item_id, item in (vindos or {}).items():
        if isinstance(item, dict) and item_id not in atuais:
            nome = Path(str(item.get("copia", ""))).name
            atuais[item_id] = dict(item, copia=str(pasta / "marcados" / nome))
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(atuais, ensure_ascii=False, indent=1), encoding="utf-8")


def _juntar_indice_figurinhas(z: zipfile.ZipFile, pasta: Path) -> None:
    try:
        vindas = json.loads(z.read("figurinhas/indice.json").decode("utf-8"))
    except (KeyError, ValueError):
        return
    arq = pasta / "figurinhas" / "indice.json"
    try:
        atuais = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        atuais = []
    ids = {i.get("id") for i in atuais if isinstance(i, dict)}
    atuais += [i for i in (vindas or []) if isinstance(i, dict) and i.get("id") not in ids]
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(atuais, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- cópia automática semanal


def automaticas(pasta: Path) -> list[Path]:
    """Cópias que o app guardou sozinho (a mais nova primeiro)."""
    p = Path(pasta) / PASTA_AUTO
    return sorted(p.glob(f"*{EXTENSAO}"), key=lambda a: a.stat().st_mtime, reverse=True) if p.is_dir() else []


def _semanais(pasta: Path) -> list[Path]:
    """Cópias semanais, a mais nova primeiro (a data está no nome: semanal-aaaa-mm-dd)."""
    p = Path(pasta) / PASTA_AUTO
    return sorted(p.glob(f"semanal-*{EXTENSAO}"), key=lambda a: a.name, reverse=True) if p.is_dir() else []


def automatica(pasta: Path, banco, agora: float | None = None) -> Path | None:
    """Uma cópia por semana em .aprova/copias (guarda as 4 últimas semanais). Devolve a nova, se fez."""
    pasta = Path(pasta)
    hoje = datetime.fromtimestamp(agora or time.time()).date()
    semanais = _semanais(pasta)
    if semanais:
        try:
            ultima = datetime.strptime(semanais[0].stem.removeprefix("semanal-"), "%Y-%m-%d").date()
            if (hoje - ultima).days < INTERVALO_AUTO_S // 86400:
                return None
        except ValueError:
            pass
    if not banco.estatisticas()["respondidas"] and not any(not str(p["origem_url"]).startswith("aprova://") for p in banco.provas()):
        return None  # nada estudado ainda
    destino = pasta / PASTA_AUTO / f"semanal-{hoje:%Y-%m-%d}{EXTENSAO}"
    criar(pasta, destino, banco, motivo="semanal")
    for velha in _semanais(pasta)[GUARDAR_AUTO:]:
        try:
            velha.unlink()
        except OSError:
            pass
    return destino
