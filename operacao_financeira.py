"""Proteção local contra envio simultâneo e repetição após resultado incerto.

Não há mudança na API Asaas nem em chaves/webhooks. O bloqueio é por
processo Streamlit; entre instâncias/reinícios a conciliação definitiva
depende dos identificadores externalReference e do provedor.
"""
import threading
from contextlib import contextmanager

_LOCK_GUARD = threading.Lock()
_LOCKS = {}
_INCONCLUSIVAS = set()


def _chave(chave):
    return str(chave)


@contextmanager
def operacao_financeira_unica(chave):
    """Serializa a consulta de duplicidade e o POST para a mesma operação."""
    chave = _chave(chave)
    with _LOCK_GUARD:
        bloqueio = _LOCKS.setdefault(chave, threading.Lock())
    with bloqueio:
        with _LOCK_GUARD:
            if chave in _INCONCLUSIVAS:
                raise RuntimeError(
                    "Uma tentativa anterior teve resposta incerta. "
                    "Confira a operação diretamente no Asaas antes de "
                    "prosseguir. Nenhuma segunda cobrança foi enviada."
                )
        yield


def marcar_resultado_inconclusivo(chave):
    """Falha fechada até conciliação manual: não executar outro POST na sessão."""
    with _LOCK_GUARD:
        _INCONCLUSIVAS.add(_chave(chave))


def resposta_inconclusiva(status_code):
    try:
        return int(status_code) >= 500 or int(status_code) in (408, 429)
    except (ValueError, TypeError):
        return True
