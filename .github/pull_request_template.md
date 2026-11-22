## O que muda

<!-- Resumo em 1–3 frases. Linke a issue: "Closes #123". -->

## Por quê

<!-- Contexto, problema ou decisão por trás da mudança. -->

## Como testei

<!-- Testes automatizados adicionados e/ou passos manuais. -->

## Checklist

- [ ] `uv run ruff check .` passa localmente
- [ ] `uv run ruff format --check .` passa localmente
- [ ] `uv run mypy` passa localmente
- [ ] `uv run pytest --cov` passa localmente
- [ ] `uv run rag eval eval/golden.jsonl --min-hit-rate 0.9` passa localmente
- [ ] Testes cobrem o comportamento novo ou o bug corrigido
- [ ] Documentação (README/ADR/CHANGELOG) atualizada quando aplicável
- [ ] Sem segredos, dados reais de clientes ou credenciais no diff
