"""Telinha "Abrindo o Aprova…" (ou "Atualizando…") mostrada enquanto o app carrega (fecha sozinha)."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        return
    win = sys.platform == "win32"
    fonte = "Segoe UI" if win else "DejaVu Sans"
    raiz = tk.Tk()
    raiz.overrideredirect(True)  # sem barra de título
    raiz.attributes("-topmost", True)
    largura, altura = 340, 230
    x = (raiz.winfo_screenwidth() - largura) // 2
    y = (raiz.winfo_screenheight() - altura) // 2
    raiz.geometry(f"{largura}x{altura}+{x}+{y}")
    raiz.configure(bg="#D9DEEA")  # borda fina
    cartao = tk.Frame(raiz, bg="#FFFFFF")
    cartao.place(x=1, y=1, width=largura - 2, height=altura - 2)
    try:
        logo = tk.PhotoImage(file=str(RAIZ / "assets" / "icon.png")).subsample(7)
        tk.Label(cartao, image=logo, bg="#FFFFFF").pack(pady=(26, 6))
    except Exception:  # noqa: BLE001
        logo = None
    tk.Label(cartao, text="Aprova", font=(fonte, 20, "bold"), fg="#2340A8", bg="#FFFFFF").pack()
    texto = sys.argv[1] if len(sys.argv) > 1 else "Abrindo…"
    tk.Label(cartao, text=texto[:60], font=(fonte, 10), fg="#586179", bg="#FFFFFF").pack(pady=(0, 10))
    estilo = ttk.Style(raiz)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("A.Horizontal.TProgressbar", troughcolor="#ECEFF6", background="#2340A8", bordercolor="#ECEFF6",
                     lightcolor="#2340A8", darkcolor="#2340A8", thickness=5)
    barra = ttk.Progressbar(cartao, style="A.Horizontal.TProgressbar", mode="indeterminate", length=220)
    barra.pack()
    barra.start(12)
    raiz.after(120000 if len(sys.argv) > 1 else 30000, raiz.destroy)  # se algo der errado, some sozinha
    raiz.mainloop()
    _ = logo


if __name__ == "__main__":
    main()
