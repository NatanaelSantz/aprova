"""Personagem e foto de perfil na tela.

- criador de personagem estilo RPG (pele, cabelo, olhos, roupa, acessório, item e cenário) ou foto;
- o "lobby": o boneco animado no cenário (respira, pisca, acena e pula);
- o busto redondo nas listas (grupos, mensagens, ranking), com a foto quando a pessoa escolheu foto;
- a sala da turma: os bonecos de todo mundo do grupo lado a lado, cada um com o seu gesto.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import flet as ft

from .. import avatar as av
from .. import config
from ..ranking import ErroRanking
from . import comp
from .tema import FONTE_TITULO

ARQ_FOTO = "avatar-foto.webp"
_CACHE: dict = {}
_FOTOS: dict[tuple[str, int], bytes | None] = {}  # fotos de outras pessoas já baixadas (uid, versão)


def _guardado(chave, fazer):
    if chave not in _CACHE:
        if len(_CACHE) > 400:
            _CACHE.clear()
        _CACHE[chave] = fazer()
    return _CACHE[chave]


def img_lobby(cfg: dict, anim: str = "lobby", escala: int = 2, largura: int = 64) -> bytes:
    """Boneco no cenário: (2 x largura x escala) por (80 x escala) pixels."""
    return _guardado(("lobby", av.chave_cache(cfg, anim, escala, largura)), lambda: av.animacao(cfg, anim, escala, largura=largura))


def img_sozinho(cfg: dict, anim: str = "parado", escala: int = 1) -> bytes:
    """Boneco sem cenário: 64 x 80 por escala."""
    return _guardado(("so", av.chave_cache(cfg, anim, escala)), lambda: av.animacao(cfg, anim, escala, cenario=False))


def img_rosto(cfg: dict, escala: int = 1) -> bytes:
    """Busto: 40 x 40 por escala."""
    return _guardado(("rosto", av.chave_cache(cfg, escala)), lambda: av.rosto(cfg, escala))


def img_membro(cfg: dict, semente: str, escala: int = 1) -> bytes:
    return _guardado(("membro", av.chave_cache(cfg, semente, escala)), lambda: av.membro(cfg, semente, escala))


def img_cenario(nome: str, largura: int, escala: int) -> bytes:
    return _guardado(("cena", nome, largura, escala), lambda: av.cenario_png(nome, largura, escala, quadros=4))


def _pixel(dados: bytes, largura: float, altura: float, ajuste=ft.BoxFit.NONE, **kw) -> ft.Image:
    """Imagem de pixel art: sem borrar e sem piscar quando troca."""
    return ft.Image(src=dados, width=largura, height=altura, fit=ajuste, filter_quality=ft.FilterQuality.NONE, gapless_playback=True, **kw)


# ---------------------------------------------------------------------- o meu personagem

def meu(app) -> dict:
    return av.validar(app.aj.get("avatar"))


def tenho_personagem(app) -> bool:
    return av.tem_personagem(app.aj.get("avatar"))


def minha_foto(app) -> bytes | None:
    try:
        caminho = Path(app.pasta_conta) / ARQ_FOTO
        return caminho.read_bytes() if caminho.exists() else None
    except OSError:
        return None


async def salvar_meu(app, cfg: dict, foto: bytes | None = None, apagar_foto: bool = False) -> dict:
    """Guarda neste computador e, se a pessoa está numa conta, manda para a turma ver."""
    cfg = av.validar(cfg)
    cfg["t"] = av.agora()
    pasta = Path(app.pasta_conta)
    try:
        if foto:
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / ARQ_FOTO).write_bytes(foto)
            cfg["foto"] = av.agora()
        elif apagar_foto:
            (pasta / ARQ_FOTO).unlink(missing_ok=True)
            cfg["foto"], cfg["usar_foto"] = 0, False
    except OSError as e:
        config.registrar(f"avatar: não salvou a foto ({e!r})")
    cfg = av.validar(cfg)
    app.aj.set("avatar", cfg)
    if app.ranking.configurado and app.ranking.logado:
        try:
            if foto:
                await app.em_segundo_plano(app.ranking.enviar_foto, foto)
            elif apagar_foto:
                await app.em_segundo_plano(app.ranking.apagar_foto)
            await app.em_segundo_plano(app.ranking.salvar_avatar, cfg)
            app.aj.set("avatar_enviado", cfg["t"])
        except ErroRanking as e:
            app.msg(f"Salvo neste computador. A turma ainda não vê: {e}")
    return cfg


async def sincronizar(app) -> None:
    """Depois de entrar: fica com o personagem mais novo (deste computador ou do servidor)."""
    r = app.ranking
    if not (r.configurado and r.logado):
        return
    try:
        perfil = await app.em_segundo_plano(r.perfil)
    except ErroRanking:
        return
    servidor = av.validar((perfil or {}).get("avatar"))
    local = meu(app)
    try:
        if servidor["t"] > local["t"]:
            if servidor["foto"] and servidor["foto"] != local["foto"]:
                dados = await app.em_segundo_plano(r.baixar_foto, r.usuario_id, servidor["foto"])
                if dados:
                    (Path(app.pasta_conta) / ARQ_FOTO).write_bytes(dados)
                else:
                    servidor["usar_foto"] = False
            app.aj.set("avatar", servidor)
            app.aj.set("avatar_enviado", servidor["t"])
            app.recarregar_tela()
        elif local["t"] > servidor["t"] and app.aj.get("avatar_enviado") != local["t"]:
            foto = minha_foto(app) if local["foto"] else None
            if foto:
                await app.em_segundo_plano(r.enviar_foto, foto)
            await app.em_segundo_plano(r.salvar_avatar, local)
            app.aj.set("avatar_enviado", local["t"])
    except (ErroRanking, OSError) as e:
        config.registrar(f"avatar: não sincronizou ({e})")


# ---------------------------------------------------------------------- busto redondo (listas)

def _iniciais(nome: str, tamanho: float) -> ft.Control:
    from .grupos import avatar as bolinha

    return bolinha(nome or "?", tamanho)


def _circulo(conteudo: ft.Control, tamanho: float, fundo: str, tooltip: str | None = None) -> ft.Container:
    return ft.Container(conteudo, width=tamanho, height=tamanho, border_radius=tamanho / 2, bgcolor=fundo, alignment=ft.Alignment.CENTER,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS, tooltip=tooltip)


def _busto_personagem(cfg: dict, tamanho: float) -> ft.Control:
    escala = max(1, round(tamanho / 34))
    return _circulo(_pixel(img_rosto(cfg, escala), tamanho, tamanho), tamanho, av.cor_fundo(cfg))


def _busto_foto(dados: bytes, tamanho: float) -> ft.Control:
    return _circulo(ft.Image(src=dados, width=tamanho, height=tamanho, fit=ft.BoxFit.COVER, gapless_playback=True), tamanho, "#DDE2EE")


def busto(app, cfg, nome: str, tamanho: float = 36, usuario_id: str | None = None) -> ft.Control:
    """Foto, personagem ou a inicial do nome, nessa ordem. cfg é o avatar que veio do servidor (pode ser None)."""
    if usuario_id and usuario_id == app.ranking.usuario_id:
        return meu_busto(app, tamanho) or _iniciais(nome, tamanho)
    cfg = av.validar(cfg) if isinstance(cfg, dict) else None
    if cfg and cfg["usar_foto"] and cfg["foto"] and usuario_id:
        chave = (usuario_id, cfg["foto"])
        if _FOTOS.get(chave):
            return _busto_foto(_FOTOS[chave], tamanho)
        reserva = _busto_personagem(cfg, tamanho) if av.tem_personagem(cfg) else _iniciais(nome, tamanho)
        caixa = ft.Container(reserva, width=tamanho, height=tamanho)
        if chave not in _FOTOS:
            _FOTOS[chave] = None
            app.page.run_task(_baixar_foto, app, caixa, usuario_id, cfg["foto"], tamanho)
        return caixa
    if cfg and av.tem_personagem(cfg):
        return _busto_personagem(cfg, tamanho)
    return _iniciais(nome, tamanho)


async def _baixar_foto(app, caixa: ft.Container, usuario_id: str, versao: int, tamanho: float) -> None:
    try:
        dados = await app.em_segundo_plano(app.ranking.baixar_foto, usuario_id, versao)
    except ErroRanking:
        dados = None
    _FOTOS[(usuario_id, versao)] = dados
    if dados:
        caixa.content = _busto_foto(dados, tamanho)
        try:
            caixa.update()
        except Exception:  # noqa: BLE001 - a tela já mudou
            pass


def meu_busto(app, tamanho: float = 38) -> ft.Control | None:
    cfg = meu(app)
    if cfg["usar_foto"]:
        foto = minha_foto(app)
        if foto:
            return _busto_foto(foto, tamanho)
    if av.tem_personagem(cfg):
        return _busto_personagem(cfg, tamanho)
    return None


# ---------------------------------------------------------------------- lobby (boneco no cenário)

def lobby(cfg: dict, largura: float, anim: str = "lobby", raio: int = 14, cena: int = 64) -> ft.Container:
    """cena = largura do cenário (64 = inteiro; menos = só o pedaço do meio)."""
    escala = max(1, min(4, int(largura // (2 * cena))))
    w, h = 2 * cena * escala, 80 * escala
    return ft.Container(_pixel(img_lobby(cfg, anim, escala, cena), w, h), border_radius=raio, clip_behavior=ft.ClipBehavior.ANTI_ALIAS, width=w, height=h)


def cartao_inicio(app) -> ft.Control:
    """No Início: o seu boneco no cenário, ou o convite para criar um."""
    c = app.c
    if tenho_personagem(app):
        cfg = meu(app)
        return ft.Container(
            lobby(cfg, 192, raio=12, cena=48),
            on_click=lambda e: abrir_criador(app),
            tooltip="Seu personagem · clique para mudar",
            border_radius=12,
            ink=True,
        )
    exemplo = av.sortear(app.ranking.usuario_id or "visitante-aprova")
    return ft.Container(
        ft.Row(
            [
                _pixel(img_sozinho(exemplo, "aceno", 1), 64, 80),
                ft.Column(
                    [
                        ft.Text("Crie o seu personagem", size=14.5, weight=ft.FontWeight.W_700, color=c["texto"]),
                        comp.apagado("Um bonequinho estilo RPG que aparece para a sua turma.", c, 12.5),
                    ],
                    spacing=2,
                    width=170,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        on_click=lambda e: abrir_criador(app),
        ink=True,
        padding=ft.Padding.only(left=6, right=14, top=6, bottom=6),
        border_radius=14,
        bgcolor=c["sup"],
        border=ft.Border.all(1, c["borda"]),
    )


def comemoracao(app, pct: float) -> ft.Control | None:
    """No resultado do simulado: o seu boneco comemora (ou acena dando força)."""
    if not tenho_personagem(app):
        return None
    anim = "pulo" if pct >= 0.7 else "aceno"
    return _pixel(img_sozinho(meu(app), anim, 2), 128, 160, tooltip="Boa!" if pct >= 0.7 else "Bora pra próxima!")


# ---------------------------------------------------------------------- sala da turma

def sala_da_turma(app, membros: list[dict], cenario: str = "biblioteca", largura_max: float = 900) -> ft.Control | None:
    """Os bonecos do grupo lado a lado no cenário (até 10), cada um com o seu gesto."""
    if not membros:
        return None
    c = app.c
    lista = sorted(membros, key=lambda m: (not m.get("voce"), not m.get("criador"), (m.get("apelido") or "").lower()))[:10]
    n = len(lista)
    passo = 22  # largura de cada pessoa no cenário (grade de montagem; na tela é o dobro)
    minimo = max(64, passo * n + 20)
    escala = 2 if 2 * minimo * 2 <= largura_max else 1
    # o cenário ocupa a largura toda do cartão (sem faixas vazias dos lados), até um limite
    largura_px = max(minimo, min(int(largura_max / (2 * escala)) // 8 * 8, 440))
    vaga = min(2 * largura_px * escala / n, 2 * passo * escala * 1.6)  # as pessoas se espalham um pouco pela sala
    fundo = _pixel(img_cenario(cenario, largura_px, escala), 2 * largura_px * escala, 80 * escala)
    pessoas = []
    for m in lista:
        cfg = m.get("avatar") if isinstance(m.get("avatar"), dict) else None
        if m.get("voce"):
            cfg = meu(app) if tenho_personagem(app) else cfg
        cfg = av.validar(cfg) if cfg and av.tem_personagem(cfg) else av.sortear(m.get("usuario_id") or m.get("apelido") or "?")
        boneco = _pixel(img_membro(cfg, m.get("usuario_id") or m.get("apelido") or "?", escala), 64 * escala, 80 * escala)
        nome = ft.Container(
            ft.Text(m.get("apelido") or "?", size=11, weight=ft.FontWeight.W_700, color="#FFFFFF", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                    text_align=ft.TextAlign.CENTER),
            bgcolor="#B3141A33" if not m.get("voce") else "#E62340A8",
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=6, vertical=1),
        )
        pessoas.append(
            ft.Container(
                ft.Column([boneco, nome], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                width=vaga,
                tooltip=m.get("apelido") or "",
            )
        )
    fila = ft.Row(pessoas, spacing=0, alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.END)
    cena = ft.Stack(
        [fundo, ft.Container(fila, left=0, right=0, bottom=4 * escala)],
        width=2 * largura_px * escala,
        height=80 * escala + 6,
    )
    sem = sum(1 for m in lista if not (isinstance(m.get("avatar"), dict) and av.tem_personagem(m["avatar"])) and not m.get("voce"))
    rodape = []
    if not tenho_personagem(app):
        rodape.append(comp.botao_texto("Criar o meu personagem", lambda e: abrir_criador(app), ft.Icons.AUTO_FIX_HIGH))
    elif sem:
        rodape.append(comp.apagado("Quem ainda não criou o seu aparece com um personagem sorteado.", c, 12))
    return ft.Column(
        [
            ft.Container(ft.Row([cena], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.CENTER), border_radius=12,
                         clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
            *([ft.Row(rodape, wrap=True)] if rodape else []),
        ],
        spacing=4,
    )


# ---------------------------------------------------------------------- criador de personagem

ABAS_CRIADOR = [("corpo", "Corpo"), ("rosto", "Rosto"), ("cabelo", "Cabelo"), ("oculos", "Óculos"), ("roupa", "Roupa"), ("acessorios", "Acessórios"),
                ("cenario", "Cenário"), ("foto", "Foto")]


def abrir_criador(app, ao_salvar=None, aba: str = "corpo") -> None:
    c = app.c
    estado = {
        "cfg": dict(meu(app)) if tenho_personagem(app) else av.sortear(app.ranking.usuario_id or app.aj.get("nome") or None),
        "aba": aba if aba in dict(ABAS_CRIADOR) else "corpo",
        "foto": None,  # foto nova escolhida agora (bytes)
        "apagar_foto": False,
        "gesto": "lobby",
    }
    foto_atual = minha_foto(app)
    largura_tela = app.largura or 900
    estreito = largura_tela < 820
    escala_previa = 2 if estreito else 3
    previa = _pixel(img_lobby(estado["cfg"], "lobby", escala_previa), 128 * escala_previa, 80 * escala_previa)
    opcoes = ft.Column(spacing=14, tight=True)
    abas = ft.Row(wrap=True, spacing=5, run_spacing=6)  # abas que quebram linha: todas sempre à vista

    def montar_abas():
        abas.controls = [
            ft.Container(
                ft.Text(rotulo, size=13.5, weight=ft.FontWeight.W_700 if k == estado["aba"] else ft.FontWeight.W_500,
                        color=c["tinta"] if k == estado["aba"] else c["texto2"]),
                bgcolor=c["tinta_suave"] if k == estado["aba"] else None,
                border=ft.Border.all(1.4, c["tinta"] if k == estado["aba"] else c["borda"]),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=10, vertical=7),  # compactas: as 8 abas cabem numa linha
                on_click=lambda e, k=k: trocar_aba(k),
                ink=True,
            )
            for k, rotulo in ABAS_CRIADOR
        ]
        try:
            abas.update()
        except Exception:  # noqa: BLE001
            pass

    def atualizar_previa(gesto: str = "lobby"):
        estado["gesto"] = gesto
        previa.src = img_lobby(estado["cfg"], gesto, escala_previa)
        try:
            previa.update()
        except Exception:  # noqa: BLE001
            pass

    async def gesto(nome: str, segundos: float):
        atualizar_previa(nome)
        await asyncio.sleep(segundos)
        if estado["gesto"] == nome:
            atualizar_previa("lobby")

    def mudar(chave, valor):
        estado["cfg"][chave] = valor
        atualizar_previa(estado["gesto"] if estado["gesto"] == "lobby" else "lobby")
        montar_opcoes()

    def chip(rotulo, marcado, ao_clicar):
        return ft.Container(
            ft.Text(rotulo, size=13, weight=ft.FontWeight.W_600, color=c["sobre_tinta"] if marcado else c["texto"]),
            bgcolor=c["tinta"] if marcado else c["sup2"],
            border_radius=999,
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            on_click=ao_clicar,
            ink=True,
        )

    def amostra(cor, nome, marcado, ao_clicar):
        return ft.Container(
            ft.Container(width=26, height=26, border_radius=13, bgcolor=cor, border=ft.Border.all(1, "#33000000")),
            padding=3,
            border_radius=17,
            border=ft.Border.all(2.5, c["tinta"] if marcado else "#00000000"),
            on_click=ao_clicar,
            tooltip=nome,
            ink=True,
        )

    def linha_estilos(titulo, chave, lista):
        return ft.Column(
            [comp.apagado(titulo, c, 12.5),
             ft.Row([chip(r, estado["cfg"][chave] == v, lambda e, v=v: mudar(chave, v)) for v, r in lista], wrap=True, spacing=6, run_spacing=6)],
            spacing=6,
        )

    def linha_cores(titulo, chave, lista):
        return ft.Column(
            [comp.apagado(titulo, c, 12.5),
             ft.Row([amostra(h, n, estado["cfg"][chave] == i, lambda e, i=i: mudar(chave, i)) for i, (h, n) in enumerate(lista)], wrap=True, spacing=2, run_spacing=2)],
            spacing=6,
        )

    def montar_opcoes():
        aba = estado["aba"]
        if aba == "corpo":
            filhos = [linha_estilos("Tipo de corpo", "corpo", av.CORPOS), linha_cores("Pele", "pele", av.PELES),
                      comp.apagado("Toda roupa, capa e mochila se ajusta ao tipo de corpo.", c, 12)]
        elif aba == "rosto":
            filhos = [linha_estilos("Olhos", "olhos", av.OLHOS), linha_cores("Cor dos olhos", "cor_olhos", av.CORES_OLHOS),
                      linha_estilos("Boca", "boca", av.BOCAS), linha_estilos("Detalhes", "marca", av.MARCAS)]
        elif aba == "cabelo":
            filhos = [linha_estilos("Corte", "cabelo", av.CABELOS), linha_cores("Cor", "cor_cabelo", av.CORES_CABELO),
                      linha_estilos("Barba e bigode", "barba", av.BARBAS),
                      comp.apagado("A barba usa a cor do cabelo.", c, 12)]
        elif aba == "roupa":
            filhos = [linha_estilos("Roupa", "roupa", av.ROUPAS), linha_cores("Cor", "cor_roupa", av.CORES_ROUPA),
                      linha_cores("Cor da calça", "cor_calca", av.CORES_CALCA)]
        elif aba == "oculos":
            filhos = [linha_estilos("Modelo", "oculos", av.OCULOS), linha_cores("Cor da armação", "cor_oculos", av.CORES_OCULOS),
                      comp.apagado("Os óculos combinam com qualquer chapéu ou acessório.", c, 12)]
        elif aba == "acessorios":
            filhos = [linha_estilos("Na cabeça", "acessorio", av.ACESSORIOS), linha_estilos("Pescoço e costas", "extra", av.EXTRAS),
                      linha_estilos("Na mão", "item", av.ITENS)]
        elif aba == "cenario":
            filhos = [linha_estilos("Onde o seu personagem fica", "cenario", av.CENARIOS),
                      comp.apagado("O cenário aparece no Início e quando você abre o personagem.", c, 12)]
        else:
            filhos = [parte_foto()]
        opcoes.controls = filhos
        try:
            opcoes.update()
        except Exception:  # noqa: BLE001
            pass

    def parte_foto() -> ft.Control:
        dados = estado["foto"] or (None if estado["apagar_foto"] else foto_atual)
        mostra = _busto_foto(dados, 96) if dados else _circulo(ft.Icon(ft.Icons.PERSON_OUTLINE, size=44, color=c["texto2"]), 96, c["sup2"])
        usar = ft.Switch(
            label="Mostrar a foto no lugar do personagem nos grupos e no ranking",
            value=bool(dados) and estado["cfg"].get("usar_foto", False),
            disabled=not dados,
            on_change=lambda e: estado["cfg"].__setitem__("usar_foto", bool(e.control.value)),
        )
        botoes = [comp.botao_contorno("Escolher foto", lambda e: app.page.run_task(escolher_foto), ft.Icons.ADD_A_PHOTO_OUTLINED)]
        if dados:
            botoes.append(comp.botao_texto("Tirar a foto", lambda e: tirar_foto(), ft.Icons.DELETE_OUTLINE))
        return ft.Column(
            [
                ft.Row([mostra, ft.Column([ft.Row(botoes, wrap=True, spacing=6), usar], spacing=8, expand=True)], spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                comp.apagado("A foto é recortada em quadrado e fica pequena. Quem usa o Aprova vê a foto nos grupos e no ranking; "
                             "o personagem continua aparecendo no Início e na sala da turma.", c, 12),
            ],
            spacing=10,
        )

    async def escolher_foto():
        picker = getattr(app, "_picker", None)
        if picker is None:
            picker = ft.FilePicker()
            app._picker = picker
        arquivos = await picker.pick_files(
            dialog_title="Escolha uma foto para o perfil",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["jpg", "jpeg", "png", "webp", "gif", "bmp"],
            with_data=app.modo_web,
        )
        if not arquivos:
            return
        f = arquivos[0]
        try:
            bruto = f.bytes if f.bytes else Path(f.path).read_bytes()
            estado["foto"] = await app.em_segundo_plano(av.preparar_foto, bruto)
        except Exception as e:  # noqa: BLE001 - imagem quebrada ou grande demais
            app.msg(f"Não consegui usar essa imagem: {e}" if isinstance(e, ValueError) else "Não consegui abrir essa imagem. Tente outra (JPG ou PNG).")
            return
        estado["apagar_foto"] = False
        estado["cfg"]["usar_foto"] = True
        montar_opcoes()

    def tirar_foto():
        estado["foto"] = None
        estado["apagar_foto"] = True
        estado["cfg"]["usar_foto"] = False
        montar_opcoes()

    def trocar_aba(aba):
        estado["aba"] = aba
        montar_abas()
        montar_opcoes()

    def sortear(e):
        novo = av.sortear()
        for k in ("usar_foto", "foto", "t"):
            novo[k] = estado["cfg"].get(k, av.PADRAO[k])
        estado["cfg"] = novo
        atualizar_previa("lobby")
        montar_opcoes()

    async def salvar(e):
        cfg = dict(estado["cfg"])
        if estado["foto"] is None and not estado["apagar_foto"] and not foto_atual:
            cfg["usar_foto"] = False
        app.page.pop_dialog()
        await salvar_meu(app, cfg, foto=estado["foto"], apagar_foto=estado["apagar_foto"])
        app.msg("Personagem salvo!" + (" A turma já vê." if app.ranking.logado else " Entre numa conta para a turma ver."))
        if ao_salvar:
            ao_salvar()
        app.montar()

    montar_opcoes()
    gestos = ft.Row(
        [
            comp.botao_texto("Acenar", lambda e: app.page.run_task(gesto, "aceno", 2.6), ft.Icons.WAVING_HAND_OUTLINED),
            comp.botao_texto("Pular", lambda e: app.page.run_task(gesto, "pulo", 2.4), ft.Icons.CELEBRATION_OUTLINED),
            comp.botao_texto("Sortear", sortear, ft.Icons.CASINO_OUTLINED),
        ],
        spacing=0,
        wrap=True,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    lado_previa = ft.Column(
        [ft.Container(previa, border_radius=14, clip_behavior=ft.ClipBehavior.ANTI_ALIAS), gestos],
        spacing=6,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        tight=True,
    )
    montar_abas()
    lado_opcoes = ft.Column([abas, opcoes], spacing=14, tight=True, expand=not estreito)
    corpo = (
        ft.Column([lado_previa, lado_opcoes], spacing=14, tight=True, scroll=ft.ScrollMode.AUTO)
        if estreito
        # a prévia fica no meio da altura das opções: em abas compridas não sobra um vão embaixo dela
        else ft.Row([lado_previa, lado_opcoes], spacing=24, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    )
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Row(
                [ft.Icon(ft.Icons.AUTO_FIX_HIGH, color=c["tinta"]), ft.Text("Seu personagem", font_family=FONTE_TITULO, size=22)],
                spacing=10,
            ),
            content=ft.Container(corpo, width=min(1000, largura_tela - 48)),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: app.page.pop_dialog()),
                ft.FilledButton("Salvar", icon=ft.Icons.CHECK, on_click=salvar),
            ],
            scrollable=True,
        )
    )
