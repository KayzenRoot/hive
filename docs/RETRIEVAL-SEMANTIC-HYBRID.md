# Retrieval semântico e híbrido

WO-007 adiciona embeddings derivados ao corpus lexical da WO-006. PostgreSQL
continua sendo a verdade durável; Redis não armazena embeddings. A integração
usa `pgvector` em `retrieval_chunk_embeddings`, com perfil que identifica
adapter, modelo, revisão, dimensão e métrica.

## Configuração

Embeddings ficam desabilitados por padrão. Para um endpoint OpenAI-compatible
confiável, configure os campos `HIVE_EMBEDDING_*` de `.env` ou do ambiente do
serviço. A API key é opcional, fica em memória como `SecretStr` e nunca deve
ser commitada. URL, modelo e dimensão são configuração do serviço; não entram
na requisição REST.

O adapter aceita `POST <base-url>/embeddings`, valida quantidade/índice/ordem,
dimensão e finitude dos vetores e impõe limites de input, batch, timeout e
dimensões. A dimensão é variável por perfil. A consulta usa scan exato bounded
nesta versão; índice aproximado não é necessário para o primeiro incremento.

## Operação

1. Sincronize o corpus lexical com
   `POST /api/v1/projects/{project_id}/retrieval/corpus/sync`.
2. Sincronize embeddings com
   `POST /api/v1/projects/{project_id}/retrieval/semantic/sync`.
3. Observe estado, perfil, cobertura e último erro em
   `GET /api/v1/projects/{project_id}/retrieval/semantic`.
4. Consulte semanticamente ou use
   `POST /api/v1/projects/{project_id}/retrieval/hybrid`.

O status semântico só fica `CURRENT` quando uma execução `COMPLETED` cobre o
corpus lexical corrente com o perfil corrente. Mudança do corpus, revisão,
modelo ou dimensão torna embeddings antigos stale; o sync seguinte reutiliza
somente dados compatíveis. Erro, indisponibilidade ou stale nunca inventa uma
contribuição: o endpoint híbrido retorna lexical com um estado explícito.

## Evidência

O script `scripts/retrieval_integration.py` executa Compose com um fixture HTTP
local determinístico, valida tipo `vector` real, reuso sem chamadas ao
provider, isolamento, challenge paraphraseado, RRF, fallback e restart. O
fixture é mecânico e não representa qualidade de modelo em produção; o
benchmark lexical permanece separado no manifesto versionado.
