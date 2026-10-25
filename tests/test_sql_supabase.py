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
grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;
-- sem "expor tabelas novas": o ranking.sql precisa dar o acesso sozinho
"""

A, B, C, D = (f"00000000-0000-0000-0000-00000000000{x}" for x in "abcd")


class Banco:
    def __init__(self):
        self.con = psycopg.connect(DSN, autocommit=True)
        self.como(None)

    def como(self, uid: str | None):
        cur = self.con.cursor()
        cur.execute("reset role")
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
    con.execute("drop schema if exists public cascade; drop schema if exists auth cascade; create schema public; grant all on schema public to public;")
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
    assert db.como(A).q("select virar_primeiro_admin()") == [(True,)]
    assert db.como(B).q("select virar_primeiro_admin()") == [(False,)]
    db.como(B).q("update perfis set papel = 'admin', bloqueado = false where id = %s", (B,))
    assert db.como(None).q("select papel from perfis where id = %s", (B,)) == [("aluno",)]
    db.como(A).q("update perfis set bloqueado = true where id = %s", (D,))
    assert db.como(None).q("select bloqueado from perfis where id = %s", (D,)) == [(True,)]


def test_forum_so_para_membros(db):
    db.como(B).q("insert into grupos (codigo, nome, criado_por) values ('TURMA-0001', 'Turma', %s)", (B,))
    for uid in (B, C, D):
        db.como(uid).q("insert into membros (codigo, usuario_id) values ('TURMA-0001', %s)", (uid,))
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
    db.como(C).q("insert into membros (codigo, usuario_id) values ('TURMA-0001', %s)", (C,))
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


def test_ranking_e_comunicados(db):
    from datetime import date, timedelta

    seg = date.today() - timedelta(days=date.today().weekday())
    db.como(C).q("insert into estatisticas (usuario_id, semana, segundos, questoes, acertos) values (%s, %s, 3600, 10, 7)", (C, seg))
    assert "check" in db.como(C).falha("insert into estatisticas (usuario_id, semana, segundos) values (%s, %s, 999999)", (C, seg - timedelta(days=7)))
    assert db.como(B).q("select apelido, taxa::float from ranking_semana") == [("Caio", 0.7)]
    assert "row-level security" in db.como(B).falha("insert into comunicados (titulo, texto) values ('Oi gente', 'teste')")
    db.como(A).q("insert into comunicados (titulo, texto) values ('Simulado sábado', 'Às 9h')")
    assert db.como(B).q("select titulo from comunicados") == [("Simulado sábado",)]
