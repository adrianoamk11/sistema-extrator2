"""Regressão sem rede nem operações reais no Asaas."""
import ast
import threading
import time
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

import operacao_financeira as seguranca
from conciliacao_fiscal import consultar_nfse_por_pagamento
from operacao_financeira import (
    operacao_financeira_unica,
    marcar_resultado_inconclusivo,
    resposta_inconclusiva,
)
from recorrencia_avulsa import criar_recorrencia


def _resposta(data, status=200):
    retorno = Mock(ok=status < 400, status_code=status)
    retorno.json.return_value = data
    return retorno


@pytest.fixture(autouse=True)
def sem_pendencias_entre_testes():
    with seguranca._LOCK_GUARD:
        seguranca._INCONCLUSIVAS.clear()
    yield
    with seguranca._LOCK_GUARD:
        seguranca._INCONCLUSIVAS.clear()


def test_falha_inconclusiva_bloqueia_reenvio_na_mesma_instancia():
    chave = ("conta-a", "referencia-123")
    with operacao_financeira_unica(chave):
        marcar_resultado_inconclusivo(chave)
    with pytest.raises(RuntimeError, match="resposta incerta"):
        with operacao_financeira_unica(chave):
            pytest.fail("Uma segunda tentativa seria insegura")
    assert resposta_inconclusiva(503)
    assert resposta_inconclusiva(429)
    assert not resposta_inconclusiva(400)


def test_mesma_referencia_nao_executa_duas_emissoes_em_paralelo():
    contador = [0]
    simultaneas = [0]
    bloqueio_contagem = threading.Lock()

    def trabalho():
        with operacao_financeira_unica(("conta", "boleto-igual")):
            with bloqueio_contagem:
                simultaneas[0] += 1
                contador[0] = max(contador[0], simultaneas[0])
            time.sleep(.02)
            with bloqueio_contagem:
                simultaneas[0] -= 1

    t1 = threading.Thread(target=trabalho)
    t2 = threading.Thread(target=trabalho)
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert not t1.is_alive() and not t2.is_alive()
    assert contador[0] == 1


def test_recorrencia_inativa_nao_reativa_automaticamente():
    ref = (
        "lider-avulso-mensal-"
        + __import__("hashlib").sha256(
            f"cus_Ab123|300.00|2026-11-10|Mensalidade".encode()
        ).hexdigest()[:24]
    )
    get = Mock(return_value=_resposta({
        "data": [{
            "id": "sub_INATIVA",
            "customer": "cus_Ab123",
            "status": "INACTIVE",
            "externalReference": ref,
        }],
        "hasMore": False,
    }))
    post = Mock()
    with pytest.raises(RuntimeError, match="suspensa ou expirada"):
        criar_recorrencia(
            "https://api-sandbox.asaas.com/v3", {}, "cus_Ab123",
            300.0, date(2026, 11, 10), "Mensalidade",
            get=get, post=post, hoje=date(2026, 11, 6),
        )
    post.assert_not_called()


def test_conciliacao_fiscal_so_leitura_usa_o_pagamento_correto():
    get = Mock(side_effect=[
        _resposta({
            "id": "pay_Ab123",
            "status": "RECEIVED",
            "externalReference": "lider-royalties-abcd|NFSE|",
        }),
        _resposta({
            "data": [{"payment": "pay_Ab123", "id": "inv_123", "status": "AUTHORIZED"}],
            "hasMore": False,
        }),
    ])
    r = consultar_nfse_por_pagamento(
        "https://api-sandbox.asaas.com/v3", {}, "pay_Ab123", get=get,
    )
    assert r["fiscal_solicitada_pelo_extrator"] is True
    assert r["notas"][0]["status"] == "AUTHORIZED"
    assert get.call_count == 2
    assert all(call.args[0].endswith(("/payments/pay_Ab123", "/invoices"))
               for call in get.call_args_list)


def test_conciliacao_bloqueia_nota_de_outro_pagamento():
    get = Mock(side_effect=[
        _resposta({"id": "pay_Ab123", "status": "RECEIVED"}),
        _resposta({
            "data": [{"payment": "pay_OUTRO", "id": "inv_ERRADA"}],
            "hasMore": False,
        }),
    ])
    with pytest.raises(RuntimeError, match="divergente"):
        consultar_nfse_por_pagamento(
            "https://api-sandbox.asaas.com/v3", {}, "pay_Ab123", get=get
        )


def _funcao_app(nome, escopo):
    fonte = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    alvo = next(no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == nome)
    exec(compile(ast.Module(body=[alvo], type_ignores=[]), "<teste-app>", "exec"), escopo)
    return escopo[nome]


def test_historico_inclui_cobranca_da_assinatura_asaas():
    pagamento = {
        "id": "pay_Ab123",
        "externalReference": "",
        "subscription": "sub_REC123",
        "dateCreated": "2026-11-07",
        "status": "PENDING",
    }
    from datetime import timedelta
    from dateutil.relativedelta import relativedelta
    get = Mock(return_value=_resposta({"data": [pagamento], "hasMore": False}))
    escopo = {
        "date": date,
        "timedelta": timedelta,
        "relativedelta": relativedelta,
        "requests": Mock(get=get),
        "ASAAS_BASE_URL": "https://api-sandbox.asaas.com/v3",
        "cabecalhos_asaas": lambda: {},
        "listar_recorrencias_extrator": Mock(return_value=[{"id": "sub_REC123"}]),
    }
    f = _funcao_app("consultar_historico_asaas", escopo)
    cobrancas = f(2026, 11)
    assert len(cobrancas) == 1
    assert cobrancas[0]["id"] == "pay_Ab123"


def test_notificacoes_ja_padronizadas_nao_regravadas():
    notificacao = {
        "id": "ntf_ABC",
        "event": "PAYMENT_CREATED",
        "scheduleOffset": 0,
        "enabled": True,
        "emailEnabledForProvider": False,
        "smsEnabledForProvider": False,
        "emailEnabledForCustomer": True,
        "smsEnabledForCustomer": False,
        "phoneCallEnabledForCustomer": False,
        "whatsappEnabledForCustomer": False,
    }
    req = Mock()
    escopo = {
        "recuperar_notificacoes_cliente": lambda _: [notificacao],
        "configuracao_base_notificacao": lambda n: {
            "id": n["id"], "enabled": False,
            "emailEnabledForProvider": False,
            "smsEnabledForProvider": False,
            "emailEnabledForCustomer": False,
            "smsEnabledForCustomer": False,
            "phoneCallEnabledForCustomer": False,
            "whatsappEnabledForCustomer": False,
        },
        "requests": req,
        "ASAAS_BASE_URL": "https://asaas.invalid/v3",
        "cabecalhos_asaas": lambda: {},
    }
    func = _funcao_app("padronizar_notificacoes_asaas", escopo)
    assert func("cus_Ab123") is True
    req.put.assert_not_called()


def test_referencia_ambigua_impede_emitir_nova_cobranca():
    referencia = "lider-royalties-abc123"
    resposta = _resposta({
        "data": [
            {"id": "pay_1", "externalReference": referencia},
            {"id": "pay_2", "externalReference": referencia},
        ],
        "hasMore": False,
    })
    escopo = {
        "requests": Mock(get=Mock(return_value=resposta)),
        "ASAAS_BASE_URL": "https://asaas.invalid/v3",
        "cabecalhos_asaas": lambda: {},
    }
    consulta = _funcao_app("buscar_cobranca_existente", escopo)
    with pytest.raises(RuntimeError, match="repetidas"):
        consulta(referencia)


def test_referencia_divergente_nao_reutiliza_cobranca_errada():
    resposta = _resposta({
        "data": [{"id": "pay_OUTRO", "externalReference": "ref-errada"}],
        "hasMore": False,
    })
    escopo = {
        "requests": Mock(get=Mock(return_value=resposta)),
        "ASAAS_BASE_URL": "https://asaas.invalid/v3",
        "cabecalhos_asaas": lambda: {},
    }
    consulta = _funcao_app("buscar_cobranca_existente", escopo)
    with pytest.raises(RuntimeError, match="divergente"):
        consulta("ref-esperada")
