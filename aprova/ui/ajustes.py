"""Ajustes: leitura, pausas, voz, acesso pelo celular e chave do Claude."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from .. import __version__, config, rede
from . import comp
from .tema import FONTE_TEXTO, FONTE_TITULO

MODELOS = [
    ("claude-haiku-5-5", "Claude Haiku 5.5 (mais barato e rápido)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (equilibrado)"),
    ("claude-opus-5-5", "Claude Opus 5.5 (mais caprichado)"),
]

COLUNAS_A_PARTIR = 1460  # janela a partir disso: os cartões ficam em duas colunas (cada uma com uns 600 px ou mais)

AMOSTRA = (
    "Assinale a alternativa em que a palavra destacada foi empregada no sentido figurado. "
    "Leia com calma: o tamanho e o espaçamento do texto mudam aqui conforme você ajusta."
)


class TelaAjustes:
    def __init__(self, app):
        self.app = app
        self.qr = ft.Container()

    def build(self) -> ft.Control:
        app, c = self.app, self.app.c
        # duas colunas em telas largas (sem sobrar espaço do lado); numa coluna só, a ordem é a mesma
        esquerda = [self._conta(), self._meu_concurso()]
        if app.desktop:
            esquerda.append(self._tamanho())
        esquerda += [self._leitura(), self._pausa()]
        if app.desktop:
            esquerda.append(self._voz())
        direita = ([] if app.celular else [self._celular()]) + [self._ranking(), self._claude()]
        if app.desktop:
            from .atualizacao import secao_ajustes

            direita.append(secao_ajustes(app, self))
        if not app.modo_web:
            direita.append(self._copia())
        direita.append(self._geral())
        colunas = ft.ResponsiveRow(
            [
                ft.Column(esquerda, spacing=22, col={"um": 12, "dois": 6}, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ft.Column(direita, spacing=22, col={"um": 12, "dois": 6}, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            ],
            spacing=22,
            run_spacing=22,
            breakpoints=comp.quebras(app, {"um": 0, "dois": COLUNAS_A_PARTIR}),
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        return ft.Column([comp.titulo("Ajustes", c, 34 if app.largo else 28), colunas, ft.Container(height=30)], spacing=22,
                         scroll=ft.ScrollMode.AUTO, expand=True)

    # ------------------------------------------------------------------ meu concurso

    def _meu_concurso(self) -> ft.Control:
        from . import meu_concurso

        app, c = self.app, self.app.c
        d = meu_concurso.dados(app)
        if d:
            dia = meu_concurso.data_da_prova(d)
            quando = f"Prova em {dia.strftime('%d/%m/%Y')}" if dia else "Sem data da prova"
            filhos: list[ft.Control] = [
                ft.Row([ft.Icon(ft.Icons.FLAG_OUTLINED, color=c["tinta"]), ft.Text(d["nome"], size=16, weight=ft.FontWeight.W_600, color=c["texto"], expand=True)]),
                comp.apagado(f"{quando} · provas na biblioteca achadas por “{d.get('filtro') or '—'}”", c, 13),
                comp.botao_texto("Mudar meu concurso", lambda e: meu_concurso.abrir_dialogo(app), ft.Icons.EDIT_OUTLINED),
            ]
        else:
            filhos = [comp.botao_contorno("Escolher meu concurso", lambda e: meu_concurso.abrir_dialogo(app), ft.Icons.FLAG_OUTLINED)]
        return self._secao("Meu concurso", "Com o concurso e a data da prova, o Início conta os dias e o “Onde focar” olha as provas dele.", *filhos)

    # ------------------------------------------------------------------ cópia de segurança

    def _copia(self) -> ft.Control:
        from .. import copia

        app, c = self.app, self.app.c
        auto = copia.automaticas(app.pasta_conta)
        ultima = next((a for a in auto if a.name.startswith("semanal-")), None)
        filhos: list[ft.Control] = [
            comp.apagado("Seus estudos ficam só neste aparelho. Salve uma cópia num pen drive ou no seu Drive para não perder nada "
                         "se trocar ou formatar o computador. O Aprova também guarda sozinho uma cópia por semana.", c, 13),
            ft.Row(
                [
                    comp.botao("Salvar cópia agora", lambda e: app.page.run_task(self._salvar_copia), ft.Icons.SAVE_ALT),
                    comp.botao_contorno("Restaurar de uma cópia", lambda e: app.page.run_task(self._escolher_copia), ft.Icons.RESTORE),
                ],
                wrap=True,
                spacing=10,
                run_spacing=10,
            ),
        ]
        if ultima is not None:
            from datetime import datetime

            quando = datetime.fromtimestamp(ultima.stat().st_mtime).strftime("%d/%m às %H:%M")
            filhos.append(ft.Row([comp.apagado(f"Última cópia automática: {quando}.", c, 12.5),
                                  comp.botao_texto("Restaurar esta", lambda e, a=ultima: app.page.run_task(self._confirmar_restauro, a), ft.Icons.HISTORY)],
                                 wrap=True, spacing=4))
        return self._secao("Cópia de segurança", "Leve seus estudos para outro computador ou volte a um ponto anterior.", *filhos)

    async def _salvar_copia(self):
        import tempfile

        from .. import copia

        app = self.app
        nome = copia.nome_sugerido()
        if app.desktop:
            picker = getattr(app, "_picker", None) or ft.FilePicker()
            app._picker = picker
            destino = await picker.save_file(dialog_title="Salvar cópia de segurança do Aprova", file_name=nome,
                                             file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["aprova"])
            if not destino:
                return
            destino = Path(destino)
            if destino.suffix.lower() != copia.EXTENSAO:
                destino = destino.with_name(destino.name + copia.EXTENSAO)
        else:
            destino = Path(tempfile.mkdtemp(prefix="aprova_copia_")) / nome
        try:
            resumo = await app.em_segundo_plano(copia.criar, app.pasta_conta, destino, app.db)
        except (copia.ErroCopia, OSError) as e:
            app.msg(f"Não deu para salvar a cópia: {e}")
            return
        if app.desktop:
            app.msg(f"Cópia salva: {destino.name} ({resumo['respondidas']} respostas, {resumo['provas']} provas).")
        else:
            await app.compartilhar_arquivo(destino)

    async def _escolher_copia(self):
        import tempfile

        app = self.app
        picker = getattr(app, "_picker", None) or ft.FilePicker()
        app._picker = picker
        arquivos = await picker.pick_files(dialog_title="Escolha a cópia de segurança (.aprova)", file_type=ft.FilePickerFileType.CUSTOM,
                                           allowed_extensions=["aprova", "zip"], with_data=not app.desktop)
        if not arquivos:
            return
        f = arquivos[0]
        if f.path:
            arquivo = Path(f.path)
        elif f.bytes:
            arquivo = Path(tempfile.mkdtemp(prefix="aprova_copia_")) / (f.name or "copia.aprova")
            arquivo.write_bytes(f.bytes)
        else:
            return
        await self._confirmar_restauro(arquivo)

    async def _confirmar_restauro(self, arquivo: Path):
        from datetime import datetime

        from .. import copia

        app = self.app
        try:
            resumo = await app.em_segundo_plano(copia.ler, arquivo)
        except copia.ErroCopia as e:
            app.msg(str(e))
            return
        try:
            quando = datetime.fromisoformat(resumo["criada_em"]).strftime("%d/%m/%Y às %H:%M")
        except (KeyError, ValueError):
            quando = "data desconhecida"

        async def restaurar(e):
            app.page.pop_dialog()
            try:
                await app.em_segundo_plano(copia.restaurar, arquivo, app.pasta_conta, app.db, app.aj)
            except (copia.ErroCopia, OSError) as ex:
                app.msg(f"Não deu para restaurar: {ex}")
                return
            app.telas.clear()
            app.ir("inicio")
            app.msg(f"Estudos restaurados da cópia de {quando}.")

        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restaurar esta cópia?", font_family=FONTE_TITULO),
                content=ft.Text(
                    f"Cópia de {quando}: {resumo['provas']} provas e {resumo['respondidas']} questões respondidas.\n\n"
                    "Os estudos de agora serão trocados pelos da cópia. Antes, o Aprova guarda uma cópia do que existe agora "
                    "(em .aprova/copias), então dá para voltar atrás.",
                    size=14.5,
                ),
                actions=[ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()), comp.botao("Restaurar", restaurar, ft.Icons.RESTORE)],
            )
        )

    def _tamanho(self) -> ft.Control:
        """Zoom da interface inteira (cabe mais coisa na tela, ou tudo fica maior)."""
        app, _c = self.app, self.app.c
        escolha = str(app.sessao.get("escala_interface") or "auto")
        opcoes = [("auto", "Automático"), ("0.8", "80%"), ("0.9", "90%"), ("1.0", "100%"), ("1.1", "110%"), ("1.25", "125%")]
        if escolha not in {k for k, _ in opcoes}:
            escolha = "auto"
        seletor = ft.SegmentedButton(
            selected=[escolha],
            segments=[ft.Segment(value=k, label=ft.Text(v)) for k, v in opcoes],
            show_selected_icon=False,
            on_change=lambda e: app.mudar_escala(e.control.selected[0] if e.control.selected else "auto"),
        )
        agora = int(round(app.escala * 100))
        return self._secao(
            "Tamanho da interface",
            f"Deixa tudo menor para caber mais coisa na tela, ou maior para ler melhor. Agora: {agora}%. "
            "No automático, o Aprova diminui sozinho em notebooks com o zoom do Windows em 125% ou 150%. "
            "Atalhos: Ctrl + e Ctrl − (Ctrl 0 volta ao automático).",
            ft.Row([seletor], scroll=ft.ScrollMode.AUTO),
        )

    def _secao(self, titulo: str, descricao: str, *filhos: ft.Control) -> ft.Control:
        c = self.app.c
        return comp.bloco(
            ft.Column([comp.subtitulo(titulo, c, 20), comp.apagado(descricao, c, 14), *filhos], spacing=12),
            c,
            padding=24,
        )

    # ------------------------------------------------------------------ leitura

    def _leitura(self) -> ft.Control:
        app, c = self.app, self.app.c
        amostra = ft.Text(
            AMOSTRA,
            size=18 * float(app.aj["fonte_escala"]),
            font_family=FONTE_TEXTO,
            color=c["texto"],
            style=ft.TextStyle(height=float(app.aj["entrelinha"])),
        )
        caixa = ft.Container(amostra, bgcolor=c["bg"], border_radius=12, padding=18, border=ft.Border.all(1, c["borda"]))

        def mudar_fonte(e):
            app.aj.set("fonte_escala", round(float(e.control.value), 2))
            amostra.size = 18 * float(e.control.value)
            amostra.update()

        def mudar_linha(e):
            app.aj.set("entrelinha", round(float(e.control.value), 2))
            amostra.style = ft.TextStyle(height=float(e.control.value))
            amostra.update()

        temas = ft.SegmentedButton(
            selected=[app.aj["tema"]],
            segments=[
                ft.Segment(value="claro", label=ft.Text("Claro"), icon=ft.Icon(ft.Icons.LIGHT_MODE_OUTLINED)),
                ft.Segment(value="sepia", label=ft.Text("Sépia"), icon=ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED)),
                ft.Segment(value="escuro", label=ft.Text("Escuro"), icon=ft.Icon(ft.Icons.DARK_MODE_OUTLINED)),
            ],
            on_change=lambda e: app.trocar_tema(e.control.selected[0]),
        )
        return self._secao(
            "Leitura confortável",
            "O tema sépia imita papel e reduz o brilho em sessões longas. A fonte das questões (Atkinson Hyperlegible) foi desenhada para ser fácil de ler.",
            temas,
            ft.Row([comp.texto("Tamanho do texto", c, 14.5), ft.Container(expand=True)]),
            ft.Slider(min=0.8, max=1.8, divisions=10, value=float(app.aj["fonte_escala"]), label="{value}x", on_change=mudar_fonte),
            comp.texto("Espaço entre linhas", c, 14.5),
            ft.Slider(min=1.3, max=2.1, divisions=8, value=float(app.aj["entrelinha"]), label="{value}", on_change=mudar_linha),
            caixa,
        )

    def _pausa(self) -> ft.Control:
        app, _c = self.app, self.app.c

        def alternar(e):
            app.aj.set("pausa_olhos", bool(e.control.value))

        def minutos(e):
            app.aj.set("pausa_minutos", int(e.control.value))

        return self._secao(
            "Pausa para os olhos",
            "A regra 20-20-20: a cada 20 minutos, olhe para algo a 6 metros por 20 segundos. O Aprova avisa e conta o tempo para você.",
            ft.Row(
                [
                    ft.Switch(value=bool(app.aj["pausa_olhos"]), label="Lembrar de descansar", on_change=alternar),
                    ft.Dropdown(
                        value=str(app.aj["pausa_minutos"]),
                        options=[ft.DropdownOption(key=str(m), text=f"a cada {m} min") for m in (15, 20, 30, 45, 60)],
                        on_select=minutos,
                        width=200,
                        dense=True,
                    ),
                ],
                wrap=True,
                spacing=20,
                run_spacing=10,
            ),
            comp.botao_texto("Testar agora", lambda e: app.page.run_task(app.mostrar_pausa), ft.Icons.VISIBILITY_OUTLINED),
        )

    def _voz(self) -> ft.Control:
        app, c = self.app, self.app.c

        def velocidade(e):
            app.aj.set("voz_velocidade", int(e.control.value))

        def testar(e):
            ok = app.leitor.falar(
                "Olá! Eu leio as questões em voz alta para você descansar a vista.", int(app.aj["voz_velocidade"] or 0)
            )
            if not ok:
                comp.mensagem(app.page, "Não encontrei uma voz instalada no sistema.")

        filhos: list[ft.Control] = []
        if not app.leitor.disponivel:
            filhos.append(comp.aviso("Nenhuma voz encontrada neste computador. No Windows, instale a voz em português em Configurações > Hora e idioma > Fala.", c, "alerta"))
        filhos += [
            comp.texto("Velocidade da voz", c, 14.5),
            ft.Slider(min=-5, max=5, divisions=10, value=int(app.aj["voz_velocidade"] or 0), label="{value}", on_change_end=velocidade),
            ft.Row([comp.botao_contorno("Testar voz", testar, ft.Icons.VOLUME_UP_OUTLINED), comp.botao_texto("Parar", lambda e: app.leitor.parar())], spacing=10),
        ]
        return self._secao(
            "Ouvir as questões",
            "Na prova, o botão de alto-falante lê o enunciado e as alternativas com a voz do sistema, sem internet.",
            *filhos,
        )

    # ------------------------------------------------------------------ celular

    def _celular(self) -> ft.Control:
        app, c = self.app, self.app.c
        if app.modo_web:
            return self._secao(
                "Versão para celular",
                "Você está usando o Aprova pelo navegador. Para instalar como app, use “Adicionar à tela inicial” no menu do navegador.",
            )
        estado = ft.Column(spacing=10)

        def mostrar():
            estado.controls.clear()
            if app.servidor.ativo:
                url = app.servidor.endereco()
                png = rede.qr_png(url)
                linha: list[ft.Control] = []
                if png:
                    linha.append(ft.Container(ft.Image(src=png, width=170, height=170), bgcolor="#FFFFFF", border_radius=12, padding=6))
                linha.append(
                    ft.Column(
                        [
                            comp.texto("Aponte a câmera do celular para o QR code ou digite o endereço inteiro:", c, 14.5),
                            ft.Text(url, size=18, weight=ft.FontWeight.W_700, color=c["tinta"], selectable=True),
                            comp.apagado(
                                "O celular precisa estar no mesmo Wi-Fi que este computador. Se não abrir, permita o Python no firewall do Windows (redes privadas).",
                                c,
                                13,
                            ),
                            comp.botao_contorno("Desligar acesso", desligar, ft.Icons.PHONELINK_OFF),
                        ],
                        spacing=8,
                        expand=True,
                    )
                )
                if app.largo:
                    estado.controls.append(ft.Row(linha, spacing=18, vertical_alignment=ft.CrossAxisAlignment.START))
                else:
                    for item in linha:
                        item.expand = False
                    estado.controls.append(ft.Column(linha, spacing=14))
            else:
                estado.controls.append(comp.botao("Ligar acesso pelo celular", ligar, ft.Icons.PHONE_ANDROID))

        def ligar(e):
            app.servidor.ligar()
            mostrar()
            app.page.update()

        def desligar(e):
            app.servidor.desligar()
            mostrar()
            app.page.update()

        mostrar()
        return self._secao(
            "Usar no celular",
            "Abre o Aprova no navegador do celular, com o mesmo progresso deste computador. Funciona enquanto o computador estiver ligado com o Aprova aberto. O endereço leva um código secreto: sem ele, ninguém no mesmo Wi-Fi abre o seu Aprova. Cada vez que você liga o acesso, o código muda.",
            estado,
        )

    # ------------------------------------------------------------------ Claude

    def _conta(self) -> ft.Control:
        app, c = self.app, self.app.c
        from .login import dialogo_conta

        from .personagem import abrir_criador

        r = app.ranking
        if r.logado:
            papel = "administrador" if r.eh_admin else "aluno"
            filhos = [
                ft.Row([app.menu_conta(), ], spacing=8),
                comp.apagado(f"Você entrou como {papel}. Seus estudos ficam separados dos de outras contas neste computador.", c, 13),
                ft.Row(
                    [
                        comp.botao_contorno("Minha conta", lambda e: dialogo_conta(app), ft.Icons.MANAGE_ACCOUNTS_OUTLINED),
                        comp.botao_contorno("Personagem e foto", lambda e: abrir_criador(app), ft.Icons.AUTO_FIX_HIGH),
                        comp.botao_texto("Sair / trocar de conta", lambda e: app.sair_da_conta(), ft.Icons.LOGOUT),
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ]
        else:
            filhos = [
                comp.apagado("Você está usando o Aprova sem conta: os estudos ficam só neste computador e você não aparece no ranking.", c, 13.5),
                ft.Row(
                    [comp.botao("Entrar ou criar conta", lambda e: app.mostrar_login(), ft.Icons.LOGIN),
                     comp.botao_contorno("Criar personagem", lambda e: abrir_criador(app), ft.Icons.AUTO_FIX_HIGH)],
                    spacing=8,
                    wrap=True,
                ),
            ]
        return self._secao("Conta", "Quem está usando o Aprova agora.", *filhos)

    def _ranking(self) -> ft.Control:
        app, c = self.app, self.app.c
        from .ranking import dialogo_servidor

        r = app.ranking
        if not r.configurado:
            estado = "Servidor ainda não configurado."
        elif r.logado and r.apelido:
            estado = f"Conectado como {r.apelido}."
        else:
            estado = "Servidor configurado. Entre ou crie sua conta em Painel → Ranking."
        filhos: list[ft.Control] = [
            comp.texto(estado, c, 14.5),
            ft.Row(
                [comp.botao_contorno("Abrir o ranking", lambda e: app.ir("painel", aba="ranking"), ft.Icons.LEADERBOARD_OUTLINED)]
                + ([] if not app.desktop else [comp.botao_texto("Servidor do ranking", lambda e: dialogo_servidor(app, lambda: (r.recarregar_config(), app.recarregar_tela())), ft.Icons.SETTINGS_OUTLINED)]),
                spacing=8,
                wrap=True,
            ),
        ]
        return self._secao("Ranking", "Compare suas horas, questões e acerto da semana com outras pessoas.", *filhos)

    def _claude(self) -> ft.Control:
        app, c = self.app, self.app.c
        tem_chave = bool(app.aj.chave_claude)
        status = comp.pilula("Chave configurada" if tem_chave else "Sem chave", c["ok_suave"] if tem_chave else c["sup2"], c["ok"] if tem_chave else c["texto2"])
        campo = ft.TextField(
            value="" if app.modo_web else app.aj["claude_api_key"],
            hint_text="sk-ant-...",
            password=True,
            can_reveal_password=not app.modo_web,
            border_radius=10,
            dense=True,
            expand=True,
        )

        def salvar(e):
            valor = (campo.value or "").strip()
            if app.modo_web and not valor:
                return
            app.aj.set("claude_api_key", valor)
            comp.mensagem(app.page, "Chave salva." if valor else "Chave removida.")
            app.recarregar_tela_sem_perder(self)

        modelo = ft.Dropdown(
            value=app.aj["claude_modelo"],
            options=[ft.DropdownOption(key=k, text=v) for k, v in MODELOS],
            on_select=lambda e: app.aj.set("claude_modelo", e.control.value),
            width=340,
            dense=True,
        )
        from .chat import dialogo_chave

        return self._secao(
            "Explicações com IA (opcional)",
            "Sem chave, a ajuda já pesquisa na internet e mostra as fontes, e os botões Perguntar ao Claude e Perguntar ao ChatGPT "
            "levam a questão para o chat no navegador (com a sua conta, grátis). Com a chave da API do Claude, a IA trabalha aqui "
            "dentro: explica cada questão, cria questões novas nos simulados e analisa o seu resultado. O uso da chave é cobrado pela "
            "Anthropic, com crédito pré-pago.",
            status,
            comp.botao("Passo a passo: como conseguir a chave", lambda e: dialogo_chave(app), ft.Icons.KEY_OUTLINED),
            ft.Row([campo, comp.botao("Salvar", salvar)], spacing=10),
            modelo,
        )

    # ------------------------------------------------------------------ geral

    def _geral(self) -> ft.Control:
        app, c = self.app, self.app.c
        nome = ft.TextField(value=app.aj["nome"], label="Seu nome (para a saudação)", border_radius=10, dense=True, width=320, on_blur=lambda e: app.aj.set("nome", (e.control.value or "").strip()))
        filhos: list[ft.Control] = [nome]
        if app.desktop:
            pasta = ft.TextField(value=app.aj["pasta_downloads"], label="Pasta onde o navegador salva os downloads", border_radius=10, dense=True, expand=True, on_blur=lambda e: app.aj.set("pasta_downloads", e.control.value))

            async def escolher(e):
                picker = getattr(app, "_picker", None) or ft.FilePicker()
                app._picker = picker
                caminho = await picker.get_directory_path(dialog_title="Pasta de downloads")
                if caminho:
                    pasta.value = caminho
                    app.aj.set("pasta_downloads", caminho)
                    pasta.update()

            filhos.append(ft.Row([pasta, ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="Escolher pasta", on_click=escolher)], spacing=6))
            filhos.append(comp.apagado(f"Seus dados ficam em {config.DATA_DIR}", c, 13))

        def limpar_cache(e):
            n = 0
            for p in Path(config.CACHE_DIR).glob("*.html"):
                p.unlink(missing_ok=True)
                n += 1
            app.telas.pop("concursos", None)
            comp.mensagem(app.page, f"{n} páginas guardadas foram apagadas. As listas serão baixadas de novo.")

        filhos.append(comp.botao_texto("Atualizar dados do site (limpar cache)", limpar_cache, ft.Icons.REFRESH))
        filhos.append(
            comp.apagado(
                f"Aprova {__version__}. Concursos e provas vêm do PCI Concursos (pciconcursos.com.br). Confirme sempre datas e regras no edital oficial.",
                c,
                12.5,
            )
        )
        return self._secao("Geral", "Seu nome, pastas e dados guardados.", *filhos)
