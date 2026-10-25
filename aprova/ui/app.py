"""Estrutura do app: navegação, tema, layout para computador e celular."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta

import flet as ft

from .. import amostras, config
from ..db import Banco
from ..fontes import Centralizador
from ..pci import ClientePCI
from ..rede import ServidorCelular
from ..voz import Leitor
from . import comp, tema
from .tema import FONTE_TITULO

LARGURA_MINIMA_LATERAL = 900

DESTINOS = [
    ("inicio", "Início", ft.Icons.HOME_OUTLINED, ft.Icons.HOME_ROUNDED),
    ("concursos", "Concursos", ft.Icons.CAMPAIGN_OUTLINED, ft.Icons.CAMPAIGN_ROUNDED),
    ("provas", "Provas", ft.Icons.DESCRIPTION_OUTLINED, ft.Icons.DESCRIPTION_ROUNDED),
    ("estudar", "Estudar", ft.Icons.EDIT_NOTE_OUTLINED, ft.Icons.EDIT_NOTE_ROUNDED),
    ("painel", "Painel", ft.Icons.INSIGHTS_OUTLINED, ft.Icons.INSIGHTS_ROUNDED),
    ("ajustes", "Ajustes", ft.Icons.TUNE_OUTLINED, ft.Icons.TUNE_ROUNDED),
]

INATIVO_S = 8 * 60  # sem tocar no app por mais que isso, o tempo para de contar
TIQUE_S = 30

# Recursos compartilhados entre sessões (no modo celular cada aparelho abre uma sessão)
_BANCO: Banco | None = None
_PCI: ClientePCI | None = None
_CENTRAL: Centralizador | None = None
_SERVIDOR = ServidorCelular()


def _recursos() -> tuple[Banco, ClientePCI, Centralizador]:
    global _BANCO, _PCI, _CENTRAL
    if _BANCO is None:
        config.garantir_pastas()
        _BANCO = Banco()
        amostras.instalar(_BANCO)
    if _PCI is None:
        _PCI = ClientePCI()
    if _CENTRAL is None:
        _CENTRAL = Centralizador(_PCI)
    return _BANCO, _PCI, _CENTRAL


class App:
    def __init__(self, page: ft.Page, modo_web: bool = False):
        self.page = page
        self.modo_web = modo_web or bool(page.web)
        self.aj = config.Ajustes()
        self.db, self.pci, self.central = _recursos()
        self.leitor = Leitor()
        self.servidor = _SERVIDOR
        self.secao = os.environ.get("APROVA_TELA_INICIAL", "inicio")
        self.foco: ft.Control | None = None  # tela em modo foco (prova em andamento)
        self.telas: dict[str, object] = {}
        self._largo: bool | None = None
        self.conteudo = ft.Container(expand=True)
        self._pausa_task = None
        self._ultima_atividade = time.time()
        self._rotulos_crono: list[ft.Text] = []
        self._adiados: dict[int, float] = {}
        from ..ranking import Ranking

        self.ranking = Ranking(self.aj)
        self._ultima_sync = 0.0

    # ------------------------------------------------------------ utilidades

    @property
    def c(self) -> dict:
        return tema.paleta(self.aj["tema"])

    @property
    def largo(self) -> bool:
        return (self.page.width or 1200) >= LARGURA_MINIMA_LATERAL

    @property
    def tem_voz(self) -> bool:
        return not self.modo_web and self.leitor.disponivel

    def msg(self, texto: str) -> None:
        comp.mensagem(self.page, texto)

    def atualizar(self) -> None:
        self.page.update()

    async def em_segundo_plano(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    # ------------------------------------------------------------ início

    def iniciar(self) -> None:
        p = self.page
        p.title = "Aprova · concursos públicos"
        p.fonts = tema.FONTES
        p.padding = 0
        p.spacing = 0
        if not self.modo_web:
            try:
                p.window.min_width = 380
                p.window.min_height = 600
                larg, alt = 1280, 820
                if os.environ.get("APROVA_JANELA"):
                    larg, alt = (int(x) for x in os.environ["APROVA_JANELA"].lower().split("x"))
                p.window.width = larg
                p.window.height = alt
            except Exception:  # noqa: BLE001
                pass
        if not self.modo_web:
            icone = config.ASSETS_DIR / "aprova.ico"
            if icone.exists():
                try:
                    p.window.icon = str(icone)
                except Exception:  # noqa: BLE001
                    pass
        tema.aplicar(p, self.aj["tema"])
        p.on_resize = self._ao_redimensionar
        p.on_keyboard_event = self._teclado
        self._migrar_tempo()
        self.montar()
        self._agendar_pausa()
        p.run_task(self._relogio_estudo)
        p.run_task(self._tique_cronometro)
        if not self.modo_web and not config.FIXTURES_DIR:
            p.run_task(self._verificar_provas_novas)
        if os.environ.get("APROVA_DEMO"):
            p.run_task(self._roteiro_demo, os.environ["APROVA_DEMO"])

    async def _roteiro_demo(self, roteiro: str) -> None:
        """Passos automáticos usados nos testes de tela (APROVA_DEMO)."""
        from .concursos import abrir_edital
        from .estudar import abrir_prova
        from .provas import baixar_prova

        await asyncio.sleep(1.5)
        for passo in roteiro.split(","):
            nome, _, arg = passo.partition(":")
            tela = self.foco
            if nome == "prova":
                demo = next(p for p in self.db.provas() if p["origem_url"] == "aprova://demo")
                abrir_prova(self, demo["id"], arg or "estudo")
            elif nome == "importada":
                prova = next(p for p in self.db.provas() if p["origem_url"] != "aprova://demo")
                abrir_prova(self, prova["id"], arg or "estudo")
            elif nome == "responder" and tela:
                tela.responder(arg)
            elif nome == "proxima" and tela:
                tela.ir_para(tela.idx + int(arg or 1))
            elif nome == "marcar" and tela:
                tela._marcar()
            elif nome == "ajuda" and tela:
                tela.abrir_ajuda(arg or "dica")
            elif nome == "finalizar" and tela:
                tela._confirmou = True
                await tela.finalizar()
            elif nome == "revisar" and tela:
                tela._revisar(True)
            elif nome == "edital":
                t = self._tela("concursos")
                await asyncio.sleep(1)
                lista = t.abertos.get(t.regiao) or []
                if lista:
                    await abrir_edital(self, lista[0])
            elif nome == "baixar":
                t = self._tela("provas")
                await asyncio.sleep(1)
                if t.itens:
                    await baixar_prova(self, t.itens[0])
            elif nome == "buscar":
                self.ir("provas", termo=arg)
            elif nome == "aba":
                t = self._tela("concursos")
                t._trocar_aba(type("E", (), {"control": type("C", (), {"selected": [arg]})()})())
            elif nome == "caderno":
                from .. import fontes as _f
                from .provas import importar_achado

                t = self._tela("provas")
                for _ in range(40):
                    if t.resultado is not None and not t.carregando:
                        break
                    await asyncio.sleep(0.5)
                grupos = _f.agrupar_por_cargo(t.resultado.oficiais)
                cargo, _, cad = arg.partition("|")
                g = next(g for g in grupos if cargo.lower() in g["cargo"].lower())
                a = next(x for x in g["cadernos"] if x.caderno == (cad or "1"))
                await importar_achado(self, a, g["gabarito"], t.resultado.termo)
            elif nome == "provas_do_orgao":
                self.ir("provas", url="https://www.pciconcursos.com.br/provas/tj-sp", rotulo="TJSP - Tribunal de Justiça")
            elif nome == "painel":
                self.ir("painel", aba=arg or "desempenho")
                self.telas["painel"].aba = arg or "desempenho"
                self.recarregar_tela_sem_perder(self.telas["painel"])
            elif nome == "estudar":
                t = self._tela("estudar")
                t.aba = arg or "biblioteca"
                self.ir("estudar")
                self.recarregar_tela_sem_perder(t)
            elif nome == "alarme":
                lem = next((l for l in self.db.lembretes() if not arg or str(l["id"]) == arg), None)
                if lem:
                    await self.disparar_lembrete(lem)
            elif nome == "cronometro":
                self.iniciar_cronometro(arg)
            elif nome == "parar":
                self.dialogo_parar()
            elif nome == "checar_alarmes":
                await self._checar_lembretes()
            elif nome == "encher":
                from .coleta import abrir_coleta

                abrir_coleta(self, arg)
            elif nome == "encher_ok":
                # clica em "Baixar e importar" na janela aberta
                for _ in range(40):
                    dlg = next((d for d in reversed(self.page._dialogs.controls) if isinstance(d, ft.AlertDialog)), None) if hasattr(self.page, "_dialogs") else None
                    bt = next((a for a in (dlg.actions if dlg else []) if isinstance(a, ft.FilledButton)), None)
                    if bt and bt.on_click:
                        await bt.on_click(None)
                        break
                    await asyncio.sleep(0.5)
            elif nome == "encher_biblioteca":
                self._tela("estudar")._encher()
            elif nome == "montar":
                from .montar import abrir_montador

                abrir_montador(self, filtro=arg)
            elif nome == "pausa":
                self.page.run_task(self.mostrar_pausa)
            elif nome == "espera":
                await asyncio.sleep(float(arg or 1))
            await asyncio.sleep(0.6)

    def _ao_redimensionar(self, e) -> None:
        if self._largo is not None and self._largo != self.largo:
            self.montar()

    def _teclado(self, e: ft.KeyboardEvent) -> None:
        self.marcar_atividade()
        tela = self.foco
        if tela is not None and hasattr(tela, "tecla"):
            tela.tecla(e)

    # ------------------------------------------------------------ layout

    def montar(self) -> None:
        """Reconstrói o esqueleto (barra lateral ou barra inferior) e a tela atual."""
        p = self.page
        self._largo = self.largo
        c = self.c
        p.bgcolor = c["bg"]
        p.controls.clear()
        p.navigation_bar = None
        p.appbar = None
        if self.foco is not None:
            p.controls.append(ft.SafeArea(self.foco_container(), expand=True))
            p.update()
            return
        self.conteudo = ft.Container(expand=True, bgcolor=c["bg"])
        if self._largo:
            p.controls.append(
                ft.Row(
                    [self._barra_lateral(), ft.Container(self.conteudo, expand=True, padding=ft.Padding.only(left=36, right=36, top=28))],
                    spacing=0,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                )
            )
        else:
            idx = [d[0] for d in DESTINOS].index(self.secao) if self.secao in [d[0] for d in DESTINOS] else 0
            p.navigation_bar = ft.NavigationBar(
                selected_index=idx,
                bgcolor=c["sup"],
                indicator_color=c["tinta_suave"],
                destinations=[ft.NavigationBarDestination(icon=d[2], selected_icon=d[3], label=d[1]) for d in DESTINOS],
                label_behavior=ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED if (p.width or 0) < 460 else ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
                on_change=lambda e: self.ir(DESTINOS[e.control.selected_index][0]),
            )
            p.controls.append(ft.SafeArea(ft.Container(self.conteudo, expand=True, padding=ft.Padding.only(left=16, right=16, top=12)), expand=True))
        self.ir(self.secao, reconstruir_layout=False)

    def foco_container(self) -> ft.Control:
        return self.foco.build() if hasattr(self.foco, "build") else self.foco

    def _barra_lateral(self) -> ft.Container:
        c = self.c
        itens = []
        for chave, rotulo, icone, icone_sel in DESTINOS:
            sel = chave == self.secao
            itens.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icone_sel if sel else icone, size=21, color=c["tinta"] if sel else c["texto2"]),
                            ft.Text(rotulo, size=15.5, color=c["texto"] if sel else c["texto2"], weight=ft.FontWeight.W_700 if sel else None),
                        ],
                        spacing=14,
                    ),
                    bgcolor=c["tinta_suave"] if sel else None,
                    border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=11),
                    on_click=lambda e, k=chave: self.ir(k),
                    ink=True,
                )
            )
        temas = ft.Row(
            [
                ft.IconButton(
                    icon=ic,
                    tooltip=tema.NOMES_TEMA[nome],
                    icon_color=c["tinta"] if self.aj["tema"] == nome else c["texto2"],
                    bgcolor=c["tinta_suave"] if self.aj["tema"] == nome else None,
                    on_click=lambda e, n=nome: self.trocar_tema(n),
                )
                for nome, ic in (
                    ("claro", ft.Icons.LIGHT_MODE_OUTLINED),
                    ("sepia", ft.Icons.AUTO_STORIES_OUTLINED),
                    ("escuro", ft.Icons.DARK_MODE_OUTLINED),
                )
            ],
            spacing=4,
        )
        return ft.Container(
            width=236,
            bgcolor=c["sup"],
            border=ft.Border.only(right=ft.BorderSide(1, c["borda"])),
            padding=ft.Padding.only(left=16, right=16, top=28, bottom=18),
            content=ft.Column(
                [
                    ft.Container(
                        ft.Row(
                            [
                                ft.Image(src="icon.png", width=44, height=44),
                                ft.Column(
                                    [
                                        ft.Text("Aprova", size=28, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=c["tinta"]),
                                        ft.Text("estudo para concursos", size=12.5, color=c["texto2"]),
                                    ],
                                    spacing=0,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=ft.Padding.only(left=6, bottom=24),
                    ),
                    *itens,
                    ft.Container(expand=True),
                    self._pilula_cronometro(),
                    ft.Container(comp.apagado("Leitura", c, 12.5), padding=ft.Padding.only(left=10)),
                    temas,
                ],
                spacing=4,
            ),
        )

    # ------------------------------------------------------------ navegação

    def _tela(self, chave: str):
        from .ajustes import TelaAjustes
        from .concursos import TelaConcursos
        from .estudar import TelaEstudar
        from .inicio import TelaInicio
        from .painel import TelaPainel
        from .provas import TelaProvas

        classes = {
            "inicio": TelaInicio,
            "concursos": TelaConcursos,
            "provas": TelaProvas,
            "estudar": TelaEstudar,
            "painel": TelaPainel,
            "ajustes": TelaAjustes,
        }
        if chave not in self.telas:
            self.telas[chave] = classes[chave](self)
        return self.telas[chave]

    def ir(self, chave: str, reconstruir_layout: bool = True, **kwargs) -> None:
        if chave not in {d[0] for d in DESTINOS}:
            chave = "inicio"
        mudou = chave != self.secao
        self.secao = chave
        if self.foco is not None:
            return
        tela = self._tela(chave)
        if kwargs and hasattr(tela, "preparar"):
            tela.preparar(**kwargs)
        if reconstruir_layout and self._largo and mudou:
            # redesenha a barra lateral para marcar a seção
            self.montar()
            return
        if not self._largo and self.page.navigation_bar is not None:
            self.page.navigation_bar.selected_index = [d[0] for d in DESTINOS].index(chave)
        self.conteudo.content = tela.build()
        self.page.update()
        if hasattr(tela, "ao_mostrar"):
            tela.ao_mostrar()

    def abrir_foco(self, tela) -> None:
        """Mostra uma tela sem a navegação (ex.: prova em andamento)."""
        self.leitor.parar()
        self.foco = tela
        self.montar()
        if hasattr(tela, "ao_mostrar"):
            tela.ao_mostrar()

    def fechar_foco(self, ir_para: str | None = None) -> None:
        self.leitor.parar()
        self.foco = None
        if ir_para:
            self.secao = ir_para
        self.telas.pop("inicio", None)
        self.telas.pop("estudar", None)
        self.montar()

    def trocar_tema(self, nome: str) -> None:
        self.aj.set("tema", nome)
        tema.aplicar(self.page, nome)
        self.telas.clear()
        self.montar()

    def recarregar_tela(self) -> None:
        self.telas.pop(self.secao, None)
        self.ir(self.secao, reconstruir_layout=False)

    def recarregar_tela_sem_perder(self, tela) -> None:
        """Reconstrói a tela atual mantendo o estado (filtros, listas já carregadas)."""
        if self.foco is None and self.telas.get(self.secao) is tela:
            self.conteudo.content = tela.build()
            self.page.update()


    # ------------------------------------------------------------ tempo de estudo

    def marcar_atividade(self) -> None:
        self._ultima_atividade = time.time()

    def _migrar_tempo(self) -> None:
        """Na primeira vez, aproveita a duração dos simulados já feitos para o histórico de horas."""
        if not self.aj["metas_desde"]:
            from datetime import date as _date

            self.aj.set("metas_desde", _date.today().isoformat())
        if self.aj["tempo_migrado"]:
            return
        try:
            for t in self.db.tentativas(limite=2000):
                if t.get("duracao_s") and t.get("inicio"):
                    self.db.somar_tempo(min(int(t["duracao_s"]), 5 * 3600), "app", "", dia=str(t["inicio"])[:10])
        finally:
            self.aj.set("tempo_migrado", True)

    @property
    def cronometro_rodando(self) -> bool:
        return float(self.aj["cronometro_inicio"] or 0) > 0

    def cronometro_segundos(self) -> int:
        ini = float(self.aj["cronometro_inicio"] or 0)
        return int(time.time() - ini) if ini else 0

    def iniciar_cronometro(self, atividade: str = "") -> None:
        if not self.cronometro_rodando:
            self.aj.set("cronometro_inicio", time.time())
        self.aj.set("cronometro_atividade", atividade or self.aj["cronometro_atividade"] or "")
        self.telas.pop("inicio", None)
        self.telas.pop("painel", None)
        self.montar()

    def parar_cronometro(self, salvar: bool = True) -> int:
        seg = self.cronometro_segundos()
        atividade = self.aj["cronometro_atividade"] or ""
        self.aj.set("cronometro_inicio", 0)
        self.aj.set("cronometro_atividade", "")
        if salvar and seg >= 60:
            self.db.somar_tempo(min(seg, 12 * 3600), "cronometro", atividade)
        self.telas.pop("inicio", None)
        self.telas.pop("painel", None)
        self.montar()
        return seg

    def rotulo_cronometro(self, tamanho: float = 15, cor: str | None = None) -> ft.Text:
        """Texto com o tempo do cronômetro, atualizado a cada segundo."""
        t = ft.Text(_fmt_relogio(self.cronometro_segundos()), size=tamanho, weight=ft.FontWeight.W_700, color=cor or self.c["tinta"])
        self._rotulos_crono.append(t)
        return t

    def botao_estudo(self) -> ft.Control:
        """Botão para iniciar e parar o tempo de estudo (Início, Estudar)."""
        c = self.c
        if not self.cronometro_rodando:
            return comp.botao("Iniciar estudo", lambda e: self.iniciar_cronometro(""), ft.Icons.PLAY_ARROW_ROUNDED,
                              tooltip="Liga o cronômetro. O tempo entra na sua meta da semana.")
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=18, color=c["tinta"]),
                    self.rotulo_cronometro(15.5),
                    comp.botao("Parar", lambda e: self.dialogo_parar(), ft.Icons.STOP_ROUNDED),
                ],
                spacing=10,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=c["tinta_suave"],
            border_radius=24,
            padding=ft.Padding.only(left=16, right=4, top=4, bottom=4),
            tooltip=self.aj["cronometro_atividade"] or "Estudando",
        )

    def _pilula_cronometro(self) -> ft.Control:
        """Na barra lateral: sempre à vista, em qualquer tela."""
        c = self.c
        if not self.cronometro_rodando:
            return ft.Container(
                ft.OutlinedButton(
                    "Iniciar estudo",
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    on_click=lambda e: self.iniciar_cronometro(""),
                    tooltip="Liga o cronômetro de estudo",
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding.symmetric(horizontal=12, vertical=12)),
                ),
                margin=ft.Margin.only(bottom=12),
            )
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=18, color=c["tinta"]),
                    self.rotulo_cronometro(15),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.STOP_CIRCLE_OUTLINED, tooltip="Parar o estudo", icon_color=c["tinta"], on_click=lambda e: self.dialogo_parar()),
                ],
                spacing=8,
            ),
            bgcolor=c["tinta_suave"],
            border_radius=10,
            padding=ft.Padding.only(left=12, right=4),
            margin=ft.Margin.only(bottom=12),
            tooltip=self.aj["cronometro_atividade"] or "Estudando",
        )

    def dialogo_parar(self) -> None:
        """Ao parar: pergunta o que estudou (opcional) para o tempo entrar na disciplina certa."""
        from ..analise import fmt_duracao

        c = self.c
        seg = self.cronometro_segundos()
        if seg < 60:
            self.parar_cronometro(salvar=False)
            self.msg("Cronômetro parado. Menos de 1 minuto não conta.")
            return
        atividade = ft.TextField(label="O que você estudou? (opcional)", value=self.aj["cronometro_atividade"] or "", dense=True, border_radius=10)
        discs = sorted({q["disciplina"] for q in self.db.banco_de_questoes()} - {"Geral", ""})[:10] or [
            "Língua Portuguesa", "Raciocínio Lógico", "Informática", "Direito Constitucional", "Direito Administrativo"]

        def escolher(d):
            atividade.value = d
            atividade.update()

        chips = ft.Row(
            [
                ft.Container(ft.Text(d, size=13, color=c["texto"]), bgcolor=c["sup2"], border_radius=16,
                             padding=ft.Padding.symmetric(horizontal=12, vertical=6), on_click=lambda e, d=d: escolher(d))
                for d in discs
            ],
            wrap=True,
            spacing=6,
            run_spacing=6,
        )

        def salvar(e):
            self.aj.set("cronometro_atividade", (atividade.value or "").strip())
            self.page.pop_dialog()
            self._parar_e_avisar()

        def descartar(e):
            self.page.pop_dialog()
            self.parar_cronometro(salvar=False)
            self.msg("Tempo descartado.")

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Parar o estudo", font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
                content=ft.Column(
                    [
                        ft.Row(
                            [ft.Icon(ft.Icons.TIMER_OUTLINED, color=c["tinta"], size=26),
                             ft.Text(fmt_duracao(seg), size=30, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                             comp.apagado("de estudo", c, 15)],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        atividade,
                        chips,
                    ],
                    tight=True,
                    spacing=12,
                    width=min(460, (self.page.width or 500) - 40),
                ),
                actions=[
                    ft.TextButton("Continuar estudando", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("Descartar", on_click=descartar),
                    comp.botao("Salvar", salvar, ft.Icons.CHECK),
                ],
            )
        )

    def _parar_e_avisar(self) -> None:
        from ..analise import fmt_duracao

        seg = self.parar_cronometro()
        self.msg(f"Salvei {fmt_duracao(seg)} de estudo. Isso já conta na sua meta." if seg >= 60 else "Cronômetro parado (menos de 1 minuto não conta).")

    async def _tique_cronometro(self) -> None:
        while True:
            await asyncio.sleep(1)
            if not self._rotulos_crono:
                continue
            texto = _fmt_relogio(self.cronometro_segundos())
            vivos = []
            for t in self._rotulos_crono:
                try:
                    if t.page is None:
                        continue
                    t.value = texto
                    t.update()
                    vivos.append(t)
                except Exception:  # noqa: BLE001 - controle saiu da tela
                    continue
            self._rotulos_crono = vivos[-6:]

    async def _relogio_estudo(self) -> None:
        """A cada 30 s: soma o tempo ativo nas provas e confere os lembretes."""
        while True:
            await asyncio.sleep(TIQUE_S)
            try:
                foco = self.foco
                if (
                    not self.cronometro_rodando
                    and foco is not None
                    and getattr(foco, "conta_tempo", False)
                    and time.time() - self._ultima_atividade < INATIVO_S
                ):
                    disc = foco.disciplina_atual() if hasattr(foco, "disciplina_atual") else ""
                    self.db.somar_tempo(TIQUE_S, "app", disc)
                await self._checar_lembretes()
                if time.time() - self._ultima_sync > 15 * 60:
                    await self.sincronizar_ranking()
            except Exception as e:  # noqa: BLE001 - o relógio não pode parar
                config.registrar(f"relógio de estudo: {type(e).__name__}: {e}")

    # ------------------------------------------------------------ ranking

    def sincronizar_ranking_agora(self) -> None:
        """Manda os números da semana para o ranking (se a pessoa entrou numa conta)."""
        self._ultima_sync = time.time()
        if config.FIXTURES_DIR and not os.environ.get("APROVA_RANKING_TESTE"):
            return
        try:
            self.ranking.enviar(self.db)
        except Exception as e:  # noqa: BLE001 - sem internet não atrapalha o estudo
            config.registrar(f"ranking: não enviou ({type(e).__name__}: {e})")

    async def sincronizar_ranking(self) -> None:
        if self.ranking.configurado and self.ranking.logado:
            await self.em_segundo_plano(self.sincronizar_ranking_agora)

    # ------------------------------------------------------------ lembretes

    async def _checar_lembretes(self, agora: datetime | None = None) -> None:
        agora = agora or datetime.now()
        hoje, hm = agora.date().isoformat(), agora.strftime("%H:%M")
        for lem in self.db.lembretes():
            lid = lem["id"]
            if lid in self._adiados:
                if time.time() >= self._adiados[lid]:
                    del self._adiados[lid]
                    await self.disparar_lembrete(lem)
                continue
            if not lem["ativo"] or not devido(lem, agora):
                continue
            # marca antes de mostrar: outra sessão (celular) não dispara de novo
            self.db.marcar_lembrete(lid, f"{hoje} {hm}", desativar=bool(lem["data"]))
            await self.disparar_lembrete(lem)

    async def disparar_lembrete(self, lem: dict) -> None:
        c = self.c
        if not self.modo_web:
            import threading

            threading.Thread(target=_bipe, daemon=True).start()
            try:
                await self.page.window.to_front()
            except Exception:  # noqa: BLE001
                pass
        destino = DESTINOS_LEMBRETE.get(lem["alvo_tipo"], ("", ft.Icons.NOTIFICATIONS_OUTLINED))[0]

        def fechar(e=None):
            self.page.pop_dialog()

        def adiar(e):
            self._adiados[lem["id"]] = time.time() + 10 * 60
            fechar()
            self.msg("Vou lembrar de novo em 10 minutos.")

        async def estudar(e):
            fechar()
            await self.abrir_destino(lem["alvo_tipo"], lem["alvo"], lem["titulo"])

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Row(
                    [ft.Icon(ft.Icons.ALARM_ON, color=c["tinta"], size=28), ft.Text(lem["titulo"], font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600, expand=True)],
                    spacing=10,
                ),
                content=ft.Column(
                    [
                        comp.apagado(f"Lembrete das {lem['hora']}", c, 14),
                        comp.texto(f"{destino}: {lem['alvo']}" if lem["alvo"] and destino else destino, c, 15) if destino else ft.Container(),
                    ],
                    tight=True,
                    spacing=6,
                    width=min(460, (self.page.width or 500) - 40),
                ),
                actions=[
                    ft.TextButton("Dispensar", on_click=fechar),
                    ft.TextButton("Adiar 10 min", on_click=adiar),
                    comp.botao("Estudar agora", estudar, ft.Icons.PLAY_ARROW_ROUNDED),
                ],
            )
        )

    async def abrir_url(self, url: str) -> None:
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception:  # noqa: BLE001
            import webbrowser

            webbrowser.open(url)

    async def abrir_destino(self, tipo: str, alvo: str, titulo: str = "") -> None:
        """Leva para o conteúdo do lembrete (ou de um atalho do Painel)."""
        from urllib.parse import quote_plus

        from .. import sessoes
        from .estudar import abrir_prova
        from .montar import abrir_montador

        externo = None
        if tipo == "link":
            externo = alvo if alvo.startswith("http") else "https://" + alvo
        elif tipo == "busca":
            externo = "https://www.google.com/search?q=" + quote_plus(alvo or titulo)
        elif tipo == "video":
            externo = "https://www.youtube.com/results?search_query=" + quote_plus((alvo or titulo) + " aula concurso")
        if externo:
            await self.abrir_url(externo)
            if not self.cronometro_rodando:
                self.iniciar_cronometro(titulo or alvo)
                self.msg("Liguei o cronômetro de estudo. Pare quando terminar para contar no seu tempo.")
            return
        if tipo == "revisao":
            pid = sessoes.preparar_revisao(self.db, alvo or None) or sessoes.preparar_revisao(self.db, alvo or None, todas=True)
            if pid:
                abrir_prova(self, pid, "estudo")
            else:
                self.msg("Nada para revisar ainda. Os erros dos simulados entram na revisão.")
        elif tipo == "treino":
            pid = sessoes.preparar_treino(self.db, alvo)
            if pid:
                abrir_prova(self, pid, "estudo")
            else:
                self.msg(f"Ainda não há questões de {alvo} na biblioteca.")
        elif tipo == "prova" and str(alvo).isdigit() and self.db.prova(int(alvo)):
            abrir_prova(self, int(alvo), "simulado")
        elif tipo == "simulado":
            abrir_montador(self, filtro=alvo, nome=f"Simulado {alvo}".strip())
        else:
            self.ir("painel")

    # ------------------------------------------------------------ provas novas dos favoritos

    async def _verificar_provas_novas(self) -> None:
        """Uma vez por dia: para concursos acompanhados com inscrição encerrada, procura a prova."""
        import time as _t

        from ..pci import concurso_de_dict

        await asyncio.sleep(8)
        if _t.time() - float(self.aj.get("ultima_busca_provas", 0) or 0) < 20 * 3600:
            return
        self.aj.set("ultima_busca_provas", _t.time())
        favoritos = [concurso_de_dict(d) for d in self.db.favoritos()]
        alvos = [f for f in favoritos if f.dias_restantes is not None and f.dias_restantes < 0][:8]
        novidades = 0
        for f in alvos:
            termo = f.nome.split(" - ")[0].strip()
            ano = (f.prazo_fim or "")[:4]
            if ano and ano not in termo:
                termo = f"{termo} {ano}"
            try:
                res = await self.em_segundo_plano(self.central.buscar, termo, None, False)
            except Exception:  # noqa: BLE001
                continue
            qtd = sum(1 for a in res.oficiais + res.web if a.tipo == "prova")
            if qtd and self.db.registrar_aviso(f.url, f.nome, termo, qtd):
                novidades += 1
        if novidades:
            self.telas.pop("inicio", None)
            if self.foco is None and self.secao == "inicio":
                self.recarregar_tela()
            self.msg(f"Saíram provas de {novidades} concurso(s) que você acompanha. Veja na tela Início.")

    # ------------------------------------------------------------ pausa para os olhos

    def _agendar_pausa(self) -> None:
        if self._pausa_task is None:
            self._pausa_task = self.page.run_task(self._ciclo_pausa)

    async def _ciclo_pausa(self) -> None:
        minutos_passados = 0
        while True:
            await asyncio.sleep(60)
            if not self.aj["pausa_olhos"]:
                minutos_passados = 0
                continue
            minutos_passados += 1
            if minutos_passados >= int(self.aj["pausa_minutos"] or 20):
                minutos_passados = 0
                try:
                    await self.mostrar_pausa()
                except Exception:  # noqa: BLE001 - sessão encerrada
                    return

    async def mostrar_pausa(self) -> None:
        c = self.c
        contador = ft.Text("20", size=56, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["tinta"])
        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Text("Pausa para os olhos", font_family=FONTE_TITULO, size=24),
            content=ft.Column(
                [
                    ft.Text(
                        "Olhe para algo a uns 6 metros de distância por 20 segundos e pisque devagar algumas vezes. "
                        "Isso relaxa o foco dos olhos depois de muito tempo na tela.",
                        size=15,
                        color=c["texto"],
                    ),
                    ft.Container(contador, alignment=ft.Alignment.CENTER, padding=10),
                ],
                tight=True,
                width=380,
            ),
            actions=[ft.TextButton("Voltar a estudar", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dlg)
        for s in range(19, -1, -1):
            await asyncio.sleep(1)
            if not dlg.open:
                return
            contador.value = str(s) if s else "Pronto"
            try:
                contador.update()
            except Exception:  # noqa: BLE001 - janela já fechada
                return


DESTINOS_LEMBRETE = {
    "busca": ("Pesquisar na internet", ft.Icons.TRAVEL_EXPLORE),
    "video": ("Vídeo-aulas", ft.Icons.SMART_DISPLAY_OUTLINED),
    "link": ("Abrir link", ft.Icons.LINK),
    "revisao": ("Revisão", ft.Icons.REPLAY),
    "treino": ("Treino de disciplina", ft.Icons.FITNESS_CENTER),
    "simulado": ("Simulado do concurso", ft.Icons.TUNE_ROUNDED),
}


def devido(lem: dict, agora: datetime) -> bool:
    """O lembrete deve tocar agora? (na hora marcada ou até 1 hora depois, uma vez por dia)."""
    hoje = agora.date().isoformat()
    if lem.get("data"):
        if lem["data"] != hoje:
            return False
    else:
        dias = {int(x) for x in str(lem.get("dias") or "").split(",") if x.strip().isdigit()}
        if agora.weekday() not in dias:
            return False
    if str(lem.get("ultimo") or "")[:10] == hoje:
        return False
    try:
        h, m = (int(x) for x in str(lem["hora"]).split(":"))
    except ValueError:
        return False
    marcado = agora.replace(hour=h, minute=m, second=0, microsecond=0)
    return marcado <= agora <= marcado + timedelta(hours=1)


def _fmt_relogio(seg: int) -> str:
    h, r = divmod(int(seg), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _bipe() -> None:
    try:
        import winsound

        for _ in range(3):
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            time.sleep(0.35)
    except Exception:  # noqa: BLE001 - fora do Windows, sem som
        pass
