"""Render the executor review for an auditable pull request."""

from __future__ import annotations

import argparse
from pathlib import Path


def _render_wo008_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
) -> str:
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

Esta entrega adiciona a fundação de reranking provider-independent, opcional e
bounded sobre candidatos híbridos project-scoped já existentes.

## 2. Base, branch e head

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata auditada: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.

## 3. Arquitetura

O reranker consome somente o conjunto híbrido limitado e não substitui lexical,
semântico ou RRF. O núcleo depende de um contrato `RerankerAdapter` substituível;
o transporte HTTP é uma implementação mínima sem SDK de fornecedor obrigatório.

## 4. Perfil e configuração

O recurso é desabilitado por padrão. Adapter, modelo, revisão e versão de
serialização formam fingerprint estável; URL e chave não participam da
identidade. Pool, query, documentos, resposta e timeout permanecem bounded.

## 5. Serialização

A versão `rerank-document-v1` serializa apenas source kind, path, title,
qualified symbol e snippet limitado, com ordem de campos estável. Não há texto
de arquivo inteiro, score bruto canônico ou payload persistido.

## 6. Transporte

O contrato local usa `{{model, query, documents, top_n}}` e exige
`{{model?, results:[{{index, relevance_score}}]}}`. Índices são explícitos e a
resposta precisa cobrir cada candidato exatamente uma vez.

## 7. API

`POST /api/v1/projects/{{project_id}}/retrieval/rerank` expõe query, top-k,
source kind, candidate pool e `strict_rerank`. Status separado mostra estado,
perfil, revisão, fingerprint curto, serializer e limites sem exibir segredos.

## 8. Fallback

Disabled, unconfigured, no candidates, provider error, timeout, stale/config
inválido e resposta malformada preservam exatamente a ordem híbrida e deixam o
score de rerank nulo. O modo estrito retorna erro 503 bounded.

## 9. Proveniência

Cada resultado preserva project/reference/chunk/corpus, hashes, snippet,
linhas, chars, source kind e identidade de origem, além de pre-rerank rank,
rerank rank, score e contribuições híbridas.

## 10. Segurança

Somente URL HTTP(S) confiável é aceita; credenciais inline, URL arbitrária e
model caller-controlled são rejeitados. A API key usa `SecretStr`, header
transitório e nunca é persistida, retornada ou registrada.

## 11. Dashboard

O Control Center mostra enabled/configured, adapter, modelo, revisão,
fingerprint curto, serializer e pool. O lab permite rerank híbrido, pool,
strict mode e inspeção antes/depois, contribuições e proveniência.

## 12. Benchmark

O benchmark preserva os baselines lexical, semantic e hybrid e adiciona um
desafio determinístico em que um candidato relevante já está no pool e é
promovido. Os gates exigem recall@5 e MRR não inferiores ao híbrido, melhoria
estrita, zero miss crítico, pool limitado e duas execuções reproduzíveis.

## 13. Testes unitários

São cobertos disabled/default, bounds, fingerprint sem segredo, serialização,
índices reversos explícitos, duplicados, ausentes, fora do range, NaN,
Infinity, score inválido, mismatch de modelo, HTTP, timeout e todos os
fallbacks, incluindo strict mode.

## 14. Integração Docker

O fixture local determinístico e o stack real PostgreSQL/pgvector, Redis, API e
dashboard validam candidatos híbridos apenas, promoção, isolamento, pool,
fallback exato, resposta inválida, provider down, status strict e benchmark.
A correção C1 também publica evidência real para isolamento project-scoped,
colapso de TASK duplicada, matriz de respostas inválidas, preservação de
semantic STALE, não vazamento de segredo-sentinela e reprodutibilidade da ordem
de identidades/ranks; os valores auditáveis ficam no artefato e no sticky.

## 15. Resiliência

O corpus corrente continua válido durante falhas de provider e reinícios de
Redis/API. Não há migration nova, tabela durável de rerank, alteração de
currentness semântica ou chamada a rede pública no gate.

## 16. Review Evidence

O marcador `<!-- hive-review-evidence:{work_order} -->` e o artefato
`{artifact_name}` são derivados dinamicamente do work order e do head. O
manifesto consolida testes, integração, benchmark, segurança, warnings e
governança com limites determinísticos.

## 17. Governança GitHub

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. A proteção permanece ativa, checks reais, squash-only, sem
bypass e com uma aprovação independente elegível exigida. O executor não
aprova e não faz merge.

## 18. Arquivos e artefato

As superfícies alteradas ficam em backend, dashboard, scripts, benchmark,
schema de evidência, configuração Docker, `.env.example`, mapas gerados e
documentação não canônica. O consolidado é `{artifact_name}`.

## 19. Riscos e limites

O adapter HTTP é deliberadamente mínimo e o fixture mede apenas propriedades
mecânicas do contrato. Não há alegação de qualidade de produção, ranking
universal, cache semântico ou dependência de um fornecedor específico.

## 20. Escopo negativo

Não foi feita migration, promoção de checkpoint canônico, release, tag, merge
manual, bypass, aprovação automática de Sol, executor autônomo, memória,
Context Manager, MCP ou WO-009.

## 21. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Aprovações independentes
observadas: zero. Sol Review State: AWAITING_SOL.

## 22. Checkpoint proposto

O checkpoint canônico não foi modificado. Após auditoria independente de Sol,
fica proposta apenas a decisão de promover WO-008; nenhuma mutação canônica é
executada por esta PR.

WO-008-C1 READY FOR SOL GITHUB AUDIT
"""


def _render_wo008_g1_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
) -> str:
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

Esta correção preserva o CI pós-merge em `main`: o workflow não arma mais
auto-merge com `GITHUB_TOKEN`. O executor deve armar o auto-merge nativo
SQUASH a partir de uma identidade GitHub User; o Review Evidence apenas
verifica e registra essa identidade.

## 2. Base, branch e head

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata auditada: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.

## 3. Arquivos alterados

As alterações ficam restritas ao workflow CI, ao gerador/verificador de Review
Evidence, ao schema e aos testes determinísticos de governança.

## 4. Ownership do auto-merge

O auto-merge deve estar armado externamente pelo executor autenticado como uma
identidade GitHub User. O manifesto e o sticky comment registram o login e o
tipo observados, sem expor credenciais; identidades Bot/App falham fechado.

## 5. Mudança no workflow

O job Review Evidence verifica PR Ready, head exato, auto-merge armado, método
SQUASH e owner User. Ele não executa `gh pr merge --auto`.

## 6. Testes

Há fixtures para owner User aceito, `github-actions[bot]`, Bot, App, ausência
de auto-merge e método incorreto rejeitados, além de cobertura do trigger push
para `main` e da ausência da mutação no workflow.
As gates de evidência C1 do WO-008 permanecem obrigatórias nesta correção.

Comandos de validação: `python scripts/verify_canonical_sources.py`,
`python scripts/check_secrets.py`, `python scripts/generate_maps.py --check`,
`python -m ruff format --check backend scripts migrations`,
`python -m ruff check backend scripts migrations`, `python -m mypy`,
`python -m pytest`, `cd dashboard && npm ci && npm run lint && npm run typecheck
&& npm run test:run && npm run build && npm audit`, e `docker compose config
--quiet`.

## 7. CI da PR e artefato

Validate, Integration health e Review Evidence devem passar no head exato.
O consolidado é `{artifact_name}` e o sticky comment deve expor o owner sem
segredos.

## 8. Riscos conhecidos e fontes canônicas

O fluxo depende de o executor armar o auto-merge como User; ausência, Bot ou
App bloqueia o handoff. Em hosts Windows, o init de PostgreSQL em bind mount
pode exceder o healthcheck padrão, sem alterar a configuração de produção.
Fontes: [checkpoint](../blob/main/docs/project-brain/13-CHECKPOINT.md),
[decisões](../blob/main/docs/project-brain/16-DECISIONS-LEDGER.md),
[escopo](../blob/main/docs/project-brain/03-SCOPE.md),
[Definition of Done](../blob/main/docs/project-brain/15-DEFINITION-OF-DONE.md),
[arquitetura](../blob/main/docs/project-brain/04-ARCHITECTURE.md) e
[requisitos](../blob/main/docs/project-brain/02-REQUIREMENTS.md).

## 9. Governança

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. A proteção permanece ativa, com os três checks reais,
SQUASH-only, uma aprovação independente exigida e zero bypass. Ruleset unchanged:
`true`, verificado contra o Ruleset 21934284.

## 10. Escopo negativo

Não foi feita alteração de produto, migration, promoção do checkpoint, merge
manual, bypass, aprovação automática de Sol ou início de WO-009.

## 11. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Aprovações independentes
observadas: zero. Sol Review State: AWAITING_SOL.

WO-008-G1 READY FOR SOL GITHUB AUDIT
"""


def _render_wo009_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
    auto_merge_owner_login: str,
    auto_merge_owner_type: str,
) -> str:
    owner_text = (
        f"`{auto_merge_owner_login}` ({auto_merge_owner_type})"
        if auto_merge_owner_login and auto_merge_owner_type
        else "recorded by Review Evidence"
    )
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo

Esta PR implementa somente a fundação determinística do Context Manager sobre
o Project Registry, Task Intake, índice/corpus, retrieval híbrido e reranking
já aprovados. Não há LLM, memória, migration ou alteração do Project Brain.

## 2. Base / branch / HEAD / PR

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- HEAD final: `{head_sha}`.

## 3. Arquivos criados/alterados

O conjunto está restrito ao Context Manager, API, testes determinísticos,
integração Docker/Git, evidência/schema, workflow, documentação não canônica,
atlas gerado e este template de handoff.

## 4. Decisões locais de implementação

O assembler reutiliza os serviços existentes para lookup de projeto e tarefa,
currentness de índice/corpus e `rerank_search(...)`; não duplica retrieval,
fusão semântica, fallback ou regras de segurança de paths.

## 5. Contrato do Context Manager

`POST /api/v1/projects/{{project_id}}/tasks/{{task_id}}/context` retorna
`context-capsule-v1` com projeto, tarefa, governança, estrutura explícita da
tarefa, retrieval, projeções de arquivos/símbolos/testes, proveniência e bounds.

## 6. Governança / checkpoint-first

Somente os cinco caminhos `docs/project-brain` Git-tracked do projeto alvo são
aceitos. O checkpoint é processado e emitido primeiro. A seleção de governança
é em duas fases: cobertura obrigatória das cinco fontes, depois extras
opcionais. A ordem de autoridade obrigatória permanece
CHECKPOINT -> SCOPE -> DEFINITION_OF_DONE -> ARCHITECTURE -> DECISIONS.
O budget de caracteres reserva cobertura obrigatória antes de extras;
cobertura impossível falha fechado.

## 7. Bounds e determinismo

Task, excerpts, seções, resultados, snippets e o JSON final usam limites fixos.
Truncation flags e métricas de caracteres são emitidos; entradas idênticas em
estado idêntico produzem o mesmo capsule sem timestamp ou UUID novo.

## 8. Trust boundary / segurança

Task text não é governança, não executa instruções e só produz constraints ou
acceptance criteria quando headings explícitos existem. Paths, symlinks,
project binding, Git tracking, SQL e erros permanecem fail-closed e bounded.

## 9. Retrieval / rerank / fallback

O query é derivado deterministicamente e normalizado pelo contrato existente.
O pipeline rerank/hybrid/semantic preserva seus estados, fallbacks, scores e
proveniência; o Context Manager não chama provider diretamente.

## 10. Testes unitários

Cobertura inclui ordem e identidade de governança, isolamento, task binding,
trust, parsing explícito, query bound, projections, provenance, fallback,
truncation, repetibilidade, races, errors e API contract.

## 11. Integração real

O cenário real usa dois projetos Git registrados, Task Intake, index, corpus,
semantic/rerank fixtures, context API, missing governance, cross-project,
HEAD race e rebuild após Redis/API restart.

## 12. Lint / typecheck / build / audit

Validate, secret scan, canonical/map checks, Ruff, mypy, pytest, dashboard
lint/typecheck/tests/build/audit, Compose config e integrações existentes
devem passar. Migration head permanece `0005_semantic_retrieval`.
Comandos executados incluem `python scripts/verify_canonical_sources.py`,
`python scripts/validate.py` e `python scripts/context_manager_integration.py`.

## 13. Review Evidence

Artifact: `{artifact_name}`. A evidência Context Manager deve mostrar
checkpoint-first, `mandatory_governance_coverage: true`, a sequência
obrigatória das cinco fontes, project/task scoped, reranked retrieval,
provenance, deterministic two-run, bounds, isolation, missing-governance/HEAD
fail-closed, Redis/API rebuild e `llm_calls: 0`.

## 14. Ruleset / auto-merge

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. Ruleset unchanged, checks reais, squash-only e zero bypass.
Auto-merge owner: {owner_text}; somente User é aceito.

## 15. Erros corrigidos durante a execução

Falhas de bounds e fixtures de integração foram corrigidas com limites e
diagnósticos determinísticos; nenhuma alteração de produto foi necessária.

## 16. Riscos pendentes

O capsule é uma fundação bounded e não substitui memória, token accounting,
progressive disclosure ou execução autônoma. O cenário local pode exigir
tempo adicional para inicialização Docker em hosts Windows.

## 17. Escopo negativo

Não foi feita memória, adaptive token budget, token accounting, MCP, planner,
executor dispatch, tool execution, dashboard UI, migration, release/tag,
alteração canônica do checkpoint ou implementação de outro work order.

## 18. Proposta de checkpoint

Nenhuma atualização canônica é executada por esta PR. A promoção futura deve
ser uma ordem separada após auditoria de Sol.

## 19. Sol Review State

A PR permanece aberta, Ready e não mesclada. Aprovações independentes
observadas: zero. Sol Review State: AWAITING_SOL.

WO-009 READY FOR SOL GITHUB AUDIT
"""


def _render_wo010_g1_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
) -> str:
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

Esta PR instala governança GitHub de conta única, aprovada pelo usuário:
somente `KayzenRoot` opera o repositório. Executor e Sol continuam papéis
lógicos distintos. A qualidade deixa de depender de Approve nativo do GitHub
e passa a ser auditoria de Sol no HEAD exato, checks obrigatórios e
autorização explícita da ação de merge após a auditoria de Sol.

## 2. Base, branch e head

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.
- A PR #34 de Progressive Disclosure permanece aberta, no HEAD C2, com
auto-merge desarmado. Esta PR não mescla WO-010.

## 3. Arquivos alterados

Somente documentação canônica de governança, Review Evidence, schema, testes,
template de PR e o workflow CI. Nenhum código de Progressive Disclosure.

## 4. Modelo operacional

Fluxo: `EXECUTOR -> CHECKS -> AWAITING_SOL -> SOL AUDIT -> SOL MERGE AUTHORIZATION ->\
 MERGE -> PUSH CI -> CHECKPOINT`. O executor para com
auto-merge desarmado. Após `APPROVED`, se a PR estiver limpa/mergeable e todos
os checks obrigatórios estiverem verdes, Sol faz diretamente o SQUASH no HEAD\
exato auditado. Se somente checks obrigatórios legítimos estiverem pendentes,
Sol pode armar auto-merge nativo SQUASH como `KayzenRoot`. HEAD movido,
check falho/ausente, conflito, draft, thread não resolvida, ruleset divergente
ou evidência incompleta bloqueiam ambas as ações.

## 5. Ruleset Protect main

O Ruleset `21934284` permanece ativo, com Protect main, deletion,
non-fast-forward, PR obrigatório, resolução de threads, squash-only, os três
checks reais e zero bypass. `required_approving_review_count` passa a 0;
`require_last_push_approval` e `require_extra_approval_for_unattributed_changes`
passam a false. Antes: {ruleset_before}; merge: {merge_before}. Depois:
{ruleset_after}; merge: {merge_after}.

## 6. Review Evidence

A evidência falha fechado se o auto-merge estiver armado antes da auditoria
de Sol. `ruleset_unchanged` compara o baseline de conta única. A permissão
de colaborador `kayzenweb3` não é mais consultada nem exigida para PASS.
Reviews históricas não bloqueiam o handoff. `--verify-auto-merge` permanece
no CLI para o caso condicional de checks pendentes e saiu do job de PR. A
autorização de SQUASH direto exige rechecagem do PR Ready, HEAD/base exatos,
mergeability, ruleset, checks verdes e threads resolvidas.

## 7. Testes

Cobertura determinística para approvals=0, last-push false, extra
unattributed false, checks/squash/zero bypass, auto-merge desarmado no
pré-Sol, ausência de dependência de `kayzenweb3`, reviews históricas e
escopo WO-010-G1.

## 8. CI da PR e artefato

Validate, Integration health e Review Evidence devem passar no head exato.
O consolidado é `{artifact_name}`. Auto-merge desta PR permanece desarmado.

## 9. Escopo negativo

Não foi feito merge da PR #34, rearmamento de auto-merge em #34, aprovação
inventada de Sol, bypass, merge-commit, rebase, início de WO-011 nem
promoção de checkpoint de Progressive Disclosure.

## 10. Riscos conhecidos e fontes canônicas

Com zero aprovações nativas, o SQUASH direto de `KayzenRoot` é tecnicamente
possível; o gate operacional é a separação de estágios, a autorização de Sol
no HEAD exato e o fail-closed em qualquer divergência. Fontes: [checkpoint]
(../blob/main/docs/project-brain/13-CHECKPOINT.md), [decisões]
(../blob/main/docs/project-brain/16-DECISIONS-LEDGER.md).

## 11. Sol Review State

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-010-G1 READY FOR SOL AUDIT
"""


def _render_wo010_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
    auto_merge_owner_login: str,
    auto_merge_owner_type: str,
) -> str:
    _ = (auto_merge_owner_login, auto_merge_owner_type)
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

Esta PR implementa somente a fundação determinística de Progressive Disclosure
L0-L5 sobre o Context Manager já aprovado. A seleção começa no menor nível
suficiente e só escala com insuficiência explícita, sem LLM, Adaptive Token
Budget, memória ou alteração canônica. O branch foi atualizado por rebase limpo
sobre o `main` aprovado, sem mudança semântica do produto.

## 2. Base, branch e HEAD

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata atual: `{base_sha}`.
- HEAD exato desta revisão: `{head_sha}`.
- Merge não executado; o branch deve permanecer com `behind_by=0`.

## 3. Governança vigente

O ADR-019 de conta única está vigente no `main`: `KayzenRoot` é a única conta
operacional, Executor e Sol são papéis lógicos distintos, e não há dependência
operacional de uma segunda conta ou de aprovação nativa independente.

## 4. HEAD candidato final

`{head_sha}`

## 5. Estado da PR

#{pr_number}, aberta como Ready for review, sem merge manual. Auto-merge
permanece desarmado antes da auditoria de Sol; `Sol Review State: AWAITING_SOL`.

## 6. Arquivos criados/alterados

O conjunto está restrito ao modelo L0-L5, integração no Context Manager,
testes determinísticos, integração Docker/Git, evidência/schema, documentação
não canônica, atlas gerado e este template de handoff. Não há alteração em
`docs/project-brain/`.

## 7. Decisões de implementação

O assembler reutiliza o pipeline existente e aplica disclosure depois do
rerank. Níveis inválidos são rejeitados. Evidência estruturada entra no
capsule sem duplicar retrieval, governança ou isolamento.

## 8. Modelo L0-L5

- L0 Project capsule
- L1 Module summaries
- L2 Symbol signatures and dependency metadata
- L3 Relevant implementation excerpts
- L4 Complete file
- L5 Repository-wide investigation

## 9. Nível inicial

O start usa título, constraints, corpo da tarefa, Acceptance Criteria,
evidência já resolvida (arquivos/símbolos/testes/retrieval) e o piso
opcional `disclosure_level`. Requisitos já conhecidos de L3/L4/L5 começam
nesse nível; não há escalada sintética L0→L1→L2→L3.

## 10. Escalada e evidência

A escalada só ocorre depois da materialização, quando o nível inicial não
consegue emitir assinatura ou excerpt exigido. Cada passo registra
`from_level`, `to_level`, `reason` e `evidence` bounded. Para no primeiro
nível suficiente e não passa de L5.

## 11. Bounds por nível

Constantes fixas e conservadoras: módulos, símbolos, excerpts, contagem de
arquivos completos e inventário. L4 emite o arquivo textual inteiro; o bound
global do capsule continua fail-closed se o arquivo completo não couber.
`total_emitted_context_characters` inclui o payload de disclosure (L1/L2/L4/L5)
sem duplicar snippets de retrieval. Truncation de conteúdo L4 por caracteres
não é usada. Não há budget adaptativo.

## 12. Contrato da API

`POST /api/v1/projects/{{project_id}}/tasks/{{task_id}}/context` aceita
`disclosure_level` opcional L0-L5 como piso (nunca retorna nível mais raso
que o pedido válido). O capsule expõe `progressive_disclosure` (com
`requested_level` / `requested_level_applied`), `module_summaries`,
`symbol_signatures`, `dependencies`, `complete_files` e `inventory`.

## 13. Migration

Head permanece `0005_semantic_retrieval`. Nenhuma migration foi criada.

## 14. Testes

Cobertura unitária/contrato para mapeamento canônico, rejeição inválida,
start a partir de Acceptance Criteria e evidência resolvida, materialização
L1/L2, piso explícito L0/L3/L4/L5, resolução L4 sem path literal, L4 vazio
fail-closed, bounds com payload de disclosure, escalada legítima, isolamento
e duas execuções idênticas.

## 15. Contagens

As contagens exatas entram no Review Evidence do head candidato; o baseline
rejeitado de WO-010 era backend 213 e dashboard 7.

## 16. Lint / typecheck / build

Validate, Ruff, mypy, dashboard lint/typecheck/tests/build/audit e Compose
devem passar no head candidato.

## 17. Integração real

O cenário real prova start L3 sem escalada sintética, L0 de estado de
projeto, escalada legítima L2→L3 por assinatura ausente, L4 resolvido por
símbolo sem path literal, piso explícito L4, isolamento, disclosure
cross-project 409, missing governance, HEAD race e rebuild após Redis/API
restart.

## 18. Benchmark / regressão

Retrieval/rerank e fixtures aceitas do Context Manager permanecem no gate
existente. Progressive disclosure não gasta LLM.

## 19. Segurança / isolamento / race

Cross-project task continua 404; disclosure fora do snapshot falha fechado;
governança obrigatória e HEAD/source race permanecem fail-closed.

## 20. Restart / recovery

Redis e API restart reconstroem o mesmo capsule e a mesma evidência de
disclosure para o mesmo estado Git.

## 21. Review Evidence e handoff

Artifact: `{artifact_name}`. A evidência inclui mapping L0-L5, smallest
sufficient, no unnecessary escalation, explicit insufficiency, bounded
escalation, stop-on-sufficient, two-run, cross-project disclosure,
Git/source race, Redis/API restart, `disclosure_llm_calls: 0` e
`adaptive_token_budget_implemented: false`.
Também registra base/HEAD exatos, PR Ready, auto-merge desarmado, Ruleset
21934284 inalterado, zero aprovações independentes, canonical diff nulo,
Validate/Integration/Review Evidence PASS e `AWAITING_SOL`.

## 22. Erros corrigidos durante a execução

Ajustes de fixtures e bounds foram feitos para preservar projeções L3 sem
escalar L0 sem necessidade. Nenhuma expansão de produto foi necessária.

## 23. Avisos conhecidos não bloqueantes

Avisos de host Redis/npm/Node já registrados pelo Review Evidence podem
reaparecer sem alterar o resultado determinístico.

## 24. Riscos pendentes

Esta fundação não substitui Adaptive Token Budget, memória, fingerprints ou
execução autônoma. A promoção de checkpoint fica para WO-010-P.

## 25. Diff / evidência

A lista completa de arquivos, diff, testes, integração e governança está no
artefato `{artifact_name}` e no comentário sticky
`<!-- hive-review-evidence:{work_order} -->`.

## 26. Auto-merge e ação posterior de Sol

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. Ruleset unchanged, checks reais, squash-only e zero bypass.
Auto-merge permanece desarmado e nenhuma aprovação de Sol é inventada. Após
`APPROVED`, Sol revalida o HEAD/base, Ready, mergeability, checks e threads:
com todos os checks verdes, executa SQUASH direto no HEAD exato; somente se
checks obrigatórios legítimos estiverem pendentes e o estado estiver bloqueado,
pode armar condicionalmente o auto-merge nativo SQUASH. Qualquer divergência
falha fechado.

## 27. Proposta de checkpoint para WO-010-P

Nenhuma atualização canônica é executada por esta PR. Texto futuro sugerido:
`PROGRESSIVE DISCLOSURE FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE`.

WO-010 READY FOR SOL GITHUB AUDIT
"""


def _render_wo012_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
) -> str:
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

Esta correção C1 torna truthful o contrato de fingerprints do Context Capsule
e a elegibilidade do cache HOT. Identidade semântica agora separa fontes
materiais de UUIDs operacionais de index/corpus/semantic; falhas transitórias
de provider não são cacheadas; hits válidos atualizam a proveniência operacional
atual sem alterar a identidade material. Não há migration, mudança canônica ou
alteração de comportamento fora do contrato de cache/fingerprint.

## 2. Base, branch e head

- PR: #{pr_number}, aberta Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato: `{head_sha}`.

## 3. Contrato de fingerprints

O input fingerprint v2 usa SHA-256 sobre JSON canônico ordenado e vincula
projeto/HEAD/inventário, fontes materiais de corpus e tarefa, request, query
derivada, perfis semantic/rerank e a identidade agregada das políticas de
context build, retrieval, task sections e seleção de governança. UUIDs
operacionais de execução não são identidade material. O output fingerprint v2
exclui a própria evidência e os run IDs operacionais, preservando identidade
semântica entre rebuilds equivalentes.

## 4. Evidência da cápsula

O campo `context_fingerprint` expõe policy, algoritmo, versões de serialização,
hashes, classes de identidade e zero chamadas LLM/provider. A evidência é
validada com schema estrito e o output é recalculado antes do retorno. Em cache
hit, project/index/corpus/result provenance é renovada para os run IDs atuais;
essa atualização não muda o output fingerprint porque esses IDs são
operacionais.

## 5. Cache HOT

O cache usa chave Redis versionada e project-scoped, envelope bounded,
schema-validado e TTL positivo fixo de 300 segundos. Redis é apenas HOT
noncanonical; miss, timeout, corrupção, mismatch ou indisponibilidade
reconstroem a partir da verdade canônica e nunca promovem cache a source of
truth. Só respostas com resultados e estado completo podem ser escritas ou
reutilizadas. Estados `RERANK_FALLBACK_PROVIDER_ERROR`,
`RERANK_FALLBACK_INVALID_RESPONSE`, `RERANK_FALLBACK_NO_CANDIDATES` e
`LEXICAL_FALLBACK_PROVIDER_ERROR` são explicitamente não cacheáveis.

## 6. Ordem segura

Lookup ocorre depois de confirmar projeto, Git/source, checkpoint, tarefa,
corpus, semantic/rerank e input fingerprint, e antes de retrieval/rerank e
montagem custosos. Hit válido revalida envelope, capsule, hashes, budget final,
estado cacheável e estabilidade da fonte imediatamente antes do retorno; então
renova a proveniência operacional corrente.

## 7. Invalidação e isolamento

O contrato invalida mudanças de source/HEAD/corpus, texto/id/proveniência da
tarefa, request/top_k/disclosure, perfil semantic/rerank e políticas. O teste
real cobre same-text tasks, cross-project poisoning, cache corrompido, race de
HEAD e rebuild equivalente com UUIDs novos. Mudanças reais de perfil ou da
identidade agregada de policy invalidam; rotação somente de segredo permanece
estável. Falha transitória não é reutilizada: após provider recovery, o mesmo
request executa novamente e retorna o caminho normal.

## 8. Restart e perda de cache

Restart persistente de Redis reutiliza o capsule; restart da API reutiliza o
cache retido. `stop` de Redis e `FLUSHDB` forçam rebuild determinístico com
provider work observável. Rebuilds equivalentes preservam fingerprints
materiais e atualizam provenance operacional.

## 9. Independência e segurança

Fingerprints não fazem LLM/network/provider calls e não persistem segredos.
Identidades usam metadados estáveis, sem URL/chave de provider; o envelope
Redis rejeita campos extras e permanece bounded.

## 10. Compatibilidade

O campo é aditivo e o produto mantém Context Capsule, Progressive Disclosure,
Adaptive Token Budget, fallback e governança existentes. Nenhuma API pública,
endpoint, job, feature flag ou migration foi removida ou alterada.

## 11. Testes unitários

Foram adicionados testes para canonical JSON/Unicode, ordem determinística,
invalidação material, exclusão de autorreferência e run IDs operacionais,
schema strict, cache bounded, estados transitórios não cacheáveis, recovery
retry, policy aggregate binding e hit válido sem rebuild. A suíte de backend,
lint, typecheck e build permanece verde.

## 12. Integração Docker

O harness real PostgreSQL/pgvector, Redis, API e fixtures de embedding/rerank
comprovou first build `1/1` provider calls, repeat `0/0`, capsule/fingerprints
idênticos, rebuild equivalente com run IDs distintos e fontes materiais
estáveis, provenance atual, mudanças de profile/policy, segredo estável,
falhas de reranker/semantic não cacheadas com recovery retry, todas as
invalidações, isolamento, corrupção, Redis loss/flush e API restart reuse.

## 13. Gates observados

`validate.py`, a integração de Context Manager, ruff, mypy, secret scan, mapas,
audit, compose config e benchmark Adaptive Token Budget devem passar no HEAD
exato. Avisos conhecidos de npm permanecem registrados e não são ocultados;
as contagens finais ficam no Evidence Bundle gerado para este HEAD.

## 14. Evidence Bundle

O manifesto, resumo, integração, validação, diff e logs bounded estão no
artefato `{artifact_name}` e no comentário sticky marcado por
`<!-- hive-review-evidence:{work_order} -->`.

## 15. Migrações e fora de escopo

Migration head permanece `0005_semantic_retrieval`; nenhuma migration foi
criada. Delta Context, provider prompt cache, memory lifecycle, telemetry
ampla, refatoração arquitetural e cleanup posterior permanecem fora de escopo.

## 16. Governança GitHub

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. Ruleset permanece inalterado, com checks reais, threads
resolvidas, squash-only e zero bypass.

## 17. Estado para revisão independente

A PR permanece aberta, Ready e não mesclada. Auto-merge permanece desarmado;
nenhuma aprovação, promoção de checkpoint ou canonical truth é presumida.

## 18. Próximos incrementos

Não iniciar cleanup automaticamente. Após auditoria independente, eventuais
limpezas devem seguir Work Orders pequenos, com characterization tests quando
necessário e comprovação `VERIFIED_DEAD` antes de remoção.

Sol Review State: AWAITING_SOL
"""


def render_body(
    *,
    work_order: str,
    pr_number: int,
    branch: str,
    base_sha: str,
    head_sha: str,
    artifact_name: str,
    ruleset_before: str,
    ruleset_after: str,
    merge_before: str,
    merge_after: str,
    auto_merge_owner_login: str = "",
    auto_merge_owner_type: str = "",
) -> str:
    if work_order == "WO-008":
        return _render_wo008_body(
            work_order=work_order,
            pr_number=pr_number,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            artifact_name=artifact_name,
            ruleset_before=ruleset_before,
            ruleset_after=ruleset_after,
            merge_before=merge_before,
            merge_after=merge_after,
        )
    if work_order == "WO-008-G1":
        return _render_wo008_g1_body(
            work_order=work_order,
            pr_number=pr_number,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            artifact_name=artifact_name,
            ruleset_before=ruleset_before,
            ruleset_after=ruleset_after,
            merge_before=merge_before,
            merge_after=merge_after,
        )
    if work_order == "WO-009":
        return _render_wo009_body(
            work_order=work_order,
            pr_number=pr_number,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            artifact_name=artifact_name,
            ruleset_before=ruleset_before,
            ruleset_after=ruleset_after,
            merge_before=merge_before,
            merge_after=merge_after,
            auto_merge_owner_login=auto_merge_owner_login,
            auto_merge_owner_type=auto_merge_owner_type,
        )
    if work_order == "WO-010-G1":
        return _render_wo010_g1_body(
            work_order=work_order,
            pr_number=pr_number,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            artifact_name=artifact_name,
            ruleset_before=ruleset_before,
            ruleset_after=ruleset_after,
            merge_before=merge_before,
            merge_after=merge_after,
        )
    if work_order == "WO-010":
        return _render_wo010_body(
            work_order=work_order,
            pr_number=pr_number,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            artifact_name=artifact_name,
            ruleset_before=ruleset_before,
            ruleset_after=ruleset_after,
            merge_before=merge_before,
            merge_after=merge_after,
            auto_merge_owner_login=auto_merge_owner_login,
            auto_merge_owner_type=auto_merge_owner_type,
        )
    if work_order == "WO-012":
        return _render_wo012_body(
            work_order=work_order,
            pr_number=pr_number,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            artifact_name=artifact_name,
            ruleset_before=ruleset_before,
            ruleset_after=ruleset_after,
            merge_before=merge_before,
            merge_after=merge_after,
        )
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

Esta entrega adiciona retrieval semântico project-scoped sobre a fundação
lexical existente, com pgvector, adapter HTTP substituível, fusão híbrida RRF
determinística e fallback lexical explícito.

## 2. Objetivo

Persistir embeddings derivados por perfil, consultar candidatos semânticos
bounded e combinar os candidatos lexical e semântico sem reranking opaco,
preservando proveniência e isolamento por projeto.

## 3. Escopo implementado

A migration 0005 cria perfis, execuções e embeddings com tipo PostgreSQL vector.
O sync reutiliza embeddings compatíveis, falha fechado em respostas inválidas,
marca current somente após cobertura completa e oferece endpoints semantic e
hybrid com contribuições RRF visíveis.

## 4. Fora de escopo explícito

Reranking, fine-tuning, qualidade de produção do modelo, cache semântico Redis,
alteração do checkpoint canônico, release, tag, merge manual e WO-008 ficam
fora desta incrementação.

## 5. Base, branch e head

- PR: #{pr_number}, aberta em estado Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.

## 6. Decisões de arquitetura

PostgreSQL continua sendo a verdade durável. Embeddings são derivados dos
chunks lexicais correntes; perfil, modelo, revisão, dimensão e adapter entram
na identidade para impedir mistura incompatível. A dimensão é variável por
perfil e a busca usa scan exato bounded nesta versão.

## 7. Migração e schema

A migration 0005 descende de 0004 sem reescrever o histórico. As tabelas são
project-scoped, têm FKs compostas quando necessário, checks de dimensão/hash e
persistem o vetor em coluna PostgreSQL `vector`, não em array JSON.

## 8. API

Foram adicionados sync/status/query semântico e query híbrida sob o projeto.
URL, modelo, chave e limites vêm de configuração; a requisição não aceita
credenciais ou provider arbitrários. Respostas não expõem vetores crus e
mantêm snippet, range, hash e proveniência.

## 9. Segurança

Chaves usam SecretStr e header Authorization sem persistência ou log. URLs
rejeitam credenciais inline e esquemas não HTTP(S); batch, input, dimensão,
timeout, respostas, índices, NaN e Infinity são bounded ou rejeitados.

## 10. Currentness e fallback

Somente a execução completa do perfil correspondente ao corpus lexical atual
fica current. Corpus lexical novo, profile alterado, erro do provider ou
resposta stale não fabricam contribuição semântica: o híbrido declara o estado
e retorna lexical quando aplicável.

## 11. Fusão híbrida

O híbrido limita os dois conjuntos de candidatos e calcula weighted reciprocal
rank fusion com k configurável. Cada resultado mostra rank e contribuição
lexical/semântica, com desempate determinístico; nenhum score de LLM é usado.

## 12. Dashboard

O Control Center preserva Corpus e Lexical Retrieval Lab e agora mostra estado
semântico, sync de embeddings e seleção Lexical/Semantic/Hybrid. Não há campo
de chave, controle de reranker ou custo fictício.

## 13. Benchmark

O baseline lexical separado permanece com quatro consultas críticas e duas
execuções reproduzíveis. O desafio paraphraseado recupera `src/durability.py`
semanticamente, o híbrido mantém recall@5 igual ou superior ao conjunto lexical
estendido e o fixture é explicitamente mecânico, não uma alegação de qualidade
de produção.

## 14. Testes automatizados

Os testes cobrem configuração desabilitada e bounded, identidade sem segredo,
adapter OpenAI-compatible, ordem por índice, dimensões, duplicatas, NaN,
parameterização SQL, RRF e estados de fallback, além da suíte lexical existente.

## 15. Integrações reais

Compose executa PostgreSQL/pgvector, Redis, API e dashboard contra Git real.
O fluxo valida migration, tipo vector real, sync/reuso, isolamento entre
projetos, challenge semântico, fallback provider/stale, races lexicais,
restart Redis/API e benchmark repetido.

## 16. CI e evidências

`Validate`, `Integration health` e `Review Evidence` são executados no head
exato. O manifesto JSON fica delimitado, o benchmark semântico/híbrido e os
logs bounded entram no artefato `{artifact_name}` junto com diff, migration,
testes, governança e avisos observados.

## 17. Governança GitHub

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. A proteção permanece ativa, sem bypass, com checks reais,
threads resolvidas e squash-only. A única identidade operacional do GitHub é
`KayzenRoot`; executor e Sol continuam papéis lógicos distintos. O fluxo futuro
é `EXECUTOR -> CHECKS -> AWAITING_SOL -> SOL AUDIT -> SOL MERGE AUTHORIZATION ->
MERGE -> PUSH CI -> CHECKPOINT`. O executor encerra com a PR Ready, checks
verdes e auto-merge nativo desarmado. Após `APPROVED`, Sol faz SQUASH direto no
HEAD exato quando a PR estiver limpa/mergeable e todos os checks estiverem
verdes; somente se checks obrigatórios legítimos estiverem pendentes pode armar
auto-merge nativo SQUASH como `KayzenRoot`. HEAD movido, check falho/ausente,
conflito, draft, thread não resolvida, ruleset divergente ou evidência
incompleta bloqueiam merge e auto-merge. O push CI pós-merge deve passar no
novo SHA exato de `main` antes do checkpoint ou do próximo Work Order.

## 18. Limitações e avisos conhecidos

Não há índice aproximado nesta versão: a consulta usa scan exato bounded.
Provider local/fixture serve apenas à prova determinística. Avisos de ambiente
ou dependências permanecem registrados no manifesto sem serem ocultados.

## 19. Arquivos e artefato

A lista completa de arquivos, diff, resultados, benchmark, logs sanitizados e
governança está no artefato `{artifact_name}` e no comentário sticky marcado
por `<!-- hive-review-evidence:{work_order} -->`.

## 20. Estado para revisão de Sol

A PR permanece aberta, Ready e não mesclada. O auto-merge permanece desarmado
antes da auditoria de Sol; nenhuma aprovação ou merge é presumido. Threads e
checks devem ser verificados no HEAD atual antes de qualquer merge.

Sol Review State: AWAITING_SOL
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--ruleset-before", default="captured in the prior audit")
    parser.add_argument("--ruleset-after", default="captured in the final evidence")
    parser.add_argument("--merge-before", default="captured in the prior audit")
    parser.add_argument("--merge-after", default="captured in the final evidence")
    parser.add_argument("--auto-merge-owner-login", default="")
    parser.add_argument("--auto-merge-owner-type", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    body = render_body(
        work_order=args.work_order,
        pr_number=args.pr_number,
        branch=args.branch,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
        artifact_name=args.artifact_name,
        ruleset_before=args.ruleset_before,
        ruleset_after=args.ruleset_after,
        merge_before=args.merge_before,
        merge_after=args.merge_after,
        auto_merge_owner_login=args.auto_merge_owner_login,
        auto_merge_owner_type=args.auto_merge_owner_type,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8", newline="\n")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
