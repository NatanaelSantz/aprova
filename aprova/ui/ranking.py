"""Painel → Ranking: compare seu estudo da semana com outras pessoas."""

from __future__ import annotations

from datetime import timedelta

import flet as ft

from .. import ranking as rk
from . import comp, metas
from .personagem import busto
from .tema import FONTE_TITULO

MEDALHAS = {1: "#C98E12", 2: "#8A94A6", 3: "#A0612D"}


def _valor(metrica: str, l: dict) -> str:
    if metrica == "horas":
        return metas.fmt_hm_longo(l.get("segundos") or 0)
    if metrica == "questoes":
        return f"{l.get('questoes') or 0} questões"
    if metrica == "acerto":
        t = l.get("taxa")
        return "—" if t is None else f"{float(t) * 100:.0f}%"
    s = l.get("sequencia") or 0
    return f"{s} dia{'s' if s != 1 else ''}"


class SecaoRanking:
    def __init__(self, app, recarregar):
        self.app = app
        self.recarregar = recarregar  # redesenha o Painel
        self.metrica = "horas"
        self.grupo: str | None = None
        self.semana_passada = False
        self.linhas: list[dict] | None = None
        self.grupos: list[dict] = []
        self.erro: str | None = None
        self.carregando = False
        self.modo_form = "criar"

    @property
    def r(self) -> rk.Ranking:
        return self.app.ranking

    # ------------------------------------------------------------------ estados

    def build(self) -> ft.Control:
        c = self.app.c
        if not self.r.configurado:
            return self._nao_configurado()
        if not self.r.logado:
            return self._convite_entrar()
        if not self.r.apelido:
            return self._pedir_apelido()
        if self.linhas is None and not self.carregando and self.erro is None:
            self.app.page.run_task(self.carregar)
        return self._ranking(c)

    def _nao_configurado(self) -> ft.Control:
        app, c = self.app, self.app.c
        acao = comp.botao("Configurar servidor", lambda e: dialogo_servidor(app, self._depois_config), ft.Icons.SETTINGS_OUTLINED) if not app.modo_web else None
        return comp.vazio(
            ft.Icons.LEADERBOARD_OUTLINED,
            "Ranking entre estudantes",
            "Para comparar seu estudo com outras pessoas, o app precisa de um servidor na internet (grátis, no Supabase). "
            "Quem cuida do app configura uma vez: o passo a passo está no README, na parte “Ranking”.",
            c,
            acao,
        )

    def _depois_config(self):
        self.r.recarregar_config()
        self.recarregar()

    def _convite_entrar(self) -> ft.Control:
        app, c = self.app, self.app.c
        return comp.vazio(
            ft.Icons.EMOJI_EVENTS_OUTLINED,
            "Entre para ver o ranking",
            "Com uma conta você compara horas, questões e acerto da semana com outras pessoas e cria grupos com a sua turma. "
            "No ranking aparecem só o seu apelido e os números.",
            c,
            comp.botao("Entrar ou criar conta", lambda e: app.mostrar_login(), ft.Icons.LOGIN),
        )

    def _entrar(self) -> ft.Control:
        app, c = self.app, self.app.c
        criar = self.modo_form == "criar"
        apelido = ft.TextField(label="Apelido (aparece no ranking)", hint_text="Ex.: Natan_TI", dense=True, border_radius=10, max_length=24, visible=criar)
        concurso = ft.TextField(label="Concurso que você estuda (opcional)", hint_text="Ex.: Dataprev 2026", dense=True, border_radius=10, visible=criar)
        email = ft.TextField(label="E-mail", dense=True, border_radius=10, keyboard_type=ft.KeyboardType.EMAIL)
        senha = ft.TextField(label="Senha (mínimo 6)", password=True, can_reveal_password=True, dense=True, border_radius=10)
        aceite = ft.Checkbox(value=False)
        linha_aceite = ft.Row(
            [aceite, ft.Text("Aceito mostrar meu apelido e meus números de estudo da semana no ranking.", size=13.5, color=c["texto"], expand=True)],
            spacing=4,
            visible=criar,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        msg = ft.Container()

        def avisar(texto: str, tipo: str = "erro"):
            msg.content = comp.aviso(texto, c, tipo)
            msg.update()

        async def enviar(e):
            if criar and not aceite.value:
                avisar("Marque o aceite para entrar no ranking.", "alerta")
                return
            if not (email.value or "").strip() or not senha.value:
                avisar("Preencha e-mail e senha.", "alerta")
                return
            botao.disabled = True
            msg.content = comp.carregando("Conectando…", c)
            app.page.update()
            try:
                if criar:
                    res = await app.em_segundo_plano(self.r.criar_conta, email.value, senha.value, apelido.value or "", concurso.value or "")
                    if res == "confirmar":
                        self.modo_form = "entrar"
                        avisar("Conta criada! Abra o e-mail que enviamos, confirme e depois toque em Entrar.", "ok")
                        botao.disabled = False
                        app.page.update()
                        return
                else:
                    await app.em_segundo_plano(self.r.entrar, email.value, senha.value)
            except rk.ErroRanking as ex:
                botao.disabled = False
                avisar(str(ex))
                return
            self.linhas = None
            app.page.run_task(app.sincronizar_ranking)
            self.recarregar()

        async def esqueci(e):
            if not (email.value or "").strip():
                avisar("Digite seu e-mail acima e toque de novo em “Esqueci a senha”.", "alerta")
                return
            try:
                await app.em_segundo_plano(self.r.recuperar_senha, email.value)
                avisar("Se o e-mail tiver conta, chega uma mensagem para criar uma senha nova.", "ok")
            except rk.ErroRanking as ex:
                avisar(str(ex))

        def trocar(e):
            self.modo_form = e.control.selected[0]
            self.recarregar()

        botao = comp.botao("Criar conta e entrar" if criar else "Entrar", enviar, ft.Icons.LOGIN)
        form = comp.bloco(
            ft.Column(
                [
                    ft.SegmentedButton(
                        selected=[self.modo_form],
                        segments=[ft.Segment(value="criar", label=ft.Text("Criar conta")), ft.Segment(value="entrar", label=ft.Text("Já tenho conta"))],
                        show_selected_icon=False,
                        on_change=trocar,
                    ),
                    apelido,
                    concurso,
                    email,
                    senha,
                    linha_aceite,
                    msg,
                    ft.Row([botao] + ([] if criar else [comp.botao_texto("Esqueci a senha", esqueci)]), spacing=8, wrap=True),
                ],
                spacing=12,
            ),
            c,
            padding=20,
            col={"um": 12, "lado": 6},
        )
        por_que = ft.Container(
            ft.Column(
                [
                    ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, color=c["marca"], size=40),
                    ft.Text("Estude junto, mesmo de longe", size=22, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                    comp.apagado("Compare horas, questões, acerto e sequência da semana com outras pessoas, no geral ou num grupo só seu (a turma do concurso, os amigos do trabalho).", c, 14),
                    _item(c, ft.Icons.VISIBILITY_OUTLINED, "No ranking aparecem só o seu apelido e os números da semana. Seu e-mail fica escondido."),
                    _item(c, ft.Icons.LOCK_OUTLINE, "A senha não fica guardada no computador."),
                    _item(c, ft.Icons.DELETE_OUTLINE, "Você pode apagar a conta e os dados quando quiser, em Minha conta."),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            col={"um": 12, "lado": 6},
        )
        return ft.ResponsiveRow([por_que, form], spacing=24, run_spacing=20, breakpoints=comp.quebras(self.app, {"um": 0, "lado": 1100}))

    def _pedir_apelido(self) -> ft.Control:
        app, c = self.app, self.app.c
        apelido = ft.TextField(label="Apelido (aparece no ranking)", dense=True, border_radius=10, max_length=24)
        concurso = ft.TextField(label="Concurso que você estuda (opcional)", dense=True, border_radius=10)
        msg = ft.Container()

        async def salvar(e):
            try:
                await app.em_segundo_plano(self.r.salvar_perfil, apelido.value or "", concurso.value or "")
            except rk.ErroRanking as ex:
                msg.content = comp.aviso(str(ex), c, "erro")
                msg.update()
                return
            app.page.run_task(app.sincronizar_ranking)
            self.recarregar()

        return comp.bloco(
            ft.Column(
                [comp.subtitulo("Escolha seu apelido", c, 19), comp.apagado("É o nome que as outras pessoas veem no ranking.", c, 13.5), apelido, concurso, msg,
                 comp.botao("Salvar e ver o ranking", salvar, ft.Icons.CHECK)],
                spacing=12,
            ),
            c,
            padding=20,
        )

    # ------------------------------------------------------------------ ranking

    async def carregar(self, e=None):
        app = self.app
        self.carregando, self.erro = True, None
        self.recarregar()
        semana = rk.inicio_semana() - (timedelta(days=7) if self.semana_passada else timedelta(0))
        try:
            await app.em_segundo_plano(app.sincronizar_ranking_agora)
            self.grupos = await app.em_segundo_plano(self.r.meus_grupos)
            if self.grupo and self.grupo not in {g["codigo"] for g in self.grupos}:
                self.grupo = None
            self.linhas = await app.em_segundo_plano(self.r.ranking, self.metrica, semana, self.grupo)
        except rk.ErroRanking as ex:
            self.erro = str(ex)
            if not self.r.logado:
                self.linhas = None
        self.carregando = False
        self.recarregar()

    def _mudar(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.linhas = None
        self.app.page.run_task(self.carregar)

    def _ranking(self, c: dict) -> ft.Control:
        app = self.app
        metricas = ft.SegmentedButton(
            selected=[self.metrica],
            segments=[ft.Segment(value=k, label=ft.Text(v[1])) for k, v in rk.METRICAS.items()],
            show_selected_icon=False,
            on_change=lambda e: self._mudar(metrica=e.control.selected[0]),
        )
        escopo = ft.Dropdown(
            value=self.grupo or "geral",
            options=[ft.DropdownOption(key="geral", text="Geral")] + [ft.DropdownOption(key=g["codigo"], text=g["nome"]) for g in self.grupos],
            on_select=lambda e: self._mudar(grupo=None if e.control.value == "geral" else e.control.value),
            dense=True,
            border_radius=10,
            width=200,
        )
        semana = ft.SegmentedButton(
            selected=["passada" if self.semana_passada else "esta"],
            segments=[ft.Segment(value="esta", label=ft.Text("Esta semana")), ft.Segment(value="passada", label=ft.Text("Semana passada"))],
            show_selected_icon=False,
            on_change=lambda e: self._mudar(semana_passada=e.control.selected[0] == "passada"),
        )
        acoes = ft.Row(
            [
                ft.IconButton(ft.Icons.REFRESH, tooltip="Atualizar", on_click=lambda e: app.page.run_task(self.carregar)),
                comp.botao_contorno("Grupos", lambda e: dialogo_grupos(app, self), ft.Icons.GROUPS_OUTLINED),
                comp.botao_contorno("Minha conta", lambda e: dialogo_conta(app, self), ft.Icons.MANAGE_ACCOUNTS_OUTLINED),
            ],
            spacing=6,
            wrap=True,
        )
        controles = ft.Row([metricas, escopo, semana], spacing=10, wrap=True, run_spacing=10)
        filhos: list[ft.Control] = [ft.Row([self._cabecalho(c), acoes], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True, run_spacing=8), controles]
        if self.erro:
            filhos.append(comp.aviso(self.erro, c, "erro"))
        if self.carregando and self.linhas is None:
            filhos.append(comp.carregando("Buscando o ranking…", c))
        elif self.linhas is not None:
            filhos.append(self._lista(c))
        if self.metrica == "acerto":
            filhos.append(comp.apagado(f"No ranking de acerto entram só pessoas com {rk.MIN_QUESTOES_ACERTO} questões ou mais na semana.", c, 12.5))
        filhos.append(comp.apagado("Os números são enviados pelo próprio app de cada pessoa (horas estudadas, questões corrigidas, acerto e dias seguidos).", c, 12))
        return ft.Column(filhos, spacing=14)

    def _cabecalho(self, c: dict) -> ft.Control:
        eu = next((l for l in (self.linhas or []) if l.get("voce")), None)
        nome = rk.METRICAS[self.metrica][1].lower()
        if eu:
            texto = f"Você está em {eu['posicao']}º de {len(self.linhas or [])}"
            sub = f"em {nome}, {'na semana passada' if self.semana_passada else 'nesta semana'} · {_valor(self.metrica, eu)}"
        else:
            texto = f"Olá, {self.r.apelido}"
            sub = "Estude e resolva questões para aparecer no ranking." if self.metrica != "acerto" else f"Resolva {rk.MIN_QUESTOES_ACERTO} questões na semana para entrar no ranking de acerto."
        return ft.Column(
            [ft.Text(texto, size=22, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]), comp.apagado(sub, c, 13.5)],
            spacing=2,
        )

    def _lista(self, c: dict) -> ft.Control:
        linhas = self.linhas or []
        if not linhas:
            return comp.vazio(
                ft.Icons.LEADERBOARD_OUTLINED,
                "Ninguém no ranking ainda",
                "Os números aparecem assim que as pessoas estudam pelo app nesta semana. Crie um grupo e mande o código para os amigos.",
                c,
            )
        itens = []
        for l in linhas[:50]:
            itens.append(self._linha(c, l))
        eu = next((l for l in linhas if l.get("voce")), None)
        if eu and eu["posicao"] > 50:
            itens.append(ft.Container(comp.apagado("…", c, 14), padding=ft.Padding.only(left=24)))
            itens.append(self._linha(c, eu))
        return comp.bloco(ft.Column(itens, spacing=0), c, padding=6)

    def _linha(self, c: dict, l: dict) -> ft.Control:
        pos = l["posicao"]
        cor = MEDALHAS.get(pos)
        selo = ft.Container(
            ft.Text(str(pos), size=14, weight=ft.FontWeight.W_700, color="#FFFFFF" if cor else c["texto2"]),
            width=34,
            height=34,
            border_radius=17,
            bgcolor=cor or c["sup2"],
            alignment=ft.Alignment.CENTER,
        )
        detalhe = "   ".join(x for x in (l.get("concurso") or "", f"{l.get('dias') or 0} dias de estudo") if x)
        return ft.Container(
            ft.Row(
                [
                    selo,
                    busto(self.app, l.get("avatar"), l.get("apelido") or "?", 36, l.get("usuario_id")),
                    ft.Column(
                        [
                            ft.Row(
                                [ft.Text(l.get("apelido") or "—", size=15, weight=ft.FontWeight.W_600, color=c["texto"])]
                                + ([comp.pilula("você", c["tinta"], c["sobre_tinta"], tamanho=11)] if l.get("voce") else []),
                                spacing=8,
                            ),
                            comp.apagado(detalhe, c, 12.5, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.Text(_valor(self.metrica, l), size=17, weight=ft.FontWeight.W_700, color=c["tinta"] if l.get("voce") else c["texto"]),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=c["tinta_suave"] if l.get("voce") else None,
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        )


def _item(c: dict, icone, texto: str) -> ft.Control:
    return ft.Row([ft.Icon(icone, size=18, color=c["tinta"]), ft.Text(texto, size=13.5, color=c["texto"], expand=True)], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START)


# ---------------------------------------------------------------------- diálogos


def dialogo_grupos(app, secao: SecaoRanking) -> None:
    c = app.c
    lista = ft.Column(spacing=8)
    nome = ft.TextField(label="Nome do grupo", hint_text="Ex.: Turma Dataprev", dense=True, border_radius=10, expand=True)
    codigo = ft.TextField(label="Código do grupo", hint_text="Ex.: DATAPREV-7A2F", dense=True, border_radius=10, expand=True, capitalization=ft.TextCapitalization.CHARACTERS)
    msg = ft.Container()

    def desenhar():
        lista.controls = [
            ft.Row(
                [
                    ft.Icon(ft.Icons.GROUPS_OUTLINED, color=c["tinta"]),
                    ft.Column([comp.texto(g["nome"], c, 14.5, peso=ft.FontWeight.W_600), comp.apagado(f"código: {g['codigo']}", c, 12.5)], spacing=0, expand=True),
                    ft.IconButton(ft.Icons.CONTENT_COPY, tooltip="Copiar o código para mandar aos amigos", on_click=lambda e, g=g: app.page.run_task(_copiar, app, g["codigo"])),
                    ft.IconButton(ft.Icons.LOGOUT, tooltip="Sair do grupo", on_click=lambda e, g=g: app.page.run_task(sair, g["codigo"])),
                ],
                spacing=8,
            )
            for g in secao.grupos
        ] or [comp.apagado("Você ainda não está em nenhum grupo.", c, 13.5)]

    def avisar(texto, tipo="erro"):
        msg.content = comp.aviso(texto, c, tipo)
        app.page.update()

    async def criar(e):
        try:
            cod = await app.em_segundo_plano(secao.r.criar_grupo, nome.value or "")
        except rk.ErroRanking as ex:
            avisar(str(ex))
            return
        secao.grupos = await app.em_segundo_plano(secao.r.meus_grupos)
        nome.value = ""
        desenhar()
        avisar(f"Grupo criado! Mande o código {cod} para quem você quer no grupo.", "ok")

    async def entrar(e):
        try:
            g = await app.em_segundo_plano(secao.r.entrar_grupo, codigo.value or "")
        except rk.ErroRanking as ex:
            avisar(str(ex))
            return
        secao.grupos = await app.em_segundo_plano(secao.r.meus_grupos)
        codigo.value = ""
        desenhar()
        avisar(f"Você entrou no grupo {g['nome']}.", "ok")

    async def sair(cod):
        try:
            await app.em_segundo_plano(secao.r.sair_grupo, cod)
            secao.grupos = await app.em_segundo_plano(secao.r.meus_grupos)
        except rk.ErroRanking as ex:
            avisar(str(ex))
            return
        desenhar()
        app.page.update()

    def fechar(e):
        app.page.pop_dialog()
        secao.linhas = None
        app.page.run_task(secao.carregar)

    desenhar()
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Grupos", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado("Num grupo, o ranking mostra só quem está nele. Crie um e mande o código, ou entre com o código que te passaram.", c, 13.5),
                    lista,
                    comp.divisor(c),
                    ft.Row([codigo, comp.botao("Entrar", entrar, ft.Icons.LOGIN)], spacing=8),
                    ft.Row([nome, comp.botao_contorno("Criar", criar, ft.Icons.ADD)], spacing=8),
                    msg,
                ],
                tight=True,
                spacing=12,
                width=min(500, (app.page.width or 540) - 40),
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[ft.TextButton("Fechar", on_click=fechar)],
        )
    )


async def _copiar(app, texto: str) -> None:
    try:
        await ft.Clipboard().set(texto)
        app.msg(f"Código {texto} copiado.")
    except Exception:  # noqa: BLE001
        app.msg(f"Código do grupo: {texto}")


def dialogo_conta(app, secao: SecaoRanking) -> None:
    c = app.c
    apelido = ft.TextField(label="Apelido", value=secao.r.apelido, dense=True, border_radius=10, max_length=24)
    concurso = ft.TextField(label="Concurso", dense=True, border_radius=10)
    msg = ft.Container()

    async def carregar_perfil():
        try:
            p = await app.em_segundo_plano(secao.r.perfil)
            if p:
                concurso.value = p.get("concurso") or ""
                concurso.update()
        except rk.ErroRanking:
            pass

    async def salvar(e):
        try:
            await app.em_segundo_plano(secao.r.salvar_perfil, apelido.value or "", concurso.value or "")
        except rk.ErroRanking as ex:
            msg.content = comp.aviso(str(ex), c, "erro")
            msg.update()
            return
        app.page.pop_dialog()
        secao.linhas = None
        secao.recarregar()

    async def sair(e):
        await app.em_segundo_plano(secao.r.sair)
        app.page.pop_dialog()
        secao.linhas = None
        secao.recarregar()

    def apagar(e):
        async def confirmar(ev):
            try:
                await app.em_segundo_plano(secao.r.apagar_conta)
            except rk.ErroRanking as ex:
                app.page.pop_dialog()
                app.msg(str(ex))
                return
            app.page.pop_dialog()
            app.page.pop_dialog()
            app.msg("Sua conta e seus números do ranking foram apagados.")
            secao.linhas = None
            secao.recarregar()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Apagar sua conta?"),
                content=ft.Text("Seu apelido, seus números e seus grupos somem do ranking. Seus estudos neste computador continuam aqui.", size=14.5),
                actions=[ft.TextButton("Cancelar", on_click=lambda ev: app.page.pop_dialog()), ft.FilledButton("Apagar", on_click=confirmar, style=ft.ButtonStyle(bgcolor=c["erro"], color="#FFFFFF"))],
            )
        )

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Minha conta", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado(f"E-mail: {app.aj.get('ranking_email', '') or '—'} (não aparece para ninguém)", c, 13),
                    apelido,
                    concurso,
                    msg,
                    comp.divisor(c),
                    ft.Row([comp.botao_texto("Sair da conta", sair, ft.Icons.LOGOUT), comp.botao_texto("Apagar minha conta", apagar, ft.Icons.DELETE_OUTLINE)], wrap=True),
                ],
                tight=True,
                spacing=12,
                width=min(460, (app.page.width or 500) - 40),
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar", salvar, ft.Icons.CHECK)],
        )
    )
    app.page.run_task(carregar_perfil)


def dialogo_servidor(app, ao_salvar) -> None:
    """Endereço e chave pública do projeto Supabase (feito uma vez por quem cuida do app)."""
    c = app.c
    atual = rk.carregar_config()
    url = ft.TextField(label="Project URL", value=atual.get("url", ""), hint_text="https://xxxx.supabase.co", dense=True, border_radius=10)
    chave = ft.TextField(label="Chave publishable (ou anon)", value=atual.get("chave", ""), dense=True, border_radius=10, password=True, can_reveal_password=True)
    msg = ft.Container()

    def salvar(e):
        try:
            rk.salvar_config(url.value or "", chave.value or "")
        except rk.ErroRanking as ex:
            msg.content = comp.aviso(str(ex), c, "erro")
            msg.update()
            return
        app.page.pop_dialog()
        app.msg("Servidor do ranking salvo. Ele vai junto no .zip para os testadores.")
        ao_salvar()

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Servidor do ranking", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado(
                        "1. Crie um projeto grátis em supabase.com.  2. Em SQL Editor, rode o arquivo supabase/ranking.sql da pasta do app.  "
                        "3. No botão Connect do projeto (ou em Settings → API Keys), copie a Project URL e a chave publishable (ou anon) e cole aqui.",
                        c,
                        13,
                    ),
                    url,
                    chave,
                    msg,
                    comp.apagado("A chave anon é pública por natureza; quem protege os dados são as regras do ranking.sql. Nunca cole aqui a chave service_role.", c, 12),
                ],
                tight=True,
                spacing=12,
                width=min(500, (app.page.width or 540) - 40),
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar", salvar, ft.Icons.CHECK)],
        )
    )
