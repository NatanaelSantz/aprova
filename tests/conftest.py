"""Os testes nunca falam com o servidor de verdade: sem ranking.json, o app usaria o servidor padrão (aprova/servidor.json)."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("APROVA_RANKING_ARQUIVO", str(Path(tempfile.gettempdir()) / "aprova-testes-sem-servidor.json"))
