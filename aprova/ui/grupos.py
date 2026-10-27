"""Grupos de estudo: fórum da turma (conversa, dúvidas, materiais), planos de estudo, ranking e membros.

Só quem está no grupo lê e escreve (o servidor confere). Quem criou o grupo modera:
fixa mensagens importantes e apaga o que não deve ficar. O administrador modera todos.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import flet as ft

from .. import analise
from .. import ranking as rk
from . import comp, metas
from .personagem import busto, sala_da_turma
from .tema import FONTE_TITULO

ABAS = [("conversa", "Conversa"), ("planos", "Planos de estudo"), ("ranking", "Ranking"), ("membros", "Membros")]
LARGURA_DUAS_COLUNAS = 1180  # janela a partir disso: lista de grupos e membros ao lado
CORES_AVATAR = ["#2340A8", "#1D7F53", "#A0612D", "#7A3E9D", "#B83A33", "#0F7C8C", "#5B6B1F"]
ICONES_TIPO = {
    "conversa": ft.Icons.FORUM_OUTLINED,
    "duvida": ft.Icons.HELP_OUTLINE,
    "material": ft.Icons.LINK,
    "plano": ft.Icons.EVENT_NOTE_OUTLINED,
}
DISCIPLINAS_COMUNS = [
    "Língua Portuguesa", "Raciocínio Lógico", "Matemática", "Informática", "Conhecimentos Específicos",
    "Direito Constitucional", "Direito Administrativo", "Legislação", "Atualidades", "Língua Inglesa",
    "Segurança da Informação", "Administração", "Contabilidade", "Conhecimentos Bancários",
]
URL = re.compile(r"https?://[^\s<>\"]+")


# ---------------------------------------------------------------------- utilidades


def quando_texto(iso: str | None) -> str:
    """'agora', 'há 5 min', 'há 2 h', 'ontem', 'há 3 dias' ou a data."""
    d = rk._quando(iso)
    seg = (datetime.now(timezone.utc) - d).total_seconds()
    if seg < 60:
        return "agora"
    if seg < 3600:
        return f"há {int(seg // 60)} min"
    if seg < 86400:
        return f"há {int(seg // 3600)} h"
    dias = int(seg // 86400)
    if dias == 1:
        return "ontem"
    if dias < 7:
        return f"há {dias} dias"
    local = d.astimezone()
    return f"{local.day:02d}/{local.month:02d}" + (f"/{local.year}" if local.year != date.today().year else "")


def avatar(nome: str, tamanho: int = 36) -> ft.Container:
    cor = CORES_AVATAR[sum(map(ord, nome or "?")) % len(CORES_AVATAR)]
    return ft.Container(
        ft.Text((nome[:1] or "?").upper(), size=tamanho * 0.42, weight=ft.FontWeight.W_700, color="#FFFFFF"),
        width=tamanho,
        height=tamanho,
        border_radius=tamanho / 2,
        bgcolor=cor,
        alignment=ft.Alignment.CENTER,
    )


def dias_texto(dias: list[int]) -> str:
    nomes = [rk.DIAS_CURTOS[d] for d in sorted(dias) if 0 <= d <= 6]
    if not nomes:
        return ""
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def horas_texto(h: float) -> str:
    h = float(h or 0)
    return f"{h:.0f} h" if abs(h - round(h)) < 0.05 else f"{h:.1f} h".replace(".", ",")


def _norm(texto: str) -> str:
    return rk.analise_norm(texto or "").lower().strip()


# ---------------------------------------------------------------------- tela


class TelaGrupos:
    def __init__(self, app):
        self.app = app
        self.aba = "conversa"
        self.codigo: str | None = app.aj.get("grupo_atual", "") or None
        self.grupos: list[dict] | None = None
        self.visitando: dict | None = None  # admin olhando um grupo de que não é membro
        self.posts: dict[tuple[str, str], list[dict]] = {}
        self.membros: dict[str, list[dict]] = {}
        self.linhas_ranking: dict[str, list[dict]] = {}
        self.respostas: dict[int, list[dict]] = {}
        self.abertos: set[int] = set()
        self.erro: str | None = None
        self.carregando = False
        self.tipo_novo = "conversa"
        self._rascunho = ""
        from .anexos import VisorAnexos

        self.visor = VisorAnexos(app)
        self._pendentes: list[dict] = []  # fotos/arquivos já enviados, esperando o "Publicar"
        self._enviando: list[str] = []  # nomes dos arquivos subindo agora
        self._rapidos: list[dict] = []  # figurinhas e GIFs indo agora: {"tipo", "valor", "post": id da mensagem (resposta) ou None}
        # figurinha ou GIF escolhido, esperando o envio (como no Teams): na mensagem nova (None) ou na resposta de um post
        self._figurinha_escolhida: dict[int | None, dict] = {}
        self._rascunho_resposta: dict[int, str] = {}
        self._assunto = ""

    @property
    def r(self) -> rk.Ranking:
        return self.app.ranking

    def preparar(self, codigo: str | None = None, aba: str | None = None, **_):
        if codigo:
            self.codigo = codigo
            self.posts = {k: v for k, v in self.posts.items() if k[0] != codigo}
            if self.grupos is not None and codigo not in {g["codigo"] for g in self.grupos}:
                self.grupos = None  # recarrega (pode ser um grupo novo ou o admin visitando)
        if aba in dict(ABAS):
            self.aba = aba

    @property
    def duas_colunas(self) -> bool:
        return self.app.largura >= LARGURA_DUAS_COLUNAS

    @property
    def grupo(self) -> dict | None:
        for g in (self.grupos or []) + ([self.visitando] if self.visitando else []):
            if g["codigo"] == self.codigo:
                return g
        return None

    def _redesenhar(self):
        self.app.recarregar_tela_sem_perder(self)

    # ------------------------------------------------------------------ montagem

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        topo_titulo = comp.titulo("Grupos", c, 34 if app.largo else 28)
        if not self.r.configurado:
            corpo = self._nao_configurado()
        elif not self.r.logado:
            corpo = comp.vazio(
                ft.Icons.FORUM_OUTLINED,
                "Estude junto com a sua turma",
                "Nos grupos você conversa com quem estuda para o mesmo concurso, tira dúvidas, troca materiais e compartilha planos de estudo. "
                "Para participar, entre na sua conta.",
                c,
                comp.botao("Entrar ou criar conta", lambda e: app.mostrar_login(), ft.Icons.LOGIN),
            )
        elif self.grupos is None:
            if not self.carregando:
                app.page.run_task(self.carregar_grupos)
            corpo = comp.aviso(self.erro, c, "erro", comp.botao_texto("Tentar de novo", lambda e: app.page.run_task(self.carregar_grupos))) if self.erro else comp.carregando("Abrindo seus grupos…", c)
        elif not self.grupos and not self.visitando:
            corpo = self._sem_grupos()
        else:
            corpo = self._com_grupos()
        acoes = []
        if self.r.logado and self.grupos:
            acoes = [
                comp.botao_contorno("Entrar com código", lambda e: self._dialogo_entrar_criar("entrar"), ft.Icons.LOGIN),
                comp.botao_contorno("Criar grupo", lambda e: self._dialogo_entrar_criar("criar"), ft.Icons.ADD),
            ]
        if app.largo and acoes:
            topo = ft.Row([topo_titulo, ft.Container(expand=True), *acoes], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            topo = topo_titulo
        return ft.Column([topo, ft.ListView([corpo, ft.Container(height=30)], expand=True, spacing=0)], spacing=16, expand=True)

    def _nao_configurado(self) -> ft.Control:
        from .ranking import dialogo_servidor

        app, c = self.app, self.app.c
        acao = None
        if not app.modo_web:
            acao = comp.botao(
                "Configurar servidor",
                lambda e: dialogo_servidor(app, lambda: (self.r.recarregar_config(), app.recarregar_tela())),
                ft.Icons.SETTINGS_OUTLINED,
            )
        return comp.vazio(
            ft.Icons.FORUM_OUTLINED,
            "Grupos de estudo",
            "Os grupos usam o mesmo servidor das contas e do ranking (grátis, no Supabase). "
            "Quem cuida do app configura uma vez: o passo a passo está no README.",
            c,
            acao,
        )

    # ------------------------------------------------------------------ sem grupos

    def _sem_grupos(self) -> ft.Control:
        app, c = self.app, self.app.c
        codigo = ft.TextField(label="Código do grupo", hint_text="Ex.: DATAPREV-7A2F", border_radius=10, capitalization=ft.TextCapitalization.CHARACTERS)
        nome = ft.TextField(label="Nome do grupo", hint_text="Ex.: Turma Dataprev", border_radius=10, max_length=40)
        msg = ft.Container()

        async def entrar(e):
            await self._entrar_ou_criar("entrar", codigo.value or "", msg)

        async def criar(e):
            await self._entrar_ou_criar("criar", nome.value or "", msg)

        def cartao(icone, titulo, texto, campo, botao):
            return comp.bloco(
                ft.Column(
                    [ft.Icon(icone, color=c["tinta"], size=30), comp.subtitulo(titulo, c, 19), comp.apagado(texto, c, 14), campo, botao],
                    spacing=12,
                ),
                c,
                padding=22,
                col={"um": 12, "dois": 6},
            )

        return ft.Column(
            [
                ft.Column(
                    [
                        ft.Text("Estude junto com a sua turma", size=22, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                        comp.apagado(
                            "Num grupo vocês conversam, tiram dúvidas, trocam materiais e compartilham planos de estudo. "
                            "Só quem tem o código entra, e só quem está no grupo vê as mensagens.",
                            c,
                            14.5,
                        ),
                    ],
                    spacing=6,
                ),
                ft.ResponsiveRow(
                    [
                        cartao(ft.Icons.LOGIN, "Entrar num grupo", "Recebeu um código de alguém da turma? Digite aqui.", codigo, comp.botao("Entrar", entrar, ft.Icons.LOGIN)),
                        cartao(
                            ft.Icons.GROUP_ADD_OUTLINED,
                            "Criar um grupo",
                            "Você vira moderador: pode fixar recados e apagar mensagens. Depois é só mandar o código para a turma.",
                            nome,
                            comp.botao_contorno("Criar grupo", criar, ft.Icons.ADD),
                        ),
                    ],
                    spacing=16,
                    run_spacing=16,
                    breakpoints=comp.quebras(self.app, {"um": 0, "dois": 820}),
                ),
                msg,
            ],
            spacing=18,
        )

    async def _entrar_ou_criar(self, modo: str, valor: str, msg: ft.Container) -> bool:
        app, c = self.app, self.app.c
        try:
            if modo == "entrar":
                g = await app.em_segundo_plano(self.r.entrar_grupo, valor)
                cod, texto = g["codigo"], f"Você entrou no grupo {g['nome']}."
            else:
                cod = await app.em_segundo_plano(self.r.criar_grupo, valor)
                texto = f"Grupo criado! Mande o código {cod} para a sua turma."
        except rk.ErroRanking as ex:
            msg.content = comp.aviso(str(ex), c, "erro")
            app.page.update()
            return False
        self.codigo = cod
        app.aj.set("grupo_atual", cod)
        self.grupos = None
        self.visitando = None
        app.msg(texto)
        await self.carregar_grupos()
        return True

    # ------------------------------------------------------------------ com grupos

    def _com_grupos(self) -> ft.Control:
        app, c = self.app, self.app.c
        g = self.grupo
        conteudo = ft.Column([self._cabecalho_grupo(g), self._sala(g), self._abas(), self._conteudo_aba(g)], spacing=16)
        if not self.duas_colunas:
            return conteudo
        lateral = ft.Column([self._lista_grupos(), self._bloco_membros(g)], spacing=16)
        return ft.ResponsiveRow(
            [ft.Container(lateral, col={"um": 12, "lado": 4, "largo": 3}), ft.Container(conteudo, col={"um": 12, "lado": 8, "largo": 9})],
            spacing=20,
            run_spacing=16,
            breakpoints=comp.quebras(self.app, {"um": 0, "lado": LARGURA_DUAS_COLUNAS, "largo": 1600}),
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _lista_grupos(self) -> ft.Control:
        c = self.app.c
        novas = self.app.novidades_grupos()
        itens = []
        for g in (self.grupos or []) + ([self.visitando] if self.visitando else []):
            sel = g["codigo"] == self.codigo
            n = novas.get(g["codigo"], 0) if not sel else 0
            itens.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.GROUPS_ROUNDED if sel else ft.Icons.GROUPS_OUTLINED, color=c["tinta"] if sel else c["texto2"], size=22),
                            ft.Column(
                                [
                                    ft.Text(g["nome"], size=14.5, weight=ft.FontWeight.W_700 if sel else ft.FontWeight.W_500, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                    comp.apagado("visitando como admin" if g.get("visitante") else g["codigo"], c, 12),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                        ]
                        + ([comp.pilula(str(n), c["tinta"], c["sobre_tinta"], tamanho=11.5)] if n else []),
                        spacing=10,
                    ),
                    bgcolor=c["tinta_suave"] if sel else None,
                    border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    on_click=lambda e, cod=g["codigo"]: self._trocar_grupo(cod),
                    ink=True,
                )
            )
        return comp.bloco(ft.Column([ft.Container(comp.apagado("Seus grupos", c, 12.5), padding=ft.Padding.only(left=10, top=4, bottom=4)), *itens], spacing=2), c, padding=8)

    def _seletor_grupo(self) -> ft.Control:
        c = self.app.c
        novas = self.app.novidades_grupos()
        opcoes = []
        for g in (self.grupos or []) + ([self.visitando] if self.visitando else []):
            n = novas.get(g["codigo"], 0)
            opcoes.append(ft.DropdownOption(key=g["codigo"], text=g["nome"] + (f"  ({n} nova{'s' if n != 1 else ''})" if n and g["codigo"] != self.codigo else "")))
        return ft.Row(
            [
                ft.Dropdown(
                    value=self.codigo,
                    options=opcoes,
                    on_select=lambda e: self._trocar_grupo(e.control.value),
                    border_radius=10,
                    dense=True,
                    expand=True,
                    leading_icon=ft.Icons.GROUPS_OUTLINED,
                ),
                ft.PopupMenuButton(
                    icon=ft.Icons.ADD,
                    tooltip="Entrar ou criar grupo",
                    items=[
                        ft.PopupMenuItem(content="Entrar com código", icon=ft.Icons.LOGIN, on_click=lambda e: self._dialogo_entrar_criar("entrar")),
                        ft.PopupMenuItem(content="Criar grupo", icon=ft.Icons.ADD, on_click=lambda e: self._dialogo_entrar_criar("criar")),
                    ],
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _cabecalho_grupo(self, g: dict | None) -> ft.Control:
        app, c = self.app, self.app.c
        if g is None:
            return ft.Container()
        n = len(self.membros.get(g["codigo"], [])) or None
        info = [comp.apagado(f"código {g['codigo']}", c, 13)]
        if n:
            info.append(comp.apagado(f"{n} membro{'s' if n != 1 else ''}", c, 13))
        pilulas = []
        if g.get("visitante"):
            pilulas.append(comp.pilula("Admin visitando", c["marca_suave"], c["marca"], ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, 11.5))
        elif g.get("modero"):
            pilulas.append(comp.pilula("Você modera", c["tinta_suave"], c["tinta"], ft.Icons.SHIELD_OUTLINED, 11.5))
        menu = [
            ft.PopupMenuItem(content="Convidar pessoas (link)", icon=ft.Icons.SHARE_OUTLINED, on_click=lambda e: dialogo_convidar(app, g)),
            ft.PopupMenuItem(content="Copiar só o código", icon=ft.Icons.CONTENT_COPY, on_click=lambda e: app.page.run_task(self._copiar, g["codigo"])),
        ]
        if not g.get("visitante"):
            menu.append(ft.PopupMenuItem(content="Sair do grupo", icon=ft.Icons.LOGOUT, on_click=lambda e: self._confirmar_sair(g)))
        if g.get("modero") and (g.get("criado_por") == self.r.usuario_id or self.r.eh_admin):
            menu.append(ft.PopupMenuItem(content="Apagar grupo", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e: self._confirmar_apagar(g)))
        cabeca = ft.Row(
            [
                ft.Column(
                    [
                        ft.Row(
                            [ft.Text(g["nome"], size=22, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]), *pilulas],
                            spacing=10,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(info, spacing=14),
                    ],
                    spacing=2,
                    expand=True,
                ),
                (
                    ft.FilledButton(
                        "Convidar",
                        icon=ft.Icons.SHARE_OUTLINED,
                        tooltip="Mandar o link do grupo pelo WhatsApp, Instagram, TikTok…",
                        on_click=lambda e: dialogo_convidar(app, g),
                        style=ft.ButtonStyle(shape=comp.forma(10), padding=ft.Padding.symmetric(horizontal=14, vertical=12)),
                    )
                    if self.app.largo
                    else ft.IconButton(ft.Icons.SHARE_OUTLINED, tooltip="Convidar pelo link", icon_color=c["tinta"], on_click=lambda e: dialogo_convidar(app, g))
                )
                if not g.get("visitante")
                else ft.Container(),
                ft.IconButton(ft.Icons.REFRESH, tooltip="Atualizar", on_click=lambda e: self._atualizar()),
                ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, items=menu),
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if self.duas_colunas:
            return cabeca
        return ft.Column([self._seletor_grupo(), cabeca], spacing=12)

    def _sala(self, g: dict | None) -> ft.Control:
        """Sala da turma: os personagens de quem está no grupo, como no lobby de um jogo."""
        from .. import avatar as av

        app, c = self.app, self.app.c
        membros = self.membros.get(g["codigo"]) if g else None
        if not membros:
            return ft.Container()
        oculta = bool(app.aj.get("sala_oculta", False))

        def alternar(e):
            app.aj.set("sala_oculta", not oculta)
            self._redesenhar()

        n = len(membros)
        topo = ft.Row(
            [
                ft.Icon(ft.Icons.GROUPS_2_OUTLINED, size=18, color=c["tinta"]),
                ft.Text("Sala da turma", size=14, weight=ft.FontWeight.W_700, color=c["texto"]),
                comp.apagado(f"{n} pessoa{'s' if n != 1 else ''}" + (" · aparecem 10" if n > 10 else ""), c, 12.5),
                ft.Container(expand=True),
                comp.botao_texto("Mostrar" if oculta else "Esconder", alternar, ft.Icons.EXPAND_MORE if oculta else ft.Icons.EXPAND_LESS),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if oculta:
            return comp.bloco(topo, c, padding=ft.Padding.symmetric(horizontal=14, vertical=4))
        cenas = [k for k, _ in av.CENARIOS]
        cena = cenas[sum(map(ord, g["codigo"])) % len(cenas)]
        largura = app.largura_conteudo
        if self.duas_colunas:  # coluna da direita: 9 de 12 em tela bem larga, 8 de 12 nas outras
            largura = (largura - 20) * (0.75 if app.largura >= 1600 else 2 / 3)
        sala = sala_da_turma(app, membros, cena, largura - 32)  # menos as bordas e a margem do cartão
        return comp.bloco(ft.Column([topo, sala] if sala else [topo], spacing=8), c, padding=ft.Padding.only(left=14, right=14, top=4, bottom=12))

    def _abas(self) -> ft.Control:
        abas = [a for a in ABAS if not (a[0] == "membros" and self.duas_colunas)]
        if self.aba == "membros" and self.duas_colunas:
            self.aba = "conversa"
        curto = self.app.largura < 700
        botao = ft.SegmentedButton(
            selected=[self.aba],
            segments=[ft.Segment(value=k, label=ft.Text("Planos" if curto and k == "planos" else v)) for k, v in abas],
            show_selected_icon=False,
            on_change=self._trocar_aba,
        )
        return ft.Row([botao], scroll=ft.ScrollMode.AUTO)

    def _trocar_aba(self, e):
        self.aba = e.control.selected[0] if e.control.selected else "conversa"
        self._redesenhar()

    def _trocar_grupo(self, codigo: str | None):
        if not codigo or codigo == self.codigo:
            return
        self.codigo = codigo
        if not (self.visitando and self.visitando["codigo"] == codigo):
            self.app.aj.set("grupo_atual", codigo)
        self.abertos.clear()
        self._redesenhar()
        self.app.page.run_task(self.carregar_grupo)

    def _atualizar(self):
        if self.codigo:
            self.posts = {k: v for k, v in self.posts.items() if k[0] != self.codigo}
            self.membros.pop(self.codigo, None)
            self.linhas_ranking.pop(self.codigo, None)
            self.respostas = {k: v for k, v in self.respostas.items() if k not in self.abertos}
        self._redesenhar()
        self.app.page.run_task(self.carregar_grupo)

    def _conteudo_aba(self, g: dict | None) -> ft.Control:
        if g is None:
            return ft.Container()
        return {"conversa": self._conversa, "planos": self._planos, "ranking": self._ranking, "membros": self._aba_membros}[self.aba](g)

    # ------------------------------------------------------------------ carregamento

    async def carregar_grupos(self):
        app = self.app
        self.carregando, self.erro = True, None
        try:
            self.grupos = await app.em_segundo_plano(self.r.meus_grupos)
        except rk.ErroRanking as ex:
            self.erro = str(ex)
            self.carregando = False
            self._redesenhar()
            return
        self.carregando = False
        codigos = {g["codigo"] for g in self.grupos}
        self.visitando = None
        if self.codigo and self.codigo not in codigos and self.r.eh_admin:
            try:
                todos = await app.em_segundo_plano(self.r.todos_grupos)
                achado = next((g for g in todos if g["codigo"] == self.codigo), None)
                if achado:
                    self.visitando = {"codigo": achado["codigo"], "nome": achado["nome"], "modero": True, "visitante": True}
            except rk.ErroRanking:
                pass
        if not self.visitando and self.codigo not in codigos:
            self.codigo = self.grupos[0]["codigo"] if self.grupos else None
        self._redesenhar()
        if self.codigo:
            await self.carregar_grupo()

    async def carregar_grupo(self):
        """Carrega o que a aba atual precisa (e os membros, usados no cabeçalho)."""
        app, cod = self.app, self.codigo
        if not cod:
            return
        try:
            if cod not in self.membros:
                self.membros[cod] = await app.em_segundo_plano(self.r.membros_grupo, cod)
            for chave, tipo in (("conversa", "conversa"), ("planos", "plano")):
                if (cod, chave) not in self.posts and (self.aba == chave or chave == "conversa"):
                    self.posts[(cod, chave)] = await app.em_segundo_plano(self.r.forum, cod, tipo)
            if self.aba == "ranking" and cod not in self.linhas_ranking:
                self.linhas_ranking[cod] = await app.em_segundo_plano(self.r.ranking, "horas", None, cod)
            self.erro = None
        except rk.ErroRanking as ex:
            self.erro = str(ex)
        self._marcar_visto(cod)
        if self.codigo == cod:
            self._redesenhar()

    async def _atualizar_conversa(self, cod: str) -> None:
        """Busca a conversa de novo sem apagar a lista da tela (nada de "Buscando as mensagens…" piscando)."""
        try:
            self.posts[(cod, "conversa")] = await self.app.em_segundo_plano(self.r.forum, cod, "conversa")
        except rk.ErroRanking:
            self.posts.pop((cod, "conversa"), None)
            await self.carregar_grupo()
            return
        self._marcar_visto(cod)

    def _marcar_visto(self, cod: str):
        datas = [p["criado_em"] for chave in ("conversa", "planos") for p in self.posts.get((cod, chave), [])]
        if not datas:
            return
        vistos = dict(self.app.aj.get("forum_vistos", {}) or {})
        mais_novo = max(datas, key=rk._quando)
        if rk._quando(mais_novo) > rk._quando(vistos.get(cod)):
            vistos[cod] = mais_novo
            self.app.aj.set("forum_vistos", vistos)
        self.app.zerar_novidades(cod)

    def _precisa(self, chave: str) -> list[dict] | None:
        lista = self.posts.get((self.codigo, chave))
        if lista is None and not self.erro:
            self.app.page.run_task(self.carregar_grupo)
        return lista

    # ------------------------------------------------------------------ conversa

    def _conversa(self, g: dict) -> ft.Control:
        c = self.app.c
        filhos: list[ft.Control] = []
        if g.get("visitante"):
            filhos.append(comp.aviso("Você está vendo como administrador: pode fixar e apagar mensagens. Para escrever, entre no grupo com o código.", c, "info"))
        else:
            filhos.append(self._caixa_nova_mensagem(g))
        if self.erro:
            filhos.append(comp.aviso(self.erro, c, "erro"))
        posts = self._precisa("conversa")
        if posts is None:
            filhos.append(comp.carregando("Buscando as mensagens…", c))
        elif not posts and not self._rapidos:
            filhos.append(comp.vazio(ft.Icons.FORUM_OUTLINED, "Nenhuma mensagem ainda", "Comece a conversa: combine um simulado, pergunte algo ou mande um material.", c))
        posts = posts or []
        fixados = 0  # a figurinha que está indo aparece logo abaixo das fixadas, onde a mensagem nova vai ficar
        while fixados < len(posts) and posts[fixados].get("fixado"):
            fixados += 1
        filhos.extend(self._cartao_post(p, g) for p in posts[:fixados])
        filhos.extend(self._cartao_enviando(r) for r in self._rapidos if r["post"] is None)
        filhos.extend(self._cartao_post(p, g) for p in posts[fixados:])
        return ft.Column(filhos, spacing=12)

    def _caixa_nova_mensagem(self, g: dict) -> ft.Control:
        app, c = self.app, self.app.c
        texto = ft.TextField(
            value=self._rascunho,
            hint_text="Escreva para a turma: combine um simulado, tire uma dúvida, mande um material…",
            multiline=True,
            min_lines=2,
            max_lines=8,
            border_radius=12,
            on_change=lambda e: setattr(self, "_rascunho", e.control.value or ""),
        )
        assunto = ft.TextField(
            value=self._assunto,
            label="Assunto (opcional)",
            hint_text="Ex.: Questão 32 de Português (2024)" if self.tipo_novo == "duvida" else "Ex.: Resumo de LGPD",
            dense=True,
            border_radius=10,
            max_length=120,
            visible=self.tipo_novo != "conversa",
            on_change=lambda e: setattr(self, "_assunto", e.control.value or ""),
        )
        msg = ft.Container(visible=False)  # só aparece com um erro (assim não sobra espaço vazio na caixa)

        def trocar_tipo(e):
            self.tipo_novo = e.control.selected[0] if e.control.selected else "conversa"
            assunto.visible = self.tipo_novo != "conversa"
            assunto.hint_text = "Ex.: Questão 32 de Português (2024)" if self.tipo_novo == "duvida" else "Ex.: Resumo de LGPD"
            app.page.update()

        async def publicar(e):
            if self._enviando:
                app.msg("Espere os arquivos terminarem de subir.")
                return
            escolhida = self._figurinha_escolhida.get(None)
            so_figurinha = bool(escolhida) and not (texto.value or "").strip() and not self._pendentes
            item = None
            if so_figurinha:
                # só a figurinha: sai da caixa e aparece na conversa na hora, "enviando…"
                item = {**escolhida, "post": None}
                self._rapidos.append(item)
                self._figurinha_escolhida.pop(None, None)
                self._redesenhar()
            else:
                botao.disabled = True
                app.page.update()
            try:
                await self._publicar_com_figurinha(g, texto.value or "", self.tipo_novo, assunto.value or "", list(self._pendentes), escolhida)
            except rk.ErroRanking as ex:
                if item is not None:
                    self._rapidos = [r for r in self._rapidos if r is not item]
                    self._figurinha_escolhida[None] = escolhida  # volta para a caixa, para tentar de novo
                    self._redesenhar()
                    app.msg(f"A figurinha não foi: {ex}")
                    return
                botao.disabled = False
                msg.content = comp.aviso(str(ex), c, "erro")
                msg.visible = True
                app.page.update()
                return
            finally:
                if item is not None:
                    self._rapidos = [r for r in self._rapidos if r is not item]
            self._rascunho = ""
            self._assunto = ""
            self._pendentes = []
            self._figurinha_escolhida.pop(None, None)
            self.tipo_novo = "conversa"
            await self._atualizar_conversa(g["codigo"])
            self._redesenhar()

        async def anexar(e):
            from .anexos import escolher_arquivos

            await self._anexar_caminhos(g, await escolher_arquivos(app))

        def tirar(anexo):
            self._pendentes = [a for a in self._pendentes if a is not anexo]
            self.app.page.run_task(app.em_segundo_plano, self.r.apagar_anexos, [anexo])
            self._redesenhar()

        def figurinhas_gifs(e):
            from .anexos import dialogo_figurinhas_gifs

            dialogo_figurinhas_gifs(app, lambda tipo, valor: self._escolher_figurinha(None, tipo, valor))

        tipos = ft.SegmentedButton(
            selected=[self.tipo_novo],
            segments=[
                ft.Segment(value="conversa", label=ft.Text("Conversa"), icon=ft.Icon(ICONES_TIPO["conversa"])),
                ft.Segment(value="duvida", label=ft.Text("Dúvida"), icon=ft.Icon(ICONES_TIPO["duvida"])),
                ft.Segment(value="material", label=ft.Text("Material"), icon=ft.Icon(ICONES_TIPO["material"])),
            ],
            show_selected_icon=False,
            on_change=trocar_tipo,
        )
        botao = comp.botao("Publicar", publicar, ft.Icons.SEND_ROUNDED)
        ferramentas = ft.Row(
            [
                ft.IconButton(ft.Icons.ATTACH_FILE, tooltip="Anexar foto ou arquivo do computador (até 20 MB)", icon_color=c["texto2"], on_click=anexar),
                ft.IconButton(ft.Icons.EMOJI_EMOTIONS_OUTLINED, tooltip="Figurinhas e GIFs", icon_color=c["texto2"], on_click=figurinhas_gifs),
            ],
            spacing=0,
            tight=True,
        )
        from .anexos import chip_pendente

        pendentes = [chip_pendente(app, a, tirar) for a in self._pendentes] + [
            ft.Container(
                ft.Row([ft.ProgressRing(width=16, height=16, stroke_width=2, color=c["tinta"]), comp.apagado(f"Enviando {n}…", c, 12.5)], spacing=8, tight=True),
                bgcolor=c["sup2"],
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            )
            for n in self._enviando
        ]
        escolhida = self._figurinha_escolhida.get(None)
        caixa_texto: ft.Control = texto
        if escolhida:
            texto.hint_text = "Escreva algo junto, se quiser, e clique em Publicar"
            texto.min_lines = 1
            caixa_texto = ft.Column([texto, self._previa_escolhida(None, 104)], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        return comp.bloco(
            ft.Column(
                [
                    ft.Row([busto(self.app, None, self.r.apelido or "?", 34, self.r.usuario_id), ft.Container(caixa_texto, expand=True)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
                    assunto,
                    *([ft.Row(pendentes, wrap=True, spacing=8, run_spacing=8)] if pendentes else []),
                    msg,
                    ft.Row([ferramentas, ft.Row([tipos], scroll=ft.ScrollMode.AUTO, expand=True), botao], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                    if self.app.largo
                    else ft.Column([ft.Row([tipos], scroll=ft.ScrollMode.AUTO), ft.Row([ferramentas, ft.Container(expand=True), botao])], spacing=6),
                ],
                spacing=10,
            ),
            c,
            padding=16,
        )

    def _escolher_figurinha(self, post: int | None, tipo: str, valor) -> None:
        """A figurinha ou GIF vai para a prévia da mensagem (troca a que estava); só sai quando a pessoa envia."""
        self._figurinha_escolhida[post] = {"tipo": tipo, "valor": valor}
        self._redesenhar()

    def _previa_escolhida(self, post: int | None, lado: int) -> ft.Control:
        """A figurinha esperando o envio, com o X para tirar."""
        from .anexos import previa_envio

        c = self.app.c
        sel = self._figurinha_escolhida[post]
        gif = sel["tipo"] == "gif" and not (isinstance(sel["valor"], dict) and sel["valor"].get("figurinha"))

        def tirar(e):
            self._figurinha_escolhida.pop(post, None)
            self._redesenhar()

        return ft.Row(
            [
                ft.Stack(
                    [
                        ft.Container(previa_envio(self.app, sel["tipo"], sel["valor"], lado), padding=8, bgcolor=c["sup2"], border_radius=14,
                                     tooltip="GIF" if gif else "Figurinha"),
                        ft.Container(
                            ft.Icon(ft.Icons.CLOSE, size=14, color="#FFFFFF"),
                            width=24, height=24, border_radius=12, bgcolor="#99000000", alignment=ft.Alignment.CENTER,
                            right=4, top=4, on_click=tirar, tooltip="Tirar", ink=True,
                        ),
                    ],
                    width=lado + 16,
                    height=lado + 16,
                ),
                comp.apagado("GIF na mensagem" if gif else "Figurinha na mensagem", c, 12),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

    async def _publicar_com_figurinha(self, g: dict, texto: str, tipo: str, titulo: str, anexos: list[dict], escolhida: dict | None,
                                      post_id: int | None = None) -> None:
        """Envia a mensagem (ou resposta) com a figurinha escolhida. A sua figurinha sobe só agora, na hora de enviar."""
        from .anexos import conteudo_rapido

        extra: dict = {}
        subiram: list[dict] = []
        if escolhida:
            extra = await conteudo_rapido(self.app, g["codigo"], escolhida["tipo"], escolhida["valor"])
            subiram = [a for a in extra.get("anexos") or [] if a.get("caminho")]
            for a in extra.get("anexos") or []:
                self.visor.lembrar(a)
        todos = list(anexos) + list(extra.get("anexos") or [])
        try:
            if post_id is None:
                await self.app.em_segundo_plano(
                    lambda: self.r.forum_publicar(g["codigo"], texto, tipo, titulo, anexos=todos or None, figurinha=extra.get("figurinha"))
                )
            else:
                await self.app.em_segundo_plano(lambda: self.r.forum_responder(post_id, texto, anexos=todos or None, figurinha=extra.get("figurinha")))
        except rk.ErroRanking:
            if subiram:  # a figurinha que subiu e não foi: apaga do servidor
                self.app.page.run_task(self.app.em_segundo_plano, self.r.apagar_anexos, subiram)
            raise

    async def _anexar_caminhos(self, g: dict, caminhos: list[Path]):
        """Sobe os arquivos escolhidos; eles ficam esperando o "Publicar" (com o texto, se tiver)."""
        app = self.app
        vagas = rk.MAX_ANEXOS - len(self._pendentes)
        if len(caminhos) > vagas:
            app.msg(f"Dá para mandar até {rk.MAX_ANEXOS} arquivos por mensagem.")
        for cam in caminhos[: max(0, vagas)]:
            self._enviando.append(cam.name)
            self._redesenhar()
            try:
                anexo = await app.em_segundo_plano(self.r.enviar_anexo, g["codigo"], cam)
            except rk.ErroRanking as ex:
                app.msg(str(ex))
            else:
                self._pendentes.append(anexo)
            finally:
                self._enviando.remove(cam.name)
            self._redesenhar()

    async def _mandar_rapido(self, g: dict, tipo: str, valor):
        """Figurinha ou GIF vai na hora, como numa conversa: aparece na lista já, enquanto sobe."""
        from .anexos import conteudo_rapido

        item = {"tipo": tipo, "valor": valor, "post": None}
        self._rapidos.append(item)
        self._redesenhar()
        try:
            extra = await conteudo_rapido(self.app, g["codigo"], tipo, valor)
            for a in extra.get("anexos") or []:
                self.visor.lembrar(a)
            await self.app.em_segundo_plano(lambda: self.r.forum_publicar(g["codigo"], "", **extra))
            await self._atualizar_conversa(g["codigo"])
        except rk.ErroRanking as ex:
            self.app.msg(f"A figurinha não foi: {ex}")
        finally:
            self._rapidos = [r for r in self._rapidos if r is not item]
            self._redesenhar()

    def _linha_autor(self, m: dict, nome_tamanho: float = 14.5) -> list[ft.Control]:
        c = self.app.c
        linha = [ft.Text(m.get("apelido") or "?", size=nome_tamanho, weight=ft.FontWeight.W_700, color=c["texto"])]
        if m.get("meu"):
            linha.append(comp.pilula("você", c["tinta_suave"], c["tinta"], tamanho=10.5))
        linha.append(comp.apagado(quando_texto(m.get("criado_em")) + (" · editada" if m.get("editado_em") else ""), c, 12.5))
        return linha

    def _lado_figurinha(self, resposta: bool = False) -> int:
        if resposta:
            return 104 if self.app.largo else 92
        return 128 if self.app.largo else 112

    def _cartao_figurinha(self, p: dict, g: dict) -> ft.Control:
        """Mensagem que é só figurinha: compacta e sem moldura em volta do desenho, como numa conversa."""
        app, c = self.app, self.app.c
        lado = self._lado_figurinha()
        if p.get("figurinha"):
            desenho = self.visor.figurinha(p["figurinha"], lado)
        else:
            desenho = self.visor.anexos(p.get("anexos") or [], lado_adesivo=lado) or ft.Container()
        linha = self._linha_autor(p)
        if p.get("fixado"):
            linha.append(comp.pilula("Fixada", c["marca_suave"], c["marca"], ft.Icons.PUSH_PIN, 11))
        filhos: list[ft.Control] = [
            ft.Row(
                [
                    busto(app, p.get("avatar"), p.get("apelido") or "?", 36, p.get("autor")),
                    ft.Column(
                        [
                            ft.Row(linha, spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Row([desenho, self._acoes_post(p, g)], spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.END),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._menu_post(p, g),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        ]
        if p["id"] in self.abertos:
            filhos.append(self._respostas(p, g))
        cartao = comp.bloco(ft.Column(filhos, spacing=8), c, padding=ft.Padding.only(left=16, right=8, top=12, bottom=8))
        if p.get("fixado"):
            cartao.border = ft.Border.all(1.4, c["marca"])
        return cartao

    def _enviando_figurinha(self, r: dict, lado: int, tamanho_busto: int) -> ft.Control:
        """A sua figurinha aparecendo na hora, meio apagada, enquanto vai para o grupo."""
        from .anexos import previa_envio

        c = self.app.c
        return ft.Row(
            [
                busto(self.app, None, self.r.apelido or "?", tamanho_busto, self.r.usuario_id),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(self.r.apelido or "Você", size=14 if tamanho_busto > 30 else 13.5, weight=ft.FontWeight.W_700, color=c["texto"]),
                                ft.ProgressRing(width=12, height=12, stroke_width=2, color=c["tinta"]),
                                comp.apagado("enviando…", c, 12.5),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(previa_envio(self.app, r["tipo"], r["valor"], lado), opacity=0.6, animate_opacity=200),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=12 if tamanho_busto > 30 else 10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _cartao_enviando(self, r: dict) -> ft.Control:
        return comp.bloco(self._enviando_figurinha(r, self._lado_figurinha(), 36), self.app.c, padding=ft.Padding.only(left=16, right=8, top=12, bottom=12))

    def _cartao_post(self, p: dict, g: dict) -> ft.Control:
        from .anexos import so_figurinha

        if so_figurinha(p):
            return self._cartao_figurinha(p, g)
        app, c = self.app, self.app.c
        tipo = p.get("tipo") or "conversa"
        nome_tipo = rk.TIPOS_FORUM.get(tipo, ("Conversa", ""))[0]
        linha_autor = self._linha_autor(p)
        topo = ft.Row(
            [
                busto(app, p.get("avatar"), p.get("apelido") or "?", 36, p.get("autor")),
                ft.Column(
                    [
                        ft.Row(linha_autor, spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Row(
                            ([comp.pilula("Fixada", c["marca_suave"], c["marca"], ft.Icons.PUSH_PIN, 11)] if p.get("fixado") else [])
                            + ([comp.pilula(nome_tipo, c["sup2"], c["texto2"], ICONES_TIPO.get(tipo), 11)] if tipo != "conversa" else []),
                            spacing=6,
                        )
                        if p.get("fixado") or tipo != "conversa"
                        else ft.Container(height=0),
                    ],
                    spacing=3,
                    expand=True,
                ),
                self._menu_post(p, g),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        corpo: list[ft.Control] = [topo]
        if p.get("titulo"):
            corpo.append(ft.Text(p["titulo"], size=16, weight=ft.FontWeight.W_600, color=c["texto"]))
        if p.get("plano"):
            corpo.append(self._resumo_plano(p["plano"]))
        if p.get("texto"):
            corpo.append(ft.Text(p["texto"], size=14.5, color=c["texto"], selectable=True))
            links = URL.findall(p["texto"])
            if links:
                corpo.append(
                    ft.Row(
                        [comp.botao_texto("Abrir link" if len(links) == 1 else f"Abrir link {i + 1}", lambda e, u=u: app.page.run_task(app.abrir_url, u.rstrip(".,);")), ft.Icons.OPEN_IN_NEW) for i, u in enumerate(links[:3])],
                        spacing=4,
                        wrap=True,
                    )
                )
        if p.get("figurinha"):
            corpo.append(self.visor.figurinha(p["figurinha"]))
        visuais = self.visor.anexos(p.get("anexos") or [])
        if visuais is not None:
            corpo.append(visuais)
        corpo.append(self._acoes_post(p, g))
        if p["id"] in self.abertos:
            corpo.append(self._respostas(p, g))
        cartao = comp.bloco(ft.Column(corpo, spacing=10), c, padding=16)
        if p.get("fixado"):
            cartao.border = ft.Border.all(1.4, c["marca"])
        return cartao

    def _menu_post(self, p: dict, g: dict) -> ft.Control:
        app = self.app
        itens = [ft.PopupMenuItem(content="Copiar texto", icon=ft.Icons.CONTENT_COPY, on_click=lambda e: app.page.run_task(self._copiar_texto, (p.get("titulo") or "") + "\n" + (p.get("texto") or "")))]
        if g.get("modero"):
            itens.append(
                ft.PopupMenuItem(
                    content="Desafixar" if p.get("fixado") else "Fixar no topo",
                    icon=ft.Icons.PUSH_PIN_OUTLINED,
                    on_click=lambda e: app.page.run_task(self._fixar, p, not p.get("fixado")),
                )
            )
        if p.get("meu") or g.get("modero"):
            itens.append(ft.PopupMenuItem(content="Apagar", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e: self._confirmar_apagar_post(p)))
        return ft.PopupMenuButton(icon=ft.Icons.MORE_HORIZ, items=itens, tooltip="Opções")

    def _acoes_post(self, p: dict, g: dict) -> ft.Control:
        app, c = self.app, self.app.c
        pode = not g.get("visitante")
        util = ft.TextButton(
            f"Útil · {p['uteis']}" if p.get("uteis") else "Útil",
            icon=ft.Icons.THUMB_UP if p.get("util_meu") else ft.Icons.THUMB_UP_OUTLINED,
            style=ft.ButtonStyle(color=c["tinta"] if p.get("util_meu") else c["texto2"], shape=comp.forma(8)),
            on_click=(lambda e: app.page.run_task(self._util, p)) if pode else None,
            disabled=not pode,
        )
        n = p.get("respostas") or 0
        aberto = p["id"] in self.abertos
        responder = ft.TextButton(
            "Esconder respostas" if aberto else (f"{n} resposta{'s' if n != 1 else ''}" if n else "Responder"),
            icon=ft.Icons.EXPAND_LESS if aberto else ft.Icons.CHAT_BUBBLE_OUTLINE,
            style=ft.ButtonStyle(color=c["texto2"], shape=comp.forma(8)),
            on_click=lambda e: self._alternar_respostas(p),
        )
        return ft.Row([util, responder], spacing=4, wrap=True)

    def _respostas(self, p: dict, g: dict) -> ft.Control:
        app, c = self.app, self.app.c
        lista = self.respostas.get(p["id"])
        filhos: list[ft.Control] = []
        if lista is None:
            filhos.append(comp.carregando("Carregando respostas…", c))
        else:
            from .anexos import so_figurinha

            lado_resp = self._lado_figurinha(resposta=True)
            for r in lista:
                so_fig = so_figurinha(r)  # só figurinha: sem o balão cinza em volta, como numa conversa
                filhos.append(
                    ft.Row(
                        [
                            busto(self.app, r.get("avatar"), r.get("apelido") or "?", 28, r.get("autor")),
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Row(
                                            [ft.Text(r.get("apelido") or "?", size=13.5, weight=ft.FontWeight.W_700, color=c["texto"]), comp.apagado(quando_texto(r.get("criado_em")), c, 12)],
                                            spacing=8,
                                        ),
                                    ]
                                    + ([ft.Text(r["texto"], size=14, color=c["texto"], selectable=True)] if r.get("texto") else [])
                                    + ([self.visor.figurinha(r["figurinha"], lado_resp)] if r.get("figurinha") else [])
                                    + ([v] if (v := self.visor.anexos(r.get("anexos") or [], compacto=True, lado_adesivo=lado_resp)) is not None else []),
                                    spacing=4,
                                ),
                                bgcolor=None if so_fig else c["sup2"],
                                border_radius=12,
                                padding=ft.Padding.only(left=2, top=2) if so_fig else ft.Padding.symmetric(horizontal=12, vertical=8),
                                expand=True,
                            ),
                        ]
                        + (
                            [ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, tooltip="Apagar resposta", on_click=lambda e, r=r: app.page.run_task(self._apagar_resposta, p, r))]
                            if r.get("meu") or g.get("modero")
                            else []
                        ),
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                )
        filhos.extend(self._enviando_figurinha(r, self._lado_figurinha(resposta=True), 28) for r in self._rapidos if r["post"] == p["id"])
        if not g.get("visitante"):
            escolhida = self._figurinha_escolhida.get(p["id"])
            campo = ft.TextField(
                value=self._rascunho_resposta.get(p["id"], ""),
                hint_text="Escreva algo junto, se quiser, e aperte Enter" if escolhida else "Escreva uma resposta…",
                dense=True, border_radius=20, expand=True, multiline=True, min_lines=1, max_lines=5, shift_enter=True,
                on_change=lambda e: self._rascunho_resposta.__setitem__(p["id"], e.control.value or ""),
                autofocus=bool(escolhida),
            )

            async def enviar(e):
                sel = self._figurinha_escolhida.get(p["id"])
                texto_resp = campo.value or ""
                item = None
                if sel and not texto_resp.strip():
                    item = {**sel, "post": p["id"]}  # só a figurinha: aparece na hora, "enviando…"
                    self._rapidos.append(item)
                    self._figurinha_escolhida.pop(p["id"], None)
                    self._redesenhar()
                try:
                    await self._publicar_com_figurinha(g, texto_resp, "", "", [], sel, post_id=p["id"])
                    self.respostas[p["id"]] = await app.em_segundo_plano(self.r.forum_respostas, p["id"])
                except rk.ErroRanking as ex:
                    if item is not None:
                        self._figurinha_escolhida[p["id"]] = sel
                    app.msg(str(ex))
                    return
                finally:
                    if item is not None:
                        self._rapidos = [r for r in self._rapidos if r is not item]
                        self._redesenhar()
                self._figurinha_escolhida.pop(p["id"], None)
                self._rascunho_resposta.pop(p["id"], None)
                p["respostas"] = len(self.respostas[p["id"]])
                self._redesenhar()

            async def recarregar():
                self.respostas[p["id"]] = await app.em_segundo_plano(self.r.forum_respostas, p["id"])
                p["respostas"] = len(self.respostas[p["id"]])
                self._redesenhar()

            async def anexar(e):
                from .anexos import escolher_arquivos

                caminhos = await escolher_arquivos(app)
                if not caminhos:
                    return
                app.msg(f"Enviando {len(caminhos)} arquivo{'s' if len(caminhos) > 1 else ''}…")
                lista = []
                for cam in caminhos:
                    try:
                        lista.append(await app.em_segundo_plano(self.r.enviar_anexo, g["codigo"], cam))
                    except rk.ErroRanking as ex:
                        app.msg(str(ex))
                if not lista:
                    return
                try:
                    await app.em_segundo_plano(lambda: self.r.forum_responder(p["id"], campo.value or "", anexos=lista))
                except rk.ErroRanking as ex:
                    app.msg(str(ex))
                    return
                await recarregar()

            def figurinhas_gifs(e):
                from .anexos import dialogo_figurinhas_gifs

                dialogo_figurinhas_gifs(app, lambda tipo, valor: self._escolher_figurinha(p["id"], tipo, valor))

            campo.on_submit = enviar
            if escolhida:
                filhos.append(ft.Container(self._previa_escolhida(p["id"], 88), padding=ft.Padding.only(left=38)))
            filhos.append(
                ft.Row(
                    [
                        busto(self.app, None, self.r.apelido or "?", 28, self.r.usuario_id),
                        campo,
                        ft.IconButton(ft.Icons.ATTACH_FILE, tooltip="Anexar foto ou arquivo", icon_size=20, icon_color=c["texto2"], on_click=anexar),
                        ft.IconButton(ft.Icons.EMOJI_EMOTIONS_OUTLINED, tooltip="Figurinhas e GIFs", icon_size=20, icon_color=c["texto2"], on_click=figurinhas_gifs),
                        ft.IconButton(ft.Icons.SEND_ROUNDED, tooltip="Enviar", icon_color=c["tinta"], on_click=enviar),
                    ],
                    spacing=4,
                )
            )
        return ft.Container(ft.Column(filhos, spacing=10), padding=ft.Padding.only(left=8, top=4), border=ft.Border.only(left=ft.BorderSide(2, c["borda"])))

    # ------------------------------------------------------------------ ações

    def _alternar_respostas(self, p: dict):
        if p["id"] in self.abertos:
            self.abertos.discard(p["id"])
        else:
            self.abertos.add(p["id"])
            if p["id"] not in self.respostas:
                self.app.page.run_task(self._carregar_respostas, p)
        self._redesenhar()

    async def _carregar_respostas(self, p: dict):
        try:
            self.respostas[p["id"]] = await self.app.em_segundo_plano(self.r.forum_respostas, p["id"])
        except rk.ErroRanking as ex:
            self.respostas[p["id"]] = []
            self.app.msg(str(ex))
        self._redesenhar()

    async def _util(self, p: dict):
        marcar = not p.get("util_meu")
        try:
            await self.app.em_segundo_plano(self.r.forum_util, p["id"], marcar)
        except rk.ErroRanking as ex:
            self.app.msg(str(ex))
            return
        p["util_meu"] = marcar
        p["uteis"] = max(0, (p.get("uteis") or 0) + (1 if marcar else -1))
        self._redesenhar()

    async def _fixar(self, p: dict, fixado: bool):
        try:
            await self.app.em_segundo_plano(self.r.forum_fixar, p["id"], fixado)
        except rk.ErroRanking as ex:
            self.app.msg(str(ex))
            return
        self.app.msg("Mensagem fixada no topo." if fixado else "Mensagem desafixada.")
        self._atualizar()

    def _confirmar_apagar_post(self, p: dict):
        app = self.app

        async def apagar(e):
            app.page.pop_dialog()
            try:
                await app.em_segundo_plano(self.r.forum_apagar, p["id"])
            except rk.ErroRanking as ex:
                app.msg(str(ex))
                return
            # os arquivos vão junto: os da mensagem e os das respostas (cada um da pasta de quem mandou)
            if p.get("anexos"):
                await app.em_segundo_plano(self.r.apagar_anexos, p["anexos"], p.get("autor"))
            for r in self.respostas.pop(p["id"], None) or []:
                if r.get("anexos"):
                    await app.em_segundo_plano(self.r.apagar_anexos, r["anexos"], r.get("autor"))
            app.msg("Mensagem apagada.")
            self._atualizar()

        quem = "sua mensagem" if p.get("meu") else f"a mensagem de {p.get('apelido')}"
        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Apagar {quem}?"),
                content=ft.Text("As respostas dela também somem. Não dá para desfazer.", size=14.5),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Apagar", apagar, ft.Icons.DELETE_OUTLINE)],
            )
        )

    async def _apagar_resposta(self, p: dict, r: dict):
        try:
            await self.app.em_segundo_plano(self.r.forum_apagar_resposta, r["id"])
            if r.get("anexos"):
                await self.app.em_segundo_plano(self.r.apagar_anexos, r["anexos"], r.get("autor"))
            self.respostas[p["id"]] = await self.app.em_segundo_plano(self.r.forum_respostas, p["id"])
        except rk.ErroRanking as ex:
            self.app.msg(str(ex))
            return
        p["respostas"] = len(self.respostas[p["id"]])
        self._redesenhar()

    async def _copiar(self, codigo: str):
        try:
            await ft.Clipboard().set(codigo)
            self.app.msg(f"Código {codigo} copiado. Mande para quem você quer no grupo.")
        except Exception:  # noqa: BLE001
            self.app.msg(f"Código do grupo: {codigo}")

    async def _copiar_texto(self, texto: str):
        try:
            await ft.Clipboard().set(texto.strip())
            self.app.msg("Texto copiado.")
        except Exception:  # noqa: BLE001
            pass

    def _confirmar_sair(self, g: dict):
        app = self.app

        async def sair(e):
            app.page.pop_dialog()
            try:
                await app.em_segundo_plano(self.r.sair_grupo, g["codigo"])
            except rk.ErroRanking as ex:
                app.msg(str(ex))
                return
            app.msg(f"Você saiu do grupo {g['nome']}.")
            self.codigo = None
            app.aj.set("grupo_atual", "")
            self.grupos = None
            self._redesenhar()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Sair do grupo {g['nome']}?"),
                content=ft.Text("Você para de ver as mensagens. Para voltar, use o código do grupo.", size=14.5),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Sair", sair, ft.Icons.LOGOUT)],
            )
        )

    def _confirmar_apagar(self, g: dict):
        app = self.app

        async def apagar(e):
            app.page.pop_dialog()
            try:
                await app.em_segundo_plano(self.r.apagar_grupo, g["codigo"])
            except rk.ErroRanking as ex:
                app.msg(str(ex))
                return
            app.msg(f"Grupo {g['nome']} apagado.")
            self.codigo = None
            app.aj.set("grupo_atual", "")
            self.grupos = None
            self.visitando = None
            self._redesenhar()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Apagar o grupo {g['nome']}?"),
                content=ft.Text("Todos saem do grupo e as mensagens, respostas e planos do fórum são apagados. Não dá para desfazer.", size=14.5),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Apagar grupo", apagar, ft.Icons.DELETE_OUTLINE)],
            )
        )

    def _dialogo_entrar_criar(self, modo: str):
        app, c = self.app, self.app.c
        campo = (
            ft.TextField(label="Código do grupo", hint_text="Ex.: DATAPREV-7A2F", border_radius=10, autofocus=True, capitalization=ft.TextCapitalization.CHARACTERS)
            if modo == "entrar"
            else ft.TextField(label="Nome do grupo", hint_text="Ex.: Turma Dataprev", border_radius=10, autofocus=True, max_length=40)
        )
        msg = ft.Container()

        async def ok(e):
            if await self._entrar_ou_criar(modo, campo.value or "", msg):
                app.page.pop_dialog()

        campo.on_submit = ok
        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Entrar num grupo" if modo == "entrar" else "Criar um grupo", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
                content=ft.Column(
                    [
                        comp.apagado(
                            "Digite o código que alguém da turma te passou." if modo == "entrar" else "Você vira moderador do grupo. Depois mande o código para a turma.",
                            c,
                            14,
                        ),
                        campo,
                        msg,
                    ],
                    tight=True,
                    spacing=12,
                    width=min(440, (app.page.width or 480) - 40),
                ),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Entrar" if modo == "entrar" else "Criar", ok, ft.Icons.CHECK)],
            )
        )

    # ------------------------------------------------------------------ planos

    def _planos(self, g: dict) -> ft.Control:
        app, c = self.app, self.app.c
        filhos: list[ft.Control] = []
        ativo = app.aj.get("plano_ativo", {}) or {}
        explica = ft.Column(
            [
                comp.subtitulo("Planos de estudo da turma", c, 19),
                comp.apagado("Horas por disciplina na semana e dias de estudo. Gostou de um? Use e acompanhe na tela Início.", c, 13.5),
            ],
            spacing=2,
        )
        compartilhar = [] if g.get("visitante") else [comp.botao("Compartilhar um plano", lambda e: dialogo_plano(app, g, self._depois_de_publicar_plano), ft.Icons.ADD)]
        if app.largo:
            explica.expand = True
            topo = ft.Row([explica, *compartilhar], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            topo = ft.Column([explica, *compartilhar], spacing=10)
        filhos.append(topo)
        if ativo:
            filhos.append(
                comp.aviso(
                    f"Você está usando o plano “{ativo.get('titulo')}”, de {ativo.get('autor')}: {horas_texto(ativo.get('meta_horas'))} por semana.",
                    c,
                    "ok",
                    comp.botao_texto("Parar de usar", lambda e: self._parar_plano()),
                )
            )
        if self.erro:
            filhos.append(comp.aviso(self.erro, c, "erro"))
        posts = self._precisa("planos")
        if posts is None:
            filhos.append(comp.carregando("Buscando os planos…", c))
        elif not posts:
            filhos.append(
                comp.vazio(
                    ft.Icons.EVENT_NOTE_OUTLINED,
                    "Nenhum plano ainda",
                    "Compartilhe o seu: quantas horas por semana em cada disciplina e em quais dias. Ajuda quem está começando.",
                    c,
                )
            )
        else:
            filhos.append(
                ft.ResponsiveRow(
                    [ft.Container(self._cartao_plano(p, g, ativo), col={"um": 12, "dois": 6}) for p in posts],
                    spacing=14,
                    run_spacing=14,
                    breakpoints=comp.quebras(self.app, {"um": 0, "dois": 1500}),
                )
            )
        return ft.Column(filhos, spacing=14)

    def _resumo_plano(self, plano: dict) -> ft.Control:
        c = self.app.c
        discs = plano.get("disciplinas") or []
        maior = max((float(d.get("horas") or 0) for d in discs), default=1) or 1
        info = [
            comp.pilula(f"{horas_texto(plano.get('meta_horas'))} por semana", c["tinta_suave"], c["tinta"], ft.Icons.TIMER_OUTLINED, 11.5),
            comp.pilula(dias_texto(plano.get("dias") or []), c["sup2"], c["texto2"], ft.Icons.CALENDAR_MONTH_OUTLINED, 11.5),
        ]
        if plano.get("semanas"):
            info.append(comp.pilula(f"{plano['semanas']} semanas", c["sup2"], c["texto2"], ft.Icons.FLAG_OUTLINED, 11.5))
        if plano.get("concurso"):
            info.append(comp.pilula(plano["concurso"], c["marca_suave"], c["marca"], ft.Icons.CAMPAIGN_OUTLINED, 11.5))
        linhas = []
        for d in discs:
            h = float(d.get("horas") or 0)
            linhas.append(
                ft.Column(
                    [
                        ft.Row(
                            [ft.Text(d.get("nome") or "", size=13.5, color=c["texto"], expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), ft.Text(horas_texto(h), size=13.5, weight=ft.FontWeight.W_600, color=c["texto"])],
                            spacing=8,
                        ),
                        comp.barra(h / maior, c, altura=6),
                    ],
                    spacing=4,
                )
            )
        return ft.Column([ft.Row(info, spacing=6, wrap=True, run_spacing=6), ft.Column(linhas, spacing=8)], spacing=12)

    def _cartao_plano(self, p: dict, g: dict, ativo: dict) -> ft.Control:
        app, c = self.app, self.app.c
        em_uso = ativo.get("id") == p["id"] and ativo.get("codigo") == g["codigo"]
        cartao = self._cartao_post(p, g)
        usar = (
            comp.pilula("Em uso", c["ok_suave"], c["ok"], ft.Icons.CHECK, 12)
            if em_uso
            else comp.botao("Usar este plano", lambda e: self._confirmar_usar(p, g), ft.Icons.PLAYLIST_ADD_CHECK)
        )
        coluna: ft.Column = cartao.content
        coluna.controls.insert(len(coluna.controls) - (2 if p["id"] in self.abertos else 1), ft.Row([usar], spacing=8))
        if em_uso:
            cartao.border = ft.Border.all(1.6, c["ok"])
        return cartao

    def _confirmar_usar(self, p: dict, g: dict):
        app, c = self.app, self.app.c
        plano = p.get("plano") or {}

        def usar(e):
            app.page.pop_dialog()
            usar_plano(app, p, g)
            self._redesenhar()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Usar este plano?", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
                content=ft.Column(
                    [
                        ft.Text(
                            f"Sua meta passa a ser {horas_texto(plano.get('meta_horas'))} por semana, estudando {dias_texto(plano.get('dias') or [])}.",
                            size=15,
                            color=c["texto"],
                        ),
                        comp.apagado("Na tela Início aparece quanto você já estudou de cada disciplina do plano nesta semana. Dá para parar de usar quando quiser.", c, 13.5),
                    ],
                    tight=True,
                    spacing=10,
                    width=min(460, (app.page.width or 500) - 40),
                ),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Usar o plano", usar, ft.Icons.CHECK)],
            )
        )

    def _parar_plano(self):
        parar_plano(self.app)
        self._redesenhar()

    def _depois_de_publicar_plano(self):
        if self.codigo:
            self.posts.pop((self.codigo, "planos"), None)
        self.aba = "planos"
        self._redesenhar()
        self.app.page.run_task(self.carregar_grupo)

    # ------------------------------------------------------------------ ranking e membros

    def _ranking(self, g: dict) -> ft.Control:
        from .ranking import SecaoRanking

        app, c = self.app, self.app.c
        linhas = self.linhas_ranking.get(g["codigo"])
        if linhas is None:
            if not self.erro:
                app.page.run_task(self.carregar_grupo)
                return comp.carregando("Buscando o ranking do grupo…", c)
            return comp.aviso(self.erro, c, "erro")
        rodape = ft.Row(
            [
                comp.apagado("Horas estudadas nesta semana, só entre quem está no grupo.", c, 12.5),
                comp.botao_texto("Mais opções em Painel → Ranking", lambda e: app.ir("painel", aba="ranking"), ft.Icons.ARROW_FORWARD),
            ],
            spacing=8,
            wrap=True,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        if not linhas:
            return ft.Column([comp.vazio(ft.Icons.LEADERBOARD_OUTLINED, "Ninguém estudou ainda nesta semana", "Os números aparecem assim que alguém do grupo estuda pelo app.", c), rodape])
        secao = SecaoRanking(app, lambda: None)
        secao.metrica = "horas"
        return ft.Column([comp.bloco(ft.Column([secao._linha(c, l) for l in linhas[:30]], spacing=0), c, padding=6), rodape], spacing=10)

    def _lista_membros(self, g: dict) -> list[ft.Control]:
        c = self.app.c
        membros = self.membros.get(g["codigo"])
        if membros is None:
            return [comp.carregando("Carregando…", c)]
        itens = []
        for m in membros:
            selos = []
            if m["criador"]:
                selos.append(comp.pilula("criou o grupo", c["tinta_suave"], c["tinta"], tamanho=10.5))
            if m["voce"]:
                selos.append(comp.pilula("você", c["sup2"], c["texto2"], tamanho=10.5))
            itens.append(
                ft.Row(
                    [
                        busto(self.app, m.get("avatar"), m["apelido"], 32, m.get("usuario_id")),
                        ft.Column(
                            [ft.Row([ft.Text(m["apelido"], size=14, weight=ft.FontWeight.W_600, color=c["texto"]), *selos], spacing=6, wrap=True)]
                            + ([comp.apagado(m["concurso"], c, 12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)] if m["concurso"] else []),
                            spacing=1,
                            expand=True,
                        ),
                    ],
                    spacing=10,
                )
            )
        return itens or [comp.apagado("Ninguém no grupo.", c, 13)]

    def _bloco_membros(self, g: dict | None) -> ft.Control:
        c = self.app.c
        if g is None:
            return ft.Container()
        n = len(self.membros.get(g["codigo"]) or [])
        return comp.bloco(
            ft.Column([comp.apagado(f"Membros ({n})" if n else "Membros", c, 12.5), *self._lista_membros(g)], spacing=10),
            c,
            padding=14,
        )

    def _aba_membros(self, g: dict) -> ft.Control:
        return comp.bloco(ft.Column(self._lista_membros(g), spacing=12), self.app.c, padding=16)


# ---------------------------------------------------------------------- plano: usar, parar, publicar


def usar_plano(app, p: dict, g: dict) -> None:
    plano = p.get("plano") or {}
    app.aj.set("meta_horas_semana", float(plano.get("meta_horas") or app.aj["meta_horas_semana"]))
    if plano.get("dias"):
        app.aj.set("dias_planejados", ",".join(str(d) for d in sorted(plano["dias"])))
    app.aj.set(
        "plano_ativo",
        {
            "id": p["id"],
            "codigo": g["codigo"],
            "grupo": g["nome"],
            "titulo": p.get("titulo") or "Plano",
            "autor": p.get("apelido") or "",
            "meta_horas": plano.get("meta_horas"),
            "dias": plano.get("dias") or [],
            "disciplinas": plano.get("disciplinas") or [],
            "desde": date.today().isoformat(),
        },
    )
    app.msg("Plano em uso! Acompanhe o andamento na tela Início.")


def parar_plano(app) -> None:
    app.aj.set("plano_ativo", {})
    app.msg("Você parou de usar o plano. A meta semanal continua como está (mude em Início → meta).")


def progresso_plano(app, plano: dict) -> list[dict]:
    """Horas planejadas x estudadas nesta semana, por disciplina do plano."""
    semana = rk.inicio_semana()
    feito = {}
    for nome, seg in app.db.tempo_por_disciplina(semana):
        feito[_norm(nome)] = feito.get(_norm(nome), 0) + seg
    saida = []
    for d in plano.get("disciplinas") or []:
        meta_s = float(d.get("horas") or 0) * 3600
        s = feito.get(_norm(d.get("nome")), 0)
        saida.append({"nome": d.get("nome"), "meta_s": meta_s, "feito_s": s, "fracao": min(1.0, s / meta_s) if meta_s else 0})
    return saida


def cartao_plano_ativo(app) -> ft.Control | None:
    """Cartão da tela Início com o plano em uso e o quanto já foi feito na semana."""
    plano = app.aj.get("plano_ativo", {}) or {}
    if not plano.get("disciplinas"):
        return None
    c = app.c
    itens = progresso_plano(app, plano)
    total_meta = sum(i["meta_s"] for i in itens)
    total_feito = sum(min(i["feito_s"], i["meta_s"]) for i in itens)
    linhas = []
    for i in itens:
        cumprido = i["meta_s"] and i["feito_s"] >= i["meta_s"]
        linhas.append(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CHECK_CIRCLE if cumprido else ft.Icons.RADIO_BUTTON_UNCHECKED, size=16, color=c["ok"] if cumprido else c["texto2"]),
                            ft.Text(i["nome"], size=13.5, color=c["texto"], expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(f"{metas.fmt_hm(i['feito_s'])} de {horas_texto(i['meta_s'] / 3600)}", size=13, color=c["texto2"]),
                        ],
                        spacing=8,
                    ),
                    comp.barra(i["fracao"], c, cor=c["ok"] if cumprido else None, altura=6),
                ],
                spacing=4,
            )
        )
    hoje = date.today().weekday()
    dia_de_estudo = hoje in (plano.get("dias") or [])
    sub = f"de {plano.get('autor')} · {plano.get('grupo')}" if plano.get("autor") else plano.get("grupo", "")
    return comp.bloco(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EVENT_NOTE_OUTLINED, color=c["tinta"]),
                        ft.Column(
                            [
                                ft.Text(f"Seu plano: {plano.get('titulo')}", size=16, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=2),
                                comp.apagado(sub, c, 12.5),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                        ft.Text(f"{round(100 * total_feito / total_meta) if total_meta else 0}%", size=20, weight=ft.FontWeight.W_700, color=c["tinta"]),
                    ],
                    spacing=10,
                ),
                comp.apagado(
                    ("Hoje é dia de estudo no plano." if dia_de_estudo else "Hoje é folga no plano.") + f" Dias: {dias_texto(plano.get('dias') or [])}.",
                    c,
                    13,
                ),
                *linhas,
                ft.Row(
                    [
                        comp.botao_texto("Ver no grupo", lambda e: app.ir("grupos", codigo=plano.get("codigo"), aba="planos"), ft.Icons.FORUM_OUTLINED),
                        comp.botao_texto("Parar de usar", lambda e: (parar_plano(app), app.recarregar_tela())),
                    ],
                    spacing=4,
                    wrap=True,
                ),
            ],
            spacing=10,
        ),
        c,
        padding=18,
    )


def dialogo_plano(app, g: dict, ao_publicar) -> None:
    """Formulário para compartilhar um plano de estudo no grupo."""
    c = app.c
    largura = min(560, (app.page.width or 600) - 40)
    titulo = ft.TextField(label="Nome do plano", hint_text="Ex.: Plano 12h — reta final Dataprev", border_radius=10, autofocus=True)
    concurso = ft.TextField(label="Concurso (opcional)", hint_text="Ex.: Dataprev 2026", border_radius=10, dense=True, expand=True)
    semanas = ft.TextField(label="Semanas", hint_text="Ex.: 8", border_radius=10, dense=True, width=110, keyboard_type=ft.KeyboardType.NUMBER)
    obs = ft.TextField(label="Como usar o plano (opcional)", hint_text="Ex.: sábado é simulado completo; domingo, revisão leve.", multiline=True, min_lines=2, max_lines=5, border_radius=10)
    escolhidos = set(analise.dias_planejados(app.aj["dias_planejados"]))
    dias_linha = ft.Row(spacing=6, wrap=True, run_spacing=6)
    linhas = ft.Column(spacing=8)
    total = ft.Text("", size=14, weight=ft.FontWeight.W_600, color=c["tinta"])
    msg = ft.Container()

    # começa com as disciplinas que a pessoa já estuda (ou as mais comuns)
    conhecidas = sorted({q["disciplina"] for q in app.db.banco_de_questoes()} - {"Geral", ""})
    iniciais = (conhecidas or ["Língua Portuguesa", "Raciocínio Lógico", "Informática", "Conhecimentos Específicos"])[:5]
    meta_atual = float(app.aj["meta_horas_semana"] or 10)
    por_disc = max(0.5, round(meta_atual / max(1, len(iniciais)) * 2) / 2)

    def somar(*_):
        soma = 0.0
        for linha in linhas.controls:
            try:
                soma += float((linha.controls[1].value or "0").replace(",", "."))
            except ValueError:
                pass
        total.value = f"Total: {horas_texto(soma)} por semana"
        try:
            total.update()
        except RuntimeError:  # ainda não está na tela
            pass

    def remover(linha):
        linhas.controls.remove(linha)
        somar()
        app.page.update()

    def adicionar(nome: str = "", horas: float | str = ""):
        nome_f = ft.TextField(value=nome, label="Disciplina", dense=True, border_radius=10, expand=True)
        horas_f = ft.TextField(value=str(horas).replace(".", ",") if horas != "" else "", label="Horas", dense=True, border_radius=10, width=90, keyboard_type=ft.KeyboardType.NUMBER, on_change=somar)
        linha = ft.Row([nome_f, horas_f], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        linha.controls.append(ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Tirar", on_click=lambda e, l=linha: remover(l)))
        linhas.controls.append(linha)

    for n in iniciais:
        adicionar(n, por_disc if por_disc != int(por_disc) else int(por_disc))
    somar()

    def desenhar_dias():
        dias_linha.controls = [
            ft.Container(
                ft.Text(rk.DIAS_CURTOS[i], size=13.5, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if i in escolhidos else c["texto"]),
                bgcolor=c["tinta"] if i in escolhidos else c["sup2"],
                border_radius=18,
                padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                on_click=lambda e, i=i: alternar(i),
                ink=True,
            )
            for i in range(7)
        ]

    def alternar(i):
        escolhidos.symmetric_difference_update({i})
        desenhar_dias()
        app.page.update()

    desenhar_dias()

    def mais(e):
        usados = {(l.controls[0].value or "").strip().lower() for l in linhas.controls}
        nome = next((d for d in DISCIPLINAS_COMUNS if d.lower() not in usados), "")
        adicionar(nome, 1)
        somar()
        app.page.update()

    async def publicar(e):
        plano = {
            "disciplinas": [{"nome": l.controls[0].value or "", "horas": l.controls[1].value or ""} for l in linhas.controls],
            "dias": sorted(escolhidos),
            "semanas": (semanas.value or "0").strip() or 0,
            "concurso": concurso.value or "",
        }
        try:
            if not str(plano["semanas"]).isdigit():
                raise rk.ErroRanking("Em semanas, use só números (ou deixe vazio).")
            await app.em_segundo_plano(app.ranking.forum_publicar, g["codigo"], obs.value or "", "plano", titulo.value or "", plano)
        except rk.ErroRanking as ex:
            msg.content = comp.aviso(str(ex), c, "erro")
            app.page.update()
            return
        app.page.pop_dialog()
        app.msg("Plano compartilhado com o grupo.")
        ao_publicar()

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Compartilhar um plano de estudo", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado(f"Vai para o grupo {g['nome']}. Quem gostar pode usar o plano como meta da semana.", c, 13.5),
                    titulo,
                    ft.Row([concurso, semanas], spacing=8),
                    comp.texto("Dias de estudo", c, 14, peso=ft.FontWeight.W_600),
                    dias_linha,
                    ft.Row([comp.texto("Horas por semana em cada disciplina", c, 14, peso=ft.FontWeight.W_600), total], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                    linhas,
                    ft.Row([comp.botao_texto("Adicionar disciplina", mais, ft.Icons.ADD)]),
                    obs,
                    msg,
                ],
                tight=True,
                spacing=12,
                width=largura,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Publicar no grupo", publicar, ft.Icons.SEND_ROUNDED)],
        )
    )


# ---------------------------------------------------------------------- convidar por link


def dialogo_convidar(app, g: dict) -> None:
    """Link do grupo para mandar no WhatsApp, Telegram, e-mail, Instagram e TikTok (com imagem para Stories)."""
    from .. import convite

    c = app.c
    url = convite.link(g["codigo"], app.ranking.cfg)
    destinos = convite.links_compartilhar(g["nome"], url)
    largura = min(520, (app.page.width or 560) - 40)
    msg = ft.Container()

    async def copiar(texto: str, aviso: str):
        try:
            await ft.Clipboard().set(texto)
            app.msg(aviso)
        except Exception:  # noqa: BLE001
            app.msg(texto)

    async def salvar_imagem(e):
        pasta = Path(app.aj["pasta_downloads"] or Path.home() / "Downloads")
        nome_arq = f"convite-{g['codigo'].lower()}.png"
        try:
            caminho = await app.em_segundo_plano(convite.imagem_stories, g["nome"], g["codigo"], url, pasta / nome_arq)
        except Exception as ex:  # noqa: BLE001
            msg.content = comp.aviso(f"Não deu para criar a imagem: {ex}", c, "erro")
            app.page.update()
            return
        await copiar(url, "Link copiado também.")
        msg.content = comp.aviso(
            f"Imagem salva em {caminho}. Poste nos Stories ou no TikTok e cole o link (já copiado) no adesivo de link ou na legenda.",
            c,
            "ok",
            comp.botao_texto("Abrir pasta", lambda ev: _abrir_pasta(app, caminho.parent), ft.Icons.FOLDER_OPEN),
        )
        app.page.update()

    def botao_rede(rotulo: str, cor: str, icone, ao_clicar) -> ft.Control:
        return ft.Container(
            ft.Column(
                [
                    ft.Container(ft.Icon(icone, color="#FFFFFF", size=24), width=52, height=52, border_radius=26, bgcolor=cor, alignment=ft.Alignment.CENTER),
                    ft.Text(rotulo, size=12.5, color=c["texto"], text_align=ft.TextAlign.CENTER),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
            on_click=ao_clicar,
            ink=True,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=6, vertical=8),
            width=88,
        )

    redes = ft.Row(
        [
            botao_rede("WhatsApp", "#25D366", ft.Icons.CHAT, lambda e: app.page.run_task(app.abrir_url, destinos["whatsapp"])),
            botao_rede("Instagram", "#C13584", ft.Icons.CAMERA_ALT_OUTLINED, lambda e: app.page.run_task(salvar_imagem, e)),
            botao_rede("TikTok", "#111111", ft.Icons.MUSIC_NOTE, lambda e: app.page.run_task(salvar_imagem, e)),
            botao_rede("Telegram", "#229ED9", ft.Icons.SEND_ROUNDED, lambda e: app.page.run_task(app.abrir_url, destinos["telegram"])),
            botao_rede("E-mail", c["tinta"], ft.Icons.MAIL_OUTLINE, lambda e: app.page.run_task(app.abrir_url, destinos["email"])),
        ],
        wrap=True,
        spacing=4,
        run_spacing=4,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    campo_link = ft.TextField(value=url, read_only=True, dense=True, border_radius=10, expand=True, text_size=13.5)
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(f"Convidar para {g['nome']}", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado(
                        "Quem abrir o link vê o grupo e entra com um clique: o Aprova abre sozinho e não precisa digitar código nem fazer cadastro.",
                        c,
                        13.5,
                    ),
                    redes,
                    ft.Row(
                        [campo_link, ft.IconButton(ft.Icons.CONTENT_COPY, tooltip="Copiar link", on_click=lambda e: app.page.run_task(copiar, url, "Link copiado. Cole no WhatsApp, no direct, na bio…"))],
                        spacing=6,
                    ),
                    comp.botao_contorno(
                        "Copiar mensagem pronta",
                        lambda e: app.page.run_task(copiar, convite.mensagem(g["nome"], url), "Mensagem copiada. É só colar."),
                        ft.Icons.CONTENT_PASTE,
                    ),
                    comp.apagado(
                        "Instagram e TikTok não aceitam compartilhar direto do computador: o Aprova salva uma imagem com QR code para os Stories "
                        "e copia o link para você colar no adesivo de link, na bio ou no direct.",
                        c,
                        12,
                    ),
                    msg,
                ],
                tight=True,
                spacing=14,
                width=largura,
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
        )
    )


def _abrir_pasta(app, pasta: Path) -> None:
    import os
    import sys

    try:
        if sys.platform == "win32":
            os.startfile(str(pasta))  # noqa: S606
            return
    except OSError:
        pass
    app.page.run_task(app.abrir_url, pasta.as_uri())
