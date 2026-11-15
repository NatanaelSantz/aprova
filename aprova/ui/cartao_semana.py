"""Início → Sua semana → Compartilhar: o card da semana (imagem) para mandar no WhatsApp ou postar."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import flet as ft

from .. import cartao, config
from . import comp, meu_concurso
from .tema import FONTE_TITULO


def _dados(app, semana: date) -> dict:
    return cartao.dados_semana(app.db, semana, nome=app.nome_exibicao, concurso=meu_concurso.dados(app).get("nome") or "")


def abrir(app, semana: date | None = None) -> None:
    from .personagem import meu, tenho_personagem

    c = app.c
    estado = {"semana": semana or date.today(), "caminho": None, "bytes": None, "dados": None}
    largura = min(560, (app.page.width or 600) - 40)
    lp, ap = min(360, largura - 40), min(450, (largura - 40) * 1.25)
    previa = ft.Container(ft.ProgressRing(width=28, height=28, stroke_width=3), width=lp, height=ap, alignment=ft.Alignment.CENTER,
                          bgcolor=c["sup2"], border_radius=12)
    aviso = ft.Container()
    titulo_semana = ft.Text("", size=13.5, color=c["texto2"])

    def pasta_cartoes() -> Path:
        if app.desktop:
            return Path(app.aj["pasta_downloads"] or Path.home() / "Downloads")
        return config.DATA_DIR / "cartoes"

    async def gerar():
        d = _dados(app, estado["semana"])
        estado["dados"] = d
        nome_arq = f"aprova-semana-{d['inicio'].isoformat()}.png"
        cfg = meu(app) if tenho_personagem(app) else None
        try:
            caminho = await app.em_segundo_plano(cartao.imagem_semana, d, cfg, pasta_cartoes() / nome_arq)
        except Exception as e:  # noqa: BLE001
            config.registrar(f"card da semana: {e!r}")
            aviso.content = comp.aviso("Não consegui montar a imagem agora.", c, "erro")
            app.page.update()
            return
        estado["caminho"] = caminho
        previa.content = ft.Image(src=caminho.read_bytes(), width=lp, height=ap, fit=ft.BoxFit.CONTAIN, border_radius=12, gapless_playback=True)
        titulo_semana.value = f"Semana de {d['inicio'].strftime('%d/%m')} a {d['fim'].strftime('%d/%m')} · {cartao.horas(d['segundos'])} · {d['questoes']} questões"
        aviso.content = None
        app.page.update()

    def mudar_semana(dias: int):
        nova = estado["semana"] + timedelta(days=dias)
        if nova > date.today():
            return
        estado["semana"] = nova
        app.page.run_task(gerar)

    async def copiar_legenda(e=None):
        if not estado["dados"]:
            return
        try:
            await ft.Clipboard().set(cartao.legenda(estado["dados"]))
            app.msg("Legenda copiada. Cole junto com a imagem.")
        except Exception:  # noqa: BLE001
            app.msg(cartao.legenda(estado["dados"]))

    async def salvar(e=None):
        if not estado["caminho"]:
            return
        if app.desktop:
            from .grupos import _abrir_pasta

            await copiar_legenda()
            aviso.content = comp.aviso(
                f"Imagem salva em {estado['caminho']}. A legenda já está copiada.", c, "ok",
                comp.botao_texto("Abrir pasta", lambda ev: _abrir_pasta(app, estado["caminho"].parent), ft.Icons.FOLDER_OPEN),
            )
            app.page.update()
        else:
            await app.compartilhar_arquivo(estado["caminho"])

    async def whatsapp(e=None):
        if not estado["dados"]:
            return
        if not app.desktop:
            await app.compartilhar_arquivo(estado["caminho"])  # no celular o menu do sistema já tem o WhatsApp
            return
        await salvar()
        await app.abrir_url("https://wa.me/?text=" + quote(cartao.legenda(estado["dados"])))

    setas = ft.Row(
        [
            ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Semana anterior", on_click=lambda e: mudar_semana(-7)),
            titulo_semana,
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Semana seguinte", on_click=lambda e: mudar_semana(7)),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=2,
    )
    botoes = ft.Row(
        [
            comp.botao("WhatsApp" if app.desktop else "Compartilhar", lambda e: app.page.run_task(whatsapp), ft.Icons.SHARE_OUTLINED),
            comp.botao_contorno("Salvar imagem" if app.desktop else "Salvar ou enviar", lambda e: app.page.run_task(salvar), ft.Icons.DOWNLOAD_OUTLINED),
            comp.botao_texto("Copiar legenda", lambda e: app.page.run_task(copiar_legenda), ft.Icons.CONTENT_COPY),
        ],
        wrap=True,
        spacing=8,
        run_spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    corpo = ft.Column(
        [
            setas,
            ft.Container(previa, alignment=ft.Alignment.CENTER),
            comp.apagado("Só os números de estudo e o personagem entram na imagem: nada de e-mail nem nome completo.", c, 12.5),
            botoes,
            aviso,
        ],
        spacing=12,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        scroll=ft.ScrollMode.AUTO,
    )
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Minha semana", font_family=FONTE_TITULO),
            content=ft.Container(corpo, width=largura),
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
        )
    )
    app.page.run_task(gerar)
