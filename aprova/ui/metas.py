"""Indicadores de meta e tempo de estudo (tela Início e Painel)."""

from __future__ import annotations

from datetime import date, timedelta

import flet as ft

from .. import analise, sessoes
from . import comp
from .tema import FONTE_TITULO

NOMES_DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def fmt_hm(seg: int) -> str:
    """3:55 (horas:minutos)."""
    m = int((seg or 0) // 60)
    return f"{m // 60}:{m % 60:02d}"


def fmt_hm_longo(seg: int) -> str:
    """21h54 / 45 min."""
    m = int(round((seg or 0) / 60))
    if m < 60:
        return f"{m} min"
    return f"{m // 60}h{m % 60:02d}"


def resumo(app) -> dict:
    inicio = None
    try:
        inicio = date.fromisoformat(app.aj["metas_desde"]) if app.aj["metas_desde"] else None
    except ValueError:
        inicio = None
    return analise.resumo_tempo(
        app.db,
        meta_horas=float(app.aj["meta_horas_semana"] or 10),
        planejados=analise.dias_planejados(app.aj["dias_planejados"]),
        inicio=inicio,
    )


# Os pontos de quebra do ResponsiveRow usam a largura da JANELA. No computador há
# ~310 px de barra lateral e margens, por isso os valores abaixo já descontam isso.
QUEBRAS_CARTOES = {"um": 0, "dois": 600, "quatro": 1430}
QUEBRAS_DIAS = {"base": 0, "sete": 1090}


def _cartao(conteudo: ft.Control, c: dict, **kw) -> ft.Container:
    return ft.Container(
        conteudo,
        bgcolor=c["sup"],
        border=ft.Border.all(1, c["borda"]),
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=18, vertical=16),
        **kw,
    )


def anel(fracao: float, c: dict, tamanho: int = 58, cor: str | None = None) -> ft.Control:
    pct = int(round(fracao * 100))
    return ft.Stack(
        [
            ft.ProgressRing(value=max(0.001, min(1.0, fracao)), width=tamanho, height=tamanho, stroke_width=6, color=cor or c["tinta"], bgcolor=c["sup2"]),
            ft.Container(ft.Text(f"{pct}%", size=14, weight=ft.FontWeight.W_700, color=c["texto"]), width=tamanho, height=tamanho, alignment=ft.Alignment.CENTER),
        ],
        width=tamanho,
        height=tamanho,
    )


def _bolinha(icone, cor: str, fundo: str) -> ft.Container:
    return ft.Container(ft.Icon(icone, color=cor, size=24), width=52, height=52, border_radius=26, bgcolor=fundo, alignment=ft.Alignment.CENTER)


def _valor(c: dict, grande: str, pequeno: str = "", cor: str | None = None) -> ft.Text:
    """Número grande + complemento pequeno; quebra linha sozinho se faltar espaço."""
    spans = [ft.TextSpan(grande, ft.TextStyle(size=23, weight=ft.FontWeight.W_600, color=cor or c["texto"], font_family=FONTE_TITULO))]
    if pequeno:
        spans.append(ft.TextSpan("  " + pequeno, ft.TextStyle(size=13.5, color=c["texto2"])))
    return ft.Text(spans=spans)


def _indicador(c: dict, icone: ft.Control, rotulo: str, valor: ft.Control, rodape: ft.Control | None) -> ft.Container:
    coluna = [comp.apagado(rotulo, c, 13), valor]
    if rodape is not None:
        coluna.append(rodape)
    return _cartao(
        ft.Row([icone, ft.Column(coluna, spacing=3, expand=True)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        c,
        col={"um": 12, "dois": 6, "quatro": 3},
    )


def indicadores(app, r: dict) -> ft.Control:
    """Meta da semana, ritmo, sequência e hoje — em grade que se ajusta à largura."""
    c = app.c
    meta = r["meta_segundos"]
    cumpriu = r["progresso"] >= 1 and meta > 0
    ajustar = ft.Container(
        ft.Row([ft.Icon(ft.Icons.EDIT_OUTLINED, size=14, color=c["tinta"]), ft.Text("Ajustar meta", size=12.5, color=c["tinta"], weight=ft.FontWeight.W_600)], spacing=4, tight=True),
        on_click=lambda e: dialogo_meta(app),
        tooltip="Mudar horas por semana e dias de estudo",
    )
    if meta:
        cart_meta = _indicador(
            c,
            anel(r["progresso"], c, cor=c["ok"] if cumpriu else c["tinta"]),
            "Meta da semana",
            _valor(c, fmt_hm_longo(r["total_semana"]), f"de {fmt_hm_longo(meta)}"),
            ajustar,
        )
    else:
        # começou num dia sem estudo planejado (ex.: sábado): a meta começa no próximo dia de estudo
        planejados = analise.dias_planejados(app.aj["dias_planejados"])
        hoje_d = date.today()
        prox = next((hoje_d + timedelta(days=k) for k in range(1, 8) if (hoje_d + timedelta(days=k)).weekday() in planejados), None)
        quando = f"começa {'no' if prox and prox.weekday() >= 5 else 'na'} {analise.DIAS_LONGOS[prox.weekday()]}" if prox else "sem meta"
        cart_meta = _indicador(
            c,
            _bolinha(ft.Icons.EVENT_AVAILABLE_OUTLINED, c["tinta"], c["tinta_suave"]),
            "Meta da semana",
            _valor(c, fmt_hm_longo(r["total_semana"]), f"estudados · sua meta {quando}"),
            ajustar,
        )

    # ritmo: nunca "vermelho". Atrás do plano mostra quanto falta para ficar em dia.
    saldo = r["saldo"]
    if (r["previsto_ate_ontem"] == 0 and saldo <= 0) or not meta:
        cart_ritmo = _indicador(
            c, _bolinha(ft.Icons.ROCKET_LAUNCH_OUTLINED, c["tinta"], c["tinta_suave"]), "Ritmo da semana",
            _valor(c, "Em dia"),
            comp.apagado("Começou agora: cada minuto de hoje já conta." if meta else "Sua meta ainda não começou: estudar agora é bônus.", c, 12.5),
        )
    elif saldo >= 0:
        cart_ritmo = _indicador(
            c, _bolinha(ft.Icons.TRENDING_UP, c["ok"], c["ok_suave"]), "Ritmo da semana",
            _valor(c, "+" + fmt_hm(saldo), "adiantado", c["ok"]), comp.apagado("Você está à frente do plano. Siga assim!", c, 12.5),
        )
    else:
        cart_ritmo = _indicador(
            c, _bolinha(ft.Icons.FLAG_OUTLINED, c["tinta"], c["tinta_suave"]), "Para ficar em dia",
            _valor(c, fmt_hm_longo(-saldo), "de estudo"), comp.apagado("Dá para recuperar ao longo da semana.", c, 12.5),
        )

    seq = r["sequencia"]
    cart_seq = _indicador(
        c,
        _bolinha(ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED, c["marca"] if seq else c["texto2"], c["marca_suave"] if seq else c["sup2"]),
        "Sequência de estudo",
        _valor(c, str(seq), "dia seguido" if seq == 1 else "dias seguidos"),
        comp.apagado(
            f"{r['dias_semana']} de {r['meta_dias']} dias de estudo nesta semana" if r["meta_dias"] else f"{r['dias_semana']} dia{'s' if r['dias_semana'] != 1 else ''} com estudo nesta semana",
            c,
            12.5,
        ),
    )

    hoje = next(x for x in r["semana"] if x["hoje"])
    meta_hoje = hoje["meta"]
    frac_hoje = min(1.0, hoje["segundos"] / meta_hoje) if meta_hoje else (1.0 if hoje["segundos"] else 0.0)
    cart_hoje = _indicador(
        c,
        _bolinha(ft.Icons.WB_SUNNY_OUTLINED, c["ok"] if frac_hoje >= 1 and meta_hoje else c["tinta"], c["ok_suave"] if frac_hoje >= 1 and meta_hoje else c["tinta_suave"]),
        "Hoje",
        _valor(c, fmt_hm_longo(hoje["segundos"]), f"de {fmt_hm_longo(meta_hoje)}" if meta_hoje else "dia livre"),
        ft.Column(
            [comp.barra(frac_hoje, c, c["ok"] if frac_hoje >= 1 else c["tinta"], altura=6), comp.apagado(_frase_hoje(hoje, meta_hoje), c, 12.5)],
            spacing=4,
        ),
    )
    cartoes = [cart_meta, cart_ritmo, cart_seq, cart_hoje]
    filhos: list[ft.Control] = []
    if r["proporcional"] and r["inicio"]:
        filhos.append(
            comp.apagado(
                f"Sua meta começou a contar em {r['inicio']:%d/%m}. Nesta primeira semana ela é proporcional aos dias que restam; os dias antes disso não contam.",
                c,
                12.5,
            )
        )
    if not app.largo:
        # celular: um cartão só, com o anel da meta e três números embaixo
        def mini(titulo: str, valor: str, cor: str) -> ft.Control:
            return ft.Column([comp.apagado(titulo, c, 12), ft.Text(valor, size=17, weight=ft.FontWeight.W_700, color=cor)], spacing=0, expand=True)

        if (r["previsto_ate_ontem"] == 0 and saldo <= 0) or not meta:
            ritmo = ("Ritmo", "Em dia", c["tinta"])
        elif saldo >= 0:
            ritmo = ("Ritmo", "+" + fmt_hm(saldo), c["ok"])
        else:
            ritmo = ("Para ficar em dia", fmt_hm_longo(-saldo), c["tinta"])
        filhos.append(
            _cartao(
                ft.Column(
                    [
                        cart_meta.content,
                        comp.divisor(c),
                        ft.Row(
                            [
                                mini(*ritmo),
                                mini("Sequência", f"{seq} dia{'s' if seq != 1 else ''}", c["texto"]),
                                mini("Hoje", fmt_hm_longo(hoje["segundos"]), c["ok"] if frac_hoje >= 1 else c["texto"]),
                            ],
                            spacing=8,
                        ),
                    ],
                    spacing=12,
                ),
                c,
            )
        )
        return ft.Column(filhos, spacing=8)
    filhos.append(ft.ResponsiveRow(cartoes, spacing=14, run_spacing=14, breakpoints=QUEBRAS_CARTOES))
    return ft.Column(filhos, spacing=8)


def _frase_hoje(hoje: dict, meta: int) -> str:
    if not meta:
        return "Estudar hoje é bônus." if not hoje["segundos"] else "Bônus no dia livre. Muito bem!"
    falta = meta - hoje["segundos"]
    if falta <= 0:
        return "Meta do dia cumprida!"
    if hoje["segundos"] == 0:
        return f"Que tal começar? A meta de hoje é {fmt_hm_longo(meta)}."
    return f"Faltam {fmt_hm_longo(falta)} para a meta do dia."


def horas_por_dia(app, r: dict) -> ft.Control:
    c = app.c
    cores = {"cumprida": c["ok"], "abaixo": c["marca"], "hoje": c["tinta"], "extra": c["ok"], "futuro": c["sup2"], "folga": c["sup2"], "antes": c["sup2"]}
    cards = []
    for x in r["semana"]:
        meta = x["meta"]
        frac = min(1.0, x["segundos"] / meta) if meta else (1.0 if x["segundos"] else 0.0)
        rotulo = x["rotulo"] + (" · hoje" if x["hoje"] else "")
        sub = f"de {fmt_hm(meta)}" if meta else ("antes do início" if x["antes"] else "folga")
        cards.append(
            ft.Container(
                ft.Column(
                    [
                        ft.Text(rotulo, size=12.5, color=c["tinta"] if x["hoje"] else c["texto2"], weight=ft.FontWeight.W_700 if x["hoje"] else None),
                        ft.Text(fmt_hm(x["segundos"]), size=20, weight=ft.FontWeight.W_700, color=c["texto"] if x["segundos"] or not (x["futuro"] or x["antes"]) else c["texto2"]),
                        comp.apagado(sub, c, 12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Container(comp.barra(frac, c, cores[x["situacao"]], altura=5), padding=ft.Padding.only(top=4)),
                    ],
                    spacing=1,
                ),
                bgcolor=c["tinta_suave"] if x["hoje"] else c["sup"],
                border=ft.Border.all(1.4 if x["hoje"] else 1, c["tinta"] if x["hoje"] else c["borda"]),
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                col={"base": 7, "sete": 4},
                width=None if app.largo else 104,
                tooltip=f"{x['dia']:%d/%m}: {fmt_hm_longo(x['segundos'])}" + (f", {x['questoes']} questões" if x["questoes"] else ""),
            )
        )
    legenda = ft.Row(
        [
            ft.Row([ft.Container(width=10, height=10, bgcolor=c["ok"], border_radius=3), comp.apagado("meta do dia cumprida", c, 12)], spacing=5, tight=True),
            ft.Row([ft.Container(width=10, height=10, bgcolor=c["marca"], border_radius=3), comp.apagado("abaixo da meta", c, 12)], spacing=5, tight=True),
        ],
        spacing=14,
        wrap=True,
    )
    if app.largo:
        # 7 por linha em telas largas, 4 por linha em janelas menores
        linha = ft.ResponsiveRow(cards, columns=28, spacing=8, run_spacing=8, breakpoints=QUEBRAS_DIAS)
        return comp.bloco(ft.Column([comp.subtitulo("Horas por dia", c, 18), linha, legenda], spacing=12), c, padding=16)
    linha = ft.Row(cards, spacing=8, scroll=ft.ScrollMode.AUTO)
    return comp.bloco(ft.Column([comp.subtitulo("Horas por dia", c, 18), linha, legenda], spacing=12), c, padding=16)


def proximo_estudo(app) -> ft.Control | None:
    """Cartão "Seu próximo estudo" com o botão para começar."""
    c = app.c
    sug = sessoes.proximo_estudo(app.db)
    if not sug:
        return None

    async def comecar(e):
        if sug["tipo"] == "revisao":
            await app.abrir_destino("revisao", "")
        else:
            await app.abrir_destino("treino", sug["disciplina"])

    texto = ft.Column(
        [
            ft.Text("SEU PRÓXIMO ESTUDO", size=11.5, weight=ft.FontWeight.W_700, color=c["tinta"]),
            ft.Text(sug["titulo"], size=19, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
            comp.apagado(sug["detalhe"], c, 13.5),
        ],
        spacing=3,
        expand=True,
    )
    botao = comp.botao(sug["acao"], comecar, ft.Icons.PLAY_ARROW_ROUNDED)
    conteudo = ft.Row([texto, botao], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER) if app.largo else ft.Column([texto, botao], spacing=12)
    return ft.Container(
        conteudo,
        bgcolor=c["tinta_suave"],
        border=ft.Border.all(1.2, c["tinta"]),
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=20, vertical=16),
    )


def cronometro(app) -> ft.Control:
    """Cronômetro para o estudo fora do app (livro, vídeo-aula) e registro manual."""
    c = app.c
    if app.cronometro_rodando:
        corpo = ft.Column(
            [
                ft.Row([ft.Icon(ft.Icons.TIMER_OUTLINED, color=c["tinta"]), comp.texto("Cronômetro ligado", c, 15, peso=ft.FontWeight.W_700)], spacing=8),
                app.rotulo_cronometro(34, c["texto"]),
                comp.apagado(app.aj["cronometro_atividade"] or "Estudo livre", c, 13.5),
                ft.Row(
                    [
                        comp.botao("Parar", lambda e: app.dialogo_parar(), ft.Icons.STOP_ROUNDED),
                        comp.botao_texto("Descartar", lambda e: (app.parar_cronometro(salvar=False), app.msg("Cronômetro descartado."))),
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=6,
        )
    else:
        atividade = ft.TextField(hint_text="O que vai estudar? (ex.: LGPD, livro de Português)", dense=True, border_radius=10)
        corpo = ft.Column(
            [
                ft.Row([ft.Icon(ft.Icons.TIMER_OUTLINED, color=c["tinta"]), comp.texto("Estudando fora do app?", c, 15, peso=ft.FontWeight.W_700)], spacing=8),
                comp.apagado("Ligue o cronômetro ao ler um livro ou ver uma aula. O tempo entra na sua meta.", c, 13),
                atividade,
                ft.Row(
                    [
                        comp.botao("Iniciar cronômetro", lambda e: app.iniciar_cronometro(atividade.value or ""), ft.Icons.PLAY_ARROW_ROUNDED),
                        comp.botao_texto("Lançar tempo", lambda e: dialogo_lancar(app), ft.Icons.MORE_TIME),
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=8,
        )
    return comp.bloco(corpo, c, padding=16)


def dialogo_meta(app) -> None:
    c = app.c
    horas = ft.TextField(value=str(app.aj["meta_horas_semana"]), label="Horas por semana", width=170, dense=True, border_radius=10, keyboard_type=ft.KeyboardType.NUMBER)
    escolhidos = set(analise.dias_planejados(app.aj["dias_planejados"]))
    chips = ft.Row(wrap=True, spacing=6, run_spacing=6)

    def desenhar():
        chips.controls = [
            ft.Container(
                ft.Text(NOMES_DIAS[i], size=14, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if i in escolhidos else c["texto"]),
                bgcolor=c["tinta"] if i in escolhidos else c["sup2"],
                border_radius=18,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                on_click=lambda e, i=i: alternar(i),
            )
            for i in range(7)
        ]

    def alternar(i):
        escolhidos.symmetric_difference_update({i})
        desenhar()
        chips.update()

    def salvar(e):
        try:
            h = float((horas.value or "0").replace(",", "."))
        except ValueError:
            horas.error = "Use um número, ex.: 12"
            horas.update()
            return
        if not escolhidos:
            app.msg("Escolha pelo menos um dia.")
            return
        app.aj.set("meta_horas_semana", max(0.5, min(100.0, h)))
        app.aj.set("dias_planejados", ",".join(str(i) for i in sorted(escolhidos)))
        app.page.pop_dialog()
        app.telas.pop("inicio", None)
        app.telas.pop("painel", None)
        app.recarregar_tela()

    desenhar()
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Sua meta de estudo", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column(
                [
                    comp.apagado("Quantas horas por semana e em quais dias você quer estudar. A meta de cada dia é dividida igualmente.", c, 13.5),
                    horas,
                    comp.texto("Dias de estudo", c, 14.5, peso=ft.FontWeight.W_600),
                    chips,
                ],
                tight=True,
                spacing=12,
                width=min(440, (app.page.width or 500) - 40),
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar", salvar, ft.Icons.CHECK)],
        )
    )


def dialogo_lancar(app) -> None:
    """Lançar manualmente um tempo de estudo (ex.: estudou no ônibus)."""
    c = app.c
    minutos = ft.TextField(label="Minutos", value="30", width=120, dense=True, border_radius=10, keyboard_type=ft.KeyboardType.NUMBER)
    atividade = ft.TextField(label="O que estudou", hint_text="Ex.: Direito Administrativo", dense=True, border_radius=10, expand=True)
    dia = ft.SegmentedButton(
        selected=["hoje"],
        segments=[ft.Segment(value="hoje", label=ft.Text("Hoje")), ft.Segment(value="ontem", label=ft.Text("Ontem"))],
        show_selected_icon=False,
    )

    def salvar(e):
        v = (minutos.value or "").strip()
        if not v.isdigit() or not 1 <= int(v) <= 720:
            minutos.error = "1 a 720"
            minutos.update()
            return
        quando = date.today() - timedelta(days=1 if dia.selected and dia.selected[0] == "ontem" else 0)
        app.db.somar_tempo(int(v) * 60, "manual", (atividade.value or "").strip(), dia=quando.isoformat())
        app.page.pop_dialog()
        app.msg(f"Lancei {fmt_hm_longo(int(v) * 60)} de estudo.")
        app.telas.pop("inicio", None)
        app.telas.pop("painel", None)
        app.recarregar_tela()

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Lançar tempo de estudo", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
            content=ft.Column([ft.Row([minutos, atividade], spacing=10), dia], tight=True, spacing=12, width=min(460, (app.page.width or 500) - 40)),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Lançar", salvar, ft.Icons.CHECK)],
        )
    )
