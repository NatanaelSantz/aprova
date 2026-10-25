"""Leitura das provas em PDF: texto, questões, gabarito e imagens das páginas."""

from __future__ import annotations

import bisect
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from . import disciplinas

LETRAS = "ABCDE"

_LIXO = re.compile(
    r"^(pcimarkpci\b.*|www\.pciconcursos\.com\.br|p[áa]gina\s*\d+\s*(de|/)\s*\d+|rascunho|"
    r"espa[çc]o\s+(reservado|para)\s+rascunho.*|\d+\s*/\s*\d+)$",
    re.I,
)
# rodapé/cabeçalho de página em caixa alta: "... TIPO 1 – PÁGINA 3", "... PÁGINA 12"
_RODAPE = re.compile(r"^[^a-zà-ú]{0,160}\bP[ÁA]GINA\s+\d+(\s*(DE|/)\s*\d+)?\s*$")


@dataclass
class Questao:
    numero: int
    enunciado: str
    alternativas: dict[str, str] = field(default_factory=dict)
    tipo: str = "ME"  # ME = múltipla escolha; CE = certo/errado
    disciplina: str = "Geral"
    pagina: int = 0
    texto_base: str = ""
    gabarito: str | None = None


@dataclass
class ResultadoLeitura:
    questoes: list[Questao]
    paginas: int
    tem_texto: bool
    qualidade: float  # 0..1: fração de questões com alternativas completas

    @property
    def aproveitavel(self) -> bool:
        return len(self.questoes) >= 3 and self.qualidade >= 0.6


# --------------------------------------------------------------------------
# texto por página, respeitando colunas


def _ordenar_blocos(blocos: list[tuple], largura: float) -> list[tuple]:
    meio = largura / 2
    folga = largura * 0.06
    esq, dir_, cheio = [], [], []
    for b in blocos:
        x0, y0, x1, y1 = b[:4]
        if x0 >= meio - folga:
            dir_.append(b)
        elif x1 <= meio + folga:
            esq.append(b)
        else:
            cheio.append(b)
    texto_esq = sum(len(b[4]) for b in esq)
    texto_dir = sum(len(b[4]) for b in dir_)
    total = texto_esq + texto_dir + sum(len(b[4]) for b in cheio) or 1
    duas_colunas = len(esq) >= 2 and len(dir_) >= 2 and texto_esq / total > 0.15 and texto_dir / total > 0.15
    if not duas_colunas:
        return sorted(blocos, key=lambda b: (round(b[1], 0), b[0]))
    topo_colunas = min(b[1] for b in esq + dir_)
    topo = [b for b in cheio if b[3] <= topo_colunas + 4]
    resto = [b for b in cheio if b not in topo]
    chave = lambda b: (b[1], b[0])  # noqa: E731
    return sorted(topo, key=chave) + sorted(esq, key=chave) + sorted(dir_, key=chave) + sorted(resto, key=chave)


def ler_paginas(pdf: Path) -> list[list[str]]:
    """Linhas de texto de cada página, na ordem de leitura e sem cabeçalhos repetidos."""
    paginas: list[list[str]] = []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            blocos = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
            linhas: list[str] = []
            for b in _ordenar_blocos(blocos, page.rect.width):
                for ln in b[4].splitlines():
                    ln = re.sub(r"\s+", " ", ln).strip()
                    if ln and not _LIXO.match(ln) and not _RODAPE.match(ln):
                        linhas.append(ln)
            paginas.append(linhas)
    # remove cabeçalhos/rodapés que se repetem em muitas páginas
    if len(paginas) >= 2:
        cont = Counter(ln for pg in paginas for ln in set(pg) if len(ln) < 110)
        limite = max(2, int(len(paginas) * 0.4))
        minimo = 12 if len(paginas) < 3 else 3
        repetidas = {
            ln
            for ln, n in cont.items()
            if n >= limite and len(ln) >= minimo and not re.fullmatch(r"\(?[A-E]\)?.{0,20}", ln)
        }
        paginas = [[ln for ln in pg if ln not in repetidas] for pg in paginas]
    return paginas


def tem_texto(pdf: Path) -> bool:
    with pymupdf.open(pdf) as doc:
        return sum(len(p.get_text("text").strip()) for p in doc) > 200


def renderizar_pagina(pdf: Path, indice: int, destino: Path, dpi: int = 110) -> Path:
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as doc:
        pix = doc[indice].get_pixmap(dpi=dpi)
        pix.save(destino)
    return destino


def contar_paginas(pdf: Path) -> int:
    with pymupdf.open(pdf) as doc:
        return doc.page_count


# --------------------------------------------------------------------------
# questões

_Q_PADROES = [
    # (regex, força)
    (re.compile(r"^(?:QUEST[ÃA]O|Quest[ãa]o)\s*(?:N[º°o.]*\s*)?(\d{1,3})\b[\s\-–—.:)]*(.*)$"), 3),
    (re.compile(r"^(\d{1,3})\s*[.)\-–—:]\s*(.*)$"), 2),
    (re.compile(r"^(\d{1,3})$"), 1),
    (re.compile(r"^(\d{1,3})\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ\"“(].*)$"), 1),
]

_ALT = re.compile(r"^\(?([A-Ea-e])\s*[).\-–—]\s*(.*)$")
_ALT_INLINE = re.compile(r"\s\(([B-E])\)\s")
_TEXTO_BASE = re.compile(
    r"(texto|leia|considere|instru[çc][õo]es|para responder).{0,60}?quest(?:ões|oes|ão|ao)\s*(?:de\s*)?(\d{1,3})\s*(?:a|e|até|-|–)\s*(\d{1,3})",
    re.I,
)


@dataclass
class _Cand:
    linha: int
    numero: int
    resto: str
    forca: int


def _candidatos(linhas: list[str]) -> list[_Cand]:
    cands = []
    for i, ln in enumerate(linhas):
        for rx, forca in _Q_PADROES:
            m = rx.match(ln)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 300:
                    resto = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                    cands.append(_Cand(i, n, (resto or "").strip(), forca))
                break
    return cands


def _melhor_cadeia(cands: list[_Cand]) -> list[_Cand]:
    """Maior sequência de questões numeradas 1, 2, 3... em ordem de leitura."""
    melhor: dict[int, tuple[int, int, int | None]] = {}  # idx -> (tamanho, força, anterior)
    por_numero: dict[int, list[int]] = defaultdict(list)
    for idx, c in enumerate(cands):
        tam, forca, ant = 1, c.forca, None
        for j in por_numero.get(c.numero - 1, []):
            if cands[j].linha < c.linha:
                t, f, _ = melhor[j]
                if (t + 1, f + c.forca) > (tam, forca):
                    tam, forca, ant = t + 1, f + c.forca, j
        melhor[idx] = (tam, forca, ant)
        por_numero[c.numero].append(idx)
    if not melhor:
        return []
    fim = max(melhor, key=lambda k: (melhor[k][0], melhor[k][1]))
    cadeia = []
    k: int | None = fim
    while k is not None:
        cadeia.append(cands[k])
        k = melhor[k][2]
    cadeia.reverse()
    return cadeia if len(cadeia) >= 3 else []


def _separar_alternativas(linhas: list[str]) -> tuple[list[str], dict[str, str], list[str]]:
    """Divide o bloco da questão em (enunciado, alternativas, sobra_depois)."""
    expand: list[str] = []
    for ln in linhas:
        if re.search(r"\(A\)", ln) and _ALT_INLINE.search(ln):
            partes = re.split(r"\s(?=\([B-E]\)\s)", ln)
            expand.extend(p.strip() for p in partes if p.strip())
        else:
            expand.append(ln)
    linhas = expand
    marcas: list[tuple[int, str, str]] = []
    esperado = 0
    for i, ln in enumerate(linhas):
        m = _ALT.match(ln)
        if m and m.group(1).upper() == LETRAS[esperado]:
            marcas.append((i, m.group(1).upper(), m.group(2)))
            esperado += 1
            if esperado == 5:
                break
        elif m and esperado > 0 and m.group(1).upper() == "A":
            # recomeçou: era uma enumeração no enunciado; reinicia
            marcas = [(i, "A", m.group(2))]
            esperado = 1
    if len(marcas) < 4:
        return linhas, {}, []
    alts: dict[str, str] = {}
    sobra: list[str] = []
    for k, (i, letra, primeira) in enumerate(marcas):
        fim = marcas[k + 1][0] if k + 1 < len(marcas) else len(linhas)
        corpo = [primeira] + linhas[i + 1 : fim]
        if k == len(marcas) - 1 and len(corpo) > 1:
            # A última alternativa tem tamanho parecido com as outras; o que passar
            # disso é texto que vem antes da próxima questão.
            tamanhos = [len(v) for v in alts.values()] or [80]
            limite = max(90, int(max(tamanhos) * 1.6))
            media = sum(tamanhos) / len(tamanhos)
            texto_ult = [corpo[0]]
            for j, ln in enumerate(corpo[1:], start=1):
                atual = len(_juntar(texto_ult))
                if atual + len(ln) > limite or (texto_ult[-1].endswith((".", "?", "!")) and atual >= media * 0.5):
                    sobra = corpo[j:]
                    break
                texto_ult.append(ln)
            corpo = texto_ult
        alts[letra] = _juntar(corpo)
    return linhas[: marcas[0][0]], alts, sobra


def _juntar(linhas: list[str]) -> str:
    texto = ""
    for ln in linhas:
        if not ln:
            continue
        if texto.endswith("-") and not texto.endswith(" -"):
            texto = texto[:-1] + ln  # palavra hifenizada na quebra de linha
        elif texto:
            texto += " " + ln
        else:
            texto = ln
    return texto.strip()


def _paragrafos(linhas: list[str]) -> str:
    """Junta linhas mantendo quebras de parágrafo prováveis."""
    saida: list[str] = []
    atual: list[str] = []
    for ln in linhas:
        atual.append(ln)
        if ln.endswith((".", ":", "?", "!")) and len(ln) < 60:
            saida.append(_juntar(atual))
            atual = []
    if atual:
        saida.append(_juntar(atual))
    return "\n\n".join(p for p in saida if p)


def extrair_questoes(pdf: Path) -> ResultadoLeitura:
    paginas = ler_paginas(pdf)
    linhas: list[str] = []
    pagina_da_linha: list[int] = []
    for p, pg in enumerate(paginas):
        linhas.extend(pg)
        pagina_da_linha.extend([p] * len(pg))
    if sum(len(ln) for ln in linhas) < 200:
        return ResultadoLeitura([], len(paginas), False, 0.0)

    # seções de disciplina
    secao_da_linha: list[str | None] = []
    atual: str | None = None
    for ln in linhas:
        s = disciplinas.secao_de_linha(ln)
        if s is not None:
            atual = s or None
        secao_da_linha.append(atual)

    cadeia = _melhor_cadeia(_candidatos(linhas))
    questoes: list[Questao] = []
    textos_base: dict[int, str] = {}
    if cadeia:
        # texto de apoio antes da primeira questão
        preambulo = linhas[: cadeia[0].linha]
        for j, ln in enumerate(preambulo):
            m = _TEXTO_BASE.search(ln)
            if m:
                ini, fim_q = int(m.group(2)), int(m.group(3))
                if fim_q >= ini:
                    resto = [x for x in preambulo[j + 1 :] if disciplinas.secao_de_linha(x) is None]
                    base = _paragrafos(resto)
                    for n in range(ini, fim_q + 1):
                        textos_base[n] = base
                break
    for k, c in enumerate(cadeia):
        fim = cadeia[k + 1].linha if k + 1 < len(cadeia) else len(linhas)
        bloco = ([c.resto] if c.resto else []) + linhas[c.linha + 1 : fim]
        bloco = [ln for ln in bloco if disciplinas.secao_de_linha(ln) is None]
        # texto compartilhado anunciado no meio do bloco ("Leia o texto para as questões 6 a 10")
        for j, ln in enumerate(bloco):
            m = _TEXTO_BASE.search(ln)
            if m and j > 0:
                ini, fim_q = int(m.group(2)), int(m.group(3))
                if ini > c.numero and fim_q >= ini:
                    base = _paragrafos(bloco[j + 1 :])
                    for n in range(ini, fim_q + 1):
                        textos_base[n] = base
                    bloco = bloco[:j]
                break
        enun, alts, sobra = _separar_alternativas(bloco)
        q = Questao(
            numero=c.numero,
            enunciado=_paragrafos(enun),
            alternativas=alts,
            tipo="ME" if alts else "CE",
            pagina=pagina_da_linha[c.linha],
            disciplina=secao_da_linha[c.linha] or "",
        )
        if sobra and sum(len(s) for s in sobra) > 250 and (c.numero + 1) not in textos_base:
            textos_base[c.numero + 1] = _paragrafos(sobra)
        questoes.append(q)
    for q in questoes:
        q.texto_base = textos_base.get(q.numero, "")
        if q.tipo == "CE":
            q.alternativas = {"C": "Certo", "E": "Errado"}
        if not q.disciplina:
            q.disciplina = disciplinas.classificar(q.enunciado, q.alternativas)
    me = [q for q in questoes if q.tipo == "ME"]
    if me and len(me) < len(questoes) * 0.5:
        # prova é de múltipla escolha mas algumas questões não tiveram alternativas lidas
        qualidade = len(me) / len(questoes)
    elif me:
        qualidade = sum(1 for q in me if len(q.alternativas) >= 4) / len(questoes)
    else:
        # certo/errado: qualidade pela quantidade de enunciados com texto
        qualidade = sum(1 for q in questoes if len(q.enunciado) > 20) / max(1, len(questoes))
    return ResultadoLeitura(questoes, len(paginas), True, qualidade)


# --------------------------------------------------------------------------
# gabarito

_RESP = r"(?:[A-E]|X|\*|NULA|ANULADA|C|E)"
_PAR = re.compile(r"(?<![\d/.,])(\d{1,3})\s*[-–:.)]?\s*(" + _RESP + r")(?![A-Za-zÀ-ú])")


def _normalizar_resposta(r: str) -> str:
    r = r.upper()
    return "*" if r in ("X", "*", "NULA", "ANULADA") else r


def _cadeias(pares: list[tuple[int, int, str]]) -> list[list[tuple[int, int, str]]]:
    """Agrupa pares (posição, número, resposta) em sequências 1,2,3..."""
    cadeias: list[list[tuple[int, int, str]]] = []
    atual: list[tuple[int, int, str]] = []
    for p in pares:
        if atual and p[1] == atual[-1][1] + 1:
            atual.append(p)
        elif p[1] == 1:
            if len(atual) >= 5:
                cadeias.append(atual)
            atual = [p]
        elif atual and p[1] <= atual[-1][1]:
            if len(atual) >= 5:
                cadeias.append(atual)
            atual = []
    if len(atual) >= 5:
        cadeias.append(atual)
    return cadeias


def _pares_tabela(linhas: list[str]) -> list[tuple[int, int, str]]:
    """Gabaritos em tabela: uma linha de números seguida de uma linha de letras.
    A posição de cada par é o índice da linha."""
    pares = []
    for i in range(len(linhas) - 1):
        nums = linhas[i].split()
        letras = linhas[i + 1].split()
        if (
            len(nums) >= 3
            and all(n.isdigit() for n in nums)
            and len(letras) == len(nums)
            and all(re.fullmatch(_RESP, x.upper()) for x in letras)
        ):
            for n, l in zip(nums, letras):
                pares.append((i, int(n), _normalizar_resposta(l)))
    return pares


def _palavras(t: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", disciplinas.sem_acento(t)).split() if len(w) >= 4]


def ler_gabarito_texto(texto: str, n_questoes: int | None = None, cargo: str = "", caderno: str = "") -> dict[int, str]:
    linhas = [ln for ln in texto.splitlines() if not _LIXO.match(ln.strip())]
    texto = "\n".join(linhas)
    inicios = [0]
    for ln in linhas:
        inicios.append(inicios[-1] + len(ln) + 1)
    candidatas = _cadeias(_pares_tabela(linhas))
    pares = [
        (bisect.bisect_right(inicios, m.start()) - 1, int(m.group(1)), _normalizar_resposta(m.group(2)))
        for m in _PAR.finditer(texto)
    ]
    candidatas += _cadeias(pares)
    if not candidatas:
        return {}
    palavras_cargo = set(_palavras(cargo))

    def cabecalho(inicio: int) -> str:
        return disciplinas.sem_acento(" ".join(linhas[max(0, inicio - 6) : inicio + 1]))

    def nota(c):
        n = len(c)
        s = -abs(n - n_questoes) * 3 if n_questoes else n
        cab = cabecalho(c[0][0])
        if palavras_cargo:
            presentes = sum(1 for w in palavras_cargo if w in cab)
            if presentes / len(palavras_cargo) >= 0.8:
                s += 50
        if caderno and re.search(rf"tipo\s*0?{re.escape(caderno)}\b", cab):
            s += 30
        return s

    melhor = max(candidatas, key=nota)
    return {num: resp for _, num, resp in melhor}


def ler_gabarito_pdf(pdf: Path, n_questoes: int | None = None, cargo: str = "", caderno: str = "") -> dict[int, str]:
    with pymupdf.open(pdf) as doc:
        texto = "\n".join(p.get_text("text", sort=True) for p in doc)
    return ler_gabarito_texto(texto, n_questoes, cargo, caderno)


def gabarito_de_texto_livre(texto: str) -> dict[int, str]:
    """Gabarito digitado pelo usuário: '1A 2B 3C', '1-a, 2-b' ou 'ABCDE...' em ordem."""
    texto = texto.strip()
    if not texto:
        return {}
    pares = {int(m.group(1)): _normalizar_resposta(m.group(2)) for m in _PAR.finditer(texto.upper())}
    if len(pares) >= 2:
        return pares
    so_letras = re.sub(r"[^A-EX*]", "", texto.upper())
    return {i + 1: _normalizar_resposta(c) for i, c in enumerate(so_letras)}
