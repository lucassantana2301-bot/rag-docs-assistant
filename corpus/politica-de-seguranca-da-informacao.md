# Política de segurança da informação

## Contas e senhas

Todas as ferramentas corporativas usam login único (SSO) pelo Okta. A autenticação em dois fatores (MFA) é obrigatória, com chave física (YubiKey) para quem tem acesso a produção e app autenticador para os demais. SMS não é aceito como segundo fator.

Senhas precisam ter no mínimo 14 caracteres e ficam no gerenciador de senhas corporativo (1Password). É proibido compartilhar senhas por chat ou e-mail; use o compartilhamento do próprio 1Password.

## Acesso a produção

Ninguém tem acesso permanente a produção. O acesso é pedido pelo Teleport com justificativa, aprovado por outra pessoa do time e expira em 4 horas. Todas as sessões são gravadas e auditadas mensalmente pelo time de Segurança.

## Dados de clientes

Dados pessoais de clientes (CPF, dados bancários, endereço) só podem ser acessados para atender um chamado ou investigar um incidente, sempre pelo backoffice, que registra o acesso. Exportar dados de clientes para planilhas ou ferramentas fora do ambiente aprovado é proibido. Os dados são tratados conforme a LGPD, e o encarregado de dados (DPO) é contatado pelo e-mail dpo@nimbuspay.example.

## Notebooks e dispositivos

Os notebooks corporativos são gerenciados pelo Jamf (macOS) ou Intune (Windows), com disco criptografado e bloqueio de tela após 5 minutos. Celular pessoal pode acessar e-mail e Slack, desde que tenha bloqueio de tela e o app de gestão (MDM) instalado.

## Como reportar um incidente de segurança

Qualquer suspeita de phishing, vazamento ou acesso indevido deve ser reportada imediatamente no canal #seguranca ou pelo e-mail seguranca@nimbuspay.example. Não tente investigar sozinho e não apague evidências. Perda ou roubo de notebook deve ser comunicado em até 2 horas para o bloqueio remoto.

## Uso de ferramentas de IA

Ferramentas de IA generativa só podem ser usadas com dados públicos ou internos não sensíveis, e apenas as aprovadas pelo time de Segurança (lista na intranet). Código-fonte, dados de clientes e credenciais nunca podem ser colados em ferramentas não aprovadas.
