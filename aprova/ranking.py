"""Contas do Aprova (aluno e administrador), ranking e fórum dos grupos, num projeto Supabase (grátis).

- O endereço e a chave pública do projeto ficam em `ranking.json`, na pasta do app
  (vão junto no .zip para os testadores). A chave "anon" é pública por natureza:
  quem protege os dados são as regras de acesso do arquivo supabase/ranking.sql.
- A senha nunca fica no computador: guardamos só o token de sessão.
- No ranking aparecem apenas o apelido e os números de estudo da semana.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from . import analise, config

ARQUIVO = Path(os.environ.get("APROVA_RANKING_ARQUIVO") or config.RAIZ / "ranking.json")
# servidor que vai junto com o app (endereço e chave pública); ranking.json, se existir, vale mais
PADRAO = Path(__file__).resolve().parent / "servidor.json"
METRICAS = {
    "horas": ("segundos", "Horas"),
    "questoes": ("questoes", "Questões"),
    "acerto": ("taxa", "Acerto"),
    "sequencia": ("sequencia", "Sequência"),
}
MIN_QUESTOES_ACERTO = 30  # para entrar no ranking de acerto


class ErroRanking(Exception):
    pass


def _ler_config(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    url = str(dados.get("url") or "").strip().rstrip("/")
    chave = str(dados.get("chave") or "").strip()
    if not (url.startswith("http") and chave):
        return {}
    cfg = {"url": url, "chave": chave}
    if str(dados.get("convite") or "").startswith("http"):
        cfg["convite"] = str(dados["convite"]).strip()
    return cfg


def carregar_config(caminho: Path | None = None) -> dict:
    if caminho is not None:
        return _ler_config(caminho)
    cfg = _ler_config(ARQUIVO)
    if cfg or os.environ.get("APROVA_RANKING_ARQUIVO"):
        return cfg
    return _ler_config(PADRAO)


def salvar_config(url: str, chave: str, caminho: Path | None = None) -> None:
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://", url):
        raise ErroRanking("O endereço do projeto deve começar com https://")
    chave = chave.strip()
    if len(chave) < 20:
        raise ErroRanking("A chave parece incompleta. Copie a chave 'anon public' inteira.")
    if chave.startswith("sb_secret_") or _papel_jwt(chave) == "service_role":
        raise ErroRanking("Essa é a chave secreta (service_role). Use a chave pública: 'anon public' ou 'publishable'.")
    (caminho or ARQUIVO).write_text(json.dumps({"url": url, "chave": chave.strip()}, indent=2), encoding="utf-8")


def _papel_jwt(chave: str) -> str:
    """Lê o campo 'role' de uma chave no formato JWT (sem validar a assinatura)."""
    import base64

    partes = chave.split(".")
    if len(partes) != 3:
        return ""
    try:
        meio = partes[1] + "=" * (-len(partes[1]) % 4)
        return str(json.loads(base64.urlsafe_b64decode(meio)).get("role", ""))
    except (ValueError, json.JSONDecodeError):
        return ""


def inicio_semana(d: date | None = None) -> date:
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def estatisticas_locais(banco, semana: date) -> dict:
    """Números de uma semana (segunda a domingo) para enviar ao ranking."""
    fim = semana + timedelta(days=7)
    tempo = banco.tempo_por_dia(semana)
    segundos = sum(s for d, s in tempo.items() if d < fim.isoformat())
    resp = [r for r in banco.respostas_corrigidas(semana) if r["dia"] < fim.isoformat()]
    questoes_dia = banco.dias_com_questoes(semana)
    dias = 0
    for i in range(7):
        k = (semana + timedelta(days=i)).isoformat()
        if tempo.get(k, 0) >= analise.MIN_SEGUNDOS_DIA or questoes_dia.get(k, 0) > 0:
            dias += 1
    seq = analise.resumo_tempo(banco)["sequencia"] if semana == inicio_semana() else 0
    return {
        "semana": semana.isoformat(),
        "segundos": min(int(segundos), 360000),
        "questoes": min(len(resp), 10000),
        "acertos": min(sum(1 for r in resp if r["correta"]), len(resp), 10000),
        "dias": dias,
        "sequencia": min(seq, 3650),
    }


def _mensagem(resp: requests.Response) -> str:
    try:
        d = resp.json()
    except ValueError:
        return f"erro {resp.status_code}"
    texto = d.get("msg") or d.get("error_description") or d.get("message") or d.get("error") or ""
    codigo = str(d.get("code") or d.get("error_code") or "")
    t = texto.lower()
    if "invalid login" in t or codigo == "invalid_credentials":
        return "E-mail ou senha incorretos."
    if "already registered" in t or "already been registered" in t or codigo == "user_already_exists":
        return "Já existe uma conta com esse e-mail. Use Entrar."
    if "password" in t and ("6" in t or "short" in t or "weak" in t):
        return "Use uma senha com pelo menos 6 caracteres."
    if "email not confirmed" in t or codigo == "email_not_confirmed":
        return "Confirme seu e-mail (veja a caixa de entrada) e depois entre."
    if "invalid" in t and "email" in t:
        return "Esse e-mail não parece válido."
    if codigo == "23505" or "duplicate key" in t:
        if "apelido" in t or "perfis" in t:
            return "Esse apelido já está em uso. Escolha outro."
        return "Esse registro já existe."
    if "rate limit" in t or resp.status_code == 429:
        return "Muitas tentativas seguidas. Espere um minuto e tente de novo."
    if "jwt" in t and "expired" in t:
        return "Sua sessão expirou. Entre de novo."
    return texto or f"erro {resp.status_code}"


class Ranking:
    """Cliente do ranking. Guarda a sessão nos ajustes do app."""

    def __init__(self, ajustes, cfg: dict | None = None):
        self.aj = ajustes
        self.cfg = cfg if cfg is not None else carregar_config()
        self._token = ""
        self._expira = 0.0
        self._lock = threading.Lock()

    # ---- estado

    @property
    def configurado(self) -> bool:
        return bool(self.cfg.get("url") and self.cfg.get("chave"))

    @property
    def logado(self) -> bool:
        return bool(self.aj.get("ranking_refresh", "")) and bool(self.aj.get("ranking_usuario", ""))

    @property
    def apelido(self) -> str:
        return self.aj.get("ranking_apelido", "") or ""

    @property
    def usuario_id(self) -> str:
        return self.aj.get("ranking_usuario", "") or ""

    @property
    def papel(self) -> str:
        return self.aj.get("ranking_papel", "") or "aluno"

    @property
    def eh_admin(self) -> bool:
        return self.logado and self.papel == "admin"

    @property
    def email(self) -> str:
        return self.aj.get("ranking_email", "") or ""

    @property
    def eh_anonimo(self) -> bool:
        """Conta rápida (entrou só com apelido): vale só neste computador até ganhar e-mail e senha."""
        return self.logado and bool(self.aj.get("ranking_anonimo", False))

    def recarregar_config(self) -> None:
        self.cfg = carregar_config()

    # ---- http

    def _url(self, caminho: str) -> str:
        return self.cfg["url"] + caminho

    def _cab(self, autenticado: bool = True, extra: dict | None = None) -> dict:
        cab = {"apikey": self.cfg["chave"], "Content-Type": "application/json"}
        if autenticado:
            cab["Authorization"] = f"Bearer {self._sessao()}"
        if extra:
            cab.update(extra)
        return cab

    def _pedir(self, metodo: str, caminho: str, autenticado: bool = True, **kw) -> requests.Response:
        if not self.configurado:
            raise ErroRanking("O ranking ainda não foi configurado neste app.")
        extra = kw.pop("cabecalhos", None)
        try:
            resp = requests.request(metodo, self._url(caminho), headers=self._cab(autenticado, extra), timeout=20, **kw)
        except requests.RequestException as e:
            raise ErroRanking("Sem conexão com o servidor do ranking. Confira a internet.") from e
        if resp.status_code == 401 and autenticado:
            # token venceu no meio do caminho: renova uma vez
            self._expira = 0
            resp = requests.request(metodo, self._url(caminho), headers=self._cab(True, extra), timeout=20, **kw)
        if resp.status_code >= 400:
            raise ErroRanking(_mensagem(resp))
        return resp

    def _guardar_sessao(self, dados: dict) -> None:
        self._token = dados["access_token"]
        self._expira = time.time() + int(dados.get("expires_in") or 3600) - 60
        self.aj.set("ranking_refresh", dados.get("refresh_token", ""))
        usuario = dados.get("user") or {}
        if usuario.get("id"):
            self.aj.set("ranking_usuario", usuario["id"])
        if usuario.get("email"):
            self.aj.set("ranking_email", usuario["email"])
        if usuario:
            self.aj.set("ranking_anonimo", bool(usuario.get("is_anonymous")))

    def _sessao(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expira:
                return self._token
            refresh = self.aj.get("ranking_refresh", "")
            if not refresh:
                raise ErroRanking("Entre na sua conta do ranking.")
            try:
                resp = requests.post(
                    self._url("/auth/v1/token?grant_type=refresh_token"),
                    headers={"apikey": self.cfg["chave"], "Content-Type": "application/json"},
                    json={"refresh_token": refresh},
                    timeout=20,
                )
            except requests.RequestException as e:
                raise ErroRanking("Sem conexão com o servidor do ranking. Confira a internet.") from e
            if resp.status_code >= 400:
                self._limpar()
                raise ErroRanking("Sua sessão expirou. Entre de novo.")
            self._guardar_sessao(resp.json())
            return self._token

    def _limpar(self) -> None:
        self._token = ""
        self._expira = 0
        for k in ("ranking_refresh", "ranking_usuario", "ranking_apelido", "ranking_email", "ranking_papel"):
            self.aj.set(k, "")
        self.aj.set("ranking_anonimo", False)

    # ---- conta

    def criar_conta(self, email: str, senha: str, apelido: str, concurso: str = "") -> str:
        """Cria a conta e o perfil. Devolve 'ok' ou 'confirmar' (quando o projeto exige confirmar o e-mail)."""
        apelido = validar_apelido(apelido)
        resp = self._pedir("POST", "/auth/v1/signup", autenticado=False, json={"email": email.strip(), "password": senha, "data": {"apelido": apelido}})
        dados = resp.json()
        if not dados.get("access_token"):
            self.aj.set("ranking_apelido_pendente", apelido)
            self.aj.set("ranking_concurso_pendente", concurso)
            return "confirmar"
        self._guardar_sessao(dados)
        self.salvar_perfil(apelido, concurso)
        self._depois_de_entrar()
        return "ok"

    def entrar_rapido(self, apelido: str = "") -> dict:
        """Conta rápida, sem e-mail e senha (login anônimo do Supabase): a pessoa só confirma o apelido."""
        apelido = validar_apelido(apelido or sugerir_apelido())
        try:
            resp = self._pedir("POST", "/auth/v1/signup", autenticado=False, json={"data": {"apelido": apelido}})
        except ErroRanking as e:
            t = str(e).lower()
            if "anonymous" in t or "disabled" in t or "signups not allowed" in t:
                raise ErroRanking("A entrada rápida está desligada no servidor. Crie a conta com e-mail e senha.") from e
            raise
        dados = resp.json()
        if not dados.get("access_token"):
            raise ErroRanking("O servidor não liberou a entrada rápida. Crie a conta com e-mail e senha.")
        self._guardar_sessao(dados)
        self.aj.set("ranking_anonimo", True)
        base, perfil = apelido, None
        for tentativa in range(6):
            try:
                perfil = self.salvar_perfil(apelido)
                break
            except ErroRanking as e:
                if "apelido já está em uso" not in str(e) or tentativa == 5:
                    raise
                apelido = f"{base[:19]} {secrets.randbelow(900) + 100}"
        self._depois_de_entrar()
        return perfil or {}

    def proteger_conta(self, email: str, senha: str) -> str:
        """Dá e-mail e senha à conta rápida (vira conta normal, que entra de qualquer computador).

        Devolve 'ok' ou 'confirmar' (o servidor mandou um e-mail para confirmar; depois a pessoa cria a senha)."""
        email = (email or "").strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise ErroRanking("Digite um e-mail válido.")
        if len(senha or "") < 6:
            raise ErroRanking("Use uma senha com pelo menos 6 caracteres.")
        usuario = self._pedir("PUT", "/auth/v1/user", json={"email": email}).json()
        if (usuario.get("email") or "").lower() != email.lower():
            self.aj.set("ranking_email_pendente", email)
            return "confirmar"
        self._pedir("PUT", "/auth/v1/user", json={"password": senha})
        self.aj.set("ranking_email", email)
        self.aj.set("ranking_anonimo", False)
        self.aj.set("ranking_email_pendente", "")
        return "ok"

    def criar_senha(self, senha: str) -> str:
        """Depois de confirmar o e-mail: cria a senha da conta rápida."""
        if len(senha or "") < 6:
            raise ErroRanking("Use uma senha com pelo menos 6 caracteres.")
        self._expira = 0  # pega um token novo, já com o e-mail confirmado
        usuario = self._pedir("PUT", "/auth/v1/user", json={"password": senha}).json()
        if usuario.get("email"):
            self.aj.set("ranking_email", usuario["email"])
            self.aj.set("ranking_anonimo", False)
            self.aj.set("ranking_email_pendente", "")
            return "ok"
        return "confirmar"

    def convite_info(self, codigo: str) -> dict | None:
        """Nome e número de membros de um grupo pelo código do convite (funciona mesmo sem conta)."""
        codigo = (codigo or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{4,24}", codigo):
            return None
        linhas = self._pedir("POST", "/rest/v1/rpc/convite_info", autenticado=False, json={"cod": codigo}).json()
        if isinstance(linhas, dict):
            linhas = [linhas]
        if not linhas:
            return None
        g = linhas[0]
        return {"codigo": g.get("codigo") or codigo, "nome": g.get("nome") or codigo, "membros": int(g.get("membros") or 0)}

    def sou_membro(self, codigo: str) -> bool:
        linhas = self._pedir("GET", f"/rest/v1/membros?codigo=eq.{codigo}&usuario_id=eq.{self.usuario_id}&select=codigo").json()
        return bool(linhas)

    def entrar(self, email: str, senha: str) -> dict | None:
        """Entra e devolve o perfil (None se a conta ainda não tem apelido)."""
        resp = self._pedir("POST", "/auth/v1/token?grant_type=password", autenticado=False, json={"email": email.strip(), "password": senha})
        self._guardar_sessao(resp.json())
        perfil = self.perfil()
        if perfil is None and self.aj.get("ranking_apelido_pendente", ""):
            perfil = self.salvar_perfil(self.aj.get("ranking_apelido_pendente", ""), self.aj.get("ranking_concurso_pendente", ""))
            self.aj.set("ranking_apelido_pendente", "")
        if perfil:
            self.aj.set("ranking_apelido", perfil["apelido"])
            perfil = self._depois_de_entrar() or perfil
        return perfil

    def _depois_de_entrar(self) -> dict | None:
        """O primeiro usuário do servidor vira administrador; depois atualiza o papel guardado."""
        try:
            self._pedir("POST", "/rest/v1/rpc/virar_primeiro_admin", json={})
        except ErroRanking:
            pass
        return self.atualizar_perfil()

    def atualizar_perfil(self) -> dict | None:
        """Relê apelido e papel no servidor (ex.: o admin mudou o seu papel)."""
        perfil = self.perfil()
        if perfil:
            self.aj.set("ranking_apelido", perfil.get("apelido", ""))
            self.aj.set("ranking_papel", perfil.get("papel") or "aluno")
        return perfil

    def recuperar_senha(self, email: str) -> None:
        self._pedir("POST", "/auth/v1/recover", autenticado=False, json={"email": email.strip()})

    def sair(self) -> None:
        try:
            if self.logado:
                self._pedir("POST", "/auth/v1/logout")
        except ErroRanking:
            pass
        self._limpar()

    def apagar_conta(self) -> None:
        self._pedir("POST", "/rest/v1/rpc/apagar_minha_conta", json={})
        self._limpar()

    def perfil(self) -> dict | None:
        resp = self._pedir("GET", f"/rest/v1/perfis?id=eq.{self.usuario_id}&select=id,apelido,concurso,papel,bloqueado")
        linhas = resp.json()
        return linhas[0] if linhas else None

    def salvar_perfil(self, apelido: str, concurso: str = "") -> dict:
        apelido = validar_apelido(apelido)
        dados = {"id": self.usuario_id, "apelido": apelido, "concurso": concurso.strip()[:60]}
        self._pedir(
            "POST",
            "/rest/v1/perfis?on_conflict=id",
            json=dados,
            cabecalhos={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        self.aj.set("ranking_apelido", apelido)
        return dados

    # ---- números

    def enviar(self, banco) -> None:
        """Manda os números desta semana e da anterior."""
        if not (self.configurado and self.logado and self.apelido):
            return
        hoje = inicio_semana()
        linhas = [estatisticas_locais(banco, hoje), estatisticas_locais(banco, hoje - timedelta(days=7))]
        self._pedir(
            "POST",
            "/rest/v1/estatisticas?on_conflict=usuario_id,semana",
            json=[{**l, "usuario_id": self.usuario_id} for l in linhas],
            cabecalhos={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        self.aj.set("ranking_enviado", time.time())

    def ranking(self, metrica: str = "horas", semana: date | None = None, grupo: str | None = None, limite: int = 100) -> list[dict]:
        coluna = METRICAS.get(metrica, METRICAS["horas"])[0]
        semana = (semana or inicio_semana()).isoformat()
        tabela = "ranking_grupo" if grupo else "ranking_semana"
        filtros = [f"semana=eq.{semana}", "select=usuario_id,apelido,concurso,segundos,questoes,acertos,dias,sequencia,taxa"]
        if grupo:
            filtros.append(f"codigo=eq.{grupo}")
        if metrica == "acerto":
            filtros.append(f"questoes=gte.{MIN_QUESTOES_ACERTO}")
        filtros.append(f"order={coluna}.desc.nullslast,questoes.desc")
        filtros.append(f"limit={limite}")
        linhas = self._pedir("GET", f"/rest/v1/{tabela}?" + "&".join(filtros)).json()
        for i, l in enumerate(linhas, start=1):
            l["posicao"] = i
            l["voce"] = l.get("usuario_id") == self.usuario_id
        return linhas

    # ---- grupos

    def meus_grupos(self) -> list[dict]:
        cods = [m["codigo"] for m in self._pedir("GET", f"/rest/v1/membros?usuario_id=eq.{self.usuario_id}&select=codigo").json()]
        if not cods:
            return []
        lista = ",".join(cods)
        grupos = self._pedir("GET", f"/rest/v1/grupos?codigo=in.({lista})&select=codigo,nome,criado_por&order=nome").json()
        for g in grupos:
            g["modero"] = self.eh_admin or g.get("criado_por") == self.usuario_id
        return grupos

    def criar_grupo(self, nome: str) -> str:
        nome = nome.strip()
        if not 3 <= len(nome) <= 40:
            raise ErroRanking("O nome do grupo deve ter de 3 a 40 letras.")
        base = re.sub(r"[^A-Z0-9]", "", analise_norm(nome).upper())[:8] or "GRUPO"
        codigo = f"{base}-{secrets.token_hex(2).upper()}"
        self._pedir("POST", "/rest/v1/grupos", json={"codigo": codigo, "nome": nome, "criado_por": self.usuario_id}, cabecalhos={"Prefer": "return=minimal"})
        self.entrar_grupo(codigo)
        return codigo

    def entrar_grupo(self, codigo: str) -> dict:
        codigo = codigo.strip().upper()
        achados = self._pedir("GET", f"/rest/v1/grupos?codigo=eq.{codigo}&select=codigo,nome").json()
        if not achados:
            raise ErroRanking("Não achei um grupo com esse código. Confira com quem te passou.")
        try:
            self._pedir("POST", "/rest/v1/membros", json={"codigo": codigo, "usuario_id": self.usuario_id}, cabecalhos={"Prefer": "return=minimal"})
        except ErroRanking as e:
            if "já existe" not in str(e):
                raise
        return achados[0]

    def sair_grupo(self, codigo: str) -> None:
        self._pedir("DELETE", f"/rest/v1/membros?codigo=eq.{codigo}&usuario_id=eq.{self.usuario_id}")

    def membros_grupo(self, codigo: str) -> list[dict]:
        """Quem está no grupo (apelido e concurso), com quem criou o grupo marcado."""
        ids = [m["usuario_id"] for m in self._pedir("GET", f"/rest/v1/membros?codigo=eq.{codigo}&select=usuario_id&limit=1000").json()]
        if not ids:
            return []
        grupo = self._pedir("GET", f"/rest/v1/grupos?codigo=eq.{codigo}&select=criado_por").json()
        criador = grupo[0].get("criado_por") if grupo else None
        perfis = self._pedir("GET", f"/rest/v1/perfis?id=in.({','.join(ids)})&select=id,apelido,concurso,bloqueado").json()
        saida = [
            {"usuario_id": p["id"], "apelido": p["apelido"], "concurso": p.get("concurso") or "", "criador": p["id"] == criador, "voce": p["id"] == self.usuario_id}
            for p in perfis
            if not p.get("bloqueado")
        ]
        return sorted(saida, key=lambda m: (not m["criador"], m["apelido"].lower()))

    # ---- fórum dos grupos (o servidor só mostra para quem é do grupo)

    def forum(self, codigo: str, tipo: str | None = None, limite: int = 60) -> list[dict]:
        """Mensagens do grupo, fixadas primeiro. tipo='plano' traz só os planos; 'conversa', o resto."""
        filtros = [
            f"codigo=eq.{codigo}",
            "select=id,codigo,autor,apelido,tipo,titulo,texto,plano,fixado,criado_em,editado_em,respostas,uteis",
            "order=fixado.desc,criado_em.desc",
            f"limit={limite}",
        ]
        if tipo == "plano":
            filtros.append("tipo=eq.plano")
        elif tipo == "conversa":
            filtros.append("tipo=neq.plano")
        posts = self._pedir("GET", "/rest/v1/forum_feed?" + "&".join(filtros)).json()
        meus: set[int] = set()
        if posts:
            ids = ",".join(str(p["id"]) for p in posts)
            meus = {u["post_id"] for u in self._pedir("GET", f"/rest/v1/forum_uteis?post_id=in.({ids})&usuario_id=eq.{self.usuario_id}&select=post_id").json()}
        for p in posts:
            if isinstance(p.get("plano"), str):
                try:
                    p["plano"] = json.loads(p["plano"])
                except ValueError:
                    p["plano"] = None
            p["meu"] = p.get("autor") == self.usuario_id
            p["util_meu"] = p["id"] in meus
            p["respostas"] = int(p.get("respostas") or 0)
            p["uteis"] = int(p.get("uteis") or 0)
        return posts

    def forum_publicar(self, codigo: str, texto: str, tipo: str = "conversa", titulo: str = "", plano: dict | None = None) -> None:
        if tipo not in TIPOS_FORUM:
            raise ErroRanking("Tipo de mensagem inválido.")
        texto, titulo = (texto or "").strip(), re.sub(r"\s+", " ", (titulo or "").strip())
        if len(texto) > 4000:
            raise ErroRanking("A mensagem pode ter até 4000 letras.")
        if len(titulo) > 120:
            raise ErroRanking("O título pode ter até 120 letras.")
        if tipo == "plano":
            plano = validar_plano(plano or {})
            if len(titulo) < 3:
                raise ErroRanking("Dê um nome ao plano (ex.: Plano 12h para a Dataprev).")
        else:
            plano = None
            if not texto:
                raise ErroRanking("Escreva a mensagem.")
        corpo = {"codigo": codigo, "autor": self.usuario_id, "tipo": tipo, "titulo": titulo, "texto": texto, "plano": plano}
        self._pedir("POST", "/rest/v1/forum_posts", json=corpo, cabecalhos={"Prefer": "return=minimal"})

    def forum_respostas(self, post_id: int) -> list[dict]:
        linhas = self._pedir("GET", f"/rest/v1/forum_respostas_v?post_id=eq.{int(post_id)}&select=id,post_id,autor,apelido,texto,criado_em&order=criado_em.asc&limit=200").json()
        for l in linhas:
            l["meu"] = l.get("autor") == self.usuario_id
        return linhas

    def forum_responder(self, post_id: int, texto: str) -> None:
        texto = (texto or "").strip()
        if not 1 <= len(texto) <= 2000:
            raise ErroRanking("A resposta deve ter de 1 a 2000 letras.")
        self._pedir("POST", "/rest/v1/forum_respostas", json={"post_id": int(post_id), "autor": self.usuario_id, "texto": texto}, cabecalhos={"Prefer": "return=minimal"})

    def forum_util(self, post_id: int, marcar: bool) -> None:
        if marcar:
            try:
                self._pedir("POST", "/rest/v1/forum_uteis", json={"post_id": int(post_id), "usuario_id": self.usuario_id}, cabecalhos={"Prefer": "return=minimal"})
            except ErroRanking as e:
                if "já existe" not in str(e):
                    raise
        else:
            self._pedir("DELETE", f"/rest/v1/forum_uteis?post_id=eq.{int(post_id)}&usuario_id=eq.{self.usuario_id}")

    def forum_fixar(self, post_id: int, fixado: bool) -> None:
        self._pedir("PATCH", f"/rest/v1/forum_posts?id=eq.{int(post_id)}", json={"fixado": bool(fixado)}, cabecalhos={"Prefer": "return=minimal"})

    def forum_apagar(self, post_id: int) -> None:
        self._pedir("DELETE", f"/rest/v1/forum_posts?id=eq.{int(post_id)}")

    def forum_apagar_resposta(self, resposta_id: int) -> None:
        self._pedir("DELETE", f"/rest/v1/forum_respostas?id=eq.{int(resposta_id)}")

    def forum_novidades(self, codigos: list[str], vistos: dict[str, str]) -> dict[str, int]:
        """Quantas mensagens de outras pessoas chegaram em cada grupo desde a última visita."""
        if not codigos:
            return {}
        marcas = {c: _quando(vistos.get(c)) for c in codigos}
        desde = min(marcas.values())
        filtros = [
            f"codigo=in.({','.join(codigos)})",
            f"autor=neq.{self.usuario_id}",
            f"criado_em=gt.{quote(desde.isoformat(), safe='')}",
            "select=codigo,criado_em",
            "order=criado_em.desc",
            "limit=300",
        ]
        cont = {c: 0 for c in codigos}
        for l in self._pedir("GET", "/rest/v1/forum_feed?" + "&".join(filtros)).json():
            if l["codigo"] in cont and _quando(l["criado_em"]) > marcas[l["codigo"]]:
                cont[l["codigo"]] += 1
        return cont

    # ---- comunicados (todos leem; admin escreve)

    def comunicados(self, todos: bool = False) -> list[dict]:
        filtro = "" if todos else "ativo=eq.true&"
        return self._pedir("GET", f"/rest/v1/comunicados?{filtro}select=id,titulo,texto,ativo,criado_em&order=criado_em.desc&limit=20").json()

    # ---- administração (o servidor confere se você é admin)

    def _exigir_admin(self) -> None:
        if not self.eh_admin:
            raise ErroRanking("Só administradores podem fazer isso.")

    def usuarios(self, semana: date | None = None) -> list[dict]:
        """Todos os perfis com os números da semana (para a área do admin)."""
        self._exigir_admin()
        semana = (semana or inicio_semana()).isoformat()
        perfis = self._pedir("GET", "/rest/v1/perfis?select=id,apelido,concurso,papel,bloqueado,criado_em&order=criado_em.desc&limit=1000").json()
        nums = {
            e["usuario_id"]: e
            for e in self._pedir("GET", f"/rest/v1/estatisticas?semana=eq.{semana}&select=usuario_id,segundos,questoes,acertos,dias,sequencia,atualizado_em").json()
        }
        for p in perfis:
            e = nums.get(p["id"], {})
            p.update(
                segundos=e.get("segundos", 0),
                questoes=e.get("questoes", 0),
                acertos=e.get("acertos", 0),
                dias=e.get("dias", 0),
                sequencia=e.get("sequencia", 0),
                atualizado_em=e.get("atualizado_em"),
                voce=p["id"] == self.usuario_id,
            )
        return perfis

    def visao_geral(self, usuarios: list[dict] | None = None) -> dict:
        usuarios = usuarios if usuarios is not None else self.usuarios()
        semana = inicio_semana().isoformat()
        ativos = [u for u in usuarios if u["segundos"] or u["questoes"]]
        questoes = sum(u["questoes"] for u in usuarios)
        acertos = sum(u["acertos"] for u in usuarios)
        concursos: dict[str, int] = {}
        for u in usuarios:
            nome = (u.get("concurso") or "").strip()
            if nome:
                concursos[nome] = concursos.get(nome, 0) + 1
        return {
            "usuarios": len(usuarios),
            "novos": sum(1 for u in usuarios if str(u.get("criado_em") or "")[:10] >= semana),
            "ativos": len(ativos),
            "segundos": sum(u["segundos"] for u in usuarios),
            "questoes": questoes,
            "taxa": acertos / questoes if questoes else None,
            "admins": sum(1 for u in usuarios if u.get("papel") == "admin"),
            "bloqueados": sum(1 for u in usuarios if u.get("bloqueado")),
            "concursos": sorted(concursos.items(), key=lambda x: -x[1])[:6],
        }

    def definir_papel(self, usuario_id: str, papel: str) -> None:
        self._exigir_admin()
        if papel not in ("aluno", "admin"):
            raise ErroRanking("Papel inválido.")
        if usuario_id == self.usuario_id and papel != "admin":
            raise ErroRanking("Você não pode tirar o seu próprio acesso de administrador.")
        self._pedir("PATCH", f"/rest/v1/perfis?id=eq.{usuario_id}", json={"papel": papel}, cabecalhos={"Prefer": "return=minimal"})

    def bloquear(self, usuario_id: str, bloqueado: bool) -> None:
        self._exigir_admin()
        if usuario_id == self.usuario_id:
            raise ErroRanking("Você não pode bloquear a si mesmo.")
        self._pedir("PATCH", f"/rest/v1/perfis?id=eq.{usuario_id}", json={"bloqueado": bool(bloqueado)}, cabecalhos={"Prefer": "return=minimal"})

    def criar_comunicado(self, titulo: str, texto: str) -> None:
        self._exigir_admin()
        titulo, texto = titulo.strip(), texto.strip()
        if not 3 <= len(titulo) <= 80 or not 1 <= len(texto) <= 1000:
            raise ErroRanking("Título de 3 a 80 letras e texto de até 1000.")
        self._pedir("POST", "/rest/v1/comunicados", json={"titulo": titulo, "texto": texto, "criado_por": self.usuario_id}, cabecalhos={"Prefer": "return=minimal"})

    def ativar_comunicado(self, comunicado_id: int, ativo: bool) -> None:
        self._exigir_admin()
        self._pedir("PATCH", f"/rest/v1/comunicados?id=eq.{comunicado_id}", json={"ativo": bool(ativo)}, cabecalhos={"Prefer": "return=minimal"})

    def apagar_comunicado(self, comunicado_id: int) -> None:
        self._exigir_admin()
        self._pedir("DELETE", f"/rest/v1/comunicados?id=eq.{comunicado_id}")

    def todos_grupos(self) -> list[dict]:
        self._exigir_admin()
        grupos = self._pedir("GET", "/rest/v1/grupos?select=codigo,nome,criado_em&order=criado_em.desc&limit=500").json()
        membros = self._pedir("GET", "/rest/v1/membros?select=codigo&limit=10000").json()
        cont: dict[str, int] = {}
        for m in membros:
            cont[m["codigo"]] = cont.get(m["codigo"], 0) + 1
        for g in grupos:
            g["membros"] = cont.get(g["codigo"], 0)
        return grupos

    def apagar_grupo(self, codigo: str) -> None:
        self._pedir("DELETE", f"/rest/v1/grupos?codigo=eq.{codigo}")


TIPOS_FORUM = {
    "conversa": ("Conversa", "FORUM_OUTLINED"),
    "duvida": ("Dúvida", "HELP_OUTLINE"),
    "material": ("Material", "LINK"),
    "plano": ("Plano de estudo", "EVENT_NOTE_OUTLINED"),
}
DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _quando(iso: str | None) -> datetime:
    """Data e hora do servidor (ISO) como datetime com fuso; vazio = bem antigo."""
    if not iso:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def validar_plano(plano: dict) -> dict:
    """Confere e arruma um plano de estudo: horas por disciplina na semana e dias de estudo."""
    discs = []
    for d in plano.get("disciplinas") or []:
        nome = re.sub(r"\s+", " ", str(d.get("nome") or "")).strip()[:40]
        bruto = str(d.get("horas") if d.get("horas") is not None else "").replace(",", ".").strip()
        if not nome and not bruto:
            continue
        try:
            horas = round(float(bruto or 0), 1)
        except ValueError:
            raise ErroRanking(f"Horas inválidas em {nome or 'uma disciplina'}.") from None
        if not nome or horas <= 0:
            continue
        if horas > 40:
            raise ErroRanking("No máximo 40 horas por disciplina na semana.")
        if any(x["nome"].lower() == nome.lower() for x in discs):
            raise ErroRanking(f"{nome} aparece duas vezes no plano.")
        discs.append({"nome": nome, "horas": horas})
    if not discs:
        raise ErroRanking("Coloque pelo menos uma disciplina com as horas da semana.")
    if len(discs) > 15:
        raise ErroRanking("Use no máximo 15 disciplinas no plano.")
    dias = sorted({int(x) for x in plano.get("dias") or [] if str(x).lstrip("-").isdigit() and 0 <= int(x) <= 6})
    if not dias:
        raise ErroRanking("Escolha os dias da semana do plano.")
    meta = round(sum(d["horas"] for d in discs), 1)
    if meta > 80:
        raise ErroRanking("O plano passa de 80 horas por semana. Diminua as horas.")
    try:
        semanas = max(0, min(52, int(plano.get("semanas") or 0)))
    except (TypeError, ValueError):
        semanas = 0
    return {"meta_horas": meta, "dias": dias, "disciplinas": discs, "semanas": semanas, "concurso": str(plano.get("concurso") or "").strip()[:60]}


def analise_norm(texto: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def sugerir_apelido() -> str:
    return f"Estudante {secrets.randbelow(9000) + 1000}"


def validar_apelido(apelido: str) -> str:
    apelido = re.sub(r"\s+", " ", (apelido or "").strip())
    if not 3 <= len(apelido) <= 24:
        raise ErroRanking("O apelido deve ter de 3 a 24 caracteres.")
    if not re.fullmatch(r"[\wÀ-ÿ .\-]+", apelido):
        raise ErroRanking("Use só letras, números, espaço, ponto ou hífen no apelido.")
    return apelido
