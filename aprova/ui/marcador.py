"""Tela de marcar PDF: marca-texto, sublinhado e notas, salvando um PDF com as marcações."""

from __future__ import annotations

import time
from pathlib import Path

import flet as ft

from .. import config, marcador
from . import comp
from .tema import FONTE_TITULO

CORES_TELA = {"amarelo": "#FFE340", "verde": "#8CE68C", "azul": "#8CC7FF", "rosa": "#FF9ED1"}
NOMES_CORES = {"amarelo": "Amarelo", "verde": "Verde", "azul": "Azul", "rosa": "Rosa"}
FERRAMENTAS = [
    ("destaque", "Marca-texto", ft.Icons.BORDER_COLOR_OUTLINED),
    ("sublinhado", "Sublinhar", ft.Icons.FORMAT_UNDERLINED),
    ("nota", "Nota", ft.Icons.STICKY_NOTE_2_OUTLINED),
    ("mao", "Ver", ft.Icons.PAN_TOOL_OUTLINED),
]
DICAS = {
    "destaque": "Arraste sobre o texto para marcar.",
    "sublinhado": "Arraste sobre o texto para sublinhar.",
    "nota": "Toque onde quer deixar uma nota.",
    "mao": "Toque numa marcação para escrever uma nota, trocar a cor ou apagar.",
}
TIPOS = {"destaque": "Destaque", "sublinhado": "Sublinhado", "nota": "Nota"}


async def escolher_pdf(app) -> Path | None:
    from .estudar import escolher_pdfs

    pdfs = await escolher_pdfs(app, titulo="Escolha o PDF para marcar", varios=False)
    return pdfs[0] if pdfs else None


def abrir_marcador(app, caminho: Path, titulo: str | None = None) -> None:
    caminho = Path(caminho)
    if not caminho.exists():
        comp.mensagem(app.page, "Não achei esse PDF. Ele pode ter sido movido ou apagado.")
        return
    try:
        doc = marcador.DocumentoMarcado(caminho, titulo=titulo, autor=app.nome_exibicao or marcador.AUTOR, base=app.pasta_conta)
    except ValueError as e:
        comp.mensagem(app.page, str(e))
        return
    except Exception as e:  # noqa: BLE001
        config.registrar(f"marcador: não abriu {caminho.name}: {e!r}")
        comp.mensagem(app.page, "Não consegui abrir esse PDF. Ele pode estar corrompido.")
        return
    app.abrir_foco(TelaMarcador(app, doc))


class TelaMarcador:
    def __init__(self, app, doc: marcador.DocumentoMarcado):
        self.app = app
        self.doc = doc
        self.pagina = 0
        self.zoom = 1.0  # 1 = página na largura da tela
        self.ferramenta = app.aj.get("marcador_ferramenta") or "destaque"
        self.cor = app.aj.get("marcador_cor") or "amarelo"
        self.painel = True
        self.raiz = ft.Container(expand=True)
        self.imagem = ft.Image(src=b"", fit=ft.BoxFit.FILL, gapless_playback=True)
        self.camada = ft.Stack([], width=1, height=1)
        self.palco = ft.Stack([], width=1, height=1)
        self._escala = 1.0
        self._inicio: tuple[float, float] | None = None
        self._baixo: tuple[float, float] | None = None
        self._ponto: tuple[float, float] | None = None
        self._digitando = False
        self._mudou = False  # marcou algo desde o último "Salvar PDF"
        self._ultimo_render = 0.0

    @property
    def c(self) -> dict:
        return self.app.c

    # ------------------------------------------------------------ montar

    def build(self) -> ft.Control:
        self._render()
        return self.raiz

    def ao_mostrar(self):
        if not self.doc.tem_texto():
            comp.mensagem(self.app.page, "Este PDF é escaneado (imagem): arraste para marcar uma área. Notas funcionam normalmente.")

    def _render(self):
        app, c = self.app, self.c
        largura_tela = app.largura
        lateral = 330 if app.largo and self.painel else 0
        disponivel = max(280, min(920, largura_tela - lateral - (64 if app.largo else 24)))
        w_pt, h_pt = self.doc.tamanho(self.pagina)
        self._escala = max(0.35, min(4.0, disponivel / w_pt * self.zoom))
        w, h = w_pt * self._escala, h_pt * self._escala
        self.imagem.width, self.imagem.height = w, h
        self.imagem.src = self.doc.imagem(self.pagina, min(4.0, self._escala * 1.6))
        self.camada.width = self.palco.width = w
        self.camada.height = self.palco.height = h
        self.camada.controls = []
        self.palco.controls = [self.imagem, self.camada]
        folha = ft.Container(
            ft.GestureDetector(
                content=self.palco,
                on_pan_down=self._pan_baixo,
                on_pan_start=self._pan_inicio,
                on_pan_update=self._pan_meio,
                on_pan_end=self._pan_fim,
                on_tap_up=self._toque,
                drag_interval=30,
                mouse_cursor=ft.MouseCursor.TEXT if self.ferramenta in ("destaque", "sublinhado") else ft.MouseCursor.CLICK,
            ),
            shadow=ft.BoxShadow(blur_radius=18, spread_radius=0, color=ft.Colors.with_opacity(0.16, "#14213D"), offset=ft.Offset(0, 4)),
            bgcolor="#FFFFFF",
        )
        area = ft.Column(
            [
                ft.Row([folha], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.CENTER),
                self._navegacao_baixo(),
                ft.Container(height=24),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
        )
        miolo = ft.Container(area, expand=True, padding=ft.Padding.only(left=32 if app.largo else 12, right=32 if app.largo else 12, top=18), bgcolor=c["sup2"])
        if lateral:
            corpo = ft.Row(
                [
                    miolo,
                    ft.Container(self._lista(), width=lateral, bgcolor=c["sup"], border=ft.Border.only(left=ft.BorderSide(1, c["borda"])), padding=ft.Padding.only(left=18, right=12, top=16)),
                ],
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        else:
            corpo = miolo
        self.raiz.content = ft.Column([self._cabecalho(), self._ferramentas(), corpo], spacing=0, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.raiz.bgcolor = c["bg"]

    def _atualizar(self):
        self._render()
        self.app.page.update()

    def _cabecalho(self) -> ft.Control:
        app, c = self.app, self.c
        n = len(self.doc.marcacoes())
        titulo = ft.Column(
            [
                ft.Text(self.doc.titulo, size=18 if app.largo else 15.5, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                comp.apagado(f"Página {self.pagina + 1} de {self.doc.paginas} · {n} marcaç{'ão' if n == 1 else 'ões'} · salvo no Aprova", c, 12.5, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=2,
            expand=True,
        )
        acoes: list[ft.Control] = [
            ft.IconButton(ft.Icons.UNDO, tooltip="Desfazer a última marcação (Ctrl+Z)", on_click=self._desfazer, icon_color=c["texto2"]),
        ]
        if app.largo:
            acoes += [
                ft.IconButton(ft.Icons.ZOOM_OUT, tooltip="Diminuir", on_click=lambda e: self._mudar_zoom(-0.25), icon_color=c["texto2"]),
                ft.IconButton(ft.Icons.ZOOM_IN, tooltip="Aumentar", on_click=lambda e: self._mudar_zoom(0.25), icon_color=c["texto2"]),
                ft.IconButton(
                    ft.Icons.VIEW_SIDEBAR_OUTLINED if not self.painel else ft.Icons.VIEW_SIDEBAR,
                    tooltip="Mostrar ou esconder a lista de marcações",
                    on_click=self._alternar_painel,
                    icon_color=c["tinta"] if self.painel else c["texto2"],
                ),
                ft.Container(width=6),
                comp.botao("Salvar PDF", lambda e: self.dialogo_salvar(), ft.Icons.SAVE_ALT),
            ]
        else:
            acoes += [
                ft.IconButton(ft.Icons.LIST_ALT, tooltip="Marcações", on_click=lambda e: self._lista_celular(), icon_color=c["texto2"]),
                ft.IconButton(ft.Icons.SAVE_ALT, tooltip="Salvar PDF", on_click=lambda e: self.dialogo_salvar(), icon_color=c["tinta"]),
            ]
        return ft.Container(
            ft.Row(
                [ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Voltar", on_click=self._sair), titulo, *acoes],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=8 if app.largo else 2, right=12, top=10, bottom=10),
            bgcolor=c["sup"],
            border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
        )

    def _ferramentas(self) -> ft.Control:
        app, c = self.app, self.c
        botoes = []
        for chave, rotulo, icone in FERRAMENTAS:
            sel = chave == self.ferramenta
            botoes.append(
                ft.Container(
                    ft.Row(
                        [ft.Icon(icone, size=18, color=c["sobre_tinta"] if sel else c["texto2"]), *( [ft.Text(rotulo, size=13.5, color=c["sobre_tinta"] if sel else c["texto"], weight=ft.FontWeight.W_600 if sel else None)] if app.largo or app.largura >= 560 else [])],
                        spacing=6,
                        tight=True,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=20,
                    bgcolor=c["tinta"] if sel else c["sup2"],
                    tooltip=rotulo,
                    on_click=lambda e, k=chave: self._escolher_ferramenta(k),
                    ink=True,
                )
            )
        cores = []
        if self.ferramenta in ("destaque", "sublinhado"):
            for nome, hexa in CORES_TELA.items():
                sel = nome == self.cor
                cores.append(
                    ft.Container(
                        width=26,
                        height=26,
                        border_radius=13,
                        bgcolor=hexa,
                        border=ft.Border.all(3 if sel else 1, c["texto"] if sel else c["borda"]),
                        tooltip=NOMES_CORES[nome],
                        on_click=lambda e, k=nome: self._escolher_cor(k),
                    )
                )
        dica = DICAS[self.ferramenta]
        if self.ferramenta in ("destaque", "sublinhado") and not self.doc.palavras(self.pagina):
            dica = "Esta página é uma imagem: arraste para marcar uma área."
        linha = [ft.Row(botoes, spacing=6, tight=True)]
        if cores:
            linha.append(ft.Container(ft.Row(cores, spacing=8, tight=True), padding=ft.Padding.only(left=10)))
        if app.largo:
            linha += [ft.Container(expand=True), comp.apagado(dica, c, 13)]
            conteudo = ft.Row(linha, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            zoom = [
                ft.IconButton(ft.Icons.ZOOM_OUT, tooltip="Diminuir", on_click=lambda e: self._mudar_zoom(-0.25), icon_color=c["texto2"], icon_size=20),
                ft.IconButton(ft.Icons.ZOOM_IN, tooltip="Aumentar", on_click=lambda e: self._mudar_zoom(0.25), icon_color=c["texto2"], icon_size=20),
            ]
            conteudo = ft.Column(
                [
                    ft.Row(linha, spacing=6, wrap=True, run_spacing=8),
                    ft.Row([ft.Container(comp.apagado(dica, c, 12.5), expand=True), *zoom], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
                spacing=0,
            )
        return ft.Container(conteudo, padding=ft.Padding.symmetric(horizontal=16 if app.largo else 10, vertical=8), bgcolor=c["sup"], border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])))

    def _navegacao_baixo(self) -> ft.Control:
        c = self.c
        return ft.Row(
            [
                ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Página anterior", on_click=lambda e: self.ir_pagina(self.pagina - 1), disabled=self.pagina == 0),
                comp.texto(f"{self.pagina + 1} / {self.doc.paginas}", c, 14.5),
                ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Próxima página", on_click=lambda e: self.ir_pagina(self.pagina + 1), disabled=self.pagina >= self.doc.paginas - 1),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        )

    # ------------------------------------------------------------ lista de marcações

    def _itens_lista(self, ao_abrir=None) -> list[ft.Control]:
        c = self.c
        itens: list[ft.Control] = []
        for m in self.doc.marcacoes():
            cor = CORES_TELA.get(m["cor"], CORES_TELA["amarelo"])
            texto = []
            if m["trecho"]:
                texto.append(ft.Text(f"“{m['trecho']}”", size=13.5, italic=True, color=c["texto"], max_lines=3, overflow=ft.TextOverflow.ELLIPSIS))
            if m["nota"]:
                texto.append(ft.Row([ft.Icon(ft.Icons.STICKY_NOTE_2_OUTLINED, size=15, color=c["tinta"]), ft.Text(m["nota"], size=13.5, color=c["texto"], expand=True, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS)], spacing=6, vertical_alignment=ft.CrossAxisAlignment.START))
            if not texto:
                texto.append(comp.apagado("(área marcada)" if m["tipo"] != "nota" else "(nota vazia)", c, 13))
            atual = m["pagina"] == self.pagina
            itens.append(
                ft.Container(
                    ft.Container(
                        ft.Column([comp.apagado(f"Pág. {m['pagina'] + 1} · {TIPOS.get(m['tipo'], 'Marcação')}", c, 12), *texto], spacing=3),
                        border=ft.Border.only(left=ft.BorderSide(4, cor)),
                        padding=ft.Padding.only(left=10),
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=9),
                    border_radius=10,
                    bgcolor=c["tinta_suave"] if atual else None,
                    on_click=lambda e, mm=m: (ao_abrir() if ao_abrir else None, self._abrir_da_lista(mm)),
                    ink=True,
                )
            )
        return itens

    def _lista(self) -> ft.Control:
        c = self.c
        itens = self._itens_lista()
        n = len(itens)
        cab = ft.Row([comp.subtitulo("Marcações", c, 19), comp.pilula(str(n), c["sup2"], c["texto2"])], spacing=8)
        if not itens:
            corpo = ft.Container(comp.apagado("As marcações e notas aparecem aqui. Toque numa delas para ir até a página.", c, 13.5), padding=ft.Padding.only(top=6))
            return ft.Column([cab, corpo], spacing=10)
        return ft.Column([cab, ft.Column(itens, spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)], spacing=10, expand=True)

    def _lista_celular(self):
        app, c = self.app, self.c
        itens = self._itens_lista(ao_abrir=lambda: app.page.pop_dialog())
        conteudo = ft.Column(itens or [comp.apagado("Nenhuma marcação ainda.", c, 14)], spacing=4, scroll=ft.ScrollMode.AUTO, tight=True)
        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Marcações", font_family=FONTE_TITULO, size=21),
                content=ft.Container(conteudo, width=min(460, (app.page.width or 400) - 40), height=min(520, (app.page.height or 600) - 200)),
                actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
            )
        )

    def _abrir_da_lista(self, m: dict):
        if m["pagina"] != self.pagina:
            self.pagina = m["pagina"]
            self._atualizar()
        self.dialogo_marcacao(m)

    # ------------------------------------------------------------ gestos

    def _pt(self, pos) -> tuple[float, float]:
        return (pos.x / self._escala, pos.y / self._escala)

    def _pan_baixo(self, e: ft.DragDownEvent):
        self._baixo = self._pt(e.local_position)  # onde o dedo/mouse encostou (o arraste só começa depois de mexer um pouco)

    def _pan_inicio(self, e: ft.DragStartEvent):
        if self.ferramenta not in ("destaque", "sublinhado"):
            return
        self._inicio = self._baixo or self._pt(e.local_position)
        self._baixo = None
        self._ponto = self._inicio

    def _pan_meio(self, e: ft.DragUpdateEvent):
        if self._inicio is None:
            return
        self._ponto = self._pt(e.local_position)
        rects = self.doc.selecao(self.pagina, self._inicio, self._ponto)
        cor = CORES_TELA.get(self.cor, CORES_TELA["amarelo"])
        s = self._escala
        controles = []
        for r in rects:
            if self.ferramenta == "sublinhado" and self.doc.palavras(self.pagina):
                controles.append(ft.Container(left=r.x0 * s, top=r.y1 * s - 2, width=max(2, r.width * s), height=3, bgcolor=cor))
            else:
                controles.append(ft.Container(left=r.x0 * s, top=r.y0 * s, width=max(2, r.width * s), height=max(2, r.height * s), bgcolor=ft.Colors.with_opacity(0.45, cor), border_radius=2))
        self.camada.controls = controles
        try:
            self.camada.update()
        except Exception:  # noqa: BLE001
            pass

    def _pan_fim(self, e: ft.DragEndEvent):
        if self._inicio is None:
            return
        a, b = self._inicio, self._ponto or self._inicio
        self._inicio = self._ponto = None
        self.camada.controls = []
        m = self.doc.marcar(self.pagina, a, b, self.ferramenta, self.cor)
        if m:
            self._mudou = True
            self._atualizar()
        else:
            try:
                self.camada.update()
            except Exception:  # noqa: BLE001
                pass

    def _toque(self, e: ft.TapEvent):
        x, y = self._pt(e.local_position)
        existente = self.doc.na_posicao(self.pagina, x, y)
        if self.ferramenta == "nota" and existente is None:
            self.dialogo_nota_nova((x, y))
        elif existente is not None:
            self.dialogo_marcacao(existente)
        elif self.ferramenta in ("destaque", "sublinhado"):
            comp.mensagem(self.app.page, "Arraste (clique e segure) sobre o texto para marcar.")

    # ------------------------------------------------------------ ações

    def _escolher_ferramenta(self, k: str):
        self.ferramenta = k
        self.app.aj.set("marcador_ferramenta", k)
        self._atualizar()

    def _escolher_cor(self, k: str):
        self.cor = k
        self.app.aj.set("marcador_cor", k)
        self._atualizar()

    def _mudar_zoom(self, delta: float):
        self.zoom = round(min(3.0, max(0.5, self.zoom + delta)), 2)
        self._atualizar()

    def _alternar_painel(self, e=None):
        self.painel = not self.painel
        self._atualizar()

    def ir_pagina(self, n: int):
        if 0 <= n < self.doc.paginas and n != self.pagina:
            self.pagina = n
            self._atualizar()

    def _desfazer(self, e=None):
        if self.doc.desfazer():
            self._mudou = True
            self._atualizar()
        else:
            comp.mensagem(self.app.page, "Nada para desfazer nesta abertura do PDF.")

    def tecla(self, e: ft.KeyboardEvent):
        if self._digitando:
            return
        k = (e.key or "").upper()
        if (e.ctrl or e.meta) and k == "Z":
            self._desfazer()
        elif e.ctrl or e.alt or e.meta:
            return
        elif k in ("ARROW RIGHT", "PAGE DOWN"):
            self.ir_pagina(self.pagina + 1)
        elif k in ("ARROW LEFT", "PAGE UP"):
            self.ir_pagina(self.pagina - 1)
        elif k in ("1", "2", "3", "4"):
            self._escolher_ferramenta(FERRAMENTAS[int(k) - 1][0])

    def _sair(self, e=None):
        app = self.app

        def fechar(ev=None):
            if ev is not None:
                app.page.pop_dialog()
            self.doc.fechar()
            app.fechar_foco("estudar", aba="pdfs")

        if not self._mudou:
            fechar()
            return

        def salvar_antes(ev):
            app.page.pop_dialog()
            self.dialogo_salvar(depois=fechar)

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Salvar o PDF marcado?"),
                content=ft.Text("Suas marcações já estão guardadas no Aprova (em Estudar → Marcar PDF). Salve agora se quiser o arquivo para enviar ou imprimir.", size=15),
                actions=[ft.TextButton("Depois", on_click=fechar), ft.FilledButton("Salvar PDF", on_click=salvar_antes)],
            )
        )

    # ------------------------------------------------------------ diálogos

    def _dialogo(self, titulo: str, conteudo: ft.Control, acoes: list[ft.Control]):
        self._digitando = True
        app = self.app

        def ao_fechar(e=None):
            self._digitando = False

        dlg = ft.AlertDialog(
            title=ft.Text(titulo, font_family=FONTE_TITULO, size=21),
            content=ft.Container(conteudo, width=min(480, (app.page.width or 500) - 48)),
            actions=acoes,
            on_dismiss=ao_fechar,
        )
        app.page.show_dialog(dlg)
        return dlg

    def _fechar_dialogo(self):
        self._digitando = False
        self.app.page.pop_dialog()

    def dialogo_nota_nova(self, ponto: tuple[float, float]):
        campo = ft.TextField(label="Sua nota", multiline=True, min_lines=3, max_lines=8, autofocus=True, border_radius=10)

        def salvar(e=None):
            texto = (campo.value or "").strip()
            self._fechar_dialogo()
            if texto:
                self.doc.nota(self.pagina, ponto, texto)
                self._mudou = True
                self._atualizar()

        self._dialogo(
            "Nova nota",
            ft.Column([campo, comp.apagado("Aparece como um balãozinho na página. Em qualquer leitor de PDF, clicar nele mostra o texto.", self.c, 13)], tight=True, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            [ft.TextButton("Cancelar", on_click=lambda e: self._fechar_dialogo()), ft.FilledButton("Salvar nota", on_click=salvar)],
        )

    def dialogo_marcacao(self, m: dict):
        c = self.c
        campo = ft.TextField(label="Nota" if m["tipo"] == "nota" else "Nota sobre este trecho (opcional)", value=m["nota"], multiline=True, min_lines=2, max_lines=8, border_radius=10, autofocus=m["tipo"] == "nota")
        escolhida = {"cor": m["cor"]}
        bolinhas = ft.Row(spacing=8)

        def desenhar_cores():
            bolinhas.controls = [
                ft.Container(
                    width=28, height=28, border_radius=14, bgcolor=hexa, tooltip=NOMES_CORES[nome],
                    border=ft.Border.all(3 if nome == escolhida["cor"] else 1, c["texto"] if nome == escolhida["cor"] else c["borda"]),
                    on_click=lambda e, k=nome: (escolhida.update(cor=k), desenhar_cores(), bolinhas.update()),
                )
                for nome, hexa in CORES_TELA.items()
            ]

        desenhar_cores()
        filhos: list[ft.Control] = [comp.apagado(f"Página {m['pagina'] + 1} · {TIPOS.get(m['tipo'], 'Marcação')}", c, 13)]
        if m["trecho"]:
            filhos.append(ft.Container(ft.Text(f"“{m['trecho']}”", italic=True, size=14.5, color=c["texto"], selectable=True), bgcolor=c["sup2"], border_radius=10, padding=12))
        filhos.append(campo)
        if m["tipo"] != "nota":
            filhos += [comp.apagado("Cor", c, 13), bolinhas]

        def salvar(e=None):
            texto = (campo.value or "").strip()
            self._fechar_dialogo()
            if texto != (m["nota"] or ""):
                self.doc.editar_nota(m["pagina"], m["xref"], texto)
                self._mudou = True
            if m["tipo"] != "nota" and escolhida["cor"] != m["cor"]:
                self.doc.mudar_cor(m["pagina"], m["xref"], escolhida["cor"])
                self._mudou = True
            self._atualizar()

        def apagar(e=None):
            self._fechar_dialogo()
            self.doc.apagar(m["pagina"], m["xref"])
            self._mudou = True
            self._atualizar()

        self._dialogo(
            "Marcação" if m["tipo"] != "nota" else "Nota",
            ft.Column(filhos, tight=True, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            [
                ft.TextButton("Apagar", icon=ft.Icons.DELETE_OUTLINE, on_click=apagar, style=ft.ButtonStyle(color=c["erro"])),
                ft.TextButton("Cancelar", on_click=lambda e: self._fechar_dialogo()),
                ft.FilledButton("Salvar", on_click=salvar),
            ],
        )

    def dialogo_salvar(self, depois=None):
        dialogo_salvar(self.app, self.doc, depois=depois, ao_salvar=lambda: setattr(self, "_mudou", False), digitando=lambda v: setattr(self, "_digitando", v))


def _caminho_livre(pasta: Path, nome: str) -> Path:
    destino = pasta / nome
    i = 2
    while destino.exists():
        destino = pasta / f"{Path(nome).stem} ({i}).pdf"
        i += 1
    return destino


def dialogo_salvar(app, doc: marcador.DocumentoMarcado, depois=None, ao_salvar=None, digitando=None) -> None:
    """Pergunta o nome e se as marcações ficam fixas, e salva na pasta de downloads."""
    c = app.c
    pasta = Path(app.aj["pasta_downloads"] or Path.home() / "Downloads")
    if not pasta.exists():
        pasta = Path.home()
    nome = ft.TextField(label="Nome do arquivo", value=marcador.nome_para_salvar(doc.titulo), border_radius=10, dense=True)
    fixas = ft.Checkbox(label="Deixar as marcações fixas (ninguém consegue apagar ou mudar)", value=bool(app.aj.get("marcador_fixas")))
    explicacao = comp.apagado("", c, 13)

    def explicar(e=None):
        if fixas.value:
            explicacao.value = "As marcações viram parte da página, como se tivessem sido impressas. O texto das notas vai para uma página “Minhas anotações” no fim do arquivo."
        else:
            explicacao.value = "As marcações continuam editáveis: dá para mudar ou apagar depois, no Aprova ou em qualquer leitor de PDF."
        try:
            explicacao.update()
        except Exception:  # noqa: BLE001
            pass

    fixas.on_change = explicar
    explicar()
    if digitando:
        digitando(True)

    def fechar(e=None):
        if digitando:
            digitando(False)
        app.page.pop_dialog()

    def salvar(e=None):
        texto = (nome.value or "").strip() or marcador.nome_para_salvar(doc.titulo)
        if not texto.lower().endswith(".pdf"):
            texto += ".pdf"
        texto = "".join(ch if ch not in '<>:"/\\|?*' else " " for ch in texto)
        app.aj.set("marcador_fixas", bool(fixas.value))
        try:
            destino = doc.exportar(_caminho_livre(pasta, texto), fixas=bool(fixas.value))
        except Exception as ex:  # noqa: BLE001
            fechar()
            comp.mensagem(app.page, f"Não consegui salvar o PDF ({ex}).")
            return
        fechar()
        if ao_salvar:
            ao_salvar()
        _salvo(app, destino, depois)

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Salvar PDF marcado", font_family=FONTE_TITULO, size=21),
            content=ft.Container(
                ft.Column(
                    [nome, comp.apagado(f"Vai para: {pasta}", c, 12.5), fixas, explicacao],
                    tight=True,
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                width=min(500, (app.page.width or 520) - 48),
            ),
            actions=[ft.TextButton("Cancelar", on_click=fechar), ft.FilledButton("Salvar", icon=ft.Icons.SAVE_ALT, on_click=salvar)],
            on_dismiss=lambda e: digitando(False) if digitando else None,
        )
    )


def _salvo(app, destino: Path, depois=None) -> None:
    from .grupos import _abrir_pasta

    def fechar(e=None):
        app.page.pop_dialog()
        if depois:
            depois()

    def abrir(e=None):
        fechar()
        _abrir_arquivo(app, destino)

    def pasta(e=None):
        fechar()
        _abrir_pasta(app, destino.parent)

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("PDF salvo", font_family=FONTE_TITULO, size=21),
            content=ft.Text(f"{destino.name}\nem {destino.parent}", size=14.5),
            actions=[ft.TextButton("Abrir a pasta", on_click=pasta), ft.TextButton("Abrir o PDF", on_click=abrir), ft.FilledButton("Pronto", on_click=fechar)],
        )
    )


def _abrir_arquivo(app, caminho: Path) -> None:
    import os
    import sys

    if app.celular:
        app.page.run_task(app.compartilhar_arquivo, caminho)
        return

    try:
        if sys.platform == "win32":
            os.startfile(str(caminho))  # noqa: S606
            return
    except OSError:
        pass
    app.page.run_task(app.abrir_url, caminho.as_uri())


def quando(ts: float) -> str:
    dif = time.time() - (ts or 0)
    if dif < 90:
        return "agora"
    if dif < 3600:
        return f"há {int(dif // 60)} min"
    if dif < 86400:
        return f"há {int(dif // 3600)} h"
    dias = int(dif // 86400)
    return "ontem" if dias == 1 else f"há {dias} dias"
