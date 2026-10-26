"""Barra de título do Windows com as cores do Aprova.

Em vez de esconder a barra do Windows (isso impediu o app de abrir na 1.9.2), o Aprova só pinta a
barra que já existe, pelo mesmo recurso que o Windows 11 usa para os apps dele (DWM): fundo, texto,
borda e o modo claro/escuro dos botões. Os botões, o arrastar, o encaixe nas bordas (snap) e o
redimensionamento continuam sendo os do Windows.

No Windows 10 a cor do fundo não muda (só o modo claro/escuro). Fora do Windows não faz nada.
Qualquer falha é ignorada: no pior caso a barra fica como era.
"""

from __future__ import annotations

import sys
import time

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
CLASSE_FLUTTER = "FLUTTER_RUNNER_WIN32_WINDOW"


def colorref(hexa: str) -> int:
    """'#RRGGBB' → COLORREF do Windows (0x00BBGGRR)."""
    h = hexa.strip().lstrip("#")[:6]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def _nome_do_processo(pid: int) -> str:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        tam = wintypes.DWORD(520)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            return buf.value.replace("/", "\\").rsplit("\\", 1)[-1].lower()
        return ""
    finally:
        k32.CloseHandle(h)


def janelas_do_app(titulo: str) -> list[int]:
    """Janelas visíveis do Aprova: título igual e janela do Flutter (ou processo do Flet)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    achadas: list[int] = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def olhar(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            texto = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, texto, 256)
            if texto.value != titulo:
                return True
            classe = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, classe, 128)
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if classe.value == CLASSE_FLUTTER or "flet" in _nome_do_processo(pid.value):
                achadas.append(hwnd)
        except Exception:  # noqa: BLE001
            pass
        return True

    user32.EnumWindows(PROC(olhar), 0)
    return achadas


def _pintar(hwnd: int, fundo: str, texto: str, borda: str, escuro: bool) -> None:
    import ctypes
    from ctypes import wintypes

    dwm = ctypes.WinDLL("dwmapi")
    dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    user32 = ctypes.WinDLL("user32")
    user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]

    def definir(atributo: int, valor: int) -> None:
        v = wintypes.DWORD(valor)
        dwm.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(v), ctypes.sizeof(v))

    definir(DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if escuro else 0)  # botões claros ou escuros
    definir(DWMWA_CAPTION_COLOR, colorref(fundo))  # Windows 11
    definir(DWMWA_TEXT_COLOR, colorref(texto))
    definir(DWMWA_BORDER_COLOR, colorref(borda))
    user32.RedrawWindow(hwnd, None, None, 0x0400 | 0x0001)  # RDW_FRAME | RDW_INVALIDATE: redesenha a barra


def _pintar_quando_aparecer(titulo: str, fundo: str, texto: str, borda: str, escuro: bool, esperar: float) -> bool:
    fim = time.time() + esperar
    while time.time() < fim:
        janelas = janelas_do_app(titulo)
        if janelas:
            for h in janelas:
                _pintar(h, fundo, texto, borda, escuro)
            return True
        time.sleep(0.4)
    return False


def pintar_barra(titulo: str, fundo: str, texto: str, borda: str, escuro: bool, esperar: float = 15.0) -> bool:
    """Pinta a barra de título num processo separado (espera a janela aparecer).

    Num processo à parte, um erro do Windows aqui nunca derruba o app. Devolve False fora do Windows."""
    if sys.platform != "win32":
        return False
    import subprocess

    subprocess.Popen(
        [sys.executable, "-I", __file__, titulo, fundo, texto, borda, "1" if escuro else "0", str(esperar)],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    try:
        t, f, tx, b, esc, esp = sys.argv[1:7]
        _pintar_quando_aparecer(t, f, tx, b, esc == "1", float(esp))
    except Exception:  # noqa: BLE001
        pass
