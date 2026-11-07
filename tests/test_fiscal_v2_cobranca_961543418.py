from unittest.mock import Mock
from fiscal_v2_cobranca_961543418 import investigar, REFERENCIA

def mock_get(url,**kw):
    obj=Mock(status_code=200)
    if url.endswith("/payments"):
        obj.json.return_value={"data":[{
            "id":"pay_teste123","invoiceNumber":"961543418",
            "externalReference":REFERENCIA,"value":5.56,"status":"RECEIVED"
        }],"hasMore":False}
    else:
        obj.json.return_value={"data":[],"hasMore":False}
    return obj

def test_pagamento_recebido_sem_nota_sem_post():
    get=Mock(side_effect=mock_get)
    resultado=investigar("chave-ficticia",get)
    assert resultado["resultado"]=="CONCILIADO"
    assert resultado["quantidade_notas"]==0
    assert get.call_count==2
    assert get.call_args_list[0].kwargs["params"]["externalReference"]==REFERENCIA
    assert get.call_args_list[1].kwargs["params"]["payment"]=="pay_teste123"

def test_cobranca_nao_unica_falha_fechada():
    def get(url,**kwargs):
        r=mock_get(url,**kwargs)
        r.json.return_value={"data":[],"hasMore":False}
        return r
    assert investigar("chave-ficticia",get)["resultado"]=="COBRANCA_NAO_UNICA"

def test_sem_chave_nao_consulta():
    get=Mock()
    assert investigar("",get)["resultado"]=="CHAVE_AUSENTE"
    get.assert_not_called()

def test_valor_divergente_nao_consulta_notas():
    def get(url,**kwargs):
        r=mock_get(url,**kwargs)
        data=r.json.return_value
        data["data"][0]["value"]=10
        return r
    g=Mock(side_effect=get)
    assert investigar("ficticia",g)["resultado"]=="VALOR_DIVERGENTE"
    assert g.call_count==1
