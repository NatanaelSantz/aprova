"""Regressões de anexos do fórum; não acessam Supabase real."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from aprova import ranking as rk
from aprova.ui.grupos import TelaGrupos


class RankingFalso:
    usuario_id = "usuario-test"

    def __init__(self, falha_publicacao=False):
        self.eventos = []
        self.falha_publicacao = falha_publicacao

    def enviar_anexo(self, codigo, caminho):
        self.eventos.append(("upload", Path(caminho).name))
        return {"tipo": "arquivo", "nome": Path(caminho).name,
                "caminho": f"{codigo}/{self.usuario_id}/{Path(caminho).name}"}

    def forum_publicar(self, codigo, texto, tipo, titulo, anexos=None, figurinha=None):
        self.eventos.append(("publicar", [x["caminho"] for x in anexos or []]))
        if self.falha_publicacao:
            raise rk.ErroRanking("falha simulada")

    def apagar_anexos(self, anexos, dono=None, tolerar_falha=True):
        self.eventos.append(("limpar", [x["caminho"] for x in anexos]))


class AppFalso:
    def __init__(self, ranking):
        self.ranking = ranking
        self.aj = {}
        self.mensagens = []
        self.c = {}

    async def em_segundo_plano(self, func, *args):
        return func(*args)

    def recarregar_tela_sem_perder(self, tela):
        return None

    def msg(self, mensagem):
        self.mensagens.append(mensagem)


def test_selecionar_anexo_nao_envia_ate_publicar(tmp_path):
    arquivo = tmp_path / "material.pdf"
    arquivo.write_bytes(b"%PDF-teste")
    r = RankingFalso()
    tela = TelaGrupos(AppFalso(r))
    grupo = {"codigo": "TURMA-0001"}

    asyncio.run(tela._anexar_caminhos(grupo, [arquivo]))
    assert r.eventos == []
    assert tela._pendentes[0]["local"] == str(arquivo)

    asyncio.run(tela._publicar_com_figurinha(
        grupo, "Material da aula", "material", "", list(tela._pendentes), None
    ))
    assert [x[0] for x in r.eventos] == ["upload", "publicar"]
    assert r.eventos[1][1] == ["TURMA-0001/usuario-test/material.pdf"]


def test_falha_na_publicacao_limpa_upload_da_tentativa(tmp_path):
    arquivo = tmp_path / "resumo.pdf"
    arquivo.write_bytes(b"pdf")
    r = RankingFalso(falha_publicacao=True)
    tela = TelaGrupos(AppFalso(r))
    grupo = {"codigo": "TURMA-0001"}
    asyncio.run(tela._anexar_caminhos(grupo, [arquivo]))

    with pytest.raises(rk.ErroRanking, match="falha simulada"):
        asyncio.run(tela._publicar_com_figurinha(
            grupo, "Resumo", "material", "", list(tela._pendentes), None
        ))
    assert [x[0] for x in r.eventos] == ["upload", "publicar", "limpar"]
    assert r.eventos[-1][1] == ["TURMA-0001/usuario-test/resumo.pdf"]


def test_cancelar_arquivo_antes_do_envio_nao_usa_storage(tmp_path):
    arquivo = tmp_path / "anexo.txt"
    arquivo.write_text("teste")
    r = RankingFalso()
    tela = TelaGrupos(AppFalso(r))
    asyncio.run(tela._anexar_caminhos({"codigo": "TURMA-0001"}, [arquivo]))
    tela._pendentes.clear()  # equivalente à remoção no formulário
    assert r.eventos == []


def test_busca_anexos_de_todas_as_respostas_paginadas():
    ranking = rk.Ranking.__new__(rk.Ranking)
    acessos = []

    def pedir(metodo, url, **kwargs):
        acessos.append(url)
        if "forum_posts?" in url:
            dados = [{"autor": "criador", "anexos": [{"tipo": "arquivo", "nome": "post.pdf", "caminho": "A/criador/post.pdf"}]}]
        elif "id=gt.0" in url:
            dados = [{"id": i, "autor": "aluno", "anexos": [{"tipo": "arquivo", "nome": f"{i}.pdf", "caminho": f"A/aluno/{i}.pdf"}]} for i in range(1, 201)]
        elif "id=gt.200" in url:
            dados = [{"id": 201, "autor": "outro", "anexos": [{"tipo": "arquivo", "nome": "201.pdf", "caminho": "A/outro/201.pdf"}]}]
        else:
            raise AssertionError(url)
        return SimpleNamespace(json=lambda: dados)

    ranking._pedir = pedir
    resultado = ranking.forum_anexos_post(45)
    assert len(resultado) == 202
    assert resultado[0]["autor"] == "criador"
    assert resultado[-1]["autor"] == "outro"
    assert any("id=gt.200" in url for url in acessos)


def test_falha_ao_listar_anexos_impede_exclusao():
    ranking = rk.Ranking.__new__(rk.Ranking)

    def pedir(metodo, url, **kwargs):
        raise rk.ErroRanking("falha de consulta")

    ranking._pedir = pedir
    with pytest.raises(rk.ErroRanking, match="falha de consulta"):
        ranking.forum_anexos_post(45)


def test_falha_limpeza_pode_ser_reportada():
    ranking = rk.Ranking.__new__(rk.Ranking)
    ranking.aj = {"ranking_usuario": "dono"}

    def pedir(metodo, url, **kwargs):
        raise rk.ErroRanking("storage indisponível")

    ranking._pedir = pedir
    anexos = [{"caminho": "A/dono/arquivo.pdf"}]
    ranking.apagar_anexos(anexos)  # padrão mantém compatibilidade
    with pytest.raises(rk.ErroRanking, match="storage indisponível"):
        ranking.apagar_anexos(anexos, tolerar_falha=False)


def test_falha_no_segundo_upload_limpa_so_arquivos_novos(tmp_path):
    r = RankingFalso()
    enviar = r.enviar_anexo

    def upload(codigo, caminho):
        if Path(caminho).name == "quebrado.pdf":
            raise rk.ErroRanking("segundo upload falhou")
        return enviar(codigo, caminho)

    r.enviar_anexo = upload
    tela = TelaGrupos(AppFalso(r))
    anexos = [{"caminho": "TURMA-0001/usuario-test/publicado.pdf"},
              {"local": str(tmp_path / "novo.pdf")},
              {"local": str(tmp_path / "quebrado.pdf")}]
    with pytest.raises(rk.ErroRanking, match="segundo upload falhou"):
        asyncio.run(tela._publicar_com_figurinha({"codigo": "TURMA-0001"}, "", "conversa", "", anexos, None))
    assert r.eventos == [("upload", "novo.pdf"), ("limpar", ["TURMA-0001/usuario-test/novo.pdf"])]


def test_resposta_falha_limpa_upload_sem_apagar_anexo_existente():
    r = RankingFalso()

    def responder(*args, **kw):
        raise rk.ErroRanking("resposta falhou")

    r.forum_responder = responder
    tela = TelaGrupos(AppFalso(r))
    with pytest.raises(rk.ErroRanking, match="resposta falhou"):
        asyncio.run(tela._publicar_com_figurinha(
            {"codigo": "TURMA-0001"}, "resposta", "", "",
            [{"local": "novo.pdf"}, {"caminho": "TURMA-0001/usuario-test/publicado.pdf"}], None, post_id=10))
    assert r.eventos[-1] == ("limpar", ["TURMA-0001/usuario-test/novo.pdf"])


def test_figurinha_rapida_falha_desfaz_upload(monkeypatch):
    from aprova.ui import anexos

    async def conteudo(app, codigo, tipo, valor):
        assert tipo == "minha"
        return {"anexos": [app.ranking.enviar_anexo(codigo, "figurinha.webp")]}

    monkeypatch.setattr(anexos, "conteudo_rapido", conteudo)
    r = RankingFalso(falha_publicacao=True)
    app = AppFalso(r)
    tela = TelaGrupos(app)
    tela.visor = SimpleNamespace(lembrar=lambda a: None)
    asyncio.run(tela._mandar_rapido({"codigo": "TURMA-0001"}, "minha", "figurinha-id"))
    assert [x[0] for x in r.eventos] == ["upload", "publicar", "limpar"]
    assert tela._rapidos == []
    assert any("A figurinha não foi" in m for m in app.mensagens)


def test_figurinha_publicada_nao_e_apagada_se_recarregar_falha(monkeypatch):
    from aprova.ui import anexos

    async def conteudo(app, codigo, tipo, valor):
        return {"anexos": [app.ranking.enviar_anexo(codigo, "figurinha.webp")]}

    async def atualizar(codigo):
        raise rk.ErroRanking("recarregar falhou")

    monkeypatch.setattr(anexos, "conteudo_rapido", conteudo)
    r = RankingFalso()
    tela = TelaGrupos(AppFalso(r))
    tela.visor = SimpleNamespace(lembrar=lambda a: None)
    tela._atualizar_conversa = atualizar
    asyncio.run(tela._mandar_rapido({"codigo": "TURMA-0001"}, "minha", "figurinha-id"))
    assert [x[0] for x in r.eventos] == ["upload", "publicar"]


def test_limite_inclui_figurinha_antes_de_subir_arquivos():
    r = RankingFalso()
    tela = TelaGrupos(AppFalso(r))
    with pytest.raises(rk.ErroRanking, match="até"):
        asyncio.run(tela._publicar_com_figurinha(
            {"codigo": "TURMA-0001"}, "", "conversa", "",
            [{"local": f"{i}.pdf"} for i in range(rk.MAX_ANEXOS)], {"tipo": "minha", "valor": "figurinha-id"}))
    assert r.eventos == []


def test_falha_na_limpeza_avisa_e_preserva_erro_original():
    r = RankingFalso(falha_publicacao=True)

    def limpar(*args):
        raise rk.ErroRanking("limpeza falhou")

    r.apagar_anexos = limpar
    app = AppFalso(r)
    tela = TelaGrupos(app)
    with pytest.raises(rk.ErroRanking, match="falha simulada"):
        asyncio.run(tela._publicar_com_figurinha({"codigo": "TURMA-0001"}, "", "conversa", "", [{"local": "novo.pdf"}], None))
    assert any("não puderam ser removidos" in m for m in app.mensagens)


@pytest.mark.parametrize("apagados", [[], [{"name": "A/dono/outro.pdf"}]])
def test_limpeza_sem_confirmacao_do_storage_e_reportada(apagados):
    ranking = rk.Ranking.__new__(rk.Ranking)
    ranking.aj = {"ranking_usuario": "dono"}
    ranking._pedir = lambda *a, **kw: SimpleNamespace(json=lambda: apagados)
    anexos = [{"caminho": "A/dono/arquivo.pdf"}]
    ranking.apagar_anexos(anexos)
    with pytest.raises(rk.ErroRanking, match="não confirmou"):
        ranking.apagar_anexos(anexos, tolerar_falha=False)
