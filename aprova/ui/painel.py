"""Painel: desempenho (onde está bem e mal), tempo de estudo, lembretes e livros."""

from __future__ import annotations

from datetime import date

import flet as ft

from .. import analise, livros
from . import comp, metas
from .app import DESTINOS_LEMBRETE
from .tema import FONTE_TITULO

ABAS = [("desempenho", "Desempenho"), ("tempo", "Tempo"), ("ranking", "Ranking"), ("lembretes", "Lembretes"), ("livros", "Livros")]
NIVEL_COR = {"forte": ("ok_suave", "ok"), "atencao": ("marca_suave", "marca"), "fraco": ("erro_suave", "erro"), "poucos": ("sup2", "texto2")}


QUEBRAS_BLOCOS = {"um": 0, "lado": 1180}  # largura da janela (já conta a barra lateral)


def _lado_a_lado(blocos: list[ft.Control], app=None) -> ft.Control:
    """Dois blocos lado a lado em janelas largas; um embaixo do outro nas menores."""
    for b in blocos:
        if getattr(b, "col", None) in (None, {}):
            b.col = {"um": 12, "lado": 6}
    return ft.ResponsiveRow(blocos, spacing=14, run_spacing=14, breakpoints=comp.quebras(app, QUEBRAS_BLOCOS))


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


class TelaPainel:
    def __init__(self, app):
        self.app = app
        self.aba = "desempenho"

    def preparar(self, aba: str | None = None, **_):
        if aba in dict(ABAS):
            self.aba = aba

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        abas = ft.SegmentedButton(
            selected=[self.aba],
            segments=[ft.Segment(value=k, label=ft.Text(v)) for k, v in ABAS],
            show_selected_icon=False,
            on_change=self._trocar,
        )
        topo = (
            ft.Row([comp.titulo("Painel", c, 34), ft.Container(expand=True), abas], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            if app.largo
            else ft.Column([comp.titulo("Painel", c, 28), ft.Row([abas], scroll=ft.ScrollMode.AUTO)], spacing=10)
        )
        corpo = {"desempenho": self._desempenho, "tempo": self._tempo, "ranking": self._ranking, "lembretes": self._lembretes, "livros": self._livros}[self.aba]()
        return ft.Column(
            [topo, ft.ListView([corpo, ft.Container(height=30)], expand=True, spacing=0)],
            spacing=16,
            expand=True,
        )

    def _ranking(self) -> ft.Control:
        from .ranking import SecaoRanking

        if getattr(self, "_secao_ranking", None) is None:
            self._secao_ranking = SecaoRanking(self.app, self._recarregar)
        return self._secao_ranking.build()

    def _trocar(self, e):
        self.aba = e.control.selected[0] if e.control.selected else "desempenho"
        self.app.recarregar_tela_sem_perder(self)

    # ================================================================ desempenho

    def _numero(self, valor: str, rotulo: str, detalhe: str = "", cor: str | None = None) -> ft.Container:
        c = self.app.c
        return ft.Container(
            ft.Column(
                [
                    comp.apagado(rotulo, c, 13),
                    ft.Text(valor, size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=cor or c["texto"]),
                    comp.apagado(detalhe, c, 12.5) if detalhe else ft.Container(),
                ],
                spacing=1,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            col={"um": 6, "quatro": 3},
        )

    def _desempenho(self) -> ft.Control:
        app, c = self.app, self.app.c
        r = analise.resumo_desempenho(app.db)
        if not r["respondidas"]:
            return comp.vazio(
                ft.Icons.INSIGHTS_OUTLINED,
                "Ainda não há respostas para analisar",
                "Faça um simulado ou estude no modo estudo. Aqui aparecem seus acertos por disciplina, banca e concurso, e onde você está bem ou mal.",
                c,
                comp.botao("Ir para Estudar", lambda e: app.ir("estudar"), ft.Icons.EDIT_NOTE),
            )
        var = r["variacao"]
        var_txt = "" if var is None else (f"{'+' if var >= 0 else '−'}{abs(var) * 100:.0f} pontos vs. semana passada")
        numeros = [
            self._numero(str(r["respondidas"]), "Questões resolvidas", f"{r['acertos']} acertos"),
            self._numero(_pct(r["taxa"]), "Taxa de acerto", "no total", c["ok"] if (r["taxa"] or 0) >= 0.7 else (c["marca"] if (r["taxa"] or 0) >= 0.5 else c["erro"])),
            self._numero(str(r["semana_respondidas"]), "Nesta semana", var_txt or "questões corrigidas"),
            self._numero(str(len(r["fracas"])), "Pontos a melhorar", f"{len(r['fortes'])} pontos fortes"),
        ]
        # um bloco só com os quatro números (em vez de quatro cartões iguais)
        linha_numeros = comp.bloco(ft.ResponsiveRow(numeros, spacing=18, run_spacing=14, breakpoints=comp.quebras(self.app, metas.QUEBRAS_CARTOES)), c, padding=18)
        blocos: list[ft.Control] = [linha_numeros, self._bloco_disciplinas(r), self._bloco_evolucao(r)]
        tabelas = [self._tabela("Por banca", r["bancas"]), self._tabela("Por concurso", r["concursos"])]
        blocos.append(_lado_a_lado(tabelas, self.app))
        return ft.Column(blocos, spacing=16)

    def _bloco_disciplinas(self, r: dict) -> ft.Control:
        app, c = self.app, self.app.c
        revisao = app.db.revisao_resumo()["por_disciplina"]
        linhas: list[ft.Control] = []
        for d in r["disciplinas"]:
            fundo, cor = NIVEL_COR[d["nivel"]]
            nome = d["chave"] or "Geral"
            acoes = ft.Row(
                [
                    ft.IconButton(ft.Icons.FITNESS_CENTER, tooltip=f"Treinar 10 questões de {nome}", icon_size=19, on_click=lambda e, n=nome: app.page.run_task(app.abrir_destino, "treino", n)),
                    ft.IconButton(
                        ft.Icons.REPLAY,
                        tooltip=f"Revisar os erros de {nome}",
                        icon_size=19,
                        disabled=not revisao.get(nome, {}).get("total"),
                        on_click=lambda e, n=nome: app.page.run_task(app.abrir_destino, "revisao", n),
                    ),
                    ft.IconButton(ft.Icons.MENU_BOOK_OUTLINED, tooltip="Livros e material", icon_size=19, on_click=lambda e: self._ir_livros()),
                    ft.IconButton(ft.Icons.TRAVEL_EXPLORE, tooltip=f"Pesquisar {nome} na internet", icon_size=19, on_click=lambda e, n=nome: app.page.run_task(app.abrir_destino, "busca", f"{n} concurso resumo")),
                ],
                spacing=0,
                tight=True,
            )
            info = ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(nome, size=15, weight=ft.FontWeight.W_600, color=c["texto"], expand=True),
                            comp.pilula(analise.ROTULOS[d["nivel"]], c[fundo], c[cor], tamanho=11.5),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [comp.barra(d["taxa"], c, c[cor] if d["nivel"] != "poucos" else c["tinta"], altura=8), comp.apagado(f"{_pct(d['taxa'])} · {d['respondidas']} questões", c, 12.5)],
                        spacing=10,
                    ),
                ],
                spacing=6,
                expand=True,
            )
            linhas.append(
                ft.Container(
                    ft.Row([info, acoes], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER) if app.largo else ft.Column([info, acoes], spacing=2),
                    padding=ft.Padding.symmetric(vertical=10),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        fracas = [d["chave"] for d in r["fracas"]][:3]
        frase = (
            "Concentre o estudo em " + ", ".join(fracas) + ". Treine, revise os erros e veja as indicações de livros."
            if fracas
            else "Nenhum ponto fraco claro ainda. Continue resolvendo questões para o Aprova medir melhor."
        )
        return comp.bloco(
            ft.Column(
                [
                    comp.subtitulo("Onde você está bem e onde está mal", c, 18),
                    comp.apagado(frase + " (Abaixo de 5 questões, a disciplina fica como 'poucos dados'.)", c, 13),
                    ft.Column(linhas, spacing=0),
                ],
                spacing=8,
            ),
            c,
            padding=18,
        )

    def _ir_livros(self):
        self.aba = "livros"
        self.app.recarregar_tela_sem_perder(self)

    def _bloco_evolucao(self, r: dict) -> ft.Control:
        c = self.app.c
        maior = 150
        barras = []
        for s in r["semanas"]:
            taxa = s["taxa"]
            altura = int(maior * taxa) if taxa is not None else 0
            cor = c["sup2"] if taxa is None else (c["ok"] if taxa >= 0.7 else (c["marca"] if taxa >= 0.5 else c["erro"]))
            barras.append(
                ft.Column(
                    [
                        comp.apagado(_pct(taxa), c, 12),
                        ft.Container(height=maior, alignment=ft.Alignment.BOTTOM_CENTER, content=ft.Container(height=max(altura, 3), bgcolor=cor, border_radius=6, width=34)),
                        comp.apagado(f"{s['inicio']:%d/%m}", c, 11.5),
                        comp.apagado(f"{s['respondidas']} q.", c, 11),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                    tooltip=f"Semana de {s['inicio']:%d/%m}: {s['acertos']} de {s['respondidas']} certas",
                )
            )
        return comp.bloco(
            ft.Column(
                [comp.subtitulo("Evolução nas últimas 8 semanas", c, 18), comp.apagado("Taxa de acerto por semana (verde a partir de 70%).", c, 13), ft.Row(barras, spacing=6)],
                spacing=10,
            ),
            c,
            padding=18,
        )

    def _tabela(self, titulo: str, itens: list[dict]) -> ft.Control:
        c = self.app.c
        linhas: list[ft.Control] = []
        for x in itens[:8]:
            fundo, cor = NIVEL_COR[x["nivel"]]
            linhas.append(
                ft.Row(
                    [
                        ft.Text(x["nome"], size=14, color=c["texto"], expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        comp.apagado(f"{x['respondidas']} q.", c, 12.5),
                        ft.Container(ft.Text(_pct(x["taxa"]), size=13, weight=ft.FontWeight.W_700, color=c[cor]), bgcolor=c[fundo], border_radius=8, padding=ft.Padding.symmetric(horizontal=8, vertical=2)),
                    ],
                    spacing=10,
                )
            )
        if not linhas:
            linhas.append(comp.apagado("Sem dados ainda.", c, 13))
        return comp.bloco(ft.Column([comp.subtitulo(titulo, c, 17)] + linhas, spacing=10), c, padding=18, col={"um": 12, "lado": 6})

    # ================================================================ tempo

    def _tempo(self) -> ft.Control:
        app, c = self.app, self.app.c
        r = metas.resumo(app)
        blocos: list[ft.Control] = [metas.painel_semana(app, r)]
        lado = [self._mapa_calor(r), self._dias_da_semana(r)]
        blocos.append(_lado_a_lado(lado, self.app))
        baixo = [self._por_disciplina(r), metas.cronometro(app)]
        blocos.append(_lado_a_lado(baixo, self.app))
        blocos.append(comp.apagado("O tempo conta sozinho enquanto você resolve questões no app (para depois de 8 minutos sem mexer). Para estudo fora do app, use o cronômetro ou lance o tempo.", c, 12.5))
        return ft.Column(blocos, spacing=16)

    def _mapa_calor(self, r: dict) -> ft.Control:
        c = self.app.c
        lim = max((d["segundos"] for s in r["semanas"] for d in s["dias"]), default=0) or 1

        def cor(d):
            if d["futuro"]:
                return c["bg"]
            if not d["estudou"]:
                return c["sup2"]
            f = d["segundos"] / lim
            return ft.Colors.with_opacity(0.3 + 0.7 * min(1, f), c["ok"]) if d["segundos"] else ft.Colors.with_opacity(0.3, c["ok"])

        colunas = []
        for s in r["semanas"]:
            colunas.append(
                ft.Column(
                    [ft.Container(width=16, height=16, border_radius=4, bgcolor=cor(d), tooltip=f"{d['dia']:%d/%m}: {metas.fmt_hm_longo(d['segundos'])}") for d in s["dias"]],
                    spacing=4,
                )
            )
        rotulos = ft.Column([ft.Container(comp.apagado(n, c, 10.5), height=16, alignment=ft.Alignment.CENTER_LEFT) for n in ["Seg", "", "Qua", "", "Sex", "", "Dom"]], spacing=4)
        estudados = sum(s["dias_estudados"] for s in r["semanas"])
        return comp.bloco(
            ft.Column(
                [
                    comp.subtitulo("Últimas 12 semanas", c, 18),
                    comp.apagado(f"Você estudou em {estudados} dias. Quanto mais verde, mais tempo no dia.", c, 13),
                    ft.Row([rotulos] + colunas, spacing=4, scroll=ft.ScrollMode.AUTO),
                ],
                spacing=10,
            ),
            c,
            padding=18,
            col={"um": 12, "lado": 6},
        )

    def _dias_da_semana(self, r: dict) -> ft.Control:
        c = self.app.c
        maior = max((d["media_segundos"] for d in r["por_dia_semana"]), default=0) or 1
        linhas = []
        for d in r["por_dia_semana"]:
            linhas.append(
                ft.Row(
                    [
                        ft.Container(comp.texto(d["rotulo"], c, 13.5, peso=ft.FontWeight.W_600), width=36),
                        comp.barra(d["media_segundos"] / maior, c, c["tinta"], altura=10),
                        ft.Container(comp.apagado(f"{d['vezes']}/{d['de']} · {metas.fmt_hm_longo(int(d['media_segundos']))}", c, 12), width=104),
                    ],
                    spacing=10,
                )
            )
        melhor = max(r["por_dia_semana"], key=lambda d: (d["vezes"], d["media_segundos"]))
        pior = min(r["por_dia_semana"], key=lambda d: (d["vezes"], d["media_segundos"]))
        frase = f"Você estuda mais às {melhor['nome']}s." if melhor["vezes"] else "Ainda sem histórico."
        if melhor["vezes"] and pior["vezes"] < melhor["vezes"]:
            frase += f" {pior['nome'].capitalize()} é o dia mais fraco."
        return comp.bloco(
            ft.Column(
                [
                    comp.subtitulo("Em que dias você estuda", c, 18),
                    comp.apagado(f"Últimas 8 semanas: vezes que estudou naquele dia e a média de tempo. {frase}", c, 13),
                    ft.Column(linhas, spacing=8),
                    comp.apagado(f"Média por dia de estudo: {metas.fmt_hm_longo(int(r['media_dia']))}", c, 12.5),
                ],
                spacing=10,
            ),
            c,
            padding=18,
            col={"um": 12, "lado": 6},
        )

    def _por_disciplina(self, r: dict) -> ft.Control:
        c = self.app.c
        itens = r["por_disciplina"][:8]
        total = sum(s for _, s in itens) or 1
        linhas = [
            ft.Row(
                [ft.Text(n, size=14, color=c["texto"], width=190, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), comp.barra(s / total, c, altura=8), ft.Container(comp.apagado(metas.fmt_hm_longo(s), c, 12.5), width=62)],
                spacing=10,
            )
            for n, s in itens
        ] or [comp.apagado("Assim que você estudar no app, o tempo por disciplina aparece aqui.", c, 13)]
        return comp.bloco(
            ft.Column([comp.subtitulo("Tempo por disciplina", c, 18), comp.apagado("Últimas 4 semanas.", c, 13)] + linhas, spacing=10),
            c,
            padding=18,
            col={"um": 12, "lado": 6},
        )

    # ================================================================ lembretes

    def _lembretes(self) -> ft.Control:
        app, c = self.app, self.app.c
        lista = app.db.lembretes()
        textos = ft.Column(
            [
                comp.subtitulo("Alarmes de estudo", c, 18),
                comp.apagado("Marque horários para atividades extras. Na hora, o Aprova toca e leva você direto ao conteúdo: pesquisa, vídeo-aulas, um link, a revisão ou um treino.", c, 13),
            ],
            spacing=4,
            expand=app.largo,
        )
        novo = comp.botao("Novo alarme", lambda e: dialogo_lembrete(app, None, self._recarregar), ft.Icons.ADD_ALARM)
        topo = (
            ft.Row([textos, novo], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            if app.largo
            else ft.Column([textos, novo], spacing=10)
        )
        if not lista:
            sugestoes = self._sugestoes()
            return ft.Column(
                [
                    comp.bloco(topo, c, padding=18),
                    comp.vazio(ft.Icons.ALARM, "Nenhum alarme ainda", "Comece com uma destas sugestões ou crie o seu.", c),
                    sugestoes,
                ],
                spacing=14,
            )
        linhas = [self._linha_lembrete(l) for l in lista]
        aviso = comp.apagado(
            "Os alarmes tocam com o Aprova aberto no celular (o celular vibra)." if app.celular
            else "Os alarmes tocam com o Aprova aberto no computador (pode ficar minimizado)." if not app.modo_web
            else "Os alarmes tocam no computador onde o Aprova está aberto.",
            c,
            12.5,
        )
        return ft.Column([comp.bloco(topo, c, padding=18), comp.bloco(ft.Column(linhas, spacing=0), c, padding=6), aviso, self._sugestoes()], spacing=14)

    def _sugestoes(self) -> ft.Control:
        app, c = self.app, self.app.c
        r = analise.resumo_desempenho(app.db)
        fraca = r["fracas"][0]["chave"] if r["fracas"] else "Língua Portuguesa"
        modelos = [
            {"titulo": "Revisão do dia", "hora": "20:00", "dias": "0,1,2,3,4", "alvo_tipo": "revisao", "alvo": ""},
            {"titulo": f"Treino de {fraca}", "hora": "19:00", "dias": "1,3", "alvo_tipo": "treino", "alvo": fraca},
            {"titulo": "Leitura da lei seca", "hora": "07:30", "dias": "5", "alvo_tipo": "busca", "alvo": "lei seca do edital"},
            {"titulo": f"Vídeo-aula de {fraca}", "hora": "21:00", "dias": "2", "alvo_tipo": "video", "alvo": fraca},
        ]
        chips = [
            ft.OutlinedButton(
                f"{m['titulo']} · {m['hora']}",
                icon=DESTINOS_LEMBRETE[m["alvo_tipo"]][1],
                on_click=lambda e, m=m: dialogo_lembrete(app, dict(m), self._recarregar),
            )
            for m in modelos
        ]
        return ft.Column([comp.apagado("Sugestões rápidas", c, 13), ft.Row(chips, wrap=True, spacing=8, run_spacing=8)], spacing=8)

    def _linha_lembrete(self, lem: dict) -> ft.Control:
        app, c = self.app, self.app.c
        dest, icone = DESTINOS_LEMBRETE.get(lem["alvo_tipo"], ("", ft.Icons.NOTIFICATIONS_OUTLINED))
        if lem["data"]:
            quando = "uma vez, em " + date.fromisoformat(lem["data"]).strftime("%d/%m")
        else:
            dias = analise.dias_planejados(lem["dias"])
            quando = "todos os dias" if len(dias) == 7 else ("seg a sex" if dias == [0, 1, 2, 3, 4] else ", ".join(metas.NOMES_DIAS[d] for d in dias))
        ativo = bool(lem["ativo"])

        def alternar(e):
            dados = dict(lem)
            dados["ativo"] = 1 if e.control.value else 0
            app.db.salvar_lembrete(dados, lem["id"])

        def apagar(e):
            app.db.apagar_lembrete(lem["id"])
            self._recarregar()

        detalhe = f"{quando} · {dest}" + (f": {lem['alvo']}" if lem["alvo"] else "")
        return ft.Container(
            ft.Row(
                [
                    ft.Text(lem["hora"], size=24, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"] if ativo else c["texto2"], width=78),
                    ft.Icon(icone, color=c["tinta"], size=20),
                    ft.Column(
                        [
                            ft.Text(lem["titulo"], size=15, weight=ft.FontWeight.W_600, color=c["texto"]),
                            comp.apagado(detalhe, c, 12.5, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.Switch(value=ativo, on_change=alternar, tooltip="Ligado/desligado"),
                    ft.IconButton(ft.Icons.PLAY_ARROW_ROUNDED, tooltip="Estudar agora", on_click=lambda e: app.page.run_task(app.abrir_destino, lem["alvo_tipo"], lem["alvo"], lem["titulo"])),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Editar", on_click=lambda e: dialogo_lembrete(app, dict(lem), self._recarregar, lem["id"])),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Apagar", on_click=apagar),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
        )

    def _recarregar(self):
        self.app.recarregar_tela_sem_perder(self)

    # ================================================================ livros

    def _livros(self) -> ft.Control:
        app, c = self.app, self.app.c
        r = analise.resumo_desempenho(app.db)
        taxa = {d["chave"]: d for d in r["disciplinas"]}
        nas_provas = [p["disciplina"] for p in app.db.prioridades(20)]
        ordem: list[str] = [d["chave"] for d in r["fracas"]]
        ordem += [d for d in nas_provas if d not in ordem]
        ordem += [d for d in livros.INDICACOES if d not in ordem]
        blocos: list[ft.Control] = [
            comp.apagado(
                "Primeiro as disciplinas em que você está pior, depois as que mais caem nas suas provas. "
                "Confira sempre a edição mais recente (as leis mudam). Material oficial gratuito aparece marcado.",
                c,
                13,
            )
        ]
        for disc in ordem:
            itens = livros.para(disc)
            if not itens:
                continue
            d = taxa.get(disc)
            selo = ft.Container()
            if d:
                fundo, cor = NIVEL_COR[d["nivel"]]
                selo = comp.pilula(f"você acerta {_pct(d['taxa'])}", c[fundo], c[cor], tamanho=11.5)
            linhas: list[ft.Control] = []
            for it in itens:
                gratis = bool(it.get("url"))
                linhas.append(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PUBLIC if gratis else ft.Icons.MENU_BOOK_OUTLINED, color=c["ok"] if gratis else c["tinta"], size=20),
                            ft.Column(
                                [
                                    ft.Row(
                                        [ft.Text(it["titulo"], size=14.5, weight=ft.FontWeight.W_600, color=c["texto"])]
                                        + ([comp.pilula("grátis", c["ok_suave"], c["ok"], tamanho=11)] if gratis else []),
                                        spacing=8,
                                        wrap=True,
                                    ),
                                    comp.apagado(f"{it['autor']} — {it['por_que']}", c, 12.5),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            comp.botao_texto("Abrir" if gratis else "Procurar", lambda e, u=livros.link_busca(it): app.page.run_task(app.abrir_url, u), ft.Icons.OPEN_IN_NEW),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                )
            atalhos = ft.Row(
                [
                    comp.botao_texto(rot, lambda e, u=url: app.page.run_task(app.abrir_url, u), getattr(ft.Icons, ic))
                    for rot, ic, url in livros.links_estudo(f"{disc} para concurso")[:2]
                ],
                spacing=4,
                wrap=True,
            )
            blocos.append(
                comp.bloco(
                    ft.Column([ft.Row([comp.subtitulo(disc, c, 17), selo], spacing=10, wrap=True), *linhas, atalhos], spacing=10),
                    c,
                    padding=18,
                )
            )
        return ft.Column(blocos, spacing=14)


def dialogo_lembrete(app, dados: dict | None, ao_salvar, lembrete_id: int | None = None) -> None:
    """Criar ou editar um alarme de estudo."""
    c = app.c
    dados = dados or {"titulo": "", "hora": "19:00", "dias": "0,1,2,3,4", "data": "", "alvo_tipo": "busca", "alvo": ""}
    titulo = ft.TextField(value=dados["titulo"], label="Atividade", hint_text="Ex.: Ler a LGPD, resolver 20 questões", dense=True, border_radius=10)
    hora = ft.TextField(value=dados["hora"], label="Hora (HH:MM)", width=140, dense=True, border_radius=10)
    escolhidos = set(analise.dias_planejados(dados["dias"])) if not dados.get("data") else set()
    uma_vez = ft.Checkbox(label="Só uma vez (hoje ou amanhã)", value=bool(dados.get("data")))
    chips = ft.Row(wrap=True, spacing=6, run_spacing=6)
    tipos = [k for k in DESTINOS_LEMBRETE if k != "simulado"] + ["simulado"]
    destino = ft.Dropdown(
        label="Ao tocar, me leve para",
        value=dados["alvo_tipo"] or "busca",
        options=[ft.DropdownOption(key=k, text=DESTINOS_LEMBRETE[k][0]) for k in tipos],
        dense=True,
        border_radius=10,
        width=min(400, (app.page.width or 500) - 80),
    )
    disciplinas = sorted({q["disciplina"] for q in app.db.banco_de_questoes()} | set(livros.INDICACOES))
    alvo = ft.TextField(value=dados["alvo"], dense=True, border_radius=10)
    dica = comp.apagado("", c, 12.5)

    def ajustar_alvo(*_):
        t = destino.value
        rotulos = {
            "busca": ("O que pesquisar", "Ex.: LGPD artigo 7 resumo"),
            "video": ("Assunto da aula", "Ex.: crase"),
            "link": ("Endereço (link)", "Ex.: https://www.planalto.gov.br/..."),
            "revisao": ("Disciplina (vazio = todas)", "Ex.: " + (disciplinas[0] if disciplinas else "Língua Portuguesa")),
            "treino": ("Disciplina", "Ex.: Raciocínio Lógico"),
            "simulado": ("Concurso", "Ex.: Dataprev"),
        }
        alvo.label, alvo.hint_text = rotulos.get(t, ("Conteúdo", ""))
        dica.value = "Disciplinas na biblioteca: " + ", ".join(disciplinas[:8]) if t in ("revisao", "treino") and disciplinas else ""
        try:
            alvo.update()
            dica.update()
        except Exception:  # noqa: BLE001
            pass

    destino.on_select = ajustar_alvo

    def desenhar():
        chips.visible = not uma_vez.value
        chips.controls = [
            ft.Container(
                ft.Text(metas.NOMES_DIAS[i], size=13.5, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if i in escolhidos else c["texto"]),
                bgcolor=c["tinta"] if i in escolhidos else c["sup2"],
                border_radius=18,
                padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                on_click=lambda e, i=i: alternar(i),
            )
            for i in range(7)
        ]

    def alternar(i):
        escolhidos.symmetric_difference_update({i})
        desenhar()
        chips.update()

    def mudou_uma_vez(e):
        desenhar()
        chips.update()

    uma_vez.on_change = mudou_uma_vez

    def salvar(e):
        h = (hora.value or "").strip().replace("h", ":")
        partes = h.split(":")
        if len(partes) != 2 or not all(p.isdigit() for p in partes) or not (0 <= int(partes[0]) < 24 and 0 <= int(partes[1]) < 60):
            hora.error = "Use HH:MM"
            hora.update()
            return
        h = f"{int(partes[0]):02d}:{int(partes[1]):02d}"
        if not (titulo.value or "").strip():
            titulo.error = "Dê um nome"
            titulo.update()
            return
        data = ""
        if uma_vez.value:
            from datetime import datetime, timedelta

            agora = datetime.now()
            dia = agora.date() if h > agora.strftime("%H:%M") else agora.date() + timedelta(days=1)
            data = dia.isoformat()
        elif not escolhidos:
            app.msg("Escolha os dias da semana.")
            return
        if destino.value in ("busca", "video", "link", "treino", "simulado") and not (alvo.value or "").strip():
            alvo.error = "Preencha"
            alvo.update()
            return
        app.db.salvar_lembrete(
            {
                "titulo": titulo.value.strip(),
                "hora": h,
                "dias": ",".join(str(i) for i in sorted(escolhidos)),
                "data": data,
                "alvo_tipo": destino.value,
                "alvo": (alvo.value or "").strip(),
                "ativo": 1,
            },
            lembrete_id,
        )
        app.page.pop_dialog()
        app.msg(f"Alarme salvo para as {h}.")
        ao_salvar()

    desenhar()
    ajustar_alvo()
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Editar alarme" if lembrete_id else "Novo alarme", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [titulo, ft.Row([hora, uma_vez], spacing=12, wrap=True), chips, destino, alvo, dica],
                tight=True,
                spacing=12,
                width=min(480, (app.page.width or 520) - 40),
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar", salvar, ft.Icons.CHECK)],
        )
    )
