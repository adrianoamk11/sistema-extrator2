from unittest.mock import Mock
import pytest
from busca_clientes_cidade import normalizar_termo, corresponde_cidade, procurar_clientes_por_cidade


def test_acento_e_cityname_e_nome():
    assert normalizar_termo("Balneário Camboriú") == "balneario camboriu"
    assert corresponde_cidade({"cityName": "Balneário Camboriú", "name": "BOX 20"}, "balneario camboriu")
    assert corresponde_cidade({"cityName": "", "name": "BOX 25 JUNDIAÍ"}, "Jundiai")
    assert not corresponde_cidade({"cityName": "Jundiaí", "name": "BOX 20"}, "Itapema")
    assert not corresponde_cidade({"cityName": "Jundiaí", "name": "BOX 20"}, "jun")


def test_paginas_com_mais_de_um_cliente_sem_selecao_automatica():
    r1=Mock(status_code=200)
    r1.json.return_value={"data":[
        {"id":"cus_a", "name":"BOX 1", "cityName":"Itapema"},
        {"id":"cus_b", "name":"BOX 2", "cityName":"Itapema"},
        {"id":"cus_c", "name":"BOX 3", "cityName":"Jundiaí"},
    ],"hasMore":True}
    r2=Mock(status_code=200)
    r2.json.return_value={"data":[{"id":"cus_d","name":"BOX 4 Itapema"}],"hasMore":False}
    get=Mock(side_effect=[r1,r2])
    clientes=procurar_clientes_por_cidade("https://api.asaas.com/v3",{"access_token":"teste"}, "itapema", get)
    assert [c["id"] for c in clientes]==["cus_a","cus_b","cus_d"]
    assert all("cpfCnpj" not in c for c in clientes)
    assert get.call_count==2
    for call in get.call_args_list:
        assert call.args[0].endswith("/customers")
        assert "json" not in call.kwargs


def test_resposta_insegura_nao_gera_resultado_parcial():
    resposta=Mock(status_code=200)
    resposta.json.return_value={"data":[],"hasMore":True}
    with pytest.raises(RuntimeError,match="vazia"):
        procurar_clientes_por_cidade("https://api.asaas.com/v3",{}, "Itapema",Mock(return_value=resposta))


def test_busca_curta_nao_consulta():
    get=Mock()
    with pytest.raises(ValueError):
        procurar_clientes_por_cidade("https://api.asaas.com/v3",{}, "Jo",get)
    get.assert_not_called()
