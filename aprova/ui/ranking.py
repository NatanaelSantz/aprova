"""Painel → Ranking: compare seu estudo da semana, do mês ou de sempre com outras pessoas."""

from __future__ import annotations

import flet as ft

from .. import ranking as rk
from . import comp, metas, movimento
from .personagem import busto
from .tema import FONTE_TITULO

MEDALHAS = {1: "#C98E12", 2: "#8A94A6", 3: "#A0612D"}


def _alfa(cor: str, a: float) -> str:
    """Cor #RRGGBB com transparência (o Flutter lê #AARRGGBB)."""
    return f"#{int(a * 255):02X}{cor[1:]}"


# como cada período aparece na frase "Você está em 3º … nesta semana"
NO_PERIODO = {"semana": "nesta semana", "passada": "na semana passada", "mes": "neste mês", "sempre": "desde o começo"}
LONGO = ("mes", "sempre")  # períodos que somam várias semanas


def _nome_metrica(metrica: str, periodo: str) -> str:
    if metrica == "sequencia" and periodo in LONGO:
        return "Maior sequência"
    return rk.METRICAS[metrica][1]


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
        self.periodo = "semana"  # semana, passada, mes ou sempre (rk.PERIODOS)
        self.linhas: list[dict] | None = None
        self.anteriores: dict[str, int] | None = None  # posição de cada pessoa no período anterior (setas de subiu/desceu)
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
                    _item(c, ft.Icons.LOCK_OUTLINE, f"A senha não fica guardada no {comp.aparelho()}."),
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
        try:
            await app.em_segundo_plano(app.sincronizar_ranking_agora)
            self.grupos = await app.em_segundo_plano(self.r.meus_grupos)
            if self.grupo and self.grupo not in {g["codigo"] for g in self.grupos}:
                self.grupo = None
            self.linhas = await app.em_segundo_plano(lambda: self.r.ranking(self.metrica, grupo=self.grupo, periodo=self.periodo))
            anterior = "passada" if self.periodo == "semana" else None  # setas: só semana contra semana passada
            if anterior and self.linhas:
                try:
                    antes = await app.em_segundo_plano(lambda: self.r.ranking(self.metrica, grupo=self.grupo, periodo=anterior))
                    self.anteriores = {l["usuario_id"]: l["posicao"] for l in antes}
                except rk.ErroRanking:
                    self.anteriores = None
        except rk.ErroRanking as ex:
            self.erro = str(ex)
            if not self.r.logado:
                self.linhas = None
        self.carregando = False
        movimento.abrir_janela(app, 1.0)  # a lista chega com as linhas entrando uma depois da outra
        self.recarregar()

    def _mudar(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.linhas = None
        self.anteriores = None
        self.app.page.run_task(self.carregar)

    # ------------------------------------------------------------------ a tela (1.31: pódio, seu cartão e lista com barras)

    def _ranking(self, c: dict) -> ft.Control:
        app = self.app
        filhos: list[ft.Control] = [self._filtros(c)]
        if self.erro:
            filhos.append(comp.aviso(self.erro, c, "erro"))
        if self.carregando and self.linhas is None:
            filhos.append(movimento.esqueleto(self.app, c, 5))
        elif self.linhas is not None:
            linhas = self.linhas
            filhos.append(movimento.entrada(app, self._podio(c), forcar=True))
            filhos.append(self._lista(c))
        notas = []
        if self.metrica == "acerto":
            notas.append(f"No acerto entram só pessoas com {rk.MIN_ACERTO[self.periodo]} questões ou mais {self._no_periodo()}.")
        if self.periodo in LONGO:
            notas.append(("Este mês soma as semanas que passam por ele. " if self.periodo == "mes" else "Desde o começo soma todas as semanas. ")
                         + "Na sequência vale a maior do período.")
        notas.append("Os números vêm do app de cada pessoa; aparecem só o apelido e o estudo.")
        filhos.append(comp.apagado(" ".join(notas), c, 12))
        return ft.Column(filhos, spacing=14)

    def _filtros(self, c: dict) -> ft.Control:
        """Uma linha: o que comparar (abas). Outra: com quem (Geral/grupo), quando (período) e os botões."""
        app = self.app
        metricas = comp.abas_chips([(k, _nome_metrica(k, self.periodo)) for k in rk.METRICAS], self.metrica, lambda m: self._mudar(metrica=m), c)
        larg_cel = max(150, min(200, ((app.largura_conteudo or 360) - 12) / 2))  # celular: os dois menus dividem a linha
        escopo = ft.Dropdown(
            value=self.grupo or "geral",
            options=[ft.DropdownOption(key="geral", text="Todo mundo")] + [ft.DropdownOption(key=g["codigo"], text=g["nome"]) for g in self.grupos],
            on_select=lambda e: self._mudar(grupo=None if e.control.value == "geral" else e.control.value),
            dense=True,
            border_radius=10,
            width=190 if app.largo else larg_cel,
            leading_icon=ft.Icons.GROUPS_OUTLINED if app.largo else None,
        )
        periodo = ft.Dropdown(
            value=self.periodo,
            options=[ft.DropdownOption(key=k, text=v) for k, v in rk.PERIODOS.items()],
            on_select=lambda e: self._mudar(periodo=e.control.value),
            dense=True,
            border_radius=10,
            width=190 if app.largo else larg_cel,
            leading_icon=ft.Icons.CALENDAR_TODAY_OUTLINED if app.largo else None,
        )
        botoes = ft.Row(
            [
                ft.IconButton(ft.Icons.REFRESH, tooltip="Atualizar", on_click=lambda e: app.page.run_task(self.carregar)),
                ft.IconButton(ft.Icons.GROUP_ADD_OUTLINED, tooltip="Grupos: criar ou entrar com código", on_click=lambda e: dialogo_grupos(app, self)),
                ft.IconButton(ft.Icons.MANAGE_ACCOUNTS_OUTLINED, tooltip="Minha conta", on_click=lambda e: dialogo_conta(app, self)),
            ],
            spacing=0,
            tight=True,
        )
        linha2 = ft.Row([escopo, periodo, botoes], spacing=10, wrap=True, run_spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.Column([metricas, linha2], spacing=10)

    def _no_periodo(self) -> str:
        return {"semana": "na semana", "passada": "na semana", "mes": "no mês", "sempre": "no total"}[self.periodo]

    def _numero(self, l: dict) -> float:
        """O valor bruto da métrica atual (para barras e diferenças)."""
        if self.metrica == "horas":
            return float(l.get("segundos") or 0)
        if self.metrica == "questoes":
            return float(l.get("questoes") or 0)
        if self.metrica == "acerto":
            return float(l.get("taxa") or 0)
        return float(l.get("sequencia") or 0)

    def _diferenca(self, quanto: float) -> str:
        if self.metrica == "horas":
            return metas.fmt_hm_longo(int(quanto))
        if self.metrica == "questoes":
            return f"{int(quanto)} questões"
        if self.metrica == "acerto":
            return f"{quanto * 100:.0f} pontos de acerto"
        return f"{int(quanto)} dia{'s' if int(quanto) != 1 else ''}"

    def _variacao(self, l: dict) -> int | None:
        """Quantas posições subiu (+) ou desceu (−) em relação ao período anterior; None se não dá para saber."""
        if not self.anteriores or l.get("usuario_id") not in self.anteriores:
            return None
        return self.anteriores[l["usuario_id"]] - l["posicao"]

    def _seta(self, c: dict, l: dict) -> ft.Control:
        v = self._variacao(l)
        if v is None or v == 0:
            return ft.Container(width=34)
        cor = c["ok"] if v > 0 else c["erro"]
        return ft.Row(
            [ft.Icon(ft.Icons.ARROW_DROP_UP if v > 0 else ft.Icons.ARROW_DROP_DOWN, size=20, color=cor), ft.Text(str(abs(v)), size=12, color=cor, weight=ft.FontWeight.W_700)],
            spacing=0,
            tight=True,
            width=34,
        )

    def _frase_minha(self, eu: dict | None) -> str:
        """'Faltam 1h32 para passar Pedro M. Subiu 2 posições desde a semana passada.'"""
        linhas = self.linhas or []
        if not eu:
            return ("Estude e resolva questões pelo app para entrar no ranking." if self.metrica != "acerto"
                    else f"Resolva {rk.MIN_ACERTO[self.periodo]} questões {self._no_periodo()} para entrar no ranking de acerto.")
        pos = eu["posicao"]
        partes = []
        if pos > 1:
            acima = next(l for l in linhas if l["posicao"] == pos - 1)
            falta = self._numero(acima) - self._numero(eu)
            if falta > 0:
                partes.append(f"Faltam {self._diferenca(falta)} para passar {acima.get('apelido') or 'quem está na frente'}.")
        else:
            partes.append("Você está na frente de todo mundo.")
        v = self._variacao(eu)
        if v is not None and self.periodo == "semana":
            partes.append(f"Subiu {v} posição{'ões' if v != 1 else ''} desde a semana passada." if v > 0 else
                          f"Desceu {-v} posição{'ões' if v != -1 else ''} desde a semana passada." if v < 0 else "Mesma posição da semana passada.")
        elif self.anteriores is not None and self.periodo == "semana":
            partes.append("Você não estava no ranking na semana passada.")
        return " ".join(partes)

    def _meu_cartao(self, c: dict) -> ft.Control:
        """Sua posição e quanto falta para subir (vai dentro do cartão escuro, abaixo do pódio)."""
        linhas = self.linhas or []
        eu = next((l for l in linhas if l.get("voce")), None)
        nome = _nome_metrica(self.metrica, self.periodo).lower()
        branco, claro = "#FFFFFF", "#C9D3F2"
        if not eu:
            titulo, valor = f"Olá, {self.r.apelido}", ""
        else:
            titulo, valor = f"Você está em {eu['posicao']}º de {len(linhas)}", _valor(self.metrica, eu)
        pos = eu["posicao"] if eu else None
        selo = ft.Container(
            ft.Text(f"{pos}º" if pos else "—", size=18, weight=ft.FontWeight.W_800, color="#14213D" if pos and pos <= 3 else branco),
            width=48, height=48, border_radius=24, bgcolor=MEDALHAS.get(pos, _alfa("#FFFFFF", 0.14)) if pos else _alfa("#FFFFFF", 0.14), alignment=ft.Alignment.CENTER,
        )
        return ft.Container(
            ft.Row(
                [
                    *([selo] if self.app.largo else []),
                    busto(self.app, eu.get("avatar") if eu else None, (eu or {}).get("apelido") or self.r.apelido or "?", 40, self.r.usuario_id),
                    ft.Column(
                        [ft.Text(titulo, size=16 if self.app.largo else 15, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=branco),
                         ft.Text(self._frase_minha(eu), size=12.5, color=claro, max_lines=3)],
                        spacing=1,
                        expand=True,
                    ),
                    *([ft.Column([ft.Text(valor, size=20, weight=ft.FontWeight.W_800, color="#FFD36B"), ft.Text(nome, size=11, color=claro)],
                                 spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END)] if valor else []),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=_alfa("#FFFFFF", 0.08),
            border=ft.Border.all(1, _alfa("#FFFFFF", 0.14)),
            border_radius=14,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        )

    def _podio(self, c: dict) -> ft.Control:
        """O cartão escuro: os três primeiros no pódio (o 1º no meio, mais alto e com coroa) e, embaixo, o seu cartão."""
        app = self.app
        linhas = self.linhas or []
        top = {l["posicao"]: l for l in linhas[:3]}
        branco, claro, ouro = "#FFFFFF", "#C9D3F2", "#FFD36B"
        estreito = not app.largo

        def lugar(pos: int) -> ft.Control:
            l = top.get(pos)
            alt = {1: 92, 2: 64, 3: 46}[pos]
            tam = {1: 72, 2: 56, 3: 56}[pos] if not estreito else {1: 60, 2: 48, 3: 48}[pos]
            cor = MEDALHAS[pos]
            if not l:
                return ft.Container(expand=True)
            rosto = ft.Container(
                busto(app, l.get("avatar"), l.get("apelido") or "?", tam, l.get("usuario_id")),
                border=ft.Border.all(3, cor), border_radius=tam, padding=2,
                shadow=ft.BoxShadow(blur_radius=18, color=_alfa(cor, 0.4)) if pos == 1 else None,
            )
            topo: list[ft.Control] = [ft.Icon(ft.Icons.WORKSPACE_PREMIUM, color=ouro, size=24)] if pos == 1 else [ft.Container(height=24)]
            return ft.Column(
                topo + [
                    rosto,
                    ft.Text(l.get("apelido") or "—", size=14 if pos == 1 else 13, weight=ft.FontWeight.W_700, color=branco, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER),
                    ft.Text(_valor(self.metrica, l), size=15 if pos == 1 else 13, weight=ft.FontWeight.W_700, color=ouro if pos == 1 else claro,
                            text_align=ft.TextAlign.CENTER),
                    ft.Container(
                        ft.Text(f"{pos}º", size=18, weight=ft.FontWeight.W_800, color=branco),
                        height=alt, border_radius=ft.BorderRadius.only(top_left=12, top_right=12), alignment=ft.Alignment.TOP_CENTER,
                        padding=ft.Padding.only(top=8),
                        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER, colors=[cor, _alfa(cor, 0.2)]),
                    ),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.END,
                expand=True,
            )

        cabecalho = ft.Row(
            [
                ft.Icon(ft.Icons.EMOJI_EVENTS, color=ouro, size=20),
                ft.Text(f"{_nome_metrica(self.metrica, self.periodo)} · {rk.PERIODOS[self.periodo]}", size=13.5, weight=ft.FontWeight.W_700, color=branco),
                ft.Container(expand=True),
                ft.Text(next((g["nome"] for g in self.grupos if g["codigo"] == self.grupo), "Todo mundo"), size=12.5, color=claro),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        partes: list[ft.Control] = [cabecalho]
        if len(linhas) >= 3:
            podio = ft.Row([lugar(2), lugar(1), lugar(3)], spacing=8, vertical_alignment=ft.CrossAxisAlignment.END)
            partes.append(ft.Container(podio, width=min(560, max(280, (app.largura_conteudo or 600) - 60)), alignment=ft.Alignment.BOTTOM_CENTER))
        partes.append(self._meu_cartao(c))
        return ft.Container(
            ft.Column(partes, spacing=14, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT, colors=["#14213D", "#2340A8"]),
            border_radius=20,
            padding=ft.Padding.only(left=16, right=16, top=14, bottom=14),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    def _lista(self, c: dict) -> ft.Control:
        linhas = self.linhas or []
        if not linhas:
            return comp.vazio(
                ft.Icons.LEADERBOARD_OUTLINED,
                "Ninguém no ranking ainda",
                f"Os números aparecem assim que as pessoas estudam pelo app {NO_PERIODO[self.periodo]}. Crie um grupo e mande o código para os amigos."
                if self.periodo != "sempre" else "Os números aparecem assim que as pessoas estudam pelo app. Crie um grupo e mande o código para os amigos.",
                c,
            )
        lider = self._numero(linhas[0]) or 1.0
        inicio = 3 if len(linhas) >= 3 else 0  # com pódio, a lista começa do 4º
        itens = [self._linha(c, l, lider) for l in linhas[inicio:50]]
        if not itens:
            return ft.Container()
        itens = movimento.cascata(self.app, itens[:12], dy=0.25) + itens[12:]
        eu = next((l for l in linhas if l.get("voce")), None)
        if eu and eu["posicao"] > 50:
            itens.append(ft.Container(comp.apagado("…", c, 14), padding=ft.Padding.only(left=24)))
            itens.append(self._linha(c, eu, lider))
        return comp.bloco(ft.Column(itens, spacing=0), c, padding=6)

    def _barra(self, c: dict, fracao: float, voce: bool, animar: bool) -> ft.Control:
        """Barra fina com degradê (a de quem lidera vai até o fim)."""
        cores = ["#2340A8", "#5B7BE8"]
        cheio = ft.Container(
            height=6, border_radius=3, expand=max(1, int(round(fracao * 1000))),
            gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT, colors=cores if voce else [_alfa(c["tinta"], 0.6), c["tinta"]]),
        )
        vazio = ft.Container(height=6, expand=max(1, int(round((1 - fracao) * 1000))))
        if animar and fracao > 0:
            cheio = movimento.crescer(self.app, cheio)
        return ft.Container(ft.Row([cheio, vazio], spacing=0), bgcolor=c["sup2"], border_radius=3, height=6, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)

    def _linha(self, c: dict, l: dict, lider: float | None = None) -> ft.Control:
        pos = l["posicao"]
        cor = MEDALHAS.get(pos)
        lider = lider or (self._numero(self.linhas[0]) if self.linhas else 0) or 1.0
        selo = ft.Container(
            ft.Text(str(pos), size=15, weight=ft.FontWeight.W_800, color="#FFFFFF" if cor else c["texto2"]),
            width=34, height=34, border_radius=17, bgcolor=cor, alignment=ft.Alignment.CENTER,
            border=None if cor else ft.Border.all(1.5, c["borda"]),
        )
        dias = l.get("dias") or 0
        detalhe = " · ".join(x for x in (l.get("concurso") or "", f"{dias} dia{'s' if dias != 1 else ''} de estudo") if x)
        fracao = max(0.0, min(1.0, self._numero(l) / lider)) if lider else 0.0
        return ft.Container(
            ft.Row(
                [
                    selo,
                    busto(self.app, l.get("avatar"), l.get("apelido") or "?", 36, l.get("usuario_id")),
                    ft.Column(
                        [
                            ft.Row(
                                [ft.Text(l.get("apelido") or "—", size=15, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
                                + ([comp.pilula("você", c["tinta"], c["sobre_tinta"], tamanho=11)] if l.get("voce") else [])
                                + ([ft.Container(expand=True), comp.apagado(detalhe, c, 12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)] if self.app.largo and detalhe else []),
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            self._barra(c, fracao, bool(l.get("voce")), animar=pos <= 15),
                        ],
                        spacing=5,
                        expand=True,
                    ),
                    self._seta(c, l),
                    ft.Text(_valor(self.metrica, l), size=16, weight=ft.FontWeight.W_700, color=c["tinta"] if l.get("voce") else c["texto"], width=118 if self.app.largo else None,
                            text_align=ft.TextAlign.RIGHT, max_lines=1, no_wrap=True),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=c["tinta_suave"] if l.get("voce") else None,
            border=ft.Border.all(1.5, c["tinta"]) if l.get("voce") else None,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=12, vertical=9),
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
                content=ft.Text(f"Seu apelido, seus números e seus grupos somem do ranking. Seus estudos neste {comp.aparelho()} continuam aqui.", size=14.5),
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
