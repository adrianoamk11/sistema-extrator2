"""Regressão: consulta fiscal somente leitura não pode emitir notas nem cobranças."""
import ast
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests


def preparar_consulta(resposta):
    fonte = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    alvo = next(
        n for n in arvore.body
        if isinstance(n, ast.FunctionDef) and n.name == "consultar_nfse_asaas_por_cobranca"
    )
    cliente = Mock()
    cliente.get.return_value = resposta
    cliente.post.side_effect = AssertionError("POST não permitido para consulta fiscal")
    contexto = {
        "requests": cliente,
        "ASAAS_BASE_URL": "https://asaas.invalid/v3",
        "cabecalhos_asaas": lambda: {"access_token": "ficticio"},
    }
    exec(compile(ast.Module(body=[alvo], type_ignores=[]), "<consulta-nfse>", "exec"), contexto)
    return contexto["consultar_nfse_asaas_por_cobranca"], cliente


def retorno(dados, has_more=False):
    r = Mock()
    r.json.return_value = {"data": dados, "hasMore": has_more}
    return r


def test_nota_autorizada_somente_leitura():
    consulta, cliente = preparar_consulta(retorno([{"id": "inv_1", "payment": "pay_1", "status": "AUTHORIZED"}]))
    assert consulta("pay_1")[0]["status"] == "AUTHORIZED"
    cliente.get.assert_called_once()
    assert cliente.get.call_args.kwargs["params"] == {"payment": "pay_1", "limit": 100}
    cliente.post.assert_not_called()


def test_sem_nota_nao_emite_nada():
    consulta, cliente = preparar_consulta(retorno([]))
    assert consulta("pay_1") == []
    cliente.post.assert_not_called()


@pytest.mark.parametrize("dados,has_more", [
    ([{"id": "inv_2", "payment": "pay_diferente"}], False),
    ([], True),
])
def test_resposta_ambigua_bloqueada(dados, has_more):
    consulta, cliente = preparar_consulta(retorno(dados, has_more))
    with pytest.raises(RuntimeError):
        consulta("pay_1")
    cliente.post.assert_not_called()


def test_identificador_invalido_nao_consulta():
    consulta, cliente = preparar_consulta(retorno([]))
    with pytest.raises(ValueError):
        consulta("961543418")
    cliente.get.assert_not_called()
    cliente.post.assert_not_called()
