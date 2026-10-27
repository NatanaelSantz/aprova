"""Área do administrador: visão geral, usuários, grupos e comunicados."""

from __future__ import annotations

from datetime import datetime

import flet as ft

from .. import ranking as rk
from . import comp, metas
from .tema import FONTE_TITULO

ABAS = [("geral", "Visão geral"), ("usuarios", "Usuários"), ("grupos", "Grupos"), ("comunicados", "Comunicados"), ("config", "Configurações")]
QUEBRAS_NUM = {"um": 0, "tres": 1000}


def _data(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)[:10]


class TelaAdmin:
    def __init__(self, app):
        self.app = app
        self.aba = "geral"
        self.usuarios: list[dict] | None = None
        self.grupos: list[dict] | None = None
        self.comunicados: list[dict] | None = None
        self.filtro = ""
        self.erro: str | None = None
        self.carregando = False

    @property
    def r(self) -> rk.Ranking:
        return self.app.ranking

    def preparar(self, aba: str | None = None, **_):
        if aba in dict(ABAS):
            self.aba = aba

    def _redesenhar(self):
        self.app.recarregar_tela_sem_perder(self)

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        if not self.r.eh_admin:
            return comp.vazio(ft.Icons.LOCK_OUTLINE, "Área do administrador", "Só administradores veem esta tela.", c)
        abas = ft.SegmentedButton(
            selected=[self.aba],
            segments=[ft.Segment(value=k, label=ft.Text(v)) for k, v in ABAS],
            show_selected_icon=False,
            on_change=self._trocar,
        )
        titulo = ft.Column(
            [
                comp.titulo("Administração", c, 34 if app.largo else 28),
                comp.apagado(f"Você entrou como administrador ({self.r.apelido}).", c, 13.5),
            ],
            spacing=2,
        )
        atualizar = ft.IconButton(ft.Icons.REFRESH, tooltip="Atualizar", on_click=lambda e: app.page.run_task(self.carregar, True))
        topo = (
            ft.Row([titulo, ft.Container(expand=True), atualizar, abas], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            if app.modo_nav == "lateral"
            else ft.Column([ft.Row([titulo, ft.Container(expand=True), atualizar]), ft.Row([abas], scroll=ft.ScrollMode.AUTO)], spacing=10)
        )
        if self.usuarios is None and not self.carregando and self.erro is None:
            app.page.run_task(self.carregar)
        if self.erro:
            corpo: ft.Control = comp.aviso(self.erro, c, "erro", comp.botao_texto("Tentar de novo", lambda e: app.page.run_task(self.carregar, True)))
        elif self.usuarios is None:
            corpo = comp.carregando("Buscando os dados do servidor…", c)
        else:
            corpo = {"geral": self._geral, "usuarios": self._usuarios, "grupos": self._grupos, "comunicados": self._comunicados, "config": self._config}[self.aba]()
        return ft.Column([topo, ft.ListView([corpo, ft.Container(height=30)], expand=True)], spacing=16, expand=True)

    def _trocar(self, e):
        self.aba = e.control.selected[0] if e.control.selected else "geral"
        self._redesenhar()

    async def carregar(self, forcar: bool = False):
        app = self.app
        self.carregando, self.erro = True, None
        if forcar:
            self.usuarios = None
            self._redesenhar()
        try:
            await app.em_segundo_plano(self.r.atualizar_perfil)
            self.usuarios = await app.em_segundo_plano(self.r.usuarios)
            self.grupos = await app.em_segundo_plano(self.r.todos_grupos)
            self.comunicados = await app.em_segundo_plano(self.r.comunicados, True)
        except rk.ErroRanking as ex:
            self.erro = str(ex)
        self.carregando = False
        if not self.r.eh_admin:
            app.montar()  # perdeu o acesso de admin
            return
        self._redesenhar()

    # ------------------------------------------------------------------ visão geral

    def _numero(self, valor: str, rotulo: str, icone, cor: str | None = None) -> ft.Control:
        c = self.app.c
        return ft.Container(
            ft.Row(
                [
                    ft.Container(ft.Icon(icone, color=cor or c["tinta"], size=22), width=44, height=44, border_radius=22, bgcolor=c["tinta_suave"], alignment=ft.Alignment.CENTER),
                    ft.Column([comp.apagado(rotulo, c, 12.5), ft.Text(valor, size=24, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"])], spacing=0),
                ],
                spacing=12,
            ),
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=14,
            padding=ft.Padding.symmetric(horizontal=16, vertical=14),
            col={"um": 6, "tres": 4},
        )

    def _geral(self) -> ft.Control:
        c = self.app.c
        vg = self.r.visao_geral(self.usuarios or [])
        numeros = ft.ResponsiveRow(
            [
                self._numero(str(vg["usuarios"]), "Usuários", ft.Icons.GROUP_OUTLINED),
                self._numero(str(vg["ativos"]), "Estudaram nesta semana", ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED, c["marca"]),
                self._numero(str(vg["novos"]), "Novos nesta semana", ft.Icons.PERSON_ADD_ALT),
                self._numero(metas.fmt_hm_longo(vg["segundos"]), "Horas somadas na semana", ft.Icons.TIMER_OUTLINED),
                self._numero(str(vg["questoes"]), "Questões na semana", ft.Icons.TASK_ALT),
                self._numero("—" if vg["taxa"] is None else f"{vg['taxa'] * 100:.0f}%", "Acerto médio", ft.Icons.INSIGHTS_OUTLINED, c["ok"]),
            ],
            spacing=12,
            run_spacing=12,
            breakpoints=comp.quebras(self.app, QUEBRAS_NUM),
        )
        top = sorted(self.usuarios or [], key=lambda u: -u["segundos"])[:5]
        mais_ativos = comp.bloco(
            ft.Column(
                [comp.subtitulo("Mais ativos da semana", c, 17)]
                + [
                    ft.Row(
                        [
                            ft.Text(f"{i}º", size=14, weight=ft.FontWeight.W_700, color=c["tinta"], width=28),
                            ft.Text(u["apelido"], size=14.5, color=c["texto"], expand=True),
                            comp.apagado(f"{metas.fmt_hm_longo(u['segundos'])} · {u['questoes']} questões", c, 12.5),
                        ],
                        spacing=8,
                    )
                    for i, u in enumerate(top, start=1)
                    if u["segundos"] or u["questoes"]
                ]
                + ([comp.apagado("Ninguém estudou ainda nesta semana.", c, 13)] if not any(u["segundos"] or u["questoes"] for u in top) else []),
                spacing=10,
            ),
            c,
            padding=18,
            col={"um": 12, "tres": 6},
        )
        concursos = comp.bloco(
            ft.Column(
                [comp.subtitulo("Concursos mais estudados", c, 17)]
                + [
                    ft.Row([ft.Text(n, size=14.5, color=c["texto"], expand=True), comp.pilula(f"{q} pessoa{'s' if q != 1 else ''}", c["sup2"], c["texto2"], tamanho=11.5)], spacing=8)
                    for n, q in vg["concursos"]
                ]
                + ([comp.apagado("As pessoas ainda não informaram o concurso.", c, 13)] if not vg["concursos"] else []),
                spacing=10,
            ),
            c,
            padding=18,
            col={"um": 12, "tres": 6},
        )
        avisos = []
        if vg["bloqueados"]:
            avisos.append(comp.apagado(f"{vg['bloqueados']} usuário(s) bloqueado(s) no ranking.", c, 12.5))
        return ft.Column(
            [numeros, ft.ResponsiveRow([mais_ativos, concursos], spacing=14, run_spacing=14, breakpoints=comp.quebras(self.app, QUEBRAS_NUM))] + avisos,
            spacing=16,
        )

    # ------------------------------------------------------------------ usuários

    def _usuarios(self) -> ft.Control:
        app, c = self.app, self.app.c
        busca = ft.TextField(
            value=self.filtro,
            hint_text="Procurar por apelido ou concurso",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=10,
            on_change=lambda e: self._filtrar(e.control.value),
        )
        lista = ft.Column(spacing=0)
        self._lista_usuarios = lista
        self._preencher_usuarios()
        return ft.Column(
            [busca, comp.apagado(f"{len(self.usuarios or [])} usuários. Números desta semana.", c, 12.5), comp.bloco(lista, c, padding=6)],
            spacing=12,
        )

    def _filtrar(self, valor: str):
        self.filtro = valor or ""
        self._preencher_usuarios()
        try:
            self._lista_usuarios.update()
        except Exception:  # noqa: BLE001
            pass

    def _preencher_usuarios(self):
        c = self.app.c
        f = (self.filtro or "").lower().strip()
        itens = [u for u in (self.usuarios or []) if not f or f in u["apelido"].lower() or f in (u.get("concurso") or "").lower()]
        self._lista_usuarios.controls = [self._linha_usuario(u) for u in itens] or [comp.apagado("Ninguém encontrado.", c, 13)]

    def _linha_usuario(self, u: dict) -> ft.Control:
        app, c = self.app, self.app.c
        admin = u.get("papel") == "admin"
        from .. import avatar as av
        from .personagem import busto

        tem_foto = isinstance(u.get("avatar"), dict) and av.validar(u["avatar"])["foto"] > 0
        avatar = (
            busto(app, u.get("avatar"), u["apelido"], 36, u["id"])
            if isinstance(u.get("avatar"), dict) and not u.get("bloqueado")
            else ft.Container(
                ft.Text(u["apelido"][:1].upper(), size=15, weight=ft.FontWeight.W_700, color=c["sobre_tinta"]),
                width=36,
                height=36,
                border_radius=18,
                bgcolor=c["erro"] if u.get("bloqueado") else (c["tinta"] if admin else c["texto2"]),
                alignment=ft.Alignment.CENTER,
            )
        )
        selos: list[ft.Control] = []
        if admin:
            selos.append(comp.pilula("admin", c["tinta_suave"], c["tinta"], tamanho=11))
        if u.get("bloqueado"):
            selos.append(comp.pilula("bloqueado", c["erro_suave"], c["erro"], tamanho=11))
        if u.get("voce"):
            selos.append(comp.pilula("você", c["sup2"], c["texto2"], tamanho=11))
        info = ft.Column(
            [
                ft.Row([ft.Text(u["apelido"], size=15, weight=ft.FontWeight.W_600, color=c["texto"]), *selos], spacing=6, wrap=True),
                comp.apagado(
                    "   ".join(x for x in (u.get("concurso") or "", f"desde {_data(u.get('criado_em'))}", f"{metas.fmt_hm_longo(u['segundos'])} na semana", f"{u['questoes']} questões") if x),
                    c,
                    12.5,
                ),
            ],
            spacing=2,
            expand=True,
        )
        menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            tooltip="Ações",
            disabled=bool(u.get("voce")),
            items=[
                ft.PopupMenuItem(
                    content="Tirar de administrador" if admin else "Tornar administrador",
                    icon=ft.Icons.REMOVE_MODERATOR_OUTLINED if admin else ft.Icons.ADD_MODERATOR_OUTLINED,
                    on_click=lambda e, u=u: app.page.run_task(self._acao, "papel", u),
                ),
                ft.PopupMenuItem(
                    content="Desbloquear no ranking" if u.get("bloqueado") else "Bloquear no ranking",
                    icon=ft.Icons.LOCK_OPEN if u.get("bloqueado") else ft.Icons.BLOCK,
                    on_click=lambda e, u=u: app.page.run_task(self._acao, "bloqueio", u),
                ),
            ]
            + (
                [ft.PopupMenuItem(content="Tirar a foto de perfil", icon=ft.Icons.HIDE_IMAGE_OUTLINED, on_click=lambda e, u=u: app.page.run_task(self._acao, "foto", u))]
                if tem_foto
                else []
            ),
        )
        return ft.Container(
            ft.Row([avatar, info, menu], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
        )

    async def _acao(self, tipo: str, u: dict):
        app = self.app
        try:
            if tipo == "papel":
                novo = "aluno" if u.get("papel") == "admin" else "admin"
                await app.em_segundo_plano(self.r.definir_papel, u["id"], novo)
                app.msg(f"{u['apelido']} agora é {'administrador' if novo == 'admin' else 'aluno'}.")
            elif tipo == "foto":
                await app.em_segundo_plano(self.r.tirar_foto_de, u["id"])
                app.msg(f"A foto de perfil de {u['apelido']} foi apagada. O personagem continua.")
            else:
                await app.em_segundo_plano(self.r.bloquear, u["id"], not u.get("bloqueado"))
                app.msg(f"{u['apelido']} {'desbloqueado' if u.get('bloqueado') else 'bloqueado'} no ranking.")
        except rk.ErroRanking as ex:
            app.msg(str(ex))
            return
        self.usuarios = await app.em_segundo_plano(self.r.usuarios)
        self._redesenhar()

    # ------------------------------------------------------------------ grupos

    def _grupos(self) -> ft.Control:
        app, c = self.app, self.app.c
        grupos = self.grupos or []
        if not grupos:
            return comp.vazio(ft.Icons.GROUPS_OUTLINED, "Nenhum grupo ainda", "Os alunos criam grupos na tela Grupos.", c)
        linhas = []
        for g in grupos:
            linhas.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.GROUPS_OUTLINED, color=c["tinta"]),
                            ft.Column(
                                [ft.Text(g["nome"], size=15, weight=ft.FontWeight.W_600, color=c["texto"]),
                                 comp.apagado(f"código {g['codigo']}   {g['membros']} membro{'s' if g['membros'] != 1 else ''}   criado em {_data(g.get('criado_em'))}", c, 12.5)],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(ft.Icons.FORUM_OUTLINED, tooltip="Ver o fórum do grupo (você pode fixar e apagar mensagens)", on_click=lambda e, g=g: app.ir("grupos", codigo=g["codigo"])),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Apagar grupo", on_click=lambda e, g=g: self._confirmar_apagar_grupo(g)),
                        ],
                        spacing=12,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        return comp.bloco(ft.Column(linhas, spacing=0), c, padding=6)

    def _confirmar_apagar_grupo(self, g: dict):
        app = self.app

        async def apagar(e):
            app.page.pop_dialog()
            try:
                await app.em_segundo_plano(self.r.apagar_grupo, g["codigo"])
                self.grupos = await app.em_segundo_plano(self.r.todos_grupos)
            except rk.ErroRanking as ex:
                app.msg(str(ex))
                return
            app.msg(f"Grupo {g['nome']} apagado.")
            self._redesenhar()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Apagar o grupo {g['nome']}?"),
                content=ft.Text("Os membros saem do grupo e o fórum dele é apagado. As contas e os números de cada pessoa continuam.", size=14.5),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), ft.FilledButton("Apagar", on_click=apagar)],
            )
        )

    # ------------------------------------------------------------------ comunicados

    def _config(self) -> ft.Control:
        """Chave do GIPHY (busca de GIFs e figurinhas animadas nos grupos)."""
        app, c = self.app, self.app.c
        atual = self.r._giphy or ""
        campo = ft.TextField(
            label="Chave da API do GIPHY",
            value=atual,
            password=True,
            can_reveal_password=True,
            dense=True,
            border_radius=10,
            expand=True,
        )

        async def carregar_atual():
            valor = await app.em_segundo_plano(self.r.chave_giphy)
            if valor and not campo.value:
                campo.value = valor
                try:
                    campo.update()
                except Exception:  # noqa: BLE001
                    pass

        async def salvar(e):
            try:
                await app.em_segundo_plano(self.r.config_salvar, "giphy", campo.value or "")
            except rk.ErroRanking as ex:
                app.msg(str(ex))
                return
            self.r._giphy = (campo.value or "").strip() or None
            app.msg("Chave salva. A busca de GIFs já funciona para todo mundo." if self.r._giphy else "Chave removida: a busca de GIFs foi desligada.")

        if not self.r._giphy:
            app.page.run_task(carregar_atual)
        passos = ft.Column(
            [
                comp.texto("Como pegar a chave (grátis, uns 3 minutos):", c, 14, peso=ft.FontWeight.W_600),
                comp.apagado("1. Entre em developers.giphy.com e crie uma conta (ou entre na sua).", c, 13.5),
                comp.apagado("2. Clique em Create an API Key, escolha API (não SDK), dê o nome Aprova e aceite os termos.", c, 13.5),
                comp.apagado("3. Copie a API Key que aparece e cole aqui.", c, 13.5),
                comp.botao_texto("Abrir developers.giphy.com", url="https://developers.giphy.com/dashboard/", icone=ft.Icons.OPEN_IN_NEW),
            ],
            spacing=4,
        )
        return comp.bloco(
            ft.Column(
                [
                    comp.subtitulo("Busca de GIFs nos grupos", c, 18),
                    comp.apagado(
                        "As figurinhas do Aprova e o envio de fotos e arquivos funcionam sem nada. Para buscar GIFs e figurinhas animadas, "
                        "o Aprova usa o GIPHY, que pede uma chave. Ela vale para todos e fica guardada no servidor; só administradores mudam.",
                        c,
                        13.5,
                    ),
                    ft.Row([campo, comp.botao("Salvar", salvar, ft.Icons.SAVE_OUTLINED)], spacing=10),
                    passos,
                ],
                spacing=12,
            ),
            c,
            padding=20,
        )

    def _comunicados(self) -> ft.Control:
        app, c = self.app, self.app.c
        titulo = ft.TextField(label="Título", hint_text="Ex.: Simulado coletivo no sábado", max_length=80, dense=True, border_radius=10)
        texto = ft.TextField(label="Mensagem", hint_text="Aparece na tela Início de todos que têm conta.", multiline=True, min_lines=3, max_lines=6, max_length=1000, border_radius=10)

        async def publicar(e):
            try:
                await app.em_segundo_plano(self.r.criar_comunicado, titulo.value or "", texto.value or "")
                self.comunicados = await app.em_segundo_plano(self.r.comunicados, True)
            except rk.ErroRanking as ex:
                app.msg(str(ex))
                return
            app.msg("Comunicado publicado.")
            self._redesenhar()

        form = comp.bloco(
            ft.Column([comp.subtitulo("Novo comunicado", c, 17), titulo, texto, ft.Row([comp.botao("Publicar", publicar, ft.Icons.CAMPAIGN_OUTLINED)])], spacing=10),
            c,
            padding=18,
        )
        linhas: list[ft.Control] = []
        for m in self.comunicados or []:
            linhas.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(m["titulo"], size=15, weight=ft.FontWeight.W_600, color=c["texto"] if m["ativo"] else c["texto2"]),
                                    comp.apagado(m["texto"], c, 13, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                                    comp.apagado(f"{_data(m.get('criado_em'))} · {'aparecendo para todos' if m['ativo'] else 'escondido'}", c, 12),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            ft.Switch(value=bool(m["ativo"]), tooltip="Mostrar para todos", on_change=lambda e, m=m: app.page.run_task(self._ativar, m, e.control.value)),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Apagar", on_click=lambda e, m=m: app.page.run_task(self._apagar_comunicado, m)),
                        ],
                        spacing=10,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        lista = comp.bloco(ft.Column(linhas, spacing=0), c, padding=6) if linhas else comp.apagado("Nenhum comunicado ainda.", c, 13)
        return ft.Column([form, comp.subtitulo("Publicados", c, 17), lista], spacing=14)

    async def _ativar(self, m: dict, valor: bool):
        try:
            await self.app.em_segundo_plano(self.r.ativar_comunicado, m["id"], bool(valor))
            self.comunicados = await self.app.em_segundo_plano(self.r.comunicados, True)
        except rk.ErroRanking as ex:
            self.app.msg(str(ex))
        self._redesenhar()

    async def _apagar_comunicado(self, m: dict):
        try:
            await self.app.em_segundo_plano(self.r.apagar_comunicado, m["id"])
            self.comunicados = await self.app.em_segundo_plano(self.r.comunicados, True)
        except rk.ErroRanking as ex:
            self.app.msg(str(ex))
        self._redesenhar()
