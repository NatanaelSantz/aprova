"""Faz o Python confiar nos certificados do próprio sistema (Windows, macOS, Linux).

Por que existe: o Python não usa o verificador do Windows. Num computador novo, o Windows
ainda não baixou alguns certificados raiz (ele só baixa quando um programa dele precisa).
Também há antivírus e redes de escola ou empresa que inspecionam o HTTPS com um
certificado próprio. Nesses casos o navegador funciona, mas o Python falha com
"CERTIFICATE_VERIFY_FAILED" (por exemplo, quando o Flet baixa a janela do app do GitHub
na primeira vez).

A solução é o truststore: ele passa a verificação para o sistema, igual ao navegador.
Sem o truststore (instalação antiga), usa de reserva a lista de certificados do certifi.
Pode chamar mais de uma vez; não desliga nenhuma verificação.
"""

from __future__ import annotations

import os

_feito = ""


def confiar_no_sistema() -> str:
    """Liga a verificação pelo sistema. Devolve "truststore", "certifi" ou "" (nada mudou)."""
    global _feito
    if _feito:
        return _feito
    try:
        import truststore

        truststore.inject_into_ssl()
        _feito = "truststore"
        return _feito
    except Exception:  # noqa: BLE001 - sem truststore ou Python antigo: tenta a reserva
        pass
    try:
        import certifi

        if not os.environ.get("SSL_CERT_FILE"):
            os.environ["SSL_CERT_FILE"] = certifi.where()
        _feito = "certifi"
    except Exception:  # noqa: BLE001
        _feito = ""
    return _feito


def explicar_erro(detalhe: str) -> str:
    """Troca os erros de rede mais comuns da primeira abertura por uma frase que dá para entender."""
    d = detalhe or ""
    if "CERTIFICATE_VERIFY_FAILED" in d or "certificate verify failed" in d.lower():
        return (
            "O Windows deste computador não confirmou o certificado de segurança do GitHub, de onde o Aprova baixa "
            "a janela do app na primeira vez. Isso costuma acontecer com antivírus que inspecionam a internet ou em "
            "redes de escola e empresa. Baixe o Aprova de novo pelo site (a versão nova já resolve isso) e abra o "
            "'Abrir Aprova.bat'. Se continuar, tente em outra rede (por exemplo, o roteador do celular)."
        )
    if "URLError" in d or "getaddrinfo" in d or "timed out" in d.lower() or "Connection" in d:
        return (
            "Na primeira vez, o Aprova baixa a janela do app do GitHub (uns 30 MB) e não conseguiu. Confira a internet "
            "e abra de novo. Depois disso ele abre sem precisar baixar."
        )
    return ""
