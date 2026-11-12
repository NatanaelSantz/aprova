"""Movimento do Aprova: animações curtas e suaves, no espírito do Stripe e do Revolut.

O que tem aqui:
- `entrada`: o que chega na tela nasce transparente e um pouco abaixo e sobe aparecendo; com `ordem`, em cascata.
- `numero`: números grandes que contam até o valor (horas, acerto, nota do simulado).
- `crescer`: barras que enchem da esquerda para a direita.
- `realce`: cartão clicável que se levanta um pouco quando o mouse passa (só no computador).
- `pulsar` e `tremer`: a alternativa certa dá um pulinho; a errada balança.
- `confete`: chuva de papel picado quando o simulado vai bem.

Por que não pesa:
- É animação implícita do Flutter: o Python muda um valor uma vez (opacidade, posição, escala) e o Flutter anima
  sozinho a 60 quadros por segundo, sem conversar com o Python a cada quadro.
- Tudo o que entrou na tela é revelado numa atualização só (page.update com a lista dos que chegaram).
- Os números que contam têm poucos passos e andam juntos, na mesma atualização.
- Só anima logo depois de trocar de tela (janela de 1,5 s): a tela que se redesenha por outro motivo não pisca.
- Ajustes → Animações desliga tudo.
"""

from __future__ import annotations

import asyncio
import math
import random
import threading
import time
from typing import Callable

import flet as ft

SUAVE = ft.AnimationCurve.EASE_OUT_CUBIC
SAIDA = ft.AnimationCurve.EASE_OUT
ELASTICA = ft.AnimationCurve.EASE_OUT_BACK
JANELA = 1.5  # segundos depois de trocar de tela em que o que aparece entra animado
TENTATIVAS = 14  # quantas vezes espera um controle entrar na tela antes de desistir de animar


# ---------------------------------------------------------------------- estado (um por janela do app)

_APPS: dict[int, "weakref.ref"] = {}


def registrar_app(app) -> None:
    """Cada janela (sessão) do app se registra pela página: assim os componentes acham o app sem recebê-lo."""
    import weakref

    _APPS[id(app.page)] = weakref.ref(app)


def app_atual():
    """O app da sessão em que o código está rodando (ou None fora de uma sessão)."""
    try:
        pg = ft.context.page
    except Exception:  # noqa: BLE001
        return None
    ref = _APPS.get(id(pg)) if pg is not None else None
    return ref() if ref else None


def ligado(app) -> bool:
    try:
        return bool(app.aj["animacoes"])
    except Exception:  # noqa: BLE001
        return True


def _estado(app) -> dict:
    st = getattr(app, "_movimento", None)
    if st is None:
        st = {"pendentes": [], "contadores": [], "agendado": False, "contando": False, "ate": 0.0, "trava": threading.Lock()}
        app._movimento = st
    return st


def abrir_janela(app, segundos: float = JANELA) -> None:
    """Acabou de trocar de tela: o que for montado logo em seguida entra animado."""
    if ligado(app):
        _estado(app)["ate"] = time.monotonic() + segundos


def fechar_janela(app) -> None:
    _estado(app)["ate"] = 0.0


def na_janela(app) -> bool:
    return ligado(app) and time.monotonic() < _estado(app)["ate"]


def _montado(ctrl: ft.Control) -> bool:
    try:
        return ctrl.page is not None
    except Exception:  # noqa: BLE001 - ainda não está na tela
        return False


def _agendar(app) -> None:
    st = _estado(app)
    with st["trava"]:
        if st["agendado"]:
            return
        st["agendado"] = True
    try:
        app.page.run_task(_revelar, app)
    except Exception:  # noqa: BLE001
        st["agendado"] = False


async def _revelar(app) -> None:
    """Espera os controles chegarem na tela e leva todos ao estado final numa atualização só."""
    st = _estado(app)
    try:
        await asyncio.sleep(0.04)
        for _ in range(TENTATIVAS + 2):
            with st["trava"]:
                lista, st["pendentes"] = st["pendentes"], []
            prontos, resto = [], []
            for item in lista:
                ctrl, final, tentativas = item
                if _montado(ctrl):
                    final(ctrl)
                    prontos.append(ctrl)
                elif tentativas >= TENTATIVAS:
                    final(ctrl)  # nunca apareceu (janela fechada, aba escondida): fica pronto, sem animação
                else:
                    item[2] += 1
                    resto.append(item)
            if prontos:
                try:
                    app.page.update(*prontos)
                except Exception:  # noqa: BLE001 - saiu da tela no meio do caminho
                    pass
            with st["trava"]:
                st["pendentes"] = resto + st["pendentes"]
                vazio = not st["pendentes"]
            if vazio:
                break
            await asyncio.sleep(0.05)
    finally:
        with st["trava"]:
            st["agendado"] = False
            sobrou = bool(st["pendentes"])
        if sobrou:
            _agendar(app)


def _pendente(app, ctrl: ft.Control, final: Callable[[ft.Control], None]) -> None:
    st = _estado(app)
    with st["trava"]:
        st["pendentes"].append([ctrl, final, 0])
    _agendar(app)


# ---------------------------------------------------------------------- entrada (fade + sobe)

def _final_entrada(ctrl: ft.Control) -> None:
    ctrl.opacity = 1
    ctrl.offset = ft.Offset(0, 0)


def entrada(app, controle: ft.Control, ordem: int = 0, dx: float = 0.0, dy: float = 0.035, duracao: int | None = None,
            forcar: bool = False, de: float = 0.0) -> ft.Control:
    """Embrulha o controle: ele nasce transparente e deslocado e chega ao lugar com um fade.
    `ordem` (0, 1, 2...) faz a cascata: cada um um pouco mais lento que o anterior, todos numa atualização só."""
    if controle is None or not ligado(app) or not (forcar or na_janela(app)):
        return controle
    if getattr(controle, "visible", True) is False:
        return controle  # escondido agora (pode aparecer depois): embrulhar deixaria um vão na coluna
    dur = duracao or (300 + 60 * min(int(ordem), 8))
    caixa = ft.Container(
        controle,
        opacity=de,  # de > 0: a tela nova já começa um pouco visível (sem o "piscar" em branco)
        offset=ft.Offset(dx, dy),
        animate_opacity=ft.Animation(dur, SAIDA),
        animate_offset=ft.Animation(dur + 140, SUAVE),
    )
    for attr in ("expand", "col"):  # o embrulho ocupa o lugar do controle na linha/coluna
        valor = getattr(controle, attr, None)
        if valor:
            setattr(caixa, attr, valor)
    _pendente(app, caixa, _final_entrada)
    return caixa


def cascata(app, controles: list, inicio: int = 0, dy: float = 0.05) -> list:
    """Vários cartões entrando um depois do outro."""
    return [entrada(app, ctl, ordem=inicio + i, dy=dy) for i, ctl in enumerate(controles)]


# ---------------------------------------------------------------------- barras que enchem

def crescer(app, preenchimento: ft.Container, duracao: int = 760) -> ft.Container:
    """A parte cheia da barra começa vazia e enche da esquerda para a direita."""
    if not na_janela(app):
        return preenchimento
    preenchimento.scale = ft.Scale(scale_x=0, scale_y=1, alignment=ft.Alignment.CENTER_LEFT)
    preenchimento.animate_scale = ft.Animation(duracao, SUAVE)
    _pendente(app, preenchimento, lambda c: setattr(c, "scale", ft.Scale(scale_x=1, scale_y=1, alignment=ft.Alignment.CENTER_LEFT)))
    return preenchimento


def crescer_altura(app, coluna: ft.Container, duracao: int = 700, ordem: int = 0) -> ft.Container:
    """Barra de gráfico que sobe do chão (as horas de cada dia)."""
    if not na_janela(app):
        return coluna
    coluna.scale = ft.Scale(scale_x=1, scale_y=0, alignment=ft.Alignment.BOTTOM_CENTER)
    coluna.animate_scale = ft.Animation(duracao + 50 * min(ordem, 8), SUAVE)
    _pendente(app, coluna, lambda c: setattr(c, "scale", ft.Scale(scale_x=1, scale_y=1, alignment=ft.Alignment.BOTTOM_CENTER)))
    return coluna


# ---------------------------------------------------------------------- números que contam

def numero(app, valor: float | None, formatar: Callable[[float], str] | None = None, **texto_kw) -> ft.Text:
    """Texto de um número grande que conta de 0 até o valor (como o saldo no Revolut)."""
    formatar = formatar or (lambda v: f"{v:.0f}")
    vazio = texto_kw.pop("vazio", "—")
    final = formatar(valor) if valor is not None else vazio
    t = ft.Text(final, **texto_kw)
    if valor and isinstance(valor, (int, float)) and na_janela(app):
        t.value = formatar(0)
        st = _estado(app)
        with st["trava"]:
            st["contadores"].append({"t": t, "alvo": float(valor), "fmt": formatar, "fim": final, "esperas": 0})
        _agendar_contagem(app)
    return t


def _agendar_contagem(app) -> None:
    st = _estado(app)
    with st["trava"]:
        if st["contando"]:
            return
        st["contando"] = True
    try:
        app.page.run_task(_contar, app)
    except Exception:  # noqa: BLE001
        st["contando"] = False


async def _contar(app, passos: int = 14, intervalo: float = 0.045) -> None:
    st = _estado(app)
    try:
        await asyncio.sleep(0.06)
        for _ in range(TENTATIVAS):
            with st["trava"]:
                prontos = [k for k in st["contadores"] if _montado(k["t"])]
            if prontos:
                break
            await asyncio.sleep(0.05)
        with st["trava"]:
            todos, st["contadores"] = st["contadores"], []
        grupo = [k for k in todos if _montado(k["t"])]
        for k in todos:
            if k not in grupo:
                k["t"].value = k["fim"]  # não chegou na tela: já fica com o valor certo
        for i in range(1, passos + 1):
            p = 1 - (1 - i / passos) ** 3  # começa rápido e desacelera no fim
            for k in grupo:
                k["t"].value = k["fim"] if i == passos else k["fmt"](k["alvo"] * p)
            try:
                app.page.update(*[k["t"] for k in grupo])
            except Exception:  # noqa: BLE001
                break
            await asyncio.sleep(intervalo)
    finally:
        with st["trava"]:
            st["contando"] = False
            sobrou = bool(st["contadores"])
        if sobrou:
            _agendar_contagem(app)


# ---------------------------------------------------------------------- cartão que levanta (computador)

def realce(app, caixa: ft.Container, escala: float = 1.012, sombra: bool = True, fundo: str | None = None) -> ft.Container:
    """No computador, quando o mouse passa: o cartão clicável sobe um pouquinho e ganha sombra;
    com `fundo`, a linha de uma lista só ganha um fundo suave (sem crescer)."""
    if getattr(app, "celular", False) or not ligado(app) or not isinstance(caixa, ft.Container):
        return caixa
    if fundo:
        escala, sombra = 1.0, False
    caixa.animate_scale = ft.Animation(170, SUAVE)
    caixa.animate = ft.Animation(170, SUAVE)
    original = caixa.shadow
    fundo_original = caixa.bgcolor
    anterior = caixa.on_hover

    def passar(e):
        dentro = str(e.data).lower() in ("true", "1")
        if escala != 1.0:
            caixa.scale = escala if dentro else 1
        if fundo:
            caixa.bgcolor = fundo if dentro else fundo_original
        if sombra:
            caixa.shadow = ft.BoxShadow(blur_radius=22, spread_radius=-4, color="#26000000", offset=ft.Offset(0, 8)) if dentro else original
        try:
            caixa.update()
        except Exception:  # noqa: BLE001
            pass
        if anterior:
            anterior(e)

    caixa.on_hover = passar
    return caixa


# ---------------------------------------------------------------------- reações (certo / errado)

async def pulsar(app, ctrl: ft.Control, escala: float = 1.025) -> None:
    """Pulinho de "acertou": cresce um tico e volta."""
    if not ligado(app) or not _montado(ctrl):
        return
    ctrl.animate_scale = ft.Animation(150, ELASTICA)
    ctrl.scale = escala
    ctrl.update()
    await asyncio.sleep(0.15)
    ctrl.scale = 1
    try:
        ctrl.update()
    except Exception:  # noqa: BLE001
        pass


async def tremer(app, ctrl: ft.Control, forca: float = 0.012) -> None:
    """Balançada de "não foi dessa vez" (como o campo de senha errada)."""
    if not ligado(app) or not _montado(ctrl):
        return
    ctrl.animate_offset = ft.Animation(70, ft.AnimationCurve.EASE_IN_OUT)
    for dx in (forca, -forca, forca * 0.6, -forca * 0.3, 0):
        ctrl.offset = ft.Offset(dx, 0)
        try:
            ctrl.update()
        except Exception:  # noqa: BLE001
            return
        await asyncio.sleep(0.07)


# ---------------------------------------------------------------------- esqueleto (carregando)

def esqueleto(app, c: dict, linhas: int = 4, altura: int = 54) -> ft.Control:
    """No lugar do "Carregando…": a forma da lista em cinza, pulsando de leve até os dados chegarem.
    O pulso é uma troca de opacidade a cada 0,8 s (o Flutter faz a transição); para sozinho quando sai da tela."""
    blocos = []
    for i in range(linhas):
        blocos.append(
            ft.Row(
                [
                    ft.Container(width=34, height=34, border_radius=17, bgcolor=c["sup2"]),
                    ft.Column(
                        [ft.Container(height=12, width=180 + 40 * (i % 3), border_radius=6, bgcolor=c["sup2"]),
                         ft.Container(height=10, width=120 + 30 * ((i + 1) % 3), border_radius=5, bgcolor=c["sup2"])],
                        spacing=8,
                    ),
                ],
                spacing=14,
                height=altura,
            )
        )
    caixa = ft.Container(ft.Column(blocos, spacing=6), padding=12, opacity=1, animate_opacity=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT))
    if not ligado(app):
        return caixa

    async def pulsar_sempre():
        for _ in range(TENTATIVAS):
            if _montado(caixa):
                break
            await asyncio.sleep(0.05)
        claro = False
        while _montado(caixa):
            caixa.opacity = 0.45 if not claro else 1
            claro = not claro
            try:
                caixa.update()
            except Exception:  # noqa: BLE001
                return
            await asyncio.sleep(0.8)

    try:
        app.page.run_task(pulsar_sempre)
    except Exception:  # noqa: BLE001
        pass
    return caixa


# ---------------------------------------------------------------------- confete

CORES_CONFETE = ["#2340A8", "#F5C451", "#3FCB8B", "#EF6B5E", "#8B5CF6", "#5B7CFA"]


def confete(app, largura: float, altura: float = 420, quantidade: int = 46) -> ft.Control | None:
    """Camada de papel picado que cai e some (para pôr num Stack por cima do resultado).
    São 3 atualizações no total: o Flutter anima a queda, o giro e o sumiço de todos os pedaços."""
    if not ligado(app):
        return None
    rnd = random.Random()
    pedacos = []
    for i in range(quantidade):
        w, h = rnd.choice([(8, 14), (10, 10), (6, 16), (9, 12)])
        x0 = largura / 2 + rnd.uniform(-60, 60)
        pedacos.append(
            ft.Container(
                width=w,
                height=h,
                bgcolor=rnd.choice(CORES_CONFETE),
                border_radius=2 if w != h else w,
                left=x0,
                top=-20,
                rotate=ft.Rotate(0),
                opacity=1,
                animate_position=ft.Animation(rnd.randint(1100, 1700), ft.AnimationCurve.EASE_OUT_QUART),
                animate_rotation=ft.Animation(1600, SAIDA),
                animate_opacity=ft.Animation(700, SAIDA),
                data=(rnd.uniform(-largura * 0.48, largura * 0.48), rnd.uniform(altura * 0.35, altura), rnd.uniform(-6, 6)),
            )
        )
    camada = ft.Stack(pedacos, width=largura, height=altura)

    async def soltar():
        for _ in range(TENTATIVAS):
            if _montado(camada):
                break
            await asyncio.sleep(0.05)
        else:
            return
        await asyncio.sleep(0.05)
        for p in pedacos:
            dx, y, giro = p.data
            p.left = max(0, min(largura - 10, largura / 2 + dx))
            p.top = y
            p.rotate = ft.Rotate(giro * math.pi)
        try:
            camada.update()
            await asyncio.sleep(1.2)
            for p in pedacos:
                p.opacity = 0
            camada.update()
            await asyncio.sleep(0.8)
            camada.visible = False
            camada.update()
        except Exception:  # noqa: BLE001
            pass

    try:
        app.page.run_task(soltar)
    except Exception:  # noqa: BLE001
        return None
    return camada
