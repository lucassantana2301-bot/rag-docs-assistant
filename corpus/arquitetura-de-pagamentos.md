# Arquitetura do processamento de pagamentos

Visão geral dos serviços que processam pagamentos na Nimbus Pay e das decisões de projeto que garantem que nenhum pagamento seja cobrado duas vezes.

## Serviços

- **payments-api:** recebe as requisições de pagamento dos clientes, valida e publica o evento `payment.requested`.
- **payments-orchestrator:** consome os eventos, chama o antifraude e o provedor de liquidação (SPI do Banco Central para Pix, adquirente para cartão) e grava o estado do pagamento.
- **ledger:** livro-razão de partidas dobradas. Todo movimento de dinheiro gera dois lançamentos que somam zero.
- **notifications:** envia webhooks e e-mails aos clientes quando o pagamento muda de estado.

A comunicação entre os serviços é assíncrona, por tópicos no Kafka. O banco de dados de cada serviço é um PostgreSQL próprio; nenhum serviço lê o banco do outro.

## Idempotência

Toda requisição de pagamento exige o cabeçalho `Idempotency-Key`. A payments-api guarda a chave por 24 horas: uma segunda requisição com a mesma chave devolve a resposta original em vez de criar outro pagamento. Os consumidores do Kafka também deduplicam pelo identificador do evento, porque o Kafka garante entrega "pelo menos uma vez".

## Estados do pagamento

Um pagamento passa por `requested`, `authorized`, `settled` e termina em `settled`, `failed` ou `refunded`. As transições são validadas por uma máquina de estados: não é possível, por exemplo, estornar um pagamento que não foi liquidado.

## Outbox

A payments-api grava o pagamento e o evento a publicar na mesma transação do banco (padrão transactional outbox). Um processo separado publica os eventos pendentes no Kafka. Isso evita o caso em que o pagamento é salvo mas o evento se perde.

## Limites e tempo de resposta

A meta (SLO) da payments-api é responder em até 300 ms no p99 e ter 99,95% de disponibilidade no mês. O limite padrão é de 100 requisições por segundo por cliente; limites maiores são negociados pelo time comercial.
