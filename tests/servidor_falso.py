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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

CHAVE = "chave-anon-de-teste-1234567890"


class Dados:
    def __init__(self):
        self.usuarios: dict[str, dict] = {}  # id -> {email, senha}
        self.tabelas: dict[str, list[dict]] = {
            "perfis": [], "estatisticas": [], "grupos": [], "membros": [], "comunicados": [],
            "forum_posts": [], "forum_respostas": [], "forum_uteis": [], "config": [],
        }
        self.arquivos: dict[str, tuple[bytes, str]] = {}  # Storage: caminho na pasta "anexos" -> (dados, tipo)
        self.sem_anexos = False  # finge um servidor sem o SQL da 1.10
        self._seq = 0
        self.anonimo_ligado = True
        self.confirmar_email = False
        self.lock = threading.Lock()

    def ranking_semana(self) -> list[dict]:
        perfis = {p["id"]: p for p in self.tabelas["perfis"]}
        saida = []
        for e in self.tabelas["estatisticas"]:
            p = perfis.get(e["usuario_id"])
            if not p or p.get("bloqueado"):
                continue
            taxa = round(e["acertos"] / e["questoes"], 4) if e["questoes"] else None
            saida.append({**e, "apelido": p["apelido"], "concurso": p.get("concurso", ""), "taxa": taxa})
        return saida

    def eh_admin(self, uid: str) -> bool:
        return any(p["id"] == uid and p.get("papel") == "admin" for p in self.tabelas["perfis"])

    def ranking_grupo(self) -> list[dict]:
        rs = self.ranking_semana()
        return [{"codigo": m["codigo"], **r} for m in self.tabelas["membros"] for r in rs if r["usuario_id"] == m["usuario_id"]]

    # ---- fórum: as mesmas regras do ranking.sql
    def eh_membro(self, uid: str, cod: str) -> bool:
        return any(m["codigo"] == cod and m["usuario_id"] == uid for m in self.tabelas["membros"])

    def modera(self, uid: str, cod: str) -> bool:
        return self.eh_admin(uid) or any(g["codigo"] == cod and g.get("criado_por") == uid for g in self.tabelas["grupos"])

    def pode_escrever(self, uid: str, cod: str) -> bool:
        bloqueado = any(p["id"] == uid and p.get("bloqueado") for p in self.tabelas["perfis"])
        return self.eh_membro(uid, cod) and not bloqueado

    def ve(self, uid: str, cod: str) -> bool:
        return self.eh_membro(uid, cod) or self.eh_admin(uid)

    def apelido(self, uid: str) -> str:
        return next((p["apelido"] for p in self.tabelas["perfis"] if p["id"] == uid), "?")

    def forum_feed(self, uid: str) -> list[dict]:
        saida = []
        for f in self.tabelas["forum_posts"]:
            if not self.ve(uid, f["codigo"]):
                continue
            n_resp = sum(1 for r in self.tabelas["forum_respostas"] if r["post_id"] == f["id"])
            n_util = sum(1 for u in self.tabelas["forum_uteis"] if u["post_id"] == f["id"])
            saida.append({**f, "apelido": self.apelido(f["autor"]), "respostas": n_resp, "uteis": n_util})
        return saida

    def forum_respostas_v(self, uid: str) -> list[dict]:
        return [{**r, "apelido": self.apelido(r["autor"])} for r in self.tabelas["forum_respostas"] if self.ve(uid, r["codigo"])]

    def post(self, pid) -> dict | None:
        return next((f for f in self.tabelas["forum_posts"] if str(f["id"]) == str(pid)), None)


def _conteudo_valido(n: dict, codigo: str) -> bool:
    anexos, figurinha = n.get("anexos"), n.get("figurinha")
    if not ((n.get("titulo") or "") + (n.get("texto") or "")) and not anexos and not figurinha:
        return False
    if figurinha is not None and not re.fullmatch(r"[a-z0-9-]{1,40}", str(figurinha)):
        return False
    for a in anexos or []:
        if a.get("tipo") not in ("imagem", "gif", "arquivo"):
            return False
        ok_caminho = str(a.get("caminho") or "").startswith(codigo + "/") and ".." not in str(a.get("caminho"))
        ok_gif = a.get("tipo") == "gif" and re.match(r"^https://media[0-9]?\.giphy\.com/", str(a.get("url") or ""))
        if not (ok_caminho or ok_gif):
            return False
    return True


def agora_iso(minutos_atras: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).isoformat()


def _comparavel(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
        except ValueError:
            return str(v)


def _filtrar(linhas: list[dict], filtros: list[tuple[str, str]]) -> list[dict]:
    out = linhas
    for col, expr in filtros:
        op, _, val = expr.partition(".")
        if op == "eq":
            out = [l for l in out if (str(l.get(col)).lower() if isinstance(l.get(col), bool) else str(l.get(col))) == val]
        elif op == "in":
            vals = val.strip("()").split(",")
            out = [l for l in out if str(l.get(col)) in vals]
        elif op == "neq":
            out = [l for l in out if str(l.get(col)) != val]
        elif op in ("gte", "gt"):
            alvo = _comparavel(val)
            out = [l for l in out if l.get(col) is not None and (_comparavel(l[col]) >= alvo if op == "gte" else _comparavel(l[col]) > alvo)]
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
        return {"access_token": f"tok-{uid}", "refresh_token": f"ref-{uid}", "expires_in": 3600,
                "user": {"id": uid, "email": u["email"], "is_anonymous": not u["email"]}}

    def _storage(self, metodo: str, caminho: str):
        """Pasta privada "anexos" do Storage, com as regras do ranking.sql."""
        d, uid = self.dados, self._uid()
        negado = (403, {"statusCode": "403", "error": "Unauthorized", "message": "new row violates row-level security policy"})
        if d.sem_anexos:
            return self._json(400, {"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"})
        if metodo == "DELETE" and caminho == "/storage/v1/object/anexos":
            pedidos = (self._corpo() or {}).get("prefixes") or []
            apagados = []
            for c in pedidos:
                partes = c.split("/")
                if c in d.arquivos and uid and (partes[1] == uid or d.modera(uid, partes[0])):
                    d.arquivos.pop(c)
                    apagados.append({"name": c})
            return self._json(200, apagados)
        m = re.match(r"/storage/v1/object/(authenticated/)?anexos/(.+)$", caminho)
        if not m or not uid:
            return self._json(400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
        nome = unquote(m.group(2))
        partes = nome.split("/")
        if metodo == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            dados = self.rfile.read(n)
            if len(partes) < 3 or partes[1] != uid or not d.pode_escrever(uid, partes[0]):
                return self._json(*negado)
            if n > 20 * 1024 * 1024:
                return self._json(413, {"statusCode": "413", "error": "Payload too large", "message": "The object exceeded the maximum allowed size"})
            d.arquivos[nome] = (dados, self.headers.get("Content-Type", "application/octet-stream"))
            return self._json(200, {"Key": "anexos/" + nome})
        if metodo == "GET":
            if nome not in d.arquivos or not d.ve(uid, partes[0]):
                return self._json(400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
            dados, tipo = d.arquivos[nome]
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
            return None
        return self._json(405, {"message": "método não suportado"})

    def _rota(self, metodo: str):
        if self.headers.get("apikey") != CHAVE:
            return self._json(401, {"message": "Invalid API key"})
        partes = urlsplit(self.path)
        caminho, query = partes.path, parse_qsl(partes.query, keep_blank_values=True)
        d = self.dados
        if caminho.startswith("/storage/v1/"):
            with d.lock:
                return self._storage(metodo, caminho)
        with d.lock:
            if caminho == "/rest/v1/rpc/convite_info":
                cod = str((self._corpo() or {}).get("cod") or "").strip().upper()
                g = next((g for g in d.tabelas["grupos"] if g["codigo"] == cod), None)
                n = sum(1 for m in d.tabelas["membros"] if m["codigo"] == cod)
                return self._json(200, [{"codigo": g["codigo"], "nome": g["nome"], "membros": n}] if g else [])
            if caminho == "/auth/v1/signup":
                c = self._corpo() or {}
                if not c.get("email"):
                    # login anônimo (entrada rápida)
                    if not d.anonimo_ligado:
                        return self._json(422, {"code": 422, "error_code": "anonymous_provider_disabled", "msg": "Anonymous sign-ins are disabled"})
                    uid = str(uuid.uuid4())
                    d.usuarios[uid] = {"email": "", "senha": ""}
                    return self._json(200, self._sessao(uid))
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
            if caminho == "/auth/v1/user" and metodo == "PUT":
                c = self._corpo() or {}
                u = d.usuarios[uid]
                if c.get("email"):
                    if any(x["email"] == c["email"] for k, x in d.usuarios.items() if k != uid):
                        return self._json(422, {"code": 422, "error_code": "email_exists", "msg": "A user with this email address has already been registered"})
                    if d.confirmar_email:
                        u["email_pendente"] = c["email"]
                    else:
                        u["email"] = c["email"]
                if c.get("password"):
                    if not u["email"]:
                        return self._json(422, {"code": 422, "msg": "Email must be verified before setting a password"})
                    u["senha"] = c["password"]
                return self._json(200, self._sessao(uid)["user"])
            if caminho == "/rest/v1/rpc/virar_primeiro_admin":
                if not d.usuarios[uid]["email"] or any(p.get("papel") == "admin" for p in d.tabelas["perfis"]):
                    return self._json(200, False)
                for p in d.tabelas["perfis"]:
                    if p["id"] == uid:
                        p["papel"] = "admin"
                        return self._json(200, True)
                return self._json(200, False)
            if caminho == "/rest/v1/rpc/apagar_minha_conta":
                d.usuarios.pop(uid, None)
                for t in d.tabelas:
                    d.tabelas[t] = [l for l in d.tabelas[t] if l.get("id") != uid and l.get("usuario_id") != uid and l.get("autor") != uid]
                return self._json(204)
            m = re.match(r"/rest/v1/(\w+)$", caminho)
            if not m:
                return self._json(404, {"message": "not found"})
            tabela = m.group(1)
            filtros = [(k, unquote(v)) for k, v in query if k not in ("select", "order", "limit", "on_conflict")]
            selecao = dict(query).get("select", "")
            if d.sem_anexos and ("anexos" in selecao or "figurinha" in selecao or tabela == "config"):
                coluna = "anexos" if tabela != "config" else "config"
                return self._json(400, {"code": "42703", "message": f"column {tabela}.{coluna} does not exist"})
            if metodo == "GET":
                if tabela == "ranking_semana":
                    linhas = d.ranking_semana()
                elif tabela == "ranking_grupo":
                    linhas = d.ranking_grupo()
                elif tabela == "comunicados" and not d.eh_admin(uid):
                    linhas = [c for c in d.tabelas[tabela] if c["ativo"]]
                elif tabela == "forum_feed":
                    linhas = d.forum_feed(uid)
                elif tabela == "forum_respostas_v":
                    linhas = d.forum_respostas_v(uid)
                elif tabela in ("forum_posts", "forum_respostas", "forum_uteis"):
                    linhas = [l for l in d.tabelas[tabela] if d.ve(uid, l["codigo"])]
                else:
                    linhas = d.tabelas[tabela]
                linhas = _filtrar(linhas, filtros)
                ordem = dict(query).get("order", "")
                for parte in reversed(ordem.split(",") if ordem else []):
                    col, *mods = parte.split(".")
                    com = sorted((l for l in linhas if l.get(col) is not None), key=lambda l: l[col], reverse="desc" in mods)
                    linhas = com + [l for l in linhas if l.get(col) is None]
                limite = int(dict(query).get("limit", 1000))
                return self._json(200, linhas[:limite])
            if metodo == "POST":
                corpo = self._corpo()
                novas = corpo if isinstance(corpo, list) else [corpo]
                chave = [c for c in dict(query).get("on_conflict", "").split(",") if c]
                for n in novas:
                    if tabela.startswith("forum_"):
                        erro = self._forum_inserir(tabela, dict(n), uid)
                        if erro:
                            return self._json(*erro)
                        continue
                    if tabela == "config":
                        if not d.eh_admin(uid):
                            return self._json(403, {"code": "42501", "message": "new row violates row-level security policy"})
                        existente = next((l for l in d.tabelas["config"] if l["chave"] == n.get("chave")), None)
                        if existente:
                            existente.update(n)
                        else:
                            d.tabelas["config"].append(dict(n))
                        continue
                    if tabela == "comunicados":
                        if not d.eh_admin(uid):
                            return self._json(403, {"code": "42501", "message": "new row violates row-level security policy"})
                        d._seq += 1
                        d.tabelas["comunicados"].append({"id": d._seq, "ativo": True, "criado_em": "2026-10-25T10:00:00", **n})
                        continue
                    dono = n.get("id") if tabela == "perfis" else n.get("criado_por") if tabela == "grupos" else n.get("usuario_id")
                    if dono != uid:
                        return self._json(403, {"code": "42501", "message": "new row violates row-level security policy"})
                    if tabela == "perfis" and not d.eh_admin(uid):
                        # gatilho proteger_perfil: o aluno não escolhe o próprio papel
                        atual = next((p for p in d.tabelas["perfis"] if p["id"] == uid), None)
                        n["papel"] = atual.get("papel", "aluno") if atual else "aluno"
                        n["bloqueado"] = atual.get("bloqueado", False) if atual else False
                        n.setdefault("criado_em", "2026-10-25T09:00:00")
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
            if metodo == "PATCH":
                corpo = self._corpo() or {}
                alvo = _filtrar(d.tabelas[tabela], filtros)
                admin = d.eh_admin(uid)
                for l in alvo:
                    if tabela == "perfis":
                        if l["id"] != uid and not admin:
                            continue  # RLS: não enxerga para atualizar
                        mudanca = dict(corpo)
                        if not admin:
                            mudanca.pop("papel", None)
                            mudanca.pop("bloqueado", None)
                        l.update(mudanca)
                    elif tabela == "comunicados" and admin:
                        l.update(corpo)
                    elif tabela == "forum_posts":
                        moderador, autor = d.modera(uid, l["codigo"]), l["autor"] == uid and d.pode_escrever(uid, l["codigo"])
                        if not (moderador or autor):
                            continue
                        mudanca = {k: v for k, v in corpo.items() if k in ("fixado", "titulo", "texto", "plano", "tipo")}
                        if not moderador:
                            mudanca.pop("fixado", None)
                        if not autor:
                            mudanca = {k: v for k, v in mudanca.items() if k == "fixado"}
                        elif set(mudanca) - {"fixado"}:
                            mudanca["editado_em"] = agora_iso()
                        l.update(mudanca)
                return self._json(204)
            if metodo == "DELETE":
                alvo = _filtrar(d.tabelas[tabela], filtros)
                admin = d.eh_admin(uid)
                if tabela == "grupos":
                    apagar = [g for g in alvo if admin or g.get("criado_por") == uid]
                    cods = {g["codigo"] for g in apagar}
                    d.tabelas["grupos"] = [g for g in d.tabelas["grupos"] if g not in apagar]
                    for t in ("membros", "forum_posts", "forum_respostas", "forum_uteis"):
                        d.tabelas[t] = [m for m in d.tabelas[t] if m["codigo"] not in cods]
                elif tabela in ("forum_posts", "forum_respostas"):
                    apagar = [l for l in alvo if l["autor"] == uid or d.modera(uid, l["codigo"])]
                    d.tabelas[tabela] = [l for l in d.tabelas[tabela] if l not in apagar]
                    if tabela == "forum_posts":
                        ids = {l["id"] for l in apagar}
                        for t in ("forum_respostas", "forum_uteis"):
                            d.tabelas[t] = [l for l in d.tabelas[t] if l["post_id"] not in ids]
                elif tabela == "comunicados":
                    if admin:
                        d.tabelas["comunicados"] = [c for c in d.tabelas["comunicados"] if c not in alvo]
                else:
                    d.tabelas[tabela] = [l for l in d.tabelas[tabela] if l not in alvo or l.get("usuario_id") != uid]
                return self._json(204)
        return self._json(405, {"message": "método não suportado"})

    def _forum_inserir(self, tabela: str, n: dict, uid: str):
        """Insere no fórum com as regras do ranking.sql. Devolve (código, corpo) se recusar."""
        d = self.dados
        negado = (403, {"code": "42501", "message": "new row violates row-level security policy"})
        checagem = (400, {"code": "23514", "message": f'new row for relation "{tabela}" violates check constraint'})
        if tabela == "forum_posts":
            if n.get("autor") != uid or not d.pode_escrever(uid, n.get("codigo", "")):
                return negado
            if not _conteudo_valido(n, n.get("codigo", "")):
                return checagem
            d._seq += 1
            linha = {"id": d._seq, "tipo": "conversa", "titulo": "", "texto": "", "plano": None, "editado_em": None, "anexos": None, "figurinha": None, **n}
            linha["fixado"] = bool(n.get("fixado")) and d.modera(uid, n["codigo"])
            linha["criado_em"] = agora_iso()
            d.tabelas["forum_posts"].append(linha)
            return None
        post = d.post(n.get("post_id"))
        if post is None:
            return (400, {"code": "P0001", "message": "mensagem não encontrada"})
        n["codigo"] = post["codigo"]
        dono = n.get("autor") if tabela == "forum_respostas" else n.get("usuario_id")
        if dono != uid or not d.pode_escrever(uid, post["codigo"]):
            return negado
        if tabela == "forum_respostas":
            if not _conteudo_valido(n, post["codigo"]):
                return checagem
            d._seq += 1
            d.tabelas["forum_respostas"].append({"id": d._seq, "texto": "", "anexos": None, "figurinha": None, **n, "criado_em": agora_iso()})
            return None
        if any(u["post_id"] == n["post_id"] and u["usuario_id"] == uid for u in d.tabelas["forum_uteis"]):
            return (409, {"code": "23505", "message": 'duplicate key value violates unique constraint "forum_uteis_pkey"'})
        d.tabelas["forum_uteis"].append(n)
        return None

    def do_GET(self):
        self._rota("GET")

    def do_POST(self):
        self._rota("POST")

    def do_DELETE(self):
        self._rota("DELETE")

    def do_PATCH(self):
        self._rota("PATCH")

    def do_PUT(self):
        self._rota("PUT")


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
            self.dados.tabelas["perfis"].append({"id": uid, "apelido": apelido, "concurso": concurso, "papel": "aluno", "bloqueado": False, "criado_em": "2026-10-20T12:00:00"})
            self.dados.tabelas["estatisticas"].append({"usuario_id": uid, "semana": semana, **nums})
            if grupo:
                self.dados.tabelas["membros"].append({"codigo": grupo[0], "usuario_id": uid})
        if grupo and not any(g["codigo"] == grupo[0] for g in self.dados.tabelas["grupos"]):
            criador = self.dados.tabelas["perfis"][-len(pessoas)]["id"] if pessoas else None
            self.dados.tabelas["grupos"].append({"codigo": grupo[0], "nome": grupo[1], "criado_por": criador})

    def uid_de(self, apelido: str) -> str:
        return next(p["id"] for p in self.dados.tabelas["perfis"] if p["apelido"] == apelido)

    def semear_forum(self, codigo: str):
        """Conversa de exemplo num grupo (para testar e tirar capturas de tela)."""
        d = self.dados

        def post(apelido, minutos, tipo, texto, titulo="", plano=None, fixado=False, anexos=None, figurinha=None):
            d._seq += 1
            d.tabelas["forum_posts"].append({
                "id": d._seq, "codigo": codigo, "autor": self.uid_de(apelido), "tipo": tipo, "titulo": titulo, "texto": texto,
                "plano": plano, "fixado": fixado, "criado_em": agora_iso(minutos), "editado_em": None, "anexos": anexos, "figurinha": figurinha,
            })
            return d._seq

        def resposta(pid, apelido, minutos, texto, figurinha=None):
            d._seq += 1
            d.tabelas["forum_respostas"].append({"id": d._seq, "post_id": pid, "codigo": codigo, "autor": self.uid_de(apelido), "texto": texto,
                                                 "criado_em": agora_iso(minutos), "anexos": None, "figurinha": figurinha})

        def arquivo(apelido, nome, dados, tipo, mime, **extra):
            caminho = f"{codigo}/{self.uid_de(apelido)}/{d._seq:04d}-{nome.replace(' ', '-')}"
            d.arquivos[caminho] = (dados, mime)
            return {"tipo": tipo, "caminho": caminho, "nome": nome, "tamanho": len(dados), "mime": mime, **extra}

        def mapa_mental() -> bytes:
            import io

            from PIL import Image, ImageDraw

            im = Image.new("RGB", (1200, 760), (250, 248, 242))
            dr = ImageDraw.Draw(im)
            dr.rounded_rectangle((470, 300, 730, 440), radius=30, fill=(35, 64, 168))
            dr.text((520, 355), "ATOS ADMINISTRATIVOS", fill=(255, 255, 255))
            for (x, y, cor, rot) in ((120, 90, (29, 127, 83), "Competência"), (880, 90, (232, 96, 76), "Finalidade"),
                                     (120, 560, (201, 142, 18), "Forma"), (880, 560, (122, 79, 48), "Motivo"), (500, 600, (90, 60, 160), "Objeto")):
                dr.line((600, 370, x + 100, y + 50), fill=(150, 156, 170), width=6)
                dr.rounded_rectangle((x, y, x + 200, y + 100), radius=24, fill=cor)
                dr.text((x + 40, y + 42), rot, fill=(255, 255, 255))
            saida = io.BytesIO()
            im.save(saida, "PNG")
            return saida.getvalue()

        def figurinha_propria() -> bytes:
            """Uma figurinha "importada do WhatsApp" de alguém (desenho simples, só para o teste)."""
            import io

            from PIL import Image, ImageDraw, ImageFont

            im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            dr = ImageDraw.Draw(im)
            dr.ellipse((36, 36, 476, 476), fill=(255, 255, 255, 255))
            dr.ellipse((52, 52, 460, 460), fill=(255, 196, 46, 255))
            dr.ellipse((170, 170, 210, 230), fill=(40, 30, 20, 255))
            dr.ellipse((302, 170, 342, 230), fill=(40, 30, 20, 255))
            dr.arc((150, 200, 362, 380), 15, 165, fill=(40, 30, 20, 255), width=16)
            try:
                fonte = ImageFont.load_default(size=58)
            except TypeError:
                fonte = ImageFont.load_default()
            dr.rounded_rectangle((96, 380, 416, 470), radius=26, fill=(35, 64, 168, 255), outline=(255, 255, 255, 255), width=8)
            dr.text((256, 425), "TÔ DENTRO", fill=(255, 255, 255, 255), font=fonte, anchor="mm")
            saida = io.BytesIO()
            im.save(saida, "WEBP", quality=90)
            return saida.getvalue()

        def util(pid, *apelidos):
            for a in apelidos:
                d.tabelas["forum_uteis"].append({"post_id": pid, "usuario_id": self.uid_de(a), "codigo": codigo})

        boas = post("Camila R.", 60 * 24 * 3, "conversa", "Bem-vindos à turma! Aqui a gente combina simulados, tira dúvidas e compartilha planos. Toda segunda eu posto o plano da semana.", "Regras da turma", fixado=True)
        util(boas, "Joao_TI", "Lia")
        plano = post(
            "Camila R.", 60 * 20, "plano",
            "Foco nas disciplinas que mais caem na FGV. Sábado é dia de simulado completo; domingo, só revisão leve.",
            "Plano 14h: reta final Dataprev",
            {"meta_horas": 14, "dias": [0, 1, 2, 3, 5], "semanas": 6, "concurso": "Dataprev 2026",
             "disciplinas": [{"nome": "Conhecimentos Específicos", "horas": 5}, {"nome": "Língua Portuguesa", "horas": 3},
                             {"nome": "Raciocínio Lógico", "horas": 2.5}, {"nome": "Segurança da Informação", "horas": 2}, {"nome": "Língua Inglesa", "horas": 1.5}]},
        )
        util(plano, "Joao_TI", "Lia", "Pedro M")
        resposta(plano, "Lia", 60 * 18, "Vou seguir esse! Só troquei o sábado pela quinta.")
        duvida = post("Joao_TI", 95, "duvida", "Na questão 32 da prova de 2024, por que a resposta é a C e não a D? O texto fala em \"exceto\", me confundi.", "Questão 32 de Português (2024)")
        resposta(duvida, "Camila R.", 80, "Pegadinha clássica: o \"exceto\" inverte. A D está correta segundo o texto, então ela NÃO é a resposta.")
        resposta(duvida, "Joao_TI", 70, "Ahh, agora fez sentido. Valeu!")
        util(duvida, "Lia")
        post("Lia", 25, "material", "Resumo de LGPD em uma página que ajudou muito: https://www.gov.br/anpd", "Resumo de LGPD")
        mapa = post("Joao_TI", 14, "material", "Fiz esse mapa mental dos elementos do ato administrativo. E a lei comentada que o professor passou:", "Mapa mental: atos administrativos",
                    anexos=[arquivo("Joao_TI", "mapa atos administrativos.png", mapa_mental(), "imagem", "image/png", largura=1200, altura=760),
                            arquivo("Joao_TI", "Lei 8.112 comentada.pdf", b"%PDF-1.4 " + b"x" * 240_000, "arquivo", "application/pdf")])
        resposta(mapa, "Lia", 11, "", figurinha="valeu")
        util(mapa, "Camila R.", "Lia")
        post("Pedro M", 8, "conversa", "Alguém topa simulado completo no sábado às 9h? Cada um faz em casa e depois a gente compara aqui.")
        post("Bruna.fiscal", 6, "conversa", "", anexos=[arquivo("Bruna.fiscal", "figurinha.webp", figurinha_propria(), "imagem", "image/webp", largura=512, altura=512, figurinha=True)])
        post("Lia", 5, "conversa", "", figurinha="bora-estudar")


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
    srv.semear_forum("DATAPREV-7A2F")
    print("servidor falso em", srv.url, "chave:", CHAVE, flush=True)
    srv.httpd.serve_forever()
