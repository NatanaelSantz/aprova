"""Banco local (SQLite): provas importadas, questões, tentativas e favoritos."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config

def _limpo(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def assinatura(q: dict) -> str:
    """Identifica a mesma questão em provas diferentes (cargos com a mesma parte comum)."""
    alts = q.get("alternativas") or {}
    if isinstance(alts, str):
        alts = json.loads(alts or "{}")
    base = _limpo(q.get("enunciado", ""))[:500] + "|" + "|".join(sorted(_limpo(v)[:150] for v in alts.values()))
    return hashlib.sha1(base.encode()).hexdigest()


ESQUEMA = """
CREATE TABLE IF NOT EXISTS provas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    cargo TEXT DEFAULT '',
    orgao TEXT DEFAULT '',
    banca TEXT DEFAULT '',
    ano TEXT DEFAULT '',
    origem_url TEXT DEFAULT '',
    pdf_prova TEXT DEFAULT '',
    pdf_gabarito TEXT DEFAULT '',
    paginas INTEGER DEFAULT 0,
    modo TEXT DEFAULT 'questoes',      -- questoes | cartao
    n_questoes INTEGER DEFAULT 0,
    criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prova_id INTEGER NOT NULL REFERENCES provas(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    enunciado TEXT DEFAULT '',
    alternativas TEXT DEFAULT '{}',
    tipo TEXT DEFAULT 'ME',
    disciplina TEXT DEFAULT 'Geral',
    pagina INTEGER DEFAULT 0,
    texto_base TEXT DEFAULT '',
    gabarito TEXT,
    explicacao TEXT DEFAULT '',
    UNIQUE(prova_id, numero)
);
CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prova_id INTEGER NOT NULL REFERENCES provas(id) ON DELETE CASCADE,
    modo TEXT NOT NULL,                -- simulado | estudo
    inicio TEXT NOT NULL,
    fim TEXT,
    duracao_s INTEGER DEFAULT 0,
    acertos INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS respostas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tentativa_id INTEGER NOT NULL REFERENCES tentativas(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    disciplina TEXT DEFAULT 'Geral',
    resposta TEXT,
    correta INTEGER,
    respondida_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favoritos (
    url TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    dados TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS avisos (
    chave TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    termo TEXT NOT NULL,
    qtd INTEGER DEFAULT 0,
    criado_em TEXT NOT NULL,
    visto INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ajuda_cache (
    chave TEXT PRIMARY KEY,
    dados TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tempo_estudo (
    dia TEXT NOT NULL,                 -- AAAA-MM-DD
    origem TEXT NOT NULL,              -- app | cronometro | manual
    disciplina TEXT NOT NULL DEFAULT '',
    segundos INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dia, origem, disciplina)
);
CREATE TABLE IF NOT EXISTS revisao (
    prova_id INTEGER NOT NULL,
    numero INTEGER NOT NULL,
    disciplina TEXT DEFAULT 'Geral',
    caixa INTEGER NOT NULL DEFAULT 1,  -- 1 a 5; 6 = dominada
    proxima TEXT,                      -- AAAA-MM-DD
    acertos INTEGER DEFAULT 0,
    erros INTEGER DEFAULT 0,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL,
    PRIMARY KEY (prova_id, numero)
);
CREATE TABLE IF NOT EXISTS duvidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prova_id INTEGER,
    numero INTEGER,
    disciplina TEXT DEFAULT '',
    resumo TEXT DEFAULT '',            -- começo do enunciado
    pergunta TEXT NOT NULL,
    resposta TEXT NOT NULL,
    fontes TEXT DEFAULT '[]',
    via TEXT DEFAULT 'busca',
    criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lembretes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    hora TEXT NOT NULL,                -- HH:MM
    dias TEXT DEFAULT '',              -- dias da semana: 0=seg ... 6=dom, separados por vírgula
    data TEXT DEFAULT '',              -- AAAA-MM-DD para lembrete de uma vez só
    alvo_tipo TEXT DEFAULT '',         -- link | busca | video | revisao | prova | simulado
    alvo TEXT DEFAULT '',
    ativo INTEGER DEFAULT 1,
    ultimo TEXT DEFAULT '',            -- AAAA-MM-DD HH:MM do último disparo
    criado_em TEXT NOT NULL
);
"""

INTERVALOS_REVISAO = {1: 1, 2: 3, 3: 7, 4: 15, 5: 30}  # dias até a próxima revisão em cada caixa
ORIGENS_INTERNAS = ("aprova://simulado", "aprova://revisao", "aprova://ia")


class Banco:
    def __init__(self, caminho: Path = config.DB_PATH):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(caminho, check_same_thread=False, timeout=15)
        self._con.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.execute("PRAGMA foreign_keys=ON")
            self.migrar()

    def migrar(self) -> None:
        """Tabelas e colunas que faltam (banco de versão antiga ou cópia de segurança restaurada)."""
        with self._lock:
            self._con.executescript(ESQUEMA)
            colunas = {r[1] for r in self._con.execute("PRAGMA table_info(questoes)")}
            if "fonte" not in colunas:
                self._con.execute("ALTER TABLE questoes ADD COLUMN fonte TEXT DEFAULT ''")
            if "ref" not in colunas:  # "prova_id:numero" da questão original (simulados e revisão)
                self._con.execute("ALTER TABLE questoes ADD COLUMN ref TEXT DEFAULT ''")
            if "ref" not in {r[1] for r in self._con.execute("PRAGMA table_info(respostas)")}:
                # 1.12: a resposta lembra a questão original (no simulado e na revisão o número muda)
                self._con.execute("ALTER TABLE respostas ADD COLUMN ref TEXT DEFAULT ''")
            self._con.commit()

    @contextmanager
    def _tx(self):
        with self._lock:
            try:
                yield self._con
                self._con.commit()
            except Exception:
                self._con.rollback()
                raise

    def _q(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self._con.execute(sql, params).fetchall()

    # ---- provas

    def criar_prova(self, **campos) -> int:
        campos.setdefault("criada_em", datetime.now().isoformat(timespec="seconds"))
        cols = ", ".join(campos)
        marks = ", ".join("?" for _ in campos)
        with self._tx() as c:
            cur = c.execute(f"INSERT INTO provas ({cols}) VALUES ({marks})", tuple(campos.values()))
            return int(cur.lastrowid)

    def atualizar_prova(self, prova_id: int, **campos) -> None:
        if not campos:
            return
        sets = ", ".join(f"{k}=?" for k in campos)
        with self._tx() as c:
            c.execute(f"UPDATE provas SET {sets} WHERE id=?", (*campos.values(), prova_id))

    def provas(self) -> list[dict]:
        linhas = self._q(
            """SELECT p.*, (SELECT COUNT(*) FROM questoes q WHERE q.prova_id=p.id AND q.gabarito IS NOT NULL) AS n_gabarito,
                      (SELECT MAX(t.acertos*1.0/NULLIF(t.total,0)) FROM tentativas t WHERE t.prova_id=p.id AND t.fim IS NOT NULL) AS melhor,
                      (SELECT COUNT(*) FROM tentativas t WHERE t.prova_id=p.id AND t.fim IS NOT NULL) AS feitas
               FROM provas p ORDER BY p.id DESC"""
        )
        return [dict(r) for r in linhas]

    def prova(self, prova_id: int) -> dict | None:
        r = self._q("SELECT * FROM provas WHERE id=?", (prova_id,))
        return dict(r[0]) if r else None

    def apagar_prova(self, prova_id: int) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM provas WHERE id=?", (prova_id,))

    def prova_por_origem(self, url: str) -> dict | None:
        r = self._q("SELECT * FROM provas WHERE origem_url=? AND origem_url<>'' ORDER BY id DESC LIMIT 1", (url,))
        return dict(r[0]) if r else None

    # ---- questões

    def salvar_questoes(self, prova_id: int, questoes: list[dict]) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM questoes WHERE prova_id=?", (prova_id,))
            c.executemany(
                """INSERT INTO questoes (prova_id, numero, enunciado, alternativas, tipo, disciplina, pagina, texto_base, gabarito, explicacao, fonte, ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        prova_id,
                        q["numero"],
                        q.get("enunciado", ""),
                        json.dumps(q.get("alternativas") or {}, ensure_ascii=False),
                        q.get("tipo", "ME"),
                        q.get("disciplina") or "Geral",
                        q.get("pagina", 0),
                        q.get("texto_base", ""),
                        q.get("gabarito"),
                        q.get("explicacao", ""),
                        q.get("fonte", ""),
                        q.get("ref", ""),
                    )
                    for q in questoes
                ],
            )
            c.execute("UPDATE provas SET n_questoes=? WHERE id=?", (len(questoes), prova_id))

    def questoes(self, prova_id: int) -> list[dict]:
        saida = []
        for r in self._q("SELECT * FROM questoes WHERE prova_id=? ORDER BY numero", (prova_id,)):
            d = dict(r)
            d["alternativas"] = json.loads(d["alternativas"] or "{}")
            saida.append(d)
        return saida

    def definir_gabarito(self, prova_id: int, gabarito: dict[int, str]) -> int:
        """Grava respostas oficiais. Cria questões vazias (modo cartão) se faltarem."""
        existentes = {r["numero"] for r in self._q("SELECT numero FROM questoes WHERE prova_id=?", (prova_id,))}
        letras = {v for v in gabarito.values() if v != "*"}
        certo_errado = len(gabarito) >= 8 and letras <= {"C", "E"}
        tipo_novo = "CE" if certo_errado else "ME"
        with self._tx() as c:
            for n, resp in gabarito.items():
                if n in existentes:
                    c.execute("UPDATE questoes SET gabarito=? WHERE prova_id=? AND numero=?", (resp, prova_id, n))
                else:
                    c.execute(
                        "INSERT INTO questoes (prova_id, numero, gabarito, alternativas, tipo) VALUES (?,?,?,?,?)",
                        (prova_id, n, resp, "{}", tipo_novo),
                    )
            if certo_errado:
                c.execute("UPDATE questoes SET tipo='CE' WHERE prova_id=? AND enunciado=''", (prova_id,))
            total = c.execute("SELECT COUNT(*) FROM questoes WHERE prova_id=?", (prova_id,)).fetchone()[0]
            c.execute("UPDATE provas SET n_questoes=? WHERE id=?", (total, prova_id))
        return len(gabarito)

    def garantir_questoes(self, prova_id: int, total: int) -> None:
        """Cria questões vazias 1..total (provas feitas pelo cartão-resposta)."""
        with self._tx() as c:
            for n in range(1, total + 1):
                c.execute(
                    "INSERT OR IGNORE INTO questoes (prova_id, numero, alternativas, tipo) VALUES (?,?,?,?)",
                    (prova_id, n, "{}", "ME"),
                )
            c.execute("DELETE FROM questoes WHERE prova_id=? AND numero>? AND enunciado=''", (prova_id, total))
            n_total = c.execute("SELECT COUNT(*) FROM questoes WHERE prova_id=?", (prova_id,)).fetchone()[0]
            c.execute("UPDATE provas SET n_questoes=? WHERE id=?", (n_total, prova_id))

    def salvar_explicacao(self, questao_id: int, texto: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE questoes SET explicacao=? WHERE id=?", (texto, questao_id))

    def banco_de_questoes(self, unicas: bool = True) -> list[dict]:
        """Todas as questões com texto (exceto simulados montados), com os dados da prova de origem.

        Com `unicas`, a mesma questão repetida em várias provas (ex.: Português igual
        para todos os cargos) aparece uma vez só, de preferência a que tem gabarito.
        """
        saida: list[dict] = []
        pos: dict[str, int] = {}
        for r in self._q(
            """SELECT q.*, p.titulo AS prova_titulo, p.orgao, p.banca, p.cargo, p.ano, p.origem_url
               FROM questoes q JOIN provas p ON p.id = q.prova_id
               WHERE q.enunciado <> '' AND p.origem_url NOT LIKE 'aprova://simulado%' AND p.origem_url NOT LIKE 'aprova://revisao%'
               ORDER BY p.id DESC, q.numero"""
        ):
            d = dict(r)
            d["alternativas"] = json.loads(d["alternativas"] or "{}")
            sig = d["assinatura"] = assinatura(d)
            if unicas:
                if sig in pos:
                    i = pos[sig]
                    if not saida[i].get("gabarito") and d.get("gabarito"):
                        saida[i] = d
                    continue
                pos[sig] = len(saida)
            saida.append(d)
        return saida

    def disciplinas(self) -> list[str]:
        """Disciplinas das questões da biblioteca (sem simulados montados), em ordem alfabética.

        Bem mais leve que montar o banco de questões inteiro só para saber os nomes."""
        return sorted(
            r[0] for r in self._q(
                """SELECT DISTINCT q.disciplina FROM questoes q JOIN provas p ON p.id = q.prova_id
                   WHERE q.enunciado <> '' AND q.disciplina IS NOT NULL
                     AND p.origem_url NOT LIKE 'aprova://simulado%' AND p.origem_url NOT LIKE 'aprova://revisao%'"""
            )
        )

    def resumo_biblioteca(self, filtro: str = "") -> dict:
        """Quantas provas e questões (sem repetidas) existem para um concurso."""
        from .montador import combina

        qs = [q for q in self.banco_de_questoes() if combina(q, filtro)]
        provas = [
            p for p in self.provas()
            if not str(p["origem_url"]).startswith("aprova://simulado") and combina({**p, "prova_titulo": p["titulo"]}, filtro)
        ]
        return {
            "provas": len(provas),
            "questoes": len(qs),
            "com_gabarito": sum(1 for q in qs if q.get("gabarito")),
        }

    def acertadas(self) -> set[tuple[int, int]]:
        """(prova_id, numero) das questões originais que você já acertou alguma vez (em qualquer lugar)."""
        return {k for k, h in self.historico_questoes().items() if h["acertou"]}

    def historico_questoes(self) -> dict[tuple[int, int], dict]:
        """O que você já fez com cada questão original: {(prova_id, numero): {"vista", "acertou", "vezes"}}.

        Respostas dadas num simulado, num treino ou na revisão contam para a questão de onde ela veio.
        As antigas (antes da 1.12) sem a referência só valem quando dá para saber a origem com certeza:
        treino e revisão reaproveitam a mesma prova com outras questões, então ficam de fora."""
        linhas = self._q(
            """SELECT t.prova_id, r.numero, r.correta, r.respondida_em, r.ref, q.ref AS ref_q, p.origem_url
               FROM respostas r
               JOIN tentativas t ON t.id = r.tentativa_id
               JOIN provas p ON p.id = t.prova_id
               LEFT JOIN questoes q ON q.prova_id = t.prova_id AND q.numero = r.numero"""
        )
        saida: dict[tuple[int, int], dict] = {}
        reaproveitadas = ("aprova://revisao", "aprova://simulado/treino")
        for r in linhas:
            ref = r["ref"] or ""
            if not ref:
                if (r["origem_url"] or "").startswith(reaproveitadas):
                    continue
                ref = r["ref_q"] or ""
            chave = self._original(r["prova_id"], r["numero"], ref)
            h = saida.setdefault(chave, {"vista": "", "acertou": False, "vezes": 0})
            h["vezes"] += 1
            h["vista"] = max(h["vista"], r["respondida_em"] or "")
            if r["correta"] == 1:
                h["acertou"] = True
        return saida

    def em_revisao(self) -> set[tuple[int, int]]:
        """Questões que você errou e que ainda estão esperando o dia de revisar."""
        return {(r["prova_id"], r["numero"]) for r in self._q("SELECT prova_id, numero FROM revisao WHERE caixa < 6")}

    def distribuicao_da_prova(self, prova_id: int) -> list[tuple[str, int]]:
        linhas = self._q(
            "SELECT disciplina, COUNT(*) n, MIN(numero) primeira FROM questoes WHERE prova_id=? GROUP BY disciplina ORDER BY primeira",
            (prova_id,),
        )
        return [(r["disciplina"] or "Geral", r["n"]) for r in linhas]

    # ---- tentativas

    def iniciar_tentativa(self, prova_id: int, modo: str) -> int:
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO tentativas (prova_id, modo, inicio) VALUES (?,?,?)",
                (prova_id, modo, datetime.now().isoformat(timespec="seconds")),
            )
            return int(cur.lastrowid)

    def registrar_resposta(self, tentativa_id: int, numero: int, disciplina: str, resposta: str | None, correta: bool | None, ref: str = "") -> None:
        """ref: "prova_id:numero" da questão original (quando a questão veio de outra prova)."""
        with self._tx() as c:
            c.execute("DELETE FROM respostas WHERE tentativa_id=? AND numero=?", (tentativa_id, numero))
            c.execute(
                "INSERT INTO respostas (tentativa_id, numero, disciplina, resposta, correta, respondida_em, ref) VALUES (?,?,?,?,?,?,?)",
                (
                    tentativa_id,
                    numero,
                    disciplina or "Geral",
                    resposta,
                    None if correta is None else int(correta),
                    datetime.now().isoformat(timespec="seconds"),
                    ref if re.fullmatch(r"\d+:\d+", ref or "") else "",
                ),
            )

    def finalizar_tentativa(self, tentativa_id: int, duracao_s: int, acertos: int, total: int) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE tentativas SET fim=?, duracao_s=?, acertos=?, total=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), duracao_s, acertos, total, tentativa_id),
            )

    def tentativas(self, prova_id: int | None = None, limite: int = 20) -> list[dict]:
        sql = """SELECT t.*, p.titulo FROM tentativas t JOIN provas p ON p.id=t.prova_id
                 WHERE t.fim IS NOT NULL {} ORDER BY t.id DESC LIMIT ?"""
        if prova_id:
            return [dict(r) for r in self._q(sql.format("AND t.prova_id=?"), (prova_id, limite))]
        return [dict(r) for r in self._q(sql.format(""), (limite,))]

    def tentativa_aberta(self, prova_id: int) -> dict | None:
        r = self._q("SELECT * FROM tentativas WHERE prova_id=? AND fim IS NULL ORDER BY id DESC LIMIT 1", (prova_id,))
        return dict(r[0]) if r else None

    def respostas_da_tentativa(self, tentativa_id: int) -> dict[int, str]:
        return {r["numero"]: r["resposta"] for r in self._q("SELECT numero, resposta FROM respostas WHERE tentativa_id=?", (tentativa_id,))}

    # ---- estatísticas

    def estatisticas(self) -> dict:
        r = self._q("SELECT COUNT(*) n, SUM(correta) a FROM respostas WHERE correta IS NOT NULL")[0]
        respondidas, acertos = r["n"] or 0, r["a"] or 0
        feitas = self._q("SELECT COUNT(*) n FROM tentativas WHERE fim IS NOT NULL")[0]["n"]
        dias = {row["d"] for row in self._q("SELECT DISTINCT substr(respondida_em,1,10) d FROM respostas")}
        sequencia = 0
        dia = date.today()
        if dia.isoformat() not in dias:
            dia -= timedelta(days=1)
        while dia.isoformat() in dias:
            sequencia += 1
            dia -= timedelta(days=1)
        return {
            "respondidas": respondidas,
            "acertos": acertos,
            "taxa": (acertos / respondidas) if respondidas else None,
            "provas_feitas": feitas,
            "sequencia": sequencia,
            "provas": self._q(
                "SELECT COUNT(*) n FROM provas WHERE origem_url NOT LIKE 'aprova://revisao%' AND origem_url NOT LIKE 'aprova://simulado/treino%'"
            )[0]["n"],
        }

    def prioridades(self, limite: int = 6, provas: set[int] | None = None) -> list[dict]:
        """Onde focar: peso da disciplina nas provas x quanto você ainda erra.

        Com `provas` (as do seu concurso), o peso vem só delas."""
        so = f" AND p.id IN ({','.join(str(int(i)) for i in provas)})" if provas else ""
        freq = {
            r["disciplina"]: r["n"]
            for r in self._q(
                f"""SELECT q.disciplina, COUNT(*) n FROM questoes q JOIN provas p ON p.id=q.prova_id
                   WHERE q.disciplina IS NOT NULL AND q.disciplina<>''
                     AND (p.origem_url NOT LIKE 'aprova://%' OR p.origem_url = 'aprova://demo'){so}
                   GROUP BY q.disciplina"""
            )
        }
        total = sum(freq.values())
        if not total:
            return []
        desempenho = {
            r["disciplina"]: (r["a"] or 0, r["n"])
            for r in self._q("SELECT disciplina, SUM(correta) a, COUNT(*) n FROM respostas WHERE correta IS NOT NULL GROUP BY disciplina")
        }
        itens = []
        for disc, n in freq.items():
            peso = n / total
            a, feitas = desempenho.get(disc, (0, 0))
            taxa = a / feitas if feitas else None
            erro = 1 - taxa if taxa is not None else 0.5
            itens.append({
                "disciplina": disc,
                "peso": peso,
                "questoes": n,
                "taxa": taxa,
                "respondidas": feitas,
                "prioridade": peso * (0.35 + erro),
            })
        itens.sort(key=lambda x: x["prioridade"], reverse=True)
        return itens[:limite]

    # ---- tempo de estudo

    def somar_tempo(self, segundos: int, origem: str = "app", disciplina: str = "", dia: str | None = None) -> None:
        if segundos <= 0:
            return
        dia = dia or date.today().isoformat()
        with self._tx() as c:
            c.execute(
                """INSERT INTO tempo_estudo (dia, origem, disciplina, segundos) VALUES (?,?,?,?)
                   ON CONFLICT(dia, origem, disciplina) DO UPDATE SET segundos = segundos + excluded.segundos""",
                (dia, origem, disciplina or "", int(segundos)),
            )

    def tempo_por_dia(self, desde: date) -> dict[str, int]:
        return {
            r["dia"]: r["s"]
            for r in self._q("SELECT dia, SUM(segundos) s FROM tempo_estudo WHERE dia >= ? GROUP BY dia", (desde.isoformat(),))
        }

    def tempo_por_disciplina(self, desde: date) -> list[tuple[str, int]]:
        return [
            (r["disciplina"] or "Outros estudos", r["s"])
            for r in self._q(
                "SELECT disciplina, SUM(segundos) s FROM tempo_estudo WHERE dia >= ? GROUP BY disciplina ORDER BY s DESC",
                (desde.isoformat(),),
            )
        ]

    def dias_com_questoes(self, desde: date) -> dict[str, int]:
        return {
            r["d"]: r["n"]
            for r in self._q(
                "SELECT substr(respondida_em,1,10) d, COUNT(*) n FROM respostas WHERE respondida_em >= ? GROUP BY d",
                (desde.isoformat(),),
            )
        }

    # ---- desempenho (painel analítico)

    def desempenho_por(self, campo: str = "disciplina", desde: date | None = None) -> list[dict]:
        """Acertos agrupados por disciplina, banca ou concurso (órgão)."""
        coluna = {"disciplina": "r.disciplina", "banca": "p.banca", "orgao": "p.orgao"}[campo]
        filtro = "AND r.respondida_em >= ?" if desde else ""
        args = (desde.isoformat(),) if desde else ()
        linhas = self._q(
            f"""SELECT COALESCE(NULLIF({coluna}, ''), '') chave, COUNT(*) n, SUM(r.correta) a
                FROM respostas r JOIN tentativas t ON t.id = r.tentativa_id JOIN provas p ON p.id = t.prova_id
                WHERE r.correta IS NOT NULL {filtro}
                GROUP BY chave ORDER BY n DESC""",
            args,
        )
        return [{"chave": r["chave"], "respondidas": r["n"], "acertos": r["a"] or 0, "taxa": (r["a"] or 0) / r["n"]} for r in linhas if r["n"]]

    def respostas_corrigidas(self, desde: date) -> list[dict]:
        return [
            dict(r)
            for r in self._q(
                "SELECT substr(respondida_em,1,10) dia, disciplina, correta FROM respostas WHERE correta IS NOT NULL AND respondida_em >= ?",
                (desde.isoformat(),),
            )
        ]

    # ---- revisão espaçada (caixas de Leitner)

    def _original(self, prova_id: int, numero: int, ref: str = "") -> tuple[int, int]:
        if ref and ":" in ref:
            a, b = ref.split(":", 1)
            if a.isdigit() and b.isdigit():
                return int(a), int(b)
        return prova_id, numero

    def revisao_registrar(self, prova_id: int, numero: int, disciplina: str, correta: bool | None, ref: str = "") -> None:
        """Erro: a questão entra (ou volta) para a caixa 1. Acerto: sobe de caixa e espaça a próxima revisão."""
        if correta is None:
            return
        pid, num = self._original(prova_id, numero, ref)
        hoje = date.today()
        agora = datetime.now().isoformat(timespec="seconds")
        atual = self._q("SELECT caixa FROM revisao WHERE prova_id=? AND numero=?", (pid, num))
        with self._tx() as c:
            if not correta:
                c.execute(
                    """INSERT INTO revisao (prova_id, numero, disciplina, caixa, proxima, erros, criada_em, atualizada_em)
                       VALUES (?,?,?,1,?,1,?,?)
                       ON CONFLICT(prova_id, numero) DO UPDATE SET caixa=1, proxima=excluded.proxima,
                           erros=erros+1, atualizada_em=excluded.atualizada_em""",
                    (pid, num, disciplina or "Geral", (hoje + timedelta(days=1)).isoformat(), agora, agora),
                )
            elif atual:
                caixa = min(int(atual[0]["caixa"]) + 1, 6)
                proxima = None if caixa >= 6 else (hoje + timedelta(days=INTERVALOS_REVISAO[caixa])).isoformat()
                c.execute(
                    "UPDATE revisao SET caixa=?, proxima=?, acertos=acertos+1, atualizada_em=? WHERE prova_id=? AND numero=?",
                    (caixa, proxima, agora, pid, num),
                )

    def revisao_adicionar(self, prova_id: int, numero: int, disciplina: str, ref: str = "") -> None:
        """Marcou para revisar: entra na revisão de hoje."""
        pid, num = self._original(prova_id, numero, ref)
        agora = datetime.now().isoformat(timespec="seconds")
        with self._tx() as c:
            c.execute(
                """INSERT INTO revisao (prova_id, numero, disciplina, caixa, proxima, criada_em, atualizada_em)
                   VALUES (?,?,?,1,?,?,?)
                   ON CONFLICT(prova_id, numero) DO UPDATE SET proxima=MIN(COALESCE(proxima, excluded.proxima), excluded.proxima),
                       caixa=MIN(caixa, 5), atualizada_em=excluded.atualizada_em""",
                (pid, num, disciplina or "Geral", date.today().isoformat(), agora, agora),
            )

    def revisao_resumo(self) -> dict:
        hoje = date.today().isoformat()
        linhas = self._q(
            """SELECT r.disciplina, r.caixa, r.proxima FROM revisao r
               JOIN questoes q ON q.prova_id=r.prova_id AND q.numero=r.numero
               WHERE q.enunciado <> ''"""
        )
        por_disc: dict[str, dict] = {}
        caixas = {i: 0 for i in range(1, 7)}
        pendentes = amanha = 0
        amanha_iso = (date.today() + timedelta(days=1)).isoformat()
        for r in linhas:
            caixas[int(r["caixa"])] += 1
            d = por_disc.setdefault(r["disciplina"] or "Geral", {"pendentes": 0, "total": 0})
            if r["caixa"] < 6:
                d["total"] += 1
            if r["proxima"] and r["proxima"] <= hoje:
                pendentes += 1
                d["pendentes"] += 1
            elif r["proxima"] == amanha_iso:
                amanha += 1
        ativas = sum(v for k, v in caixas.items() if k < 6)
        return {"pendentes": pendentes, "amanha": amanha, "ativas": ativas, "dominadas": caixas[6], "caixas": caixas, "por_disciplina": por_disc}

    def revisao_questoes(self, disciplina: str | None = None, todas: bool = False, limite: int = 30) -> list[dict]:
        """Questões para a sessão de revisão (as mais atrasadas e de caixa mais baixa primeiro)."""
        hoje = date.today().isoformat()
        cond = ["q.enunciado <> ''", "r.caixa < 6"]
        args: list = []
        if not todas:
            cond.append("r.proxima <= ?")
            args.append(hoje)
        if disciplina:
            cond.append("r.disciplina = ?")
            args.append(disciplina)
        linhas = self._q(
            f"""SELECT q.*, r.caixa, r.erros, p.titulo AS prova_titulo FROM revisao r
                JOIN questoes q ON q.prova_id=r.prova_id AND q.numero=r.numero
                JOIN provas p ON p.id=q.prova_id
                WHERE {' AND '.join(cond)}
                ORDER BY r.proxima, r.caixa, r.erros DESC LIMIT ?""",
            (*args, limite),
        )
        saida = []
        for r in linhas:
            d = dict(r)
            d["alternativas"] = json.loads(d["alternativas"] or "{}")
            saida.append(d)
        return saida

    def prova_interna(self, origem: str, titulo: str) -> int:
        """Prova fixa usada pelo app (ex.: a sessão de revisão), reaproveitada a cada vez."""
        r = self._q("SELECT id FROM provas WHERE origem_url=? LIMIT 1", (origem,))
        if r:
            self.atualizar_prova(r[0]["id"], titulo=titulo)
            return int(r[0]["id"])
        return self.criar_prova(titulo=titulo, origem_url=origem, modo="questoes")

    # ---- dúvidas

    def salvar_duvida(self, prova_id: int | None, numero: int | None, disciplina: str, resumo: str, pergunta: str, resposta: str, fontes: list, via: str) -> int:
        with self._tx() as c:
            cur = c.execute(
                """INSERT INTO duvidas (prova_id, numero, disciplina, resumo, pergunta, resposta, fontes, via, criada_em)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (prova_id, numero, disciplina, resumo[:220], pergunta, resposta, json.dumps(fontes, ensure_ascii=False), via, datetime.now().isoformat(timespec="seconds")),
            )
            return int(cur.lastrowid)

    def duvidas(self, prova_id: int | None = None, numero: int | None = None, limite: int = 200) -> list[dict]:
        if prova_id is not None:
            linhas = self._q("SELECT * FROM duvidas WHERE prova_id=? AND numero=? ORDER BY id", (prova_id, numero))
        else:
            linhas = self._q(
                """SELECT d.*, p.titulo AS prova_titulo FROM duvidas d LEFT JOIN provas p ON p.id=d.prova_id
                   ORDER BY d.id DESC LIMIT ?""",
                (limite,),
            )
        saida = []
        for r in linhas:
            d = dict(r)
            d["fontes"] = json.loads(d["fontes"] or "[]")
            saida.append(d)
        return saida

    def apagar_duvida(self, duvida_id: int) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM duvidas WHERE id=?", (duvida_id,))

    # ---- lembretes

    def salvar_lembrete(self, dados: dict, lembrete_id: int | None = None) -> int:
        campos = {k: dados.get(k, "") for k in ("titulo", "hora", "dias", "data", "alvo_tipo", "alvo")}
        campos["ativo"] = int(dados.get("ativo", 1))
        with self._tx() as c:
            if lembrete_id:
                sets = ", ".join(f"{k}=?" for k in campos)
                c.execute(f"UPDATE lembretes SET {sets}, ultimo='' WHERE id=?", (*campos.values(), lembrete_id))
                return lembrete_id
            campos["criado_em"] = datetime.now().isoformat(timespec="seconds")
            cols = ", ".join(campos)
            cur = c.execute(f"INSERT INTO lembretes ({cols}) VALUES ({', '.join('?' for _ in campos)})", tuple(campos.values()))
            return int(cur.lastrowid)

    def lembretes(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM lembretes ORDER BY hora, id")]

    def apagar_lembrete(self, lembrete_id: int) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM lembretes WHERE id=?", (lembrete_id,))

    def marcar_lembrete(self, lembrete_id: int, quando: str, desativar: bool = False) -> None:
        with self._tx() as c:
            c.execute("UPDATE lembretes SET ultimo=?, ativo=CASE WHEN ? THEN 0 ELSE ativo END WHERE id=?", (quando, int(desativar), lembrete_id))

    # ---- favoritos

    def favoritar(self, url: str, nome: str, dados: dict) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO favoritos (url, nome, dados, criado_em) VALUES (?,?,?,?)",
                (url, nome, json.dumps(dados, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
            )

    def desfavoritar(self, url: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM favoritos WHERE url=?", (url,))

    def favoritos(self) -> list[dict]:
        return [json.loads(r["dados"]) for r in self._q("SELECT dados FROM favoritos ORDER BY criado_em DESC")]

    def eh_favorito(self, url: str) -> bool:
        return bool(self._q("SELECT 1 FROM favoritos WHERE url=?", (url,)))

    # ---- avisos de provas novas

    def registrar_aviso(self, chave: str, nome: str, termo: str, qtd: int) -> bool:
        """Grava o aviso. Devolve True se é novidade (concurso novo ou mais provas que antes)."""
        r = self._q("SELECT qtd FROM avisos WHERE chave=?", (chave,))
        if r and r[0]["qtd"] >= qtd:
            return False
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO avisos (chave, nome, termo, qtd, criado_em, visto) VALUES (?,?,?,?,?,0)",
                (chave, nome, termo, qtd, datetime.now().isoformat(timespec="seconds")),
            )
        return True

    def avisos_novos(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM avisos WHERE visto=0 ORDER BY criado_em DESC")]

    def marcar_aviso_visto(self, chave: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE avisos SET visto=1 WHERE chave=?", (chave,))

    # ---- cache da ajuda

    def ajuda_salva(self, chave: str) -> dict | None:
        r = self._q("SELECT dados FROM ajuda_cache WHERE chave=?", (chave,))
        return json.loads(r[0]["dados"]) if r else None

    def salvar_ajuda(self, chave: str, dados: dict) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO ajuda_cache (chave, dados, criado_em) VALUES (?,?,?)",
                (chave, json.dumps(dados, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
            )
