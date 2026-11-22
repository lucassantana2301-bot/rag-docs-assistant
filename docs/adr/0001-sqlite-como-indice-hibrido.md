# ADR 0001: SQLite como índice lexical e vetorial

- **Status:** aceito
- **Data:** 2026-11-22

## Contexto

O assistente precisa de busca lexical (BM25) e vetorial sobre alguns milhares a algumas centenas de milhares de trechos. As opções consideradas:

| Opção | Prós | Contras |
| --- | --- | --- |
| Banco vetorial dedicado (Qdrant, Weaviate) | escala, filtros, ANN | mais um serviço para operar; BM25 fraco ou ausente |
| PostgreSQL + pgvector + `tsvector` | maduro, escala bem | exige servidor; configuração de português no `tsvector` |
| Elasticsearch/OpenSearch | BM25 excelente, kNN | pesado para o tamanho do problema |
| **SQLite com FTS5 + vetores em BLOB** | um arquivo, zero operação, transação única | busca vetorial exata (O(n)); uma escrita por vez |

## Decisão

SQLite: tabela `chunks` com o vetor em BLOB (`float32`) e índice FTS5 com `tokenize='unicode61 remove_diacritics 2'`, para "férias" e "ferias" serem o mesmo termo. Texto e vetor são gravados na mesma transação, então não existe chunk só com um dos dois. A busca vetorial é um produto de matriz em NumPy sobre a matriz carregada em memória, invalidada a cada escrita.

## Consequências

- Exato e rápido até cerca de 1 milhão de chunks de 768 dimensões (~3 GB em memória). Acima disso, a interface `Store` (gravar, apagar, `lexical_search`, `vector_search`) é pequena o bastante para uma implementação em pgvector com índice HNSW.
- Uma escrita por vez: suficiente para indexação em lote e uploads ocasionais, não para ingestão contínua de alto volume.
- O índice grava o nome e a dimensão do embedder. Trocar de modelo sem reindexar é recusado, porque vetores de modelos diferentes não são comparáveis.
