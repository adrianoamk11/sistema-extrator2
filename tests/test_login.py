"""Teste isolado da tela de entrada, sem acionar cobranças ou Asaas."""
from streamlit.testing.v1 import AppTest


def test_login_exibe_campos_e_botao():
    app = AppTest.from_file("app.py", default_timeout=25).run()
    assert len(app.exception) == 0, [str(e.message) for e in app.exception]
    assert [campo.label for campo in app.text_input] == ["Usuário", "Senha"]
    assert any(botao.label == "Entrar" for botao in app.button)
    assert any("Acesso ao sistema" in titulo.value for titulo in app.title)
