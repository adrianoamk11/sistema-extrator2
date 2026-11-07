"""Motor Fiscal V2 (isolado). Sem alterar o webhook atualmente em produção.

Etapa 1: auditar pagamentos e notas somente por GET. Não há endpoints POST
nem autorização para criar NFS-e. A ativação deve ocorrer após homologação.
"""
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests


MARCADOR_NFSE = "|NFSE|"
PAGAMENTO_RECEBIDO = frozenset({"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"})
ESTADOS_NOTA_CONCLUIDA = frozenset({"AUTHORIZED"})


class FalhaConciliacao(RuntimeError):
    """Não classifique como emitida uma operação sem prova externa suficiente."""


@dataclass(frozen=True)
class ResultadoFiscal:
    payment_id: str
    payment_status: str
    nota_solicitada: bool
    situacao: str
    invoice_id: Optional[str] = None
    invoice_status: Optional[str] = None
    detalhe: str = ""

    def as_dict(self):
        return {
            "payment_id": self.payment_id,
            "payment_status": self.payment_status,
            "nota_solicitada": self.nota_solicitada,
            "situacao": self.situacao,
            "invoice_id": self.invoice_id,
            "invoice_status": self.invoice_status,
            "detalhe": self.detalhe,
        }


class ConsultaFiscal:
    """Cliente Asaas limitado a leitura de cobrança e notas por identificador."""

    def __init__(self, api_key, base_url="https://api.asaas.com/v3", session=None):
        if not api_key:
            raise ValueError("Chave Asaas ausente")
        base = base_url.rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("API Asaas deve utilizar HTTPS")
        self.api_key = api_key
        self.base_url = base
        self.session = session if session is not None else requests.Session()

    def _get(self, path, params=None):
        r = self.session.get(
            self.base_url + path,
            headers={"access_token": self.api_key, "Accept": "application/json"},
            params=params,
            timeout=15,
            allow_redirects=False,
        )
        r.raise_for_status()
        if not 200 <= r.status_code < 300:
            raise FalhaConciliacao("Resposta HTTP inesperada do Asaas")
        dados = r.json()
        if not isinstance(dados, dict):
            raise FalhaConciliacao("Resposta Asaas não é um objeto JSON")
        return dados

    def pagamento(self, payment_id):
        if not isinstance(payment_id, str) or not re.fullmatch(r"pay_[a-zA-Z0-9]+", payment_id):
            raise ValueError("ID de cobrança inválido")
        dados = self._get("/payments/" + payment_id)
        if dados.get("id") != payment_id:
            raise FalhaConciliacao("Asaas retornou outra cobrança")
        return dados

    def notas(self, payment_id):
        # Paginação completa: ausência de notas não pode ser presumida da 1ª página.
        notas = []
        offset = 0
        while True:
            dados = self._get(
                "/invoices", params={"payment": payment_id, "limit": 100, "offset": offset}
            )
            lote = dados.get("data")
            if not isinstance(lote, list):
                raise FalhaConciliacao("Lista de notas inválida")
            for nota in lote:
                if not isinstance(nota, dict) or nota.get("payment") != payment_id:
                    raise FalhaConciliacao("Nota sem vínculo confirmado com a cobrança")
                notas.append(nota)
            if not dados.get("hasMore"):
                return notas
            if not lote or len(notas) > 10000:
                raise FalhaConciliacao("Paginação incompleta de notas fiscais")
            offset += len(lote)


def classificar_pagamento(pagamento, notas):
    payment_id = pagamento["id"]
    referencia = pagamento.get("externalReference")
    referencia = referencia if isinstance(referencia, str) else ""
    solicitada = MARCADOR_NFSE in referencia
    status_pagamento = str(pagamento.get("status") or "DESCONHECIDO").upper()

    if notas:
        if len(notas) > 1:
            return ResultadoFiscal(payment_id, status_pagamento, solicitada,
                                   "REVISAR_DUPLICIDADE", detalhe="Mais de uma NFS-e vinculada")
        nota = notas[0]
        status_nota = str(nota.get("status") or "DESCONHECIDO").upper()
        invoice_id = str(nota.get("id") or "") or None
        if status_nota in ESTADOS_NOTA_CONCLUIDA:
            situacao = "REGISTRADA_NO_ASAAS"
        elif status_nota == "SCHEDULED":
            situacao = "AGENDADA_NO_ASAAS"
        elif status_nota == "SYNCHRONIZED":
            situacao = "AGUARDANDO_AUTORIZACAO"
        elif status_nota in ("ERROR", "CANCELED", "CANCELLED"):
            situacao = "ERRO_OU_CANCELAMENTO"
        else:
            situacao = "ANALISAR_STATUS"
        return ResultadoFiscal(payment_id, status_pagamento, solicitada, situacao,
                               invoice_id=invoice_id, invoice_status=status_nota)

    if not solicitada:
        return ResultadoFiscal(payment_id, status_pagamento, False, "NAO_SOLICITADA")
    if status_pagamento not in PAGAMENTO_RECEBIDO:
        return ResultadoFiscal(payment_id, status_pagamento, True, "AGUARDANDO_PAGAMENTO")
    return ResultadoFiscal(
        payment_id, status_pagamento, True, "PAGA_SEM_NOTA",
        detalhe="Verificar fila de webhooks e rejeições; não solicitar outra nota automaticamente",
    )


def conciliar(client, payment_id):
    """GET-only: nenhuma cobrança, nota ou webhook é criado/retransmitido."""
    pagamento = client.pagamento(payment_id)
    notas = client.notas(payment_id)
    return classificar_pagamento(pagamento, notas)


def configuracao_v2():
    """Flag desligada por padrão, sem permitir ativação implícita via importação."""
    return {
        "modo": "SOMENTE_LEITURA",
        "emissao_automatica_ativa": False,
        "banco_legado_preservado": True,
        "requer_homologacao_fiscal": True,
    }
