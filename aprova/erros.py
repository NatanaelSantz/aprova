"""Erros do app: anotar no aprova.log e, se a pessoa deixou (Ajustes → Geral), avisar quem mantém o Aprova.

Pega o que escapa: erro num botão (o Flet avisa pelo logger "flet"), erro numa tarefa em segundo plano
(asyncio), numa thread ou no programa. O relatório leva só o erro técnico: versão, sistema, a tela onde
estava e o rastro do erro, sem o nome da pasta do usuário, sem e-mail e sem nada dos estudos.
O mesmo erro vai no máximo uma vez por dia (e o servidor tem trava contra enxurrada).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import platform
import re
import sys
import threading
import traceback
from datetime import date
from pathlib import Path

from . import __version__, config

_estado: dict = {"ranking": None, "aj": None, "onde": lambda: "", "enviando": set()}
_lock = threading.Lock()


def limpar(texto: str) -> str:
    """Tira do texto o que identifica a pessoa: pasta do usuário, nome de usuário e e-mails."""
    t = str(texto or "")
    casa = str(Path.home())
    for variante in {casa, casa.replace("\\", "/"), casa.replace("\\", "\\\\")}:
        if variante and len(variante) > 3:
            t = t.replace(variante, "~")
    usuario = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(usuario) >= 3:
        t = re.sub(re.escape(usuario), "<usuário>", t, flags=re.I)
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<e-mail>", t)
    t = re.sub(r"\b(sk-ant-[\w-]{6})[\w-]+", r"\1…", t)  # chave da API, se aparecer
    return t


def assinatura(tipo: str, tb: traceback.StackSummary | list) -> str:
    """O mesmo erro (tipo + os últimos lugares do código) dá sempre a mesma assinatura."""
    partes = [tipo] + [f"{Path(f.filename).name}:{f.name}" for f in list(tb)[-4:]]
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:16]


def sistema() -> str:
    from . import plataforma

    if plataforma.CELULAR:
        return plataforma.nome()
    return f"{platform.system()} {platform.release()}"[:40]


def relatorio(exc: BaseException, onde: str = "") -> dict:
    tb = traceback.extract_tb(exc.__traceback__)
    rastro = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "versao_app": __version__,
        "sistema_op": sistema(),
        "local": limpar(onde)[:120],
        "msg": limpar(f"{type(exc).__name__}: {exc}")[:300],
        "rastro": limpar(rastro)[-4000:],
        "chave": assinatura(type(exc).__name__, tb),
    }


def _ja_enviado_hoje(aj, chave: str) -> bool:
    enviados = aj.get("erros_enviados") or {}
    hoje = date.today().isoformat()
    if enviados.get(chave) == hoje:
        return True
    enviados = {k: v for k, v in enviados.items() if v == hoje}  # o dicionário não cresce para sempre
    enviados[chave] = hoje
    aj.set("erros_enviados", enviados)
    return False


def anotar(exc: BaseException, onde: str = "") -> dict:
    """Anota no aprova.log e manda o relatório (se a pessoa deixou). Devolve o relatório."""
    rel = relatorio(exc, onde or _estado["onde"]())
    config.registrar(f"ERRO {rel['msg']} (em {rel['local'] or '?'})\n{rel['rastro']}")
    aj, rk = _estado["aj"], _estado["ranking"]
    if aj is None or rk is None or not aj.get("enviar_erros") or not getattr(rk, "configurado", False):
        return rel
    with _lock:
        if rel["chave"] in _estado["enviando"] or _ja_enviado_hoje(aj, rel["chave"]):
            return rel
        _estado["enviando"].add(rel["chave"])
    threading.Thread(target=_enviar, args=(rk, rel), daemon=True).start()
    return rel


def _enviar(rk, rel: dict) -> None:
    try:
        rk.reportar_erro(rel)
    except Exception as e:  # noqa: BLE001 - relatório nunca atrapalha
        config.registrar(f"relatório de erro não foi: {type(e).__name__}: {e}")
    finally:
        with _lock:
            _estado["enviando"].discard(rel["chave"])


class _Pegador(logging.Handler):
    """Erros que o Flet pega nos botões e nos efeitos (ele anota com o rastro no logger "flet")."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            try:
                anotar(record.exc_info[1], _estado["onde"]())
            except Exception:  # noqa: BLE001
                pass


def ligar(aj, ranking, onde=None, loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Começa a vigiar os erros do app. `onde`: função que diz a tela atual."""
    _estado.update(aj=aj, ranking=ranking, onde=onde or (lambda: ""))
    flet_log = logging.getLogger("flet")
    if not any(isinstance(h, _Pegador) for h in flet_log.handlers):
        flet_log.addHandler(_Pegador(level=logging.ERROR))

    antigo_sys = sys.excepthook

    def no_programa(tipo, valor, tb):
        if valor is not None and not isinstance(valor, KeyboardInterrupt):
            anotar(valor.with_traceback(tb), "programa")
        antigo_sys(tipo, valor, tb)

    if getattr(sys.excepthook, "__name__", "") != "no_programa":
        sys.excepthook = no_programa

    def na_thread(args):
        if args.exc_value is not None and not isinstance(args.exc_value, SystemExit):
            anotar(args.exc_value, f"thread {getattr(args.thread, 'name', '')}")

    threading.excepthook = na_thread
    if loop is not None:
        anterior = loop.get_exception_handler()

        def na_tarefa(lp, contexto):
            exc = contexto.get("exception")
            if isinstance(exc, Exception):
                anotar(exc, _estado["onde"]())
            if anterior:
                anterior(lp, contexto)
            else:
                lp.default_exception_handler(contexto)

        loop.set_exception_handler(na_tarefa)


def trocar_conta(aj, ranking) -> None:
    """A pessoa entrou em outra conta: os ajustes (e o "posso enviar?") passam a ser os dela."""
    _estado.update(aj=aj, ranking=ranking)
