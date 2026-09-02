# Reranking provider-independent

O WO-008 adiciona uma etapa opcional e limitada sobre o conjunto já produzido
por retrieval híbrido project-scoped. O reranker não indexa, não consulta
arquivos fora do corpus e não substitui lexical, semântico ou RRF.

## Contrato

O núcleo depende apenas do contrato `RerankerAdapter`: recebe a consulta e uma
lista ordenada de documentos serializados; devolve exatamente um score finito
por índice posicional explícito. A implementação HTTP usa `POST /rerank` com
`{model, query, documents, top_n}` e aceita `{model?, results:[{index,
relevance_score}]}`. SDKs de fornecedores não fazem parte do núcleo.

A serialização `rerank-document-v1` contém somente `source_kind`, `path`,
`title`, `qualified_symbol` e snippet limitado. A identidade do perfil inclui
adapter, modelo, revisão e versão de serialização; não inclui URL ou segredo.

## Estados e segurança

O recurso é desabilitado por padrão (`HIVE_RERANK_ENABLED=false`). Quando
desabilitado, sem configuração, com resposta inválida, erro do provider,
timeout ou sem candidatos, a API conserva a ordem híbrida e deixa
`rerank_score` nulo. O modo `strict_rerank` transforma falhas do provider em
erro HTTP 503 limitado.

URL, modelo e chave vêm somente da configuração confiável do processo. A chave
é `SecretStr`, enviada apenas no header de autorização e nunca persistida,
retornada ou registrada. O transporte rejeita URL com credenciais, esquemas
não HTTP(S), respostas acima do limite e índices duplicados, ausentes ou fora
do pool. A ordenação ativa é score decrescente, posição pré-rerank e referência
estável.

## API e Control Center

`POST /api/v1/projects/{project_id}/retrieval/rerank` expõe consulta, top-k,
source kind, pool limitado e modo estrito. A resposta mantém os campos de
proveniência híbrida e acrescenta posição antes/depois, score de rerank, perfil
e estado de fallback. O Control Center mostra o estado do reranker, modelo,
revisão, fingerprint curto, versão de serialização e pool, sem exibir chaves.

## Validação

O fixture local em `scripts/rerank_fixture.py` é determinístico e serve apenas
para testes. A integração Docker cobre promoção de um candidato relevante,
recall@5 e MRR não inferiores ao híbrido, melhoria estrita, reprodutibilidade
em duas execuções, isolamento, pool, proveniência, falhas malformadas,
fallback exato, modo estrito e reinícios. Esses resultados são gates
mechanical do fixture, não uma alegação de qualidade de produção.
