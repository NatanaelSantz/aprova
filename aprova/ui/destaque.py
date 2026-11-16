"""Aviso de novidade vindo do site (ex.: vídeo novo): janela com o seu personagem, uma vez, e cartão no Início."""

from __future__ import annotations

import asyncio
import time

import flet as ft

from .. import config, destaque
from . import comp
from .tema import FONTE_TITULO

INTERVALO = 6 * 3600  # o versao.json é um arquivinho: confere a cada 6 horas com o app aberto
AZUL = ("#14213D", "#2340A8")
OURO = "#FFD84D"


def atual(app) -> dict | None:
    """O destaque guardado (confere de novo: pode ter vencido desde que chegou)."""
    return destaque.ler(app.sessao.get("destaque") or None)


def _lista(app, chave: str) -> list:
    return list(app.aj.get(chave, []) or [])


def _anotar(app, chave: str, ident: str) -> None:
    v = _lista(app, chave)
    if ident not in v:
        v.append(ident)
        app.aj.set(chave, v[-30:])


def pendente(app) -> dict | None:
    """O destaque que ainda vale um cartão no Início (não assistiu nem fechou)."""
    d = atual(app)
    return d if d and d["id"] not in _lista(app, "destaques_fechados") else None


async def carregar(app, forcar: bool = False) -> dict | None:
    from .atualizacao import url_versao

    agora = time.time()
    if forcar or agora - float(app.sessao.get("destaque_em") or 0) >= INTERVALO:
        d = await app.em_segundo_plano(destaque.buscar, url_versao(), 8)
        app.sessao.set("destaque_em", agora)
        app.sessao.set("destaque", d or {})
        _atualizar_inicio(app)
    return atual(app)


def _janela_aberta(app) -> bool:
    dialogos = getattr(getattr(app.page, "_dialogs", None), "controls", None) or []
    return any(getattr(d, "open", False) for d in dialogos)


async def vigiar(app) -> None:
    """Roda em segundo plano: busca o destaque e mostra a janela uma vez, quando a pessoa estiver livre."""
    await asyncio.sleep(7)  # deixa o aviso de "atualizado" e o resto da abertura passarem primeiro
    primeira = True
    while True:
        try:
            await carregar(app, forcar=primeira)
        except Exception as e:  # noqa: BLE001 - sem internet: tenta de novo mais tarde
            config.registrar(f"destaque: não deu para buscar ({e!r})")
        primeira = False
        d = pendente(app)
        if d and d["id"] not in _lista(app, "destaques_mostrados"):
            for _ in range(360):  # espera sair da prova, do login e de outra janela (até 30 min)
                if app.foco is None and not app.em_login and not _janela_aberta(app):
                    break
                await asyncio.sleep(5)
            else:
                d = None
            if d:
                mostrar(app, d)
        await asyncio.sleep(INTERVALO + 60)


def _atualizar_inicio(app) -> None:
    t = app.telas.get("inicio") if hasattr(app, "telas") else None
    if t is not None and hasattr(t, "atualizar_topo") and app.secao == "inicio" and app.foco is None:
        t.atualizar_topo()


def assistir(app, d: dict) -> None:
    _anotar(app, "destaques_mostrados", d["id"])
    _anotar(app, "destaques_fechados", d["id"])
    app.page.run_task(app.abrir_url, d["link"])
    _atualizar_inicio(app)


def fechar(app, d: dict) -> None:
    _anotar(app, "destaques_fechados", d["id"])
    _atualizar_inicio(app)


# ---------------------------------------------------------------- desenho


def _boneco(app, escala: int) -> ft.Control:
    from .personagem import _pixel, img_sozinho, meu

    try:
        return _pixel(img_sozinho(meu(app), "aceno", escala), 64 * escala, 80 * escala)
    except Exception:  # noqa: BLE001 - sem o personagem, fica o ícone
        return ft.Icon(ft.Icons.SMART_DISPLAY, size=40 * escala, color=ft.Colors.WHITE)


def _balao(texto: str, tamanho: float) -> ft.Control:
    return ft.Container(
        ft.Text(texto, size=tamanho, weight=ft.FontWeight.W_700, color="#1F1A2E"),
        bgcolor=ft.Colors.WHITE,
        border_radius=ft.BorderRadius.only(top_left=14, top_right=14, bottom_right=14, bottom_left=4),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        shadow=ft.BoxShadow(blur_radius=0, spread_radius=0, offset=ft.Offset(3, 3), color="#33000000"),
    )


def _selo(texto: str) -> ft.Control:
    return ft.Container(
        ft.Text(texto, size=11.5, weight=ft.FontWeight.W_800, color="#1F1A2E"),
        bgcolor=OURO,
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
    )


def _play(tamanho: float, ao_clicar=None) -> ft.Control:
    return ft.Container(
        ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=tamanho * 0.62, color=AZUL[1]),
        width=tamanho,
        height=tamanho,
        bgcolor=ft.Colors.WHITE,
        border_radius=tamanho / 2,
        alignment=ft.Alignment.CENTER,
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=2, color="#6614213D"),
        on_click=ao_clicar,
        tooltip="Assistir",
    )


def mostrar(app, d: dict) -> None:
    """A janela de novidade: cabeçalho azul com o seu personagem acenando, os destaques e o botão de assistir."""
    _anotar(app, "destaques_mostrados", d["id"])
    c = app.c
    estreito = (app.page.width or 800) < 560
    largura = min(500, (app.page.width or 540) - 40)

    def ir(e=None):
        app.page.pop_dialog()
        assistir(app, d)

    def depois(e=None):
        app.page.pop_dialog()
        _atualizar_inicio(app)

    cabeca = ft.Container(
        ft.Row(
            [
                _boneco(app, 2 if not estreito else 1),
                ft.Column(
                    [_selo("NOVIDADE"), _balao(d["fala"] or "Saiu vídeo novo! Bora ver?", 15 if not estreito else 13.5)],
                    spacing=10,
                    expand=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                _play(64 if not estreito else 48, ir),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=list(AZUL)),
        border_radius=18,
        padding=ft.Padding.only(left=14, right=18, top=12, bottom=12),
    )
    itens = ft.Row(
        [comp.pilula(i, c["tinta_suave"], c["tinta"], ft.Icons.AUTO_AWESOME, 13) for i in d["itens"]],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )
    corpo = ft.Column(
        [
            cabeca,
            ft.Text(d["titulo"], font_family=FONTE_TITULO, size=24 if not estreito else 21, weight=ft.FontWeight.W_600, color=c["texto"]),
            *([ft.Text(d["texto"], size=15, color=c["texto"])] if d["texto"] else []),
            *([itens] if d["itens"] else []),
        ],
        spacing=14,
        tight=True,
    )
    app.page.show_dialog(
        ft.AlertDialog(
            content=ft.Container(corpo, width=largura),
            actions=[comp.botao_texto("Depois", depois), comp.botao(d["botao"], ir, ft.Icons.PLAY_CIRCLE_FILL_ROUNDED)],
            actions_alignment=ft.MainAxisAlignment.END,
            content_padding=ft.Padding.only(left=18, right=18, top=18, bottom=6),
            scrollable=True,
            on_dismiss=lambda e: _atualizar_inicio(app),
        )
    )


def cartao_inicio(app) -> list[ft.Control]:
    """Faixa azul no Início até assistir ou fechar."""
    d = pendente(app)
    if not d:
        return []
    largo = app.largo
    texto = ft.Column(
        [
            *([ft.Row([_selo("NOVIDADE"), ft.Text(d["titulo"], size=16, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE, expand=True)], spacing=10)] if largo
              else [_selo("NOVIDADE"), ft.Text(d["titulo"], size=16, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE)]),
            *([ft.Text(d["texto"], size=14, color="#D9E0FF")] if d["texto"] else []),
        ],
        spacing=6,
        expand=True,
    )
    botao = ft.FilledButton(
        d["botao"],
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        on_click=lambda e: assistir(app, d),
        style=ft.ButtonStyle(bgcolor=ft.Colors.WHITE, color=AZUL[1], shape=comp.forma(10), padding=ft.Padding.symmetric(horizontal=18, vertical=14)),
    )
    x = ft.IconButton(ft.Icons.CLOSE, icon_color="#D9E0FF", icon_size=18, tooltip="Fechar", on_click=lambda e: fechar(app, d))
    if largo:
        linha = ft.Row([_boneco(app, 1), texto, botao, x], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    else:
        linha = ft.Column(
            [ft.Row([_boneco(app, 1), texto, x], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START), botao],
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    return [
        ft.Container(
            linha,
            gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT, colors=list(AZUL)),
            border_radius=16,
            padding=ft.Padding.only(left=14, right=8, top=10, bottom=10),
        )
    ]
