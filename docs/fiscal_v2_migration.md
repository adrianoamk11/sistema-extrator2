# Reconstrução fiscal V2 — Líder Franquia

## Situação desta entrega
- `fiscal_v2.py` executa **somente GET** no Asaas: leitura de cobrança por ID e de notas vinculadas.
- Não cria boletos, NFS-e nem reenvia eventos. Não modifica chaves, webhooks ou bancos existentes.
- Não está integrado ao webhook em produção e **não emite notas automaticamente** nesta fase.
- Estados calculados a partir de evidências externas: NAO_SOLICITADA, AGUARDANDO_PAGAMENTO, PAGA_SEM_NOTA, AGENDADA_NO_ASAAS, REGISTRADA_NO_ASAAS, ERRO_OU_CANCELAMENTO, REVISAR_DUPLICIDADE, ANALISAR_STATUS.
- A classificação REGISTRADA_NO_ASAAS não garante autorização fiscal na prefeitura se o Asaas retornar estado diferente de AUTHORIZED; apresentar status real sempre.

## Origem de dados
- O extrator marca opt-in fiscal em `externalReference` com `|NFSE|` ao criar cobrança.
- A V2 deve confirmar independentemente a cobrança via GET /payments/{id} e procurar NFS-e via GET /invoices?payment={id}.
- A seleção de cliente, a empresa emissora, códigos de serviço e retenções precisam ser conferidas antes de qualquer POST fiscal.

## Fase 2 — antes de ativar emissão automática
1. Conferir configurações fiscais, contrato Asaas e resposta real da API para o Portal Nacional (código municipal, NBS, ISS, natureza da operação) com contador/responsável fiscal.
2. Conferir onde a interface Streamlit está hospedada: o serviço Render atual usa `gunicorn webhook:app` e NÃO disponibiliza `app.py` como interface.
3. Criar orquestrador de NFS-e com banco durável em disco persistente (ou banco transacional), idempotência por payment ID e trilha de auditoria, contemplando falhas e reinícios.
4. Implementar consulta periódica read-only de pagamentos confirmados marcados `|NFSE|` para conciliação da fila; **não reemitir** automaticamente pagamentos com reserva ou resultado incerto.
5. Implementar endpoint autenticado de webhook com validação de assinatura/token, confirmação de evento e persistência do recebimento antes da resposta 2xx.
6. Validar transições: recebimento Pix -> webhook/consulta -> solicitação NFS-e -> retorno do Asaas -> autorização ou rejeição. Não confundir resposta HTTP 200 do webhook com NFS-e emitida.
7. Testar com mocks e homologação do Asaas, incluindo concorrência, duplicidade, evento fora de ordem, recusa HTTP 400, timeout e restart.
8. Fazer backup verificado, plano de rollback e migração supervisionada com **um único emissor ativo**.
9. Desativar o emissor anterior apenas quando V2 estiver validada e confirmada, sem apagar os registros legados.

## Regra para pagamentos antigos
- Nenhuma cobrança paga anteriormente deve gerar NFS-e retroativa automaticamente.
- Se paga e sem nota, classificar PAGA_SEM_NOTA e exigir revisão fiscal/manual.
- Não reprocessar automaticamente sem confirmar ausência de nota no Asaas e inexistência de tentativa persistida.

## Critério mínimo para publicação
- Todos os testes verdes;
- dados de emissão fiscal validados;
- endpoint Asaas correto e webhook entregando eventos;
- comprovação em homologação de NFS-e criada sem duplicatas;
- monitoramento e rollback preparados.
