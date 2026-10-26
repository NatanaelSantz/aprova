"""Comentário do resultado do simulado: o que foi bem, onde ganhar pontos e o próximo passo.

Escrito como um professor que torce por você: direto, específico e sem bronca. Funciona sem
internet e sem IA; com a chave do Claude, o app ainda pode pedir uma análise mais detalhada.
"""

from __future__ import annotations

MIN_POR_QUESTAO = 3 * 60  # nas provas de concurso, sobra perto de 3 minutos para cada questão


def _pct(a: int, t: int) -> int:
    return round(100 * a / t) if t else 0


def _tempo(seg: float) -> str:
    seg = int(round(seg))
    return f"{seg // 60} min {seg % 60:02d} s" if seg >= 60 else f"{seg} s"


def comentar(resultado: dict, erradas_por_disc: dict[str, int] | None = None) -> dict:
    """Monta o comentário. resultado: o do fim da prova (acertos, total, por_disc, duracao, respondidas).

    Devolve {"titulo", "paragrafos": [...], "forte": disciplina|None, "foco": disciplina|None}."""
    acertos, total = int(resultado.get("acertos") or 0), int(resultado.get("total") or 0)
    por_disc: dict[str, list[int]] = {d: list(v) for d, v in (resultado.get("por_disc") or {}).items() if v and v[1]}
    if not total:
        return {
            "titulo": "Prova registrada",
            "paragrafos": ["Essa prova ainda não tem gabarito, então não dá para corrigir. Cadastre as respostas oficiais para ver o que acertou."],
            "forte": None,
            "foco": None,
        }
    taxa = acertos / total
    if taxa >= 0.85:
        titulo = "Mandou muito bem!"
        abertura = f"Você acertou {acertos} de {total} ({_pct(acertos, total)}%). Esse é nível de aprovação: agora é manter o ritmo e não deixar o conteúdo esfriar."
    elif taxa >= 0.7:
        titulo = "Bom resultado!"
        abertura = f"Você acertou {acertos} de {total} ({_pct(acertos, total)}%). Está perto do nível de quem passa: os pontos que faltam estão nas matérias abaixo."
    elif taxa >= 0.5:
        titulo = "Você está no caminho"
        abertura = f"Você acertou {acertos} de {total} ({_pct(acertos, total)}%). Já tem base, e cada erro de hoje mostra exatamente o que estudar."
    else:
        titulo = "Simulado é para isso"
        abertura = (
            f"Você acertou {acertos} de {total} ({_pct(acertos, total)}%). Errar aqui é o que faz você acertar no dia da prova: "
            "cada questão errada já entrou na sua Revisão."
        )
    paragrafos = [abertura]

    # ponto forte: a matéria com mais acertos (com pelo menos 2 questões para valer)
    validas = {d: v for d, v in por_disc.items() if v[1] >= 2} or por_disc
    forte = max(validas, key=lambda d: (validas[d][0] / validas[d][1], validas[d][1]), default=None)
    foco = min(validas, key=lambda d: (validas[d][0] / validas[d][1], -validas[d][1]), default=None)
    if forte and validas[forte][0] / validas[forte][1] >= 0.7:
        a, t = validas[forte]
        paragrafos.append(f"Seu ponto forte hoje: {forte}, com {a} de {t}. Continue revisando para não perder o que já é seu.")
    else:
        forte = None
    if foco and foco != forte and validas[foco][0] < validas[foco][1]:
        a, t = validas[foco]
        erros = t - a
        paragrafos.append(
            f"Onde dá para ganhar mais pontos: {foco}. Você errou {erros} de {t}. "
            "Essas questões voltam na Revisão de amanhã, e um treino curto agora ajuda a fixar o que faltou."
        )
    else:
        foco = None

    respondidas = int(resultado.get("respondidas") or 0)
    em_branco = max(0, total - respondidas)
    if em_branco:
        paragrafos.append(f"Ficaram {em_branco} em branco. Na próxima, tente passar por todas antes de aprofundar nas difíceis.")
    duracao = float(resultado.get("duracao") or 0)
    if respondidas and duracao / max(respondidas, 1) > MIN_POR_QUESTAO * 1.3:
        paragrafos.append(
            f"Você levou em média {_tempo(duracao / respondidas)} por questão. Nas provas sobra perto de 3 minutos para cada uma: "
            "treinar com o cronômetro ajuda a chegar no ritmo."
        )
    return {"titulo": titulo, "paragrafos": paragrafos, "forte": forte, "foco": foco}


def erradas_por_disciplina(questoes: list[dict], respostas: dict[int, str], gabarito) -> dict[str, list[dict]]:
    """As questões erradas (e em branco) agrupadas por matéria, na ordem da prova.

    gabarito(q) devolve a letra certa (ou "*" se anulada / None se não tem)."""
    saida: dict[str, list[dict]] = {}
    for q in questoes:
        gab = gabarito(q)
        if not gab or gab == "*":
            continue
        resp = respostas.get(q["numero"])
        if resp == gab:
            continue
        saida.setdefault(q.get("disciplina") or "Geral", []).append(
            {
                "numero": q["numero"],
                "sua": resp,
                "certa": gab,
                "enunciado": " ".join(str(q.get("enunciado") or "").split()),
                "texto_certa": str((q.get("alternativas") or {}).get(gab) or ""),
                "explicacao": str(q.get("explicacao") or "").strip(),
            }
        )
    return saida
