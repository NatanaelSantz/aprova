"""Índices restaurados nunca dão acesso a arquivos fora das figurinhas da conta."""
from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

from aprova import config, copia
from aprova.db import Banco
from aprova.minhas_figurinhas import Colecao, ErroFigurinha, caminho_seguro


@pytest.mark.parametrize("nome", [
    "../externa.webp", "..\\externa.webp", "sub/presente.webp", "sub\\presente.webp",
    "/tmp/externa.webp", "C:\\segredos\\externa.webp", "C:externa.webp",
    "\\\\servidor\\pasta\\externa.webp", "foto.webp:segredo", "../ajustes.json",
    "script.py", "indice.json", "", None,
])
def test_caminhos_do_windows_e_posix_sao_recusados(tmp_path, nome):
    colecao = Colecao(tmp_path / "conta")
    assert caminho_seguro(colecao.pasta, nome) is None
    with pytest.raises(ErroFigurinha, match="caminho"):
        colecao.caminho({"arquivo": nome})


def test_indice_local_nao_le_nem_apaga_arquivo_externo(tmp_path):
    colecao = Colecao(tmp_path / "conta")
    colecao.pasta.mkdir(parents=True)
    externa = tmp_path / "externa.webp"
    externa.write_bytes(b"arquivo pessoal")
    (colecao.pasta / "foto antiga.PNG").write_bytes(b"figurinha")
    itens = [
        {"id": "absoluto", "arquivo": str(externa)},
        {"id": "relativo", "arquivo": "../../externa.webp"},
        {"id": "legitima", "arquivo": "foto antiga.PNG"},
    ]
    colecao._indice.write_text(json.dumps(itens), encoding="utf-8")

    assert [i["id"] for i in colecao.lista()] == ["legitima"]
    assert colecao.dados("absoluto") is None
    assert colecao.dados("relativo") is None
    colecao.apagar("absoluto")
    colecao.apagar("relativo")
    assert externa.read_bytes() == b"arquivo pessoal"
    assert colecao.dados("legitima")[1] == b"figurinha"


def test_restaurar_backup_descarta_caminhos_perigosos(tmp_path):
    origem = tmp_path / "origem"
    destino = tmp_path / "destino"
    banco = Banco(origem / "aprova.db")
    restaurado = Banco(destino / "aprova.db")
    arquivo = tmp_path / "importada.aprova"
    try:
        copia.criar(origem, arquivo, banco)
        with zipfile.ZipFile(arquivo, "a") as z:
            z.writestr("figurinhas/foto.webp", b"figurinha")
            z.writestr("figurinhas/indice.json", json.dumps([
                {"id": "armadilha", "arquivo": "../ajustes.json"},
                {"id": "boa", "arquivo": "foto.webp"},
            ]))
        ajustes = config.Ajustes(destino / "ajustes.json")
        copia.restaurar(arquivo, destino, restaurado, ajustes)
        indice = json.loads((destino / "figurinhas" / "indice.json").read_text(encoding="utf-8"))
        assert [i["id"] for i in indice] == ["boa"]
        colecao = Colecao(destino)
        colecao.apagar("armadilha")
        assert ajustes.caminho.is_file()
        assert colecao.dados("boa")[1] == b"figurinha"
    finally:
        banco._con.close()
        restaurado._con.close()


def test_link_de_arquivo_nao_escapa_da_colecao(tmp_path):
    colecao = Colecao(tmp_path / "conta")
    colecao.pasta.mkdir(parents=True)
    externa = tmp_path / "externa.webp"
    externa.write_bytes(b"pessoal")
    link = colecao.pasta / "link.webp"
    try:
        link.symlink_to(externa)
    except OSError:
        pytest.skip("sistema não permite criar link simbólico de arquivo")
    assert caminho_seguro(colecao.pasta, link.name) is None
    assert externa.read_bytes() == b"pessoal"


def test_junction_da_pasta_nao_importa_indice_fora_da_conta(tmp_path):
    if os.name != "nt":
        pytest.skip("junction é específica do Windows")
    conta = tmp_path / "conta"
    conta.mkdir()
    fora = tmp_path / "fora"
    fora.mkdir()
    junction = conta / "figurinhas"
    resultado = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(fora)],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if resultado.returncode:
        pytest.skip("sistema não permite criar junction de teste")
    try:
        assert caminho_seguro(junction, "foto.webp") is None
        arquivo = tmp_path / "indice.zip"
        with zipfile.ZipFile(arquivo, "w") as z:
            z.writestr("figurinhas/indice.json", json.dumps([{"id": "x", "arquivo": "foto.webp"}]))
        with zipfile.ZipFile(arquivo) as z:
            copia._juntar_indice_figurinhas(z, conta)
        assert not (fora / "indice.json").exists()
    finally:
        junction.rmdir()
