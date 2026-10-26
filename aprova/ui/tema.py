"""Paletas, fontes e tema do app.

A cor principal é o azul de caneta esferográfica — a tinta do cartão-resposta.
O modo sépia é o modo de leitura: fundo de papel amarelado, menos brilho e
contraste suave, para longas sessões de estudo.
"""

from __future__ import annotations

import flet as ft

FONTE_TITULO = "Fraunces"
FONTE_TEXTO = "Atkinson"

FONTES = {
    FONTE_TITULO: "fonts/Fraunces.ttf",
    FONTE_TEXTO: "fonts/AtkinsonHyperlegible-Regular.ttf",
}

PALETAS: dict[str, dict[str, str]] = {
    "claro": {
        "bg": "#F4F6FA",
        "sup": "#FFFFFF",
        "sup2": "#ECEFF6",
        "borda": "#E0E4ED",
        "traco": "#B8C0D2",
        "texto": "#141C33",
        "texto2": "#586179",
        "tinta": "#2340A8",
        "tinta_suave": "#E4E9F8",
        "sobre_tinta": "#FFFFFF",
        "ok": "#1D7F53",
        "ok_suave": "#E0F2E8",
        "erro": "#B83A33",
        "erro_suave": "#FAE6E3",
        "marca": "#C98E12",
        "marca_suave": "#FCF0D2",
        "destaque": "#FFE16A",
        "sobre_destaque": "#3A2C00",
    },
    "sepia": {
        "bg": "#F2E9D4",
        "sup": "#F9F3E5",
        "sup2": "#ECE1C8",
        "borda": "#DCCEB0",
        "traco": "#BFA982",
        "texto": "#3A2E20",
        "texto2": "#75654D",
        "tinta": "#3F4F8A",
        "tinta_suave": "#E3DECF",
        "sobre_tinta": "#FBF6EA",
        "ok": "#3D7448",
        "ok_suave": "#E1E6CC",
        "erro": "#A14335",
        "erro_suave": "#F1DAC8",
        "marca": "#A87414",
        "marca_suave": "#F1E0B8",
        "destaque": "#F2D46B",
        "sobre_destaque": "#3A2E20",
    },
    "escuro": {
        "bg": "#0E1220",
        "sup": "#161B2B",
        "sup2": "#1D2335",
        "borda": "#262D43",
        "traco": "#4A5371",
        "texto": "#E5E8F1",
        "texto2": "#98A1B7",
        "tinta": "#93A8FF",
        "tinta_suave": "#222B4A",
        "sobre_tinta": "#0E1220",
        "ok": "#55C792",
        "ok_suave": "#16332A",
        "erro": "#F08077",
        "erro_suave": "#3A2020",
        "marca": "#F0C04E",
        "marca_suave": "#3A311D",
        "destaque": "#5E4D12",
        "sobre_destaque": "#FFE9A3",
    },
}

NOMES_TEMA = {"claro": "Claro", "sepia": "Sépia (leitura)", "escuro": "Escuro"}


def paleta(nome: str) -> dict[str, str]:
    return PALETAS.get(nome, PALETAS["claro"])


def tema_flet(nome: str) -> ft.Theme:
    c = paleta(nome)
    return ft.Theme(
        font_family=FONTE_TEXTO,
        scaffold_bgcolor=c["bg"],
        dialog_theme=ft.DialogTheme(bgcolor=c["sup"], shape=ft.RoundedRectangleBorder(radius=20)),
        scrollbar_theme=ft.ScrollbarTheme(thickness=6, radius=3, thumb_color=c["traco"], main_axis_margin=2, cross_axis_margin=2),
        divider_theme=ft.DividerTheme(color=c["borda"], thickness=1, space=1),
        tooltip_theme=ft.TooltipTheme(text_style=ft.TextStyle(size=12.5, color=c["sup"]), decoration=ft.BoxDecoration(bgcolor=c["texto"], border_radius=8)),
        bottom_sheet_theme=ft.BottomSheetTheme(bgcolor=c["sup"]),
        color_scheme=ft.ColorScheme(
            primary=c["tinta"],
            on_primary=c["sobre_tinta"],
            primary_container=c["tinta_suave"],
            on_primary_container=c["texto"],
            secondary=c["tinta"],
            on_secondary=c["sobre_tinta"],
            surface=c["sup"],
            on_surface=c["texto"],
            on_surface_variant=c["texto2"],
            outline=c["borda"],
            outline_variant=c["borda"],
            error=c["erro"],
            surface_container=c["sup"],
            surface_container_low=c["sup"],
            surface_container_high=c["sup2"],
            surface_container_highest=c["sup2"],
            secondary_container=c["tinta_suave"],
            on_secondary_container=c["texto"],
        ),
    )


def aplicar(page: ft.Page, nome: str) -> None:
    t = tema_flet(nome)
    page.theme = t
    page.dark_theme = t
    page.theme_mode = ft.ThemeMode.DARK if nome == "escuro" else ft.ThemeMode.LIGHT
    page.bgcolor = paleta(nome)["bg"]
