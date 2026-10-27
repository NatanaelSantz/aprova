"""Mini prova de uma disciplina (ex.: Conhecimentos Específicos), aberta pelo "Onde focar" da tela Início."""

from __future__ import annotations

import flet as ft

from .. import sessoes
from . import comp
from .tema import FONTE_TITULO

MINUTOS_POR_QUESTAO = 3  # referência comum em provas objetivas de concurso
QUANTIDADES = (5, 10, 20, 30)
TODAS_ATE = 60  # "Todas" só aparece quando não vira uma prova inteira


def opcoes_quantidade(total: int) -> list[tuple[int, str]]:
    """Botões de quantidade para quem tem `total` questões: 5, 10, 20, 30 e "Todas (n)"."""
    if total <= 0:
        return []
    opcoes = [(n, str(n)) for n in QUANTIDADES if n < total]
    if total <= TODAS_ATE or not opcoes:
        opcoes.append((total, f"Todas ({total})"))
    return opcoes


def quantidade_padrao(total: int) -> int:
    return min(10, total) if total else 0


def abrir_mini_prova(app, disciplina: str, taxa: float | None = None) -> None:
    c = app.c
    dados = sessoes.opcoes_mini_prova(app.db, disciplina)
    largura = min(520, (app.page.width or 600) - 40)
    estado = {"prova": None, "qtd": quantidade_padrao(dados["total"]), "modo": "simulado"}

    def total_atual() -> int:
        if estado["prova"] is None:
            return dados["total"]
        return next((p["questoes"] for p in dados["provas"] if p["prova_id"] == estado["prova"]), 0)

    def novas_atual() -> int:
        if estado["prova"] is None:
            return dados["novas"]
        return next((p["novas"] for p in dados["provas"] if p["prova_id"] == estado["prova"]), 0)

    cabecalho = ft.Column(
        [
            comp.apagado("Mini prova", c, 13.5),
            ft.Text(disciplina, size=23, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
        ],
        spacing=0,
    )

    if not dados["total"]:
        app.page.show_dialog(
            ft.AlertDialog(
                title=cabecalho,
                content=ft.Column(
                    [
                        comp.aviso(
                            f"Ainda não há questões de {disciplina} com o texto na sua biblioteca (provas só com cartão-resposta não servem). "
                            "Importe uma prova que tenha essa disciplina e volte aqui.",
                            c,
                            "alerta",
                        )
                    ],
                    tight=True,
                    width=largura,
                ),
                actions=[
                    ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog()),
                    comp.botao("Ir para Estudar", lambda e: (app.page.pop_dialog(), app.ir("estudar")), ft.Icons.LIBRARY_BOOKS_OUTLINED),
                ],
            )
        )
        return

    resumo = comp.apagado("", c, 14)
    linha_qtd = ft.Row(wrap=True, spacing=6, run_spacing=6)
    linha_modo = ft.Row(wrap=True, spacing=10, run_spacing=10)
    tempo = comp.apagado("", c, 13)

    def chip(rotulo: str, marcado: bool, ao_clicar) -> ft.Container:
        return ft.Container(
            ft.Text(rotulo, size=14, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if marcado else c["texto"]),
            bgcolor=c["tinta"] if marcado else c["sup2"],
            border_radius=999,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            on_click=ao_clicar,
            ink=True,
        )

    def cartao_modo(chave: str, icone, titulo: str, texto: str) -> ft.Container:
        marcado = estado["modo"] == chave
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(icone, color=c["tinta"] if marcado else c["texto2"], size=24),
                    ft.Column(
                        [
                            ft.Text(titulo, size=15, weight=ft.FontWeight.W_700, color=c["texto"]),
                            ft.Text(texto, size=12.5, color=c["texto2"]),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            width=(largura - 10) / 2 if largura >= 420 else largura,
            bgcolor=c["tinta_suave"] if marcado else None,
            border=ft.Border.all(1.6, c["tinta"] if marcado else c["borda"]),
            border_radius=12,
            padding=12,
            on_click=lambda e, k=chave: mudar("modo", k),
            ink=True,
        )

    def atualizar():
        total, novas = total_atual(), novas_atual()
        partes = [f"{total} {'questão' if total == 1 else 'questões'} {'nesta prova' if estado['prova'] else 'na sua biblioteca'}"]
        if novas == total:
            partes.append("nenhuma feita ainda" if total > 1 else "ainda não feita")
        elif novas:
            partes.append(f"{novas} que você ainda não fez")
        else:
            partes.append("você já fez todas (vêm primeiro as que errou)")
        texto = ", ".join(partes) + "."
        if taxa is not None:
            texto += f" Você acerta {taxa * 100:.0f}% nesta disciplina."
        resumo.value = texto
        opcoes = opcoes_quantidade(total)
        if estado["qtd"] not in [n for n, _ in opcoes]:
            estado["qtd"] = quantidade_padrao(total) if quantidade_padrao(total) in [n for n, _ in opcoes] else opcoes[-1][0]
        linha_qtd.controls = [chip(r, estado["qtd"] == n, lambda e, n=n: mudar("qtd", n)) for n, r in opcoes]
        linha_modo.controls = [
            cartao_modo("simulado", ft.Icons.TIMER_OUTLINED, "Prova", "Com cronômetro. A nota sai no fim, como no dia da prova."),
            cartao_modo("estudo", ft.Icons.LIGHTBULB_OUTLINE, "Estudo", "Vê se acertou a cada questão, com a explicação."),
        ]
        minutos = estado["qtd"] * MINUTOS_POR_QUESTAO
        tempo.value = f"Tempo de referência: {minutos} min ({MINUTOS_POR_QUESTAO} min por questão)." if estado["modo"] == "simulado" else ""
        tempo.visible = estado["modo"] == "simulado"
        try:
            corpo.update()
        except Exception:  # noqa: BLE001 - ainda não está na tela
            pass

    def mudar(chave: str, valor):
        estado[chave] = valor
        atualizar()

    filhos: list[ft.Control] = [resumo]
    if len(dados["provas"]) > 1:
        filhos.append(
            ft.Dropdown(
                label="De qual prova",
                value="todas",
                options=[ft.DropdownOption(key="todas", text=f"Todas as provas da biblioteca ({dados['total']})")]
                + [ft.DropdownOption(key=str(p["prova_id"]), text=f"{p['titulo'][:58]} ({p['questoes']})") for p in dados["provas"][:30]],
                on_select=lambda e: mudar("prova", None if e.control.value in (None, "todas") else int(e.control.value)),
                dense=True,
                border_radius=10,
                width=largura,
            )
        )
    filhos += [
        comp.texto("Quantas questões", c, 14, peso=ft.FontWeight.W_700),
        linha_qtd,
        comp.texto("Como fazer", c, 14, peso=ft.FontWeight.W_700),
        linha_modo,
        tempo,
    ]
    corpo = ft.Column(filhos, spacing=10, tight=True, width=largura)

    def comecar(e):
        pid = sessoes.preparar_treino(app.db, disciplina, estado["qtd"], estado["prova"], titulo=f"Mini prova · {disciplina}")
        app.page.pop_dialog()
        if not pid:
            comp.mensagem(app.page, f"Não encontrei questões de {disciplina} para a mini prova.")
            return
        from .estudar import abrir_prova

        abrir_prova(app, pid, estado["modo"])

    atualizar()
    app.page.show_dialog(
        ft.AlertDialog(
            title=cabecalho,
            content=corpo,
            scrollable=True,  # janela baixa (celular): rola em vez de cortar
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()),
                comp.botao("Começar", comecar, ft.Icons.PLAY_ARROW_ROUNDED),
            ],
        )
    )
