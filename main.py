"""Aprova — estudo para concursos públicos.

Uso:
    python main.py                 abre o app no computador
    python main.py --web           abre no navegador (e libera o acesso pelo celular)
    python main.py aprova://grupo/CODIGO   abre (ou leva ao app já aberto) um convite de grupo
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

import flet as ft  # noqa: E402

from aprova import config, convite  # noqa: E402
from aprova.ui.app import App  # noqa: E402


def _fechar_abertura() -> None:
    """Fecha a telinha "Abrindo o Aprova…" (aberta pelo iniciar.pyw)."""
    pid = os.environ.pop("APROVA_ABERTURA_PID", "")
    if pid.isdigit():
        import signal

        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass


def principal(modo_web: bool):
    async def main(page: ft.Page):
        try:
            App(page, modo_web=modo_web).iniciar()
        finally:
            if not modo_web:
                # a janela nasce escondida (sem a tela preta do Flet) e aparece já com o app desenhado
                if not page.window.maximized:
                    try:
                        await page.window.center()
                    except Exception:  # noqa: BLE001
                        pass
                page.window.visible = True
                page.update()
                _fechar_abertura()
                try:
                    await page.window.to_front()
                except Exception:  # noqa: BLE001
                    pass

    return main


def run():
    p = argparse.ArgumentParser(description="Aprova — estudo para concursos públicos")
    p.add_argument("--web", action="store_true", help="servir pelo navegador (computador e celular na mesma rede)")
    p.add_argument("--porta", type=int, default=8550)
    p.add_argument("--sem-navegador", action="store_true", help="no modo web, não abre o navegador do computador")
    p.add_argument("link", nargs="?", default="", help="convite de grupo (aprova://grupo/CODIGO ou o link da página)")
    args = p.parse_args()
    config.garantir_pastas()
    codigo = convite.extrair_codigo(args.link)
    if codigo:
        convite.guardar_pendente(codigo, "link")
        if not args.web and convite.outro_app_aberto():
            # o Aprova já está aberto: ele pega o convite e vem para a frente
            _fechar_abertura()
            return
    assets = str(config.ASSETS_DIR)
    if args.web:
        from aprova import rede

        if args.sem_navegador:
            os.environ["FLET_FORCE_WEB_SERVER"] = "1"
        print(f"\nAprova no navegador: http://localhost:{args.porta}")
        print(f"No celular (mesmo Wi-Fi): {rede.endereco_celular(args.porta)}\n")
        ft.run(principal(True), view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=args.porta, assets_dir=assets)
    else:
        try:
            ft.run(principal(False), view=ft.AppView.FLET_APP_HIDDEN, assets_dir=assets)
        finally:
            convite.parar_vivo()


if __name__ == "__main__":
    run()
