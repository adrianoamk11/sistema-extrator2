"""Leitores específicos para extratos PagBank e Santander em PDF digital.

Não toca em pagamentos ou APIs. Nenhum dado de clientes é persistido.
Outros formatos continuam sob responsabilidade do leitor original.
"""
import re
import unicodedata
from datetime import date

DATA_LONGA = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\b")
MOEDA = re.compile(r"(?<![\d/])(?P<antes>-?\s*(?:R\$\s*)?)(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})(?P<depois>-?)(?!\d)")
MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return re.sub(r"\s+", " ", texto.encode("ascii", "ignore").decode("ascii")).lower()


def _dinheiro(encontrado):
    valor = float(encontrado.group("valor").replace(".", "").replace(",", "."))
    if "-" in encontrado.group("antes") or encontrado.group("depois") == "-":
        valor = -valor
    return valor


def _registro(data, descricao, valor):
    return {
        "Data": data,
        "Descrição": re.sub(r"\s+", " ", descricao).strip(),
        "Valor": valor,
        "Tipo do lançamento": "Crédito" if valor > 0 else "Débito",
    }


def detectar_layout(documento):
    texto = _normalizar(" ".join(p.get_text()[:2500] for p in list(documento)[:3]))
    if "pagseguro internet" in texto and "extrato da conta" in texto:
        return "pagbank"
    if "aplicativo santander empresas" in texto and "periodos:" in texto:
        return "santander_app"
    if ("extrato consolidado" in texto and "conta corrente" in texto
            and "movimentacao" in texto):
        return "santander_consolidado"
    return None


def _pagbank(documento):
    registros = []
    for pagina in documento:
        for bloco in pagina.get_text("blocks"):
            texto = bloco[4].strip()
            data = DATA_LONGA.match(texto)
            if not data or _normalizar(texto).startswith("saldo do dia"):
                continue
            valores = list(MOEDA.finditer(texto))
            if len(valores) != 1:
                continue
            descricao = texto[data.end():valores[0].start()].strip()
            if not descricao or "saldo do dia" in _normalizar(descricao):
                continue
            registros.append(_registro(data.group(1), descricao, _dinheiro(valores[0])))
    return registros


def _santander_app(documento):
    registros = []
    for pagina in documento:
        for bloco in pagina.get_text("blocks"):
            texto = bloco[4].strip()
            data = DATA_LONGA.match(texto)
            if not data:
                continue
            valores = list(MOEDA.finditer(texto))
            # Extrato do aplicativo: penúltimo valor = movimento; último = saldo.
            if len(valores) < 2:
                continue
            movimento = valores[-2]
            descricao = texto[data.end():movimento.start()].strip()
            if descricao:
                registros.append(_registro(data.group(1), descricao, _dinheiro(movimento)))
    return registros


def _spans(pagina):
    spans = []
    for bloco in pagina.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            for span in linha["spans"]:
                conteudo = span["text"].strip()
                if conteudo:
                    spans.append((
                        float(span["bbox"][0]),
                        float(span["bbox"][1]),
                        conteudo,
                    ))
    return spans


def _santander_consolidado(documento):
    # Outras tabelas do PDF (investimentos, saldos e resumos) são ignoradas.
    paginas = []
    for pagina in documento:
        texto = _normalizar(pagina.get_text()[:7500])
        if ("movimentos (r$)" in texto and "creditos" in texto
                and "debitos" in texto):
            paginas.append(pagina)
    if not paginas:
        raise ValueError("Tabela de movimentações Santander não encontrada")

    cabecalho = _normalizar(" ".join(p.get_text()[:1200] for p in documento))
    mes_ano = re.search(r"([a-z]+)/(20\d{2})", cabecalho)
    if not mes_ano or mes_ano.group(1) not in MESES:
        raise ValueError("Mês do extrato consolidado não identificado")
    mes, ano = MESES[mes_ano.group(1)], int(mes_ano.group(2))
    registros = []
    ultima_data = None

    for pagina in paginas:
        spans = _spans(pagina)
        datas = sorted(
            (y, t) for x, y, t in spans
            if x < 60 and re.fullmatch(r"\d{2}/\d{2}\s*", t)
        )
        if not datas:
            raise ValueError("Página de movimentações sem datas Santander")
        inicio_tabela = min(y for y, _ in datas)
        fim_tabela = min(
            (y for x, y, t in spans
             if 61 <= x < 310 and _normalizar(t).startswith("saldo em ")
             and y > inicio_tabela),
            default=float("inf"),
        )
        valores = []
        for x, y, t in spans:
            if y < inicio_tabela or y >= fim_tabela or not 355 <= x < 515:
                continue
            encontrado = MOEDA.fullmatch(t)
            if encontrado:
                valores.append((y, encontrado))
        valores.sort(key=lambda item: item[0])

        for pos, (y, encontrado) in enumerate(valores):
            candidatos = [
                (abs(ys - y), texto) for x, ys, texto in spans
                if 61 <= x < 310 and -7.5 <= ys - y <= 1.5
                and re.search(r"[A-Za-z]", texto)
            ]
            if not candidatos:
                continue
            distancia, descricao = min(candidatos, key=lambda item: item[0])
            if distancia > 5.5:
                continue
            limite = valores[pos + 1][0] - 2 if pos + 1 < len(valores) else y + 18
            complementos = [
                (ys, texto) for x, ys, texto in spans
                if 61 <= x < 310 and y + 2 <= ys < min(limite, y + 18)
                and re.search(r"[A-Za-z]", texto)
            ]
            if complementos:
                descricao += " " + " ".join(
                    texto for _, texto in sorted(complementos)
                )
            for yd, texto in datas:
                if yd <= y + 1.5:
                    ultima_data = texto.strip()
            if not ultima_data:
                raise ValueError("Movimentação sem data no extrato Santander")
            dia, mes_linha = map(int, ultima_data.split("/"))
            if mes_linha != mes:
                raise ValueError("Data da movimentação fora do mês do extrato")
            data_completa = date(ano, mes_linha, dia).strftime("%d/%m/%Y")
            registros.append(_registro(data_completa, descricao, _dinheiro(encontrado)))
    return registros


def extrair_pdf_bancario(documento):
    """Retorna None para PDFs desconhecidos, sem alterar o leitor legado."""
    layout = detectar_layout(documento)
    if layout is None:
        return None
    registros = {
        "pagbank": _pagbank,
        "santander_app": _santander_app,
        "santander_consolidado": _santander_consolidado,
    }[layout](documento)
    if not registros:
        raise ValueError(f"Nenhum lançamento legível no layout {layout}")
    return registros
