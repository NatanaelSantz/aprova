"""Gera páginas HTML e PDFs de exemplo para testar o app sem internet.

As páginas imitam a estrutura do PCI Concursos (classes na/ua/ca/cc/cd/ce,
tabela de provas e página de download) com dados reais de outubro/2026.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
FIX = AQUI / "fixtures"

CONCURSOS = [
    ("SP", "TJSP - Tribunal de Justiça do Estado de São Paulo", "tjsp-abre-concursos-para-oficial-de-justica-e-escrevente-tecnico-judiciario", "132 vagas até R$ 9.856,95", "Oficial de Justiça, Escrevente Técnico Judiciário", "Médio / Superior", "28/10 a<br>10/12/2026"),
    ("SP", "Câmara de Boituva", "camara-de-boituva-sp-abre-concursos-com-salarios-de-ate-8595", "7 vagas até R$ 8.595,15", "Vários Cargos", "Fundamental / Médio / Técnico / Superior", "09/11/2026"),
    ("SP", "Prefeitura de Matão", "prefeitura-de-matao-sp-abre-concurso-publico-com-salarios-de-ate-17433", "44 vagas até R$ 17.433,24", "Vários Cargos", "Fundamental / Médio / Superior", "29/10/2026"),
    ("SP", "SEFAZ - Secretaria da Fazenda e Planejamento", "sefaz-sp-abre-concurso-publico-para-analista-em-planejamento-orcamento-e-financas-publicas", "60 vagas até R$ 11.359,50", "Analista em Planejamento, Orçamento e Finanças Públicas", "Superior", "03/11/2026"),
    ("SP", "DETRAN - Departamento Estadual de Trânsito de São Paulo", "detran-sp-prorroga-inscricoes-do-concurso-com-145-vagas-para-agentes-estaduais-de-transito", "145 vagas até R$ 5.702,18", "Agente Estadual de Trânsito", "Superior", "Prorrogado até<br>13/11/2026"),
    ("SP", "Prefeitura de Itapecerica da Serra", "prefeitura-de-itapecerica-da-serra-sp-abre-concurso-para-motorista-de-caminhao", "1 vaga até R$ 2.755,86", "Motorista de Caminhão", "Ensino Médio", "26/10/2026"),
    ("SP", "USP - Universidade de São Paulo", "usp-sp-abre-10-novos-concursos-publicos-para-diversos-cargos", "10 vagas até R$ 11.778,84", "Vários Cargos", "Médio / Superior", "01/12/2026 a<br>07/01/2027"),
    ("RJ", "Prefeitura de São Gonçalo", "prefeitura-de-sao-goncalo-rj-abre-concursos-para-guardas-municipais", "101 vagas até R$ 4.535,54", "Guarda Municipal Nível II, Guarda Municipal Nível III - Psicólogo", "Médio / Superior", "18/11/2026"),
    ("RJ", "CREMERJ - Conselho Regional de Medicina do Rio de Janeiro", "cremerj-retifica-concurso-com-salarios-de-ate-18000-para-diversos-cargos", "26 vagas até R$ 18.000,00", "Vários Cargos", "Médio / Técnico / Superior", "Prorrogado até<br>29/10/2026"),
    ("MG", "PMMG - Polícia Militar de Minas Gerais", "pmmg-abre-concurso-com-90-vagas-para-o-curso-de-formacao-de-oficiais", "90 vagas até R$ 12.170,61", "Cadete do Curso de Formação de Oficiais", "Superior", "10/11 a<br>10/12/2026"),
    ("MG", "Prefeitura de Contagem", "prefeitura-de-contagem-mg-retifica-edital-de-concurso-publico", "272 vagas até R$ 13.305,57", "Vários Cargos", "Médio / Técnico / Superior", "17/11/2026"),
    ("MG", "EMATER - Empresa de Assistência Técnica e Extensão Rural", "emater-mg-anuncia-retificacao-de-concurso-publico-com-salarios-de-ate-7321", "120 vagas até R$ 7.321,75", "Vários Cargos", "Médio / Técnico / Superior", "30/10/2026"),
]

NOMES_UF = {"SP": "SÃO PAULO", "RJ": "RIO DE JANEIRO", "MG": "MINAS GERAIS"}


def html_concursos(itens, classe="na") -> str:
    partes = ['<html><body><div id="concursos"><h1>Concursos Abertos - Sudeste</h1>']
    uf_atual = None
    for uf, nome, slug, vagas, cargos, nivel, prazo in itens:
        if uf != uf_atual and classe != "ea":
            partes.append(f'<div class="ua" id="{uf}"><div class="uf">{NOMES_UF.get(uf, uf)}</div></div>')
            uf_atual = uf
        partes.append(
            f'<div class="{classe}" data-url="x"><div class="ca"><a href="https://www.pciconcursos.com.br/noticias/{slug}" '
            f'title="{nome} abre concurso">{nome}</a></div><div class="cc">{uf}</div>'
            f'<div class="cd">{vagas}<br><span>{cargos}<br><span>{nivel}</span></span></div>'
            f'<div class="ce"><span>{prazo}</span></div></div>'
        )
    partes.append("</div></body></html>")
    return "".join(partes)


EDITAL = """<html><body><article id="noticia"><h1 itemprop="headline">TJSP abre concursos para Oficial de Justiça e Escrevente Técnico Judiciário</h1>
<div class="description">O Tribunal de Justiça do Estado de São Paulo publicou editais com 132 vagas.</div>
<abbr class="published" title="2026-10-20T10:00:00-03:00">20/10/2026</abbr>
<div itemprop="articleBody"><p>O Tribunal de Justiça do Estado de São Paulo (TJSP) anuncia a abertura de concursos públicos para Oficial de Justiça e Escrevente Técnico Judiciário.</p>
<h2>Inscrições</h2><p>As inscrições ficam abertas de 28 de outubro a 10 de dezembro de 2026, pela internet.</p>
<h2>Provas</h2><p>A prova objetiva terá questões de Língua Portuguesa, Conhecimentos em Direito, Matemática, Informática e Raciocínio Lógico.</p></div>
</article><aside id="links"><ul><li class="pdf"><a href="https://arquivos.pciconcursos.com.br/edital-tjsp-2026.pdf">Edital de abertura</a></li>
<li class="li_provas"><a href="https://www.pciconcursos.com.br/provas/tj-sp">Provas anteriores do TJ-SP</a></li></ul></aside></body></html>"""

PROVAS = [
    ("escrevente-tecnico-judiciario-tj-sp-vunesp-2023", "Escrevente Técnico Judiciário", "2023", "TJ/SP", "tj-sp", "VUNESP", "vunesp"),
    ("escrevente-tecnico-judiciario-tj-sp-vunesp-2021", "Escrevente Técnico Judiciário", "2021", "TJ/SP", "tj-sp", "VUNESP", "vunesp"),
    ("oficial-de-justica-tj-sp-vunesp-2023", "Oficial de Justiça", "2023", "TJ/SP", "tj-sp", "VUNESP", "vunesp"),
    ("analista-de-sistemas-tj-sp-vunesp-2019", "Analista de Sistemas", "2019", "TJ/SP", "tj-sp", "VUNESP", "vunesp"),
    ("assistente-social-judiciario-tj-sp-vunesp-2018", "Assistente Social Judiciário", "2018", "TJ/SP", "tj-sp", "VUNESP", "vunesp"),
]


def html_provas() -> str:
    linhas = "".join(
        f'<tr><td><a class="prova_download" href="https://www.pciconcursos.com.br/provas/download/{slug}">{cargo}</a></td>'
        f'<td>{ano}</td><td><a href="https://www.pciconcursos.com.br/provas/{os}">{org}</a></td>'
        f'<td><a href="https://www.pciconcursos.com.br/provas/{bs}">{banca}</a></td></tr>'
        for slug, cargo, ano, org, os, banca, bs in PROVAS
    )
    return (
        "<html><body><h1>Provas para Download</h1><table id='lista_provas'><tr><th>Prova</th><th>Ano</th><th>Órgão</th><th>Organizadora</th></tr>"
        f"{linhas}</table><div>Mostrando página <b>1</b> de <b>1</b></div></body></html>"
    )


DOWNLOAD_BLOQUEADO = """<html><body><h5>Prova Escrevente Técnico Judiciário - TJ/SP</h5>
<h5>Verificação de segurança</h5><p>Complete a verificação abaixo para acessar os arquivos desta página.</p>
<div id="download"><a class="item-link">Ver escrevente-tj-sp-2023.pdf</a><a class="item-link">Baixar escrevente-tj-sp-2023.pdf</a>
<a class="item-link">Baixar gabaritos.pdf</a></div></body></html>"""


def pdf_prova(destino: Path):
    """Prova de exemplo em duas colunas, com cabeçalho repetido e marca d'água do PCI."""
    doc = pymupdf.open()
    questoes = [
        ("LÍNGUA PORTUGUESA", None),
        (None, ("Leia o texto para responder às questões 1 a 3.",)),
        (None, ("A leitura diária de jornais amplia o vocabulário e melhora a interpretação de textos, habilidades essenciais em qualquer prova de concurso público. Quem lê com frequência reconhece mais rapidamente o sentido das palavras no contexto.",)),
    ]
    itens = [
        ("1", "De acordo com o texto, a leitura de jornais:", ["reduz a capacidade de interpretação.", "amplia o vocabulário do leitor.", "é dispensável para concursos.", "dificulta o reconhecimento de palavras.", "substitui o estudo de gramática."]),
        ("2", "No trecho 'reconhece mais rapidamente o sentido', a palavra 'rapidamente' expressa circunstância de:", ["lugar.", "intensidade.", "modo.", "tempo.", "causa."]),
        ("3", "A palavra 'essenciais' pode ser substituída, sem prejuízo de sentido, por:", ["fundamentais.", "secundárias.", "opcionais.", "raras.", "ocasionais."]),
        ("NOÇÕES DE INFORMÁTICA", None, None),
        ("4", "No Microsoft Word, o atalho Ctrl + B, na versão em português, é usado para:", ["salvar o documento.", "aplicar negrito.", "abrir um arquivo.", "imprimir.", "fechar o programa."]),
        ("5", "Um programa que bloqueia conexões não autorizadas entre o computador e a rede é o:", ["navegador.", "editor de texto.", "firewall.", "compactador.", "leitor de PDF."]),
        ("RACIOCÍNIO LÓGICO", None, None),
        ("6", "Se todo A é B e nenhum B é C, então é correto afirmar que:", ["algum A é C.", "todo C é A.", "nenhum A é C.", "todo B é A.", "algum C é B."]),
        ("7", "Qual é o próximo número da sequência 3, 7, 15, 31, ...?", ["47", "62", "63", "64", "60"]),
        ("8", "A negação de 'Pedro estuda e trabalha' é:", ["Pedro não estuda e não trabalha.", "Pedro não estuda ou não trabalha.", "Pedro estuda ou trabalha.", "Pedro não estuda e trabalha.", "Pedro estuda e não trabalha."]),
    ]
    W, H = 595, 842
    page = doc.new_page(width=W, height=H)
    y = {"esq": 90, "dir": 90}
    coluna = "esq"
    larg = (W - 90) / 2

    def cabecalho(pg):
        pg.insert_text((45, 40), "CONCURSO PÚBLICO – TRIBUNAL DE EXEMPLO – ESCREVENTE", fontsize=8, fontname="helv")
        pg.insert_text((45, 820), "pcimarkpci MDAwMDowMDAwOjAwMDA=:VGVzdGU=", fontsize=5, fontname="helv")
        pg.insert_text((45, 830), "www.pciconcursos.com.br", fontsize=5, fontname="helv")

    cabecalho(page)

    def escrever(texto, tamanho=9.5, negrito=False):
        nonlocal page, coluna
        x0 = 45 if coluna == "esq" else 45 + larg + 10
        rect = pymupdf.Rect(x0, y[coluna], x0 + larg - 5, y[coluna] + 400)
        fonte = "hebo" if negrito else "helv"
        sobra = page.insert_textbox(rect, texto, fontsize=tamanho, fontname=fonte)
        usado = 400 - sobra
        if y[coluna] + usado > H - 70:
            # não coube: desfaz desenhando de novo na próxima coluna/página
            page.add_redact_annot(rect)
            page.apply_redactions()
            if coluna == "esq":
                coluna = "dir"
            else:
                page = doc.new_page(width=W, height=H)
                cabecalho(page)
                coluna = "esq"
                y["esq"] = y["dir"] = 90
            return escrever(texto, tamanho, negrito)
        y[coluna] += usado + 6

    escrever("LÍNGUA PORTUGUESA", 10.5, True)
    escrever("Leia o texto para responder às questões de 1 a 3.", 9)
    escrever(questoes[2][1][0], 9)
    for num, enun, alts in itens:
        if enun is None:
            escrever(num, 10.5, True)
            continue
        escrever(num, 10, True)
        escrever(enun)
        for letra, alt in zip("ABCDE", alts):
            escrever(f"({letra}) {alt}")
    doc.save(destino)


def pdf_gabarito(destino: Path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), "GABARITO DEFINITIVO", fontsize=14, fontname="hebo")
    page.insert_text((50, 90), "Cargo: Analista de Sistemas", fontsize=10)
    page.insert_text((50, 110), "01 02 03 04 05 06 07 08", fontsize=10)
    page.insert_text((50, 125), "A  D  B  E  C  A  B  D", fontsize=10)
    page.insert_text((50, 170), "Cargo: Escrevente Técnico Judiciário", fontsize=10)
    page.insert_text((50, 190), "01 02 03 04 05 06 07 08", fontsize=10)
    page.insert_text((50, 205), "B  C  A  B  C  C  C  B", fontsize=10)
    doc.save(destino)


BUSCA = [
    {"titulo": "Advérbio: o que é, tipos e exemplos - Brasil Escola", "url": "https://brasilescola.uol.com.br/gramatica/adverbio.htm", "trecho": "Advérbio é a palavra que modifica o verbo, o adjetivo ou outro advérbio. Os advérbios de modo indicam a maneira como a ação acontece, como rapidamente, devagar e bem."},
    {"titulo": "Advérbios de modo terminados em -mente - Toda Matéria", "url": "https://www.todamateria.com.br/adverbios-de-modo/", "trecho": "Grande parte dos advérbios de modo é formada pelo acréscimo do sufixo -mente a adjetivos, como rápido + mente. Eles expressam a circunstância de modo da ação verbal."},
    {"titulo": "Questões de advérbio para concursos", "url": "https://www.qconcursos.com/questoes-de-concursos/disciplinas/letras-portugues/adverbios", "trecho": "Resolva questões de concursos sobre advérbios e locuções adverbiais com gabarito comentado."},
]


def main():
    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / "concursos-sudeste.html").write_text(html_concursos(CONCURSOS), encoding="utf-8")
    (FIX / "concursos.html").write_text(html_concursos(CONCURSOS), encoding="utf-8")
    (FIX / "pesquisa-p-tj-tipopesquisa-1.html").write_text(
        html_concursos(
            [("SP", "TJ/SP - Tribunal de Justiça", "tj-sp-2023-escrevente", "400 vagas até R$ 6.043,20", "Escrevente Técnico Judiciário", "Médio", "03/2023"),
             ("BA", "TJ/BA - Tribunal de Justiça da Bahia", "tj-ba-2024", "100 vagas até R$ 5.000,00", "Técnico Judiciário", "Médio", "11/2024")],
            classe="ea",
        ),
        encoding="utf-8",
    )
    (FIX / "noticias-tjsp-abre-concursos-para-oficial-de-justica-e-escrevente-tecnico-judiciario.html").write_text(EDITAL, encoding="utf-8")
    (FIX / "provas-tj-sp.html").write_text(html_provas(), encoding="utf-8")
    (FIX / "provas-escrevente-abrangente.html").write_text(html_provas(), encoding="utf-8")
    for p in PROVAS:
        (FIX / f"provas-download-{p[0]}.html").write_text(DOWNLOAD_BLOQUEADO, encoding="utf-8")
    (FIX / "busca.json").write_text(json.dumps(BUSCA, ensure_ascii=False, indent=1), encoding="utf-8")
    pdf_prova(FIX / "escrevente-tj-sp-2023.pdf")
    pdf_gabarito(FIX / "gabaritos.pdf")
    print("fixtures em", FIX)


# ----------------------------------------------------------------------------- FGV (site oficial)

FGV_LISTA = """<html><body><h2>Acesso aos concursos em andamento</h2><ul>
<li><a href="/concursos/dataprev26">Concurso Público para a Empresa de Tecnologia e Informações da Previdência - DATAPREV</a></li>
<li><a href="/concursos/tjpb26">Concurso Público para Tribunal de Justiça do Estado da Paraíba</a></li>
<li><a href="https://conhecimento.fgv.br/cpnu2">Concurso Público Nacional Unificado 2</a></li>
</ul><h2>Acesso aos concursos realizados</h2><ul>
<li><a href="/concursos/dataprev23">Concurso Público DATAPREV 2023</a></li>
<li><a href="/concursos/tjsc24">Concurso Público TJ Santa Catarina 2024</a></li>
</ul><a href="/concursos?page=1">2</a></body></html>"""

ARQ = "https://conhecimento.fgv.br/sites/default/files/concursos/"
FGV_DATAPREV = f"""<html><body><h1>DATAPREV 2026</h1><h2>Arquivos do concurso</h2>
<div class="item"><span>13/10/2026</span><strong>Prova Objetiva</strong><ul>
<li><p><strong>ANALISTA DE PROCESSAMENTO</strong></p><a href="{ARQ}analista-de-processamento-cns013-tipo-1.pdf">Tipo 1</a></li>
<li><p><strong>DESENVOLVIMENTO DE SOFTWARE</strong></p><a href="{ARQ}analista-de-tecnologia-da-informacao-desenvolvimento-de-software-cns003-tipo-1.pdf">Tipo 1</a>
<a href="{ARQ}analista-de-tecnologia-da-informacao-desenvolvimento-de-software-cns003-tipo-2.pdf">Tipo 2</a></li>
</ul></div>
<div class="item"><span>13/10/2026</span><a href="{ARQ}dataprev2026-gabaritos-para-publicacao.pdf">Gabarito Oficial Preliminar da Prova Objetiva</a></div>
<div class="item"><span>03/07/2026</span><a href="{ARQ}edital-retificado-dataprev.pdf">Edital (retificado em 29/07/2026)</a></div>
<div class="item"><span>03/09/2026</span><a href="{ARQ}resultado-definitivo-de-negros.pdf">Resultado definitivo de homologação de inscrição nas vagas destinadas aos candidatos negros</a></div>
<div class="item"><a href="https://conhecimento.fgv.br/sites/default/files/2026.01.16-termos-de-uso-fgv-conhecimento.pdf">Termos de Uso</a></div>
</body></html>"""

FGV_DATAPREV23 = f"""<html><body><h1>DATAPREV 2023</h1><h2>Arquivos do concurso</h2>
<div class="item"><strong>Prova Objetiva</strong><ul>
<li><p><strong>DESENVOLVIMENTO DE SOFTWARE</strong></p><a href="{ARQ}dp23-desenvolvimento-de-software-tipo-1.pdf">Tipo 1</a>
<a href="{ARQ}dp23-desenvolvimento-de-software-tipo-2.pdf">Tipo 2</a></li>
<li><p><strong>ANALISTA DE INFRAESTRUTURA</strong></p><a href="{ARQ}dp23-infraestrutura-tipo-1.pdf">Tipo 1</a></li>
</ul></div>
<div class="item"><a href="{ARQ}dp23-gabaritos-definitivos.pdf">Gabaritos Definitivos</a></div>
</body></html>"""

BUSCA_DATAPREV = [
    {"titulo": "Prova Dataprev 2026 comentada - Desenvolvimento de Software", "url": "https://www.exemplocursos.com.br/arquivos/dataprev-2026-prova-comentada-ti.pdf", "trecho": "Prova comentada"},
    {"titulo": "Gabarito Dataprev 2026 FGV", "url": "https://conhecimento.fgv.br/sites/default/files/concursos/dataprev2026-gabaritos-para-publicacao.pdf", "trecho": "Gabarito oficial"},
    {"titulo": "Dataprev 2026: veja a prova", "url": "https://noticias.exemplo.com.br/dataprev-prova", "trecho": "notícia"},
]


ITENS_2023 = [
    ("Língua Portuguesa", None, None),
    ("1", "Assinale a opção em que o acento grave foi usado corretamente.", ["Fui à pé.", "Entreguei à ela.", "Cheguei à escola.", "Voltei à casa de carro, e.", "Comecei à estudar."]),
    ("2", "O plural de 'cidadão' é:", ["cidadões", "cidadãos", "cidadães", "cidadans", "cidadãoes"]),
    ("Língua Inglesa", None, None),
    ("3", "The opposite of 'cheap' is:", ["low", "expensive", "small", "easy", "free"]),
    ("Raciocínio lógico-matemático", None, None),
    ("4", "Quanto é 15% de 200?", ["15", "20", "30", "35", "40"]),
    ("Conhecimentos Específicos", None, None),
    ("5", "Em SQL, o comando que remove linhas de uma tabela é:", ["DROP", "DELETE", "ALTER", "REMOVE", "CLEAR"]),
    ("6", "Em Git, o comando que cria um novo ramo é:", ["git init", "git branch", "git push", "git stash", "git clone"]),
]


def pdf_fgv(destino: Path, itens=None):
    """Prova no layout da FGV: capa, duas colunas, números soltos, títulos em caixa mista e rodapé com PÁGINA."""
    doc = pymupdf.open()
    W, H = 595, 842
    capa = doc.new_page(width=W, height=H)
    capa.insert_text((60, 80), "CONCURSO PÚBLICO DA EMPRESA DE EXEMPLO", fontsize=12, fontname="hebo")
    capa.insert_text((60, 110), "SUA PROVA", fontsize=11, fontname="hebo")
    capa.insert_textbox(pymupdf.Rect(60, 120, 540, 200), "As questões objetivas têm 5 (cinco) opções de resposta (A, B, C, D e E) e somente uma delas está correta. Você receberá 8 (oito) questões objetivas.", fontsize=10)
    itens = itens or [
        ("Conhecimentos Gerais", None, None),
        ("Língua Portuguesa", None, None),
        ("1", "Assinale a frase em que a vírgula foi empregada corretamente.", ["Os alunos, estudaram.", "Ontem, choveu muito.", "Ele disse, que viria.", "A casa, é azul.", "Maria, saiu cedo hoje, e."]),
        ("2", "O antônimo de 'efêmero' é:", ["passageiro", "duradouro", "breve", "rápido", "fugaz"]),
        ("Língua Inglesa", None, None),
        ("3", "In the sentence 'She has lived here since 2010', the verb tense is:", ["simple past", "present perfect", "past perfect", "future", "present continuous"]),
        ("4", "The word 'however' expresses:", ["addition", "contrast", "cause", "time", "example"]),
        ("Raciocínio lógico-matemático", None, None),
        ("5", "Se 3 canetas custam R$ 12,00, quanto custam 5 canetas?", ["R$ 15,00", "R$ 18,00", "R$ 20,00", "R$ 22,00", "R$ 24,00"]),
        ("Legislação Acerca de Segurança da Informação e Proteção de Dados", None, None),
        ("6", "Segundo a LGPD, quem decide sobre o tratamento de dados pessoais é o:", ["operador", "controlador", "titular", "encarregado", "auditor"]),
        ("Conhecimentos Específicos", None, None),
        ("7", "Em Java, a palavra-chave usada para herança de classes é:", ["implements", "extends", "inherits", "super", "this"]),
        ("8", "O verbo HTTP mais adequado para atualizar parcialmente um recurso é:", ["GET", "POST", "PATCH", "HEAD", "OPTIONS"]),
    ]
    larg = (W - 90) / 2
    estado = {"page": None, "col": "esq", "y": 90, "num": 2}

    def nova_pagina():
        pg = doc.new_page(width=W, height=H)
        pg.insert_text((45, 40), "EMPRESA DE EXEMPLO - FGV CONHECIMENTO", fontsize=8, fontname="helv")
        pg.insert_text((45, 822), f"ANALISTA - DESENVOLVIMENTO DE SOFTWARE - TARDE TIPO 1 – PÁGINA {estado['num']}", fontsize=7, fontname="helv")
        estado.update(page=pg, col="esq", y=90, num=estado["num"] + 1)

    nova_pagina()

    def escrever(texto, tamanho=9.5, negrito=False):
        pg = estado["page"]
        x0 = 45 if estado["col"] == "esq" else 45 + larg + 10
        rect = pymupdf.Rect(x0, estado["y"], x0 + larg - 5, estado["y"] + 300)
        sobra = pg.insert_textbox(rect, texto, fontsize=tamanho, fontname="hebo" if negrito else "helv")
        usado = 300 - sobra
        if estado["y"] + usado > H - 80:
            pg.add_redact_annot(rect)
            pg.apply_redactions()
            if estado["col"] == "esq":
                estado.update(col="dir", y=90)
            else:
                nova_pagina()
            return escrever(texto, tamanho, negrito)
        estado["y"] += usado + 6

    for num, enun, alts in itens:
        if enun is None:
            escrever(num, 10.5, True)
            continue
        escrever(num, 10, True)
        escrever(enun)
        for letra, alt in zip("ABCDE", alts):
            escrever(f"({letra}) {alt}")
    doc.save(destino)


def pdf_gabarito_fgv(destino: Path, secoes=None):
    doc = pymupdf.open()
    for i, (cargo, tipo, letras) in enumerate(secoes or [
        ("ANALISTA DE PROCESSAMENTO - PROVA TIPO 1", None, "ACDBEABC"),
        ("ANALISTA DE TECNOLOGIA DA INFORMAÇÃO - DESENVOLVIMENTO DE SOFTWARE", "PROVA TIPO 1", "BBBCBBBC"),
        ("ANALISTA DE TECNOLOGIA DA INFORMAÇÃO - DESENVOLVIMENTO DE SOFTWARE", "PROVA TIPO 2", "CCCCCCCC"),
    ]):
        pg = doc.new_page()
        pg.insert_text((50, 50), "GABARITOS PRELIMINARES DA PROVA APLICADA NO DIA 11/10/2026", fontsize=10)
        pg.insert_text((50, 70), f"Página {i + 1} de 3", fontsize=9)
        pg.insert_text((50, 95), cargo, fontsize=9, fontname="hebo")
        y = 110
        if tipo:
            pg.insert_text((50, y), tipo, fontsize=9, fontname="hebo")
            y += 15
        pg.insert_text((50, y + 10), " ".join(str(n) for n in range(1, len(letras) + 1)), fontsize=10)
        pg.insert_text((50, y + 25), " ".join(letras), fontsize=10)
    doc.save(destino)


def main_fgv():
    from aprova.pci import slugify

    def nome(url):
        return slugify(url) + ".html"

    (FIX / nome("https://conhecimento.fgv.br/concursos?page=0")).write_text(FGV_LISTA, encoding="utf-8")
    (FIX / nome("https://conhecimento.fgv.br/concursos/dataprev26")).write_text(FGV_DATAPREV, encoding="utf-8")
    (FIX / nome("https://conhecimento.fgv.br/concursos/dataprev23")).write_text(FGV_DATAPREV23, encoding="utf-8")
    pdf_fgv(FIX / "fgv-2023-desenvolvimento.pdf", ITENS_2023)
    pdf_gabarito_fgv(FIX / "fgv-2023-gabaritos.pdf", [
        ("ANALISTA DE TECNOLOGIA DA INFORMAÇÃO - DESENVOLVIMENTO DE SOFTWARE - TIPO 1", None, "CBBCBB"),
        ("ANALISTA DE INFRAESTRUTURA - TIPO 1", None, "CBBCAA"),
    ])
    (FIX / "busca-dataprev-2026-prova-gabarito-pdf.json").write_text(json.dumps(BUSCA_DATAPREV, ensure_ascii=False, indent=1), encoding="utf-8")
    (FIX / "busca-dataprev-2026-concurso-provas-gabaritos-banca.json").write_text("[]", encoding="utf-8")
    pdf_fgv(FIX / "fgv-desenvolvimento-tipo-1.pdf")
    pdf_gabarito_fgv(FIX / "fgv-gabaritos.pdf")
    (FIX / "downloads.json").write_text(json.dumps({
        "analista-de-tecnologia-da-informacao-desenvolvimento-de-software-cns003-tipo-1.pdf": "fgv-desenvolvimento-tipo-1.pdf",
        "analista-de-tecnologia-da-informacao-desenvolvimento-de-software-cns003-tipo-2.pdf": "fgv-desenvolvimento-tipo-1.pdf",
        "dataprev2026-gabaritos-para-publicacao.pdf": "fgv-gabaritos.pdf",
        "analista-de-processamento-cns013-tipo-1.pdf": "fgv-desenvolvimento-tipo-1.pdf",
        "dp23-desenvolvimento-de-software-tipo-1.pdf": "fgv-2023-desenvolvimento.pdf",
        "dp23-desenvolvimento-de-software-tipo-2.pdf": "fgv-2023-desenvolvimento.pdf",
        "dp23-gabaritos-definitivos.pdf": "fgv-2023-gabaritos.pdf",
    }, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
    main_fgv()
