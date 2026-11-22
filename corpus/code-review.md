# Boas práticas de code review

## Para quem abre o pull request

- Pull requests pequenos: o ideal é até 400 linhas alteradas. PR grande demais deve ser dividido.
- A descrição explica o porquê da mudança, como foi testada e o link para a tarefa.
- O pipeline precisa estar verde antes de pedir revisão.

## Para quem revisa

- A primeira revisão deve acontecer em até 1 dia útil. Se não puder revisar, avise e indique outra pessoa.
- Comente o código, não a pessoa. Prefira perguntas ("o que acontece se a lista vier vazia?") a ordens.
- Marque comentários opcionais com o prefixo "nit:". Eles não bloqueiam a aprovação.
- Verifique testes, tratamento de erro, segurança (dados sensíveis em log, validação de entrada) e impacto em desempenho.

## Merge

O merge é feito por quem abriu o PR, com squash, depois da aprovação. Mudanças que exigem duas aprovações estão listadas no guia de deploy.
