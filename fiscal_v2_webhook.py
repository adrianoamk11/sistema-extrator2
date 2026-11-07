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


def diagnostico_persistencia(db_path, diretorio_persistente="/var/data"):
    """Impede gravar eventos reais no disco efêmero da instância."""
    import pathlib
    try:
        raiz = pathlib.Path(diretorio_persistente).resolve(strict=True)
        banco = pathlib.Path(db_path).resolve(strict=False)
    except (OSError, TypeError, ValueError):
        return "BANCO_INVALIDO"
    if not banco.is_relative_to(raiz) or banco == raiz:
        return "FORA_DO_DISCO_PERSISTENTE"
    if not os.path.ismount(str(raiz)):
        return "DISCO_PERSISTENTE_NAO_MONTADO"
    if not os.access(str(raiz), os.W_OK):
        return "DISCO_SEM_ESCRITA"
    return "OK"


@app_v2.get("/fiscal-v2/health")
def health_fiscal_v2():
    # Sem revelar caminhos internos, credenciais, clientes ou informações fiscais.
    return jsonify({
        "servico": "Fiscal V2",
        "recepcao": "desativada" if os.environ.get("FISCAL_V2_RECEPCAO_SANDBOX") != "SIM"
                    else "configurada",
        "emissao_automatica": "desativada",
    }), 200


@app_v2.post("/webhook/asaas/v2")
def webhook_fiscal_v2():
    # Permanece desativado por padrão, mesmo após importação ou deploy.
    if os.environ.get("FISCAL_V2_RECEPCAO_SANDBOX") != "SIM":
        return jsonify({"erro": "não habilitado"}), 404
    if diagnostico_persistencia(os.environ.get("FISCAL_V2_EVENT_DB", "")) != "OK":
        # Nunca confirmar entregas de webhook sem armazenamento durável.
        return jsonify({"erro": "persistência fiscal não está pronta"}), 503
    resposta, status = receber_evento(
        request.get_json(silent=True),
        request.headers.get("asaas-access-token"),
        os.environ.get("FISCAL_V2_WEBHOOK_TOKEN"),
        os.environ.get("FISCAL_V2_EVENT_DB", ""),
    )
    return jsonify(resposta), status

def verificar_conexao_sandbox():
    """Somente GET; não registra chave, resposta da conta ou dados pessoais."""
    import requests

    chave = os.environ.get("ASAAS_SANDBOX_API_KEY", "").strip()
    if not chave:
        app_v2.logger.warning("Fiscal V2 Sandbox: chave não configurada.")
        return "CHAVE_AUSENTE"
    try:
        resposta = requests.get(
            "https://api-sandbox.asaas.com/v3/myAccount/status/",
            headers={
                "access_token": chave,
                "Accept": "application/json",
                "User-Agent": "LiderFiscalV2Sandbox/1.0",
            },
            timeout=12,
            allow_redirects=False,
        )
    except requests.RequestException as erro:
        app_v2.logger.warning(
            "Fiscal V2 Sandbox: consulta falhou (%s).",
            type(erro).__name__,
        )
        return "SEM_RESPOSTA"

    codigo = resposta.status_code
    if codigo == 200:
        app_v2.logger.warning("Fiscal V2 Sandbox: autenticação OK (HTTP 200).")
        return "CONECTADO"
    if codigo == 401:
        app_v2.logger.warning("Fiscal V2 Sandbox: autenticação recusada (HTTP 401).")
        return "NAO_AUTORIZADO"
    app_v2.logger.warning("Fiscal V2 Sandbox: resposta HTTP %s.", codigo)
    return "HTTP_" + str(codigo)


# Executa apenas quando configurada, ao iniciar o serviço de homologação.
# O endpoint de webhook continua desligado e a verificação não emite NFS-e.
if os.environ.get("FISCAL_V2_CONEXAO_CHECK") == "SIM":
    verificar_conexao_sandbox()

def verificar_prontidao_fiscal_sandbox():
    """Consulta configuração fiscal e acesso às notas; sem modificar a conta."""
    import requests

    chave = os.environ.get("ASAAS_SANDBOX_API_KEY", "").strip()
    if not chave:
        app_v2.logger.warning("Fiscal V2 preflight: CHAVE_AUSENTE")
        return {"fiscal_info": "CHAVE_AUSENTE", "notas": "CHAVE_AUSENTE"}
    headers = {
        "access_token": chave, "Accept": "application/json",
        "User-Agent": "LiderFiscalV2Sandbox/1.0",
    }
    resultados = {}
    for item, caminho in (
        ("fiscal_info", "/fiscalInfo/"),
        ("notas", "/invoices?limit=1"),
    ):
        try:
            resposta = requests.get(
                "https://api-sandbox.asaas.com/v3" + caminho,
                headers=headers, timeout=12, allow_redirects=False
            )
            codigo = resposta.status_code
            situacao = (
                "OK" if codigo == 200 else
                "NAO_CONFIGURADO" if item == "fiscal_info" and codigo == 404 else
                "ACESSO_NEGADO" if codigo in (401, 403) else
                "HTTP_" + str(codigo)
            )
        except requests.RequestException:
            situacao = "SEM_RESPOSTA"
        resultados[item] = situacao
        app_v2.logger.warning("Fiscal V2 preflight: %s = %s", item, situacao)
    return resultados


if os.environ.get("FISCAL_V2_PREFLIGHT") == "SIM":
    verificar_prontidao_fiscal_sandbox()


if os.environ.get("FISCAL_V2_PROD_CHECK") == "SIM":
    from fiscal_v2_production_readonly import diagnosticar_producao
    # Resultado apenas de códigos HTTP; não registrar qualquer dado da conta.
    for item, situacao in diagnosticar_producao().items():
        app_v2.logger.warning("Fiscal V2 produção leitura: %s = %s", item, situacao)


if os.environ.get("FISCAL_V2_CONCILIAR_961543418") == "SIM":
    from fiscal_v2_cobranca_961543418 import investigar
    # Logs de conciliação apenas no serviço de testes isolado.
    import json
    relatorio = investigar(os.environ.get("ASAAS_PRODUCAO_CONSULTA_KEY", "").strip())
    app_v2.logger.warning("Fiscal V2 fatura 961543418: %s", json.dumps(relatorio))


if os.environ.get("FISCAL_V2_NBS_CHECK") == "SIM":
    from fiscal_v2_nbs_diagnostico import diagnosticar_catalogo
    import json
    resultado_nbs=diagnosticar_catalogo()
    app_v2.logger.warning("Fiscal V2 catalogo NBS: %s",json.dumps(resultado_nbs,ensure_ascii=False))


if os.environ.get("FISCAL_V2_NOTAS_RECENTES") == "SIM":
    import json
    from fiscal_v2_notas_recentes import auditar_notas_recentes
    app_v2.logger.warning(
        "Fiscal V2 auditoria NFS-e recente: %s",
        json.dumps(auditar_notas_recentes(), ensure_ascii=False),
    )
