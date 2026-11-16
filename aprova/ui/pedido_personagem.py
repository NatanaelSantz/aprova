"""Pedido para criar o personagem: o admin aperta um botão e quem ainda está com o boneco sorteado recebe o convite.

O pedido fica no servidor (tabela config, chave "pedido_personagem"), como {"id", "texto", "quando"}. Cada pessoa logada
que ainda não criou o personagem vê a janela uma vez por pedido; um pedido novo (id novo) aparece de novo.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date

import flet as ft

from .. import avatar as av
from .. import config
from .. import ranking as rk
from . import comp
from .tema import FONTE_TITULO

CHAVE = "pedido_personagem"
TEXTO_PADRAO = "A turma quer ver você na sala! Leva um minuto: escolha o corpo, o cabelo, a roupa e um item para a mão."
AZUL = ("#14213D", "#2340A8")


def ler(valor: str) -> dict | None:
    """Confere o pedido guardado no servidor (texto vindo de lá: só entra o formato esperado)."""
    try:
        d = json.loads(valor) if valor else None
    except ValueError:
        return None
    if not isinstance(d, dict) or not re.fullmatch(r"[a-z0-9-]{1,40}", str(d.get("id") or "")):
        return None
    texto = " ".join(str(d.get("texto") or "").split())[:200] or TEXTO_PADRAO
    quando = str(d.get("quando") or "")
    return {"id": d["id"], "texto": texto, "quando": quando if re.fullmatch(r"\d{4}-\d{2}-\d{2}", quando) else ""}


def novo(texto: str) -> str:
    """O valor a gravar no servidor para um pedido novo."""
    return json.dumps({"id": f"p{int(time.time())}", "texto": " ".join((texto or "").split())[:200] or TEXTO_PADRAO,
                       "quando": date.today().isoformat()}, ensure_ascii=False)


def precisa(app, pedido: dict | None) -> bool:
    """Mostra a janela? Só para quem está logado, sem personagem e ainda não viu este pedido."""
    from .personagem import tenho_personagem

    return bool(pedido and app.ranking.logado and not tenho_personagem(app) and pedido["id"] not in (app.aj.get("pedidos_personagem_vistos", []) or []))


def _janela_aberta(app) -> bool:
    dialogos = getattr(getattr(app.page, "_dialogs", None), "controls", None) or []
    return any(getattr(d, "open", False) for d in dialogos)


async def vigiar(app) -> None:
    """Ao abrir (logado): busca o pedido e, se for o caso, mostra a janela quando a pessoa estiver livre."""
    await asyncio.sleep(9)  # depois do aviso de versão nova e da novidade do site
    try:
        pedido = ler(await app.em_segundo_plano(app.ranking.config_valor, CHAVE))
    except Exception as e:  # noqa: BLE001 - sem internet: fica para a próxima abertura
        config.registrar(f"pedido de personagem: {e!r}")
        return
    if not precisa(app, pedido):
        return
    for _ in range(360):  # espera sair da prova, do login e de outra janela (até 30 min)
        if app.foco is None and not app.em_login and not _janela_aberta(app):
            mostrar(app, pedido)
            return
        await asyncio.sleep(5)


def mostrar(app, pedido: dict) -> None:
    """A janela: o boneco sorteado (o que a turma vê hoje) pedindo para virar o seu."""
    from .personagem import _pixel, abrir_criador, img_sozinho

    v = list(app.aj.get("pedidos_personagem_vistos", []) or [])
    if pedido["id"] not in v:
        app.aj.set("pedidos_personagem_vistos", (v + [pedido["id"]])[-20:])
    c = app.c
    estreito = (app.page.width or 800) < 560
    sorteado = av.sortear(app.ranking.usuario_id or app.aj.get("nome") or "visitante-aprova")
    nome = (getattr(app, "nome_saudacao", "") or "").split(" ")[0]

    def criar(e=None):
        app.page.pop_dialog()
        abrir_criador(app)

    balao = ft.Container(
        ft.Text("Psiu! Eu sou um boneco sorteado. Troca por um com a sua cara?", size=14 if not estreito else 13, weight=ft.FontWeight.W_700, color="#1F1A2E"),
        bgcolor=ft.Colors.WHITE,
        border_radius=ft.BorderRadius.only(top_left=14, top_right=14, bottom_right=14, bottom_left=4),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        expand=True,
    )
    cabeca = ft.Container(
        ft.Row([_pixel(img_sozinho(sorteado, "aceno", 2 if not estreito else 1), 128 if not estreito else 64, 160 if not estreito else 80), balao],
               spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=list(AZUL)),
        border_radius=18,
        padding=ft.Padding.only(left=14, right=18, top=12, bottom=12),
    )
    corpo = ft.Column(
        [
            cabeca,
            ft.Text(f"{nome}, monte o seu personagem" if nome else "Monte o seu personagem", font_family=FONTE_TITULO, size=23 if not estreito else 20,
                    weight=ft.FontWeight.W_600, color=c["texto"]),
            ft.Text(pedido["texto"], size=15, color=c["texto"]),
            comp.apagado("Ele aparece na sala da turma, no ranking e comemora com você no resultado do simulado.", c, 13.5),
        ],
        spacing=12,
        tight=True,
    )
    app.page.show_dialog(
        ft.AlertDialog(
            content=ft.Container(corpo, width=min(480, (app.page.width or 520) - 40)),
            actions=[comp.botao_texto("Agora não", lambda e: app.page.pop_dialog()), comp.botao("Criar meu personagem", criar, ft.Icons.AUTO_FIX_HIGH)],
            actions_alignment=ft.MainAxisAlignment.END,
            content_padding=ft.Padding.only(left=18, right=18, top=18, bottom=6),
            scrollable=True,
        )
    )


# ---------------------------------------------------------------- admin


def linha_admin(tela, sem: int) -> ft.Control | None:
    """Admin → Personagens: quantas pessoas estão sem personagem e o botão de pedir que criem."""
    if sem <= 0:
        return None
    app, c = tela.app, tela.app.c
    enviado = getattr(tela, "pedido_personagem", None)
    quando = ""
    if enviado and enviado.get("quando"):
        a, m, d = enviado["quando"].split("-")
        quando = f" Último pedido: {d}/{m}."
    texto = ft.Column(
        [
            ft.Text(f"{sem} pessoa{'s' if sem != 1 else ''} sem personagem", size=15, weight=ft.FontWeight.W_700, color=c["texto"]),
            comp.apagado("Nos grupos elas aparecem com um boneco sorteado." + quando, c, 13),
        ],
        spacing=2,
        expand=True,
    )
    bt = comp.botao("Pedir para criarem", lambda e: dialogo_admin(tela), ft.Icons.CAMPAIGN_OUTLINED)
    linha = ft.Row([ft.Icon(ft.Icons.FACE_RETOUCHING_NATURAL, color=c["tinta"], size=26), texto, bt], spacing=12,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER) if app.largo else \
        ft.Column([ft.Row([ft.Icon(ft.Icons.FACE_RETOUCHING_NATURAL, color=c["tinta"], size=26), texto], spacing=12), bt], spacing=10)
    return ft.Container(linha, bgcolor=c["tinta_suave"], border_radius=14, padding=ft.Padding.only(left=16, right=12, top=12, bottom=12))


def dialogo_admin(tela) -> None:
    app, c = tela.app, tela.app.c
    campo = ft.TextField(label="Mensagem", value=TEXTO_PADRAO, multiline=True, min_lines=2, max_lines=4, max_length=200, border_radius=10)
    msg = ft.Container()

    async def enviar(e):
        valor = novo(campo.value or "")
        try:
            await app.em_segundo_plano(app.ranking.config_salvar, CHAVE, valor)
        except rk.ErroRanking as ex:
            msg.content = comp.aviso(str(ex), c, "erro")
            app.page.update()
            return
        tela.pedido_personagem = ler(valor)
        app.page.pop_dialog()
        app.msg("Pedido enviado: quem ainda está sem personagem vê o convite na próxima vez que abrir o Aprova.")
        tela._redesenhar()

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Pedir para criarem o personagem", font_family=FONTE_TITULO, size=21),
            content=ft.Container(
                ft.Column(
                    [
                        comp.apagado("Quem está logado e ainda não criou o personagem vê uma janela com esta mensagem, uma vez, na próxima vez que abrir o "
                                     "Aprova. Quem já tem personagem não vê nada.", c, 13.5),
                        campo,
                        msg,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=min(480, (app.page.width or 520) - 48),
            ),
            actions=[comp.botao_texto("Cancelar", lambda e: app.page.pop_dialog()), comp.botao("Enviar pedido", enviar, ft.Icons.SEND)],
            scrollable=True,
        )
    )


async def carregar_admin(tela) -> None:
    """Admin: lê o último pedido (para mostrar a data)."""
    try:
        tela.pedido_personagem = ler(await tela.app.em_segundo_plano(tela.app.ranking.config_valor, CHAVE))
    except Exception:  # noqa: BLE001
        return
    if tela.aba == "personagens":
        tela._redesenhar()
