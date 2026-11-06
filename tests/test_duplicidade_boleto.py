"""Testa deduplicação sem importar Streamlit e sem chamar a API do Asaas."""
import ast
from datetime import date
from pathlib import Path
from unittest.mock import Mock
import pytest


def carregar_funcao_boleto(busca):
    fonte = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    alvo = next(no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == "emitir_boleto_asaas")
    funcao = compile(ast.Module(body=[alvo], type_ignores=[]), "<teste-boleto>", "exec")
    contexto = {
        "localizar_cliente_asaas_por_box": lambda _: ({"id": "cus_teste", "name": "Teste"}, 1),
        "padronizar_notificacoes_asaas": lambda _: None,
        "criar_referencia_externa": lambda *args: "lider-royalties-mesma-operacao",
        "buscar_cobranca_existente": busca,
        "formatar_moeda": str,
        "ASAAS_BASE_URL": "https://asaas.invalid/v3",
        "cabecalhos_asaas": lambda: {},
        "requests": Mock(),
    }
    exec(funcao, contexto)
    return contexto["emitir_boleto_asaas"], contexto["requests"]


@pytest.mark.parametrize("emite_nota", [True, False])
def test_opcao_nota_diferente_impede_segunda_cobranca(emite_nota):
    referencia_anterior = (
        "lider-royalties-mesma-operacao" if emite_nota
        else "lider-royalties-mesma-operacao|NFSE|"
    )
    def buscar(referencia):
        return {"id": "pay_existente"} if referencia == referencia_anterior else None
    emitir, requests = carregar_funcao_boleto(buscar)
    with pytest.raises(RuntimeError, match="Já existe uma cobrança"):
        emitir("BOX 1.xlsx", 100, 4, date(2026, 11, 10), "Royalties", emite_nota)
    requests.post.assert_not_called()


def test_mesma_referencia_reaproveita_cobranca():
    def buscar(referencia):
        return {"id": "pay_existente", "status": "CONFIRMED"} if referencia.endswith("|NFSE|") else None
    emitir, requests = carregar_funcao_boleto(buscar)
    resultado = emitir("BOX 1.xlsx", 100, 4, date(2026, 11, 10), "Royalties", True)
    assert resultado["novo"] is False
    assert resultado["id"] == "pay_existente"
    requests.post.assert_not_called()
