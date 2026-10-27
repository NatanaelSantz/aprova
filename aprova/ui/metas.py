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


def _ritmo(r: dict) -> tuple[str, str, str]:
    """(rótulo, valor, explicação). Nunca "vermelho": atrás do plano mostra quanto falta."""
    meta, saldo = r["meta_segundos"], r["saldo"]
    if (r["previsto_ate_ontem"] == 0 and saldo <= 0) or not meta:
        return "Ritmo", "Em dia", ("Cada minuto de hoje já conta." if meta else "A meta ainda não começou.")
    if saldo >= 0:
        return "Ritmo", "+" + fmt_hm(saldo), "à frente do plano"
    return "Para ficar em dia", fmt_hm_longo(-saldo), "dá para recuperar na semana"


def _quando_comeca(app) -> str:
    planejados = analise.dias_planejados(app.aj["dias_planejados"])
    hoje_d = date.today()
    prox = next((hoje_d + timedelta(days=k) for k in range(1, 8) if (hoje_d + timedelta(days=k)).weekday() in planejados), None)
    if not prox:
        return "Sem dias de estudo marcados."
    return f"Sua meta começa {'no' if prox.weekday() >= 5 else 'na'} {analise.DIAS_LONGOS[prox.weekday()]}."


def largura_util(app) -> float:
    """Largura que sobra para o conteúdo (janela menos a navegação e as margens)."""
    w = app.largura
    modo = app.modo_nav
    return w - (236 + 72 if modo == "lateral" else 88 + 48 if modo == "trilho" else 32)


def nota_inicio_meta(r: dict) -> str:
    """Na primeira semana da meta, o aviso de que ela vale só para os dias que restam (ou "")."""
    if r["proporcional"] and r["inicio"]:
        return f"Sua meta começou a contar em {r['inicio']:%d/%m}: nesta primeira semana ela vale só para os dias que restam."
    return ""


def painel_semana(app, r: dict, com_nota: bool = True) -> ft.Control:
    """Um painel só para a semana: total estudado, ritmo, sequência, hoje e as barras dos 7 dias.
    com_nota=False: o aviso da primeira semana fica com quem chamou (no Início ele vai para o cabeçalho)."""
    c = app.c
    meta, total = r["meta_segundos"], r["total_semana"]
    cumpriu = r["progresso"] >= 1 and meta > 0
    hoje = next(x for x in r["semana"] if x["hoje"])
    meta_hoje = hoje["meta"]
    frac_hoje = min(1.0, hoje["segundos"] / meta_hoje) if meta_hoje else (1.0 if hoje["segundos"] else 0.0)

    ajustar = ft.Container(
        ft.Row([ft.Icon(ft.Icons.EDIT_OUTLINED, size=14, color=c["tinta"]), ft.Text("Ajustar meta", size=13, color=c["tinta"], weight=ft.FontWeight.W_600)], spacing=4, tight=True),
        on_click=lambda e: dialogo_meta(app),
        tooltip="Mudar horas por semana e dias de estudo",
        padding=ft.Padding.symmetric(vertical=2),
    )
    grande = ft.Text(
        spans=[
            ft.TextSpan(fmt_hm_longo(total), ft.TextStyle(size=44 if app.largo else 38, weight=ft.FontWeight.W_600, font_family=FONTE_TITULO, color=c["ok"] if cumpriu else c["texto"])),
            ft.TextSpan(f"  de {fmt_hm_longo(meta)}" if meta else "  estudados", ft.TextStyle(size=15, color=c["texto2"])),
        ]
    )
    linhas: list[ft.Control] = [comp.rotulo("Sua semana", c), grande]
    if meta:
        linhas.append(comp.barra(r["progresso"], c, c["ok"] if cumpriu else c["tinta"], altura=8))
        nota = "Meta da semana cumprida!" if cumpriu else f"{int(round(r['progresso'] * 100))}% da meta"
    else:
        nota = _quando_comeca(app)
    linhas.append(ft.Row([comp.apagado(nota, c, 13), ft.Container(expand=True), ajustar], vertical_alignment=ft.CrossAxisAlignment.CENTER))
    principal = ft.Column(linhas, spacing=6)

    rot_r, val_r, exp_r = _ritmo(r)
    seq = r["sequencia"]
    dias_txt = f"{r['dias_semana']} de {r['meta_dias']} dias nesta semana" if r["meta_dias"] else f"{r['dias_semana']} dia{'s' if r['dias_semana'] != 1 else ''} nesta semana"

    def dado(rotulo: str, valor: str, detalhe: str, cor: str | None = None) -> ft.Control:
        return ft.Column(
            [comp.rotulo(rotulo, c), ft.Text(valor, size=24 if app.largo else 20, weight=ft.FontWeight.W_600, font_family=FONTE_TITULO, color=cor or c["texto"]), comp.apagado(detalhe, c, 12.5)],
            spacing=2,
            expand=True,
        )

    dados = [
        dado(rot_r, val_r, exp_r, c["ok"] if val_r.startswith("+") else None),
        dado("Sequência", f"{seq} dia{'s' if seq != 1 else ''}", dias_txt, c["marca"] if seq >= 3 else None),
        dado("Hoje", fmt_hm_longo(hoje["segundos"]), _frase_hoje(hoje, meta_hoje), c["ok"] if frac_hoje >= 1 and meta_hoje else None),
    ]

    def separador(altura: int = 74):
        # altura fixa: dentro de uma tela que rola, a linha não pode "esticar"
        return ft.Container(width=1, height=altura, bgcolor=c["borda"], margin=ft.Margin.symmetric(horizontal=4))

    grafico = barras_dias(app, r)
    if largura_util(app) >= 880:
        topo = ft.Row(
            [
                ft.Container(principal, expand=5),
                separador(104),
                ft.Container(ft.Row([dados[0], separador(), dados[1], separador(), dados[2]], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER), expand=7),
            ],
            spacing=22,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        corpo = ft.Column([topo, comp.divisor(c), grafico], spacing=18)
        padding = ft.Padding.symmetric(horizontal=26, vertical=22)
    else:
        # janela estreita: os três números vão para baixo do total
        corpo = ft.Column([principal, comp.divisor(c), ft.Row(dados, spacing=10, vertical_alignment=ft.CrossAxisAlignment.START), comp.divisor(c), grafico], spacing=14)
        padding = ft.Padding.symmetric(horizontal=22 if app.largo else 18, vertical=20 if app.largo else 18)
    filhos: list[ft.Control] = []
    if com_nota and (nota := nota_inicio_meta(r)):
        filhos.append(comp.apagado(nota, c, 12.5))
    filhos.append(ft.Container(corpo, bgcolor=c["sup"], border=ft.Border.all(1, c["borda"]), border_radius=18, padding=padding))
    return ft.Column(filhos, spacing=8)


def barras_dias(app, r: dict) -> ft.Control:
    """As horas de cada dia em barras, com a marca da meta do dia. Cabe até no celular (7 colunas)."""
    c = app.c
    estudou = any(x["segundos"] for x in r["semana"])
    # sem nada estudado na semana, as barras ficam baixinhas: só a linha da meta, sem um vão vazio no cartão
    altura = (92 if app.largo else 76) if estudou else 34
    maior = max([x["segundos"] for x in r["semana"]] + [x["meta"] for x in r["semana"]] + [3600])
    cores = {"cumprida": c["ok"], "extra": ft.Colors.with_opacity(0.45, c["tinta"]), "abaixo": c["marca"], "hoje": c["tinta"]}
    tem_extra = any(x["situacao"] == "extra" for x in r["semana"])
    colunas = []
    for x in r["semana"]:
        seg, meta = x["segundos"], x["meta"]
        h = max(4, altura * seg / maior) if seg else 3
        cor = cores.get(x["situacao"], c["traco"]) if seg else c["borda"]
        if x["hoje"] and seg and x["situacao"] not in ("cumprida", "extra"):
            cor = c["tinta"]
        pilha: list[ft.Control] = [ft.Container(height=h, bgcolor=cor, border_radius=ft.BorderRadius.only(top_left=6, top_right=6, bottom_left=2, bottom_right=2), width=26 if app.largo else 18, bottom=0)]
        if meta:
            # tracinho na altura da meta do dia
            pilha.append(ft.Container(height=2, width=36 if app.largo else 26, bgcolor=c["texto2"], bottom=altura * meta / maior - 1, opacity=0.55))
        barra = ft.Stack(pilha, height=altura, width=40 if app.largo else 28, alignment=ft.Alignment.BOTTOM_CENTER)
        nome = comp.marca_texto("Hoje", c, 12.5) if x["hoje"] else ft.Text(x["rotulo"], size=12.5, color=c["texto2"])
        valor = ft.Text(fmt_hm(seg) if seg else "–", size=12.5, weight=ft.FontWeight.W_600 if seg else None, color=c["texto"] if seg else c["texto2"])
        colunas.append(
            ft.Container(
                ft.Column([valor, barra, nome], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=True,
                tooltip=f"{x['dia']:%d/%m}: {fmt_hm_longo(seg)}" + (f" (meta {fmt_hm_longo(meta)})" if meta else " (folga)" if not x["antes"] else " (antes do início)") + (f", {x['questoes']} questões" if x["questoes"] else ""),
            )
        )
    legenda = ft.Row(
        [
            ft.Row([ft.Container(width=10, height=10, bgcolor=c["ok"], border_radius=3), comp.apagado("meta do dia cumprida", c, 12)], spacing=5, tight=True),
            ft.Row([ft.Container(width=10, height=10, bgcolor=c["marca"], border_radius=3), comp.apagado("abaixo da meta", c, 12)], spacing=5, tight=True),
            ft.Row([ft.Container(width=14, height=2, bgcolor=c["texto2"], opacity=0.55), comp.apagado("meta do dia", c, 12)], spacing=5, tight=True),
        ]
        + ([ft.Row([ft.Container(width=10, height=10, bgcolor=ft.Colors.with_opacity(0.45, c["tinta"]), border_radius=3), comp.apagado("estudo em dia sem meta", c, 12)], spacing=5, tight=True)] if tem_extra else []),
        spacing=16,
        wrap=True,
        run_spacing=4,
    )
    return ft.Column([ft.Row(colunas, spacing=2, vertical_alignment=ft.CrossAxisAlignment.END), legenda], spacing=12)


def _frase_hoje(hoje: dict, meta: int) -> str:
    if not meta:
        return "Estudar hoje é bônus." if not hoje["segundos"] else "Bônus no dia livre. Muito bem!"
    falta = meta - hoje["segundos"]
    if falta <= 0:
        return "Meta do dia cumprida!"
    if hoje["segundos"] == 0:
        return f"Que tal começar? A meta de hoje é {fmt_hm_longo(meta)}."
    return f"Faltam {fmt_hm_longo(falta)} para a meta do dia."


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
            comp.rotulo("Seu próximo estudo", c, c["tinta"]),
            ft.Text(sug["titulo"], size=21, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
            comp.apagado(sug["detalhe"], c, 13.5),
        ],
        spacing=3,
        expand=True,
    )
    botao = comp.botao(sug["acao"], comecar, ft.Icons.PLAY_ARROW_ROUNDED)
    conteudo = ft.Row([texto, botao], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER) if app.largo else ft.Column([texto, botao], spacing=12)
    # fio de tinta à esquerda, como a marcação na margem do caderno
    return ft.Container(
        conteudo,
        bgcolor=c["tinta_suave"],
        border=ft.Border.only(left=ft.BorderSide(5, c["tinta"])),
        border_radius=ft.BorderRadius.only(top_right=16, bottom_right=16, top_left=6, bottom_left=6),
        padding=ft.Padding.only(left=22, right=18, top=16, bottom=16),
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
