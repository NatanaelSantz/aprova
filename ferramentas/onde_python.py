"""Usado pelo 'Abrir Aprova.bat': mostra o caminho deste Python se ele servir (3.10 ou mais novo)."""
import sys

if sys.version_info >= (3, 10):
    print(sys.executable)
else:
    sys.exit(1)
