"""Minhas figurinhas: as que cada pessoa traz do WhatsApp, de arquivos ou salva do grupo.

Ficam no computador, na pasta da conta (<pasta da conta>/figurinhas), com um indice.json.
Na hora de mandar, a figurinha sobe para o grupo como um anexo de imagem marcado com
"figurinha": true (quem recebe vê sem moldura e pode guardar nas dele).

Como trazer do WhatsApp:
- Android: a pasta WhatsApp/Media/WhatsApp Stickers (no Android 11 ou mais novo, em
  Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Stickers) tem as figurinhas em .webp;
- iPhone: "Exportar conversa" com mídia gera um .zip; o Aprova pega as .webp de dentro;
- pacotes .wastickers (de apps de figurinhas) também são .zip com .webp;
- WhatsApp Web/no PC: botão direito na figurinha → Copiar imagem, e "Colar" no Aprova.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

LIMITE = 400  # figurinhas por conta
LADO = 512  # tamanho das figurinhas do WhatsApp
MAX_ANIMADA = 2 * 1024 * 1024
MAX_ENTRADA = 15 * 1024 * 1024  # arquivo que alguém tenta importar
MAX_ZIP = 300  # arquivos lidos de um pacote
TIPOS = ("webp", "png", "gif", "jpg", "jpeg")
PACOTES = ("zip", "wastickers")


class ErroFigurinha(Exception):
    pass


def caminho_seguro(pasta: Path, arquivo) -> Path | None:
    """Aceita só um nome de imagem dentro da coleção, inclusive em índices restaurados.

    Barras dos dois sistemas são recusadas também ao abrir uma cópia feita em outro sistema.
    A resolução real impede que um link de arquivo ou de pasta leve para fora da coleção.
    """
    if not isinstance(arquivo, str) or not arquivo or any(c in arquivo for c in ("/", "\\", ":", "\x00")):
        return None
    if Path(arquivo).suffix.lower().lstrip(".") not in TIPOS:
        return None
    pasta = Path(pasta)
    try:
        raiz = pasta.resolve()
        if raiz != pasta.parent.resolve() / pasta.name:
            return None  # a própria pasta da coleção é um link para outro lugar
        caminho = pasta / arquivo
        if caminho.resolve().parent != raiz:
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return caminho


def _ler_imagem(dados: bytes):
    from PIL import Image

    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
    except Exception as e:  # noqa: BLE001 - qualquer arquivo quebrado
        raise ErroFigurinha("não parece ser uma imagem") from e
    return im


def preparar(dados: bytes) -> tuple[bytes, str, int, int, bool]:
    """Deixa a imagem no jeito de figurinha. Devolve (dados, ext, largura, altura, animada).

    Animada (WebP ou GIF) fica como veio; parada vira WebP de até 512 px com fundo transparente."""
    if not dados:
        raise ErroFigurinha("arquivo vazio")
    if len(dados) > MAX_ENTRADA:
        raise ErroFigurinha("arquivo grande demais")
    im = _ler_imagem(dados)
    formato = (im.format or "").upper()
    largura, altura = im.size
    if largura < 16 or altura < 16:
        raise ErroFigurinha("imagem pequena demais")
    animada = bool(getattr(im, "is_animated", False)) and getattr(im, "n_frames", 1) > 1
    if animada:
        if formato not in ("WEBP", "GIF"):
            raise ErroFigurinha("formato animado não suportado")
        if len(dados) > MAX_ANIMADA:
            raise ErroFigurinha("figurinha animada grande demais (até 2 MB)")
        return dados, formato.lower(), largura, altura, True
    if formato == "WEBP" and max(largura, altura) <= LADO and len(dados) <= 300_000:
        return dados, "webp", largura, altura, False
    im = im.convert("RGBA")
    im.thumbnail((LADO, LADO))
    saida = io.BytesIO()
    im.save(saida, "WEBP", quality=88, method=4)
    return saida.getvalue(), "webp", im.size[0], im.size[1], False


class Colecao:
    """As figurinhas de uma conta."""

    def __init__(self, base: Path):
        self.pasta = Path(base) / "figurinhas"
        self._indice = self.pasta / "indice.json"

    # ---------------------------------------------------------------- leitura

    def lista(self) -> list[dict]:
        """Mais recentes primeiro (as usadas por último sobem)."""
        try:
            itens = json.loads(self._indice.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        itens = [i for i in itens if isinstance(i, dict)
                 and (cam := caminho_seguro(self.pasta, i.get("arquivo"))) is not None and cam.is_file()]
        return sorted(itens, key=lambda i: -float(i.get("usada") or i.get("criada") or 0))

    def caminho(self, item: dict) -> Path:
        caminho = caminho_seguro(self.pasta, item.get("arquivo"))
        if caminho is None:
            raise ErroFigurinha("caminho de figurinha inválido")
        return caminho

    def dados(self, ident: str) -> tuple[dict, bytes] | None:
        for item in self.lista():
            if item["id"] == ident:
                try:
                    return item, self.caminho(item).read_bytes()
                except OSError:
                    return None
        return None

    def __len__(self) -> int:
        return len(self.lista())

    # ---------------------------------------------------------------- escrita

    def _salvar_indice(self, itens: list[dict]) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = self._indice.with_suffix(".tmp")
        tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._indice)

    def adicionar(self, dados: bytes, origem: str = "") -> tuple[dict, bool]:
        """Guarda uma figurinha. Devolve (item, nova); nova=False se ela já estava lá."""
        dados, ext, largura, altura, animada = preparar(dados)
        ident = hashlib.sha1(dados).hexdigest()[:16]
        itens = self.lista()
        for item in itens:
            if item["id"] == ident:
                return item, False
        if len(itens) >= LIMITE:
            raise ErroFigurinha(f"você já tem {LIMITE} figurinhas; apague algumas antes")
        self.pasta.mkdir(parents=True, exist_ok=True)
        arquivo = f"{ident}.{ext}"
        (self.pasta / arquivo).write_bytes(dados)
        item = {
            "id": ident,
            "arquivo": arquivo,
            "largura": largura,
            "altura": altura,
            "animada": animada,
            "tamanho": len(dados),
            "origem": (origem or "")[:80],
            "criada": time.time(),
        }
        itens.append(item)
        self._salvar_indice(itens)
        return item, True

    def importar(self, caminhos: list[Path | str]) -> dict:
        """Importa arquivos soltos e pacotes (.zip/.wastickers). Devolve {"novas", "repetidas", "erros"}."""
        res = {"novas": 0, "repetidas": 0, "erros": []}

        def um(dados: bytes, nome: str):
            try:
                _, nova = self.adicionar(dados, nome)
            except ErroFigurinha as e:
                res["erros"].append(f"{nome}: {e}")
                if "apague algumas" in str(e):
                    raise
                return
            res["novas" if nova else "repetidas"] += 1

        try:
            for cam in caminhos:
                cam = Path(cam)
                ext = cam.suffix.lower().lstrip(".")
                if ext in PACOTES:
                    self._importar_pacote(cam, um, res)
                elif ext in TIPOS:
                    try:
                        if cam.stat().st_size > MAX_ENTRADA:
                            res["erros"].append(f"{cam.name}: arquivo grande demais")
                            continue
                        um(cam.read_bytes(), cam.name)
                    except OSError:
                        res["erros"].append(f"{cam.name}: não consegui ler")
                else:
                    res["erros"].append(f"{cam.name}: tipo de arquivo que não vira figurinha")
        except ErroFigurinha:
            pass
        return res

    @staticmethod
    def _importar_pacote(cam: Path, um, res: dict) -> None:
        """Pacote do WhatsApp (.wastickers) ou conversa exportada (.zip): pega as .webp de dentro."""
        try:
            with zipfile.ZipFile(cam) as z:
                entradas = [
                    i for i in z.infolist()
                    if not i.is_dir() and i.filename.lower().endswith(".webp") and 0 < i.file_size <= MAX_ENTRADA
                ][:MAX_ZIP]
                if not entradas:
                    res["erros"].append(f"{cam.name}: não achei figurinhas (.webp) dentro")
                    return
                for i in entradas:
                    um(z.read(i), Path(i.filename).name)
        except (OSError, zipfile.BadZipFile):
            res["erros"].append(f"{cam.name}: não consegui abrir o pacote")

    def usada(self, ident: str) -> None:
        itens = self.lista()
        for item in itens:
            if item["id"] == ident:
                item["usada"] = time.time()
                self._salvar_indice(itens)
                return

    def apagar(self, ident: str) -> None:
        itens = self.lista()
        resto = [i for i in itens if i["id"] != ident]
        for i in itens:
            if i["id"] == ident:
                _apagar_arquivo(self.caminho(i))
        self._salvar_indice(resto)


def _apagar_arquivo(caminho: Path, tentativas: int = 4) -> bool:
    """Apaga o arquivo. No Windows, o antivírus às vezes segura um arquivo recém-gravado por um instante
    (PermissionError): espera um pouco e tenta de novo, em vez de deixar o arquivo para trás."""
    for i in range(tentativas):
        try:
            caminho.unlink(missing_ok=True)
            return True
        except PermissionError:
            time.sleep(0.1 * (i + 1))
        except OSError:
            return False
    return False


def resumo(res: dict) -> str:
    """Frase para mostrar depois de importar."""
    partes = []
    if res["novas"]:
        partes.append(f"{res['novas']} figurinha{'s' if res['novas'] > 1 else ''} nova{'s' if res['novas'] > 1 else ''}")
    if res["repetidas"]:
        partes.append(f"{res['repetidas']} que você já tinha")
    if not partes:
        return "Nenhuma figurinha importada" + (f" ({res['erros'][0]})" if res["erros"] else ".")
    frase = "Importadas: " + " e ".join(partes) + "."
    if res["erros"]:
        frase += f" {len(res['erros'])} arquivo{'s' if len(res['erros']) > 1 else ''} não deu certo."
    return frase
