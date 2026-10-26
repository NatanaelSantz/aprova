"""Biblioteca de provas: importar PDFs, escolher o modo e ver o histórico."""

from __future__ import annotations

import re
import tempfile
from datetime import datetime
from pathlib import Path

import flet as ft

from .. import importador, pdfprova
from . import comp
from .tema import FONTE_TITULO


def abrir_prova(app, prova_id: int, modo: str, numero: int | None = None) -> None:
    from .prova import TelaProva

    prova = app.db.prova(prova_id)
    if not prova:
        comp.mensagem(app.page, "Essa prova não está mais na biblioteca.")
        return
    tela = TelaProva(app, prova, modo)
    if numero is not None:
        tela.idx = next((i for i, q in enumerate(tela.questoes) if q["numero"] == numero), 0)
    app.abrir_foco(tela)


INTERNAS = ("aprova://revisao", "aprova://simulado/treino")


async def escolher_pdfs(app, titulo: str = "Escolha a prova e o gabarito (PDF)", varios: bool = True) -> list[Path]:
    """Abre o seletor de arquivos e devolve caminhos locais dos PDFs escolhidos."""
    picker = getattr(app, "_picker", None)
    if picker is None:
        picker = ft.FilePicker()
        app._picker = picker
    pasta = app.aj["pasta_downloads"] if Path(app.aj["pasta_downloads"]).exists() else None
    arquivos = await picker.pick_files(
        dialog_title=titulo,
        initial_directory=pasta,
        file_type=ft.FilePickerFileType.CUSTOM,
        allowed_extensions=["pdf"],
        allow_multiple=varios,
        with_data=app.modo_web,
    )
    caminhos: list[Path] = []
    for f in arquivos or []:
        if f.path:
            caminhos.append(Path(f.path))
        elif f.bytes:
            destino = Path(tempfile.mkdtemp(prefix="aprova_up_")) / (f.name or "prova.pdf")
            destino.write_bytes(f.bytes)
            caminhos.append(destino)
    return caminhos


def painel_importacao(app) -> tuple[ft.Column, callable]:
    """Coluna com barra de progresso e uma função para atualizá-la."""
    c = app.c
    barra = ft.ProgressBar(value=0, color=c["tinta"], bgcolor=c["sup2"], border_radius=4, bar_height=6)
    rotulo = comp.apagado("Preparando…", c, 14)
    coluna = ft.Column([rotulo, barra], spacing=8)

    def progresso(frac: float, texto: str):
        barra.value = frac
        rotulo.value = texto
        try:
            coluna.update()
        except Exception:  # noqa: BLE001
            pass

    return coluna, progresso


def resumo_importacao(app, res: dict, ao_fechar=None) -> list[ft.Control]:
    c = app.c
    linhas: list[ft.Control] = []
    if res["modo"] == "questoes":
        txt = f"{res['n_questoes']} questões prontas para resolver"
        txt += f", com gabarito de {res['n_gabarito']} respostas." if res["n_gabarito"] else ". Ainda sem gabarito."
        linhas.append(comp.aviso(txt, c, "ok"))
    else:
        txt = "A prova vai abrir com as páginas originais e um cartão-resposta ao lado."
        if res["n_gabarito"]:
            txt += f" Gabarito com {res['n_gabarito']} respostas."
        linhas.append(comp.aviso(txt, c, "info"))
    if res.get("aviso"):
        linhas.append(comp.aviso(res["aviso"], c, "alerta"))
    if not res["n_gabarito"]:
        linhas.append(
            comp.apagado("Sem gabarito, a prova é corrigida só depois que você digitar as respostas oficiais (menu ⋮ da prova → Gabarito).", c, 13.5)
        )

    def ir(modo):
        def _f(e):
            app.page.pop_dialog()
            abrir_prova(app, res["prova_id"], modo)

        return _f

    linhas.append(
        ft.Row(
            [
                comp.botao("Fazer simulado", ir("simulado"), ft.Icons.TIMER_OUTLINED),
                comp.botao_contorno("Modo estudo", ir("estudo"), ft.Icons.LIGHTBULB_OUTLINE),
            ],
            wrap=True,
            spacing=10,
            run_spacing=10,
        )
    )
    return linhas


async def importar_arquivos(app, corpo: ft.Column, pdfs: list[Path], meta: dict | None = None) -> dict | None:
    """Importa PDFs mostrando o progresso dentro de `corpo` (uma coluna de diálogo)."""
    c = app.c
    painel, progresso = painel_importacao(app)
    corpo.controls = [painel]
    app.page.update()
    try:
        prova, gab = await app.em_segundo_plano(importador.separar_arquivos, pdfs)
        if prova is None:
            corpo.controls = [comp.aviso("Nenhum PDF de prova foi escolhido.", c, "erro")]
            app.page.update()
            return None
        res = await app.em_segundo_plano(
            importador.importar,
            app.db,
            app.aj,
            prova,
            gab,
            meta or {},
            bool(app.aj.chave_claude),
            progresso,
        )
    except Exception as ex:  # noqa: BLE001
        corpo.controls = [comp.aviso(f"Não consegui ler esse PDF ({type(ex).__name__}: {ex}).", c, "erro")]
        app.page.update()
        return None
    corpo.controls = resumo_importacao(app, res)
    app.telas.pop("estudar", None)
    app.telas.pop("inicio", None)
    app.page.update()
    return res


def dialogo_gabarito(app, prova: dict, ao_salvar=None) -> None:
    """Editar/colar o gabarito oficial de uma prova."""
    c = app.c
    questoes = app.db.questoes(prova["id"])
    atual = " ".join(f"{q['numero']}{q['gabarito']}" for q in questoes if q.get("gabarito"))
    campo = ft.TextField(
        value=atual,
        multiline=True,
        min_lines=4,
        max_lines=10,
        hint_text="Ex.: 1A 2C 3B 4E ...  ou só as letras em ordem: ACBE...",
        border_radius=10,
    )
    n_campo = ft.TextField(
        value=str(len(questoes) or ""),
        label="Total de questões",
        width=170,
        keyboard_type=ft.KeyboardType.NUMBER,
        visible=prova["modo"] == "cartao",
        border_radius=10,
    )
    info = comp.apagado("", c, 13)

    def ler_pdf(e):
        if prova.get("pdf_gabarito") and Path(prova["pdf_gabarito"]).exists():
            g = pdfprova.ler_gabarito_pdf(Path(prova["pdf_gabarito"]), len(questoes) or None, prova.get("cargo", ""))
            campo.value = " ".join(f"{k}{v}" for k, v in sorted(g.items()))
            info.value = f"{len(g)} respostas lidas do PDF. Confira com o cargo certo antes de salvar."
            app.page.update()

    def salvar(e):
        g = pdfprova.gabarito_de_texto_livre(campo.value or "")
        if prova["modo"] == "cartao" and (n_campo.value or "").strip().isdigit():
            total = int(n_campo.value.strip())
            app.db.garantir_questoes(prova["id"], total)
            g = {k: v for k, v in g.items() if k <= total}
        app.db.definir_gabarito(prova["id"], g)
        app.page.pop_dialog()
        comp.mensagem(app.page, f"Gabarito salvo: {len(g)} respostas.")
        if ao_salvar:
            ao_salvar()

    filhos = [
        comp.apagado("Cole ou digite as respostas oficiais. Use X para questão anulada.", c, 14),
        campo,
        n_campo,
        info,
    ]
    acoes = [ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar gabarito", salvar)]
    if prova.get("pdf_gabarito"):
        acoes.insert(0, ft.TextButton("Ler do PDF de novo", on_click=ler_pdf))
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Gabarito oficial", font_family=FONTE_TITULO, size=22),
            content=ft.Column(filhos, tight=True, spacing=10, width=min(520, (app.page.width or 600) - 40)),
            actions=acoes,
        )
    )


class TelaEstudar:
    def __init__(self, app):
        self.app = app
        self.aba = "biblioteca"

    def preparar(self, aba: str | None = None, **_):
        if aba in ("biblioteca", "revisao", "duvidas", "pdfs"):
            self.aba = aba

    def _abas(self) -> ft.Control:
        rev = self.app.db.revisao_resumo()["pendentes"]
        return ft.SegmentedButton(
            selected=[self.aba],
            segments=[
                ft.Segment(value="biblioteca", label=ft.Text("Biblioteca"), icon=ft.Icon(ft.Icons.LIBRARY_BOOKS_OUTLINED)),
                ft.Segment(value="revisao", label=ft.Text(f"Revisão ({rev})" if rev else "Revisão"), icon=ft.Icon(ft.Icons.REPLAY)),
                ft.Segment(value="duvidas", label=ft.Text("Dúvidas"), icon=ft.Icon(ft.Icons.QUESTION_ANSWER_OUTLINED)),
                ft.Segment(value="pdfs", label=ft.Text("Marcar PDF"), icon=ft.Icon(ft.Icons.BORDER_COLOR_OUTLINED)),
            ],
            show_selected_icon=False,
            on_change=self._trocar_aba,
        )

    def _trocar_aba(self, e):
        self.aba = e.control.selected[0] if e.control.selected else "biblioteca"
        self._recarregar()

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        provas = [p for p in app.db.provas() if not str(p["origem_url"]).startswith(INTERNAS)]
        botoes = [
            app.botao_estudo(),
            comp.botao_contorno("Importar PDF", self._importar, ft.Icons.UPLOAD_FILE),
            comp.botao_contorno("Encher biblioteca", self._encher, ft.Icons.LIBRARY_ADD_OUTLINED),
            comp.botao("Montar simulado", lambda e: self._montar(), ft.Icons.TUNE_ROUNDED),
        ]
        if app.largo:
            topo = ft.Row(
                [comp.titulo("Estudar", c, 34), ft.Container(expand=True), *botoes],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            )
        else:
            # no celular: título em cima e botões quebrando linha (sem espaço elástico dentro do wrap)
            topo = ft.Column(
                [comp.titulo("Estudar", c, 28), ft.Row(botoes, wrap=True, spacing=8, run_spacing=8)],
                spacing=12,
            )
        explicacao = ft.Row(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Row([ft.Icon(ft.Icons.TIMER_OUTLINED, size=18, color=c["tinta"]), comp.texto("Simulado", c, 15, peso=ft.FontWeight.W_700)], spacing=8),
                            comp.apagado("Cronômetro ligado e correção só no final, como no dia da prova.", c, 13.5),
                        ],
                        spacing=4,
                    ),
                    expand=True,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Row([ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=18, color=c["tinta"]), comp.texto("Modo estudo", c, 15, peso=ft.FontWeight.W_700)], spacing=8),
                            comp.apagado("Correção a cada questão, com ajuda e pesquisa na internet.", c, 13.5),
                        ],
                        spacing=4,
                    ),
                    expand=True,
                ),
            ],
            spacing=24,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        lista = ft.Column(spacing=0)
        # provas do mesmo concurso (3 ou mais) ficam juntas num grupo que abre e fecha
        from .. import coleta

        def chave(p: dict) -> str:
            if not p.get("orgao") or str(p["origem_url"]).startswith("aprova://"):
                return ""
            return coleta.nome_curto(re.sub(r"\b20\d\d\b", "", p["orgao"]).strip())

        grupos: dict[str, list[dict]] = {}
        for p in provas:
            if chave(p):
                grupos.setdefault(chave(p), []).append(p)
        grupos = {k: v for k, v in grupos.items() if len(v) >= 3}
        feitos: set[str] = set()
        itens: list[tuple[str, object]] = []
        for p in provas:
            g = chave(p)
            if g in grupos:
                if g not in feitos:
                    feitos.add(g)
                    itens.append(("grupo", g))
            else:
                itens.append(("prova", p))
        for i, (tipo, val) in enumerate(itens):
            ultima = i == len(itens) - 1
            lista.controls.append(self._grupo(val, grupos[val], ultima) if tipo == "grupo" else self._linha(val, ultima=ultima))
        if not provas:
            lista.controls.append(
                comp.vazio(
                    ft.Icons.DESCRIPTION_OUTLINED,
                    "Sua biblioteca está vazia",
                    "Use “Encher biblioteca” para baixar as provas de um concurso de uma vez, ou importe um PDF que você já tem.",
                    c,
                    comp.botao("Encher biblioteca", self._encher, ft.Icons.LIBRARY_ADD_OUTLINED),
                )
            )
        if self.aba == "revisao":
            corpo = [self._revisao()]
        elif self.aba == "duvidas":
            corpo = [self._duvidas()]
        elif self.aba == "pdfs":
            corpo = [self._pdfs()]
        else:
            corpo = [explicacao, comp.subtitulo("Suas provas", c, 21), comp.bloco(lista, c, padding=8), self._historico()]
        abas = self._abas() if app.largo else ft.Row([self._abas()], scroll=ft.ScrollMode.AUTO)
        return ft.Column(
            [topo, abas, *corpo, ft.Container(height=30)],
            spacing=18,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # ------------------------------------------------------------------ revisão

    def _revisao(self) -> ft.Control:
        app, c = self.app, self.app.c
        r = app.db.revisao_resumo()
        if not r["ativas"] and not r["dominadas"]:
            return comp.vazio(
                ft.Icons.REPLAY,
                "Nada para revisar ainda",
                "As questões que você errar nos simulados e no modo estudo entram aqui, e também as que você marcar com a bandeira. "
                "O Aprova traz cada uma de volta no dia certo para fixar o conteúdo.",
                c,
            )

        async def comecar(disciplina: str | None = None, todas: bool = False):
            await app.abrir_destino("revisao", disciplina or "") if not todas else self._revisar_todas(disciplina)

        pend = r["pendentes"]
        cabeca = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(str(pend), size=44, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["tinta"] if pend else c["texto2"]),
                        ft.Column(
                            [
                                comp.texto("para revisar hoje" if pend != 1 else "para revisar hoje", c, 16, peso=ft.FontWeight.W_700),
                                comp.apagado(f"{r['amanha']} amanhã · {r['ativas']} em revisão · {r['dominadas']} dominadas", c, 13),
                            ],
                            spacing=0,
                        ),
                    ],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        comp.botao(f"Começar revisão ({min(pend, 30)})" if pend else "Nada vence hoje", lambda e: app.page.run_task(comecar), ft.Icons.PLAY_ARROW_ROUNDED, disabled=not pend),
                        comp.botao_contorno("Revisar todos os erros agora", lambda e: self._revisar_todas(None), ft.Icons.REPLAY) if r["ativas"] else ft.Container(),
                    ],
                    spacing=10,
                    wrap=True,
                ),
            ],
            spacing=12,
        )
        nomes = ["Caixa 1\namanhã", "Caixa 2\n3 dias", "Caixa 3\n7 dias", "Caixa 4\n15 dias", "Caixa 5\n30 dias", "Dominadas"]
        caixas = ft.Row(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(str(r["caixas"][i + 1]), size=22, weight=ft.FontWeight.W_700, color=c["ok"] if i == 5 else c["texto"]),
                            ft.Text(nomes[i], size=11.5, color=c["texto2"], text_align=ft.TextAlign.CENTER),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=c["ok_suave"] if i == 5 else c["sup2"],
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=10),
                    expand=True if app.largo else None,
                    width=None if app.largo else 92,
                )
                for i in range(6)
            ],
            spacing=8,
            scroll=None if app.largo else ft.ScrollMode.AUTO,
        )
        linhas = []
        for disc, d in sorted(r["por_disciplina"].items(), key=lambda x: (-x[1]["pendentes"], -x[1]["total"])):
            if not d["total"]:
                continue
            linhas.append(
                ft.Row(
                    [
                        ft.Text(disc, size=14.5, color=c["texto"], expand=True),
                        comp.apagado(f"{d['pendentes']} hoje · {d['total']} no total", c, 12.5),
                        comp.botao_texto(
                            "Revisar",
                            (lambda e, n=disc: app.page.run_task(app.abrir_destino, "revisao", n)) if d["pendentes"] else (lambda e, n=disc: self._revisar_todas(n)),
                            ft.Icons.PLAY_ARROW_ROUNDED,
                        ),
                    ],
                    spacing=10,
                )
            )
        como = comp.apagado(
            "Como funciona: cada erro vai para a caixa 1 e volta no dia seguinte. Acertou, a questão sobe de caixa e volta depois "
            "de 3, 7, 15 e 30 dias. Errou de novo, volta para a caixa 1. Passou da caixa 5, está dominada.",
            c,
            13,
        )
        return ft.Column(
            [
                comp.bloco(cabeca, c, padding=20),
                caixas,
                como,
                comp.bloco(ft.Column([comp.subtitulo("Por disciplina", c, 18)] + linhas, spacing=8), c, padding=18) if linhas else ft.Container(),
            ],
            spacing=16,
        )

    def _revisar_todas(self, disciplina: str | None):
        from .. import sessoes

        pid = sessoes.preparar_revisao(self.app.db, disciplina, todas=True)
        if pid:
            abrir_prova(self.app, pid, "estudo")
        else:
            comp.mensagem(self.app.page, "Nada para revisar.")

    # ------------------------------------------------------------------ dúvidas

    def _duvidas(self) -> ft.Control:
        app, c = self.app, self.app.c
        itens = app.db.duvidas()
        if not itens:
            return comp.vazio(
                ft.Icons.QUESTION_ANSWER_OUTLINED,
                "Nenhuma dúvida ainda",
                "Durante uma questão, toque em Ajuda e escreva sua dúvida no fim do painel (ex.: “por que a B está errada?”). "
                "O Aprova pesquisa na internet para responder e guarda tudo aqui para você revisar.",
                c,
            )
        cartoes = []
        for d in itens:
            quando = datetime.fromisoformat(d["criada_em"]).strftime("%d/%m %H:%M")
            meta = "   ".join(x for x in (d.get("disciplina"), d.get("prova_titulo"), f"questão {d['numero']}" if d.get("numero") else "", quando) if x)
            fontes = [
                ft.Container(
                    ft.Row([ft.Icon(ft.Icons.OPEN_IN_NEW, size=13, color=c["tinta"]), ft.Text(f["titulo"], size=12.5, color=c["tinta"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)], spacing=6),
                    url=f["url"],
                )
                for f in d["fontes"][:3]
            ]
            acoes = ft.Row(
                [
                    comp.botao_texto("Abrir a questão", lambda e, d=d: abrir_prova(app, d["prova_id"], "estudo", d["numero"]), ft.Icons.ARROW_FORWARD)
                    if d.get("prova_id") and app.db.prova(d["prova_id"])
                    else ft.Container(),
                    comp.botao_texto("Apagar", lambda e, d=d: (app.db.apagar_duvida(d["id"]), self._recarregar()), ft.Icons.DELETE_OUTLINE),
                ],
                spacing=4,
            )
            cartoes.append(
                ft.Container(
                    ft.ExpansionTile(
                        title=ft.Text(d["pergunta"], size=15, weight=ft.FontWeight.W_600, color=c["texto"]),
                        subtitle=comp.apagado(meta, c, 12.5),
                        leading=ft.Icon(ft.Icons.QUESTION_ANSWER_OUTLINED, color=c["tinta"]),
                        controls=[
                            ft.Container(
                                ft.Column(
                                    [comp.apagado("Questão: " + (d.get("resumo") or "")[:200] + ("…" if len(d.get("resumo") or "") > 200 else ""), c, 12.5),
                                     ft.Markdown(d["resposta"], selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB), *fontes, acoes],
                                    spacing=8,
                                ),
                                padding=ft.Padding.only(left=16, right=16, bottom=12),
                            )
                        ],
                        shape=ft.RoundedRectangleBorder(radius=0),
                        collapsed_shape=ft.RoundedRectangleBorder(radius=0),
                    ),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        return ft.Column(
            [comp.apagado(f"{len(itens)} dúvida{'s' if len(itens) != 1 else ''} respondida{'s' if len(itens) != 1 else ''}. Releia antes da prova: é revisão de graça.", c, 13),
             comp.bloco(ft.Column(cartoes, spacing=0), c, padding=4)],
            spacing=12,
        )

    def _grupo(self, nome: str, provas: list[dict], ultima: bool) -> ft.Control:
        app, c = self.app, self.app.c
        from .. import coleta
        from .montar import abrir_gerador_ia, abrir_montador

        n_q = sum(p["n_questoes"] or 0 for p in provas)
        filtro = nome
        banca = next((p["banca"] for p in provas if p.get("banca")), "")
        anos = sorted({p["ano"] for p in provas if p.get("ano")}, reverse=True)
        return ft.Container(
            ft.ExpansionTile(
                title=ft.Text(nome, size=17, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                subtitle=comp.apagado(
                    "  ·  ".join(x for x in (f"{len(provas)} provas", f"{n_q} questões", ", ".join(anos[:4]), banca) if x), c, 13.5
                ),
                leading=ft.Icon(ft.Icons.FOLDER_OUTLINED, color=c["tinta"]),
                trailing=ft.Row(
                    [
                        comp.botao_contorno(
                            "Simulado do concurso",
                            lambda e: abrir_montador(app, filtro=filtro, nome=f"Simulado {filtro}", banca=banca),
                            ft.Icons.TUNE_ROUNDED,
                        )
                        if app.largo
                        else ft.IconButton(
                            ft.Icons.TUNE_ROUNDED,
                            tooltip="Simulado do concurso",
                            on_click=lambda e: abrir_montador(app, filtro=filtro, nome=f"Simulado {filtro}", banca=banca),
                        ),
                        ft.IconButton(
                            ft.Icons.AUTO_AWESOME,
                            tooltip="Questões inéditas com IA no estilo deste concurso",
                            on_click=lambda e: abrir_gerador_ia(app, filtro=filtro, banca=banca),
                        ),
                        ft.Icon(ft.Icons.EXPAND_MORE, color=c["texto2"]),
                    ],
                    tight=True,
                    spacing=8,
                ),
                controls=[self._linha(p, ultima=j == len(provas) - 1) for j, p in enumerate(provas)],
                controls_padding=ft.Padding.only(left=24),
                tile_padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                shape=ft.RoundedRectangleBorder(radius=0),
                collapsed_shape=ft.RoundedRectangleBorder(radius=0),
                maintain_state=True,
            ),
            border=None if ultima else ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
        )

    def _encher(self, e=None) -> None:
        from .coleta import pedir_concurso

        pedir_concurso(self.app)

    def _linha(self, p: dict, ultima: bool = False) -> ft.Control:
        app, c = self.app, self.app.c
        meta = [x for x in (p.get("cargo"), p.get("orgao"), p.get("banca"), p.get("ano")) if x]
        pills: list[ft.Control] = [comp.pilula(f"{p['n_questoes']} questões", c["sup2"], c["texto2"])]
        if p["modo"] == "cartao":
            pills.append(comp.pilula("cartão-resposta", c["tinta_suave"], c["tinta"]))
        if p["n_questoes"] and p.get("n_gabarito", 0) < p["n_questoes"]:
            falta = "sem gabarito" if not p.get("n_gabarito") else f"gabarito {p['n_gabarito']}/{p['n_questoes']}"
            pills.append(comp.pilula(falta, c["marca_suave"], c["marca"], ft.Icons.WARNING_AMBER_ROUNDED))
        if p.get("melhor") is not None:
            pills.append(comp.pilula(f"melhor: {p['melhor'] * 100:.0f}%", c["ok_suave"], c["ok"]))

        menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            tooltip="Mais opções",
            items=[
                ft.PopupMenuItem(content="Gabarito", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda e, pr=p: dialogo_gabarito(app, pr, self._recarregar)),
                ft.PopupMenuItem(content="Abrir PDF original", icon=ft.Icons.PICTURE_AS_PDF_OUTLINED, on_click=lambda e, pr=p: self._abrir_pdf(pr)),
                ft.PopupMenuItem(content="Marcar e anotar o PDF", icon=ft.Icons.BORDER_COLOR_OUTLINED, on_click=lambda e, pr=p: self._marcar_prova(pr)),
                ft.PopupMenuItem(content="Apagar da biblioteca", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e, pr=p: self._apagar(pr)),
            ],
        )
        acoes = ft.Row(
            [
                comp.botao("Simulado", lambda e, i=p["id"]: abrir_prova(app, i, "simulado"), ft.Icons.TIMER_OUTLINED),
                comp.botao_contorno("Estudo", lambda e, i=p["id"]: abrir_prova(app, i, "estudo"), ft.Icons.LIGHTBULB_OUTLINE),
                menu,
            ],
            spacing=8,
            tight=True,
        )
        info = ft.Column(
            [
                ft.Text(p["titulo"], size=17, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                comp.apagado("   ".join(meta), c, 13.5) if meta else ft.Container(),
                ft.Row(pills, spacing=6, wrap=True, run_spacing=6),
            ],
            spacing=5,
            expand=True,
        )
        linha = ft.Row([info, acoes], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER) if app.largo else ft.Column([info, acoes], spacing=10)
        return ft.Container(
            linha,
            padding=ft.Padding.symmetric(horizontal=16, vertical=14),
            border=None if ultima else ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
        )

    def _historico(self) -> ft.Control:
        app, c = self.app, self.app.c
        tentativas = app.db.tentativas(limite=8)
        if not tentativas:
            return ft.Container()
        linhas = []
        for t in tentativas:
            quando = datetime.fromisoformat(t["fim"]).strftime("%d/%m %H:%M")
            taxa = t["acertos"] / t["total"] if t["total"] else 0
            linhas.append(
                ft.Row(
                    [
                        ft.Container(comp.apagado(quando, c, 13.5), width=96),
                        ft.Container(comp.texto(t["titulo"], c, 14.5, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), expand=True),
                        comp.apagado("simulado" if t["modo"] == "simulado" else "estudo", c, 13),
                        ft.Container(
                            ft.Text(f"{t['acertos']}/{t['total']}", size=15, weight=ft.FontWeight.W_700, color=c["ok"] if taxa >= 0.7 else c["texto"]),
                            width=70,
                            alignment=ft.Alignment.CENTER_RIGHT,
                        ),
                    ],
                    spacing=12,
                )
            )
        return ft.Column([comp.subtitulo("Últimas tentativas", c, 21), comp.bloco(ft.Column(linhas, spacing=10), c, padding=18)], spacing=12)

    # ------------------------------------------------------------------

    def _recarregar(self):
        self.app.recarregar_tela_sem_perder(self)

    def _montar(self):
        from .montar import abrir_montador

        abrir_montador(self.app)

    def _abrir_pdf(self, p: dict):
        if not p.get("pdf_prova"):
            comp.mensagem(self.app.page, "Esta prova não tem PDF (é o simulado de demonstração).")
            return
        import webbrowser

        webbrowser.open(Path(p["pdf_prova"]).as_uri())

    # ------------------------------------------------------------------ marcar PDF

    def _marcar_prova(self, p: dict):
        from .marcador import abrir_marcador

        if not p.get("pdf_prova") or not Path(p["pdf_prova"]).exists():
            comp.mensagem(self.app.page, "Esta prova não tem o PDF guardado.")
            return
        abrir_marcador(self.app, Path(p["pdf_prova"]), titulo=p["titulo"])

    async def _marcar_novo(self, e=None):
        from .marcador import abrir_marcador, escolher_pdf

        pdf = await escolher_pdf(self.app)
        if pdf:
            abrir_marcador(self.app, pdf)

    def _pdfs(self) -> ft.Control:
        from .. import marcador
        from .marcador import abrir_marcador, dialogo_salvar, quando

        app, c = self.app, self.app.c
        explicacao = ft.Row(
            [
                ft.Container(ft.Icon(ft.Icons.BORDER_COLOR_OUTLINED, color=c["tinta"], size=26), bgcolor=c["tinta_suave"], border_radius=12, padding=12),
                ft.Column(
                    [
                        comp.texto("Marque e anote qualquer PDF", c, 16, peso=ft.FontWeight.W_700),
                        comp.apagado("Lei seca, apostila, edital ou prova: marca-texto em 4 cores, sublinhado e notas. Depois salve um PDF com as marcações, editáveis ou fixas. O arquivo original não muda.", c, 13.5),
                    ],
                    spacing=3,
                    expand=True,
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        botao = comp.botao("Abrir um PDF para marcar", self._marcar_novo, ft.Icons.FILE_OPEN_OUTLINED)
        topo = ft.Column([explicacao, botao], spacing=14) if not app.largo else ft.Row([ft.Container(explicacao, expand=True), botao], spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        recentes = marcador.recentes(app.pasta_conta)
        if not recentes:
            return ft.Column([comp.bloco(topo, c), comp.vazio(ft.Icons.PICTURE_AS_PDF_OUTLINED, "Nenhum PDF marcado ainda", "Os PDFs que você marcar ficam aqui para continuar depois, com todas as marcações.", c)], spacing=16)

        def esquecer(item):
            def confirmar(e):
                app.page.pop_dialog()
                marcador.esquecer(item["id"], app.pasta_conta)
                self._recarregar()

            app.page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Tirar da lista?"),
                    content=ft.Text(f"As marcações de “{item['titulo']}” guardadas no Aprova serão apagadas. O PDF original e os PDFs que você já salvou continuam onde estão."),
                    actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), ft.TextButton("Tirar da lista", on_click=confirmar)],
                )
            )

        def salvar(item):
            try:
                doc = marcador.DocumentoMarcado(Path(item["copia"]))
            except Exception:  # noqa: BLE001
                comp.mensagem(app.page, "Não consegui abrir esse PDF.")
                return
            dialogo_salvar(app, doc, depois=doc.fechar)

        linhas = ft.Column(spacing=0)
        for i, item in enumerate(recentes):
            n = item.get("marcacoes", 0)
            info = ft.Column(
                [
                    ft.Text(item["titulo"], size=16.5, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    comp.apagado(f"{item.get('paginas', 0)} páginas · {n} marcaç{'ão' if n == 1 else 'ões'} · aberto {quando(item.get('aberto_em', 0))}", c, 13),
                ],
                spacing=3,
                expand=True,
            )
            menu = ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                tooltip="Mais opções",
                items=[
                    ft.PopupMenuItem(content="Salvar PDF marcado", icon=ft.Icons.SAVE_ALT, on_click=lambda e, it=item: salvar(it)),
                    ft.PopupMenuItem(content="Tirar da lista", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e, it=item: esquecer(it)),
                ],
            )
            acoes = ft.Row([comp.botao_contorno("Continuar", lambda e, it=item: abrir_marcador(app, Path(it["copia"])), ft.Icons.EDIT_OUTLINED), menu], spacing=6, tight=True)
            linha = ft.Row([ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, color=c["erro"]), info, acoes], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER) if app.largo else ft.Column([ft.Row([ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, color=c["erro"]), info], spacing=12), acoes], spacing=8)
            linhas.controls.append(
                ft.Container(
                    linha,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                    border=None if i == len(recentes) - 1 else ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        return ft.Column([comp.bloco(topo, c), comp.subtitulo("Seus PDFs marcados", c, 21), comp.bloco(linhas, c, padding=8)], spacing=16)

    def _apagar(self, p: dict):
        app = self.app

        def confirmar(e):
            app.db.apagar_prova(p["id"])
            app.page.pop_dialog()
            app.telas.pop("inicio", None)
            self._recarregar()
            comp.mensagem(app.page, "Prova apagada.")

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Apagar esta prova?"),
                content=ft.Text(f"“{p['titulo']}” e o histórico de tentativas dela saem da biblioteca."),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), ft.TextButton("Apagar", on_click=confirmar)],
            )
        )

    async def _importar(self, e=None):
        app, c = self.app, self.app.c
        pdfs = await escolher_pdfs(app)
        if not pdfs:
            return
        corpo = ft.Column(tight=True, spacing=12, width=min(520, (app.page.width or 600) - 40))
        dlg = ft.AlertDialog(
            title=ft.Text("Importar prova", font_family=FONTE_TITULO, size=22),
            content=corpo,
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
        )
        app.page.show_dialog(dlg)
        res = await importar_arquivos(app, corpo, pdfs)
        if res:
            self._recarregar()
