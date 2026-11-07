from unittest.mock import Mock
from fiscal_v2_nbs_diagnostico import diagnosticar_catalogo

def test_consulta_catalogo_nao_escreve():
    retorno=Mock(status_code=200)
    retorno.json.return_value={"data":[{"code":"1.1110.00.00","description":"Serviços de franquia"}],"hasMore":False}
    g=Mock(return_value=retorno)
    resultado=diagnosticar_catalogo("token-ficticio",get=g)
    assert g.call_count == 4
    assert all(c.args[0].endswith("/fiscalInfo/nbsCodes") for c in g.call_args_list)
    assert all(c.kwargs["allow_redirects"] is False for c in g.call_args_list)
    assert resultado["franquia"]["correspondencias"][0]["codigo"]=="1.1110.00.00"

def test_sem_credencial_impede_consulta():
    g=Mock()
    assert diagnosticar_catalogo("",get=g)=={"resultado":"CHAVE_AUSENTE"}
    g.assert_not_called()

def test_recusa_http_400_somente_informa_codigo():
    g=Mock(return_value=Mock(status_code=400))
    resultado=diagnosticar_catalogo("token-ficticio",get=g)
    assert resultado["111100000"]=={"status":"HTTP_400"}
