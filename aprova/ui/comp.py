"""Componentes visuais reutilizados pelas telas."""

from __future__ import annotations

from datetime import date

import flet as ft

from .tema import FONTE_TITULO

# pontos de quebra padrão do ResponsiveRow (largura da janela, em px)
QUEBRAS_PADRAO = {"xs": 0, "sm": 576, "md": 768, "lg": 992, "xl": 1200, "xxl": 1400}


def quebras(app, d: dict | None = None) -> dict:
    """Pontos de quebra ajustados ao zoom da interface (o ResponsiveRow mede a janela de verdade)."""
    s = getattr(app, "_escala_usada", 1.0) or 1.0
    return {k: v * s for k, v in (d or QUEBRAS_PADRAO).items()}


MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def titulo(texto: str, c: dict, tamanho: int = 34, peso=ft.FontWeight.W_600) -> ft.Text:
    return ft.Text(texto, size=tamanho, weight=peso, font_family=FONTE_TITULO, color=c["texto"])


def subtitulo(texto: str, c: dict, tamanho: int = 20) -> ft.Text:
    return ft.Text(texto, size=tamanho, weight=ft.FontWeight.W_600, font_family=FONTE_TITULO, color=c["texto"])


def texto(valor: str, c: dict, tamanho: float = 15, cor: str | None = None, peso=None, **kw) -> ft.Text:
    return ft.Text(valor, size=tamanho, color=cor or c["texto"], weight=peso, **kw)


def apagado(valor: str, c: dict, tamanho: float = 14, **kw) -> ft.Text:
    return ft.Text(valor, size=tamanho, color=c["texto2"], **kw)


def forma(r: int = 10) -> ft.RoundedRectangleBorder:
    return ft.RoundedRectangleBorder(radius=r)


def botao(rotulo: str, on_click=None, icone=None, c: dict | None = None, url: str | None = None, **kw) -> ft.FilledButton:
    return ft.FilledButton(
        rotulo,
        icon=icone,
        on_click=on_click,
        url=url,
        style=ft.ButtonStyle(shape=forma(10), padding=ft.Padding.symmetric(horizontal=18, vertical=14)),
        **kw,
    )


def botao_contorno(rotulo: str, on_click=None, icone=None, url: str | None = None, **kw) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        rotulo,
        icon=icone,
        on_click=on_click,
        url=url,
        style=ft.ButtonStyle(shape=forma(10), padding=ft.Padding.symmetric(horizontal=16, vertical=14)),
        **kw,
    )


def botao_texto(rotulo: str, on_click=None, icone=None, url: str | None = None, **kw) -> ft.TextButton:
    return ft.TextButton(rotulo, icon=icone, on_click=on_click, url=url, style=ft.ButtonStyle(shape=forma(8)), **kw)


def pilula(rotulo: str, fundo: str, cor: str, icone=None, tamanho: float = 12.5) -> ft.Container:
    filhos: list[ft.Control] = []
    if icone:
        filhos.append(ft.Icon(icone, size=14, color=cor))
    filhos.append(ft.Text(rotulo, size=tamanho, color=cor, weight=ft.FontWeight.W_600))
    return ft.Container(
        content=ft.Row(filhos, spacing=4, tight=True),
        bgcolor=fundo,
        border_radius=20,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )


def bolha(
    letra: str,
    c: dict,
    marcada: bool = False,
    estado: str | None = None,
    tamanho: int = 36,
    on_click=None,
) -> ft.Container:
    """A bolinha do cartão-resposta. estado: None | 'certa' | 'errada' | 'gabarito'."""
    borda, fundo, cor_letra = c["tinta"], c["sup"], c["tinta"]
    if marcada:
        fundo, cor_letra = c["tinta"], c["sobre_tinta"]
    if estado == "certa":
        borda, fundo, cor_letra = c["ok"], c["ok"], c["sup"]
    elif estado == "errada":
        borda, fundo, cor_letra = c["erro"], c["erro"], c["sup"]
    elif estado == "gabarito":
        borda, fundo, cor_letra = c["ok"], c["ok_suave"], c["ok"]
    return ft.Container(
        width=tamanho,
        height=tamanho,
        shape=ft.BoxShape.CIRCLE,
        border=ft.Border.all(1.6, borda),
        bgcolor=fundo,
        alignment=ft.Alignment.CENTER,
        content=ft.Text(letra, size=tamanho * 0.42, weight=ft.FontWeight.W_700, color=cor_letra),
        on_click=on_click,
        animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
    )


def bloco(content: ft.Control, c: dict, padding: int = 20, **kw) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=c["sup"],
        border=ft.Border.all(1, c["borda"]),
        border_radius=16,
        padding=padding,
        **kw,
    )


def rotulo(texto_: str, c: dict, cor: str | None = None) -> ft.Text:
    """Rótulo curto acima de um número ou bloco (sem caixa alta)."""
    return ft.Text(texto_, size=13, weight=ft.FontWeight.W_600, color=cor or c["texto2"])


def bolha_icone(icone, c: dict, marcada: bool = False, tamanho: int = 36, icone_marcado=None) -> ft.Container:
    """Ícone dentro de uma bolinha do cartão-resposta: vazia (traço) ou marcada (cheia de tinta)."""
    return ft.Container(
        ft.Icon(icone_marcado if (marcada and icone_marcado) else icone, size=round(tamanho * 0.52), color=c["sobre_tinta"] if marcada else c["texto2"]),
        width=tamanho,
        height=tamanho,
        shape=ft.BoxShape.CIRCLE,
        bgcolor=c["tinta"] if marcada else None,
        border=ft.Border.all(1.5, c["tinta"] if marcada else c["traco"]),
        alignment=ft.Alignment.CENTER,
        animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
    )


def marca_texto(texto_: str, c: dict, tamanho: float = 12.5, peso=ft.FontWeight.W_700) -> ft.Container:
    """Palavra com fundo de marca-texto (usado só para "hoje" e o próximo passo)."""
    return ft.Container(
        ft.Text(texto_, size=tamanho, weight=peso, color=c["sobre_destaque"]),
        bgcolor=c["destaque"],
        border_radius=4,
        padding=ft.Padding.symmetric(horizontal=5, vertical=1),
    )


def carregando(texto_: str, c: dict) -> ft.Row:
    return ft.Row(
        [ft.ProgressRing(width=18, height=18, stroke_width=2.2, color=c["tinta"]), apagado(texto_, c, 14)],
        spacing=12,
    )


def aviso(texto_: str, c: dict, tipo: str = "info", acao: ft.Control | None = None) -> ft.Container:
    cores = {
        "info": (c["tinta_suave"], c["tinta"], ft.Icons.INFO_OUTLINE),
        "alerta": (c["marca_suave"], c["marca"], ft.Icons.WARNING_AMBER_ROUNDED),
        "erro": (c["erro_suave"], c["erro"], ft.Icons.ERROR_OUTLINE),
        "ok": (c["ok_suave"], c["ok"], ft.Icons.CHECK_CIRCLE_OUTLINE),
    }
    fundo, cor, icone = cores.get(tipo, cores["info"])
    filhos: list[ft.Control] = [
        ft.Icon(icone, color=cor, size=20),
        ft.Container(ft.Text(texto_, size=14, color=c["texto"]), expand=True),
    ]
    if acao:
        filhos.append(acao)
    return ft.Container(
        content=ft.Row(filhos, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=fundo,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    )


def vazio(icone, titulo_: str, texto_: str, c: dict, acao: ft.Control | None = None) -> ft.Container:
    filhos: list[ft.Control] = [
        ft.Icon(icone, size=40, color=c["texto2"]),
        subtitulo(titulo_, c, 19),
        ft.Text(texto_, size=14.5, color=c["texto2"], text_align=ft.TextAlign.CENTER),
    ]
    if acao:
        filhos.append(ft.Container(acao, padding=ft.Padding.only(top=6)))
    return ft.Container(
        content=ft.Column(filhos, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        padding=ft.Padding.symmetric(vertical=40, horizontal=24),
        alignment=ft.Alignment.CENTER,
    )


def bloco_data(iso: str | None, c: dict, dias: int | None, futuro_iso: str | None = None) -> ft.Container:
    """Bloco do prazo: dia grande, mês e dias que faltam."""
    if not iso:
        return ft.Container(width=64, content=apagado("—", c, 22), alignment=ft.Alignment.CENTER)
    d = date.fromisoformat(iso)
    if dias is None:
        cor, rotulo = c["texto2"], ""
    elif dias < 0:
        cor, rotulo = c["texto2"], "encerrou"
    elif dias == 0:
        cor, rotulo = c["erro"], "hoje"
    elif dias <= 3:
        cor, rotulo = c["erro"], f"{dias} dia" + ("s" if dias > 1 else "")
    elif dias <= 7:
        cor, rotulo = c["marca"], f"{dias} dias"
    else:
        cor, rotulo = c["texto2"], f"{dias} dias"
    if futuro_iso:
        cor, rotulo = c["tinta"], "abre " + date.fromisoformat(futuro_iso).strftime("%d/%m")
    return ft.Container(
        width=68,
        content=ft.Column(
            [
                ft.Text(f"{d.day:02d}", size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"], height=30),
                ft.Text(MESES[d.month - 1], size=13, color=c["texto2"]),
                ft.Text(rotulo, size=12, color=cor, weight=ft.FontWeight.W_700),
            ],
            spacing=1,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def barra(fracao: float, c: dict, cor: str | None = None, altura: int = 8, largura: int | None = None) -> ft.Container:
    fracao = max(0.0, min(1.0, fracao))
    return ft.Container(
        height=altura,
        width=largura,
        expand=largura is None,
        bgcolor=c["sup2"],
        border_radius=altura,
        content=ft.Row(
            [
                ft.Container(bgcolor=cor or c["tinta"], border_radius=altura, expand=max(1, int(fracao * 1000))),
                ft.Container(expand=max(1, int((1 - fracao) * 1000)) if fracao < 1 else None, visible=fracao < 1),
            ],
            spacing=0,
        ),
    )


def divisor(c: dict) -> ft.Divider:
    return ft.Divider(height=1, thickness=1, color=c["borda"])


def mensagem(page: ft.Page, texto_: str, c: dict | None = None) -> None:
    page.show_dialog(ft.SnackBar(content=ft.Text(texto_, size=14), duration=3500, behavior=ft.SnackBarBehavior.FLOATING))
