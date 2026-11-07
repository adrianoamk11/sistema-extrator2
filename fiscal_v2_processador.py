"""Processador de eventos fiscais V2, somente leitura.

Separa entrega do webhook e processamento fiscal. Eventos persistidos podem
ser auditados/reprocessados sem reenviar a notificação ao Asaas.
"""
import os
import sqlite3
from contextlib import closing

from fiscal_v2 import conciliar


def processar_pendentes(db_path, client, limite=50):
    if not os.path.isabs(str(db_path)):
        raise ValueError("Banco de eventos deve usar caminho absoluto")
    if not 1 <= limite <= 100:
        raise ValueError("Limite fora do intervalo permitido")

    with closing(sqlite3.connect(db_path, timeout=5)) as conexao:
        eventos = conexao.execute(
            "SELECT event_id, evento, origem_id FROM fiscal_v2_eventos "
            "WHERE situacao='PENDENTE' ORDER BY recebido_em, event_id LIMIT ?",
            (limite,)
        ).fetchall()

    resumo = {"concluidos": 0, "revisar": 0, "falhas": 0}
    for event_id, tipo, origem_id in eventos:
        try:
            if tipo.startswith("PAYMENT_"):
                resultado = conciliar(client, origem_id)
                situacao = resultado.situacao
            else:
                # INVOICE_* exige consultar a nota e sua cobrança; não inferir
                # autorização apenas pelo nome do evento.
                situacao = "CONFERIR_NOTA_NO_ASAAS"
            if situacao in ("PAGA_SEM_NOTA", "REVISAR_DUPLICIDADE", "ERRO_OU_CANCELAMENTO"):
                resumo["revisar"] += 1
            else:
                resumo["concluidos"] += 1
        except Exception:
            # Evita registrar token ou dados fiscais em log. O evento permanece
            # PENDENTE para consulta posterior, sem POST ou emissão.
            resumo["falhas"] += 1
            continue

        with closing(sqlite3.connect(db_path, timeout=5)) as conexao:
            with conexao:
                conexao.execute(
                    "UPDATE fiscal_v2_eventos SET situacao=? "
                    "WHERE event_id=? AND situacao='PENDENTE'",
                    (situacao, event_id)
                )
    return resumo
