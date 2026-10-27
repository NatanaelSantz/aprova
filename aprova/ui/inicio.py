"""Tela inicial: progresso, onde focar e prazos dos concursos acompanhados."""

from __future__ import annotations

from datetime import date, datetime

import flet as ft

from ..pci import concurso_de_dict
from . import comp
from .tema import FONTE_TITULO

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


class TelaInicio:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        agora = datetime.now()
        saudacao = "Bom dia" if agora.hour < 12 else "Boa tarde" if agora.hour < 18 else "Boa noite"
        nome = app.nome_exibicao
        hoje = date.today()
        cabecalho = ft.Column(
            [
                comp.apagado(f"{DIAS[hoje.weekday()]}, {hoje.day} de {MESES[hoje.month - 1]}", c, 14),
                comp.titulo(f"{saudacao}{', ' + nome if nome else ''}.", c, 36 if app.largo else 30),
            ],
            spacing=2,
        )
        from . import metas

        est = app.db.estatisticas()
        numeros = self._numeros(est)
        avisos = self._avisos()
        foco = self._onde_focar()
        prazos = self._prazos()
        continuar = self._continuar()
        alarmes = self._alarmes_hoje()
        r = metas.resumo(app)
        from .grupos import cartao_plano_ativo

        motivacao = ft.Column(
            [metas.painel_semana(app, r)]
            + ([x] if (x := cartao_plano_ativo(app)) else [])
            + ([x] if (x := metas.proximo_estudo(app)) else []),
            spacing=14,
        )
        cronometro = app.botao_estudo()
        from .personagem import cartao_inicio

        if app.modo_nav == "lateral" and app.largura >= 1000:
            cabecalho = ft.Row([cabecalho, ft.Container(expand=True), cartao_inicio(app), cronometro], spacing=18, vertical_alignment=ft.CrossAxisAlignment.END)
        elif app.modo_nav == "lateral":
            cabecalho = ft.Row([cabecalho, ft.Container(expand=True), cronometro], vertical_alignment=ft.CrossAxisAlignment.END)
        elif app.modo_nav == "trilho":
            cabecalho = ft.Row([cabecalho, ft.Container(expand=True), cronometro], vertical_alignment=ft.CrossAxisAlignment.END)
        else:
            # celular: o menu da conta fica no canto do cabeçalho
            cabecalho = ft.Column(
                [ft.Row([cabecalho, ft.Container(expand=True), app.menu_conta(compacto=True)], vertical_alignment=ft.CrossAxisAlignment.START), cronometro],
                spacing=12,
            )
        topo = self._cartoes_topo()
        self.caixa_comunicados = ft.Column(topo, spacing=10, visible=bool(topo))
        if app.largo:
            corpo = ft.ResponsiveRow(
                breakpoints=comp.quebras(app),
                controls=[
                    ft.Column([foco], col={"md": 12, "lg": 7}, spacing=28, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                    ft.Column([continuar, alarmes, prazos], col={"md": 12, "lg": 5}, spacing=28, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ],
                spacing=36,
                run_spacing=28,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        else:
            corpo = ft.Column([continuar, alarmes, foco, prazos], spacing=28, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        return ft.Column(
            [cabecalho, self.caixa_comunicados, avisos, motivacao, numeros, corpo, ft.Container(height=30)],
            spacing=26,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def ao_mostrar(self):
        self.app.page.run_task(self._buscar_comunicados)

    async def _buscar_comunicados(self):
        await self.app.carregar_comunicados()
        await self.app.carregar_novidades()
        try:
            self.caixa_comunicados.controls = self._cartoes_topo()
            self.caixa_comunicados.visible = bool(self.caixa_comunicados.controls)
            self.caixa_comunicados.update()
        except Exception:  # noqa: BLE001 - saiu da tela
            pass

    def _cartoes_topo(self) -> list[ft.Control]:
        from .atualizacao import cartao_inicio

        return cartao_inicio(self.app) + self._cartoes_comunicados(self.app.comunicados_cache()) + self._cartoes_grupos()

    def _cartoes_grupos(self) -> list[ft.Control]:
        """Aviso de mensagens novas nos grupos desde a última visita."""
        app, c = self.app, self.app.c
        novas = {k: v for k, v in app.novidades_grupos().items() if v}
        if not novas:
            return []
        itens = sorted(novas.items(), key=lambda x: -x[1])
        partes = [f"{app.nomes_grupos.get(cod, cod)}: {n} mensage{'ns' if n != 1 else 'm'} nova{'s' if n != 1 else ''}" for cod, n in itens[:3]]
        return [
            ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.FORUM_OUTLINED, color=c["tinta"], size=26),
                        ft.Column(
                            [ft.Text("Novidades nos seus grupos", size=16, weight=ft.FontWeight.W_700, color=c["texto"]), comp.apagado(" · ".join(partes), c, 14)],
                            spacing=2,
                            expand=True,
                        ),
                        comp.botao_contorno("Ver", lambda e, cod=itens[0][0]: app.ir("grupos", codigo=cod, aba="conversa"), ft.Icons.ARROW_FORWARD),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=c["tinta_suave"],
                border_radius=14,
                padding=ft.Padding.only(left=18, right=12, top=12, bottom=12),
            )
        ]

    def _cartoes_comunicados(self, lista: list) -> list[ft.Control]:
        c = self.app.c
        vistos = set(self.app.aj.get("comunicados_vistos", []) or [])
        cartoes = []
        for m in lista[:3]:
            if m.get("id") in vistos:
                continue

            def fechar(e, mid=m.get("id")):
                v = list(self.app.aj.get("comunicados_vistos", []) or [])
                v.append(mid)
                self.app.aj.set("comunicados_vistos", v[-50:])
                self.caixa_comunicados.controls = self._cartoes_topo()
                self.caixa_comunicados.visible = bool(self.caixa_comunicados.controls)
                self.caixa_comunicados.update()

            cartoes.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CAMPAIGN_OUTLINED, color=c["marca"], size=26),
                            ft.Column(
                                [ft.Text(m["titulo"], size=16, weight=ft.FontWeight.W_700, color=c["texto"]), ft.Text(m["texto"], size=14, color=c["texto"], selectable=True)],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(ft.Icons.CLOSE, tooltip="Já li", on_click=fechar, icon_size=18),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    bgcolor=c["marca_suave"],
                    border_radius=14,
                    padding=ft.Padding.only(left=18, right=6, top=12, bottom=12),
                )
            )
        return cartoes

    def _alarmes_hoje(self) -> ft.Control:
        """Alarmes de estudo de hoje, com atalho para criar."""
        app, c = self.app, self.app.c
        from .app import DESTINOS_LEMBRETE

        hoje = date.today()
        itens = [
            l for l in app.db.lembretes()
            if l["ativo"] and (l["data"] == hoje.isoformat() or (not l["data"] and str(hoje.weekday()) in str(l["dias"]).split(",")))
        ]
        if not itens:
            return ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.ALARM_ADD, color=c["tinta"]),
                        ft.Column(
                            [comp.texto("Alarmes de estudo", c, 15, peso=ft.FontWeight.W_700), comp.apagado("Marque um horário e o Aprova leva você ao conteúdo na hora.", c, 13)],
                            spacing=2,
                            expand=True,
                        ),
                        comp.botao_texto("Criar", lambda e: app.ir("painel", aba="lembretes")),
                    ],
                    spacing=12,
                ),
                bgcolor=c["sup"],
                border=ft.Border.all(1, c["borda"]),
                border_radius=14,
                padding=16,
            )
        agora = datetime.now().strftime("%H:%M")
        linhas = []
        for l in itens[:4]:
            feito = str(l["ultimo"])[:10] == hoje.isoformat()
            linhas.append(
                ft.Row(
                    [
                        ft.Text(l["hora"], size=16, weight=ft.FontWeight.W_700, color=c["texto2"] if feito or l["hora"] < agora else c["texto"], width=56),
                        ft.Icon(DESTINOS_LEMBRETE.get(l["alvo_tipo"], ("", ft.Icons.ALARM))[1], size=18, color=c["tinta"]),
                        ft.Text(l["titulo"], size=14.5, color=c["texto"], expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.IconButton(ft.Icons.PLAY_ARROW_ROUNDED, tooltip="Estudar agora", icon_size=20,
                                      on_click=lambda e, l=l: app.page.run_task(app.abrir_destino, l["alvo_tipo"], l["alvo"], l["titulo"])),
                    ],
                    spacing=8,
                )
            )
        return ft.Container(
            ft.Column(
                [ft.Row([comp.subtitulo("Alarmes de hoje", c, 18), ft.Container(expand=True), comp.botao_texto("Ver todos", lambda e: app.ir("painel", aba="lembretes"))])] + linhas,
                spacing=6,
            ),
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=14,
            padding=16,
        )

    # ------------------------------------------------------------------

    def _numeros(self, est: dict) -> ft.Control:
        c = self.app.c
        taxa = est["taxa"]
        itens = [
            (str(est["respondidas"]), "questões resolvidas"),
            (f"{taxa * 100:.0f}%" if taxa is not None else "—", "de acerto"),
            (str(self.app.db.revisao_resumo()["pendentes"]), "para revisar hoje"),
            (str(est["provas"]), "provas na sua biblioteca"),
        ]
        from .metas import largura_util

        # numa linha só quando cabe; senão, duas por linha (sem uma sobrando sozinha)
        uma_linha = largura_util(self.app) >= 760
        blocos = []
        for i, (valor, rotulo) in enumerate(itens):
            separa = i if uma_linha else i % 2
            blocos.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(valor, size=34 if self.app.largo else 30, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["tinta"] if i == 1 else c["texto"]),
                            comp.apagado(rotulo, c, 13.5),
                        ],
                        spacing=0,
                    ),
                    padding=ft.Padding.only(left=22 if separa else 0, right=22),
                    border=ft.Border.only(left=ft.BorderSide(1, c["borda"])) if separa else None,
                    expand=uma_linha,
                    col=6,
                )
            )
        if uma_linha:
            return ft.Row(blocos, spacing=0)
        return ft.ResponsiveRow(blocos, run_spacing=16, spacing=0, breakpoints=comp.quebras(self.app))

    def _avisos(self) -> ft.Control:
        app, c = self.app, self.app.c
        novos = app.db.avisos_novos()
        if not novos:
            return ft.Container(visible=False)

        def ver(av):
            def _f(e):
                app.db.marcar_aviso_visto(av["chave"])
                app.telas.pop("inicio", None)
                app.ir("provas", termo=av["termo"], rotulo=av["nome"])

            return _f

        linhas = [
            ft.Row(
                [
                    ft.Icon(ft.Icons.MARK_EMAIL_UNREAD_OUTLINED, color=c["ok"]),
                    ft.Column(
                        [
                            comp.texto(av["nome"], c, 15, peso=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            comp.apagado("1 prova encontrada" if av['qtd'] == 1 else f"{av['qtd']} provas encontradas", c, 13),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    comp.botao("Ver provas", ver(av), ft.Icons.DESCRIPTION_OUTLINED),
                ],
                spacing=12,
            )
            for av in novos[:4]
        ]
        return ft.Container(
            ft.Column([comp.subtitulo("Saiu a prova", c, 20), *linhas], spacing=10),
            bgcolor=c["ok_suave"],
            border_radius=14,
            padding=20,
        )

    FOCO_VISIVEIS = 6

    def _onde_focar(self) -> ft.Control:
        self.caixa_foco = comp.bloco(self._conteudo_foco(), self.app.c, padding=24)
        return self.caixa_foco

    def _alternar_foco(self, e=None):
        self.foco_todas = not getattr(self, "foco_todas", False)
        self.caixa_foco.content = self._conteudo_foco()
        self.caixa_foco.update()

    def _conteudo_foco(self) -> ft.Control:
        """Disciplinas por prioridade; tocar numa abre a mini prova só dela."""
        from .miniprova import abrir_mini_prova

        app, c = self.app, self.app.c
        todas = app.db.prioridades(200)
        abrir = getattr(self, "foco_todas", False)
        itens = todas if abrir else todas[: self.FOCO_VISIVEIS]
        filhos: list[ft.Control] = [
            comp.subtitulo("Onde focar", c, 22),
            comp.apagado(
                "Disciplinas que mais caem nas provas da sua biblioteca, pesadas pelo quanto você ainda erra. "
                "Escolha uma para fazer uma mini prova só dela.",
                c,
                14,
            ),
        ]
        if not itens:
            filhos.append(comp.aviso("Importe uma prova ou faça o simulado de demonstração para ver onde focar.", c))
        maximo = max((i["prioridade"] for i in todas), default=1) or 1
        for i in itens:
            taxa = i["taxa"]
            cor = c["erro"] if taxa is not None and taxa < 0.5 else c["tinta"]
            if taxa is not None:
                desempenho = comp.texto(f"você acerta {taxa * 100:.0f}%", c, 13, cor=c["erro"] if taxa < 0.5 else c["ok"], peso=ft.FontWeight.W_600)
            else:
                desempenho = comp.apagado("você ainda não fez questões", c, 13)
            abrir_mini = lambda e, d=i["disciplina"], t=taxa: abrir_mini_prova(app, d, t)  # noqa: E731
            filhos.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    comp.texto(i["disciplina"], c, 15.5, peso=ft.FontWeight.W_600, expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    comp.apagado(f"{i['peso'] * 100:.0f}% da prova", c, 13),
                                ],
                                spacing=10,
                            ),
                            comp.barra(i["prioridade"] / maximo, c, cor=cor, altura=9),
                            ft.Row(
                                [
                                    desempenho,
                                    ft.Container(expand=True),
                                    ft.TextButton(
                                        "Mini prova",
                                        icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                        on_click=abrir_mini,
                                        tooltip=f"Fazer uma mini prova de {i['disciplina']}",
                                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=0), shape=comp.forma(8)),
                                    ),
                                ],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=4,
                    ),
                    on_click=abrir_mini,
                    border_radius=10,
                    padding=ft.Padding.only(top=4),
                    ink=True,
                )
            )
        if len(todas) > self.FOCO_VISIVEIS:
            filhos.append(
                comp.botao_texto(
                    "Mostrar só as principais" if abrir else f"Ver todas as disciplinas ({len(todas)})",
                    self._alternar_foco,
                    ft.Icons.EXPAND_LESS if abrir else ft.Icons.EXPAND_MORE,
                )
            )
        return ft.Column(filhos, spacing=10)

    def _continuar(self) -> ft.Control:
        app, c = self.app, self.app.c
        provas = [p for p in app.db.provas() if not str(p["origem_url"]).startswith(("aprova://revisao", "aprova://simulado/treino"))]
        tentativas = app.db.tentativas(limite=1)
        alvo = None
        if tentativas:
            alvo = next((p for p in provas if p["id"] == tentativas[0]["prova_id"]), None)
        if alvo is None:
            alvo = next((p for p in provas if p["origem_url"] != "aprova://demo"), None) or (provas[0] if provas else None)
        if alvo is None:
            return ft.Container()
        from .estudar import abrir_prova

        texto_apoio = f"{alvo['n_questoes']} questões"
        if alvo.get("melhor") is not None:
            texto_apoio += f", melhor resultado {alvo['melhor'] * 100:.0f}%"
        return ft.Container(
            content=ft.Column(
                [
                    comp.apagado("Continue de onde parou", c, 13.5),
                    ft.Text(alvo["titulo"], size=21, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                    comp.apagado(texto_apoio, c, 14),
                    ft.Row(
                        [
                            comp.botao("Fazer simulado", lambda e: abrir_prova(app, alvo["id"], "simulado"), ft.Icons.TIMER_OUTLINED),
                            comp.botao_contorno("Modo estudo", lambda e: abrir_prova(app, alvo["id"], "estudo"), ft.Icons.LIGHTBULB_OUTLINE),
                        ],
                        wrap=True,
                        spacing=10,
                        run_spacing=10,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=c["tinta_suave"],
            border_radius=14,
            padding=24,
        )

    def _prazos(self) -> ft.Control:
        app, c = self.app, self.app.c
        favs = [concurso_de_dict(d) for d in app.db.favoritos()]
        favs = [f for f in favs if f.dias_restantes is None or f.dias_restantes >= -3]
        favs.sort(key=lambda x: (x.dias_restantes is None, x.dias_restantes if x.dias_restantes is not None else 0))
        filhos: list[ft.Control] = [comp.subtitulo("Prazos que você acompanha", c, 22)]
        if not favs:
            filhos.append(
                comp.apagado("Toque na estrela de um concurso para acompanhar o prazo de inscrição aqui.", c, 14)
            )
            filhos.append(comp.botao_contorno("Ver concursos abertos", lambda e: app.ir("concursos"), ft.Icons.CAMPAIGN_OUTLINED))
        for f in favs[:6]:
            filhos.append(
                ft.Container(
                    ft.Row(
                        [
                            comp.bloco_data(f.prazo_fim, c, f.dias_restantes, f.prazo_inicio if f.inscricoes_futuras else None),
                            ft.Column(
                                [
                                    comp.texto(f.nome, c, 15, peso=ft.FontWeight.W_600, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    comp.apagado(f.cargos or f.vagas, c, 13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.TRAVEL_EXPLORE,
                                tooltip="Procurar a prova deste concurso",
                                icon_color=c["tinta"],
                                on_click=lambda e, nome=f.nome: app.ir("provas", termo=nome.split(" - ")[0].strip(), rotulo=nome),
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=8),
                    border=ft.Border.only(top=ft.BorderSide(1, c["borda"])),
                    on_click=lambda e, u=f.url: app.ir("concursos", abrir=u),
                )
            )
        return comp.bloco(ft.Column(filhos, spacing=10), c, padding=24)
