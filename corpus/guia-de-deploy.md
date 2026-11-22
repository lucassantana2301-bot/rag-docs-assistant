# Guia de deploy

Como mudanças chegam à produção na Nimbus Pay.

## Pipeline

Todo merge na branch `main` dispara o pipeline do GitHub Actions: testes, análise de segurança (SAST e dependências), build da imagem e deploy automático em staging. A promoção para produção é feita pelo botão "Promote" no Argo CD, depois que os testes de fumaça de staging passam.

## Janelas de deploy

Deploys em produção acontecem de segunda a quinta-feira, das 10h às 17h. Não há deploy em produção na sexta-feira, em véspera de feriado nem nos dias de pico de pagamentos (dia 5 e dia 20 de cada mês). Correções de incidente SEV1 ou SEV2 podem ser feitas fora da janela com aprovação do incident commander.

## Estratégia de rollout

Serviços do domínio de pagamentos usam canary: 5% do tráfego por 15 minutos, depois 25%, 50% e 100%. O Argo Rollouts interrompe e reverte sozinho se a taxa de erro passar de 1% ou a latência p99 subir mais de 20% em relação à versão anterior.

## Feature flags

Funcionalidades novas entram desligadas por feature flag (LaunchDarkly). Ligar uma flag para clientes é uma mudança de produção e segue a mesma janela de deploy. Flags devem ser removidas do código em até 30 dias depois de ligadas para 100% dos clientes.

## Rollback

O rollback é feito pelo Argo CD, voltando para a revisão anterior, e leva cerca de 3 minutos. Migrações de banco precisam ser compatíveis com a versão anterior do código (expand and contract), para que o rollback nunca dependa de desfazer a migração.

## Aprovação de mudanças

Pull requests precisam de uma aprovação de outra pessoa do time. Mudanças em `infra/`, em regras de antifraude ou em cálculo de tarifas exigem duas aprovações, sendo uma de pessoa sênior.
