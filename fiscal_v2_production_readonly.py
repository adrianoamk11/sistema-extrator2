"""Diagnóstico somente leitura da conta REAL do Asaas.

Nunca imprime credenciais, dados de clientes, valores ou o corpo da resposta.
Não cria NFS-e, pagamentos ou webhooks. Usado apenas no serviço separado
Fiscal V2 e explicitamente habilitado por variável de ambiente.
"""
import os

import requests

PROD_API = "https://api.asaas.com/v3"
CAMINHOS_PERMITIDOS = (
    ("autenticacao", "/myAccount/status/"),
    ("configuracao_fiscal", "/fiscalInfo/"),
    ("consulta_notas", "/invoices?limit=1"),
)


def diagnosticar_producao(chave=None, get=None):
    if chave is None:
        chave = os.environ.get("ASAAS_PRODUCAO_CONSULTA_KEY", "").strip()
    if not chave:
        return {nome: "CHAVE_AUSENTE" for nome, _ in CAMINHOS_PERMITIDOS}
    if get is None:
        get = requests.get
    headers = {
        "access_token": chave,
        "Accept": "application/json",
        "User-Agent": "LiderFiscalV2Readonly/1.0",
    }
    resultados = {}
    for nome, caminho in CAMINHOS_PERMITIDOS:
        try:
            resposta = get(
                PROD_API + caminho, headers=headers,
                timeout=12, allow_redirects=False
            )
            codigo = resposta.status_code
            resultados[nome] = (
                "OK" if codigo == 200
                else "ACESSO_NEGADO" if codigo in (401, 403)
                else "HTTP_" + str(codigo)
            )
        except requests.RequestException:
            resultados[nome] = "SEM_RESPOSTA"
    return resultados
