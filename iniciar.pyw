"""Abre o Aprova sem janela preta.

- Se tudo já está instalado, abre o app direto.
- Se falta alguma coisa (primeira vez ou versão nova), mostra uma janela de
  instalação com progresso, instala as bibliotecas e cria o atalho na área de trabalho.

O atalho "Aprova" da área de trabalho aponta para este arquivo (com pythonw, sem console).
"""

from __future__ import annotations

import os
import queue
import re
import runpy
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
WIN = sys.platform == "win32"
VENV = RAIZ / ".venv"
PY_VENV = VENV / ("Scripts/python.exe" if WIN else "bin/python")
PYW_VENV = VENV / ("Scripts/pythonw.exe" if WIN else "bin/python")
REQUISITOS = RAIZ / os.environ.get("APROVA_REQUISITOS", "requirements.txt")
MODULOS = [m for m in os.environ.get("APROVA_MODULOS", "flet,flet_desktop,pymupdf,bs4,requests,ddgs,anthropic,qrcode,PIL,truststore").split(",") if m]
SEM_JANELA = 0x08000000 if WIN else 0  # CREATE_NO_WINDOW
DADOS = Path(os.environ.get("APROVA_DATA", Path.home() / ".aprova"))
LOG = DADOS / "instalacao.log"
VERSAO_ATALHO = "2"  # atalho que abre com pythonw (sem console)
DEMO = os.environ.get("APROVA_INSTALADOR_DEMO") == "1"  # simula a instalação (capturas de tela)
SO_INSTALAR = os.environ.get("APROVA_INSTALADOR_SO_INSTALAR") == "1"  # testes: não abre o app no fim


def _rodar(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA, **kw)


PROCESSOS: list[subprocess.Popen] = []  # pip em andamento (para cancelar)


def _no_ambiente() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


MARCA_REQUISITOS = VENV / ".requisitos"  # resumo do requirements.txt da última instalação


def _resumo_requisitos() -> str:
    import hashlib

    try:
        return hashlib.sha256(REQUISITOS.read_bytes()).hexdigest()
    except OSError:
        return ""


def requisitos_mudaram() -> bool:
    """Uma atualização trouxe bibliotecas novas? (instalação antiga, sem resumo: confere só os módulos)"""
    try:
        return MARCA_REQUISITOS.read_text(encoding="utf-8").strip() != _resumo_requisitos()
    except OSError:
        return False


def marcar_requisitos() -> None:
    try:
        MARCA_REQUISITOS.write_text(_resumo_requisitos(), encoding="utf-8")
    except OSError:
        pass


def ambiente_ok() -> bool:
    if DEMO:
        return False
    if not PY_VENV.exists():
        return False
    if requisitos_mudaram():
        return False
    if _no_ambiente():
        import importlib.util

        ok = all(importlib.util.find_spec(m) is not None for m in MODULOS)
    else:
        try:
            ok = _rodar([str(PY_VENV), "-c", "import " + ", ".join(MODULOS)], timeout=60).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    if ok and not MARCA_REQUISITOS.exists():
        marcar_requisitos()
    return ok


def _modulo_atualizar():
    import importlib.util

    spec = importlib.util.spec_from_file_location("aprova_atualizar", RAIZ / "aprova" / "atualizar.py")
    if spec is None or spec.loader is None:
        return None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _confiar_certificados() -> str:
    """Faz o Python verificar o HTTPS pelo sistema (como o navegador). Ver aprova/certificados.py."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("aprova_certificados", RAIZ / "aprova" / "certificados.py")
        if spec is None or spec.loader is None:
            return ""
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo.confiar_no_sistema()
    except Exception:  # noqa: BLE001 - nunca impede de abrir
        _anotar("Falha ao preparar os certificados:\n" + traceback.format_exc())
        return ""


def _explicar_erro(detalhe: str) -> str:
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("aprova_certificados", RAIZ / "aprova" / "certificados.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo.explicar_erro(detalhe)
    except Exception:  # noqa: BLE001
        return ""


def aplicar_atualizacao() -> None:
    """Se uma versão nova foi baixada pelo app, copia os arquivos dela antes de abrir."""
    try:
        modulo = _modulo_atualizar()
        if modulo is None:
            return
        versao = modulo.aplicar_pendente(RAIZ, DADOS)
        if versao:
            _anotar(f"\n=== Atualizado para a versão {versao} em {time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception:  # noqa: BLE001
        _anotar("Falha ao aplicar a atualização:\n" + traceback.format_exc())


def voltar_se_preciso(erro: str = "") -> str | None:
    """A versão nova não abriu: devolve os arquivos da anterior. Devolve a versão para a qual voltou.

    Sem `erro`, conta mais uma abertura da versão nova e só volta depois de várias sem a janela aparecer
    (o app fechou sozinho). Com `erro` (deu erro ao abrir), volta na hora."""
    try:
        modulo = _modulo_atualizar()
        if modulo is None or not hasattr(modulo, "voltar"):
            return None
        if erro:
            if not modulo.em_teste(DADOS):
                return None
        elif not modulo.contar_abertura(DADOS):
            return None
        u = modulo.ultima(DADOS)
        de = modulo.voltar(RAIZ, DADOS)
        if de:
            motivo = ("erro ao abrir:\n" + erro.strip()) if erro else "a janela não apareceu nas últimas aberturas"
            _anotar(f"\n=== A versão {u.get('versao')} não abriu ({motivo}). Voltou para a {de} em {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return de
    except Exception:  # noqa: BLE001
        _anotar("Falha ao voltar para a versão anterior:\n" + traceback.format_exc())
        return None


def _versao_instalada() -> str:
    try:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (RAIZ / "aprova" / "__init__.py").read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except OSError:
        return ""


def _app_ja_aberto() -> bool:
    """O Aprova já está aberto (ex.: clicou num convite): não atrasa nada, o app aberto cuida da atualização."""
    try:
        return time.time() - (DADOS / "app.vivo").stat().st_mtime < 75
    except OSError:
        return False


def atualizar_ao_abrir(mostrar_tela: bool = True) -> str | None:
    """Toda vez que abre: se saiu versão nova, baixa e aplica antes de mostrar o app.

    A consulta é um arquivo de 1 KB (espera no máximo 4 s). Sem internet, ou se algo falhar,
    abre a versão que já está instalada, sem travar. Devolve a versão nova aplicada (ou None)."""
    if DEMO or SO_INSTALAR or os.environ.get("APROVA_SEM_ATUALIZAR_AO_ABRIR") or _app_ja_aberto():
        return None
    tela = None
    try:
        modulo = _modulo_atualizar()
        atual = _versao_instalada()
        if modulo is None or not atual:
            return None
        url = os.environ.get("APROVA_ATUALIZACAO_URL") or modulo.URL_VERSAO
        try:
            try:
                info = modulo.verificar(atual, url, timeout=4, pasta=DADOS)
            except TypeError:  # atualizar.py de antes da volta automática
                info = modulo.verificar(atual, url, timeout=4)
        except modulo.ErroAtualizacao:
            return None  # sem internet agora
        if not info:
            return None
        if mostrar_tela:
            tela = _tela_atualizando(info["versao"])
        versao = modulo.preparar(info, DADOS, atual)
        aplicada = modulo.aplicar_pendente(RAIZ, DADOS)
        if aplicada:
            _anotar(f"\n=== Atualizado ao abrir para a versão {aplicada} em {time.strftime('%Y-%m-%d %H:%M:%S')} (antes {atual})")
        return aplicada or versao
    except Exception:  # noqa: BLE001
        _anotar("Falha ao atualizar ao abrir (abrindo a versão instalada):\n" + traceback.format_exc())
        return None
    finally:
        if tela is not None:
            try:
                tela.terminate()
            except OSError:
                pass


def _tela_atualizando(versao: str):
    if os.environ.get("APROVA_SEM_ABERTURA"):
        return None
    try:
        return subprocess.Popen([sys.executable, str(RAIZ / "ferramentas" / "abertura.pyw"), f"Atualizando para a versão {versao}…"],
                                cwd=str(RAIZ), creationflags=SEM_JANELA)
    except OSError:
        return None


def _anotar(texto: str) -> None:
    try:
        DADOS.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(texto.rstrip("\n") + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- atalho


def criar_atalho() -> bool:
    """Atalho "Aprova" na área de trabalho que abre sem console."""
    if not WIN:
        return False
    alvo = PYW_VENV if PYW_VENV.exists() else PY_VENV
    icone = RAIZ / "assets" / "aprova.ico"

    def q(s) -> str:
        return str(s).replace("'", "''")

    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Aprova.lnk'));"
        f"$s.TargetPath='{q(alvo)}';"
        f"$s.Arguments='\"{q(RAIZ / 'iniciar.pyw')}\"';"
        f"$s.WorkingDirectory='{q(RAIZ)}';"
        f"$s.IconLocation='{q(icone)}';"
        "$s.Description='Aprova - estudo para concursos';"
        "$s.Save()"
    )
    try:
        r = _rodar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=60)
        ok = r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if ok:
        try:
            (VENV / ".atalho").write_text(VERSAO_ATALHO, encoding="utf-8")
        except OSError:
            pass
    return ok


def atalho_atualizado() -> bool:
    try:
        return (VENV / ".atalho").read_text(encoding="utf-8").strip() == VERSAO_ATALHO
    except OSError:
        return False


# --------------------------------------------------------------------------- abrir o app


def _saida_em_arquivo() -> None:
    """Com pythonw não há console: mensagens do app vão para um arquivo."""
    if sys.stdout is None or sys.stderr is None:
        try:
            DADOS.mkdir(parents=True, exist_ok=True)
            arq = open(DADOS / "aprova-saida.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            sys.stdout = sys.stdout or arq
            sys.stderr = sys.stderr or arq
        except OSError:
            pass


def _erro_ao_abrir(detalhe: str) -> None:
    _anotar("ERRO AO ABRIR:\n" + detalhe)
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        ultima = detalhe.strip().splitlines()[-1][:300]
        amigavel = _explicar_erro(detalhe)
        if amigavel:
            texto = f"O Aprova não conseguiu abrir.\n\n{amigavel}\n\nDetalhe técnico: {ultima}\n\nOs detalhes estão em:\n{LOG}"
        else:
            texto = (
                f"O Aprova não conseguiu abrir.\n\n{ultima}\n\nOs detalhes estão em:\n{LOG}"
                "\n\nSe continuar, apague a pasta .venv dentro da pasta do Aprova e abra o 'Abrir Aprova.bat' de novo."
            )
        messagebox.showerror("Aprova", texto)
        raiz.destroy()
    except Exception:  # noqa: BLE001
        pass


def _mostrar_abertura() -> None:
    """Telinha "Abrindo o Aprova…" enquanto a janela do app carrega (o app fecha ela quando aparece)."""
    if os.environ.get("APROVA_SEM_ABERTURA"):
        return
    try:
        proc = subprocess.Popen([sys.executable, str(RAIZ / "ferramentas" / "abertura.pyw")], cwd=str(RAIZ), creationflags=SEM_JANELA)
        os.environ["APROVA_ABERTURA_PID"] = str(proc.pid)
    except OSError:
        pass


def abrir_app() -> None:
    if SO_INSTALAR:
        return
    if _no_ambiente():
        _saida_em_arquivo()
        voltar_se_preciso()  # a versão nova já fechou sozinha várias vezes: abre a anterior
        _mostrar_abertura()
        os.chdir(RAIZ)
        sys.path.insert(0, str(RAIZ))
        argumentos = sys.argv[1:]
        sys.argv = [str(RAIZ / "main.py")] + argumentos
        try:
            runpy.run_path(str(RAIZ / "main.py"), run_name="__main__")
        except SystemExit:
            pass
        except Exception:  # noqa: BLE001
            detalhe = traceback.format_exc()
            if voltar_se_preciso(detalhe):
                # abre de novo num processo novo: os módulos da versão nova já estão carregados neste
                subprocess.Popen([sys.executable, str(RAIZ / "iniciar.pyw")] + argumentos, cwd=str(RAIZ), creationflags=SEM_JANELA)
                return
            _erro_ao_abrir(detalhe)
        return
    # ainda no Python do sistema: abre pelo Python do ambiente, sem console (repassa o convite, se houver)
    subprocess.Popen([str(PYW_VENV), str(RAIZ / "iniciar.pyw")] + sys.argv[1:], cwd=str(RAIZ), creationflags=SEM_JANELA)


# --------------------------------------------------------------------------- instalação


ETAPAS = [
    ("python", "Python encontrado"),
    ("ambiente", "Preparar o ambiente do app"),
    ("bibliotecas", "Baixar e instalar as bibliotecas"),
    ("atalho", "Criar o atalho na área de trabalho"),
]
ESTIMATIVA_PACOTES = 45


def _python_cli() -> str:
    """python.exe ao lado do pythonw.exe (para capturar a saída dos comandos)."""
    exe = Path(sys.executable)
    if WIN and exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def _erro_amigavel(saida: str) -> str:
    s = saida.lower()
    if any(x in s for x in ("connectionerror", "failed to establish", "proxyerror", "timed out", "temporary failure", "getaddrinfo", "network is unreachable")):
        return "Não consegui baixar as bibliotecas. Confira a internet e toque em Tentar de novo."
    if "no matching distribution" in s or "could not find a version" in s:
        return "Uma biblioteca não tem versão para este Python. Instale o Python 3.12 ou 3.13 em python.org e abra o 'Abrir Aprova.bat' de novo."
    if "permission" in s or "access is denied" in s or "acesso negado" in s:
        return "O Windows bloqueou a instalação. Feche outros Aprova abertos ou mova a pasta para Documentos e tente de novo."
    if "no space left" in s or "espaço insuficiente" in s:
        return "Falta espaço no disco para instalar."
    return "A instalação falhou. Toque em Ver detalhes para ver a mensagem, ou tente de novo."


class Trabalho(threading.Thread):
    """Faz a instalação em segundo plano e manda o andamento para a janela."""

    def __init__(self, fila: queue.Queue):
        super().__init__(daemon=True)
        self.fila = fila

    def enviar(self, **dados):
        self.fila.put(dados)

    def run(self):
        try:
            if DEMO:
                self._demo()
            else:
                self._instalar()
        except Exception as e:  # noqa: BLE001
            _anotar(traceback.format_exc())
            self.enviar(tipo="erro", texto=f"Erro inesperado: {e}")

    def _demo(self):
        self.enviar(tipo="etapa", etapa="python", estado="feito")
        self.enviar(tipo="etapa", etapa="ambiente", estado="atual")
        time.sleep(0.8)
        self.enviar(tipo="etapa", etapa="ambiente", estado="feito")
        self.enviar(tipo="etapa", etapa="bibliotecas", estado="atual")
        pacotes = ["flet", "flet-desktop", "pymupdf", "beautifulsoup4", "requests", "ddgs", "anthropic", "qrcode", "pillow", "httpx"]
        for i, p in enumerate(pacotes):
            self.enviar(tipo="status", texto=f"Baixando {p}…", progresso=0.08 + 0.55 * (i + 1) / len(pacotes))
            self.enviar(tipo="log", texto=f"Collecting {p}")
            time.sleep(float(os.environ.get("APROVA_INSTALADOR_PASSO", "0.5")))
        self.enviar(tipo="status", texto="Instalando (pode levar um minuto)…", progresso=0.72)
        time.sleep(float(os.environ.get("APROVA_INSTALADOR_FIM", "1")))
        self.enviar(tipo="etapa", etapa="bibliotecas", estado="feito")
        self.enviar(tipo="etapa", etapa="atalho", estado="feito")
        self.enviar(tipo="pronto")

    def _instalar(self):
        _anotar(f"\n=== Instalação {time.strftime('%Y-%m-%d %H:%M:%S')} — Python {sys.version.split()[0]} ({sys.executable})")
        self.enviar(tipo="etapa", etapa="python", estado="feito")
        # 1) ambiente (.venv)
        self.enviar(tipo="etapa", etapa="ambiente", estado="atual")
        self.enviar(tipo="status", texto="Preparando o ambiente do app…", progresso=0.03)
        precisa = not PY_VENV.exists()
        if not precisa:
            try:
                precisa = _rodar([str(PY_VENV), "-c", "import sys"], timeout=30).returncode != 0
            except (OSError, subprocess.SubprocessError):
                precisa = True
        if precisa:
            r = _rodar([_python_cli(), "-m", "venv", "--clear", str(VENV)], timeout=600)
            _anotar(r.stdout + r.stderr)
            if r.returncode != 0 or not PY_VENV.exists():
                self.enviar(tipo="erro", texto="Não consegui preparar o ambiente do app.", detalhe=r.stdout + r.stderr)
                return
        self.enviar(tipo="etapa", etapa="ambiente", estado="feito")
        # 2) bibliotecas
        self.enviar(tipo="etapa", etapa="bibliotecas", estado="atual")
        self.enviar(tipo="status", texto="Conectando…", progresso=0.06)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
        cmd = [str(PY_VENV), "-m", "pip", "install", "--progress-bar", "off", "-r", str(REQUISITOS)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                creationflags=SEM_JANELA, cwd=str(RAIZ), env=env, bufsize=1)
        PROCESSOS.append(proc)
        vistos = 0
        instalando = False
        saida: list[str] = []
        for linha in proc.stdout:  # type: ignore[union-attr]
            linha = linha.rstrip()
            if not linha:
                continue
            saida.append(linha)
            _anotar(linha)
            self.enviar(tipo="log", texto=linha)
            m = re.match(r"(Collecting|Requirement already satisfied:)\s+([A-Za-z0-9_.\-]+)", linha)
            if m:
                vistos += 1
                nome = m.group(2)
                verbo = "Conferindo" if m.group(1).startswith("Requirement") else "Baixando"
                self.enviar(tipo="status", texto=f"{verbo} {nome}…", progresso=0.08 + 0.6 * min(1.0, vistos / ESTIMATIVA_PACOTES))
                continue
            m = re.search(r"Downloading .*?\(([\d.,]+\s*[kMG]B)\)", linha)
            if m:
                self.enviar(tipo="detalhe", texto=f"arquivo de {m.group(1)}")
                continue
            if linha.startswith("Installing collected packages"):
                instalando = True
                self.enviar(tipo="status", texto="Instalando (pode levar um minuto)…", progresso=0.72, devagar=True)
        proc.wait()
        if proc.returncode != 0:
            texto = "\n".join(saida[-40:])
            self.enviar(tipo="erro", texto=_erro_amigavel(texto), detalhe=texto)
            return
        _ = instalando
        marcar_requisitos()
        self.enviar(tipo="etapa", etapa="bibliotecas", estado="feito")
        # 3) atalho
        self.enviar(tipo="etapa", etapa="atalho", estado="atual")
        self.enviar(tipo="status", texto="Criando o atalho…", progresso=0.97)
        if WIN:
            criar_atalho()
        self.enviar(tipo="etapa", etapa="atalho", estado="feito")
        self.enviar(tipo="pronto")


def janela_instalacao() -> None:
    import tkinter as tk
    from tkinter import ttk

    AZUL, AZUL_SUAVE, VERDE, CINZA, TEXTO, TEXTO2, ERRO, FUNDO = (
        "#2340A8", "#E4E9F8", "#1D7F53", "#ECEFF6", "#141C33", "#586179", "#B83A33", "#FFFFFF",
    )
    fonte = "Segoe UI" if WIN else "DejaVu Sans"
    fonte_titulo = ("Segoe UI Semibold", 17) if WIN else (fonte, 16, "bold")

    raiz = tk.Tk()
    raiz.title("Aprova — instalação")
    raiz.configure(bg=FUNDO)
    raiz.resizable(False, False)
    largura, altura = 560, 420
    raiz.geometry(f"{largura}x{altura}+{(raiz.winfo_screenwidth() - largura) // 2}+{(raiz.winfo_screenheight() - altura) // 3}")
    logo = None
    try:
        if WIN:
            raiz.iconbitmap(str(RAIZ / "assets" / "aprova.ico"))
        logo = tk.PhotoImage(file=str(RAIZ / "assets" / "icon.png")).subsample(8)
        if not WIN:
            raiz.iconphoto(True, logo)
    except Exception:  # noqa: BLE001
        logo = None

    estilo = ttk.Style(raiz)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("Aprova.Horizontal.TProgressbar", troughcolor=CINZA, background=AZUL, bordercolor=CINZA,
                     lightcolor=AZUL, darkcolor=AZUL, thickness=8)

    topo = tk.Frame(raiz, bg=FUNDO)
    topo.pack(fill="x", padx=28, pady=(26, 8))
    if logo is not None:
        tk.Label(topo, image=logo, bg=FUNDO).pack(side="left", padx=(0, 14))
    textos = tk.Frame(topo, bg=FUNDO)
    textos.pack(side="left", fill="x", expand=True)
    titulo = tk.Label(textos, text="Preparando o Aprova", font=fonte_titulo, fg=TEXTO, bg=FUNDO, anchor="w")
    titulo.pack(fill="x")
    subtitulo = tk.Label(textos, text="Isso acontece só na primeira vez e leva alguns minutos.\nPode deixar esta janela aberta e fazer outra coisa.",
                         font=(fonte, 10), fg=TEXTO2, bg=FUNDO, anchor="w", justify="left")
    subtitulo.pack(fill="x", pady=(2, 0))

    lista = tk.Frame(raiz, bg=FUNDO)
    lista.pack(fill="x", padx=34, pady=(14, 6))
    marcas: dict[str, tuple[tk.Canvas, tk.Label]] = {}
    situacao: dict[str, str] = {}
    for chave, rotulo in ETAPAS:
        linha = tk.Frame(lista, bg=FUNDO)
        linha.pack(fill="x", pady=3)
        m = tk.Canvas(linha, width=20, height=20, bg=FUNDO, highlightthickness=0)
        m.pack(side="left")
        t = tk.Label(linha, text=rotulo, font=(fonte, 11), fg=TEXTO2, bg=FUNDO, anchor="w")
        t.pack(side="left", padx=(8, 0))
        marcas[chave] = (m, t)

    def desenhar_marca(cv: tk.Canvas, est: str) -> None:
        """Bolinha da etapa desenhada (não depende de fonte com símbolos)."""
        cv.delete("all")
        if est == "feito":
            cv.create_oval(2, 2, 18, 18, fill=VERDE, outline=VERDE)
            cv.create_line(6, 10, 9, 13, 14, 7, fill="#FFFFFF", width=2.2, capstyle="round", joinstyle="round")
        elif est == "atual":
            cv.create_oval(2, 2, 18, 18, outline=AZUL, width=2)
            cv.create_oval(6, 6, 14, 14, fill=AZUL, outline=AZUL)
        elif est == "erro":
            cv.create_oval(2, 2, 18, 18, fill=ERRO, outline=ERRO)
            cv.create_line(7, 7, 13, 13, fill="#FFFFFF", width=2)
            cv.create_line(13, 7, 7, 13, fill="#FFFFFF", width=2)
        else:
            cv.create_oval(3, 3, 17, 17, outline="#C3C9D8", width=2)

    barra = ttk.Progressbar(raiz, style="Aprova.Horizontal.TProgressbar", mode="determinate", maximum=1000)
    barra.pack(fill="x", padx=28, pady=(14, 6))
    status = tk.Label(raiz, text="Começando…", font=(fonte, 10), fg=TEXTO2, bg=FUNDO, anchor="w")
    status.pack(fill="x", padx=28)

    rodape = tk.Frame(raiz, bg=FUNDO)
    rodape.pack(fill="x", side="bottom", padx=28, pady=(6, 18))
    detalhes_txt = tk.Text(raiz, height=7, font=("Consolas" if WIN else "DejaVu Sans Mono", 8), fg=TEXTO2, bg=CINZA, relief="flat", wrap="word")
    estado = {"detalhes": False, "alvo": 0.0, "devagar": False, "acabou": False}

    def alternar_detalhes(e=None):
        estado["detalhes"] = not estado["detalhes"]
        if estado["detalhes"]:
            detalhes_txt.pack(fill="both", expand=True, padx=28, pady=(8, 0), before=rodape)
            raiz.geometry(f"{largura}x{altura + 140}")
            link.config(text="Esconder detalhes")
        else:
            detalhes_txt.pack_forget()
            raiz.geometry(f"{largura}x{altura}")
            link.config(text="Ver detalhes")

    link = tk.Label(rodape, text="Ver detalhes", font=(fonte, 10, "underline"), fg=AZUL, bg=FUNDO, cursor="hand2")
    link.pack(side="left")
    link.bind("<Button-1>", alternar_detalhes)
    botoes = tk.Frame(rodape, bg=FUNDO)
    botoes.pack(side="right")

    def botao(texto: str, acao, principal: bool = False) -> tk.Button:
        return tk.Button(botoes, text=texto, command=acao, font=(fonte, 10, "bold" if principal else "normal"),
                         fg="#FFFFFF" if principal else AZUL, bg=AZUL if principal else FUNDO,
                         activebackground=AZUL_SUAVE, relief="flat", padx=16, pady=6, cursor="hand2", bd=0, highlightthickness=0)

    fila: queue.Queue = queue.Queue()

    def marcar(chave: str, est: str):
        m, t = marcas[chave]
        situacao[chave] = est
        desenhar_marca(m, est)
        cores = {"feito": TEXTO, "atual": TEXTO, "erro": ERRO}
        t.config(fg=cores.get(est, TEXTO2), font=(fonte, 11, "bold") if est == "atual" else (fonte, 11))

    def comecar():
        for w in botoes.winfo_children():
            w.destroy()
        for chave, _ in ETAPAS:
            marcar(chave, "pendente")
        titulo.config(text="Preparando o Aprova", fg=TEXTO)
        estado.update(alvo=0.0, devagar=False, acabou=False)
        barra["value"] = 0
        botao("Cancelar", cancelar).pack(side="right")
        Trabalho(fila).start()

    def cancelar():
        for proc in PROCESSOS:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        raiz.destroy()

    def terminar_e_abrir():
        raiz.destroy()
        abrir_app()

    def processar():
        try:
            while True:
                ev = fila.get_nowait()
                tipo = ev["tipo"]
                if tipo == "etapa":
                    marcar(ev["etapa"], ev["estado"])
                elif tipo == "status":
                    status.config(text=ev["texto"], fg=TEXTO2)
                    estado["alvo"] = max(estado["alvo"], ev.get("progresso", 0))
                    estado["devagar"] = bool(ev.get("devagar"))
                elif tipo == "detalhe":
                    status.config(text=status.cget("text").split("  ·")[0] + "  ·  " + ev["texto"])
                elif tipo == "log":
                    detalhes_txt.insert("end", ev["texto"] + "\n")
                    detalhes_txt.see("end")
                elif tipo == "erro":
                    estado["acabou"] = True
                    atual = next((k for k, _ in ETAPAS if situacao.get(k) == "atual"), None)
                    if atual:
                        marcar(atual, "erro")
                    titulo.config(text="Não deu para terminar", fg=ERRO)
                    status.config(text=ev["texto"], fg=ERRO, wraplength=largura - 56, justify="left")
                    if ev.get("detalhe"):
                        detalhes_txt.insert("end", "\n" + ev["detalhe"] + "\n")
                    for w in botoes.winfo_children():
                        w.destroy()
                    botao("Tentar de novo", comecar, principal=True).pack(side="right", padx=(8, 0))
                    botao("Fechar", lambda: raiz.destroy()).pack(side="right")
                elif tipo == "pronto":
                    estado["acabou"] = True
                    estado["alvo"] = 1.0
                    barra["value"] = 1000
                    titulo.config(text="Tudo pronto!", fg=VERDE)
                    status.config(text="Abrindo o Aprova… Da próxima vez, use o atalho Aprova na área de trabalho." if WIN else "Abrindo o Aprova…")
                    for w in botoes.winfo_children():
                        w.destroy()
                    espera = float(os.environ.get("APROVA_INSTALADOR_PAUSA", "1.6"))
                    raiz.after(int(espera * 1000), terminar_e_abrir)
        except queue.Empty:
            pass
        # a barra anda suave até o alvo; na fase de instalação, continua andando devagar
        atual = barra["value"] / 1000
        alvo = estado["alvo"]
        if estado["devagar"] and not estado["acabou"]:
            alvo = max(alvo, min(0.95, atual + 0.0012))
            estado["alvo"] = alvo
        if atual < alvo:
            barra["value"] = min(1000, (atual + max(0.004, (alvo - atual) * 0.15)) * 1000)
        raiz.after(80, processar)

    comecar()
    raiz.after(80, processar)
    raiz.mainloop()


def instalar_sem_janela() -> None:
    """Sem tkinter: instala mostrando um console (raro)."""
    if not PY_VENV.exists():
        subprocess.run([_python_cli(), "-m", "venv", str(VENV)])
    flags = 0x00000010 if WIN else 0  # CREATE_NEW_CONSOLE
    if subprocess.run([str(PY_VENV), "-m", "pip", "install", "-r", str(REQUISITOS)], creationflags=flags).returncode == 0:
        marcar_requisitos()
    criar_atalho()
    abrir_app()


def main() -> None:
    aplicar_atualizacao()
    if _no_ambiente():  # (no Python do sistema ele só repassa para o do ambiente, que faz isto)
        _confiar_certificados()  # antes de qualquer download (atualização e a janela do Flet na primeira vez)
        atualizar_ao_abrir()
    if ambiente_ok():
        if WIN and not atalho_atualizado():
            threading.Thread(target=criar_atalho, daemon=True).start()
        abrir_app()
        return
    try:
        import tkinter  # noqa: F401
    except ImportError:
        instalar_sem_janela()
        return
    janela_instalacao()


if __name__ == "__main__":
    main()
