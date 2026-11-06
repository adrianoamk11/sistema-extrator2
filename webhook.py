import os
import requests
from datetime import date
from flask import Flask, request, jsonify

app = Flask(__name__)

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = os.environ.get("ASAAS_BASE_URL", "https://api.asaas.com/v3").rstrip("/")
WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN")

# Estes campos precisam ser validados no Asaas e com a contabilidade.
# Nunca usar os antigos "06522" / "17.07" como valores implícitos.
NFSE_MUNICIPAL_SERVICE_CODE = os.environ.get("NFSE_MUNICIPAL_SERVICE_CODE", "").strip()
NFSE_MUNICIPAL_SERVICE_NAME = os.environ.get("NFSE_MUNICIPAL_SERVICE_NAME", "").strip()
NFSE_ISS_PERCENT = os.environ.get("NFSE_ISS_PERCENT", "").strip()


def cabecalhos_asaas():
    return {"access_token": ASAAS_API_KEY, "Content-Type": "application/json"}


def configuracao_fiscal():
    if not all((NFSE_MUNICIPAL_SERVICE_CODE, NFSE_MUNICIPAL_SERVICE_NAME, NFSE_ISS_PERCENT)):
        raise ValueError("Configuracao fiscal de NFS-e pendente de validacao")
    try:
        iss = float(NFSE_ISS_PERCENT.replace(",", "."))
    except ValueError as exc:
        raise ValueError("Percentual de ISS invalido") from exc
    if not (0 <= iss <= 100):
        raise ValueError("Percentual de ISS fora do intervalo")
    return iss


def notas_do_pagamento(payment_id):
    """Verifica notas existentes antes de criar outra.

    Em caso de erro ou resposta inesperada, interrompe a emissao para
    evitar uma segunda nota. A paginacao e o filtro devem ser validados
    em ambiente de homologacao antes da ativacao em producao.
    """
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/invoices",
        headers=cabecalhos_asaas(),
        params={"payment": payment_id, "limit": 100, "offset": 0},
        timeout=30,
    )
    resposta.raise_for_status()
    corpo = resposta.json()
    if not isinstance(corpo, dict) or not isinstance(corpo.get("data"), list):
        raise RuntimeError("Resposta inesperada ao consultar notas fiscais")
    if corpo.get("hasMore"):
        raise RuntimeError("Consulta de notas requer paginacao; emissao interrompida")
    # Não assumir que a API respeitou o filtro: validar o payment de cada nota.
    return [nota for nota in corpo["data"] if nota.get("payment") == payment_id]


@app.get("/")
def inicio():
    return "Webhook Lider funcionando", 200


@app.post("/webhook/asaas")
def webhook_asaas():
    token_recebido = request.headers.get("asaas-access-token")
    if not WEBHOOK_TOKEN or token_recebido != WEBHOOK_TOKEN:
        return jsonify({"erro": "nao autorizado"}), 401

    evento = request.get_json(silent=True) or {}
    if evento.get("event") != "PAYMENT_RECEIVED":
        return jsonify({"ok": True, "ignorado": True}), 200

    pagamento = evento.get("payment") or {}
    payment_id = pagamento.get("id")
    referencia = pagamento.get("externalReference") or ""

    if "|NFSE|" not in referencia:
        return jsonify({"ok": True, "nota": "nao solicitada"}), 200
    if not payment_id:
        return jsonify({"erro": "payment id ausente"}), 400

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

    valor = pagamento.get("value")
    if not isinstance(valor, (int, float)) or valor <= 0:
        return jsonify({"erro": "valor do pagamento invalido"}), 400

    payload_nota = {
        "payment": payment_id,
        "serviceDescription": "Royalties",
        "value": valor,
        "deductions": 0,
        "effectiveDate": date.today().isoformat(),
        "municipalServiceCode": NFSE_MUNICIPAL_SERVICE_CODE,
        "municipalServiceName": NFSE_MUNICIPAL_SERVICE_NAME,
        "taxes": {"retainIss": False, "iss": iss},
    }

    try:
        resposta = requests.post(
            f"{ASAAS_BASE_URL}/invoices",
            headers=cabecalhos_asaas(),
            json=payload_nota,
            timeout=30,
        )
    except requests.RequestException:
        app.logger.error("Falha de rede na solicitacao de NFS-e")
        return jsonify({"ok": False, "nota": "falha de comunicacao"}), 503

    if not resposta.ok:
        app.logger.error("Asaas recusou a criacao da NFS-e: HTTP %s", resposta.status_code)
        return jsonify({"ok": False, "nota": "falha na criacao", "status_asaas": resposta.status_code}), 503

    dados = resposta.json()
    return jsonify({"ok": True, "nota": {"id": dados.get("id"), "status": dados.get("status")}}), 200
