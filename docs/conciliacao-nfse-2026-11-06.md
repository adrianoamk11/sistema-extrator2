# Conciliação da NFS-e rejeitada — 06/11/2026

## Cobrança analisada
- Payment ID: `pay_jb5aum5psse9sfiu`
- Evento observado: `PAYMENT_RECEIVED`
- Tentativa de criar NFS-e: resposta HTTP 400 do Asaas às 22:41:38 UTC (19:41:38 America/Sao_Paulo).
- Entregas posteriores do webhook: HTTP 503 por reserva de tentativa anterior.
- **Não há confirmação de emissão, autorização ou ausência de nota.** A documentação recomenda consulta pontual.

## Consultas somente leitura (não emitir, não reenviar, não cancelar)
1. No Asaas da **Líder Franquia**, localizar `pay_jb5aum5psse9sfiu` e conferir o status do pagamento e a referência externa; confirmar que se trata da operação analisada.
2. Consultar notas associadas à cobrança: `GET /v3/invoices?payment=pay_jb5aum5psse9sfiu&limit=100`, verificando lista e paginação. Também revisar notas por cliente/referência se necessário.
3. Verificar `GET /v3/fiscalInfo`, em particular emissor Portal Nacional, credenciais configuradas, regime tributário, série/número DPS e situação dos serviços; não divulgar senhas/chaves.
4. Confrontar `municipalServiceCode`, classificação nacional do serviço, `taxes.nbsCode` e outros campos eventualmente obrigatórios com a contabilidade.
5. Solicitar ao suporte Asaas o corpo `errors` da requisição `POST /v3/invoices` rejeitada em 06/11/2026 às 22:41:38 UTC, associada à cobrança; os logs históricos da aplicação registraram apenas HTTP 400.
6. Classificar a cobrança como: nota autorizada; agendada; em erro; não encontrada. **Não** limpar registro de tentativa/emitir novamente antes de confirmar ausência de nota e obter orientação de conciliação.

## Alterações preparadas, ainda não implantadas
- Mensagens de rejeição 4xx ficam registradas para investigação futura.
- A reserva de idempotência é preservada — nenhuma segunda tentativa automática.
- Alternar a opção de nota fiscal não cria um segundo boleto para a mesma referência base.
- Testes automatizados usam mocks, sem movimentos financeiros.

## Limites
A alteração não recupera o conteúdo de erros 400 anteriores, não corrige automaticamente dados fiscais nem regulariza a cobrança já paga.

## Referências
- https://docs.asaas.com/reference/codigos-http-das-respostas
- https://docs.asaas.com/reference/listar-notas-fiscais
- https://docs.asaas.com/reference/fiscal-info
- https://docs.asaas.com/changelog/nfs-e-migra%C3%A7%C3%A3o-obrigat%C3%B3ria-do-simples-nacional-para-o-portal-nacional-em-01112026
