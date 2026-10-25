"""Concursos: inscrições abertas, já realizados e a lista oficial das bancas."""

from __future__ import annotations

import flet as ft

from ..pci import REGIOES, Concurso, ErroRede, concurso_de_dict, concurso_para_dict
from . import comp
from .tema import FONTE_TITULO

NIVEIS = ["Fundamental", "Médio", "Técnico", "Superior"]


class TelaConcursos:
    def __init__(self, app):
        self.app = app
        self.aba = "abertos"
        self.regiao = app.aj["regiao"] if app.aj["regiao"] in REGIOES else "sudeste"
        self.filtro = ""
        self.niveis: set[str] = set()
        self.so_favoritos = False
        self.abertos: dict[str, list[Concurso]] = {}
        self.realizados: list[Concurso] = []
        self.busca_realizados = ""
        self.bancas: list = []
        self.filtro_bancas = ""
        self.situacao_bancas = "em andamento"
        self.carregando = False
        self.erro: str | None = None
        self.lista = ft.ListView(expand=True, spacing=0, padding=ft.Padding.only(bottom=40))
        self.status = ft.Container()
        self._abrir_url: str | None = None

    def preparar(self, abrir: str | None = None, **_):
        self._abrir_url = abrir

    # ------------------------------------------------------------------ layout

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        abas = ft.SegmentedButton(
            selected=[self.aba],
            segments=[
                ft.Segment(value="abertos", label=ft.Text("Inscrições abertas")),
                ft.Segment(value="realizados", label=ft.Text("Já realizados")),
                ft.Segment(value="bancas", label=ft.Text("Nas bancas")),
            ],
            show_selected_icon=False,
            on_change=self._trocar_aba,
        )
        topo = ft.Row(
            [comp.titulo("Concursos", c, 34 if app.largo else 28), ft.Container(expand=True), abas] if app.largo else [abas],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=not app.largo,
        )
        filhos: list[ft.Control] = []
        if not app.largo:
            filhos.append(comp.titulo("Concursos", c, 28))
        filhos.append(topo)
        filhos.append(self._filtros())
        filhos.append(self.status)
        filhos.append(self.lista)
        self._preencher()
        return ft.Column(filhos, spacing=16, expand=True)

    def _filtros(self) -> ft.Control:
        app, c = self.app, self.app.c
        if self.aba == "bancas":
            campo = ft.TextField(
                value=self.filtro_bancas,
                hint_text="Filtrar por nome (ex.: Dataprev, TJ, prefeitura)",
                prefix_icon=ft.Icons.SEARCH,
                border_radius=10,
                filled=True,
                dense=True,
                bgcolor=c["sup"],
                expand=True,
                on_change=self._filtrar_bancas,
            )
            situacao = ft.SegmentedButton(
                selected=[self.situacao_bancas],
                segments=[
                    ft.Segment(value="em andamento", label=ft.Text("Em andamento")),
                    ft.Segment(value="realizado", label=ft.Text("Realizados")),
                ],
                show_selected_icon=False,
                on_change=self._trocar_situacao,
            )
            return ft.Column(
                [
                    ft.Row([campo, situacao], spacing=10) if app.largo else ft.Column([campo, situacao], spacing=10),
                    comp.apagado(
                        "Lista oficial da banca, com provas e gabaritos direto do site dela. Hoje: FGV Conhecimento. "
                        "Para outras bancas, cole o link da página do concurso na aba Provas.",
                        c,
                        13.5,
                    ),
                ],
                spacing=8,
            )
        if self.aba == "realizados":
            campo = ft.TextField(
                value=self.busca_realizados,
                hint_text="Órgão, cidade ou cargo (ex.: TJ-SP, INSS, escrevente)",
                prefix_icon=ft.Icons.SEARCH,
                border_radius=10,
                filled=True,
                bgcolor=c["sup"],
                expand=True,
                on_submit=self._buscar_realizados,
                on_change=lambda e: setattr(self, "busca_realizados", e.control.value),
                autofocus=True,
            )
            return ft.Column(
                [
                    ft.Row([campo, comp.botao("Buscar", self._buscar_realizados, ft.Icons.SEARCH)], spacing=10),
                    comp.apagado(
                        "Veja concursos que já aconteceram para conhecer a banca e baixar as provas anteriores.", c, 13.5
                    ),
                ],
                spacing=8,
            )
        regiao = ft.Dropdown(
            value=self.regiao,
            options=[ft.DropdownOption(key=k, text=v[0]) for k, v in REGIOES.items()],
            on_select=self._trocar_regiao,
            width=190,
            dense=True,
            border_radius=10,
            filled=True,
            bgcolor=c["sup"],
        )
        busca = ft.TextField(
            value=self.filtro,
            hint_text="Filtrar por órgão, cargo ou UF",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=10,
            filled=True,
            dense=True,
            bgcolor=c["sup"],
            expand=True if app.largo else None,
            on_change=self._filtrar,
        )
        chips = [
            ft.Chip(
                label=ft.Text(n),
                selected=n in self.niveis,
                on_select=lambda e, n=n: self._alternar_nivel(n),
                show_checkmark=False,
                selected_color=c["tinta_suave"],
                bgcolor=c["sup"],
                border_side=ft.BorderSide(1, c["borda"]),
            )
            for n in NIVEIS
        ]
        chips.append(
            ft.Chip(
                label=ft.Text("Acompanhando"),
                leading=ft.Icon(ft.Icons.STAR_ROUNDED, size=16, color=c["marca"]),
                selected=self.so_favoritos,
                on_select=lambda e: self._alternar_favoritos(),
                show_checkmark=False,
                selected_color=c["marca_suave"],
                bgcolor=c["sup"],
                border_side=ft.BorderSide(1, c["borda"]),
            )
        )
        linha1 = ft.Row([regiao, busca], spacing=10) if app.largo else ft.Column([ft.Row([regiao], spacing=10), busca], spacing=10)
        return ft.Column([linha1, ft.Row(chips, spacing=8, wrap=True, run_spacing=8)], spacing=10)

    # ------------------------------------------------------------------ eventos

    def _encher(self, b) -> None:
        from .. import coleta
        from .coleta import abrir_coleta

        abrir_coleta(self.app, f"{coleta.nome_curto(b.nome)} {coleta.ano_de(b.nome, b.url)}".strip())

    def _trocar_aba(self, e):
        self.aba = e.control.selected[0] if e.control.selected else "abertos"
        self.app.recarregar_tela_sem_perder(self)
        if self.aba == "bancas" and not self.bancas and not self.carregando:
            self.app.page.run_task(self.carregar_bancas)

    def _trocar_regiao(self, e):
        self.regiao = e.control.value or "todas"
        self.app.aj.set("regiao", self.regiao)
        if self.regiao not in self.abertos:
            self.app.page.run_task(self.carregar)
        else:
            self._preencher()
            self.app.atualizar()

    def _filtrar(self, e):
        self.filtro = e.control.value or ""
        self._preencher()
        self.app.atualizar()

    def _alternar_nivel(self, n: str):
        self.niveis ^= {n}
        self._preencher()
        self.app.recarregar_tela_sem_perder(self)

    def _alternar_favoritos(self):
        self.so_favoritos = not self.so_favoritos
        self.app.recarregar_tela_sem_perder(self)

    async def _buscar_realizados(self, e=None):
        termo = (self.busca_realizados or "").strip()
        if len(termo) < 2:
            comp.mensagem(self.app.page, "Digite pelo menos 2 letras para buscar.")
            return
        self.carregando, self.erro = True, None
        self._preencher()
        self.app.atualizar()
        try:
            self.realizados = await self.app.em_segundo_plano(self.app.pci.concursos_realizados, termo)
        except ErroRede as ex:
            self.erro = str(ex)
            self.realizados = []
        self.carregando = False
        self._preencher()
        self.app.atualizar()

    def _filtrar_bancas(self, e):
        self.filtro_bancas = e.control.value or ""
        self._preencher()
        self.app.atualizar()

    def _trocar_situacao(self, e):
        self.situacao_bancas = e.control.selected[0] if e.control.selected else "em andamento"
        self._preencher()
        self.app.atualizar()

    async def carregar_bancas(self):
        self.carregando, self.erro = True, None
        self._preencher()
        self.app.atualizar()
        try:
            self.bancas = await self.app.em_segundo_plano(self.app.central.concursos_fgv)
        except ErroRede as ex:
            self.erro = str(ex)
        self.carregando = False
        self._preencher()
        self.app.atualizar()

    def ao_mostrar(self):
        if self.aba == "abertos" and self.regiao not in self.abertos and not self.carregando:
            self.app.page.run_task(self.carregar)
        if self.aba == "bancas" and not self.bancas and not self.carregando:
            self.app.page.run_task(self.carregar_bancas)
        if self._abrir_url:
            url, self._abrir_url = self._abrir_url, None
            dados = next((d for d in self.app.db.favoritos() if d.get("url") == url), None)
            if dados:
                self.app.page.run_task(abrir_edital, self.app, concurso_de_dict(dados))

    async def carregar(self):
        regiao = self.regiao
        self.carregando, self.erro = True, None
        self._preencher()
        self.app.atualizar()
        try:
            self.abertos[regiao] = await self.app.em_segundo_plano(self.app.pci.concursos_abertos, regiao)
        except ErroRede as ex:
            self.erro = str(ex)
        self.carregando = False
        self._preencher()
        self.app.atualizar()

    # ------------------------------------------------------------------ lista

    def _visiveis(self) -> list[Concurso]:
        if self.aba == "realizados":
            return self.realizados
        itens = list(self.abertos.get(self.regiao, []))
        if self.so_favoritos:
            favs = {d["url"] for d in self.app.db.favoritos()}
            itens = [i for i in itens if i.url in favs]
        if self.niveis:
            itens = [i for i in itens if any(n.lower() in i.nivel.lower() for n in self.niveis)]
        f = self.filtro.strip().lower()
        if f:
            itens = [i for i in itens if f in f"{i.nome} {i.cargos} {i.uf} {i.titulo}".lower()]
        return itens

    def _preencher(self):
        c = self.app.c
        self.lista.controls.clear()
        if self.carregando:
            fonte = "no site da FGV" if self.aba == "bancas" else "no PCI Concursos"
            self.status.content = comp.carregando(f"Buscando concursos {fonte}…", c)
            return
        if self.aba == "bancas" and not self.erro:
            self._preencher_bancas()
            return
        if self.erro:
            tentar = {"abertos": self.carregar, "realizados": self._buscar_realizados, "bancas": self.carregar_bancas}[self.aba]
            self.status.content = comp.aviso(self.erro, c, "erro", comp.botao_texto("Tentar de novo", lambda e: self.app.page.run_task(tentar)))
            return
        itens = self._visiveis()
        if self.aba == "realizados" and not self.realizados:
            self.status.content = None
            self.lista.controls.append(
                comp.vazio(ft.Icons.HISTORY, "Concursos que já passaram", "Busque um órgão ou cargo para ver os editais anteriores e as provas aplicadas.", c)
            )
            return
        total = len(self.abertos.get(self.regiao, [])) if self.aba == "abertos" else len(itens)
        rotulo = f"{len(itens)} de {total} concursos" if len(itens) != total else f"{total} concursos"
        self.status.content = comp.apagado(rotulo, c, 13.5)
        if not itens:
            self.lista.controls.append(comp.vazio(ft.Icons.SEARCH_OFF, "Nada encontrado", "Tente outra região ou tire alguns filtros.", c))
            return
        favs = {d["url"] for d in self.app.db.favoritos()}
        uf_anterior = None
        for item in itens[:400]:
            if self.aba == "abertos" and item.uf != uf_anterior and not self.filtro:
                uf_anterior = item.uf
                self.lista.controls.append(
                    ft.Container(
                        ft.Text("Nacionais" if item.uf == "BR" else item.uf, size=13, color=c["texto2"], weight=ft.FontWeight.W_700),
                        padding=ft.Padding.only(top=18, bottom=6, left=4),
                    )
                )
            self.lista.controls.append(self._linha(item, item.url in favs))

    def _preencher_bancas(self):
        app, c = self.app, self.app.c
        f = self.filtro_bancas.strip().lower()
        itens = [b for b in self.bancas if b.situacao == self.situacao_bancas and (not f or f in b.nome.lower() or f in b.url.lower())]
        self.status.content = comp.apagado(f"{len(itens)} concursos da FGV", c, 13.5)
        if not itens:
            self.lista.controls.append(comp.vazio(ft.Icons.SEARCH_OFF, "Nada encontrado", "Tente outro nome ou troque entre em andamento e realizados.", c))
            return
        from .. import coleta

        for b in itens[:300]:
            curto = f"{coleta.nome_curto(b.nome)} {coleta.ano_de(b.nome, b.url)}".strip()
            textos = ft.Column(
                [
                    comp.texto(curto, c, 15.5, peso=ft.FontWeight.W_600, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    comp.apagado(b.nome if b.nome != curto else b.url.replace("https://", ""), c, 12.5, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=2,
                expand=True,
            )
            encher = comp.botao_texto("Encher biblioteca", lambda e, b=b: self._encher(b), ft.Icons.LIBRARY_ADD_OUTLINED)
            ver = comp.botao_contorno("Ver provas", lambda e, b=b: app.ir("provas", termo=b.url, rotulo=b.nome), ft.Icons.DESCRIPTION_OUTLINED)
            selo = comp.pilula(b.banca, c["tinta_suave"], c["tinta"], tamanho=11.5)
            if app.largo:
                conteudo = ft.Row(
                    [ft.Container(selo, width=68, alignment=ft.Alignment.CENTER), textos, encher, ver],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            else:
                conteudo = ft.Column(
                    [ft.Row([selo, textos], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START), ft.Row([ver, encher], spacing=6)],
                    spacing=8,
                )
            self.lista.controls.append(
                ft.Container(
                    conteudo,
                    padding=ft.Padding.symmetric(vertical=12, horizontal=8),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )

    def _linha(self, item: Concurso, favorito: bool) -> ft.Control:
        app, c = self.app, self.app.c
        detalhes: list[ft.Control] = []
        if item.vagas:
            detalhes.append(comp.texto(item.vagas, c, 13.5, peso=ft.FontWeight.W_600))
        if item.salario:
            detalhes.append(comp.texto(item.salario, c, 13.5, cor=c["ok"], peso=ft.FontWeight.W_600))
        if item.nivel:
            detalhes.append(comp.apagado(item.nivel, c, 13.5))
        estrela = ft.IconButton(
            icon=ft.Icons.STAR_ROUNDED if favorito else ft.Icons.STAR_BORDER_ROUNDED,
            icon_color=c["marca"] if favorito else c["texto2"],
            tooltip="Parar de acompanhar" if favorito else "Acompanhar prazo",
            on_click=lambda e, it=item: self._alternar_favorito(e, it),
        )
        esquerda = (
            comp.bloco_data(item.prazo_fim, c, item.dias_restantes, item.prazo_inicio if item.inscricoes_futuras else None)
            if self.aba == "abertos"
            else ft.Container(
                ft.Text(item.prazo or "—", size=13, color=c["texto2"], text_align=ft.TextAlign.CENTER), width=68, alignment=ft.Alignment.CENTER
            )
        )
        return ft.Container(
            content=ft.Row(
                [
                    esquerda,
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    comp.pilula(item.uf or "—", c["sup2"], c["texto2"], tamanho=11.5),
                                    ft.Container(
                                        comp.texto(item.nome, c, 16, peso=ft.FontWeight.W_600, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                        expand=True,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            comp.apagado(item.cargos, c, 14, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS) if item.cargos else ft.Container(),
                            ft.Row(detalhes, spacing=16, wrap=True, run_spacing=2),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    estrela,
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(vertical=12, horizontal=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
            on_click=lambda e, it=item: app.page.run_task(abrir_edital, app, it),
            ink=True,
            border_radius=8,
        )

    def _alternar_favorito(self, e, item: Concurso):
        db = self.app.db
        if db.eh_favorito(item.url):
            db.desfavoritar(item.url)
            comp.mensagem(self.app.page, "Você parou de acompanhar este concurso.")
        else:
            db.favoritar(item.url, item.nome, concurso_para_dict(item))
            comp.mensagem(self.app.page, "Acompanhando. O prazo aparece na tela Início.")
        self._preencher()
        self.app.atualizar()


async def abrir_edital(app, concurso: Concurso) -> None:
    """Janela com o resumo do edital, PDFs e link para as provas anteriores."""
    c = app.c
    corpo = ft.Column([comp.carregando("Abrindo o edital…", c)], tight=True, spacing=12, scroll=ft.ScrollMode.AUTO)
    largura = min(680, (app.page.width or 700) - 40)
    dlg = ft.AlertDialog(
        title=ft.Text(concurso.nome, font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
        content=ft.Container(corpo, width=largura, height=min(520, (app.page.height or 700) - 220)),
        actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
        scrollable=False,
    )
    app.page.show_dialog(dlg)
    try:
        ed = await app.em_segundo_plano(app.pci.edital, concurso.url)
    except ErroRede as ex:
        corpo.controls = [comp.aviso(str(ex), c, "erro"), comp.botao_contorno("Abrir no site", url=concurso.url, icone=ft.Icons.OPEN_IN_NEW)]
        app.page.update()
        return
    resumo: list[ft.Control] = []
    linha_dados = [comp.pilula(concurso.uf or "—", c["sup2"], c["texto2"])]
    if concurso.vagas:
        linha_dados.append(comp.pilula(concurso.vagas, c["tinta_suave"], c["tinta"]))
    if concurso.salario:
        linha_dados.append(comp.pilula(concurso.salario, c["ok_suave"], c["ok"]))
    if concurso.prazo:
        linha_dados.append(comp.pilula("Inscrições: " + concurso.prazo, c["marca_suave"], c["texto"]))
    resumo.append(ft.Row(linha_dados, wrap=True, spacing=8, run_spacing=8))
    if ed.titulo:
        resumo.append(comp.texto(ed.titulo, c, 16, peso=ft.FontWeight.W_600))
    if ed.data:
        resumo.append(comp.apagado(f"Publicado em {ed.data}", c, 13))
    if ed.descricao:
        resumo.append(comp.texto(ed.descricao, c, 15))
    for ptx in ed.paragrafos[:14]:
        resumo.append(ft.Text(ptx, size=14.5, color=c["texto"], selectable=True))
    if ed.pdfs:
        resumo.append(comp.subtitulo("Arquivos do edital", c, 17))
        for a in ed.pdfs[:12]:
            resumo.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, color=c["erro"]),
                    title=ft.Text(a.nome, size=14.5),
                    url=a.url,
                    dense=True,
                )
            )
    resumo.append(comp.aviso("Confira sempre as datas e regras no edital oficial.", c, "info"))
    corpo.controls = resumo
    acoes: list[ft.Control] = []

    def buscar_provas(e):
        app.page.pop_dialog()
        app.ir("provas", url=ed.provas_url, rotulo=concurso.nome, termo=concurso.nome.split(" - ")[0].strip())

    acoes.append(comp.botao("Buscar provas", buscar_provas, ft.Icons.TRAVEL_EXPLORE))
    def montar_simulado(e):
        from .montar import abrir_montador

        app.page.pop_dialog()
        curto = concurso.nome.split(" - ")[0].strip()
        abrir_montador(app, filtro=curto, nome=f"Simulado {curto}")

    acoes.append(comp.botao_contorno("Montar simulado", montar_simulado, ft.Icons.TUNE_ROUNDED))
    eh_fav = app.db.eh_favorito(concurso.url)

    def alternar(e):
        if app.db.eh_favorito(concurso.url):
            app.db.desfavoritar(concurso.url)
            e.control.content = "Acompanhar"
            e.control.icon = ft.Icons.STAR_BORDER_ROUNDED
        else:
            app.db.favoritar(concurso.url, concurso.nome, concurso_para_dict(concurso))
            e.control.content = "Acompanhando"
            e.control.icon = ft.Icons.STAR_ROUNDED
        e.control.update()
        tela = app.telas.get("concursos")
        if tela is not None:
            tela._preencher()

    acoes.append(comp.botao_texto("Acompanhando" if eh_fav else "Acompanhar", alternar, ft.Icons.STAR_ROUNDED if eh_fav else ft.Icons.STAR_BORDER_ROUNDED))
    acoes.append(comp.botao_texto("Abrir no site", url=concurso.url, icone=ft.Icons.OPEN_IN_NEW))
    acoes.append(ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog()))
    dlg.actions = acoes
    dlg.actions_alignment = ft.MainAxisAlignment.END
    app.page.update()
