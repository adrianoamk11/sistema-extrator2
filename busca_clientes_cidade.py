"""Busca de clientes por cidade na API Asaas, estritamente somente leitura.

O Asaas retorna cityName (nome da cidade) e city (identificador).
Nunca supõe que a cidade identifica um único cliente.
"""
import re
import unicodedata

import requests


def normalizar_termo(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return re.sub(r"\s+", " ", texto.encode("ascii", "ignore").decode("ascii")).strip().lower()


def corresponde_cidade(cliente, nome):
    procurado = normalizar_termo(nome)
    if len(procurado) < 3:
        return False
    campos = (
        str(cliente.get("cityName") or ""),
        str(cliente.get("name") or ""),
    )
    return any(re.search(r"(?<![a-z0-9])" + re.escape(procurado) + r"(?![a-z0-9])",
                         normalizar_termo(campo)) for campo in campos)


def procurar_clientes_por_cidade(base_url, headers, cidade, get=requests.get):
    cidade = str(cidade or "").strip()
    if len(normalizar_termo(cidade)) < 3:
        raise ValueError("Digite pelo menos três letras da cidade.")
    encontrados = []
    offset = 0
    for _ in range(1000):
        resposta = get(
            f"{base_url}/customers",
            headers=headers,
            params={"offset": offset, "limit": 100},
            timeout=30,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict) or not isinstance(dados.get("data"), list):
            raise RuntimeError("Lista de clientes inválida no Asaas.")
        for cliente in dados["data"]:
            if isinstance(cliente, dict) and cliente.get("id") and corresponde_cidade(cliente, cidade):
                encontrados.append({
                    "id": str(cliente["id"]),
                    "name": str(cliente.get("name") or ""),
                    "cityName": str(cliente.get("cityName") or ""),
                })
        if not dados.get("hasMore"):
            return encontrados
        if not dados["data"]:
            raise RuntimeError("Asaas indicou mais clientes, mas retornou página vazia.")
        offset += 100
    raise RuntimeError("Consulta muito extensa: limite de páginas atingido.")
