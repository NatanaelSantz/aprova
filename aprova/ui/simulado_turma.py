"""Grupos → Simulados: quem modera publica uma prova da biblioteca; a turma faz e vê o resultado de todos.

O gabarito fica no servidor até a pessoa entregar (o servidor corrige), então ninguém espia antes.
A prova roda no próprio app, em modo simulado, como qualquer outra."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import flet as ft

from .. import ranking as rk
from . import comp
from .personagem import busto
from .tema import FONTE_TITULO

ORIGEM = "aprova://turma/"  # prova local criada a partir do simulado da turma: aprova://turma/<id>


def _quando(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return ""
    return d.strftime("%d/%m %H:%M")


def _prazo(sim: dict) -> str:
    if not sim.get("fecha_em"):
        return "sem prazo"
    try:
        fim = datetime.fromisoformat(sim["fecha_em"].replace("Z", "+00:00"))
    except ValueError:
        return ""
    falta = fim - datetime.now(timezone.utc)
    if falta.total_seconds() <= 0:
        return "encerrado"
    dias = round(falta.total_seconds() / 86400)
    if dias >= 1:
        return f"até {fim.astimezone().strftime('%d/%m')} ({dias} dia{'s' if dias != 1 else ''})"
    horas = int(falta.total_seconds() // 3600)
    return f"fecha em {horas} h" if horas >= 1 else f"fecha em {int(falta.total_seconds() // 60)} min"


def _tempo(segundos: int) -> str:
    m = int(segundos) // 60
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


# ---------------------------------------------------------------------- aba do grupo


def aba_simulados(tela, g: dict) -> ft.Control:
    """Lista dos simulados do grupo. `tela` é a TelaGrupos (usa tela.simulados, tela.erro, tela.carregar_grupo)."""
    app, c = tela.app, tela.app.c
    sims = tela.simulados.get(g["codigo"])
    if sims is None:
        if not tela.erro:
            app.page.run_task(tela.carregar_grupo)
            return comp.carregando("Buscando os simulados da turma…", c)
        return comp.aviso(tela.erro, c, "erro")
    modero = bool(g.get("modero"))
    publicar = comp.botao("Marcar simulado", lambda e: dialogo_publicar(app, g, lambda: tela.recarregar_simulados(g["codigo"])), ft.Icons.ADD_TASK) if modero else None
    if not sims:
        texto = ("Escolha uma prova da sua biblioteca e marque um simulado para a turma: todo mundo faz pelo app, "
                 "o servidor corrige e o resultado de cada um aparece aqui." if modero else
                 "Quando quem cuida do grupo marcar um simulado, ele aparece aqui para você fazer pelo app e comparar com a turma.")
        return comp.vazio(ft.Icons.FACT_CHECK_OUTLINED, "Nenhum simulado da turma ainda", texto, c, publicar)
    linhas = [_linha(tela, g, s) for s in sims]
    topo = [comp.apagado(f"{len(sims)} simulado{'s' if len(sims) != 1 else ''} da turma. Quem entrega vê o gabarito e o resultado de todos.", c, 13)]
    if publicar:
        topo.append(publicar)
    return ft.Column([ft.Row(topo, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True, run_spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                      comp.bloco(ft.Column(linhas, spacing=0), c, padding=6)], spacing=10)


def _linha(tela, g: dict, s: dict) -> ft.Control:
    app, c = tela.app, tela.app.c
    meu = s.get("meu")
    detalhes = [f"{s['total']} questões"]
    if s.get("duracao_min"):
        detalhes.append(f"{s['duracao_min']} min")
    detalhes.append(_prazo(s))
    detalhes.append(f"{s.get('entregas', 0)} entrega{'s' if s.get('entregas', 0) != 1 else ''}")
    if meu:
        pct = 100 * meu["acertos"] / meu["total"] if meu["total"] else 0
        cor = c["ok"] if pct >= 70 else c["marca"] if pct >= 50 else c["erro"]
        selo = ft.Container(ft.Text(f"{meu['acertos']}/{meu['total']}", size=14, weight=ft.FontWeight.W_700, color=c["sobre_tinta"]), bgcolor=cor,
                            border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=6), tooltip=f"Você acertou {pct:.0f}%")
        acao = comp.botao_contorno("Ver resultado da turma", lambda e: dialogo_resultado(app, s), ft.Icons.LEADERBOARD_OUTLINED)
    elif s.get("aberto"):
        selo = comp.pilula("a fazer", c["tinta_suave"], c["tinta"], ft.Icons.TIMER_OUTLINED)
        acao = comp.botao("Fazer agora", lambda e: app.page.run_task(fazer, app, s), ft.Icons.PLAY_ARROW_ROUNDED)
    else:
        selo = comp.pilula("encerrado", c["sup2"], c["texto2"])
        acao = comp.botao_contorno("Ver resultado da turma", lambda e: dialogo_resultado(app, s), ft.Icons.LEADERBOARD_OUTLINED)
    acoes: list[ft.Control] = [acao]
    if g.get("modero"):
        acoes.append(ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Apagar o simulado (e os resultados)", on_click=lambda e: _confirmar_apagar(tela, g, s)))
    return ft.Container(
        ft.Row(
            [
                selo,
                ft.Column(
                    [ft.Text(s["titulo"], size=15, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                     comp.apagado(" · ".join(x for x in detalhes if x), c, 12.5)],
                    spacing=2,
                    expand=True,
                ),
                ft.Row(acoes, spacing=2, tight=True),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=not app.largo,
            run_spacing=8,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=10),
        border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
    )


def _confirmar_apagar(tela, g: dict, s: dict) -> None:
    app = tela.app

    async def apagar(e):
        app.page.pop_dialog()
        try:
            await app.em_segundo_plano(app.ranking.apagar_simulado, s["id"])
        except rk.ErroRanking as ex:
            app.msg(str(ex))
            return
        tela.recarregar_simulados(g["codigo"])

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Apagar o simulado?", font_family=FONTE_TITULO),
            content=ft.Text(f"“{s['titulo']}” some para a turma toda, com os resultados de quem já fez.", size=15),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()),
                     comp.botao("Apagar", lambda e: app.page.run_task(apagar, e), ft.Icons.DELETE_OUTLINE)],
        )
    )


# ---------------------------------------------------------------------- publicar


def dialogo_publicar(app, g: dict, depois) -> None:
    c = app.c
    provas = [p for p in app.db.provas() if not str(p["origem_url"]).startswith(("aprova://revisao", "aprova://simulado/treino", ORIGEM))]
    com_gabarito = []
    for p in provas:
        qs = app.db.questoes(p["id"])
        n = sum(1 for q in qs if (q.get("gabarito") or "").strip() and (q.get("enunciado") or "").strip())
        if n:
            com_gabarito.append((p, n))
    if not com_gabarito:
        app.msg("Nenhuma prova com questões e gabarito na sua biblioteca. Baixe uma em Concursos ou monte um simulado antes.")
        return
    escolha = ft.Dropdown(
        label="Prova da sua biblioteca",
        options=[ft.DropdownOption(key=str(p["id"]), text=f"{p['titulo'][:60]} · {n} questões") for p, n in com_gabarito],
        width=min(520, (app.page.width or 560) - 48),
        value=str(com_gabarito[0][0]["id"]),
        border_radius=10,
        dense=True,
    )
    titulo = ft.TextField(label="Nome do simulado", value=f"Simulado da turma · {datetime.now().strftime('%d/%m')}", border_radius=10, dense=True, max_length=80)
    estado = {"duracao": 0, "prazo": 7}
    linha_dur = ft.Row(spacing=6, wrap=True, run_spacing=6)
    linha_prazo = ft.Row(spacing=6, wrap=True, run_spacing=6)

    def chip(rotulo, marcado, ao_clicar):
        return ft.Container(ft.Text(rotulo, size=13, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if marcado else c["texto"]),
                            bgcolor=c["tinta"] if marcado else c["sup2"], border_radius=999, padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                            on_click=ao_clicar, ink=True)

    def montar():
        linha_dur.controls = [chip(r, estado["duracao"] == v, lambda e, v=v: (estado.__setitem__("duracao", v), montar()))
                              for v, r in ((0, "Livre"), (30, "30 min"), (60, "1 h"), (120, "2 h"), (180, "3 h"))]
        linha_prazo.controls = [chip(r, estado["prazo"] == v, lambda e, v=v: (estado.__setitem__("prazo", v), montar()))
                                for v, r in ((1, "1 dia"), (3, "3 dias"), (7, "1 semana"), (14, "2 semanas"), (None, "Sem prazo"))]
        try:
            linha_dur.update()
            linha_prazo.update()
        except Exception:  # noqa: BLE001
            pass

    montar()
    aviso = ft.Container()

    async def publicar(e):
        pid = int(escolha.value)
        qs = [q for q in app.db.questoes(pid) if (q.get("gabarito") or "").strip() and (q.get("enunciado") or "").strip()]
        try:
            await app.em_segundo_plano(app.ranking.publicar_simulado, g["codigo"], titulo.value or "", qs, estado["duracao"], estado["prazo"])
        except rk.ErroRanking as ex:
            aviso.content = comp.aviso(str(ex) if "SQL novo" not in str(ex) else "O servidor ainda não tem o simulado da turma (SQL da 1.31).", c, "erro")
            app.page.update()
            return
        app.page.pop_dialog()
        app.msg("Simulado publicado para a turma.")
        depois()

    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Marcar simulado da turma", font_family=FONTE_TITULO),
            content=ft.Container(
                ft.Column(
                    [
                        escolha,
                        titulo,
                        ft.Column([comp.rotulo("Tempo de prova", c), linha_dur], spacing=6),
                        ft.Column([comp.rotulo("Até quando dá para fazer", c), linha_prazo], spacing=6),
                        comp.apagado("As questões vão para o servidor sem o gabarito: cada pessoa só vê as respostas depois de entregar. "
                                     "O servidor corrige e monta o resultado da turma.", c, 12.5),
                        aviso,
                    ],
                    spacing=12,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                width=min(520, (app.page.width or 560) - 48),
            ),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()),
                     comp.botao("Publicar", lambda e: app.page.run_task(publicar, e), ft.Icons.SEND_ROUNDED)],
        )
    )


# ---------------------------------------------------------------------- fazer e entregar


async def fazer(app, s: dict) -> None:
    """Baixa as questões, monta a prova local (sem gabarito) e abre em modo simulado."""
    from .estudar import abrir_prova

    try:
        sim = await app.em_segundo_plano(app.ranking.questoes_simulado, s["id"])
    except rk.ErroRanking as ex:
        app.msg(str(ex))
        return
    titulo = sim["titulo"] + (f" · {sim['duracao_min']} min" if sim.get("duracao_min") else "")
    pid = app.db.prova_interna(f"{ORIGEM}{sim['id']}", titulo)
    app.db.atualizar_prova(pid, orgao="Simulado da turma", banca="", ano=datetime.now().year)
    questoes = []
    for q in sim["questoes"]:  # o que vem do servidor é de outra pessoa: só entra texto nos formatos esperados
        if not isinstance(q, dict) or not str(q.get("numero", "")).isdigit():
            continue
        alternativas = q.get("alternativas") if isinstance(q.get("alternativas"), dict) else {}
        questoes.append({"numero": int(q["numero"]), "enunciado": str(q.get("enunciado") or "")[:6000],
                         "alternativas": {str(k)[:2].upper(): str(v)[:2000] for k, v in alternativas.items()},
                         "tipo": "CE" if q.get("tipo") == "CE" else "ME", "disciplina": str(q.get("disciplina") or "Geral")[:80],
                         "texto_base": str(q.get("texto_base") or "")[:8000], "gabarito": None})
    if not questoes:
        app.msg("Esse simulado veio sem questões legíveis.")
        return
    app.db.salvar_questoes(pid, questoes)
    abrir_prova(app, pid, "simulado")


def id_da_turma(prova: dict) -> int | None:
    origem = str(prova.get("origem_url") or "")
    if origem.startswith(ORIGEM) and origem[len(ORIGEM):].isdigit():
        return int(origem[len(ORIGEM):])
    return None


async def entregar(app, prova: dict, respostas: dict[int, str], inicio: float) -> dict | None:
    """Manda as respostas ao servidor e grava o gabarito que volta na prova local. None se não deu."""
    sid = id_da_turma(prova)
    if sid is None:
        return None
    try:
        r = await app.em_segundo_plano(app.ranking.entregar_simulado, sid, respostas, int(time.time() - inicio))
    except rk.ErroRanking as ex:
        if "duplicate" in str(ex).lower() or "já" in str(ex).lower():
            try:  # já tinha entregado antes (ex.: fechou no meio): só pega o gabarito
                gab = await app.em_segundo_plano(app.ranking.gabarito_simulado, sid)
                r = {"gabarito": gab}
            except rk.ErroRanking:
                app.msg("Sem conexão com o servidor: a entrega não foi. Tente finalizar de novo quando a internet voltar.")
                return None
        else:
            app.msg(f"A entrega não foi: {ex} Tente finalizar de novo.")
            return None
    if r.get("gabarito"):
        app.db.definir_gabarito(prova["id"], r["gabarito"])
    return r


# ---------------------------------------------------------------------- resultado da turma


def dialogo_resultado(app, s: dict) -> None:
    c = app.c
    corpo = ft.Column([comp.carregando("Buscando o resultado da turma…", c)], spacing=0, tight=True, scroll=ft.ScrollMode.AUTO)

    async def carregar():
        try:
            linhas = await app.em_segundo_plano(app.ranking.ranking_simulado, s["id"])
        except rk.ErroRanking as ex:
            corpo.controls = [comp.aviso(str(ex), c, "erro")]
            app.page.update()
            return
        if not linhas:
            corpo.controls = [comp.apagado("Ninguém entregou ainda.", c, 13.5)]
            caixa.height = 60
        else:
            melhor = linhas[0]["acertos"] or 1
            itens = []
            for l in linhas:
                pct = 100 * l["acertos"] / l["total"] if l["total"] else 0
                itens.append(ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(f"{l['posicao']}º", size=14, weight=ft.FontWeight.W_700, color=c["tinta"] if l["posicao"] <= 3 else c["texto2"], width=30),
                                    busto(app, l.get("avatar"), l["apelido"], 30, l.get("usuario_id")),
                                    ft.Text(l["apelido"] + (" (você)" if l.get("voce") else ""), size=14, weight=ft.FontWeight.W_600 if l.get("voce") else ft.FontWeight.W_500,
                                            color=c["texto"], expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                    comp.apagado(_tempo(l["segundos"]), c, 12.5),
                                    ft.Text(f"{l['acertos']}/{l['total']} · {pct:.0f}%", size=14, weight=ft.FontWeight.W_700, color=c["texto"]),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Container(comp.barra(l["acertos"] / melhor, c, c["tinta"] if l.get("voce") else None, altura=4, animar=False), padding=ft.Padding.only(left=38)),
                        ],
                        spacing=4,
                    ),
                    bgcolor=c["tinta_suave"] if l.get("voce") else None,
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=7),
                ))
            media = sum(l["acertos"] for l in linhas) / len(linhas)
            corpo.controls = [comp.apagado(f"{len(linhas)} entrega{'s' if len(linhas) != 1 else ''} · média {media:.1f} de {linhas[0]['total']} · "
                                           "desempate pelo tempo", c, 12.5)] + itens
            caixa.height = min(460, (app.page.height or 600) - 220, 40 + 62 * len(itens))
        app.page.update()

    caixa = ft.Container(corpo, width=min(520, (app.page.width or 560) - 48), height=80)
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(s["titulo"], font_family=FONTE_TITULO, max_lines=2),
            content=caixa,
            actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())],
        )
    )
    app.page.run_task(carregar)
