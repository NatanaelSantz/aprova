"""Fotos, arquivos, GIFs e figurinhas nos grupos: escolher, enviar e mostrar."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import flet as ft

from .. import figurinhas, minhas_figurinhas as mf, ranking as rk
from . import comp
from .tema import FONTE_TITULO

ICONES_EXT = {
    "pdf": ft.Icons.PICTURE_AS_PDF_OUTLINED,
    "doc": ft.Icons.DESCRIPTION_OUTLINED, "docx": ft.Icons.DESCRIPTION_OUTLINED, "odt": ft.Icons.DESCRIPTION_OUTLINED,
    "rtf": ft.Icons.DESCRIPTION_OUTLINED, "txt": ft.Icons.ARTICLE_OUTLINED,
    "xls": ft.Icons.TABLE_CHART_OUTLINED, "xlsx": ft.Icons.TABLE_CHART_OUTLINED, "ods": ft.Icons.TABLE_CHART_OUTLINED, "csv": ft.Icons.TABLE_CHART_OUTLINED,
    "ppt": ft.Icons.SLIDESHOW_OUTLINED, "pptx": ft.Icons.SLIDESHOW_OUTLINED, "odp": ft.Icons.SLIDESHOW_OUTLINED,
    "mp3": ft.Icons.AUDIO_FILE_OUTLINED, "m4a": ft.Icons.AUDIO_FILE_OUTLINED, "ogg": ft.Icons.AUDIO_FILE_OUTLINED, "wav": ft.Icons.AUDIO_FILE_OUTLINED,
    "mp4": ft.Icons.VIDEO_FILE_OUTLINED, "zip": ft.Icons.FOLDER_ZIP_OUTLINED,
}


def _ext(nome: str) -> str:
    return Path(nome or "").suffix.lower().lstrip(".")


async def escolher_arquivos(app) -> list[Path]:
    """Seletor do computador com os tipos que dá para mandar no grupo."""
    picker = getattr(app, "_picker", None)
    if picker is None:
        picker = ft.FilePicker()
        app._picker = picker
    pasta = app.aj["pasta_downloads"] if Path(app.aj["pasta_downloads"] or "").exists() else None
    arquivos = await picker.pick_files(
        dialog_title="Escolha fotos ou arquivos para mandar ao grupo",
        initial_directory=pasta,
        file_type=ft.FilePickerFileType.CUSTOM,
        allowed_extensions=list(rk.TIPOS_ARQUIVO),
        allow_multiple=True,
        with_data=app.modo_web,
    )
    caminhos: list[Path] = []
    for f in arquivos or []:
        if f.path:
            caminhos.append(Path(f.path))
        elif f.bytes:
            destino = Path(tempfile.mkdtemp(prefix="aprova_anexo_")) / (f.name or "arquivo")
            destino.write_bytes(f.bytes)
            caminhos.append(destino)
    return caminhos[: rk.MAX_ANEXOS]


def colecao(app) -> mf.Colecao:
    """As figurinhas de quem está usando o app (cada conta tem as suas)."""
    return mf.Colecao(app.pasta_conta)


async def conteudo_rapido(app, codigo: str, tipo: str, valor) -> dict:
    """O que vai na mensagem quando alguém escolhe uma figurinha ou GIF (para forum_publicar/forum_responder)."""
    if tipo == "figurinha":
        return {"figurinha": valor}
    if tipo == "minha":
        achado = colecao(app).dados(valor)
        if achado is None:
            raise rk.ErroRanking("Essa figurinha não está mais na sua coleção.")
        item, dados = achado
        anexo = await app.em_segundo_plano(app.ranking.enviar_figurinha, codigo, dados, item)
        colecao(app).usada(valor)
        return {"anexos": [anexo]}
    return {"anexos": [valor]}


async def escolher_figurinhas(app) -> list[Path]:
    """Seletor para importar figurinhas: imagens soltas ou pacotes do WhatsApp (.wastickers / .zip)."""
    picker = getattr(app, "_picker", None)
    if picker is None:
        picker = ft.FilePicker()
        app._picker = picker
    arquivos = await picker.pick_files(
        dialog_title="Escolha figurinhas (.webp, .png, .gif) ou um pacote do WhatsApp (.wastickers, .zip)",
        file_type=ft.FilePickerFileType.CUSTOM,
        allowed_extensions=list(mf.TIPOS) + list(mf.PACOTES),
        allow_multiple=True,
        with_data=app.modo_web,
    )
    caminhos: list[Path] = []
    for f in arquivos or []:
        if f.path:
            caminhos.append(Path(f.path))
        elif f.bytes:
            destino = Path(tempfile.mkdtemp(prefix="aprova_fig_")) / (f.name or "figurinha.webp")
            destino.write_bytes(f.bytes)
            caminhos.append(destino)
    return caminhos


def _caminho_colado(texto: str) -> Path | None:
    from urllib.parse import unquote, urlparse
    from urllib.request import url2pathname

    texto = (texto or "").strip()
    if texto.startswith("file:"):
        texto = url2pathname(unquote(urlparse(texto).path))
    try:
        p = Path(texto)
        return p if p.is_file() else None
    except (OSError, ValueError):
        return None


async def colar_figurinhas(app) -> dict | None:
    """Pega do Ctrl+C: arquivos copiados no Explorador ou uma imagem copiada (WhatsApp Web: Copiar imagem)."""
    cb = ft.Clipboard()
    caminhos: list[Path] = []
    try:
        caminhos = [c for c in (_caminho_colado(t) for t in (await cb.get_files()) or []) if c]
    except Exception:  # noqa: BLE001 - plataforma sem arquivos na área de transferência
        caminhos = []
    if caminhos:
        return await app.em_segundo_plano(colecao(app).importar, caminhos)
    try:
        imagem = await cb.get_image()
    except Exception:  # noqa: BLE001
        imagem = None
    if not imagem:
        return None
    res = {"novas": 0, "repetidas": 0, "erros": []}
    try:
        _, nova = await app.em_segundo_plano(colecao(app).adicionar, imagem, "colada")
    except mf.ErroFigurinha as ex:
        res["erros"].append(f"imagem colada: {ex}")
    else:
        res["novas" if nova else "repetidas"] += 1
    return res


# ---------------------------------------------------------------- mostrar nas mensagens

class VisorAnexos:
    """Mostra fotos, GIFs, figurinhas e arquivos. Guarda as fotos já baixadas para não piscar ao redesenhar."""

    def __init__(self, app):
        self.app = app
        self._bytes: dict[str, bytes] = {}
        self._baixando: set[str] = set()

    @property
    def r(self) -> rk.Ranking:
        return self.app.ranking

    def figurinha(self, ident: str, tamanho: int = 150) -> ft.Control:
        c = self.app.c
        if figurinhas.caminho(ident) is None:
            return comp.apagado("(figurinha nova: atualize o Aprova para ver)", c, 12.5)
        return ft.Image(src=f"figurinhas/{ident}.png", width=tamanho, height=tamanho, fit=ft.BoxFit.CONTAIN, tooltip=figurinhas.LEGENDAS.get(ident, ""))

    def anexos(self, anexos: list[dict], compacto: bool = False) -> ft.Control | None:
        if not anexos:
            return None
        adesivos = [a for a in anexos if a.get("figurinha") and a.get("caminho")]
        visuais = [a for a in anexos if a.get("tipo") in ("imagem", "gif") and a not in adesivos]
        arquivos = [a for a in anexos if a.get("tipo") == "arquivo"]
        filhos: list[ft.Control] = []
        if adesivos:
            filhos.append(ft.Row([self._adesivo(a, compacto) for a in adesivos], wrap=True, spacing=8))
        if visuais:
            sozinho = len(visuais) == 1
            filhos.append(ft.Row([self._visual(a, sozinho, compacto) for a in visuais], wrap=True, spacing=8, run_spacing=8))
        if arquivos:
            filhos.append(ft.Column([self._arquivo(a) for a in arquivos], spacing=6))
        return ft.Column(filhos, spacing=8)

    def _tamanho(self, a: dict, sozinho: bool, compacto: bool) -> tuple[int, int]:
        if not sozinho:
            lado = 120 if compacto else 160
            return lado, lado
        maxl, maxa = (240, 200) if compacto else (380, 320)
        w, h = int(a.get("largura") or 0), int(a.get("altura") or 0)
        if not w or not h:
            return maxl, int(maxl * 0.66)
        f = min(maxl / w, maxa / h, 1.0)
        return max(60, int(w * f)), max(60, int(h * f))

    def _visual(self, a: dict, sozinho: bool, compacto: bool) -> ft.Control:
        c = self.app.c
        w, h = self._tamanho(a, sozinho, compacto)
        caixa = ft.Container(
            width=w,
            height=h,
            border_radius=12,
            bgcolor=c["sup2"],
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e, a=a: self.abrir_imagem(a),
            tooltip=a.get("nome") or "",
        )
        ajuste = ft.BoxFit.COVER if not sozinho else ft.BoxFit.CONTAIN
        if a.get("url"):  # GIF do GIPHY: o app baixa direto
            caixa.content = ft.Image(src=a["url"], width=w, height=h, fit=ajuste, gapless_playback=True)
            return caixa
        chave = a.get("caminho") or ""
        if chave in self._bytes:
            caixa.content = ft.Image(src=self._bytes[chave], width=w, height=h, fit=ajuste, gapless_playback=True)
        else:
            caixa.content = ft.ProgressRing(width=22, height=22, stroke_width=2.4, color=c["tinta"])
            if chave not in self._baixando:
                self._baixando.add(chave)
                self.app.page.run_task(self._carregar, a, caixa, w, h, ajuste)
        return caixa

    def _adesivo(self, a: dict, compacto: bool) -> ft.Control:
        """Figurinha de alguém (das "minhas figurinhas" dele): sem moldura, como no WhatsApp."""
        lado = 110 if compacto else 150
        caixa = ft.Container(width=lado, height=lado, alignment=ft.Alignment.CENTER, on_click=lambda e, a=a: self.abrir_adesivo(a), tooltip="Figurinha")
        chave = a.get("caminho") or ""
        if chave in self._bytes:
            caixa.content = ft.Image(src=self._bytes[chave], width=lado, height=lado, fit=ft.BoxFit.CONTAIN, gapless_playback=True)
        else:
            caixa.content = ft.ProgressRing(width=22, height=22, stroke_width=2.4, color=self.app.c["tinta"])
            if chave not in self._baixando:
                self._baixando.add(chave)
                self.app.page.run_task(self._carregar, a, caixa, lado, lado, ft.BoxFit.CONTAIN)
        return caixa

    def abrir_adesivo(self, a: dict):
        """Ver a figurinha grande e guardar nas suas."""
        app, c = self.app, self.app.c
        dados = self._bytes.get(a.get("caminho") or "")
        if dados is None:
            return
        import hashlib

        ja_tenho = any(i["id"] == hashlib.sha1(dados).hexdigest()[:16] for i in colecao(app).lista())
        guardar: ft.Control = (
            ft.Row([ft.Icon(ft.Icons.FAVORITE, color=c["tinta"], size=18), comp.apagado("Já está nas suas figurinhas", c, 13)], spacing=6, tight=True)
            if ja_tenho
            else ft.FilledButton("Guardar nas minhas figurinhas", icon=ft.Icons.FAVORITE_BORDER, on_click=lambda e: self.guardar(dados, fechar=True))
        )
        app.page.show_dialog(
            ft.AlertDialog(
                content=ft.Container(ft.Image(src=dados, width=240, height=240, fit=ft.BoxFit.CONTAIN), width=260, height=250, alignment=ft.Alignment.CENTER),
                actions=[ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog()), guardar],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def guardar(self, dados: bytes, fechar: bool = False):
        try:
            _, nova = colecao(self.app).adicionar(dados, "grupo")
        except mf.ErroFigurinha as ex:
            self.app.msg(f"Não deu para guardar: {ex}.")
            return
        if fechar:
            self.app.page.pop_dialog()
        self.app.msg("Guardada nas suas figurinhas (🙂 → Minhas)." if nova else "Você já tinha essa figurinha.")

    async def _carregar(self, a: dict, caixa: ft.Container, w: int, h: int, ajuste):
        chave = a.get("caminho") or ""
        try:
            dados = await self.app.em_segundo_plano(self.r.baixar_anexo, a)
        except rk.ErroRanking:
            caixa.content = ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, color=self.app.c["texto2"])
        else:
            self._bytes[chave] = dados
            caixa.content = ft.Image(src=dados, width=w, height=h, fit=ajuste, gapless_playback=True)
        finally:
            self._baixando.discard(chave)
        try:
            caixa.update()
        except Exception:  # noqa: BLE001 - saiu da tela
            pass

    def _arquivo(self, a: dict) -> ft.Control:
        c = self.app.c
        nome = a.get("nome") or "arquivo"
        detalhe = rk.tamanho_texto(int(a.get("tamanho") or 0)) if a.get("tamanho") else ""
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(ICONES_EXT.get(_ext(nome), ft.Icons.INSERT_DRIVE_FILE_OUTLINED), color=c["tinta"], size=26),
                    ft.Column(
                        [ft.Text(nome, size=14, weight=ft.FontWeight.W_600, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), comp.apagado(detalhe, c, 12)],
                        spacing=0,
                        expand=True,
                    ),
                    ft.IconButton(ft.Icons.OPEN_IN_NEW, tooltip="Abrir", icon_size=20, icon_color=c["texto2"], on_click=lambda e, a=a: self.app.page.run_task(self.abrir_arquivo, a)),
                    ft.IconButton(ft.Icons.DOWNLOAD, tooltip="Salvar na pasta de downloads", icon_size=20, icon_color=c["texto2"], on_click=lambda e, a=a: self.app.page.run_task(self.salvar_arquivo, a)),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=c["sup2"],
            border_radius=12,
            padding=ft.Padding.only(left=12, right=4, top=6, bottom=6),
            width=420,
        )

    # ---------------------------------------------------------------- ações

    async def _baixar(self, a: dict) -> bytes | None:
        try:
            return await self.app.em_segundo_plano(self.r.baixar_anexo, a)
        except rk.ErroRanking as ex:
            self.app.msg(str(ex))
            return None

    async def abrir_arquivo(self, a: dict):
        self.app.msg(f"Abrindo {a.get('nome') or 'o arquivo'}…")
        dados = await self._baixar(a)
        if dados is None:
            return
        pasta = Path(tempfile.gettempdir()) / "aprova-anexos"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / _nome_local(a)
        destino.write_bytes(dados)
        _abrir_no_sistema(self.app, destino)

    async def salvar_arquivo(self, a: dict):
        dados = await self._baixar(a)
        if dados is None:
            return
        pasta = Path(self.app.aj["pasta_downloads"] or Path.home() / "Downloads")
        if not pasta.exists():
            pasta = Path.home()
        destino = _livre(pasta / _nome_local(a))
        destino.write_bytes(dados)
        self.app.msg(f"Salvo em {destino}")

    def abrir_imagem(self, a: dict):
        app, c = self.app, self.app.c
        largura = min(900, (app.page.width or 900) - 80)
        altura = min(640, (app.page.height or 700) - 200)
        if a.get("url"):
            imagem: ft.Control = ft.Image(src=a["url"], fit=ft.BoxFit.CONTAIN, width=largura, height=altura)
        elif (a.get("caminho") or "") in self._bytes:
            imagem = ft.InteractiveViewer(ft.Image(src=self._bytes[a["caminho"]], fit=ft.BoxFit.CONTAIN, width=largura, height=altura), min_scale=0.8, max_scale=5)
        else:
            imagem = comp.carregando("Abrindo…", c)
        acoes = [ft.TextButton("Fechar", on_click=lambda e: app.page.pop_dialog())]
        if a.get("caminho"):
            acoes.insert(0, ft.TextButton("Salvar", icon=ft.Icons.DOWNLOAD, on_click=lambda e: app.page.run_task(self.salvar_arquivo, a)))
            if a["caminho"] in self._bytes:
                acoes.insert(0, ft.TextButton("Virar figurinha", icon=ft.Icons.EMOJI_EMOTIONS_OUTLINED, on_click=lambda e: self.guardar(self._bytes[a["caminho"]], fechar=True)))
        app.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(a.get("nome") or "Imagem", size=16, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                content=ft.Container(imagem, width=largura, height=altura, alignment=ft.Alignment.CENTER),
                actions=acoes,
            )
        )


def _nome_local(a: dict) -> str:
    nome = re.sub(r'[<>:"/\\|?*]+', " ", a.get("nome") or "arquivo").strip() or "arquivo"
    if not Path(nome).suffix and a.get("caminho"):
        nome += Path(a["caminho"]).suffix
    return nome


def _livre(destino: Path) -> Path:
    i, saida = 2, destino
    while saida.exists():
        saida = destino.with_name(f"{destino.stem} ({i}){destino.suffix}")
        i += 1
    return saida


def _abrir_no_sistema(app, caminho: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(caminho))  # noqa: S606
            return
    except OSError:
        pass
    app.page.run_task(app.abrir_url, caminho.as_uri())


# ---------------------------------------------------------------- figurinhas e GIFs

COMO_TRAZER = [
    ("No computador (WhatsApp Web)", "Clique com o botão direito na figurinha → Copiar imagem. Aqui, aperte Ctrl+V ou o botão Colar."),
    ("Do celular Android", "As figurinhas ficam na pasta WhatsApp › Media › WhatsApp Stickers (no Android 11 ou mais novo, dentro de Android › media › com.whatsapp). Passe os arquivos .webp para o PC pelo cabo e clique em Importar."),
    ("Do iPhone", "Mande as figurinhas para uma conversa sua, use Exportar conversa → Anexar mídia e traga o .zip para o PC. O Importar pega as figurinhas de dentro."),
    ("Pacotes", "Arquivos .wastickers (de apps de figurinhas) também entram pelo Importar."),
]


def dialogo_figurinhas_gifs(app, ao_escolher) -> None:
    """Escolher uma figurinha (do Aprova ou das suas), um GIF ou uma figurinha animada do GIPHY.

    ao_escolher(tipo, valor): tipo "figurinha" (valor = id do Aprova), "minha" (valor = id da coleção)
    ou "gif" (valor = anexo)."""
    c = app.c
    aba_salva = app.aj.get("ultima_aba_figurinhas") or "aprova"
    estado = {"aba": aba_salva if aba_salva in ("aprova", "minhas", "gifs", "animadas") else "aprova", "apagando": False, "ajuda": False}
    grade = ft.GridView(max_extent=118, spacing=8, run_spacing=8, height=330, expand=False)
    busca = ft.TextField(hint_text="Buscar no GIPHY (ex.: estudando, cansado, comemorando)", dense=True, border_radius=20, prefix_icon=ft.Icons.SEARCH, expand=True)
    linha_busca = ft.Row([busca], visible=False)
    linha_minhas = ft.Row(visible=False, wrap=True, spacing=6, run_spacing=6)
    aviso = ft.Container()
    rodape = comp.apagado("GIFs: Powered by GIPHY", c, 11.5)
    corpo = ft.Column(spacing=10, tight=True)

    def fechar_colar(e=None):
        app._ao_colar = None

    def escolher(tipo, valor):
        fechar_colar()
        app.page.pop_dialog()
        ao_escolher(tipo, valor)

    def mostrar_aprova():
        grade.controls = [
            ft.Container(
                ft.Image(src=f"figurinhas/{ident}.png", fit=ft.BoxFit.CONTAIN),
                tooltip=legenda,
                border_radius=12,
                padding=6,
                ink=True,
                on_click=lambda e, i=ident: escolher("figurinha", i),
            )
            for ident, legenda in figurinhas.FIGURINHAS
            if figurinhas.caminho(ident)
        ]

    # ------------------------------------------------ minhas figurinhas

    def ajuda() -> ft.Control:
        return ft.Container(
            ft.Column(
                [comp.texto("Como trazer suas figurinhas do WhatsApp", c, 14, peso=ft.FontWeight.W_600)]
                + [
                    ft.Column([ft.Text(titulo, size=13, weight=ft.FontWeight.W_600, color=c["texto"]), comp.apagado(texto, c, 12.5)], spacing=1)
                    for titulo, texto in COMO_TRAZER
                ],
                spacing=8,
            ),
            bgcolor=c["sup2"],
            border_radius=12,
            padding=12,
        )

    def mostrar_minhas():
        itens = colecao(app).lista()
        app._ao_colar = lambda: app.page.run_task(colar)
        linha_minhas.controls = [
            comp.botao("Importar", importar, ft.Icons.FILE_UPLOAD_OUTLINED),
            ft.OutlinedButton("Colar", icon=ft.Icons.CONTENT_PASTE, on_click=lambda e: app.page.run_task(colar), tooltip="Cole uma figurinha copiada (Ctrl+V)"),
            ft.TextButton("Como trazer do WhatsApp", icon=ft.Icons.HELP_OUTLINE, on_click=alternar_ajuda),
        ]
        if itens:
            linha_minhas.controls.append(
                ft.TextButton(
                    "Pronto" if estado["apagando"] else "Apagar",
                    icon=ft.Icons.CHECK if estado["apagando"] else ft.Icons.DELETE_OUTLINE,
                    on_click=alternar_apagar,
                    style=ft.ButtonStyle(color=c["erro"]) if not estado["apagando"] else None,
                )
            )
        if not itens:
            grade.controls = []
            grade.height = 0
            aviso.content = ft.Column(
                [comp.apagado("Você ainda não tem figurinhas suas. Importe as do WhatsApp ou guarde as que aparecerem no grupo (clique nelas).", c, 13.5), ajuda()],
                spacing=10,
            )
            return
        grade.height = 210 if estado["ajuda"] else 330
        if estado["ajuda"]:
            aviso.content = ajuda()

        def ladrilho(item):
            imagem = ft.Image(src=str(colecao(app).caminho(item)), fit=ft.BoxFit.CONTAIN, gapless_playback=True)
            if estado["apagando"]:
                conteudo = ft.Stack(
                    [
                        ft.Container(imagem, opacity=0.55, padding=6),
                        ft.Container(ft.Icon(ft.Icons.CLOSE, color="#FFFFFF", size=16), bgcolor=c["erro"], border_radius=12, width=24, height=24, alignment=ft.Alignment.CENTER, right=2, top=2),
                    ]
                )
                return ft.Container(conteudo, border_radius=12, ink=True, tooltip="Apagar", on_click=lambda e, i=item["id"]: apagar(i))
            return ft.Container(imagem, border_radius=12, padding=6, ink=True, on_click=lambda e, i=item["id"]: escolher("minha", i))

        grade.controls = [ladrilho(i) for i in itens]

    def depois_de_importar(res: dict | None, vazio: str):
        estado["apagando"] = False
        mostrar_minhas()
        if res is None:
            aviso.content = comp.aviso(vazio, c, "info")
        elif res["novas"] or res["repetidas"]:
            aviso.content = comp.aviso(mf.resumo(res), c, "ok")
        else:
            aviso.content = comp.aviso(mf.resumo(res), c, "erro")
        app.page.update()

    async def importar(e=None):
        caminhos = await escolher_figurinhas(app)
        if not caminhos:
            return
        aviso.content = comp.carregando("Importando…", c)
        app.page.update()
        res = await app.em_segundo_plano(colecao(app).importar, caminhos)
        depois_de_importar(res, "")

    async def colar():
        if estado["aba"] != "minhas":
            return
        res = await colar_figurinhas(app)
        depois_de_importar(res, "Nada para colar. No WhatsApp Web, clique com o botão direito na figurinha → Copiar imagem, e volte aqui.")

    def alternar_ajuda(e):
        estado["ajuda"] = not estado["ajuda"]
        aviso.content = ajuda() if estado["ajuda"] else None
        mostrar_minhas()
        app.page.update()

    def alternar_apagar(e):
        estado["apagando"] = not estado["apagando"]
        mostrar_minhas()
        app.page.update()

    def apagar(ident):
        colecao(app).apagar(ident)
        if not colecao(app).lista():
            estado["apagando"] = False
        mostrar_minhas()
        app.page.update()

    # ------------------------------------------------ GIPHY

    async def buscar(e=None):
        animadas = estado["aba"] == "animadas"
        grade.controls = [ft.Container(comp.carregando("Buscando…", c), padding=10)]
        aviso.content = None
        app.page.update()
        try:
            achados = await app.em_segundo_plano(app.ranking.buscar_gifs, busca.value or "", animadas)
        except rk.ErroRanking as ex:
            grade.controls = []
            aviso.content = comp.aviso(str(ex), c, "info")
            app.page.update()
            return
        if estado["aba"] not in ("gifs", "animadas"):
            return  # trocou de aba enquanto buscava
        grade.controls = [
            ft.Container(
                ft.Image(src=g["previa"], fit=ft.BoxFit.COVER if not animadas else ft.BoxFit.CONTAIN, gapless_playback=True),
                tooltip=g["titulo"] or "GIF",
                border_radius=10,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                bgcolor=c["sup2"] if not animadas else None,
                ink=True,
                on_click=lambda e, g=g: escolher("gif", g["anexo"]),
            )
            for g in achados
        ] or [comp.apagado("Nada encontrado. Tente outra palavra.", c, 13.5)]
        app.page.update()

    busca.on_submit = buscar

    def trocar(e):
        estado["aba"] = e.control.selected[0] if e.control.selected else "aprova"
        estado["apagando"] = False
        app.aj.set("ultima_aba_figurinhas", estado["aba"])
        desenhar()
        app.page.update()

    def desenhar():
        aviso.content = None
        grade.height = 330
        linha_busca.visible = estado["aba"] in ("gifs", "animadas")
        linha_minhas.visible = estado["aba"] == "minhas"
        rodape.visible = estado["aba"] in ("gifs", "animadas")
        if estado["aba"] != "minhas":
            app._ao_colar = None
        if estado["aba"] == "aprova":
            mostrar_aprova()
        elif estado["aba"] == "minhas":
            mostrar_minhas()
        else:
            app.page.run_task(buscar)

    abas = ft.SegmentedButton(
        selected=[estado["aba"]],
        segments=[
            ft.Segment(value="aprova", label=ft.Text("Do Aprova"), icon=ft.Icon(ft.Icons.EMOJI_EMOTIONS_OUTLINED)),
            ft.Segment(value="minhas", label=ft.Text("Minhas"), icon=ft.Icon(ft.Icons.FAVORITE_BORDER)),
            ft.Segment(value="gifs", label=ft.Text("GIFs"), icon=ft.Icon(ft.Icons.GIF_BOX_OUTLINED)),
            ft.Segment(value="animadas", label=ft.Text("Animadas"), icon=ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED)),
        ],
        show_selected_icon=False,
        on_change=trocar,
    )
    desenhar()
    corpo.controls = [ft.Row([abas], scroll=ft.ScrollMode.AUTO), linha_busca, linha_minhas, aviso, grade, rodape]
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Figurinhas e GIFs", font_family=FONTE_TITULO, size=21),
            content=ft.Container(corpo, width=min(580, (app.page.width or 600) - 48)),
            actions=[ft.TextButton("Fechar", on_click=lambda e: (fechar_colar(), app.page.pop_dialog()))],
            on_dismiss=fechar_colar,
            scrollable=True,
        )
    )


def chip_pendente(app, a: dict, ao_remover) -> ft.Control:
    """Anexo já enviado, esperando a mensagem ser publicada."""
    c = app.c
    if a.get("tipo") in ("imagem", "gif") and a.get("caminho"):
        dados = rk._ler_cache(a["caminho"])
        icone = ft.Image(src=dados, width=36, height=36, fit=ft.BoxFit.COVER, border_radius=6) if dados else ft.Icon(ft.Icons.IMAGE_OUTLINED, color=c["tinta"])
    else:
        icone = ft.Icon(ICONES_EXT.get(_ext(a.get("nome") or ""), ft.Icons.INSERT_DRIVE_FILE_OUTLINED), color=c["tinta"], size=22)
    return ft.Container(
        ft.Row(
            [
                icone,
                ft.Text(a.get("nome") or "arquivo", size=13, color=c["texto"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, width=150),
                ft.IconButton(ft.Icons.CLOSE, icon_size=16, tooltip="Tirar", on_click=lambda e: ao_remover(a)),
            ],
            spacing=6,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=c["sup2"],
        border_radius=10,
        padding=ft.Padding.only(left=6, right=0, top=2, bottom=2),
    )
