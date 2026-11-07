"""Consulta de NFS-e recentes na conta real; GET-only e sem dados identificáveis.

Não faz POST, não cria cobrancas e não mostra clientes, CNPJ, nota ou valores.
"""
import os
from collections import Counter

import requests

API = "https://api.asaas.com/v3"


def auditar_notas_recentes(chave=None, get=None):
    chave = os.environ.get("ASAAS_PRODUCAO_CONSULTA_KEY", "").strip() if chave is None else chave
    if not chave:
        return {"resultado": "CHAVE_AUSENTE"}
    if get is None:
        get = requests.get
    try:
        resposta = get(
            API + "/invoices",
            headers={"access_token": chave, "Accept": "application/json",
                     "User-Agent": "LiderFiscalV2Readonly/1.0"},
            params={"limit": 100, "offset": 0},
            timeout=15,
            allow_redirects=False,
        )
        if resposta.status_code != 200:
            return {"resultado": "HTTP_" + str(resposta.status_code)}
        dados = resposta.json()
        if not isinstance(dados, dict) or not isinstance(dados.get("data"), list):
            return {"resultado": "DADOS_INVALIDOS"}
        notas = dados["data"]
        situacoes = Counter(
            str(n.get("status") or "NAO_INFORMADO")[:40]
            for n in notas if isinstance(n, dict)
        )
        return {
            "resultado": "OK",
            "quantidade_primeira_pagina": len(notas),
            "possui_mais_paginas": bool(dados.get("hasMore")),
            "situacoes": dict(situacoes),
            "emitida_autorizada_na_primeira_pagina": situacoes.get("AUTHORIZED", 0),
            "observacao": "A consulta nao comprova emissao apos a ultima correcao",
        }
    except (requests.RequestException, ValueError, TypeError):
        return {"resultado": "CONSULTA_INDISPONIVEL"}
