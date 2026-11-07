"""Diagnóstico NBS ao vivo usando somente GET na conta de produção.

Faz busca no catálogo oficial disponibilizado pelo Asaas, sem emitir notas.
Registra somente até 8 códigos/descrições de serviço de franquia, sem dados
de clientes, credenciais, detalhes da conta ou outros serviços.
"""
import os
import re

import requests

API="https://api.asaas.com/v3"
FILTROS=("111100000", "1.1110.00.00", "franquia", "franchising")
VALIDOS=("111100000", "11110000", "1111000000")


def diagnosticar_catalogo(chave=None, get=None):
    chave=chave if chave is not None else os.environ.get("ASAAS_PRODUCAO_CONSULTA_KEY","")
    if not chave:
        return {"resultado":"CHAVE_AUSENTE"}
    if get is None:
        get=requests.get
    headers={"access_token":chave,"Accept":"application/json",
             "User-Agent":"LiderFiscalV2Readonly/1.0"}
    encontrados={}
    for filtro in FILTROS:
        try:
            resposta=get(
                API+"/fiscalInfo/nbsCodes",
                headers=headers,
                params={"limit":100,"offset":0,"codeDescription":filtro},
                timeout=15,allow_redirects=False
            )
            if resposta.status_code != 200:
                encontrados[filtro]={"status":"HTTP_"+str(resposta.status_code)}
                continue
            dados=resposta.json()
            if not isinstance(dados,dict) or not isinstance(dados.get("data"),list):
                encontrados[filtro]={"status":"RESPOSTA_INVALIDA"}
                continue
            selecionados=[]
            for row in dados["data"]:
                if not isinstance(row,dict):
                    continue
                codigo=str(row.get("code") or row.get("nbsCode") or "")
                descricao=str(row.get("description") or "")
                if (
                    re.search(r"franqu|franch",descricao,re.I)
                    or re.sub(r"\D","",codigo).startswith("11110")
                ):
                    selecionados.append({
                        "codigo":codigo[:35],
                        "descricao":descricao[:125],
                    })
            encontrados[filtro]={
                "status":"OK",
                "resultados_servidor":len(dados["data"]),
                "mais_paginas":dados.get("hasMore"),
                "correspondencias":selecionados[:8],
            }
        except (requests.RequestException, ValueError, TypeError):
            encontrados[filtro]={"status":"CONSULTA_FALHOU"}
    return encontrados
