"""Conciliação fiscal somente leitura por ID de pagamento.
Não altera notas, cobranças, notificações ou reservas do webhook.
"""
import re


def _dados_resposta(resposta, acao):
    if not resposta.ok:
        raise RuntimeError(
            f"Asaas recusou {acao} (HTTP {resposta.status_code}). "
            "Confira o pagamento e a conta emissora."
        )
    try:
        dados = resposta.json()
    except ValueError as exc:
        raise RuntimeError(f"Resposta não legível ao {acao}.") from exc
    if not isinstance(dados, dict):
        raise RuntimeError(f"Resposta inesperada ao {acao}.")
    return dados


def consultar_nfse_por_pagamento(base_url, headers, payment_id, get):
    """Consulta uma cobrança e todas as notas vinculadas, sem POST nem PUT."""
    if not re.fullmatch(r"pay_[A-Za-z0-9]+", str(payment_id or "")):
        raise ValueError("Informe um ID de cobrança válido, iniciado por pay_.")
    base = base_url.rstrip("/")
    pagamento = _dados_resposta(
        get(
            base + "/payments/" + payment_id,
            headers=headers, timeout=20,
        ),
        "consultar a cobrança",
    )
    if pagamento.get("id") != payment_id:
        raise RuntimeError("A API retornou um pagamento diferente do solicitado.")
    referencia = str(pagamento.get("externalReference") or "")
    deve_emitir_nfse = "|NFSE|" in referencia
    notas = []
    offset = 0
    for _ in range(50):
        corpo = _dados_resposta(
            get(
                base + "/invoices",
                headers=headers,
                params={"payment": payment_id, "offset": offset, "limit": 100},
                timeout=20,
            ),
            "consultar as notas fiscais",
        )
        pagina = corpo.get("data")
        if not isinstance(pagina, list):
            raise RuntimeError("O Asaas não retornou lista válida de notas.")
        for item in pagina:
            if not isinstance(item, dict) or item.get("payment") != payment_id:
                raise RuntimeError("Nota fiscal divergente da cobrança consultada.")
            notas.append({
                "id": str(item.get("id") or ""),
                "status": str(item.get("status") or "Não informado"),
            })
        if not corpo.get("hasMore"):
            return {
                "payment_id": payment_id,
                "payment_status": str(pagamento.get("status") or ""),
                "fiscal_solicitada_pelo_extrator": deve_emitir_nfse,
                "notas": notas,
            }
        if not pagina:
            raise RuntimeError("Paginação de NFS-e inconclusiva.")
        offset += len(pagina)
    raise RuntimeError("Consulta de NFS-e excedeu limite seguro de páginas.")
