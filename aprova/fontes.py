"""Buscador central: encontra provas, gabaritos e editais de um concurso em várias fontes.

Fontes, da mais confiável para a menos:
1. Site oficial da banca (hoje a FGV Conhecimento é lida direto; outras bancas entram
   quando a página do concurso tem os PDFs no HTML).
2. Busca na internet por PDFs de prova e gabarito do concurso (qualquer site).
3. PCI Concursos (acervo grande de provas antigas; o download passa pelo navegador).

Cada arquivo encontrado vira um `Achado`, com o tipo (prova, gabarito, edital...),
o cargo e o tipo de caderno quando dá para descobrir.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from . import ajuda
from .pci import ClientePCI, ErroRede, ProvaItem

# domínio -> nome da banca (sites oficiais)
BANCAS: dict[str, str] = {
    "conhecimento.fgv.br": "FGV",
    "cebraspe.org.br": "Cebraspe",
    "cdn.cebraspe.org.br": "Cebraspe",
    "vunesp.com.br": "Vunesp",
    "cesgranrio.org.br": "Cesgranrio",
    "ibfc.org.br": "IBFC",
    "institutoaocp.org.br": "Instituto AOCP",
    "quadrix.org.br": "Quadrix",
    "idecan.org.br": "IDECAN",
    "consulplan.net": "Consulplan",
    "fundatec.org.br": "Fundatec",
    "iades.com.br": "IADES",
    "objetivas.com.br": "Objetiva",
    "selecon.org.br": "Selecon",
    "ibade.org.br": "IBADE",
    "avancasp.org.br": "Avança SP",
    "institutomais.org.br": "Instituto Mais",
    "fundep.ufmg.br": "Fundep",
    "fcc.org.br": "FCC",
    "concursosfcc.com.br": "FCC",
    "cetrede.com.br": "CETREDE",
    "funcern.br": "Funcern",
    "ufpr.br": "UFPR",
    "comperve.ufrn.br": "Comperve",
}

# Sites que pedem para não serem lidos por robôs: não buscamos páginas deles.
NAO_LER = {"concursosfcc.com.br"}

FGV_LISTA = "https://conhecimento.fgv.br/concursos?page={pagina}"
FGV_BASE = "https://conhecimento.fgv.br"


@dataclass
class Achado:
    titulo: str
    url: str
    tipo: str  # prova | gabarito | edital | comentada | outro
    fonte: str  # nome amigável: "FGV (site oficial)", "brasilescola.uol.com.br"...
    oficial: bool = False
    cargo: str = ""
    caderno: str = ""  # "1", "2"... (tipo/cor do caderno)
    pagina: str = ""  # página onde o link estava
    contexto: str = ""

    @property
    def dominio(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")


@dataclass
class ConcursoBanca:
    nome: str
    url: str
    banca: str
    situacao: str = ""  # em andamento | realizado


@dataclass
class Resultado:
    termo: str
    oficiais: list[Achado] = field(default_factory=list)
    web: list[Achado] = field(default_factory=list)
    pci: list[ProvaItem] = field(default_factory=list)
    paginas_oficiais: list[ConcursoBanca] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    web_falhou: bool = False

    @property
    def total(self) -> int:
        return len(self.oficiais) + len(self.web) + len(self.pci)


# ---------------------------------------------------------------------------- texto


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


PALAVRAS_VAZIAS = {"concurso", "publico", "para", "do", "da", "de", "dos", "das", "e", "o", "a", "processo", "seletivo", "edital"}


def tokens(t: str) -> list[str]:
    return [w for w in norm(t).split() if w not in PALAVRAS_VAZIAS and len(w) > 1]


def parecido(consulta: str, nome: str) -> float:
    """Quanto o nome de um concurso combina com o que a pessoa digitou (0..1)."""
    q = tokens(consulta)
    if not q:
        return 0.0
    alvo = norm(nome)
    alvo_compacto = alvo.replace(" ", "")
    acertos = 0
    for w in q:
        if re.fullmatch(r"20\d\d", w):
            # ano: aceita "2026" ou "26" no slug (dataprev26)
            if w in alvo or w[2:] in alvo_compacto:
                acertos += 1
        elif w in alvo.split() or w in alvo_compacto:
            acertos += 1
    return acertos / len(q)


def classificar(texto: str, url: str) -> str:
    t = norm(texto + " " + unquote(urlparse(url).path.rsplit("/", 1)[-1]))
    if "gabarito" in t or re.search(r"\bgab\b", t):
        return "gabarito"
    if re.search(r"comentad|resolvid|\bcorrecao\b", t):
        return "comentada"
    if re.search(
        r"\b(resultado|isencao|demanda|convocacao|local de prova|locais de prova|homologacao|classificacao|comunicado|"
        r"recursos?|cronograma|termos|aviso|cookies|privacidade|sub judice|atendimento|deferidos?|indeferidos?|"
        r"candidatos? inscritos|lista de|certificado)\b",
        t,
    ):
        return "outro"
    if re.search(r"\bedital\b|retificac|\bextrato\b", t):
        return "edital"
    if re.search(r"\bprova\b|caderno|\btipo \d\b|objetiva|discursiva|questoes", t):
        return "prova"
    return "outro"


def caderno_de(texto: str) -> str:
    m = re.search(r"tipo[\s_-]*0?(\d)\b", norm(texto))
    return m.group(1) if m else ""


def cargo_do_arquivo(url: str) -> str:
    """'analista-de-ti-desenvolvimento-de-software-cns003-tipo-1.pdf' -> 'Analista de TI Desenvolvimento de Software'."""
    nome = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    nome = re.sub(r"\.pdf$", "", nome, flags=re.I)
    nome = re.sub(r"(?i)[-_ ]?(tipo|caderno|prova)[-_ ]?\d+.*$", "", nome)
    nome = re.sub(r"(?i)[-_]?(cns|cod|c)\d{2,}", "", nome)
    nome = re.sub(r"[_-]+", " ", nome).strip()
    menores = {"de", "da", "do", "das", "dos", "e", "em", "para"}
    return " ".join(w if w in menores else w.capitalize() for w in nome.split())


def _contexto(a) -> str:
    """Texto próximo ao link (o rótulo do cargo costuma vir antes de 'Tipo 1', 'Tipo 2'...)."""
    textos = []
    for s in a.find_all_previous(string=True, limit=12):
        s = re.sub(r"\s+", " ", s).strip()
        if not s or re.fullmatch(r"(?i)tipo\s*\d|download|baixar|pdf|\d{2}/\d{2}/\d{4}", s):
            continue
        textos.append(s)
        if len(s) > 6 and sum(ch.isupper() for ch in s if ch.isalpha()) >= 0.6 * max(1, sum(ch.isalpha() for ch in s)):
            break
        if len(textos) >= 3:
            break
    return " | ".join(reversed(textos))[:220]


def extrair_arquivos(html: str, base_url: str, fonte: str, oficial: bool) -> list[Achado]:
    soup = BeautifulSoup(html, "html.parser")
    achados: list[Achado] = []
    vistos: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        if not re.search(r"\.pdf(\?|#|$)", href, re.I):
            continue
        if href in vistos:
            continue
        vistos.add(href)
        texto = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        generico = not texto or re.fullmatch(r"(?i)(tipo\s*\d+|download|baixar|clique aqui|pdf|arquivo|ver|abrir)", texto)
        contexto = _contexto(a)
        titulo = texto if not generico else ""
        cargo = ""
        if generico:
            rotulo = contexto.split(" | ")[0] if contexto else ""
            cargo = rotulo if rotulo and len(rotulo) < 120 else cargo_do_arquivo(href)
            titulo = f"{cargo} — {texto}" if texto else cargo
        # o contexto só ajuda quando o texto do link é genérico ("Tipo 1", "Baixar")
        tipo = classificar(f"{titulo} {contexto}" if generico else titulo, href)
        if tipo == "prova" and not cargo:
            cargo = re.sub(r"(?i)\s*[-–]?\s*(prova|caderno)?\s*tipo\s*\d+.*$", "", titulo).strip() or cargo_do_arquivo(href)
        achados.append(
            Achado(
                titulo=titulo or cargo_do_arquivo(href) or href.rsplit("/", 1)[-1],
                url=href,
                tipo=tipo,
                fonte=fonte,
                oficial=oficial,
                cargo=cargo,
                caderno=caderno_de(f"{texto} {href}"),
                pagina=base_url,
                contexto=contexto,
            )
        )
    return achados


def parse_lista_fgv(html: str) -> list[ConcursoBanca]:
    soup = BeautifulSoup(html, "html.parser")
    itens: list[ConcursoBanca] = []
    vistos: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(FGV_BASE, a["href"].strip())
        if not re.match(r"https?://conhecimento\.fgv\.br/(concursos/[\w.-]+|processoseletivo/[\w.-]+|exames/[\w./-]+|cpnu\w*|res\w+)/?$", href):
            continue
        if re.search(r"/concursos/?$|page=", href) or href in vistos:
            continue
        nome = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if len(nome) < 6:
            continue
        vistos.add(href)
        cab = a.find_previous(string=re.compile(r"concursos (em andamento|realizados)", re.I))
        situacao = "realizado" if cab and "realizad" in cab.lower() else "em andamento"
        itens.append(ConcursoBanca(nome=nome, url=href, banca="FGV", situacao=situacao))
    return itens


# ---------------------------------------------------------------------------- buscador


class Centralizador:
    def __init__(self, pci: ClientePCI):
        self.pci = pci
        self._fgv: list[ConcursoBanca] | None = None
        self._fgv_quando = 0.0

    # ---- FGV

    def concursos_fgv(self, paginas: int = 22) -> list[ConcursoBanca]:
        if self._fgv is not None and time.time() - self._fgv_quando < 6 * 3600:
            return self._fgv
        todos: list[ConcursoBanca] = []
        vistos: set[str] = set()
        for p in range(paginas):
            try:
                html = self.pci.html(FGV_LISTA.format(pagina=p), ttl_horas=12)
            except ErroRede:
                if p == 0:
                    raise
                break
            novos = [c for c in parse_lista_fgv(html) if c.url not in vistos]
            if not novos:
                break
            for c in novos:
                vistos.add(c.url)
                todos.append(c)
        self._fgv, self._fgv_quando = todos, time.time()
        return todos

    def edicoes(self, termo: str, limite: int = 4) -> list[ConcursoBanca]:
        """Edições do mesmo concurso no site oficial (a mais recente primeiro)."""
        from .coleta import ano_de

        base = re.sub(r"\b20\d\d\b", "", termo).strip()
        if not tokens(base):
            return []
        achados = [c for c in self.concursos_fgv() if parecido(base, c.nome + " " + c.url) >= 0.6]
        achados.sort(key=lambda c: ano_de(c.nome, c.url) or "0", reverse=True)
        return achados[:limite]

    def arquivos_da_pagina(self, url: str, banca: str = "") -> list[Achado]:
        dominio = urlparse(url).netloc.lower().removeprefix("www.")
        if any(dominio.endswith(d) for d in NAO_LER):
            return []
        banca = banca or next((b for d, b in BANCAS.items() if dominio.endswith(d)), "")
        html = self.pci.html(url, ttl_horas=6)
        fonte = f"{banca} (site oficial)" if banca else dominio
        return extrair_arquivos(html, url, fonte, oficial=bool(banca))

    # ---- busca geral

    def buscar(self, termo: str, progresso=None, incluir_pci: bool = True) -> Resultado:
        """Procura provas do concurso em todas as fontes. `termo` pode ser um nome ou um link."""

        def passo(f, t):
            if progresso:
                progresso(f, t)

        termo = termo.strip()
        res = Resultado(termo=termo)
        if termo.startswith("http"):
            passo(0.2, "Lendo a página que você colou…")
            try:
                achados = self.arquivos_da_pagina(termo)
                (res.oficiais if any(a.oficial for a in achados) else res.web).extend(achados)
            except ErroRede as e:
                res.avisos.append(f"Página: {e}")
            passo(1, "Pronto")
            return res

        # 1) FGV oficial
        passo(0.05, "Procurando no site da FGV…")
        try:
            candidatos = sorted(self.concursos_fgv(), key=lambda c: parecido(termo, c.nome + " " + c.url), reverse=True)
            bons = [c for c in candidatos if parecido(termo, c.nome + " " + c.url) >= 0.6][:2]
            for c in bons:
                res.paginas_oficiais.append(c)
                res.oficiais += self.arquivos_da_pagina(c.url, "FGV")
        except ErroRede as e:
            res.avisos.append(f"FGV: {e}")

        # 2) internet: páginas oficiais de outras bancas e PDFs soltos
        passo(0.3, "Procurando na internet…")
        consultas = [f"{termo} prova gabarito pdf", f"{termo} concurso provas gabaritos banca"]
        vistos_pag = {p.url for p in res.paginas_oficiais}
        vistos_pdf = {a.url for a in res.oficiais}
        try:
            for i, q in enumerate(consultas):
                for r in ajuda.pesquisar_web(q, max_resultados=10, enciclopedia=False, limite_s=20):
                    url = r["url"]
                    dominio = urlparse(url).netloc.lower().removeprefix("www.")
                    banca = next((b for d, b in BANCAS.items() if dominio.endswith(d)), "")
                    if re.search(r"\.pdf(\?|#|$)", url, re.I):
                        if url in vistos_pdf:
                            continue
                        vistos_pdf.add(url)
                        tipo = classificar(r["titulo"], url)
                        if tipo == "outro":
                            continue
                        destino = res.oficiais if banca else res.web
                        destino.append(
                            Achado(
                                titulo=r["titulo"] or cargo_do_arquivo(url),
                                url=url,
                                tipo=tipo,
                                fonte=f"{banca} (site oficial)" if banca else dominio,
                                oficial=bool(banca),
                                cargo=cargo_do_arquivo(url) if tipo == "prova" else "",
                                caderno=caderno_de(r["titulo"] + " " + url),
                            )
                        )
                    elif banca and url not in vistos_pag and banca != "FGV" and parecido(termo, r["titulo"] + " " + url) >= 0.5:
                        vistos_pag.add(url)
                        res.paginas_oficiais.append(ConcursoBanca(nome=r["titulo"], url=url, banca=banca))
                        try:
                            for a in self.arquivos_da_pagina(url, banca):
                                if a.url not in vistos_pdf:
                                    vistos_pdf.add(a.url)
                                    res.oficiais.append(a)
                        except ErroRede:
                            pass
                passo(0.3 + 0.3 * (i + 1) / len(consultas), "Procurando na internet…")
        except Exception as e:  # noqa: BLE001 - buscador fora do ar, sem internet
            from . import config

            config.registrar(f"central: busca na internet falhou para '{termo}': {type(e).__name__}: {e}")
            res.web_falhou = True

        # 3) PCI Concursos
        if incluir_pci:
            passo(0.7, "Procurando no PCI Concursos…")
            try:
                itens, _, _ = self.pci.buscar_provas(re.sub(r"\b20\d\d\b", "", termo).strip() or termo)
                ano = re.search(r"\b(20\d\d)\b", termo)
                if ano:
                    itens = sorted(itens, key=lambda i: i.ano != ano.group(1))
                res.pci = itens[:40]
            except ErroRede as e:
                # se outras fontes já trouxeram arquivos, um 404 no PCI é só ruído
                if not (res.oficiais or res.web):
                    res.avisos.append(f"PCI Concursos: {e}")
        if res.web_falhou and not res.total:
            res.avisos.append("Os buscadores da internet não responderam agora. Confira a conexão e tente de novo em alguns minutos.")
        passo(1, "Pronto")
        return res


# ---------------------------------------------------------------------------- organização


def agrupar_por_cargo(achados: list[Achado]) -> list[dict]:
    """Provas agrupadas por cargo, com os cadernos (tipos) e o melhor gabarito da mesma página."""
    grupos: dict[str, dict] = {}
    gabaritos = [a for a in achados if a.tipo == "gabarito"]
    for a in achados:
        if a.tipo != "prova":
            continue
        chave = norm(a.cargo or a.titulo) + "|" + a.pagina
        g = grupos.setdefault(chave, {"cargo": a.cargo or a.titulo, "fonte": a.fonte, "pagina": a.pagina, "cadernos": []})
        g["cadernos"].append(a)
    for g in grupos.values():
        g["cadernos"].sort(key=lambda a: (a.caderno or "9", a.url))
        mesma = [x for x in gabaritos if x.pagina == g["pagina"]] or gabaritos
        g["gabarito"] = melhor_gabarito(mesma)
    return sorted(grupos.values(), key=lambda g: g["cargo"])


def melhor_gabarito(gabaritos: list[Achado]) -> Achado | None:
    if not gabaritos:
        return None

    def nota(a: Achado):
        t = norm(a.titulo + " " + a.contexto + " " + a.url)
        return ("definitiv" in t, "objetiva" in t, "preliminar" not in t)

    return max(gabaritos, key=nota)


def baixar_pdf(pci: ClientePCI, url: str, destino: Path) -> Path:
    return pci.baixar(url, destino)
