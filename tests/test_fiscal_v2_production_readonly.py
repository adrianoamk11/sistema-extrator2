"""Prova que a integração com Asaas de produção é somente GET e não lê dados."""
from unittest.mock import Mock

import requests

from fiscal_v2_production_readonly import CAMINHOS_PERMITIDOS, PROD_API, diagnosticar_producao


def test_usa_exclusivamente_get_em_rotas_permitidas():
    get = Mock(side_effect=[
        Mock(status_code=200),
        Mock(status_code=200),
        Mock(status_code=200),
    ])
    resultados = diagnosticar_producao(chave="chave-ficticia", get=get)
    assert all(valor == "OK" for valor in resultados.values())
    assert get.call_count == 3
    assert [chamada.args[0] for chamada in get.call_args_list] == [
        PROD_API + rota for _, rota in CAMINHOS_PERMITIDOS
    ]
    assert all(chamada.kwargs["allow_redirects"] is False for chamada in get.call_args_list)


def test_sem_chave_nunca_acessa_conta():
    get = Mock()
    assert all(
        valor == "CHAVE_AUSENTE"
        for valor in diagnosticar_producao(chave="", get=get).values()
    )
    get.assert_not_called()


def test_erro_http_nao_vaza_corpo_e_dados():
    get = Mock(side_effect=[
        Mock(status_code=401, text="SEGREDO"),
        Mock(status_code=404, text="DADOS"),
        Mock(status_code=403, text="CLIENTES"),
    ])
    resultado = diagnosticar_producao(chave="ficticia", get=get)
    assert resultado == {
        "autenticacao": "ACESSO_NEGADO",
        "configuracao_fiscal": "HTTP_404",
        "consulta_notas": "ACESSO_NEGADO",
    }
    assert "SEGREDO" not in repr(resultado)


def test_timeout_nao_repete_mutacoes():
    get = Mock(side_effect=requests.Timeout("segredo"))
    resultado = diagnosticar_producao(chave="ficticia", get=get)
    assert list(resultado.values()) == ["SEM_RESPOSTA"] * 3
