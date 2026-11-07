"""Teste do recebimento durável sem rede, sem emissão e sem atualizar o webhook anterior."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fiscal_v2_webhook import app_v2, receber_evento


def evento():
    return {
        "id": "evt_teste123",
        "event": "PAYMENT_RECEIVED",
        "payment": {"id": "pay_teste", "status": "RECEIVED"},
    }


def test_sem_token_rejeita_e_nao_grava(tmp_path):
    arquivo = str(tmp_path / "eventos.sqlite3")
    resultado, status = receber_evento(evento(), "token-errado", "segredo", arquivo)
    assert status == 401
    assert not (tmp_path / "eventos.sqlite3").exists()


def test_registra_uma_unica_vez_respondendo_200(tmp_path):
    arquivo = str(tmp_path / "eventos.sqlite3")
    assert receber_evento(evento(), "segredo", "segredo", arquivo)[1] == 200
    body, status = receber_evento(evento(), "segredo", "segredo", arquivo)
    assert status == 200
    assert body["registrado"] is False
    with sqlite3.connect(arquivo) as db:
        assert db.execute("SELECT count(*) FROM fiscal_v2_eventos").fetchone()[0] == 1
        assert db.execute("SELECT situacao FROM fiscal_v2_eventos").fetchone()[0] == "PENDENTE"


def test_concorrencia_nao_duplica_evento(tmp_path):
    arquivo = str(tmp_path / "eventos.sqlite3")
    def processar(_):
        return receber_evento(evento(), "segredo", "segredo", arquivo)
    with ThreadPoolExecutor(max_workers=3) as pool:
        respostas = list(pool.map(processar, range(3)))
    assert sum(body.get("registrado") is True for body, status in respostas) == 1
    assert all(status == 200 for _, status in respostas)


def test_erro_de_disco_nao_confirma_entrega(tmp_path):
    arquivo = str(tmp_path / "inexistente" / "eventos.sqlite3")
    assert receber_evento(evento(), "segredo", "segredo", arquivo)[1] == 503


def test_evento_nao_suportado_e_ignorado(tmp_path):
    arquivo = str(tmp_path / "eventos.sqlite3")
    evento_novo = {"id": "evt_outro", "event": "PAYMENT_UPDATED"}
    body, status = receber_evento(evento_novo, "segredo", "segredo", arquivo)
    assert status == 200
    assert body["ignorado"]
    assert not (tmp_path / "eventos.sqlite3").exists()


def test_endpoint_desligado_por_padrao(monkeypatch):
    monkeypatch.delenv("FISCAL_V2_RECEPCAO_SANDBOX", raising=False)
    with app_v2.test_client() as client:
        result = client.post("/webhook/asaas/v2", json=evento())
    assert result.status_code == 404


def test_endpoint_ligado_requer_token_e_banco(monkeypatch, tmp_path):
    monkeypatch.setenv("FISCAL_V2_RECEPCAO_SANDBOX", "SIM")
    monkeypatch.setenv("FISCAL_V2_WEBHOOK_TOKEN", "segredo")
    monkeypatch.setenv("FISCAL_V2_EVENT_DB", str(tmp_path / "eventos.sqlite3"))
    with app_v2.test_client() as client:
        assert client.post("/webhook/asaas/v2", json=evento()).status_code == 401
        response = client.post(
            "/webhook/asaas/v2", json=evento(),
            headers={"asaas-access-token": "segredo"}
        )
    assert response.status_code == 200


def test_verificacao_sandbox_sem_chave_nao_chama_api(monkeypatch):
    import fiscal_v2_webhook
    monkeypatch.delenv("ASAAS_SANDBOX_API_KEY", raising=False)
    assert fiscal_v2_webhook.verificar_conexao_sandbox() == "CHAVE_AUSENTE"


def test_verificacao_sandbox_get_somente_e_nao_expoe_resposta(monkeypatch):
    import requests
    import fiscal_v2_webhook
    from unittest.mock import Mock
    monkeypatch.setenv("ASAAS_SANDBOX_API_KEY", "chave-ficticia")
    retorno = Mock(status_code=200)
    fake_get = Mock(return_value=retorno)
    monkeypatch.setattr(requests, "get", fake_get)
    assert fiscal_v2_webhook.verificar_conexao_sandbox() == "CONECTADO"
    assert fake_get.call_count == 1
    args, kwargs = fake_get.call_args
    assert args[0] == "https://api-sandbox.asaas.com/v3/myAccount/status/"
    assert kwargs["headers"]["access_token"] == "chave-ficticia"
    assert kwargs["allow_redirects"] is False


def test_verificacao_sandbox_recusa_credencial_invalida(monkeypatch):
    import requests
    import fiscal_v2_webhook
    from unittest.mock import Mock
    monkeypatch.setenv("ASAAS_SANDBOX_API_KEY", "chave-ficticia")
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=401)))
    assert fiscal_v2_webhook.verificar_conexao_sandbox() == "NAO_AUTORIZADO"


def test_preflight_fiscal_info_ausente_nao_emite_nada(monkeypatch):
    import requests
    import fiscal_v2_webhook
    from unittest.mock import Mock
    monkeypatch.setenv("ASAAS_SANDBOX_API_KEY", "somente-teste")
    get = Mock(side_effect=[Mock(status_code=404), Mock(status_code=200)])
    monkeypatch.setattr(requests, "get", get)
    assert fiscal_v2_webhook.verificar_prontidao_fiscal_sandbox() == {
        "fiscal_info": "NAO_CONFIGURADO", "notas": "OK"
    }
    assert get.call_count == 2
    assert all(
        c.args[0].startswith("https://api-sandbox.asaas.com/v3/")
        for c in get.call_args_list
    )


def test_preflight_nunca_faz_get_sem_chave(monkeypatch):
    import fiscal_v2_webhook
    monkeypatch.delenv("ASAAS_SANDBOX_API_KEY", raising=False)
    assert fiscal_v2_webhook.verificar_prontidao_fiscal_sandbox()["fiscal_info"] == "CHAVE_AUSENTE"
