"""Estrutura do app: navegação, tema, layout para computador e celular."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import flet as ft

from .. import amostras, config, convite
from ..db import Banco
from ..fontes import Centralizador
from ..pci import ClientePCI
from ..rede import ServidorCelular
from ..voz import Leitor
from . import comp, tema
from .tema import FONTE_TITULO

LARGURA_TRILHO = 700  # abaixo disso: celular (barra embaixo)
LARGURA_LATERAL = 1180
ALTURA_BARRA = 40  # barra de título própria (computador)
TITULO_JANELA = "Aprova"  # a partir disso: barra lateral completa; entre os dois: trilho só com ícones

DESTINOS = [
    ("inicio", "Início", ft.Icons.HOME_OUTLINED, ft.Icons.HOME_ROUNDED),
    ("concursos", "Concursos", ft.Icons.CAMPAIGN_OUTLINED, ft.Icons.CAMPAIGN_ROUNDED),
    ("provas", "Provas", ft.Icons.DESCRIPTION_OUTLINED, ft.Icons.DESCRIPTION_ROUNDED),
    ("estudar", "Estudar", ft.Icons.EDIT_NOTE_OUTLINED, ft.Icons.EDIT_NOTE_ROUNDED),
    ("grupos", "Grupos", ft.Icons.FORUM_OUTLINED, ft.Icons.FORUM_ROUNDED),
    ("painel", "Painel", ft.Icons.INSIGHTS_OUTLINED, ft.Icons.INSIGHTS_ROUNDED),
    ("ajustes", "Ajustes", ft.Icons.TUNE_OUTLINED, ft.Icons.TUNE_ROUNDED),
]
DESTINO_ADMIN = ("admin", "Admin", ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, ft.Icons.ADMIN_PANEL_SETTINGS)
FORA_DA_BARRA = ("ajustes", "admin")  # no celular: ficam no menu do avatar e abrem com botão Voltar

INATIVO_S = 8 * 60  # sem tocar no app por mais que isso, o tempo para de contar
TIQUE_S = 30

# Recursos compartilhados entre sessões (no modo celular cada aparelho abre uma sessão)
_BANCOS: dict[str, Banco] = {}
_PCI: ClientePCI | None = None
_CENTRAL: Centralizador | None = None
_SERVIDOR = ServidorCelular()


def banco_em(caminho: Path) -> Banco:
    """Um banco por pasta de dados (visitante ou cada conta), aberto uma vez só."""
    chave = str(caminho)
    if chave not in _BANCOS:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        b = Banco(caminho)
        amostras.instalar(b)
        _BANCOS[chave] = b
    return _BANCOS[chave]


def pasta_dados(conta_id: str | None) -> Path:
    """Visitante usa a pasta .aprova; cada conta tem a sua subpasta (estudos separados por pessoa)."""
    return config.DATA_DIR / "contas" / conta_id if conta_id else config.DATA_DIR


def _recursos() -> tuple[ClientePCI, Centralizador]:
    global _PCI, _CENTRAL
    config.garantir_pastas()
    if _PCI is None:
        _PCI = ClientePCI()
    if _CENTRAL is None:
        _CENTRAL = Centralizador(_PCI)
    return _PCI, _CENTRAL


def _sessao_maquina(modo_web: bool):
    """Conta lembrada neste computador. No celular a sessão fica só na memória daquele aparelho."""
    arquivo = config.DATA_DIR / "sessao.json"
    if not modo_web:
        return config.Ajustes(arquivo)
    inicial = {}
    try:
        import json as _json

        inicial = _json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return config.AjustesMemoria(inicial)


class App:
    def __init__(self, page: ft.Page, modo_web: bool = False):
        self.page = page
        self.modo_web = modo_web or bool(page.web)
        self.pci, self.central = _recursos()
        self.sessao = _sessao_maquina(self.modo_web)
        self.conta_id: str | None = None
        self.em_login = False
        self._abrir_dados(None)
        self.leitor = Leitor()
        self.servidor = _SERVIDOR
        self.secao = os.environ.get("APROVA_TELA_INICIAL", "inicio")
        self.foco: ft.Control | None = None  # tela em modo foco (prova em andamento)
        self.telas: dict[str, object] = {}
        self._largo: bool | None = None
        self._modo_nav: str | None = None
        self._baixa: bool | None = None
        self._tema_pintado: str | None = None
        self.conteudo = ft.Container(expand=True)
        self._moldura: ft.Container | None = None
        self._comunicados: tuple[float, list] = (0.0, [])
        self._novidades: tuple[float, dict] = (0.0, {})
        self.nomes_grupos: dict[str, str] = {}
        self._pausa_task = None
        self._ultima_atividade = time.time()
        self._rotulos_crono: list[ft.Text] = []
        self._adiados: dict[int, float] = {}
        from ..ranking import Ranking

        self.ranking = Ranking(self.sessao)
        self._ultima_sync = 0.0
        self._antes_extra = "inicio"
        self.convite: dict | None = None  # convite de grupo esperando a pessoa entrar
        self.atualizacao: dict | None = None  # versão nova disponível (versao.json do site)
        self.atualizacao_pronta: str | None = None  # versão já baixada, entra ao reiniciar
        self._ultimo_texto_area = ""

    # ------------------------------------------------------------ utilidades

    @property
    def c(self) -> dict:
        return tema.paleta(self.aj["tema"])

    @property
    def modo_nav(self) -> str:
        """'lateral' (barra completa), 'trilho' (só ícones) ou 'inferior' (celular)."""
        w = self.page.width or 1200
        if w < LARGURA_TRILHO:
            return "inferior"
        return "trilho" if w < LARGURA_LATERAL else "lateral"

    @property
    def largo(self) -> bool:
        return self.modo_nav != "inferior"

    def destinos(self) -> list[tuple]:
        return DESTINOS[:-1] + [DESTINO_ADMIN, DESTINOS[-1]] if self.ranking.eh_admin else list(DESTINOS)

    def destinos_barra(self) -> list[tuple]:
        """Itens da barra de baixo no celular (Ajustes e Admin vão para o menu do avatar)."""
        return [d for d in self.destinos() if d[0] not in FORA_DA_BARRA]

    # ------------------------------------------------------------ contas e dados de cada pessoa

    def _abrir_dados(self, conta_id: str | None) -> None:
        pasta = pasta_dados(conta_id)
        self.conta_id = conta_id
        self.aj = config.Ajustes(pasta / "ajustes.json")
        self.db = banco_em(pasta / "aprova.db")
        if hasattr(self, "telas"):
            self.telas.clear()

    @property
    def pasta_conta(self) -> Path:
        """Pasta de dados de quem está usando (visitante ou a conta)."""
        return pasta_dados(self.conta_id)

    @property
    def nome_exibicao(self) -> str:
        if self.ranking.logado and self.ranking.apelido:
            return self.ranking.apelido
        return (self.aj["nome"] or "").strip()

    def mostrar_login(self) -> None:
        from .login import TelaLogin

        self.foco = None
        self.em_login = True
        self._tela_login = TelaLogin(self)
        if self.convite:
            self._tela_login.modo = "convite"
        self.montar()

    def continuar_sem_conta(self) -> None:
        self.sessao.set("pular_login", True)
        self.em_login = False
        if self.conta_id is not None:
            self._abrir_dados(None)
            self._migrar_tempo()
        tema.aplicar(self.page, self.aj["tema"])
        self.secao = "inicio"
        self.montar()

    def _tem_estudos_de_visitante(self) -> bool:
        try:
            b = banco_em(pasta_dados(None) / "aprova.db")
            if b.estatisticas()["respondidas"] > 0 or any(p["origem_url"] != "aprova://demo" for p in b.provas()):
                return True
            from .. import marcador

            return bool(marcador.recentes(pasta_dados(None)))
        except Exception:  # noqa: BLE001
            return False

    def _levar_estudos_para(self, conta_id: str) -> None:
        """Copia os estudos feitos sem conta para a pasta da conta (o original fica onde está)."""
        import shutil
        import sqlite3

        origem = banco_em(pasta_dados(None) / "aprova.db")
        destino = pasta_dados(conta_id)
        destino.mkdir(parents=True, exist_ok=True)
        with origem._lock:
            alvo = sqlite3.connect(destino / "aprova.db")
            origem._con.backup(alvo)
            alvo.close()
        aj_origem = pasta_dados(None) / "ajustes.json"
        if aj_origem.exists():
            shutil.copy2(aj_origem, destino / "ajustes.json")
        try:
            from .. import marcador

            marcador.copiar_para(pasta_dados(None), destino)
        except OSError as e:
            config.registrar(f"marcador: não levou os PDFs marcados ({e})")
        self.sessao.set("estudos_levados_para", conta_id)

    async def _perguntar(self, titulo: str, texto: str, sim: str, nao: str) -> bool:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()

        def responder(valor: bool):
            def _f(e):
                self.page.pop_dialog()
                if not fut.done():
                    fut.set_result(valor)

            return _f

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(titulo, font_family=FONTE_TITULO, size=22, weight=ft.FontWeight.W_600),
                content=ft.Text(texto, size=15, width=min(460, (self.page.width or 500) - 40)),
                actions=[ft.TextButton(nao, on_click=responder(False)), comp.botao(sim, responder(True), ft.Icons.CHECK)],
            )
        )
        return await fut

    async def depois_do_login(self) -> None:
        """Abre os estudos da conta que entrou e leva para a tela certa (admin ou aluno)."""
        cid = self.ranking.usuario_id
        if not cid:
            return
        pasta = pasta_dados(cid)
        if not (pasta / "aprova.db").exists() and not self.sessao.get("estudos_levados_para", "") and self._tem_estudos_de_visitante():
            levar = await self._perguntar(
                "Levar seus estudos para a conta?",
                "Neste computador já há provas e respostas feitas sem conta. Quer usar esses estudos na sua conta? "
                "Você não perde nada: o original continua guardado.",
                "Sim, levar",
                "Começar do zero",
            )
            if levar:
                await self.em_segundo_plano(self._levar_estudos_para, cid)
        self._abrir_dados(cid)
        self._migrar_tempo()
        self.sessao.set("pular_login", False)
        self.em_login = False
        tema.aplicar(self.page, self.aj["tema"])
        self.secao = "admin" if self.ranking.eh_admin else "inicio"
        if self.convite:
            pendente, self.convite = self.convite, None
            self.secao = "grupos"
            self.montar()
            await self._entrar_no_grupo(pendente)
        else:
            self.montar()
        self.page.run_task(self.sincronizar_ranking)

    def sair_da_conta(self) -> None:
        self.page.run_task(self._sair)

    async def _sair(self) -> None:
        if self.cronometro_rodando:
            self.parar_cronometro()
        await self.em_segundo_plano(self.ranking.sair)
        self.sessao.set("pular_login", False)
        self._abrir_dados(None)
        self.secao = "inicio"
        tema.aplicar(self.page, self.aj["tema"])
        self.mostrar_login()

    def menu_conta(self, compacto: bool = False) -> ft.Control:
        """Avatar com o nome; abre o menu da conta (entrar, minha conta, sair)."""
        from .login import dialogo_conta

        c = self.c
        logado = self.ranking.logado
        nome = self.nome_exibicao or "Visitante"
        papel = "Administrador" if self.ranking.eh_admin else ("Aluno" if logado else "Sem conta")
        avatar = ft.Container(
            ft.Text((nome[:1] or "?").upper(), size=16, weight=ft.FontWeight.W_700, color=c["sobre_tinta"]),
            width=38,
            height=38,
            border_radius=19,
            bgcolor=c["tinta"] if logado else c["texto2"],
            alignment=ft.Alignment.CENTER,
        )
        if compacto:
            rosto = avatar
        else:
            rosto = ft.Row(
                [
                    avatar,
                    ft.Column(
                        [
                            ft.Text(nome, size=14.5, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(papel, size=12, color=c["tinta"] if self.ranking.eh_admin else c["texto2"]),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.EXPAND_MORE, size=18, color=c["texto2"]),
                ],
                spacing=10,
            )
        if logado:
            itens = [
                ft.PopupMenuItem(content="Minha conta", icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, on_click=lambda e: dialogo_conta(self)),
                ft.PopupMenuItem(content="Sair / trocar de conta", icon=ft.Icons.LOGOUT, on_click=lambda e: self.sair_da_conta()),
            ]
        else:
            itens = [ft.PopupMenuItem(content="Entrar ou criar conta", icon=ft.Icons.LOGIN, on_click=lambda e: self.mostrar_login())]
        if self.modo_nav == "inferior":
            extras = [ft.PopupMenuItem(content="Ajustes", icon=ft.Icons.TUNE_OUTLINED, on_click=lambda e: self.ir("ajustes"))]
            if self.ranking.eh_admin:
                extras.insert(0, ft.PopupMenuItem(content="Administração", icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, on_click=lambda e: self.ir("admin")))
            itens = extras + [ft.PopupMenuItem()] + itens
        return ft.PopupMenuButton(content=rosto, items=itens, tooltip=f"{nome} · {papel}")

    def comunicados_cache(self) -> list:
        return self._comunicados[1]

    async def carregar_comunicados(self, forcar: bool = False) -> list:
        if not (self.ranking.configurado and self.ranking.logado):
            return []
        if not forcar and time.time() - self._comunicados[0] < 300:
            return self._comunicados[1]
        try:
            lista = await self.em_segundo_plano(self.ranking.comunicados)
        except Exception:  # noqa: BLE001
            lista = self._comunicados[1]
        self._comunicados = (time.time(), lista)
        return lista

    def novidades_grupos(self) -> dict:
        """Mensagens novas por grupo (desde a última visita), da última consulta."""
        return self._novidades[1]

    def zerar_novidades(self, codigo: str) -> None:
        if self._novidades[1].get(codigo):
            self._novidades[1][codigo] = 0

    async def carregar_novidades(self, forcar: bool = False) -> dict:
        if not (self.ranking.configurado and self.ranking.logado):
            return {}
        if not forcar and time.time() - self._novidades[0] < 300:
            return self._novidades[1]
        try:
            grupos = await self.em_segundo_plano(self.ranking.meus_grupos)
            vistos = self.aj.get("forum_vistos", {}) or {}
            novas = await self.em_segundo_plano(self.ranking.forum_novidades, [g["codigo"] for g in grupos], vistos)
            self.nomes_grupos = {g["codigo"]: g["nome"] for g in grupos}
            self._novidades = (time.time(), {k: v for k, v in novas.items() if v})
        except Exception:  # noqa: BLE001
            pass
        return self._novidades[1]

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
        p.title = TITULO_JANELA
        p.fonts = tema.FONTES
        p.padding = 0
        p.spacing = 0
        if not self.modo_web:
            try:
                p.window.min_width = 380
                p.window.min_height = 520
                if os.environ.get("APROVA_JANELA"):
                    larg, alt = (int(x) for x in os.environ["APROVA_JANELA"].lower().split("x"))
                    p.window.width, p.window.height = larg, alt
                else:
                    # tamanho que cabe mesmo em notebook com zoom de 150% no Windows (a janela de 1280x820
                    # passava da tela e cortava o rodapé do menu). Depois que a janela aparece, o main.py
                    # maximiza (maximizar com a janela ainda escondida é arriscado no Windows).
                    p.window.width, p.window.height = 1120, 620
                if self.barra_propria:
                    p.window.title_bar_hidden = True
                    p.window.title_bar_buttons_hidden = True
            except Exception:  # noqa: BLE001
                pass
        if not self.modo_web:
            icone = config.ASSETS_DIR / "aprova.ico"
            if icone.exists():
                try:
                    p.window.icon = str(icone)
                except Exception:  # noqa: BLE001
                    pass
        p.on_resize = self._ao_redimensionar
        p.on_keyboard_event = self._teclado
        sem_login = bool(os.environ.get("APROVA_SEM_LOGIN")) or (bool(config.FIXTURES_DIR) and not os.environ.get("APROVA_LOGIN"))
        if self.ranking.configurado and self.ranking.logado and self.ranking.usuario_id:
            self._abrir_dados(self.ranking.usuario_id)  # conta lembrada: entra direto
            if self.ranking.eh_admin and self.secao == "inicio" and not os.environ.get("APROVA_TELA_INICIAL"):
                self.secao = "admin"
        elif not (sem_login or self.sessao.get("pular_login")):
            self.em_login = True
            from .login import TelaLogin

            self._tela_login = TelaLogin(self)
        tema.aplicar(p, self.aj["tema"])
        self._migrar_tempo()
        self.montar()
        self._agendar_pausa()
        p.run_task(self._relogio_estudo)
        p.run_task(self._tique_cronometro)
        if not self.modo_web:
            p.run_task(self._vigiar_convites)
            import threading

            threading.Thread(target=convite.registrar_protocolo, args=(config.RAIZ,), daemon=True).start()
            try:
                p.window.on_event = self._evento_janela
            except Exception:  # noqa: BLE001
                pass
        if not self.modo_web and not config.FIXTURES_DIR:
            p.run_task(self._verificar_provas_novas)
        from . import atualizacao

        atualizacao.ver_pronta(self)
        if atualizacao.disponivel(self):
            p.run_task(atualizacao.vigiar, self)
        if os.environ.get("APROVA_DEMO"):
            p.run_task(self._roteiro_demo, os.environ["APROVA_DEMO"])

    def pintar_barra_windows(self) -> None:
        """Barra de título do Windows com as cores do tema (só pinta; não esconde nada)."""
        if self.modo_web or self.barra_propria or self._tema_pintado == self.aj["tema"]:
            return
        esperar = 20.0 if self._tema_pintado is None else 3.0  # na abertura, espera a janela aparecer
        self._tema_pintado = self.aj["tema"]
        from .. import janela

        c = self.c
        try:
            janela.pintar_barra(TITULO_JANELA, c["sup"], c["texto"], c["borda"], self.aj["tema"] == "escuro", esperar)
        except Exception as e:  # noqa: BLE001
            config.registrar(f"janela: não pintou a barra ({e!r})")

    async def _roteiro_demo(self, roteiro: str) -> None:
        """Passos automáticos usados nos testes de tela (APROVA_DEMO)."""
        await asyncio.sleep(1.5)
        for passo in roteiro.split(","):
            try:
                await self._passo_demo(passo)
            except Exception:  # noqa: BLE001
                import traceback

                traceback.print_exc()
            await asyncio.sleep(0.6)

    async def _passo_demo(self, passo: str) -> None:
        from .concursos import abrir_edital
        from .estudar import abrir_prova
        from .provas import baixar_prova

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
        elif nome == "entrar":
            email, _, senha = arg.partition(":")
            await self.em_segundo_plano(self.ranking.entrar, email, senha)
            self.page.run_task(self.depois_do_login)
        elif nome == "grupos":
            aba, _, cod = arg.partition("|")
            self.ir("grupos", aba=aba or "conversa", **({"codigo": cod} if cod else {}))
            t = self._tela("grupos")
            t.aba = aba or "conversa"
            self.recarregar_tela_sem_perder(t)
        elif nome == "respostas":
            t = self._tela("grupos")
            for _ in range(30):
                lista = t.posts.get((t.codigo, "conversa"))
                if lista:
                    break
                await asyncio.sleep(0.5)
            alvo = next((p for p in (lista or []) if p.get("respostas")), None)
            if alvo:
                t._alternar_respostas(alvo)
        elif nome == "plano_novo":
            from .grupos import dialogo_plano

            t = self._tela("grupos")
            if t.grupo:
                dialogo_plano(self, t.grupo, t._depois_de_publicar_plano)
        elif nome == "plano_usar":
            from .grupos import usar_plano

            t = self._tela("grupos")
            for _ in range(30):
                lista = t.posts.get((t.codigo, "planos"))
                if lista:
                    break
                await asyncio.sleep(0.5)
            if lista and t.grupo:
                usar_plano(self, lista[0], t.grupo)
        elif nome == "ir":
            self.ir(arg)
        elif nome == "convite":
            await self.processar_convite(arg, "link")
        elif nome == "rapido":
            await self.em_segundo_plano(self.ranking.entrar_rapido, arg)
            await self.depois_do_login()
        elif nome == "convidar":
            from .grupos import dialogo_convidar

            t = self._tela("grupos")
            for _ in range(30):
                if t.grupo:
                    break
                await asyncio.sleep(0.5)
            if t.grupo:
                dialogo_convidar(self, t.grupo)
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
        elif nome == "marcador":
            from .marcador import abrir_marcador

            abrir_marcador(self, Path(arg))
        elif nome == "marcas" and tela is not None and hasattr(tela, "doc"):
            # algumas marcações de exemplo na página atual (para as capturas de tela)
            w = tela.doc.palavras(tela.pagina)
            if len(w) > 40:
                def ponto(i, fim=False):
                    return ((w[i][2] - 1) if fim else (w[i][0] + 1), (w[i][1] + w[i][3]) / 2)

                tela.doc.marcar(tela.pagina, ponto(14), ponto(16, True), "destaque", "amarelo", nota="Cai muito em prova: decorar os princípios (LIMPE).")
                tela.doc.marcar(tela.pagina, ponto(24), ponto(31, True), "sublinhado", "azul")
                tela.doc.marcar(tela.pagina, ponto(36), ponto(min(44, len(w) - 1), True), "destaque", "verde")
                tela.doc.nota(tela.pagina, (tela.doc.tamanho(tela.pagina)[0] - 46, w[30][1] - 4), "Revisar este artigo antes do simulado.")
                tela._mudou = True
                tela._atualizar()
        elif nome == "selecao" and tela is not None and hasattr(tela, "doc"):
            # mostra a seleção ao vivo (como no meio de um arraste)
            w = tela.doc.palavras(tela.pagina)
            s = tela._escala
            tela._inicio = (w[50][0] + 1, (w[50][1] + w[50][3]) / 2)
            fim = w[min(62, len(w) - 1)]
            tela._pan_meio(type("E", (), {"local_position": ft.Offset((fim[2] - 1) * s, (fim[1] + fim[3]) / 2 * s)})())
        elif nome == "atualizacao":
            # finge que o site anunciou uma versão nova (capturas de tela)
            from . import atualizacao

            self.atualizacao = {"versao": arg or "1.9.1", "data": "25/10/2026", "notas": ["Marcar PDF: marca-texto, sublinhado e notas", "Atualização automática dentro do app", "Correções nos grupos"], "zip": os.environ.get("APROVA_DEMO_ZIP", "https://exemplo.invalid/main.zip")}
            if self.foco is None:
                self.recarregar_tela()
        elif nome == "dialogo_atualizacao" and self.atualizacao:
            from . import atualizacao

            atualizacao.dialogo_atualizar(self, self.atualizacao)
        elif nome == "clicar_atualizar":
            dlg = next((d for d in reversed(self.page._dialogs.controls) if isinstance(d, ft.AlertDialog)), None) if hasattr(self.page, "_dialogs") else None
            bt = next((b for b in (dlg.actions if dlg else []) if isinstance(b, ft.FilledButton)), None)
            if bt and bt.on_click:
                self.page.run_task(bt.on_click, None)
        elif nome == "atualizacao_pronta":
            self.atualizacao_pronta = arg or "1.9.1"
            if self.foco is None:
                self.recarregar_tela()
        elif nome == "fechar_marcador" and tela is not None and hasattr(tela, "doc"):
            tela._mudou = False
            tela._sair()
        elif nome == "salvar_pdf" and tela is not None and hasattr(tela, "dialogo_salvar"):
            if arg == "fixas":
                self.aj.set("marcador_fixas", True)
            tela.dialogo_salvar()
        elif nome == "nota_aberta" and tela is not None and hasattr(tela, "doc"):
            m = next((x for x in tela.doc.marcacoes() if x["nota"] and x["tipo"] != "nota"), None)
            if m:
                tela.dialogo_marcacao(m)

    def _ao_redimensionar(self, e) -> None:
        if self._modo_nav is not None and (self._modo_nav != self.modo_nav or self._baixa != self.baixa):
            self.montar()
            return
        if self._moldura is not None and not self.em_login and self.foco is None:
            try:
                self._moldura.padding = self._margens()
                self._moldura.update()
            except Exception:  # noqa: BLE001
                pass
        if False and self._largo is not None and self._largo != self.largo:
            self.montar()

    def _teclado(self, e: ft.KeyboardEvent) -> None:
        self.marcar_atividade()
        tela = self.foco
        if tela is not None and hasattr(tela, "tecla"):
            tela.tecla(e)

    # ------------------------------------------------------------ layout

    def montar(self) -> None:
        """Reconstrói o esqueleto (barra lateral, trilho ou barra inferior) e a tela atual."""
        p = self.page
        self._largo = self.largo
        self._modo_nav = self.modo_nav
        self._baixa = self.baixa
        self.pintar_barra_windows()
        c = self.c
        p.bgcolor = c["bg"]
        p.controls.clear()
        p.navigation_bar = None
        p.appbar = None
        if self.em_login:
            p.controls.append(ft.SafeArea(self._tela_login.build(), expand=True))
            self._vestir_barra("login")
            p.update()
            return
        if self.foco is not None:
            p.controls.append(ft.SafeArea(self.foco_container(), expand=True))
            self._vestir_barra("foco")
            p.update()
            return
        destinos = self.destinos()
        chaves = [d[0] for d in destinos]
        if self.secao not in chaves:
            self.secao = "inicio"
        self.conteudo = ft.Container(expand=True, bgcolor=c["bg"])
        modo = self._modo_nav
        if modo == "lateral":
            self._moldura = ft.Container(self.conteudo, expand=True, padding=self._margens())
            p.controls.append(
                ft.Row([self._barra_lateral(), self._moldura], spacing=0, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
            )
        elif modo == "trilho":
            self._moldura = ft.Container(self.conteudo, expand=True, padding=self._margens())
            p.controls.append(
                ft.Row([self._trilho(destinos), self._moldura], spacing=0, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
            )
        else:
            barra = self.destinos_barra()
            self._moldura = ft.Container(self.conteudo, expand=True, padding=self._margens())
            if self.secao in FORA_DA_BARRA:
                # Ajustes / Admin no celular: tela cheia com Voltar (sem a barra de baixo)
                voltar = ft.Container(
                    ft.TextButton("Voltar", icon=ft.Icons.ARROW_BACK, on_click=lambda e: self._voltar_celular()),
                    padding=ft.Padding.only(left=4, top=4),
                )
                p.controls.append(ft.SafeArea(ft.Column([voltar, self._moldura], spacing=0, expand=True), expand=True))
            else:
                p.navigation_bar = ft.NavigationBar(
                    selected_index=[d[0] for d in barra].index(self.secao),
                    bgcolor=c["sup"],
                    indicator_color=c["tinta"],
                    indicator_shape=ft.CircleBorder(),
                    border=ft.Border.only(top=ft.BorderSide(1, c["borda"])),
                    elevation=0,
                    destinations=[
                        ft.NavigationBarDestination(icon=ft.Icon(d[2], color=c["texto2"]), selected_icon=ft.Icon(d[3], color=c["sobre_tinta"]), label=d[1]) for d in barra
                    ],
                    label_behavior=ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED if (p.width or 0) < 460 else ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
                    on_change=lambda e: self.ir(barra[e.control.selected_index][0]),
                )
                p.controls.append(ft.SafeArea(self._moldura, expand=True))
        self._vestir_barra(modo)
        self.ir(self.secao, reconstruir_layout=False)

    # ------------------------------------------------------------ barra de título

    def _vestir_barra(self, modo: str) -> None:
        """Põe a barra de título própria em cima do que já está na página."""
        if not self.barra_propria:
            return
        corpo = list(self.page.controls)
        self.page.controls.clear()
        self.page.controls.append(ft.Column([self._barra_janela(modo), *corpo], spacing=0, expand=True))

    def _barra_janela(self, modo: str) -> ft.Control:
        """Faixa de cima integrada ao app: continua a barra lateral, mostra a marca e os botões da janela."""
        c = self.c
        altura = ALTURA_BARRA

        def marca(tam_icone: int, tam_texto: float) -> ft.Control:
            return ft.Row(
                [ft.Image(src="icon.png", width=tam_icone, height=tam_icone), ft.Text("Aprova", size=tam_texto, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=c["tinta"])],
                spacing=8,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        fundo = c["sup"] if modo == "foco" else c["bg"]
        if modo == "lateral":
            esquerda = ft.Container(marca(24, 18), width=236, height=altura, bgcolor=c["sup"], padding=ft.Padding.only(left=22), alignment=ft.Alignment.CENTER_LEFT, border=ft.Border.only(right=ft.BorderSide(1, c["borda"])))
        elif modo == "trilho":
            esquerda = ft.Container(ft.Image(src="icon.png", width=24, height=24), width=88, height=altura, bgcolor=c["sup"], alignment=ft.Alignment.CENTER, border=ft.Border.only(right=ft.BorderSide(1, c["borda"])))
        else:
            esquerda = ft.Container(marca(20, 15.5), height=altura, padding=ft.Padding.only(left=14), alignment=ft.Alignment.CENTER_LEFT)
        arrastar = ft.WindowDragArea(
            ft.Row([esquerda, ft.Container(expand=True, height=altura)], spacing=0),
            maximizable=True,
            expand=True,
        )
        self._icone_maximizar = ft.Icon(ft.Icons.FILTER_NONE if self.page.window.maximized else ft.Icons.CROP_SQUARE, size=15, color=c["texto2"])
        botoes = ft.Row(
            [
                self._botao_janela(ft.Icon(ft.Icons.REMOVE, size=16, color=c["texto2"]), "Minimizar", self._minimizar),
                self._botao_janela(self._icone_maximizar, "Maximizar / restaurar", self._alternar_maximizar),
                self._botao_janela(ft.Icon(ft.Icons.CLOSE, size=17, color=c["texto2"]), "Fechar", self._fechar_janela, perigo=True),
            ],
            spacing=0,
        )
        if modo == "login" and (self.page.width or 0) >= 960:
            # tela de entrada larga: a faixa continua o painel azul da esquerda (mesma proporção 5:6)
            return ft.Container(
                ft.Row(
                    [
                        ft.WindowDragArea(ft.Container(height=altura, bgcolor=c["tinta"]), maximizable=True, expand=5),
                        ft.Container(ft.Row([ft.WindowDragArea(ft.Container(height=altura), maximizable=True, expand=True), botoes], spacing=0), expand=6),
                    ],
                    spacing=0,
                ),
                height=altura,
                bgcolor=fundo,
            )
        return ft.Container(ft.Row([arrastar, botoes], spacing=0), height=altura, bgcolor=fundo)

    def _botao_janela(self, icone: ft.Icon, dica: str, acao, perigo: bool = False) -> ft.Control:
        c = self.c
        caixa = ft.Container(icone, width=46, height=ALTURA_BARRA, alignment=ft.Alignment.CENTER, on_click=acao, tooltip=dica)

        def passar(e):
            dentro = str(e.data).lower() in ("true", "1")
            caixa.bgcolor = ("#C42B1C" if perigo else c["sup2"]) if dentro else None
            icone.color = "#FFFFFF" if (perigo and dentro) else c["texto2"]
            try:
                caixa.update()
            except Exception:  # noqa: BLE001
                pass

        caixa.on_hover = passar
        return caixa

    def _minimizar(self, e=None) -> None:
        self.page.window.minimized = True
        self.page.update()

    def _alternar_maximizar(self, e=None) -> None:
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._atualizar_icone_maximizar()

    def _atualizar_icone_maximizar(self) -> None:
        icone = getattr(self, "_icone_maximizar", None)
        if icone is None:
            return
        icone.icon = ft.Icons.FILTER_NONE if self.page.window.maximized else ft.Icons.CROP_SQUARE
        try:
            icone.update()
        except Exception:  # noqa: BLE001
            pass

    async def _fechar_janela(self, e=None) -> None:
        if self.cronometro_rodando:
            self.parar_cronometro(salvar=True)  # não perde o tempo que estava contando
        try:
            await self.page.window.close()
        except Exception:  # noqa: BLE001
            await self.page.window.destroy()

    def _voltar_celular(self) -> None:
        destino = self._antes_extra if self._antes_extra not in FORA_DA_BARRA else "inicio"
        self.secao = destino
        self.montar()

    def _margens(self) -> ft.Padding:
        """Margens por tamanho; em telas muito largas o conteúdo fica centralizado (linhas não ficam longas demais)."""
        w = self.page.width or 1200
        modo = self.modo_nav
        topo_extra = 0 if self.barra_propria else 1  # a barra de título própria já dá o respiro de cima
        if modo == "inferior":
            return ft.Padding.only(left=16, right=16, top=4 + 8 * topo_extra)
        barra = 236 if modo == "lateral" else 88
        lado = 36 if modo == "lateral" else 24
        sobra = (w - barra) - 1480
        if sobra > 0:
            lado += sobra // 2
        return ft.Padding.only(left=lado, right=lado, top=(28 if modo == "lateral" else 20) if topo_extra else 6)

    def _trilho(self, destinos: list[tuple]) -> ft.Control:
        """Navegação só com ícones, para janelas médias."""
        c = self.c
        estudo = (
            ft.IconButton(ft.Icons.STOP_CIRCLE_OUTLINED, tooltip="Parar o estudo", icon_color=c["tinta"], on_click=lambda e: self.dialogo_parar())
            if self.cronometro_rodando
            else ft.IconButton(ft.Icons.PLAY_CIRCLE_OUTLINE, tooltip="Iniciar estudo", icon_color=c["tinta"], on_click=lambda e: self.iniciar_cronometro(""))
        )
        proximo = {"claro": "sepia", "sepia": "escuro", "escuro": "claro"}
        icone_tema = {"claro": ft.Icons.LIGHT_MODE_OUTLINED, "sepia": ft.Icons.AUTO_STORIES_OUTLINED, "escuro": ft.Icons.DARK_MODE_OUTLINED}
        itens = []
        for chave, rotulo, icone, icone_sel in destinos:
            sel = chave == self.secao
            itens.append(
                ft.Container(
                    ft.Column(
                        [
                            comp.bolha_icone(icone, c, marcada=sel, tamanho=38, icone_marcado=icone_sel),
                            ft.Text(rotulo, size=11.5, color=c["texto"] if sel else c["texto2"], weight=ft.FontWeight.W_700 if sel else None, max_lines=1),
                        ],
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=5),
                    border_radius=12,
                    on_click=lambda e, k=chave: self.ir(k),
                    ink=True,
                    width=80,
                )
            )
        return ft.Container(
            ft.Column(
                [
                    ft.Container(height=8) if self.barra_propria else ft.Container(ft.Image(src="icon.png", width=40, height=40), padding=ft.Padding.only(top=16)),
                    self.menu_conta(compacto=True),
                    ft.Container(height=6),
                    ft.Column(itens, spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO, expand=True),
                    estudo,
                    self.rotulo_cronometro(11.5) if self.cronometro_rodando else ft.Container(),
                    ft.IconButton(
                        icone_tema.get(self.aj["tema"], ft.Icons.LIGHT_MODE_OUTLINED),
                        tooltip=f"Leitura: {tema.NOMES_TEMA.get(self.aj['tema'], '')} (toque para trocar)",
                        on_click=lambda e: self.trocar_tema(proximo.get(self.aj["tema"], "claro")),
                        icon_color=c["texto2"],
                    ),
                    ft.Container(height=8),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=c["sup"],
            border=ft.Border.only(right=ft.BorderSide(1, c["borda"])),
            width=88,
        )

    def foco_container(self) -> ft.Control:
        return self.foco.build() if hasattr(self.foco, "build") else self.foco

    @property
    def barra_propria(self) -> bool:
        """Barra de título desenhada pelo Aprova (no lugar da faixa do Windows).

        Desligada por padrão: na 1.9.2 ela impediu o app de abrir no Windows. Fica disponível para
        testes com APROVA_BARRA_PROPRIA=1 até ser conferida num Windows de verdade."""
        return not self.modo_web and os.environ.get("APROVA_BARRA_PROPRIA") == "1"

    @property
    def baixa(self) -> bool:
        """Janela baixa (ex.: notebook com zoom de 125% ou 150% no Windows): menu mais compacto."""
        return (self.page.height or 900) - (ALTURA_BARRA if self.barra_propria else 0) < 720

    def _barra_lateral(self) -> ft.Container:
        c = self.c
        baixa = self.baixa
        bolha = 30 if baixa else 34
        itens = []
        for chave, rotulo, icone, icone_sel in self.destinos():
            sel = chave == self.secao
            # cada seção é uma bolinha do cartão-resposta; a atual fica "marcada"
            itens.append(
                ft.Container(
                    content=ft.Row(
                        [
                            comp.bolha_icone(icone, c, marcada=sel, tamanho=bolha, icone_marcado=icone_sel),
                            ft.Text(rotulo, size=15 if baixa else 15.5, color=c["texto"] if sel else c["texto2"], weight=ft.FontWeight.W_700 if sel else ft.FontWeight.W_500),
                        ],
                        spacing=14,
                    ),
                    border_radius=22,
                    padding=ft.Padding.only(left=8, right=12, top=3 if baixa else 5, bottom=3 if baixa else 5),
                    on_click=lambda e, k=chave: self.ir(k),
                    ink=True,
                )
            )
        temas = ft.Row(
            [
                comp.apagado("Leitura", c, 12.5),
                ft.Container(expand=True),
                *[
                    ft.IconButton(
                        icon=ic,
                        tooltip=tema.NOMES_TEMA[nome],
                        icon_color=c["tinta"] if self.aj["tema"] == nome else c["texto2"],
                        bgcolor=c["tinta_suave"] if self.aj["tema"] == nome else None,
                        icon_size=20,
                        on_click=lambda e, n=nome: self.trocar_tema(n),
                    )
                    for nome, ic in (
                        ("claro", ft.Icons.LIGHT_MODE_OUTLINED),
                        ("sepia", ft.Icons.AUTO_STORIES_OUTLINED),
                        ("escuro", ft.Icons.DARK_MODE_OUTLINED),
                    )
                ],
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        marca = ft.Row(
            [
                ft.Image(src="icon.png", width=36 if baixa else 44, height=36 if baixa else 44),
                ft.Column(
                    [ft.Text("Aprova", size=24 if baixa else 28, font_family=FONTE_TITULO, weight=ft.FontWeight.W_700, color=c["tinta"])]
                    + ([] if baixa else [ft.Text("estudo para concursos", size=12.5, color=c["texto2"])]),
                    spacing=0,
                ),
            ],
            spacing=10,
        )
        return ft.Container(
            width=236,
            bgcolor=c["sup"],
            border=ft.Border.only(right=ft.BorderSide(1, c["borda"])),
            padding=ft.Padding.only(left=16, right=12, top=(8 if baixa else 14) if self.barra_propria else (14 if baixa else 28), bottom=8 if baixa else 14),
            content=ft.Column(
                ([] if self.barra_propria else [ft.Container(marca, padding=ft.Padding.only(left=6, bottom=8 if baixa else 16))])
                + [
                    ft.Container(self.menu_conta(), padding=ft.Padding.only(left=4, right=2, bottom=6 if baixa else 14)),
                    # os itens rolam se a janela for baixa demais; o rodapé (estudo e leitura) fica sempre à vista
                    ft.Column(itens, spacing=2 if baixa else 4, scroll=ft.ScrollMode.AUTO, expand=True),
                    self._pilula_cronometro(),
                    ft.Container(temas, padding=ft.Padding.only(left=8)),
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
        from .admin import TelaAdmin
        from .grupos import TelaGrupos
        from .painel import TelaPainel
        from .provas import TelaProvas

        classes = {
            "inicio": TelaInicio,
            "concursos": TelaConcursos,
            "provas": TelaProvas,
            "estudar": TelaEstudar,
            "grupos": TelaGrupos,
            "painel": TelaPainel,
            "ajustes": TelaAjustes,
            "admin": TelaAdmin,
        }
        if chave not in self.telas:
            self.telas[chave] = classes[chave](self)
        return self.telas[chave]

    def ir(self, chave: str, reconstruir_layout: bool = True, **kwargs) -> None:
        if self.em_login:
            return
        if chave not in {d[0] for d in self.destinos()}:
            chave = "inicio"
        mudou = chave != self.secao
        extra_antes, extra_agora = self.secao in FORA_DA_BARRA, chave in FORA_DA_BARRA
        if extra_agora and not extra_antes:
            self._antes_extra = self.secao
        self.secao = chave
        if self.foco is not None:
            return
        tela = self._tela(chave)
        if kwargs and hasattr(tela, "preparar"):
            tela.preparar(**kwargs)
        if reconstruir_layout and self._modo_nav == "lateral" and mudou:
            # redesenha a barra lateral para marcar a seção
            self.montar()
            return
        if self._modo_nav == "inferior" and extra_antes != extra_agora:
            self.montar()  # entra ou sai de Ajustes/Admin: mostra ou esconde a barra de baixo
            return
        if self._modo_nav == "inferior" and self.page.navigation_bar is not None:
            self.page.navigation_bar.selected_index = [d[0] for d in self.destinos_barra()].index(chave)
        elif self._modo_nav == "trilho" and mudou and reconstruir_layout:
            self.montar()
            return
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

    def fechar_foco(self, ir_para: str | None = None, **preparar) -> None:
        self.leitor.parar()
        self.foco = None
        if ir_para:
            self.secao = ir_para
        self.telas.pop("inicio", None)
        self.telas.pop("estudar", None)
        if ir_para and preparar:
            tela = self._tela(ir_para)
            if hasattr(tela, "preparar"):
                tela.preparar(**preparar)
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
                margin=ft.Margin.only(top=6, bottom=2),
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
            margin=ft.Margin.only(top=6, bottom=2),
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

    # ------------------------------------------------------------ convites por link

    async def _vigiar_convites(self) -> None:
        """Pega convites que chegam pelo link (aprova://) e marca que o app está aberto."""
        await asyncio.sleep(1.2)
        await self._ler_area_de_transferencia()
        passo = 0
        while True:
            if passo % 15 == 0:
                await self.em_segundo_plano(convite.marcar_vivo)
            pendente = convite.pegar_pendente()
            if pendente:
                try:
                    await self.page.window.to_front()
                except Exception:  # noqa: BLE001
                    pass
                await self.processar_convite(pendente["codigo"], "link")
            passo += 1
            await asyncio.sleep(2)

    async def _evento_janela(self, e) -> None:
        tipo = str(getattr(e, "type", "")).lower()
        if tipo.endswith("focus"):
            await self._ler_area_de_transferencia()
        elif tipo.endswith("maximize") or tipo.endswith("unmaximize") or tipo.endswith("restore"):
            self._atualizar_icone_maximizar()

    async def _ler_area_de_transferencia(self) -> None:
        """Quem clicou no convite antes de instalar o app tem o link copiado: oferece entrar no grupo."""
        if self.modo_web or not self.ranking.configurado or config.FIXTURES_DIR and not os.environ.get("APROVA_LER_AREA"):
            return
        try:
            texto = await ft.Clipboard().get()
        except Exception:  # noqa: BLE001
            return
        if not texto or texto == self._ultimo_texto_area or not convite.eh_convite(texto):
            return
        self._ultimo_texto_area = texto
        codigo = convite.extrair_codigo(texto)
        vistos = list(self.sessao.get("convites_vistos", []) or [])
        if codigo and codigo not in vistos:
            self.sessao.set("convites_vistos", (vistos + [codigo])[-30:])
            await self.processar_convite(codigo, "area")

    async def processar_convite(self, codigo: str, origem: str = "link") -> None:
        """Convite aberto: com conta, entra no grupo; sem conta, mostra a entrada rápida já com o grupo."""
        r = self.ranking
        vistos = list(self.sessao.get("convites_vistos", []) or [])
        if codigo not in vistos:
            self.sessao.set("convites_vistos", (vistos + [codigo])[-30:])
        if not r.configurado:
            self.msg("Este app ainda não está ligado ao servidor dos grupos.")
            return
        try:
            info = await self.em_segundo_plano(r.convite_info, codigo)
        except Exception as ex:  # noqa: BLE001
            self.msg(f"Não deu para abrir o convite: {ex}")
            return
        if not info:
            self.msg(f"O convite {codigo} não vale mais (o grupo pode ter sido apagado).")
            return
        if not (r.logado and r.apelido):
            self.convite = info
            if self.foco is not None:
                self.msg(f"Convite para o grupo {info['nome']} guardado: ao terminar a prova, entre para participar.")
                return
            if self.em_login:
                self._tela_login.modo = "convite"
                self.montar()
            else:
                self.mostrar_login()
            return
        try:
            ja = await self.em_segundo_plano(r.sou_membro, info["codigo"])
        except Exception:  # noqa: BLE001
            ja = False
        if ja:
            if self.foco is None:
                self.ir("grupos", codigo=info["codigo"], aba="conversa")
            self.msg(f"Você já está no grupo {info['nome']}.")
            return
        if origem == "link":
            await self._entrar_no_grupo(info)
            return
        if await self._perguntar(
            f"Entrar no grupo {info['nome']}?",
            f"Você abriu um convite do Aprova. O grupo tem {info['membros']} membro{'s' if info['membros'] != 1 else ''}: "
            "lá a turma conversa, tira dúvidas e compartilha planos de estudo.",
            "Entrar no grupo",
            "Agora não",
        ):
            await self._entrar_no_grupo(info)

    async def _entrar_no_grupo(self, info: dict) -> None:
        try:
            await self.em_segundo_plano(self.ranking.entrar_grupo, info["codigo"])
        except Exception as ex:  # noqa: BLE001
            self.msg(str(ex))
            return
        self.aj.set("grupo_atual", info["codigo"])
        tela = self.telas.get("grupos")
        if tela is not None:
            tela.grupos = None
        if self.foco is None:
            self.ir("grupos", codigo=info["codigo"], aba="conversa")
        self.msg(f"Você entrou no grupo {info['nome']}! 🎉")

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
