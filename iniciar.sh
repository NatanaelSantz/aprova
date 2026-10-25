#!/usr/bin/env bash
# macOS / Linux: prepara o ambiente na primeira vez e abre o Aprova.
# Uso: ./iniciar.sh        (app no computador)
#      ./iniciar.sh --web  (navegador + celular na mesma rede)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Preparando o Aprova pela primeira vez..."
  python3 -m venv .venv || { echo "Instale o Python 3.11 ou mais novo."; exit 1; }
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python main.py "$@"
