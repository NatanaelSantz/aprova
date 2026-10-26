"""Marcar PDFs: destaque (marca-texto), sublinhado e notas, salvos como anotações do próprio PDF.

O texto do PDF não é alterado: as marcações são anotações padrão, que aparecem em qualquer leitor
(Edge, Chrome, Acrobat, celular). Ao salvar, dá para deixá-las fixas ("assadas" na página), e aí
ninguém consegue apagar ou mudar.

O Aprova trabalha numa cópia do PDF (pasta .aprova/marcados), salva a cada marcação. O arquivo
original nunca é mexido.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import unicodedata
from pathlib import Path

import pymupdf

from . import config

CORES = {
    "amarelo": (1.0, 0.89, 0.25),
    "verde": (0.55, 0.9, 0.55),
    "azul": (0.55, 0.78, 1.0),
    "rosa": (1.0, 0.62, 0.82),
}
AUTOR = "Aprova"


def pasta(base: Path | None = None) -> Path:
    """Pasta das cópias de trabalho. base = pasta de dados da conta (cada pessoa vê só os seus PDFs)."""
    p = Path(base or config.DATA_DIR) / "marcados"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ler_indice(base: Path | None) -> dict:
    try:
        return json.loads((pasta(base) / "indice.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_indice(dados: dict, base: Path | None) -> None:
    arq = pasta(base) / "indice.json"
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def recentes(base: Path | None = None) -> list[dict]:
    """PDFs que a pessoa já marcou no Aprova, do mais recente para o mais antigo."""
    itens = [d for d in _ler_indice(base).values() if Path(d.get("copia", "")).exists()]
    return sorted(itens, key=lambda d: d.get("aberto_em", 0), reverse=True)


def esquecer(item_id: str, base: Path | None = None) -> None:
    """Tira um PDF da lista (apaga a cópia de trabalho do Aprova; o original continua onde estava)."""
    dados = _ler_indice(base)
    item = dados.pop(item_id, None)
    _gravar_indice(dados, base)
    if item:
        try:
            Path(item["copia"]).unlink()
        except OSError:
            pass


def copiar_para(origem: Path, destino: Path) -> int:
    """Leva os PDFs marcados de uma pasta de dados para outra (estudos de visitante → conta)."""
    dados, novos, n = _ler_indice(origem), _ler_indice(destino), 0
    for item_id, item in dados.items():
        copia = Path(item.get("copia", ""))
        if item_id in novos or not copia.exists():
            continue
        alvo = pasta(destino) / copia.name
        shutil.copy2(copia, alvo)
        novos[item_id] = dict(item, copia=str(alvo))
        n += 1
    if n:
        _gravar_indice(novos, destino)
    return n


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()[:40] or "pdf"


class DocumentoMarcado:
    def __init__(self, origem: Path, titulo: str | None = None, autor: str = AUTOR, base: Path | None = None):
        origem = Path(origem)
        self.autor = autor or AUTOR
        if origem.parent.name == "marcados" and (origem.parent / "indice.json").exists():
            # já é uma cópia de trabalho (aberta pela lista de recentes)
            self.base = origem.parent.parent
            self.copia = origem
            existente = next((d for d in recentes(self.base) if Path(d["copia"]) == origem), None)
            self.id = existente["id"] if existente else origem.stem
            self.origem = Path(existente["origem"]) if existente else origem
            self.titulo = titulo or (existente or {}).get("titulo") or origem.stem
        else:
            self.base = Path(base or config.DATA_DIR)
            self.origem = origem
            self.id = hashlib.sha1(str(origem.resolve()).encode("utf-8")).hexdigest()[:10]
            self.titulo = titulo or origem.stem
            self.copia = pasta(self.base) / f"{self.id}-{_slug(self.titulo)}.pdf"
            if not self.copia.exists():
                shutil.copy2(origem, self.copia)
        # aberto da memória: assim o arquivo não fica preso (no Windows, dá para trocar a cópia a cada marcação)
        self.doc = pymupdf.open(stream=self.copia.read_bytes(), filetype="pdf")
        if self.doc.needs_pass:
            self.doc.close()
            raise ValueError("Este PDF tem senha. Abra no leitor de PDF, salve uma cópia sem senha e tente de novo.")
        self._palavras: dict[int, list] = {}
        self._feitas: list[tuple[int, int]] = []  # (página, xref) para desfazer
        self._registrar()

    # ------------------------------------------------------------------ básico

    @property
    def paginas(self) -> int:
        return self.doc.page_count

    def tamanho(self, pagina: int) -> tuple[float, float]:
        r = self.doc[pagina].rect
        return r.width, r.height

    def imagem(self, pagina: int, escala: float = 1.5) -> bytes:
        """PNG da página com as marcações (escala 1 = 72 pontos por polegada)."""
        pix = self.doc[pagina].get_pixmap(matrix=pymupdf.Matrix(escala, escala), annots=True, alpha=False)
        return pix.tobytes("png")

    def tem_texto(self) -> bool:
        return any(self.palavras(i) for i in range(min(self.paginas, 3)))

    def palavras(self, pagina: int) -> list:
        if pagina not in self._palavras:
            self._palavras[pagina] = self.doc[pagina].get_text("words")
        return self._palavras[pagina]

    # ------------------------------------------------------------------ seleção

    def _linhas(self, pagina: int) -> list[tuple[pymupdf.Rect, list[int]]]:
        """Linhas de texto da página: (retângulo da linha, índices das palavras)."""
        chave = ("linhas", pagina)
        if chave not in self._palavras:
            grupos: dict[tuple, list[int]] = {}
            for i, w in enumerate(self.palavras(pagina)):
                grupos.setdefault((w[5], w[6]), []).append(i)
            linhas = []
            for indices in grupos.values():
                r = pymupdf.Rect(self.palavras(pagina)[indices[0]][:4])
                for i in indices[1:]:
                    r |= pymupdf.Rect(self.palavras(pagina)[i][:4])
                linhas.append((r, indices))
            self._palavras[chave] = linhas
        return self._palavras[chave]

    def _mais_perto(self, pagina: int, x: float, y: float) -> int | None:
        """Palavra mais perto do ponto, como num editor: primeiro a linha (pela altura), depois a palavra."""
        palavras = self.palavras(pagina)
        if not palavras:
            return None

        def distancia(r, x, y):
            dy = 0 if r.y0 <= y <= r.y1 else min(abs(y - r.y0), abs(y - r.y1))
            dx = 0 if r.x0 <= x <= r.x1 else min(abs(x - r.x0), abs(x - r.x1))
            return dy, dx

        _, indices = min(self._linhas(pagina), key=lambda li: distancia(li[0], x, y))
        return min(indices, key=lambda i: distancia(pymupdf.Rect(palavras[i][:4]), x, palavras[i][1])[1])

    def selecao(self, pagina: int, a: tuple[float, float], b: tuple[float, float]) -> list[pymupdf.Rect]:
        """Retângulos (um por linha) do texto entre os pontos a e b, na ordem de leitura.

        Em PDF digitalizado (sem texto), devolve o retângulo arrastado."""
        ia, ib = self._mais_perto(pagina, *a), self._mais_perto(pagina, *b)
        if ia is None or ib is None:
            r = pymupdf.Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            return [r] if r.width > 4 and r.height > 4 else []
        if ia > ib:
            ia, ib = ib, ia
        linhas: dict[tuple, pymupdf.Rect] = {}
        for w in self.palavras(pagina)[ia: ib + 1]:
            chave = (w[5], w[6])
            r = pymupdf.Rect(w[:4])
            linhas[chave] = linhas[chave] | r if chave in linhas else r
        return list(linhas.values())

    def trecho(self, pagina: int, rects: list) -> str:
        """Texto das palavras cujo centro está dentro dos retângulos, na ordem de leitura."""
        caixas = [pymupdf.Rect(r) for r in rects]
        palavras = []
        for w in self.palavras(pagina):
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            if any(r.x0 - 1 <= cx <= r.x1 + 1 and r.y0 - 1 <= cy <= r.y1 + 1 for r in caixas):
                palavras.append(w[4])
        return re.sub(r"\s+", " ", " ".join(palavras)).strip()

    # ------------------------------------------------------------------ marcações

    def marcar(self, pagina: int, a: tuple[float, float], b: tuple[float, float], tipo: str = "destaque", cor: str = "amarelo", nota: str = "") -> dict | None:
        rects = self.selecao(pagina, a, b)
        if not rects:
            return None
        page = self.doc[pagina]
        rgb = CORES.get(cor, CORES["amarelo"])
        if self.palavras(pagina):
            if tipo == "sublinhado":
                annot = page.add_underline_annot(rects)
            else:
                annot = page.add_highlight_annot(rects)
            annot.set_colors(stroke=rgb)
        else:
            # página digitalizada: um retângulo translúcido no lugar do marca-texto
            annot = page.add_rect_annot(rects[0])
            annot.set_colors(stroke=rgb, fill=rgb)
            annot.set_border(width=0)
            annot.set_opacity(0.35)
        info = {"title": self.autor, "subject": "Sublinhado" if tipo == "sublinhado" else "Destaque"}
        if nota:
            info["content"] = nota
        annot.set_info(info)
        annot.update()
        self._feitas.append((pagina, annot.xref))
        self.salvar()
        return self._descrever(pagina, annot)

    def nota(self, pagina: int, ponto: tuple[float, float], texto: str) -> dict:
        page = self.doc[pagina]
        annot = page.add_text_annot(pymupdf.Point(*ponto), texto.strip(), icon="Comment")
        annot.set_colors(stroke=CORES["amarelo"])
        annot.set_info(title=self.autor, subject="Nota")
        annot.update()
        self._feitas.append((pagina, annot.xref))
        self.salvar()
        return self._descrever(pagina, annot)

    def _achar(self, pagina: int, xref: int):
        """(página, anotação). A página precisa ficar viva enquanto a anotação é usada."""
        page = self.doc[pagina]
        for annot in page.annots() or []:
            if annot.xref == xref:
                return page, annot
        return page, None

    def editar_nota(self, pagina: int, xref: int, texto: str) -> None:
        _page, annot = self._achar(pagina, xref)
        if annot is None:
            return
        annot.set_info(content=texto.strip())
        annot.update()
        self.salvar()

    def mudar_cor(self, pagina: int, xref: int, cor: str) -> None:
        _page, annot = self._achar(pagina, xref)
        if annot is None:
            return
        rgb = CORES.get(cor, CORES["amarelo"])
        if annot.type[1] == "Square":
            annot.set_colors(stroke=rgb, fill=rgb)
        else:
            annot.set_colors(stroke=rgb)
        annot.update()
        self.salvar()

    def apagar(self, pagina: int, xref: int) -> None:
        page, annot = self._achar(pagina, xref)
        if annot is not None:
            page.delete_annot(annot)
            self._feitas = [f for f in self._feitas if f != (pagina, xref)]
            self.salvar()

    def desfazer(self) -> bool:
        while self._feitas:
            pagina, xref = self._feitas.pop()
            page, annot = self._achar(pagina, xref)
            if annot is not None:
                page.delete_annot(annot)
                self.salvar()
                return True
        return False

    def na_posicao(self, pagina: int, x: float, y: float) -> dict | None:
        """Marcação que está embaixo do ponto (para abrir, mudar a nota ou apagar)."""
        page = self.doc[pagina]
        for annot in page.annots() or []:
            r = annot.rect
            if r.x0 - 2 <= x <= r.x1 + 2 and r.y0 - 2 <= y <= r.y1 + 2:
                return self._descrever(pagina, annot)
        return None

    def _descrever(self, pagina: int, annot) -> dict:
        tipo = {"Highlight": "destaque", "Underline": "sublinhado", "Text": "nota", "Square": "destaque", "FreeText": "nota"}.get(annot.type[1], annot.type[1].lower())
        cores = annot.colors or {}
        rgb = tuple(round(c, 2) for c in (cores.get("stroke") or cores.get("fill") or CORES["amarelo"]))
        cor = min(CORES, key=lambda k: sum((a - b) ** 2 for a, b in zip(CORES[k], rgb)))
        if tipo == "nota":
            trecho = ""
        else:
            verts = annot.vertices or []
            rects = [pymupdf.Quad(verts[i:i + 4]).rect for i in range(0, len(verts), 4)] if verts else [annot.rect]
            trecho = self.trecho(pagina, rects)
        return {"pagina": pagina, "xref": annot.xref, "tipo": tipo, "cor": cor, "trecho": trecho, "nota": (annot.info or {}).get("content", ""), "rect": tuple(annot.rect)}

    def marcacoes(self) -> list[dict]:
        saida = []
        for i in range(self.paginas):
            page = self.doc[i]
            for annot in page.annots() or []:
                if annot.type[1] in ("Highlight", "Underline", "Text", "Square", "FreeText", "StrikeOut"):
                    saida.append(self._descrever(i, annot))
        return sorted(saida, key=lambda m: (m["pagina"], round(m["rect"][1] / 6), m["rect"][0]))

    # ------------------------------------------------------------------ salvar

    def salvar(self) -> None:
        """Guarda na cópia de trabalho (o PDF original não muda).

        Grava num arquivo temporário e troca no fim: se o PC desligar no meio, a cópia anterior fica inteira."""
        tmp = self.copia.with_name(self.copia.stem + ".salvando.pdf")
        self.doc.save(tmp)
        tmp.replace(self.copia)
        self._registrar()

    def exportar(self, destino: Path, fixas: bool = False) -> Path:
        """Salva um PDF novo com as marcações.

        fixas=True: as marcações viram parte da página (ninguém apaga nem muda) e o texto das notas,
        que deixaria de abrir ao clicar, vai para páginas "Minhas anotações" no fim do arquivo."""
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        marcacoes = self.marcacoes() if fixas else []
        with pymupdf.open(stream=self.copia.read_bytes(), filetype="pdf") as copia:
            if fixas:
                copia.bake(annots=True, widgets=False)
                _paginas_de_anotacoes(copia, self.titulo, [m for m in marcacoes if m["nota"] or m["trecho"]])
            copia.save(destino, garbage=3, deflate=True)
        return destino

    def _registrar(self) -> None:
        try:
            n = sum(1 for i in range(self.paginas) for _ in (self.doc[i].annots() or []))
        except Exception:  # noqa: BLE001
            n = 0
        dados = _ler_indice(self.base)
        dados[self.id] = {"id": self.id, "titulo": self.titulo, "origem": str(self.origem), "copia": str(self.copia), "paginas": self.paginas, "marcacoes": n, "aberto_em": time.time()}
        _gravar_indice(dados, self.base)

    def fechar(self) -> None:
        try:
            self.doc.close()
        except Exception:  # noqa: BLE001
            pass


def _html(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")


def _paginas_de_anotacoes(doc, titulo: str, marcacoes: list[dict]) -> None:
    """Acrescenta ao fim do PDF a lista de marcações e notas, página por página."""
    if not marcacoes:
        return
    largura, altura = (doc[-1].rect.width, doc[-1].rect.height) if doc.page_count else (595, 842)
    margem = 56
    estilo = "font-family: sans-serif; font-size: 10.5pt; color: #222; margin: 0;"
    page, y = None, 0.0

    def nova_pagina(primeira: bool):
        nonlocal page, y
        page = doc.new_page(width=largura, height=altura)
        y = margem
        cab = f"<p style='{estilo} font-size: 15pt; font-weight: bold;'>Minhas anotações</p><p style='{estilo} color: #666;'>{_html(titulo)}</p>" if primeira else f"<p style='{estilo} color: #666;'>Minhas anotações (continuação)</p>"
        livre, _ = page.insert_htmlbox(pymupdf.Rect(margem, y, largura - margem, altura - margem), cab, scale_low=1)
        y = altura - margem - livre + 14

    nova_pagina(True)
    for m in marcacoes:
        tipo = {"destaque": "Destaque", "sublinhado": "Sublinhado", "nota": "Nota"}.get(m["tipo"], "Marcação")
        partes = [f"<p style='{estilo} font-weight: bold;'>Pág. {m['pagina'] + 1} · {tipo}</p>"]
        if m["trecho"]:
            partes.append(f"<p style='{estilo} color: #555; font-style: italic;'>“{_html(m['trecho'][:600])}”</p>")
        if m["nota"]:
            partes.append(f"<p style='{estilo}'>{_html(m['nota'])}</p>")
        html = "".join(partes)
        for tentativa in range(2):
            livre, _ = page.insert_htmlbox(pymupdf.Rect(margem, y, largura - margem, altura - margem), html, scale_low=1)
            if livre >= 0:
                y = altura - margem - livre + 10
                break
            if tentativa == 0:
                nova_pagina(False)
            else:  # nota maior que uma página inteira: escreve reduzida
                livre, _ = page.insert_htmlbox(pymupdf.Rect(margem, y, largura - margem, altura - margem), html, scale_low=0)
                y = altura - margem


def nome_para_salvar(titulo: str) -> str:
    base = re.sub(r'[<>:"/\\|?*]+', " ", titulo).strip() or "documento"
    return f"{base} (marcado).pdf"
