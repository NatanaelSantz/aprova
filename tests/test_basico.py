"""Testes das partes sem interface: leitura do site, PDFs, gabarito e banco.

Rode com:  python -m pytest -q tests
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
FIX = RAIZ / "tests" / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (FIX / "escrevente-tj-sp-2023.pdf").exists():
        import gerar_fixtures  # noqa: F401

        gerar_fixtures.main()


def test_concursos_abertos(tmp_path):
    from aprova.pci import ClientePCI

    c = ClientePCI(cache_dir=tmp_path, fixtures=str(FIX))
    itens = c.concursos_abertos("sudeste")
    assert len(itens) == 12
    tj = itens[0]
    assert tj.uf == "SP" and tj.vagas == "132 vagas" and tj.salario.startswith("até R$")
    assert tj.prazo_inicio == "2026-10-28" and tj.prazo_fim == "2026-12-10"
    assert {i.uf for i in itens} == {"SP", "RJ", "MG"}


def test_edital_e_provas(tmp_path):
    from aprova.pci import ClientePCI

    c = ClientePCI(cache_dir=tmp_path, fixtures=str(FIX))
    tj = c.concursos_abertos("sudeste")[0]
    ed = c.edital(tj.url)
    assert ed.provas_url.endswith("/provas/tj-sp") and ed.pdfs
    itens, paginas = c.provas(ed.provas_url)
    assert len(itens) == 5 and paginas == 1 and itens[0].banca == "VUNESP"
    arquivos, navegador = c.arquivos_prova(itens[0].url)
    assert navegador and [a.tipo for a in arquivos] == ["prova", "gabarito"]


def test_prazos():
    from aprova.pci import interpretar_prazo

    assert interpretar_prazo("03 a 06/11/2026") == ("2026-11-03", "2026-11-06")
    assert interpretar_prazo("Prorrogado até 13/10/2026") == (None, "2026-10-13")
    assert interpretar_prazo("01/12/2026 a 07/01/2027") == ("2026-12-01", "2027-01-07")


def test_questoes_do_pdf():
    from aprova import pdfprova

    r = pdfprova.extrair_questoes(FIX / "escrevente-tj-sp-2023.pdf")
    assert [q.numero for q in r.questoes] == list(range(1, 9))
    assert all(len(q.alternativas) == 5 for q in r.questoes)
    assert r.questoes[0].texto_base.startswith("A leitura diária")
    assert r.questoes[3].disciplina == "Informática"
    assert "CONCURSO PÚBLICO" not in r.questoes[-1].enunciado


def test_gabarito_por_cargo():
    from aprova import pdfprova

    g = pdfprova.ler_gabarito_pdf(FIX / "gabaritos.pdf", 8, "Escrevente Técnico Judiciário")
    assert g == {1: "B", 2: "C", 3: "A", 4: "B", 5: "C", 6: "C", 7: "C", 8: "B"}
    assert pdfprova.gabarito_de_texto_livre("1A 2b 3-x") == {1: "A", 2: "B", 3: "*"}


def test_importar_e_estatisticas(tmp_path, monkeypatch):
    from aprova import config, db, importador

    monkeypatch.setattr(config, "PROVAS_DIR", tmp_path / "provas")
    banco = db.Banco(tmp_path / "t.db")
    aj = config.Ajustes(tmp_path / "aj.json")
    res = importador.importar(banco, aj, FIX / "escrevente-tj-sp-2023.pdf", FIX / "gabaritos.pdf", {"cargo": "Escrevente Técnico Judiciário"})
    assert res["modo"] == "questoes" and res["n_gabarito"] == 8
    t = banco.iniciar_tentativa(res["prova_id"], "simulado")
    banco.registrar_resposta(t, 1, "Língua Portuguesa", "B", True)
    banco.registrar_resposta(t, 2, "Língua Portuguesa", "A", False)
    banco.finalizar_tentativa(t, 60, 1, 2)
    est = banco.estatisticas()
    assert est["respondidas"] == 2 and est["taxa"] == 0.5 and est["sequencia"] == 1
    assert banco.prioridades()[0]["disciplina"] == "Língua Portuguesa"


def test_ajuda_sem_internet(monkeypatch):
    from aprova import ajuda, config

    monkeypatch.setattr(config, "FIXTURES_DIR", str(FIX))
    q = {"enunciado": "A palavra 'rapidamente' expressa circunstância de:", "alternativas": {"A": "lugar", "B": "modo"}, "disciplina": "Língua Portuguesa"}
    dados = ajuda.obter_ajuda(q, "dica", None)
    assert dados["fontes"] and "Como pensar" in dados["texto"] and "rapidamente" in dados["consulta"]


def test_montar_simulado(tmp_path, monkeypatch):
    from aprova import amostras, config, db, importador, montador

    monkeypatch.setattr(config, "PROVAS_DIR", tmp_path / "provas")
    banco = db.Banco(tmp_path / "t.db")
    aj = config.Ajustes(tmp_path / "aj.json")
    amostras.instalar(banco)
    importador.importar(banco, aj, FIX / "escrevente-tj-sp-2023.pdf", FIX / "gabaritos.pdf", {"orgao": "TJ/SP", "cargo": "Escrevente Técnico Judiciário"})
    so_tj = montador.montar(banco, aj, "TJ", [("Língua Portuguesa", 3), ("Informática", 2)], filtro="TJ/SP", usar_outras=False)
    assert so_tj["total"] == 5 and not so_tj["faltas"]
    assert all("questão" in q["fonte"] for q in banco.questoes(so_tj["prova_id"]))
    dataprev = montador.MODELOS["Dataprev 2026 (FGV) — 70 questões"]
    assert sum(n for _, n in dataprev["disciplinas"]) == 70
    r = montador.montar(banco, aj, "Dataprev", dataprev["disciplinas"], filtro="Dataprev", banca="FGV")
    assert r["faltas"]["Língua Inglesa"] == 12 and r["total"] == r["da_biblioteca"]


def test_busca_central_fgv(tmp_path, monkeypatch):
    from aprova import config, fontes
    from aprova.pci import ClientePCI

    monkeypatch.setattr(config, "FIXTURES_DIR", str(FIX))
    cen = fontes.Centralizador(ClientePCI(cache_dir=tmp_path, fixtures=str(FIX)))
    lista = cen.concursos_fgv()
    assert {c.situacao for c in lista} == {"em andamento", "realizado"}
    r = cen.buscar("Dataprev 2026")
    assert r.paginas_oficiais[0].url.endswith("/dataprev26")
    tipos = {a.titulo: a.tipo for a in r.oficiais}
    assert tipos["Gabarito Oficial Preliminar da Prova Objetiva"] == "gabarito"
    assert tipos["Edital (retificado em 29/07/2026)"] == "edital"
    grupos = fontes.agrupar_por_cargo(r.oficiais)
    dev = next(g for g in grupos if "DESENVOLVIMENTO" in g["cargo"])
    assert [a.caderno for a in dev["cadernos"]] == ["1", "2"] and dev["gabarito"].tipo == "gabarito"
    assert any(a.tipo == "comentada" for a in r.web)


def test_prova_fgv_e_gabarito_por_caderno(tmp_path, monkeypatch):
    from aprova import config, db, importador, pdfprova

    r = pdfprova.extrair_questoes(FIX / "fgv-desenvolvimento-tipo-1.pdf")
    assert len(r.questoes) == 8 and r.aproveitavel
    assert [q.disciplina for q in r.questoes][::2] == ["Língua Portuguesa", "Língua Inglesa", "Raciocínio Lógico", "Conhecimentos Específicos"]
    monkeypatch.setattr(config, "PROVAS_DIR", tmp_path / "provas")
    banco = db.Banco(tmp_path / "t.db")
    res = importador.importar(
        banco, config.Ajustes(tmp_path / "a.json"), FIX / "fgv-desenvolvimento-tipo-1.pdf", FIX / "fgv-gabaritos.pdf",
        {"cargo": "DESENVOLVIMENTO DE SOFTWARE", "caderno": "2"},
    )
    assert {q["gabarito"] for q in banco.questoes(res["prova_id"])} == {"C"}


def test_busca_tenta_outros_buscadores(monkeypatch, tmp_path):
    import ddgs
    from ddgs.exceptions import DDGSException

    from aprova import ajuda, config

    monkeypatch.setattr(config, "FIXTURES_DIR", None)
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "aprova.log")
    chamados = []

    def fabrica(funciona):
        class Falso:
            def __init__(self, **kw):
                pass

            def text(self, consulta, backend="auto", **kw):
                chamados.append(backend)
                if backend in funciona:
                    return [{"title": "Prova", "href": "https://x.com/p.pdf", "body": "..."}]
                if funciona == "nada":
                    raise DDGSException("No results found.")
                raise DDGSException("Ratelimit 202")

        return Falso

    monkeypatch.setattr(ddgs, "DDGS", fabrica({"mojeek"}))
    assert ajuda.pesquisar_web("dataprev")[0]["url"] == "https://x.com/p.pdf"
    assert "," in chamados[0] and chamados[-1] == "mojeek"

    monkeypatch.setattr(ddgs, "DDGS", fabrica("nada"))
    assert ajuda.pesquisar_web("dataprev") == []

    monkeypatch.setattr(ddgs, "DDGS", fabrica(set()))
    import pytest

    with pytest.raises(ajuda.BuscaIndisponivel):
        ajuda.pesquisar_web("dataprev", limite_s=5)
    assert "Ratelimit" in (tmp_path / "aprova.log").read_text(encoding="utf-8")


def test_encher_biblioteca_do_concurso(tmp_path, monkeypatch):
    from aprova import coleta, config, db, fontes
    from aprova.pci import ClientePCI

    monkeypatch.setattr(config, "FIXTURES_DIR", str(FIX))
    monkeypatch.setattr(config, "PROVAS_DIR", tmp_path / "provas")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    banco = db.Banco(tmp_path / "t.db")
    pci = ClientePCI(cache_dir=tmp_path / "cache", fixtures=str(FIX))
    cen = fontes.Centralizador(pci)

    assert [c.url.rsplit("/", 1)[-1] for c in cen.edicoes("Dataprev 2026")] == ["dataprev26", "dataprev23"]
    plano = coleta.planejar(cen, banco, "Dataprev 2026")
    assert plano.edicoes() == ["Dataprev 2026", "Dataprev 2023"]
    assert all(i.prova.caderno == "1" for i in plano.itens)  # um caderno por cargo
    assert all(i.gabarito is not None for i in plano.itens)

    rel = coleta.coletar(banco, config.Ajustes(tmp_path / "a.json"), pci, plano, [i for i in plano.itens if i.marcado])
    assert rel.provas == 3 and len(rel.falhas) == 1  # a de infraestrutura não tem PDF no exemplo
    assert rel.questoes == 22 and rel.repetidas == 8 and rel.novas == 14 and rel.com_gabarito == 22
    # nos simulados, a questão repetida entre cargos aparece uma vez só
    assert len(banco.banco_de_questoes()) == 14 and len(banco.banco_de_questoes(unicas=False)) == 22
    assert banco.resumo_biblioteca("Dataprev") == {"provas": 3, "questoes": 14, "com_gabarito": 14}
    # rodando de novo, o que já está na biblioteca vem desmarcado
    de_novo = coleta.planejar(cen, banco, "Dataprev 2026")
    assert [i.cargo for i in de_novo.itens if i.marcado] == ["Analista de Infraestrutura"]


def test_nomes_de_concurso():
    from aprova import coleta

    assert coleta.nome_curto("Concurso Público para a Empresa de Tecnologia e Informações da Previdência - DATAPREV") == "Dataprev"
    assert coleta.nome_curto("Concurso Público DATAPREV 2023") == "Dataprev"
    assert coleta.ano_de("Concurso X", "https://conhecimento.fgv.br/concursos/tjpb26") == "2026"
    assert coleta.bonito("ANALISTA DE TECNOLOGIA DA INFORMAÇÃO") == "Analista de Tecnologia da Informação"


def _banco_com_historico(tmp_path):
    """Banco com uma prova, respostas em semanas diferentes e tempo de estudo."""
    from datetime import date, timedelta

    from aprova import db

    banco = db.Banco(tmp_path / "h.db")
    pid = banco.criar_prova(titulo="Prova X", orgao="Dataprev 2026", banca="FGV", origem_url="https://x/p.pdf", modo="questoes")
    qs = []
    for i in range(1, 11):
        qs.append({"numero": i, "enunciado": f"Pergunta {i} sobre assunto {i} cobrado na prova", "alternativas": {"A": "a", "B": "b", "C": "c", "D": "d"}, "gabarito": "A",
                   "disciplina": "Língua Portuguesa" if i <= 6 else "Raciocínio Lógico"})
    banco.salvar_questoes(pid, qs)
    t = banco.iniciar_tentativa(pid, "simulado")
    for i in range(1, 11):
        # Português: acerta 5 de 6 (forte); Raciocínio: erra 4 de 4 (fraco, mas poucos dados)
        certo = i <= 5
        banco.registrar_resposta(t, i, qs[i - 1]["disciplina"], "A" if certo else "B", certo)
        banco.revisao_registrar(pid, i, qs[i - 1]["disciplina"], certo)
    banco.finalizar_tentativa(t, 1800, 5, 10)
    hoje = date.today()
    banco.somar_tempo(3600, "app", "Língua Portuguesa", hoje.isoformat())
    banco.somar_tempo(1800, "cronometro", "Leitura da LGPD", (hoje - timedelta(days=1)).isoformat())
    return banco, pid, hoje


def test_painel_tempo_e_desempenho(tmp_path):
    from datetime import timedelta

    from aprova import analise

    banco, pid, hoje = _banco_com_historico(tmp_path)
    r = analise.resumo_tempo(banco, hoje, meta_horas=10, planejados=[0, 1, 2, 3, 4])
    assert r["meta_dia"] == 2 * 3600 and r["hoje_segundos"] == 3600
    assert r["semana"][hoje.weekday()]["hoje"] and r["semana"][hoje.weekday()]["questoes"] == 10
    ontem_na_semana = hoje.weekday() > 0
    assert r["total_semana"] == 3600 + (1800 if ontem_na_semana else 0)
    assert r["sequencia"] >= 1
    previsto = sum(x["meta"] for x in r["semana"] if x["dia"] < hoje)
    assert r["saldo"] == r["total_semana"] - previsto
    assert len(r["semanas"]) == 12 and len(r["por_dia_semana"]) == 7

    d = analise.resumo_desempenho(banco, hoje)
    assert d["respondidas"] == 10 and d["acertos"] == 5
    niveis = {x["chave"]: x["nivel"] for x in d["disciplinas"]}
    assert niveis == {"Língua Portuguesa": "forte", "Raciocínio Lógico": "poucos"}
    assert d["semanas"][-1]["respondidas"] == 10
    assert d["bancas"][0]["nome"] == "FGV" and d["concursos"][0]["nome"] == "Dataprev 2026"
    assert analise.classificar(0.4, 10) == "fraco" and analise.classificar(0.6, 10) == "atencao"
    assert analise.fmt_duracao(5400) == "1h30"
    _ = timedelta


def test_revisao_espacada(tmp_path):
    from datetime import date, timedelta

    from aprova import sessoes

    banco, pid, hoje = _banco_com_historico(tmp_path)
    r = banco.revisao_resumo()
    assert r["ativas"] == 5 and r["pendentes"] == 0 and r["amanha"] == 5  # erros voltam amanhã
    # marcar para revisar coloca hoje
    banco.revisao_adicionar(pid, 1, "Língua Portuguesa")
    assert banco.revisao_resumo()["pendentes"] == 1
    sessao = sessoes.preparar_revisao(banco)
    qs = banco.questoes(sessao)
    assert len(qs) == 1 and qs[0]["ref"] == f"{pid}:1"
    # acertar na sessão sobe de caixa (pela referência, na questão original)
    banco.revisao_registrar(sessao, 1, "Língua Portuguesa", True, qs[0]["ref"])
    caixa = banco._q("SELECT caixa, proxima FROM revisao WHERE prova_id=? AND numero=1", (pid,))[0]
    assert caixa["caixa"] == 2 and caixa["proxima"] == (date.today() + timedelta(days=3)).isoformat()
    # a sessão de revisão não entra no banco de questões dos simulados
    assert all(q["prova_id"] != sessao for q in banco.banco_de_questoes())
    # revisar todos os erros agora (sem esperar o dia)
    todas = sessoes.preparar_revisao(banco, todas=True)
    assert len(banco.questoes(todas)) == 6  # 5 erros + a marcada (agora na caixa 2)
    treino = sessoes.preparar_treino(banco, "Raciocínio Lógico", 3)
    assert len(banco.questoes(treino)) == 3
    sug = sessoes.proximo_estudo(banco)
    assert sug and sug["tipo"] in ("revisao", "treino")


def test_lembretes_disparam_na_hora(tmp_path):
    from datetime import datetime

    from aprova.ui.app import devido

    seg = datetime(2026, 10, 26, 19, 10)  # segunda-feira
    lem = {"hora": "19:00", "dias": "0,2,4", "data": "", "ultimo": ""}
    assert devido(lem, seg)
    assert not devido(lem, seg.replace(hour=18, minute=59))
    assert not devido(lem, seg.replace(hour=20, minute=30))  # passou mais de 1 hora
    assert not devido({**lem, "ultimo": "2026-10-26 19:00"}, seg)  # já tocou hoje
    assert not devido(lem, datetime(2026, 10, 27, 19, 5))  # terça não está nos dias
    assert devido({"hora": "07:30", "dias": "", "data": "2026-10-27", "ultimo": ""}, datetime(2026, 10, 27, 7, 31))

    from aprova import db

    banco = db.Banco(tmp_path / "l.db")
    lid = banco.salvar_lembrete({"titulo": "Revisão", "hora": "20:00", "dias": "0,1,2,3,4", "alvo_tipo": "revisao", "alvo": ""})
    banco.marcar_lembrete(lid, "2026-10-26 20:00")
    assert banco.lembretes()[0]["ultimo"] == "2026-10-26 20:00"


def test_duvida_sem_chave_usa_a_busca(tmp_path, monkeypatch):
    from aprova import ajuda, config, db

    monkeypatch.setattr(config, "FIXTURES_DIR", str(FIX))
    q = {"enunciado": "Segundo a LGPD, quem decide sobre o tratamento de dados pessoais?", "alternativas": {"A": "operador", "B": "controlador"}, "disciplina": "Segurança da Informação"}
    r = ajuda.tirar_duvida(q, "por que não é o operador?", [], config.Ajustes(tmp_path / "a.json"))
    assert r["via"] == "busca" and r["fontes"] and "chave do Claude" in r["texto"]
    banco = db.Banco(tmp_path / "d.db")
    banco.salvar_duvida(7, 3, q["disciplina"], q["enunciado"], "por que não é o operador?", r["texto"], r["fontes"], r["via"])
    assert banco.duvidas(7, 3)[0]["pergunta"].startswith("por que") and banco.duvidas()[0]["fontes"]


def test_simulado_guarda_referencia_e_exemplos_para_ia(tmp_path):
    from aprova import config, montador

    banco, pid, _ = _banco_com_historico(tmp_path)
    res = montador.montar(banco, config.Ajustes(tmp_path / "a.json"), "S", [("Língua Portuguesa", 3)], filtro="Dataprev")
    refs = [q["ref"] for q in banco.questoes(res["prova_id"])]
    assert len(refs) == 3 and all(r.startswith(f"{pid}:") for r in refs)
    ex = montador.exemplos_para(banco.banco_de_questoes(), "Língua Portuguesa", "Dataprev", "FGV")
    assert ex and all(e["disciplina"] == "Língua Portuguesa" for e in ex)
    assert montador.distribuicao_do_concurso(banco, "Dataprev", 10) == [("Língua Portuguesa", 6), ("Raciocínio Lógico", 4)]


def test_meta_comeca_no_primeiro_dia_de_uso(tmp_path):
    from datetime import date, timedelta

    from aprova import analise, db

    banco = db.Banco(tmp_path / "m.db")
    sabado = date(2026, 10, 24)
    r = analise.resumo_tempo(banco, sabado, meta_horas=10, planejados=list(range(7)), inicio=sabado)
    # quem começa no sábado não fica "devendo" segunda a sexta
    assert r["saldo"] == 0 and r["previsto_ate_ontem"] == 0
    assert r["proporcional"] and r["meta_segundos"] == 2 * (10 * 3600 // 7) and r["meta_dias"] == 2
    assert [x["situacao"] for x in r["semana"][:5]] == ["antes"] * 5
    # semana seguinte: meta cheia
    r2 = analise.resumo_tempo(banco, sabado + timedelta(days=2), meta_horas=10, planejados=list(range(7)), inicio=sabado)
    assert not r2["proporcional"] and r2["meta_segundos"] == 36000


def test_ranking_cadastro_envio_e_grupos(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import config, ranking

    srv = ServidorFalso().iniciar()
    try:
        semana = ranking.inicio_semana().isoformat()
        srv.semear([("Camila", "Dataprev", {"segundos": 50000, "questoes": 400, "acertos": 300, "dias": 6, "sequencia": 10}),
                    ("Rafa", "INSS", {"segundos": 9000, "questoes": 20, "acertos": 19, "dias": 2, "sequencia": 1})], semana)
        aj = config.Ajustes(tmp_path / "a.json")
        r = ranking.Ranking(aj, {"url": srv.url, "chave": CHAVE})
        assert r.configurado and not r.logado
        assert r.criar_conta("eu@exemplo.com", "segredo1", "Natan", "Dataprev 2026") == "ok"
        assert r.logado and r.apelido == "Natan"
        # apelido repetido e e-mail repetido viram mensagens claras
        outro = ranking.Ranking(config.Ajustes(tmp_path / "b.json"), {"url": srv.url, "chave": CHAVE})
        try:
            outro.criar_conta("eu@exemplo.com", "segredo1", "Outro")
            raise AssertionError("devia falhar")
        except ranking.ErroRanking as e:
            assert "Já existe uma conta" in str(e)
        outro.criar_conta("outro@exemplo.com", "segredo1", "Fulano")
        try:
            outro.salvar_perfil("natan")
            raise AssertionError("devia falhar")
        except ranking.ErroRanking as e:
            assert "apelido já está em uso" in str(e)
        # envia os números da semana (banco com histórico)
        banco, _, _ = _banco_com_historico(tmp_path)
        r.enviar(banco)
        lista = r.ranking("horas")
        assert [l["apelido"] for l in lista][:1] == ["Camila"] and any(l["voce"] and l["apelido"] == "Natan" for l in lista)
        eu = next(l for l in lista if l["voce"])
        assert eu["questoes"] == 10 and eu["acertos"] == 5
        # acerto exige um mínimo de questões (Rafa tem 20, fica de fora)
        assert "Rafa" not in [l["apelido"] for l in r.ranking("acerto")]
        # grupos por código
        codigo = r.criar_grupo("Turma Dataprev")
        assert re.match(r"^[A-Z0-9]+-[A-HJ-NP-Z2-9]{6}$", codigo)  # 6 letras/números: não dá para adivinhar
        # quem não é do grupo não lista os códigos nem entra sem o convite
        assert outro._pedir("GET", "/rest/v1/grupos?select=codigo").json() == []
        assert outro._pedir("GET", "/rest/v1/membros?select=codigo").json() == []
        with pytest.raises(ranking.ErroRanking):
            outro._pedir("POST", "/rest/v1/membros", json={"codigo": codigo, "usuario_id": outro.usuario_id})
        with pytest.raises(ranking.ErroRanking, match="inválido"):
            outro.entrar_grupo("X&usuario_id=neq.0")  # nada de filtro enfiado no código
        assert outro.meus_grupos() == []
        outro.entrar_grupo(codigo.lower())
        nomes = [l["apelido"] for l in r.ranking("horas", grupo=codigo)]
        assert set(nomes) == {"Natan"}  # Fulano ainda não enviou números
        assert r.meus_grupos()[0]["nome"] == "Turma Dataprev"
        assert [g["codigo"] for g in outro.meus_grupos()] == [codigo]
        # servidor ainda sem o SQL da 1.12: entrar continua funcionando do jeito antigo
        srv.dados.sem_entrar_no_grupo = True
        cod_velho = r.criar_grupo("Grupo antigo")
        assert outro.entrar_grupo(cod_velho)["nome"] == "Grupo antigo"
        srv.dados.sem_entrar_no_grupo = False
        # sessão continua depois de reabrir o app (só com o token salvo)
        r2 = ranking.Ranking(config.Ajustes(tmp_path / "a.json"), {"url": srv.url, "chave": CHAVE})
        assert r2.logado and r2.perfil()["apelido"] == "Natan"
        # senha errada
        try:
            ranking.Ranking(config.Ajustes(tmp_path / "c.json"), {"url": srv.url, "chave": CHAVE}).entrar("eu@exemplo.com", "errada")
            raise AssertionError("devia falhar")
        except ranking.ErroRanking as e:
            assert "incorretos" in str(e)
        # apagar a conta remove tudo
        r2.apagar_conta()
        assert not r2.logado and "Natan" not in [p["apelido"] for p in srv.dados.tabelas["perfis"]]
    finally:
        srv.parar()


def test_ranking_config_e_apelido(tmp_path):
    from aprova import ranking

    arq = tmp_path / "ranking.json"
    assert ranking.carregar_config(arq) == {}
    ranking.salvar_config("https://abc.supabase.co/", "x" * 40, arq)
    assert ranking.carregar_config(arq)["url"] == "https://abc.supabase.co"
    for ruim in ("ab", "x" * 30, "nome<script>"):
        try:
            ranking.validar_apelido(ruim)
            raise AssertionError(ruim)
        except ranking.ErroRanking:
            pass
    assert ranking.validar_apelido("  João   da Silva ") == "João da Silva"


def test_contas_admin_e_aluno(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import config, ranking

    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        semana = ranking.inicio_semana().isoformat()
        srv.semear([("Camila", "Dataprev", {"segundos": 50000, "questoes": 400, "acertos": 300, "dias": 6, "sequencia": 10})], semana)
        # o primeiro cadastro vira administrador
        adm = ranking.Ranking(config.Ajustes(tmp_path / "adm.json"), cfg)
        adm.criar_conta("adm@exemplo.com", "segredo1", "Natan", "Dataprev")
        assert adm.eh_admin and adm.papel == "admin"
        # o segundo é aluno e não consegue se promover
        aluno = ranking.Ranking(config.Ajustes(tmp_path / "aluno.json"), cfg)
        aluno.criar_conta("aluno@exemplo.com", "segredo1", "Joana")
        assert not aluno.eh_admin
        aluno._pedir("PATCH", f"/rest/v1/perfis?id=eq.{aluno.usuario_id}", json={"papel": "admin"})
        assert aluno.atualizar_perfil()["papel"] == "aluno"
        with pytest.raises(ranking.ErroRanking):
            aluno.usuarios()
        # admin vê todos e a visão geral
        us = adm.usuarios()
        assert {u["apelido"] for u in us} == {"Natan", "Joana", "Camila"}
        vg = adm.visao_geral(us)
        assert vg["usuarios"] == 3 and vg["ativos"] == 1 and vg["admins"] == 1
        # bloquear tira do ranking
        camila = next(u for u in us if u["apelido"] == "Camila")
        adm.bloquear(camila["id"], True)
        assert "Camila" not in [l["apelido"] for l in aluno.ranking("horas")]
        adm.bloquear(camila["id"], False)
        assert "Camila" in [l["apelido"] for l in aluno.ranking("horas")]
        # promover aluno
        adm.definir_papel(aluno.usuario_id, "admin")
        assert aluno.atualizar_perfil()["papel"] == "admin" and aluno.eh_admin
        adm.definir_papel(aluno.usuario_id, "aluno")
        with pytest.raises(ranking.ErroRanking):
            adm.definir_papel(adm.usuario_id, "aluno")  # não tira o próprio acesso
        # comunicados: admin escreve, aluno lê só os ativos
        adm.criar_comunicado("Simulado no sábado", "Simulado da Dataprev às 9h.")
        assert [c["titulo"] for c in aluno.comunicados()] == ["Simulado no sábado"]
        cid = adm.comunicados(todos=True)[0]["id"]
        adm.ativar_comunicado(cid, False)
        assert aluno.comunicados() == [] and len(adm.comunicados(todos=True)) == 1
        with pytest.raises(ranking.ErroRanking):
            aluno.atualizar_perfil()
            aluno.criar_comunicado("Oi", "teste")
        # grupos: admin vê e apaga
        cod = aluno.criar_grupo("Amigos do TI")
        assert next(g for g in adm.todos_grupos() if g["codigo"] == cod)["membros"] == 1
        adm.apagar_grupo(cod)
        assert all(g["codigo"] != cod for g in adm.todos_grupos())
    finally:
        srv.parar()


def test_estudos_separados_por_conta(tmp_path, monkeypatch):
    from aprova import config
    from aprova.ui import app as A

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    A._BANCOS.clear()
    visitante = A.banco_em(A.pasta_dados(None) / "aprova.db")
    pid = visitante.criar_prova(titulo="Minha prova", origem_url="https://x/p.pdf", modo="questoes")
    visitante.salvar_questoes(pid, [{"numero": 1, "enunciado": "Q", "alternativas": {"A": "a", "B": "b"}, "gabarito": "A", "disciplina": "Língua Portuguesa"}])
    t = visitante.iniciar_tentativa(pid, "estudo")
    visitante.registrar_resposta(t, 1, "Língua Portuguesa", "A", True)
    # outra conta começa vazia (só o simulado de demonstração)
    outra = A.banco_em(A.pasta_dados("conta-b") / "aprova.db")
    assert outra.estatisticas()["respondidas"] == 0
    # levar os estudos para a conta A copia tudo e mantém o original
    falso = type("F", (), {})()
    falso.sessao = config.Ajustes(tmp_path / "sessao.json")
    A.App._levar_estudos_para(falso, "conta-a")
    conta_a = A.banco_em(A.pasta_dados("conta-a") / "aprova.db")
    assert conta_a.estatisticas()["respondidas"] == 1
    assert any(p["titulo"] == "Minha prova" for p in conta_a.provas())
    assert visitante.estatisticas()["respondidas"] == 1
    assert falso.sessao.get("estudos_levados_para") == "conta-a"
    A._BANCOS.clear()


def test_forum_do_grupo(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import config, ranking

    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        adm = ranking.Ranking(config.Ajustes(tmp_path / "adm.json"), cfg)
        adm.criar_conta("adm@exemplo.com", "segredo1", "Natan")
        dono = ranking.Ranking(config.Ajustes(tmp_path / "dono.json"), cfg)
        dono.criar_conta("dono@exemplo.com", "segredo1", "Camila")
        aluno = ranking.Ranking(config.Ajustes(tmp_path / "aluno.json"), cfg)
        aluno.criar_conta("aluno@exemplo.com", "segredo1", "Joana")
        fora = ranking.Ranking(config.Ajustes(tmp_path / "fora.json"), cfg)
        fora.criar_conta("fora@exemplo.com", "segredo1", "Pedro")

        cod = dono.criar_grupo("Turma Dataprev")
        aluno.entrar_grupo(cod)
        assert next(g for g in dono.meus_grupos() if g["codigo"] == cod)["modero"]
        assert not next(g for g in aluno.meus_grupos() if g["codigo"] == cod)["modero"]
        assert [m["apelido"] for m in aluno.membros_grupo(cod)] == ["Camila", "Joana"]  # quem criou vem primeiro

        # conversa: só membros leem e escrevem
        aluno.forum_publicar(cod, "Alguém topa simulado no sábado?")
        with pytest.raises(ranking.ErroRanking):
            fora.forum_publicar(cod, "posso entrar?")
        assert fora.forum(cod) == []
        assert len(adm.forum(cod)) == 1  # admin modera todos os grupos
        post = dono.forum(cod)[0]
        assert post["apelido"] == "Joana" and not post["meu"] and post["tipo"] == "conversa"

        # plano de estudo
        with pytest.raises(ranking.ErroRanking):
            dono.forum_publicar(cod, "", "plano", "Plano", {"disciplinas": [], "dias": [0]})
        dono.forum_publicar(
            cod, "Sábado é simulado.", "plano", "Plano 10h",
            {"disciplinas": [{"nome": "Língua Portuguesa", "horas": "4"}, {"nome": "Informática", "horas": 6}], "dias": [0, 2, 4]},
        )
        planos = aluno.forum(cod, tipo="plano")
        assert len(planos) == 1 and planos[0]["plano"]["meta_horas"] == 10 and planos[0]["plano"]["dias"] == [0, 2, 4]
        assert [p["tipo"] for p in aluno.forum(cod, tipo="conversa")] == ["conversa"]

        # respostas e "útil"
        aluno.forum_responder(planos[0]["id"], "Vou seguir!")
        aluno.forum_util(planos[0]["id"], True)
        aluno.forum_util(planos[0]["id"], True)  # marcar duas vezes não dá erro
        p = aluno.forum(cod, tipo="plano")[0]
        assert p["respostas"] == 1 and p["uteis"] == 1 and p["util_meu"]
        assert aluno.forum_respostas(p["id"])[0]["apelido"] == "Joana"
        aluno.forum_util(p["id"], False)
        assert not aluno.forum(cod, tipo="plano")[0]["util_meu"]

        # moderação: aluno não fixa nem apaga a mensagem dos outros; quem criou o grupo pode
        aluno.forum_fixar(p["id"], True)
        aluno.forum_apagar(p["id"])
        p = dono.forum(cod, tipo="plano")[0]
        assert not p["fixado"]
        conversa = dono.forum(cod, tipo="conversa")[0]
        dono.forum_fixar(conversa["id"], True)
        assert dono.forum(cod)[0]["id"] == conversa["id"] and dono.forum(cod)[0]["fixado"]  # fixada vem primeiro

        # novidades: conta as mensagens dos outros desde a última visita
        novas = aluno.forum_novidades([cod], {})
        assert novas == {cod: 1}  # o plano da Camila (a conversa é da própria Joana)
        visto = aluno.forum(cod)[0]["criado_em"]
        assert aluno.forum_novidades([cod], {cod: max(x["criado_em"] for x in aluno.forum(cod))}) == {cod: 0}
        assert visto

        # bloqueado não escreve; apagar o grupo leva o fórum junto
        adm.bloquear(aluno.usuario_id, True)
        with pytest.raises(ranking.ErroRanking):
            aluno.forum_publicar(cod, "spam")
        dono.forum_apagar(p["id"])
        assert dono.forum(cod, tipo="plano") == []
        dono.apagar_grupo(cod)
        assert srv.dados.tabelas["forum_posts"] == []
    finally:
        srv.parar()


def test_plano_em_uso_e_progresso(tmp_path):
    from datetime import datetime, timedelta, timezone

    from aprova import config, ranking
    from aprova.db import Banco
    from aprova.ui import grupos

    falso = type("F", (), {})()
    falso.aj = config.Ajustes(tmp_path / "aj.json")
    falso.db = Banco(tmp_path / "a.db")
    falso.msg = lambda texto: None
    post = {"id": 7, "titulo": "Plano 10h", "apelido": "Camila", "plano": ranking.validar_plano(
        {"disciplinas": [{"nome": "Língua Portuguesa", "horas": 4}, {"nome": "Informática", "horas": 6}], "dias": [0, 2, 4]})}
    grupos.usar_plano(falso, post, {"codigo": "TURMA-1", "nome": "Turma"})
    assert falso.aj["meta_horas_semana"] == 10 and falso.aj["dias_planejados"] == "0,2,4"
    # o tempo da disciplina entra mesmo com acento/maiúscula diferente
    falso.db.somar_tempo(2 * 3600, "app", "lingua portuguesa")
    prog = {p["nome"]: p for p in grupos.progresso_plano(falso, falso.aj["plano_ativo"])}
    assert prog["Língua Portuguesa"]["fracao"] == 0.5 and prog["Informática"]["feito_s"] == 0
    grupos.parar_plano(falso)
    assert not falso.aj["plano_ativo"]
    # textos de tempo do fórum
    agora = datetime.now(timezone.utc)
    assert grupos.quando_texto(agora.isoformat()) == "agora"
    assert grupos.quando_texto((agora - timedelta(hours=3)).isoformat()) == "há 3 h"
    assert grupos.quando_texto((agora - timedelta(days=1, hours=1)).isoformat()) == "ontem"
    assert grupos.dias_texto([4, 0, 2]) == "seg, qua e sex"


def test_link_de_convite(tmp_path, monkeypatch):
    from aprova import config, convite

    url = convite.link("dataprev-7a2f")
    assert url == "https://natanaelsantz.github.io/aprova/convite/?g=DATAPREV-7A2F"
    assert convite.link("X1-AB", {"convite": "https://exemplo.com/c"}) == "https://exemplo.com/c/?g=X1-AB"
    for texto in (url, f"Bora estudar? {url} valeu", "aprova://grupo/DATAPREV-7A2F", "APROVA://GRUPO/dataprev-7a2f/"):
        assert convite.extrair_codigo(texto) == "DATAPREV-7A2F", texto
        assert convite.eh_convite(texto), texto
    assert convite.extrair_codigo("https://site.com/?g=1") is None  # código curto demais
    assert not convite.eh_convite("https://youtube.com/watch?g=ABCDEF")  # não é do Aprova
    assert not convite.eh_convite("texto qualquer")
    w = convite.links_compartilhar("Turma Dataprev", url)
    assert w["whatsapp"].startswith("https://wa.me/?text=") and "DATAPREV-7A2F" in w["whatsapp"]
    assert w["telegram"].startswith("https://t.me/share/url?url=")
    # convite chegando pelo aprova:// enquanto o app está aberto
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert not convite.outro_app_aberto()
    convite.marcar_vivo()
    assert convite.outro_app_aberto()
    convite.guardar_pendente("DATAPREV-7A2F")
    assert convite.pegar_pendente()["codigo"] == "DATAPREV-7A2F"
    assert convite.pegar_pendente() is None  # lido uma vez só
    convite.parar_vivo()
    assert not convite.outro_app_aberto()
    # imagem para Stories
    img = convite.imagem_stories("Turma Dataprev 2026 — reta final", "DATAPREV-7A2F", url, tmp_path / "c.png")
    from PIL import Image

    assert Image.open(img).size == (1080, 1920)


def test_entrada_rapida_e_convite(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import config, ranking

    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        adm = ranking.Ranking(config.Ajustes(tmp_path / "adm.json"), cfg)
        adm.criar_conta("adm@exemplo.com", "segredo1", "Natan")
        cod = adm.criar_grupo("Turma Dataprev")
        # mesmo num servidor sem admin, a conta rápida nunca vira administrador
        srv.dados.tabelas["perfis"][0]["papel"] = "aluno"
        anonimo = ranking.Ranking(config.Ajustes(tmp_path / "an.json"), cfg)
        anonimo.entrar_rapido("Visitante")
        assert anonimo.eh_anonimo and not anonimo.eh_admin
        srv.dados.tabelas["perfis"][0]["papel"] = "admin"
        # a página do convite (e o app sem conta) leem o nome do grupo sem login
        visitante = ranking.Ranking(config.Ajustes(tmp_path / "v.json"), cfg)
        info = visitante.convite_info(cod.lower())
        assert info == {"codigo": cod, "nome": "Turma Dataprev", "membros": 1}
        assert visitante.convite_info("NAO-EXISTE") is None
        assert visitante.convite_info("x") is None
        # entrada rápida: só o apelido, sem e-mail e senha
        visitante.entrar_rapido("Natan")  # apelido em uso: ganha um número
        assert visitante.logado and visitante.eh_anonimo and visitante.apelido.startswith("Natan ")
        assert not visitante.eh_admin  # o admin já existe
        visitante.entrar_grupo(cod)
        assert visitante.sou_membro(cod) and visitante.convite_info(cod)["membros"] == 2
        visitante.forum_publicar(cod, "Cheguei pelo link!")
        assert adm.forum(cod)[0]["texto"] == "Cheguei pelo link!"
        # proteger a conta: vira conta normal com e-mail e senha
        with pytest.raises(ranking.ErroRanking):
            visitante.proteger_conta("adm@exemplo.com", "segredo1")  # e-mail de outra pessoa
        assert visitante.proteger_conta("novo@exemplo.com", "segredo2") == "ok"
        assert not visitante.eh_anonimo and visitante.email == "novo@exemplo.com"
        outro_pc = ranking.Ranking(config.Ajustes(tmp_path / "pc2.json"), cfg)
        assert outro_pc.entrar("novo@exemplo.com", "segredo2")["apelido"] == visitante.apelido
        # projeto que exige confirmar o e-mail
        srv.dados.confirmar_email = True
        rapido = ranking.Ranking(config.Ajustes(tmp_path / "r2.json"), cfg)
        rapido.entrar_rapido()
        assert rapido.apelido.startswith("Estudante ")
        assert rapido.proteger_conta("depois@exemplo.com", "segredo3") == "confirmar"
        assert rapido.eh_anonimo
        # servidor com a entrada rápida desligada: mensagem clara
        srv.dados.anonimo_ligado = False
        with pytest.raises(ranking.ErroRanking, match="entrada rápida"):
            ranking.Ranking(config.Ajustes(tmp_path / "r3.json"), cfg).entrar_rapido("Alguem")
    finally:
        srv.parar()


def _pdf_de_texto(caminho: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Art. 5 Todos sao iguais perante a lei, sem distincao de qualquer natureza.", fontsize=11)
    page.insert_text((72, 120), "Segunda linha com o prazo de cinco dias para recurso administrativo.", fontsize=11)
    page.insert_text((72, 140), "Terceira linha fora da marcacao.", fontsize=11)
    doc.new_page(width=595, height=842)  # página sem texto (como um PDF digitalizado)
    doc.save(caminho)
    return caminho


def test_marcador_de_pdf(tmp_path, monkeypatch):
    import pymupdf

    from aprova import config, marcador

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "dados")
    original = _pdf_de_texto(tmp_path / "lei.pdf")
    bytes_original = original.read_bytes()
    d = marcador.DocumentoMarcado(original, autor="Natan")
    assert d.paginas == 2 and d.tem_texto()

    # arrastar do começo de "Todos" até "lei," marca só esse trecho
    m = d.marcar(0, (110, 95), (250, 96), "destaque", "verde", nota="cai muito")
    assert m and m["tipo"] == "destaque" and m["cor"] == "verde" and m["nota"] == "cai muito"
    assert "iguais perante" in m["trecho"] and "Segunda" not in m["trecho"]

    # seleção em duas linhas vira um sublinhado com um retângulo por linha
    s = d.marcar(0, (300, 96), (200, 116), "sublinhado", "azul")
    assert s["tipo"] == "sublinhado" and "Segunda" in s["trecho"] and "Terceira" not in s["trecho"]

    # soltar à direita do fim de uma linha curta pega até o fim dela (como num editor de texto)
    ate_o_fim = d.selecao(0, (72, 136), (580, 138))
    assert d.trecho(0, ate_o_fim) == "Terceira linha fora da marcacao."

    n = d.nota(0, (500, 140), "Revisar art. 5")
    assert n["tipo"] == "nota" and n["nota"] == "Revisar art. 5"
    d.editar_nota(0, n["xref"], "Revisar art. 5 e 37")

    # página sem texto: marca o retângulo arrastado
    r = d.marcar(1, (100, 100), (300, 160))
    assert r and r["tipo"] == "destaque"
    assert d.marcar(1, (10, 10), (11, 11)) is None  # toque sem arrastar não marca nada

    assert len(d.marcacoes()) == 4
    assert d.na_posicao(0, 120, 98)["xref"] == m["xref"]
    assert d.desfazer() and len(d.marcacoes()) == 3  # tira o retângulo da página 2
    d.apagar(0, s["xref"])
    assert [x["tipo"] for x in d.marcacoes()] == ["destaque", "nota"]
    assert d.imagem(0, 1.0)[:4] == b"\x89PNG"
    d.fechar()

    # o original não muda; reabrir mostra as marcações salvas e a lista de recentes
    assert original.read_bytes() == bytes_original
    assert marcador.recentes()[0]["marcacoes"] == 2
    d2 = marcador.DocumentoMarcado(Path(marcador.recentes()[0]["copia"]))
    assert d2.marcacoes()[1]["nota"] == "Revisar art. 5 e 37" and d2.titulo == "lei"

    # salvar editável: as anotações continuam anotações; fixas: viram parte da página
    editavel = d2.exportar(tmp_path / "saida" / "lei (marcado).pdf")
    fixo = d2.exportar(tmp_path / "saida" / "lei (fixo).pdf", fixas=True)
    with pymupdf.open(editavel) as e, pymupdf.open(fixo) as f:
        assert len(list(e[0].annots())) == 2
        assert not list(f[0].annots() or [])
        assert "Todos" in f[0].get_text()  # o texto continua pesquisável
        assert e.page_count == 2 and f.page_count == 3  # as notas fixas vão para "Minhas anotações"
        resumo = f[2].get_text()
        assert "Minhas anotações" in resumo and "Revisar art. 5 e 37" in resumo and "cai muito" in resumo and "Pág. 1" in resumo
    d2.fechar()
    assert marcador.nome_para_salvar('Prova: TJ/SP') == "Prova  TJ SP (marcado).pdf"
    # cada conta tem os seus PDFs; os do visitante vão junto quando ele cria a conta
    conta = tmp_path / "dados" / "contas" / "u1"
    assert marcador.recentes(conta) == []
    assert marcador.copiar_para(tmp_path / "dados", conta) == 1 and marcador.copiar_para(tmp_path / "dados", conta) == 0
    levado = marcador.recentes(conta)[0]
    assert Path(levado["copia"]).parent == conta / "marcados"
    d3 = marcador.DocumentoMarcado(Path(levado["copia"]))
    assert d3.base == conta and len(d3.marcacoes()) == 2
    d3.fechar()
    marcador.esquecer(marcador.recentes()[0]["id"])
    assert marcador.recentes() == [] and len(marcador.recentes(conta)) == 1


def _zip_do_aprova(versao: str, extra: dict | None = None) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("aprova-main/main.py", "print('novo')\n")
        z.writestr("aprova-main/aprova/__init__.py", f'__version__ = "{versao}"\n')
        z.writestr("aprova-main/aprova/novo.py", "X = 1\n")
        z.writestr("aprova-main/ranking.json", "{}")  # nunca troca a configuração da pessoa
        z.writestr("aprova-main/../fora.txt", "nao")
        for nome, texto in (extra or {}).items():
            z.writestr("aprova-main/" + nome, texto)
    return buf.getvalue()


def test_atualizacao_automatica(tmp_path, monkeypatch):
    import json

    from aprova import atualizar

    assert atualizar.mais_nova("1.10.0", "1.9.3") and not atualizar.mais_nova("1.9.0", "1.9.0")
    raiz, dados = tmp_path / "app", tmp_path / "dados"
    (raiz / "aprova").mkdir(parents=True)
    (raiz / "main.py").write_text("print('velho')\n")
    (raiz / "aprova" / "__init__.py").write_text('__version__ = "1.8.0"\n')
    (raiz / "ranking.json").write_text('{"url": "meu"}')

    # versao.json do site
    monkeypatch.setattr(atualizar, "_baixar", lambda url, timeout, progresso=None, limite=0: json.dumps({"versao": "1.9.0", "notas": ["Marcar PDF"], "zip": "https://github.com/NatanaelSantz/aprova/archive/refs/heads/main.zip"}).encode())
    info = atualizar.verificar("1.8.0")
    assert info["versao"] == "1.9.0" and info["notas"] == ["Marcar PDF"]
    assert atualizar.verificar("1.9.0") is None
    # .zip de outro lugar que não o repositório do Aprova não é aceito
    assert not atualizar.zip_confiavel("https://site-estranho.com/NatanaelSantz/aprova/main.zip")
    assert not atualizar.zip_confiavel("https://github.com/outra-pessoa/aprova/archive/main.zip")
    with pytest.raises(atualizar.ErroAtualizacao):
        atualizar.preparar({**info, "zip": "https://site-estranho.com/main.zip"}, dados, "1.8.0")

    with pytest.raises(atualizar.ErroAtualizacao):
        atualizar.preparar(info, dados, "1.8.0", conteudo=_zip_do_aprova("1.8.0"))  # não é mais nova
    with pytest.raises(atualizar.ErroAtualizacao):
        atualizar.preparar(info, dados, "1.8.0", conteudo=b"isto nao e zip")
    assert atualizar.pendente(dados) is None

    assert atualizar.preparar(info, dados, "1.8.0", conteudo=_zip_do_aprova("1.9.0")) == "1.9.0"
    assert atualizar.pendente(dados)["versao"] == "1.9.0"
    assert (raiz / "main.py").read_text() == "print('velho')\n"  # nada muda com o app aberto

    assert atualizar.aplicar_pendente(raiz, dados) == "1.9.0"
    assert (raiz / "main.py").read_text() == "print('novo')\n"
    assert (raiz / "aprova" / "novo.py").exists()
    assert json.loads((raiz / "ranking.json").read_text()) == {"url": "meu"}
    assert not (tmp_path / "fora.txt").exists()
    assert (dados / "atualizacao" / "anterior" / "1.8.0" / "main.py").read_text() == "print('velho')\n"
    assert atualizar.pendente(dados) is None and atualizar.aplicar_pendente(raiz, dados) is None


def test_iniciar_reinstala_so_quando_requisitos_mudam(tmp_path, monkeypatch):
    import importlib.machinery
    import importlib.util

    caminho = str(RAIZ / "iniciar.pyw")
    spec = importlib.util.spec_from_loader("iniciar_teste", importlib.machinery.SourceFileLoader("iniciar_teste", caminho))
    ini = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ini)
    monkeypatch.setattr(ini, "MARCA_REQUISITOS", tmp_path / ".requisitos")
    assert not ini.requisitos_mudaram()  # instalação antiga sem a marca: não reinstala à toa
    ini.marcar_requisitos()
    assert not ini.requisitos_mudaram()
    (tmp_path / ".requisitos").write_text("outro")
    assert ini.requisitos_mudaram()


def test_aviso_de_atualizacao_no_app(tmp_path, monkeypatch):
    import asyncio
    import json

    from aprova import __version__, atualizar, config
    from aprova.ui import atualizacao

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    consultas = []

    def falso(url, timeout, progresso=None, limite=0):
        consultas.append(url)
        return json.dumps({"versao": "99.0.0", "notas": ["Novidade"], "zip": "https://github.com/NatanaelSantz/aprova/archive/refs/heads/main.zip"}).encode()

    monkeypatch.setattr(atualizar, "_baixar", falso)

    class AppFalso:
        modo_web = False
        sessao = config.AjustesMemoria()
        atualizacao = None
        atualizacao_pronta = None

        async def em_segundo_plano(self, f, *a, **k):
            return f(*a, **k)

    app = AppFalso()
    info = asyncio.run(atualizacao.verificar(app))
    assert info["versao"] == "99.0.0" and app.atualizacao == info and len(consultas) == 1
    asyncio.run(atualizacao.verificar(app))  # dentro do intervalo: não consulta o site de novo
    assert len(consultas) == 1
    asyncio.run(atualizacao.verificar(app, forcar=True))
    assert len(consultas) == 2

    # versão já baixada esperando reiniciar
    (tmp_path / "atualizacao").mkdir()
    (tmp_path / "atualizacao" / "pronta.json").write_text(json.dumps({"versao": "99.0.0", "de": __version__}))
    atualizacao.ver_pronta(app)
    assert app.atualizacao_pronta == "99.0.0"

    # o site ainda anuncia a versão que a pessoa já tem: nenhum aviso
    monkeypatch.setattr(atualizar, "_baixar", lambda url, timeout, progresso=None, limite=0: json.dumps({"versao": __version__, "zip": "https://github.com/NatanaelSantz/aprova/archive/refs/heads/main.zip"}).encode())
    assert asyncio.run(atualizacao.verificar(app, forcar=True)) is None and app.atualizacao is None


def test_versao_publicada_bate_com_o_app():
    import json

    from aprova import __version__

    site = json.loads((RAIZ / "docs" / "versao.json").read_text(encoding="utf-8"))
    assert site["versao"] == __version__, "rode ferramentas/nova_versao.py para publicar a versão"
    assert site["zip"].startswith("https://github.com/") and site["notas"]


def test_ferramenta_nova_versao(tmp_path, monkeypatch):
    import importlib.util
    import json
    import shutil

    (tmp_path / "aprova").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "ferramentas").mkdir()
    shutil.copy(RAIZ / "ferramentas" / "nova_versao.py", tmp_path / "ferramentas" / "nova_versao.py")
    (tmp_path / "aprova" / "__init__.py").write_text('"""Aprova."""\n\n__version__ = "1.9.0"\n')
    spec = importlib.util.spec_from_file_location("nova_versao", tmp_path / "ferramentas" / "nova_versao.py")
    nv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nv)
    assert nv.main(["x", "1.8.9"]) == 1  # não volta versão
    assert nv.main(["x", "1.9.1", "Corrige o fórum"]) == 0
    assert '__version__ = "1.9.1"' in (tmp_path / "aprova" / "__init__.py").read_text()
    assert json.loads((tmp_path / "docs" / "versao.json").read_text(encoding="utf-8"))["notas"] == ["Corrige o fórum"]


def test_barra_do_windows_so_pinta_no_windows():
    from aprova import janela

    assert janela.colorref("#2340A8") == 0xA84023  # COLORREF é 0x00BBGGRR
    assert janela.colorref("FFFFFF") == 0xFFFFFF
    if sys.platform != "win32":
        assert janela.pintar_barra("Aprova", "#FFFFFF", "#141C33", "#E0E4ED", False) is False


def test_anexos_figurinhas_e_gifs_no_grupo(tmp_path, monkeypatch):
    import io
    import json as _json

    from PIL import Image

    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import config, ranking

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        adm = ranking.Ranking(config.Ajustes(tmp_path / "adm.json"), cfg)
        adm.criar_conta("adm@exemplo.com", "segredo1", "Natan")
        dono = ranking.Ranking(config.Ajustes(tmp_path / "dono.json"), cfg)
        dono.criar_conta("dono@exemplo.com", "segredo1", "Camila")
        aluno = ranking.Ranking(config.Ajustes(tmp_path / "aluno.json"), cfg)
        aluno.criar_conta("aluno@exemplo.com", "segredo1", "Joana")
        fora = ranking.Ranking(config.Ajustes(tmp_path / "fora.json"), cfg)
        fora.criar_conta("fora@exemplo.com", "segredo1", "Pedro")
        cod = dono.criar_grupo("Turma Dataprev")
        aluno.entrar_grupo(cod)

        # foto enorme (de celular) chega leve; PDF chega igual
        foto = tmp_path / "Resumo da Lei 8.112 (versão final).png"
        Image.new("RGB", (4000, 3000), (40, 60, 160)).save(foto)
        pdf = tmp_path / "lei.pdf"
        pdf.write_bytes(b"%PDF-1.4 conteudo de teste")
        a_foto = aluno.enviar_anexo(cod, foto)
        a_pdf = aluno.enviar_anexo(cod, pdf)
        assert a_foto["tipo"] == "imagem" and max(a_foto["largura"], a_foto["altura"]) == 1600
        assert a_foto["caminho"].startswith(f"{cod}/{aluno.usuario_id}/") and " " not in a_foto["caminho"]
        assert a_foto["nome"] == "Resumo da Lei 8.112 (versão final).png"
        assert a_pdf["tipo"] == "arquivo" and a_pdf["tamanho"] == len(b"%PDF-1.4 conteudo de teste")

        # mensagem só com anexos (sem texto), só com figurinha e com GIF do GIPHY
        aluno.forum_publicar(cod, "", anexos=[a_foto, a_pdf])
        aluno.forum_publicar(cod, "", figurinha="bora-estudar")
        gif = {"tipo": "gif", "url": "https://media2.giphy.com/media/abc/200.gif", "largura": 200, "altura": 150, "nome": "GIF"}
        dono.forum_publicar(cod, "kkk", anexos=[gif])
        posts = dono.forum(cod)
        assert [p.get("figurinha") for p in posts].count("bora-estudar") == 1
        com_arquivos = next(p for p in posts if len(p["anexos"]) == 2)
        # quem é do grupo baixa (vem do servidor, sem cache); quem não é, não
        monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache-dono")
        assert dono.baixar_anexo(com_arquivos["anexos"][1]) == b"%PDF-1.4 conteudo de teste"
        assert Image.open(io.BytesIO(dono.baixar_anexo(com_arquivos["anexos"][0]))).size == (1600, 1200)
        monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache-fora")
        with pytest.raises(ranking.ErroRanking):
            fora.baixar_anexo(com_arquivos["anexos"][1])

        # respostas com figurinha ou anexo
        pid = com_arquivos["id"]
        dono.forum_responder(pid, "", figurinha="valeu")
        dono.forum_responder(pid, "Olha esse", anexos=[dono.enviar_anexo(cod, pdf)])
        resp = aluno.forum_respostas(pid)
        assert resp[0]["figurinha"] == "valeu" and resp[1]["anexos"][0]["tipo"] == "arquivo"

        # o que não pode: tipo perigoso, vazio, grande demais, mensagem vazia, link qualquer, grupo dos outros
        exe = tmp_path / "virus.exe"
        exe.write_bytes(b"MZ")
        for ruim in (exe,):
            with pytest.raises(ranking.ErroRanking, match="não pode ser enviado"):
                aluno.enviar_anexo(cod, ruim)
        vazio = tmp_path / "vazio.txt"
        vazio.write_bytes(b"")
        with pytest.raises(ranking.ErroRanking, match="vazio"):
            aluno.enviar_anexo(cod, vazio)
        monkeypatch.setattr(ranking, "LIMITE_ARQUIVO", 10)
        with pytest.raises(ranking.ErroRanking, match="limite"):
            aluno.enviar_anexo(cod, pdf)
        monkeypatch.setattr(ranking, "LIMITE_ARQUIVO", 20 * 1024 * 1024)
        with pytest.raises(ranking.ErroRanking):
            aluno.forum_publicar(cod, "")
        with pytest.raises(ranking.ErroRanking):
            aluno.forum_publicar(cod, "", anexos=[{"tipo": "gif", "url": "https://site-estranho.com/x.gif"}])
        with pytest.raises(ranking.ErroRanking):
            fora.enviar_anexo(cod, pdf)

        # apagar a mensagem leva os arquivos junto
        n = len(srv.dados.arquivos)
        aluno.apagar_anexos(com_arquivos["anexos"])
        assert len(srv.dados.arquivos) == n - 2

        # busca de GIFs: precisa da chave do GIPHY, que só o admin põe
        with pytest.raises(ranking.ErroRanking, match="GIPHY"):
            aluno.buscar_gifs("estudar")
        with pytest.raises(ranking.ErroRanking):
            aluno.config_salvar("giphy", "chave-falsa")
        adm.config_salvar("giphy", "chave-publica")
        aluno._giphy = None
        assert aluno.chave_giphy() == "chave-publica"

        class Resp:
            status_code = 200

            def json(self):
                return {"data": [
                    {"id": "1", "title": "estudando", "images": {"fixed_height": {"url": "https://media0.giphy.com/media/1/200.gif", "width": "267", "height": "200"},
                                                                  "fixed_width_small": {"url": "https://media0.giphy.com/media/1/100w.gif"}}},
                    {"id": "2", "title": "fora", "images": {"fixed_height": {"url": "https://outro-site.com/x.gif"}}},
                ]}

        pedidos = []
        monkeypatch.setattr(ranking.requests, "get", lambda url, params=None, timeout=0: (pedidos.append((url, params)), Resp())[1])
        achados = aluno.buscar_gifs("estudar")
        assert [g["id"] for g in achados] == ["1"] and achados[0]["anexo"]["largura"] == 267
        assert pedidos[0][0].endswith("/gifs/search") and pedidos[0][1]["q"] == "estudar" and pedidos[0][1]["rating"] == "pg"
        animadas = aluno.buscar_gifs("", figurinhas=True)
        assert pedidos[1][0].endswith("/stickers/trending")
        # figurinha animada vai marcada como figurinha (aparece sem moldura) e o servidor aceita
        assert animadas[0]["anexo"]["figurinha"] is True and "figurinha" not in achados[0]["anexo"]
        aluno.forum_publicar(cod, "", anexos=[animadas[0]["anexo"]])
        from aprova.ui.anexos import so_figurinha

        enviada = next(p for p in aluno.forum(cod) if p.get("anexos") and p["anexos"][0].get("url") == animadas[0]["anexo"]["url"])
        assert so_figurinha(enviada)
        # a chave grátis tem 100 buscas por hora para o app todo: a mesma busca não vai de novo ao GIPHY
        assert aluno.buscar_gifs("Estudar ") == achados and len(pedidos) == 2
        _json.dumps(achados)  # o anexo vai como JSON para o servidor

        # servidor antigo (sem o SQL da 1.10): o fórum continua funcionando, e o envio avisa o que fazer
        srv.dados.sem_anexos = True
        velho = ranking.Ranking(config.Ajustes(tmp_path / "aluno.json"), cfg)
        assert velho.forum(cod) and velho.servidor_sem_anexos
        velho.forum_publicar(cod, "só texto ainda funciona")
        with pytest.raises(ranking.ErroRanking, match="SQL novo"):
            velho.forum_publicar(cod, "", figurinha="valeu")
    finally:
        srv.parar()


def test_figurinhas_tem_desenho():
    from aprova import figurinhas

    for ident, legenda in figurinhas.FIGURINHAS:
        assert figurinhas.caminho(ident) is not None, ident
        assert legenda
        assert re.fullmatch(r"[a-z0-9-]{1,40}", ident)  # o mesmo formato que o servidor aceita
    assert figurinhas.caminho("nao-existe") is None


def _figurinha_png(cor, lado=800, animada=False):
    import io

    from PIL import Image

    saida = io.BytesIO()
    if animada:
        quadros = [Image.new("RGBA", (lado, lado), (*cor, 255)), Image.new("RGBA", (lado, lado), (0, 0, 0, 255))]
        quadros[0].save(saida, "WEBP", save_all=True, append_images=quadros[1:], duration=100, loop=0)
    else:
        Image.new("RGBA", (lado, lado), (*cor, 200)).save(saida, "PNG")
    return saida.getvalue()


def test_minhas_figurinhas(tmp_path, monkeypatch):
    import io
    import zipfile

    from PIL import Image

    from aprova import minhas_figurinhas as mf

    col = mf.Colecao(tmp_path / "conta")
    assert col.lista() == []

    # imagem grande vira WebP de até 512 px, com transparência
    item, nova = col.adicionar(_figurinha_png((200, 30, 30)), "minha.png")
    assert nova and item["arquivo"].endswith(".webp") and max(item["largura"], item["altura"]) == 512
    im = Image.open(col.caminho(item))
    assert im.format == "WEBP" and im.mode == "RGBA"
    # a mesma de novo não duplica
    assert col.adicionar(_figurinha_png((200, 30, 30)), "de novo")[1] is False
    # animada fica como veio (WhatsApp manda WebP animado)
    animada = _figurinha_png((30, 200, 30), 512, animada=True)
    item_an, _ = col.adicionar(animada, "STK-20260101-WA0001.webp")
    assert item_an["animada"] and col.caminho(item_an).read_bytes() == animada

    # arquivos soltos, pacote .wastickers e conversa exportada do iPhone (.zip): só as .webp de dentro
    solta = tmp_path / "solta.webp"
    Image.new("RGBA", (512, 512), (10, 10, 200, 255)).save(solta, "WEBP")
    pacote = tmp_path / "estudos.wastickers"
    with zipfile.ZipFile(pacote, "w") as z:
        for i in range(3):
            b = io.BytesIO()
            Image.new("RGBA", (512, 512), (i * 60, 120, 90, 255)).save(b, "WEBP")
            z.writestr(f"{i}.webp", b.getvalue())
        z.writestr("tray.png", _figurinha_png((1, 2, 3), 96))
        z.writestr("author.txt", "alguém")
    conversa = tmp_path / "Conversa do WhatsApp com Eu.zip"
    with zipfile.ZipFile(conversa, "w") as z:
        z.writestr("_chat.txt", "[01/01/26] Eu: <anexado: STK-1.webp>")
        z.writestr("STK-1.webp", solta.read_bytes())  # a mesma da solta: conta como repetida
        z.writestr("IMG-1.jpg", b"foto que nao e figurinha")
    texto = tmp_path / "lista.txt"
    texto.write_text("nada")
    quebrada = tmp_path / "quebrada.png"
    quebrada.write_bytes(b"isso nao e png")
    res = col.importar([solta, pacote, conversa, texto, quebrada, tmp_path / "zip-quebrado.zip"])
    assert res["novas"] == 4 and res["repetidas"] == 1, res
    assert len(res["erros"]) == 3  # o .txt, a imagem quebrada e o zip que não abre
    assert "4 figurinhas novas" in mf.resumo(res) and "1 que você já tinha" in mf.resumo(res)
    assert len(col) == 6

    # a usada por último aparece primeiro; apagar tira o arquivo
    ultima = col.lista()[-1]
    col.usada(ultima["id"])
    assert col.lista()[0]["id"] == ultima["id"]
    col.apagar(ultima["id"])
    assert len(col) == 5 and not col.caminho(ultima).exists()
    assert col.dados(ultima["id"]) is None

    # limite por conta
    monkeypatch.setattr(mf, "LIMITE", 5)
    res = col.importar([pacote])
    assert res["novas"] == 0
    with pytest.raises(mf.ErroFigurinha, match="apague"):
        col.adicionar(_figurinha_png((9, 9, 9)), "mais uma")
    assert mf.resumo({"novas": 0, "repetidas": 0, "erros": []}).startswith("Nenhuma")

    # cada conta tem as suas
    assert mf.Colecao(tmp_path / "outra-conta").lista() == []


def test_figurinha_propria_vai_para_o_grupo(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import config, minhas_figurinhas as mf, ranking

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        dono = ranking.Ranking(config.Ajustes(tmp_path / "dono.json"), cfg)
        dono.criar_conta("dono@exemplo.com", "segredo1", "Camila")
        aluno = ranking.Ranking(config.Ajustes(tmp_path / "aluno.json"), cfg)
        aluno.criar_conta("aluno@exemplo.com", "segredo1", "Joana")
        cod = dono.criar_grupo("Turma")
        aluno.entrar_grupo(cod)

        col = mf.Colecao(tmp_path / "aluno")
        item, _ = col.adicionar(_figurinha_png((250, 200, 40), 512, animada=True), "STK.webp")
        dados = col.dados(item["id"])[1]
        anexo = aluno.enviar_figurinha(cod, dados, item)
        assert anexo["figurinha"] is True and anexo["tipo"] == "imagem" and anexo["mime"] == "image/webp"
        assert anexo["caminho"].startswith(f"{cod}/{aluno.usuario_id}/") and anexo["largura"] == 512
        aluno.forum_publicar(cod, "", anexos=[anexo])
        recebida = dono.forum(cod)[0]["anexos"][0]
        assert recebida["figurinha"] is True
        monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache-dono")
        baixada = dono.baixar_anexo(recebida)
        assert baixada == dados  # animada chega igual
        # quem recebe guarda nas dele
        assert mf.Colecao(tmp_path / "dono").adicionar(baixada, "grupo")[0]["animada"]
        # GIF de verdade também vale
        item_gif, _ = col.adicionar(_gif_animado(), "pulando.gif")
        assert aluno.enviar_figurinha(cod, col.dados(item_gif["id"])[1], item_gif)["tipo"] == "gif"
    finally:
        srv.parar()


def _gif_animado() -> bytes:
    import io

    from PIL import Image

    saida = io.BytesIO()
    q = [Image.new("RGB", (200, 200), (i * 90, 40, 200 - i * 60)) for i in range(3)]
    q[0].save(saida, "GIF", save_all=True, append_images=q[1:], duration=80, loop=0)
    return saida.getvalue()


def test_mensagem_de_servidor_sem_sql_novo():
    from aprova import ranking

    class R:
        status_code = 404

        def json(self):
            return {"code": "PGRST205", "message": "Could not find the table 'public.config' in the schema cache"}

    assert "SQL novo" in ranking._mensagem(R())


def test_simulado_nao_repete_o_que_voce_ja_fez(tmp_path):
    """Acerto feito dentro de um simulado conta para a questão original; o próximo simulado traz as novas primeiro."""
    from aprova import config, db, montador, sessoes

    banco = db.Banco(tmp_path / "r.db")
    aj = config.Ajustes(tmp_path / "a.json")
    pid = banco.criar_prova(titulo="Prova Dataprev", orgao="Dataprev", banca="FGV", origem_url="https://x/d.pdf", modo="questoes")
    banco.salvar_questoes(pid, [
        {"numero": i, "enunciado": f"Questão de português número {i} sobre crase e regência", "alternativas": {"A": f"a{i}", "B": f"b{i}", "C": f"c{i}", "D": f"d{i}"},
         "gabarito": "A", "disciplina": "Língua Portuguesa"}
        for i in range(1, 9)
    ])
    # a mesma questão 1 aparece em outra prova (outro cargo): é a mesma questão
    outra = banco.criar_prova(titulo="Prova Dataprev cargo 2", orgao="Dataprev", banca="FGV", origem_url="https://x/d2.pdf", modo="questoes")
    banco.salvar_questoes(outra, [{"numero": 1, "enunciado": "Questão de português número 1 sobre crase e regência", "alternativas": {"A": "a1", "B": "b1", "C": "c1", "D": "d1"},
                                   "gabarito": "A", "disciplina": "Língua Portuguesa"}])

    def fazer(prova_id, acertar):
        """Resolve o simulado como o app faz (com a referência da questão original)."""
        qs = banco.questoes(prova_id)
        t = banco.iniciar_tentativa(prova_id, "simulado")
        for q in qs:
            certo = acertar(q)
            banco.registrar_resposta(t, q["numero"], q["disciplina"], "A" if certo else "B", certo, q.get("ref") or "")
            banco.revisao_registrar(prova_id, q["numero"], q["disciplina"], certo, q.get("ref") or "")
        banco.finalizar_tentativa(t, 60, 0, len(qs))
        return {q.get("ref") for q in qs}

    s1 = montador.montar(banco, aj, "S1", [("Língua Portuguesa", 4)], filtro="Dataprev")
    assert s1["repetidas"] == {}
    vistas1 = fazer(s1["prova_id"], lambda q: True)
    with banco._tx() as c:  # o primeiro simulado foi feito semana passada
        c.execute("UPDATE respostas SET respondida_em='2026-01-05T20:00:00'")
    # o acerto dentro do simulado conta para a questão original
    assert {f"{a}:{b}" for a, b in banco.acertadas()} >= vistas1

    s2 = montador.montar(banco, aj, "S2", [("Língua Portuguesa", 4)], filtro="Dataprev")
    vistas2 = {q.get("ref") for q in banco.questoes(s2["prova_id"])}
    assert not (vistas1 & vistas2), "o segundo simulado tinha que trazer só questões novas"
    assert s2["repetidas"] == {}
    fazer(s2["prova_id"], lambda q: q["numero"] != 1)  # erra uma: ela vai para a Revisão

    # todas já vistas: volta primeiro a acertada há mais tempo, e a errada (esperando a revisão) fica por último
    s3 = montador.montar(banco, aj, "S3", [("Língua Portuguesa", 7)], filtro="Dataprev")
    refs3 = [q.get("ref") for q in banco.questoes(s3["prova_id"])]
    assert s3["repetidas"] == {"Língua Portuguesa": 7}
    errada = next(r for r in vistas2 if r in {f"{a}:{b}" for a, b in banco.em_revisao()})
    assert errada not in refs3[:7] or len(refs3) == 7 and refs3[-1] == errada
    assert set(refs3[:4]) == vistas1  # as mais antigas primeiro

    # a mesma questão em outra prova conta como vista; o treino também segue a ordem
    hist = montador.Historico(banco)
    q1_outra = next(q for q in banco.banco_de_questoes(unicas=False) if q["prova_id"] == outra)
    assert hist.ja_vista(q1_outra)
    treino = sessoes.preparar_treino(banco, "Língua Portuguesa", 3)
    assert treino


def test_mini_prova_por_disciplina_e_por_prova(tmp_path):
    """Onde focar: mini prova só de uma disciplina, da biblioteca toda ou de uma prova escolhida."""
    from aprova import db, sessoes
    from aprova.ui.miniprova import opcoes_quantidade, quantidade_padrao

    banco = db.Banco(tmp_path / "mp.db")

    def prova(titulo, n_esp, n_port, ini):
        pid = banco.criar_prova(titulo=titulo, orgao=titulo.split()[0], origem_url=f"https://x/{titulo.split()[0]}.pdf", modo="questoes")
        qs = []
        for i in range(n_esp + n_port):
            disc = "Conhecimentos Específicos" if i < n_esp else "Língua Portuguesa"
            k = ini + i
            qs.append({"numero": i + 1, "enunciado": f"Questão {k} de {disc} sobre o assunto {k} do edital", "alternativas": {"A": f"a{k}", "B": f"b{k}", "C": f"c{k}"},
                       "gabarito": "A", "disciplina": disc})
        # uma questão quebrada (PDF mal lido) não entra
        qs.append({"numero": len(qs) + 1, "enunciado": "curta", "alternativas": {"A": "x", "B": "y", "C": "z"}, "gabarito": "A", "disciplina": "Conhecimentos Específicos"})
        banco.salvar_questoes(pid, qs)
        return pid

    dataprev = prova("Dataprev 2024 Analista", 12, 4, 0)
    serpro = prova("Serpro 2023 Analista", 7, 3, 100)
    op = sessoes.opcoes_mini_prova(banco, "Conhecimentos Específicos")
    assert op["total"] == 19 and op["novas"] == 19
    assert [(p["prova_id"], p["questoes"]) for p in op["provas"]] == [(dataprev, 12), (serpro, 7)]

    # mini prova da biblioteca toda
    pid = sessoes.preparar_treino(banco, "Conhecimentos Específicos", 10, titulo="Mini prova · Conhecimentos Específicos")
    qs = banco.questoes(pid)
    assert len(qs) == 10 and {q["disciplina"] for q in qs} == {"Conhecimentos Específicos"}
    assert banco.prova(pid)["titulo"] == "Mini prova · Conhecimentos Específicos"
    # de uma prova só (ex.: o cargo da Serpro): só vêm questões dela
    pid = sessoes.preparar_treino(banco, "Conhecimentos Específicos", 20, prova_id=serpro)
    qs = banco.questoes(pid)
    assert len(qs) == 7 and all(q["ref"].startswith(f"{serpro}:") for q in qs)
    # a mini prova reaproveita a mesma prova interna e não aparece como fonte de questões
    assert all(q["prova_id"] != pid for q in banco.banco_de_questoes())
    # depois de fazer, as feitas deixam de contar como novas
    t = banco.iniciar_tentativa(pid, "simulado")
    for q in qs[:5]:
        banco.registrar_resposta(t, q["numero"], q["disciplina"], "A", True, q["ref"])
    banco.finalizar_tentativa(t, 300, 5, 7)
    op = sessoes.opcoes_mini_prova(banco, "Conhecimentos Específicos")
    assert op["novas"] == 14 and next(p for p in op["provas"] if p["prova_id"] == serpro)["novas"] == 2
    assert sessoes.preparar_treino(banco, "Direito Penal") is None
    assert sessoes.opcoes_mini_prova(banco, "Direito Penal") == {"total": 0, "novas": 0, "provas": []}

    # botões de quantidade
    assert opcoes_quantidade(0) == []
    assert opcoes_quantidade(3) == [(3, "Todas (3)")]
    assert opcoes_quantidade(19) == [(5, "5"), (10, "10"), (19, "Todas (19)")]
    assert opcoes_quantidade(200) == [(5, "5"), (10, "10"), (20, "20"), (30, "30")]
    assert quantidade_padrao(19) == 10 and quantidade_padrao(4) == 4


def test_figurinhas_na_conversa(tmp_path):
    """Mensagem só de figurinha fica compacta; recentes guardam a última primeiro; a grade tem a altura certa."""
    from aprova import config
    from aprova.ui import anexos as ax

    giphy = {"tipo": "gif", "url": "https://media1.giphy.com/media/x/200.gif", "figurinha": True}
    minha = {"tipo": "imagem", "caminho": "G/u/a.webp", "figurinha": True}
    foto = {"tipo": "imagem", "caminho": "G/u/foto.png"}
    assert ax.e_adesivo(giphy) and ax.e_adesivo(minha) and not ax.e_adesivo(foto)
    assert not ax.e_adesivo({"tipo": "gif", "url": "https://outro.com/x.gif", "figurinha": True})
    assert ax.so_figurinha({"texto": "", "figurinha": "valeu"})
    assert ax.so_figurinha({"texto": " ", "anexos": [minha]}) and ax.so_figurinha({"anexos": [giphy]})
    assert not ax.so_figurinha({"texto": "oi", "figurinha": "valeu"})
    assert not ax.so_figurinha({"titulo": "Plano", "figurinha": "valeu"})
    assert not ax.so_figurinha({"anexos": [minha, foto]}) and not ax.so_figurinha({"anexos": []})

    class App:
        aj = config.Ajustes(tmp_path / "aj.json")
        pasta_conta = tmp_path / "conta"

    app = App()
    for i in ("valeu", "kkkk", "valeu"):
        ax.lembrar_recente(app, "figurinha", i)
    ax.lembrar_recente(app, "gif", giphy)
    ax.lembrar_recente(app, "minha", "apagada-ja")
    ax.lembrar_recente(app, "figurinha", "nao-existe-mais")
    assert [(r["tipo"], r["chave"]) for r in ax.recentes(app)] == [("gif", giphy["url"]), ("figurinha", "valeu"), ("figurinha", "kkkk")]
    for i in range(30):
        ax.lembrar_recente(app, "figurinha", f"x{i}")
    assert len(app.aj.get("figurinhas_recentes")) == ax.RECENTES_MAX

    assert ax.colunas_grade(532) == 5 and ax.colunas_grade(300) == 3
    assert ax.altura_grade(0, 532) == 0
    assert ax.altura_grade(1, 532) == ax.altura_grade(5, 532) < ax.altura_grade(6, 532)
    assert ax.altura_grade(400, 532) == ax.ALTURA_GRADE


def test_resposta_antiga_sem_referencia_nao_confunde(tmp_path):
    """Respostas de antes da 1.12 no treino/revisão (prova reaproveitada) não são atribuídas à questão errada."""
    from aprova import db, sessoes

    banco = db.Banco(tmp_path / "v.db")
    pid = banco.criar_prova(titulo="P", orgao="X", origem_url="https://x/p.pdf", modo="questoes")
    banco.salvar_questoes(pid, [{"numero": i, "enunciado": f"Enunciado {i} bem diferente dos outros enunciados", "alternativas": {"A": "1", "B": "2", "C": "3"}, "gabarito": "A",
                                 "disciplina": "Informática"} for i in range(1, 4)])
    treino = sessoes.preparar_treino(banco, "Informática", 3)
    t = banco.iniciar_tentativa(treino, "estudo")
    banco.registrar_resposta(t, 1, "Informática", "A", True)  # jeito antigo: sem ref
    assert banco.historico_questoes() == {}
    # simulado montado (prova própria, não reaproveitada): dá para achar a origem pela questão
    from aprova import config, montador

    s = montador.montar(banco, config.Ajustes(tmp_path / "a.json"), "S", [("Informática", 1)], filtro="X")
    t2 = banco.iniciar_tentativa(s["prova_id"], "simulado")
    banco.registrar_resposta(t2, 1, "Informática", "A", True)  # sem ref, mas a questão do simulado sabe de onde veio
    ref = banco.questoes(s["prova_id"])[0]["ref"]
    a, b = (int(x) for x in ref.split(":"))
    assert banco.historico_questoes()[(a, b)]["acertou"]


def test_modo_web_pede_codigo_de_acesso(monkeypatch):
    """Pelo Wi-Fi, o Aprova só abre com o código do QR code; neste computador abre direto."""
    import asyncio
    import importlib.util

    from aprova import rede

    assert rede.acesso_liberado("127.0.0.1", "/", "abc")
    assert rede.acesso_liberado("::1", "/", "")
    assert not rede.acesso_liberado("192.168.0.20", "/", "segredo")
    assert not rede.acesso_liberado("192.168.0.20", "/?k=errado", "segredo")
    assert not rede.acesso_liberado("192.168.0.20", "/?k=segredo", "")  # sem código configurado, ninguém de fora
    assert rede.acesso_liberado("192.168.0.20", "/?k=segredo", "segredo")
    assert "/?k=xyz" in rede.endereco_celular(8550, "xyz")
    assert rede.nova_chave() != rede.nova_chave()

    spec = importlib.util.spec_from_file_location("main_aprova", Path(__file__).parent.parent / "main.py")
    principal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(principal)
    abriu = []
    monkeypatch.setattr(principal, "App", lambda page, modo_web: abriu.append(page) or type("A", (), {"iniciar": lambda self: None})())
    monkeypatch.setenv(rede.CHAVE_ENV, "segredo")

    class Pagina:
        def __init__(self, ip, rota):
            self.client_ip, self.route, self.adicionados = ip, rota, []

        def add(self, *c):
            self.adicionados.extend(c)

    de_fora = Pagina("192.168.0.20", "/")
    asyncio.run(principal.principal(True)(de_fora))
    assert de_fora.adicionados and not abriu  # tela "Abra pelo QR code"
    com_codigo = Pagina("192.168.0.20", "/?k=segredo")
    asyncio.run(principal.principal(True)(com_codigo))
    assert abriu == [com_codigo]


def test_atualizacao_chega_por_notificacao(tmp_path, monkeypatch):
    """Versão nova: notificação do sistema uma vez (clicar abre aprova://atualizar) e faixa dentro do app."""
    import base64
    import json

    from aprova import __version__, atualizar, config, convite, notificar
    from aprova.ui import atualizacao

    # a notificação do Windows: texto escapado, botão e clique levando ao app
    xml = notificar.xml_toast('Versão "nova" <1.12>', "Simulados & segurança", "aprova://atualizar", "Atualizar agora")
    assert "&lt;1.12&gt;" in xml and "&amp;" in xml and 'launch="aprova://atualizar"' in xml and 'content="Atualizar agora"' in xml
    cmd = notificar.comando_windows("Título com 'aspas'", "texto", "aprova://atualizar", "Atualizar")
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert cmd[0] == "powershell.exe" and notificar.APP_ID in script and "Título com ''aspas''" in script

    mostradas = []
    monkeypatch.setattr(notificar, "mostrar", lambda *a, **k: mostradas.append((a, k)) or True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    class Pagina:
        def __init__(self):
            self.dialogos = []

        def show_dialog(self, d):
            self.dialogos.append(d)

    class AppFalso:
        sessao = config.AjustesMemoria()
        atualizacao = None
        atualizacao_pronta = None
        page = Pagina()

        def msg(self, t):
            self.page.dialogos.append(t)

    app = AppFalso()
    info = {"versao": "99.0.0", "notas": ["Simulados sem repetição"]}
    assert atualizacao.notificar_versao(app, info)
    assert mostradas[0][1]["link"] == "aprova://atualizar" and "99.0.0" in mostradas[0][0][0]
    assert len(app.page.dialogos) == 1  # a faixa dentro do app
    assert not atualizacao.notificar_versao(app, info)  # a mesma versão não avisa de novo
    assert len(mostradas) == 1

    # clicar na notificação: o app aberto recebe o pedido
    assert convite.acao_do_link("aprova://atualizar/") == "atualizar" and convite.acao_do_link("aprova://grupo/X") is None
    convite.guardar_acao("atualizar")
    assert convite.pegar_pendente()["acao"] == "atualizar"
    assert convite.pegar_pendente() is None

    # depois de atualizar, a primeira abertura conta a novidade (uma vez)
    app2 = AppFalso()
    app2.page = Pagina()
    app2.sessao = config.AjustesMemoria()
    (tmp_path / atualizar.PASTA).mkdir(parents=True, exist_ok=True)
    (tmp_path / atualizar.PASTA / "ultima.json").write_text(json.dumps({"versao": __version__, "de": "1.0.0"}))
    app2.sessao.set("atualizacao_info", {"versao": __version__, "notas": ["Novidade boa"]})
    atualizacao.avisar_atualizado(app2)
    assert len(app2.page.dialogos) == 1
    atualizacao.avisar_atualizado(app2)
    assert len(app2.page.dialogos) == 1



def test_questao_esquisita_fica_fora_do_simulado(tmp_path):
    """PDF mal lido (letras separadas, alternativa faltando ou repetida) não entra no simulado."""
    from aprova import config, db, montador

    banco = db.Banco(tmp_path / "q.db")
    pid = banco.criar_prova(titulo="P", orgao="TJ", origem_url="https://x/p.pdf", modo="questoes")
    boas = [{"numero": i, "enunciado": f"Sobre a Lei 8.112, assinale a alternativa correta quanto ao item {i} da lei.",
             "alternativas": {"A": f"um {i}", "B": f"dois {i}", "C": f"três {i}", "D": f"quatro {i}"}, "gabarito": "C", "disciplina": "Direito"}
            for i in range(1, 4)]
    ruins = [
        {"numero": 10, "enunciado": "A s s i n a l e a a l t e r n a t i v a c o r r e t a s o b r e", "alternativas": {"A": "1", "B": "2", "C": "3"}, "gabarito": "A", "disciplina": "Direito"},
        {"numero": 11, "enunciado": "Sobre a Lei 8.112, assinale a alternativa correta quanto à posse.", "alternativas": {"A": "igual", "B": "igual", "C": "outra"}, "gabarito": "A", "disciplina": "Direito"},
        {"numero": 12, "enunciado": "Sobre a Lei 8.112, assinale a alternativa correta quanto à vacância.", "alternativas": {"A": "só uma"}, "gabarito": "A", "disciplina": "Direito"},
    ]
    sem_gabarito = {"numero": 20, "enunciado": "Sobre a Lei 8.112, assinale a alternativa correta quanto à remoção.", "alternativas": {"A": "x", "B": "y", "C": "z"}, "disciplina": "Direito"}
    banco.salvar_questoes(pid, boas + ruins + [sem_gabarito])
    res = montador.montar(banco, config.Ajustes(tmp_path / "a.json"), "S", [("Direito", 10)], filtro="TJ")
    nums = [int(q["ref"].split(":")[1]) for q in banco.questoes(res["prova_id"])]
    assert set(nums) == {1, 2, 3, 20} and nums[-1] == 20  # a sem gabarito só no fim; as esquisitas, nunca
    assert res["faltas"] == {"Direito": 6}


def test_ia_troca_as_repetidas_por_novas(tmp_path, monkeypatch):
    """Com a chave do Claude, a IA completa o simulado e troca as questões já feitas por inéditas."""
    from aprova import config, db, ia, montador

    banco = db.Banco(tmp_path / "ia.db")
    aj = config.Ajustes(tmp_path / "a.json")
    aj.set("claude_api_key", "sk-teste")
    pid = banco.criar_prova(titulo="P", orgao="INSS", banca="Cebraspe", origem_url="https://x/p.pdf", modo="questoes")
    banco.salvar_questoes(pid, [{"numero": i, "enunciado": f"Questão {i} sobre seguridade social e benefícios do INSS.",
                                 "alternativas": {"A": f"a{i}", "B": f"b{i}", "C": f"c{i}"}, "gabarito": "A", "disciplina": "Previdenciário"}
                                for i in range(1, 4)])
    t = banco.iniciar_tentativa(pid, "estudo")
    for i in (1, 2):  # já fez duas
        banco.registrar_resposta(t, i, "Previdenciário", "A", True)
    pedidos = []

    def gerar(disc, n, *a, **k):
        pedidos.append(n)
        return [{"enunciado": f"Questão inédita {j} sobre aposentadoria por idade e carência.", "alternativas": {"A": "1", "B": "2", "C": "3", "D": "4"},
                 "gabarito": "B", "tipo": "ME"} for j in range(n)]

    monkeypatch.setattr(ia, "gerar_questoes", gerar)
    res = montador.montar(banco, aj, "S", [("Previdenciário", 4)], filtro="INSS", usar_ia=True)
    qs = banco.questoes(res["prova_id"])
    assert pedidos == [3]  # 1 que faltava + 2 repetidas
    assert len(qs) == 4 and res["geradas"] == 3 and res["repetidas"] == {}
    assert [q["ref"] for q in qs if q.get("ref")] == [f"{pid}:3"]  # da biblioteca, só a que você nunca fez
    # sem a IA, as repetidas ficam (e o app avisa)
    sem = montador.montar(banco, aj, "S2", [("Previdenciário", 4)], filtro="INSS", usar_ia=False)
    assert sem["repetidas"] == {"Previdenciário": 2} and sem["faltas"] == {"Previdenciário": 1}


def test_comentario_do_simulado(tmp_path):
    """O resultado diz o que foi bem, onde ganhar pontos e lista cada erro por matéria."""
    from aprova import coach

    r = {"acertos": 7, "total": 10, "duracao": 600, "respondidas": 9,
         "por_disc": {"Língua Portuguesa": [5, 5], "Raciocínio Lógico": [1, 4], "Informática": [1, 1]}}
    com = coach.comentar(r)
    texto = " ".join(com["paragrafos"])
    assert com["titulo"] == "Bom resultado!" and com["forte"] == "Língua Portuguesa" and com["foco"] == "Raciocínio Lógico"
    assert "errou 3 de 4" in texto and "5 de 5" in texto and "1 em branco" in texto
    devagar = coach.comentar({**r, "duracao": 9 * 400})
    assert "por questão" in " ".join(devagar["paragrafos"])
    assert coach.comentar({"acertos": 2, "total": 10, "por_disc": {"X": [2, 10]}})["titulo"] == "Simulado é para isso"
    assert coach.comentar({"acertos": 0, "total": 0})["foco"] is None

    qs = [
        {"numero": 1, "disciplina": "Raciocínio Lógico", "enunciado": "Se  todo A é B...", "alternativas": {"A": "x", "B": "y"}, "gabarito": "A", "explicacao": "Silogismo."},
        {"numero": 2, "disciplina": "Raciocínio Lógico", "enunciado": "Quantos anagramas...", "alternativas": {"A": "10", "B": "120"}, "gabarito": "B"},
        {"numero": 3, "disciplina": "Língua Portuguesa", "enunciado": "Crase", "alternativas": {"A": "a", "B": "b"}, "gabarito": "A"},
        {"numero": 4, "disciplina": "Informática", "enunciado": "Anulada", "alternativas": {"A": "a"}, "gabarito": "*"},
    ]
    erradas = coach.erradas_por_disciplina(qs, {1: "B", 3: "A"}, lambda q: q.get("gabarito"))
    assert list(erradas) == ["Raciocínio Lógico"]
    e1, e2 = erradas["Raciocínio Lógico"]
    assert (e1["sua"], e1["certa"], e1["texto_certa"], e1["explicacao"]) == ("B", "A", "x", "Silogismo.")
    assert e1["enunciado"] == "Se todo A é B..." and e2["sua"] is None


def test_pergunta_pronta_para_o_chat_de_ia():
    """Sem chave: a questão vai para o chat do Claude ou do ChatGPT já escrita (no link, se couber)."""
    from urllib.parse import parse_qs, urlparse

    from aprova import chat_ia

    q = {"numero": 5, "disciplina": "Raciocínio Lógico", "enunciado": "Qual é a negação de  'Todo servidor é pontual'?",
         "alternativas": {"A": "Nenhum servidor é pontual", "E": "Algum servidor não é pontual"}, "gabarito": "E"}
    dica = chat_ia.pergunta_questao(q, "dica", "A", mostrar_gabarito=False, banca="FGV")
    assert "Gabarito oficial" not in dica and "DICA" in dica and "Eu marquei A" in dica and "banca FGV" in dica
    exp = chat_ia.pergunta_questao(q, "explicacao", "A")
    assert "Gabarito oficial: E." in exp and "(E) Algum servidor não é pontual" in exp
    for servico, base in (("claude", "https://claude.ai/new"), ("chatgpt", "https://chatgpt.com/")):
        url = chat_ia.link(servico, exp)
        assert url.startswith(base + "?q=") and parse_qs(urlparse(url).query)["q"][0] == exp
        assert chat_ia.link(servico, "x" * 5000) == base  # longa demais: vai só pela área de transferência
    res = chat_ia.pergunta_resultado({"acertos": 7, "total": 10, "por_disc": {"RL": [1, 3]}},
                                     {"RL": [{"enunciado": "Negação de todo", "sua": "A", "certa": "E"}]}, "Simulado Dataprev")
    assert "acertei 7 de 10 (70%)" in res and "marquei A, a certa era E" in res and "3 dias" in res


def test_iniciar_atualiza_ao_abrir(tmp_path, monkeypatch):
    """Ao abrir, o iniciar.pyw confere o site e, se tem versão nova, aplica antes de mostrar o app."""
    import http.server
    import importlib.machinery
    import importlib.util
    import json
    import shutil
    import threading

    app_dir, dados, site = tmp_path / "Aprova", tmp_path / "dados", tmp_path / "site"
    (app_dir / "aprova").mkdir(parents=True)
    site.mkdir()
    shutil.copy(RAIZ / "iniciar.pyw", app_dir / "iniciar.pyw")
    shutil.copy(RAIZ / "aprova" / "atualizar.py", app_dir / "aprova" / "atualizar.py")
    (app_dir / "aprova" / "__init__.py").write_text('__version__ = "1.12.0"\n')
    (app_dir / "main.py").write_text("print('velho')\n")
    (site / "main.zip").write_bytes(_zip_do_aprova("1.13.0", {"aprova/atualizar.py": (RAIZ / "aprova" / "atualizar.py").read_text()}))

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(site), **k)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Silencioso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        (site / "versao.json").write_text(json.dumps({"versao": "1.13.0", "notas": ["Nova"], "zip": f"{url}/main.zip"}))
        monkeypatch.setenv("APROVA_DATA", str(dados))
        monkeypatch.setenv("APROVA_ATUALIZACAO_URL", f"{url}/versao.json")
        spec = importlib.util.spec_from_loader("iniciar_copia", importlib.machinery.SourceFileLoader("iniciar_copia", str(app_dir / "iniciar.pyw")))
        ini = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ini)

        # com o app já aberto (clicou num convite), não atrasa a abertura
        dados.mkdir()
        (dados / "app.vivo").write_text("1")
        assert ini.atualizar_ao_abrir(mostrar_tela=False) is None
        (dados / "app.vivo").unlink()

        assert ini.atualizar_ao_abrir(mostrar_tela=False) == "1.13.0"
        assert (app_dir / "main.py").read_text() == "print('novo')\n"
        assert '1.13.0' in (app_dir / "aprova" / "__init__.py").read_text()
        # abrindo de novo, já está na última: nada a fazer
        assert ini.atualizar_ao_abrir(mostrar_tela=False) is None
        # sem internet: abre a versão instalada, sem erro
        monkeypatch.setenv("APROVA_ATUALIZACAO_URL", "http://127.0.0.1:9/versao.json")
        assert ini.atualizar_ao_abrir(mostrar_tela=False) is None
    finally:
        srv.shutdown()


def test_app_baixa_a_atualizacao_sozinho(tmp_path, monkeypatch):
    import asyncio

    from aprova import atualizar, config, notificar
    from aprova.ui import atualizacao

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(atualizar, "preparar", lambda info, dados, atual, progresso=None, conteudo=None: info["versao"])
    avisos = []
    monkeypatch.setattr(notificar, "mostrar", lambda *a, **k: avisos.append(a[0]) or True)

    class Pagina:
        def __init__(self):
            self.dialogos = []

        def show_dialog(self, d):
            self.dialogos.append(d)

    class AppFalso:
        sessao = config.AjustesMemoria()
        atualizacao = {"versao": "99.0.0", "notas": ["Coisa nova"]}
        atualizacao_pronta = None
        page = Pagina()

        async def em_segundo_plano(self, f, *a, **k):
            return f(*a, **k)

    app = AppFalso()
    assert asyncio.run(atualizacao.baixar_sozinho(app, app.atualizacao))
    assert app.atualizacao_pronta == "99.0.0"
    assert atualizacao.notificar_pronta(app) and avisos == ["Aprova 99.0.0 pronto para usar"]
    assert not atualizacao.notificar_pronta(app)  # avisa uma vez só


# ---------------------------------------------------------------- 1.14: personagem (avatar) e foto de perfil

def test_personagem_validar_e_desenhar():
    import io as _io

    from PIL import Image

    from aprova import avatar as av

    # só passa o que o app conhece (vem do servidor, de outras pessoas)
    sujo = {"cabelo": "https://x.com/a.png", "pele": 99, "roupa": "manto", "cor_roupa": True, "usar_foto": "sim", "foto": -5,
            "item": "espada", "extra": "oi", "t": 1793000000.7}
    v = av.validar(sujo)
    assert v["cabelo"] == av.PADRAO["cabelo"] and v["pele"] == av.PADRAO["pele"] and v["roupa"] == "manto" and v["item"] == "espada"
    assert v["cor_roupa"] == av.PADRAO["cor_roupa"] and v["usar_foto"] is False and v["foto"] == 0 and v["t"] == 1793000000
    assert v["extra"] == "nenhum" and "lixo" not in av.validar({"lixo": "x"}) and av.validar(None) == av.PADRAO and av.validar(["x"]) == av.PADRAO
    assert av.validar({"usar_foto": True, "foto": 0})["usar_foto"] is False  # sem foto enviada não usa foto
    assert not av.tem_personagem(av.PADRAO) and av.tem_personagem({**av.PADRAO, "t": 5})
    # sorteio estável por semente e sempre válido
    assert av.sortear("uid-1") == av.sortear("uid-1") and av.sortear("uid-1") != av.sortear("uid-2")
    for i in range(40):
        c = av.sortear(f"s{i}")
        assert av.validar(c) == c
        assert av.boneco(c).size == (av.W2, av.H2)  # 64 x 80: o dobro da grade de montagem, com detalhes
    # todas as combinações de estilo desenham sem erro (cabelo x acessório x óculos, roupa x item x extra) e todos os gestos
    for cab, _ in av.CABELOS:
        for ac, _ in av.ACESSORIOS:
            av.boneco({**av.PADRAO, "cabelo": cab, "acessorio": ac})
        for oc, _ in av.OCULOS:
            for cor in range(len(av.CORES_OCULOS)):
                av.boneco({**av.PADRAO, "cabelo": cab, "oculos": oc, "cor_oculos": cor, "olhos": "determinado"})
    gestos = ({}, {"braco": "aceno", "aceno": 1}, {"braco": "dois", "pulo": 5}, {"respira": 1, "piscando": True})
    for corpo, _ in av.CORPOS:  # cada roupa e cada extra em cada tipo de corpo, com todos os gestos
        for i, (roupa, _) in enumerate(av.ROUPAS):
            for j, (extra, _) in enumerate(av.EXTRAS):
                item = av.ITENS[(i + j) % len(av.ITENS)][0]
                av.boneco({**av.PADRAO, "corpo": corpo, "roupa": roupa, "item": item, "extra": extra, "olhos": "feliz"}, **gestos[(i + j) % 4])
        for k, (item, _) in enumerate(av.ITENS):
            for kw in gestos:
                av.boneco({**av.PADRAO, "corpo": corpo, "item": item, "cabelo": av.CABELOS[k % len(av.CABELOS)][0]}, **kw)
    for barba, _ in av.BARBAS:  # rosto: barba x boca, olhos x detalhes
        for boca, _ in av.BOCAS:
            av.boneco({**av.PADRAO, "barba": barba, "boca": boca, "cabelo": "careca" if boca == "neutra" else "curto"})
    for olhos, _ in av.OLHOS:
        for marca, _ in av.MARCAS:
            for kw in ({}, {"piscando": True}, {"alegre": True}):
                av.boneco({**av.PADRAO, "olhos": olhos, "marca": marca}, **kw)
    for i in range(len(av.CORES_CALCA)):
        av.boneco({**av.PADRAO, "cor_calca": i})
    # tipo de corpo: quem salvou antes (sem "corpo") fica com o médio, mais magro que o desenho antigo
    assert av.validar({"cabelo": "longo", "t": 5})["corpo"] == "medio"
    largura = {}
    for corpo, _ in av.CORPOS:
        b = av.boneco({**av.PADRAO, "corpo": corpo, "item": "nenhum"})
        largura[corpo] = b.crop((0, 52, 64, 62)).getbbox()[2] - b.crop((0, 52, 64, 62)).getbbox()[0]  # altura da barriga
    assert largura["magro"] < largura["medio"] < largura["gordinho"] and largura["medio"] <= largura["forte"]
    ombro = {c: (lambda b: b[2] - b[0])(av.boneco({**av.PADRAO, "corpo": c, "item": "nenhum"}).crop((0, 50, 64, 52)).getbbox()) for c in ("medio", "forte")}
    assert ombro["forte"] > ombro["medio"]
    # a mão (e o que ela segura) acompanha o corpo: o livro do magro fica mais perto do meio
    def direita(c):
        return av.boneco({**av.PADRAO, "item": "livro", "corpo": c}).getbbox()[2]
    assert direita("magro") < direita("gordinho")
    # cabe no servidor (perfis.avatar: até 600 letras, chaves e valores simples), mesmo com os nomes mais longos
    import json as _json
    import re as _re

    maior = {**av.PADRAO, "t": 10**10, "foto": 10**10, "usar_foto": True}
    for chave, opcoes in av.CATEGORIAS.items():
        maior[chave] = max((o[0] for o in opcoes), key=len)
    for chave, lista in av.CORES.items():
        maior[chave] = len(lista) - 1
    texto = _json.dumps(av.validar(maior), separators=(", ", ": "))
    assert len(texto) <= 600, len(texto)
    for k, v in av.validar(maior).items():
        assert _re.fullmatch(r"[a-z_]{1,16}", k) and (not isinstance(v, str) or _re.fullmatch(r"[a-z0-9_-]{0,24}", v))
    # busto: cabelo alto (black power) ou chapéu cabem no recorte
    for alto in ({"cabelo": "afro"}, {"cabelo": "moicano"}, {"acessorio": "chapeu"}):
        busto = Image.open(_io.BytesIO(av.rosto({**av.PADRAO, **alto}, 1, piscar=False))).convert("RGBA")
        assert busto.size == (40, 40) and busto.getbbox()[1] >= 0
        assert not any(busto.getpixel((x, 0))[3] for x in range(40)) or alto.get("acessorio")
    # 1.14.0 tinha óculos como acessório: vira o óculos redondo
    antigo = av.validar({"acessorio": "oculos", "t": 5})
    assert antigo["acessorio"] == "nenhum" and antigo["oculos"] == "redondo"
    # óculos que cobrem os olhos (escuro) escondem os olhos; os outros deixam ver
    caixa_olho = (av.OLHO_X[0], av.OLHO_Y, av.OLHO_X[0] + 5, av.OLHO_Y + 6)
    rosto_normal = av.boneco({**av.PADRAO, "cor_olhos": 2}).crop(caixa_olho).getcolors(100)
    rosto_escuro = av.boneco({**av.PADRAO, "cor_olhos": 2, "oculos": "escuro"}).crop(caixa_olho).getcolors(100)
    azul = (59, 122, 212, 255)
    assert any(c == azul for _, c in rosto_normal) and not any(c == azul for _, c in rosto_escuro)
    # olhos grandes: brilho branco em cima e pupila escura; olhos brancos ganham pupila cinza e brilho azulado
    cores_olho = {c for _, c in rosto_normal}
    assert (255, 255, 255, 255) in cores_olho and len(cores_olho) >= 5
    branco = av.CORES_OLHOS.index(next(c for c in av.CORES_OLHOS if c[1] == "Brancos"))
    olho_branco = {c for _, c in av.boneco({**av.PADRAO, "cor_olhos": branco}).crop(caixa_olho).getcolors(100)}
    assert (150, 200, 255, 255) in olho_branco
    # animações: WebP animado, ampliado sem borrar
    for anim in ("parado", "aceno", "pulo", "lobby"):
        im = Image.open(_io.BytesIO(av.animacao(av.sortear("x"), anim, 2)))
        assert im.format == "WEBP" and im.size == (128 * 2, 80 * 2) and getattr(im, "is_animated", False)
    assert Image.open(_io.BytesIO(av.animacao(av.sortear("x"), "lobby", 2, largura=48))).size == (96 * 2, 160)
    sozinho = Image.open(_io.BytesIO(av.animacao(av.sortear("x"), "parado", 2, cenario=False)))
    assert sozinho.size == (128, 160)
    assert Image.open(_io.BytesIO(av.membro(av.sortear("x"), "uid-9", 2))).size == (128, 160)
    assert Image.open(_io.BytesIO(av.rosto(av.sortear("x"), 2))).size == (80, 80)
    for nome, _ in av.CENARIOS:
        for larg in (64, 150):
            assert Image.open(_io.BytesIO(av.cenario_png(nome, larg, 2))).size == (larg * 4, 160)
            assert Image.open(_io.BytesIO(av.cenario_png(nome, larg, 1, quadros=4))).size == (larg * 2, 80)
    assert av.cor_fundo(av.PADRAO).startswith("#") and len(av.cor_fundo(av.PADRAO)) == 7
    # ampliado sem borrar: cada pixel vira um quadrado de cor única (nenhuma cor de meio-termo)
    q = Image.open(_io.BytesIO(av.animacao(av.PADRAO, "parado", 3, cenario=False))).convert("RGBA")
    for x in range(0, q.width, 3):
        for y in range(0, q.height, 3):
            bloco = q.crop((x, y, x + 3, y + 3)).tobytes()
            assert len({bloco[i:i + 4] for i in range(0, len(bloco), 4)}) == 1


def test_foto_de_perfil_fica_pequena_e_quadrada(tmp_path):
    import io as _io

    from PIL import Image

    from aprova import avatar as av

    grande = Image.new("RGB", (1600, 900), (200, 50, 50))
    b = _io.BytesIO()
    grande.save(b, "JPEG", quality=90)
    dados = av.preparar_foto(b.getvalue())
    im = Image.open(_io.BytesIO(dados))
    assert im.format == "WEBP" and im.size == (256, 256) and len(dados) < 300 * 1024
    with pytest.raises(Exception):
        av.preparar_foto(b"isso nao e imagem")
    with pytest.raises(ValueError):
        av.preparar_foto(b"")
    pequena = _io.BytesIO()
    Image.new("RGB", (10, 10)).save(pequena, "PNG")
    with pytest.raises(ValueError):
        av.preparar_foto(pequena.getvalue())


def test_avatar_no_servidor_grupo_ranking_e_forum(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import avatar as av
    from aprova import config, ranking

    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        ana = ranking.Ranking(config.Ajustes(tmp_path / "ana.json"), cfg)
        ana.criar_conta("ana@exemplo.com", "segredo1", "Ana")
        beto = ranking.Ranking(config.Ajustes(tmp_path / "beto.json"), cfg)
        beto.criar_conta("beto@exemplo.com", "segredo1", "Beto")
        cod = ana.criar_grupo("Turma Avatar")
        beto.entrar_grupo(cod)

        meu = {**av.sortear("ana"), "roupa": "manto", "t": av.agora(), "lixo": "x"}
        salvo = ana.salvar_avatar(meu)
        assert "lixo" not in salvo and salvo["roupa"] == "manto"
        assert ana.perfil()["avatar"]["roupa"] == "manto"
        # aparece para a turma: membros, fórum, respostas e ranking
        membros = {m["apelido"]: m for m in beto.membros_grupo(cod)}
        assert membros["Ana"]["avatar"]["roupa"] == "manto" and membros["Beto"]["avatar"] is None
        ana.forum_publicar(cod, "Olha meu personagem")
        post = beto.forum(cod)[0]
        assert post["avatar"]["roupa"] == "manto"
        beto.forum_responder(post["id"], "Que legal!")
        assert ana.forum_respostas(post["id"])[0]["avatar"] is None
        srv.dados.tabelas["estatisticas"].append({"usuario_id": ana.usuario_id, "semana": ranking.inicio_semana().isoformat(), "segundos": 600,
                                                  "questoes": 5, "acertos": 4, "dias": 1, "sequencia": 1})
        assert next(l for l in beto.ranking() if l["apelido"] == "Ana")["avatar"]["roupa"] == "manto"
        # ninguém muda o avatar dos outros (o PATCH só pega a própria linha)
        beto._pedir("PATCH", f"/rest/v1/perfis?id=eq.{ana.usuario_id}", json={"avatar": {"roupa": "terno"}}, cabecalhos={"Prefer": "return=minimal"})
        assert ana.perfil()["avatar"]["roupa"] == "manto"

        # foto: só WebP pequeno; cada um troca a sua; os outros baixam (e fica guardada por versão)
        import io as _io

        from PIL import Image

        b = _io.BytesIO()
        Image.new("RGB", (500, 400), (10, 120, 200)).save(b, "PNG")
        foto = av.preparar_foto(b.getvalue())
        with pytest.raises(ranking.ErroRanking):
            ana.enviar_foto(b.getvalue())  # PNG cru não vai
        ana.enviar_foto(foto)
        ana.enviar_foto(foto)  # trocar de novo não dá erro
        ana.salvar_avatar({**salvo, "foto": 1793000123, "usar_foto": True})
        assert beto.baixar_foto(ana.usuario_id, 1793000123) == foto
        assert beto.baixar_foto(beto.usuario_id, 0) is None
        with pytest.raises(ranking.ErroRanking):
            beto.baixar_foto("../anexos/x", 1)
        beto.enviar_foto(foto)
        assert set(srv.dados.fotos) == {f"{ana.usuario_id}.webp", f"{beto.usuario_id}.webp"}
        ana.apagar_foto()
        assert set(srv.dados.fotos) == {f"{beto.usuario_id}.webp"}

        # servidor sem o SQL da 1.14: tudo continua funcionando, sem avatar, e salvar explica o que falta
        srv.dados.sem_avatar = True
        velho = ranking.Ranking(config.Ajustes(tmp_path / "velho.json"), cfg)
        velho.entrar("beto@exemplo.com", "segredo1")
        assert [m["apelido"] for m in velho.membros_grupo(cod)] == ["Ana", "Beto"]
        assert velho.forum(cod)[0]["texto"] == "Olha meu personagem" and velho.ranking() and velho.perfil()["apelido"] == "Beto"
        with pytest.raises(ranking.ErroRanking, match="SQL novo"):
            velho.salvar_avatar(av.sortear("b"))
    finally:
        srv.parar()



def test_admin_tira_foto_de_perfil(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from servidor_falso import CHAVE, ServidorFalso

    from aprova import avatar as av
    from aprova import config, ranking

    srv = ServidorFalso().iniciar()
    try:
        cfg = {"url": srv.url, "chave": CHAVE}
        adm = ranking.Ranking(config.Ajustes(tmp_path / "adm.json"), cfg)
        adm.criar_conta("adm@exemplo.com", "segredo1", "Natan")
        srv.dados.tabelas["perfis"][0]["papel"] = "admin"
        adm.atualizar_perfil()
        aluno = ranking.Ranking(config.Ajustes(tmp_path / "al.json"), cfg)
        aluno.criar_conta("al@exemplo.com", "segredo1", "Joana")
        import io as _io

        from PIL import Image

        b = _io.BytesIO()
        Image.new("RGB", (300, 300), (1, 2, 3)).save(b, "PNG")
        aluno.enviar_foto(av.preparar_foto(b.getvalue()))
        aluno.salvar_avatar({**av.sortear("j"), "foto": 1793000000, "usar_foto": True, "t": 1793000000})
        joana = next(u for u in adm.usuarios() if u["apelido"] == "Joana")
        assert joana["avatar"]["usar_foto"] is True
        with pytest.raises(ranking.ErroRanking):
            aluno.tirar_foto_de(adm.usuario_id)  # só admin
        adm.tirar_foto_de(joana["id"])
        joana = next(u for u in adm.usuarios() if u["apelido"] == "Joana")
        assert joana["avatar"]["usar_foto"] is False and joana["avatar"]["foto"] == 0 and joana["avatar"]["t"] == 1793000000
        assert srv.dados.fotos == {}
    finally:
        srv.parar()


def test_https_pelo_sistema_e_erro_explicado():
    """Computador da aluna: CERTIFICATE_VERIFY_FAILED ao baixar a janela do Flet. O app passa a verificar pelo sistema."""
    import subprocess

    from aprova import certificados

    codigo = (
        "import ssl, sys; sys.path.insert(0, '.');"
        "from aprova import certificados as c;"
        "a = c.confiar_no_sistema(); b = c.confiar_no_sistema();"
        "print(a, b, ssl.SSLContext.__module__)"
    )
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=Path(__file__).parent.parent, timeout=60).stdout.split()
    assert saida[0] == saida[1] == "truststore" and saida[2].startswith("truststore")
    erro = "Traceback ...\nurllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1032)>"
    assert "certificado de segurança do GitHub" in certificados.explicar_erro(erro)
    assert "uns 30 MB" in certificados.explicar_erro("urllib.error.URLError: <urlopen error [Errno 11001] getaddrinfo failed>")
    assert certificados.explicar_erro("KeyError: 'x'") == ""
    # o main.py liga isso antes de importar o Flet; o iniciar.pyw, antes de qualquer download
    main = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")
    assert main.index("confiar_no_sistema()") < main.index("import flet as ft")
    iniciar = (Path(__file__).parent.parent / "iniciar.pyw").read_text(encoding="utf-8")
    trecho = iniciar[iniciar.index("def main() -> None:"):]
    assert trecho.index("_confiar_certificados()") < trecho.index("atualizar_ao_abrir()")
    assert "truststore" in (Path(__file__).parent.parent / "requirements.txt").read_text()
