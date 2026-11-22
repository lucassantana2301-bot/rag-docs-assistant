# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota o
[Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [1.0.0] - 2026-11-22

Primeira versão estável.

### Adicionado

- **Ingestão** de Markdown, texto, HTML e PDF com caminho de títulos e página de origem de cada trecho;
  reingestão idempotente por hash de conteúdo.
- **Chunking estrutural** (título → parágrafo → frase) com sobreposição entre trechos.
- **Busca híbrida**: BM25 no SQLite FTS5 (sem acento e sem diferenciar maiúsculas) e similaridade
  vetorial no mesmo arquivo, fundidas por Reciprocal Rank Fusion.
- **Respostas sempre citadas** com validação das citações e recusa quando a resposta não está nos documentos.
- **Provedores plugáveis**: embedding local por hashing (offline) ou OpenAI/Ollama; geração extrativa
  (offline) ou OpenAI, Anthropic e Ollama, com proteção contra prompt injection vinda dos documentos.
- **API REST** (FastAPI) com upload autenticado, interface web e documentação interativa.
- **Avaliação automática** com golden set de 38 perguntas: hit rate, MRR, fidelidade das citações,
  fatos-chave e recusas, usada como portão de qualidade no CI.
- **Relatório de avaliação navegável** (`rag eval --html`), publicado no GitHub Pages a cada push.
- **Imagem Docker** sem root publicada no GHCR com SBOM e atestado de proveniência, e wheel anexado à release.
- **Qualidade**: ruff, mypy `strict`, 60 testes com 94% de cobertura, CodeQL, Dependabot, devcontainer e ADRs.

[Não lançado]: https://github.com/lucassantana2301-bot/rag-docs-assistant/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lucassantana2301-bot/rag-docs-assistant/releases/tag/v1.0.0
