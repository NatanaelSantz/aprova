"""Prepara uma versão nova para quem já tem o Aprova instalado.

Uso (na pasta do Aprova):
    python ferramentas/nova_versao.py 1.9.1 "Primeira novidade" "Segunda novidade"

Muda o número em aprova/__init__.py e escreve docs/versao.json. Depois é só enviar para o GitHub
(git commit e git push na main). Em até 12 horas, quem tem o Aprova 1.9 ou mais novo vê o aviso
"Nova versão" no Início e atualiza com um toque.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ZIP = "https://github.com/NatanaelSantz/aprova/archive/refs/heads/main.zip"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not re.fullmatch(r"\d+\.\d+\.\d+", argv[1]):
        print(__doc__)
        return 1
    versao, notas = argv[1], [n.strip() for n in argv[2:] if n.strip()]
    init = RAIZ / "aprova" / "__init__.py"
    texto = init.read_text(encoding="utf-8")
    atual = re.search(r'__version__\s*=\s*"([^"]+)"', texto).group(1)
    if tuple(map(int, versao.split("."))) <= tuple(int(x) for x in re.findall(r"\d+", atual)[:3]):
        print(f"A versão nova ({versao}) precisa ser maior que a atual ({atual}).")
        return 1
    init.write_text(re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{versao}"', texto), encoding="utf-8")
    projeto = RAIZ / "pyproject.toml"  # versão do app do celular (flet build)
    if projeto.exists():
        conteudo = projeto.read_text(encoding="utf-8")
        projeto.write_text(re.sub(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{versao}"', conteudo, count=1), encoding="utf-8")
    dados = {
        "versao": versao,
        "data": datetime.date.today().strftime("%d/%m/%Y"),
        "notas": notas or ["Melhorias e correções."],
        "zip": ZIP,
    }
    (RAIZ / "docs" / "versao.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Pronto: {atual} -> {versao}. Agora envie para o GitHub:")
    print(f'  git commit -am "Versão {versao}" && git push')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
