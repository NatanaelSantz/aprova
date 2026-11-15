"""Discursiva corrigida por IA: a pessoa escreve a redação ou a questão discursiva e recebe a correção
nos moldes das bancas (conteúdo, estrutura, coesão, gramática e aderência ao tema), com nota de 0 a 10.

Com a chave do Claude, a correção vem dentro do app (corrigir()). Sem chave, o app monta o pedido
pronto (pedido_correcao()) para colar no chat do Claude ou do ChatGPT, e a pessoa cola a correção de volta.
"""

from __future__ import annotations

import re

TIPOS = {
    "dissertativa": "Redação dissertativa",
    "questao": "Questão discursiva",
    "peca": "Peça / parecer",
}
LINHA = 75  # caracteres por linha na folha de resposta (padrão das bancas: 70 a 80)

# temas prontos (quem não tem o enunciado do edital começa por aqui)
TEMAS = [
    ("dissertativa", "O papel da transparência pública no combate à corrupção no Brasil", 30),
    ("dissertativa", "Inteligência artificial no serviço público: oportunidades e riscos", 30),
    ("dissertativa", "Desafios da educação pública brasileira no século XXI", 30),
    ("dissertativa", "Saúde mental dos servidores públicos e produtividade", 30),
    ("dissertativa", "Sustentabilidade e desenvolvimento econômico: é possível conciliar?", 30),
    ("dissertativa", "Os impactos da LGPD na administração pública", 30),
    ("questao", "Discorra sobre os princípios da administração pública previstos no art. 37 da Constituição Federal, "
                "explicando cada um com um exemplo prático.", 20),
    ("questao", "Explique a diferença entre ato administrativo vinculado e discricionário e os limites do controle judicial sobre cada um.", 20),
    ("questao", "Conceitue licitação, apresente seus princípios e cite três hipóteses de dispensa previstas na Lei nº 14.133/2021.", 20),
    ("questao", "Diferencie improbidade administrativa de crime contra a administração pública, apontando as sanções cabíveis em cada caso.", 20),
    ("questao", "Discorra sobre o controle de constitucionalidade no Brasil: modelos, legitimados e efeitos das decisões.", 20),
    ("questao", "Explique o que é a responsabilidade civil do Estado e em que situações ela pode ser afastada.", 20),
]

SISTEMA = """Você é um examinador experiente de bancas de concurso público brasileiras (Cebraspe, FGV, FCC, Vunesp).
Corrija textos de candidatos com rigor e didatismo, em português do Brasil, linguagem simples e direta.
Nunca reescreva o texto inteiro: aponte o problema, mostre o trecho e sugira como melhorar."""

PEDIDO = """Corrija a {tipo} abaixo como uma banca de concurso corrigiria.{limite}

TEMA / ENUNCIADO:
{tema}

TEXTO DO CANDIDATO ({palavras} palavras, cerca de {linhas} linhas):
\"\"\"
{texto}
\"\"\"

Responda em Markdown, nesta ordem:
1. **Nota: X/10** (na primeira linha, exatamente neste formato) e uma frase de avaliação geral.
2. **Aderência ao tema**: respondeu tudo o que foi pedido? Faltou algum ponto do enunciado?
3. **Conteúdo e argumentação**: o que está bom e o que está fraco ou errado (cite trechos entre aspas).
4. **Estrutura e coesão**: introdução, desenvolvimento, conclusão; parágrafos e conectivos.
5. **Gramática e norma culta**: liste até 8 erros com o trecho, a correção e a regra, em tabela.
6. **Três melhorias prioritárias** para a próxima redação, em frases curtas.
Seja específico e use no máximo 450 palavras."""


def contar(texto: str) -> dict:
    """Palavras, caracteres e linhas estimadas (folha de resposta padrão)."""
    t = (texto or "").strip()
    palavras = len(re.findall(r"\S+", t))
    linhas = 0
    for paragrafo in t.split("\n"):
        linhas += max(1, -(-len(paragrafo) // LINHA)) if paragrafo.strip() else 0
    return {"palavras": palavras, "caracteres": len(t), "linhas": linhas}


def pedido_correcao(tema: str, texto: str, tipo: str = "dissertativa", limite_linhas: int | None = None) -> str:
    n = contar(texto)
    limite = f" O limite da prova é de {limite_linhas} linhas." if limite_linhas else ""
    return PEDIDO.format(tipo=TIPOS.get(tipo, TIPOS["dissertativa"]).lower(), limite=limite, tema=tema.strip(), palavras=n["palavras"],
                         linhas=n["linhas"], texto=texto.strip())


def extrair_nota(correcao: str) -> float | None:
    """Pega o "Nota: 7,5/10" do começo da correção (também aceita "7.5 / 10" e "nota 8")."""
    m = re.search(r"nota\**\s*:?\s*\**\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:/|de)\s*10", correcao or "", re.I)
    if not m:
        m = re.search(r"\bnota\b[^0-9\n]{0,12}(\d{1,2}(?:[.,]\d{1,2})?)", correcao or "", re.I)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return v if 0 <= v <= 10 else None


def corrigir(tema: str, texto: str, tipo: str, api_key: str, modelo: str, limite_linhas: int | None = None) -> str:
    """Correção pela API do Claude (com a chave da pessoa). Devolve Markdown."""
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key, timeout=120)
    msg = cliente.messages.create(
        model=modelo,
        max_tokens=1500,
        system=SISTEMA,
        messages=[{"role": "user", "content": pedido_correcao(tema, texto, tipo, limite_linhas)}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content).strip()
