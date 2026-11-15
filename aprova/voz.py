"""Leitura em voz alta usando as vozes do próprio sistema (sem internet), com escolha da voz.

Windows: as vozes "clássicas" (System.Speech, ex.: Maria Desktop) e as vozes novas do Windows 10/11
(Windows.Media.SpeechSynthesis, ex.: Maria e Daniel), que o System.Speech não enxerga. As novas são
gravadas num WAV temporário e tocadas na hora.
macOS: comando `say` (todas as vozes de `say -v ?`). Linux: `espeak-ng`/`espeak`, com variações de timbre.

Cada voz tem um id "motor|nome" (o que fica guardado nos ajustes, chave "voz"); "" = automática
(a primeira em português).
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading

SISTEMA = platform.system()
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW (Windows)

IDIOMAS = {"pt-br": "Português (Brasil)", "pt-pt": "Português (Portugal)", "pt": "Português", "en": "Inglês", "es": "Espanhol",
           "fr": "Francês", "it": "Italiano", "de": "Alemão", "ja": "Japonês", "zh": "Chinês"}


def nome_idioma(codigo: str) -> str:
    c = (codigo or "").lower().replace("_", "-")
    return IDIOMAS.get(c) or IDIOMAS.get(c.split("-")[0]) or (codigo or "Outro idioma")


def em_portugues(v: dict) -> bool:
    return (v.get("idioma") or "").lower().replace("_", "-").startswith("pt")


def _nome_curto(nome: str) -> str:
    """'Microsoft Maria Desktop - Portuguese(Brazil)' -> 'Maria' (para juntar a mesma voz vista pelos dois motores)."""
    n = re.sub(r"^Microsoft\s+", "", nome or "")
    n = re.split(r"\s+-\s+|\s+Desktop\b|\s*\(", n)[0]
    return n.strip().lower()


def _ps(texto: str) -> str:
    """Texto entre aspas simples do PowerShell."""
    return "'" + (texto or "").replace("'", "''") + "'"


# ---------------------------------------------------------------- Windows

_LISTAR_WINDOWS = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($v in $s.GetInstalledVoices()) { if ($v.Enabled) { 'sapi|' + $v.VoiceInfo.Name + '|' + $v.VoiceInfo.Culture.Name + '|' + $v.VoiceInfo.Gender } }
try {
  [void][Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
  foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) { 'winrt|' + $v.DisplayName + '|' + $v.Language + '|' + $v.Gender }
} catch {}
"""


def _script_sapi(nome: str | None, velocidade: int, txt: str, wav: str | None) -> str:
    escolher = (
        f"try {{ $s.SelectVoice({_ps(nome)}) }} catch {{}};" if nome else
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'pt*' } | Select-Object -First 1;"
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
    )
    saida = f"$s.SetOutputToWaveFile({_ps(wav)});" if wav else ""
    return (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        + escolher +
        f"$s.Rate = {velocidade * 2};"
        + saida +
        f"$t = Get-Content -Raw -Encoding UTF8 -LiteralPath {_ps(txt)};"
        "$s.Speak($t); $s.Dispose()"
    )


def _script_winrt(nome: str, velocidade: int, txt: str, wav: str, tocar: bool) -> str:
    taxa = max(0.5, min(3.0, 1.0 + 0.12 * velocidade))
    return (
        "$ErrorActionPreference = 'Stop';"
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
        "[void][Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime];"
        "[void][Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime];"
        "$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and "
        "$_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0];"
        "function Esperar($op, [Type]$tipo) { $t = $asTask.MakeGenericMethod($tipo).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result };"
        "$s = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer;"
        f"$v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object {{ $_.DisplayName -eq {_ps(nome)} }} | Select-Object -First 1;"
        "if ($v) { $s.Voice = $v };"
        f"try {{ $s.Options.SpeakingRate = {taxa:.2f} }} catch {{}};"
        f"$t = Get-Content -Raw -Encoding UTF8 -LiteralPath {_ps(txt)};"
        "$st = Esperar ($s.SynthesizeTextToStreamAsync($t)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream]);"
        "$r = New-Object Windows.Storage.Streams.DataReader($st.GetInputStreamAt(0));"
        "$n = Esperar ($r.LoadAsync([uint32]$st.Size)) ([uint32]);"
        "$b = New-Object byte[] $n; $r.ReadBytes($b);"
        f"[IO.File]::WriteAllBytes({_ps(wav)}, $b);"
        + (f"(New-Object System.Media.SoundPlayer {_ps(wav)}).PlaySync()" if tocar else "")
    )


def _vozes_windows() -> list[dict]:
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _LISTAR_WINDOWS],
                               capture_output=True, timeout=25, creationflags=SEM_JANELA).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    texto = saida.decode("utf-8", "replace")
    vozes, vistos = [], set()
    linhas = [l.strip().split("|") for l in texto.splitlines() if l.count("|") >= 3]
    # a mesma voz pode aparecer nos dois motores: fica a clássica (mais testada), e as novas só entram se faltarem
    for motor in ("sapi", "winrt"):
        for m, nome, idioma, genero in (l[:4] for l in linhas):
            if m != motor or not nome:
                continue
            chave = (_nome_curto(nome), idioma.lower())
            if chave in vistos:
                continue
            vistos.add(chave)
            vozes.append({"id": f"{motor}|{nome}", "nome": re.sub(r"^Microsoft\s+", "", nome), "idioma": idioma,
                          "genero": "feminina" if genero.lower().startswith("f") else "masculina" if genero.lower().startswith("m") else ""})
    return vozes


# ---------------------------------------------------------------- macOS e Linux

def _vozes_mac() -> list[dict]:
    try:
        saida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    vozes = []
    for linha in saida.splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2}[_-][A-Za-z0-9]{2,4})\s+#", linha)
        if m:
            vozes.append({"id": f"say|{m.group(1).strip()}", "nome": m.group(1).strip(), "idioma": m.group(2), "genero": ""})
    return vozes


def _vozes_linux() -> list[dict]:
    if not (shutil.which("espeak-ng") or shutil.which("espeak")):
        return []
    # o espeak tem uma voz por idioma e variações de timbre (+f = feminina, +m = masculina)
    timbres = [("", "Padrão", ""), ("+f3", "Feminina", "feminina"), ("+f5", "Feminina suave", "feminina"),
               ("+m3", "Masculina", "masculina"), ("+m7", "Masculina grave", "masculina")]
    return [{"id": f"espeak|pt-br{v}", "nome": f"eSpeak {rot}", "idioma": "pt-BR", "genero": g} for v, rot, g in timbres]


_cache_vozes: list[list[dict]] = []


def vozes(recarregar: bool = False) -> list[dict]:
    """As vozes instaladas, as em português primeiro. [{"id", "nome", "idioma", "genero"}]. Pode demorar ~1 s no Windows."""
    if _cache_vozes and not recarregar:
        return _cache_vozes[0]
    from . import plataforma

    if plataforma.CELULAR:
        lista = []
    elif SISTEMA == "Windows":
        lista = _vozes_windows()
    elif SISTEMA == "Darwin":
        lista = _vozes_mac()
    else:
        lista = _vozes_linux()
    lista.sort(key=lambda v: (not em_portugues(v), not (v["idioma"] or "").lower().replace("_", "-").startswith("pt-br"), v["nome"].lower()))
    _cache_vozes[:] = [lista]
    return lista


def rotulo(v: dict) -> str:
    """'Daniel · Português (Brasil) · masculina'."""
    return " · ".join(x for x in (v["nome"], nome_idioma(v["idioma"]), v.get("genero") or "") if x)


# ---------------------------------------------------------------- leitor


class Leitor:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def disponivel(self) -> bool:
        from . import plataforma

        if plataforma.CELULAR:
            return False  # no celular a voz fica para uma versão futura (sem programas do sistema para chamar)
        if SISTEMA == "Windows":
            return shutil.which("powershell") is not None
        if SISTEMA == "Darwin":
            return shutil.which("say") is not None
        return bool(shutil.which("espeak-ng") or shutil.which("espeak"))

    @property
    def falando(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def comando(self, caminho_txt: str, velocidade: int, voz: str = "", wav: str | None = None, tocar: bool = True) -> list[str]:
        """O comando que lê o arquivo de texto com a voz escolhida (ou grava em 'wav', para os testes)."""
        velocidade = max(-5, min(5, int(velocidade)))
        motor, _, nome = (voz or "").partition("|")
        if SISTEMA == "Windows":
            if motor == "winrt" and nome:
                script = _script_winrt(nome, velocidade, caminho_txt, wav or caminho_txt[:-4] + ".wav", tocar)
            else:
                script = _script_sapi(nome if motor == "sapi" else None, velocidade, caminho_txt, wav if not tocar else None)
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
        if SISTEMA == "Darwin":
            cmd = ["say", "-r", str(185 + 20 * velocidade), "-f", caminho_txt]
            escolhida = nome if motor == "say" and nome else _voz_mac_pt()
            if escolhida:
                cmd[1:1] = ["-v", escolhida]
            if wav and not tocar:
                cmd += ["-o", wav, "--data-format=LEI16@22050"]
            return cmd
        prog = shutil.which("espeak-ng") or shutil.which("espeak") or "espeak-ng"
        cmd = [prog, "-v", nome if motor == "espeak" and nome else "pt-br", "-s", str(165 + 15 * velocidade), "-f", caminho_txt]
        if wav and not tocar:
            cmd += ["-w", wav]
        return cmd

    def falar(self, texto: str, velocidade: int = 0, ao_terminar=None, voz: str = "") -> bool:
        """Lê o texto. velocidade vai de -5 (lenta) a +5 (rápida); voz é o id de vozes() ("" = automática)."""
        self.parar()
        texto = (texto or "").strip()
        if not texto or not self.disponivel:
            return False
        fd, caminho = tempfile.mkstemp(suffix=".txt", prefix="aprova_voz_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        wav = caminho[:-4] + ".wav"
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if SISTEMA == "Windows":
            kwargs["creationflags"] = SEM_JANELA
        with self._lock:
            try:
                self._proc = subprocess.Popen(self.comando(caminho, velocidade, voz, wav), **kwargs)
            except OSError:
                self._proc = None
                return False
        proc = self._proc

        def esperar():
            proc.wait()
            for arq in (caminho, wav):
                try:
                    os.remove(arq)
                except OSError:
                    pass
            if ao_terminar and self._proc is proc:
                ao_terminar()

        threading.Thread(target=esperar, daemon=True).start()
        return True

    def gravar(self, texto: str, wav: str, velocidade: int = 0, voz: str = "", timeout: float = 60) -> bool:
        """Grava a fala num arquivo WAV sem tocar (para conferir uma voz). True se o arquivo saiu."""
        fd, caminho = tempfile.mkstemp(suffix=".txt", prefix="aprova_voz_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        kwargs: dict = {"capture_output": True, "timeout": timeout}
        if SISTEMA == "Windows":
            kwargs["creationflags"] = SEM_JANELA
        try:
            subprocess.run(self.comando(caminho, velocidade, voz, wav, tocar=False), **kwargs)
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass
        return os.path.exists(wav) and os.path.getsize(wav) > 1000

    def parar(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except OSError:
                    pass
            self._proc = None


_cache_voz_mac: list[str | None] = []


def _voz_mac_pt() -> str | None:
    if _cache_voz_mac:
        return _cache_voz_mac[0]
    voz = next((v["nome"] for v in _vozes_mac() if (v["idioma"] or "").replace("-", "_") == "pt_BR"), None)
    _cache_voz_mac.append(voz)
    return voz
