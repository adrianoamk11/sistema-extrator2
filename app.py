
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
st.markdown(
    """
    <style>
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #16a34a !important;
        border-color: #16a34a !important;
        color: white !important;
    }

    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #15803d !important;
        border-color: #15803d !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True
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

if "mostrar_boleto_avulso" not in st.session_state:
    st.session_state.mostrar_boleto_avulso = False

col_empresa, _, col_atalho_boleto = st.columns([1, 4, 1])

with col_empresa:
    EMPRESA_SELECIONADA = st.selectbox(
        "Empresa",
        ["Lider Franquia", "Lider Serviços"],
        label_visibility="collapsed"
    )

with col_atalho_boleto:
    if st.button(
        "💳 Boleto avulso",
        type="secondary",
        use_container_width=True,
        key="abrir_fechar_boleto_avulso"
    ):
        st.session_state.mostrar_boleto_avulso = (
            not st.session_state.mostrar_boleto_avulso
        )

if EMPRESA_SELECIONADA == "Lider Franquia":
    ASAAS_API_KEY = st.secrets["ASAAS_LIDER_FRANQUIA_API_KEY"]
else:
    ASAAS_API_KEY = st.secrets["ASAAS_LIDER_SERVICOS_API_KEY"]

ASAAS_BASE_URL = st.secrets["ASAAS_PRODUCAO_BASE_URL"].rstrip("/")
emitir_nota_apos_pagamento = False


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
    encontrado = re.search(r"\bbox\s*[-_:]?\s*0*(\d+)", texto_norm)

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

        # 3) Cobrança vencida / atraso:
        # envia apenas um e-mail ao CLIENTE quando o Asaas
        # identificar que a cobrança venceu e não foi paga.
        elif evento == "PAYMENT_OVERDUE" and offset_atual == 0:
            config.update({
                "enabled": True,
                "emailEnabledForProvider": False,
                "smsEnabledForProvider": False,
                "emailEnabledForCustomer": True,
                "smsEnabledForCustomer": False,
                "phoneCallEnabledForCustomer": False,
                "whatsappEnabledForCustomer": False,
            })

        # Lembretes periódicos após o vencimento ficam desativados.
        elif evento == "PAYMENT_OVERDUE" and offset_atual > 0:
            config.update({
                "enabled": False,
                "scheduleOffset": offset_atual,
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
    descricao_boleto,
    emitir_nota=False
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

    if emitir_nota:
        external_reference = f"{external_reference}|NFSE|"

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
# OUTRO EXTRATO / MAQUININHA
# ============================================================

PALAVRAS_IGNORAR_OUTRO_EXTRATO = [
    "saldo inicial",
    "saldo final",
    "saldo diario",
    "daily balance",
    "final balance",
    "initial balance",
    "total inflows",
    "total outflows",
    "rendimento",
    "earnings",
    "juros",
    "interest",
    "cashback",
    "cash back",
    "tarifa",
    "taxa",
]

def converter_numero_flexivel(valor):
    """
    Converte valores tanto no padrão brasileiro (1.234,56)
    quanto no padrão internacional (1,234.56).
    """
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    texto = (
        texto
        .replace("R$", "")
        .replace("BRL", "")
        .replace("\xa0", "")
        .replace(" ", "")
    )

    if not texto:
        return None

    # Mantém somente sinal, números e separadores.
    texto = re.sub(r"[^0-9,\.\-\+]", "", texto)

    if not texto:
        return None

    try:
        if "," in texto and "." in texto:
            # O último separador é tratado como separador decimal.
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif texto.count(".") > 1:
            partes = texto.split(".")
            texto = "".join(partes[:-1]) + "." + partes[-1]

        return float(texto)
    except Exception:
        return None


def texto_pdf_em_linhas(arquivo):
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

    return linhas


def detectar_origem_outro_extrato(linhas):
    texto = normalizar(" ".join(linhas))

    if (
        "stone instituicao de pagamento" in texto
        or "pix | maquininha" in texto
    ):
        return "Stone"

    if (
        "cloudwalk" in texto
        or "infinitepay" in texto
        or "transaction report" in texto
    ):
        return "InfinitePay"

    if (
        "mercado pago instituicao de pagamento" in texto
        or "mercadopago.com.br" in texto
    ):
        return "Mercado Pago"

    return "Formato genérico"


def valor_monetario_da_linha(linha):
    # Valores com R$.
    encontrados = re.findall(
        r"(?:R\$\s*)?([+\-]?\s*[\d\.]+,\d{2}|[+\-]?\s*[\d,]+\.\d{2})",
        str(linha)
    )

    if not encontrados:
        return None

    return converter_numero_flexivel(encontrados[0])


def montar_tabela_outro_extrato(registros):
    if not registros:
        raise ValueError(
            "Não encontrei entradas legíveis neste extrato."
        )

    tabela = pd.DataFrame(registros)

    for coluna in ["Data", "Descrição"]:
        if coluna not in tabela.columns:
            tabela[coluna] = ""

    tabela["Valor"] = pd.to_numeric(
        tabela["Valor"],
        errors="coerce"
    )

    tabela = tabela[
        tabela["Valor"].notna()
    ].copy()

    # O campo precisa ser booleano para o CheckboxColumn do Streamlit.
    if "Considerar" not in tabela.columns:
        tabela["Considerar"] = True

    tabela["Considerar"] = (
        tabela["Considerar"]
        .fillna(False)
        .astype(bool)
    )

    tabela["Classificação"] = tabela["Considerar"].map(
        {True: "ENTRADA", False: "REVISAR"}
    )

    return tabela[
        [
            "Data",
            "Descrição",
            "Valor",
            "Classificação",
            "Considerar",
        ]
    ].reset_index(drop=True)


def ler_outro_pdf_stone(linhas):
    registros = []
    padrao_data = re.compile(r"^\d{2}/\d{2}/\d{2,4}$")

    indices_datas = [
        indice
        for indice, linha in enumerate(linhas)
        if padrao_data.match(linha.strip())
    ]

    for posicao, inicio in enumerate(indices_datas):
        fim = (
            indices_datas[posicao + 1]
            if posicao + 1 < len(indices_datas)
            else len(linhas)
        )

        bloco = linhas[inicio:fim]

        if len(bloco) < 2:
            continue

        tipo = normalizar(bloco[1])

        if "entrada" not in tipo:
            continue

        indice_valor = None
        valor = None

        for i in range(2, len(bloco)):
            if "r$" in normalizar(bloco[i]):
                candidato = valor_monetario_da_linha(bloco[i])

                if candidato is not None:
                    indice_valor = i
                    valor = candidato
                    break

        if valor is None or valor <= 0:
            continue

        descricao = " | ".join(
            bloco[2:indice_valor]
        ).strip()

        descricao_norm = normalizar(descricao)

        considerar = not any(
            palavra in descricao_norm
            for palavra in PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Data": bloco[0],
            "Descrição": descricao or "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def ler_outro_pdf_infinitepay(linhas):
    registros = []

    # No PDF da InfinitePay/CloudWalk, cada transação aparece como:
    # horário -> tipo -> nome -> detalhe -> valor.
    # Saldos e totais são descartados explicitamente.
    for indice, linha in enumerate(linhas):
        texto = str(linha).strip()

        if not re.fullmatch(
            r"[+\-]?\s*[\d,]+\.\d{2}",
            texto
        ):
            continue

        valor = converter_numero_flexivel(texto)

        if valor is None or valor <= 0:
            continue

        contexto = linhas[
            max(0, indice - 5):indice
        ]

        descricao = " | ".join(contexto).strip()
        descricao_norm = normalizar(descricao)

        if any(
            termo in descricao_norm
            for termo in [
                "daily balance",
                "final balance",
                "initial balance",
                "total inflows",
                "total outflows",
            ]
        ):
            continue

        # Rendimentos são mostrados para revisão, mas não entram por padrão.
        considerar = not any(
            palavra in descricao_norm
            for palavra in PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Data": "",
            "Descrição": descricao or "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def ler_outro_pdf_mercado_pago(linhas):
    registros = []
    padrao_data = re.compile(r"^\d{2}-\d{2}-\d{4}$")

    try:
        inicio_detalhes = next(
            i
            for i, linha in enumerate(linhas)
            if "detalhe dos movimentos" in normalizar(linha)
        )
    except StopIteration:
        inicio_detalhes = 0

    linhas_detalhes = linhas[inicio_detalhes:]

    indices_datas = [
        indice
        for indice, linha in enumerate(linhas_detalhes)
        if padrao_data.match(linha.strip())
    ]

    for posicao, inicio in enumerate(indices_datas):
        fim = (
            indices_datas[posicao + 1]
            if posicao + 1 < len(indices_datas)
            else len(linhas_detalhes)
        )

        bloco = linhas_detalhes[inicio:fim]

        indice_valor = None
        valor = None

        # O primeiro R$ do bloco é o valor da movimentação;
        # o segundo é o saldo da conta.
        for i in range(1, len(bloco)):
            if "r$" in normalizar(bloco[i]):
                candidato = valor_monetario_da_linha(bloco[i])

                if candidato is not None:
                    indice_valor = i
                    valor = candidato
                    break

        if valor is None or valor <= 0:
            continue

        descricao_partes = []

        for item in bloco[1:indice_valor]:
            # Evita colocar o ID numérico da operação como descrição.
            if re.fullmatch(r"\d{6,}", item.strip()):
                continue

            descricao_partes.append(item)

        descricao = " | ".join(descricao_partes).strip()
        descricao_norm = normalizar(descricao)

        considerar = not any(
            palavra in descricao_norm
            for palavra in PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Data": bloco[0],
            "Descrição": descricao or "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def ler_outro_pdf_generico(linhas):
    """
    Leitor conservador para PDFs de outros bancos:
    procura blocos iniciados por data e usa o primeiro valor monetário
    do bloco como valor da movimentação, evitando somar o saldo.
    """
    registros = []

    padrao_data = re.compile(
        r"^(?:\d{2}[\/\-\.]\d{2}[\/\-\.]\d{2,4})$"
    )

    indices_datas = [
        indice
        for indice, linha in enumerate(linhas)
        if padrao_data.match(str(linha).strip())
    ]

    for posicao, inicio in enumerate(indices_datas):
        fim = (
            indices_datas[posicao + 1]
            if posicao + 1 < len(indices_datas)
            else len(linhas)
        )

        bloco = linhas[inicio:fim]

        indice_valor = None
        valor = None

        for i in range(1, len(bloco)):
            candidato = valor_monetario_da_linha(bloco[i])

            if candidato is not None:
                indice_valor = i
                valor = candidato
                break

        if valor is None or valor <= 0:
            continue

        descricao = " | ".join(
            bloco[1:indice_valor]
        ).strip()

        descricao_norm = normalizar(descricao)

        considerar = not any(
            palavra in descricao_norm
            for palavra in PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Data": bloco[0],
            "Descrição": descricao or "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    if registros:
        return montar_tabela_outro_extrato(registros)

    raise ValueError(
        "O PDF não segue um formato reconhecível de movimentações. "
        "Tente exportar o extrato em PDF, Excel ou CSV."
    )


def ler_outro_pdf(arquivo):
    linhas = texto_pdf_em_linhas(arquivo)
    origem = detectar_origem_outro_extrato(linhas)

    if origem == "Stone":
        tabela = ler_outro_pdf_stone(linhas)
    elif origem == "InfinitePay":
        tabela = ler_outro_pdf_infinitepay(linhas)
    elif origem == "Mercado Pago":
        tabela = ler_outro_pdf_mercado_pago(linhas)
    else:
        tabela = ler_outro_pdf_generico(linhas)

    return tabela, origem


def preparar_outro_extrato_tabela(dados):
    dados = dados.copy()

    if "Valor" not in dados.columns:
        raise ValueError(
            "Não encontrei a coluna de valor neste arquivo."
        )

    dados["Valor"] = dados["Valor"].apply(
        converter_numero_flexivel
    )

    dados = dados[
        dados["Valor"].notna()
    ].copy()

    if "Data" not in dados.columns:
        dados["Data"] = ""

    if "Descrição" not in dados.columns:
        dados["Descrição"] = ""

    # Se o arquivo informa explicitamente Crédito/Débito,
    # somente créditos positivos entram como candidatos.
    if "Tipo do lançamento" in dados.columns:
        tipo = (
            dados["Tipo do lançamento"]
            .fillna("")
            .astype(str)
            .apply(normalizar)
        )

        candidatos = dados[
            (dados["Valor"] > 0)
            & tipo.str.contains("credito", regex=False)
        ].copy()
    else:
        candidatos = dados[
            dados["Valor"] > 0
        ].copy()

    if candidatos.empty:
        raise ValueError(
            "Não encontrei entradas positivas neste arquivo."
        )

    descricoes_norm = (
        candidatos["Descrição"]
        .fillna("")
        .astype(str)
        .apply(normalizar)
    )

    candidatos["Considerar"] = ~descricoes_norm.apply(
        lambda texto: any(
            palavra in texto
            for palavra in PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )
    )

    return montar_tabela_outro_extrato(
        candidatos[
            ["Data", "Descrição", "Valor", "Considerar"]
        ].to_dict("records")
    )


def ler_outro_ofx(arquivo):
    texto = arquivo.getvalue().decode(
        "latin1",
        errors="ignore"
    )

    blocos = re.findall(
        r"<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>|$)",
        texto,
        flags=re.IGNORECASE | re.DOTALL
    )

    registros = []

    for bloco in blocos:
        def campo(nome):
            encontrado = re.search(
                rf"<{nome}>([^\r\n<]+)",
                bloco,
                flags=re.IGNORECASE
            )
            return encontrado.group(1).strip() if encontrado else ""

        valor = converter_numero_flexivel(
            campo("TRNAMT")
        )

        if valor is None or valor <= 0:
            continue

        descricao = (
            campo("MEMO")
            or campo("NAME")
            or campo("TRNTYPE")
            or "Entrada"
        )

        data_texto = campo("DTPOSTED")
        data_texto = data_texto[:8] if data_texto else ""

        if len(data_texto) == 8 and data_texto.isdigit():
            data_formatada = (
                f"{data_texto[6:8]}/"
                f"{data_texto[4:6]}/"
                f"{data_texto[0:4]}"
            )
        else:
            data_formatada = data_texto

        descricao_norm = normalizar(descricao)

        considerar = not any(
            palavra in descricao_norm
            for palavra in PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Data": data_formatada,
            "Descrição": descricao,
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def processar_outro_extrato(arquivo):
    nome = arquivo.name.lower()

    if nome.endswith(".pdf"):
        return ler_outro_pdf(arquivo)

    if nome.endswith(".ofx"):
        return ler_outro_ofx(arquivo), "OFX"

    if nome.endswith((".xlsx", ".xls", ".csv")):
        dados = ler_excel_ou_csv(arquivo)
        return preparar_outro_extrato_tabela(dados), "Excel/CSV"

    raise ValueError(
        "Formato não suportado. Use PDF, XLSX, XLS, CSV ou OFX."
    )


def assinatura_arquivos_adicionais(arquivos):
    hash_total = hashlib.sha256()

    for arquivo in arquivos:
        hash_total.update(
            arquivo.name.encode("utf-8", errors="ignore")
        )
        hash_total.update(arquivo.getvalue())

    return hash_total.hexdigest()


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



# ============================================================
# BOLETO AVULSO
# ============================================================

if st.session_state.mostrar_boleto_avulso:
    with st.container(border=True):
        st.subheader("Boleto avulso")
        st.caption(
            f"Emissão pela empresa: {EMPRESA_SELECIONADA}. "
            "Esta cobrança não gera nota fiscal."
        )

        col_box, col_buscar = st.columns([2, 1])

        numero_box_avulso = col_box.number_input(
            "Número do BOX",
            min_value=1,
            step=1,
            value=None,
            placeholder="Ex.: 25",
            key="box_boleto_avulso"
        )

        buscar_cliente_avulso = col_buscar.button(
            "🔎 Buscar cliente",
            use_container_width=True,
            key="buscar_cliente_boleto_avulso"
        )

        # Se a empresa ou o BOX mudar, uma identificação antiga não pode
        # ser usada para uma nova cobrança.
        assinatura_busca_atual = (
            EMPRESA_SELECIONADA,
            int(numero_box_avulso) if numero_box_avulso is not None else None
        )

        if (
            st.session_state.get("assinatura_cliente_avulso")
            != assinatura_busca_atual
        ):
            st.session_state.pop("cliente_avulso_encontrado", None)

        if buscar_cliente_avulso:
            if numero_box_avulso is None:
                st.warning("Informe o número do BOX.")
            else:
                try:
                    cliente_avulso, box_confirmado = localizar_cliente_asaas_por_box(
                        f"BOX {int(numero_box_avulso)}.txt"
                    )

                    st.session_state["cliente_avulso_encontrado"] = {
                        "id": cliente_avulso.get("id"),
                        "name": cliente_avulso.get("name", ""),
                        "box": box_confirmado,
                    }
                    st.session_state["assinatura_cliente_avulso"] = (
                        assinatura_busca_atual
                    )

                except Exception as erro_cliente:
                    st.session_state.pop("cliente_avulso_encontrado", None)
                    st.error(
                        f"Não foi possível localizar o cliente: {erro_cliente}"
                    )

        cliente_avulso_salvo = st.session_state.get(
            "cliente_avulso_encontrado"
        )

        cliente_confirmado = (
            cliente_avulso_salvo is not None
            and st.session_state.get("assinatura_cliente_avulso")
            == assinatura_busca_atual
        )

        if cliente_confirmado:
            st.success(
                f"Cliente encontrado: "
                f"{cliente_avulso_salvo.get('name', '')} "
                f"(BOX {cliente_avulso_salvo.get('box', '')})"
            )
        else:
            st.info(
                "Informe o BOX e clique em “Buscar cliente” antes de emitir."
            )

        descricao_avulsa = st.text_area(
            "Descrição do boleto",
            placeholder=(
                "Ex.: Taxa de publicidade\n"
                "Multa contratual\n"
                "Outra descrição"
            ),
            height=120,
            key="descricao_boleto_avulso"
        )

        col_valor_avulso, col_venc_avulso = st.columns(2)

        valor_avulso = col_valor_avulso.number_input(
            "Valor do boleto",
            min_value=0.00,
            step=0.01,
            format="%.2f",
            key="valor_boleto_avulso"
        )

        vencimento_avulso = col_venc_avulso.date_input(
            "Vencimento do boleto",
            value=proximo_dia_10(),
            min_value=date.today(),
            format="DD/MM/YYYY",
            key="vencimento_boleto_avulso"
        )

        pode_emitir_avulso = (
            cliente_confirmado
            and bool(str(descricao_avulsa).strip())
            and float(valor_avulso) > 0
        )

        clicou_emitir_avulso = st.button(
            "💳 Emitir boleto avulso",
            type="primary",
            use_container_width=True,
            disabled=not pode_emitir_avulso,
            key="emitir_boleto_avulso"
        )

        if clicou_emitir_avulso:
            try:
                with st.spinner("Gerando boleto avulso no Asaas..."):
                    # Usa a mesma rotina de localização, notificações e
                    # proteção contra duplicidade do fluxo já existente.
                    boleto_avulso = emitir_boleto_asaas(
                        f"BOX {int(numero_box_avulso)}.txt",
                        0.0,
                        float(valor_avulso),
                        vencimento_avulso,
                        str(descricao_avulsa).strip(),
                        False
                    )

                st.session_state["resultado_boleto_avulso"] = boleto_avulso
                st.session_state["assinatura_resultado_boleto_avulso"] = (
                    EMPRESA_SELECIONADA,
                    int(numero_box_avulso),
                    round(float(valor_avulso), 2),
                    vencimento_avulso.isoformat(),
                    str(descricao_avulsa).strip(),
                )

            except Exception as erro_boleto_avulso:
                st.error(
                    f"Não foi possível emitir o boleto avulso: "
                    f"{erro_boleto_avulso}"
                )

        assinatura_resultado_atual = None
        if numero_box_avulso is not None:
            assinatura_resultado_atual = (
                EMPRESA_SELECIONADA,
                int(numero_box_avulso),
                round(float(valor_avulso), 2),
                vencimento_avulso.isoformat(),
                str(descricao_avulsa).strip(),
            )

        boleto_avulso_salvo = st.session_state.get(
            "resultado_boleto_avulso"
        )

        if (
            boleto_avulso_salvo
            and st.session_state.get(
                "assinatura_resultado_boleto_avulso"
            ) == assinatura_resultado_atual
        ):
            if boleto_avulso_salvo.get("novo"):
                st.success(
                    f"✅ Boleto avulso criado para "
                    f"{boleto_avulso_salvo.get('clienteNome', '')} "
                    f"(BOX {boleto_avulso_salvo.get('box', '')}) e "
                    f"notificações padronizadas com sucesso. "
                    f"ID: {boleto_avulso_salvo.get('id', '')}"
                )
            else:
                st.info(
                    "ℹ️ Esta cobrança já existia no Asaas. "
                    "O sistema não gerou uma cobrança duplicada."
                )

            if boleto_avulso_salvo.get("invoiceUrl"):
                st.link_button(
                    "🔗 Abrir cobrança no Asaas",
                    boleto_avulso_salvo["invoiceUrl"],
                    use_container_width=True
                )

            if boleto_avulso_salvo.get("bankSlipUrl"):
                st.link_button(
                    "📄 Abrir boleto",
                    boleto_avulso_salvo["bankSlipUrl"],
                    use_container_width=True
                )

st.divider()

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



                # ====================================================
                # OUTRO EXTRATO / MAQUININHA
                # ====================================================

                chave_area_outro = f"outro_extrato_area_{indice}"

                st.markdown(
                    f"""
                    <style>
                    .st-key-{{chave_area_outro}} {{
                        background: #f0fdf4 !important;
                        border: 1px solid #86efac !important;
                        border-radius: 14px !important;
                        padding: 18px 20px 16px 20px !important;
                        margin-top: 8px !important;
                        margin-bottom: 22px !important;
                    }}

                    .st-key-{{chave_area_outro}} [data-testid="stFileUploader"] {{
                        background: transparent !important;
                    }}

                    .st-key-{{chave_area_outro}} [data-testid="stExpander"] {{
                        background: rgba(255, 255, 255, 0.72) !important;
                        border-radius: 10px !important;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True
                )

                with st.container(
                    border=False,
                    key=chave_area_outro
                ):
                    st.markdown("#### Outro extrato / maquininha")
                    st.caption(
                        "Área destinada às entradas de extratos adicionais "
                        "(Stone, InfinitePay, Mercado Pago e outros formatos). "
                        "O valor confirmado aqui será somado ao faturamento total."
                    )

                    outros_arquivos = st.file_uploader(
                        "Carregar outro extrato",
                        type=["pdf", "xlsx", "xls", "csv", "ofx"],
                        accept_multiple_files=True,
                        help=(
                            "Aceita PDF, Excel, CSV e OFX. "
                            "O sistema reconhece automaticamente Stone, "
                            "InfinitePay e Mercado Pago e também tenta "
                            "interpretar outros formatos de extrato."
                        ),
                        key=f"outro_extrato_uploader_{indice}"
                    )

                    valor_outros_extratos = 0.0
                    quantidade_outros_extratos = 0
                    chave_confirmacao_outro = (
                        f"outro_extrato_confirmado_{indice}"
                    )
                    chave_assinatura_outro = (
                        f"outro_extrato_assinatura_{indice}"
                    )

                    if outros_arquivos:
                        assinatura_atual_outro = (
                            assinatura_arquivos_adicionais(
                                outros_arquivos
                            )
                        )

                        if (
                            st.session_state.get(
                                chave_assinatura_outro
                            )
                            != assinatura_atual_outro
                        ):
                            st.session_state[
                                chave_assinatura_outro
                            ] = assinatura_atual_outro

                            st.session_state[
                                chave_confirmacao_outro
                            ] = False

                        totais_por_arquivo = []

                        for indice_outro, arquivo_outro in enumerate(
                            outros_arquivos
                        ):
                            try:
                                (
                                    dados_outro,
                                    origem_outro,
                                ) = processar_outro_extrato(
                                    arquivo_outro
                                )

                                # Segurança contra o erro de CheckboxColumn
                                # receber FLOAT em vez de booleano.
                                dados_outro["Considerar"] = (
                                    dados_outro["Considerar"]
                                    .fillna(False)
                                    .astype(bool)
                                )

                                chave_editor_outro = (
                                    f"editor_outro_{indice}_"
                                    f"{indice_outro}_"
                                    f"{assinatura_atual_outro[:12]}"
                                )

                                with st.expander(
                                    (
                                        f"🔎 Ver detalhes — "
                                        f"{arquivo_outro.name} "
                                        f"({origem_outro})"
                                    ),
                                    expanded=False
                                ):
                                    st.caption(
                                        "Desmarque qualquer entrada que "
                                        "não queira somar ao faturamento."
                                    )

                                    editado_outro = st.data_editor(
                                        dados_outro,
                                        use_container_width=True,
                                        hide_index=True,
                                        key=chave_editor_outro,
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

                                selecionado_outro = editado_outro[
                                    editado_outro["Considerar"] == True
                                ].copy()

                                total_arquivo_outro = (
                                    pd.to_numeric(
                                        selecionado_outro["Valor"],
                                        errors="coerce"
                                    )
                                    .fillna(0)
                                    .sum()
                                )

                                quantidade_arquivo_outro = len(
                                    selecionado_outro
                                )

                                valor_outros_extratos += float(
                                    total_arquivo_outro
                                )

                                quantidade_outros_extratos += (
                                    quantidade_arquivo_outro
                                )

                                totais_por_arquivo.append(
                                    (
                                        arquivo_outro.name,
                                        origem_outro,
                                        float(total_arquivo_outro),
                                    )
                                )

                            except Exception as erro_outro:
                                st.error(
                                    f"Erro ao processar "
                                    f"{arquivo_outro.name}: "
                                    f"{erro_outro}"
                                )

                        for (
                            nome_outro,
                            origem_outro,
                            total_outro,
                        ) in totais_por_arquivo:
                            st.caption(
                                f"{origem_outro} • {nome_outro} • "
                                f"Entradas selecionadas: "
                                f"{formatar_moeda(total_outro)}"
                            )

                        col_total_outro, col_ok_outro, col_espaco_outro = st.columns(
                            [1.05, 0.60, 2.35]
                        )

                        col_total_outro.metric(
                            "Total do outro extrato",
                            formatar_moeda(
                                valor_outros_extratos
                            )
                        )

                        col_ok_outro.markdown(
                            "<div style='height: 26px;'></div>",
                            unsafe_allow_html=True
                        )

                        if chave_confirmacao_outro not in st.session_state:
                            st.session_state[
                                chave_confirmacao_outro
                            ] = False

                        if not st.session_state[
                            chave_confirmacao_outro
                        ]:
                            clicou_ok_outro = col_ok_outro.button(
                                "OK — Adicionar",
                                type="secondary",
                                use_container_width=True,
                                disabled=(
                                    valor_outros_extratos <= 0
                                ),
                                key=f"confirmar_outro_{indice}"
                            )

                            if clicou_ok_outro:
                                st.session_state[
                                    chave_confirmacao_outro
                                ] = True
                        else:
                            col_ok_outro.success(
                                "✅ Adicionado ao faturamento"
                            )

                            if col_ok_outro.button(
                                "Remover do faturamento",
                                use_container_width=True,
                                key=f"remover_outro_{indice}"
                            ):
                                st.session_state[
                                    chave_confirmacao_outro
                                ] = False
                                st.rerun()

                        if st.session_state.get(
                            chave_confirmacao_outro,
                            False
                        ):
                            faturamento = (
                                float(faturamento)
                                + float(valor_outros_extratos)
                            )

                            st.caption(
                                "O valor acima já está incluído no faturamento total. "
                                "Se você desmarcar uma entrada em “Ver detalhes”, "
                                "o total será recalculado automaticamente."
                            )
                        else:
                            pass


                st.markdown("#### Adicionar valor ao faturamento")

                # Layout organizado
                col_esq, col_centro, col_dir = st.columns([0.85, 1.15, 0.75])
    
                # ==========================================
                # COLUNA ESQUERDA
                # ==========================================
    
                adicional_texto = col_esq.text_input(
                    "Valor adicional ao faturamento",
                    value="0,00",
                    key=f"adicional_boleto_{indice}",
                    help=(
                        "Digite um valor positivo para somar ou negativo para diminuir o faturamento. "
                        "Ex.: 500,00 soma; -500,00 diminui. Os royalties de 4% serão recalculados sobre o novo total."
                    )
                )
    
                adicional_boleto = converter_numero(adicional_texto)
    
                if adicional_boleto is None:
                    adicional_boleto = 0.0
                    col_esq.warning("Digite um valor válido, por exemplo: 100,00")
    
    
                # Recalcula faturamento e royalties
                faturamento = (
                    float(faturamento)
                    + float(adicional_boleto)
                )
    
                royalties = (
                    float(faturamento)
                    * PERCENTUAL_ROYALTIES
                )
    
                # Valor final do boleto editável
                # Atualiza automaticamente quando os royalties mudarem,
                # mas preserva uma alteração manual feita pelo usuário.
                chave_valor_boleto = f"valor_final_boleto_{indice}"
                chave_valor_auto = f"valor_final_boleto_auto_{indice}"
                novo_valor_auto = round(float(royalties), 2)

                if chave_valor_boleto not in st.session_state:
                    # Primeira exibição: usa automaticamente 4% do faturamento total.
                    st.session_state[chave_valor_boleto] = novo_valor_auto

                elif chave_valor_auto in st.session_state:
                    valor_auto_anterior = float(
                        st.session_state[chave_valor_auto]
                    )

                    # Se o faturamento mudou (inclusive por valor adicional
                    # ou seleção/desseleção de entradas), recalcula os 4%
                    # e atualiza também o valor final do boleto.
                    if abs(novo_valor_auto - valor_auto_anterior) >= 0.005:
                        st.session_state[chave_valor_boleto] = novo_valor_auto

                st.session_state[chave_valor_auto] = novo_valor_auto

                valor_final_boleto = col_esq.number_input(
                    "Valor final do boleto",
                    min_value=0.00,
                    step=0.01,
                    format="%.2f",
                    key=chave_valor_boleto
                )

                # O valor grande de Royalties acompanha o valor final do boleto.
                # O cálculo automático de 4% continua sendo usado como valor-base
                # antes de qualquer ajuste manual.
                royalties = float(valor_final_boleto)
    
                # ==========================================
                # COLUNA CENTRAL
                # ==========================================
    
                col_centro.metric(
                    "Total do faturamento",
                    formatar_moeda(faturamento)
                )
    
                col_centro.metric(
                    "Royalties 4%",
                    formatar_moeda(royalties)
                )
    
                # ==========================================
                # COLUNA DIREITA
                # ==========================================
    
                col_dir.metric(
                    "Entradas consideradas",
                    (
                        len(selecionadas)
                        + (
                            quantidade_outros_extratos
                            if st.session_state.get(
                                chave_confirmacao_outro,
                                False
                            )
                            else 0
                        )
                    )
                )
    
                    
                st.markdown(f"#### Cobrança Asaas — {EMPRESA_SELECIONADA}")
                col_venc, col_botao = st.columns([2, 1])
                descricao_boleto = "Royalties"
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
    
    
                if EMPRESA_SELECIONADA == "Lider Franquia":
                        emitir_nota_apos_pagamento = col_botao.checkbox(
                            "Emitir nota fiscal de Royalties após o pagamento",
                            value=False,
                            key=f"emitir_nota_{indice}"
                    )
                else:
                        emitir_nota_apos_pagamento = False
    
                clicou_emitir_boleto = col_botao.button(
                    "💳 Emitir boleto",
                    key=chave_boleto,
                    type="primary",
                    use_container_width=True,
                    disabled=valor_final_boleto <= 0
                )
    
                if clicou_emitir_boleto:
                    try:
                        with st.spinner("Gerando boleto no Asaas..."):
                            boleto = emitir_boleto_asaas(
                                arquivo.name,
                                faturamento,
                                valor_final_boleto,
                                vencimento,
                                descricao_boleto,
                                emitir_nota_apos_pagamento
                            )

                        st.session_state[f"resultado_boleto_{indice}"] = boleto

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
        "Royalties 4% total",
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
