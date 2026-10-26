"""Janela "Montar simulado": número de questões e distribuição por disciplina."""

from __future__ import annotations

from datetime import datetime

import flet as ft

from .. import montador
from . import comp
from .tema import FONTE_TITULO

PERSONALIZADO = "Personalizado"


def abrir_montador(app, filtro: str = "", nome: str = "", banca: str = "") -> None:
    c = app.c
    todas = app.db.banco_de_questoes()
    provas = [p for p in app.db.provas() if not p["origem_url"].startswith("aprova://simulado") and p["n_questoes"]]
    tem_ia = bool(app.aj.chave_claude)
    largura = min(640, (app.page.width or 700) - 40)

    linhas: list[dict] = []  # {"disc": TextField, "qtd": TextField, "info": Text, "row": Row}
    lista = ft.Column(spacing=8)
    total_txt = comp.texto("", c, 15, peso=ft.FontWeight.W_700)
    aviso_falta = ft.Container()

    campo_nome = ft.TextField(value=nome or f"Simulado {datetime.now():%d/%m}", label="Nome do simulado", border_radius=10, dense=True)
    campo_filtro = ft.TextField(
        value=filtro,
        label="Concurso ou órgão (ex.: Dataprev, TJ-SP)",
        border_radius=10,
        dense=True,
        expand=True,
        on_change=lambda e: recalcular(),
    )
    campo_banca = ft.TextField(value=banca, label="Banca (ex.: FGV)", border_radius=10, dense=True, width=170, on_change=lambda e: recalcular())
    outras = ft.Checkbox(
        label="Quando faltar ou repetir, usar questões de outras provas da biblioteca",
        value=True,
        on_change=lambda e: recalcular(),
    )
    usar_ia = ft.Checkbox(
        label="Usar a IA: completar o que faltar e trocar as que você já fez por questões novas",
        value=tem_ia,
        disabled=not tem_ia,
        on_change=lambda e: (setattr(assuntos, "visible", bool(e.control.value)), recalcular()),
    )
    assuntos = ft.TextField(
        label="Assuntos do edital (a IA usa para criar as questões)",
        hint_text="Ex.: Desenvolvimento de Software: Java, Spring Boot, APIs REST, microsserviços, testes, DevOps…",
        multiline=True,
        min_lines=3,
        max_lines=6,
        border_radius=10,
        visible=tem_ia,
    )

    opcoes_modelo = [ft.DropdownOption(key=PERSONALIZADO, text=PERSONALIZADO)]
    opcoes_modelo += [ft.DropdownOption(key=k, text=k) for k in montador.MODELOS]
    opcoes_modelo += [ft.DropdownOption(key=f"prova:{p['id']}", text=f"Igual à prova: {p['titulo'][:60]} ({p['n_questoes']})") for p in provas[:30]]
    modelo = ft.Dropdown(
        label="Modelo de prova",
        value=PERSONALIZADO,
        options=opcoes_modelo,
        on_select=lambda e: aplicar_modelo(e.control.value),
        dense=True,
        border_radius=10,
        width=largura - 50,
    )

    def disponiveis() -> dict[str, int]:
        return montador.contar_disponiveis(todas, campo_filtro.value or "", bool(outras.value))

    def adicionar(disc: str = "", qtd: int = 10):
        dfield = ft.TextField(value=disc, hint_text="Disciplina", dense=True, border_radius=8, expand=True, on_change=lambda e: recalcular())
        qfield = ft.TextField(
            value=str(qtd),
            dense=True,
            width=74,
            border_radius=8,
            text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: recalcular(),
        )
        info = comp.apagado("", c, 12.5)
        item: dict = {"disc": dfield, "qtd": qfield, "info": info}

        def remover(e):
            linhas.remove(item)
            lista.controls.remove(item["row"])
            recalcular()

        item["row"] = ft.Row(
            [
                ft.Column([dfield, info], spacing=2, expand=True),
                qfield,
                ft.IconButton(ft.Icons.CLOSE, tooltip="Tirar disciplina", on_click=remover, icon_size=18),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=8,
        )
        linhas.append(item)
        lista.controls.append(item["row"])

    def aplicar_modelo(chave: str | None):
        linhas.clear()
        lista.controls.clear()
        if chave in montador.MODELOS:
            m = montador.MODELOS[chave]
            campo_filtro.value = campo_filtro.value or m["filtro"]
            campo_banca.value = campo_banca.value or m["banca"]
            if not nome:
                campo_nome.value = f"Simulado {m['filtro']} {datetime.now():%d/%m}"
            for d, n in m["disciplinas"]:
                adicionar(d, n)
        elif chave and chave.startswith("prova:"):
            pid = int(chave.split(":")[1])
            for d, n in app.db.distribuicao_da_prova(pid):
                adicionar(d, n)
        else:
            base = disponiveis()
            for d, n in sorted(base.items(), key=lambda x: -x[1])[:8]:
                adicionar(d, min(n, 10))
            if not base:
                adicionar("Língua Portuguesa", 10)
        recalcular()

    def quantidade(item) -> int:
        v = (item["qtd"].value or "").strip()
        return int(v) if v.isdigit() else 0

    def recalcular():
        disp = disponiveis()
        total = 0
        falta_total = 0
        for item in linhas:
            n = quantidade(item)
            total += n
            d = (item["disc"].value or "").strip()
            tem = disp.get(d, 0)
            if n > tem:
                falta_total += n - tem
                item["info"].value = f"{tem} na biblioteca, faltam {n - tem}" + (" (a IA cria)" if usar_ia.value else "")
                item["info"].color = c["tinta"] if usar_ia.value else c["marca"]
            else:
                item["info"].value = f"{tem} na biblioteca"
                item["info"].color = c["texto2"]
        total_txt.value = f"Total: {total} questões"
        if falta_total and not usar_ia.value:
            msg = f"Faltam {falta_total} questões na biblioteca. Importe provas anteriores desse concurso ou da banca"
            msg += ", ou ative a criação por IA." if tem_ia else ". Com a chave do Claude em Ajustes, a IA cria as que faltarem."
            filtro_atual = (campo_filtro.value or "").strip()
            acao = None
            if filtro_atual:
                from .coleta import abrir_coleta

                acao = comp.botao_texto(
                    "Buscar provas",
                    lambda e, t=filtro_atual: (app.page.pop_dialog(), abrir_coleta(app, t)),
                    ft.Icons.LIBRARY_ADD_OUTLINED,
                )
            aviso_falta.content = comp.aviso(msg, c, "alerta", acao)
        else:
            aviso_falta.content = None
        try:
            corpo.update()
        except Exception:  # noqa: BLE001 - ainda não está na tela
            pass

    corpo = ft.Column(
        [
            modelo,
            campo_nome,
            ft.Row([campo_filtro, campo_banca], spacing=10),
            ft.Row([comp.subtitulo("Disciplinas e quantidades", c, 17), ft.Container(expand=True), total_txt]),
            lista,
            comp.botao_texto("Adicionar disciplina", lambda e: (adicionar("", 5), recalcular()), ft.Icons.ADD),
            outras,
            usar_ia,
            assuntos,
            aviso_falta,
        ]
        + ([] if tem_ia else [comp.apagado("A criação de questões por IA fica disponível quando você coloca a chave do Claude em Ajustes.", c, 13)]),
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        width=largura,
        height=min(600, (app.page.height or 760) - 200),
    )

    async def montar(e):
        distribuicao = [((i["disc"].value or "").strip(), quantidade(i)) for i in linhas]
        distribuicao = [(d, n) for d, n in distribuicao if d and n > 0]
        if not distribuicao:
            comp.mensagem(app.page, "Coloque pelo menos uma disciplina com quantidade.")
            return
        from .estudar import painel_importacao, abrir_prova

        painel, progresso = painel_importacao(app)
        corpo.controls = [painel]
        dlg.actions = [ft.TextButton("Fechar", on_click=lambda ev: app.page.pop_dialog())]
        app.page.update()
        res = await app.em_segundo_plano(
            montador.montar,
            app.db,
            app.aj,
            campo_nome.value or "Simulado",
            distribuicao,
            campo_filtro.value or "",
            campo_banca.value or "",
            bool(outras.value),
            bool(usar_ia.value),
            assuntos.value or "",
            progresso,
        )
        app.telas.pop("estudar", None)
        app.telas.pop("inicio", None)
        if not res["prova_id"]:
            corpo.controls = [comp.aviso("Não encontrei questões para montar esse simulado. Importe provas anteriores primeiro.", c, "erro")]
            app.page.update()
            return
        partes = [f"{res['total']} questões prontas"]
        detalhe = []
        if res["da_biblioteca"]:
            detalhe.append(f"{res['da_biblioteca']} de provas anteriores")
        if res["geradas"]:
            detalhe.append(f"{res['geradas']} criadas por IA")
        texto = partes[0] + (": " + " e ".join(detalhe) if detalhe else "") + "."
        filhos: list[ft.Control] = [comp.aviso(texto, c, "ok")]
        if res["faltas"]:
            falt = ", ".join(f"{d}: {n}" for d, n in res["faltas"].items())
            filhos.append(comp.aviso(f"Não deu para completar: {falt}.", c, "alerta"))
        if res.get("repetidas"):
            rep = res["repetidas"]
            n_rep = sum(rep.values())
            discs = sorted(rep, key=lambda d: -rep[d])
            nomes = ", ".join(discs[:3]) + (" e outras" if len(discs) > 3 else "")
            filhos.append(
                comp.aviso(
                    f"{n_rep} {'questão você já tinha visto' if n_rep == 1 else 'questões você já tinha visto'} ({nomes}). "
                    "As novas dessa parte da sua biblioteca acabaram: baixe mais provas do concurso ou crie questões inéditas com a IA para variar.",
                    c,
                    "info",
                )
            )

        def ir(modo):
            def _f(ev):
                app.page.pop_dialog()
                abrir_prova(app, res["prova_id"], modo)

            return _f

        filhos.append(
            ft.Row(
                [comp.botao("Fazer simulado", ir("simulado"), ft.Icons.TIMER_OUTLINED), comp.botao_contorno("Modo estudo", ir("estudo"), ft.Icons.LIGHTBULB_OUTLINE)],
                wrap=True,
                spacing=10,
            )
        )
        corpo.controls = filhos
        corpo.height = None
        tela = app.telas.get(app.secao)
        app.page.update()
        if app.secao == "estudar" and tela is None:
            app.recarregar_tela()

    dlg = ft.AlertDialog(
        title=ft.Text("Montar simulado", font_family=FONTE_TITULO, size=24),
        content=corpo,
        actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Montar simulado", montar, ft.Icons.CHECK_ROUNDED)],
    )
    aplicar_modelo(next((k for k, m in montador.MODELOS.items() if filtro and m["filtro"].lower() in filtro.lower()), PERSONALIZADO))
    if filtro and any(m["filtro"].lower() in filtro.lower() for m in montador.MODELOS.values()):
        modelo.value = next(k for k, m in montador.MODELOS.items() if m["filtro"].lower() in filtro.lower())
    app.page.show_dialog(dlg)


def abrir_gerador_ia(app, filtro: str = "", banca: str = "") -> None:
    """Questões inéditas criadas pela IA a partir das provas reais do concurso na biblioteca."""
    from .estudar import abrir_prova, painel_importacao

    c = app.c
    largura = min(560, (app.page.width or 600) - 40)
    if not app.aj.chave_claude:
        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Questões inéditas com IA", font_family=FONTE_TITULO, size=22),
                content=ft.Column(
                    [
                        comp.texto("Para a IA criar questões novas no estilo das provas da sua biblioteca, coloque a chave do Claude em Ajustes.", c, 15),
                        comp.apagado("O uso da API é cobrado pela Anthropic; o modelo Haiku, o padrão, é o mais barato.", c, 13),
                    ],
                    tight=True,
                    spacing=10,
                    width=largura,
                ),
                actions=[
                    ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog()),
                    comp.botao("Ir para Ajustes", lambda e: (app.page.pop_dialog(), app.ir("ajustes")), ft.Icons.TUNE),
                ],
            )
        )
        return
    campo_filtro = ft.TextField(value=filtro, label="Concurso ou órgão", dense=True, border_radius=10, expand=True)
    campo_banca = ft.TextField(value=banca, label="Banca", dense=True, border_radius=10, width=150)
    total = ft.TextField(value="20", label="Quantas questões", dense=True, border_radius=10, width=150, keyboard_type=ft.KeyboardType.NUMBER)
    previa = comp.apagado("", c, 13)

    def distribuicao() -> list[tuple[str, int]]:
        n = int(total.value) if (total.value or "").isdigit() else 20
        return montador.distribuicao_do_concurso(app.db, campo_filtro.value or "", max(1, min(n, 80)))

    def atualizar(e=None):
        dist = distribuicao()
        previa.value = (
            "Distribuição, igual às provas do concurso na biblioteca: " + ", ".join(f"{d} {n}" for d, n in dist)
            if dist
            else "Não há provas desse concurso na biblioteca. Use “Encher biblioteca” primeiro, para a IA ter modelos."
        )
        try:
            previa.update()
        except Exception:  # noqa: BLE001
            pass

    campo_filtro.on_change = atualizar
    total.on_change = atualizar
    atualizar()
    corpo = ft.Column(
        [
            comp.apagado(
                "A IA lê questões reais das provas anteriores desse concurso e cria questões novas no mesmo estilo, nível e assuntos. "
                "Depois resolve cada uma sem ver a resposta e descarta as que não baterem com o gabarito.",
                c,
                13.5,
            ),
            ft.Row([campo_filtro, campo_banca], spacing=10),
            total,
            previa,
        ],
        tight=True,
        spacing=12,
        width=largura,
    )

    async def gerar(e):
        dist = distribuicao()
        if not dist:
            comp.mensagem(app.page, "Sem provas desse concurso na biblioteca para servir de modelo.")
            return
        painel, progresso = painel_importacao(app)
        corpo.controls = [painel]
        dlg.actions = [ft.TextButton("Fechar", on_click=lambda ev: app.page.pop_dialog())]
        app.page.update()
        res = await app.em_segundo_plano(montador.gerar_lote_ia, app.db, app.aj, campo_filtro.value or "", campo_banca.value or "", dist, progresso)
        app.telas.pop("estudar", None)
        if not res["prova_id"]:
            corpo.controls = [comp.aviso("A IA não conseguiu criar as questões agora. " + ", ".join(res["faltas"]), c, "erro")]
            app.page.update()
            return
        filhos: list[ft.Control] = [comp.aviso(f"{res['total']} questões inéditas prontas, conferidas pela IA.", c, "ok")]
        if res["faltas"]:
            filhos.append(comp.apagado("Ficaram faltando: " + ", ".join(f"{d}: {n}" for d, n in res["faltas"].items()), c, 13))

        def ir(modo):
            def _f(ev):
                app.page.pop_dialog()
                abrir_prova(app, res["prova_id"], modo)

            return _f

        filhos.append(ft.Row([comp.botao("Fazer simulado", ir("simulado"), ft.Icons.TIMER_OUTLINED), comp.botao_contorno("Modo estudo", ir("estudo"), ft.Icons.LIGHTBULB_OUTLINE)], spacing=10, wrap=True))
        corpo.controls = filhos
        app.page.update()

    dlg = ft.AlertDialog(
        title=ft.Text("Questões inéditas com IA", font_family=FONTE_TITULO, size=22),
        content=corpo,
        actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Gerar questões", gerar, ft.Icons.AUTO_AWESOME)],
    )
    app.page.show_dialog(dlg)
