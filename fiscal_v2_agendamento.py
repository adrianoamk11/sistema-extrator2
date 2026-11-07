"""Agendamento NFS-e V2 — operação somente em HOMOLOGAÇÃO do Asaas.

Não ativar em produção antes de validar dados fiscais e migração do webhook.
A reserva local é permanente para resultados ambíguos; nenhuma repetição
automática do POST é permitida.
"""
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import os
import re
import sqlite3

import requests

from fiscal_v2 import ConsultaFiscal, conciliar

SANDBOX_ASAAS = "https://api-sandbox.asaas.com/v3"


@dataclass(frozen=True)
class DadosNota:
    service_description: str
    observations: str
    municipal_service_code: str
    municipal_service_name: str
    taxes: dict
    effective_date: str

    def validar(self):
        if not all((
            self.service_description.strip(),
            self.observations.strip(),
            self.municipal_service_name.strip(),
            self.municipal_service_code.strip(),
        )):
            raise ValueError("Dados obrigatórios da NFS-e ausentes")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.effective_date):
            raise ValueError("Data de NFS-e inválida")
        date.fromisoformat(self.effective_date)
        if not isinstance(self.taxes, dict) or not isinstance(self.taxes.get("retainIss"), bool):
            raise ValueError("Valide os tributos com o responsável fiscal")
        if not isinstance(self.taxes.get("iss"), (int, float)):
            raise ValueError("ISS ainda não foi validado")
        return self


class ReservaFiscal:
    def __init__(self, db_path):
        if not os.path.isabs(str(db_path)):
            raise ValueError("Banco SQLite precisa ter caminho absoluto")
        self.db_path = str(db_path)

    def reservar(self, payment_id):
        """Reserva durável antes de uma chamada externa; nunca libera sozinha."""
        with closing(sqlite3.connect(self.db_path, timeout=5)) as conexao:
            with conexao:
                conexao.execute(
                    "CREATE TABLE IF NOT EXISTS fiscal_v2_tentativas ("
                    "payment_id TEXT PRIMARY KEY, "
                    "status TEXT NOT NULL, "
                    "invoice_id TEXT, "
                    "criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "atualizada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                )
                cursor = conexao.execute(
                    "INSERT INTO fiscal_v2_tentativas(payment_id, status) VALUES (?, 'RESERVADA') "
                    "ON CONFLICT(payment_id) DO NOTHING", (payment_id,)
                )
                return cursor.rowcount == 1

    def registrar_resultado(self, payment_id, status, invoice_id=None):
        if status not in ("AGENDADA", "RESPOSTA_AMBIGUA", "REJEITADA"):
            raise ValueError("Status inválido de agendamento")
        with closing(sqlite3.connect(self.db_path, timeout=5)) as conexao:
            with conexao:
                atualizado = conexao.execute(
                    "UPDATE fiscal_v2_tentativas "
                    "SET status=?, invoice_id=?, atualizada_em=CURRENT_TIMESTAMP "
                    "WHERE payment_id=? AND status IN ('RESERVADA', 'RESPOSTA_AMBIGUA')",
                    (status, invoice_id, payment_id)
                )
                if atualizado.rowcount != 1:
                    raise RuntimeError("Estado da reserva não pode ser alterado")

    def consultar(self, payment_id):
        with closing(sqlite3.connect(self.db_path, timeout=5)) as conexao:
            try:
                linha = conexao.execute(
                    "SELECT status, invoice_id FROM fiscal_v2_tentativas WHERE payment_id=?",
                    (payment_id,)
                ).fetchone()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc):
                    return None
                raise
        return {"status": linha[0], "invoice_id": linha[1]} if linha else None


def valor_nota(pagamento):
    try:
        valor = Decimal(str(pagamento.get("value")))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Valor de cobrança inválido") from exc
    if not valor.is_finite() or valor <= 0 or valor.as_tuple().exponent < -2:
        raise ValueError("Valor não elegível para NFS-e")
    return float(valor)


def preparar_nota(pagamento, dados):
    dados.validar()
    return {
        "payment": pagamento["id"],
        "serviceDescription": dados.service_description,
        "observations": dados.observations,
        "externalReference": "lider-fiscal-v2-" + pagamento["id"],
        "updatePayment": False,
        "value": valor_nota(pagamento),
        "deductions": 0,
        "effectiveDate": dados.effective_date,
        "municipalServiceCode": dados.municipal_service_code,
        "municipalServiceName": dados.municipal_service_name,
        "taxes": dados.taxes.copy(),
    }


def agendar_em_homologacao(client, reserva, payment_id, dados, autorizacao_explicita=False):
    """Uma única chamada POST em sandbox, após GET e reserva durável.

    Nunca executa no Asaas de produção. Resultado de rede incerto exige
    conciliação manual: não tentamos um segundo POST.
    """
    if not autorizacao_explicita:
        raise PermissionError("Agendamento não autorizado")
    if client.base_url != SANDBOX_ASAAS:
        raise PermissionError("Agendamento V2 bloqueado fora do sandbox do Asaas")
    if not isinstance(client, ConsultaFiscal):
        raise TypeError("Cliente fiscal inválido")
    estado = conciliar(client, payment_id)
    if estado.situacao != "PAGA_SEM_NOTA":
        raise RuntimeError("Cobrança não elegível; conciliar o status antes de prosseguir")
    pagamento = client.pagamento(payment_id)
    payload = preparar_nota(pagamento, dados)

    if not reserva.reservar(payment_id):
        raise RuntimeError("Tentativa anterior existente: reconciliação manual obrigatória")
    try:
        resposta = client.session.post(
            client.base_url + "/invoices",
            headers={"access_token": client.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=15,
            allow_redirects=False,
        )
    except requests.RequestException:
        # Reserva mantida mesmo em timeout, pois Asaas pode ter criado a nota.
        reserva.registrar_resultado(payment_id, "RESPOSTA_AMBIGUA")
        raise RuntimeError("Resultado da API incerto: consultar notas antes de qualquer ação")

    if not 200 <= resposta.status_code < 300:
        if 400 <= resposta.status_code < 500:
            reserva.registrar_resultado(payment_id, "REJEITADA")
        else:
            reserva.registrar_resultado(payment_id, "RESPOSTA_AMBIGUA")
        raise RuntimeError("Asaas não confirmou o agendamento; revisar a tentativa")

    try:
        corpo = resposta.json()
        invoice_id = corpo.get("id")
        status = corpo.get("status")
    except (ValueError, AttributeError):
        invoice_id = None
        status = None

    if not isinstance(invoice_id, str) or not invoice_id or status not in (
        "SCHEDULED", "SYNCHRONIZED", "AUTHORIZED"
    ):
        reserva.registrar_resultado(payment_id, "RESPOSTA_AMBIGUA")
        raise RuntimeError("Resposta de NFS-e ambígua; não repetir solicitação")

    reserva.registrar_resultado(payment_id, "AGENDADA", invoice_id)
    return {
        "payment_id": payment_id, "invoice_id": invoice_id,
        "status_asaas": status,
        "nota_emitida": status == "AUTHORIZED",
    }
