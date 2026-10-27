"""Fazer a prova: questões com cartão-resposta, ajuda, voz, cronômetro e resultado."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from pathlib import Path

import flet as ft

from .. import ajuda, config, pdfprova
from . import comp
from .tema import FONTE_TEXTO, FONTE_TITULO


def _fmt_tempo(seg: int) -> str:
    h, r = divmod(int(seg), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class TelaProva:
    conta_tempo = True  # o relógio de estudo do app soma o tempo enquanto esta tela está aberta

    def __init__(self, app, prova: dict, modo: str):
        self.app = app
        self.prova = prova
        self.modo = modo  # simulado | estudo | revisao
        self.modo_original = modo
        self._confirmou = False
        self.questoes = app.db.questoes(prova["id"])
        self.cartao = prova["modo"] == "cartao" or not any((q.get("enunciado") or "").strip() for q in self.questoes)
        self.respostas: dict[int, str] = {}
        self.marcadas: set[int] = set()
        self.reveladas: set[int] = set()
        self.idx = 0
        self.inicio = time.time()
        self.finalizada = False
        self.resultado: dict | None = None
        self.ajuda_aberta = False
        self.ajuda_corpo = ft.Column(spacing=12)
        self.ajuda_numero: int | None = None
        self.mostrar_texto_base = True
        self.pagina_pdf = 0
        self.zoom = 1.0
        self.total_paginas = int(prova.get("paginas") or 0)
        self.falando = False
        self.raiz = ft.Container(expand=True)
        self.relogio = ft.Text("00:00", size=16, weight=ft.FontWeight.W_700)
        self._ativo = True
        self._digitando = False  # campo de dúvida em uso: as teclas A-E não respondem a questão
        self.tentativa_id = app.db.iniciar_tentativa(prova["id"], "estudo" if modo == "revisao" else modo)
        app.marcar_atividade()

    def disciplina_atual(self) -> str:
        q = self.q
        return (q.get("disciplina") or "") if q else ""

    # ================================================================ util

    @property
    def c(self) -> dict:
        return self.app.c

    @property
    def q(self) -> dict | None:
        return self.questoes[self.idx] if self.questoes else None

    def _escala(self) -> float:
        return float(self.app.aj["fonte_escala"] or 1.0)

    def _estilo_leitura(self, tamanho: float) -> dict:
        return {
            "size": tamanho * self._escala(),
            "font_family": FONTE_TEXTO,
            "color": self.c["texto"],
            "style": ft.TextStyle(height=float(self.app.aj["entrelinha"] or 1.55)),
        }

    def _corrigida(self, numero: int) -> bool:
        return self.modo == "revisao" or self.finalizada or numero in self.reveladas

    def _gab(self, q: dict) -> str | None:
        g = q.get("gabarito")
        return g if g and g != "?" else None

    # ================================================================ ciclo de vida

    def build(self) -> ft.Control:
        self._render()
        return self.raiz

    def ao_mostrar(self):
        self._ativo = True
        if self.modo == "simulado":
            self.app.page.run_task(self._cronometro)
        if self.cartao and not self.questoes:
            self._pedir_total()
        if self.cartao and self.prova.get("pdf_prova"):
            self.app.page.run_task(self._carregar_pagina)

    async def _cronometro(self):
        while self._ativo and not self.finalizada:
            self.relogio.value = _fmt_tempo(time.time() - self.inicio)
            try:
                self.relogio.update()
            except Exception:  # noqa: BLE001 - controle fora da tela
                pass
            await asyncio.sleep(1)

    def _sair(self, e=None):
        def confirmar(ev=None):
            if ev is not None:
                self.app.page.pop_dialog()
            self._ativo = False
            self.app.leitor.parar()
            self.app.fechar_foco("estudar")

        if self.finalizada or self.modo == "revisao" or not self.respostas:
            confirmar()
            return
        self.app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Sair da prova?"),
                content=ft.Text("Suas respostas desta tentativa não serão corrigidas.", size=15),
                actions=[
                    ft.TextButton("Continuar a prova", on_click=lambda ev: self.app.page.pop_dialog()),
                    ft.TextButton("Sair", on_click=confirmar),
                ],
            )
        )

    # ================================================================ render

    def _render(self):
        if self.resultado is not None and self.modo != "revisao":
            self.raiz.content = self._tela_resultado()
            return
        app, c = self.app, self.c
        cabecalho = self._cabecalho()
        principal = self._principal_cartao() if self.cartao else self._principal_questao()
        if app.largo:
            lateral = self._painel_ajuda() if self.ajuda_aberta else self._painel_cartao()
            corpo = ft.Row(
                [
                    ft.Container(principal, expand=True, padding=ft.Padding.only(left=36, right=28, top=22)),
                    ft.Container(
                        lateral,
                        width=340 if self.ajuda_aberta else 300,
                        bgcolor=c["sup"],
                        border=ft.Border.only(left=ft.BorderSide(1, c["borda"])),
                        padding=20,
                    ),
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        else:
            corpo = ft.Container(principal, expand=True, padding=ft.Padding.only(left=14, right=14, top=14))
        self.raiz.content = ft.Column([cabecalho, corpo], spacing=0, expand=True)
        self.raiz.bgcolor = c["bg"]

    def _atualizar(self):
        self._render()
        self.app.page.update()

    # ---------------------------------------------------------------- cabeçalho

    def _cabecalho(self) -> ft.Control:
        app, c = self.app, self.c
        if self.modo == "simulado" and not self.finalizada:
            selo = ft.Row([ft.Icon(ft.Icons.TIMER_OUTLINED, size=18, color=c["tinta"]), self.relogio], spacing=6, tight=True)
            self.relogio.color = c["texto"]
        elif self.modo == "revisao":
            selo = comp.pilula("Revisão", c["ok_suave"], c["ok"], ft.Icons.FACT_CHECK_OUTLINED)
        else:
            selo = comp.pilula("Modo estudo", c["tinta_suave"], c["tinta"], ft.Icons.LIGHTBULB_OUTLINE)
        acoes: list[ft.Control] = [
            ft.IconButton(ft.Icons.TEXT_DECREASE, tooltip="Diminuir letra", on_click=lambda e: self._fonte(-0.1), icon_color=c["texto2"]),
            ft.IconButton(ft.Icons.TEXT_INCREASE, tooltip="Aumentar letra", on_click=lambda e: self._fonte(0.1), icon_color=c["texto2"]),
            ft.IconButton(
                ft.Icons.AUTO_STORIES if app.aj["tema"] == "sepia" else ft.Icons.AUTO_STORIES_OUTLINED,
                tooltip="Modo leitura (sépia)",
                on_click=self._alternar_sepia,
                icon_color=c["tinta"] if app.aj["tema"] == "sepia" else c["texto2"],
            ),
        ]
        if app.tem_voz and not self.cartao:
            acoes.append(
                ft.IconButton(
                    ft.Icons.STOP_CIRCLE_OUTLINED if self.falando else ft.Icons.VOLUME_UP_OUTLINED,
                    tooltip="Parar leitura" if self.falando else "Ouvir a questão",
                    on_click=self._voz,
                    icon_color=c["tinta"] if self.falando else c["texto2"],
                )
            )
        if not app.largo:
            acoes.append(ft.IconButton(ft.Icons.GRID_VIEW_ROUNDED, tooltip="Cartão-resposta", on_click=self._cartao_celular, icon_color=c["texto2"]))
        titulo = ft.Column(
            [
                ft.Text(self.prova["titulo"], size=18 if app.largo else 15.5, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                selo,
            ],
            spacing=2,
            expand=True,
        )
        return ft.Container(
            ft.Row(
                [ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Sair da prova", on_click=self._sair), titulo, *acoes],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=8 if app.largo else 2, right=12, top=10, bottom=10),
            bgcolor=c["sup"],
            border=ft.Border.only(bottom=ft.BorderSide(1, c["borda"])),
        )

    def _fonte(self, delta: float):
        novo = round(min(1.8, max(0.8, self._escala() + delta)), 2)
        self.app.aj.set("fonte_escala", novo)
        self._atualizar()

    def _alternar_sepia(self, e):
        app = self.app
        anterior = app.aj.get("tema_antes_sepia") or "claro"
        if app.aj["tema"] == "sepia":
            novo = anterior
        else:
            app.aj.set("tema_antes_sepia", app.aj["tema"])
            novo = "sepia"
        app.aj.set("tema", novo)
        from . import tema

        tema.aplicar(app.page, novo)
        app.telas.clear()
        app.montar()

    # ---------------------------------------------------------------- questão

    def _principal_questao(self) -> ft.Control:
        app, c, q = self.app, self.c, self.q
        if q is None:
            return comp.vazio(ft.Icons.ERROR_OUTLINE, "Prova sem questões", "Não encontrei questões nesta prova.", c)
        n = q["numero"]
        total = len(self.questoes)
        corrigida = self._corrigida(n)
        gab = self._gab(q)
        resp = self.respostas.get(n)
        topo = ft.Row(
            [
                ft.Text(f"Questão {n}", size=26, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                comp.apagado(f"de {total}", c, 15),
                ft.Container(expand=True),
                comp.pilula(q.get("disciplina") or "Geral", c["sup2"], c["texto2"]),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )
        blocos: list[ft.Control] = [topo]
        if q.get("fonte"):
            blocos.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME if "IA" in q["fonte"] else ft.Icons.HISTORY_EDU, size=16, color=c["texto2"]),
                        comp.apagado(q["fonte"], c, 13),
                    ],
                    spacing=6,
                )
            )
        if n in self.marcadas:
            blocos.append(comp.pilula("Marcada para revisar", c["marca_suave"], c["marca"], ft.Icons.FLAG_ROUNDED))
        if (q.get("texto_base") or "").strip():
            blocos.append(self._texto_base(q))
        enunciado = (q.get("enunciado") or "").strip() or "(Enunciado não lido do PDF. Use “Ver na prova original”.)"
        blocos.append(ft.Text(enunciado, selectable=True, **self._estilo_leitura(18)))
        alts = q.get("alternativas") or {}
        if q.get("tipo") == "CE" and not alts:
            alts = {"C": "Certo", "E": "Errado"}
        lista_alts = ft.Column(spacing=8)
        for letra, txt in alts.items():
            estado = None
            if corrigida and gab:
                if letra == gab or gab == "*":
                    estado = "certa" if resp == letra else "gabarito"
                elif letra == resp:
                    estado = "errada"
            sel = resp == letra
            fundo = None
            if estado in ("certa", "gabarito"):
                fundo = c["ok_suave"]
            elif estado == "errada":
                fundo = c["erro_suave"]
            elif sel:
                fundo = c["tinta_suave"]
            lista_alts.controls.append(
                ft.Container(
                    ft.Row(
                        [
                            comp.bolha(letra, c, marcada=sel, estado=estado, tamanho=int(36 * min(1.25, self._escala()))),
                            ft.Container(ft.Text(txt, **self._estilo_leitura(16.5)), expand=True, padding=ft.Padding.only(top=5)),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border_radius=12,
                    bgcolor=fundo,
                    border=ft.Border.all(1, c["tinta"] if sel and not estado else "transparent"),
                    on_click=None if (corrigida and self.modo != "simulado") or self.finalizada else (lambda e, L=letra: self.responder(L)),
                    ink=not corrigida,
                )
            )
        blocos.append(lista_alts)
        if corrigida:
            blocos.append(self._feedback(q, resp, gab))
        if self.prova.get("pdf_prova") and Path(self.prova["pdf_prova"]).exists():
            blocos.append(
                comp.botao_texto(f"Ver na prova original (página {int(q.get('pagina') or 0) + 1})", lambda e: self._ver_pagina(q), ft.Icons.REMOVE_RED_EYE_OUTLINED)
            )
        conteudo = ft.Container(ft.Column(blocos, spacing=18), width=780 if app.largo else None)
        rolagem = ft.Column([conteudo, ft.Container(height=20)], scroll=ft.ScrollMode.AUTO, expand=True)
        return ft.Column([rolagem, self._barra_acoes()], spacing=0, expand=True)

    def _texto_base(self, q: dict) -> ft.Control:
        c = self.c
        cab = ft.Row(
            [
                ft.Icon(ft.Icons.ARTICLE_OUTLINED, size=18, color=c["texto2"]),
                comp.apagado("Texto de apoio", c, 14),
                ft.Container(expand=True),
                comp.botao_texto("Esconder" if self.mostrar_texto_base else "Mostrar", self._alternar_texto_base),
            ],
            spacing=8,
        )
        filhos: list[ft.Control] = [cab]
        if self.mostrar_texto_base:
            filhos.append(ft.Text(q["texto_base"], selectable=True, **self._estilo_leitura(16.5)))
        return ft.Container(ft.Column(filhos, spacing=6), bgcolor=c["sup2"], border_radius=12, padding=ft.Padding.only(left=18, right=10, top=8, bottom=16))

    def _alternar_texto_base(self, e):
        self.mostrar_texto_base = not self.mostrar_texto_base
        self._atualizar()

    def _feedback(self, q: dict, resp: str | None, gab: str | None) -> ft.Control:
        c = self.c
        if not gab:
            return comp.aviso("Esta questão está sem gabarito. Use a ajuda para conferir a resposta.", c, "alerta")
        if gab == "*":
            caixa = comp.aviso("Questão anulada pela banca: conta ponto para todos.", c, "info")
        elif resp == gab:
            caixa = comp.aviso(f"Você acertou. Resposta: {gab}.", c, "ok")
        elif resp:
            caixa = comp.aviso(f"Resposta correta: {gab}. Você marcou {resp}.", c, "erro")
        else:
            caixa = comp.aviso(f"Resposta correta: {gab}.", c, "info")
        filhos = [caixa]
        if q.get("explicacao"):
            filhos.append(ft.Container(ft.Text(q["explicacao"], selectable=True, **self._estilo_leitura(15.5)), padding=ft.Padding.only(left=4)))
        filhos.append(comp.botao_texto("Por que é essa? Pesquisar explicação", lambda e: self.abrir_ajuda("explicacao"), ft.Icons.TRAVEL_EXPLORE))
        return ft.Column(filhos, spacing=8)

    def _barra_acoes(self) -> ft.Control:
        app, c, q = self.app, self.c, self.q
        n = q["numero"] if q else 0
        ultima = self.idx >= len(self.questoes) - 1
        marcar = ft.IconButton(
            ft.Icons.FLAG_ROUNDED if n in self.marcadas else ft.Icons.FLAG_OUTLINED,
            tooltip="Marcar para revisar (M)",
            icon_color=c["marca"] if n in self.marcadas else c["texto2"],
            on_click=lambda e: self._marcar(),
        )
        ajuda_btn = comp.botao_contorno("Ajuda", lambda e: self.abrir_ajuda("dica"), ft.Icons.LIGHTBULB_OUTLINE) if app.largo else ft.IconButton(
            ft.Icons.LIGHTBULB_OUTLINE, tooltip="Ajuda", on_click=lambda e: self.abrir_ajuda("dica"), icon_color=c["tinta"]
        )
        anterior = ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, tooltip="Anterior (←)", on_click=lambda e: self.ir_para(self.idx - 1), disabled=self.idx == 0)
        if self.modo == "revisao" or self.finalizada:
            proxima = comp.botao("Próxima", lambda e: self.ir_para(self.idx + 1), ft.Icons.ARROW_FORWARD_ROUNDED, disabled=ultima)
            fim = comp.botao_contorno("Ver resultado", lambda e: self._ver_resultado()) if self.resultado else ft.Container()
            direita = ft.Row([fim, proxima], spacing=8, tight=True)
        elif ultima:
            direita = comp.botao("Finalizar prova", self.finalizar, ft.Icons.CHECK_ROUNDED)
        else:
            direita = comp.botao("Próxima", lambda e: self.ir_para(self.idx + 1), ft.Icons.ARROW_FORWARD_ROUNDED)
        return ft.Container(
            ft.Row([anterior, marcar, ajuda_btn, ft.Container(expand=True), direita], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=12),
            border=ft.Border.only(top=ft.BorderSide(1, c["borda"])),
        )

    # ---------------------------------------------------------------- interações

    def responder(self, letra: str):
        q = self.q
        if q is None or self.finalizada:
            return
        n = q["numero"]
        if self.modo == "estudo" and n in self.reveladas:
            return
        self.app.marcar_atividade()
        self.respostas[n] = letra
        if self.modo == "estudo":
            self.reveladas.add(n)
            gab = self._gab(q)
            correta = None if not gab else (gab == "*" or gab == letra)
            self.app.db.registrar_resposta(self.tentativa_id, n, q.get("disciplina") or "Geral", letra, correta, q.get("ref") or "")
            self.app.db.revisao_registrar(self.prova["id"], n, q.get("disciplina") or "Geral", correta, q.get("ref") or "")
        self._atualizar()

    def ir_para(self, idx: int):
        self.app.marcar_atividade()
        if not self.questoes:
            return
        idx = max(0, min(len(self.questoes) - 1, idx))
        if idx != self.idx:
            self.idx = idx
            self.app.leitor.parar()
            self.falando = False
            if self.ajuda_aberta and not self.app.largo:
                self.ajuda_aberta = False
            if self.ajuda_aberta:
                self.abrir_ajuda("dica", atualizar=False)
            if self.cartao:
                q = self.q
                pagina = int(q.get("pagina") or 0) if q else 0
                if pagina and pagina != self.pagina_pdf:
                    self.pagina_pdf = pagina
                    self.app.page.run_task(self._carregar_pagina)
        self._atualizar()

    def _marcar(self):
        q = self.q
        if q:
            self.marcadas ^= {q["numero"]}
            if q["numero"] in self.marcadas and (q.get("enunciado") or "").strip():
                self.app.db.revisao_adicionar(self.prova["id"], q["numero"], q.get("disciplina") or "Geral", q.get("ref") or "")
            self._atualizar()

    def tecla(self, e: ft.KeyboardEvent):
        if self._digitando:
            return
        if self.resultado is not None and self.modo != "revisao":
            return
        k = (e.key or "").upper()
        if e.ctrl or e.alt or e.meta:
            return
        if k in ("ARROW RIGHT", "PAGE DOWN"):
            self.ir_para(self.idx + 1)
        elif k in ("ARROW LEFT", "PAGE UP"):
            self.ir_para(self.idx - 1)
        elif k == "M":
            self._marcar()
        elif k == "H":
            self.abrir_ajuda("dica")
        elif len(k) == 1 and self.q and not self.cartao:
            alts = self.q.get("alternativas") or ({"C": "", "E": ""} if self.q.get("tipo") == "CE" else {})
            if k in alts and not self._corrigida(self.q["numero"]):
                self.responder(k)

    # ---------------------------------------------------------------- voz

    def _voz(self, e=None):
        app = self.app
        if self.falando:
            app.leitor.parar()
            self.falando = False
            self._atualizar()
            return
        q = self.q
        if not q:
            return
        partes = [f"Questão {q['numero']}."]
        if q.get("texto_base") and self.mostrar_texto_base:
            partes.append("Texto de apoio. " + q["texto_base"])
        partes.append(q.get("enunciado") or "")
        for letra, txt in (q.get("alternativas") or {}).items():
            partes.append(f"Alternativa {letra}: {txt}.")
        ok = app.leitor.falar("\n".join(partes), int(app.aj["voz_velocidade"] or 0), ao_terminar=lambda: app.page.run_task(self._voz_terminou))
        if not ok:
            comp.mensagem(app.page, "Não encontrei uma voz no sistema para ler em voz alta.")
            return
        self.falando = True
        self._atualizar()

    async def _voz_terminou(self):
        if self.falando:
            self.falando = False
            if self._ativo:
                self._atualizar()

    # ---------------------------------------------------------------- cartão-resposta lateral

    def _estado_numero(self, q: dict) -> tuple[str, str, str]:
        """(fundo, cor_texto, borda) do número no cartão-resposta."""
        c = self.c
        n = q["numero"]
        resp = self.respostas.get(n)
        gab = self._gab(q)
        if self._corrigida(n) and gab and resp:
            ok = gab == "*" or gab == resp
            return (c["ok"] if ok else c["erro"], c["sup"], c["ok"] if ok else c["erro"])
        if resp:
            return (c["tinta"], c["sobre_tinta"], c["tinta"])
        return (c["sup"], c["texto2"], c["borda"])

    def _grade_numeros(self, ao_clicar) -> ft.Control:
        c = self.c
        itens = []
        for i, q in enumerate(self.questoes):
            fundo, cor, borda = self._estado_numero(q)
            atual = i == self.idx
            marc = q["numero"] in self.marcadas
            itens.append(
                ft.Container(
                    ft.Text(str(q["numero"]), size=13, weight=ft.FontWeight.W_700, color=cor),
                    width=40,
                    height=40,
                    shape=ft.BoxShape.CIRCLE,
                    bgcolor=fundo,
                    alignment=ft.Alignment.CENTER,
                    border=ft.Border.all(3 if atual else (2 if marc else 1.2), c["marca"] if marc and not atual else (c["texto"] if atual else borda)),
                    on_click=lambda e, i=i: ao_clicar(i),
                    tooltip=("Marcada para revisar" if marc else None),
                )
            )
        return ft.Row(itens, wrap=True, spacing=8, run_spacing=8)

    def _painel_cartao(self) -> ft.Control:
        c = self.c
        if self.cartao:
            return self._folha_resposta()
        respondidas = len(self.respostas)
        total = len(self.questoes)
        legenda = ft.Column(
            [
                ft.Row([ft.Container(width=14, height=14, shape=ft.BoxShape.CIRCLE, bgcolor=c["tinta"]), comp.apagado("respondida", c, 13)], spacing=8),
                ft.Row([ft.Container(width=14, height=14, shape=ft.BoxShape.CIRCLE, border=ft.Border.all(2, c["marca"])), comp.apagado("marcada para revisar", c, 13)], spacing=8),
            ]
            + (
                [ft.Row([ft.Container(width=14, height=14, shape=ft.BoxShape.CIRCLE, bgcolor=c["ok"]), comp.apagado("certa", c, 13), ft.Container(width=14, height=14, shape=ft.BoxShape.CIRCLE, bgcolor=c["erro"]), comp.apagado("errada", c, 13)], spacing=8)]
                if self.modo != "simulado" or self.finalizada
                else []
            ),
            spacing=6,
        )
        filhos: list[ft.Control] = [
            ft.Text("Cartão-resposta", size=19, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
            comp.apagado(f"{respondidas} de {total} respondidas", c, 13.5),
            comp.barra(respondidas / total if total else 0, c, altura=6),
            self._grade_numeros(self.ir_para),
            legenda,
        ]
        if not self.finalizada and self.modo != "revisao":
            filhos.append(comp.botao("Finalizar prova", self.finalizar, ft.Icons.CHECK_ROUNDED, width=260))
        filhos.append(comp.apagado("Atalhos: A a E responde, ← → navega, M marca, H abre a ajuda.", c, 12.5))
        return ft.Column(filhos, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _cartao_celular(self, e=None):
        def clicar(i):
            self.app.page.pop_dialog()
            self.ir_para(i)

        c = self.c
        conteudo = ft.Column(
            [
                ft.Text("Cartão-resposta", size=20, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600),
                comp.apagado(f"{len(self.respostas)} de {len(self.questoes)} respondidas", c, 13.5),
                self._grade_numeros(clicar) if not self.cartao else self._folha_resposta(),
            ]
            + ([comp.botao("Finalizar prova", lambda e: (self.app.page.pop_dialog(), self.app.page.run_task(self.finalizar)), ft.Icons.CHECK_ROUNDED)] if not self.finalizada and self.modo != "revisao" else []),
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
        )
        self.app.page.show_dialog(ft.BottomSheet(ft.Container(conteudo, padding=20), show_drag_handle=True, scrollable=True, bgcolor=c["sup"]))

    # ---------------------------------------------------------------- modo cartão (PDF + folha de respostas)

    def _pedir_total(self):
        c = self.c
        campo = ft.TextField(label="Quantas questões tem a prova?", value="50", width=260, keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)

        def ok(e):
            v = (campo.value or "").strip()
            if not v.isdigit() or not (1 <= int(v) <= 300):
                campo.error = "Digite um número de 1 a 300"
                campo.update()
                return
            self.app.db.garantir_questoes(self.prova["id"], int(v))
            self.questoes = self.app.db.questoes(self.prova["id"])
            self.app.page.pop_dialog()
            self._atualizar()

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Cartão-resposta"),
                content=ft.Column(
                    [comp.apagado("Não consegui ler o texto deste PDF, então você responde num cartão ao lado das páginas originais.", c, 14.5), campo],
                    tight=True,
                    spacing=12,
                    width=380,
                ),
                actions=[ft.TextButton("Voltar", on_click=lambda e: (self.app.page.pop_dialog(), self._sair())), ft.FilledButton("Começar", on_click=ok)],
            )
        )

    def _imagem_pagina(self) -> ft.Control:
        c = self.c
        caminho = self._caminho_pagina(self.pagina_pdf)
        largura_util = self.app.largura - (300 + 90 if self.app.largo else 40)
        largura = max(320, largura_util * self.zoom)
        if caminho and caminho.exists():
            img: ft.Control = ft.Column(
                [
                    ft.Row(
                        [ft.Image(src=caminho.read_bytes(), width=largura, fit=ft.BoxFit.FIT_WIDTH)],
                        scroll=ft.ScrollMode.AUTO if self.zoom > 1 else None,
                        alignment=ft.MainAxisAlignment.CENTER,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        else:
            img = ft.Container(comp.carregando("Abrindo a página…", c), alignment=ft.Alignment.CENTER, expand=True)
        nav = ft.Row(
            [
                ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Página anterior", on_click=lambda e: self._mudar_pagina(-1), disabled=self.pagina_pdf <= 0),
                comp.apagado(f"Página {self.pagina_pdf + 1} de {self.total_paginas or '?'}", c, 14),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="Próxima página",
                    on_click=lambda e: self._mudar_pagina(1),
                    disabled=bool(self.total_paginas) and self.pagina_pdf >= self.total_paginas - 1,
                ),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.ZOOM_OUT, tooltip="Diminuir zoom", on_click=lambda e: self._zoom(-0.25), disabled=self.zoom <= 0.5),
                comp.apagado(f"{self.zoom * 100:.0f}%", c, 13),
                ft.IconButton(ft.Icons.ZOOM_IN, tooltip="Aumentar zoom", on_click=lambda e: self._zoom(0.25), disabled=self.zoom >= 2.5),
            ],
            spacing=4,
        )
        return ft.Column(
            [nav, ft.Container(img, expand=True, bgcolor=c["sup"], border_radius=8, border=ft.Border.all(1, c["borda"]), padding=6)],
            spacing=6,
            expand=True,
        )

    def _zoom(self, delta: float):
        self.zoom = round(min(2.5, max(0.5, self.zoom + delta)), 2)
        self._atualizar()

    def _principal_cartao(self) -> ft.Control:
        if not self.prova.get("pdf_prova"):
            return comp.vazio(ft.Icons.PICTURE_AS_PDF_OUTLINED, "PDF não encontrado", "Importe a prova de novo pela aba Estudar.", self.c)
        if self.app.largo:
            return ft.Container(self._imagem_pagina(), padding=ft.Padding.only(bottom=16), expand=True)
        acoes = ft.Row(
            [comp.botao_contorno("Responder", self._cartao_celular, ft.Icons.GRID_VIEW_ROUNDED), ft.Container(expand=True)]
            + ([comp.botao("Finalizar", self.finalizar, ft.Icons.CHECK_ROUNDED)] if not self.finalizada else [comp.botao("Resultado", lambda e: self._ver_resultado())]),
        )
        return ft.Column([ft.Container(self._imagem_pagina(), expand=True), ft.Container(acoes, padding=ft.Padding.symmetric(vertical=10))], expand=True)

    def _folha_resposta(self) -> ft.Control:
        c = self.c
        linhas = []
        for q in self.questoes:
            n = q["numero"]
            letras = "CE" if q.get("tipo") == "CE" else "ABCDE"
            resp = self.respostas.get(n)
            gab = self._gab(q)
            bolhas = []
            for L in letras:
                estado = None
                if self.finalizada and gab:
                    if L == gab or gab == "*":
                        estado = "certa" if resp == L else "gabarito"
                    elif L == resp:
                        estado = "errada"
                bolhas.append(
                    comp.bolha(
                        L,
                        c,
                        marcada=resp == L,
                        estado=estado,
                        tamanho=30,
                        on_click=None if self.finalizada else (lambda e, n=n, L=L: self._marcar_folha(n, L)),
                    )
                )
            linhas.append(
                ft.Row(
                    [ft.Container(ft.Text(f"{n:02d}", size=14, weight=ft.FontWeight.W_700, color=c["texto2"]), width=30), *bolhas],
                    spacing=6,
                )
            )
        cab: list[ft.Control] = [
            ft.Text("Cartão-resposta", size=19, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
            comp.apagado(f"{len(self.respostas)} de {len(self.questoes)} marcadas", c, 13.5),
        ]
        if not self.finalizada and self.app.largo:
            cab.append(comp.botao("Finalizar prova", self.finalizar, ft.Icons.CHECK_ROUNDED, width=250))
        elif self.finalizada and self.app.largo:
            cab.append(comp.botao("Ver resultado", lambda e: self._ver_resultado()))
        return ft.Column(cab + [ft.Column(linhas, spacing=6)], spacing=12, scroll=ft.ScrollMode.AUTO if self.app.largo else None)

    def _marcar_folha(self, n: int, letra: str):
        if self.respostas.get(n) == letra:
            self.respostas.pop(n)
        else:
            self.respostas[n] = letra
        self._atualizar()
        if not self.app.largo:
            # reabre o cartão atualizado no celular
            self.app.page.pop_dialog()
            self._cartao_celular()

    def _caminho_pagina(self, indice: int) -> Path | None:
        pdf = self.prova.get("pdf_prova")
        if not pdf:
            return None
        return Path(pdf).parent / "paginas" / f"p{indice + 1:03d}.png"

    async def _carregar_pagina(self):
        destino = self._caminho_pagina(self.pagina_pdf)
        if destino is None:
            return
        if not destino.exists():
            try:
                await self.app.em_segundo_plano(pdfprova.renderizar_pagina, Path(self.prova["pdf_prova"]), self.pagina_pdf, destino, 120)
            except Exception as ex:  # noqa: BLE001
                comp.mensagem(self.app.page, f"Não consegui abrir a página ({ex}).")
                return
        if not self.total_paginas:
            self.total_paginas = await self.app.em_segundo_plano(pdfprova.contar_paginas, Path(self.prova["pdf_prova"]))
        if self._ativo:
            self._atualizar()

    def _mudar_pagina(self, delta: int):
        novo = self.pagina_pdf + delta
        if novo < 0 or (self.total_paginas and novo >= self.total_paginas):
            return
        self.pagina_pdf = novo
        self._atualizar()
        self.app.page.run_task(self._carregar_pagina)

    def _ver_pagina(self, q: dict):
        """Mostra a página do PDF onde a questão está (figuras, tabelas)."""
        indice = int(q.get("pagina") or 0)
        destino = self._caminho_pagina(indice)
        c = self.c
        conteudo = ft.Container(comp.carregando("Abrindo a página…", c), width=min(760, (self.app.page.width or 800) - 60), height=min(820, (self.app.page.height or 800) - 160))
        self.app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Página {indice + 1} da prova original", size=18),
                content=conteudo,
                actions=[ft.TextButton("Fechar", on_click=lambda e: self.app.page.pop_dialog())],
            )
        )

        async def carregar():
            if not destino.exists():
                await self.app.em_segundo_plano(pdfprova.renderizar_pagina, Path(self.prova["pdf_prova"]), indice, destino, 130)
            conteudo.content = ft.InteractiveViewer(ft.Image(src=destino.read_bytes(), fit=ft.BoxFit.FIT_WIDTH), min_scale=0.8, max_scale=4)
            conteudo.update()

        self.app.page.run_task(carregar)

    # ---------------------------------------------------------------- ajuda

    def abrir_ajuda(self, modo: str = "dica", atualizar: bool = True):
        q = self.q
        if q is None or self.cartao:
            return
        self.ajuda_aberta = True
        self.ajuda_numero = q["numero"]
        self.ajuda_corpo.controls = [comp.carregando("Pesquisando na internet…", self.c)]
        if self.app.largo:
            if atualizar:
                self._atualizar()
        else:
            self._abrir_ajuda_celular()
        self.app.page.run_task(self._buscar_ajuda, q, modo)

    def _abrir_ajuda_celular(self):
        c = self.c
        conteudo = ft.Column(
            [
                ft.Row(
                    [ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=c["tinta"]), ft.Text("Ajuda nesta questão", size=19, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600)],
                    spacing=8,
                ),
                self.ajuda_corpo,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

        def fechou(e):
            self.ajuda_aberta = False

        self.app.page.show_dialog(
            ft.BottomSheet(ft.Container(conteudo, padding=20), show_drag_handle=True, scrollable=True, bgcolor=c["sup"], on_dismiss=fechou)
        )

    async def _buscar_ajuda(self, q: dict, modo: str):
        app, c = self.app, self.c
        resp = self.respostas.get(q["numero"])
        dados = await app.em_segundo_plano(ajuda.obter_ajuda, q, modo, app.aj, app.db, resp)
        if self.ajuda_numero != q["numero"] or not self.ajuda_aberta:
            return
        filhos: list[ft.Control] = []
        filhos.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.TRAVEL_EXPLORE, size=16, color=c["texto2"]),
                    ft.Container(comp.apagado(f"Pesquisei na internet: {dados['consulta']}", c, 12.5), expand=True),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
        if dados.get("aviso"):
            filhos.append(comp.aviso(dados["aviso"], c, "alerta"))
        filhos.append(
            ft.Markdown(
                dados["texto"],
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                on_tap_link=self._abrir_link,
            )
        )
        if dados.get("fontes"):
            filhos.append(comp.apagado("Fontes", c, 13))
            for f in dados["fontes"][:6]:
                filhos.append(
                    ft.Container(
                        ft.Row(
                            [ft.Icon(ft.Icons.OPEN_IN_NEW, size=15, color=c["tinta"]), ft.Text(f["titulo"], size=13.5, color=c["tinta"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, expand=True)],
                            spacing=8,
                        ),
                        url=f["url"],
                        padding=ft.Padding.symmetric(vertical=4),
                        tooltip=f["url"],
                    )
                )
        # continuar a conversa no chat do Claude ou do ChatGPT (funciona sem chave, com a conta da pessoa)
        from .. import chat_ia
        from .chat import botoes_chat, dialogo_chave

        sem_spoiler = modo == "dica" or (self.modo == "simulado" and not self.finalizada)
        filhos.append(comp.apagado("Quer conversar sobre a questão? Abra no chat com a pergunta pronta:", c, 13))
        filhos.append(
            botoes_chat(
                app,
                lambda: chat_ia.pergunta_questao(q, "dica" if modo == "dica" else "explicacao", self.respostas.get(q["numero"]),
                                                 mostrar_gabarito=not sem_spoiler, banca=self.prova.get("banca") or ""),
            )
        )
        if dados.get("via") == "busca" and not app.aj.chave_claude:
            filhos.append(comp.botao_texto("Explicação escrita por IA aqui no app: como ligar (passo a passo)", lambda e: dialogo_chave(app), ft.Icons.KEY_OUTLINED))
        if modo == "dica":
            revela = self.modo == "simulado" and not self.finalizada
            filhos.append(
                comp.botao_contorno(
                    "Explicação completa" + (" (mostra a resposta)" if revela else ""),
                    lambda e: self.abrir_ajuda("explicacao"),
                    ft.Icons.MENU_BOOK_OUTLINED,
                )
            )
        filhos.append(self._caixa_duvida(q))
        self.ajuda_corpo.controls = filhos
        try:
            app.page.update()
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- dúvidas

    def _bloco_resposta(self, d: dict) -> ft.Control:
        c = self.c
        filhos: list[ft.Control] = [
            ft.Container(
                ft.Text(d["pergunta"], size=14.5, color=c["texto"], selectable=True),
                bgcolor=c["tinta_suave"],
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                margin=ft.Margin.only(left=30),
            ),
            ft.Markdown(d["resposta"], selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, on_tap_link=self._abrir_link),
        ]
        for f in (d.get("fontes") or [])[:3]:
            filhos.append(
                ft.Container(
                    ft.Row([ft.Icon(ft.Icons.OPEN_IN_NEW, size=13, color=c["tinta"]), ft.Text(f["titulo"], size=12.5, color=c["tinta"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)], spacing=6),
                    url=f["url"],
                    tooltip=f["url"],
                )
            )
        return ft.Column(filhos, spacing=6)

    def _caixa_duvida(self, q: dict) -> ft.Control:
        app, c = self.app, self.c
        pid, num = app.db._original(self.prova["id"], q["numero"], q.get("ref") or "")
        historico = app.db.duvidas(pid, num)
        lista = ft.Column([self._bloco_resposta(d) for d in historico], spacing=14)

        def foco(valor):
            self._digitando = valor

        campo = ft.TextField(
            hint_text="Ex.: por que a letra B está errada?",
            multiline=True,
            min_lines=1,
            max_lines=4,
            shift_enter=True,
            border_radius=10,
            dense=True,
            expand=True,
            on_focus=lambda e: foco(True),
            on_blur=lambda e: foco(False),
        )

        async def enviar(e=None):
            pergunta = (campo.value or "").strip()
            if not pergunta:
                return
            campo.value = ""
            campo.disabled = True
            espera = ft.Column(
                [
                    ft.Container(ft.Text(pergunta, size=14.5, color=c["texto"]), bgcolor=c["tinta_suave"], border_radius=12,
                                 padding=ft.Padding.symmetric(horizontal=12, vertical=8), margin=ft.Margin.only(left=30)),
                    comp.carregando("Pesquisando para responder…", c),
                ],
                spacing=6,
            )
            lista.controls.append(espera)
            app.page.update()
            app.marcar_atividade()
            dados = await app.em_segundo_plano(ajuda.tirar_duvida, q, pergunta, historico, app.aj)
            d = {"pergunta": pergunta, "resposta": dados["texto"], "fontes": dados["fontes"]}
            app.db.salvar_duvida(pid, num, q.get("disciplina") or "", q.get("enunciado") or "", pergunta, dados["texto"], dados["fontes"], dados["via"])
            historico.append(d)
            lista.controls[-1] = self._bloco_resposta(d)
            if dados.get("aviso"):
                lista.controls.append(comp.apagado(dados["aviso"], c, 12.5))
            campo.disabled = False
            try:
                app.page.update()
            except Exception:  # noqa: BLE001
                pass

        campo.on_submit = enviar
        return ft.Column(
            [
                comp.divisor(c),
                ft.Row([ft.Icon(ft.Icons.QUESTION_ANSWER_OUTLINED, size=20, color=c["tinta"]), comp.texto("Tirar dúvida", c, 16, peso=ft.FontWeight.W_700)], spacing=8),
                comp.apagado("Pergunte o que não ficou claro nesta questão. O Aprova pesquisa na internet para responder.", c, 13),
                lista,
                ft.Row([campo, ft.IconButton(ft.Icons.SEND_ROUNDED, tooltip="Enviar dúvida", icon_color=c["tinta"], on_click=enviar)], spacing=4),
            ],
            spacing=10,
        )

    def _abrir_link(self, e):
        url = e.data if isinstance(e.data, str) else None
        if url:
            import webbrowser

            webbrowser.open(url)

    def _painel_ajuda(self) -> ft.Control:
        c = self.c

        def fechar(e):
            self.ajuda_aberta = False
            self._atualizar()

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=c["tinta"]),
                        ft.Text("Ajuda", size=19, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"], expand=True),
                        ft.IconButton(ft.Icons.CLOSE, tooltip="Voltar ao cartão-resposta", on_click=fechar),
                    ],
                    spacing=8,
                ),
                comp.apagado(f"Questão {self.ajuda_numero}", c, 13),
                self.ajuda_corpo,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

    # ---------------------------------------------------------------- finalizar e resultado

    async def finalizar(self, e=None):
        sem_resposta = [q["numero"] for q in self.questoes if q["numero"] not in self.respostas]
        if sem_resposta and not self._confirmou:
            def confirmar(ev):
                self._confirmou = True
                self.app.page.pop_dialog()
                self.app.page.run_task(self.finalizar)

            self.app.page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Finalizar a prova?"),
                    content=ft.Text(f"Ainda faltam {len(sem_resposta)} questões sem resposta.", size=15),
                    actions=[ft.TextButton("Voltar", on_click=lambda ev: self.app.page.pop_dialog()), ft.FilledButton("Finalizar mesmo assim", on_click=confirmar)],
                )
            )
            return
        self._calcular_resultado()
        self.app.page.run_task(self.app.sincronizar_ranking)
        self.finalizada = True
        self.app.leitor.parar()
        self.falando = False
        self.app.telas.pop("inicio", None)
        self.app.telas.pop("estudar", None)
        self._atualizar()

    def _calcular_resultado(self):
        db = self.app.db
        por_disc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        acertos = total = 0
        erradas = []
        for q in self.questoes:
            n = q["numero"]
            gab = self._gab(q)
            resp = self.respostas.get(n)
            disc = q.get("disciplina") or "Geral"
            if not gab:
                if resp and self.modo != "estudo":
                    db.registrar_resposta(self.tentativa_id, n, disc, resp, None, q.get("ref") or "")
                continue
            correta = gab == "*" or resp == gab
            total += 1
            acertos += int(correta)
            por_disc[disc][1] += 1
            por_disc[disc][0] += int(correta)
            if not correta:
                erradas.append(n)
            if self.modo != "estudo" or n not in self.reveladas:
                db.registrar_resposta(self.tentativa_id, n, disc, resp, correta, q.get("ref") or "")
                if resp:  # em branco não entra na revisão (pode ter sido falta de tempo)
                    db.revisao_registrar(self.prova["id"], n, disc, correta, q.get("ref") or "")
            if n in self.marcadas and (q.get("enunciado") or "").strip():
                # marcou com a bandeira: fica para revisar mesmo se acertou
                db.revisao_adicionar(self.prova["id"], n, disc, q.get("ref") or "")
        duracao = int(time.time() - self.inicio)
        db.finalizar_tentativa(self.tentativa_id, duracao, acertos, total)
        self.resultado = {
            "acertos": acertos,
            "total": total,
            "sem_gabarito": len(self.questoes) - total,
            "duracao": duracao,
            "por_disc": dict(por_disc),
            "erradas": erradas,
            "respondidas": len(self.respostas),
        }

    def _ver_resultado(self):
        self.modo = self.modo_original
        self._atualizar()

    def _revisar(self, apenas_erradas: bool):
        if apenas_erradas and self.resultado and self.resultado["erradas"]:
            alvo = self.resultado["erradas"][0]
            self.idx = next((i for i, q in enumerate(self.questoes) if q["numero"] == alvo), 0)
        else:
            self.idx = 0
        self.modo = "revisao"
        self._atualizar()

    def _ir_para_questao(self, numero: int):
        self.idx = next((i for i, q in enumerate(self.questoes) if q["numero"] == numero), 0)
        self.modo = "revisao"
        self._atualizar()

    def _tela_resultado(self) -> ft.Control:
        from .. import coach

        app, c, r = self.app, self.c, self.resultado
        taxa = r["acertos"] / r["total"] if r["total"] else None
        from .personagem import comemoracao

        numero = ft.Row(
            [
                ft.Text(f"{r['acertos']}", size=84, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["tinta"]),
                ft.Text(f"/{r['total']}", size=36, font_family=FONTE_TITULO, color=c["texto2"]),
            ]
            + ([ft.Container(festa, margin=ft.Margin.only(left=18))] if taxa is not None and (festa := comemoracao(app, taxa)) else []),
            vertical_alignment=ft.CrossAxisAlignment.END,
            spacing=2,
        )
        dados = ft.Row(
            [
                comp.pilula(f"{taxa * 100:.0f}% de acerto" if taxa is not None else "sem correção", c["tinta_suave"], c["tinta"]),
                comp.pilula(f"tempo {_fmt_tempo(r['duracao'])}", c["sup2"], c["texto2"], ft.Icons.TIMER_OUTLINED),
                comp.pilula(f"{r['respondidas']} respondidas", c["sup2"], c["texto2"]),
            ]
            + ([comp.pilula(f"{r['sem_gabarito']} sem gabarito", c["marca_suave"], c["marca"])] if r["sem_gabarito"] else []),
            wrap=True,
            spacing=8,
            run_spacing=8,
        )

        # ---- comentário do professor (sem internet) + próximo passo
        erradas = coach.erradas_por_disciplina(self.questoes, self.respostas, self._gab)
        com = coach.comentar(r)
        acoes_coach: list[ft.Control] = []
        if com["foco"]:
            foco = com["foco"]
            acoes_coach.append(
                comp.botao(f"Treinar {foco}", lambda e, d=foco: app.page.run_task(app.abrir_destino, "treino", d, d), ft.Icons.FITNESS_CENTER)
            )
        if r["erradas"] and not self.cartao:
            acoes_coach.append(comp.botao_contorno("Revisar os erros", lambda e: self._revisar(True), ft.Icons.FACT_CHECK_OUTLINED))
        cartao_coach = ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.EMOJI_EVENTS_OUTLINED if (taxa or 0) >= 0.7 else ft.Icons.TRENDING_UP, color=c["tinta"], size=26),
                         ft.Text(com["titulo"], size=21, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"], expand=True)],
                        spacing=10,
                    ),
                    *[ft.Text(t, size=15, color=c["texto"]) for t in com["paragrafos"]],
                    ft.Row(acoes_coach, wrap=True, spacing=10, run_spacing=8) if acoes_coach else ft.Container(height=0),
                ],
                spacing=10,
            ),
            bgcolor=c["tinta_suave"],
            border_radius=16,
            padding=ft.Padding.symmetric(horizontal=20, vertical=18),
            border=ft.Border.only(left=ft.BorderSide(4, c["tinta"])),
        )

        # ---- análise do professor com IA (quem tem a chave do Claude)
        analise = ft.Column(spacing=8)

        from .. import chat_ia
        from .chat import botoes_chat, menu_chat

        def no_chat() -> list[ft.Control]:
            if not erradas:
                return []
            return [
                comp.apagado("Leve seus erros para uma IA: ela diz o que revisar e monta um plano de 3 dias (abre o chat com tudo pronto).", c, 13.5),
                botoes_chat(app, lambda: chat_ia.pergunta_resultado(r, erradas, self.prova.get("titulo") or ""), "Pedir análise"),
            ]

        def mostrar_analise():
            if getattr(self, "_analise", None):
                analise.controls = [
                    comp.subtitulo("Análise do professor (IA)", c, 18),
                    ft.Markdown(self._analise, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
                ]
            elif app.aj.chave_claude and erradas:
                analise.controls = [
                    comp.botao_contorno("Pedir a análise do professor (IA): assuntos para revisar e plano de 3 dias", pedir_analise, ft.Icons.AUTO_AWESOME)
                ]
            else:
                analise.controls = no_chat()

        async def pedir_analise(e=None):
            from .. import ia

            analise.controls = [comp.carregando("O professor está lendo as suas respostas…", c)]
            analise.update()
            try:
                self._analise = await app.em_segundo_plano(ia.analisar_resultado, r, erradas, app.aj.chave_claude, app.aj["claude_modelo"])
            except Exception as ex:  # noqa: BLE001
                analise.controls = [comp.aviso(f"Não deu para pedir a análise agora ({type(ex).__name__}). Confira a chave do Claude nos Ajustes.", c, "erro")]
                analise.update()
                return
            mostrar_analise()
            analise.update()

        mostrar_analise()

        # ---- por matéria
        disc_linhas: list[ft.Control] = []
        for disc, (a, t) in sorted(r["por_disc"].items(), key=lambda x: x[1][0] / x[1][1] if x[1][1] else 1):
            fr = a / t if t else 0
            disc_linhas.append(
                ft.Column(
                    [
                        ft.Row([comp.texto(disc, c, 15, peso=ft.FontWeight.W_600), ft.Container(expand=True), comp.apagado(f"{a} de {t}", c, 14)]),
                        comp.barra(fr, c, cor=c["ok"] if fr >= 0.7 else (c["marca"] if fr >= 0.5 else c["erro"]), altura=9),
                    ],
                    spacing=6,
                )
            )

        # ---- o que você errou, matéria por matéria
        blocos_erros: list[ft.Control] = []
        for disc, lista in sorted(erradas.items(), key=lambda x: -len(x[1])):
            itens: list[ft.Control] = []
            for e in lista:
                resumo = e["enunciado"][:260] + ("…" if len(e["enunciado"]) > 260 else "")
                linha_resp = [
                    comp.pilula(f"Questão {e['numero']}", c["sup2"], c["texto"], tamanho=11.5),
                    comp.pilula(f"você: {e['sua']}" if e["sua"] else "em branco", c["erro_suave"], c["erro"], tamanho=11.5),
                    comp.pilula(f"certa: {e['certa']}", c["ok_suave"], c["ok"], tamanho=11.5),
                ]
                corpo_item: list[ft.Control] = [
                    ft.Row(linha_resp, spacing=6, wrap=True, run_spacing=6),
                    ft.Text(resumo, size=14, color=c["texto"]),
                ]
                if e["texto_certa"]:
                    corpo_item.append(comp.apagado(f"Resposta certa ({e['certa']}): {e['texto_certa'][:220]}", c, 13.5))
                if e["explicacao"]:
                    corpo_item.append(comp.apagado("Por quê: " + e["explicacao"][:300] + ("…" if len(e["explicacao"]) > 300 else ""), c, 13.5))
                acoes_item: list[ft.Control] = []
                if not self.cartao:
                    acoes_item.append(comp.botao_texto("Ver a questão", lambda ev, n=e["numero"]: self._ir_para_questao(n), ft.Icons.ARROW_FORWARD))
                    q_orig = next((x for x in self.questoes if x["numero"] == e["numero"]), None)
                    if q_orig:
                        acoes_item.append(
                            menu_chat(app, lambda q_=q_orig, sua=e["sua"]: chat_ia.pergunta_questao(q_, "explicacao", sua, banca=self.prova.get("banca") or ""),
                                      "Entender com IA")
                        )
                if acoes_item:
                    corpo_item.append(ft.Row(acoes_item, spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                itens.append(
                    ft.Container(
                        ft.Column(corpo_item, spacing=6),
                        bgcolor=c["sup"],
                        border=ft.Border.all(1, c["borda"]),
                        border_radius=12,
                        padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                    )
                )
            blocos_erros.append(
                ft.Column(
                    [ft.Row([comp.texto(disc, c, 16, peso=ft.FontWeight.W_700), comp.apagado(f"{len(lista)} {'erro' if len(lista) == 1 else 'erros'}", c, 13.5)], spacing=10),
                     ft.Column(itens, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)],
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                )
            )

        botoes = ft.Row(
            [
                comp.botao_contorno("Ver todas as questões", lambda e: self._revisar(False), ft.Icons.LIST_ALT),
                comp.botao_texto("Voltar à biblioteca", lambda e: self._sair()),
            ],
            wrap=True,
            spacing=10,
            run_spacing=10,
        )
        if self.cartao:
            botoes.controls[0] = comp.botao("Ver o cartão corrigido", lambda e: self._revisar(False), ft.Icons.FACT_CHECK_OUTLINED)
        coluna = ft.Column(
            [
                comp.apagado("Resultado", c, 15),
                ft.Text(self.prova["titulo"], size=24 if app.largo else 20, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                numero,
                dados,
                cartao_coach,
                analise,
                botoes,
                ft.Container(height=4),
                comp.subtitulo("Por matéria", c, 20) if disc_linhas else ft.Container(),
                ft.Column(disc_linhas, spacing=16),
                ft.Container(height=8),
                comp.subtitulo("O que você errou", c, 20) if blocos_erros else ft.Container(),
                comp.apagado("Cada uma já está na sua Revisão: ela volta no dia certo até você dominar.", c, 13.5) if blocos_erros else ft.Container(),
                ft.Column(blocos_erros, spacing=18, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ft.Container(height=30),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        return ft.Container(
            ft.Container(coluna, width=760 if app.largo else None, expand=True),
            padding=ft.Padding.only(left=36 if app.largo else 16, right=16, top=28),
            alignment=ft.Alignment.TOP_LEFT if not app.largo else ft.Alignment.TOP_CENTER,
            bgcolor=c["bg"],
            expand=True,
        )
