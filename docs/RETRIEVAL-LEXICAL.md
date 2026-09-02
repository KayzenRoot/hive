# Retrieval lexical

WO-006 adiciona um corpus durável e project-scoped derivado do índice de
repositório e do texto READY de tasks. PostgreSQL é a fonte canônica; Redis não
guarda corpus nem referências.

## Corpus

`POST /api/v1/projects/{project_id}/retrieval/corpus/sync` reconcilia fontes
indexadas, revalida o `HEAD`, lista de arquivos e SHA-256 dos bytes antes de
publicar chunks. O chunker `line-window-v1` usa janelas determinísticas de até
80 linhas/6.000 caracteres, overlap de 10 linhas e divisão limitada de linhas
muito longas. Cada referência mantém path, símbolo/task, SHA, linhas e offsets
de caracteres.

Uma falha de revalidação não substitui o último corpus válido: o estado passa a
`STALE` e a API continua devolvendo o snapshot anterior. Um projeto sem corpus
válido fica `BLOCKED` até uma sincronização bem-sucedida.

## Lexical API

`POST /api/v1/projects/{project_id}/retrieval/lexical` aceita `query`, `top_k`
(1–20) e filtro opcional `source_kind`. A consulta normaliza aliases
ordinary/snake/kebab/dotted/camel-case e usa busca lexical simples do PostgreSQL
com boosts determinísticos para match exato, path, basename, título e símbolo.
Empates são resolvidos por score, tipo, path, símbolo, linha e ID; snippets e
resultados possuem limites fixos. Todas as consultas filtram `project_id`.

O benchmark versionado está em
`benchmarks/retrieval_lexical_manifest.json`; a integração real escreve
`tmp/validation/retrieval-benchmark.json` e executa a mesma bateria duas vezes
para conferir reprodutibilidade.
