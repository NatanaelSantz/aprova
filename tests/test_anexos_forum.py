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
    ranking.usuario_id = "dono"

    def pedir(metodo, url, **kwargs):
        raise rk.ErroRanking("storage indisponível")

    ranking._pedir = pedir
    anexos = [{"caminho": "A/dono/arquivo.pdf"}]
    ranking.apagar_anexos(anexos)  # padrão mantém compatibilidade
    with pytest.raises(rk.ErroRanking, match="storage indisponível"):
        ranking.apagar_anexos(anexos, tolerar_falha=False)
