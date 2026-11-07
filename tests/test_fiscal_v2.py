"""Fiscal V2 only makes GET calls and does not claim emission without Asaas evidence."""
from unittest.mock import Mock
import pytest
from fiscal_v2 import ConsultaFiscal, FalhaConciliacao, conciliar, configuracao_v2


def cliente(payment, invoices=()):
    sessao = Mock()
    def get(url, **kwargs):
        resposta = Mock()
        resposta.status_code = 200
        if "/payments/" in url:
            resposta.json.return_value = payment
        else:
            resposta.json.return_value = {
                "data": list(invoices), "hasMore": False
            }
        return resposta
    sessao.get.side_effect = get
    sessao.post.side_effect = AssertionError("POST não permitido na V2")
    sessao.put.side_effect = AssertionError("PUT não permitido na V2")
    sessao.delete.side_effect = AssertionError("DELETE não permitido na V2")
    return ConsultaFiscal("token-ficticio", session=sessao), sessao


def pagamento(referencia="lider-royalties-teste|NFSE|", status="RECEIVED", payment_id="pay_teste"):
    return {"id": payment_id, "status": status, "externalReference": referencia, "value": 5.56}


def test_pagamento_recebido_sem_nota_fica_pendente():
    c, s = cliente(pagamento())
    r = conciliar(c, "pay_teste")
    assert r.situacao == "PAGA_SEM_NOTA"
    assert r.nota_solicitada
    assert s.get.call_count == 2
    s.post.assert_not_called()


def test_pagamento_sem_marcador_nao_solicita():
    c, s = cliente(pagamento(referencia="lider-royalties-teste"))
    r = conciliar(c, "pay_teste")
    assert r.situacao == "NAO_SOLICITADA"
    s.post.assert_not_called()


def test_agendamento_nao_se_confunde_com_emissao():
    c, s = cliente(pagamento(), [{"id": "inv_1", "payment": "pay_teste", "status": "SCHEDULED"}])
    r = conciliar(c, "pay_teste")
    assert r.situacao == "AGENDADA_NO_ASAAS"
    assert r.invoice_id == "inv_1"
    s.post.assert_not_called()


def test_status_erro_nao_passa_por_autorizado():
    c, _ = cliente(pagamento(), [{"id": "inv_1", "payment": "pay_teste", "status": "ERROR"}])
    assert conciliar(c, "pay_teste").situacao == "ERRO_OU_CANCELAMENTO"


def test_duas_notas_demandam_conciliacao():
    notas = [{"id": x, "payment": "pay_teste", "status": "AUTHORIZED"} for x in ("inv_1", "inv_2")]
    c, s = cliente(pagamento(), notas)
    assert conciliar(c, "pay_teste").situacao == "REVISAR_DUPLICIDADE"
    s.post.assert_not_called()


def test_nota_de_outro_pagamento_rejeitada():
    c, s = cliente(pagamento(), [{"id": "inv_1", "payment": "pay_outro", "status": "AUTHORIZED"}])
    with pytest.raises(FalhaConciliacao):
        conciliar(c, "pay_teste")
    s.post.assert_not_called()


def test_api_nunca_reconcilia_outra_cobranca():
    c, s = cliente(pagamento(payment_id="pay_outro"))
    with pytest.raises(FalhaConciliacao):
        conciliar(c, "pay_teste")
    s.post.assert_not_called()


def test_paginacao_ambigua_falha_fechada():
    c, s = cliente(pagamento())
    def get(url, **kwargs):
        r = Mock(status_code=200)
        r.json.return_value = pagamento() if "/payments/" in url else {
            "data": [], "hasMore": True
        }
        return r
    s.get.side_effect = get
    with pytest.raises(FalhaConciliacao):
        conciliar(c, "pay_teste")
    s.post.assert_not_called()


def test_v2_inativa_por_padrao():
    assert configuracao_v2()["emissao_automatica_ativa"] is False
    assert configuracao_v2()["modo"] == "SOMENTE_LEITURA"
