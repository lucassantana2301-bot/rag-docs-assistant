# Runbook de gestão de incidentes

Este runbook define como a engenharia da Nimbus Pay classifica, comunica e encerra incidentes de produção.

## Severidades

| Severidade | Critério | Tempo para acionar |
| --- | --- | --- |
| SEV1 | Pagamentos fora do ar, vazamento de dados ou perda financeira em andamento | imediato |
| SEV2 | Funcionalidade importante degradada para muitos clientes (ex.: Pix com latência acima de 5 s) | até 15 minutos |
| SEV3 | Problema com contorno ou que afeta poucos clientes | horário comercial |
| SEV4 | Problema estético ou interno, sem impacto para clientes | backlog |

## Papéis

- **Incident commander (IC):** coordena a resposta, decide prioridades e é a única pessoa que declara o incidente resolvido. Em SEV1 e SEV2, quem está de plantão no momento aciona o IC da escala pelo PagerDuty (serviço "incident-commander").
- **Responsável técnico:** investiga e aplica a correção. Pode ser o próprio plantonista.
- **Comunicação:** atualiza a status page e o canal #incidentes a cada 30 minutos em SEV1 e a cada hora em SEV2.

## Fluxo de resposta

1. Abra o incidente com o comando `/incidente abrir` no Slack. Isso cria o canal dedicado e o documento do incidente.
2. Classifique a severidade. Na dúvida entre duas, escolha a mais alta: rebaixar depois é barato.
3. Priorize mitigar antes de entender a causa: rollback, feature flag desligada ou desvio de tráfego.
4. Registre a linha do tempo no documento do incidente enquanto trabalha.
5. O IC declara o incidente resolvido quando as métricas voltam ao normal por 30 minutos.

## Postmortem

Todo SEV1 e SEV2 tem postmortem sem culpados (blameless), escrito em até 5 dias úteis após o encerramento e revisado na reunião semanal de confiabilidade de quarta-feira. O postmortem precisa ter linha do tempo, impacto em clientes e valores, causa raiz e ações com dono e prazo.

## Plantão

A escala de plantão é semanal, começa na segunda-feira às 10h e é gerenciada no PagerDuty. O plantonista deve responder ao alerta em até 5 minutos. Quem faz plantão recebe adicional de sobreaviso conforme o acordo coletivo.
