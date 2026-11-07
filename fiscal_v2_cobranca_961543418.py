"""Reconciliacao pontual e estritamente somente leitura de cobrança de royalties.

Confere a identidade da cobrança pela referência externa exata e por data,
valor, número de fatura, sem emitir nota e sem imprimir dados do cliente.
"""
import requests

API="https://api.asaas.com/v3"
REFERENCIA="lider-royalties-7d33a112df7c734474ba|NFSE|"
FATURA="961543418"


def investigar(chave, get=None):
    if not chave:
        return {"resultado":"CHAVE_AUSENTE"}
    if get is None:
        get=requests.get
    cabecalho={"access_token":chave, "Accept":"application/json",
               "User-Agent":"LiderFiscalV2Readonly/1.0"}
    def consulta(path,params):
        res=get(API+path, headers=cabecalho,params=params,timeout=15,allow_redirects=False)
        if res.status_code!=200:
            return None, "HTTP_"+str(res.status_code)
        try:
            corpo=res.json()
        except ValueError:
            return None, "JSON_INVALIDO"
        if not isinstance(corpo,dict):
            return None,"JSON_INVALIDO"
        return corpo,None

    try:
        pagamentos,erro=consulta("/payments",{"externalReference":REFERENCIA,"limit":100})
        if erro:
            return {"resultado":"CONSULTA_COBRANCA_"+erro}
        lista=pagamentos.get("data")
        if not isinstance(lista,list) or pagamentos.get("hasMore") is not False:
            return {"resultado":"LISTAGEM_INCOMPLETA"}
        candidatos=[p for p in lista if isinstance(p,dict) and p.get("externalReference")==REFERENCIA]
        if len(candidatos)!=1:
            return {"resultado":"COBRANCA_NAO_UNICA","quantidade":len(candidatos)}
        pagamento=candidatos[0]
        payment_id=pagamento.get("id")
        if not isinstance(payment_id,str) or not payment_id.startswith("pay_"):
            return {"resultado":"IDENTIFICADOR_INVALIDO"}
        if str(pagamento.get("invoiceNumber") or "") != FATURA:
            return {"resultado":"NUMERO_FATURA_DIVERGENTE"}
        if str(pagamento.get("value")) not in ("5.56","5.560"):
            return {"resultado":"VALOR_DIVERGENTE"}
        if pagamento.get("status") not in ("RECEIVED","CONFIRMED","RECEIVED_IN_CASH"):
            return {"resultado":"COBRANCA_NAO_RECEBIDA","situacao":str(pagamento.get("status"))[:30]}
        notas,erro=consulta("/invoices",{"payment":payment_id,"limit":100})
        if erro:
            return {"resultado":"CONSULTA_NOTAS_"+erro}
        registros=notas.get("data")
        if not isinstance(registros,list) or notas.get("hasMore") is not False:
            return {"resultado":"NOTAS_INCOMPLETAS"}
        if any(not isinstance(n,dict) or n.get("payment")!=payment_id for n in registros):
            return {"resultado":"NOTAS_VINCULO_INCONSISTENTE"}
        return {
            "resultado":"CONCILIADO",
            "pagamento":payment_id,
            "situacao_pagamento":pagamento["status"],
            "quantidade_notas":len(registros),
            "situacoes_notas":[str(n.get("status") or "NAO_INFORMADO")[:30] for n in registros],
        }
    except requests.RequestException:
        return {"resultado":"FALHA_REDE"}
