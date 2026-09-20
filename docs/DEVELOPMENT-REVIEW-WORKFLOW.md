# Development review workflow

O incremento de retrieval é revisado como PR Ready. O job obrigatório
`Review Evidence` depende de `Validate` e `Integration health`, verifica que a
PR não está Draft e executa contra o SHA exato do head da PR. Auto-merge squash
fica condicionado a uma aprovação independente elegível e à resolução de
threads; o executor não aprova nem mescla.

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


## Correção direta durante o review

Defeitos encontrados por Sol durante o review são classificados como
`SELF_HEALABLE` ou `EXECUTOR_REQUIRED`.

`SELF_HEALABLE` é exclusivamente um defeito pequeno, localizado e de baixo
risco que Sol consegue corrigir com as ferramentas atualmente disponíveis e
validar com evidência objetiva, sem depender de segredo, estado apenas local,
migração, ação destrutiva/irreversível, expansão de escopo, mudança de
arquitetura, alteração de decisão aprovada ou evidência inacessível ao reviewer.

Quando o defeito for `SELF_HEALABLE`, Sol deve aplicar a menor correção segura,
validar o delta e continuar o mesmo review. Se o incremento ficar limpo, o mesmo
review já libera o próximo prompt autorizado, evitando uma rodada de Codex usada
somente para um erro trivial.

Quando o defeito for `EXECUTOR_REQUIRED`, o veredito é `CORRECTION REQUIRED`
e Sol fornece somente o delta corretivo ao executor. Nenhum Work Order posterior
é liberado até a correção ser objetivamente validada.

A correção direta nunca autoriza bypass de `main` protegido, required checks,
Review Evidence, promoção canônica, STOP CONDITION, gates HIGH/CRITICAL ou
limpeza/refatoração não relacionada.
