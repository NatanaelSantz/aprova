"""O rascunho de uma turma nunca aparece no formulário de outra."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aprova.ui.grupos import TelaGrupos


class Ajustes(dict):
    def set(self, chave, valor):
        self[chave] = valor


class AppFalso:
    def __init__(self):
        self.aj = Ajustes(grupo_atual="TURMA-A")
        self.tarefas = []
        self.redesenhos = 0
        self.c = {}
        self.mensagens = []
        self.page = SimpleNamespace(run_task=self.tarefas.append)

    async def em_segundo_plano(self, func, *args):
        return func(*args)

    def msg(self, texto):
        self.mensagens.append(texto)

    def recarregar_tela_sem_perder(self, tela):
        self.redesenhos += 1


def test_trocar_grupo_separa_texto_anexos_e_figurinha():
    app = AppFalso()
    tela = TelaGrupos(app)
    anexo_a = {"local": "C:/aula-a.pdf", "nome": "aula-a.pdf", "tipo": "arquivo"}
    figurinha_a = {"tipo": "minha", "valor": "figurinha-a"}
    tela._rascunho = "Material exclusivo da turma A"
    tela._assunto = "Aula A"
    tela.tipo_novo = "material"
    tela._pendentes.append(anexo_a)
    tela._figurinha_escolhida[None] = figurinha_a
    tela._figurinha_escolhida[10] = {"tipo": "figurinha", "valor": "gabaritei"}
    tela._rascunho_resposta[10] = "Resposta em andamento"
    tela.abertos.add(10)

    tela._trocar_grupo("TURMA-B")

    assert tela.codigo == "TURMA-B"
    assert tela._rascunho == tela._assunto == ""
    assert tela.tipo_novo == "conversa"
    assert tela._pendentes == []
    assert None not in tela._figurinha_escolhida
    assert tela._figurinha_escolhida[10]["valor"] == "gabaritei"
    assert tela._rascunho_resposta[10] == "Resposta em andamento"
    assert tela.abertos == set()
    assert app.aj["grupo_atual"] == "TURMA-B"

    anexo_b = {"local": "C:/aula-b.pdf", "nome": "aula-b.pdf", "tipo": "arquivo"}
    figurinha_b = {"tipo": "figurinha", "valor": "passei"}
    tela._rascunho = "Pergunta da turma B"
    tela._assunto = "Dúvida B"
    tela.tipo_novo = "duvida"
    tela._pendentes.append(anexo_b)
    tela._figurinha_escolhida[None] = figurinha_b
    tela._trocar_grupo("TURMA-A")

    assert tela._rascunho == "Material exclusivo da turma A"
    assert tela._assunto == "Aula A"
    assert tela.tipo_novo == "material"
    assert tela._pendentes == [anexo_a]
    assert tela._figurinha_escolhida[None] == figurinha_a

    # Editar ou publicar o rascunho restaurado não modifica o da outra turma.
    tela._rascunho = tela._assunto = ""
    tela.tipo_novo = "conversa"
    tela._pendentes.clear()
    tela._figurinha_escolhida.pop(None)
    tela._trocar_grupo("TURMA-B")

    assert tela._rascunho == "Pergunta da turma B"
    assert tela._assunto == "Dúvida B"
    assert tela.tipo_novo == "duvida"
    assert tela._pendentes == [anexo_b]
    assert tela._figurinha_escolhida[None] == figurinha_b

    tela._trocar_grupo("TURMA-A")
    assert tela._rascunho == tela._assunto == ""
    assert tela._pendentes == []
    assert None not in tela._figurinha_escolhida


def test_grupo_visitado_restaura_rascunho_sem_mudar_grupo_atual():
    app = AppFalso()
    tela = TelaGrupos(app)
    tela.visitando = {"codigo": "VISITA"}
    tela._rascunho = "Rascunho da minha turma"

    tela._trocar_grupo("VISITA")

    assert tela._rascunho == ""
    assert app.aj["grupo_atual"] == "TURMA-A"
    tela._trocar_grupo("TURMA-A")
    assert tela._rascunho == "Rascunho da minha turma"


def test_troca_vazia_ou_mesmo_grupo_preserva_composer_e_nao_recarrega():
    app = AppFalso()
    tela = TelaGrupos(app)
    tela._rascunho = "Ainda escrevendo"
    tela._pendentes.append({"local": "C:/aula.pdf"})
    tela._figurinha_escolhida[None] = {"tipo": "figurinha", "valor": "passei"}

    for codigo in (None, "", "TURMA-A"):
        tela._trocar_grupo(codigo)

    assert tela._rascunho == "Ainda escrevendo"
    assert tela._pendentes == [{"local": "C:/aula.pdf"}]
    assert tela._figurinha_escolhida[None]["valor"] == "passei"
    assert app.tarefas == []
    assert app.redesenhos == 0


def test_preparar_por_link_separa_e_restaura_o_rascunho():
    app = AppFalso()
    tela = TelaGrupos(app)
    tela._rascunho = "Texto da turma A"
    tela._pendentes = [{"local": "C:/privado-a.pdf"}]
    tela._figurinha_escolhida[None] = {"tipo": "minha", "valor": "adesivo-a"}

    tela.preparar(codigo="TURMA-B", aba="planos")

    assert tela.codigo == "TURMA-B"
    assert tela.aba == "planos"
    assert tela._rascunho == ""
    assert tela._pendentes == []
    assert None not in tela._figurinha_escolhida
    assert app.tarefas == []  # preparar não agenda um carregamento extra
    tela._rascunho = "Texto da turma B"

    tela.preparar(codigo="TURMA-A")
    assert tela._rascunho == "Texto da turma A"
    assert tela._pendentes == [{"local": "C:/privado-a.pdf"}]
    assert tela._figurinha_escolhida[None]["valor"] == "adesivo-a"

    tela.preparar(codigo="TURMA-B")
    assert tela._rascunho == "Texto da turma B"
    assert tela._pendentes == []


def test_entrar_em_outro_grupo_nao_leva_o_rascunho_anterior():
    app = AppFalso()
    app.ranking = SimpleNamespace(entrar_grupo=lambda codigo: {"codigo": codigo, "nome": "Turma B"})
    tela = TelaGrupos(app)
    tela._rascunho = "Rascunho da turma A"
    tela._pendentes = [{"local": "C:/privado-a.pdf"}]

    async def carregar():
        return None

    tela.carregar_grupos = carregar
    assert asyncio.run(tela._entrar_ou_criar("entrar", "TURMA-B", SimpleNamespace()))
    assert tela.codigo == "TURMA-B"
    assert tela._rascunho == ""
    assert tela._pendentes == []
    tela.preparar(codigo="TURMA-A")
    assert tela._rascunho == "Rascunho da turma A"
    assert tela._pendentes == [{"local": "C:/privado-a.pdf"}]


def test_grupo_indisponivel_nao_leva_o_rascunho_ao_grupo_seguinte():
    app = AppFalso()
    app.ranking = SimpleNamespace(eh_admin=False, meus_grupos=lambda: [{"codigo": "TURMA-B"}])
    tela = TelaGrupos(app)
    tela._rascunho = "Material da turma que saiu da lista"
    tela._pendentes = [{"local": "C:/privado-a.pdf"}]

    async def carregar():
        return None

    tela.carregar_grupo = carregar
    asyncio.run(tela.carregar_grupos())

    assert tela.codigo == "TURMA-B"
    assert tela._rascunho == ""
    assert tela._pendentes == []


def test_sair_do_grupo_limpa_formulario_ativo_sem_perder_rascunho():
    tela = TelaGrupos(AppFalso())
    tela._rascunho = "Ainda não enviado"
    tela._pendentes = [{"local": "C:/aula.pdf"}]
    tela._figurinha_escolhida[None] = {"tipo": "figurinha", "valor": "passei"}

    tela._selecionar_grupo(None)

    assert tela.codigo is None
    assert tela._rascunho == ""
    assert tela._pendentes == []
    assert None not in tela._figurinha_escolhida
    tela._selecionar_grupo("TURMA-A")
    assert tela._rascunho == "Ainda não enviado"
    assert tela._pendentes == [{"local": "C:/aula.pdf"}]
    assert tela._figurinha_escolhida[None]["valor"] == "passei"


def test_envio_termina_em_outra_turma_sem_apagar_rascunho_atual():
    tela = TelaGrupos(AppFalso())
    tela._rascunho = "Enviando para A"
    tela._pendentes = [{"local": "C:/a.pdf"}]
    tela._selecionar_grupo("TURMA-B")
    tela._rascunho = "Ainda escrevendo para B"
    tela._pendentes = [{"local": "C:/b.pdf"}]

    tela._limpar_rascunho_grupo("TURMA-A")

    assert tela._rascunho == "Ainda escrevendo para B"
    assert tela._pendentes == [{"local": "C:/b.pdf"}]
    tela._selecionar_grupo("TURMA-A")
    assert tela._rascunho == ""
    assert tela._pendentes == []


def test_figurinha_falhou_apos_troca_volta_so_ao_grupo_de_origem():
    tela = TelaGrupos(AppFalso())
    figurinha_a = {"tipo": "minha", "valor": "adesivo-a"}
    figurinha_b = {"tipo": "figurinha", "valor": "passei"}
    tela._selecionar_grupo("TURMA-B")
    tela._figurinha_escolhida[None] = figurinha_b

    tela._restaurar_figurinha_grupo("TURMA-A", figurinha_a)

    assert tela._figurinha_escolhida[None] == figurinha_b
    tela._selecionar_grupo("TURMA-A")
    assert tela._figurinha_escolhida[None] == figurinha_a
