
importar streamlit como st
import pandas as pd
importar fitz
importar re
importar dados unicode
solicitações de importação
import hashlib
Importe data e hora a partir de datetime e timedelta.
from dateutil.relativedelta import relativedelta
from io import BytesIO
from pathlib import Path

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Extrator de Faturamento",
    page_icon="💰",
    layout="amplo"
)
st.markdown(
    """
    <style>
    div[data-testid="stButton"] botão[kind="primary"] {
        cor de fundo: #16a34a !importante;
        cor da borda: #16a34a !importante;
        cor: branco !importante;
    }

    div[data-testid="stButton"] button[kind="primary"]:hover {
        cor de fundo: #15803d !importante;
        cor da borda: #15803d !importante;
        cor: branco !importante;
    }
    </style>
    "",
    unsafe_allow_html=True
)
# =========================
# LOGIN DO SISTEMA
# =========================

se "autenticado" não estiver em st.session_state:
    st.session_state.autenticado = Falso

se não st.session_state.autenticado:
    st.title("Acesso ao sistema")

    usuário = st.text_input("Usuário")
    senha = st.text_input("Senha", type="senha")

    se st.button("Entrar"):
        se (
            usuário == st.secrets["LOGIN_USUARIO"]
            e senha == st.secrets["LOGIN_SENHA"]
        ):
            st.session_state.autenticado = True
            st.rerun()
        outro:
            st.error("Usuário ou senha incorreta.")

    st.stop()
st.markdown("""
<style>
/* Encosta o conteúdo no topo da página */
[data-testid="stAppViewContainer"] .main .block-container {
    padding-top: 0rem !important;
    margem-superior: 0rem !importante;
}
[data-testid="stMainBlockContainer"] {
    padding-top: 0rem !important;
    margem-superior: 0rem !importante;
}
</style>
"", unsafe_allow_html=True)

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo_lider.png"

# ============================================================
# CABEÇALHO
# ============================================================

Se LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width=360)

# Reduza aproximadamente pela metade o espaço entre o logotipo e o título.
st.markdown(
    """
    <meta name="google" content="notranslate">
    <style>
    html, corpo, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] * {
        -webkit-translate: nenhum !importante;
    }
    .notranslate {
        não !importante;
    }
    div[data-testid="stImage"] {
        margem-inferior: -105px !importante;
    }
    </style>
    "",
    unsafe_allow_html=True,
)

st.title("Extrator de Faturamento")
st.caption("LÍDER Aluguel de Motos • PDF, Excel (.xlsx/.xls) e CSV")

st.divider()

# ============================================================
# CONFIGURAÇÕES
# ============================================================

ROYALTIES_PERCENTUAIS = 0,04

# ============================================================
# ASAAS - SELEÇÃO DA EMPRESA
# ============================================================

st.write("Selecione a empresa que deseja utilizar:")

se "mostrar_boleto_avulso" não estiver em st.session_state:
    st.session_state.mostrar_boleto_avulso = Falso

col_empresa, _, col_atalho_boleto = st.colunas([1, 4, 1])

com col_empresa:
    EMPRESA_SELECIONADA = st.selectbox(
        "Empresa",
        ["Líder Franquia", "Líder Serviços"],
        visibilidade_do_rótulo="recolhido"
    )

com col_atalho_boleto:
    se st.botão(
        "💳 Boleto avulso",
        tipo="secundário",
        use_container_width=True,
        key="abrir_fechar_boleto_avulso"
    ):
        st.session_state.mostrar_boleto_avulso = (
            não st.session_state.mostrar_boleto_avulso
        )

# ============================================================
# IDENTIDADE VISUAL POR EMPRESA
# ============================================================
# A Líder Franquia mantém o fundo branco.
# A Líder Serviços usa um amarelo suave em toda a área do sistema
# para reduzir o risco de operar na empresa errada.
if EMPRESA_SELECIONADA == "Líder Serviços":
    st.markdown(
        """
        <style>
        html, corpo, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background-color: #FFF8D8 !important;
        }

        /* Mantém componentes de entrada claros e simples de ler. */
        [data-testid="stFileUploaderDropzone"],
        [data-testid="stDataFrame"],
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div {
            cor de fundo: #FFFFFF !importante;
        }
        </style>
        "",
        unsafe_allow_html=True,
    )

if EMPRESA_SELECIONADA == "Líder Franquia":
    ASAAS_API_KEY = st.secrets["ASAAS_LIDER_FRANQUIA_API_KEY"]
outro:
    ASAAS_API_KEY = st.secrets["ASAAS_LIDER_SERVICOS_API_KEY"]

ASAAS_BASE_URL = st.secrets["ASAAS_PRODUCAO_BASE_URL"].rstrip("/")
emitir_nota_apos_pagamento = Falso


def próximo_dia_10():
    hoje = data.hoje()

    se hoje.day <= 10:
        data de retorno (hoje.ano, hoje.mês, 10)

    proximo_mes = hoje + relativodelta(meses=1)
    data de retorno (proximo_mes.ano, proximo_mes.mês, 10)


def cabecalhos_asaas():
    retornar {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json",
    }

def extrair_numero_box(texto):
    """
    Extrai o número após a palavra BOX.
    Exemplos:
    'BOX 25.xlsx' -> 25
    'Box 025 Julho.xlsx' -> 25
    'caixa mendel 025 zona norte' -> 25
    """
    texto_norm = normalizar(texto)
    encontrado = re.search(r"\bbox\s*[-_:]?\s*0*(\d+)", texto_norm)

    se não encontrado:
        retornar Nenhum

    return int(encontrado.group(1))


def localizar_cliente_asaas_por_box(nome_arquivo):
    """
    Localize o cliente do Asaas usando somente o número do BOX
    encontrado sem nome do arquivo.

    Exemplo:
    Arquivo: 'Extrato BOX 25 Julho.xlsx'
    Cliente Asaas: 'mendel box 025 zona norte'

    Ambos correspondem ao BOX 25.
    """
    numero_box = extrair_numero_box(Path(nome_arquivo).stem)

    Se numero_box for None:
        raise RuntimeError(
            "Não encontrei o número do BOX no nome do arquivo. "
            "Renomeie o arquivo incluindo, por exemplo, 'BOX 25'."
        )

    encontrado = []
    deslocamento = 0
    limite = 100

    enquanto Verdadeiro:
        resposta = requests.get(
            f"{ASAAS_BASE_URL}/clientes",
            cabeçalhos=cabecalhos_asaas(),
            parâmetros={
                "deslocamento": deslocamento,
                "limite": limite,
            },
            tempo limite=30,
        )

        se não resposta.ok:
            tentar:
                detalhe = resposta.json()
            exceto Exceção:
                detalhe = resposta.text

            raise RuntimeError(
                f"Erro ao consultar clientes no Asaas "
                f"(HTTP {resposta.status_code}): {detalhe}"
            )

        corpo = resposta.json()
        clientes = corpo.get("dados", [])

        para cliente em clientes:
            nome_asaas = str(cliente.get("nome", ""))
            box_cliente = extrair_numero_box(nome_asaas)

            se box_cliente == numero_box:
                encontrado.adicionar(cliente)

        se não corpo.get("hasMore"):
            quebrar

        deslocamento += limite

    se len(encontrados) == 1:
        retorno encontrado[0], numero_box

    se len(encontrados) == 0:
        raise RuntimeError(
            f"Não encontrei no Asaas nenhum cliente com BOX {numero_box}. "
            f"Confira se o cadastro do cliente contém 'BOX {numero_box}' "
            f"no campo Nome."
        )

    nomes = " | ".join(
        str(cliente.get("name", ""))
        para cliente em encontrados[:5]
    )

    raise RuntimeError(
        f"Encontrei {len(encontrados)} clientes com BOX {numero_box}: {nomes}. "
        f"Para evitar cobrança de cliente errado, a transferência foi bloqueada."
        f"Deixe apenas um cadastro correspondente a esse BOX."
    )



def recuperar_notificacoes_cliente(customer_id):
    """
    Recupera todas as notificações já existentes do cliente no Asaas.
    """
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/customers/{customer_id}/notifications",
        cabeçalhos=cabecalhos_asaas(),
        tempo limite=30,
    )

    se não resposta.ok:
        tentar:
            detalhe = resposta.json()
        exceto Exceção:
            detalhe = resposta.text

        raise RuntimeError(
            f"Não foi possível consultar as notificações do cliente "
            f"(HTTP {resposta.status_code}): {detalhe}"
        )

    corpo = resposta.json()

    # A resposta normalmente vem em "data", mas mantemos compatibilidade
    # caso o endpoint retorne diretamente a uma lista.
    se isinstance(corpo, lista):
        retorno corporativo

    retornar corpo.get("dados", [])


def configuracao_base_notificacao(notificacao):
    """
    Desliga canais que não fazem parte do padrão Líder.
    """
    retornar {
        "id": notificação["id"],
        "ativado": Falso,
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

    2. Dia do aniversário:
       - E-mail
       - WhatsApp

    3. Um dia após o surgimento:
       - E-mail

    Mais notificações:
       - Desativadas
       - SMS desativado
       - Ligação desativada
    """
    notificações = recuperar_notificacoes_cliente(customer_id)

    se não houver notificações:
        raise RuntimeError(
            "O Asaas não retorna notificações para este cliente."
        )

    atualizações = []

    para notificação em notificações:
        evento = str(notificacao.get("event", "")).upper()
        offset_atual = notificação.get("scheduleOffset", 0)

        tentar:
            deslocamento_atual = int(deslocamento_atual ou 0)
        exceto Exceção:
            deslocamento_real = 0

        config = configuracao_base_notificacao(notificacao)

        # 1) No momento da criação: apenas e-mail.
        se evento == "PAGAMENTO_CRIADO":
            config.update({
                "ativado": Verdadeiro,
                "emailEnabledForCustomer": Verdadeiro,
                "deslocamento do cronograma": 0,
            })

        # 2) No dia do vencimento: e-mail + WhatsApp.
        elif evento == "PAYMENT_DUEDATE_WARNING" and offset_atual == 0:
            config.update({
                "ativado": Verdadeiro,
                "emailEnabledForCustomer": Verdadeiro,
                "whatsappEnabledForCustomer": Verdadeiro,
                "deslocamento do cronograma": 0,
            })

        # Avisos antecipados (ex.: 10 dias antes): desligados.
        elif evento == "PAYMENT_DUEDATE_WARNING" and offset_atual != 0:
            config.update({
                "ativado": Falso,
                "deslocamento_cronometrado": deslocamento_real,
            })

        #3) Cobrança vencida/atraso:
        # envia apenas um e-mail ao CLIENTE quando o Asaas
        # identificar que a cobrança foi vencida e não foi paga.
        elif evento == "PAYMENT_OVERDUE" and offset_atual == 0:
            config.update({
                "ativado": Verdadeiro,
                "emailEnabledForProvider": False,
                "smsEnabledForProvider": False,
                "emailEnabledForCustomer": Verdadeiro,
                "smsEnabledForCustomer": False,
                "phoneCallEnabledForCustomer": False,
                "whatsappEnabledForCustomer": False,
            })

        # Lembretes periódicos após o vencimento ficam desativados.
        elif evento == "PAYMENT_OVERDUE" and offset_atual > 0:
            config.update({
                "ativado": Falso,
                "deslocamento_cronometrado": deslocamento_real,
            })

        # Pagamento confirmado e demais eventos ficam desativados.
        # Linha digitável, alteração de cobrança e quaisquer outros
        # eventos ficam desativados para evitar mensagens duplicadas.
        outro:
            se "scheduleOffset" em notificação:
                config["scheduleOffset"] = offset_atual

        atualizacoes.append(config)

    carga útil = {
        "cliente": id_do_cliente,
        "notificações": atualizações,
    }

    resposta = solicitações.put(
        f"{ASAAS_BASE_URL}/notificações/lote",
        cabeçalhos=cabecalhos_asaas(),
        json=carga útil,
        tempo limite=30,
    )

    se não resposta.ok:
        tentar:
            detalhe = resposta.json()
        exceto Exceção:
            detalhe = resposta.text

        raise RuntimeError(
            f"Não foi possível configurar as notificações no Asaas "
            f"(HTTP {resposta.status_code}): {detalhe}"
        )

    retornar Verdadeiro


def criar_referencia_externa(nome_arquivo, valor, vencimento, descrição=""):
    base = (
        f"{nome_arquivo}|{valor:.2f}|{vencimento.isoformat()}|"
        f"{str(descricao).strip()}"
    )
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    return f"lider-royalties-{digest}"

def buscar_cobranca_existente(referência_externa):
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/pagamentos",
        cabeçalhos=cabecalhos_asaas(),
        params={"externalReference": external_reference},
        tempo limite=30,
    )
    resposta.raise_for_status()
    dados = resposta.json().get("dados", [])
    retornar dados[0] se dados else Nenhum

def emitir_boleto_asaas(
    nome_arquivo,
    Vastículo,
    valor_cobranca,
    não,
    descricao_boleto,
    emitir_nota=False
):
    cliente, numero_box = localizar_cliente_asaas_por_box(nome_arquivo)
    customer_id = cliente.get("id")
    nome_cliente = cliente.get("nome", "")

    se não for customer_id:
        raise RuntimeError(
            f"O cliente do BOX {numero_box} foi encontrado, "
            f"mas o Asaas não retornou um ID válido."
        )

    # Antes de emitir a cobrança, aplica-se automaticamente
    # o padrão de notificações definido pelo Líder.
    padronizar_notificacoes_asaas(customer_id)

    descrição_final = str(descricao_boleto ou "").strip()

    se não descricao_final:
        descrição_final = (
            "Royalties"
            f"Faturamento {formatar_moeda(faturamento)}"
        )

    referência_externa = criar_referencia_externa(
        nome_arquivo,
        valor_cobranca,
        não,
        descrição_final
    )

    se emitir_nota:
        referência_externa = f"{referência_externa}|NFSE|"

    existente = buscar_cobranca_existente(external_reference)
    se existir:
        retornar {
            "novo": Falso,
            "clienteNome": cliente.get("nome"),
            "clienteId": id_do_cliente,
            "caixa": numero_box,
            "id": existe.get("id"),
            "invoiceUrl": existe.get("invoiceUrl"),
            "bankSlipUrl": existe.get("bankSlipUrl"),
            "status": existente.get("status"),
            "referência_externa": referência_externa,
        }


    carga útil = {
        "cliente": id_do_cliente,
        "Tipo de cobrança": "BOLETO",
        "valor": round(float(valor_cobranca), 2),
        "dueDate": vencimento.isoformat(),
        "descrição": descrição_final[:500],
        "referência_externa": referência_externa,
    }

    resposta = requests.post(
        f"{ASAAS_BASE_URL}/pagamentos",
        cabeçalhos=cabecalhos_asaas(),
        json=carga útil,
        tempo limite=30,
    )

    se não resposta.ok:
        tentar:
            detalhe = resposta.json()
        exceto Exceção:
            detalhe = resposta.text
        raise RuntimeError(
            f"Asaas retornaram HTTP {resposta.status_code}: {detalhe}"
        )

    dados = resposta.json()

    retornar {
        "novo": Verdadeiro,
        "clienteNome": cliente.get("nome"),
        "clienteId": id_do_cliente,
        "caixa": numero_box,
        "id": dados.get("id"),
        "invoiceUrl": dados.get("invoiceUrl"),
        "bankSlipUrl": dados.get("bankSlipUrl"),
        "status": dados.get("status"),
        "referência_externa": referência_externa,
    }

PALAVRAS_FATURAMENTO = [
    "cobranca recebida",
    "pagamento",
    "recebimento",
    "pix pesado",
    "crédito de cliente",
    "venda",
    "fatura recebida",
    "boleto",
]

PALAVRAS_IGNORAR = [
    "saldo inicial",
    "saldo final",
    "saldo anterior",
    "saldo disponivel",
    "saldo bloqueado",
    "taxas",
    "tarifa",
    "mensageria",
    "notificação",
]

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar(texto):
    texto = "" se texto for None else str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    retorne re.sub(r"\s+", " ", texto).strip().lower()


def converter_numero(valor):
    se pd.isna(valor):
        retornar Nenhum

    se isinstance(valor, (int, float)):
        retornar float(valor)

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace(" ", "")

    se não for texto:
        retornar Nenhum

    tentar:
        se "," no texto:
            texto = texto.replace(".", "").replace(",", ".")
        retornar float(texto)
    exceto Exceção:
        retornar Nenhum


def formatar_moeda(valor):
    retornar (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .substituir(".", ",")
        .replace("X", ".")
    )


def achar_coluna(colunas, nomes_possiveis):
    mapa = {col: normalizar(col) para col em colunas}

    # Primeira tentativa de igualdade exata
    para nome em visionário_possivo:
        alvo = normalizar(nome)
        para original, atual em mapa.items():
            se atual == alvo:
                devolver original

    # Depois tenta ocorrência parcial
    para nome em visionário_possivo:
        alvo = normalizar(nome)
        para original, atual em mapa.items():
            se alvo em atual:
                devolver original

    retornar Nenhum


# ============================================================
# LEITURA DE EXCEL / CSV
# ============================================================

def encontrar_linha_cabecalho_excel(arquivo, motor):
    """
    Procure automaticamente a linha do cabeçalho.
    Útil para extratos Asaas que possuem informações antes da tabela.
    """
    arquivo.seek(0)

    bruto = pd.read_excel(
        arquivo,
        motor=motor,
        cabeçalho=Nenhum,
        nrows=30
    )

    = [
        "dados",
        "tipo de transacao",
        "descricao",
        "valentia",
        "saldo",
        "tipo do lançamento",
    ]

    melhor_linha = 0
    melhor_pontuacao = -1

    para índice, linha em bruto.iterrows():
        texto = " | ".join(
            normalizar(valor)
            para valor em linha.tolist()
            se não pd.isna(valor)
        )

        pontuação = soma(
            1 para palavra em palavras
            if normalizar(palavra) em texto
        )

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuação
            melhor_linha = índice

    retornar int(melhor_linha)


def preparar_layout_asaas(df):
    """
    Tratamento específico do Excel exportado pela Asaas.

    IMPORTANTE:
    - Use a coluna VALOR para o valor da entrega.
    - Usa Tipo de lançamento para Crédito/Débito.
    - NÃO usa a coluna Saldo como faturamento.
    """
    colunas = lista(df.colunas)

    col_data = achar_coluna(colunas, ["Dados"])
    col_tipo = achar_coluna(colunas, ["Tipo de transação"])
    col_descricao = achar_coluna(colunas, ["Descrição"])
    col_valor = achar_coluna(colunas, ["Valor"])
    col_tipo_lancamento = achar_coluna(
        colunas,
        ["Tipo do lançamento"]
    )

    Se col_valor for None ou col_tipo_lancamento for None:
        retornar Nenhum

    resultado = pd.DataFrame()

    se col_data:
        resultado["Dados"] = df[col_data].astype(str)
    outro:
        resultado["Dados"] = ""

    tipo = (
        df[col_tipo].fillna("").astype(str)
        se col_tipo senão ""
    )

    descrição = (
        df[col_descricao].fillna("").astype(str)
        se col_descricao senão ""
    )

    if col_tipo e col_descricao:
        resultado["Deda"] = (
            tipo.str.strip()
            + " - "
            + descricao.str.strip()
        )
    elif col_tipo:
        resultado["Descrição"] = tipo.str.strip()
    elif col_descricao:
        resultado["Descrição"] = descrição.str.strip()
    outro:
        resultado["Deda"] = ""

    resultado["Valor"] = df[col_valor].apply(
        conversor_número
    )

    resultado["Tipo de lançamento"] = (
        df[col_tipo_lancamento]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    resultado = resultado[
        resultado["Valor"].notna()
    ].cópia()

    resultado = resultado[
        resultado["Tipo de lançamento"].str.len() > 0
    ].cópia()

    retornar resultado


def preparar_layout_generico(df):
    df = df.copy()
    df.columns = [str(col).strip() para col em df.columns]

    col_data = achar_coluna(
        df.columns,
        [
            "dados",
            "data",
            "dados de movimentação",
            "data de lançamento",
        ],
    )

    col_descricao = achar_coluna(
        df.columns,
        [
            "descricao",
            "histórico",
            "lançamento",
            "movimentacao",
            "detalhes",
        ],
    )

    col_valor = achar_coluna(
        df.columns,
        [
            "valentia",
            "quantia",
            "valor movimentacao",
            "valor lancamento",
        ],
    )

    col_credito = achar_coluna(
        df.columns,
        ["crédito", "entrada", "créditos"],
    )

    Se col_descricao for None:
        colunas_texto = [
            coluna para coluna em df.columns
            se df[col].dtype == "objeto"
        ]

        se colunas_texto:
            df["_descricao_auto"] = (
                df[colunas_texto]
                .fillna("")
                .astype(str)
                .agg(" | ".join, axis=1)
            )
        outro:
            df["_descricao_auto"] = ""

        col_descricao = "_descricao_auto"

    Se col_data for None:
        df["_data_auto"] = ""
        col_data = "_data_auto"

    se col_valor não for None:
        valores = df[col_valor].apply(converter_numero)
    elif col_credito is not None:
        valores = df[col_crédito].apply(converter_numero)
    outro:
        raise ValueError(
            "Não encontrei uma coluna de valor da movimentação. "
            "O sistema não usará a coluna Saldo para evitar cálculos incorretos."
        )

    resultado = pd.DataFrame({
        "Dados": df[col_data].astype(str),
        "Descrição": df[col_descricao].astype(str),
        "Valor": valores,
    })

    retornar resultado[
        resultado["Valor"].notna()
    ].cópia()


def ler_excel_ou_csv(arquivo):
    nome = arquivo.name.lower()

    se nome.terminarcom(".xlsx"):
        cabecalho = encontrar_linha_cabecalho_excel(
            arquivo,
            "openpyxl"
        )

        arquivo.seek(0)

        df = pd.read_excel(
            arquivo,
            motor="openpyxl",
            cabeçalho=cabecalho
        )

        asaas = preparar_layout_asaas(df)

        se asaas não for None:
            retornar asaas

        retornar preparar_layout_generico(df)

    se nome.terminarcom(".xls"):
        cabecalho = encontrar_linha_cabecalho_excel(
            arquivo,
            "xlrd"
        )

        arquivo.seek(0)

        df = pd.read_excel(
            arquivo,
            motor="xlrd",
            cabeçalho=cabecalho
        )

        asaas = preparar_layout_asaas(df)

        se asaas não for None:
            retornar asaas

        retornar preparar_layout_generico(df)

    # CSV
    bruto = arquivo.getvalue()

    para codificação em ["utf-8-sig", "utf-8", "latin1"]:
        para separador em [";", ","", "\t"]:
            tentar:
                df = pd.read_csv(
                    BytesIO(bruto),
                    sep=separador,
                    codificação=codificação
                )

                se df.shape[1] > 1:
                    asaas = preparar_layout_asaas(df)

                    se asaas não for None:
                        retornar asaas

                    retornar preparar_layout_generico(df)

            exceto Exceção:
                passar

    raise ValueError(
        "Não consegui interpretar o arquivo CSV."
    )


# ============================================================
# LEITURA DE PDF
# ============================================================

def ler_pdf(arquivo):
    documento = fitz.open(
        fluxo=arquivo.getvalue(),
        filetype="pdf"
    )

    linhas = []

    para página em documento:
        linhas += [
            re.sub(r"\s+", " ", linha).strip()
            para linha na pagina.get_text().splitlines()
            se linha.strip()
        ]

    padrao_data = re.compile(
        r"\b(\d{2}/\d{2}/\d{4})\b"
    )

    padrao_valor = re.compile(
        r"R\$\s*(-?[\d\.]+,\d{2})"
    )

    dados_reais = ""
    contexto = []
    registros = []

    para linha em linhas:
        datas = padrão_data.findall(linha)

        se houver dados:
            dados_reais = dados[0]

        valores = padrão_valor.findall(linha)

        para valor_texto em valores:
            descrição = " ".join(
                contexto[-3:] + [linha]
            )

            descricao = padrao_valor.sub(
                ","
                descrição
            ).tira()

            registros.append({
                "Dados": dados_reais,
                "Descrição": descrição,
                "Valor": conversor_numero(valor_texto),
            })

        contexto.append(linha)

    se não registros:
        raise ValueError(
            "Não encontrei movimentações legíveis neste PDF."
        )

    retornar pd.DataFrame(registros)


# ============================================================
# CLASSIFICAÇÃO DO FATURAMENTO
# ============================================================

def classificar_movimentacao(
    descrição,
    valentia,
    tipo_lançamento=""
):
    descrição_normalizada = normalizar(descrição)
    lancamento_normalizado = normalizar(
        tipo_lançamento
    )

    Se o valor for None:
        retornar "IGNORAR", Falso

    # Excel Asaas: Crédito/Débito explícito
    se lancamento_normalizado:
        if "debito" em lancamento_normalizado:
            retornar "SAÍDA", Falso

        if "crédito" em lancamento_normalizado:
            se houver(
                palavra em descrição_normalizada
                para palavra em PALAVRAS_FATURAMENTO
            ):
                retornar "FATURAMENTO", Verdadeiro

            # Crédito não identificado automaticamente:
            # fica disponível para revisão manual.
            retornar "REVISAR", Falso

    # PDFs e formatos sem Crédito/Débito explícito
    se valor <= 0:
        retornar "SAÍDA", Falso

    se houver(
        palavra em descrição_normalizada
        para palavra em PALAVRAS_IGNORAR
    ):
        retornar "IGNORAR", Falso

    se houver(
        palavra em descrição_normalizada
        para palavra em PALAVRAS_FATURAMENTO
    ):
        retornar "FATURAMENTO", Verdadeiro

    retornar "REVISAR", Falso


def processar_arquivo(arquivo):
    if arquivo.name.lower().endswith(".pdf"):
        dados = ler_pdf(arquivo)
    outro:
        dados = ler_excel_ou_csv(arquivo)

    if "Tipo do lançamento" em dados.columns:
        classificação = dados.apply(
            lambda linha: classificar_movimentacao(
                linha["Det"],
                linha["Valor"],
                linha["Tipo do lançamento"],
            ),
            eixo=1,
        )
    outro:
        classificação = dados.apply(
            lambda linha: classificar_movimentacao(
                linha["Det"],
                linha["Valor"],
            ),
            eixo=1,
        )

    dados["Classificação"] = [
        item[0] para item na classificação
    ]

    dados["Considerar"] = [
        item[1] para item na classificação
    ]

    retornar dados


# ============================================================
# OUTRO EXTRATO / MAQUININHA
# ============================================================

PALAVRAS_IGNORAR_OUTRO_EXTRATO = [
    "saldo inicial",
    "saldo final",
    "saldo diário",
    "equilíbrio diário",
    "saldo final",
    "saldo inicial",
    "fluxos totais",
    "saídas totais",
    "rendimento",
    "ganhos",
    "juros",
    "interesse",
    "cashback",
    "dinheiro de volta",
    "tarifa",
    "taxas",
]

def conversor_numero_flexivel(valor):
    """
    Converter valores tanto no padrão brasileiro (1.234,56)
    quanto no padrão internacional (1.234,56).
    """
    Se o valor for None:
        retornar Nenhum

    tentar:
        se pd.isna(valor):
            retornar Nenhum
    exceto Exceção:
        passar

    se isinstance(valor, (int, float)):
        retornar float(valor)

    texto = str(valor).strip()
    texto = (
        texto
        .replace("R$", "")
        .replace("BRL", "")
        .replace("\xa0", "")
        .substituir(" ", "")
    )

    se não for texto:
        retornar Nenhum

    # Mantém somente sinais, números e separadores.
    texto = re.sub(r"[^0-9,\.\-\+]", "", texto)

    se não for texto:
        retornar Nenhum

    tentar:
        se "," no texto e "." no texto:
            # O último separador é tratado como separador decimal.
            se texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            outro:
                texto = texto.replace(",", "")
        elif "," no texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif texto.count(".") > 1:
            partes = texto.split(".")
            texto = "".join(partes[:-1]) + "." + partes[-1]

        retornar float(texto)
    exceto Exceção:
        retornar Nenhum


def texto_pdf_em_linhas(arquivo):
    documento = fitz.open(
        fluxo=arquivo.getvalue(),
        filetype="pdf"
    )

    linhas = []

    para página em documento:
        linhas += [
            re.sub(r"\s+", " ", linha).strip()
            para linha na pagina.get_text().splitlines()
            se linha.strip()
        ]

    retornar linhas


def detectar_origem_outro_extrato(linhas):
    texto = normalizar(" ".join(linhas))

    se (
        "pedra instituição de pagamento" em texto
        ou "pix | maquininha" no texto
    ):
        retornar "Pedra"

    se (
        "caminhada nas nuvens" em texto
        ou "pagamento infinito" em texto
        ou "relatório de transações" em texto
    ):
        retornar "Pagamento Infinito"

    se (
        "mercado pago instituição de pagamento" em texto
        ou "mercadopago.com.br" em texto
    ):
        retornar "Mercado Pago"

    retornar "Formato genérico"


def valor_monetario_da_linha(linha):
    # Valores com R$.
    encontrado = re.findall(
        r"(?:R\$\s*)?([+\-]?\s*[\d\.]+,\d{2}|[+\-]?\s*[\d,]+\.\d{2})",
        str(linha)
    )

    se não for encontrado:
        retornar Nenhum

    return converter_numero_flexivel(encontrados[0])


def montar_tabela_outro_extrato(registros):
    se não registros:
        raise ValueError(
            "Não encontrei entradas legíveis neste extrato."
        )

    tabela = pd.DataFrame(registros)

    para coluna em ["Dados", "Descrição"]:
        se a coluna não estiver em tabela.columns:
            Viúvo[coluna] = ""

    tabela["Valor"] = pd.to_numeric(
        Vale["Valor"],
        erros="coagir"
    )

    tabela = ~[
        Vi["Valor"].notna()
    ].cópia()

    # O campo precisa ser booleano para o CheckboxColumn do Streamlit.
    Se "Considerar" não estiver em tabela.columns:
        Vi["Considerar"] = Verdadeiro

    Vi["Considerar"] = (
        Vi["Considerar"]
        .fillna(False)
        .astype(bool)
    )

    tabela["Classificação"] = tabela["Considerar"].map(
        {Verdadeiro: "ENTRADA", Falso: "REVISAR"}
    )

    retornar[
        [
            "Dados",
            "Ded",
            "Valentia",
            "Classificação",
            "Considerar",
        ]
    ].reset_index(drop=True)


def ler_outro_pdf_stone(linhas):
    registros = []
    padrao_data = re.compile(r"^\d{2}/\d{2}/\d{2,4}$")

    dados_índices = [
        índice
        para índice, linha in enumerate(linhas)
        if padrão_data.match(linha.strip())
    ]

    para posição, inicio em enumerar(indices_datas):
        fim = (
            índices_dados[posição + 1]
            if posição + 1 < len(índices_dados)
            senão len(linhas)
        )

        bloco = linhas[inicio:fim]

        se len(bloco) < 2:
            continuar

        tipo = normalizar(bloco[1])

        se "entrada" não estiver em tipo:
            continuar

        valor_índice = Nenhum
        valor = Nenhum

        para i em range(2, len(bloco)):
            if "r$" em normalizar(bloco[i]):
                candidato = valor_monetario_da_linha(bloco[i])

                se não for None:
                    valor_índice = i
                    valor =
                    quebrar

        Se valor for None ou valor <= 0:
            continuar

        descrição = " | ".join(
            bloco[2:indice_valor]
        ).tira()

        descrição_norm = normalizar(descrição)

        considerar = nenhum(
            palavra em descricao_norm
            para palavra em PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Dados": bloco[0],
            "Descrição": descricao ou "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def ler_outro_pdf_infinitepay(linhas):
    registros = []

    # No PDF da InfinitePay/CloudWalk, cada transação aparece como:
    # local -> tipo -> nome -> detalhe -> valor.
    # Saldos e totais são descartados explicitamente.
    para índice, linha in enumerate(linhas):
        texto = str(linha).strip()

        se não re.fullmatch(
            r"[+\-]?\s*[\d,]+\.\d{2}",
            texto
        ):
            continuar

        valor = conversor_numero_flexivel(texto)

        Se valor for None ou valor <= 0:
            continuar

        contexto = linhas[
            max(0, índice - 5):índice
        ]

        descrição = " | ".join(contexto).strip()
        descrição_norm = normalizar(descrição)

        se houver(
            termo em descricao_norm
            para termo em [
                "equilíbrio diário",
                "saldo final",
                "saldo inicial",
                "fluxos totais",
                "saídas totais",
            ]
        ):
            continuar

        # Rendimentos são marcados para revisão, mas não entram por padrão.
        considerar = nenhum(
            palavra em descricao_norm
            para palavra em PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Dados": "",
            "Descrição": descricao ou "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def ler_outro_pdf_mercado_pago(linhas):
    registros = []
    padrao_data = re.compile(r"^\d{2}-\d{2}-\d{4}$")

    tentar:
        inicio_detalhes = próximo(
            eu
            for i, linha in enumerate(linhas)
            if "detalhe dos movimentos" em normalizar(linha)
        )
    exceto StopIteration:
        início_detalhes = 0

    linhas_detalhes = linhas[inicio_detalhes:]

    dados_índices = [
        índice
        para índice, linha in enumerate(linhas_detalhes)
        if padrão_data.match(linha.strip())
    ]

    para posição, inicio em enumerar(indices_datas):
        fim = (
            índices_dados[posição + 1]
            if posição + 1 < len(índices_dados)
            senão len(linhas_detalhes)
        )

        bloco = linhas_detalhes[inicio:fim]

        valor_índice = Nenhum
        valor = Nenhum

        # O primeiro R$ do bloco é o valor da entrega;
        # o segundo é o saldo da conta.
        para i em range(1, len(bloco)):
            if "r$" em normalizar(bloco[i]):
                candidato = valor_monetario_da_linha(bloco[i])

                se não for None:
                    valor_índice = i
                    valor =
                    quebrar

        Se valor for None ou valor <= 0:
            continuar

        descricao_partes = []

        para item do bloco[1:índice_valor]:
            # Evite colocar o ID numérico da operação conforme descrição.
            se re.fullmatch(r"\d{6,}", item.strip()):
                continuar

            descricao_partes.append(item)

        descrição = " | ".join(descricao_partes).strip()
        descrição_norm = normalizar(descrição)

        considerar = nenhum(
            palavra em descricao_norm
            para palavra em PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Dados": bloco[0],
            "Descrição": descricao ou "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def ler_outro_pdf_generico(linhas):
    """
    Leitor conservador para PDFs de outros bancos:
    procura blocos iniciados por dados e usa o primeiro valor monetário
    do bloco como valor da movimentação, evitando somar o saldo.
    """
    registros = []

    padrao_data = re.compile(
        r"^(?:\d{2}[\/\-\.]\d{2}[\/\-\.]\d{2,4})$"
    )

    dados_índices = [
        índice
        para índice, linha in enumerate(linhas)
        if padrão_data.match(str(linha).strip())
    ]

    para posição, inicio em enumerar(indices_datas):
        fim = (
            índices_dados[posição + 1]
            if posição + 1 < len(índices_dados)
            senão len(linhas)
        )

        bloco = linhas[inicio:fim]

        valor_índice = Nenhum
        valor = Nenhum

        para i em range(1, len(bloco)):
            candidato = valor_monetario_da_linha(bloco[i])

            se não for None:
                valor_índice = i
                valor =
                quebrar

        Se valor for None ou valor <= 0:
            continuar

        descrição = " | ".join(
            bloco[1:indice_valor]
        ).tira()

        descrição_norm = normalizar(descrição)

        considerar = nenhum(
            palavra em descricao_norm
            para palavra em PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Dados": bloco[0],
            "Descrição": descricao ou "Entrada",
            "Valor": valor,
            "Considerar": considerar,
        })

    se registros:
        return montar_tabela_outro_extrato(registros)

    raise ValueError(
        "O PDF não segue um formato reconhecível de movimentações."
        "Tente exportar o extrato em PDF, Excel ou CSV."
    )


def ler_outro_pdf(arquivo):
    linhas = texto_pdf_em_linhas(arquivo)
    origem = detectar_origem_outro_extrato(linhas)

    ifl == "Pedra":
        tabela = ler_outro_pdf_stone(linhas)
    elifs == "Pagamento Infinito":
        tabela = ler_outro_pdf_infinitepay(linhas)
    elif origem == "Mercado Pago":
        tabela = ler_outro_pdf_mercado_pago(linhas)
    outro:
        tabela = ler_outro_pdf_generico(linhas)

    retornar tabela,


def preparar_outro_extrato_tabela(dados):
    dados = dados.copiar()

    Se "Valor" não estiver em dados.columns:
        raise ValueError(
            "Não encontrei a coluna de valor neste arquivo."
        )

    dados["Valor"] = dados["Valor"].apply(
        conversor_numero_flexível
    )

    dados = dados[
        dados["Valor"].notna()
    ].cópia()

    Se "Data" não estiver em dados.columns:
        dados["Dados"] = ""

    se "Descrição" não estiver em dados.columns:
        dados["Deda"] = ""

    # Se o arquivo informa explicitamente Crédito/Débito,
    #somente créditos positivos ganham como candidatos.
    if "Tipo do lançamento" em dados.columns:
        tipo = (
            dados["Tipo do lançamento"]
            .fillna("")
            .astype(str)
            .aplicar(normalizar)
        )

        candidatos = dados[
            (dados["Valor"] > 0)
            & tipo.str.contains("crédito", regex=False)
        ].cópia()
    outro:
        candidatos = dados[
            dados["Valor"] > 0
        ].cópia()

    se candidatos.vazio:
        raise ValueError(
            "Não encontrei entradas positivas neste arquivo."
        )

    descricoes_norm = (
        candidatos["Deda"]
        .fillna("")
        .astype(str)
        .aplicar(normalizar)
    )

    candidatos["Considerar"] = ~descricoes_norm.apply(
        lambda texto: qualquer(
            palavra em texto
            para palavra em PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )
    )

    return montar_tabela_outro_extrato(
        candidatos[
            ["Dados", "Descrição", "Valor", "Considerar"]
        ].to_dict("registros")
    )


def ler_outro_ofx(arquivo):
    texto = arquivo.getvalue().decode(
        "latin1",
        erros="ignore"
    )

    blocos = re.findall(
        r"<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>|$)",
        texto,
        flags=re.IGNORECASE | re.DOTALL
    )

    registros = []

    para bloco em blocos:
        def campo(nome):
            encontrado = re.pesquisa(
                rf"<{nome}>([^\r\n<]+)",
                bloco,
                flags=re.IGNORECASE
            )
            retorne encontrado.group(1).strip() se encontrado else ""

        valor = conversor_numero_flexivel(
            campo("TRNAMT")
        )

        Se valor for None ou valor <= 0:
            continuar

        descrição = (
            campo("MEMO")
            ou campo("NOME")
            ou campo ("TRNTYPE")
            ou "Entrada"
        )

        data_texto = campo("DTPOSTED")
        texto_dados = texto_dados[:8] if texto_dados else ""

        se len(data_texto) == 8 e data_texto.isdigit():
            data_formatada = (
                f"{data_texto[6:8]}/"
                f"{data_texto[4:6]}/"
                f"{data_texto[0:4]}"
            )
        outro:
            data_formatada = data_texto

        descrição_norm = normalizar(descrição)

        considerar = nenhum(
            palavra em descricao_norm
            para palavra em PALAVRAS_IGNORAR_OUTRO_EXTRATO
        )

        registros.append({
            "Dados": data_formatada,
            "Descrição": descrição,
            "Valor": valor,
            "Considerar": considerar,
        })

    return montar_tabela_outro_extrato(registros)


def processar_outro_extrato(arquivo):
    nome = arquivo.name.lower()

    se nome.terminarcom(".pdf"):
        retornar ler_outro_pdf(arquivo)

    se nome.terminarcom(".ofx"):
        return ler_outro_ofx(arquivo), "OFX"

    se nome.terminarcom((".xlsx", ".xls", ".csv")):
        dados = ler_excel_ou_csv(arquivo)
        return preparar_outro_extrato_tabela(dados), "Excel/CSV"

    raise ValueError(
        "Formato não suportado. Use PDF, XLSX, XLS, CSV ou OFX."
    )


def assinatura_arquivos_adicionais(arquivos):
    hash_total = hashlib.sha256()

    para arquivo em arquivos:
        hash_total.atualizar(
            arquivo.name.encode("utf-8", errors="ignore")
        )
        hash_total.update(arquivo.getvalue())

    retornar hash_total.hexdigest()


# ============================================================
# EXPORTAÇÃO DO RELATÓRIO GERAL
# ============================================================

def nome_aba_excel(nome, usados):
    nome = re.sub(
        r'[\[\]\:\*\?\/\\]',
        "_",
        nome
    )

    nome = nome[:31] ou "Extrato"

    original = nome
    contador = 2

    enquanto nome em usados:
        sufixo = f"_{contador}"
        nome = original[:31-len(sufixo)] + sufixo
        contador += 1

    usados.adicionar(nome)

    retornar nome


def gerar_excel_geral(resumo, detalhes):
    arquivo_excel = BytesIO()

    com pd.ExcelWriter(
        arquivo_excel,
        motor="openpyxl"
    ) como escritor:

        resumo_exportar = resumo.copy()

        resumo_exportar.to_excel(
            escritor,
            índice=Falso,
            sheet_name="Resumo Geral"
        )

        usados ​​= {"Resumo Geral"}

        para nome_arquivo, tabela em detalhes.items():
            aba = nome_aba_excel(
                Caminho(nome_arquivo).tronco,
                usados
            )

            tabela.to_excel(
                escritor,
                índice=Falso,
                nome_da_folha=aba
            )

        # Ajustes simples de largura
        para ws em writer.book.worksheets:
            ws.column_dimensions["A"].width = 25
            ws.column_dimensions["B"].width = 60
            ws.column_dimensions["C"].width = 18
            ws.column_dimensions["D"].width = 20
            ws.column_dimensions["E"].width = 14

    arquivo_excel.seek(0)

    retornar arquivo_excel


# ============================================================
# INTERFACE
# ============================================================

# ============================================================
# TAMANHO DO RESUMO CLICÁVEL POR ARQUIVO
# ============================================================
st.markdown(
    """
    <style>
    div[data-testid="stExpander"] resumo p,
    div[data-testid="stExpander"] resumo p * {
        tamanho da fonte: 20px !importante;
        altura da linha: 1,45 !importante;
    }

    div[data-testid="stExpander"] resumo p {
        cor: #262730 !importante;
    }
    </style>
    "",
    unsafe_allow_html=True,
)



# ============================================================
# BOLETO AVULSO
# ============================================================

if st.session_state.mostrar_boleto_avulso:
    com st.container(border=True):
        st.subheader("Boleto avulso")
        st.caption(
            f"Emissão pela empresa: {EMPRESA_SELECIONADA}. "
            "Esta cobrança não gera nota fiscal."
        )

        col_box, col_buscar = st.columns([2, 1])

        numero_box_avulso = col_box.number_input(
            "Número do BOX",
            valor_mínimo=1,
            passo=1,
            valor=Nenhum,
            placeholder="Ex.: 25",
            chave="box_boleto_avulso"
        )

        buscar_cliente_avulso = col_buscar.button(
            "🔎 Buscar cliente",
            use_container_width=True,
            key="buscar_cliente_boleto_avulso"
        )

        # Se a empresa ou o BOX mudar, uma identificação antiga não pode
        # ser usado para uma nova cobrança.
        assinatura_busca_atual = (
            EMPRESA_SELECIONADA,
            int(numero_box_avulso) se numero_box_avulso não for None else None
        )

        se (
            st.session_state.get("assinatura_cliente_avulso")
            != assinatura_busca_atual
        ):
            st.session_state.pop("cliente_avulso_encontrado", Nenhum)

        se buscar_cliente_avulso:
            se numero_box_avulso for None:
                st.warning("Informe o número do BOX.")
            outro:
                tentar:
                    cliente_avulso, box_confirmado = localizar_cliente_asaas_por_box(
                        f"BOX {int(numero_box_avulso)}.txt"
                    )

                    st.session_state["cliente_avulso_encontrado"] = {
                        "id": cliente_avulso.get("id"),
                        "nome": cliente_avulso.get("nome", ""),
                        "caixa": caixa_confirmada,
                    }
                    st.session_state["assinatura_cliente_avulso"] = (
                        assinatura_busca_atual
                    )

                exceto Exceção como erro_cliente:
                    st.session_state.pop("cliente_avulso_encontrado", Nenhum)
                    st.erro(
                        f"Não foi possível localizar o cliente: {erro_cliente}"
                    )

        cliente_avulso_salvo = st.session_state.get(
            "cliente_avulso_encontrado"
        )

        cliente_confirmado = (
            cliente_avulso_salvo não é Nenhum
            e st.session_state.get("assinatura_cliente_avulso")
            == assinatura_busca_atual
        )

        se cliente_confirmado:
            st.sucesso(
                f"Cliente encontrado: "
                f"{cliente_avulso_salvo.get('nome', '')} "
                f"(BOX {cliente_avulso_salvo.get('caixa', '')})"
            )
        outro:
            st.info(
                "Informe o BOX e clique em “Buscar cliente” antes de emitir."
            )

        descrição_avulsa = st.text_area(
            "Desencadeado do boleto",
            espaço reservado=(
                "Ex.: Taxa de venda\n"
                "Multa contratual\n"
                "Outra descrição"
            ),
            altura=120,
            chave="descricao_boleto_avulso"
        )

        col_valor_avulso, col_venc_avulso = st.columns(2)

        valor_avulso = col_valor_avulso.número_input(
            "Valor do boleto",
            valor_mínimo=0,00,
            passo=0,01,
            formato="%.2f",
            chave="valor_boleto_avulso"
        )

        vencimento_avulso = col_venc_avulso.date_input(
            "Vencimento do boleto",
            valor=próximo_dia_10(),
            valor_mínimo=data.hoje(),
            formato="DD/MM/AAAA",
            key="vencimento_boleto_avulso"
        )

        pode_emitir_avulso = (
            cliente_confirmado
            e bool(str(descrição_avulsa).strip())
            e float(valor_avulso) > 0
        )

        clicou_emitir_avulso = st.button(
            "💳 Emitir boleto avulso",
            tipo="primário",
            use_container_width=True,
            desativado=não pode_emitir_avulso,
            chave="emitir_boleto_avulso"
        )

        se clicou_emitir_avulso:
            tentar:
                with st.spinner("Gerando boleto avulso no Asaas..."):
                    # Usa a mesma rotina de localização, notificações e
                    # proteção contra duplicidade do fluxo já existente.
                    boleto_avulso = emitir_boleto_asaas(
                        f"BOX {int(numero_box_avulso)}.txt",
                        0,0,
                        float(valor_avulso),
                        virada_avulso,
                        str(descrição_avulsa).strip(),
                        Falso
                    )

                st.session_state["resultado_boleto_avulso"] = boleto_avulso
                st.session_state["assinatura_resultado_boleto_avulso"] = (
                    EMPRESA_SELECIONADA,
                    int(numero_box_avulso),
                    round(float(valor_avulso), 2),
                    vencimento_avulso.isoformat(),
                    str(descrição_avulsa).strip(),
                )

            exceto Exceção como erro_boleto_avulso:
                st.erro(
                    f"Não foi possível emitir o boleto avulso: "
                    f"{erro_boleto_avulso}"
                )

        assinatura_resultado_atual = Nenhuma
        se numero_box_avulso não for Nenhum:
            assinatura_resultado_atual = (
                EMPRESA_SELECIONADA,
                int(numero_box_avulso),
                round(float(valor_avulso), 2),
                vencimento_avulso.isoformat(),
                str(descrição_avulsa).strip(),
            )

        boleto_avulso_salvo = st.session_state.get(
            "resultado_boleto_avulso"
        )

        se (
            boleto_avulso_salvo
            e st.session_state.get(
                "assinatura_resultado_boleto_avulso"
            ) == assinatura_resultado_atual
        ):
            if boleto_avulso_salvo.get("novo"):
                st.sucesso(
                    f"✅ Boleto avulso criado para "
                    f"{boleto_avulso_salvo.get('clienteNome', '')} "
                    f"(BOX {boleto_avulso_salvo.get('box', '')}) e "
                    f"notificações padronizadas com sucesso."
                    f"ID: {boleto_avulso_salvo.get('id', '')}"
                )
            outro:
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

se "uploader_key" não estiver em st.session_state:
    st.session_state.uploader_key = 0

arquivos = st.file_uploader(
    "Carregue os extratos",
    tipo=["pdf", "xlsx", "xls", "csv"],
    aceitar_múltiplos_arquivos=Verdadeiro,
    help="Você pode selecionar vários arquivos de uma só vez.",
    chave=f"uploader_{st.session_state.uploader_key}"
)

se arquivos:
    se st.botão(
        "🗑️ Limpar todos os arquivos",
        tipo="secundário",
        help="Remover todos os extratos carregados desta remessa."
    ):
        st.session_state.uploader_key += 1

        # Limpe também os editores das remessas anteriores.
        fila_para_apagar = [
            chave
            para chave em list(st.session_state.keys())
            se str(chave).startswith("editor_")
        ]

        para chave em chaves_para_apagar:
            del st.session_state[chave]

        st.rerun()

se não houver arquivos:
    st.info(
        "Selecione um ou vários arquivos PDF, Excel ou CSV para começar."
    )

outro:
    st.sucesso(
        f"{len(arquivos)} arquivo(s) carregado(s)."
    )

    resultados = []
    exportação_de_verdade = {}

    st.subheader("Resumo dos arquivos")
    st.caption(
        "Clique em qualquer linha para abrir e editar as movimentações desse arquivo."
    )

    total_faturamento = 0.0
    total_royalties = 0,0

    para índice, arquivo in enumerate(arquivos):
        tentar:
            # Reiniciar variáveis ​​desta linha para não reaproveitar dados do arquivo anterior.
            editada = Nenhuma
            selecionados = Nenhum
            faturamento = Nenhum
            royalties = Nenhum
            vencimento = próximo_dia_10()

            dados = processar_arquivo(arquivo)

            visiveis = dados[
                dados["Classificação"].isin(
                    ["FATURAMENTO", "REVISAR"]
                )
            ].cópia()

            editor_chave = (
                f"editor_{índice}_"
                + re.sub(
                    r"[^a-zA-Z0-9_]",
                    "_",
                    nome do arquivo
                )
            )

            # Primeiro calcule com a seleção padrão para exibir no título.
            selecionadoss_padrao = visiveis[
                visiveis["Considerar"] == Verdadeiro
            ].cópia()

            faturamento_padrao = (
                pd.para_numérico(
                    selecionado_padrao["Valor"],
                    erros="coagir"
                )
                .fillna(0)
                .soma()
            )

            royalties_padrao = (
                faturamento_padrão
                * ROYALTIES_PERCENTUAIS
            )

            valor_faturamento_titulo = formatar_moeda(
                faturamento_padrão
            ).replace("$", r"\$")

            valor_royalties_titulo = formatar_moeda(
                royalties_padrao
            ).replace("$", r"\$")

            # Exibição padronizada do BOX no resumo.
            # Não depende do texto completo do arquivo e evita que o navegador
            # traduza "box" para "caixa".
            numero_box_resumo = extrair_numero_box(arquivo.name)

            se numero_box_resumo não for None:
                # Caracteres Unicode visualmente equivalentes impedem o
                # tradutor automático do navegador de interpretação BOX como palavra inglesa.
                nome_resumo = f"BΟX {numero_box_resumo:02d}" # O é ômicron grego
            outro:
                nome_resumo = Caminho(arquivo.nome).stem

            título_linha = (
                f"📄 {nome_resumo}"
                f" | Faturamento: :green[{valor_faturamento_titulo}]"
                f" | Royalties 4%: :green[{valor_royalties_titulo}]"
            )

            com st.expander(
                titulo_linha,
                expandido=Falso
            ):
                st.caption(
                    "Desmarque qualquer valor que não queira considerar no faturamento."
                )

                editada = st.data_editor(
                    visivo
                        [
                            "Dados",
                            "Ded",
                            "Valentia",
                            "Classificação",
                            "Considerar",
                        ]
                    ],
                    use_container_width=True,
                    ocultar_índice=Verdadeiro,
                    chave=editor_chave,
                    configuração_coluna={
                        "Considerar":
                            st.column_config.CheckboxColumn(
                                "Considerar"
                            ),
                        "Valentia":
                            st.column_config.NumberColumn(
                                "Valentia",
                                formato="R$ %.2f"
                            ),
                    },
                    desativado=[
                        "Dados",
                        "Ded",
                        "Valentia",
                        "Classificação",
                    ],
                )

                selecionados = editada[
                    editada["Considerar"] == True
                ].cópia()

                faturamento = (
                    pd.para_numérico(
                        selecionado["Valor"],
                        erros="coagir"
                    )
                    .fillna(0)
                    .soma()
                )



                # ====================================================
                # OUTRO EXTRATO / MAQUININHA
                # ====================================================

                chave_area_outro = f"outro_extrato_area_{índice}"

                st.markdown(
                    f"""
                    <style>
                    .st-key-{chave_area_outro} {{
                        cor de fundo: #f0fdf4 !importante;
                        borda: 1px sólida #86efac !importante;
                        border-radius: 14px !important;
                        preenchimento: 18px 20px 16px 20px !importante;
                        margem superior: 8px !importante;
                        margem-inferior: 22px !importante;
                    }}

                    .st-key-{chave_area_outro} [data-testid="stFileUploader"] {{
                        fundo: transparente !importante;
                    }}

                    .st-key-{chave_area_outro} [data-testid="stExpander"] {{
                        fundo: rgba(255, 255, 255, 0.72) !importante;
                        border-radius: 10px !important;
                    }}
                    </style>
                    "",
                    unsafe_allow_html=True
                )

                com st.container(
                    borda=False,
                    chave=chave_área_outro
                ):
                    st.markdown("#### Outro extrato / maquininha")
                    st.caption(
                        "Área destinada às entradas de extratos adicionais"
                        "(Stone, InfinitePay, Mercado Pago e outros formatos). "
                        "O valor confirmado aqui será somado ao faturamento total."
                    )

                    outros_arquivos = st.file_uploader(
                        "Carregar outro extrato",
                        tipo=["pdf", "xlsx", "xls", "csv", "ofx"],
                        aceitar_múltiplos_arquivos=Verdadeiro,
                        ajuda=(
                            "Aceita PDF, Excel, CSV e OFX."
                            "O sistema sincronizado automaticamente Stone,"
                            "InfinitePay e Mercado Pago e também tenta"
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
                        f"outro_extrato_assinatura_{índice}"
                    )

                    se outros_arquivos:
                        assinatura_atual_outro = (
                            assinatura_arquivos_adicionais(
                                outros_arquivos
                            )
                        )

                        se (
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
                            ] = Falso

                        totais_por_arquivo = []

                        para índice_outro, arquivo_outro em enumerate(
                            outros_arquivos
                        ):
                            tentar:
                                (
                                    dados_outro,
                                    origem_outro,
                                ) = som_outro_extrato(
                                    arquivo_outro
                                )

                                # Segurança contra erro de CheckboxColumn
                                # receba FLOAT em vez de booleano.
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

                                com st.expander(
                                    (
                                        f"🔎 Ver sempre — "
                                        f"{arquivo_outro.name} "
                                        f"({origem_outro})"
                                    ),
                                    expandido=Falso
                                ):
                                    st.caption(
                                        "Desmarque qualquer entrada que "
                                        "não quero somar ao faturamento."
                                    )

                                    editado_outro = st.data_editor(
                                        dados_outro,
                                        use_container_width=True,
                                        ocultar_índice=Verdadeiro,
                                        chave=chave_editor_outro,
                                        configuração_coluna={
                                            "Considerar":
                                                st.column_config.CheckboxColumn(
                                                    "Considerar"
                                                ),
                                            "Valentia":
                                                st.column_config.NumberColumn(
                                                    "Valentia",
                                                    formato="R$ %.2f"
                                                ),
                                        },
                                        desativado=[
                                            "Dados",
                                            "Ded",
                                            "Valentia",
                                            "Classificação",
                                        ],
                                    )

                                selecionado_outro = editado_outro[
                                    editado_outro["Considerar"] == Verdadeiro
                                ].cópia()

                                total_arquivo_outro = (
                                    pd.para_numérico(
                                        selecionado_outro["Valor"],
                                        erros="coagir"
                                    )
                                    .fillna(0)
                                    .soma()
                                )

                                quantidade_arquivo_outro = len(
                                    selecionado_outro
                                )

                                valor_outros_extratos += float(
                                    total_arquivo_outro
                                )

                                quantidade_outros_extratos += (
                                    outro_arquivo
                                )

                                totais_por_arquivo.append(
                                    (
                                        arquivo_outro.name,
                                        origem_outro,
                                        float(total_arquivo_outro),
                                    )
                                )

                            exceto Exceção como erro_outro:
                                st.erro(
                                    f"Erro ao"
                                    f"{arquivo_outro.name}: "
                                    f"{erro_outro}"
                                )

                        para (
                            nome_outro,
                            origem_outro,
                            total_outro,
                        ) em totais_por_arquivo:
                            st.caption(
                                f"{origem_outro} • {nome_outro} • "
                                f"Entradas: "
                                f"{formatar_moeda(total_outro)}"
                            )

                        col_total_outro, col_ok_outro, col_espaco_outro = st.columns(
                            [1,05, 0,60, 2,35]
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

                        se chave_confirmacao_outro não estiver em st.session_state:
                            st.session_state[
                                chave_confirmacao_outro
                            ] = Falso

                        se não st.session_state[
                            chave_confirmacao_outro
                        ]:
                            clicou_ok_outro = col_ok_outro.button(
                                "OK —fera",
                                tipo="secundário",
                                use_container_width=True,
                                desativado=(
                                    valor_outros_extratos <= 0
                                ),
                                key=f"confirmar_outro_{indice}"
                            )

                            se clicou_ok_outro:
                                st.session_state[
                                    chave_confirmacao_outro
                                ] = Verdadeiro
                        outro:
                            col_ok_outro.success(
                                "✅ Adicionado ao faturamento"
                            )

                            se col_ok_outro.button(
                                "Removedor do faturamento",
                                use_container_width=True,
                                chave=f"remover_outro_{índice}"
                            ):
                                st.session_state[
                                    chave_confirmacao_outro
                                ] = Falso
                                st.rerun()

                        se st.session_state.get(
                            chave_confirmacao_outro,
                            Falso
                        ):
                            faturamento = (
                                flutuar (faturamento)
                                + float(valor_outros_extratos)
                            )

                            st.caption(
                                "O valor acima já está incluído no faturamento total."
                                "Se você desmarcar uma entrada em “Ver detalhes”, "
                                "o total será recalculado automaticamente."
                            )
                        outro:
                            passar


                st.markdown("#### Adicionar valor ao faturamento")

                # Layout organizado
                col_esq, col_centro, col_dir = st.columns([0,85, 1,15, 0,75])
    
                # ==========================================
                # COLUNA ESQUERDA
                # ==========================================
    
                adicional_texto = col_esq.text_input(
                    "Valor adicional ao faturamento",
                    valor="0,00",
                    key=f"adicional_boleto_{índice}",
                    ajuda=(
                        "Digite um valor positivo para somar ou negativo para diminuir o faturamento. "
                        "Ex.: 500,00 soma; -500,00 diminuída. Os royalties de 4% serão recalculados sobre o novo total."
                    )
                )
    
                boleto_adicional = conversor_numero(adicional_texto)
    
                se adicional_boleto for None:
                    boleto_adicional = 0,0
                    col_esq.warning("Digite um valor válido, por exemplo: 100,00")
    
    
                #Recalcula faturamento e royalties
                faturamento = (
                    flutuar (faturamento)
                    + float(boleto_adicional)
                )
    
                royalties = (
                    flutuar (faturamento)
                    * ROYALTIES_PERCENTUAIS
                )
    
                # Valor final do boleto editável
                # Atualiza automaticamente quando os royalties mudam,
                # mas preserve uma alteração manual feita pelo usuário.
                chave_valor_boleto = f"valor_final_boleto_{índice}"
                chave_valor_auto = f"valor_final_boleto_auto_{índice}"
                novo_valor_auto = arredondar(float(royalties), 2)

                se chave_valor_boleto não estiver em st.session_state:
                    # Primeira exibição: usa automaticamente 4% do faturamento total.
                    st.session_state[chave_valor_boleto] = novo_valor_auto

                elif chave_valor_auto in st.session_state:
                    valor_auto_anterior = float(
                        st.session_state[chave_valor_auto]
                    )

                    # Se o faturamento mudou (inclusive por valor adicional
                    # ou seleção/desseleção de entradas), recalcula os 4%
                    # e atualiza também o valor final do boleto.
                    if abs(novo_valor_auto - valor_auto_anterior) >= 0,005:
                        st.session_state[chave_valor_boleto] = novo_valor_auto

                st.estado_sessão[chave_valor_auto] = novo_valor_auto

                valor_final_boleto = col_esq.número_input(
                    "Valor final do boleto",
                    valor_mínimo=0,00,
                    passo=0,01,
                    formato="%.2f",
                    chave=chave_valor_boleto
                )

                # O valor grande de Royalties acompanha o valor final do boleto.
                # O cálculo automático de 4% continua sendo usado como valor-base
                # antes de qualquer ajuste manual.
                royalties = float(valor_final_boleto)
    
                # ==========================================
                # COLUNA CENTRAL
                # ==========================================
    
                col_centro.métrica(
                    "Total do faturamento",
                    formatar_moeda(faturamento)
                )
    
                col_centro.métrica(
                    "Royalties 4%",
                    formatar_moeda(royalties)
                )
    
                # ==========================================
                # COLUNA DIREITA
                # ==========================================
    
                col_dir.métrica(
                    "Entradas considerando",
                    (
                        len(selecionadas)
                        + (
                            outros_extratos
                            se st.session_state.get(
                                chave_confirmacao_outro,
                                Falso
                            )
                            caso contrário 0
                        )
                    )
                )
    
                    
                st.markdown(f"#### Cobrança Asaas — {EMPRESA_SELECIONADA}")
                col_venc, col_botao = st.colunas([2, 1])
                descricao_boleto = "Royalties"
                vencimento = col_venc.date_input(
                    "Vencimento do boleto",
                    valor=próximo_dia_10(),
                    valor_mínimo=data.hoje(),
                    formato="DD/MM/AAAA",
                    chave=f"vencimento_{índice}"
                )
    
                chave_boleto = (
                    f"boleto_{índice}_"
                    + re.sub(r"[^a-zA-Z0-9_]", "_", arquivo.name)
                )
    
    
                if EMPRESA_SELECIONADA == "Líder Franquia":
                        emitir_nota_apos_pagamento = col_botao.checkbox(
                            "Emitir nota fiscal de Royalties após o pagamento",
                            valor=Falso,
                            chave=f"emitir_nota_{índice}"
                    )
                outro:
                        emitir_nota_apos_pagamento = Falso
    
                clicou_emitir_boleto = col_botao.button(
                    "💳 Emitir boleto",
                    chave=chave_boleto,
                    tipo="primário",
                    use_container_width=True,
                    desativado=valor_final_boleto <= 0
                )
    
                se clicou_emitir_boleto:
                    tentar:
                        with st.spinner("Gerando boleto no Asaas..."):
                            boleto = emitir_boleto_asaas(
                                nome.do.arquivo,
                                Vaso sanitário,
                                valor_final_boleto,
                                não,
                                descricao_boleto,
                                emitir_nota_apos_pagamento
                            )

                        st.session_state[f"resultado_boleto_{indice}"] = boleto

                    exceto Exceção como erro_boleto:
                        st.erro(
                            f"Não foi possível emitir o boleto: {erro_boleto}"
                        )

                boleto_salvo = st.session_state.get(
                    f"resultado_boleto_{indice}"
                )

                se boleto_salvo:
                    se boleto_salvo.get("novo"):
                        st.sucesso(
                            f"✅ Boleto criado para "
                            f"{boleto_salvo.get('clienteNome', '')} "
                            f"(BOX {boleto_salvo.get('box', '')}) "
                            f"e notificações padronizadas com sucesso."
                            f"ID: {boleto_salvo.get('id', '')}"
                        )
                    outro:
                        st.info(
                            "ℹ️ Esta cobrança já existia no Asaas. "
                            "O sistema não gerou uma cobrança duplicada."
                        )

                    se boleto_salvo.get("invoiceUrl"):
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
                "Arquivo": nome.do.arquivo,
                "Faturamento": faturamento,
                "Royalties 4%": royalties,
            })

            aviso_exportação[
                nome do arquivo
            ] = editada.copy()

            total_faturamento += faturamento
            total_royalties += royalties

        exceto Exception como erro:
            st.erro(
                f"Erro ao processar {arquivo.name}: {erro}"
            )

            resultados.append({
                "Arquivo": nome.do.arquivo,
                "Faturamento": 0,0,
                "Royalties 4%": 0,0,
            })

    st.divider()

    col_total1, col_total2 = st.columns(2)

    col_total1.métrica(
        "Faturamento total geral",
        formatar_moeda(total_faturamento)
    )
    
    col_total2.métrica(
        "Royalties 4% no total",
        formatar_moeda(total_royalties)
    )
    
    # ========================================================
    # DOWNLOAD DO RELATÓRIO GERAL
    # ========================================================
    
    resumo = pd.DataFrame(resultados)

    excel_geral = gerar_excel_geral(
    resumo,
    exportação_do_imigrante
)
    
    st.download_button(
        "📥 Baixar relatório geral em Excel",
        dados=excel_geral,
        file_name="relatorio_geral_faturamento.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
