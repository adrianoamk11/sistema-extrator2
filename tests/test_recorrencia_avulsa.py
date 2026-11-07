from datetime import date
from unittest.mock import Mock

import pytest

from recorrencia_avulsa import (
    PREFIXO,
    criar_recorrencia,
    listar_recorrencias_extrator,
    referencia_recorrencia,
    suspender_recorrencia,
)


def resposta(corpo, status=200):
    r = Mock(ok=status < 400, status_code=status)
    r.json.return_value = corpo
    return r


CLIENTE = "cus_ABC12345"
DATA = date(2026, 11, 10)
API = "https://api-sandbox.asaas.com/v3"
CAB = {"access_token": "fake-key"}


def argumento_criar(get, post=None, **kwargs):
    return criar_recorrencia(
        API, CAB, CLIENTE, 300.0, DATA, "Mensalidade", get=get,
        post=post or Mock(), hoje=date(2026, 11, 6), **kwargs,
    )


def test_cria_assinatura_mensal_boletos_sem_data_fim_e_sem_nf():
    get = Mock(return_value=resposta({"data": [], "hasMore": False}))
    post = Mock(return_value=resposta({
        "id": "sub_01", "customer": CLIENTE, "status": "ACTIVE",
    }))
    retorno, novo = argumento_criar(get, post)
    assert novo is True
    assert retorno["id"] == "sub_01"
    assert post.call_count == 1
    assert post.call_args.args[0] == API + "/subscriptions"
    payload = post.call_args.kwargs["json"]
    assert payload == {
        "customer": CLIENTE,
        "billingType": "BOLETO",
        "value": 300.0,
        "nextDueDate": "2026-11-10",
        "cycle": "MONTHLY",
        "description": "Mensalidade",
        "externalReference": referencia_recorrencia(CLIENTE, 300, DATA, "Mensalidade"),
    }
    assert "endDate" not in payload
    assert "maxPayments" not in payload
    assert "taxes" not in payload
    assert "NFSE" not in str(payload)
    assert all("/payments" not in str(c) for c in get.call_args_list)


def test_repeticao_da_mesma_recorrencia_nunca_gera_nova():
    ref = referencia_recorrencia(CLIENTE, 300, DATA, "Mensalidade")
    get = Mock(return_value=resposta({"data": [{
        "id": "sub_EXISTENTE",
        "customer": CLIENTE,
        "externalReference": ref,
        "status": "ACTIVE",
    }], "hasMore": False}))
    post = Mock()
    sub, nova = argumento_criar(get, post)
    assert not nova
    assert sub["id"] == "sub_EXISTENTE"
    post.assert_not_called()


def test_recorrencia_ativa_equivalente_mesma_descricao_bloqueia_duplicidade():
    get = Mock(side_effect=[
        resposta({"data": [], "hasMore": False}),
        resposta({"data": [{
            "id": "sub_old", "customer": CLIENTE,
            "cycle": "MONTHLY", "billingType": "BOLETO",
            "description": "Mensalidade", "value": 300.0,
            "externalReference": PREFIXO + "outra-data",
        }], "hasMore": False}),
    ])
    post = Mock()
    with pytest.raises(RuntimeError, match="mesmo valor"):
        argumento_criar(get, post)
    post.assert_not_called()


def test_falha_envio_nao_tenta_repetir_e_pede_conciliacao():
    get = Mock(return_value=resposta({"data": [], "hasMore": False}))
    post = Mock(side_effect=TimeoutError())
    with pytest.raises(RuntimeError, match="Antes de tentar novamente"):
        argumento_criar(get, post)
    assert post.call_count == 1


def test_suspendendo_preserva_cobrancas_existentes_e_nao_deleta():
    get = Mock(return_value=resposta({
        "id": "sub_12", "status": "ACTIVE",
        "externalReference": PREFIXO + "teste",
    }))
    put = Mock(return_value=resposta({
        "id": "sub_12", "status": "INACTIVE",
    }))
    resposta_sub, mudou = suspender_recorrencia(API, CAB, "sub_12", get, put)
    assert mudou
    assert resposta_sub["status"] == "INACTIVE"
    assert put.call_count == 1
    assert put.call_args.args[0] == API + "/subscriptions/sub_12"
    assert put.call_args.kwargs["json"] == {"status": "INACTIVE"}
    assert "/payments" not in str(put.call_args)
    assert "/customers" not in str(put.call_args)


def test_outra_assinatura_nao_pode_ser_suspensa():
    get = Mock(return_value=resposta({
        "id": "sub_12", "status": "ACTIVE",
        "externalReference": "externa-nao-lider",
    }))
    put = Mock()
    with pytest.raises(RuntimeError, match="não foi criada"):
        suspender_recorrencia(API, CAB, "sub_12", get, put)
    put.assert_not_called()


def test_lista_somente_recorrencias_do_extrator():
    get = Mock(return_value=resposta({"data": [
        {"id": "sub_a", "customer": CLIENTE, "externalReference": PREFIXO + "123",
         "status": "ACTIVE", "description": "Mensalidade", "value": 300},
        {"id": "sub_terceiro", "externalReference": "outra origem"},
    ], "hasMore": False}))
    linhas = listar_recorrencias_extrator(API, CAB, get, status="ACTIVE")
    assert len(linhas) == 1
    assert linhas[0]["id"] == "sub_a"
    assert get.call_args.kwargs["params"]["status"] == "ACTIVE"


def test_rejeita_data_passada_antes_de_chamar_asaas():
    get, post = Mock(), Mock()
    with pytest.raises(ValueError, match="passado"):
        criar_recorrencia(
            API, CAB, CLIENTE, 300, date(2026, 11, 5),
            "Mensalidade", get=get, post=post, hoje=date(2026, 11, 6)
        )
    get.assert_not_called()
    post.assert_not_called()
