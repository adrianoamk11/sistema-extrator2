"""Teste visual real com navegador e credenciais fictícias (somente CI)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.goto("http://127.0.0.1:8501", wait_until="networkidle")
    page.get_by_text("Acesso ao sistema").wait_for(timeout=30000)
    user = page.get_by_role("textbox", name="Usuário")
    password = page.locator('input[type="password"]')
    assert user.is_visible() and password.is_visible()
    ubox = user.bounding_box()
    pbox = password.bounding_box()
    assert ubox and pbox
    assert ubox["width"] < 700, f"Campo de usuário amplo demais: {ubox['width']}"
    assert pbox["width"] < 700, f"Campo de senha amplo demais: {pbox['width']}"
    assert abs(ubox["x"] - pbox["x"]) < 10
    Path("capturas").mkdir(exist_ok=True)
    page.screenshot(path="capturas/login-desktop.png", full_page=True)
    user.fill("usuario-incorreto")
    password.fill("senha-incorreta")
    page.get_by_role("button", name="Entrar").click()
    page.get_by_text("Usuário ou senha incorretos.").wait_for(timeout=15000)
    page.screenshot(path="capturas/login-validacao.png", full_page=True)
    browser.close()
