"""Cria um histórico de estudo de exemplo (para as capturas de tela do Painel).

Uso: APROVA_DATA=pasta python tests/semear_demo.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aprova import amostras, config  # noqa: E402
from aprova.db import Banco  # noqa: E402


def main():
    random.seed(7)
    config.garantir_pastas()
    banco = Banco(config.DB_PATH)
    amostras.instalar(banco)
    demo = next(p for p in banco.provas() if p["origem_url"] == "aprova://demo")
    qs = banco.questoes(demo["id"])
    acerto = {"Língua Portuguesa": 0.82, "Raciocínio Lógico": 0.41, "Informática": 0.66, "Direito Administrativo": 0.55,
              "Direito Constitucional": 0.74, "Matemática": 0.38}
    hoje = date.today()
    for dias_atras in range(55, -1, -1):
        d = hoje - timedelta(days=dias_atras)
        if d.weekday() == 6 or random.random() < 0.18:
            continue
        minutos = random.choice([35, 50, 70, 95, 120, 150])
        if dias_atras == 0:
            minutos = 75
        banco.somar_tempo(minutos * 60 * 2 // 3, "app", random.choice(list(acerto)), d.isoformat())
        banco.somar_tempo(minutos * 60 // 3, "cronometro", "Leitura de lei seca", d.isoformat())
        if random.random() < 0.6 or dias_atras == 0:
            t = banco.iniciar_tentativa(demo["id"], "estudo")
            banco._con.execute("UPDATE tentativas SET inicio=? WHERE id=?", (datetime.combine(d, datetime.min.time()).replace(hour=19).isoformat(), t))
            acertos = 0
            for q in random.sample(qs, 8):
                melhora = 0.12 * (1 - dias_atras / 56)
                certo = random.random() < min(0.95, acerto.get(q["disciplina"], 0.6) + melhora)
                acertos += certo
                banco.registrar_resposta(t, q["numero"], q["disciplina"], q["gabarito"] if certo else "E", certo)
                banco._con.execute(
                    "UPDATE respostas SET respondida_em=? WHERE tentativa_id=? AND numero=?",
                    (datetime.combine(d, datetime.min.time()).replace(hour=19, minute=30).isoformat(), t, q["numero"]),
                )
                if not certo:
                    banco.revisao_registrar(demo["id"], q["numero"], q["disciplina"], False)
            banco._con.commit()
            banco.finalizar_tentativa(t, minutos * 40, acertos, 8)
    # algumas revisões vencidas hoje
    banco._con.execute("UPDATE revisao SET proxima=? WHERE rowid % 2 = 0", (hoje.isoformat(),))
    banco._con.commit()
    banco.salvar_lembrete({"titulo": "Revisão do dia", "hora": "20:00", "dias": "0,1,2,3,4", "alvo_tipo": "revisao", "alvo": ""})
    banco.salvar_lembrete({"titulo": "Treino de Raciocínio Lógico", "hora": "19:00", "dias": "1,3", "alvo_tipo": "treino", "alvo": "Raciocínio Lógico"})
    banco.salvar_lembrete({"titulo": "Ler a LGPD (artigos 5º a 22)", "hora": "07:30", "dias": "5", "alvo_tipo": "link",
                           "alvo": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"})
    q = qs[0]
    banco.salvar_duvida(demo["id"], q["numero"], q["disciplina"], q["enunciado"], "Por que a vírgula antes do 'e' está errada?",
                        "Porque as orações coordenadas ligadas por **e** com o mesmo sujeito não levam vírgula. "
                        "A vírgula antes do *e* só aparece quando os sujeitos são diferentes ou para dar ênfase.",
                        [{"titulo": "Uso da vírgula antes do e — exemplo", "url": "https://exemplo.com/virgula"}], "busca")
    print("ok", config.DATA_DIR)


if __name__ == "__main__":
    main()
