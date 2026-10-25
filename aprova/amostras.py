"""Simulado de demonstração (questões originais), para testar o app sem internet."""

from __future__ import annotations

TITULO = "Simulado de demonstração"

QUESTOES = [
    {
        "numero": 1,
        "disciplina": "Língua Portuguesa",
        "enunciado": "Assinale a alternativa em que o acento indicativo de crase está empregado corretamente.",
        "alternativas": {
            "A": "Entregamos o relatório à todos os servidores.",
            "B": "A reunião começará às 14 horas.",
            "C": "O candidato voltou à pé para casa.",
            "D": "Refiro-me à esta proposta.",
            "E": "Ele estava disposto à colaborar.",
        },
        "gabarito": "B",
        "explicacao": "Há crase diante de horas determinadas (às 14 horas). Não há crase antes de pronome indefinido (todos), de palavra masculina (pé), de pronome demonstrativo 'esta' nem de verbo (colaborar).",
    },
    {
        "numero": 2,
        "disciplina": "Língua Portuguesa",
        "enunciado": "Assinale a frase que segue a norma-padrão quanto à concordância verbal.",
        "alternativas": {
            "A": "Fazem dois anos que estudo para concursos.",
            "B": "Houveram muitas inscrições no último dia.",
            "C": "Existem candidatos que preferem estudar à noite.",
            "D": "Aluga-se salas no centro da cidade.",
            "E": "Chegou, na semana passada, os novos editais.",
        },
        "gabarito": "C",
        "explicacao": "'Existir' concorda com o sujeito (candidatos). 'Fazer' indicando tempo e 'haver' no sentido de existir são impessoais e ficam no singular; em 'alugam-se salas' o verbo vai ao plural; e 'os novos editais chegaram'.",
    },
    {
        "numero": 3,
        "disciplina": "Língua Portuguesa",
        "enunciado": "No trecho “A banca foi categórica ao anular a questão”, a palavra “categórica” pode ser substituída, sem alteração de sentido, por:",
        "alternativas": {
            "A": "hesitante",
            "B": "parcial",
            "C": "tardia",
            "D": "taxativa",
            "E": "discreta",
        },
        "gabarito": "D",
        "explicacao": "Categórico é o que se expressa de forma firme, sem deixar dúvida: o mesmo que taxativo. 'Hesitante' tem sentido oposto.",
    },
    {
        "numero": 4,
        "disciplina": "Língua Portuguesa",
        "enunciado": "Assinale a alternativa corretamente pontuada.",
        "alternativas": {
            "A": "O edital, publicado ontem, traz novas regras.",
            "B": "Os candidatos, aprovados na primeira fase farão a prova discursiva.",
            "C": "Estudei muito, mas, não passei.",
            "D": "O servidor público deve, agir com ética.",
            "E": "Maria, estuda todos os dias.",
        },
        "gabarito": "A",
        "explicacao": "O trecho explicativo 'publicado ontem' está isolado por duas vírgulas. Nas demais há vírgula separando sujeito de verbo, verbo de complemento, ou vírgula indevida depois de 'mas'.",
    },
    {
        "numero": 5,
        "disciplina": "Raciocínio Lógico",
        "enunciado": "Qual é a negação lógica da proposição “Todo servidor é pontual”?",
        "alternativas": {
            "A": "Nenhum servidor é pontual.",
            "B": "Todo servidor não é pontual.",
            "C": "Algum servidor é pontual.",
            "D": "Nenhum pontual é servidor.",
            "E": "Algum servidor não é pontual.",
        },
        "gabarito": "E",
        "explicacao": "Para negar 'todo', basta um contraexemplo: existe pelo menos um servidor que não é pontual. 'Nenhum' é o oposto extremo, não a negação.",
    },
    {
        "numero": 6,
        "disciplina": "Raciocínio Lógico",
        "enunciado": "Considere verdadeira a proposição “Se chove, então a rua fica molhada”. Sabendo que a rua não está molhada, conclui-se que:",
        "alternativas": {
            "A": "choveu.",
            "B": "não choveu.",
            "C": "pode ter chovido.",
            "D": "a rua secou com o sol.",
            "E": "nada se pode concluir.",
        },
        "gabarito": "B",
        "explicacao": "Se p → q é verdadeira e q é falsa, então p é falsa (modus tollens). Logo, não choveu.",
    },
    {
        "numero": 7,
        "disciplina": "Raciocínio Lógico",
        "enunciado": "Na sequência 2, 6, 12, 20, 30, ..., o próximo termo é:",
        "alternativas": {"A": "40", "B": "36", "C": "42", "D": "44", "E": "48"},
        "gabarito": "C",
        "explicacao": "As diferenças entre os termos crescem de 2 em 2: +4, +6, +8, +10. A próxima é +12, então 30 + 12 = 42.",
    },
    {
        "numero": 8,
        "disciplina": "Matemática",
        "enunciado": "Um produto de R$ 250,00 teve aumento de 20% e, em seguida, desconto de 20% sobre o novo preço. O preço final é:",
        "alternativas": {"A": "R$ 240,00", "B": "R$ 250,00", "C": "R$ 260,00", "D": "R$ 230,00", "E": "R$ 245,00"},
        "gabarito": "A",
        "explicacao": "250 × 1,20 = 300. Depois, 300 × 0,80 = 240. O desconto incide sobre um valor maior, por isso não volta aos R$ 250,00.",
    },
    {
        "numero": 9,
        "disciplina": "Matemática",
        "enunciado": "Se 4 servidores analisam 120 processos em 3 dias, quantos processos 6 servidores analisam em 5 dias, no mesmo ritmo?",
        "alternativas": {"A": "200", "B": "250", "C": "180", "D": "300", "E": "360"},
        "gabarito": "D",
        "explicacao": "Cada servidor analisa 120 ÷ (4 × 3) = 10 processos por dia. Então 6 × 5 × 10 = 300.",
    },
    {
        "numero": 10,
        "disciplina": "Informática",
        "enunciado": "No Windows e na maioria dos programas, o atalho de teclado Ctrl + Z serve para:",
        "alternativas": {
            "A": "desfazer a última ação.",
            "B": "copiar o item selecionado.",
            "C": "colar o conteúdo copiado.",
            "D": "fechar a janela atual.",
            "E": "salvar o arquivo.",
        },
        "gabarito": "A",
        "explicacao": "Ctrl + Z desfaz. Copiar é Ctrl + C, colar é Ctrl + V, salvar é Ctrl + S.",
    },
    {
        "numero": 11,
        "disciplina": "Informática",
        "enunciado": "Uma mensagem de e-mail que imita um banco e pede que o usuário clique em um link para “atualizar seus dados” é um exemplo típico de:",
        "alternativas": {"A": "backup", "B": "firewall", "C": "phishing", "D": "criptografia", "E": "cookie"},
        "gabarito": "C",
        "explicacao": "Phishing é a fraude que se passa por uma instituição confiável para roubar dados, geralmente com links falsos.",
    },
    {
        "numero": 12,
        "disciplina": "Informática",
        "enunciado": "Em uma planilha, com A1 = 2, A2 = 5 e A3 = 3, a fórmula =SOMA(A1:A3) resulta em:",
        "alternativas": {"A": "8", "B": "10", "C": "30", "D": "5", "E": "3"},
        "gabarito": "B",
        "explicacao": "O intervalo A1:A3 inclui as três células: 2 + 5 + 3 = 10.",
    },
    {
        "numero": 13,
        "disciplina": "Direito Constitucional",
        "enunciado": "Segundo a Constituição Federal de 1988, são Poderes da União, independentes e harmônicos entre si:",
        "alternativas": {
            "A": "o Executivo, o Judiciário e o Ministério Público.",
            "B": "o Legislativo, o Executivo e o Tribunal de Contas.",
            "C": "o Executivo, o Legislativo e as Forças Armadas.",
            "D": "o Judiciário, o Ministério Público e a Defensoria Pública.",
            "E": "o Legislativo, o Executivo e o Judiciário.",
        },
        "gabarito": "E",
        "explicacao": "Art. 2º da CF/88. Ministério Público, Defensoria e Tribunais de Contas são órgãos importantes, mas não são Poderes.",
    },
    {
        "numero": 14,
        "disciplina": "Direito Constitucional",
        "enunciado": "Pelo art. 5º da Constituição, a casa é asilo inviolável do indivíduo. Sem consentimento do morador, é possível entrar nela durante o dia por determinação judicial e, a qualquer hora, em caso de:",
        "alternativas": {
            "A": "flagrante delito, desastre ou para prestar socorro.",
            "B": "investigação policial em andamento.",
            "C": "dívida tributária do morador.",
            "D": "ordem escrita do prefeito.",
            "E": "denúncia anônima.",
        },
        "gabarito": "A",
        "explicacao": "Art. 5º, XI: salvo flagrante delito, desastre ou para prestar socorro (a qualquer hora), ou durante o dia por determinação judicial.",
    },
    {
        "numero": 15,
        "disciplina": "Direito Administrativo",
        "enunciado": "O princípio da Administração Pública segundo o qual o agente só pode fazer o que a lei permite ou determina é o princípio da:",
        "alternativas": {"A": "publicidade", "B": "eficiência", "C": "legalidade", "D": "impessoalidade", "E": "moralidade"},
        "gabarito": "C",
        "explicacao": "Legalidade: o particular pode fazer tudo que a lei não proíbe; a Administração só faz o que a lei autoriza. Os cinco princípios do art. 37 formam o LIMPE.",
    },
    {
        "numero": 16,
        "disciplina": "Direito Administrativo",
        "enunciado": "Conforme o art. 37 da Constituição, a investidura em cargo ou emprego público depende, em regra, de:",
        "alternativas": {
            "A": "indicação da autoridade competente.",
            "B": "entrevista com a chefia imediata.",
            "C": "sorteio entre os inscritos.",
            "D": "aprovação prévia em concurso público de provas ou de provas e títulos.",
            "E": "comprovação de experiência anterior.",
        },
        "gabarito": "D",
        "explicacao": "Art. 37, II. A exceção são os cargos em comissão, de livre nomeação e exoneração.",
    },
]


def instalar(banco) -> int:
    """Cria o simulado de demonstração no banco, se ainda não existir."""
    for p in banco.provas():
        if p["origem_url"] == "aprova://demo":
            return p["id"]
    pid = banco.criar_prova(
        titulo=TITULO,
        cargo="Nível médio (geral)",
        orgao="Aprova",
        banca="Questões originais",
        ano="2026",
        origem_url="aprova://demo",
        modo="questoes",
    )
    banco.salvar_questoes(pid, [dict(q, tipo="ME", pagina=0, texto_base="") for q in QUESTOES])
    return pid
