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
# versão nova baixada pelo app: troca os arquivos antes de abrir (e reinstala bibliotecas se mudaram)
.venv/bin/python - <<'PY'
import hashlib, importlib.util, os, pathlib
raiz = pathlib.Path.cwd()
spec = importlib.util.spec_from_file_location("aprova_atualizar", raiz / "aprova" / "atualizar.py")
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)
versao = modulo.aplicar_pendente(raiz, pathlib.Path(os.environ.get("APROVA_DATA", pathlib.Path.home() / ".aprova")))
if versao:
    print(f"Aprova atualizado para a versão {versao}.")
PY
RESUMO="$(.venv/bin/python -c "import hashlib;print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())")"
if [ -f .venv/.requisitos ] && [ "$(cat .venv/.requisitos)" != "$RESUMO" ]; then
  echo "Instalando as bibliotecas novas..."
  .venv/bin/python -m pip install -r requirements.txt && echo "$RESUMO" > .venv/.requisitos
elif [ ! -f .venv/.requisitos ]; then
  echo "$RESUMO" > .venv/.requisitos
fi
exec .venv/bin/python main.py "$@"
