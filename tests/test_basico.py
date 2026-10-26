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
        qs.append({"numero": i, "enunciado": f"Pergunta {i} sobre assunto {i}", "alternativas": {"A": "a", "B": "b"}, "gabarito": "A",
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
        assert re.match(r"^[A-Z0-9]+-[0-9A-F]{4}$", codigo)
        outro.entrar_grupo(codigo.lower())
        nomes = [l["apelido"] for l in r.ranking("horas", grupo=codigo)]
        assert set(nomes) == {"Natan"}  # Fulano ainda não enviou números
        assert r.meus_grupos()[0]["nome"] == "Turma Dataprev"
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
    monkeypatch.setattr(atualizar, "_baixar", lambda url, timeout, progresso=None, limite=0: json.dumps({"versao": "1.9.0", "notas": ["Marcar PDF"], "zip": "https://x/main.zip"}).encode())
    info = atualizar.verificar("1.8.0")
    assert info["versao"] == "1.9.0" and info["notas"] == ["Marcar PDF"]
    assert atualizar.verificar("1.9.0") is None

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
        return json.dumps({"versao": "99.0.0", "notas": ["Novidade"], "zip": "https://x/main.zip"}).encode()

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
    asyncio.run(atualizacao.verificar(app))  # dentro de 12 horas: não consulta o site de novo
    assert len(consultas) == 1
    asyncio.run(atualizacao.verificar(app, forcar=True))
    assert len(consultas) == 2

    # versão já baixada esperando reiniciar
    (tmp_path / "atualizacao").mkdir()
    (tmp_path / "atualizacao" / "pronta.json").write_text(json.dumps({"versao": "99.0.0", "de": __version__}))
    atualizacao.ver_pronta(app)
    assert app.atualizacao_pronta == "99.0.0"

    # o site ainda anuncia a versão que a pessoa já tem: nenhum aviso
    monkeypatch.setattr(atualizar, "_baixar", lambda url, timeout, progresso=None, limite=0: json.dumps({"versao": __version__, "zip": "https://x"}).encode())
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
