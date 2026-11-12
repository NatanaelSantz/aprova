"""Painel → Edital: o edital verticalizado (tópicos por disciplina com teoria, questões e revisão)."""

from __future__ import annotations

import copy
import time

import flet as ft

from .. import config, edital
from . import comp, meu_concurso, movimento
from .tema import FONTE_TITULO

ABRIR_TUDO_ATE = 40  # com até tantos tópicos, todas as disciplinas já abrem abertas
ICONES = {"teoria": ft.Icons.MENU_BOOK_OUTLINED, "questoes": ft.Icons.EDIT_NOTE, "revisao": ft.Icons.REPLAY}


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def resumo(app) -> dict | None:
    """Progresso do edital guardado ou None se não há edital (com as marcas automáticas já calculadas)."""
    ed = app.aj.get("edital")
    return edital.progresso(ed, getattr(app, "edital_vinculo", None)) if edital.valido(ed) else None


def vinculo_velho(app, idade: float = 60) -> bool:
    """O acerto por tópico precisa ser calculado (de novo)? Ele muda quando a pessoa resolve questões."""
    return getattr(app, "edital_vinculo", None) is None or time.monotonic() - getattr(app, "edital_vinculo_em", 0) > idade


async def calcular_vinculo(app) -> dict:
    """Calcula em segundo plano o acerto por tópico do edital guardado e guarda no app (vale para o Início também)."""
    try:
        v = await app.em_segundo_plano(edital.vincular, app.db, app.aj.get("edital") or {})
    except Exception as e:  # noqa: BLE001 - sem o acerto, o edital funciona igual
        config.registrar(f"edital: acerto por tópico: {type(e).__name__}: {e}")
        v = {"topicos": {}, "disciplinas": {}}
    app.edital_vinculo, app.edital_vinculo_em = v, time.monotonic()
    return v


class SecaoEdital:
    def __init__(self, app, recarregar):
        self.app = app
        self.recarregar = recarregar  # redesenha o Painel
        self.carregando = False
        self.abertas: set[int] | None = None
        self._linhas: dict[tuple[int, int], ft.Container] = {}
        self._cab_disc: dict[int, ft.Container] = {}
        self._topo: ft.Container | None = None

    @property
    def vinculo(self) -> dict | None:
        """Acerto por tópico (calculado em segundo plano e guardado no app)."""
        return getattr(self.app, "edital_vinculo", None)

    @vinculo.setter
    def vinculo(self, valor: dict | None) -> None:
        self.app.edital_vinculo, self.app.edital_vinculo_em = valor, time.monotonic()

    @property
    def ed(self) -> dict:
        return self.app.aj.get("edital") or {}

    def _salvar(self, ed: dict) -> None:
        self.app.aj.set("edital", ed)

    # ------------------------------------------------------------------ montar

    def build(self) -> ft.Control:
        ed = self.ed
        if not edital.valido(ed):
            return self._vazio()
        if vinculo_velho(self.app) and not self.carregando:
            self.carregando = True  # enquanto isso, mostra o último cálculo (ou sem o acerto)
            self.app.page.run_task(self._carregar)
        if self.abertas is None:
            total = sum(len(d["topicos"]) for d in ed["disciplinas"])
            self.abertas = set(range(len(ed["disciplinas"]))) if total <= ABRIR_TUDO_ATE else {0}
        self._linhas, self._cab_disc = {}, {}
        self._topo = ft.Container(self._conteudo_topo(ed))
        blocos: list[ft.Control] = [comp.bloco(self._topo, self.app.c, padding=18)]
        blocos += [self._disciplina(ed, i) for i in range(len(ed["disciplinas"]))]
        return ft.Column(movimento.cascata(self.app, blocos[:8]) + blocos[8:], spacing=14)

    async def _carregar(self):
        await calcular_vinculo(self.app)
        self.carregando = False
        self.recarregar()

    def _vazio(self) -> ft.Control:
        app, c = self.app, self.app.c
        acoes = ft.Row(
            [
                comp.botao("Colar o conteúdo do edital", lambda e: self.dialogo_colar(), ft.Icons.CONTENT_PASTE),
                comp.botao_contorno("Começar com um modelo", lambda e: self._usar_modelo(), ft.Icons.AUTO_AWESOME_OUTLINED),
            ],
            spacing=10,
            wrap=True,
            run_spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        return comp.vazio(
            ft.Icons.CHECKLIST_RTL,
            "Edital verticalizado",
            "Cole o conteúdo programático do edital e o Aprova separa os tópicos por disciplina. Em cada tópico você marca "
            "teoria, questões e revisão, e vê quanto do edital já estudou. A marca de questões se preenche sozinha "
            f"quando você resolve {edital.AUTO_QUESTOES} questões do assunto no app.",
            c,
            acoes,
        )

    def _conteudo_topo(self, ed: dict) -> ft.Control:
        c = self.app.c
        p = edital.progresso(ed, self.vinculo)
        nome = ed.get("concurso") or (meu_concurso.dados(self.app).get("nome") or "")
        titulo = ft.Column(
            [
                comp.apagado("Edital verticalizado" + (f" · {nome}" if nome else ""), c, 13),
                ft.Text(f"{_pct(p['fracao'])} do edital estudado", size=22, font_family=FONTE_TITULO, weight=ft.FontWeight.W_600, color=c["texto"]),
                comp.apagado(f"{p['completos']} de {p['topicos']} tópicos completos (teoria, questões e revisão)", c, 13),
            ],
            spacing=2,
            expand=True,
        )
        acoes = ft.Row(
            [
                comp.botao_contorno("Colar de novo", lambda e: self.dialogo_colar(), ft.Icons.CONTENT_PASTE),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Apagar o edital", on_click=lambda e: self._confirmar_apagar()),
            ],
            spacing=4,
        )
        if self.app.largo:
            cab: ft.Control = ft.Row([titulo, acoes], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:  # celular: botões embaixo (texto com expand numa linha que quebra vira caixa cinza no Flutter)
            titulo.expand = False
            cab = ft.Column([titulo, acoes], spacing=4)
        legenda = comp.apagado(
            "Toque em Teoria, Questões e Revisão para marcar. Com o raio, a marca de questões veio sozinha: "
            f"você já resolveu {edital.AUTO_QUESTOES} questões ou mais daquele assunto aqui no app.",
            c,
            12.5,
        )
        return ft.Column([cab, comp.barra(p["fracao"], c, c["ok"] if p["fracao"] >= 1 else None, altura=10), legenda], spacing=10)

    # ------------------------------------------------------------------ disciplina

    def _cabecalho_disciplina(self, ed: dict, i: int) -> ft.Control:
        c = self.app.c
        d = ed["disciplinas"][i]
        p = edital.progresso(ed, self.vinculo, so=i)
        geral = ((self.vinculo or {}).get("disciplinas") or {}).get(i)
        detalhe = f"{p['completos']} de {p['topicos']} tópicos completos"
        if geral:
            detalhe += f" · acerto {_pct(geral['taxa'])} em {geral['total']} {'questão' if geral['total'] == 1 else 'questões'}"
        aberta = i in (self.abertas or set())
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EXPAND_LESS if aberta else ft.Icons.EXPAND_MORE, color=c["texto2"], size=22),
                        ft.Column(
                            [
                                ft.Text(d["nome"], size=16, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                comp.apagado(detalhe, c, 12.5),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Text(_pct(p["fracao"]), size=16, weight=ft.FontWeight.W_700, color=c["ok"] if p["fracao"] >= 1 else c["tinta"]),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                comp.barra(p["fracao"], c, c["ok"] if p["fracao"] >= 1 else None, altura=6),
            ],
            spacing=8,
        )

    def _disciplina(self, ed: dict, i: int) -> ft.Control:
        c = self.app.c
        cab = ft.Container(self._cabecalho_disciplina(ed, i), on_click=lambda e, i=i: self._alternar(i), border_radius=10, ink=True,
                           padding=ft.Padding.symmetric(horizontal=4, vertical=4))
        self._cab_disc[i] = cab
        corpo = ft.Column(spacing=0, visible=i in (self.abertas or set()), horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        if corpo.visible:
            corpo.controls = self._topicos(ed, i)
        return comp.bloco(ft.Column([cab, corpo], spacing=10), c, padding=14)

    def _alternar(self, i: int) -> None:
        ed = self.ed
        cab = self._cab_disc.get(i)
        if cab is None or not cab.parent:
            return
        corpo = cab.parent.controls[1]
        if i in self.abertas:
            self.abertas.discard(i)
            corpo.visible = False
        else:
            self.abertas.add(i)
            corpo.controls = self._topicos(ed, i)
            corpo.visible = True
        cab.content = self._cabecalho_disciplina(ed, i)
        self.app.page.update(cab.parent)

    def _topicos(self, ed: dict, i: int) -> list[ft.Control]:
        linhas = []
        for j, t in enumerate(ed["disciplinas"][i]["topicos"]):
            caixa = ft.Container(self._linha(t, i, j), padding=ft.Padding.symmetric(vertical=7, horizontal=4),
                                 border=ft.Border.only(top=ft.BorderSide(1, self.app.c["borda"])))
            self._linhas[(i, j)] = caixa
            linhas.append(caixa)
        return linhas

    # ------------------------------------------------------------------ tópico

    def _linha(self, t: dict, i: int, j: int) -> ft.Control:
        app, c = self.app, self.app.c
        desemp = ((self.vinculo or {}).get("topicos") or {}).get((i, j))
        texto = ft.Text(t["texto"], size=13.5, color=c["texto"], selectable=False)
        info: list[ft.Control] = []
        if desemp:
            taxa = desemp["taxa"] or 0
            cor = c["erro"] if taxa < 0.5 else c["marca"] if taxa < 0.7 else c["ok"]
            info.append(ft.Container(
                ft.Text(f"{_pct(taxa)} em {desemp['total']}", size=11.5, color=cor, weight=ft.FontWeight.W_600),
                tooltip=f"Seu acerto em {desemp['assunto']}: {desemp['acertos']} de {desemp['total']} questões",
            ))
        marcas = ft.Row([self._marca(t, campo, desemp, i, j) for campo in edital.CAMPOS], spacing=6, tight=True)
        recuo = 18 * int(t.get("nivel") or 0)
        if app.largo:
            return ft.Row(
                [ft.Container(texto, expand=True, padding=ft.Padding.only(left=recuo)), *info, marcas],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        return ft.Column(
            [ft.Container(texto, padding=ft.Padding.only(left=recuo)), ft.Row([marcas, *info], spacing=10, wrap=True,
                                                                               vertical_alignment=ft.CrossAxisAlignment.CENTER)],
            spacing=6,
        )

    def _marca(self, t: dict, campo: str, desemp: dict | None, i: int, j: int) -> ft.Control:
        c = self.app.c
        feito = edital.marcado(t, campo, desemp)
        auto = campo == "questoes" and edital.automatico(t, desemp)
        icone = ft.Icons.BOLT if auto else (ft.Icons.CHECK_ROUNDED if feito else ICONES[campo])
        cor = c["sobre_tinta"] if feito else c["texto2"]
        dica = (f"Marcada sozinha: você resolveu {desemp['total']} questões de {desemp['assunto']}" if auto
                else f"{edital.NOMES_CAMPOS[campo]}: {'feito' if feito else 'ainda não'} (toque para mudar)")
        return ft.Container(
            ft.Row([ft.Icon(icone, size=15, color=cor), ft.Text(edital.NOMES_CAMPOS[campo], size=12, color=cor, weight=ft.FontWeight.W_600)],
                   spacing=4, tight=True),
            bgcolor=(c["ok"] if campo == "revisao" else c["tinta"]) if feito else None,
            border=None if feito else ft.Border.all(1, c["borda"]),
            border_radius=16,
            padding=ft.Padding.symmetric(horizontal=9, vertical=5),
            on_click=lambda e: self._trocar(i, j, campo),
            tooltip=dica,
            animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
        )

    def _trocar(self, i: int, j: int, campo: str) -> None:
        ed = copy.deepcopy(self.ed)
        try:
            t = ed["disciplinas"][i]["topicos"][j]
        except (IndexError, KeyError):
            return
        desemp = ((self.vinculo or {}).get("topicos") or {}).get((i, j))
        t[campo] = not edital.marcado(t, campo, desemp)
        self._salvar(ed)
        # só o que muda: a linha, o cabeçalho da disciplina e o topo
        mudou: list[ft.Control] = []
        if (caixa := self._linhas.get((i, j))) is not None:
            caixa.content = self._linha(t, i, j)
            mudou.append(caixa)
        if (cab := self._cab_disc.get(i)) is not None:
            cab.content = self._cabecalho_disciplina(ed, i)
            mudou.append(cab)
        if self._topo is not None:
            self._topo.content = self._conteudo_topo(ed)
            mudou.append(self._topo)
        try:
            self.app.page.update(*mudou)
        except Exception:  # noqa: BLE001 - saiu da tela no meio
            pass
        if campo == "revisao" and t[campo] and edital.progresso(ed, self.vinculo, so=i)["fracao"] >= 1:
            self.app.msg(f"{ed['disciplinas'][i]['nome']}: edital completo! Agora é revisar e fazer simulados.")

    # ------------------------------------------------------------------ colar, modelo, apagar

    def _guardar(self, disciplinas: list[dict]) -> None:
        concurso = meu_concurso.dados(self.app).get("nome") or self.ed.get("concurso") or ""
        self._salvar(edital.novo(concurso, disciplinas, self.ed))
        self.app.edital_vinculo, self.abertas = None, None
        movimento.abrir_janela(self.app)
        self.recarregar()

    def _usar_modelo(self) -> None:
        self._guardar(edital.modelo_basico())
        self.app.msg("Modelo com as disciplinas que mais caem. Quando tiver o edital, use Colar de novo: as marcas que baterem ficam.")

    def dialogo_colar(self) -> None:
        app, c = self.app, self.app.c
        campo = ft.TextField(
            multiline=True,
            min_lines=8,
            max_lines=14,
            border_radius=10,
            label="Conteúdo programático",
            hint_text="LÍNGUA PORTUGUESA: 1 Compreensão e interpretação de textos. 2 Ortografia oficial. 3 Pontuação...\n"
                      "NOÇÕES DE INFORMÁTICA: 1 Windows e Linux. 2 Planilhas...",
            text_size=13.5,
        )
        previa = comp.apagado("Copie do PDF do edital a parte \"Conteúdo programático\" (pode ser tudo de uma vez) e cole aqui.", c, 12.5)
        lido: list[list[dict]] = [[]]

        def mudou(e=None):
            lido[0] = edital.ler_texto(campo.value or "")
            n = sum(len(d["topicos"]) for d in lido[0])
            if not (campo.value or "").strip():
                previa.value = "Copie do PDF do edital a parte \"Conteúdo programático\" (pode ser tudo de uma vez) e cole aqui."
            elif not n:
                previa.value = "Ainda não achei tópicos. Confira se colou o conteúdo programático."
            else:
                nomes = ", ".join(d["nome"] for d in lido[0][:4]) + ("…" if len(lido[0]) > 4 else "")
                previa.value = f"Achei {len(lido[0])} disciplina{'s' if len(lido[0]) != 1 else ''} e {n} tópicos: {nomes}"
            previa.update()

        campo.on_change = mudou

        def salvar(e):
            if not lido[0]:
                mudou()
                return
            app.page.pop_dialog()
            self._guardar(lido[0])
            antigo = sum(1 for d in self.ed["disciplinas"] for t in d["topicos"] if any(t.get(k) is not None for k in edital.CAMPOS))
            app.msg("Edital pronto." + (f" {antigo} tópicos já vieram com as suas marcas." if antigo else " Agora é marcar o que já estudou."))

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Colar o edital", font_family=FONTE_TITULO),
                content=ft.Container(ft.Column([campo, previa], spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH), width=min(640, (app.page.width or 700) - 60)),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Montar o edital", salvar, ft.Icons.CHECK)],
            )
        )

    def _confirmar_apagar(self) -> None:
        app = self.app

        def apagar(e):
            app.page.pop_dialog()
            app.aj.set("edital", {})
            app.edital_vinculo, self.abertas = None, None
            self.recarregar()

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Apagar o edital?", font_family=FONTE_TITULO),
                content=ft.Text("Os tópicos e as marcas de teoria, questões e revisão saem deste aparelho. Suas questões resolvidas continuam."),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Apagar", apagar, ft.Icons.DELETE_OUTLINE)],
            )
        )
