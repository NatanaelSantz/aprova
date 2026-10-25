"""Contas do Aprova (aluno e administrador) e ranking entre estudantes, num projeto Supabase (grátis).

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
from datetime import date, timedelta
from pathlib import Path

import requests

from . import analise, config

ARQUIVO = Path(os.environ.get("APROVA_RANKING_ARQUIVO") or config.RAIZ / "ranking.json")
METRICAS = {
    "horas": ("segundos", "Horas"),
    "questoes": ("questoes", "Questões"),
    "acerto": ("taxa", "Acerto"),
    "sequencia": ("sequencia", "Sequência"),
}
MIN_QUESTOES_ACERTO = 30  # para entrar no ranking de acerto


class ErroRanking(Exception):
    pass


def carregar_config(caminho: Path | None = None) -> dict:
    caminho = caminho or ARQUIVO
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    url = str(dados.get("url") or "").strip().rstrip("/")
    chave = str(dados.get("chave") or "").strip()
    return {"url": url, "chave": chave} if url.startswith("http") and chave else {}


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
        return self._pedir("GET", f"/rest/v1/grupos?codigo=in.({lista})&select=codigo,nome&order=nome").json()

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


def analise_norm(texto: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def validar_apelido(apelido: str) -> str:
    apelido = re.sub(r"\s+", " ", (apelido or "").strip())
    if not 3 <= len(apelido) <= 24:
        raise ErroRanking("O apelido deve ter de 3 a 24 caracteres.")
    if not re.fullmatch(r"[\wÀ-ÿ .\-]+", apelido):
        raise ErroRanking("Use só letras, números, espaço, ponto ou hífen no apelido.")
    return apelido
