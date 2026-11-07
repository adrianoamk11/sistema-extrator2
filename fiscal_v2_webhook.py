"""Entrada de eventos Asaas para Fiscal V2, isolada do endpoint de produção.

Esta aplicação não é iniciada pelo Render atualmente e não emite NFS-e.
Recebe e persiste notificações autenticadas, respondendo 200 após commit.
"""
import os
import re
import sqlite3
from contextlib import closing
from hmac import compare_digest

from flask import Flask, jsonify, request

app_v2 = Flask(__name__)

EVENTOS_SUPORTADOS = frozenset({
    "PAYMENT_RECEIVED", "PAYMENT_CONFIRMED",
    "INVOICE_AUTHORIZED", "INVOICE_ERROR",
    "INVOICE_CANCELED", "INVOICE_SYNCHRONIZED"
})


def registrar_evento(db_path, evento):
    """Idempotência pelo ID do evento; retém metadados mínimos sem dados pessoais."""
    if not os.path.isabs(db_path):
        raise ValueError("Caminho absoluto do banco obrigatório")
    identificador = evento.get("id")
    tipo = evento.get("event")
    if not isinstance(identificador, str) or not re.fullmatch(r"evt_[\w-]{1,128}", identificador):
        raise ValueError("ID do evento inválido")
    if not isinstance(tipo, str) or len(tipo) > 80:
        raise ValueError("Tipo de evento inválido")

    origem = evento.get("payment") if tipo.startswith("PAYMENT_") else evento.get("invoice")
    if not isinstance(origem, dict):
        raise ValueError("Objeto do evento inválido")
    origem_id = origem.get("id")
    if not isinstance(origem_id, str) or not re.fullmatch(r"(pay|inv)_[\w-]{1,128}", origem_id):
        raise ValueError("ID de origem inválido")

    with closing(sqlite3.connect(db_path, timeout=5)) as conexao:
        with conexao:
            conexao.execute(
                "CREATE TABLE IF NOT EXISTS fiscal_v2_eventos ("
                "event_id TEXT PRIMARY KEY, evento TEXT NOT NULL, origem_id TEXT NOT NULL, "
                "situacao TEXT NOT NULL DEFAULT 'PENDENTE', "
                "recebido_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            novo = conexao.execute(
                "INSERT INTO fiscal_v2_eventos(event_id, evento, origem_id) VALUES (?,?,?) "
                "ON CONFLICT(event_id) DO NOTHING",
                (identificador, tipo, origem_id),
            ).rowcount == 1
    return novo


def receber_evento(evento, token_recebido, token_configurado, db_path):
    if not token_configurado or not compare_digest(
        str(token_recebido or "").encode(), str(token_configurado).encode()
    ):
        return {"erro": "não autorizado"}, 401
    if not isinstance(evento, dict):
        return {"erro": "JSON inválido"}, 400
    if evento.get("event") not in EVENTOS_SUPORTADOS:
        # Evento com novo formato não deve travar a fila por indisponibilidade fiscal.
        return {"ok": True, "ignorado": True}, 200
    try:
        novo = registrar_evento(db_path, evento)
    except (sqlite3.Error, ValueError, OSError):
        return {"erro": "persistência indisponível"}, 503
    return {"ok": True, "registrado": novo}, 200


@app_v2.post("/webhook/asaas/v2")
def webhook_fiscal_v2():
    # Permanece desativado por padrão, mesmo após importação ou deploy.
    if os.environ.get("FISCAL_V2_RECEPCAO_SANDBOX") != "SIM":
        return jsonify({"erro": "não habilitado"}), 404
    resposta, status = receber_evento(
        request.get_json(silent=True),
        request.headers.get("asaas-access-token"),
        os.environ.get("FISCAL_V2_WEBHOOK_TOKEN"),
        os.environ.get("FISCAL_V2_EVENT_DB", ""),
    )
    return jsonify(resposta), status
