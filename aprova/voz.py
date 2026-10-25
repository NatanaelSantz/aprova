"""Leitura em voz alta usando a voz do próprio sistema (sem internet).

Windows: System.Speech (vozes do Windows; procura uma voz em português).
macOS: comando `say`. Linux: `espeak-ng`/`espeak`.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import threading

SISTEMA = platform.system()


class Leitor:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._arquivo: str | None = None

    @property
    def disponivel(self) -> bool:
        if SISTEMA == "Windows":
            return shutil.which("powershell") is not None
        if SISTEMA == "Darwin":
            return shutil.which("say") is not None
        return bool(shutil.which("espeak-ng") or shutil.which("espeak"))

    @property
    def falando(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def falar(self, texto: str, velocidade: int = 0, ao_terminar=None) -> bool:
        """Lê o texto. velocidade vai de -5 (lenta) a +5 (rápida)."""
        self.parar()
        texto = (texto or "").strip()
        if not texto or not self.disponivel:
            return False
        fd, caminho = tempfile.mkstemp(suffix=".txt", prefix="aprova_voz_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        self._arquivo = caminho
        velocidade = max(-5, min(5, int(velocidade)))
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if SISTEMA == "Windows":
            alvo = caminho.replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'pt*' } | Select-Object -First 1;"
                "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
                f"$s.Rate = {velocidade * 2};"
                f"$t = Get-Content -Raw -Encoding UTF8 -LiteralPath '{alvo}';"
                "$s.Speak($t)"
            )
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        elif SISTEMA == "Darwin":
            cmd = ["say", "-r", str(185 + 20 * velocidade), "-f", caminho]
            voz = _voz_mac_pt()
            if voz:
                cmd[1:1] = ["-v", voz]
        else:
            prog = shutil.which("espeak-ng") or shutil.which("espeak")
            cmd = [prog, "-v", "pt-br", "-s", str(165 + 15 * velocidade), "-f", caminho]
        with self._lock:
            try:
                self._proc = subprocess.Popen(cmd, **kwargs)
            except OSError:
                self._proc = None
                return False
        proc = self._proc

        def esperar():
            proc.wait()
            try:
                os.remove(caminho)
            except OSError:
                pass
            if ao_terminar and self._proc is proc:
                ao_terminar()

        threading.Thread(target=esperar, daemon=True).start()
        return True

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
    voz = None
    try:
        saida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5).stdout
        for linha in saida.splitlines():
            if "pt_BR" in linha:
                voz = linha.split()[0]
                break
    except (OSError, subprocess.SubprocessError):
        pass
    _cache_voz_mac.append(voz)
    return voz
