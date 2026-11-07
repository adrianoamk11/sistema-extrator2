"""Rota da Fiscal V2 no webhook legado não pode iniciar sem opt-in."""
import importlib
import os

import pytest

import webhook


def test_rota_v2_desativada_sem_flag(monkeypatch):
    monkeypatch.delenv("FISCAL_V2_RECEPCAO_REAL", raising=False)
    with webhook.app.test_client() as c:
        resposta = c.post("/webhook/asaas/v2", json={"event": "PAYMENT_RECEIVED"})
    assert resposta.status_code == 404


def test_rota_v2_sem_disco_retornara_503_sem_responder_sucesso(monkeypatch):
    import fiscal_v2_webhook

    monkeypatch.setenv("FISCAL_V2_RECEPCAO_REAL", "SIM")
    monkeypatch.setenv("FISCAL_V2_WEBHOOK_TOKEN", "token-teste")
    monkeypatch.setenv("FISCAL_V2_EVENT_DB", "/tmp/nao-persistente.sqlite3")
    monkeypatch.setattr(
        fiscal_v2_webhook,
        "diagnostico_persistencia",
        lambda *_: "FORA_DO_DISCO_PERSISTENTE",
    )
    with webhook.app.test_client() as c:
        resposta = c.post(
            "/webhook/asaas/v2",
            json={"id": "evt_123", "event": "PAYMENT_RECEIVED",
                  "payment": {"id": "pay_123"}},
            headers={"asaas-access-token": "token-teste"},
        )
    assert resposta.status_code == 503


def test_rota_v2_responde_200_apos_gravar_em_volume_mockado(monkeypatch, tmp_path):
    import fiscal_v2_webhook

    monkeypatch.setenv("FISCAL_V2_RECEPCAO_REAL", "SIM")
    monkeypatch.setenv("FISCAL_V2_WEBHOOK_TOKEN", "token-teste")
    monkeypatch.setenv("FISCAL_V2_EVENT_DB", str(tmp_path / "eventos.sqlite3"))
    monkeypatch.setattr(fiscal_v2_webhook, "diagnostico_persistencia", lambda *_: "OK")
    evento = {
        "id": "evt_abc123", "event": "PAYMENT_RECEIVED",
        "payment": {"id": "pay_abc123"},
    }
    with webhook.app.test_client() as c:
        primeiro = c.post(
            "/webhook/asaas/v2",
            json=evento, headers={"asaas-access-token": "token-teste"},
        )
        segundo = c.post(
            "/webhook/asaas/v2",
            json=evento, headers={"asaas-access-token": "token-teste"},
        )
    assert primeiro.status_code == 200
    assert primeiro.json["registrado"] is True
    assert segundo.status_code == 200
    assert segundo.json["registrado"] is False
