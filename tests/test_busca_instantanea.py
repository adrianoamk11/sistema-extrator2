from unittest.mock import Mock

import pytest

from busca_clientes_cidade import (
    filtrar_autocomplete,
    listar_clientes_para_autocomplete,
)


CLIENTES = [
    {"id": "cus_a", "name": "BOX 25 Balneário Camboriú", "cityName": ""},
    {"id": "cus_b", "name": "BOX 250 Cidade", "cityName": "Itapema"},
    {"id": "cus_c", "name": "BOX 30", "cityName": "Jundiaí"},
    {"id": "cus_d", "name": "BOX 35", "cityName": "Balneário Camboriú"},
    {"id": "cus_e", "name": "BOX 025", "cityName": "São Paulo"},
]


def test_busca_box_incremental_e_multiplas_sugestoes():
    assert [c["id"] for c in filtrar_autocomplete(CLIENTES, "2", "BOX")] == [
        "cus_a", "cus_b", "cus_e"
    ]
    assert [c["id"] for c in filtrar_autocomplete(CLIENTES, "25", "BOX")] == [
        "cus_a", "cus_b", "cus_e"
    ]
    assert [c["id"] for c in filtrar_autocomplete(CLIENTES, "30", "BOX")] == [
        "cus_c"
    ]
    assert filtrar_autocomplete(CLIENTES, "", "BOX") == []


def test_busca_cidade_parcial_sem_acentos():
    assert [c["id"] for c in filtrar_autocomplete(CLIENTES, "balne", "Cidade")] == [
        "cus_a", "cus_d"
    ]
    assert [c["id"] for c in filtrar_autocomplete(CLIENTES, "itap", "Cidade")] == [
        "cus_b"
    ]
    assert [c["id"] for c in filtrar_autocomplete(CLIENTES, "Jundi", "Cidade")] == [
        "cus_c"
    ]
    assert filtrar_autocomplete(CLIENTES, "a", "Cidade") == []


def test_lista_de_clientes_somente_get_sem_dados_sensiveis():
    primeira = Mock()
    primeira.json.return_value = {
        "data": [{**CLIENTES[0], "cpfCnpj": "nao_expor"}],
        "hasMore": True,
    }
    segunda = Mock()
    segunda.json.return_value = {"data": CLIENTES[1:], "hasMore": False}
    get = Mock(side_effect=[primeira, segunda])
    lista = listar_clientes_para_autocomplete(
        "https://api.asaas.com/v3", {"access_token": "teste"}, get=get,
    )
    assert len(lista) == 5
    assert all("cpfCnpj" not in item for item in lista)
    assert get.call_count == 2
    assert all(
        chamada.args[0] == "https://api.asaas.com/v3/customers"
        for chamada in get.call_args_list
    )
    assert all("json" not in chamada.kwargs for chamada in get.call_args_list)


def test_listagem_invalida_nao_retorna_parcial():
    resposta = Mock()
    resposta.json.return_value = {"data": [], "hasMore": True}
    with pytest.raises(RuntimeError, match="vazia"):
        listar_clientes_para_autocomplete("https://api.asaas.com/v3", {}, get=Mock(return_value=resposta))
