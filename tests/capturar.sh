#!/usr/bin/env bash
# Abre o app numa tela virtual e salva uma captura.
# Uso: tests/capturar.sh saida.png LARGURAxALTURA SEGUNDOS [VAR=valor ...]
set -u
SAIDA="$1"; JANELA="$2"; ESPERA="$3"; shift 3
AQUI="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${SAIDA%.png}.log"
env APROVA_JANELA="$JANELA" APROVA_FIXTURES="${APROVA_FIXTURES:-$AQUI/tests/fixtures}" APROVA_RANKING_ARQUIVO="${APROVA_RANKING_ARQUIVO:-/tmp/aprova-sem-servidor.json}" "$@" \
  xvfb-run -a -s "-screen 0 ${JANELA}x24" bash -c "${PYTHON:-python} '$AQUI/main.py' > '$LOG' 2>&1 & PID=\$!; sleep $ESPERA; import -window root '$SAIDA'; kill \$PID; true"
grep -v -E "libEGL|DRI3|Atk-CRITICAL|^$" "$LOG" | tail -15
