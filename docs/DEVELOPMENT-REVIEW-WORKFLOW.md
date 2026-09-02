# Development review workflow

O incremento de retrieval é revisado como Draft PR. O job obrigatório
`Review Evidence` depende de `Validate` e `Integration health`, verifica que a
PR continua Draft e executa contra o SHA exato do head da PR.

O artefato `review-manifest.json` segue
`schemas/review-evidence-v1.schema.json`; `review-summary.md`, logs e o
benchmark são anexados ao mesmo run. Um comentário sticky identificado por um
marcador fixo pode ser atualizado pelo job, sem criar comentários duplicados.

`scripts/review_evidence.py` é genérico: recebe work order, base/head, PR e
estado de integração por argumentos e não presume uma branch ou projeto. O
gerador `scripts/review_bundle.py` permanece compatível com bundles históricos;
novos incrementos devem usar o manifesto versionado para evidência de revisão.

Nenhum job executa merge, publica release, altera o Project Brain canônico ou
aplica regras de proteção antes de o check real existir e passar no SHA
correto. Falhas de permissão do GitHub devem permanecer explícitas na evidência.
