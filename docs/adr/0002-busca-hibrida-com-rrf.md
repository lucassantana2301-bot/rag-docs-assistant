# ADR 0002: Busca híbrida com Reciprocal Rank Fusion

- **Status:** aceito
- **Data:** 2026-11-22

## Contexto

BM25 acerta termos exatos (siglas, nomes de sistema, "SEV1", "Idempotency-Key"), mas erra quando a pergunta usa outras palavras. A busca vetorial generaliza por significado, mas pode trazer trechos "parecidos" que não contêm o termo pedido. Usar só um dos dois deixa resultado na mesa.

Para combinar, a abordagem ingênua é somar os scores. O problema é que o BM25 não tem teto e varia com o tamanho do corpus, enquanto o cosseno fica entre -1 e 1. A soma ponderada precisa ser recalibrada a cada corpus.

## Decisão

Reciprocal Rank Fusion (Cormack, Clarke e Büttcher, 2009): cada lista contribui com `1 / (60 + posição)` para cada trecho, e a lista final é ordenada pela soma. Depois da fusão, no máximo 3 trechos por documento entram no contexto, para que um documento longo não ocupe todas as vagas.

Os pesos de cada lista ficam configuráveis no código. No corpus de exemplo, variar o peso vetorial entre 0,5 e 1,0 não mudou o hit rate (97%) e mudou o MRR em menos de 0,015, por isso o padrão é peso igual.

## Consequências

- Sem calibração por corpus, e um trecho que aparece nas duas listas sobe naturalmente.
- O ganho do híbrido depende da qualidade do embedding: com o embedding léxico local, o híbrido empata com o BM25; com embedding neural, a lista vetorial traz os casos de sinônimo que o BM25 perde. A avaliação (`rag eval`) mede os três modos lado a lado para tornar isso visível.
