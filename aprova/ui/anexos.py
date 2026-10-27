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

    def lembrar(self, anexo: dict) -> None:
        """Usa os bytes que já estão no computador (ex.: a figurinha que você acabou de mandar), sem baixar de novo."""
        chave = anexo.get("caminho") or ""
        if chave and chave not in self._bytes:
            dados = rk._ler_cache(chave)
            if dados:
                self._bytes[chave] = dados

    def anexos(self, anexos: list[dict], compacto: bool = False, lado_adesivo: int | None = None) -> ft.Control | None:
        if not anexos:
            return None
        adesivos = [a for a in anexos if e_adesivo(a)]
        visuais = [a for a in anexos if a.get("tipo") in ("imagem", "gif") and a not in adesivos]
        arquivos = [a for a in anexos if a.get("tipo") == "arquivo"]
        filhos: list[ft.Control] = []
        if adesivos:
            filhos.append(ft.Row([self._adesivo(a, compacto, lado_adesivo) for a in adesivos], wrap=True, spacing=8))
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
        if _gif_giphy(a):  # GIF do GIPHY: o app baixa direto (outro endereço qualquer nunca é carregado)
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

    def _adesivo(self, a: dict, compacto: bool, lado: int | None = None) -> ft.Control:
        """Figurinha de alguém (das "minhas figurinhas" dele ou animada do GIPHY): sem moldura, como no WhatsApp."""
        lado = lado or (110 if compacto else 150)
        if _gif_giphy(a):
            return ft.Container(ft.Image(src=a["url"], width=lado, height=lado, fit=ft.BoxFit.CONTAIN, gapless_playback=True),
                                width=lado, height=lado, alignment=ft.Alignment.CENTER, tooltip="Figurinha animada")
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
        nome, seguro = rk.nome_local_seguro(a)
        if not seguro:
            # .exe, .bat, atalho...: o app não abre arquivo que pode rodar programa no seu computador
            self.app.msg("Esse tipo de arquivo não abre pelo Aprova, por segurança. Use Salvar e confira antes de abrir.")
            return
        self.app.msg(f"Abrindo {nome}…")
        dados = await self._baixar(a)
        if dados is None:
            return
        pasta = Path(tempfile.mkdtemp(prefix="aprova-anexo-"))
        destino = pasta / nome
        destino.write_bytes(dados)
        marcar_da_internet(destino)
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
        marcar_da_internet(destino)
        self.app.msg(f"Salvo em {destino}")

    def abrir_imagem(self, a: dict):
        app, c = self.app, self.app.c
        largura = min(900, (app.page.width or 900) - 80)
        altura = min(640, (app.page.height or 700) - 200)
        if _gif_giphy(a):
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


def e_adesivo(a: dict) -> bool:
    """Anexo que é figurinha (das suas ou animada do GIPHY): aparece sem moldura."""
    return bool(a.get("figurinha")) and (bool(a.get("caminho")) or _gif_giphy(a))


def so_figurinha(m: dict) -> bool:
    """Mensagem (ou resposta) que é só uma figurinha, sem texto: aparece compacta, como numa conversa."""
    if (m.get("texto") or "").strip() or (m.get("titulo") or "").strip() or m.get("plano"):
        return False
    anexos = m.get("anexos") or []
    if m.get("figurinha"):
        return all(e_adesivo(a) for a in anexos)
    return bool(anexos) and all(e_adesivo(a) for a in anexos)


def previa_envio(app, tipo: str, valor, lado: int) -> ft.Control:
    """O desenho da figurinha (ou GIF) que está indo, para aparecer na hora na conversa."""
    if tipo == "figurinha":
        return ft.Image(src=f"figurinhas/{valor}.png", width=lado, height=lado, fit=ft.BoxFit.CONTAIN)
    if tipo == "minha":
        item = next((i for i in colecao(app).lista() if i["id"] == valor), None)
        if item:
            return ft.Image(src=str(colecao(app).caminho(item)), width=lado, height=lado, fit=ft.BoxFit.CONTAIN, gapless_playback=True)
    elif isinstance(valor, dict) and _gif_giphy(valor):
        return ft.Image(src=valor["url"], width=lado, height=lado, fit=ft.BoxFit.CONTAIN, gapless_playback=True, border_radius=0 if valor.get("figurinha") else 10)
    return ft.Icon(ft.Icons.EMOJI_EMOTIONS_OUTLINED, size=lado // 2, color=app.c["texto2"])


RECENTES_MAX = 15


def lembrar_recente(app, tipo: str, valor) -> None:
    """Guarda a figurinha usada na aba "Recentes" (a última primeiro, sem repetir)."""
    chave = valor.get("url") if isinstance(valor, dict) else valor
    lista = [r for r in (app.aj.get("figurinhas_recentes") or []) if isinstance(r, dict) and r.get("chave") != chave]
    lista.insert(0, {"tipo": tipo, "valor": valor, "chave": chave})
    app.aj.set("figurinhas_recentes", lista[:RECENTES_MAX])


def recentes(app) -> list[dict]:
    """As recentes que ainda existem (figurinha do Aprova que este app conhece, sua que não foi apagada)."""
    minhas = {i["id"] for i in colecao(app).lista()}
    saida = []
    for r in app.aj.get("figurinhas_recentes") or []:
        if not isinstance(r, dict):
            continue
        tipo, valor = r.get("tipo"), r.get("valor")
        if (tipo == "figurinha" and figurinhas.caminho(str(valor)) is not None) or (tipo == "minha" and valor in minhas) or (
            tipo == "gif" and isinstance(valor, dict) and _gif_giphy(valor)
        ):
            saida.append(r)
    return saida


def _nome_local(a: dict) -> str:
    return rk.nome_local_seguro(a)[0]


def _gif_giphy(a: dict) -> bool:
    return a.get("tipo") == "gif" and bool(rk.GIPHY.match(str(a.get("url") or "")))


def marcar_da_internet(caminho: Path) -> None:
    """No Windows, marca o arquivo como baixado da internet (como o navegador faz).

    Assim o Word/Excel abrem no Modo de Exibição Protegido e o Windows avisa antes de rodar algo."""
    if sys.platform != "win32":
        return
    try:
        with open(str(caminho) + ":Zone.Identifier", "wb") as f:
            f.write(b"[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=about:internet\r\n")
    except OSError:
        pass


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


ABAS_FIGURINHAS = [
    ("recentes", "Recentes", ft.Icons.HISTORY),
    ("aprova", "Do Aprova", ft.Icons.EMOJI_EMOTIONS_OUTLINED),
    ("minhas", "Minhas", ft.Icons.FAVORITE_BORDER),
    ("gifs", "GIFs", ft.Icons.GIF_BOX_OUTLINED),
    ("animadas", "Animadas", ft.Icons.AUTO_AWESOME_OUTLINED),
]
ALTURA_GRADE = 330


def colunas_grade(largura: float) -> int:
    """Quantas figurinhas por linha cabem na janela (3 no celular, 5 no computador)."""
    return max(3, min(6, int((largura + 8) // 104)))


def altura_grade(n: int, largura: float, maximo: int = ALTURA_GRADE) -> int:
    """Altura da grade para n figurinhas: só o necessário, até o máximo (depois rola)."""
    if n <= 0:
        return 0
    cols = colunas_grade(largura)
    lado = (largura - 8 * (cols - 1)) / cols
    linhas = -(-n // cols)
    return int(min(maximo, linhas * lado + 8 * (linhas - 1)))


def dialogo_figurinhas_gifs(app, ao_escolher) -> None:
    """Escolher uma figurinha (recentes, do Aprova ou das suas), um GIF ou uma figurinha animada do GIPHY.

    ao_escolher(tipo, valor): tipo "figurinha" (valor = id do Aprova), "minha" (valor = id da coleção)
    ou "gif" (valor = anexo). Um toque já manda, como no WhatsApp."""
    c = app.c
    largura = min(580, (app.page.width or 600) - 48) - 2
    tem_recentes = bool(recentes(app))
    aba_salva = app.aj.get("ultima_aba_figurinhas") or ("recentes" if tem_recentes else "aprova")
    validas = {k for k, _, _ in ABAS_FIGURINHAS}
    estado = {"aba": aba_salva if aba_salva in validas else "aprova", "apagando": False, "ajuda": False}
    if estado["aba"] == "recentes" and not tem_recentes:
        estado["aba"] = "aprova"
    cols = colunas_grade(largura)
    grade = ft.GridView(runs_count=cols, child_aspect_ratio=1.0, spacing=8, run_spacing=8, height=ALTURA_GRADE, expand=False)
    busca = ft.TextField(hint_text="Buscar no GIPHY (ex.: estudando, cansado, comemorando)", dense=True, border_radius=20, prefix_icon=ft.Icons.SEARCH, expand=True)
    linha_busca = ft.Row([busca], visible=False)
    linha_minhas = ft.Row(visible=False, wrap=True, spacing=6, run_spacing=6)
    abas = ft.Row(wrap=True, spacing=6, run_spacing=6)  # quebram linha: todas à vista no celular
    aviso = ft.Container()
    dica = comp.apagado("Toque numa figurinha para mandar.", c, 12)
    rodape = comp.apagado("GIFs: Powered by GIPHY", c, 11.5)
    corpo = ft.Column(spacing=10, tight=True)

    def fechar_colar(e=None):
        app._ao_colar = None

    def escolher(tipo, valor):
        fechar_colar()
        lembrar_recente(app, tipo, valor)
        app.page.pop_dialog()
        ao_escolher(tipo, valor)

    def ladrilho(conteudo: ft.Control, ao_clicar, dica_: str = "", fundo: str | None = None, padding: int = 6) -> ft.Container:
        """Uma figurinha na grade: cresce um pouco e ganha fundo quando o mouse passa."""

        def passar(e):
            dentro = e.data in (True, "true")
            e.control.scale = 1.06 if dentro else 1.0
            e.control.bgcolor = c["sup2"] if dentro or fundo else None
            e.control.update()

        return ft.Container(
            conteudo,
            tooltip=dica_ or None,
            bgcolor=fundo,
            border_radius=12,
            padding=padding,
            ink=True,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            alignment=ft.Alignment.CENTER,
            scale=1.0,
            animate_scale=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            on_hover=passar,
            on_click=ao_clicar,
        )

    def mostrar(controles: list[ft.Control], maximo: int = ALTURA_GRADE):
        grade.controls = controles
        grade.height = altura_grade(len(controles), largura, maximo)
        dica.visible = bool(controles) and not estado["apagando"]

    def mostrar_aprova():
        mostrar([
            ladrilho(ft.Image(src=f"figurinhas/{ident}.png", fit=ft.BoxFit.CONTAIN), lambda e, i=ident: escolher("figurinha", i), legenda)
            for ident, legenda in figurinhas.FIGURINHAS
            if figurinhas.caminho(ident)
        ])

    def mostrar_recentes():
        itens = []
        for r in recentes(app):
            tipo, valor = r["tipo"], r["valor"]
            if tipo == "gif":
                previa = ft.Image(src=valor["url"], fit=ft.BoxFit.CONTAIN if valor.get("figurinha") else ft.BoxFit.COVER, gapless_playback=True)
                itens.append(ladrilho(previa, lambda e, v=valor: escolher("gif", v), "Figurinha animada" if valor.get("figurinha") else "GIF",
                                      None if valor.get("figurinha") else c["sup2"], 6 if valor.get("figurinha") else 0))
            else:
                itens.append(ladrilho(previa_envio(app, tipo, valor, 96), lambda e, t=tipo, v=valor: escolher(t, v), figurinhas.LEGENDAS.get(str(valor), "")))
        mostrar(itens)

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
            mostrar([])
            aviso.content = ft.Column(
                [comp.apagado("Você ainda não tem figurinhas suas. Importe as do WhatsApp ou guarde as que aparecerem no grupo (clique nelas).", c, 13.5), ajuda()],
                spacing=10,
            )
            return
        if estado["ajuda"]:
            aviso.content = ajuda()

        def item_minha(item):
            imagem = ft.Image(src=str(colecao(app).caminho(item)), fit=ft.BoxFit.CONTAIN, gapless_playback=True)
            if estado["apagando"]:
                conteudo = ft.Stack(
                    [
                        ft.Container(imagem, opacity=0.55, padding=6, alignment=ft.Alignment.CENTER),
                        ft.Container(ft.Icon(ft.Icons.CLOSE, color="#FFFFFF", size=16), bgcolor=c["erro"], border_radius=12, width=24, height=24, alignment=ft.Alignment.CENTER, right=2, top=2),
                    ]
                )
                return ft.Container(conteudo, border_radius=12, ink=True, tooltip="Apagar", on_click=lambda e, i=item["id"]: apagar(i))
            return ladrilho(imagem, lambda e, i=item["id"]: escolher("minha", i))

        mostrar([item_minha(i) for i in itens], 210 if estado["ajuda"] else ALTURA_GRADE)

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
        grade.height = 60
        aviso.content = None
        app.page.update()
        try:
            achados = await app.em_segundo_plano(app.ranking.buscar_gifs, busca.value or "", animadas)
        except rk.ErroRanking as ex:
            mostrar([])
            aviso.content = comp.aviso(str(ex), c, "info")
            app.page.update()
            return
        if estado["aba"] not in ("gifs", "animadas"):
            return  # trocou de aba enquanto buscava
        if not achados:
            mostrar([])
            aviso.content = comp.apagado("Nada encontrado. Tente outra palavra.", c, 13.5)
        else:
            mostrar([
                ladrilho(
                    ft.Image(src=g["previa"], fit=ft.BoxFit.CONTAIN if animadas else ft.BoxFit.COVER, gapless_playback=True),
                    lambda e, g=g: escolher("gif", g["anexo"]),
                    g["titulo"] or "GIF",
                    None if animadas else c["sup2"],
                    6 if animadas else 0,
                )
                for g in achados
            ])
        app.page.update()

    busca.on_submit = buscar

    def montar_abas():
        visiveis = [a for a in ABAS_FIGURINHAS if a[0] != "recentes" or recentes(app)]
        abas.controls = [
            ft.Container(
                ft.Row(
                    [ft.Icon(icone, size=17, color=c["tinta"] if k == estado["aba"] else c["texto2"]),
                     ft.Text(rotulo, size=13.5, weight=ft.FontWeight.W_700 if k == estado["aba"] else ft.FontWeight.W_500,
                             color=c["tinta"] if k == estado["aba"] else c["texto2"])],
                    spacing=6,
                    tight=True,
                ),
                bgcolor=c["tinta_suave"] if k == estado["aba"] else None,
                border=ft.Border.all(1.4, c["tinta"] if k == estado["aba"] else c["borda"]),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=11, vertical=7),
                on_click=lambda e, k=k: trocar(k),
                ink=True,
            )
            for k, rotulo, icone in visiveis
        ]

    def trocar(aba: str):
        estado["aba"] = aba
        estado["apagando"] = False
        app.aj.set("ultima_aba_figurinhas", aba)
        desenhar()
        app.page.update()

    def desenhar():
        aviso.content = None
        montar_abas()
        linha_busca.visible = estado["aba"] in ("gifs", "animadas")
        linha_minhas.visible = estado["aba"] == "minhas"
        rodape.visible = estado["aba"] in ("gifs", "animadas")
        if estado["aba"] != "minhas":
            app._ao_colar = None
        if estado["aba"] == "recentes":
            mostrar_recentes()
        elif estado["aba"] == "aprova":
            mostrar_aprova()
        elif estado["aba"] == "minhas":
            mostrar_minhas()
        else:
            app.page.run_task(buscar)

    desenhar()
    corpo.controls = [abas, linha_busca, linha_minhas, aviso, grade, ft.Row([dica, ft.Container(expand=True), rodape])]
    app.page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Figurinhas e GIFs", font_family=FONTE_TITULO, size=21),
            content=ft.Container(corpo, width=largura),
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
