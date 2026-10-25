"""Leitura de concursos e provas do PCI Concursos (pciconcursos.com.br).

O site não tem API pública de provas, então lemos o HTML das páginas. Cada
função tenta primeiro os seletores conhecidos e depois cai para uma leitura mais
genérica, para continuar funcionando se o layout mudar um pouco.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup, Tag

from . import config

BASE = "https://www.pciconcursos.com.br"

REGIOES = {
    "todas": ("Brasil todo", "/concursos/"),
    "nacional": ("Nacionais", "/concursos/nacional/"),
    "sudeste": ("Sudeste", "/concursos/sudeste/"),
    "sul": ("Sul", "/concursos/sul/"),
    "centrooeste": ("Centro-Oeste", "/concursos/centrooeste/"),
    "nordeste": ("Nordeste", "/concursos/nordeste/"),
    "norte": ("Norte", "/concursos/norte/"),
}

NOMES_UF = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARÁ": "CE", "DISTRITO FEDERAL": "DF", "ESPÍRITO SANTO": "ES", "GOIÁS": "GO",
    "MARANHÃO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARÁ": "PA", "PARAÍBA": "PB", "PARANÁ": "PR",
    "PERNAMBUCO": "PE", "PIAUÍ": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDÔNIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SÃO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO", "NACIONAL": "BR",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36 Aprova/1.0"
)


class ErroRede(Exception):
    """Falha ao acessar o site (sem internet, site fora do ar, bloqueio)."""


@dataclass
class Concurso:
    nome: str
    url: str
    uf: str = ""
    vagas: str = ""
    salario: str = ""
    cargos: str = ""
    nivel: str = ""
    prazo: str = ""
    prazo_fim: str | None = None  # ISO yyyy-mm-dd
    prazo_inicio: str | None = None
    titulo: str = ""  # título da notícia (mais descritivo)

    @property
    def dias_restantes(self) -> int | None:
        if not self.prazo_fim:
            return None
        return (date.fromisoformat(self.prazo_fim) - date.today()).days

    @property
    def inscricoes_futuras(self) -> bool:
        return bool(self.prazo_inicio and date.fromisoformat(self.prazo_inicio) > date.today())


@dataclass
class ProvaItem:
    cargo: str
    url: str
    ano: str = ""
    orgao: str = ""
    orgao_url: str = ""
    banca: str = ""
    banca_url: str = ""


@dataclass
class Arquivo:
    nome: str
    url: str | None = None

    @property
    def tipo(self) -> str:
        n = self.nome.lower()
        if "gab" in n or "resposta" in n:
            return "gabarito"
        if "edital" in n:
            return "edital"
        return "prova"


@dataclass
class Edital:
    titulo: str
    url: str
    descricao: str = ""
    data: str = ""
    paragrafos: list[str] = field(default_factory=list)
    pdfs: list[Arquivo] = field(default_factory=list)
    provas_url: str | None = None


# --------------------------------------------------------------------------
# utilidades de texto


def slugify(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")
    return t


def _limpo(texto: str | None) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


_DATA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def interpretar_prazo(texto: str) -> tuple[str | None, str | None]:
    """Converte '28/10 a 10/12/2026', '03 a 06/11/2026' ou 'Prorrogado até 13/10/2026'
    em (inicio_iso, fim_iso)."""
    texto = _limpo(texto)
    datas = list(_DATA.finditer(texto))
    if not datas:
        return None, None
    d, m, a = (int(x) for x in datas[-1].groups())
    try:
        fim = date(a, m, d)
    except ValueError:
        return None, None
    inicio = None
    if len(datas) >= 2:
        d0, m0, a0 = (int(x) for x in datas[0].groups())
        try:
            inicio = date(a0, m0, d0)
        except ValueError:
            inicio = None
    else:
        antes = texto[: datas[-1].start()]
        m1 = re.search(r"(\d{1,2})/(\d{1,2})\s*a\s*$", antes)
        m2 = re.search(r"(\d{1,2})\s*a\s*$", antes)
        try:
            if m1:
                d0, m0 = int(m1.group(1)), int(m1.group(2))
                inicio = date(a if m0 <= m else a - 1, m0, d0)
            elif m2:
                inicio = date(a, m, int(m2.group(1)))
        except ValueError:
            inicio = None
    return (inicio.isoformat() if inicio else None), fim.isoformat()


# --------------------------------------------------------------------------
# parsers (funções puras, testáveis com HTML salvo)


def _uf_da_entrada(el: Tag) -> str:
    cc = el.select_one("div.cc")
    if cc and _limpo(cc.get_text()):
        return _limpo(cc.get_text())[:3]
    ant = el.find_previous(class_=re.compile(r"^(ua|uf)$"))
    if ant:
        ident = (ant.get("id") or "").upper()
        if ident in NOMES_UF.values() or ident == "NACIONAL":
            return "BR" if ident == "NACIONAL" else ident
        return NOMES_UF.get(_limpo(ant.get_text()).upper(), "")
    return ""


def _concurso_de_elemento(el: Tag) -> Concurso | None:
    link = el.select_one("div.ca a[href]") or el.find("a", href=re.compile(r"/noticias/"))
    if not link:
        return None
    nome = _limpo(link.get_text())
    if not nome:
        return None
    url = urljoin(BASE, link["href"])
    vagas = salario = cargos = nivel = ""
    cd = el.select_one("div.cd")
    if cd:
        partes = [_limpo(s) for s in cd.stripped_strings if _limpo(s)]
        if partes:
            primeira = partes[0]
            m = re.match(r"^(.*?)\s*(até\s+R\$.*)$", primeira, flags=re.I)
            if m:
                vagas, salario = m.group(1).strip(), m.group(2).strip()
            elif "R$" in primeira and not re.search(r"vaga|reserva|CR", primeira, re.I):
                salario = primeira
            else:
                vagas = primeira
        if len(partes) >= 2:
            cargos = partes[1]
        if len(partes) >= 3:
            nivel = partes[-1]
    ce = el.select_one("div.ce")
    prazo = _limpo(ce.get_text(" ")) if ce else ""
    inicio, fim = interpretar_prazo(prazo)
    return Concurso(
        nome=nome,
        url=url,
        uf=_uf_da_entrada(el),
        vagas=vagas,
        salario=salario,
        cargos=cargos,
        nivel=nivel,
        prazo=prazo,
        prazo_inicio=inicio,
        prazo_fim=fim,
        titulo=_limpo(link.get("title")),
    )


def parse_concursos(html: str) -> list[Concurso]:
    """Lista de concursos (abertos: div.na/div.da; realizados: div.ea)."""
    soup = BeautifulSoup(html, "html.parser")
    itens: list[Concurso] = []
    vistos: set[str] = set()
    for el in soup.select("div.na, div.da, div.ea"):
        c = _concurso_de_elemento(el)
        if c and c.url not in vistos:
            vistos.add(c.url)
            itens.append(c)
    if itens:
        return itens
    # Plano B: qualquer bloco com div.ca (layout parecido, classes diferentes)
    for ca in soup.select("div.ca"):
        c = _concurso_de_elemento(ca.parent or ca)
        if c and c.url not in vistos:
            vistos.add(c.url)
            itens.append(c)
    return itens


def parse_edital(html: str, url: str) -> Edital:
    soup = BeautifulSoup(html, "html.parser")
    art = soup.select_one("article#noticia") or soup.find("article") or soup
    h1 = art.select_one('h1[itemprop="headline"]') or art.find("h1") or soup.find("h1")
    titulo = _limpo(h1.get_text()) if h1 else ""
    desc = art.select_one("div.description")
    pub = art.select_one("abbr.published")
    data = ""
    if pub and pub.get("title"):
        p = pub["title"][:10].split("-")
        data = "/".join(reversed(p)) if len(p) == 3 else pub["title"]
    corpo = art.select_one('div[itemprop="articleBody"]') or art
    paragrafos: list[str] = []
    for no in corpo.find_all(["p", "li", "h2", "h3"]):
        t = _limpo(no.get_text(" "))
        if t and len(t) > 2 and t not in paragrafos:
            paragrafos.append(t)
    pdfs: list[Arquivo] = []
    for a in soup.select("aside#links li.pdf a[href]"):
        pdfs.append(Arquivo(_limpo(a.get_text()) or "Arquivo PDF", urljoin(BASE, a["href"])))
    if not pdfs:
        for a in soup.find_all("a", href=re.compile(r"\.pdf($|\?)", re.I)):
            pdfs.append(Arquivo(_limpo(a.get_text()) or a["href"].rsplit("/", 1)[-1], urljoin(BASE, a["href"])))
    provas = soup.select_one("aside#links li.li_provas a[href]")
    provas_url = urljoin(BASE, provas["href"]) if provas else None
    if not provas_url:
        cand = soup.find("a", href=re.compile(r"/provas/[a-z0-9-]+/?$"), string=re.compile("prova", re.I))
        provas_url = urljoin(BASE, cand["href"]) if cand else None
    return Edital(
        titulo=titulo,
        url=url,
        descricao=_limpo(desc.get_text(" ")) if desc else "",
        data=data,
        paragrafos=paragrafos[:60],
        pdfs=pdfs,
        provas_url=provas_url,
    )


def parse_lista_provas(html: str) -> tuple[list[ProvaItem], int]:
    """Tabela de /provas/<slug>. Devolve (itens, total_de_paginas)."""
    soup = BeautifulSoup(html, "html.parser")
    itens: list[ProvaItem] = []
    vistos: set[str] = set()
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        a = tds[0].find("a", href=re.compile(r"/provas/download/"))
        if not a:
            continue
        url = urljoin(BASE, a["href"])
        if url in vistos:
            continue
        vistos.add(url)
        cargo = _limpo("".join(t for t in a.find_all(string=True, recursive=False))) or _limpo(a.get_text())
        item = ProvaItem(cargo=cargo, url=url)
        if len(tds) > 1:
            item.ano = _limpo(tds[1].get_text())
        if len(tds) > 2:
            item.orgao = _limpo(tds[2].get_text())
            ao = tds[2].find("a", href=True)
            item.orgao_url = urljoin(BASE, ao["href"]) if ao else ""
        if len(tds) > 3:
            item.banca = _limpo(tds[3].get_text())
            ab = tds[3].find("a", href=True)
            item.banca_url = urljoin(BASE, ab["href"]) if ab else ""
        itens.append(item)
    if not itens:
        for a in soup.select("a.prova_download[href], a[href*='/provas/download/']"):
            url = urljoin(BASE, a["href"])
            if url not in vistos:
                vistos.add(url)
                itens.append(ProvaItem(cargo=_limpo(a.get_text()), url=url))
    paginas = 1
    m = re.search(r"Mostrando p[áa]gina\s*(\d+)\s*de\s*(\d+)", soup.get_text(" "), re.I)
    if m:
        paginas = int(m.group(2))
    return itens, paginas


_PDF_URL = re.compile(r"""https?://[^\s"'<>]+?\.pdf(?:\?[^\s"'<>]*)?""", re.I)


def parse_arquivos_prova(html: str) -> tuple[list[Arquivo], bool]:
    """Arquivos da página /provas/download/... Devolve (arquivos, precisa_navegador).

    O site pode exigir uma verificação de segurança antes de liberar os links.
    Nesse caso devolvemos os nomes dos arquivos sem URL e precisa_navegador=True.
    """
    soup = BeautifulSoup(html, "html.parser")
    arquivos: list[Arquivo] = []
    vistos: set[str] = set()

    def add(nome: str, url: str | None):
        nome = nome.strip()
        chave = url or nome
        if nome and chave not in vistos:
            vistos.add(chave)
            arquivos.append(Arquivo(nome, url))

    for a in soup.select("div#download a[href]"):
        href = a["href"]
        texto = _limpo(a.get_text())
        if re.search(r"\.pdf", href, re.I) and not texto.lower().startswith(("ver ", "compartilhar")):
            add(re.sub(r"^Baixar\s+", "", texto, flags=re.I) or href.rsplit("/", 1)[-1], urljoin(BASE, href))
    if not arquivos:
        for a in soup.find_all("a", href=_PDF_URL):
            add(a["href"].rsplit("/", 1)[-1].split("?")[0], a["href"])
    if not arquivos:
        for attr in ("data-href", "data-url", "data-file", "data-src"):
            for el in soup.find_all(attrs={attr: re.compile(r"\.pdf", re.I)}):
                add(el[attr].rsplit("/", 1)[-1].split("?")[0], urljoin(BASE, el[attr]))
    if arquivos:
        return arquivos, False
    # Sem links: pega os nomes dos arquivos citados ("Baixar prova.pdf")
    texto = soup.get_text("\n")
    for m in re.finditer(r"Baixar\s+([^\n]+?\.pdf)", texto, re.I):
        add(m.group(1), None)
    if not arquivos:
        for m in re.finditer(r"([\w\-. ]+\.pdf)", texto, re.I):
            add(m.group(1), None)
    return arquivos, True


# --------------------------------------------------------------------------
# cliente HTTP com cache e intervalo mínimo entre requisições


class ClientePCI:
    def __init__(self, cache_dir: Path = config.CACHE_DIR, fixtures: str | None = config.FIXTURES_DIR):
        self.cache_dir = cache_dir
        self.fixtures = Path(fixtures) if fixtures else None
        self.sessao = requests.Session()
        self.sessao.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
        })
        self._lock = threading.Lock()
        self._ultimo = 0.0

    # ---- baixo nível

    def _espera(self):
        with self._lock:
            falta = 0.8 - (time.monotonic() - self._ultimo)
            if falta > 0:
                time.sleep(falta)
            self._ultimo = time.monotonic()

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    def _fixture(self, url: str) -> str | None:
        if not self.fixtures:
            return None
        nome = slugify(url.replace(BASE, "")) or "index"
        p = self.fixtures / f"{nome}.html"
        if p.exists():
            return p.read_text(encoding="utf-8")
        raise ErroRede(f"Sem fixture para {url} ({p.name})")

    def html(self, url: str, ttl_horas: float = 6) -> str:
        fx = self._fixture(url)
        if fx is not None:
            return fx
        cp = self._cache_path(url)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < ttl_horas * 3600:
            return cp.read_text(encoding="utf-8")
        self._espera()
        try:
            r = self.sessao.get(url, timeout=25)
            r.raise_for_status()
        except requests.RequestException as e:
            if cp.exists():  # sem internet: usa a última cópia salva
                return cp.read_text(encoding="utf-8")
            raise ErroRede(_mensagem_erro(e)) from e
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        texto = r.text
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cp.write_text(texto, encoding="utf-8")
        except OSError:
            pass
        return texto

    def baixar(self, url: str, destino: Path, progresso=None) -> Path:
        if self.fixtures:
            mapa = self.fixtures / "downloads.json"
            if mapa.exists():
                arquivo = json.loads(mapa.read_text(encoding="utf-8")).get(url.rsplit("/", 1)[-1])
                if arquivo:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes((self.fixtures / arquivo).read_bytes())
                    return destino
            raise ErroRede(f"Sem fixture de download para {url}")
        self._espera()
        try:
            with self.sessao.get(url, timeout=60, stream=True, headers={"Referer": BASE + "/provas/"}) as r:
                r.raise_for_status()
                tipo = r.headers.get("Content-Type", "")
                total = int(r.headers.get("Content-Length") or 0)
                destino.parent.mkdir(parents=True, exist_ok=True)
                feito = 0
                with open(destino, "wb") as f:
                    for bloco in r.iter_content(64 * 1024):
                        f.write(bloco)
                        feito += len(bloco)
                        if progresso and total:
                            progresso(feito / total)
        except requests.RequestException as e:
            raise ErroRede(_mensagem_erro(e)) from e
        with open(destino, "rb") as f:
            inicio = f.read(5)
        if inicio != b"%PDF-":
            destino.unlink(missing_ok=True)
            raise ErroRede(
                "O site devolveu uma página em vez do PDF (provavelmente pediu verificação "
                f"de segurança). Tipo recebido: {tipo or 'desconhecido'}."
            )
        return destino

    # ---- alto nível

    def concursos_abertos(self, regiao: str = "todas") -> list[Concurso]:
        caminho = REGIOES.get(regiao, REGIOES["todas"])[1]
        return parse_concursos(self.html(BASE + caminho, ttl_horas=6))

    def concursos_realizados(self, busca: str) -> list[Concurso]:
        url = f"{BASE}/pesquisa/?p={quote_plus(busca)}&tipopesquisa=1"
        return parse_concursos(self.html(url, ttl_horas=24))

    def edital(self, url: str) -> Edital:
        return parse_edital(self.html(url, ttl_horas=24), url)

    def provas(self, url_ou_slug: str, pagina: int = 1) -> tuple[list[ProvaItem], int]:
        if url_ou_slug.startswith("http"):
            url = url_ou_slug.rstrip("/")
        else:
            url = f"{BASE}/provas/{url_ou_slug.strip('/')}"
        if pagina > 1:
            url = f"{url}/{pagina}"
        return parse_lista_provas(self.html(url, ttl_horas=72))

    def buscar_provas(self, termo: str, pagina: int = 1) -> tuple[list[ProvaItem], int, str]:
        """Procura provas por cargo, órgão ou banca. Devolve (itens, paginas, slug_usado)."""
        base = slugify(termo)
        if not base:
            return [], 0, ""
        tentativas = [f"{base}-abrangente", base]
        # órgãos costumam vir com UF no fim: "tj sp" -> "tj-sp"; prefeituras: "pref-..."
        if not base.startswith("pref-") and base.startswith("prefeitura-"):
            tentativas.append("pref-" + base[len("prefeitura-"):])
        erros = []
        for slug in tentativas:
            try:
                itens, paginas = self.provas(slug, pagina)
            except ErroRede as e:
                erros.append(str(e))
                continue
            if itens:
                return itens, paginas, slug
        if erros and len(erros) == len(tentativas):
            raise ErroRede(erros[0])
        return [], 0, ""

    def arquivos_prova(self, url_download: str) -> tuple[list[Arquivo], bool]:
        return parse_arquivos_prova(self.html(url_download, ttl_horas=24))


def _mensagem_erro(e: Exception) -> str:
    if isinstance(e, requests.ConnectionError):
        return "Sem conexão com o site. Confira sua internet e tente de novo."
    if isinstance(e, requests.Timeout):
        return "O site demorou demais para responder. Tente de novo em instantes."
    if isinstance(e, requests.HTTPError) and e.response is not None:
        code = e.response.status_code
        if code == 404:
            return "Página não encontrada no site."
        if code in (403, 429):
            return "O site recusou o acesso agora (muitas consultas seguidas). Espere um pouco e tente de novo."
        return f"O site respondeu com erro {code}."
    return f"Falha ao acessar o site: {e}"


def concurso_para_dict(c: Concurso) -> dict:
    return asdict(c)


def concurso_de_dict(d: dict) -> Concurso:
    campos = {k: d.get(k) for k in Concurso.__dataclass_fields__}
    return Concurso(**{k: (v if v is not None or k in ("prazo_fim", "prazo_inicio") else "") for k, v in campos.items()})


def salvar_json(caminho: Path, dados) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
