"""Recorrência mensal opcional de boleto avulso via Assinaturas Asaas V3.

Integração isolada da emissão avulsa, extratos, royalties e NFS-e.
A criação tem referência determinística, conciliação de tentativas e
verificação de uma assinatura anterior antes de qualquer POST.
"""
import hashlib
import re
from datetime import date

from operacao_financeira import (
    operacao_financeira_unica,
    marcar_resultado_inconclusivo,
    resposta_inconclusiva,
)


PREFIXO = "lider-avulso-mensal-"


def referencia_recorrencia(customer_id, valor, primeiro_vencimento, descricao):
    """Identifica a operação, independentemente da forma de busca do cliente."""
    texto = (
        f"{customer_id}|{float(valor):.2f}|"
        f"{primeiro_vencimento.isoformat()}|{str(descricao).strip()}"
    )
    return PREFIXO + hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]


def _clientes_validos(customer_id):
    if not re.fullmatch(r"cus_[A-Za-z0-9]+", str(customer_id or "")):
        raise ValueError("Identificador do cliente Asaas inválido.")


def _requisicao_status(resposta, acao):
    if not resposta.ok:
        # Não expor resposta do provedor, dados privados ou token no front-end.
        raise RuntimeError(
            f"Não foi possível {acao} no Asaas (HTTP {resposta.status_code}). "
            "Consulte o cadastro e tente conciliar antes de repetir a operação."
        )
    try:
        dados = resposta.json()
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"Resposta inválida do Asaas ao {acao}.") from exc
    if not isinstance(dados, dict):
        raise RuntimeError(f"Resposta inesperada do Asaas ao {acao}.")
    return dados


def _listar(base_url, headers, parametros, get, limite_paginas=200):
    resultados = []
    offset = 0
    for _ in range(limite_paginas):
        params = dict(parametros, limit=100, offset=offset)
        retorno = get(
            base_url.rstrip("/") + "/subscriptions",
            headers=headers, params=params, timeout=30,
        )
        corpo = _requisicao_status(retorno, "consultar recorrências")
        pagina = corpo.get("data")
        if not isinstance(pagina, list):
            raise RuntimeError("Asaas retornou uma lista inválida de recorrências.")
        resultados.extend(item for item in pagina if isinstance(item, dict))
        if not corpo.get("hasMore"):
            return resultados
        if not pagina:
            raise RuntimeError("Asaas retornou uma página vazia ao consultar recorrências.")
        offset += 100
    raise RuntimeError("Quantidade de recorrências excede o limite de consulta.")


def localizar_recorrencia(base_url, headers, referencia, get):
    """Somente uma recorrência pode corresponder à referência da operação."""
    todas = _listar(
        base_url, headers, {"externalReference": referencia}, get,
    )
    exatas = [s for s in todas if s.get("externalReference") == referencia]
    if len(exatas) > 1:
        raise RuntimeError(
            "Mais de uma recorrência corresponde a esta operação no Asaas. "
            "É necessário conciliar antes de criar outra."
        )
    return exatas[0] if exatas else None


def criar_recorrencia(
    base_url, headers, customer_id, valor, primeiro_vencimento,
    descricao, get, post, hoje=None,
):
    """Cria UMA assinatura mensal BOLETO ou recupera uma idêntica.

    O primeiro pagamento fica a cargo do Asaas. Nunca executa POST /payments.
    Não utiliza endDate ou maxPayments: permanece até suspensão explícita.
    """
    _clientes_validos(customer_id)
    descricao = str(descricao or "").strip()
    if not descricao or len(descricao) > 500:
        raise ValueError("Informe uma descrição de até 500 caracteres.")
    if not isinstance(primeiro_vencimento, date):
        raise ValueError("Informe uma data válida para o primeiro vencimento.")
    hoje = hoje or date.today()
    if primeiro_vencimento < hoje:
        raise ValueError("O primeiro vencimento não pode estar no passado.")
    try:
        valor = round(float(valor), 2)
    except (ValueError, TypeError) as exc:
        raise ValueError("Valor da recorrência inválido.") from exc
    if not 0 < valor <= 1000000:
        raise ValueError("O valor da recorrência precisa ser positivo.")

    referencia = referencia_recorrencia(
        customer_id, valor, primeiro_vencimento, descricao,
    )
    # Mantém consultas de deduplicação e POST serializados por cliente,
    # valor e descrição, mesmo quando a data inicial foi alterada.
    chave_operacao_financeira = (
        base_url.rstrip("/"), "recorrencia", customer_id,
        valor, descricao.casefold(),
    )
    with operacao_financeira_unica(chave_operacao_financeira):
        existente = localizar_recorrencia(base_url, headers, referencia, get)
        if existente:
            if str(existente.get("customer") or "") != customer_id:
                raise RuntimeError("Recorrência conflitante vinculada a outro cliente.")
            if existente.get("status") != "ACTIVE":
                raise RuntimeError(
                    "Esta recorrência já existe, mas está suspensa ou expirada. "
                    "Confira-a no Asaas; nenhuma nova assinatura foi criada."
                )
            return existente, False

        # Verificação adicional: impede nova recorrência ativa equivalente
        # após edição da data inicial, evitando cobrança mensal duplicada.
        ativas = _listar(
            base_url, headers, {"customer": customer_id, "status": "ACTIVE"}, get,
        )
        for assinatura in ativas:
            if (assinatura.get("cycle") == "MONTHLY"
                    and assinatura.get("billingType") == "BOLETO"
                    and str(assinatura.get("description") or "").strip() == descricao
                    and round(float(assinatura.get("value") or 0), 2) == valor
                    and str(assinatura.get("externalReference") or "").startswith(PREFIXO)):
                raise RuntimeError(
                    "Este cliente já possui recorrência mensal ativa de mesmo valor "
                    "e descrição criada pelo Extrator. Confira as recorrências ativas."
                )

        # Chamada de escrita só depois de conciliação de registros existentes.
        payload = {
            "customer": customer_id,
            "billingType": "BOLETO",
            "value": valor,
            "nextDueDate": primeiro_vencimento.isoformat(),
            "cycle": "MONTHLY",
            "description": descricao,
            "externalReference": referencia,
        }
        try:
            resposta = post(
                base_url.rstrip("/") + "/subscriptions",
                headers=headers, json=payload, timeout=30,
            )
        except Exception as exc:
            # Timeout após envio pode significar assinatura criada.
            marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise RuntimeError(
                "Não foi possível confirmar a criação. Antes de tentar novamente, "
                "consulte as recorrências no Asaas para evitar duplicidade."
            ) from exc
        if resposta_inconclusiva(resposta.status_code):
            marcar_resultado_inconclusivo(chave_operacao_financeira)
        try:
            dados = _requisicao_status(resposta, "criar recorrência")
        except RuntimeError as exc:
            if resposta.ok:
                marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise
        if (not str(dados.get("id") or "").startswith("sub_")
                or str(dados.get("customer") or "") != customer_id):
            marcar_resultado_inconclusivo(chave_operacao_financeira)
            raise RuntimeError(
                "O Asaas não confirmou os dados da recorrência. "
                "Confira a lista antes de repetir a operação."
            )
        return dados, True


def listar_recorrencias_extrator(base_url, headers, get, status=None):
    parametros = {"billingType": "BOLETO"}
    if status:
        parametros["status"] = status
    assinaturas = _listar(base_url, headers, parametros, get)
    return [
        {
            "id": str(a.get("id")),
            "customer": str(a.get("customer") or ""),
            "description": str(a.get("description") or ""),
            "value": a.get("value"),
            "nextDueDate": str(a.get("nextDueDate") or ""),
            "status": str(a.get("status") or ""),
        }
        for a in assinaturas
        if str(a.get("externalReference") or "").startswith(PREFIXO)
        and str(a.get("id") or "").startswith("sub_")
    ]


def suspender_recorrencia(base_url, headers, assinatura_id, get, put):
    """Interrompe novas cobranças; mantém as já geradas e seu histórico."""
    if not re.fullmatch(r"sub_[A-Za-z0-9]+", str(assinatura_id or "")):
        raise ValueError("Identificador de recorrência inválido.")
    base = base_url.rstrip("/")
    atual = _requisicao_status(
        get(base + "/subscriptions/" + assinatura_id, headers=headers, timeout=30),
        "consultar recorrência",
    )
    if (atual.get("id") != assinatura_id
            or not str(atual.get("externalReference") or "").startswith(PREFIXO)):
        raise RuntimeError("Esta recorrência não foi criada pelo Extrator.")
    if atual.get("status") != "ACTIVE":
        return atual, False
    retorno = _requisicao_status(
        put(
            base + "/subscriptions/" + assinatura_id,
            headers=headers,
            json={"status": "INACTIVE"},
            timeout=30,
        ),
        "interromper recorrência",
    )
    if retorno.get("id") != assinatura_id or retorno.get("status") != "INACTIVE":
        raise RuntimeError(
            "Não foi possível confirmar a suspensão. Consulte o Asaas."
        )
    return retorno, True
