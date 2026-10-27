"""Aviso de versão nova, janela de atualizar e reinício do app."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

import flet as ft

from .. import __version__, atualizar, config, convite
from . import comp
from .tema import FONTE_TITULO

INTERVALO = 3 * 3600  # procura versão nova a cada 3 horas com o app aberto (é um arquivinho de 1 KB)


def url_versao() -> str:
    return os.environ.get("APROVA_ATUALIZACAO_URL") or atualizar.URL_VERSAO


def disponivel(app) -> bool:
    """Só no app do computador. No navegador quem atualiza é o computador que serve o app; no app do celular,
    a versão nova vem pela loja (ou pelo APK novo do site)."""
    if not app.desktop:
        return False
    return not config.FIXTURES_DIR or bool(os.environ.get("APROVA_ATUALIZACAO_URL"))


def ver_pronta(app) -> None:
    pronta = atualizar.pendente(config.DATA_DIR)
    if pronta and atualizar.mais_nova(str(pronta.get("versao") or ""), __version__):
        app.atualizacao_pronta = str(pronta["versao"])


async def verificar(app, forcar: bool = False) -> dict | None:
    """Procura versão nova. Lança atualizar.ErroAtualizacao se não der para consultar (sem internet)."""
    ver_pronta(app)
    agora = time.time()
    ultima = float(app.sessao.get("atualizacao_verificada_em") or 0)
    if not forcar and agora - ultima < INTERVALO:
        info = app.sessao.get("atualizacao_info") or None
    else:
        info = await app.em_segundo_plano(atualizar.verificar, __version__, url_versao())
        app.sessao.set("atualizacao_verificada_em", agora)
        app.sessao.set("atualizacao_info", info or {})
    if info and not atualizar.mais_nova(str(info.get("versao") or ""), __version__):
        info = None
    app.atualizacao = info
    return info


async def vigiar(app) -> None:
    """Roda em segundo plano enquanto o app está aberto."""
    await asyncio.sleep(3)
    avisar_atualizado(app)
    primeira = True
    while True:
        antes = (app.atualizacao or {}).get("versao")
        try:
            # ao abrir, sempre confere na hora (o iniciar.pyw já atualiza antes de abrir; aqui pega o resto)
            await verificar(app, forcar=primeira)
        except atualizar.ErroAtualizacao:
            pass  # sem internet agora: tenta de novo mais tarde
        except Exception as e:  # noqa: BLE001
            config.registrar(f"atualização: falhou ao verificar ({e!r})")
        primeira = False
        info = app.atualizacao
        if info and not app.atualizacao_pronta:
            # baixa sozinho em segundo plano: a versão nova entra ao reiniciar (ou na próxima vez que abrir)
            await baixar_sozinho(app, info)
        if app.atualizacao_pronta:
            notificar_pronta(app)
        elif info:
            notificar_versao(app, info)  # não deu para baixar agora: avisa para atualizar à mão
        novo = (info or {}).get("versao")
        if novo and novo != antes and app.foco is None and app.secao == "inicio" and not app.em_login:
            app.recarregar_tela()
        await asyncio.sleep(INTERVALO + 60)


async def baixar_sozinho(app, info: dict) -> bool:
    """Baixa e prepara a versão nova sem perguntar (uns 2 MB). Ela entra quando o app reabrir."""
    if getattr(app, "_baixando_atualizacao", False):
        return False
    app._baixando_atualizacao = True
    try:
        versao = await app.em_segundo_plano(atualizar.preparar, info, config.DATA_DIR, __version__)
    except Exception as e:  # noqa: BLE001 - sem internet, arquivo corrompido...: o aviso para atualizar à mão continua
        config.registrar(f"atualização: não baixou sozinho ({e!r})")
        return False
    finally:
        app._baixando_atualizacao = False
    app.atualizacao_pronta = versao
    return True


def notificar_pronta(app) -> bool:
    """A versão nova já foi baixada: avisa uma vez (notificação + faixa com "Reiniciar agora")."""
    versao = str(app.atualizacao_pronta or "")
    if not versao or app.sessao.get("atualizacao_pronta_avisada") == versao:
        return False
    app.sessao.set("atualizacao_pronta_avisada", versao)
    info = app.atualizacao or {}
    notas = info.get("notas") or []
    from .. import notificar

    notificar.mostrar(
        f"Aprova {versao} pronto para usar",
        (notas[0] + ". " if notas else "") + "Clique para reiniciar agora (ou ele entra na próxima vez que você abrir).",
        link="aprova://atualizar",
        botao="Reiniciar agora",
    )
    _faixa(app, f"A versão {versao} do Aprova já foi baixada.", "Reiniciar agora", lambda e: app.page.run_task(reiniciar, app))
    return True


def notificar_versao(app, info: dict) -> bool:
    """Avisa da versão nova uma vez: notificação do sistema (clicar leva para a atualização) e faixa no app.

    Devolve True se avisou agora (False se esta versão já tinha sido avisada)."""
    versao = str(info.get("versao") or "")
    if not versao or app.sessao.get("atualizacao_avisada") == versao:
        return False
    app.sessao.set("atualizacao_avisada", versao)
    notas = info.get("notas") or []
    from .. import notificar

    notificar.mostrar(
        f"Nova versão do Aprova: {versao}",
        (notas[0] if notas else "Melhorias e correções.") + " Clique para atualizar.",
        link="aprova://atualizar",
        botao="Atualizar agora",
    )
    _faixa(app, f"Nova versão do Aprova: {versao}", "Atualizar", lambda e: dialogo_atualizar(app, info))
    return True


def _faixa(app, texto: str, acao: str, ao_clicar) -> None:
    """Aviso na parte de baixo da tela, em qualquer tela do app (não só no Início)."""
    try:
        app.page.show_dialog(
            ft.SnackBar(
                ft.Text(texto),
                action=acao,
                on_action=ao_clicar,
                duration=ft.Duration(seconds=12),
                show_close_icon=True,
            )
        )
    except Exception:  # noqa: BLE001
        app.msg(texto)


async def abrir_pela_notificacao(app) -> None:
    """Clicou na notificação: mostra a versão nova (ou pede para reiniciar, se já baixou)."""
    if app.atualizacao_pronta:
        _faixa(app, f"A versão {app.atualizacao_pronta} já foi baixada.", "Reiniciar agora", lambda e: app.page.run_task(reiniciar, app))
        return
    info = app.atualizacao
    if not info:
        try:
            info = await verificar(app, forcar=True)
        except atualizar.ErroAtualizacao as ex:
            app.msg(str(ex))
            return
    if info:
        dialogo_atualizar(app, info)
    else:
        app.msg(f"Você já está na versão mais nova ({__version__}).")


def avisar_atualizado(app) -> None:
    """Primeira abertura depois de atualizar: conta o que mudou (uma vez)."""
    if app.sessao.get("versao_anunciada") == __version__:
        return
    anterior = app.sessao.get("versao_anunciada")
    app.sessao.set("versao_anunciada", __version__)
    try:
        import json

        ultima = json.loads((config.DATA_DIR / atualizar.PASTA / "ultima.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ultima = {}
    if not anterior and str(ultima.get("versao")) != __version__:
        return  # primeira vez com o app (ou instalado à mão): nada a anunciar
    info = app.sessao.get("atualizacao_info") or {}
    notas = info.get("notas") if str(info.get("versao")) == __version__ else None
    texto = f"Aprova atualizado para a versão {__version__}."
    if notas:
        texto += " Novidade: " + notas[0]
    _faixa(app, texto, "OK", lambda e: None)


def cartao_inicio(app) -> list[ft.Control]:
    """Cartão no Início: versão nova disponível ou já baixada esperando reiniciar."""
    c = app.c
    if app.atualizacao_pronta:
        icone, titulo, texto = ft.Icons.RESTART_ALT, f"Versão {app.atualizacao_pronta} pronta", "Reinicie o Aprova para começar a usar. Leva poucos segundos."
        botao = comp.botao("Reiniciar agora", lambda e: app.page.run_task(reiniciar, app), ft.Icons.RESTART_ALT)
    elif app.atualizacao:
        info = app.atualizacao
        notas = info.get("notas") or []
        icone, titulo = ft.Icons.SYSTEM_UPDATE_ALT, f"Nova versão do Aprova: {info['versao']}"
        texto = notas[0] if notas else "Melhorias e correções."
        if len(notas) > 1:
            texto += f" (e mais {len(notas) - 1} novidade{'s' if len(notas) > 2 else ''})"
        botao = comp.botao("Atualizar", lambda e: dialogo_atualizar(app, info), ft.Icons.SYSTEM_UPDATE_ALT)
    else:
        return []
    corpo = ft.Column([ft.Text(titulo, size=16, weight=ft.FontWeight.W_700, color=c["texto"]), comp.apagado(texto, c, 14)], spacing=2, expand=True)
    linha = (
        ft.Row([ft.Icon(icone, color=c["ok"], size=26), corpo, botao], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        if app.largo
        else ft.Column([ft.Row([ft.Icon(icone, color=c["ok"], size=26), corpo], spacing=12), botao], spacing=10)
    )
    return [ft.Container(linha, bgcolor=c["ok_suave"], border_radius=14, padding=ft.Padding.only(left=18, right=12, top=12, bottom=12))]


def secao_ajustes(app, secao) -> ft.Control:
    """Bloco "Atualizações" dos Ajustes."""
    c = app.c
    status = comp.apagado("", c, 14)
    acoes = ft.Row(spacing=10, wrap=True, run_spacing=8)

    def desenhar():
        ultima = float(app.sessao.get("atualizacao_verificada_em") or 0)
        quando = time.strftime("%d/%m às %H:%M", time.localtime(ultima)) if ultima else ""
        if app.atualizacao_pronta:
            status.value = f"A versão {app.atualizacao_pronta} já foi baixada. Reinicie o Aprova para usar."
            acoes.controls = [comp.botao("Reiniciar agora", lambda e: app.page.run_task(reiniciar, app), ft.Icons.RESTART_ALT)]
        elif app.atualizacao:
            status.value = f"Tem versão nova: {app.atualizacao['versao']}."
            acoes.controls = [comp.botao("Ver novidades e atualizar", lambda e: dialogo_atualizar(app, app.atualizacao), ft.Icons.SYSTEM_UPDATE_ALT)]
        else:
            status.value = "Você está na versão mais nova." + (f" Última verificação: {quando}." if quando else "")
            acoes.controls = [comp.botao_contorno("Procurar atualização", procurar, ft.Icons.REFRESH)]

    async def procurar(e=None):
        acoes.controls = [comp.carregando("Procurando…", c)]
        acoes.update()
        try:
            info = await verificar(app, forcar=True)
        except atualizar.ErroAtualizacao as ex:
            desenhar()
            status.value = str(ex)
            app.page.update()
            return
        desenhar()
        app.page.update()
        if info:
            dialogo_atualizar(app, info)
        else:
            comp.mensagem(app.page, f"Você já está na versão mais nova ({__version__}).")

    desenhar()
    return secao._secao(
        "Atualizações",
        f"Você usa o Aprova {__version__}. O app procura versão nova sozinho e avisa no Início. Seus estudos, contas e PDFs marcados continuam como estão.",
        status,
        acoes,
    )


def dialogo_atualizar(app, info: dict) -> None:
    c = app.c
    notas = info.get("notas") or ["Melhorias e correções."]
    lista = ft.Column(
        [ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=18, color=c["ok"]), ft.Text(n, size=14.5, color=c["texto"], expand=True)], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START) for n in notas],
        spacing=8,
    )
    barra = ft.ProgressBar(value=0, color=c["tinta"], bgcolor=c["sup2"], visible=False, border_radius=4)
    estado = comp.apagado("Baixa uns 2 MB. Seus estudos, contas e PDFs marcados não mudam.", c, 13)
    corpo = ft.Column(
        [comp.apagado(f"Você está na {__version__}." + (f" Publicada em {info['data']}." if info.get("data") else ""), c, 13), comp.texto("O que tem de novo", c, 15, peso=ft.FontWeight.W_700), lista, barra, estado],
        spacing=10,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    agora_nao = ft.TextButton("Agora não", on_click=lambda e: app.page.pop_dialog())
    atualizar_bt = ft.FilledButton("Atualizar", icon=ft.Icons.DOWNLOAD)
    dlg = ft.AlertDialog(
        title=ft.Text(f"Atualizar para a versão {info['versao']}", font_family=FONTE_TITULO, size=21),
        content=ft.Container(corpo, width=min(480, (app.page.width or 520) - 48)),
        actions=[agora_nao, atualizar_bt],
    )

    async def baixar(e=None):
        progresso = {"feito": 0, "total": 0}
        atualizar_bt.disabled = agora_nao.disabled = True
        barra.visible = True
        barra.value = None
        estado.value = "Baixando…"
        dlg.update()

        def cb(feito, total):
            progresso["feito"], progresso["total"] = feito, total

        tarefa = asyncio.ensure_future(app.em_segundo_plano(atualizar.preparar, info, config.DATA_DIR, __version__, cb))
        while not tarefa.done():
            f, t = progresso["feito"], progresso["total"]
            barra.value = (f / t) if t else None
            estado.value = f"Baixando… {f / 1e6:.1f} MB" + (f" de {t / 1e6:.1f} MB" if t else "")
            try:
                dlg.update()
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.25)
        try:
            versao = tarefa.result()
        except atualizar.ErroAtualizacao as ex:
            falhou(str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            config.registrar(f"atualização: falhou ao baixar ({ex!r})")
            falhou("Não deu para baixar a atualização agora. Confira a internet e tente de novo.")
            return
        app.atualizacao_pronta = versao
        barra.value = 1
        estado.value = f"Pronto! A versão {versao} entra quando o Aprova reiniciar."
        agora_nao.disabled = False
        agora_nao.content = "Depois"
        atualizar_bt.disabled = False
        atualizar_bt.content = "Reiniciar agora"
        atualizar_bt.icon = ft.Icons.RESTART_ALT
        atualizar_bt.on_click = lambda e: app.page.run_task(reiniciar, app)
        agora_nao.on_click = depois
        dlg.update()

    def falhou(texto: str):
        barra.visible = False
        estado.value = texto
        atualizar_bt.disabled = agora_nao.disabled = False
        atualizar_bt.content = "Tentar de novo"
        dlg.update()

    def depois(e=None):
        app.page.pop_dialog()
        comp.mensagem(app.page, "A versão nova entra na próxima vez que você abrir o Aprova.")
        if app.foco is None and app.secao in ("inicio", "ajustes"):
            app.recarregar_tela()

    atualizar_bt.on_click = baixar
    app.page.show_dialog(dlg)


async def reiniciar(app) -> None:
    """Fecha o app e abre de novo pelo iniciar.pyw, que aplica a versão baixada antes de abrir."""
    if config.FIXTURES_DIR:
        comp.mensagem(app.page, "(modo de teste: o app não reinicia)")
        return
    lancador = config.RAIZ / "iniciar.pyw"
    env = {k: v for k, v in os.environ.items() if k != "APROVA_ABERTURA_PID"}
    try:
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([sys.executable, str(lancador)], cwd=str(config.RAIZ), env=env, creationflags=flags, close_fds=True)
        else:
            subprocess.Popen([sys.executable, str(lancador)], cwd=str(config.RAIZ), env=env, start_new_session=True)
    except OSError as e:
        config.registrar(f"atualização: não reabriu ({e!r})")
        comp.mensagem(app.page, "Feche e abra o Aprova para usar a versão nova.")
        return
    convite.parar_vivo()
    try:
        await app.page.window.destroy()
    except Exception:  # noqa: BLE001
        os._exit(0)
