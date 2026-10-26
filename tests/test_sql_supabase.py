"""Roda supabase/ranking.sql num PostgreSQL de verdade e confere as regras de acesso.

Precisa de um PostgreSQL vazio para testes (o banco é recriado do zero):
    APROVA_PG="host=/caminho/socket port=5544 user=postgres dbname=postgres" pytest tests/test_sql_supabase.py
Sem a variável APROVA_PG o teste é pulado.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("APROVA_PG")
pytestmark = pytest.mark.skipif(not DSN, reason="defina APROVA_PG para testar o SQL num PostgreSQL")

SQL = (Path(__file__).resolve().parent.parent / "supabase" / "ranking.sql").read_text(encoding="utf-8")

# o mínimo do Supabase que o ranking.sql usa: papéis, auth.users e auth.uid()
SUPABASE = """
do $$ begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
end $$;
create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $f$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$f$;
create function auth.jwt() returns jsonb language sql stable as $f$
    select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$f$;
grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;
-- Storage: só as peças que o ranking.sql usa (pastas e arquivos com regras por linha)
create schema storage;
create table storage.buckets (id text primary key, name text not null, public boolean default false,
    file_size_limit bigint, allowed_mime_types text[]);
create table storage.objects (id bigserial primary key, bucket_id text references storage.buckets (id), name text not null,
    owner uuid default auth.uid(), unique (bucket_id, name));
create function storage.foldername(name text) returns text[] language plpgsql immutable as $f$
declare partes text[] := string_to_array(name, '/');
begin
    return partes[1:array_length(partes, 1) - 1];
end $f$;
alter table storage.objects enable row level security;
grant usage on schema storage to authenticated;
grant select, insert, delete on storage.objects to authenticated;
grant usage, select on all sequences in schema storage to authenticated;
-- sem "expor tabelas novas": o ranking.sql precisa dar o acesso sozinho
"""

A, B, C, D = (f"00000000-0000-0000-0000-00000000000{x}" for x in "abcd")


class Banco:
    def __init__(self):
        self.con = psycopg.connect(DSN, autocommit=True)
        self.como(None)

    def como(self, uid: str | None, anonimo: bool = False):
        cur = self.con.cursor()
        cur.execute("reset role")
        cur.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": uid, "is_anonymous": anonimo}) if uid else "",))
        if uid:
            cur.execute("set role authenticated")
            cur.execute("select set_config('request.jwt.claim.sub', %s, false)", (uid,))
        else:
            cur.execute("select set_config('request.jwt.claim.sub', '', false)")
        return self

    def q(self, sql: str, args=()) -> list[tuple]:
        cur = self.con.cursor()
        cur.execute(sql, args)
        return cur.fetchall() if cur.description else []

    def falha(self, sql: str, args=()) -> str:
        try:
            self.q(sql, args)
        except psycopg.Error as e:
            return str(e)
        raise AssertionError(f"deveria falhar: {sql}")


@pytest.fixture(scope="module")
def db():
    con = psycopg.connect(DSN, autocommit=True)
    con.execute("drop schema if exists public cascade; drop schema if exists auth cascade; drop schema if exists storage cascade; create schema public; grant all on schema public to public;")
    con.execute(SUPABASE)
    con.execute(SQL)
    con.execute(SQL)  # rodar de novo não pode dar erro (o README manda rodar de novo nas atualizações)
    for uid in (A, B, C, D):
        con.execute("insert into auth.users values (%s, %s)", (uid, uid[-1] + "@x.com"))
    con.close()
    b = Banco()
    yield b
    b.con.close()


def test_papeis_e_primeiro_admin(db):
    for uid, nome in ((A, "Ana"), (B, "Beto"), (C, "Caio"), (D, "Duda")):
        db.como(uid).q("insert into perfis (id, apelido, papel) values (%s, %s, 'admin')", (uid, nome))
    db.como(None)
    assert db.q("select count(*) from perfis where papel = 'admin'") == [(0,)]  # ninguém se cria admin
    assert db.como(D, anonimo=True).q("select virar_primeiro_admin()") == [(False,)]  # conta rápida não vira admin
    assert db.como(A).q("select virar_primeiro_admin()") == [(True,)]
    assert db.como(B).q("select virar_primeiro_admin()") == [(False,)]
    db.como(B).q("update perfis set papel = 'admin', bloqueado = false where id = %s", (B,))
    assert db.como(None).q("select papel from perfis where id = %s", (B,)) == [("aluno",)]
    db.como(A).q("update perfis set bloqueado = true where id = %s", (D,))
    assert db.como(None).q("select bloqueado from perfis where id = %s", (D,)) == [(True,)]


def test_forum_so_para_membros(db):
    db.como(B).q("insert into grupos (codigo, nome, criado_por) values ('TURMA-0001', 'Turma', %s)", (B,))
    db.como(B).q("insert into membros (codigo, usuario_id) values ('TURMA-0001', %s)", (B,))
    for uid in (C, D):
        db.como(uid).q("select * from entrar_no_grupo('turma-0001')")
    db.como(None).q("update perfis set bloqueado = false where id = %s", (D,))
    db.como(D).q("select * from entrar_no_grupo('TURMA-0001')")
    db.como(None).q("update perfis set bloqueado = true where id = %s", (D,))
    # membro escreve; o pedido de fixar é ignorado para quem não modera
    db.como(C).q("insert into forum_posts (codigo, autor, tipo, texto, fixado) values ('TURMA-0001', %s, 'conversa', 'Bora estudar?', true)", (C,))
    pid = db.como(C).q("select id, fixado from forum_posts")[0]
    assert pid[1] is False
    pid = pid[0]
    # quem não é do grupo não vê e não escreve
    assert db.como(A).q("select count(*) from forum_feed") == [(1,)]  # admin vê tudo
    db.como(None).q("delete from membros where usuario_id = %s", (C,))
    assert db.como(C).q("select count(*) from forum_feed") == [(0,)]
    assert "row-level security" in db.como(C).falha("insert into forum_posts (codigo, autor, texto) values ('TURMA-0001', %s, 'oi')", (C,))
    db.como(C).q("select * from entrar_no_grupo('TURMA-0001')")
    # bloqueado não escreve
    assert "row-level security" in db.como(D).falha("insert into forum_posts (codigo, autor, texto) values ('TURMA-0001', %s, 'spam')", (D,))
    # não dá para escrever em nome de outra pessoa
    assert "row-level security" in db.como(C).falha("insert into forum_posts (codigo, autor, texto) values ('TURMA-0001', %s, 'fingindo')", (B,))
    # respostas e útil herdam o grupo da mensagem
    db.como(B).q("insert into forum_respostas (post_id, texto, codigo) values (%s, 'Bora!', 'OUTRO')", (pid,))
    db.como(B).q("insert into forum_uteis (post_id, usuario_id) values (%s, %s)", (pid, B))
    assert db.como(C).q("select respostas, uteis, apelido from forum_feed where id = %s", (pid,)) == [(1, 1, "Caio")]
    assert db.como(C).q("select codigo, apelido from forum_respostas_v") == [("TURMA-0001", "Beto")]


def test_moderacao_e_edicao(db):
    pid = db.como(C).q("select id from forum_posts order by id limit 1")[0][0]
    # o autor edita o texto; não consegue fixar
    db.como(C).q("update forum_posts set texto = 'Bora estudar hoje?', fixado = true where id = %s", (pid,))
    assert db.como(C).q("select texto, fixado, editado_em is not null from forum_posts where id = %s", (pid,)) == [("Bora estudar hoje?", False, True)]
    # quem criou o grupo fixa, mas não muda o texto dos outros
    db.como(B).q("update forum_posts set fixado = true, texto = 'mudei' where id = %s", (pid,))
    assert db.como(C).q("select texto, fixado from forum_posts where id = %s", (pid,)) == [("Bora estudar hoje?", True)]
    # plano de estudo com dados estruturados
    plano = {"meta_horas": 12, "dias": [0, 1, 2, 3, 4], "disciplinas": [{"nome": "Língua Portuguesa", "horas": 4}]}
    db.como(B).q("insert into forum_posts (codigo, autor, tipo, titulo, plano) values ('TURMA-0001', %s, 'plano', 'Plano 12h', %s)", (B, json.dumps(plano)))
    assert db.como(C).q("select plano->>'meta_horas' from forum_feed where tipo = 'plano'") == [("12",)]
    # outro membro não apaga a mensagem alheia; o moderador apaga
    db.como(C).q("delete from forum_posts where tipo = 'plano'")
    assert db.como(C).q("select count(*) from forum_posts where tipo = 'plano'") == [(1,)]
    db.como(A).q("delete from forum_posts where tipo = 'plano'")
    assert db.como(C).q("select count(*) from forum_posts where tipo = 'plano'") == [(0,)]
    # apagar o grupo leva o fórum junto
    db.como(B).q("delete from grupos where codigo = 'TURMA-0001'")
    assert db.como(None).q("select count(*) from forum_posts") == [(0,)]
    assert db.como(None).q("select count(*) from forum_respostas") == [(0,)]


def test_convite_sem_login(db):
    db.como(B).q("insert into grupos (codigo, nome, criado_por) values ('CONVITE-01', 'Turma do convite', %s)", (B,))
    db.como(B).q("insert into membros (codigo, usuario_id) values ('CONVITE-01', %s)", (B,))
    # a página do convite usa a chave pública (papel anon): vê nome e membros, nada mais
    con = db.con.cursor()
    con.execute("reset role")
    con.execute("set role anon")
    con.execute("select * from convite_info(' convite-01 ')")
    assert con.fetchall() == [("CONVITE-01", "Turma do convite", 1)]
    for tabela in ("grupos", "membros", "perfis", "forum_posts"):
        try:
            con.execute(f"select count(*) from {tabela}")
            assert con.fetchone() == (0,), tabela  # sem permissão ou sem linhas
        except psycopg.Error:
            pass
    con.execute("reset role")


def test_ranking_e_comunicados(db):
    from datetime import date, timedelta

    seg = date.today() - timedelta(days=date.today().weekday())
    db.como(C).q("insert into estatisticas (usuario_id, semana, segundos, questoes, acertos) values (%s, %s, 3600, 10, 7)", (C, seg))
    assert "check" in db.como(C).falha("insert into estatisticas (usuario_id, semana, segundos) values (%s, %s, 999999)", (C, seg - timedelta(days=7)))
    assert db.como(B).q("select apelido, taxa::float from ranking_semana") == [("Caio", 0.7)]
    assert "row-level security" in db.como(B).falha("insert into comunicados (titulo, texto) values ('Oi gente', 'teste')")
    db.como(A).q("insert into comunicados (titulo, texto) values ('Simulado sábado', 'Às 9h')")
    assert db.como(B).q("select titulo from comunicados") == [("Simulado sábado",)]


def test_anexos_figurinhas_e_arquivos(db):
    db.como(B).q("insert into grupos (codigo, nome, criado_por) values ('ANEXO-0001', 'Turma', %s)", (B,))
    db.como(B).q("insert into membros (codigo, usuario_id) values ('ANEXO-0001', %s)", (B,))
    db.como(C).q("select * from entrar_no_grupo('ANEXO-0001')")
    foto = json.dumps([{"tipo": "imagem", "caminho": f"ANEXO-0001/{C}/a1-resumo.png", "nome": "resumo.png", "tamanho": 1000}])
    gif = json.dumps([{"tipo": "gif", "url": "https://media1.giphy.com/media/abc/giphy.gif", "largura": 200, "altura": 150}])
    # só figurinha, só foto ou só GIF (sem texto) valem
    db.como(C).q("insert into forum_posts (codigo, autor, figurinha) values ('ANEXO-0001', %s, 'bora-estudar')", (C,))
    db.como(C).q("insert into forum_posts (codigo, autor, anexos) values ('ANEXO-0001', %s, %s)", (C, foto))
    db.como(C).q("insert into forum_posts (codigo, autor, anexos) values ('ANEXO-0001', %s, %s)", (C, gif))
    assert db.como(B).q("select figurinha, anexos is not null from forum_feed where codigo = 'ANEXO-0001' order by id") == [("bora-estudar", False), (None, True), (None, True)]
    # mensagem vazia, anexo de outro grupo, link qualquer e figurinha esquisita são recusados
    assert "check" in db.como(C).falha("insert into forum_posts (codigo, autor) values ('ANEXO-0001', %s)", (C,))
    alheio = json.dumps([{"tipo": "imagem", "caminho": f"OUTRO-GRUPO/{C}/x.png"}])
    assert "check" in db.como(C).falha("insert into forum_posts (codigo, autor, anexos) values ('ANEXO-0001', %s, %s)", (C, alheio))
    link = json.dumps([{"tipo": "gif", "url": "https://site-estranho.com/x.gif"}])
    assert "check" in db.como(C).falha("insert into forum_posts (codigo, autor, anexos) values ('ANEXO-0001', %s, %s)", (C, link))
    assert "check" in db.como(C).falha("insert into forum_posts (codigo, autor, figurinha) values ('ANEXO-0001', %s, '<script>')", (C,))
    # 1.12: arquivo que roda programa, endereço fora do GIPHY e caminho fora do padrão são recusados
    for ruim in (
        [{"tipo": "arquivo", "caminho": f"ANEXO-0001/{C}/a1-resumo.pdf", "nome": "Resumo.pdf.bat"}],
        [{"tipo": "arquivo", "caminho": f"ANEXO-0001/{C}/a1-virus.exe", "nome": "virus.pdf"}],
        [{"tipo": "imagem", "caminho": f"ANEXO-0001/{C}/a1-resumo.png", "url": "https://rastreador.com/pixel.png"}],
        [{"tipo": "imagem", "caminho": f"ANEXO-0001/{C}/../x.png"}],
        [{"tipo": "imagem", "caminho": "ANEXO-0001/nao-e-uuid/x.png"}],
        [{"tipo": "imagem", "caminho": f"ANEXO-0001/{C}/a1.png", "figurinha": "sim"}],
    ):
        assert "check" in db.como(C).falha("insert into forum_posts (codigo, autor, anexos) values ('ANEXO-0001', %s, %s)", (C, json.dumps(ruim))), ruim
    figurinha = json.dumps([{"tipo": "imagem", "caminho": f"ANEXO-0001/{C}/f1-figurinha.webp", "nome": "Figurinha", "figurinha": True}])
    db.como(C).q("insert into forum_posts (codigo, autor, anexos) values ('ANEXO-0001', %s, %s)", (C, figurinha))
    # resposta só com figurinha ou só com foto
    pid = db.como(C).q("select id from forum_posts where figurinha is not null")[0][0]
    db.como(B).q("insert into forum_respostas (post_id, figurinha) values (%s, 'valeu')", (pid,))
    db.como(B).q("insert into forum_respostas (post_id, anexos) values (%s, %s)", (pid, json.dumps([{"tipo": "arquivo", "caminho": f"ANEXO-0001/{B}/b2-lei.pdf", "nome": "Lei 8.112.pdf"}])))
    assert db.como(C).q("select figurinha from forum_respostas_v where post_id = %s order by id", (pid,)) == [("valeu",), (None,)]
    assert "check" in db.como(B).falha("insert into forum_respostas (post_id) values (%s)", (pid,))
    # quem modera não troca a figurinha nem os anexos de outra pessoa
    db.como(B).q("update forum_posts set figurinha = 'kkk' where id = %s", (pid,))
    assert db.como(C).q("select figurinha from forum_posts where id = %s", (pid,)) == [("bora-estudar",)]

    # arquivos: a pasta "anexos" existe, privada, até 20 MB
    assert db.como(None).q("select public, file_size_limit from storage.buckets where id = 'anexos'") == [(False, 20971520)]
    db.como(C).q("insert into storage.objects (bucket_id, name) values ('anexos', %s)", (f"ANEXO-0001/{C}/a1-resumo.png",))
    # não envia na pasta de outra pessoa nem em grupo que não é seu
    assert "row-level security" in db.como(C).falha("insert into storage.objects (bucket_id, name) values ('anexos', %s)", (f"ANEXO-0001/{B}/x.png",))
    assert "row-level security" in db.como(D).falha("insert into storage.objects (bucket_id, name) values ('anexos', %s)", (f"ANEXO-0001/{D}/x.png",))
    # quem é do grupo vê; quem não é, não
    assert db.como(B).q("select count(*) from storage.objects") == [(1,)]
    assert db.como(D).q("select count(*) from storage.objects") == [(0,)]
    # quem enviou ou quem modera apaga; outro membro não
    db.como(B).q("insert into storage.objects (bucket_id, name) values ('anexos', %s)", (f"ANEXO-0001/{B}/b2-lei.pdf",))
    db.como(C).q("delete from storage.objects where name like %s", (f"ANEXO-0001/{B}/%",))
    assert db.como(B).q("select count(*) from storage.objects") == [(2,)]
    db.como(B).q("delete from storage.objects where name like %s", (f"ANEXO-0001/{C}/%",))
    assert db.como(B).q("select count(*) from storage.objects") == [(1,)]


def test_config_so_admin_muda(db):
    assert "row-level security" in db.como(C).falha("insert into config (chave, valor) values ('giphy', 'abc')")
    db.como(A).q("insert into config (chave, valor) values ('giphy', 'chave-publica-123')")
    assert db.como(C).q("select valor from config where chave = 'giphy'") == [("chave-publica-123",)]
    db.como(C).q("update config set valor = 'hack' where chave = 'giphy'")
    assert db.como(C).q("select valor from config where chave = 'giphy'") == [("chave-publica-123",)]


def test_grupos_so_para_quem_tem_o_convite(db):
    """1.12: ninguém lista os grupos dos outros nem entra sem o código."""
    db.como(B).q("insert into grupos (codigo, nome, criado_por) values ('SEGREDO-ABC234', 'Turma fechada', %s)", (B,))
    db.como(B).q("insert into membros (codigo, usuario_id) values ('SEGREDO-ABC234', %s)", (B,))
    # quem não é do grupo não vê o grupo nem os membros
    assert db.como(C).q("select count(*) from grupos where codigo = 'SEGREDO-ABC234'") == [(0,)]
    assert db.como(C).q("select count(*) from membros where codigo = 'SEGREDO-ABC234'") == [(0,)]
    # não entra pela tabela (só quem criou entra direto)
    assert "row-level security" in db.como(C).falha("insert into membros (codigo, usuario_id) values ('SEGREDO-ABC234', %s)", (C,))
    # com o código errado não acontece nada; com o certo, entra e passa a ver
    assert db.como(C).q("select * from entrar_no_grupo('SEGREDO-XXXXXX')") == []
    assert db.como(C).q("select * from entrar_no_grupo(' segredo-abc234 ')") == [("SEGREDO-ABC234", "Turma fechada")]
    assert db.como(C).q("select * from entrar_no_grupo('SEGREDO-ABC234')") == [("SEGREDO-ABC234", "Turma fechada")]  # de novo: sem erro
    assert db.como(C).q("select count(*) from grupos where codigo = 'SEGREDO-ABC234'") == [(1,)]
    assert db.como(C).q("select count(*) from membros where codigo = 'SEGREDO-ABC234'") == [(2,)]
    # bloqueado não entra; o admin vê todos os grupos; quem não está logado não chama a função
    assert db.como(D).q("select * from entrar_no_grupo('SEGREDO-ABC234')") == []
    assert db.como(A).q("select count(*) from grupos where codigo = 'SEGREDO-ABC234'") == [(1,)]
    assert "permission denied" in db.como(None).falha("set role anon; select * from entrar_no_grupo('SEGREDO-ABC234')")
    db.como(None)
