"""Meu concurso: para qual prova a pessoa estuda e quando ela é.

Com isso o Início mostra a contagem regressiva, o "Onde focar" passa a olhar as provas desse concurso
na biblioteca e o personagem lembra quantos dias faltam. Fica só neste computador (nos ajustes).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

import flet as ft

from . import comp
from .tema import FONTE_TITULO

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
# palavras que não ajudam a achar as provas do concurso na biblioteca
GENERICAS = {"prefeitura", "municipal", "camara", "concurso", "publico", "de", "da", "do", "das", "dos", "e", "para", "edital"}


def dados(app) -> dict:
    """{"nome", "filtro", "data" (aaaa-mm-dd ou ""), "url"} ou {} se a pessoa ainda não escolheu."""
    d = app.aj.get("meu_concurso") or {}
    return d if isinstance(d, dict) and str(d.get("nome") or "").strip() else {}


def data_da_prova(d: dict) -> date | None:
    try:
        return date.fromisoformat(str(d.get("data") or ""))
    except ValueError:
        return None


def dias_para_a_prova(app, hoje: date | None = None) -> int | None:
    dia = data_da_prova(dados(app))
    return None if dia is None else (dia - (hoje or date.today())).days


def filtro(app) -> str:
    return str(dados(app).get("filtro") or "").strip()


def _sem_acento(t: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(ch) != "Mn")


def sugerir_filtro(nome: str) -> str:
    """Palavras curtas para achar as provas do concurso: "TJSP - Tribunal de Justiça..." -> "TJSP";
    "Prefeitura de Matão" -> "Matão"; "Dataprev 2026" -> "Dataprev"."""
    base = re.split(r"\s+[-–—]\s+|\s*\(", nome or "", maxsplit=1)[0]
    palavras = [p for p in re.findall(r"[\wÀ-ú]+", base) if not re.fullmatch(r"(19|20)\d\d", p)]
    uteis = [p for p in palavras if _sem_acento(p) not in GENERICAS]
    return " ".join((uteis or palavras)[:3])


def _junto(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _sem_acento(t or ""))


def eh_do_concurso(prova: dict, filtro_: str) -> bool:
    """A prova é do concurso? Cada palavra do filtro aparece no título/órgão/cargo/banca, ignorando
    acentos, hífens e espaços ("TJSP" acha "TJ-SP"; "TJ SP" também)."""
    palavras = [_junto(p) for p in (filtro_ or "").split()]
    palavras = [p for p in palavras if p]
    if not palavras:
        return False
    alvo = _junto(" ".join(str(prova.get(k) or "") for k in ("titulo", "prova_titulo", "orgao", "cargo", "banca")))
    return all(p in alvo for p in palavras)


def provas_do_concurso(app) -> set[int]:
    f = filtro(app)
    return {p["id"] for p in app.db.provas() if f and eh_do_concurso(p, f)} if dados(app) else set()


def ler_data(texto: str) -> date | None:
    """dd/mm/aaaa (ou dd/mm/aa) -> date; vazio ou inválido -> None."""
    m = re.fullmatch(r"\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\s*", texto or "")
    if not m:
        return None
    d, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    ano += 2000 if ano < 100 else 0
    try:
        return date(ano, mes, d)
    except ValueError:
        return None


def data_por_extenso(dia: date) -> str:
    return f"{DIAS_SEMANA[dia.weekday()]}, {dia.day} de {MESES[dia.month - 1]}"


def frase_contagem(dias: int, nome: str) -> str:
    if dias > 1:
        return f"Faltam {dias} dias para a prova do {nome}"
    if dias == 1:
        return f"A prova do {nome} é amanhã"
    if dias == 0:
        return f"Hoje é a prova do {nome}. Boa prova!"
    return f"A prova do {nome} já passou"


# ---------------------------------------------------------------- Início


def cartao(app) -> ft.Control | None:
    """Contagem regressiva (ou o convite para escolher o concurso). None se a pessoa dispensou o convite."""
    c = app.c
    d = dados(app)
    if not d:
        if app.aj.get("meu_concurso_dispensado"):
            return None

        def dispensar(e):
            app.aj.set("meu_concurso_dispensado", True)
            app.recarregar_tela()

        return ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.EVENT_OUTLINED, color=c["tinta"], size=22),
                    ft.Text("Para qual concurso você estuda? Diga qual é e quando é a prova: o Aprova conta os dias e foca no que cai nele.",
                            size=14, color=c["texto"], expand=True),
                    comp.botao_texto("Escolher meu concurso", lambda e: abrir_dialogo(app), ft.Icons.FLAG_OUTLINED),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Agora não", on_click=dispensar, icon_color=c["texto2"]),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=not app.largo,
            ),
            bgcolor=c["sup"],
            border=ft.Border.all(1, c["borda"]),
            border_radius=14,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )
    nome = d["nome"]
    dia = data_da_prova(d)
    editar = comp.botao_texto("Mudar", lambda e: abrir_dialogo(app), ft.Icons.EDIT_OUTLINED)
    if dia is None:
        principal = ft.Column(
            [
                comp.apagado("Meu concurso", c, 12.5),
                ft.Text(nome, size=20, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                comp.apagado("Sem data da prova ainda. Quando sair, coloque aqui para ver a contagem.", c, 13),
            ],
            spacing=2,
            expand=True,
        )
        return comp.bloco(ft.Row([ft.Icon(ft.Icons.FLAG_OUTLINED, color=c["tinta"], size=28), principal, editar],
                                 spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER), c, padding=18)
    dias = (dia - date.today()).days
    if dias < 0:
        texto = ft.Column(
            [
                ft.Text(f"A prova do {nome} foi em {dia.strftime('%d/%m')}.", size=17, weight=ft.FontWeight.W_600, color=c["texto"]),
                comp.apagado("Torcendo pelo resultado! Quando quiser, escolha o próximo concurso.", c, 13),
            ],
            spacing=2,
            expand=True,
        )
        return comp.bloco(ft.Row([ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED, color=c["marca"], size=28), texto,
                                  comp.botao_texto("Próximo concurso", lambda e: abrir_dialogo(app), ft.Icons.FLAG_OUTLINED)],
                                 spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER), c, padding=18)
    numero = "Hoje!" if dias == 0 else str(dias)
    semanas = dias // 7
    detalhe = data_por_extenso(dia)
    if dias >= 14:
        detalhe += f" · {semanas} semanas de estudo pela frente"
    elif dias >= 2:
        detalhe += " · reta final: revise os erros e faça simulados"
    contador = ft.Container(
        ft.Column(
            [
                ft.Text(numero, size=34 if dias else 26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=c["sobre_tinta"]),
                ft.Text("dias" if dias > 1 else "dia" if dias == 1 else "boa prova", size=12.5, color=c["sobre_tinta"]),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=c["tinta"] if dias > 7 else c["marca"],
        border_radius=14,
        width=96,
        padding=ft.Padding.symmetric(vertical=10),
        alignment=ft.Alignment.CENTER,
    )
    texto = ft.Column(
        [
            comp.apagado("Meu concurso", c, 12.5),
            ft.Text(frase_contagem(dias, nome), size=19, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
            comp.apagado(detalhe, c, 13),
        ],
        spacing=2,
        expand=True,
    )
    return comp.bloco(ft.Row([contador, texto, editar], spacing=18, vertical_alignment=ft.CrossAxisAlignment.CENTER), c, padding=16)


# ---------------------------------------------------------------- escolher


def abrir_dialogo(app, nome: str = "", url: str = "") -> None:
    """Escolher o concurso, as palavras para achar as provas dele e a data da prova."""
    c = app.c
    atual = dados(app)
    nome = nome or atual.get("nome") or ""
    favoritos = [f["nome"] for f in app.db.favoritos()][:8]
    campo_nome = ft.TextField(value=nome, label="Concurso", hint_text="ex.: TJ-SP Escrevente, Dataprev 2026", border_radius=10,
                              autofocus=not nome)
    campo_filtro = ft.TextField(
        value=(atual.get("filtro") if atual and not url else "") or sugerir_filtro(nome),
        label="Como ele aparece no nome das provas",
        helper="Sigla ou órgão (ex.: TJSP, Dataprev). É assim que o foco acha as provas dele.",
        border_radius=10,
    )
    dia_atual = data_da_prova(atual) if atual and not url else None
    campo_data = ft.TextField(value=dia_atual.strftime("%d/%m/%Y") if dia_atual else "", label="Data da prova",
                              hint_text="dd/mm/aaaa (vazio se ainda não saiu)", border_radius=10, expand=True)
    erro = comp.apagado("", c, 12.5)
    erro.color = c["erro"]

    def mudou_nome(e):
        if not (campo_filtro.value or "").strip() or campo_filtro.data == "auto":
            campo_filtro.value = sugerir_filtro(campo_nome.value or "")
            campo_filtro.data = "auto"
            campo_filtro.update()

    campo_nome.on_change = mudou_nome
    campo_filtro.data = "auto" if not (atual.get("filtro") if atual else "") else ""

    def escolheu_data(e):
        v = e.control.value
        if v:
            campo_data.value = v.strftime("%d/%m/%Y")
            campo_data.update()

    picker = ft.DatePicker(first_date=date.today().replace(year=date.today().year - 1), last_date=date.today().replace(year=date.today().year + 3),
                           value=dia_atual, on_change=escolheu_data, help_text="Data da prova", cancel_text="Cancelar", confirm_text="OK")
    calendario = ft.IconButton(ft.Icons.CALENDAR_MONTH_OUTLINED, tooltip="Escolher no calendário", on_click=lambda e: app.page.show_dialog(picker))

    def usar(n: str):
        campo_nome.value = n
        campo_filtro.value = sugerir_filtro(n)
        campo_filtro.data = "auto"
        campo_nome.update()
        campo_filtro.update()

    sugestoes = []
    if favoritos:
        sugestoes = [comp.apagado("Dos que você acompanha:", c, 12.5),
                     ft.Row([ft.Chip(label=ft.Text(f[:40], size=12.5), on_click=lambda e, f=f: usar(f)) for f in favoritos], wrap=True, spacing=6, run_spacing=6)]

    def salvar(e):
        n = (campo_nome.value or "").strip()
        if len(n) < 2:
            erro.value = "Escreva o nome do concurso."
            erro.update()
            return
        texto_data = (campo_data.value or "").strip()
        dia = ler_data(texto_data) if texto_data else None
        if texto_data and dia is None:
            erro.value = "Data inválida. Use dd/mm/aaaa (ex.: 14/12/2026)."
            erro.update()
            return
        app.aj.set("meu_concurso", {"nome": n[:80], "filtro": (campo_filtro.value or "").strip()[:60] or sugerir_filtro(n),
                                     "data": dia.isoformat() if dia else "", "url": url or (atual.get("url") if atual else "") or ""})
        app.page.pop_dialog()
        app.msg(f"Meu concurso: {n}." + (f" {frase_contagem((dia - date.today()).days, n)}." if dia else ""))
        app.recarregar_tela()

    def tirar(e):
        app.aj.set("meu_concurso", {})
        app.page.pop_dialog()
        app.recarregar_tela()

    acoes = [ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Salvar", salvar, ft.Icons.CHECK)]
    if atual:
        acoes.insert(0, ft.TextButton("Não tenho concurso definido", on_click=tirar))
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Meu concurso", font_family=FONTE_TITULO),
            content=ft.Container(
                ft.Column([campo_nome, *sugestoes, campo_filtro, ft.Row([campo_data, calendario], spacing=6), erro], spacing=14, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                width=min(520, (app.page.width or 600) - 60),
            ),
            actions=acoes,
        )
    )
