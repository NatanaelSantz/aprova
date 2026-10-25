"""Recursos opcionais com a API do Claude (precisam de chave da API).

- explicar(): explica ou dá uma dica sobre a questão, pesquisando na web.
- extrair_questoes(): lê o texto da prova e devolve as questões estruturadas,
  para PDFs em que a leitura automática não funcionou bem.
- responder_duvida(): responde uma pergunta livre sobre a questão.
- gerar_questoes(): cria questões inéditas no estilo das provas da biblioteca,
  com conferência do gabarito por uma segunda resolução.
"""

from __future__ import annotations

import json
import re

FERRAMENTA_BUSCA = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}

SISTEMA_TUTOR = """Você é um professor brasileiro que prepara candidatos para concursos públicos.
Responda em português do Brasil, com frases curtas e linguagem simples.
Sempre pesquise na web antes de responder, para confirmar a regra, a lei ou o conceito cobrado.
Cite a regra, o artigo de lei ou o conceito que resolve a questão.
Formate em Markdown, com no máximo 180 palavras."""

PEDIDO_DICA = """Dê uma DICA para o candidato resolver sozinho. NÃO diga qual alternativa está correta
e não elimine alternativas pela letra. Explique qual conhecimento a questão cobra e como raciocinar."""

PEDIDO_EXPLICACAO = """Explique a resolução: qual alternativa está correta e por quê, e o erro das principais
alternativas incorretas. Se a resposta oficial for informada, use-a como referência."""


def _formatar_questao(q: dict, resposta_usuario: str | None) -> str:
    partes = []
    if q.get("texto_base"):
        partes.append("Texto de apoio:\n" + q["texto_base"][:3000])
    partes.append(f"Questão {q.get('numero', '')} ({q.get('disciplina', 'Geral')}):\n{q.get('enunciado', '')}")
    for letra, texto in (q.get("alternativas") or {}).items():
        partes.append(f"({letra}) {texto}")
    if q.get("gabarito"):
        partes.append(f"Resposta oficial: {q['gabarito']}")
    if resposta_usuario:
        partes.append(f"O candidato marcou: {resposta_usuario}")
    return "\n".join(partes)


def explicar(questao: dict, resultados: list[dict], modo: str, api_key: str, modelo: str,
             resposta_usuario: str | None = None) -> tuple[str, list[dict]]:
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key, timeout=90)
    contexto = ""
    if resultados:
        contexto = "\n\nResultados de uma busca prévia (use se forem úteis):\n" + "\n".join(
            f"- {r['titulo']} ({r['url']}): {r['trecho'][:300]}" for r in resultados[:5]
        )
    pedido = PEDIDO_DICA if modo == "dica" else PEDIDO_EXPLICACAO
    msg = cliente.messages.create(
        model=modelo,
        max_tokens=1200,
        system=SISTEMA_TUTOR,
        tools=[FERRAMENTA_BUSCA],
        messages=[{"role": "user", "content": f"{pedido}\n\n{_formatar_questao(questao, resposta_usuario)}{contexto}"}],
    )
    return _texto_e_fontes(msg)


def _texto_e_fontes(msg) -> tuple[str, list[dict]]:
    textos: list[str] = []
    fontes: list[dict] = []
    vistos: set[str] = set()
    for bloco in msg.content:
        if getattr(bloco, "type", "") == "text":
            textos.append(bloco.text)
            for c in getattr(bloco, "citations", None) or []:
                url = getattr(c, "url", None)
                if url and url not in vistos:
                    vistos.add(url)
                    fontes.append({"titulo": getattr(c, "title", None) or url, "url": url})
        elif getattr(bloco, "type", "") == "web_search_tool_result":
            conteudo = getattr(bloco, "content", None)
            if isinstance(conteudo, list):
                for r in conteudo:
                    url = getattr(r, "url", None)
                    if url and url not in vistos and len(fontes) < 8:
                        vistos.add(url)
                        fontes.append({"titulo": getattr(r, "title", None) or url, "url": url})
    texto = "".join(textos).strip()
    if not texto:
        raise RuntimeError("resposta vazia")
    return texto, fontes


PEDIDO_EXTRACAO = """Abaixo está o texto extraído de um PDF de prova de concurso público (pode estar desordenado).
Extraia TODAS as questões objetivas. Responda SOMENTE com um array JSON, sem comentários, no formato:
[{"numero": 1, "disciplina": "Língua Portuguesa", "enunciado": "...", "alternativas": {"A": "...", "B": "..."}, "texto_base": ""}]
Regras: mantenha o texto original das questões; para itens de certo/errado use "alternativas": {"C": "Certo", "E": "Errado"};
coloque em "texto_base" o texto de apoio compartilhado, se houver; "disciplina" pelo título da seção ou pelo assunto."""


def _json_array(texto: str) -> list:
    ini, fim = texto.find("["), texto.rfind("]")
    if ini < 0 or fim <= ini:
        return []
    try:
        return json.loads(texto[ini : fim + 1])
    except ValueError:
        # tenta remover vírgulas sobrando
        limpo = re.sub(r",\s*([\]}])", r"\1", texto[ini : fim + 1])
        try:
            return json.loads(limpo)
        except ValueError:
            return []


def extrair_questoes(paginas: list[list[str]], api_key: str, modelo: str, progresso=None) -> list[dict]:
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key, timeout=180)
    blocos: list[str] = []
    atual = ""
    for i, pg in enumerate(paginas):
        texto = f"\n--- página {i + 1} ---\n" + "\n".join(pg)
        if len(atual) + len(texto) > 14000 and atual:
            blocos.append(atual)
            atual = ""
        atual += texto
    if atual:
        blocos.append(atual)
    questoes: dict[int, dict] = {}
    for k, bloco in enumerate(blocos):
        msg = cliente.messages.create(
            model=modelo,
            max_tokens=16000,
            messages=[{"role": "user", "content": f"{PEDIDO_EXTRACAO}\n\n{bloco}"}],
        )
        texto = "".join(getattr(b, "text", "") for b in msg.content)
        for q in _json_array(texto):
            try:
                n = int(q.get("numero"))
            except (TypeError, ValueError):
                continue
            alts = {str(k2).upper()[:1]: str(v) for k2, v in (q.get("alternativas") or {}).items()}
            questoes[n] = {
                "numero": n,
                "enunciado": str(q.get("enunciado") or ""),
                "alternativas": alts,
                "tipo": "CE" if set(alts) == {"C", "E"} and alts.get("C", "").lower().startswith("cert") else "ME",
                "disciplina": str(q.get("disciplina") or "Geral"),
                "texto_base": str(q.get("texto_base") or ""),
                "pagina": 0,
            }
        if progresso:
            progresso((k + 1) / len(blocos))
    return [questoes[n] for n in sorted(questoes)]


SISTEMA_DUVIDA = """Você é um professor brasileiro que tira dúvidas de candidatos a concursos públicos.
Responda em português do Brasil, com linguagem simples e direta, à pergunta do candidato sobre a questão.
Pesquise na web quando a resposta depender de lei, norma, dado ou conceito técnico, e cite a fonte.
Se a pergunta revelar um erro de raciocínio, mostre onde está o erro. Use Markdown, no máximo 220 palavras."""


def responder_duvida(questao: dict, pergunta: str, historico: list[dict], api_key: str, modelo: str,
                     resultados: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Responde uma pergunta livre sobre a questão, lembrando as perguntas anteriores."""
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key, timeout=120)
    mensagens: list[dict] = []
    base = "Questão da prova:\n" + _formatar_questao(questao, None)
    if resultados:
        base += "\n\nResultados de uma busca prévia (use se forem úteis):\n" + "\n".join(
            f"- {r['titulo']} ({r['url']}): {r['trecho'][:300]}" for r in resultados[:5]
        )
    for i, h in enumerate(historico[-4:]):
        conteudo = (base + "\n\nMinha dúvida: " if i == 0 else "") + h["pergunta"]
        mensagens.append({"role": "user", "content": conteudo})
        mensagens.append({"role": "assistant", "content": h["resposta"]})
    mensagens.append({"role": "user", "content": (base + "\n\nMinha dúvida: " if not mensagens else "") + pergunta})
    msg = cliente.messages.create(model=modelo, max_tokens=1500, system=SISTEMA_DUVIDA, tools=[FERRAMENTA_BUSCA], messages=mensagens)
    return _texto_e_fontes(msg)


PEDIDO_GERAR = """Crie {n} questões INÉDITAS de múltipla escolha para concurso público brasileiro.
Disciplina: {disciplina}
Estilo da banca: {banca}
Concurso/órgão: {concurso}
Assuntos do edital (use os que forem desta disciplina): {assuntos}
{exemplos}
Regras:
- Nível de prova real dessa banca, com alternativas A, B, C, D e E e uma única resposta correta.
- Varie os assuntos e a letra da resposta correta.
- Não copie questões existentes; escreva questões novas.
- Para Língua Inglesa, inclua um pequeno texto em inglês no campo "texto_base" quando precisar.
- "explicacao": 1 a 3 frases dizendo por que a resposta está certa.
Responda SOMENTE com um array JSON, sem comentários:
[{{"enunciado": "...", "texto_base": "", "alternativas": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "gabarito": "C", "explicacao": "..."}}]"""


def _exemplos_texto(exemplos: list[dict]) -> str:
    if not exemplos:
        return ""
    partes = ["", "Questões REAIS de provas anteriores deste concurso/banca, para você seguir o estilo, o nível,",
              "o tamanho dos enunciados e os assuntos (NÃO copie nem parafraseie de perto; crie questões novas):"]
    for i, q in enumerate(exemplos[:8], start=1):
        alts = " | ".join(f"({k}) {v[:160]}" for k, v in (q.get("alternativas") or {}).items())
        gab = f" [resposta: {q['gabarito']}]" if q.get("gabarito") else ""
        partes.append(f"{i}. {q.get('enunciado', '')[:700]} {alts}{gab}")
    return "\n".join(partes) + "\n"


PEDIDO_CONFERIR = """Resolva cada questão abaixo, de forma independente, e responda SOMENTE com um array JSON
com a letra correta de cada uma, na mesma ordem, por exemplo ["B", "D", "A"]. Se uma questão tiver
mais de uma resposta defensável ou nenhuma correta, use "X" para ela.

{questoes}"""


def conferir_gabaritos(questoes: list[dict], api_key: str, modelo: str) -> list[str]:
    """Pede para a IA resolver as questões sem ver o gabarito. Devolve as letras (ou 'X')."""
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key, timeout=180)
    texto_q = "\n\n".join(
        f"Questão {i}:\n" + (f"Texto: {q['texto_base'][:1500]}\n" if q.get("texto_base") else "") + q["enunciado"] + "\n"
        + "\n".join(f"({k}) {v}" for k, v in q["alternativas"].items())
        for i, q in enumerate(questoes, start=1)
    )
    msg = cliente.messages.create(model=modelo, max_tokens=800, messages=[{"role": "user", "content": PEDIDO_CONFERIR.format(questoes=texto_q)}])
    letras = [str(x).upper()[:1] for x in _json_array("".join(getattr(b, "text", "") for b in msg.content))]
    return letras if len(letras) == len(questoes) else []


def gerar_questoes(
    disciplina: str,
    quantidade: int,
    api_key: str,
    modelo: str,
    banca: str = "",
    concurso: str = "",
    assuntos: str = "",
    exemplos: list[dict] | None = None,
    conferir: bool = True,
) -> list[dict]:
    """Questões novas no estilo da banca, para completar um simulado.

    Com `exemplos` (questões reais da biblioteca), a IA segue o estilo e os assuntos
    das provas anteriores. Com `conferir`, uma segunda chamada resolve as questões
    sem ver o gabarito e descarta as que não baterem.
    """
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key, timeout=180)
    feitas: list[dict] = []
    tentativas = 0
    exemplos = list(exemplos or [])
    while len(feitas) < quantidade and tentativas < 6:
        tentativas += 1
        n = min(10, quantidade - len(feitas))
        amostra = exemplos[(tentativas - 1) * 4 :][:8] or exemplos[:8]
        msg = cliente.messages.create(
            model=modelo,
            max_tokens=12000,
            messages=[
                {
                    "role": "user",
                    "content": PEDIDO_GERAR.format(
                        n=n,
                        disciplina=disciplina,
                        banca=banca or "bancas brasileiras em geral",
                        concurso=concurso or "não informado",
                        assuntos=(assuntos or "os assuntos mais cobrados dessa disciplina")[:4000],
                        exemplos=_exemplos_texto(amostra),
                    ),
                }
            ],
        )
        texto = "".join(getattr(b, "text", "") for b in msg.content)
        lote: list[dict] = []
        for q in _json_array(texto):
            alts = {str(k).upper()[:1]: str(v) for k, v in (q.get("alternativas") or {}).items()}
            gab = str(q.get("gabarito") or "").upper()[:1]
            if len(alts) < 4 or gab not in alts or not q.get("enunciado"):
                continue
            lote.append(
                {
                    "enunciado": str(q["enunciado"]),
                    "texto_base": str(q.get("texto_base") or ""),
                    "alternativas": alts,
                    "gabarito": gab,
                    "explicacao": str(q.get("explicacao") or ""),
                    "disciplina": disciplina,
                    "tipo": "ME",
                }
            )
        if conferir and lote:
            try:
                letras = conferir_gabaritos(lote, api_key, modelo)
            except Exception:  # noqa: BLE001 - se a conferência falhar, fica o lote como veio
                letras = []
            if letras:
                lote = [q for q, l in zip(lote, letras) if l == q["gabarito"]]
        feitas += lote
    return feitas[:quantidade]
