# Incidente NFS-e — Royalties de Franquia (06/11/2026)

## Evidências confirmadas
- Pagamento `pay_bnepyq5l8qnh4y3t`, fatura `961543418`, R$ 5,56, `PAYMENT_RECEIVED`.
- `externalReference`: `lider-royalties-7d33a112df7c734474ba|NFSE|`.
- A API real do Asaas retornou zero registros em `GET /invoices?payment=pay_bnepyq5l8qnh4y3t`.
- Render, 07/11/2026 00:41:57Z: `Asaas recusou NFS-e da cobrança pay_bnepyq5l8qnh4y3t (HTTP 400): invalid_action: Código NBS inválido`.
- Outra rejeição para `pay_h9i1hwa9p6qtgd1j` em 07/11/2026 00:41:55Z: mesmo erro.
- O webhook anterior contém reserva persistente por `payment_id`; não autoriza repetição automática de POST após rejeições/erros, mesmo com nota ausente.

## Possível incompatibilidade fiscal
- Código tributação nacional para franquia: `170801` (17.08.01).
- Tabela de correlação NFS-e Nacional relaciona franquia a NBS `1.1110.00.00` (sem pontuação, `111100000`).
- Portanto, **o erro do Asaas não demonstra isoladamente que o NBS está incorreto juridicamente**; pode estar relacionado a cadastro/validação/serialização no endpoint.
- Referências:
  - https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/anexoviii-correlacaoitemnbsindopcclasstrib_ibscbs_v1-01-00.xlsx/view
  - https://central.ajuda.asaas.com/hc/pt-br/articles/54571261077019-Como-cadastrar-o-c%C3%B3digo-de-servi%C3%A7o-para-emiss%C3%A3o-no-Portal-Nacional
  - https://docs.asaas.com/changelog/nfs-e-migra%C3%A7%C3%A3o-obrigat%C3%B3ria-do-simples-nacional-para-o-portal-nacional-em-01112026

## Bloqueios para ativação V2
1. Confirmar junto ao Asaas quais campos do payload da API de NFS-e devem transmitir o NBS no Portal Nacional e o formato aceito, sem experimentação em notas reais.
2. Confirmar com contabilidade a classificação de royalties de franquia e a configuração efetiva do serviço no Asaas.
3. Corrigir parametrização na integração **somente após** esclarecimento da rejeição HTTP 400.
4. Validar processamento fiscal com resposta `SCHEDULED` e evento `INVOICE_AUTHORIZED`, sem confundir agendamento e emissão.
5. Resolver penalização da fila Asaas, garantindo persistência de webhook em volume durável, com plano de rollback.
6. Conciliar todas as tentativas anteriores e notas existentes antes de liberar nova emissão.
7. Nunca tentar emitir nota automaticamente para pagamentos anteriores até análise fiscal/manual das reservas legadas.

## Estado
A V2 permanece isolada em branch não mesclada, sem emissão em produção. O sistema legado continua operando, porém com rejeições fiscais observadas.
