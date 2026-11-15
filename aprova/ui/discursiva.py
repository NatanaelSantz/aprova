"""Estudar → Discursiva: escrever a redação ou a questão discursiva e receber a correção da IA."""

from __future__ import annotations

import random
import time
from datetime import datetime

import flet as ft

from .. import config, discursiva
from . import comp
from .chat import botoes_chat
from .tema import FONTE_TITULO


class SecaoDiscursiva:
    def __init__(self, app, recarregar):
        self.app = app
        self.recarregar = recarregar
        self.editando: dict | None = None  # {"id", "tema", "tipo", "texto", "limite", "inicio"}
        self.corrigindo = False
        self._contagem: ft.Text | None = None

    # ------------------------------------------------------------------ lista

    def build(self) -> ft.Control:
        if self.editando is not None:
            return self._editor()
        app, c = self.app, self.app.c
        itens = app.db.discursivas()
        novo = comp.botao("Nova discursiva", lambda e: self._nova(), ft.Icons.EDIT_NOTE)
        if not itens:
            return comp.vazio(
                ft.Icons.HISTORY_EDU,
                "Discursiva corrigida por IA",
                "Escreva a redação ou a questão discursiva aqui (com tema seu ou um dos prontos) e receba a correção como a banca faria: "
                "nota de 0 a 10, aderência ao tema, argumentação, estrutura e os erros de português com a regra. "
                "Com a sua chave do Claude a correção chega no app; sem chave, abre no Claude ou no ChatGPT.",
                c,
                novo,
            )
        cartoes = []
        for d in itens:
            quando = datetime.fromisoformat(d["criada_em"]).strftime("%d/%m")
            n = discursiva.contar(d["texto"])
            nota = (
                ft.Container(ft.Text(f"{d['nota']:g}", size=18, weight=ft.FontWeight.W_700, color=c["sobre_tinta"]), width=46, height=46, border_radius=23,
                             bgcolor=c["ok"] if d["nota"] >= 7 else c["marca"] if d["nota"] >= 5 else c["erro"], alignment=ft.Alignment.CENTER,
                             tooltip=f"Nota {d['nota']:g} de 10")
                if d.get("nota") is not None
                else ft.Container(ft.Icon(ft.Icons.EDIT_OUTLINED if not d.get("correcao") else ft.Icons.CHECK, color=c["texto2"]), width=46, height=46,
                                  border_radius=23, bgcolor=c["sup2"], alignment=ft.Alignment.CENTER,
                                  tooltip="Sem nota" if d.get("correcao") else "Rascunho, ainda sem correção")
            )
            cartoes.append(
                ft.Container(
                    ft.Row(
                        [
                            nota,
                            ft.Column(
                                [
                                    ft.Text(d["tema"], size=15, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    comp.apagado(f"{discursiva.TIPOS.get(d['tipo'], 'Discursiva')} · {n['palavras']} palavras · {quando}"
                                                 + (" · corrigida" if d.get("correcao") else " · rascunho"), c, 12.5),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Apagar", on_click=lambda e, d=d: self._apagar(d["id"])),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    on_click=lambda e, d=d: self._abrir(d),
                    ink=True,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
                )
            )
        notas = [d["nota"] for d in itens if d.get("nota") is not None]
        media = f" Média das notas: {sum(notas) / len(notas):.1f}." if notas else ""
        return ft.Column(
            [
                ft.Row([comp.apagado(f"{len(itens)} discursiva{'s' if len(itens) != 1 else ''}.{media}", c, 13), ft.Container(expand=True), novo],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                comp.bloco(ft.Column(cartoes, spacing=0), c, padding=4),
            ],
            spacing=12,
        )

    def _nova(self, tema: str = "", tipo: str = "dissertativa", limite: int | None = 30) -> None:
        self.editando = {"id": None, "tema": tema, "tipo": tipo, "texto": "", "limite": limite, "inicio": time.monotonic(), "segundos": 0, "correcao": ""}
        self.recarregar()

    def _abrir(self, d: dict) -> None:
        self.editando = {"id": d["id"], "tema": d["tema"], "tipo": d["tipo"], "texto": d["texto"], "limite": None, "inicio": time.monotonic(),
                         "segundos": int(d.get("segundos") or 0), "correcao": d.get("correcao") or "", "nota": d.get("nota")}
        self.recarregar()

    def _apagar(self, discursiva_id: int) -> None:
        self.app.db.apagar_discursiva(discursiva_id)
        self.recarregar()

    # ------------------------------------------------------------------ editor

    def _editor(self) -> ft.Control:
        app, c, ed = self.app, self.app.c, self.editando
        tema = ft.TextField(label="Tema ou enunciado", value=ed["tema"], multiline=True, min_lines=1, max_lines=4, border_radius=10,
                            hint_text="Cole o enunciado da prova ou escolha um tema pronto", on_change=lambda e: ed.__setitem__("tema", e.control.value))
        tipos = ft.Row([self._chip(r, ed["tipo"] == k, lambda e, k=k: self._mudar_tipo(k)) for k, r in discursiva.TIPOS.items()], wrap=True, spacing=6, run_spacing=6)
        sortear = comp.botao_texto("Tema pronto", lambda e: self._tema_pronto(tema), ft.Icons.CASINO_OUTLINED)
        self._contagem = comp.apagado(self._texto_contagem(ed["texto"]), c, 12.5)

        def mudou(e):
            ed["texto"] = e.control.value
            self._contagem.value = self._texto_contagem(ed["texto"])
            try:
                self._contagem.update()
            except Exception:  # noqa: BLE001
                pass

        texto = ft.TextField(
            value=ed["texto"], multiline=True, min_lines=12 if app.largo else 10, max_lines=30, border_radius=10, text_size=15,
            hint_text="Escreva aqui como escreveria na folha de resposta. Sem apoio externo: na prova também não tem.",
            on_change=mudou, label="Seu texto",
        )
        botoes: list[ft.Control] = [comp.botao_contorno("Salvar rascunho", lambda e: self._salvar(avisar=True), ft.Icons.SAVE_OUTLINED)]
        if app.aj.chave_claude:
            botoes.append(comp.botao("Corrigir com a IA", lambda e: app.page.run_task(self._corrigir_com_chave), ft.Icons.AUTO_AWESOME_OUTLINED,
                                     disabled=self.corrigindo))
        pedido = lambda: (self._salvar(), discursiva.pedido_correcao(ed["tema"], ed["texto"], ed["tipo"], ed["limite"]))[1]  # noqa: E731
        chat = botoes_chat(app, pedido, "Corrigir")
        colar = comp.botao_texto("Colar a correção que recebi", lambda e: self._dialogo_colar(), ft.Icons.CONTENT_PASTE)
        ajuda = comp.apagado(
            ("Corrigir com a IA usa a sua chave do Claude (Ajustes → IA) e guarda a correção aqui. " if app.aj.chave_claude else
             "Sem chave da IA: Corrigir ao Claude/ChatGPT abre o chat com o pedido pronto; depois cole a correção aqui para guardar a nota. "
             "Com a chave do Claude (Ajustes → IA), a correção chega dentro do app. ")
            + "Conte o tempo: numa prova real você tem cerca de 1 hora para 30 linhas.",
            c, 12.5,
        )
        partes: list[ft.Control] = [
            ft.Row([comp.botao_texto("Voltar", lambda e: self._voltar(), ft.Icons.ARROW_BACK),
                    ft.Text("Rascunho" if not ed["id"] else "Discursiva", size=18, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"])],
                   spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([tipos, sortear], vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True, spacing=12, run_spacing=6),
            tema,
            texto,
            self._contagem,
            ft.Row(botoes + [chat, colar], wrap=True, spacing=8, run_spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ajuda,
        ]
        if self.corrigindo:
            partes.append(ft.Row([ft.ProgressRing(width=18, height=18, stroke_width=2), comp.apagado("Corrigindo… leva uns 20 segundos.", c, 13)], spacing=10))
        if ed.get("correcao"):
            nota = ed.get("nota")
            partes.append(comp.bloco(
                ft.Column(
                    [
                        ft.Row([ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, color=c["tinta"]),
                                ft.Text(f"Correção · nota {nota:g}/10" if nota is not None else "Correção", size=17, font_family=FONTE_TITULO,
                                        weight=ft.FontWeight.W_600, color=c["texto"])], spacing=8),
                        ft.Markdown(ed["correcao"], selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
                    ],
                    spacing=10,
                ),
                c,
            ))
        return comp.bloco(ft.Column(partes, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH), c, padding=18 if app.largo else 12)

    def _chip(self, rotulo: str, marcado: bool, ao_clicar) -> ft.Control:
        c = self.app.c
        return ft.Container(
            ft.Text(rotulo, size=13, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if marcado else c["texto"]),
            bgcolor=c["tinta"] if marcado else c["sup2"], border_radius=999, padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            on_click=ao_clicar, ink=True,
        )

    def _texto_contagem(self, texto: str) -> str:
        n = discursiva.contar(texto)
        limite = self.editando.get("limite") if self.editando else None
        linhas = f"{n['linhas']} linha{'s' if n['linhas'] != 1 else ''}" + (f" de {limite}" if limite else "")
        return f"{n['palavras']} palavras · {linhas} (folha de {discursiva.LINHA} caracteres por linha)"

    def _mudar_tipo(self, tipo: str) -> None:
        self.editando["tipo"] = tipo
        self.editando["limite"] = {"dissertativa": 30, "questao": 20, "peca": 60}[tipo]
        self.recarregar()

    def _tema_pronto(self, campo: ft.TextField) -> None:
        opcoes = [t for t in discursiva.TEMAS if t[0] == self.editando["tipo"]] or discursiva.TEMAS
        _, tema, limite = random.choice([t for t in opcoes if t[1] != self.editando["tema"]] or opcoes)
        self.editando["tema"], self.editando["limite"] = tema, limite
        campo.value = tema
        try:
            campo.update()
        except Exception:  # noqa: BLE001
            pass

    def _segundos(self) -> int:
        ed = self.editando
        return int(ed["segundos"] + (time.monotonic() - ed["inicio"]))

    def _salvar(self, avisar: bool = False) -> int | None:
        ed = self.editando
        if not (ed["texto"] or "").strip():
            if avisar:
                self.app.msg("Escreva o texto antes de salvar.")
            return None
        if not (ed["tema"] or "").strip():
            ed["tema"] = "Sem tema"
        ed["id"] = self.app.db.salvar_discursiva(ed["tema"], ed["tipo"], ed["texto"], self._segundos(), ed["id"])
        if avisar:
            self.app.msg("Rascunho salvo.")
        return ed["id"]

    def _voltar(self) -> None:
        if (self.editando["texto"] or "").strip():
            self._salvar()
        self.editando = None
        self.recarregar()

    async def _corrigir_com_chave(self):
        app, ed = self.app, self.editando
        if discursiva.contar(ed["texto"])["palavras"] < 40:
            app.msg("Escreva pelo menos uns 40 palavras para a correção valer a pena.")
            return
        if self._salvar() is None:
            return
        self.corrigindo = True
        self.recarregar()
        try:
            correcao = await app.em_segundo_plano(discursiva.corrigir, ed["tema"], ed["texto"], ed["tipo"], app.aj.chave_claude, app.aj["claude_modelo"], ed["limite"])
        except Exception as e:  # noqa: BLE001
            config.registrar(f"discursiva: {e!r}")
            self.corrigindo = False
            self.recarregar()
            app.msg("A correção não veio. Confira a chave em Ajustes → IA e a internet, e tente de novo.")
            return
        self.corrigindo = False
        self._guardar_correcao(correcao, "chave")

    def _guardar_correcao(self, correcao: str, via: str) -> None:
        ed = self.editando
        nota = discursiva.extrair_nota(correcao)
        ed["correcao"], ed["nota"] = correcao, nota
        self.app.db.corrigir_discursiva(ed["id"], correcao, nota, via)
        self.app.db.somar_tempo(min(self._segundos(), 3 * 3600), "app", "Discursiva")  # escrever conta como estudo
        ed["segundos"], ed["inicio"] = 0, time.monotonic()
        self.recarregar()
        if nota is not None:
            self.app.msg(f"Nota {nota:g} de 10. " + ("Muito bom!" if nota >= 8 else "Veja as melhorias prioritárias no fim da correção."))

    def _dialogo_colar(self) -> None:
        app, c = self.app, self.app.c
        if self._salvar(avisar=True) is None:
            return
        campo = ft.TextField(multiline=True, min_lines=8, max_lines=16, border_radius=10, label="Correção recebida no chat",
                             hint_text="Cole aqui a resposta inteira do Claude ou do ChatGPT (a nota é lida do começo).", text_size=13.5)

        def guardar(e):
            if not (campo.value or "").strip():
                return
            app.page.pop_dialog()
            self._guardar_correcao(campo.value.strip(), "chat")

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Colar a correção", font_family=FONTE_TITULO),
                content=ft.Container(ft.Column([campo], tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH), width=min(640, (app.page.width or 700) - 60)),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Guardar", guardar, ft.Icons.CHECK)],
            )
        )
