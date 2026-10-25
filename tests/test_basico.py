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
