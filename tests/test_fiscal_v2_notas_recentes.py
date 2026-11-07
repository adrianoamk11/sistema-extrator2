from unittest.mock import Mock

from fiscal_v2_notas_recentes import auditar_notas_recentes


def test_consulta_de_notas_apenas_get_e_sem_dados_fiscais():
    result = Mock(status_code=200)
    result.json.return_value = {
        "data": [
            {"id": "inv_seg1", "status": "AUTHORIZED", "customer": "segredo_cliente"},
            {"id": "inv_seg2", "status": "SCHEDULED", "value": 2000},
        ],
        "hasMore": False,
    }
    get = Mock(return_value=result)
    retorno = auditar_notas_recentes("chave-ficticia", get)
    assert retorno["resultado"] == "OK"
    assert retorno["situacoes"] == {"AUTHORIZED": 1, "SCHEDULED": 1}
    assert "segredo_cliente" not in repr(retorno)
    assert "inv_seg1" not in repr(retorno)
    assert get.call_count == 1
    assert get.call_args.args[0] == "https://api.asaas.com/v3/invoices"


def test_sem_chave_nao_faz_consulta():
    get = Mock()
    assert auditar_notas_recentes("", get) == {"resultado": "CHAVE_AUSENTE"}
    get.assert_not_called()
