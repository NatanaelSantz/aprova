"""Levar a dúvida para o chat do Claude ou do ChatGPT (sem chave da API, com a conta grátis da pessoa).

O app monta a pergunta pronta (questão, alternativas, o que você marcou), copia para a área de
transferência e abre o chat no navegador. Quando a pergunta é curta, ela já vai no endereço
(claude.ai/new?q=… e chatgpt.com/?q=…); se o chat abrir vazio, é só colar (Ctrl+V) e enviar.
"""

from __future__ import annotations

from urllib.parse import quote

SERVICOS = {
    "claude": ("Claude", "https://claude.ai/new"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
}
MAX_NO_LINK = 1800  # pergunta maior que isso vai só pela área de transferência (link longo falha)


def link(servico: str, pergunta: str) -> str:
    _, base = SERVICOS[servico]
    if pergunta and len(pergunta) <= MAX_NO_LINK:
        return f"{base}?q={quote(pergunta)}"
    return base


def _questao_texto(q: dict, limite_base: int = 1500) -> str:
    partes = []
    if q.get("texto_base"):
        base = " ".join(str(q["texto_base"]).split())
        partes.append("Texto de apoio: " + base[:limite_base] + ("…" if len(base) > limite_base else ""))
    partes.append(" ".join(str(q.get("enunciado") or "").split()))
    for letra, texto in (q.get("alternativas") or {}).items():
        partes.append(f"({letra}) {' '.join(str(texto).split())}")
    return "\n".join(partes)


def pergunta_questao(q: dict, modo: str = "explicacao", sua: str | None = None, mostrar_gabarito: bool = True, banca: str = "") -> str:
    """modo "dica": ajuda a pensar sem dar a resposta; "explicacao": explica a resposta certa."""
    origem = f" ({q.get('disciplina') or 'concurso'}" + (f", banca {banca}" if banca else "") + ")"
    cabeca = f"Estou estudando para concurso público. Esta é uma questão{origem}:\n\n"
    corpo = _questao_texto(q)
    extra = []
    gab = str(q.get("gabarito") or "").strip()
    if mostrar_gabarito and gab and gab != "*":
        extra.append(f"Gabarito oficial: {gab}.")
    if sua:
        extra.append(f"Eu marquei {sua}.")
    if modo == "dica":
        pedido = ("Me dê uma DICA para eu resolver sozinho, sem dizer a alternativa certa: qual conhecimento a questão cobra "
                  "e como pensar. Use linguagem simples.")
    else:
        pedido = ("Explique, em português simples, por que a resposta certa está certa e onde as outras erram. Cite a regra, "
                  "o artigo de lei ou o conceito cobrado. Se eu marquei errado, mostre onde eu me confundi.")
    return cabeca + corpo + ("\n\n" + " ".join(extra) if extra else "") + "\n\n" + pedido


def pergunta_resultado(resultado: dict, erradas: dict[str, list[dict]], titulo: str = "") -> str:
    """Pedido de análise do simulado para o chat: assuntos para revisar e um plano de 3 dias."""
    total = int(resultado.get("total") or 0)
    acertos = int(resultado.get("acertos") or 0)
    pct = round(100 * acertos / total) if total else 0
    por_disc = "; ".join(f"{d}: {a} de {t}" for d, (a, t) in (resultado.get("por_disc") or {}).items())
    linhas = []
    for disc, lista in erradas.items():
        for e in lista[:5]:
            enun = e["enunciado"][:220] + ("…" if len(e["enunciado"]) > 220 else "")
            linhas.append(f"- [{disc}] {enun} (marquei {e['sua'] or 'em branco'}, a certa era {e['certa']})")
    texto = (
        f"Fiz um simulado de concurso público{f' ({titulo})' if titulo else ''} e acertei {acertos} de {total} ({pct}%).\n"
        f"Por matéria: {por_disc}.\n\nQuestões que eu errei:\n" + "\n".join(linhas[:20]) + "\n\n"
        "Como um professor de cursinho que torce por mim: diga quais assuntos eu preciso revisar (bem específicos), "
        "monte um plano curto para os próximos 3 dias e termine com uma frase de incentivo. Seja direto, em português simples."
    )
    return texto
