"""Testes com PDFs sintéticos: não versionar extratos bancários de clientes."""
import fitz
from extratos_bancos_pdf import detectar_layout, extrair_pdf_bancario


def pdf():
    documento = fitz.open()
    return documento, documento.new_page()


def test_pagbank_vendas_e_debitos_sem_saldo():
    doc, pagina = pdf()
    pagina.insert_text((30, 40), "290 - PagSeguro Internet S/A\nExtrato da conta")
    pagina.insert_text((30, 100), "02/10/2026\nVendas - Disponivel PIX\nR$ 980,20")
    pagina.insert_text((30, 210), "02/10/2026\nPix enviado - fornecedor\n-R$ 980,00")
    pagina.insert_text((30, 320), "Saldo do dia\n02/10/2026\nR$ 12.800,00")
    assert detectar_layout(doc) == "pagbank"
    registros = extrair_pdf_bancario(doc)
    assert [r["Valor"] for r in registros] == [980.2, -980.0]
    assert registros[0]["Tipo do lançamento"] == "Crédito"
    assert registros[1]["Tipo do lançamento"] == "Débito"


def test_santander_app_valor_movimentacao_nao_saldo():
    doc, pagina = pdf()
    pagina.insert_text(
        (30, 40),
        "Aplicativo Santander Empresas\nPeriodos: 01/09/2026 a 30/09/2026",
    )
    pagina.insert_text((30, 100), "01/09/2026 Pix Recebido 124578\n1.000,40\n51.000,40")
    pagina.insert_text((30, 210), "01/09/2026 Pix Enviado Fornecedor\n-500,00\n50.500,40")
    assert detectar_layout(doc) == "santander_app"
    registros = extrair_pdf_bancario(doc)
    assert [r["Valor"] for r in registros] == [1000.4, -500.0]
    assert len(registros) == 2


def test_santander_consolidado_isola_movimentos_do_resumo():
    doc, pagina = pdf()
    pagina.insert_text((30, 30), "EXTRATO CONSOLIDADO outubro/2026")
    pagina.insert_text((30, 48), "Conta Corrente\nMovimentacao")
    pagina.insert_text((65, 75), "Movimentos (R$) Creditos Debitos")
    pagina.insert_text((65, 95), "Saldo de Conta Corrente")
    pagina.insert_text((376, 95), "99.999,00")
    pagina.insert_text((34, 120), "01/10", fontsize=7)
    pagina.insert_text((65, 120), "PIX RECEBIDO CLIENTE", fontsize=7)
    pagina.insert_text((376, 120), "1.200,00", fontsize=7)
    pagina.insert_text((530, 120), "0,00", fontsize=7)
    pagina.insert_text((65, 145), "RESGATE CONTAMAX AUTOMATICO")
    pagina.insert_text((376, 145), "3.400,00")
    pagina.insert_text((65, 170), "PIX ENVIADO FORNECEDOR")
    pagina.insert_text((420, 170), "800,00-")
    pagina.insert_text((65, 195), "SALDO EM 31/10")
    assert detectar_layout(doc) == "santander_consolidado"
    registros = extrair_pdf_bancario(doc)
    assert [r["Valor"] for r in registros] == [1200.0, 3400.0, -800.0]
    assert all(r["Data"] == "01/10/2026" for r in registros)


def test_outros_pdfs_permanecem_no_leitor_anterior():
    doc, pagina = pdf()
    pagina.insert_text((50, 50), "Extrato bancario de outro formato")
    assert detectar_layout(doc) is None
    assert extrair_pdf_bancario(doc) is None
