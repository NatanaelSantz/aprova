"""Tela de entrada (login / criar conta / usar sem conta) e a janela "Minha conta"."""

from __future__ import annotations

import flet as ft

from .. import ranking as rk
from . import comp
from .tema import FONTE_TITULO

QUEBRAS = {"um": 0, "dois": 960}


class TelaLogin:
    def __init__(self, app):
        self.app = app
        self.modo = "convite" if app.convite else "entrar"  # entrar | criar | convite
        self.msg = ft.Container()
        self._apelido_sugerido = rk.sugerir_apelido()

    @property
    def r(self) -> rk.Ranking:
        return self.app.ranking

    def _redesenhar(self):
        self.app.montar()

    # ------------------------------------------------------------------ layout

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        largo = app.largura >= QUEBRAS["dois"]
        cartao = self._cartao()
        if largo:
            return ft.Row(
                [
                    ft.Container(self._apresentacao(), expand=5, bgcolor=c["tinta"], padding=ft.Padding.symmetric(horizontal=56, vertical=48)),
                    ft.Container(
                        ft.Column(
                            [cartao],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            alignment=ft.MainAxisAlignment.CENTER,
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                        expand=6,
                        alignment=ft.Alignment.CENTER,
                        padding=ft.Padding.symmetric(horizontal=32, vertical=24),
                    ),
                ],
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        topo = ft.Row(
            [ft.Image(src="icon.png", width=46, height=46), ft.Text("Aprova", size=30, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=c["tinta"])],
            spacing=10,
        )
        return ft.Container(
            ft.Column(
                [topo, comp.apagado("Estudo para concursos, com suas provas, metas e ranking.", c, 14), cartao],
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=20),
            expand=True,
        )

    def _bolinhas(self, branco: str) -> ft.Control:
        """A, B, C, D, E do cartão-resposta, com a C marcada: a marca do Aprova."""
        tinta = "#2340A8"
        return ft.Row(
            [
                ft.Container(
                    ft.Text(letra, size=13, weight=ft.FontWeight.W_700, color=tinta if letra == "C" else branco),
                    width=30,
                    height=30,
                    shape=ft.BoxShape.CIRCLE,
                    bgcolor=branco if letra == "C" else None,
                    border=ft.Border.all(1.5, branco),
                    alignment=ft.Alignment.CENTER,
                    opacity=1 if letra == "C" else 0.75,
                )
                for letra in "ABCDE"
            ],
            spacing=10,
        )

    def _apresentacao(self) -> ft.Control:
        branco, suave = "#FFFFFF", "#D8DFF7"

        def item(icone, texto):
            return ft.Row([ft.Icon(icone, color=branco, size=22), ft.Text(texto, size=15, color=branco, expand=True)], spacing=12)

        conv = self.app.convite
        if conv:
            n = conv.get("membros") or 0
            return ft.Column(
                [
                    ft.Row(
                        [ft.Image(src="icon.png", width=56, height=56), ft.Text("Aprova", size=40, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=branco)],
                        spacing=14,
                    ),
                    ft.Container(height=24),
                    ft.Text("Você foi convidado para estudar junto", size=17, color=suave),
                    ft.Text(conv["nome"], size=34, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=branco),
                    ft.Text(f"{n} pessoa{'s' if n != 1 else ''} no grupo" if n else "Seja a primeira pessoa do grupo", size=15, color=suave),
                    ft.Container(height=16),
                    item(ft.Icons.FORUM_OUTLINED, "Conversa da turma, dúvidas e materiais"),
                    item(ft.Icons.EVENT_NOTE_OUTLINED, "Planos de estudo prontos para usar"),
                    item(ft.Icons.LEADERBOARD_OUTLINED, "Ranking só entre quem está no grupo"),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
            )

        return ft.Column(
            [
                ft.Row(
                    [ft.Image(src="icon.png", width=56, height=56), ft.Text("Aprova", size=40, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=branco)],
                    spacing=14,
                ),
                ft.Container(height=18),
                self._bolinhas(branco),
                ft.Text("Estude para o seu concurso com método.", size=28, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=branco),
                ft.Text("Provas reais, simulados, revisão no dia certo e metas da semana. Tudo no seu ritmo.", size=15, color=suave),
                ft.Container(height=16),
                item(ft.Icons.DESCRIPTION_OUTLINED, "Provas e gabaritos das bancas, prontos para resolver"),
                item(ft.Icons.INSIGHTS_OUTLINED, "Onde você está bem e onde precisa melhorar"),
                item(ft.Icons.LEADERBOARD_OUTLINED, "Ranking com quem estuda para o mesmo concurso"),
                item(ft.Icons.LOCK_OUTLINE, "Seus estudos separados da conta de outras pessoas neste computador"),
            ],
            spacing=12,
            alignment=ft.MainAxisAlignment.CENTER,
        )

    def _cartao(self) -> ft.Control:
        app, c = self.app, self.app.c
        if not self.r.configurado:
            return self._cartao_sem_servidor()
        if self.modo == "convite" and app.convite and not (self.r.logado and not self.r.apelido):
            return self._cartao_convite()
        criar = self.modo == "criar"
        apelido = ft.TextField(label="Apelido (aparece no ranking)", hint_text="Ex.: Natan_TI", max_length=24, border_radius=10, visible=criar)
        concurso = ft.TextField(label="Concurso que você estuda (opcional)", hint_text="Ex.: Dataprev 2026", border_radius=10, visible=criar)
        email = ft.TextField(label="E-mail", border_radius=10, keyboard_type=ft.KeyboardType.EMAIL, autofocus=True, value=self.r.email or None)
        senha = ft.TextField(label="Senha", password=True, can_reveal_password=True, border_radius=10)
        aceite = ft.Checkbox(value=False)
        linha_aceite = ft.Row(
            [aceite, ft.Text("Aceito mostrar meu apelido e meus números de estudo da semana no ranking.", size=13.5, color=c["texto"], expand=True)],
            spacing=4,
            visible=criar,
        )

        def avisar(texto: str, tipo: str = "erro"):
            self.msg.content = comp.aviso(texto, c, tipo)
            app.page.update()

        async def enviar(e=None):
            if not (email.value or "").strip() or not senha.value:
                avisar("Preencha e-mail e senha.", "alerta")
                return
            if criar and not aceite.value:
                avisar("Marque o aceite para criar a conta.", "alerta")
                return
            botao.disabled = True
            self.msg.content = comp.carregando("Conectando…", c)
            app.page.update()
            try:
                if criar:
                    res = await app.em_segundo_plano(self.r.criar_conta, email.value, senha.value, apelido.value or "", concurso.value or "")
                    if res == "confirmar":
                        self.modo = "entrar"
                        botao.disabled = False
                        avisar("Conta criada! Abra o e-mail que enviamos, confirme e depois entre aqui.", "ok")
                        return
                else:
                    perfil = await app.em_segundo_plano(self.r.entrar, email.value, senha.value)
                    if perfil is None:
                        # conta sem apelido: pede na tela de cadastro
                        self.modo = "criar"
                        self.msg.content = comp.aviso("Escolha um apelido para terminar sua conta.", c, "info")
                        self._redesenhar()
                        return
            except rk.ErroRanking as ex:
                botao.disabled = False
                avisar(str(ex))
                return
            self.msg.content = None
            await app.depois_do_login()

        async def esqueci(e):
            if not (email.value or "").strip():
                avisar("Digite seu e-mail acima e toque de novo em “Esqueci a senha”.", "alerta")
                return
            try:
                await app.em_segundo_plano(self.r.recuperar_senha, email.value)
                avisar("Se esse e-mail tiver conta, chega uma mensagem para criar uma senha nova.", "ok")
            except rk.ErroRanking as ex:
                avisar(str(ex))

        def trocar(e):
            self.modo = e.control.selected[0]
            self.msg.content = None
            self._redesenhar()

        senha.on_submit = enviar
        botao = ft.FilledButton(
            "Criar conta" if criar else "Entrar",
            icon=ft.Icons.PERSON_ADD_ALT if criar else ft.Icons.LOGIN,
            on_click=enviar,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding.symmetric(vertical=16)),
            expand=True,
        )
        if self.r.logado and not self.r.apelido:
            # entrou mas falta o apelido
            return self._cartao_apelido()
        return ft.Container(
            ft.Column(
                [
                    ft.Text("Criar sua conta" if criar else "Entrar", size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                    comp.apagado("Leva menos de um minuto. Com a conta você entra no ranking e guarda seus estudos separados." if criar else "Bem-vindo de volta! Entre para continuar de onde parou.", c, 14),
                    ft.SegmentedButton(
                        selected=[self.modo],
                        segments=[ft.Segment(value="entrar", label=ft.Text("Entrar")), ft.Segment(value="criar", label=ft.Text("Criar conta"))],
                        show_selected_icon=False,
                        on_change=trocar,
                    ),
                    apelido,
                    concurso,
                    email,
                    senha,
                    linha_aceite,
                    self.msg,
                    ft.Row([botao]),
                    comp.botao_texto("Esqueci a senha", esqueci) if not criar else ft.Container(),
                    ft.Row([ft.Container(comp.divisor(c), expand=True), comp.apagado("ou", c, 12.5), ft.Container(comp.divisor(c), expand=True)], spacing=10),
                    ft.OutlinedButton(
                        "Usar sem conta",
                        icon=ft.Icons.PERSON_OUTLINE,
                        on_click=lambda e: app.continuar_sem_conta(),
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding.symmetric(vertical=14)),
                    ),
                    comp.apagado("Sem conta, seus estudos ficam só neste computador e você não aparece no ranking. Dá para entrar depois.", c, 12.5),
                ]
                + ([comp.botao_texto(f"Voltar ao convite do grupo {app.convite['nome']}", lambda e: self._voltar_convite(), ft.Icons.ARROW_BACK)] if app.convite else []),
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=440,
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=18,
            padding=ft.Padding.symmetric(horizontal=28, vertical=28),
        )

    def _voltar_convite(self):
        self.modo = "convite"
        self.msg.content = None
        self._redesenhar()

    def _cartao_convite(self) -> ft.Control:
        """Convite aberto e sem conta: a pessoa só confirma o apelido e já entra no grupo."""
        app, c = self.app, self.app.c
        conv = app.convite
        apelido = ft.TextField(label="Seu apelido no grupo", value=self._apelido_sugerido, border_radius=10)

        async def entrar_rapido(e=None):
            botao.disabled = True
            self.msg.content = comp.carregando(f"Entrando no grupo {conv['nome']}…", c)
            app.page.update()
            try:
                await app.em_segundo_plano(self.r.entrar_rapido, apelido.value or self._apelido_sugerido)
            except rk.ErroRanking as ex:
                botao.disabled = False
                self.msg.content = comp.aviso(str(ex), c, "erro")
                app.page.update()
                return
            self.msg.content = None
            await app.depois_do_login()

        def com_email(modo: str):
            self.modo = modo
            self.msg.content = None
            self._redesenhar()

        def agora_nao(e):
            app.convite = None
            com_email("entrar")

        apelido.on_submit = entrar_rapido
        botao = ft.FilledButton(
            "Entrar no grupo",
            icon=ft.Icons.GROUP_ADD,
            on_click=entrar_rapido,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding.symmetric(vertical=18)),
        )
        n = conv.get("membros") or 0
        return ft.Container(
            ft.Column(
                [
                    ft.Row([comp.pilula("Convite", c["tinta_suave"], c["tinta"], ft.Icons.MAIL_OUTLINE)]),
                    ft.Text(f"Entrar no grupo {conv['nome']}", size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                    comp.apagado(
                        (f"{n} pessoa{'s' if n != 1 else ''} já estuda{'m' if n != 1 else ''} nesse grupo. " if n else "")
                        + "Não precisa de e-mail nem senha: confira o apelido e toque em Entrar.",
                        c,
                        14,
                    ),
                    apelido,
                    self.msg,
                    botao,
                    comp.apagado("Sua conta fica neste computador. Depois, se quiser, coloque e-mail e senha em Minha conta para entrar de outro lugar.", c, 12.5),
                    ft.Row([ft.Container(comp.divisor(c), expand=True), comp.apagado("já tem conta?", c, 12.5), ft.Container(comp.divisor(c), expand=True)], spacing=10),
                    ft.OutlinedButton(
                        "Entrar com e-mail e senha",
                        icon=ft.Icons.LOGIN,
                        on_click=lambda e: com_email("entrar"),
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding.symmetric(vertical=14)),
                    ),
                    comp.botao_texto("Agora não", agora_nao),
                ],
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=440,
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=18,
            padding=ft.Padding.symmetric(horizontal=28, vertical=28),
        )

    def _cartao_apelido(self) -> ft.Control:
        app, c = self.app, self.app.c
        apelido = ft.TextField(label="Apelido (aparece no ranking)", max_length=24, border_radius=10, autofocus=True)
        concurso = ft.TextField(label="Concurso que você estuda (opcional)", border_radius=10)

        async def salvar(e):
            try:
                await app.em_segundo_plano(self.r.salvar_perfil, apelido.value or "", concurso.value or "")
                await app.em_segundo_plano(self.r._depois_de_entrar)
            except rk.ErroRanking as ex:
                self.msg.content = comp.aviso(str(ex), c, "erro")
                app.page.update()
                return
            await app.depois_do_login()

        return ft.Container(
            ft.Column(
                [
                    ft.Text("Falta pouco", size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                    comp.apagado("Escolha o apelido que as outras pessoas vão ver no ranking.", c, 14),
                    apelido,
                    concurso,
                    self.msg,
                    comp.botao("Continuar", salvar, ft.Icons.ARROW_FORWARD),
                    comp.botao_texto("Sair desta conta", lambda e: app.sair_da_conta(), ft.Icons.LOGOUT),
                ],
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=440,
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=18,
            padding=28,
        )

    def _cartao_sem_servidor(self) -> ft.Control:
        app, c = self.app, self.app.c
        from .ranking import dialogo_servidor

        filhos: list[ft.Control] = [
            ft.Text("Bem-vindo ao Aprova", size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
            comp.apagado(
                "As contas online (ranking e área do administrador) ainda não foram ligadas neste app. "
                "Você já pode estudar normalmente: seus estudos ficam guardados neste computador.",
                c,
                14,
            ),
            ft.FilledButton(
                "Começar a estudar",
                icon=ft.Icons.ARROW_FORWARD,
                on_click=lambda e: app.continuar_sem_conta(),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding.symmetric(vertical=16)),
            ),
        ]
        if app.desktop:
            filhos += [
                comp.divisor(c),
                comp.apagado("É quem cuida do app? Ligue as contas com um projeto grátis do Supabase (passo a passo no README).", c, 12.5),
                comp.botao_texto(
                    "Ligar as contas online",
                    lambda e: dialogo_servidor(app, lambda: (app.ranking.recarregar_config(), app.montar())),
                    ft.Icons.SETTINGS_OUTLINED,
                ),
            ]
        return ft.Container(
            ft.Column(filhos, spacing=14, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            width=440,
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=18,
            padding=28,
        )


def dialogo_conta(app) -> None:
    """Minha conta: apelido, concurso, sair e apagar a conta."""
    c = app.c
    r = app.ranking
    apelido = ft.TextField(label="Apelido", value=r.apelido, dense=True, border_radius=10, max_length=24)
    concurso = ft.TextField(label="Concurso", dense=True, border_radius=10)
    msg = ft.Container()
    papel = "Administrador" if r.eh_admin else "Aluno"
    novo_email = ft.TextField(label="E-mail", dense=True, border_radius=10, keyboard_type=ft.KeyboardType.EMAIL, value=r.aj.get("ranking_email_pendente", "") or None)
    nova_senha = ft.TextField(label="Senha (mínimo 6)", dense=True, border_radius=10, password=True, can_reveal_password=True)
    msg_proteger = ft.Container()

    async def proteger(e):
        try:
            if r.aj.get("ranking_email_pendente", ""):
                res = await app.em_segundo_plano(r.criar_senha, nova_senha.value or "")
            else:
                res = await app.em_segundo_plano(r.proteger_conta, novo_email.value or "", nova_senha.value or "")
        except rk.ErroRanking as ex:
            msg_proteger.content = comp.aviso(str(ex), c, "erro")
            app.page.update()
            return
        if res == "ok":
            app.page.pop_dialog()
            app.msg("Conta protegida! Agora você entra com e-mail e senha em qualquer computador.")
            app.montar()
        else:
            msg_proteger.content = comp.aviso("Mandamos um e-mail de confirmação. Confirme e volte aqui para criar a senha.", c, "ok")
            app.page.update()

    bloco_proteger = (
        [
            comp.aviso("Conta rápida: ela vale só neste computador. Coloque e-mail e senha para não perder e entrar de outro lugar.", c, "alerta"),
            novo_email,
            nova_senha,
            msg_proteger,
            comp.botao("Proteger minha conta", proteger, ft.Icons.SHIELD_OUTLINED),
            comp.divisor(c),
        ]
        if r.eh_anonimo
        else []
    )

    async def carregar_perfil():
        try:
            p = await app.em_segundo_plano(r.atualizar_perfil)
            if p:
                concurso.value = p.get("concurso") or ""
                concurso.update()
        except rk.ErroRanking:
            pass

    async def salvar(e):
        try:
            await app.em_segundo_plano(r.salvar_perfil, apelido.value or "", concurso.value or "")
        except rk.ErroRanking as ex:
            msg.content = comp.aviso(str(ex), c, "erro")
            msg.update()
            return
        app.page.pop_dialog()
        app.msg("Conta atualizada.")
        app.montar()

    def sair(e):
        app.page.pop_dialog()
        app.sair_da_conta()

    def apagar(e):
        async def confirmar(ev):
            try:
                await app.em_segundo_plano(r.apagar_conta)
            except rk.ErroRanking as ex:
                app.page.pop_dialog()
                app.msg(str(ex))
                return
            app.page.pop_dialog()
            app.page.pop_dialog()
            app.msg("Sua conta foi apagada. Seus estudos neste computador continuam guardados.")
            app.sair_da_conta()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Apagar sua conta?"),
                content=ft.Text("Seu apelido, seus números do ranking e seus grupos são apagados do servidor. Os estudos neste computador continuam aqui.", size=14.5),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda ev: app.page.pop_dialog()),
                    ft.FilledButton("Apagar", on_click=confirmar, style=ft.ButtonStyle(bgcolor=c["erro"], color="#FFFFFF")),
                ],
            )
        )

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Minha conta", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.pilula(papel, c["tinta_suave"], c["tinta"], ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED if r.eh_admin else ft.Icons.SCHOOL_OUTLINED),
                    comp.apagado(f"E-mail: {r.email or '—'} (não aparece para ninguém)", c, 13),
                    *bloco_proteger,
                    apelido,
                    concurso,
                    msg,
                    comp.divisor(c),
                    ft.Row(
                        [comp.botao_texto("Sair / trocar de conta", sair, ft.Icons.LOGOUT), comp.botao_texto("Apagar minha conta", apagar, ft.Icons.DELETE_OUTLINE)],
                        wrap=True,
                    ),
                ],
                tight=True,
                spacing=12,
                width=min(460, (app.page.width or 500) - 40),
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar", salvar, ft.Icons.CHECK)],
        )
    )
    app.page.run_task(carregar_perfil)
