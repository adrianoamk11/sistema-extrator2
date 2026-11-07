import streamlit as st
import pandas as pd
import fitz
import time
from st_keyup import st_keyup
from conciliacao_fiscal import consultar_nfse_por_pagamento
from operacao_financeira import (
    operacao_financeira_unica, marcar_resultado_inconclusivo,
    resposta_inconclusiva,
)
from recorrencia_avulsa import (
    criar_recorrencia,
    listar_recorrencias_extrator,
    suspender_recorrencia,
)
from busca_clientes_cidade import listar_clientes_para_autocomplete, filtrar_autocomplete
from extratos_bancos_pdf import extrair_pdf_bancario
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
    # Apresentação visual; a validação das credenciais permanece inalterada.
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg,#E9F7EE 0%,#F4F9FF 54%,#FFF4DB 100%);
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 1060px;
        padding-top: 12vh !important;
    }
    div[data-testid="stForm"] {
        background: #FFFFFF;
        border: 1px solid #DFEAE4;
        border-radius: 19px;
        padding: 1.8rem;
        box-shadow: 0 15px 46px rgba(22,67,45,.1);
    }
    div[data-testid="stFormSubmitButton"] button {
        background: #177A45 !important;
        border-color: #177A45 !important;
        color: white !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        min-height: 44px;
    }
    div[data-testid="stFormSubmitButton"] button:hover {
        background: #126638 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    coluna_marca, login_coluna = st.columns([1, 1], gap="large")
    with coluna_marca:
        logo_login = Path(__file__).resolve().parent / "logo_lider.png"
        if logo_login.exists():
            st.image(str(logo_login), width=315)
        st.markdown("""
        <div style="padding-top:1rem">
          <div style="font-size:.81rem;letter-spacing:.1em;color:#177A45;font-weight:800">
            GESTÃO FINANCEIRA
          </div>
          <div style="font-size:2.2rem;font-weight:800;color:#143F2C;line-height:1.2;margin-top:.6rem">
            Extrator de<br>Faturamento
          </div>
          <p style="color:#60776A;margin-top:1rem;font-size:1rem">
            Um espaço organizado para seus extratos, cobranças e relatórios.
          </p>
        </div>
        """, unsafe_allow_html=True)
    with login_coluna:
        st.subheader("Acesso ao sistema")
        st.caption("Entre com suas credenciais para continuar.")
        with st.form("formulario_login"):
            usuario = st.text_input("Usuário", key="login_usuario")
            senha = st.text_input("Senha", type="password", key="login_senha")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            if (
                usuario == st.secrets["LOGIN_USUARIO"]
                and senha == st.secrets["LOGIN_SENHA"]
            ):
                st.session_state.autenticado = True
                st.session_state.pop("login_senha", None)
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

    st.stop()
# ============================================
# CAMADA VISUAL — sem alterar regras financeiras
# ============================================
st.markdown("""
<style>
:root {
  --lider-verde: #177A45;
  --lider-escuro: #143F2C;
  --lider-azul: #2563EB;
  --lider-amarelo: #E5A800;
  --lider-laranja: #D97706;
}
[data-testid="stHeader"] { background: rgba(255,255,255,.82); }
[data-testid="stMainBlockContainer"] {
  max-width: 1500px;
  padding: 4.2rem 2.5rem 4rem !important;
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg,#E8F5ED 0%,#F1F7FC 60%,#FFF8E7 100%) !important;
  border-right: 1px solid #D7E7DF;
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding-top: .65rem !important;
}
[data-testid="stSidebar"] [data-testid="stImage"] {
  margin: 0 0 .15rem !important;
}
.lider-sidebar-caption {
  font-size: .76rem;
  color: #557063;
  letter-spacing: .06em;
  font-weight: 800;
  text-transform: uppercase;
  padding: .15rem .5rem .35rem;
}
.lider-nav {
  display: flex;
  flex-direction: column;
  gap: .55rem;
  margin-bottom: .5rem;
}
.lider-nav a {
  display: block;
  border-radius: 11px;
  font-size: .94rem;
  font-weight: 650;
  padding: .78rem 1rem;
  text-decoration: none !important;
  transition: transform .12s,filter .12s;
}
.lider-nav a:hover { filter: brightness(.97); transform: translateX(2px); }
.lider-nav .inicio { background: #D2F2DE; color: #14532D !important; }
.lider-nav .extratos { background: #DCEAFF; color: #1D4ED8 !important; }
.lider-nav .historico { background: #FFEDD5; color: #9A3412 !important; }
[data-testid="stSidebar"] .stButton button {
  border-radius: 11px !important;
  font-weight: 700 !important;
  min-height: 44px;
}
[data-testid="stSidebar"] .st-key-navegar_Início button {
  background: #D2F2DE !important; color: #14532D !important; border-color: #C3E9D0 !important;
}
[data-testid="stSidebar"] .st-key-navegar_Extratos button {
  background: #DCEAFF !important; color: #1D4ED8 !important; border-color: #BED7FC !important;
}
[data-testid="stSidebar"] .st-key-navegar_Histórico button {
  background: #FFEDD5 !important; color: #9A3412 !important; border-color: #FED7AA !important;
}
[data-testid="stSidebar"] .st-key-abrir_fechar_boleto_avulso button {
  background: #FFF0BF !important; color: #8C5600 !important; border-color: #F4D783 !important;
}
[data-testid="stSidebar"] .stButton button:hover { filter: brightness(.95); }
.lider-hero {
  background: linear-gradient(105deg,#143F2C 0%,#177A45 67%,#219B64 100%);
  border-radius: 18px;
  color: white;
  padding: 1.5rem 1.9rem;
  margin: .35rem 0 1.1rem;
  box-shadow: 0 10px 24px rgba(20,63,44,.13);
}
.lider-hero h1 {
  color: white !important;
  font-size: clamp(1.45rem,2.5vw,2.1rem);
  font-weight: 760;
  margin: 0 0 .3rem;
  line-height: 1.2;
}
.lider-hero p { color: #D9FBE7; font-size: .92rem; margin: 0; }
.lider-section-title {
  color: #173D2B;
  font-weight: 750;
  font-size: 1.12rem;
  margin: 1.4rem 0 .65rem;
}
[data-testid="stFileUploaderDropzone"] {
  background: #F0F7FF !important;
  border: 2px dashed #8EB9F8 !important;
  border-radius: 15px !important;
  padding: 1.2rem !important;
}
[data-testid="stFileUploaderDropzone"]:hover { background: #E7F1FF !important; }
div[data-testid="stVerticalBlockBorderWrapper"] > div[style*="border"] {
  border-radius: 14px !important;
}
div[data-testid="stButton"] button {
  border-radius: 10px !important;
  font-weight: 650 !important;
}
div[data-testid="stButton"] button[kind="primary"] {
  background: #177A45 !important;
  color: white !important;
  border-color: #177A45 !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
  background: #126538 !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
  border-radius: 10px !important;
}
[data-testid="stAlert"] { border-radius: 11px !important; }
/* Não exibir como botão ativo quando os campos obrigatórios faltarem. */
[data-testid="stButton"] button:disabled,
[data-testid="stButton"] button[kind="primary"]:disabled {
  background: #E4E7EB !important;
  color: #65717F !important;
  border-color: #D2D7DE !important;
  cursor: not-allowed !important;
  opacity: 1 !important;
}
@media(max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding: .7rem 1rem 3rem !important; }
  .lider-hero { padding: 1.2rem; }
}
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo_lider.png"

# O arquivo da logomarca original é reutilizado sem alterações.
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=215)
    st.markdown('<div class="lider-sidebar-caption">Navegação</div>', unsafe_allow_html=True)
    if "pagina_lider" not in st.session_state:
        st.session_state.pagina_lider = "Extratos"
    for rotulo, pagina in (
        ("🏠 Início", "Início"),
        ("📘 Extratos", "Extratos"),
        ("🕘 Histórico", "Histórico"),
    ):
        if st.button(rotulo, key=f"navegar_{pagina}", use_container_width=True,
                     type="primary" if st.session_state.pagina_lider == pagina else "secondary"):
            st.session_state.pagina_lider = pagina

st.markdown(
    '<meta name="google" content="notranslate">'
    '<div id="inicio" class="lider-hero">'
    '<h1>Extrator de Faturamento</h1>'
    '<p>LÍDER Aluguel de Motos &nbsp;·&nbsp; PDF, Excel (.xlsx/.xls) e CSV</p>'
    '</div>',
    unsafe_allow_html=True,
)

# ============================================================
# CONFIGURAÇÕES
# ============================================================

PERCENTUAL_ROYALTIES = 0.04

# ============================================================
# ASAAS - SELEÇÃO DA EMPRESA
# ============================================================

if "mostrar_boleto_avulso" not in st.session_state:
    st.session_state.mostrar_boleto_avulso = False

# Os controles originais foram apenas posicionados no menu lateral.
with st.sidebar:
    st.markdown('<div class="lider-sidebar-caption">Empresa</div>', unsafe_allow_html=True)
    EMPRESA_SELECIONADA = st.selectbox(
        "Empresa",
        ["Lider Franquia", "Lider Serviços"],
        label_visibility="collapsed"
    )
    st.markdown('<div class="lider-sidebar-caption">Cobranças</div>', unsafe_allow_html=True)
    if st.button(
        "💳 Boleto avulso",
        type="secondary",
        use_container_width=True,
        key="abrir_fechar_boleto_avulso"
    ):
        st.session_state.mostrar_boleto_avulso = (
            not st.session_state.mostrar_boleto_avulso
        )
        if st.session_state.mostrar_boleto_avulso:
            st.session_state.pagina_lider = "Boleto avulso"
        else:
            st.session_state.pagina_lider = "Extratos"

st.markdown('<div class="lider-section-title">Processamento de extratos</div>', unsafe_allow_html=True)

# ============================================================
# IDENTIDADE VISUAL POR EMPRESA
# ============================================================
# A Líder Franquia mantém o fundo branco.
# A Líder Serviços usa um amarelo suave em toda a área do sistema
# para reduzir o risco de operar na empresa errada.
if EMPRESA_SELECIONADA == "Lider Serviços":
    st.markdown(
        """
        <style>
        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background-color: #FFF8D8 !important;
        }

        /* Mantém componentes de entrada claros e fáceis de ler. */
        [data-testid="stFileUploaderDropzone"],
        [data-testid="stDataFrame"],
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div {
            background-color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
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
    """Busca o BOX usando a lista de clientes mantida em cache por empresa."""
    numero_box = extrair_numero_box(Path(nome_arquivo).stem)
    if numero_box is None:
        raise RuntimeError(
            "Não encontrei o número do BOX no nome do arquivo. "
            "Renomeie o arquivo incluindo, por exemplo, 'BOX 25'."
        )

    encontrados = [
        cliente for cliente in clientes_avulsos_em_cache()
        if extrair_numero_box(str(cliente.get("name") or "")) == numero_box
    ]
    if len(encontrados) == 1:
        return encontrados[0], numero_box
    if not encontrados:
        raise RuntimeError(
            f"Não encontrei no Asaas nenhum cliente com BOX {numero_box}. "
            "Confira o número e o cadastro do cliente."
        )
    nomes = " | ".join(str(c.get("name") or "") for c in encontrados[:5])
    raise RuntimeError(
        f"Encontrei {len(encontrados)} clientes com BOX {numero_box}: {nomes}. "
        "Para evitar cobrar a pessoa errada, selecione o cadastro correto."
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

    # O padrão já está aplicado? Evita PUT desnecessário em cada boleto.
    if all(
        all(
            original.get(campo) == valor
            for campo, valor in desejada.items()
            if campo != "id"
        )
        for original, desejada in zip(notificacoes, atualizacoes)
    ):
        return True

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
    """Somente leitura: impede reutilizar cobrança errada ou ambígua."""
    resposta = requests.get(
        f"{ASAAS_BASE_URL}/payments",
        headers=cabecalhos_asaas(),
        params={"externalReference": external_reference, "limit": 100},
        timeout=30,
    )
    resposta.raise_for_status()
    corpo = resposta.json()
    if not isinstance(corpo, dict) or not isinstance(corpo.get("data"), list):
        raise RuntimeError("Resposta inválida ao conciliar cobrança no Asaas.")
    # A referência completa precisa corresponder; não usar primeira cobrança
    # de uma lista que possa conter filtros aplicados de forma inesperada.
    itens = corpo["data"]
    if any(
        not isinstance(p, dict) or p.get("externalReference") != external_reference
        for p in itens
    ):
        raise RuntimeError("A consulta retornou cobrança com referência divergente.")
    if corpo.get("hasMore") or len(itens) > 1:
        raise RuntimeError(
            "Foram encontradas cobranças repetidas com a mesma referência. "
            "Concilie manualmente no Asaas antes de emitir novamente."
        )
    return itens[0] if itens else None

def emitir_boleto_asaas(
    nome_arquivo,
    faturamento,
    valor_cobranca,
    vencimento,
    descricao_boleto,
    emitir_nota=False,
    cliente_selecionado_id=None,
):
    if cliente_selecionado_id is None:
        cliente, numero_box = localizar_cliente_asaas_por_box(nome_arquivo)
    else:
        # Busca avulsa por cidade: recupera o cadastro indicado, sem
        # selecionar automaticamente um pagador só pelo nome da cidade.
        identificador = str(cliente_selecionado_id).strip()
        if not re.fullmatch(r"cus_[A-Za-z0-9]+", identificador):
            raise RuntimeError("Identificador de cliente Asaas inválido.")
        resposta_cliente = requests.get(
            f"{ASAAS_BASE_URL}/customers/{identificador}",
            headers=cabecalhos_asaas(),
            timeout=30,
        )
        resposta_cliente.raise_for_status()
        cliente = resposta_cliente.json()
        if cliente.get("id") != identificador:
            raise RuntimeError("O Asaas retornou um cadastro diferente do selecionado.")
        numero_box = extrair_numero_box(str(cliente.get("name") or ""))
    customer_id = cliente.get("id")
    nome_cliente = cliente.get("name", "")

    if not customer_id:
        raise RuntimeError(
            f"O cliente do BOX {numero_box} foi encontrado, "
            f"mas o Asaas não retornou um ID válido."
        )

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

    referencia_base = external_reference
    if emitir_nota:
        external_reference = f"{referencia_base}|NFSE|"

    chave_operacao_financeira = (ASAAS_BASE_URL, referencia_base)
    # A busca por cobrança existente e a criação ficam sob um único bloqueio
    # por processo. As chaves do Asaas e seus webhooks não são modificados.
    with operacao_financeira_unica(chave_operacao_financeira):
        # Não criar outro boleto se a mesma operação já foi cobrada com a
        # opção de nota fiscal diferente. A cobrança existente deve ser conciliada.
        referencia_alternativa = (
            referencia_base if emitir_nota else f"{referencia_base}|NFSE|"
        )
        # Compatibilidade com boletos avulsos já criados pela busca por cidade
        # na versão anterior: a referência usava CLIENTE {id}, mesmo com BOX.
        # Consulta somente leitura; evita duplicidade ao alternar modos de busca.
        if cliente_selecionado_id is not None and numero_box is not None:
            referencia_legada = criar_referencia_externa(
                f"CLIENTE {customer_id}.txt",
                valor_cobranca,
                vencimento,
                descricao_final,
            )
            if referencia_legada != referencia_base:
                existente_legado = buscar_cobranca_existente(referencia_legada)
                if existente_legado:
                    return {
                        "novo": False,
                        "clienteNome": cliente.get("name"),
                        "clienteId": customer_id,
                        "box": numero_box,
                        "id": existente_legado.get("id"),
                        "invoiceUrl": existente_legado.get("invoiceUrl"),
                        "bankSlipUrl": existente_legado.get("bankSlipUrl"),
                        "status": existente_legado.get("status"),
                        "externalReference": referencia_legada,
                    }

        cobranca_alternativa = buscar_cobranca_existente(referencia_alternativa)
        if cobranca_alternativa:
            raise RuntimeError(
                "Já existe uma cobrança para esta operação no Asaas "
                f"({cobranca_alternativa.get('id', 'ID não informado')}). "
                "A opção de nota fiscal é diferente. Não foi criado outro boleto; "
                "concilie a cobrança existente antes de prosseguir."
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

        # O padrão de notificações é reaplicado só se diferente do atual.
        padronizar_notificacoes_asaas(customer_id)

        try:
            resposta = requests.post(
                f"{ASAAS_BASE_URL}/payments",
                headers=cabecalhos_asaas(),
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise RuntimeError(
                "Não foi possível confirmar se o Asaas criou a cobrança. "
                "Confira a referência no Asaas; não repita até conciliar."
            ) from exc

        if not resposta.ok:
            if resposta_inconclusiva(resposta.status_code):
                marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise RuntimeError(
                f"Asaas retornou HTTP {resposta.status_code}. "
                "Verifique o resultado e o cadastro diretamente no Asaas "
                "antes de tentar novamente."
            )

        try:
            dados = resposta.json()
        except ValueError as exc:
            marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise RuntimeError(
                "Asaas respondeu sem confirmação verificável. "
                "Confira a cobrança no provedor antes de repetir."
            ) from exc
        if not isinstance(dados, dict) or not str(dados.get("id") or "").startswith("pay_"):
            marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise RuntimeError(
                "O Asaas não confirmou o identificador da cobrança. "
                "É necessária conciliação antes de nova emissão."
            )

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

def _ler_pdf_digital(documento):
    """Mantém o leitor original para PDFs com camada de texto."""
    linhas = []
    for pagina in documento:
        linhas += [
            re.sub(r"\s+", " ", linha).strip()
            for linha in pagina.get_text().splitlines()
            if linha.strip()
        ]

    padrao_data = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
    padrao_valor = re.compile(r"R\$\s*(-?[\d\.]+,\d{2})")
    data_atual = ""
    contexto = []
    registros = []
    for linha in linhas:
        datas = padrao_data.findall(linha)
        if datas:
            data_atual = datas[0]
        for valor_texto in padrao_valor.findall(linha):
            descricao = " ".join(contexto[-3:] + [linha])
            descricao = padrao_valor.sub("", descricao).strip()
            registros.append({
                "Data": data_atual,
                "Descrição": descricao,
                "Valor": converter_numero(valor_texto),
            })
        contexto.append(linha)
    return registros


def _ler_pdf_imagem_asaas(documento):
    """OCR apenas quando o PDF não possui texto extraível.

    Exige pytesseract, Pillow e Tesseract instalados no servidor.
    Considera apenas linhas iniciadas por data e terminadas por valor,
    evitando confundir saldos de abertura/fechamento com movimentações.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise ValueError(
            "Este PDF é uma imagem. Instale pytesseract e Pillow "
            "no requirements.txt e tesseract-ocr no packages.txt."
        ) from exc

    padrao_linha = re.compile(
        r"^\s*(\d{2}/\d{2}/\d{4})\s+(.+?)\s+"
        r"R\$\s*([+\-−]?\s*[\d.]+,\d{2})\s*$",
        re.IGNORECASE,
    )
    registros = []
    for pagina in documento:
        # 2x oferece boa leitura mantendo consumo moderado de memória.
        pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        imagem = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        texto = pytesseract.image_to_string(imagem, config="--psm 6")
        for linha in texto.splitlines():
            linha = re.sub(r"\s+", " ", linha).strip()
            encontrado = padrao_linha.match(linha)
            if not encontrado:
                continue
            data, descricao, valor_texto = encontrado.groups()
            valor = converter_numero(valor_texto.replace("−", "-").replace(" ", ""))
            if valor is None:
                continue
            # OCR pode confundir a primeira letra de 'Cobrança'.
            # A combinação 'recebida - fatura' é específica do Asaas.
            descricao_norm = normalizar(descricao)
            if "recebida" in descricao_norm and "fatura" in descricao_norm:
                descricao = "Cobrança recebida - " + re.sub(
                    r"^.*?recebida\s*-\s*", "", descricao, count=1, flags=re.IGNORECASE
                )
            registros.append({"Data": data, "Descrição": descricao, "Valor": valor})
    return registros


def ler_pdf(arquivo):
    with fitz.open(stream=arquivo.getvalue(), filetype="pdf") as documento:
        # Prioriza leitores conhecidos e preserva integralmente o leitor anterior
        # para qualquer outro PDF, inclusive os digitalizados.
        registros = extrair_pdf_bancario(documento)
        if registros is None:
            texto_total = sum(len(pagina.get_text().strip()) for pagina in documento)
            if texto_total:
                registros = _ler_pdf_digital(documento)
            else:
                registros = _ler_pdf_imagem_asaas(documento)

    if not registros:
        raise ValueError(
            "Não encontrei movimentações legíveis neste PDF. "
            "Se for um PDF digitalizado, confira a nitidez da imagem."
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

    # InfinitePay/CloudWalk possui mais de um layout de PDF.
    # Layout novo (relatorio em portugues):
    # horario -> tipo de transacao -> nome -> detalhe -> valor.
    # Ex.: 17:00 | Pix | Pix NOME | Recebido | +356,00
    # Ex.: 05:43 | Deposito de vendas | Vendas | Deposito InfinitePay | +1.083,01
    #
    # Usar o horario como inicio da transacao evita confundir:
    # - Saldo inicial/final
    # - Total de entradas/saidas
    # - Saldo do dia
    # com movimentacoes reais.
    padrao_hora = re.compile(r"^\d{2}:\d{2}$")

    for indice, linha in enumerate(linhas):
        if not padrao_hora.fullmatch(str(linha).strip()):
            continue

        # A estrutura observada coloca o valor poucos campos depois do horario.
        # A janela um pouco maior preserva nomes que quebram em duas linhas.
        bloco = linhas[indice:min(len(linhas), indice + 9)]
        indice_valor = None
        valor = None

        for posicao in range(1, len(bloco)):
            texto_valor = str(bloco[posicao]).strip()

            # Aceita os dois formatos usados pela InfinitePay:
            # +1.176,00 (brasileiro) e +530.00 (internacional).
            if not re.fullmatch(
                r"[+\-]?\s*(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}|[+\-]?\s*(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}",
                texto_valor,
            ):
                continue

            candidato = converter_numero_flexivel(texto_valor)

            if candidato is not None:
                indice_valor = posicao
                valor = candidato
                break

        if valor is None or valor <= 0:
            continue

        descricao_partes = bloco[1:indice_valor]
        descricao = " | ".join(descricao_partes).strip()
        descricao_norm = normalizar(descricao)

        # Protecao extra: mesmo dentro de um bloco iniciado por horario,
        # nunca considerar linhas de saldo/resumo como movimentacao.
        if any(
            termo in descricao_norm
            for termo in [
                "saldo do dia",
                "saldo inicial",
                "saldo final",
                "daily balance",
                "final balance",
                "initial balance",
                "total de entradas",
                "total de saidas",
                "total inflows",
                "total outflows",
            ]
        ):
            continue

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

    # Se o layout por horario foi reconhecido, usa somente essas transacoes.
    # Isso evita duplicar valores ao executar tambem o leitor legado.
    if registros:
        return montar_tabela_outro_extrato(registros)

    # Compatibilidade com o layout antigo da InfinitePay/CloudWalk,
    # no qual os valores aparecem em linhas como +530.00.
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

        contexto = linhas[max(0, indice - 5):indice]
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



# Página inicial independente, sem criar métricas ou consultas financeiras.
if st.session_state.pagina_lider == "Início":
    st.subheader("Bem-vindo ao Extrator Líder")
    st.caption("Acesse as funções existentes pelos atalhos abaixo.")
    inicio_extratos, inicio_historico = st.columns(2)
    with inicio_extratos:
        with st.container(border=True):
            st.markdown("### 📘 Extratos")
            st.write("Importe, confira e processe seus arquivos financeiros.")
            if st.button("Abrir extratos", key="inicio_abrir_extratos", use_container_width=True):
                st.session_state.pagina_lider = "Extratos"
    with inicio_historico:
        with st.container(border=True):
            st.markdown("### 🕘 Histórico")
            st.write("Consulte cobranças anteriores diretamente no Asaas.")
            if st.button("Consultar histórico", key="inicio_abrir_historico", use_container_width=True):
                st.session_state.pagina_lider = "Histórico"

# ============================================================
# BOLETO AVULSO
# ============================================================

def clientes_avulsos_em_cache():
    """Cache por sessão/empresa: nenhuma consulta ao Asaas a cada tecla."""
    chave = (EMPRESA_SELECIONADA, ASAAS_BASE_URL)
    cache = st.session_state.get("cache_busca_avulsa")
    if (cache and cache.get("chave") == chave
            and time.monotonic() - cache.get("quando", 0) < 120):
        return cache["clientes"]
    clientes = listar_clientes_para_autocomplete(
        ASAAS_BASE_URL, cabecalhos_asaas()
    )
    st.session_state["cache_busca_avulsa"] = {
        "chave": chave, "quando": time.monotonic(), "clientes": clientes,
    }
    return clientes


@st.fragment
def exibir_boleto_avulso():
    with st.container(border=True):
        st.subheader("Boleto avulso")
        st.caption(
            f"Emissão pela empresa: {EMPRESA_SELECIONADA}. "
            "Esta cobrança não gera nota fiscal."
        )
        modo = st.radio(
            "Localizar o cliente por",
            ("BOX", "Cidade"), horizontal=True, key="modo_busca_cliente_avulso",
        )
        termo = st_keyup(
            "Digite o BOX" if modo == "BOX" else "Digite a cidade",
            key="buscar_box_avulso_instantaneo" if modo == "BOX"
                else "buscar_cidade_avulso_instantaneo",
            placeholder="Ex.: 25" if modo == "BOX"
                else "Ex.: Balneário Camboriú, Itapema, Jundiaí",
            debounce=300,
        ) or ""
        # Somente consulta. Mostra todas as correspondências sem botão Buscar.
        candidatos = []
        min_len = 1 if modo == "BOX" else 2
        if len(normalizar(termo)) >= min_len:
            try:
                with st.spinner("Consultando cadastros..." if not
                                st.session_state.get("cache_busca_avulsa") else
                                "Filtrando cadastros..."):
                    candidatos = filtrar_autocomplete(
                        clientes_avulsos_em_cache(), termo, modo
                    )
            except Exception as erro_busca:
                st.error(f"Não foi possível consultar os cadastros: {erro_busca}")
        else:
            st.caption(
                "Digite um número para localizar BOX."
                if modo == "BOX" else
                "Digite pelo menos duas letras para localizar cidades."
            )

        selecionado = None
        if candidatos:
            st.caption(
                f"{len(candidatos)} cadastro(s) encontrado(s). "
                "Selecione o cadastro correto para habilitar a emissão."
            )
            opcoes = {c["id"]: c for c in candidatos}
            escolhido = st.radio(
                "Selecione o cadastro correto antes de emitir",
                list(opcoes),
                index=None,
                key=f"escolha_avulsa_{modo.lower()}",
                format_func=lambda ident: (
                    f'{opcoes[ident]["name"]} — '
                    f'{opcoes[ident].get("cityName") or "cidade no nome"} '
                    f'({ident})'
                ),
            )
            if escolhido in opcoes:
                selecionado = opcoes[escolhido]
        elif len(normalizar(termo)) >= min_len:
            st.info("Nenhum cliente correspondente encontrado no Asaas.")

        box = extrair_numero_box(selecionado["name"]) if selecionado else None
        assinatura = (
            EMPRESA_SELECIONADA, modo,
            selecionado["id"] if selecionado else None,
        )
        cliente_confirmado = selecionado is not None
        if cliente_confirmado:
            st.success(
                f'Cadastro selecionado: {selecionado["name"]} '
                f'(BOX {box if box is not None else "não informado"})'
            )

        descricao_avulsa = st.text_area(
            "Descrição do boleto",
            placeholder="Ex.: Taxa de publicidade\nMulta contratual\nOutra descrição",
            height=120,
            key="descricao_boleto_avulso",
        )
        col_valor, col_venc = st.columns(2)
        valor_avulso = col_valor.number_input(
            "Valor do boleto", min_value=0.00, step=0.01,
            format="%.2f", key="valor_boleto_avulso",
        )
        vencimento_avulso = col_venc.date_input(
            "Vencimento do boleto", value=proximo_dia_10(),
            min_value=date.today(), format="DD/MM/YYYY",
            key="vencimento_boleto_avulso",
        )
        recorrencia_mensal = st.checkbox(
            "Recorrência mensal — repetir até eu cancelar",
            value=False,
            key="ativar_recorrencia_boleto_avulso",
            help=(
                "O Asaas emitirá as cobranças mensalmente com o mesmo valor e "
                "dia do primeiro vencimento. Não há data final automática."
            ),
        )
        if recorrencia_mensal:
            st.info(
                "O Asaas fará novas cobranças mensais até a suspensão da recorrência. "
                "O primeiro vencimento é a data informada acima. "
                "Nenhuma nota fiscal será configurada por esta opção."
            )
        assinatura_resultado_atual = (
            assinatura, round(float(valor_avulso), 2),
            vencimento_avulso.isoformat(), str(descricao_avulsa).strip(),
            bool(recorrencia_mensal),
        ) if cliente_confirmado else None
        pode_emitir = (
            cliente_confirmado and bool(str(descricao_avulsa).strip())
            and float(valor_avulso) > 0
        )
        if not pode_emitir:
            campos_faltantes = []
            if not cliente_confirmado:
                campos_faltantes.append("selecionar o cliente")
            if not str(descricao_avulsa).strip():
                campos_faltantes.append("preencher a descrição do boleto")
            if float(valor_avulso) <= 0:
                campos_faltantes.append("informar um valor maior que zero")
            st.warning(
                "Para habilitar "
                + ("Criar recorrência mensal" if recorrencia_mensal else "Emitir boleto avulso")
                + ", é necessário: "
                + "; ".join(campos_faltantes)
                + "."
            )
        if st.button(
            (
                "🔁 Criar recorrência mensal" if recorrencia_mensal
                else "💳 Emitir boleto avulso"
            ),
            type="primary", use_container_width=True,
            disabled=not pode_emitir, key="emitir_boleto_avulso",
        ):
            try:
                referencia = (
                    f"BOX {box}.txt" if box is not None
                    else f'CLIENTE {selecionado["id"]}.txt'
                )
                if recorrencia_mensal:
                    # Evita transformar uma cobrança avulsa existente em
                    # uma segunda obrigação na mesma data e com mesmo valor.
                    referencia_avulsa = criar_referencia_externa(
                        referencia, float(valor_avulso),
                        vencimento_avulso, str(descricao_avulsa).strip(),
                    )
                    if buscar_cobranca_existente(referencia_avulsa):
                        raise RuntimeError(
                            "Já existe boleto avulso para este cliente, valor, "
                            "descrição e primeiro vencimento. "
                            "Concilie antes de criar a recorrência."
                        )
                    # Mantém o padrão de notificações do cliente utilizado
                    # pelo boleto avulso atual, sem criar um segundo webhook.
                    with st.spinner("Conferindo e criando assinatura mensal no Asaas..."):
                        padronizar_notificacoes_asaas(selecionado["id"])
                        recorrencia, nova = criar_recorrencia(
                            ASAAS_BASE_URL, cabecalhos_asaas(),
                            selecionado["id"], float(valor_avulso),
                            vencimento_avulso, str(descricao_avulsa).strip(),
                            get=requests.get, post=requests.post,
                        )
                    st.session_state["resultado_recorrencia_avulsa"] = {
                        "id": recorrencia["id"], "novo": nova,
                    }
                    st.session_state["assinatura_resultado_recorrencia_avulsa"] = (
                        assinatura_resultado_atual
                    )
                    st.session_state.pop("cache_lista_recorrencias", None)
                else:
                    with st.spinner("Gerando boleto avulso no Asaas..."):
                        boleto = emitir_boleto_asaas(
                            referencia, 0.0, float(valor_avulso),
                            vencimento_avulso, str(descricao_avulsa).strip(),
                            False, cliente_selecionado_id=selecionado["id"],
                        )
                    st.session_state["resultado_boleto_avulso"] = boleto
                    st.session_state["assinatura_resultado_boleto_avulso"] = (
                        assinatura_resultado_atual
                    )
            except Exception as erro:
                st.error(f"Não foi possível concluir a operação: {erro}")

        if recorrencia_mensal:
            recorrencia_salva = st.session_state.get("resultado_recorrencia_avulsa")
            if (recorrencia_salva
                    and st.session_state.get("assinatura_resultado_recorrencia_avulsa")
                    == assinatura_resultado_atual):
                if recorrencia_salva["novo"]:
                    st.success(
                        "Recorrência mensal criada no Asaas. "
                        f'Identificador: {recorrencia_salva["id"]}. '
                        "Continue acompanhando as cobranças no Asaas."
                    )
                else:
                    st.info(
                        "Esta recorrência já estava cadastrada no Asaas. "
                        "Nenhuma nova recorrência foi criada."
                    )
        else:
            boleto_salvo = st.session_state.get("resultado_boleto_avulso")
            if (boleto_salvo and assinatura_resultado_atual is not None
                    and st.session_state.get("assinatura_resultado_boleto_avulso")
                    == assinatura_resultado_atual):
                if boleto_salvo.get("novo"):
                    st.success(
                        f'Boleto criado para {boleto_salvo.get("clienteNome", "")}. '
                        f'ID: {boleto_salvo.get("id", "")}'
                    )
                else:
                    st.info("Essa cobrança já existia no Asaas. Nenhuma duplicidade criada.")
                if boleto_salvo.get("invoiceUrl"):
                    st.link_button(
                        "🔗 Abrir cobrança no Asaas", boleto_salvo["invoiceUrl"],
                        use_container_width=True,
                    )
                if boleto_salvo.get("bankSlipUrl"):
                    st.link_button(
                        "📄 Abrir boleto", boleto_salvo["bankSlipUrl"],
                        use_container_width=True,
                    )

        if st.toggle(
            "Exibir e gerenciar recorrências ativas",
            key="abrir_lista_recorrencias_avulsas",
            value=False,
        ):
            with st.expander("Recorrências mensais — consultar e cancelar", expanded=False):
                st.caption(
                    "A consulta mostra apenas as recorrências de boletos mensais "
                    "criadas por este Extrator na empresa selecionada."
                )
                if st.button(
                    "Atualizar recorrências", key="atualizar_recorrencias_avulsas",
                ):
                    st.session_state.pop("cache_lista_recorrencias", None)
                chave_cache = (EMPRESA_SELECIONADA, ASAAS_BASE_URL)
                cache = st.session_state.get("cache_lista_recorrencias")
                if not cache or cache.get("chave") != chave_cache or (
                    time.monotonic() - cache.get("quando", 0) > 120
                ):
                    try:
                        with st.spinner("Consultando recorrências no Asaas..."):
                            lista = listar_recorrencias_extrator(
                                ASAAS_BASE_URL, cabecalhos_asaas(),
                                get=requests.get, status="ACTIVE",
                            )
                        st.session_state["cache_lista_recorrencias"] = {
                            "chave": chave_cache, "quando": time.monotonic(),
                            "lista": lista,
                        }
                    except Exception as erro_lista:
                        st.error(f"Falha ao consultar recorrências: {erro_lista}")
                        lista = []
                else:
                    lista = cache["lista"]
                if not lista:
                    st.caption("Nenhuma recorrência ativa encontrada nesta empresa.")
                else:
                    st.caption(f"{len(lista)} recorrência(s) ativa(s).")
                    opcoes_rec = {r["id"]: r for r in lista}
                    rec_id = st.selectbox(
                        "Selecione a recorrência a consultar",
                        list(opcoes_rec),
                        index=None,
                        placeholder="Escolha uma assinatura ativa",
                        format_func=lambda ident: (
                            f'{opcoes_rec[ident]["description"]} — '
                            f'R$ {float(opcoes_rec[ident]["value"] or 0):.2f} — '
                            f'{opcoes_rec[ident]["nextDueDate"]} ({ident})'
                        ),
                        key="recorrencia_avulsa_selecionada",
                    )
                    if rec_id in opcoes_rec:
                        rec = opcoes_rec[rec_id]
                        st.write(f'Cliente Asaas: **{rec["customer"]}**')
                        st.write(f'Descrição: **{rec["description"]}**')
                        st.write(f'Próximo vencimento: **{rec["nextDueDate"]}**')
                        st.warning(
                            "Suspender interrompe novas cobranças. "
                            "Boletos já emitidos permanecem no Asaas."
                        )
                        confirma = st.checkbox(
                            "Confirmo a suspensão de novas cobranças desta recorrência",
                            key=f"confirmar_suspensao_recorrencia_avulsa_{rec_id}",
                        )
                        if st.button(
                            "Suspender recorrência", type="secondary",
                            disabled=not confirma,
                            key="suspender_recorrencia_avulsa",
                        ):
                            try:
                                with st.spinner("Suspendendo novas cobranças..."):
                                    _, mudou = suspender_recorrencia(
                                        ASAAS_BASE_URL, cabecalhos_asaas(),
                                        rec_id, get=requests.get, put=requests.put,
                                    )
                                st.session_state.pop("cache_lista_recorrencias", None)
                                st.success(
                                    "Recorrência suspensa; novas cobranças interrompidas."
                                    if mudou else "Essa recorrência já estava suspensa."
                                )
                            except Exception as erro_suspensao:
                                st.error(f"Falha ao suspender: {erro_suspensao}")


if (st.session_state.pagina_lider == "Boleto avulso"
        and st.session_state.mostrar_boleto_avulso):
    exibir_boleto_avulso()

st.divider()

# ============================================================
# HISTÓRICO MENSAL DE BOLETOS — CONSULTA DIRETA AO ASAAS
# ============================================================
# Somente leitura: nunca cria, altera ou exclui cobranças.

# Tradução apenas visual dos status retornados pelo Asaas.
# Status desconhecidos continuam visíveis para conferência.
STATUS_ASAAS_PT = {
    "PENDING": "Pendente",
    "OVERDUE": "Vencido",
    "CONFIRMED": "Pagamento confirmado",
    "RECEIVED": "Pago",
    "RECEIVED_IN_CASH": "Pago em dinheiro",
    "REFUNDED": "Reembolsado",
    "REFUND_REQUESTED": "Reembolso solicitado",
    "REFUND_IN_PROGRESS": "Reembolso em andamento",
    "CHARGEBACK_REQUESTED": "Contestação solicitada",
    "CHARGEBACK_DISPUTE": "Contestação em disputa",
    "AWAITING_CHARGEBACK_REVERSAL": "Aguardando reversão da contestação",
    "DUNNING_REQUESTED": "Negativação solicitada",
    "DUNNING_RECEIVED": "Negativação recebida",
    "AWAITING_RISK_ANALYSIS": "Aguardando análise de risco",
    "CANCELLED": "Cancelado",
    "DELETED": "Excluído",
}


def traduzir_status_asaas(status):
    codigo = str(status or "").strip().upper()
    return STATUS_ASAAS_PT.get(codigo, codigo or "Não informado")


def consultar_historico_asaas(ano, mes):
    inicio = date(ano, mes, 1)
    fim = inicio + relativedelta(months=1) - timedelta(days=1)
    pagamentos = []
    offset = 0
    limite = 100
    while True:
        resposta = requests.get(
            f"{ASAAS_BASE_URL}/payments",
            headers=cabecalhos_asaas(),
            params={
                "dateCreated[ge]": inicio.isoformat(),
                "dateCreated[le]": fim.isoformat(),
                "offset": offset,
                "limit": limite,
            },
            timeout=45,
        )
        if not resposta.ok:
            raise RuntimeError(
                f"Consulta ao Asaas falhou (HTTP {resposta.status_code}): "
                f"{resposta.text[:350]}"
            )
        corpo = resposta.json()
        lote = corpo.get("data", [])
        if not isinstance(lote, list):
            raise RuntimeError("O Asaas retornou uma lista de cobranças inválida.")
        pagamentos.extend(lote)
        if not corpo.get("hasMore"):
            break
        if not lote:
            raise RuntimeError("O Asaas indicou mais páginas, mas não retornou dados.")
        offset += len(lote)
        if offset > 100000:
            raise RuntimeError("Consulta muito extensa. Contate o suporte.")

    # Identifica também as cobranças geradas pelo Asaas para assinaturas
    # mensais originadas neste Extrator (o ID fica no campo 'subscription').
    subscription_ids = {
        str(p.get("subscription")) for p in pagamentos if p.get("subscription")
    }
    assinaturas_extrator = set()
    if subscription_ids:
        assinaturas = listar_recorrencias_extrator(
            ASAAS_BASE_URL, cabecalhos_asaas(), get=requests.get,
        )
        assinaturas_extrator = {
            assinatura["id"] for assinatura in assinaturas
        }

    # Referência criada pela rotina de emissão deste aplicativo.
    # As cobranças das recorrências são correlacionadas por subscription.
    registros = []
    for pagamento in pagamentos:
        referencia = str(pagamento.get("externalReference") or "")
        if (
            not referencia.startswith("lider-royalties-")
            and str(pagamento.get("subscription") or "") not in assinaturas_extrator
        ):
            continue
        # Não filtrar por billingType: a cobrança emitida pelo extrator
        # pode ser quitada por outra modalidade disponibilizada pelo Asaas.
        # A referência exclusiva "lider-royalties-" identifica a origem.
        criado = str(pagamento.get("dateCreated") or "")[:10]
        if not (inicio.isoformat() <= criado <= fim.isoformat()):
            continue
        # Inclui PENDING, OVERDUE, CONFIRMED, RECEIVED e demais situações.
        registros.append(pagamento)
    return registros


def clientes_historico_asaas(ids_clientes):
    """Nomes reutilizados da lista em cache: evita uma chamada por boleto."""
    clientes = clientes_avulsos_em_cache()
    nomes = {
        str(cliente["id"]): str(cliente.get("name") or "")
        for cliente in clientes
        if cliente.get("id")
    }
    return {
        identificador: nomes.get(identificador, "Cliente não localizado")
        for identificador in ids_clientes
    }


if st.session_state.pagina_lider == "Extratos":
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    st.markdown('<div id="extratos"></div>', unsafe_allow_html=True)
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
                        .st-key-{chave_area_outro} {{
                            background-color: #f0fdf4 !important;
                            border: 1px solid #86efac !important;
                            border-radius: 14px !important;
                            padding: 18px 20px 16px 20px !important;
                            margin-top: 8px !important;
                            margin-bottom: 22px !important;
                        }}

                        .st-key-{chave_area_outro} [data-testid="stFileUploader"] {{
                            background: transparent !important;
                        }}

                        .st-key-{chave_area_outro} [data-testid="stExpander"] {{
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
        
                    assinatura_boleto_atual = (
                        EMPRESA_SELECIONADA,
                        arquivo.name,
                        hashlib.sha256(arquivo.getvalue()).hexdigest(),
                        round(float(valor_final_boleto), 2),
                        vencimento.isoformat(),
                        descricao_boleto,
                        bool(emitir_nota_apos_pagamento),
                    )
                    chave_resultado = f"resultado_boleto_{indice}"
                    chave_assinatura = f"assinatura_resultado_boleto_{indice}"
                    if clicou_emitir_boleto:
                        st.session_state.pop(chave_resultado, None)
                        st.session_state.pop(chave_assinatura, None)
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
                            st.session_state[chave_resultado] = boleto
                            st.session_state[chave_assinatura] = assinatura_boleto_atual
                        except Exception as erro_boleto:
                            st.error(f"Não foi possível emitir o boleto: {erro_boleto}")

                    boleto_salvo = (
                        st.session_state.get(chave_resultado)
                        if st.session_state.get(chave_assinatura) == assinatura_boleto_atual
                        else None
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


# Histórico discreto: na tela inicial e após o relatório geral quando houver extratos.
st.markdown("""
<style>
.st-key-historico_discreto [data-testid="stExpander"] summary p,
.st-key-historico_discreto [data-testid="stExpander"] summary p * {
    font-size: 13px !important;
    font-weight: 400 !important;
    line-height: 1.25 !important;
}
.st-key-historico_discreto [data-testid="stExpander"] {
    margin-top: 0 !important;
}
</style>
""", unsafe_allow_html=True)
st.markdown('<div id="historico"></div>', unsafe_allow_html=True)
if st.session_state.pagina_lider == "Histórico":
    with st.container(key="historico_discreto"):
        with st.expander("📚 Histórico mensal de boletos", expanded=True):
            st.caption(
                "Consulta somente leitura ao Asaas da empresa selecionada. "
                "Exibe boletos identificados pela referência gerada neste extrator; "
                "cobranças criadas manualmente ou por outros sistemas podem não aparecer. "
                "Nenhum boleto é apagado."
            )
            col_mes, col_ano, col_consultar = st.columns([2, 1, 1])
            meses_pt = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
            ]
            mes_historico = col_mes.selectbox(
                "Mês", range(1, 13), index=date.today().month - 1,
                format_func=lambda numero: meses_pt[numero - 1], key="historico_mes",
            )
            ano_historico = col_ano.number_input(
                "Ano", min_value=2020, max_value=2100, value=date.today().year,
                step=1, key="historico_ano",
            )
            with col_consultar:
                st.write("")
                consultar = st.button("🔎 Consultar", key="consultar_historico")

            assinatura_consulta = (EMPRESA_SELECIONADA, int(ano_historico), int(mes_historico))
            if consultar:
                try:
                    with st.spinner("Consultando boletos e clientes no Asaas..."):
                        cobrancas = consultar_historico_asaas(int(ano_historico), int(mes_historico))
                        ids = {str(c.get("customer")) for c in cobrancas if c.get("customer")}
                        nomes = clientes_historico_asaas(ids)
                        linhas = []
                        for cobranca in cobrancas:
                            cliente_id = str(cobranca.get("customer") or "")
                            nome = nomes.get(cliente_id, "Cliente não identificado")
                            box = extrair_numero_box(nome)
                            descricao = str(cobranca.get("description") or "")
                            linhas.append({
                                "Emissão": str(cobranca.get("dateCreated") or "")[:10],
                                "BOX": box,
                                "Franqueado": nome,
                                "Descrição": descricao,
                                "Valor (R$)": float(cobranca.get("value") or 0),
                                "Vencimento": str(cobranca.get("dueDate") or "")[:10],
                                "Situação": traduzir_status_asaas(cobranca.get("status")),
                                "ID Asaas": str(cobranca.get("id") or ""),
                                "Boleto": str(cobranca.get("bankSlipUrl") or cobranca.get("invoiceUrl") or ""),
                            })
                        tabela_historico = pd.DataFrame(linhas, columns=[
                            "Emissão", "BOX", "Franqueado", "Descrição", "Valor (R$)",
                            "Vencimento", "Situação", "ID Asaas", "Boleto",
                        ])
                        # Ordem numérica crescente dos BOX (7, 38, 71, 250).
                        # BOX sem número identificado ficam ao final.
                        tabela_historico["BOX"] = pd.to_numeric(
                            tabela_historico["BOX"], errors="coerce"
                        ).astype("Int64")
                        tabela_historico = tabela_historico.sort_values(
                            by=["BOX", "Emissão"],
                            ascending=[True, True],
                            na_position="last",
                            kind="stable",
                        ).reset_index(drop=True)
                        st.session_state["historico_dados"] = tabela_historico
                        st.session_state["historico_assinatura"] = assinatura_consulta
                except Exception as erro:
                    st.session_state.pop("historico_dados", None)
                    st.session_state.pop("historico_assinatura", None)
                    st.error(f"Não foi possível consultar o histórico: {erro}")

            if st.session_state.get("historico_assinatura") == assinatura_consulta:
                tabela = st.session_state["historico_dados"]
                col_quantidade, col_franqueados, col_total = st.columns(3)
                col_quantidade.metric("Boletos encontrados", len(tabela))
                col_franqueados.metric("BOX distintos", tabela["BOX"].dropna().nunique())
                col_total.metric("Valor total", formatar_moeda(tabela["Valor (R$)"].sum()))
                if tabela.empty:
                    st.info("Nenhum boleto deste extrator encontrado nesse mês e empresa.")
                else:
                    st.dataframe(tabela, use_container_width=True, hide_index=True,
                        column_config={
                            "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                            "Boleto": st.column_config.LinkColumn("Abrir boleto"),
                        })
                    st.caption(
                        "O total soma cobranças registradas, independentemente de estarem "
                        "pagas, vencidas ou canceladas. Confira a coluna Situação."
                    )

                st.markdown("**Conferir BOX que deveriam receber boleto**")
                esperados_texto = st.text_area(
                    "Informe os números dos BOX previstos (separados por vírgula, espaço ou linha)",
                    placeholder="Ex.: 07, 38, 71, 81",
                    key="historico_boxes_esperados",
                )
                if esperados_texto.strip():
                    tokens = re.split(r"[,;\s]+", esperados_texto.strip())
                    invalidos = [t for t in tokens if t and not re.fullmatch(r"(?:BOX[-_ ]*)?0*\d+", t, re.I)]
                    if invalidos:
                        st.warning("Confira os números informados: " + ", ".join(invalidos[:10]))
                    else:
                        previstos = {int(re.search(r"\d+", t).group()) for t in tokens if t}
                        encontrados = {int(x) for x in tabela["BOX"].dropna().tolist()}
                        pendentes = sorted(previstos - encontrados)
                        st.write(f"Previstos: **{len(previstos)}** | Com boleto: **{len(previstos & encontrados)}** | Sem boleto identificado: **{len(pendentes)}**")
                        if pendentes:
                            st.warning("BOX sem boleto identificado neste mês: " + ", ".join(f"{x:02d}" for x in pendentes))
                        else:
                            st.success("Todos os BOX informados possuem ao menos um boleto identificado.")
                        st.caption("A conferência considera qualquer boleto deste extrator, inclusive avulsos e cancelados. Verifique a descrição e a situação antes de concluir o fechamento.")

                saida = BytesIO()
                with pd.ExcelWriter(saida, engine="openpyxl") as writer:
                    tabela.to_excel(writer, index=False, sheet_name="Boletos do mês")
                st.download_button(
                    "📥 Baixar histórico em Excel", data=saida.getvalue(),
                    file_name=f"boletos_{EMPRESA_SELECIONADA.lower().replace(' ', '_')}_{ano_historico}_{mes_historico:02d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_historico_mensal",
                )
            else:
                st.info("Selecione o mês e clique em Consultar para carregar o histórico.")

# Consulta de NFS-e estritamente somente leitura, para conciliação fiscal.
# Nenhum evento é reenviado; nenhuma nota é criada/cancelada aqui.
if (st.session_state.pagina_lider == "Histórico"
        and EMPRESA_SELECIONADA == "Lider Franquia"):
    with st.expander("Conferir NFS-e de uma cobrança (somente consulta)", expanded=False):
        st.caption(
            "Informe o identificador pay_ do Asaas. A consulta não emite, "
            "cancela nem reenvia nota fiscal; pendências precisam de conciliação."
        )
        pagamento_conciliacao = st.text_input(
            "ID da cobrança",
            placeholder="pay_...",
            key="pagamento_conciliacao_nfse",
        ).strip()
        if st.button("Consultar cobrança e notas", key="verificar_nfse_sem_emissao"):
            try:
                with st.spinner("Consultando pagamento e NFS-e no Asaas..."):
                    resultado_nfse = consultar_nfse_por_pagamento(
                        ASAAS_BASE_URL, cabecalhos_asaas(),
                        pagamento_conciliacao, get=requests.get,
                    )
                st.session_state["resultado_conciliacao_nfse"] = resultado_nfse
                st.session_state["consulta_conciliacao_nfse"] = (
                    EMPRESA_SELECIONADA, pagamento_conciliacao,
                )
            except Exception as erro_nfse:
                st.session_state.pop("resultado_conciliacao_nfse", None)
                st.session_state.pop("consulta_conciliacao_nfse", None)
                st.error(f"Não foi possível conciliar a nota fiscal: {erro_nfse}")
        if st.session_state.get("consulta_conciliacao_nfse") == (
            EMPRESA_SELECIONADA, pagamento_conciliacao,
        ):
            resultado_nfse = st.session_state["resultado_conciliacao_nfse"]
            st.write(f'Situação da cobrança: **{resultado_nfse["payment_status"]}**')
            if not resultado_nfse["fiscal_solicitada_pelo_extrator"]:
                st.info(
                    "A cobrança não possui a marca de emissão automática de NFS-e "
                    "do Extrator. Confira as regras de faturamento aplicáveis."
                )
            notas_nfse = resultado_nfse["notas"]
            if notas_nfse:
                st.dataframe(pd.DataFrame(notas_nfse), hide_index=True,
                             use_container_width=True)
                if any(n["status"] not in ("AUTHORIZED", "SYNCHRONIZED")
                       for n in notas_nfse):
                    st.warning(
                        "Existe nota pendente, em erro ou em situação que exige "
                        "verificação no Asaas antes de tomar qualquer ação."
                    )
            elif resultado_nfse["fiscal_solicitada_pelo_extrator"]:
                st.warning(
                    "A API não localizou uma NFS-e vinculada a esta cobrança. "
                    "Não repita a emissão sem verificar registros anteriores "
                    "e conciliar com o Asaas."
                )
            else:
                st.caption("Nenhuma nota fiscal vinculada a esta cobrança.")
