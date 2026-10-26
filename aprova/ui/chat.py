"""Botões "Perguntar ao Claude / ao ChatGPT" e o passo a passo da chave da IA."""

from __future__ import annotations

import flet as ft

from .. import chat_ia
from . import comp
from .tema import FONTE_TITULO


async def abrir_chat(app, servico: str, pergunta: str) -> None:
    """Copia a pergunta e abre o chat no navegador (com a pergunta já escrita quando cabe no link)."""
    try:
        await ft.Clipboard().set(pergunta)
    except Exception:  # noqa: BLE001 - sem área de transferência (ex.: celular): o link ainda leva a pergunta
        pass
    nome = chat_ia.SERVICOS[servico][0]
    await app.abrir_url(chat_ia.link(servico, pergunta))
    app.msg(f"Abrindo o {nome}… A pergunta também foi copiada: se o chat abrir vazio, cole com Ctrl+V e envie.")


def botoes_chat(app, pergunta, rotulo: str = "Perguntar") -> ft.Control:
    """Dois botões lado a lado. pergunta: texto ou função que monta o texto na hora do clique."""

    def clicar(servico):
        def _f(e):
            texto = pergunta() if callable(pergunta) else pergunta
            app.page.run_task(abrir_chat, app, servico, texto)

        return _f

    return ft.Row(
        [
            comp.botao_contorno(f"{rotulo} ao Claude", clicar("claude"), ft.Icons.AUTO_AWESOME_OUTLINED),
            comp.botao_contorno(f"{rotulo} ao ChatGPT", clicar("chatgpt"), ft.Icons.CHAT_OUTLINED),
        ],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )


def menu_chat(app, pergunta, rotulo: str = "Perguntar à IA") -> ft.Control:
    """Versão compacta (um botão com as duas opções), para listas."""
    c = app.c

    def escolher(servico):
        return lambda e: app.page.run_task(abrir_chat, app, servico, pergunta() if callable(pergunta) else pergunta)

    return ft.PopupMenuButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED, size=18, color=c["tinta"]), ft.Text(rotulo, size=14, color=c["tinta"], weight=ft.FontWeight.W_600)],
            spacing=6,
            tight=True,
        ),
        items=[
            ft.PopupMenuItem(content="No Claude", icon=ft.Icons.AUTO_AWESOME_OUTLINED, on_click=escolher("claude")),
            ft.PopupMenuItem(content="No ChatGPT", icon=ft.Icons.CHAT_OUTLINED, on_click=escolher("chatgpt")),
        ],
        tooltip="Abre o chat com a questão já escrita",
    )


PASSOS_CHAVE = [
    ("Crie a conta no Claude Console",
     "Entre em platform.claude.com e crie uma conta (ou entre com a sua). É o site do Claude para programadores, diferente do chat.",
     ("Abrir o Claude Console", "https://platform.claude.com/")),
    ("Coloque crédito",
     "Em Billing, coloque um valor com cartão. É pré-pago: você só gasta o que colocou. A assinatura do Claude (Pro) não inclui esse crédito; "
     "os planos Max e Team vêm com um crédito por mês.",
     None),
    ("Crie a chave",
     "Em API keys, clique em Create key e dê o nome Aprova. A chave começa com sk-ant- e aparece uma vez só: copie na hora "
     "(se perder, é só criar outra).",
     ("Abrir a página das chaves", "https://platform.claude.com/settings/keys")),
    ("Cole no Aprova",
     "Volte aqui, cole a chave no campo e clique em Salvar. Pronto: explicações, questões novas nos simulados e a análise do professor passam a funcionar.",
     None),
]


def dialogo_chave(app) -> None:
    """Passo a passo para conseguir a chave do Claude, e o caminho sem chave (chat no navegador)."""
    c = app.c
    passos: list[ft.Control] = []
    for i, (titulo, texto, botao) in enumerate(PASSOS_CHAVE, start=1):
        coluna: list[ft.Control] = [ft.Text(titulo, size=15.5, weight=ft.FontWeight.W_700, color=c["texto"]), comp.apagado(texto, c, 13.5)]
        if botao:
            coluna.append(comp.botao_texto(botao[0], url=botao[1], icone=ft.Icons.OPEN_IN_NEW))
        passos.append(
            ft.Row(
                [
                    ft.Container(ft.Text(str(i), color=c["sobre_tinta"], weight=ft.FontWeight.W_700),
                                 width=30, height=30, border_radius=15, bgcolor=c["tinta"], alignment=ft.Alignment.CENTER),
                    ft.Column(coluna, spacing=4, expand=True),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
    cuidados = comp.aviso(
        "A chave é como um cartão: quem tiver a chave gasta o seu crédito. Não mande no grupo nem mostre em print. "
        "Ela fica guardada só neste computador.",
        c,
        "alerta",
    )
    sem_chave = ft.Container(
        ft.Column(
            [
                ft.Text("Sem chave também dá", size=15.5, weight=ft.FontWeight.W_700, color=c["texto"]),
                comp.apagado(
                    "Na ajuda de cada questão e no resultado do simulado, os botões Perguntar ao Claude e Perguntar ao ChatGPT "
                    "abrem o chat no navegador com a pergunta já escrita. Funciona com a conta grátis de cada um.",
                    c,
                    13.5,
                ),
            ],
            spacing=4,
        ),
        bgcolor=c["sup2"],
        border_radius=12,
        padding=14,
    )
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Como ligar a IA no Aprova", font_family=FONTE_TITULO, size=21),
            content=ft.Container(
                ft.Column([*passos, cuidados, sem_chave], spacing=16, tight=True, scroll=ft.ScrollMode.AUTO),
                width=min(560, (app.page.width or 600) - 48),
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
            scrollable=True,
        )
    )
