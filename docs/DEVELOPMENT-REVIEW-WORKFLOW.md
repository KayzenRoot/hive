# Development review workflow

O incremento de retrieval é revisado como Draft PR. O job obrigatório
`Review Evidence` depende de `Validate` e `Integration health`, verifica que a
PR continua Draft e executa contra o SHA exato do head da PR.

O artefato `review-manifest.json` segue
`schemas/review-evidence-v1.schema.json` e contém evidência estruturada de
testes, integrações, segurança, avisos e governança. O JSON completo também é
impresso entre `HIVE_REVIEW_MANIFEST_BEGIN` e `HIVE_REVIEW_MANIFEST_END`.
`review-summary.md`, diagnósticos bounded, logs selecionados e o benchmark
formam um único pacote consolidado. Um comentário sticky identificado por um
marcador fixo pode ser atualizado pelo job, sem criar comentários duplicados.
O job de integração também persiste em `service-logs.log` uma captura Docker
limitada a `--tail=200`, com credenciais comuns redigidas. O coletor de avisos
deduplica classes conhecidas — Redis `vm.overcommit_memory`, depreciação npm e
depreciação de runtime Node das Actions — e as replica no manifesto, resumo e
artefato consolidado.

`scripts/review_evidence.py` é genérico: recebe work order, base/head, PR e
estado de integração por argumentos e não presume uma branch ou projeto. O
gerador `scripts/review_bundle.py` é um fallback genérico, consome/constrói o
mesmo manifesto versionado e produz ZIP determinístico com SHA-256.

Nenhum job executa merge, publica release, altera o Project Brain canônico ou
aplica regras de proteção antes de o check real existir e passar no SHA
correto. Falhas de permissão do GitHub devem permanecer explícitas na evidência.
