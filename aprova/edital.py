"""Edital verticalizado: os tópicos do edital, disciplina por disciplina, com o que já foi estudado.

A pessoa cola o conteúdo programático do edital (ou começa de um modelo). Cada tópico tem três marcas:
teoria, questões e revisão. A marca de questões se preenche sozinha quando o tópico corresponde a um
assunto que o app reconhece (ver assuntos.py) e a pessoa já resolveu questões suficientes dele;
o acerto nesse assunto aparece ao lado. Fica só neste aparelho (nos ajustes, chave "edital").
"""

from __future__ import annotations

import re

from . import assuntos
from .disciplinas import secao_de_linha, sem_acento

CAMPOS = ("teoria", "questoes", "revisao")
NOMES_CAMPOS = {"teoria": "Teoria", "questoes": "Questões", "revisao": "Revisão"}
AUTO_QUESTOES = 10  # questões resolvidas no assunto para a marca de questões se preencher sozinha
MAX_DISCIPLINAS = 40
MAX_TOPICOS = 150  # por disciplina
MAX_TEXTO = 240  # caracteres por tópico

_LIGACOES = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "na", "no", "nas", "nos", "para", "com", "por", "ao", "aos", "à", "às"}
_SIGLAS = {"ti", "sus", "lgpd", "rlm", "eca", "cf", "inss", "stf", "stj", "pcd", "ctb", "cpc", "cpp", "clt", "ia", "sql", "ux", "ui"}

# título de disciplina em caixa alta seguido de dois-pontos, no começo da linha ou no meio do texto
_PALAVRA_ALTA = r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ0-9\-–/]*"
_CABECALHO = re.compile(rf"^((?:{_PALAVRA_ALTA}\.?[ \t]+){{0,9}}{_PALAVRA_ALTA}\)?)[ \t]*:[ \t]*(.*)$")
_CABECALHO_NO_MEIO = re.compile(rf"(?<=[.;)])[ \t]+((?:{_PALAVRA_ALTA}[ \t]+){{0,9}}{_PALAVRA_ALTA})(?=[ \t]*:)")
# título em caixa mista no começo da linha: "Direito Constitucional: Princípios fundamentais; ..."
_CABECALHO_MISTO = re.compile(r"^([A-ZÀ-ÖØ-Þ][^:.;]{2,60}):[ \t]*(.*)$")
# item numerado: "1 Compreensão", "4.1 Emprego", "2) Ortografia", "3. Pontuação"
_NUMERO = re.compile(r"(?:(?<=\s)|^)(\d{1,2}(?:\.\d{1,2}){0,3})(?:[.)\-–]|\s*[.)\-–])?\s+(?=[A-ZÀ-ÖØ-Þ\"“(])")


# ---------------------------------------------------------------- ler o texto do edital


def _letras(t: str) -> list[str]:
    return [ch for ch in t if ch.isalpha()]


def _caixa_alta(t: str) -> bool:
    letras = _letras(t)
    return len(letras) >= 3 and sum(1 for ch in letras if ch.isupper()) / len(letras) >= 0.8


def nome_bonito(t: str) -> str:
    """'NOÇÕES DE INFORMÁTICA' -> 'Noções de Informática'; nomes em caixa mista ficam como estão."""
    t = re.sub(r"\s+", " ", t).strip(" :.-–")
    if not _caixa_alta(t):
        return t[:80]
    palavras = []
    for i, p in enumerate(t.split(" ")):
        base = p.lower()
        nucleo = re.sub(r"[^\wà-ÿ]", "", base)
        if nucleo in _SIGLAS or (nucleo and not re.search(r"[aeiouà-ÿ]", nucleo)):
            palavras.append(p.upper())
        elif i > 0 and nucleo in _LIGACOES:
            palavras.append(base)
        else:
            palavras.append(base[:1].upper() + base[1:])
    return " ".join(palavras)[:80]


def _cabecalho(linha: str) -> tuple[str, str] | None:
    """Se a linha começa com o nome de uma disciplina, devolve (nome, resto da linha)."""
    m = _CABECALHO.match(linha)
    if m and len(_letras(m.group(1))) >= 4 and _caixa_alta(m.group(1)):
        return m.group(1), m.group(2)
    m = _CABECALHO_MISTO.match(linha)
    if m and len(m.group(1).split()) <= 7 and secao_de_linha(m.group(1)):
        return m.group(1), m.group(2)
    if len(linha) <= 70 and not re.search(r"\d", linha):
        sem_dois_pontos = linha.rstrip(":").strip()
        if _caixa_alta(sem_dois_pontos) and len(sem_dois_pontos.split()) <= 10:
            return sem_dois_pontos, ""  # título sozinho na linha, em caixa alta
        if linha.endswith(":") and sem_dois_pontos[:1].isupper() and len(sem_dois_pontos.split()) <= 8:
            return sem_dois_pontos, ""  # "Conhecimentos Específicos:"
        if secao_de_linha(linha):
            return linha, ""  # "Língua Portuguesa" sozinho na linha
    return None


def _segue(anterior: tuple[int, ...] | None, atual: tuple[int, ...]) -> bool:
    """O número 'atual' pode vir logo depois de 'anterior' numa lista numerada (1 -> 2, 4 -> 4.1, 4.2 -> 5)?"""
    if anterior is None:
        return atual in ((1,), (0,)) or len(atual) == 1 and atual[0] <= 2
    if len(atual) == len(anterior) + 1 and atual[:-1] == anterior and atual[-1] == 1:
        return True
    for nivel in range(min(len(atual), len(anterior)), 0, -1):
        if len(atual) == nivel and atual[:-1] == anterior[: nivel - 1] and atual[-1] == anterior[nivel - 1] + 1:
            return True
    return False


def _limpar(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip(" \t.;,:-–")
    return t[:MAX_TEXTO].rstrip() + ("…" if len(t) > MAX_TEXTO else "")


def _topicos(texto: str) -> list[dict]:
    texto = re.sub(r"\s+", " ", texto).strip()
    if not texto:
        return []
    # 1) lista numerada, aceitando só números que seguem a sequência (não quebra "Lei 8.112 Estatuto")
    aceitos: list[tuple[int, int, tuple[int, ...]]] = []  # (início do número, início do texto, número)
    anterior = None
    for m in _NUMERO.finditer(texto):
        num = tuple(int(x) for x in m.group(1).split("."))
        antes = texto[: m.start()].rstrip()
        pontuado = not antes or antes[-1] in ".;:)"
        if _segue(anterior, num) and (pontuado or anterior is not None):
            aceitos.append((m.start(), m.end(), num))
            anterior = num
    if len(aceitos) >= 2:
        itens = []
        preambulo = _limpar(texto[: aceitos[0][0]])
        if len(_letras(preambulo)) >= 12:
            itens.append({"texto": preambulo, "nivel": 0})
        for i, (_, ini, num) in enumerate(aceitos):
            fim = aceitos[i + 1][0] if i + 1 < len(aceitos) else len(texto)
            t = _limpar(texto[ini:fim])
            if len(_letras(t)) >= 3:
                itens.append({"texto": t, "nivel": min(len(num) - 1, 2)})
        return itens
    # 2) sem números: separa por ";" ou por frases (". " seguido de maiúscula)
    if texto.count(";") >= 2:
        partes = texto.split(";")
    else:
        partes = re.split(r"(?<=[a-zà-ÿ0-9)\"”])\.\s+(?=[A-ZÀ-ÖØ-Þ])", texto)
    partes = [_limpar(re.sub(r"^\s*\d{1,2}(?:\.\d{1,2})*[.)\-–]?\s+", "", p)) for p in partes]  # "1 Código de Ética" (item único)
    return [{"texto": p, "nivel": 0} for p in partes if len(_letras(p)) >= 3]


def ler_texto(texto: str) -> list[dict]:
    """Conteúdo programático colado do edital -> [{"nome", "topicos": [{"texto", "nivel"}]}].

    Reconhece títulos em caixa alta ("LÍNGUA PORTUGUESA: 1 ... 2 ..."), títulos sozinhos na linha
    e listas numeradas (1, 1.1, 2...), por ponto e vírgula ou por frases."""
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").replace("\t", " ")
    texto = _CABECALHO_NO_MEIO.sub(lambda m: "\n" + m.group(1) if len(_letras(m.group(1))) >= 4 else m.group(0), texto)
    blocos: list[dict] = []
    atual: dict | None = None
    for bruta in texto.split("\n"):
        linha = bruta.strip(" •●▪◦-–*")
        if not linha:
            continue
        cab = _cabecalho(linha)
        if cab:
            atual = {"nome": nome_bonito(cab[0]), "texto": ""}
            blocos.append(atual)
            linha = cab[1]
            if not linha:
                continue
        if atual is None:
            atual = {"nome": "Conteúdo", "texto": ""}
            blocos.append(atual)
        atual["texto"] += " " + linha
    saida = []
    for b in blocos:
        topicos = _topicos(b["texto"])[:MAX_TOPICOS]
        if topicos:
            saida.append({"nome": b["nome"], "topicos": topicos})
    return saida[:MAX_DISCIPLINAS]


# ---------------------------------------------------------------- modelo pronto

MODELO = {
    "portugues": "Língua Portuguesa",
    "logica": "Raciocínio Lógico",
    "matematica": "Matemática",
    "informatica": "Informática",
    "constitucional": "Direito Constitucional",
    "administrativo": "Direito Administrativo",
}


def modelo_basico() -> list[dict]:
    """As disciplinas que mais caem, com os assuntos que o app já reconhece (para quem ainda não tem o edital)."""
    return [{"nome": nome, "topicos": [{"texto": a, "nivel": 0} for a, _ in assuntos._R[fam]]} for fam, nome in MODELO.items()]


# ---------------------------------------------------------------- edital guardado


def novo(concurso: str, disciplinas: list[dict], antigo: dict | None = None) -> dict:
    """Monta o edital para guardar. Se já havia um, mantém as marcas dos tópicos com o mesmo texto."""
    marcas: dict[tuple[str, str], dict] = {}
    for d in (antigo or {}).get("disciplinas") or []:
        for t in d.get("topicos") or []:
            marcas[(sem_acento(d.get("nome") or ""), sem_acento(t.get("texto") or ""))] = t
    saida = []
    for d in disciplinas[:MAX_DISCIPLINAS]:
        topicos = []
        for t in (d.get("topicos") or [])[:MAX_TOPICOS]:
            velho = marcas.get((sem_acento(d["nome"]), sem_acento(t["texto"]))) or {}
            topicos.append({"texto": t["texto"], "nivel": int(t.get("nivel") or 0), **{k: velho.get(k) for k in CAMPOS if velho.get(k) is not None}})
        saida.append({"nome": d["nome"], "topicos": topicos})
    return {"concurso": (concurso or "").strip()[:80], "disciplinas": saida}


def valido(ed) -> bool:
    return isinstance(ed, dict) and isinstance(ed.get("disciplinas"), list) and any(d.get("topicos") for d in ed["disciplinas"])


def disciplina_do_app(nome: str) -> str:
    """Nome da disciplina como o app guarda nas respostas ('NOÇÕES DE INFORMÁTICA' -> 'Informática')."""
    return secao_de_linha(nome) or secao_de_linha(nome.upper()) or nome


def vincular(banco, ed: dict) -> dict:
    """Acerto de cada tópico que corresponde a um assunto conhecido e de cada disciplina.

    {"topicos": {(i, j): {"assunto", "acertos", "total", "taxa"}}, "disciplinas": {i: {"acertos", "total", "taxa"}}}"""
    por_disciplina = {d["chave"]: d for d in banco.desempenho_por("disciplina")}
    topicos: dict[tuple[int, int], dict] = {}
    discs: dict[int, dict] = {}
    cache: dict[str, dict[str, dict]] = {}
    for i, d in enumerate(ed.get("disciplinas") or []):
        nome_app = disciplina_do_app(d["nome"])
        geral = por_disciplina.get(nome_app)
        if geral and geral.get("respondidas"):
            discs[i] = {"acertos": geral["acertos"], "total": geral["respondidas"], "taxa": geral["taxa"]}
        if assuntos.familia(nome_app) is None:
            continue
        if nome_app not in cache:
            cache[nome_app] = {x["assunto"]: x for x in assuntos.desempenho(banco, nome_app)}
        for j, t in enumerate(d.get("topicos") or []):
            a = assuntos.assunto(nome_app, t["texto"])
            if a != assuntos.OUTROS and a in cache[nome_app]:
                topicos[(i, j)] = cache[nome_app][a]
    return {"topicos": topicos, "disciplinas": discs}


def marcado(t: dict, campo: str, desempenho: dict | None = None) -> bool:
    """A marca está feita? Questões: o que a pessoa marcou ou, se ela não mexeu, o automático."""
    valor = t.get(campo)
    if valor is not None:
        return bool(valor)
    return campo == "questoes" and bool(desempenho) and desempenho["total"] >= AUTO_QUESTOES


def automatico(t: dict, desempenho: dict | None) -> bool:
    """A marca de questões veio sozinha (do que a pessoa resolveu no app)?"""
    return t.get("questoes") is None and marcado(t, "questoes", desempenho)


def progresso(ed: dict, vinculo: dict | None = None, so: int | None = None) -> dict:
    """{"feitas", "marcas", "completos", "topicos", "fracao"} do edital todo (ou só da disciplina 'so')."""
    vt = (vinculo or {}).get("topicos") or {}
    feitas = marcas = completos = n = 0
    for i, d in enumerate(ed.get("disciplinas") or []):
        if so is not None and i != so:
            continue
        for j, t in enumerate(d.get("topicos") or []):
            ok = [marcado(t, k, vt.get((i, j))) for k in CAMPOS]
            feitas += sum(ok)
            marcas += len(CAMPOS)
            completos += all(ok)
            n += 1
    return {"feitas": feitas, "marcas": marcas, "completos": completos, "topicos": n, "fracao": feitas / marcas if marcas else 0.0}
