"""Testes de agendamento fiscal V2 sem acesso à rede ou a contas reais."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest
import requests

from fiscal_v2 import ConsultaFiscal
from fiscal_v2_agendamento import (
    DadosNota, ReservaFiscal, agendar_em_homologacao, preparar_nota,
    SANDBOX_ASAAS,
)


def tributacao():
    return DadosNota(
        service_description="Royalties de franquia",
        observations="Teste fiscal sandbox",
        municipal_service_code="17.08.01",
        municipal_service_name="Franquia",
        taxes={"retainIss": False, "iss": 2.0, "nbsCode": "111100000"},
        effective_date="2026-11-06",
    )


def cliente(base_url=SANDBOX_ASAAS, status_http=200, invoice_payload=None):
    sessao = Mock()
    def get(url, **kwargs):
        res = Mock(status_code=200)
        if "/payments/" in url:
            res.json.return_value = {
                "id": "pay_teste", "status": "RECEIVED",
                "value": 5.56, "externalReference": "lider-royalties-teste|NFSE|"
            }
        else:
            res.json.return_value = {"data": [], "hasMore": False}
        return res
    sessao.get.side_effect = get
    res = Mock(status_code=status_http)
    res.json.return_value = invoice_payload or {"id": "inv_teste", "status": "SCHEDULED"}
    sessao.post.return_value = res
    return ConsultaFiscal("chave-ficticia", base_url=base_url, session=sessao), sessao


def test_sem_autorizacao_nao_escreve_ou_emite(tmp_path):
    c, s = cliente()
    db = ReservaFiscal(str(tmp_path / "registros.sqlite3"))
    with pytest.raises(PermissionError):
        agendar_em_homologacao(c, db, "pay_teste", tributacao())
    s.post.assert_not_called()
    assert db.consultar("pay_teste") is None


def test_producao_bloqueada_sem_chamadas(tmp_path):
    c, s = cliente("https://api.asaas.com/v3")
    with pytest.raises(PermissionError):
        agendar_em_homologacao(
            c, ReservaFiscal(str(tmp_path / "db.sqlite3")), "pay_teste", tributacao(), True
        )
    s.get.assert_not_called()
    s.post.assert_not_called()


def test_sandbox_uma_unica_solicitacao(tmp_path):
    c, s = cliente()
    db = ReservaFiscal(str(tmp_path / "db.sqlite3"))
    resultado = agendar_em_homologacao(c, db, "pay_teste", tributacao(), True)
    assert resultado["status_asaas"] == "SCHEDULED"
    assert resultado["nota_emitida"] is False
    assert db.consultar("pay_teste") == {"status": "AGENDADA", "invoice_id": "inv_teste"}
    assert s.post.call_count == 1
    assert s.post.call_args.kwargs["json"]["payment"] == "pay_teste"
    assert s.post.call_args.kwargs["json"]["updatePayment"] is False
    with pytest.raises(RuntimeError, match="Tentativa anterior"):
        agendar_em_homologacao(c, db, "pay_teste", tributacao(), True)
    assert s.post.call_count == 1


def test_timeout_persistido_e_sem_novo_post(tmp_path):
    c, s = cliente()
    db = ReservaFiscal(str(tmp_path / "db.sqlite3"))
    s.post.side_effect = requests.Timeout()
    with pytest.raises(RuntimeError, match="incerto"):
        agendar_em_homologacao(c, db, "pay_teste", tributacao(), True)
    assert db.consultar("pay_teste")["status"] == "RESPOSTA_AMBIGUA"
    with pytest.raises(RuntimeError, match="Tentativa anterior"):
        agendar_em_homologacao(c, db, "pay_teste", tributacao(), True)
    assert s.post.call_count == 1


def test_erro_validacao_persistido_sem_repeticao(tmp_path):
    c, s = cliente(status_http=400)
    db = ReservaFiscal(str(tmp_path / "db.sqlite3"))
    with pytest.raises(RuntimeError, match="não confirmou"):
        agendar_em_homologacao(c, db, "pay_teste", tributacao(), True)
    assert db.consultar("pay_teste")["status"] == "REJEITADA"
    s.post.assert_called_once()


def test_retorno_ambiguidade_status_persistida(tmp_path):
    c, s = cliente(invoice_payload={"status": "SCHEDULED"})
    db = ReservaFiscal(str(tmp_path / "db.sqlite3"))
    with pytest.raises(RuntimeError, match="ambígua"):
        agendar_em_homologacao(c, db, "pay_teste", tributacao(), True)
    assert db.consultar("pay_teste")["status"] == "RESPOSTA_AMBIGUA"
    s.post.assert_called_once()


def test_sem_codigo_fiscal_valido_sem_post(tmp_path):
    c, s = cliente()
    db = ReservaFiscal(str(tmp_path / "db.sqlite3"))
    dados = DadosNota("Royalties", "", "17.08.01", "Franquia",
                     {"retainIss": False, "iss": 2}, "2026-11-06")
    with pytest.raises(ValueError):
        agendar_em_homologacao(c, db, "pay_teste", dados, True)
    s.post.assert_not_called()
    assert db.consultar("pay_teste") is None


def test_idempotencia_entre_instancias(tmp_path):
    db_path = str(tmp_path / "db.sqlite3")
    assert ReservaFiscal(db_path).reservar("pay_teste")
    assert not ReservaFiscal(db_path).reservar("pay_teste")
