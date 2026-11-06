import os
import sqlite3
from contextlib import closing
from datetime import datetime
from hmac import compare_digest
from zoneinfo import ZoneInfo

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = os.environ.get("ASAAS_BASE_URL", "https://api.asaas.com/v3").rstrip("/")
WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN")

# Códigos conferidos no cadastro de serviço do Asaas (Portal Nacional).
# Código de tributação nacional 170801 e NBS 1.1110.00.00 constam
# no cadastro; a API de agendamento utiliza municipalServiceCode.
# A alíquota ISS continua obrigatória por configuração, até validação fiscal.
NFSE_MUNICIPAL_SERVICE_CODE = os.environ.get("NFSE_MUNICIPAL_SERVICE_CODE", "").strip()
NFSE_MUNICIPAL_SERVICE_NAME = os.environ.get("NFSE_MUNICIPAL_SERVICE_NAME", "Franquia (franchising)").strip()
NFSE_ISS_PERCENT = os.environ.get("NFSE_ISS_PERCENT", "").strip()
NFSE_DB_PATH = os.environ.get("NFSE_DB_PATH", "").strip()
FUSO_FISCAL = ZoneInfo("America/Sao_Paulo")


def cabecalhos_asaas():
    return {"access_token": ASAAS_API_KEY, "Content-Type": "application/json"}


def configuracao_fiscal():
    if not all((NFSE_MUNICIPAL_SERVICE_CODE, NFSE_MUNICIPAL_SERVICE_NAME, NFSE_ISS_PERCENT)):
        raise ValueError("Configuracao fiscal de NFS-e pendente de validacao")
    if NFSE_MUNICIPAL_SERVICE_CODE == "06522":
        raise ValueError("Codigo municipal local nao corresponde ao cadastro esperado no Portal Nacional")
    try:
        iss = float(NFSE_ISS_PERCENT.replace(",", "."))
    except ValueError as exc:
        raise ValueError("Percentual de ISS invalido") from exc
    if not (2 <= iss <= 5):
        raise ValueError("Percentual de ISS fora do intervalo")
    return iss


def notas_do_pagamento(payment_id):
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/invoices",
        headers=cabecalhos_asaas(),
        params={"payment": payment_id, "limit": 100},
        timeout=10,
    )
    resposta.raise_for_status()
    corpo = resposta.json()
    if not isinstance(corpo, dict) or not isinstance(corpo.get("data"), list):
        raise RuntimeError("Resposta inesperada ao consultar notas fiscais")
    notas = corpo["data"]
    # Qualquer nota vinculada exige conciliação antes de uma nova emissão.
    if notas:
        if any(
            not isinstance(nota, dict) or nota.get("payment") != payment_id
            for nota in notas
        ):
            raise RuntimeError("Consulta retornou notas de outra cobrança")
        return notas
    if corpo.get("hasMore") is not False or corpo.get("totalCount") != 0:
        raise RuntimeError("Não foi possível confirmar ausência de notas fiscais")
    return []


def reservar_emissao(payment_id):
    """Confirma a reserva em disco antes de enviar uma única tentativa ao Asaas."""
    if not os.path.isabs(NFSE_DB_PATH):
        raise ValueError("Caminho absoluto para o banco de NFS-e obrigatório")
    with closing(sqlite3.connect(NFSE_DB_PATH, timeout=3)) as conexao, conexao:
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS nfse_tentativas "
            "(payment_id TEXT PRIMARY KEY, criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor = conexao.execute(
            "INSERT INTO nfse_tentativas (payment_id) VALUES (?) "
            "ON CONFLICT(payment_id) DO NOTHING",
            (payment_id,),
        )
        return cursor.rowcount == 1


@app.get("/")
def inicio():
    return "Webhook Lider funcionando", 200


@app.post("/webhook/asaas")
def webhook_asaas():
    token_recebido = request.headers.get("asaas-access-token")
    if not WEBHOOK_TOKEN or not compare_digest(
        (token_recebido or "").encode(), WEBHOOK_TOKEN.encode()
    ):
        return jsonify({"erro": "nao autorizado"}), 401

    evento = request.get_json(silent=True)
    if not isinstance(evento, dict):
        return jsonify({"erro": "evento invalido"}), 400
    if evento.get("event") != "PAYMENT_RECEIVED":
        return jsonify({"ok": True, "ignorado": True}), 200

    pagamento = evento.get("payment")
    if not isinstance(pagamento, dict):
        return jsonify({"erro": "pagamento invalido"}), 400
    payment_id = pagamento.get("id")
    referencia = pagamento.get("externalReference") or ""

    if not isinstance(referencia, str) or "|NFSE|" not in referencia:
        return jsonify({"ok": True, "nota": "nao solicitada"}), 200
    if not isinstance(payment_id, str) or not payment_id.strip():
        return jsonify({"erro": "payment id ausente"}), 400

    valor = pagamento.get("value")
    if (
        isinstance(valor, bool)
        or not isinstance(valor, (int, float))
        or not (0 < valor < float("inf"))
    ):
        return jsonify({"erro": "valor do pagamento invalido"}), 400

    # Falha fechada: sem configuracao validada, nao emite nota incorreta.
    try:
        iss = configuracao_fiscal()
    except ValueError as exc:
        app.logger.warning("NFS-e nao criada: %s", exc)
        return jsonify({"ok": False, "nota": "configuracao fiscal pendente"}), 503

    if not ASAAS_API_KEY:
        return jsonify({"ok": False, "nota": "integracao nao configurada"}), 503

    try:
        existentes = notas_do_pagamento(payment_id)
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        app.logger.error("Falha na verificacao de notas existentes: %s", type(exc).__name__)
        return jsonify({"ok": False, "nota": "consulta de duplicidade indisponivel"}), 503

    if existentes:
        return jsonify({"ok": True, "nota": "ja existe nota para este pagamento"}), 200

    try:
        reservada = reservar_emissao(payment_id)
    except (ValueError, sqlite3.Error) as exc:
        app.logger.error("Falha na reserva de NFS-e: %s", type(exc).__name__)
        return jsonify({"ok": False, "nota": "reserva indisponivel"}), 503
    if not reservada:
        app.logger.warning("NFS-e aguardando conciliacao: %s", payment_id)
        return jsonify({"ok": False, "nota": "tentativa anterior pendente de conciliacao"}), 503

    payload_nota = {
        "payment": payment_id,
        "serviceDescription": "Royalties",
        "observations": "Royalties de franquia",
        "externalReference": f"lider-nfse-{payment_id}",
        "updatePayment": False,
        "value": valor,
        "deductions": 0,
        "effectiveDate": datetime.now(FUSO_FISCAL).date().isoformat(),
        "municipalServiceCode": NFSE_MUNICIPAL_SERVICE_CODE,
        "municipalServiceName": NFSE_MUNICIPAL_SERVICE_NAME,
        "taxes": {"retainIss": False, "iss": iss},
    }

    try:
        resposta = requests.post(
            f"{ASAAS_BASE_URL}/invoices",
            headers=cabecalhos_asaas(),
            json=payload_nota,
            timeout=10,
            allow_redirects=False,
        )
    except requests.RequestException:
        app.logger.error("Falha de rede na solicitacao de NFS-e")
        return jsonify({"ok": False, "nota": "falha de comunicacao"}), 503

    if not 200 <= resposta.status_code < 300:
        app.logger.error("Asaas recusou a criacao da NFS-e: HTTP %s", resposta.status_code)
        return jsonify({"ok": False, "nota": "falha na criacao", "status_asaas": resposta.status_code}), 503

    try:
        dados = resposta.json()
    except ValueError:
        dados = None
    if (
        not isinstance(dados, dict)
        or not isinstance(dados.get("id"), str)
        or not dados["id"].strip()
        or dados.get("status") not in ("SCHEDULED", "SYNCHRONIZED", "AUTHORIZED")
    ):
        app.logger.error("Resultado de NFS-e exige conciliacao: %s", payment_id)
        return jsonify({"ok": False, "nota": "resposta exige conciliacao"}), 503
    return jsonify({"ok": True, "nota": {"id": dados["id"], "status": dados["status"]}}), 200
