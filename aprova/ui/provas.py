"""Provas: escolha um concurso e o Aprova procura a prova em várias fontes."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import flet as ft

from .. import config, fontes, importador
from ..pci import Arquivo, ErroRede, ProvaItem
from . import comp
from .estudar import abrir_prova, escolher_pdfs, importar_arquivos
from .tema import FONTE_TITULO

SUGESTOES = ["Dataprev 2026", "TJ-SP escrevente", "INSS", "Banco do Brasil", "Caixa", "Receita Federal", "VUNESP", "Cebraspe"]

ROTULO_TIPO = {"prova": "Prova", "gabarito": "Gabarito", "edital": "Edital", "comentada": "Prova comentada", "outro": "Arquivo"}


class TelaProvas:
    def __init__(self, app):
        self.app = app
        self.termo = ""
        self.pci_url: str | None = None  # lista de provas do órgão no PCI (vinda do edital)
        self.rotulo = ""
        self.resultado: fontes.Resultado | None = None
        self.pci_pagina = 1
        self.pci_paginas = 0
        self.carregando = False
        self.passo = ""
        self.erro: str | None = None
        self.lista = ft.Column(spacing=18)
        self.status = ft.Container()
        self._pendente = False

    def preparar(self, url: str | None = None, rotulo: str = "", termo: str | None = None, **_):
        """url: lista de provas do PCI; termo: nome do concurso ou link da página da banca."""
        self.pci_url = url
        self.rotulo = rotulo
        self.termo = termo or _nome_curto(rotulo) or ""
        self.resultado, self.erro = None, None
        self._pendente = True

    def ao_mostrar(self):
        if self._pendente:
            self._pendente = False
            self.app.page.run_task(self.buscar)

    # ------------------------------------------------------------------ layout

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        self.campo = ft.TextField(
            value=self.termo,
            hint_text="Concurso (ex.: Dataprev 2026, TJ-SP escrevente) ou cole o link da página do concurso",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=10,
            filled=True,
            bgcolor=c["sup"],
            expand=True,
            on_submit=self._buscar_campo,
        )
        sugestoes = ft.Row(
            [
                ft.Chip(label=ft.Text(s), on_click=lambda e, s=s: self._sugestao(s), bgcolor=c["sup"], border_side=ft.BorderSide(1, c["borda"]))
                for s in (SUGESTOES if app.largo else SUGESTOES[:4])
            ],
            wrap=True,
            spacing=8,
            run_spacing=8,
        )
        filhos: list[ft.Control] = [
            comp.titulo("Provas", c, 34 if app.largo else 28),
            comp.apagado(
                "Escolha um concurso e o Aprova procura a prova e o gabarito no site oficial da banca, em outros sites e no PCI Concursos.",
                c,
                14.5,
            ),
            ft.Row([self.campo, comp.botao("Buscar", self._buscar_campo, ft.Icons.SEARCH)], spacing=10),
            sugestoes,
            self.status,
            self.lista,
            ft.Container(height=30),
        ]
        self._preencher()
        return ft.Column(filhos, spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def _sugestao(self, s: str):
        self.campo.value = s
        self._buscar_campo(None)

    def _buscar_campo(self, e):
        termo = (self.campo.value or "").strip()
        if len(termo) < 2:
            comp.mensagem(self.app.page, "Digite o nome do concurso.")
            return
        self.termo, self.pci_url, self.rotulo = termo, None, ""
        self.resultado = None
        self.app.page.run_task(self.buscar)

    async def buscar(self):
        app = self.app
        if not self.termo and not self.pci_url:
            self._preencher()
            app.atualizar()
            return
        self.carregando, self.erro, self.passo = True, None, "Começando a busca…"
        self._preencher()
        app.atualizar()

        def progresso(f, texto):
            self.passo = texto
            try:
                self.status.content = comp.carregando(texto, app.c)
                self.status.update()
            except Exception:  # noqa: BLE001
                pass

        try:
            res = await app.em_segundo_plano(app.central.buscar, self.termo or self.rotulo, progresso, self.pci_url is None)
            if self.pci_url:
                try:
                    itens, paginas = await app.em_segundo_plano(app.pci.provas, self.pci_url, 1)
                    res.pci, self.pci_paginas, self.pci_pagina = itens, paginas, 1
                except ErroRede as ex:
                    res.avisos.append(f"PCI Concursos: {ex}")
            self.resultado = res
        except Exception as ex:  # noqa: BLE001
            self.erro = f"A busca falhou: {ex}"
        self.carregando = False
        self._preencher()
        app.atualizar()

    async def _mais_pci(self, e):
        if not self.pci_url or not self.resultado:
            return
        self.pci_pagina += 1
        try:
            itens, _ = await self.app.em_segundo_plano(self.app.pci.provas, self.pci_url, self.pci_pagina)
            self.resultado.pci += itens
        except ErroRede as ex:
            comp.mensagem(self.app.page, str(ex))
        self._preencher()
        self.app.atualizar()

    # ------------------------------------------------------------------ resultados

    def _preencher(self):
        c = self.app.c
        self.lista.controls.clear()
        if self.carregando:
            self.status.content = comp.carregando(self.passo or "Procurando…", c)
            return
        if self.erro:
            self.status.content = comp.aviso(self.erro, c, "erro", comp.botao_texto("Tentar de novo", lambda e: self.app.page.run_task(self.buscar)))
            return
        r = self.resultado
        if r is None:
            self.status.content = None
            self.lista.controls.append(
                comp.vazio(
                    ft.Icons.TRAVEL_EXPLORE,
                    "Qual concurso você quer?",
                    "Digite o nome (com o ano, se souber) ou cole o link da página do concurso no site da banca.",
                    c,
                )
            )
            return
        provas_oficiais = [a for a in r.oficiais if a.tipo == "prova"]
        resumo = []
        def qtd(n, um, varios):
            return f"{n} {um if n == 1 else varios}"

        if r.oficiais:
            resumo.append(qtd(len(provas_oficiais), "prova", "provas") + " no site oficial")
        if r.web:
            resumo.append(qtd(len(r.web), "arquivo", "arquivos") + " em outros sites")
        if r.pci:
            resumo.append(qtd(len(r.pci), "prova", "provas") + " no PCI Concursos")
        texto_resumo = ", ".join(resumo) if resumo else "Nenhum arquivo encontrado."
        if r.web_falhou and r.total:
            texto_resumo += " · os buscadores da internet não responderam agora, então “Outros sites” ficou de fora"
        self.status.content = comp.apagado(texto_resumo, c, 13.5)
        for aviso in r.avisos:
            self.lista.controls.append(comp.aviso(aviso, c, "alerta"))
        if provas_oficiais or any(a.tipo == "prova" for a in r.web):
            self.lista.controls.append(self._cartao_encher(r, len(provas_oficiais)))
        if r.oficiais:
            self.lista.controls.append(self._secao_oficial(r))
        if r.web:
            self.lista.controls.append(self._secao_web(r.web))
        if r.pci:
            self.lista.controls.append(self._secao_pci(r.pci))
        if not r.total:
            self.lista.controls.append(
                comp.vazio(
                    ft.Icons.SEARCH_OFF,
                    "Não achei provas desse concurso",
                    "Tente só o nome do órgão (ex.: “Dataprev”), o cargo, ou cole o link da página do concurso no site da banca.",
                    c,
                )
            )

    def _cabecalho_secao(self, titulo: str, descricao: str, icone) -> ft.Control:
        c = self.app.c
        return ft.Column(
            [
                ft.Row([ft.Icon(icone, color=c["tinta"], size=20), comp.subtitulo(titulo, c, 19)], spacing=8),
                comp.apagado(descricao, c, 13.5),
            ],
            spacing=2,
        )

    def _secao_oficial(self, r: fontes.Resultado) -> ft.Control:
        app, c = self.app, self.app.c
        linhas: list[ft.Control] = []
        for g in fontes.agrupar_por_cargo(r.oficiais):
            gab = g["gabarito"]
            cadernos = [
                ft.Chip(
                    label=ft.Text(f"Caderno {a.caderno}" if a.caderno else "Prova"),
                    leading=ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=16, color=c["tinta"]),
                    on_click=lambda e, a=a, gab=gab, g=g: app.page.run_task(importar_achado, app, a, gab, r.termo),
                    bgcolor=c["tinta_suave"],
                    border_side=ft.BorderSide(1, c["tinta_suave"]),
                )
                for a in g["cadernos"]
            ]
            linhas.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    comp.texto(_bonito(g["cargo"]), c, 15.5, peso=ft.FontWeight.W_600, expand=True),
                                    comp.pilula("com gabarito" if gab else "sem gabarito", c["ok_suave"] if gab else c["marca_suave"], c["ok"] if gab else c["marca"]),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            ft.Row(cadernos, wrap=True, spacing=8, run_spacing=8),
                        ],
                        spacing=8,
                    ),
                    padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        extras = [a for a in r.oficiais if a.tipo in ("gabarito", "edital", "comentada")]
        if extras:
            linhas.append(ft.Container(comp.apagado("Gabaritos e editais", c, 13), padding=ft.Padding.only(left=14, top=10)))
            for a in extras[:12]:
                linhas.append(self._linha_arquivo(a))
        paginas = ft.Row(
            [
                comp.botao_texto(f"Página do concurso: {p.banca}", url=p.url, icone=ft.Icons.OPEN_IN_NEW)
                for p in r.paginas_oficiais[:3]
            ],
            wrap=True,
        )
        return ft.Column(
            [
                self._cabecalho_secao(
                    "Site oficial da banca",
                    "Toque no caderno da sua área: o Aprova baixa a prova, junta o gabarito oficial e deixa pronta para resolver.",
                    ft.Icons.VERIFIED_OUTLINED,
                ),
                paginas,
                comp.bloco(ft.Column(linhas, spacing=0), c, padding=4),
            ],
            spacing=10,
        )

    def _linha_arquivo(self, a: fontes.Achado) -> ft.Control:
        app, c = self.app, self.app.c
        cor = {"gabarito": (c["ok_suave"], c["ok"]), "edital": (c["sup2"], c["texto2"]), "comentada": (c["marca_suave"], c["marca"])}.get(
            a.tipo, (c["tinta_suave"], c["tinta"])
        )
        acao = (
            ft.IconButton(ft.Icons.DOWNLOAD_ROUNDED, tooltip="Baixar e resolver aqui", on_click=lambda e, a=a: app.page.run_task(importar_achado, app, a, None, ""))
            if a.tipo in ("prova", "comentada")
            else ft.IconButton(ft.Icons.OPEN_IN_NEW, tooltip="Abrir", url=a.url)
        )
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, color=c["erro"], size=20),
                    ft.Column(
                        [
                            comp.texto(a.titulo, c, 14.5, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Row([comp.pilula(ROTULO_TIPO.get(a.tipo, "Arquivo"), *cor, tamanho=11.5), comp.apagado(a.fonte, c, 12.5)], spacing=8),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    acao,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        )

    def _cartao_encher(self, r: fontes.Resultado, n_oficiais: int) -> ft.Control:
        app, c = self.app, self.app.c
        from .coleta import abrir_coleta

        cargos = len({fontes.norm(a.cargo or a.titulo) for a in r.oficiais if a.tipo == "prova"})
        detalhe = (
            f"Baixa de uma vez as provas de {cargos} cargo{'s' if cargos != 1 else ''} desta edição e das anteriores, com o gabarito oficial."
            if n_oficiais
            else "Baixa de uma vez os PDFs de prova encontrados."
        )
        texto = ft.Column(
            [
                comp.texto("Treinar para este concurso", c, 16, peso=ft.FontWeight.W_700),
                comp.apagado(detalhe + " Depois é só montar simulados com elas.", c, 13.5),
            ],
            spacing=3,
            expand=True,
        )
        termo = r.termo or self.rotulo
        if termo.startswith("http") and self.rotulo and not self.rotulo.startswith("http"):
            from .. import coleta

            # link de uma página da banca: usa o nome para achar também as edições anteriores
            termo = f"{coleta.nome_curto(self.rotulo)} {coleta.ano_de(self.rotulo, termo)}".strip()
        botao = comp.botao("Encher a biblioteca", lambda e: abrir_coleta(app, termo, r), ft.Icons.LIBRARY_ADD_OUTLINED)
        conteudo = (
            ft.Row([ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED, color=c["tinta"], size=26), texto, botao], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            if app.largo
            else ft.Column([ft.Row([ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED, color=c["tinta"], size=24), texto], spacing=12), botao], spacing=10)
        )
        return ft.Container(conteudo, bgcolor=c["tinta_suave"], border_radius=14, padding=ft.Padding.symmetric(horizontal=18, vertical=14))

    def _secao_web(self, achados: list[fontes.Achado]) -> ft.Control:
        c = self.app.c
        ordem = {"prova": 0, "gabarito": 1, "comentada": 2, "edital": 3}
        itens = sorted(achados, key=lambda a: ordem.get(a.tipo, 9))
        return ft.Column(
            [
                self._cabecalho_secao(
                    "Outros sites",
                    "PDFs encontrados na internet. Confira se são do concurso certo antes de resolver.",
                    ft.Icons.PUBLIC,
                ),
                comp.bloco(ft.Column([self._linha_arquivo(a) for a in itens[:15]], spacing=0), c, padding=4),
            ],
            spacing=10,
        )

    def _secao_pci(self, itens: list[ProvaItem]) -> ft.Control:
        c = self.app.c
        importadas = {p["origem_url"]: p["id"] for p in self.app.db.provas()}
        linhas = [self._linha_pci(it, importadas.get(it.url)) for it in itens]
        filhos: list[ft.Control] = [
            self._cabecalho_secao(
                "PCI Concursos",
                "Acervo grande de provas antigas. O download passa pelo seu navegador por causa da verificação de segurança do site.",
                ft.Icons.ARCHIVE_OUTLINED,
            ),
            comp.bloco(ft.Column(linhas, spacing=0), c, padding=4),
        ]
        if self.pci_url and self.pci_paginas > self.pci_pagina:
            filhos.append(ft.Row([comp.botao_contorno("Carregar mais provas do PCI", self._mais_pci, ft.Icons.EXPAND_MORE)], alignment=ft.MainAxisAlignment.CENTER))
        return ft.Column(filhos, spacing=10)

    def _linha_pci(self, it: ProvaItem, prova_id: int | None) -> ft.Control:
        app, c = self.app, self.app.c
        direita: list[ft.Control] = []
        if prova_id:
            direita.append(comp.pilula("na biblioteca", c["ok_suave"], c["ok"], ft.Icons.CHECK_ROUNDED))
        direita.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, color=c["texto2"]))
        dados = ft.Row(
            [
                comp.texto(it.ano, c, 13.5, peso=ft.FontWeight.W_700),
                comp.apagado(it.orgao, c, 13.5),
                comp.pilula(it.banca, c["sup2"], c["texto2"], tamanho=11.5) if it.banca else ft.Container(),
            ],
            spacing=14,
            wrap=True,
        )
        return ft.Container(
            ft.Row(
                [
                    ft.Column([comp.texto(it.cargo, c, 15, peso=ft.FontWeight.W_600), dados], spacing=4, expand=True),
                    ft.Row(direita, spacing=6, tight=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
            on_click=lambda e, i=it, pid=prova_id: self._abrir_pci(i, pid),
            ink=True,
            border_radius=8,
        )

    def _abrir_pci(self, it: ProvaItem, prova_id: int | None):
        app = self.app
        if prova_id:
            app.page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text(it.cargo, font_family=FONTE_TITULO, size=22),
                    content=comp.apagado("Esta prova já está na sua biblioteca.", app.c, 14.5),
                    actions=[
                        ft.TextButton("Baixar de novo", on_click=lambda e: (app.page.pop_dialog(), app.page.run_task(baixar_prova, app, it))),
                        comp.botao_contorno("Modo estudo", lambda e: (app.page.pop_dialog(), abrir_prova(app, prova_id, "estudo"))),
                        comp.botao("Fazer simulado", lambda e: (app.page.pop_dialog(), abrir_prova(app, prova_id, "simulado"))),
                    ],
                )
            )
            return
        app.page.run_task(baixar_prova, app, it)


def _ano(texto: str) -> str:
    m = re.search(r"\b(20\d\d)\b", texto)
    return m.group(1) if m else ""


def _nome_curto(nome: str) -> str:
    return re.split(r"\s+[-–]\s+", nome or "")[0].strip()


def _bonito(texto: str) -> str:
    """'DESENVOLVIMENTO DE SOFTWARE' -> 'Desenvolvimento de Software' (mantém siglas curtas)."""
    if not texto or not texto.isupper():
        return texto
    menores = {"de", "da", "do", "das", "dos", "e", "em", "para", "a", "o"}
    saida = []
    for w in texto.lower().split():
        saida.append(w if w in menores else (w.upper() if len(w) <= 3 and w not in menores and w.isalpha() and w in {"ti", "tic", "ui", "ux"} else w.capitalize()))
    return " ".join(saida)


async def importar_achado(app, prova: fontes.Achado, gabarito: fontes.Achado | None, concurso: str) -> None:
    """Baixa a prova (e o gabarito) de um link direto e importa para a biblioteca."""
    c = app.c
    corpo = ft.Column([comp.carregando("Baixando a prova…", c)], tight=True, spacing=12, width=min(540, (app.page.width or 600) - 40))
    titulo_cargo = _bonito(prova.cargo or prova.titulo)
    dlg = ft.AlertDialog(
        title=ft.Column(
            [
                ft.Text(titulo_cargo, font_family=FONTE_TITULO, size=21, weight=ft.FontWeight.W_600),
                comp.apagado("   ".join(x for x in (concurso, f"caderno {prova.caderno}" if prova.caderno else "", prova.fonte) if x), c, 13),
            ],
            tight=True,
            spacing=2,
        ),
        content=corpo,
        actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
    )
    app.page.show_dialog(dlg)
    pasta = config.CACHE_DIR / "downloads" / str(int(time.time()))
    arquivos: list[Path] = []
    try:
        nome = Path(prova.url.split("?")[0]).name or "prova.pdf"
        arquivos.append(await app.em_segundo_plano(app.pci.baixar, prova.url, pasta / nome))
        if gabarito:
            corpo.controls = [comp.carregando("Baixando o gabarito oficial…", c)]
            app.page.update()
            gnome = Path(gabarito.url.split("?")[0]).name or "gabarito.pdf"
            if "gab" not in gnome.lower():
                gnome = "gabarito-" + gnome
            try:
                arquivos.append(await app.em_segundo_plano(app.pci.baixar, gabarito.url, pasta / gnome))
            except ErroRede as ex:
                comp.mensagem(app.page, f"Não consegui baixar o gabarito ({ex}).")
    except ErroRede as ex:
        corpo.controls = [
            comp.aviso(f"Não consegui baixar a prova: {ex}", c, "erro"),
            comp.botao_contorno("Abrir o arquivo no navegador", url=prova.url, icone=ft.Icons.OPEN_IN_NEW),
        ]
        app.page.update()
        return
    meta = {
        "titulo": " — ".join(x for x in (titulo_cargo, concurso) if x) + (f" (caderno {prova.caderno})" if prova.caderno else ""),
        "cargo": prova.cargo,
        "caderno": prova.caderno,
        "orgao": concurso,
        "banca": prova.fonte.replace(" (site oficial)", "") if prova.oficial else "",
        "ano": _ano(concurso + " " + prova.url),
        "origem_url": prova.url,
    }
    await importar_arquivos(app, corpo, arquivos, meta)


async def baixar_prova(app, it: ProvaItem) -> None:
    """Fluxo de download: tenta baixar direto; se o site pedir verificação,
    abre a página no navegador e espera os arquivos aparecerem em Downloads."""
    c = app.c
    corpo = ft.Column([comp.carregando("Procurando os arquivos da prova…", c)], tight=True, spacing=12, width=min(560, (app.page.width or 600) - 40))
    estado = {"aberto": True}

    def fechar(e=None):
        estado["aberto"] = False
        app.page.pop_dialog()

    dlg = ft.AlertDialog(
        title=ft.Column(
            [
                ft.Text(it.cargo, font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
                comp.apagado("   ".join(x for x in (it.orgao, it.banca, it.ano) if x), c, 13.5),
            ],
            spacing=2,
            tight=True,
        ),
        content=corpo,
        actions=[ft.TextButton("Fechar", on_click=fechar)],
        on_dismiss=lambda e: estado.update(aberto=False),
    )
    app.page.show_dialog(dlg)
    meta = {"titulo": f"{it.cargo} — {it.orgao} {it.ano}".strip(), "cargo": it.cargo, "orgao": it.orgao, "banca": it.banca, "ano": it.ano, "origem_url": it.url}
    try:
        arquivos, precisa_navegador = await app.em_segundo_plano(app.pci.arquivos_prova, it.url)
    except ErroRede as ex:
        corpo.controls = [comp.aviso(str(ex), c, "erro"), comp.botao_contorno("Abrir no site", url=it.url, icone=ft.Icons.OPEN_IN_NEW)]
        app.page.update()
        return

    if not precisa_navegador and arquivos:
        pasta = config.CACHE_DIR / "downloads" / str(int(time.time()))
        baixados: list[Path] = []
        try:
            for i, a in enumerate(arquivos[:4]):
                corpo.controls = [comp.carregando(f"Baixando {a.nome} ({i + 1} de {min(len(arquivos), 4)})…", c)]
                app.page.update()
                destino = pasta / Path(a.nome).name
                if not destino.suffix:
                    destino = destino.with_suffix(".pdf")
                baixados.append(await app.em_segundo_plano(app.pci.baixar, a.url, destino))
        except ErroRede:
            precisa_navegador = True  # o site recusou o download direto: segue pelo navegador
        else:
            await importar_arquivos(app, corpo, baixados, meta)
            return

    await _fluxo_navegador(app, corpo, it, arquivos, meta, estado)


async def _fluxo_navegador(app, corpo: ft.Column, it: ProvaItem, arquivos: list[Arquivo], meta: dict, estado: dict) -> None:
    c = app.c
    nomes = [a.nome for a in arquivos if a.nome.lower().endswith(".pdf")]
    pasta = Path(app.aj["pasta_downloads"])
    inicio = time.time()
    aguardando = comp.carregando(f"Esperando os arquivos aparecerem em {pasta}…", c)

    async def escolher(e):
        pdfs = await escolher_pdfs(app)
        if pdfs:
            estado["aberto"] = False
            await importar_arquivos(app, corpo, pdfs, meta)

    lista_nomes = ft.Column(
        [ft.Row([ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, size=18, color=c["erro"]), comp.texto(n, c, 14.5)], spacing=8) for n in nomes],
        spacing=6,
    )
    passos = [
        comp.aviso("O site pede uma verificação de segurança antes de liberar os PDFs, então o download é feito no seu navegador.", c, "info"),
        comp.texto("1. Abra a página da prova e confirme a verificação.", c, 15),
        comp.botao("Abrir página da prova", url=it.url, icone=ft.Icons.OPEN_IN_NEW),
        comp.texto("2. Clique em “Baixar” nestes arquivos:", c, 15),
        lista_nomes if nomes else comp.apagado("A prova e o gabarito (PDF).", c, 14),
    ]
    if not app.desktop:
        passos += [
            comp.texto("3. Depois, escolha os arquivos baixados:", c, 15),
            comp.botao_contorno("Escolher PDFs", escolher, ft.Icons.UPLOAD_FILE),
        ]
    else:
        passos += [
            comp.texto("3. Pronto. O Aprova encontra os arquivos na pasta Downloads e importa sozinho.", c, 15),
            aguardando,
            comp.botao_texto("Escolher os PDFs manualmente", escolher, ft.Icons.FOLDER_OPEN),
        ]
    corpo.controls = passos
    app.page.update()
    if not app.desktop or not nomes:
        return
    # espera até 15 minutos pelos arquivos
    achou_prova_em = None
    while estado.get("aberto") and time.time() - inicio < 900:
        await asyncio.sleep(2)
        achados = await app.em_segundo_plano(importador.procurar_baixados, nomes, pasta, inicio)
        if not achados:
            continue
        tem_todos = len(achados) >= len(nomes)
        if achou_prova_em is None:
            achou_prova_em = time.time()
        if tem_todos or time.time() - achou_prova_em > 40:
            prontos = [p for p in achados if await app.em_segundo_plano(importador.aguardar_estavel, p)]
            if len(prontos) == len(achados):
                estado["aberto"] = False
                await importar_arquivos(app, corpo, prontos, meta)
                return
            aguardando.controls[1].value = f"Encontrei {len(achados)} arquivo(s), esperando o download terminar…"
            app.page.update()
