"""Servidor de teste que imita as partes do Supabase usadas pelo ranking (auth + REST).

Uso nos testes:  srv = ServidorFalso(); srv.iniciar(); ... srv.url ...; srv.parar()
Uso manual (capturas de tela):  python tests/servidor_falso.py 8787
"""

from __future__ import annotations

import json
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

CHAVE = "chave-anon-de-teste-1234567890"


class Dados:
    def __init__(self):
        self.usuarios: dict[str, dict] = {}  # id -> {email, senha}
        self.tabelas: dict[str, list[dict]] = {"perfis": [], "estatisticas": [], "grupos": [], "membros": []}
        self.lock = threading.Lock()

    def ranking_semana(self) -> list[dict]:
        perfis = {p["id"]: p for p in self.tabelas["perfis"]}
        saida = []
        for e in self.tabelas["estatisticas"]:
            p = perfis.get(e["usuario_id"])
            if not p:
                continue
            taxa = round(e["acertos"] / e["questoes"], 4) if e["questoes"] else None
            saida.append({**e, "apelido": p["apelido"], "concurso": p.get("concurso", ""), "taxa": taxa})
        return saida

    def ranking_grupo(self) -> list[dict]:
        rs = self.ranking_semana()
        return [{"codigo": m["codigo"], **r} for m in self.tabelas["membros"] for r in rs if r["usuario_id"] == m["usuario_id"]]


def _filtrar(linhas: list[dict], filtros: list[tuple[str, str]]) -> list[dict]:
    out = linhas
    for col, expr in filtros:
        op, _, val = expr.partition(".")
        if op == "eq":
            out = [l for l in out if str(l.get(col)) == val]
        elif op == "in":
            vals = val.strip("()").split(",")
            out = [l for l in out if str(l.get(col)) in vals]
        elif op == "gte":
            out = [l for l in out if l.get(col) is not None and float(l[col]) >= float(val)]
    return out


class Manipulador(BaseHTTPRequestHandler):
    dados: Dados = None  # type: ignore[assignment]

    def log_message(self, *a):  # silencioso
        pass

    def _json(self, codigo: int, corpo=None):
        dado = b"" if corpo is None else json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dado)))
        self.end_headers()
        self.wfile.write(dado)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"null") if n else None

    def _uid(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        m = re.match(r"Bearer tok-(.+)", auth)
        return m.group(1) if m and m.group(1) in self.dados.usuarios else None

    def _sessao(self, uid: str):
        u = self.dados.usuarios[uid]
        return {"access_token": f"tok-{uid}", "refresh_token": f"ref-{uid}", "expires_in": 3600, "user": {"id": uid, "email": u["email"]}}

    def _rota(self, metodo: str):
        if self.headers.get("apikey") != CHAVE:
            return self._json(401, {"message": "Invalid API key"})
        partes = urlsplit(self.path)
        caminho, query = partes.path, parse_qsl(partes.query, keep_blank_values=True)
        d = self.dados
        with d.lock:
            if caminho == "/auth/v1/signup":
                c = self._corpo()
                if any(u["email"] == c["email"] for u in d.usuarios.values()):
                    return self._json(422, {"code": 422, "error_code": "user_already_exists", "msg": "User already registered"})
                if len(c["password"]) < 6:
                    return self._json(422, {"code": 422, "error_code": "weak_password", "msg": "Password should be at least 6 characters."})
                uid = str(uuid.uuid4())
                d.usuarios[uid] = {"email": c["email"], "senha": c["password"]}
                return self._json(200, self._sessao(uid))
            if caminho == "/auth/v1/token":
                c = self._corpo()
                tipo = dict(query).get("grant_type")
                if tipo == "password":
                    uid = next((k for k, u in d.usuarios.items() if u["email"] == c["email"] and u["senha"] == c["password"]), None)
                    if not uid:
                        return self._json(400, {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"})
                    return self._json(200, self._sessao(uid))
                m = re.match(r"ref-(.+)", c.get("refresh_token", ""))
                if not m or m.group(1) not in d.usuarios:
                    return self._json(400, {"error_code": "refresh_token_not_found", "msg": "Invalid Refresh Token"})
                return self._json(200, self._sessao(m.group(1)))
            if caminho in ("/auth/v1/logout", "/auth/v1/recover"):
                return self._json(204 if caminho.endswith("logout") else 200, None if caminho.endswith("logout") else {})
            uid = self._uid()
            if uid is None:
                return self._json(401, {"code": "PGRST301", "message": "JWT expired"})
            if caminho == "/rest/v1/rpc/apagar_minha_conta":
                d.usuarios.pop(uid, None)
                for t in d.tabelas:
                    d.tabelas[t] = [l for l in d.tabelas[t] if l.get("id") != uid and l.get("usuario_id") != uid]
                return self._json(204)
            m = re.match(r"/rest/v1/(\w+)$", caminho)
            if not m:
                return self._json(404, {"message": "not found"})
            tabela = m.group(1)
            filtros = [(k, unquote(v)) for k, v in query if k not in ("select", "order", "limit", "on_conflict")]
            if metodo == "GET":
                if tabela == "ranking_semana":
                    linhas = d.ranking_semana()
                elif tabela == "ranking_grupo":
                    linhas = d.ranking_grupo()
                else:
                    linhas = d.tabelas[tabela]
                linhas = _filtrar(linhas, filtros)
                ordem = dict(query).get("order", "")
                for parte in reversed(ordem.split(",") if ordem else []):
                    col, *mods = parte.split(".")
                    desc = "desc" in mods
                    linhas = sorted(linhas, key=lambda l: (l.get(col) is None, -(l.get(col) or 0) if desc else (l.get(col) or 0)))
                limite = int(dict(query).get("limit", 1000))
                return self._json(200, linhas[:limite])
            if metodo == "POST":
                corpo = self._corpo()
                novas = corpo if isinstance(corpo, list) else [corpo]
                chave = [c for c in dict(query).get("on_conflict", "").split(",") if c]
                for n in novas:
                    dono = n.get("id") if tabela == "perfis" else n.get("criado_por") if tabela == "grupos" else n.get("usuario_id")
                    if dono != uid:
                        return self._json(403, {"code": "42501", "message": "new row violates row-level security policy"})
                    if tabela == "perfis" and any(p["apelido"].lower() == n["apelido"].lower() and p["id"] != uid for p in d.tabelas["perfis"]):
                        return self._json(409, {"code": "23505", "message": 'duplicate key value violates unique constraint "perfis_apelido_unico"'})
                    pk = chave or {"grupos": ["codigo"], "membros": ["codigo", "usuario_id"], "perfis": ["id"], "estatisticas": ["usuario_id", "semana"]}[tabela]
                    existente = next((l for l in d.tabelas[tabela] if all(l.get(k) == n.get(k) for k in pk)), None)
                    if existente and not chave:
                        return self._json(409, {"code": "23505", "message": f"duplicate key value violates unique constraint \"{tabela}_pkey\""})
                    if existente:
                        existente.update(n)
                    else:
                        d.tabelas[tabela].append(dict(n))
                return self._json(201)
            if metodo == "DELETE":
                alvo = _filtrar(d.tabelas[tabela], filtros)
                d.tabelas[tabela] = [l for l in d.tabelas[tabela] if l not in alvo or l.get("usuario_id") != uid]
                return self._json(204)
        return self._json(405, {"message": "método não suportado"})

    def do_GET(self):
        self._rota("GET")

    def do_POST(self):
        self._rota("POST")

    def do_DELETE(self):
        self._rota("DELETE")


class ServidorFalso:
    def __init__(self, porta: int = 0):
        self.dados = Dados()
        manip = type("M", (Manipulador,), {"dados": self.dados})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", porta), manip)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self._t: threading.Thread | None = None

    def iniciar(self):
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._t.start()
        return self

    def parar(self):
        self.httpd.shutdown()

    def semear(self, pessoas: list[tuple[str, str, dict]], semana: str, grupo: tuple[str, str] | None = None):
        """Cria pessoas de exemplo: (apelido, concurso, números)."""
        for apelido, concurso, nums in pessoas:
            uid = str(uuid.uuid4())
            self.dados.usuarios[uid] = {"email": f"{apelido.lower()}@exemplo.com", "senha": "123456"}
            self.dados.tabelas["perfis"].append({"id": uid, "apelido": apelido, "concurso": concurso})
            self.dados.tabelas["estatisticas"].append({"usuario_id": uid, "semana": semana, **nums})
            if grupo:
                self.dados.tabelas["membros"].append({"codigo": grupo[0], "usuario_id": uid})
        if grupo and not any(g["codigo"] == grupo[0] for g in self.dados.tabelas["grupos"]):
            self.dados.tabelas["grupos"].append({"codigo": grupo[0], "nome": grupo[1], "criado_por": None})


if __name__ == "__main__":
    from datetime import date, timedelta

    srv = ServidorFalso(int(sys.argv[1]) if len(sys.argv) > 1 else 8787)
    semana = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    srv.semear(
        [
            ("Camila R.", "Dataprev 2026", {"segundos": 52000, "questoes": 410, "acertos": 312, "dias": 6, "sequencia": 18}),
            ("Joao_TI", "Dataprev 2026", {"segundos": 43100, "questoes": 360, "acertos": 241, "dias": 6, "sequencia": 9}),
            ("Bruna.fiscal", "Receita Federal", {"segundos": 39800, "questoes": 290, "acertos": 226, "dias": 5, "sequencia": 12}),
            ("Pedro M", "TJ-SP", {"segundos": 30500, "questoes": 250, "acertos": 160, "dias": 5, "sequencia": 4}),
            ("Lia", "Dataprev 2026", {"segundos": 21600, "questoes": 120, "acertos": 90, "dias": 4, "sequencia": 3}),
            ("Rafa", "INSS", {"segundos": 12600, "questoes": 80, "acertos": 49, "dias": 3, "sequencia": 1}),
        ],
        semana,
        grupo=("DATAPREV-7A2F", "Turma Dataprev"),
    )
    print("servidor falso em", srv.url, "chave:", CHAVE, flush=True)
    srv.httpd.serve_forever()
