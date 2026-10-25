"""Identificação da disciplina de cada questão.

Primeiro usamos os títulos de seção que quase toda prova tem
("LÍNGUA PORTUGUESA", "NOÇÕES DE INFORMÁTICA"...). Quando não há título,
classificamos pelo vocabulário do enunciado.
"""

from __future__ import annotations

import re
import unicodedata

# nome exibido -> padrões de título de seção (sem acento, minúsculo)
SECOES: list[tuple[str, tuple[str, ...]]] = [
    # "" = título de módulo genérico: zera a seção e deixa o vocabulário decidir
    ("", ("conhecimentos gerais", "conhecimentos basicos", "conhecimentos gerais e especificos")),
    ("Língua Portuguesa", ("lingua portuguesa", "portugues", "interpretacao de texto", "redacao oficial")),
    ("Raciocínio Lógico", ("raciocinio logico", "logica", "raciocinio")),
    ("Matemática", ("matematica financeira", "matematica", "estatistica")),
    ("Segurança da Informação", ("seguranca da informacao", "protecao de dados", "lgpd", "legislacao sobre seguranca", "seguranca cibernetica")),
    ("Informática", ("nocoes de informatica", "informatica", "tecnologia da informacao")),
    ("Direito Constitucional", ("direito constitucional", "constituicao federal")),
    ("Direito Administrativo", ("direito administrativo",)),
    ("Direito Penal", ("direito penal", "processo penal", "direito processual penal")),
    ("Direito Civil", ("direito civil", "processo civil", "direito processual civil")),
    ("Legislação", ("legislacao", "estatuto", "lei organica", "regimento interno", "etica no servico publico", "etica")),
    ("Atualidades", ("atualidades", "realidade brasileira", "conhecimentos sobre o municipio")),
    ("Administração", ("administracao publica", "administracao geral", "gestao publica", "arquivologia")),
    ("Contabilidade", ("contabilidade",)),
    ("Conhecimentos Bancários", ("conhecimentos bancarios", "sistema financeiro", "vendas e negociacao")),
    ("Língua Inglesa", ("lingua inglesa", "ingles")),
    ("Conhecimentos Específicos", ("conhecimentos especificos", "especificos")),
    ("Pedagogia", ("conhecimentos pedagogicos", "pedagogia", "fundamentos da educacao")),
    ("Saúde", ("sistema unico de saude", "saude publica", "sus")),
]

# vocabulário para classificar o enunciado
PALAVRAS: dict[str, tuple[str, ...]] = {
    "Língua Portuguesa": (
        "texto", "oracao", "concordancia", "regencia", "crase", "pontuacao", "virgula", "sinonimo",
        "sentido", "pronome", "verbo", "sujeito", "predicado", "acentuacao", "ortografia", "coesao",
        "conjuncao", "substantivo", "adjetivo", "trecho", "paragrafo", "autor", "narrador", "palavra",
        "reescrita", "colocacao pronominal", "voz passiva", "tempo verbal",
    ),
    "Raciocínio Lógico": (
        "proposicao", "verdadeira", "falsa", "negacao", "tabela-verdade", "silogismo", "conjunto",
        "sequencia", "argumento", "equivalente", "se e somente se", "logicamente", "diagrama",
        "probabilidade", "permutacao", "combinacao", "anagrama",
    ),
    "Matemática": (
        "porcentagem", "juros", "razao", "proporcao", "equacao", "fracao", "media", "area",
        "volume", "regra de tres", "desconto", "lucro", "numero", "soma", "produto", "metros",
    ),
    "Informática": (
        "windows", "excel", "word", "planilha", "navegador", "e-mail", "internet", "arquivo",
        "pasta", "teclado", "atalho", "ctrl", "backup", "virus", "malware", "phishing", "nuvem",
        "linux", "libreoffice", "writer", "calc", "powerpoint", "outlook", "firewall", "senha", "url",
        "chrome", "firefox", "sistema operacional",
    ),
    "Direito Constitucional": (
        "constituicao", "direitos fundamentais", "art. 5", "habeas", "mandado de seguranca",
        "poder legislativo", "poder judiciario", "uniao", "estados", "municipios", "emenda",
        "nacionalidade", "direitos politicos", "stf",
    ),
    "Direito Administrativo": (
        "administracao publica", "ato administrativo", "licitacao", "servidor publico", "improbidade",
        "poder de policia", "autarquia", "concessao", "lei 8.112", "lei 14.133", "contrato administrativo",
        "principio da legalidade", "impessoalidade", "moralidade", "publicidade", "eficiencia",
    ),
    "Segurança da Informação": (
        "lgpd", "dados pessoais", "titular", "controlador", "operador", "anpd", "marco civil", "acesso a informacao",
        "criptografia", "confidencialidade", "integridade", "disponibilidade", "incidente", "autenticacao", "13.709",
    ),
    "Direito Penal": ("crime", "pena", "dolo", "culpa", "tipicidade", "codigo penal", "inquerito", "reu"),
    "Direito Civil": ("contrato", "obrigacoes", "codigo civil", "prescricao", "posse", "propriedade", "heranca"),
    "Atualidades": ("governo", "eleicao", "pandemia", "economia", "clima", "brasil", "mundial", "2024", "2025", "2026"),
    "Conhecimentos Bancários": ("banco central", "copom", "selic", "cmn", "cvm", "lavagem de dinheiro", "pix", "credito"),
    "Língua Inglesa": (" the ", " of ", " and ", " is ", " are ", " which ", " according to "),
}


def sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return t.lower()


def secao_de_linha(linha: str) -> str | None:
    """Se a linha parece um título de seção de disciplina, devolve o nome padronizado."""
    bruta = linha.strip()
    if not bruta or len(bruta) > 70:
        return None
    letras = [c for c in bruta if c.isalpha()]
    if len(letras) < 4:
        return None
    maiusculas = sum(1 for c in letras if c.isupper()) / len(letras)
    t = sem_acento(bruta)
    t = re.sub(r"[^a-z ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    caixa_alta = maiusculas >= 0.75
    # títulos em caixa mista ("Língua Portuguesa", "Raciocínio lógico-matemático") só valem
    # se forem curtos, sem pontuação final e começarem com o nome da disciplina
    if not caixa_alta and (bruta[-1] in ".?:;,!" or len(bruta) > 70 or not bruta[0].isupper()):
        return None
    for nome, padroes in SECOES:
        for p in padroes:
            if caixa_alta:
                if t == p or t.startswith(p + " ") or t.endswith(" " + p) or (p in t and len(t) <= len(p) + 25):
                    return nome
            elif t == p or t.startswith(p + " ") or (t.endswith(" " + p) and len(t) <= len(p) + 50):
                if len(t.split()) <= 11:
                    return nome
    return None


def classificar(enunciado: str, alternativas: dict[str, str] | None = None) -> str:
    texto = " " + sem_acento(enunciado + " " + " ".join((alternativas or {}).values())) + " "
    melhor, pontos = "Geral", 0
    for nome, palavras in PALAVRAS.items():
        p = sum(texto.count(w) for w in palavras)
        if p > pontos:
            melhor, pontos = nome, p
    return melhor if pontos >= 2 else "Geral"


DICAS_POR_DISCIPLINA = {
    "Língua Portuguesa": "Leia o trecho citado na questão dentro do texto, não isolado. Em reescritas, confira se o sentido e a correção gramatical se mantêm ao mesmo tempo.",
    "Raciocínio Lógico": "Traduza as frases em símbolos (p, q, ∧, ∨, →) antes de calcular. Em negações, lembre: a negação de 'todo' é 'algum não'.",
    "Matemática": "Escreva os dados numa linha só e estime o resultado antes de fazer a conta: isso já elimina alternativas absurdas.",
    "Informática": "Pense no uso prático: qual programa, qual menu, qual atalho. Desconfie de alternativas com 'sempre' e 'nunca'.",
    "Direito Constitucional": "Identifique o artigo da Constituição envolvido. A banca costuma trocar uma palavra da lei seca (pode/deve, União/Estados).",
    "Direito Administrativo": "Lembre do LIMPE (legalidade, impessoalidade, moralidade, publicidade, eficiência) e confira se a alternativa troca o sujeito ou o prazo da lei.",
    "Legislação": "Questões de legislação cobram o texto literal: procure a palavra trocada entre as alternativas.",
    "Atualidades": "Relacione o tema a fatos dos últimos 12 meses e elimine alternativas com datas ou números exagerados.",
    "Conhecimentos Bancários": "Separe quem regula (CMN), quem executa (Banco Central) e quem fiscaliza o mercado de capitais (CVM).",
    "Língua Inglesa": "Leia primeiro a pergunta e depois procure no texto só o trecho que responde. Cognatos ajudam, mas cuidado com os falsos (actually, pretend, eventually).",
    "Segurança da Informação": "Separe os pilares (confidencialidade, integridade, disponibilidade) e, na LGPD, quem é titular, controlador, operador e encarregado.",
    "Geral": "Elimine primeiro as alternativas claramente erradas e compare as duas que sobrarem palavra por palavra.",
}
