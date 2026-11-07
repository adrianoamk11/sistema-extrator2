import os
import re
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

# A conta emissora usa o Portal Nacional. O código enviado ao Asaas
# tem pontuação e só inclui complemento quando ele existe na NFS-e.
NFSE_MUNICIPAL_SERVICE_CODE = os.environ.get("NFSE_PORTAL_SERVICE_CODE", "").strip()
NFSE_NBS_CODE = os.environ.get("NFSE_NBS_CODE", "").strip()
NFSE_MUNICIPAL_SERVICE_NAME = os.environ.get("NFSE_MUNICIPAL_SERVICE_NAME", "Franquia (franchising)").strip()
NFSE_ISS_PERCENT = os.environ.get("NFSE_ISS_PERCENT", "").strip()
NFSE_DB_PATH = os.environ.get("NFSE_DB_PATH", "").strip()
FUSO_FISCAL = ZoneInfo("America/Sao_Paulo")


def cabecalhos_asaas():
    return {"access_token": ASAAS_API_KEY, "Content-Type": "application/json"}


def configuracao_fiscal():
    if not all((NFSE_MUNICIPAL_SERVICE_CODE, NFSE_MUNICIPAL_SERVICE_NAME, NFSE_ISS_PERCENT)):
        raise ValueError("Configuracao fiscal de NFS-e pendente de validacao")
    if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{2}(?:\.[0-9]{3})?", NFSE_MUNICIPAL_SERVICE_CODE):
        raise ValueError("Codigo de servico do Portal Nacional invalido")
    if not re.fullmatch(r"[0-9]{9}", NFSE_NBS_CODE):
        raise ValueError("Codigo NBS invalido")
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


def detalhes_erro_asaas(resposta):
    """Extrai erro de validação sem registrar payloads ou credenciais."""
    try:
        dados = resposta.json()
    except ValueError:
        return "resposta sem JSON de erro"

    if not isinstance(dados, dict) or not isinstance(dados.get("errors"), list):
        return "resposta sem lista de erros reconhecida"

    detalhes = []
    for erro in dados["errors"][:5]:
        if not isinstance(erro, dict):
            continue
        codigo = str(erro.get("code") or "sem_codigo")[:60]
        descricao = str(erro.get("description") or "sem_descricao")[:300]
        # Evita registrar caracteres de controle e valores de token completos.
        codigo = re.sub(r"[^\w.:-]", "_", codigo)
        descricao = re.sub(r"[\r\n\t]", " ", descricao)
        descricao = re.sub(r"(?i)(access[_ -]?token|api[_ -]?key|authorization)\s*[:=]\s*\S+", r"\1=[protegido]", descricao)
        detalhes.append(f"{codigo}: {descricao}")
    return " | ".join(detalhes) if detalhes else "lista de erros vazia"


def registrar_rejeicao_asaas(payment_id, status_http, detalhes):
    """Guarda erro definitivo em disco para conciliação, sem liberar reenvio automático."""
    if not os.path.isabs(NFSE_DB_PATH):
        raise ValueError("Caminho absoluto para o banco de NFS-e obrigatório")
    with closing(sqlite3.connect(NFSE_DB_PATH, timeout=3)) as conexao, conexao:
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS nfse_rejeicoes "
            "(payment_id TEXT PRIMARY KEY, status_http INTEGER NOT NULL, "
            "detalhes TEXT NOT NULL, registrada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        conexao.execute(
            "INSERT INTO nfse_rejeicoes (payment_id, status_http, detalhes) VALUES (?, ?, ?) "
            "ON CONFLICT(payment_id) DO UPDATE SET status_http=excluded.status_http, "
            "detalhes=excluded.detalhes, registrada_em=CURRENT_TIMESTAMP",
            (payment_id, status_http, detalhes),
        )


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
        # A tentativa anterior ja foi registrada em disco. Repetir POST /invoices
        # pode gerar NFS-e duplicada em caso de timeout ou resposta ambigua.
        # Acknowledge da entrega do webhook evita penalizar toda a fila Asaas;
        # a pendencia continua persistida para conciliacao manual.
        app.logger.warning("NFS-e aguardando conciliacao manual: %s", payment_id)
        return jsonify({"ok": True, "nota": "pendente de conciliacao manual"}), 200

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
        "taxes": {"retainIss": False, "iss": iss, "nbsCode": NFSE_NBS_CODE},
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
        # HTTP 4xx: pedido recusado. A reserva continua para impedir duplicatas,
        # e a mensagem de validação é registrada para conciliação manual.
        # HTTP 5xx: resultado pode ser incerto; não assumir que não houve criação.
        if 400 <= resposta.status_code < 500:
            detalhes = detalhes_erro_asaas(resposta)
            try:
                registrar_rejeicao_asaas(payment_id, resposta.status_code, detalhes)
            except (ValueError, sqlite3.Error):
                app.logger.error("Falha ao persistir rejeicao de NFS-e: %s", payment_id)
                return jsonify({"ok": False, "nota": "falha ao registrar rejeicao"}), 503
            app.logger.error(
                "Asaas recusou NFS-e da cobrança %s (HTTP %s): %s",
                payment_id, resposta.status_code, detalhes,
            )
        else:
            app.logger.error(
                "Resposta incerta na criacao de NFS-e da cobrança %s: HTTP %s",
                payment_id, resposta.status_code,
            )
        # Rejeicao definitiva foi persistida; nao adianta reenviar o mesmo
        # evento, que bloquearia a fila e nao corrigiria o dado fiscal.
        # Respostas 5xx permanecem incertas e sao tratadas com cautela.
        if 400 <= resposta.status_code < 500:
            return jsonify({"ok": True, "nota": "rejeitada pelo Asaas; conciliacao manual necessaria", "status_asaas": resposta.status_code}), 200
        return jsonify({"ok": False, "nota": "requer conciliacao", "status_asaas": resposta.status_code}), 503

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
