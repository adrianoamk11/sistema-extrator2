"""End-to-end sem rede: webhook persistido -> conciliação -> situação auditável."""
import sqlite3
from unittest.mock import Mock
from fiscal_v2 import ConsultaFiscal
from fiscal_v2_webhook import receber_evento
from fiscal_v2_processador import processar_pendentes


def fake_client(invoice_list):
    sessao = Mock()
    def get(url, **kwargs):
        resultado = Mock(status_code=200)
        if "/payments/" in url:
            resultado.json.return_value = {
                "id": "pay_teste", "status": "RECEIVED",
                "externalReference": "lider-royalties-teste|NFSE|",
                "value": 5.56,
            }
        else:
            resultado.json.return_value = {"data": invoice_list, "hasMore": False}
        return resultado
    sessao.get.side_effect = get
    sessao.post.side_effect = AssertionError("Não pode fazer POST")
    return ConsultaFiscal("token-ficticio", session=sessao), sessao


def test_recebido_sem_nota_vai_para_revisao(tmp_path):
    path = str(tmp_path / "inbox.sqlite3")
    evento = {"id": "evt_teste", "event": "PAYMENT_RECEIVED", "payment": {"id": "pay_teste"}}
    body, status = receber_evento(evento, "token", "token", path)
    assert status == 200 and body["registrado"] is True
    client, sessao = fake_client([])
    resumo = processar_pendentes(path, client)
    assert resumo == {"concluidos": 0, "revisar": 1, "falhas": 0}
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT situacao FROM fiscal_v2_eventos").fetchone()[0] == "PAGA_SEM_NOTA"
    assert processar_pendentes(path, client) == {"concluidos": 0, "revisar": 0, "falhas": 0}
    sessao.post.assert_not_called()


def test_recebido_com_nota_autorizada(tmp_path):
    path = str(tmp_path / "inbox.sqlite3")
    receber_evento({"id": "evt_teste", "event": "PAYMENT_RECEIVED",
                    "payment": {"id": "pay_teste"}}, "token", "token", path)
    client, sessao = fake_client([{"id": "inv_teste", "payment": "pay_teste",
                                  "status": "AUTHORIZED"}])
    assert processar_pendentes(path, client)["concluidos"] == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT situacao FROM fiscal_v2_eventos").fetchone()[0] == "REGISTRADA_NO_ASAAS"
    sessao.post.assert_not_called()


def test_sem_rede_evento_continua_pendente(tmp_path):
    path = str(tmp_path / "inbox.sqlite3")
    receber_evento({"id": "evt_teste", "event": "PAYMENT_RECEIVED",
                    "payment": {"id": "pay_teste"}}, "token", "token", path)
    client, sessao = fake_client([])
    sessao.get.side_effect = RuntimeError("falha de teste")
    assert processar_pendentes(path, client)["falhas"] == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT situacao FROM fiscal_v2_eventos").fetchone()[0] == "PENDENTE"
    sessao.post.assert_not_called()
