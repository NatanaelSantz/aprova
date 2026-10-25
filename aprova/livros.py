"""Indicações de estudo por disciplina: livros consagrados e material oficial gratuito.

Lista curta e conservadora (obras conhecidas e fontes oficiais). Edições mudam:
o app manda procurar a edição mais recente em vez de fixar ano ou preço.
"""

from __future__ import annotations

from urllib.parse import quote_plus

PLANALTO = "https://www.planalto.gov.br/ccivil_03/"

INDICACOES: dict[str, list[dict]] = {
    "Língua Portuguesa": [
        {"titulo": "Gramática para Concursos Públicos", "autor": "Fernando Pestana", "por_que": "Feita para concurso, com teoria direta e muitas questões comentadas."},
        {"titulo": "Moderna Gramática Portuguesa", "autor": "Evanildo Bechara", "por_que": "Referência para tirar dúvidas de regra com segurança."},
        {"titulo": "Português Esquematizado", "autor": "Agnaldo Martino", "por_que": "Esquemas visuais, bom para revisar rápido."},
    ],
    "Língua Inglesa": [
        {"titulo": "Inglês Instrumental: estratégias de leitura", "autor": "Rosângela Munhoz", "por_que": "Prova de concurso cobra leitura; o livro ensina a ler texto técnico sem traduzir tudo."},
        {"titulo": "English Grammar in Use", "autor": "Raymond Murphy", "por_que": "Gramática com exercícios curtos, uma lição por página."},
    ],
    "Raciocínio Lógico": [
        {"titulo": "Raciocínio Lógico Simplificado (vol. 1 e 2)", "autor": "Sérgio Carvalho e Weber Campos", "por_que": "Clássico de concurso: proposições, equivalências e problemas no estilo das bancas."},
    ],
    "Matemática": [
        {"titulo": "Fundamentos de Matemática Elementar", "autor": "Gelson Iezzi e outros", "por_que": "Base sólida de porcentagem, razão, funções e probabilidade."},
    ],
    "Informática": [
        {"titulo": "Informática para Concursos: teoria e questões", "autor": "João Antonio Carvalho", "por_que": "Cobre Windows, pacote Office, internet e segurança no nível das provas."},
    ],
    "Segurança da Informação": [
        {"titulo": "Fundamentos de Segurança da Informação (com base na ISO 27001 e 27002)", "autor": "Hintzbergen, Hintzbergen, Smulders e Baars", "por_que": "Conceitos de confidencialidade, integridade, riscos e controles das normas ISO."},
        {"titulo": "LGPD: Lei Geral de Proteção de Dados Comentada", "autor": "Viviane Nóbrega Maldonado e Renato Opice Blum (coord.)", "por_que": "Artigo por artigo, ajuda nas questões de legislação de proteção de dados."},
        {"titulo": "Texto oficial da LGPD (Lei 13.709/2018)", "autor": "Planalto", "url": PLANALTO + "_ato2015-2018/2018/lei/l13709.htm", "por_que": "Grátis. A banca cobra a letra da lei: leia os artigos 5º a 22."},
    ],
    "Direito Constitucional": [
        {"titulo": "Direito Constitucional Descomplicado", "autor": "Vicente Paulo e Marcelo Alexandrino", "por_que": "Linguagem simples e foco no que cai em prova."},
        {"titulo": "Direito Constitucional Esquematizado", "autor": "Pedro Lenza", "por_que": "Mais completo; bom para aprofundar e consultar."},
        {"titulo": "Constituição Federal (texto oficial)", "autor": "Planalto", "url": PLANALTO + "constituicao/constituicao.htm", "por_que": "Grátis. Leia sempre a lei seca dos artigos do seu edital."},
    ],
    "Direito Administrativo": [
        {"titulo": "Direito Administrativo Descomplicado", "autor": "Marcelo Alexandrino e Vicente Paulo", "por_que": "Didático, com os temas clássicos de prova."},
        {"titulo": "Manual de Direito Administrativo", "autor": "Matheus Carvalho", "por_que": "Atualizado com a jurisprudência; bom para nível superior."},
        {"titulo": "Lei 14.133/2021 (licitações e contratos)", "autor": "Planalto", "url": PLANALTO + "_ato2019-2022/2021/lei/l14133.htm", "por_que": "Grátis. Tema muito cobrado nas provas recentes."},
    ],
    "Direito Penal": [
        {"titulo": "Direito Penal: parte geral", "autor": "Cleber Masson", "por_que": "Muito usado em concursos, com teoria e quadros de revisão."},
        {"titulo": "Curso de Direito Penal", "autor": "Rogério Greco", "por_que": "Explicação aprofundada para quem precisa de base."},
        {"titulo": "Código Penal (texto oficial)", "autor": "Planalto", "url": PLANALTO + "decreto-lei/del2848compilado.htm", "por_que": "Grátis. Leia os artigos do edital."},
    ],
    "Direito Civil": [
        {"titulo": "Manual de Direito Civil: volume único", "autor": "Flávio Tartuce", "por_que": "Todo o conteúdo num volume, bom para concurso."},
        {"titulo": "Código Civil (texto oficial)", "autor": "Planalto", "url": PLANALTO + "leis/2002/l10406compilada.htm", "por_que": "Grátis."},
    ],
    "Legislação": [
        {"titulo": "Vade Mecum atualizado", "autor": "Saraiva, Rideel ou JusPodivm", "por_que": "Reúne as leis num só livro; confira se é a edição do ano."},
        {"titulo": "Portal da Legislação", "autor": "Planalto", "url": PLANALTO, "por_que": "Grátis e sempre atualizado: procure pelo número da lei do edital."},
    ],
    "Administração": [
        {"titulo": "Introdução à Teoria Geral da Administração", "autor": "Idalberto Chiavenato", "por_que": "Base das teorias administrativas cobradas em prova."},
        {"titulo": "Administração Geral e Pública", "autor": "Idalberto Chiavenato", "por_que": "Junta administração geral e pública no foco de concursos."},
    ],
    "Contabilidade": [
        {"titulo": "Contabilidade Introdutória", "autor": "Equipe de professores da FEA-USP", "por_que": "Clássico para começar do zero."},
        {"titulo": "Manual de Contabilidade Societária", "autor": "FIPECAFI (Gelbcke, Santos, Iudícibus e Martins)", "por_que": "Para nível avançado e normas atuais (CPC)."},
    ],
    "Conhecimentos Bancários": [
        {"titulo": "Site do Banco Central", "autor": "Banco Central do Brasil", "url": "https://www.bcb.gov.br", "por_que": "Grátis. Sistema Financeiro Nacional, Pix e normas vêm daqui."},
    ],
    "Atualidades": [
        {"titulo": "Agência Brasil", "autor": "EBC", "url": "https://agenciabrasil.ebc.com.br", "por_que": "Grátis. Leia um resumo por semana dos temas de economia, política e tecnologia."},
    ],
    "Conhecimentos Específicos": [
        {"titulo": "Engenharia de Software", "autor": "Ian Sommerville", "por_que": "Para cargos de TI: processos, requisitos e testes, muito cobrados."},
        {"titulo": "Sistemas de Banco de Dados", "autor": "Ramez Elmasri e Shamkant Navathe", "por_que": "Para cargos de TI: modelagem, SQL e normalização."},
        {"titulo": "Redes de Computadores e a Internet", "autor": "James Kurose e Keith Ross", "por_que": "Para cargos de TI: protocolos e camadas, base de segurança."},
        {"titulo": "Código Limpo", "autor": "Robert C. Martin", "por_que": "Para desenvolvimento: boas práticas que aparecem nas questões de qualidade."},
    ],
}


def link_busca(item: dict) -> str:
    if item.get("url"):
        return item["url"]
    return "https://www.google.com/search?tbm=bks&q=" + quote_plus(f"{item['titulo']} {item['autor']}")


def para(disciplina: str) -> list[dict]:
    return INDICACOES.get(disciplina, [])


def links_estudo(assunto: str) -> list[tuple[str, str, str]]:
    """Atalhos para pesquisar um assunto: (rótulo, ícone, url)."""
    q = quote_plus(assunto)
    return [
        ("Pesquisar na internet", "TRAVEL_EXPLORE", f"https://www.google.com/search?q={q}"),
        ("Vídeo-aulas", "SMART_DISPLAY_OUTLINED", f"https://www.youtube.com/results?search_query={quote_plus(assunto + ' aula concurso')}"),
        ("Livros", "MENU_BOOK_OUTLINED", f"https://www.google.com/search?tbm=bks&q={q}"),
    ]
