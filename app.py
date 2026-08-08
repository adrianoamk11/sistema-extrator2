
import streamlit as st
import pandas as pd
import fitz
import re
import unicodedata
import requests
import hashlib
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from io import BytesIO
from pathlib import Path

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Extrator de Faturamento",
    page_icon="💰",
    layout="wide"
)
# =========================
# LOGIN DO SISTEMA
# =========================

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("Acesso ao sistema")

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if (
            usuario == st.secrets["LOGIN_USUARIO"]
            and senha == st.secrets["LOGIN_SENHA"]
        ):
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

    st.stop()
st.markdown("""
<style>
/* Encosta o conteúdo no topo da página */
[data-testid="stAppViewContainer"] .main .block-container {
    padding-top: 0rem !important;
    margin-top: 0rem !important;
}
[data-testid="stMainBlockContainer"] {
    padding-top: 0rem !important;
    margin-top: 0rem !important;
}
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo_lider.png"

# ============================================================
# CABEÇALHO
# ============================================================

if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width=360)

# Reduz aproximadamente pela metade o espaço entre a logo e o título.
st.markdown(
    """
    <meta name="google" content="notranslate">
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] * {
        -webkit-translate: none !important;
    }
    .notranslate {
        translate: no !important;
    }
    div[data-testid="stImage"] {
        margin-bottom: -105px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Extrator de Faturamento")
st.caption("LÍDER Aluguel de Motos • PDF, Excel (.xlsx/.xls) e CSV")

st.divider()

# ============================================================
# CONFIGURAÇÕES
# ============================================================

PERCENTUAL_ROYALTIES = 0.04

# ============================================================
# ASAAS - SELEÇÃO DA EMPRESA
# ============================================================

st.write("Selecione a empresa que deseja utilizar:")

col_empresa, _ = st.columns([1, 5])

with col_empresa:
    EMPRESA_SELECIONADA = st.selectbox(
        "Empresa",
        ["Lider Franquia", "Lider Serviços"],
        label_visibility="collapsed"
    )

if EMPRESA_SELECIONADA == "Lider Franquia":
    ASAAS_API_KEY = st.secrets["ASAAS_LIDER_FRANQUIA_API_KEY"]
else:
    ASAAS_API_KEY = st.secrets["ASAAS_LIDER_SERVICOS_API_KEY"]

ASAAS_BASE_URL = st.secrets["ASAAS_PRODUCAO_BASE_URL"].rstrip("/")

def proximo_dia_10():
    hoje = date.today()

    if hoje.day <= 10:
        return date(hoje.year, hoje.month, 10)

    proximo_mes = hoje + relativedelta(months=1)
    return date(proximo_mes.year, proximo_mes.month, 10)


def cabecalhos_asaas():
    return {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json",
    }

def extrair_numero_box(texto):
    """
    Extrai o número após a palavra BOX.
    Exemplos:
    'BOX 25.xlsx' -> 25
    'Box 025 Julho.xlsx' -> 25
    'mendel box 025 zona norte' -> 25
    """
    texto_norm = normalizar(texto)
    encontrado = re.search(r"\bbox\s*[-_:]?\s*0*(\d+)\b", texto_norm)

    if not encontrado:
        return None

    return int(encontrado.group(1))


def localizar_cliente_asaas_por_box(nome_arquivo):
    """
    Localiza o cliente do Asaas usando somente o número do BOX
    encontrado no nome do arquivo.

    Exemplo:
    Arquivo: 'Extrato BOX 25 Julho.xlsx'
    Cliente Asaas: 'mendel box 025 zona norte'

    Ambos correspondem ao BOX 25.
    """
    numero_box = extrair_numero_box(Path(nome_arquivo).stem)

    if numero_box is None:
        raise RuntimeError(
            "Não encontrei o número do BOX no nome do arquivo. "
            "Renomeie o arquivo incluindo, por exemplo, 'BOX 25'."
        )

    encontrados = []
    offset = 0
    limite = 100

    while True:
        resposta = requests.get(
            f"{ASAAS_BASE_URL}/customers",
            headers=cabecalhos_asaas(),
            params={
                "offset": offset,
                "limit": limite,
            },
            timeout=30,
        )

        if not resposta.ok:
            try:
                detalhe = resposta.json()
            except Exception:
                detalhe = resposta.text

            raise RuntimeError(
                f"Erro ao consultar clientes no Asaas "
                f"(HTTP {resposta.status_code}): {detalhe}"
            )

        corpo = resposta.json()
        clientes = corpo.get("data", [])

        for cliente in clientes:
            nome_asaas = str(cliente.get("name", ""))
            box_cliente = extrair_numero_box(nome_asaas)

            if box_cliente == numero_box:
                encontrados.append(cliente)

        if not corpo.get("hasMore"):
            break

        offset += limite

    if len(encontrados) == 1:
        return encontrados[0], numero_box

    if len(encontrados) == 0:
        raise RuntimeError(
            f"Não encontrei no Asaas nenhum cliente com BOX {numero_box}. "
            f"Confira se o cadastro do cliente contém 'BOX {numero_box}' "
            f"no campo Nome."
        )

    nomes = " | ".join(
        str(cliente.get("name", ""))
        for cliente in encontrados[:5]
    )

    raise RuntimeError(
        f"Encontrei {len(encontrados)} clientes com BOX {numero_box}: {nomes}. "
        f"Para evitar cobrança no cliente errado, a emissão foi bloqueada. "
        f"Deixe apenas um cadastro correspondente a esse BOX."
    )



def recuperar_notificacoes_cliente(customer_id):
    """
    Recupera todas as notificações já existentes do cliente no Asaas.
    """
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/customers/{customer_id}/notifications",
        headers=cabecalhos_asaas(),
        timeout=30,
    )

    if not resposta.ok:
        try:
            detalhe = resposta.json()
        except Exception:
            detalhe = resposta.text

        raise RuntimeError(
            f"Não foi possível consultar as notificações do cliente "
            f"(HTTP {resposta.status_code}): {detalhe}"
        )

    corpo = resposta.json()

    # A resposta normalmente vem em "data", mas mantemos compatibilidade
    # caso o endpoint retorne diretamente uma lista.
    if isinstance(corpo, list):
        return corpo

    return corpo.get("data", [])


def configuracao_base_notificacao(notificacao):
    """
    Desliga canais que não fazem parte do padrão Líder.
    """
    return {
        "id": notificacao["id"],
        "enabled": False,
        "emailEnabledForProvider": False,
        "smsEnabledForProvider": False,
        "emailEnabledForCustomer": False,
        "smsEnabledForCustomer": False,
        "phoneCallEnabledForCustomer": False,
        "whatsappEnabledForCustomer": False,
    }


def padronizar_notificacoes_asaas(customer_id):
    """
    Padrão Líder para o pagador:

    1. Cobrança criada:
       - E-mail

    2. Dia do vencimento:
       - E-mail
       - WhatsApp

    3. Um dia após o vencimento:
       - E-mail

    Demais notificações:
       - Desativadas
       - SMS desativado
       - Ligação desativada
    """
    notificacoes = recuperar_notificacoes_cliente(customer_id)

    if not notificacoes:
        raise RuntimeError(
            "O Asaas não retornou notificações para este cliente."
        )

    atualizacoes = []

    for notificacao in notificacoes:
        evento = str(notificacao.get("event", "")).upper()
        offset_atual = notificacao.get("scheduleOffset", 0)

        try:
            offset_atual = int(offset_atual or 0)
        except Exception:
            offset_atual = 0

        config = configuracao_base_notificacao(notificacao)

        # 1) No momento da criação: apenas e-mail.
        if evento == "PAYMENT_CREATED":
            config.update({
                "enabled": True,
                "emailEnabledForCustomer": True,
                "scheduleOffset": 0,
            })

        # 2) No dia do vencimento: e-mail + WhatsApp.
        elif evento == "PAYMENT_DUEDATE_WARNING" and offset_atual == 0:
            config.update({
                "enabled": True,
                "emailEnabledForCustomer": True,
                "whatsappEnabledForCustomer": True,
                "scheduleOffset": 0,
            })

        # Avisos antecipados (ex.: 10 dias antes): desligados.
        elif evento == "PAYMENT_DUEDATE_WARNING" and offset_atual != 0:
            config.update({
                "enabled": False,
                "scheduleOffset": offset_atual,
            })

        # 3) Aviso periódico depois do vencimento:
        # pega a notificação que já possui offset (>0) e muda para 1 dia.
        elif evento == "PAYMENT_OVERDUE" and offset_atual > 0:
            config.update({
                "enabled": True,
                "emailEnabledForCustomer": True,
                "scheduleOffset": 1,
            })

        # Aviso imediato de atraso/falha: desligado.
        elif evento == "PAYMENT_OVERDUE" and offset_atual == 0:
            config.update({
                "enabled": False,
                "scheduleOffset": 0,
            })

        # Pagamento confirmado e demais eventos ficam desativados.
        # Linha digitável, alteração de cobrança e quaisquer outros
        # eventos ficam desativados para evitar mensagens duplicadas.
        else:
            if "scheduleOffset" in notificacao:
                config["scheduleOffset"] = offset_atual

        atualizacoes.append(config)

    payload = {
        "customer": customer_id,
        "notifications": atualizacoes,
    }

    resposta = requests.put(
        f"{ASAAS_BASE_URL}/notifications/batch",
        headers=cabecalhos_asaas(),
        json=payload,
        timeout=30,
    )

    if not resposta.ok:
        try:
            detalhe = resposta.json()
        except Exception:
            detalhe = resposta.text

        raise RuntimeError(
            f"Não foi possível configurar as notificações no Asaas "
            f"(HTTP {resposta.status_code}): {detalhe}"
        )

    return True


def criar_referencia_externa(nome_arquivo, valor, vencimento, descricao=""):
    base = (
        f"{nome_arquivo}|{valor:.2f}|{vencimento.isoformat()}|"
        f"{str(descricao).strip()}"
    )
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    return f"lider-royalties-{digest}"

def buscar_cobranca_existente(external_reference):
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/payments",
        headers=cabecalhos_asaas(),
        params={"externalReference": external_reference},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json().get("data", [])
    return dados[0] if dados else None

def emitir_boleto_asaas(
    nome_arquivo,
    faturamento,
    valor_cobranca,
    vencimento,
    descricao_boleto
):
    cliente, numero_box = localizar_cliente_asaas_por_box(nome_arquivo)
    customer_id = cliente.get("id")
    nome_cliente = cliente.get("name", "")

    if not customer_id:
        raise RuntimeError(
            f"O cliente do BOX {numero_box} foi encontrado, "
            f"mas o Asaas não retornou um ID válido."
        )

    # Antes de emitir a cobrança, aplica automaticamente
    # o padrão de notificações definido pela Líder.
    padronizar_notificacoes_asaas(customer_id)

    descricao_final = str(descricao_boleto or "").strip()

    if not descricao_final:
        descricao_final = (
            "Royalties"
            f"Faturamento {formatar_moeda(faturamento)}"
        )

    external_reference = criar_referencia_externa(
        nome_arquivo,
        valor_cobranca,
        vencimento,
        descricao_final
    )

    existente = buscar_cobranca_existente(external_reference)
    if existente:
        return {
            "novo": False,
            "clienteNome": cliente.get("name"),
            "clienteId": customer_id,
            "box": numero_box,
            "id": existente.get("id"),
            "invoiceUrl": existente.get("invoiceUrl"),
            "bankSlipUrl": existente.get("bankSlipUrl"),
            "status": existente.get("status"),
            "externalReference": external_reference,
        }

    payload = {
        "customer": customer_id,
        "billingType": "BOLETO",
        "value": round(float(valor_cobranca), 2),
        "dueDate": vencimento.isoformat(),
        "description": descricao_final[:500],
        "externalReference": external_reference,
    }

    resposta = requests.post(
        f"{ASAAS_BASE_URL}/payments",
        headers=cabecalhos_asaas(),
        json=payload,
        timeout=30,
    )

    if not resposta.ok:
        try:
            detalhe = resposta.json()
        except Exception:
            detalhe = resposta.text
        raise RuntimeError(
            f"Asaas retornou HTTP {resposta.status_code}: {detalhe}"
        )

    dados = resposta.json()

    return {
        "novo": True,
        "clienteNome": cliente.get("name"),
        "clienteId": customer_id,
        "box": numero_box,
        "id": dados.get("id"),
        "invoiceUrl": dados.get("invoiceUrl"),
        "bankSlipUrl": dados.get("bankSlipUrl"),
        "status": dados.get("status"),
        "externalReference": external_reference,
    }

PALAVRAS_FATURAMENTO = [
    "cobranca recebida",
    "pagamento recebido",
    "recebimento",
    "pix recebido",
    "credito de cliente",
    "venda",
    "fatura recebida",
    "boleto recebido",
]

PALAVRAS_IGNORAR = [
    "saldo inicial",
    "saldo final",
    "saldo anterior",
    "saldo disponivel",
    "saldo bloqueado",
    "taxa",
    "tarifa",
    "mensageria",
    "notificacao",
]

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar(texto):
    texto = "" if texto is None else str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto).strip().lower()


def converter_numero(valor):
    if pd.isna(valor):
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace(" ", "")

    if not texto:
        return None

    try:
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        return float(texto)
    except Exception:
        return None


def formatar_moeda(valor):
    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def achar_coluna(colunas, nomes_possiveis):
    mapa = {col: normalizar(col) for col in colunas}

    # Primeiro tenta igualdade exata
    for nome in nomes_possiveis:
        alvo = normalizar(nome)
        for original, atual in mapa.items():
            if atual == alvo:
                return original

    # Depois tenta ocorrência parcial
    for nome in nomes_possiveis:
        alvo = normalizar(nome)
        for original, atual in mapa.items():
            if alvo in atual:
                return original

    return None


# ============================================================
# LEITURA DE EXCEL / CSV
# ============================================================

def encontrar_linha_cabecalho_excel(arquivo, engine):
    """
    Procura automaticamente a linha de cabeçalho.
    Útil para extratos Asaas que possuem informações antes da tabela.
    """
    arquivo.seek(0)

    bruto = pd.read_excel(
        arquivo,
        engine=engine,
        header=None,
        nrows=30
    )

    palavras = [
        "data",
        "tipo de transacao",
        "descricao",
        "valor",
        "saldo",
        "tipo do lancamento",
    ]

    melhor_linha = 0
    melhor_pontuacao = -1

    for indice, linha in bruto.iterrows():
        texto = " | ".join(
            normalizar(valor)
            for valor in linha.tolist()
            if not pd.isna(valor)
        )

        pontuacao = sum(
            1 for palavra in palavras
            if normalizar(palavra) in texto
        )

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_linha = indice

    return int(melhor_linha)


def preparar_layout_asaas(df):
    """
    Tratamento específico do Excel exportado pelo Asaas.

    IMPORTANTE:
    - Usa a coluna VALOR para o valor da movimentação.
    - Usa Tipo do lançamento para Crédito/Débito.
    - NÃO usa a coluna Saldo como faturamento.
    """
    colunas = list(df.columns)

    col_data = achar_coluna(colunas, ["Data"])
    col_tipo = achar_coluna(colunas, ["Tipo de transação"])
    col_descricao = achar_coluna(colunas, ["Descrição"])
    col_valor = achar_coluna(colunas, ["Valor"])
    col_tipo_lancamento = achar_coluna(
        colunas,
        ["Tipo do lançamento"]
    )

    if col_valor is None or col_tipo_lancamento is None:
        return None

    resultado = pd.DataFrame()

    if col_data:
        resultado["Data"] = df[col_data].astype(str)
    else:
        resultado["Data"] = ""

    tipo = (
        df[col_tipo].fillna("").astype(str)
        if col_tipo else ""
    )

    descricao = (
        df[col_descricao].fillna("").astype(str)
        if col_descricao else ""
    )

    if col_tipo and col_descricao:
        resultado["Descrição"] = (
            tipo.str.strip()
            + " - "
            + descricao.str.strip()
        )
    elif col_tipo:
        resultado["Descrição"] = tipo.str.strip()
    elif col_descricao:
        resultado["Descrição"] = descricao.str.strip()
    else:
        resultado["Descrição"] = ""

    resultado["Valor"] = df[col_valor].apply(
        converter_numero
    )

    resultado["Tipo do lançamento"] = (
        df[col_tipo_lancamento]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    resultado = resultado[
        resultado["Valor"].notna()
    ].copy()

    resultado = resultado[
        resultado["Tipo do lançamento"].str.len() > 0
    ].copy()

    return resultado


def preparar_layout_generico(df):
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    col_data = achar_coluna(
        df.columns,
        [
            "data",
            "date",
            "data movimentacao",
            "data lancamento",
        ],
    )

    col_descricao = achar_coluna(
        df.columns,
        [
            "descricao",
            "historico",
            "lancamento",
            "movimentacao",
            "detalhes",
        ],
    )

    col_valor = achar_coluna(
        df.columns,
        [
            "valor",
            "amount",
            "valor movimentacao",
            "valor lancamento",
        ],
    )

    col_credito = achar_coluna(
        df.columns,
        ["credito", "entrada", "creditos"],
    )

    if col_descricao is None:
        colunas_texto = [
            col for col in df.columns
            if df[col].dtype == "object"
        ]

        if colunas_texto:
            df["_descricao_auto"] = (
                df[colunas_texto]
                .fillna("")
                .astype(str)
                .agg(" | ".join, axis=1)
            )
        else:
            df["_descricao_auto"] = ""

        col_descricao = "_descricao_auto"

    if col_data is None:
        df["_data_auto"] = ""
        col_data = "_data_auto"

    if col_valor is not None:
        valores = df[col_valor].apply(converter_numero)
    elif col_credito is not None:
        valores = df[col_credito].apply(converter_numero)
    else:
        raise ValueError(
            "Não encontrei uma coluna de valor da movimentação. "
            "O sistema não usará a coluna Saldo para evitar cálculo incorreto."
        )

    resultado = pd.DataFrame({
        "Data": df[col_data].astype(str),
        "Descrição": df[col_descricao].astype(str),
        "Valor": valores,
    })

    return resultado[
        resultado["Valor"].notna()
    ].copy()


def ler_excel_ou_csv(arquivo):
    nome = arquivo.name.lower()

    if nome.endswith(".xlsx"):
        cabecalho = encontrar_linha_cabecalho_excel(
            arquivo,
            "openpyxl"
        )

        arquivo.seek(0)

        df = pd.read_excel(
            arquivo,
            engine="openpyxl",
            header=cabecalho
        )

        asaas = preparar_layout_asaas(df)

        if asaas is not None:
            return asaas

        return preparar_layout_generico(df)

    if nome.endswith(".xls"):
        cabecalho = encontrar_linha_cabecalho_excel(
            arquivo,
            "xlrd"
        )

        arquivo.seek(0)

        df = pd.read_excel(
            arquivo,
            engine="xlrd",
            header=cabecalho
        )

        asaas = preparar_layout_asaas(df)

        if asaas is not None:
            return asaas

        return preparar_layout_generico(df)

    # CSV
    bruto = arquivo.getvalue()

    for encoding in ["utf-8-sig", "utf-8", "latin1"]:
        for separador in [";", ",", "\t"]:
            try:
                df = pd.read_csv(
                    BytesIO(bruto),
                    sep=separador,
                    encoding=encoding
                )

                if df.shape[1] > 1:
                    asaas = preparar_layout_asaas(df)

                    if asaas is not None:
                        return asaas

                    return preparar_layout_generico(df)

            except Exception:
                pass

    raise ValueError(
        "Não consegui interpretar o arquivo CSV."
    )


# ============================================================
# LEITURA DE PDF
# ============================================================

def ler_pdf(arquivo):
    documento = fitz.open(
        stream=arquivo.getvalue(),
        filetype="pdf"
    )

    linhas = []

    for pagina in documento:
        linhas += [
            re.sub(r"\s+", " ", linha).strip()
            for linha in pagina.get_text().splitlines()
            if linha.strip()
        ]

    padrao_data = re.compile(
        r"\b(\d{2}/\d{2}/\d{4})\b"
    )

    padrao_valor = re.compile(
        r"R\$\s*(-?[\d\.]+,\d{2})"
    )

    data_atual = ""
    contexto = []
    registros = []

    for linha in linhas:
        datas = padrao_data.findall(linha)

        if datas:
            data_atual = datas[0]

        valores = padrao_valor.findall(linha)

        for valor_texto in valores:
            descricao = " ".join(
                contexto[-3:] + [linha]
            )

            descricao = padrao_valor.sub(
                "",
                descricao
            ).strip()

            registros.append({
                "Data": data_atual,
                "Descrição": descricao,
                "Valor": converter_numero(valor_texto),
            })

        contexto.append(linha)

    if not registros:
        raise ValueError(
            "Não encontrei movimentações legíveis neste PDF."
        )

    return pd.DataFrame(registros)


# ============================================================
# CLASSIFICAÇÃO DO FATURAMENTO
# ============================================================

def classificar_movimentacao(
    descricao,
    valor,
    tipo_lancamento=""
):
    descricao_normalizada = normalizar(descricao)
    lancamento_normalizado = normalizar(
        tipo_lancamento
    )

    if valor is None:
        return "IGNORAR", False

    # Excel Asaas: Crédito/Débito explícito
    if lancamento_normalizado:
        if "debito" in lancamento_normalizado:
            return "SAÍDA", False

        if "credito" in lancamento_normalizado:
            if any(
                palavra in descricao_normalizada
                for palavra in PALAVRAS_FATURAMENTO
            ):
                return "FATURAMENTO", True

            # Crédito não identificado automaticamente:
            # fica disponível para revisão manual.
            return "REVISAR", False

    # PDFs e formatos sem Crédito/Débito explícito
    if valor <= 0:
        return "SAÍDA", False

    if any(
        palavra in descricao_normalizada
        for palavra in PALAVRAS_IGNORAR
    ):
        return "IGNORAR", False

    if any(
        palavra in descricao_normalizada
        for palavra in PALAVRAS_FATURAMENTO
    ):
        return "FATURAMENTO", True

    return "REVISAR", False


def processar_arquivo(arquivo):
    if arquivo.name.lower().endswith(".pdf"):
        dados = ler_pdf(arquivo)
    else:
        dados = ler_excel_ou_csv(arquivo)

    if "Tipo do lançamento" in dados.columns:
        classificacao = dados.apply(
            lambda linha: classificar_movimentacao(
                linha["Descrição"],
                linha["Valor"],
                linha["Tipo do lançamento"],
            ),
            axis=1,
        )
    else:
        classificacao = dados.apply(
            lambda linha: classificar_movimentacao(
                linha["Descrição"],
                linha["Valor"],
            ),
            axis=1,
        )

    dados["Classificação"] = [
        item[0] for item in classificacao
    ]

    dados["Considerar"] = [
        item[1] for item in classificacao
    ]

    return dados


# ============================================================
# EXPORTAÇÃO DO RELATÓRIO GERAL
# ============================================================

def nome_aba_excel(nome, usados):
    nome = re.sub(
        r'[\[\]\:\*\?\/\\]',
        "_",
        nome
    )

    nome = nome[:31] or "Extrato"

    original = nome
    contador = 2

    while nome in usados:
        sufixo = f"_{contador}"
        nome = original[:31-len(sufixo)] + sufixo
        contador += 1

    usados.add(nome)

    return nome


def gerar_excel_geral(resumo, detalhes):
    arquivo_excel = BytesIO()

    with pd.ExcelWriter(
        arquivo_excel,
        engine="openpyxl"
    ) as writer:

        resumo_exportar = resumo.copy()

        resumo_exportar.to_excel(
            writer,
            index=False,
            sheet_name="Resumo Geral"
        )

        usados = {"Resumo Geral"}

        for nome_arquivo, tabela in detalhes.items():
            aba = nome_aba_excel(
                Path(nome_arquivo).stem,
                usados
            )

            tabela.to_excel(
                writer,
                index=False,
                sheet_name=aba
            )

        # Ajustes simples de largura
        for ws in writer.book.worksheets:
            ws.column_dimensions["A"].width = 25
            ws.column_dimensions["B"].width = 60
            ws.column_dimensions["C"].width = 18
            ws.column_dimensions["D"].width = 20
            ws.column_dimensions["E"].width = 14

    arquivo_excel.seek(0)

    return arquivo_excel


# ============================================================
# INTERFACE
# ============================================================

# ============================================================
# TAMANHO DO RESUMO CLICÁVEL POR ARQUIVO
# ============================================================
st.markdown(
    """
    <style>
    div[data-testid="stExpander"] summary p,
    div[data-testid="stExpander"] summary p * {
        font-size: 20px !important;
        line-height: 1.45 !important;
    }

    div[data-testid="stExpander"] summary p {
        color: #262730 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

arquivos = st.file_uploader(
    "Carregue os extratos",
    type=["pdf", "xlsx", "xls", "csv"],
    accept_multiple_files=True,
    help="Você pode selecionar vários arquivos de uma só vez.",
    key=f"uploader_{st.session_state.uploader_key}"
)

if arquivos:
    if st.button(
        "🗑️ Limpar todos os arquivos",
        type="secondary",
        help="Remove todos os extratos carregados desta remessa."
    ):
        st.session_state.uploader_key += 1

        # Limpa também os editores das remessas anteriores.
        chaves_para_apagar = [
            chave
            for chave in list(st.session_state.keys())
            if str(chave).startswith("editor_")
        ]

        for chave in chaves_para_apagar:
            del st.session_state[chave]

        st.rerun()

if not arquivos:
    st.info(
        "Selecione um ou vários arquivos PDF, Excel ou CSV para começar."
    )

else:
    st.success(
        f"{len(arquivos)} arquivo(s) carregado(s)."
    )

    resultados = []
    detalhes_exportacao = {}

    st.subheader("Resumo dos arquivos")
    st.caption(
        "Clique em qualquer linha para abrir e editar as movimentações daquele arquivo."
    )

    total_faturamento = 0.0
    total_royalties = 0.0

    for indice, arquivo in enumerate(arquivos):
        try:
            # Reinicia variáveis desta linha para não reaproveitar dados do arquivo anterior.
            editada = None
            selecionadas = None
            faturamento = None
            royalties = None
            vencimento = proximo_dia_10()

            dados = processar_arquivo(arquivo)

            visiveis = dados[
                dados["Classificação"].isin(
                    ["FATURAMENTO", "REVISAR"]
                )
            ].copy()

            chave_editor = (
                f"editor_{indice}_"
                + re.sub(
                    r"[^a-zA-Z0-9_]",
                    "_",
                    arquivo.name
                )
            )

            # Primeiro calcula com a seleção padrão para exibir no título.
            selecionadas_padrao = visiveis[
                visiveis["Considerar"] == True
            ].copy()

            faturamento_padrao = (
                pd.to_numeric(
                    selecionadas_padrao["Valor"],
                    errors="coerce"
                )
                .fillna(0)
                .sum()
            )

            royalties_padrao = (
                faturamento_padrao
                * PERCENTUAL_ROYALTIES
            )

            valor_faturamento_titulo = formatar_moeda(
                faturamento_padrao
            ).replace("$", r"\$")

            valor_royalties_titulo = formatar_moeda(
                royalties_padrao
            ).replace("$", r"\$")

            # Exibição padronizada do BOX no resumo.
            # Não depende do texto completo do arquivo e evita que o navegador
            # traduza "box" para "caixa".
            numero_box_resumo = extrair_numero_box(arquivo.name)

            if numero_box_resumo is not None:
                # Caracteres Unicode visualmente equivalentes impedem o
                # tradutor automático do navegador de interpretar BOX como palavra inglesa.
                nome_resumo = f"BΟX {numero_box_resumo:02d}"  # O é ômicron grego
            else:
                nome_resumo = Path(arquivo.name).stem

            titulo_linha = (
                f"📄 {nome_resumo}"
                f"   |   Faturamento: :green[{valor_faturamento_titulo}]"
                f"   |   Royalties 4%: :green[{valor_royalties_titulo}]"
            )

            with st.expander(
                titulo_linha,
                expanded=False
            ):
                st.caption(
                    "Desmarque qualquer valor que não queira considerar no faturamento."
                )

                editada = st.data_editor(
                    visiveis[
                        [
                            "Data",
                            "Descrição",
                            "Valor",
                            "Classificação",
                            "Considerar",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    key=chave_editor,
                    column_config={
                        "Considerar":
                            st.column_config.CheckboxColumn(
                                "Considerar"
                            ),
                        "Valor":
                            st.column_config.NumberColumn(
                                "Valor",
                                format="R$ %.2f"
                            ),
                    },
                    disabled=[
                        "Data",
                        "Descrição",
                        "Valor",
                        "Classificação",
                    ],
                )

                selecionadas = editada[
                    editada["Considerar"] == True
                ].copy()

                faturamento = (
                    pd.to_numeric(
                        selecionadas["Valor"],
                        errors="coerce"
                    )
                    .fillna(0)
                    .sum()
                )

                royalties = (
                    faturamento
                    * PERCENTUAL_ROYALTIES
                )

                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "Entradas consideradas",
                    len(selecionadas)
                )

                col2.metric(
                    "Faturamento",
                    formatar_moeda(faturamento)
                )

                col3.metric(
                    "Royalties 4%",
                    formatar_moeda(royalties)
                )

                st.markdown("#### Adicionar valor ao boleto")

                col_adicional, col_total_boleto = st.columns(2)

                adicional_texto = col_adicional.text_input(
                    "Valor adicional",
                    value="0,00",
                    key=f"adicional_boleto_{indice}",
                    help=(
                        "Digite o valor em reais que deseja acrescentar. "
                        "Ex.: 100,00 ou 250,50."
                    )
                )

                adicional_boleto = converter_numero(adicional_texto)

                if adicional_boleto is None:
                    adicional_boleto = 0.0
                    col_adicional.warning(
                        "Digite um valor válido, por exemplo: 100,00"
                    )

                if adicional_boleto < 0:
                    adicional_boleto = 0.0
                    col_adicional.warning(
                        "O valor adicional não pode ser negativo."
                    )

                valor_final_boleto = (
                    float(royalties)
                    + float(adicional_boleto)
                )

                col_total_boleto.metric(
                    "Valor final do boleto",
                    formatar_moeda(valor_final_boleto)
                )

                descricao_padrao = "Royalties"

                descricao_boleto = st.text_input(
                    "Descrição do boleto",
                    value=descricao_padrao,
                    max_chars=500,
                    key=f"descricao_boleto_{indice}",
                    help="Esta descrição será enviada ao Asaas junto com a cobrança."
                )

                st.markdown(f"#### Cobrança Asaas — {EMPRESA_SELECIONADA}")
                col_venc, col_botao = st.columns([2, 1])

                vencimento = col_venc.date_input(
                    "Vencimento do boleto",
                    value=proximo_dia_10(),
                    min_value=date.today(),
                    format="DD/MM/YYYY",
                    key=f"vencimento_{indice}"
                )

                chave_boleto = (
                    f"boleto_{indice}_"
                    + re.sub(r"[^a-zA-Z0-9_]", "_", arquivo.name)
                )
           emitir_nota_apos_pagamento = False

          if EMPRESA_SELECIONADA == "Lider Franquia":
          emitir_nota_apos_pagamento = st.checkbox(
          "Emitir nota fiscal automaticamente após o pagamento",
          value=False,
          key=f"emitir_nota_{indice}",
          help="Quando marcado, a NFS-e de Royalties será preparada para emissão após a confirmação do pagamento."
    )
                if col_botao.button(
                    "💳 Emitir boleto",
                    key=chave_boleto,
                    type="primary",
                    use_container_width=True,
                    disabled=valor_final_boleto <= 0
                ):
                    try:
                        with st.spinner("Gerando boleto no Asaas Sandbox..."):
                            boleto = emitir_boleto_asaas(
                                arquivo.name,
                                faturamento,
                                valor_final_boleto,
                                vencimento,
                                descricao_boleto
                            )

                        st.session_state[
                            f"resultado_boleto_{indice}"
                        ] = boleto

                    except Exception as erro_boleto:
                        st.error(
                            f"Não foi possível emitir o boleto: {erro_boleto}"
                        )

                boleto_salvo = st.session_state.get(
                    f"resultado_boleto_{indice}"
                )

                if boleto_salvo:
                    if boleto_salvo.get("novo"):
                        st.success(
                            f"✅ Boleto criado para "
                            f"{boleto_salvo.get('clienteNome', '')} "
                            f"(BOX {boleto_salvo.get('box', '')}) "
                            f"e notificações padronizadas com sucesso. "
                            f"ID: {boleto_salvo.get('id', '')}"
                        )
                    else:
                        st.info(
                            "ℹ️ Esta cobrança já existia no Asaas. "
                            "O sistema não gerou uma cobrança duplicada."
                        )

                    if boleto_salvo.get("invoiceUrl"):
                        st.link_button(
                            "🔗 Abrir cobrança no Asaas",
                            boleto_salvo["invoiceUrl"],
                            use_container_width=True
                        )

                    if boleto_salvo.get("bankSlipUrl"):
                        st.link_button(
                            "📄 Abrir boleto",
                            boleto_salvo["bankSlipUrl"],
                            use_container_width=True
                        )

            resultados.append({
                "Arquivo": arquivo.name,
                "Faturamento": faturamento,
                "Royalties 4%": royalties,
            })

            detalhes_exportacao[
                arquivo.name
            ] = editada.copy()

            total_faturamento += faturamento
            total_royalties += royalties

        except Exception as erro:
            st.error(
                f"Erro ao processar {arquivo.name}: {erro}"
            )

            resultados.append({
                "Arquivo": arquivo.name,
                "Faturamento": 0.0,
                "Royalties 4%": 0.0,
            })

    st.divider()

    col_total1, col_total2 = st.columns(2)

    col_total1.metric(
        "Faturamento total geral",
        formatar_moeda(total_faturamento)
    )

    col_total2.metric(
        "Royalties total geral (4%)",
        formatar_moeda(total_royalties)
    )

    # ========================================================
    # DOWNLOAD DO RELATÓRIO GERAL
    # ========================================================

    resumo = pd.DataFrame(resultados)

    excel_geral = gerar_excel_geral(
        resumo,
        detalhes_exportacao
    )

    st.download_button(
        "📥 Baixar relatório geral em Excel",
        data=excel_geral,
        file_name="relatorio_geral_faturamento.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
