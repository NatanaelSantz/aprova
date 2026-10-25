"""Janela "Encher a biblioteca": baixa de uma vez as provas de um concurso."""

from __future__ import annotations

import re

import flet as ft

from .. import coleta, fontes
from . import comp
from .tema import FONTE_TITULO


def filtro_do_concurso(termo: str) -> str:
    """'Dataprev 2026' -> 'Dataprev' (para montar simulados com todas as edições)."""
    if termo.startswith("http"):
        return ""
    return coleta.nome_curto(re.sub(r"\b20\d\d\b", "", termo).strip()) or termo


def pedir_concurso(app) -> None:
    """Pergunta o concurso e abre a coleta (usado na tela Estudar)."""
    c = app.c
    campo = ft.TextField(
        label="Concurso",
        hint_text="Ex.: Dataprev 2026, TJ-PB, CNU",
        autofocus=True,
        border_radius=10,
        prefix_icon=ft.Icons.SEARCH,
    )
    sugestoes = []
    for f in app.db.favoritos()[:6]:
        nome = (f.get("nome") or "").split(" - ")[0].strip()
        if nome:
            sugestoes.append(nome)

    def ir(e=None, termo: str | None = None):
        t = (termo or campo.value or "").strip()
        if not t:
            campo.error = "Digite o nome do concurso"
            campo.update()
            return
        app.page.pop_dialog()
        abrir_coleta(app, t)

    campo.on_submit = ir
    chips = ft.Row(
        [ft.OutlinedButton(s, on_click=lambda e, s=s: ir(termo=s)) for s in sugestoes],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Encher a biblioteca", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado(
                        "Escolha o concurso. O Aprova procura as provas das últimas edições, de todos os cargos, "
                        "e importa com o gabarito oficial.",
                        c,
                        14,
                    ),
                    campo,
                ]
                + ([comp.apagado("Concursos que você acompanha:", c, 13), chips] if sugestoes else []),
                tight=True,
                spacing=12,
                width=min(520, (app.page.width or 600) - 40),
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Procurar provas", ir, ft.Icons.TRAVEL_EXPLORE)],
        )
    )


def abrir_coleta(app, termo: str, resultado: fontes.Resultado | None = None) -> None:
    app.page.run_task(_coleta, app, termo, resultado)


async def _coleta(app, termo: str, resultado: fontes.Resultado | None) -> None:
    c = app.c
    largura = min(660, (app.page.width or 700) - 40)
    altura_lista = max(220, min(430, (app.page.height or 760) - 330))
    estado = {"parar": False, "plano": None}
    texto_passo = comp.apagado("Procurando as provas do concurso…", c, 14)
    barra = ft.ProgressBar(value=None, color=c["tinta"], bgcolor=c["sup2"], border_radius=4, bar_height=6)
    corpo = ft.Column([ft.Row([ft.ProgressRing(width=18, height=18, stroke_width=2.2, color=c["tinta"]), texto_passo], spacing=12)], tight=True, spacing=14, width=largura)
    titulo = ft.Column(
        [
            ft.Text("Encher a biblioteca", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            comp.apagado(termo if not termo.startswith("http") else "Página colada", c, 13.5),
        ],
        tight=True,
        spacing=2,
    )
    dlg = ft.AlertDialog(title=titulo, content=corpo, actions=[ft.TextButton("Cancelar", on_click=lambda e: fechar())])
    app.page.show_dialog(dlg)

    def fechar():
        estado["parar"] = True
        app.page.pop_dialog()

    def progresso(f, texto):
        texto_passo.value = texto
        if f is not None:
            barra.value = max(0.0, min(1.0, f))
        try:
            corpo.update()
        except Exception:  # noqa: BLE001 - janela fechada
            pass

    try:
        plano: coleta.Plano = await app.em_segundo_plano(coleta.planejar, app.central, app.db, termo, resultado, lambda f, t: progresso(None, t))
    except Exception as ex:  # noqa: BLE001
        corpo.controls = [comp.aviso(f"Não consegui procurar as provas: {ex}", c, "erro")]
        dlg.actions = [ft.TextButton("Fechar", on_click=lambda e: fechar())]
        app.page.update()
        return
    if estado["parar"]:
        return
    estado["plano"] = plano
    _mostrar_escolha(app, dlg, corpo, plano, largura, altura_lista, estado, texto_passo, barra, progresso, fechar)


def _mostrar_escolha(app, dlg, corpo, plano: coleta.Plano, largura, altura_lista, estado, texto_passo, barra, progresso, fechar) -> None:
    c = app.c
    if not plano.itens:
        corpo.controls = [
            comp.vazio(
                ft.Icons.SEARCH_OFF,
                "Não achei provas com link direto",
                "Para este concurso não encontrei PDFs que dê para baixar sozinho. As provas do PCI Concursos "
                "pedem a verificação no navegador; baixe-as uma por uma na aba Provas.",
                c,
            )
        ] + [comp.aviso(a, c, "alerta") for a in plano.avisos[:2]]
        dlg.actions = [ft.TextButton("Fechar", on_click=lambda e: fechar())]
        app.page.update()
        return

    caixas: list[tuple[ft.Checkbox, coleta.Item, ft.Control]] = []
    contador = comp.texto("", c, 14.5, peso=ft.FontWeight.W_600)
    botao_ir = comp.botao("Baixar e importar", None, ft.Icons.DOWNLOAD_ROUNDED)

    def recontar(e=None):
        n = sum(1 for cx, _, _ in caixas if cx.value and not cx.disabled)
        contador.value = f"{n} prova{'s' if n != 1 else ''} marcada{'s' if n != 1 else ''}"
        botao_ir.disabled = n == 0
        botao_ir.content = f"Baixar e importar ({n})" if n else "Baixar e importar"
        try:
            corpo.update()
            botao_ir.update()
        except Exception:  # noqa: BLE001
            pass

    def marcar_todos(valor: bool):
        for cx, it, linha in caixas:
            if not cx.disabled and linha.visible:
                cx.value = valor
        recontar()

    def filtrar(e):
        alvo = fontes.norm(e.control.value or "")
        for cx, it, linha in caixas:
            linha.visible = not alvo or all(p in fontes.norm(it.cargo + " " + it.edicao) for p in alvo.split())
        corpo.update()

    n_ed = len({i.edicao for i in plano.itens})
    lista = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=min(altura_lista, 44 * len(plano.itens) + 46 * n_ed + 16))
    edicao_atual = None
    for it in plano.itens:
        if it.edicao != edicao_atual:
            edicao_atual = it.edicao
            da_edicao = [i for i in plano.itens if i.edicao == it.edicao]
            rotulo = it.edicao + (f" · {it.banca}" if it.banca else "")
            lista.controls.append(
                ft.Container(
                    ft.Row(
                        [
                            comp.texto(rotulo, c, 15, peso=ft.FontWeight.W_700),
                            comp.apagado(f"{len(da_edicao)} cargo{'s' if len(da_edicao) != 1 else ''}" if it.oficial else "podem vir sem gabarito", c, 13),
                        ],
                        spacing=10,
                    ),
                    padding=ft.Padding.only(top=12, bottom=4, left=4),
                )
            )
        cx = ft.Checkbox(value=it.marcado, disabled=it.ja_tem, on_change=recontar)
        if it.ja_tem:
            selo = comp.pilula("já na biblioteca", c["ok_suave"], c["ok"], ft.Icons.CHECK)
        elif it.gabarito:
            selo = comp.pilula("com gabarito", c["sup2"], c["texto2"])
        else:
            selo = comp.pilula("sem gabarito", c["marca_suave"], c["marca"])
        linha = ft.Container(
            ft.Row(
                [cx, ft.Text(it.cargo, size=14.5, color=c["texto"], expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS), selo],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(vertical=1),
            on_click=lambda e, cx=cx: (setattr(cx, "value", not cx.value), recontar()) if not cx.disabled else None,
        )
        caixas.append((cx, it, linha))
        lista.controls.append(linha)

    oficiais = [i for i in plano.itens if i.oficial]
    edicoes = [e for e in plano.edicoes() if e != "Outros sites"]
    explicacao = (
        f"Achei {len(oficiais)} prova{'s' if len(oficiais) != 1 else ''} de {len(edicoes)} edição{'ões' if len(edicoes) != 1 else ''} "
        "no site oficial. De cada cargo entra um caderno: os outros tipos têm as mesmas questões em outra ordem. "
        "Questões repetidas entre cargos (como Português) aparecem uma vez só nos simulados."
    )
    corpo.controls = [
        comp.apagado(explicacao, c, 13.5),
        ft.Row(
            [
                ft.TextField(
                    hint_text="Filtrar cargos (ex.: tecnologia, analista)",
                    prefix_icon=ft.Icons.FILTER_LIST,
                    dense=True,
                    border_radius=10,
                    expand=True,
                    on_change=filtrar,
                ),
                comp.botao_texto("Todos", lambda e: marcar_todos(True)),
                comp.botao_texto("Nenhum", lambda e: marcar_todos(False)),
            ],
            spacing=4,
        ),
        ft.Container(lista, border=ft.Border.all(1, c["borda"]), border_radius=12, padding=ft.Padding.symmetric(horizontal=10)),
        contador,
    ] + [comp.aviso(a, c, "alerta") for a in plano.avisos[:1]]

    async def comecar(e):
        escolhidos = [it for cx, it, _ in caixas if cx.value and not cx.disabled]
        if not escolhidos:
            return
        await _importar(app, dlg, corpo, plano, escolhidos, estado, texto_passo, barra, progresso, fechar)

    botao_ir.on_click = comecar
    dlg.actions = [ft.TextButton("Cancelar", on_click=lambda e: fechar()), botao_ir]
    recontar()
    app.page.update()


async def _importar(app, dlg, corpo, plano, escolhidos, estado, texto_passo, barra, progresso, fechar) -> None:
    c = app.c
    barra.value = 0
    texto_passo.value = "Começando…"
    corpo.controls = [
        comp.texto(f"Importando {len(escolhidos)} prova{'s' if len(escolhidos) != 1 else ''}", c, 16, peso=ft.FontWeight.W_600),
        barra,
        texto_passo,
        comp.apagado("Pode levar alguns minutos. Se parar no meio, o que já foi importado fica na biblioteca.", c, 13),
    ]

    def parar(e):
        estado["parar"] = True
        texto_passo.value = "Parando depois desta prova…"
        e.control.disabled = True
        app.page.update()

    dlg.actions = [ft.TextButton("Parar", on_click=parar)]
    app.page.update()
    rel: coleta.Relatorio = await app.em_segundo_plano(
        coleta.coletar, app.db, app.aj, app.pci, plano, escolhidos, progresso, lambda: estado["parar"]
    )
    _mostrar_relatorio(app, dlg, corpo, plano, rel, fechar)


def _mostrar_relatorio(app, dlg, corpo, plano, rel: coleta.Relatorio, fechar) -> None:
    from .montar import abrir_montador

    c = app.c
    filtro = filtro_do_concurso(plano.termo)
    banca = next((i.banca for i in plano.itens if i.banca), "")
    if rel.provas:
        principal = (
            f"{rel.provas} prova{'s' if rel.provas != 1 else ''} na biblioteca, com {rel.novas} questões novas"
            + (f" ({rel.repetidas} repetidas entre cargos ficam de fora dos simulados)" if rel.repetidas else "")
            + "."
        )
        tipo = "ok"
    else:
        principal = "Nenhuma prova foi importada."
        tipo = "alerta"
    linhas: list[ft.Control] = [comp.aviso(principal, c, tipo)]
    if rel.questoes and rel.com_gabarito < rel.questoes:
        linhas.append(comp.apagado(f"{rel.questoes - rel.com_gabarito} questões ficaram sem gabarito; dá para completar em ⋮ → Gabarito.", c, 13.5))
    if rel.cartao:
        linhas.append(comp.apagado(f"{rel.cartao} prova(s) eram imagem digitalizada e abrem no modo cartão-resposta.", c, 13.5))
    if rel.interrompido:
        linhas.append(comp.apagado("Você parou a importação antes do fim.", c, 13.5))
    if rel.falhas:
        linhas.append(comp.texto(f"Não consegui importar {len(rel.falhas)}:", c, 14, peso=ft.FontWeight.W_600))
        linhas += [comp.apagado("• " + f, c, 13) for f in rel.falhas[:5]]
    resumo = app.db.resumo_biblioteca(filtro) if filtro else None
    if resumo and resumo["questoes"]:
        linhas.append(
            comp.apagado(f"Agora você tem {resumo['questoes']} questões de {filtro} para montar simulados ({resumo['provas']} provas).", c, 14)
        )
    corpo.controls = linhas

    def montar(e):
        app.page.pop_dialog()
        abrir_montador(app, filtro=filtro, nome=f"Simulado {filtro}", banca=banca)

    def ver(e):
        app.page.pop_dialog()
        app.telas.pop("estudar", None)
        app.ir("estudar")

    def so_fechar(e):
        fechar()
        if app.secao in ("estudar", "inicio"):
            app.recarregar_tela()

    dlg.actions = [ft.TextButton("Fechar", on_click=so_fechar)]
    if rel.provas:
        dlg.actions = [
            ft.TextButton("Fechar", on_click=so_fechar),
            ft.TextButton("Ver biblioteca", on_click=ver),
            comp.botao("Montar simulado", montar, ft.Icons.TUNE_ROUNDED),
        ]
    app.page.update()
