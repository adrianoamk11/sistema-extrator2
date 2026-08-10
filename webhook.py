import os
import requests
from datetime import date
from flask import Flask, request, jsonify

app = Flask(__name__)

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = os.environ.get(
    "ASAAS_BASE_URL",
    "https://api.asaas.com/v3"
).rstrip("/")

WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN")


def cabecalhos_asaas():
    return {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json",
    }


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

    # Só emite nota para cobranças marcadas pelo sistema.
    if "|NFSE|" not in referencia:
        return jsonify({"ok": True, "nota": "nao solicitada"}), 200

    if not payment_id:
        return jsonify({"erro": "payment id ausente"}), 400
        
    payload_nota = {
        "payment": payment_id,
        "serviceDescription": "Royalties",
        "observations": "Royalties - Lider Franquia",
        "value": pagamento.get("value"),
        "effectiveDate": date.today().isoformat(),
    }

    print("PAYLOAD NOTA:", payload_nota, flush=True)

    resposta = requests.post(
        f"{ASAAS_BASE_URL}/invoices",
        headers=cabecalhos_asaas(),
        json=payload_nota,
        timeout=30,
    )

    if not resposta.ok:
        print("ERRO AO CRIAR NOTA FISCAL NO ASAAS")
        print("STATUS:", resposta.status_code)
        print("RESPOSTA:", resposta.text)

        return jsonify({
            "ok": True,
            "nota": "falhou",
            "status_asaas": resposta.status_code,
            "detalhe": resposta.text,
        }), 200

    return jsonify({
        "ok": True,
        "nota": resposta.json(),
    }), 200
