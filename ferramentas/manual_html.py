"""Gera docs/manual.html (o guia completo no site) a partir do docs/MANUAL.md.

Rode depois de mudar o guia:  python ferramentas/manual_html.py   (precisa do pacote markdown: pip install markdown)
A parte "Para desenvolver" fica só no MANUAL.md e no README (é de quem mantém o app).
"""

from __future__ import annotations

import html
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parent.parent
BAIXAR = "https://github.com/NatanaelSantz/aprova/releases/latest/download/Aprova.zip"

PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Guia completo · Aprova</title>
<meta name="description" content="Guia completo do Aprova: como instalar, achar provas, resolver, revisar, usar os grupos, o ranking, o personagem e a IA.">
<meta name="theme-color" content="#2340A8">
<link rel="icon" href="favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Fraunces:ital,opsz,wght,SOFT@0,9..144,400..700,0..100;1,9..144,400..700,0..100&display=swap">
<style>
:root { --papel: #F4F6FB; --folha: #FFFFFF; --tinta: #111A33; --tinta2: #4E5772; --linha: #DCE1EC; --azul: #2340A8; --azul-suave: #E4E9F8; --sobre-azul: #FFFFFF; --marca: #FFD84D;
  --f-titulo: "Fraunces", Georgia, serif; --f-texto: "Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", sans-serif; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --papel: #0C1020; --folha: #141A2C; --tinta: #E8EBF4; --tinta2: #A0A9BF; --linha: #262E46; --azul: #93A8FF; --azul-suave: #1C2646; --sobre-azul: #0C1020; color-scheme: dark; }
}
:root[data-theme="dark"] { --papel: #0C1020; --folha: #141A2C; --tinta: #E8EBF4; --tinta2: #A0A9BF; --linha: #262E46; --azul: #93A8FF; --azul-suave: #1C2646; --sobre-azul: #0C1020; color-scheme: dark; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 80px; }
body { margin: 0; background: var(--papel); color: var(--tinta); font-family: var(--f-texto); font-size: 17px; line-height: 1.65; -webkit-font-smoothing: antialiased; }
a { color: var(--azul); text-underline-offset: 3px; }
:focus-visible { outline: 3px solid var(--azul); outline-offset: 3px; border-radius: 6px; }
.topo { position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--papel) 85%, transparent); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border-bottom: 1px solid var(--linha); }
.topo div { max-width: 1100px; margin: 0 auto; padding: 12px 22px; display: flex; align-items: center; gap: 16px; }
.marca { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.marca img { width: 34px; height: 34px; border-radius: 9px; }
.marca span { font-family: var(--f-titulo); font-weight: 600; font-size: 1.4rem; color: var(--azul); }
.bt { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; background: var(--azul); color: var(--sobre-azul); font-weight: 700; font-size: .92rem; text-decoration: none; border-radius: 999px; padding: 10px 18px; }
main { max-width: 1100px; margin: 0 auto; padding: 40px 22px 80px; display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 56px; align-items: start; }
nav.indice { position: sticky; top: 84px; font-size: .92rem; max-height: calc(100vh - 110px); overflow: auto; }
nav.indice p { margin: 0 0 8px; font-weight: 700; }
nav.indice ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
nav.indice a { display: block; color: var(--tinta2); text-decoration: none; padding: 4px 10px; border-radius: 8px; }
nav.indice a:hover { color: var(--tinta); background: var(--azul-suave); }
article { min-width: 0; max-width: 46em; }
h1, h2, h3 { font-family: var(--f-titulo); font-weight: 500; letter-spacing: -0.02em; line-height: 1.12; text-wrap: balance; }
h1 { font-size: clamp(2.3rem, 5vw, 3.4rem); margin: 0 0 18px; }
h2 { font-size: clamp(1.6rem, 3vw, 2.1rem); margin: 56px 0 14px; padding-top: 18px; border-top: 1px solid var(--linha); }
h3 { font-size: 1.3rem; margin: 30px 0 10px; }
p, li { color: var(--tinta); }
ul, ol { padding-left: 1.3em; }
li { margin: 6px 0; }
code { font-size: .9em; background: var(--azul-suave); padding: 1px 6px; border-radius: 5px; }
pre { background: var(--folha); border: 1px solid var(--linha); border-radius: 12px; padding: 14px 16px; overflow-x: auto; }
pre code { background: none; padding: 0; }
table { width: 100%; border-collapse: collapse; font-size: .95rem; margin: 16px 0; display: block; overflow-x: auto; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--linha); vertical-align: top; }
th { color: var(--tinta2); font-weight: 700; }
blockquote { margin: 18px 0; padding: 12px 18px; border-left: 4px solid var(--marca); background: var(--folha); border-radius: 0 12px 12px 0; }
strong { font-weight: 700; }
.voltar { display: inline-block; margin-bottom: 18px; font-size: .95rem; }
@media (max-width: 860px) { main { grid-template-columns: minmax(0, 1fr); gap: 0; padding-top: 28px; } nav.indice { position: static; max-height: none; margin-bottom: 10px; }
  nav.indice ul { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
</head>
<body>
<header class="topo"><div>
  <a class="marca" href="./"><img src="icon.png" alt="" width="34" height="34"><span>Aprova</span></a>
  <a class="bt" href="{baixar}" target="_blank" rel="noopener">Baixar grátis</a>
</div></header>
<main>
  <nav class="indice" aria-label="Nesta página"><p>Nesta página</p><ul>
{indice}
  </ul></nav>
  <article>
    <a class="voltar" href="./">Voltar para o site</a>
{corpo}
  </article>
</main>
</body>
</html>
"""


def main() -> None:
    texto = (RAIZ / "docs" / "MANUAL.md").read_text(encoding="utf-8")
    texto = texto.split("\n## Para desenvolver")[0]  # a parte de quem mantém o app fica no README
    linhas = [ln for ln in texto.splitlines() if not ln.startswith("[← voltar ao início]")]
    linhas[0] = "# Guia completo do Aprova"
    texto = "\n".join(linhas).replace("Um robô do GitHub confere", "Um robô confere")
    # no site, sem falar do GitHub (o guia é para quem usa o app)
    texto = texto.replace("baixa do GitHub a janela do app", "baixa da internet a janela do app").replace("o certificado do GitHub", "o certificado do site de onde ele baixa")
    md = markdown.Markdown(extensions=["tables", "sane_lists", "toc"], extension_configs={"toc": {"toc_depth": "2"}})
    corpo = md.convert(texto)
    indice = "\n".join(f'    <li><a href="#{t["id"]}">{html.escape(t["name"])}</a></li>' for t in md.toc_tokens[0]["children"]) if md.toc_tokens else ""
    destino = RAIZ / "docs" / "manual.html"
    destino.write_text(PAGINA.replace("{baixar}", BAIXAR).replace("{indice}", indice).replace("{corpo}", corpo), encoding="utf-8")
    print("ok:", destino, len(corpo), "caracteres")


if __name__ == "__main__":
    main()
