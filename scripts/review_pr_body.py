"""Render the executor review for an auditable pull request."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

EXACT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _require_exact_head(work_order: str, head_sha: str) -> None:
    if work_order in {
        "WO-016-G1",
        "WO-016",
        "WO-016-P-G1",
        "WO-016-P",
        "WO-017-G1",
        "WO-017",
        "WO-017-P-G1",
        "WO-017-P",
        "WO-018-G1",
        "WO-018",
        "WO-018-P-G1",
        "WO-018-P",
        "WO-019-G1",
        "WO-019",
        "WO-019-P-G1",
        "WO-019-P",
        "WO-020-G1",
        "WO-020",
    } and not (EXACT_SHA.fullmatch(head_sha)):
        raise ValueError(
            f"{work_order} dedicated renderer requires a lowercase 40-hex exact HEAD SHA"
        )


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


def _render_wo012p_g1_body(
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

Esta PR é uma correção de governança/tooling para tornar explícito e fail-closed
o suporte do Review Evidence à promoção de checkpoint `WO-012-P`. Não altera
produto, Context Fingerprints, checkpoint canônico, migrations ou comportamento
de execução.

## 2. Identidade e escopo

- PR: #{pr_number}, aberta Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.
- Base G1 registrada: `743253ef079596370a7ff1102faf03b3a603b585`.
- Arquivos permitidos: `scripts/review_evidence.py`, `scripts/review_pr_body.py` e
  `backend/tests/test_review_evidence.py`.
- Arquivos canônicos alterados: nenhum.

## 3. Contratos adicionados

`WO-012-P-G1` é reconhecido e valida sua própria base exata, escopo exclusivo
de tooling/testes e ausência de Project Brain, migrations e código de produto.
`WO-012-P` possui registro explícito, exige um marcador imutável de base
autorizada e ainda compara essa SHA com a base da PR e o `origin/main` protegido
no momento da validação. A promoção futura exige exatamente `13-CHECKPOINT.md`
e `CANONICAL-SHA256SUMS.txt`, valida a transição semântica do checkpoint e
compara o manifesto byte-a-byte salvo pela única nova hash do checkpoint.

O contrato também exige a evidência Context Fingerprints já aprovada para
`WO-012-P`, rejeita hashes inválidos, duplicados, reordenação e alterações
canônicas não autorizadas. Marcadores de promoção desconhecidos, como
`WO-013-P`, falham fechado em vez de cair no fallback genérico.

## 4. Testes e governança

Os testes cobrem bases incorretas, escopo G1, arquivos canônicos incompletos ou
extras, semântica de STATUS/PENDING/IN PROGRESS/NEXT STEP, integridade do
manifesto, reutilização da evidência WO-012 e marcadores de promoção
desconhecidos. Ruleset antes: {ruleset_before}; depois: {ruleset_after}.
Merge antes: {merge_before}; depois: {merge_after}.

## 5. Estado para auditoria de Sol

Migration head permanece `0005_semantic_retrieval`. A proposta local de
`WO-012-P` não foi incluída, nenhum checkpoint foi promovido, nenhum Delta
Context foi implementado e nenhum merge ocorreu. Auto-merge permanece
desarmado; a PR está Ready e aberta.

Evidence Bundle: `{artifact_name}`.

Sol Review State: AWAITING_SOL
"""


def _render_wo012p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor — {work_order}

## 1. Promoção de checkpoint somente

Esta PR promove somente o checkpoint Context Fingerprints já implementado,
aprovado, mesclado e validado no pós-merge. Não implementa Delta Context,
provider/prompt cache, memory lifecycle ou qualquer mudança de produto.

## 2. Identidade exata

- PR: #{pr_number}, aberta Ready for review.
- Branch: `{branch}`.
- Base exata registrada: `{base_sha}`.
- Head exato: `{head_sha}`.
- Arquivos alterados: exatamente `docs/project-brain/13-CHECKPOINT.md` e
  `docs/project-brain/CANONICAL-SHA256SUMS.txt`.

## 3. Contrato validado

O status muda de Adaptive Token Budget para Context Fingerprints Foundation;
somente `context fingerprints.` é removido de PENDING; os demais itens,
histórico, migration `0005_semantic_retrieval` e hashes canônicos permanecem
inalterados. IN PROGRESS e NEXT STEP apontam exclusivamente para a preparação
do menor Delta Context Foundation determinístico. A evidência Context
Fingerprints continua obrigatória, com false hits `0` e critical misses `0`.

## 4. Gates e handoff

Ruleset antes: {ruleset_before}; depois: {ruleset_after}. Merge antes:
{merge_before}; depois: {merge_after}. Validate, Integration health, Review
Evidence, canonical verifier e secret scan devem estar PASS. Auto-merge fica
UNARMED, nenhum merge ocorreu e o executor não promove a verdade canônica fora
desta PR.

Evidence Bundle: `{artifact_name}`.

Sol Review State: AWAITING_SOL
"""


def _render_wo013p_g1_body(
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

## 1. Resumo

Esta PR adiciona somente o suporte fail-closed de Review Evidence necessário
para a futura promoção `WO-013-P`. É uma mudança de governança/tooling; não
promove checkpoint, não altera Project Brain, não altera produto, não altera
migration, não implementa Provider/Prompt Cache ou Memory e não executa merge.

## 2. Identidade e escopo

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.
- Base G1 autorizada: `d952be125da97afacf1099244cf2755f8243d288`.
- Arquivos permitidos: `scripts/review_evidence.py`,
  `backend/tests/test_review_evidence.py` e `scripts/review_pr_body.py`.
- Arquivos do Project Brain alterados: nenhum.

## 3. Governança adicionada

`WO-012-P-G1` e `WO-012-P` permanecem disponíveis somente para compatibilidade
histórica. Os únicos IDs de promoção Delta ativos são `WO-013-P-G1` e
`WO-013-P`; `WO-011-P` e `WO-014-P` falham fechado para novos PRs.

`WO-013-P-G1` valida a própria base exata e o escopo exclusivo de tooling/testes.
`WO-013-P` exige exatamente `13-CHECKPOINT.md` e
`CANONICAL-SHA256SUMS.txt`, marcador autorizado único e lowercase, base igual à
PR e ao `origin/main`, transição fechada do checkpoint, cinco bullets Delta e
manifesto canônico com somente a hash do checkpoint alterada.

## 4. Reuso da evidência WO-013

A promoção futura continua exigindo o benchmark Delta PASS, reconstrução exata,
zero false reconstructions, zero critical context misses, corridas pós-build
fail-closed, estabilidade final, baseline not-smaller, byte bound, contrato de
estimativa final, regressão do falso positivo de metadata, economia de tokens
truthful, migration inalterada e Provider/Prompt Cache, Memory e autonomous
dispatch não implementados.

## 5. Estado para auditoria

Ruleset antes: {ruleset_before}; depois: {ruleset_after}. Merge antes:
{merge_before}; depois: {merge_after}. Checks exigidos permanecem Validate,
Integration health e Review Evidence; squash-only, zero bypass e zero
aprovações nativas obrigatórias permanecem preservados.

Auto-merge: UNARMED. Nenhum checkpoint foi promovido e nenhum merge foi
executado. Evidence Bundle: `{artifact_name}`.

Sol Review State: AWAITING_SOL
"""


def _render_wo014p_g1_body(
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

## 1. Resumo

Esta PR adiciona somente o suporte fail-closed de Review Evidence e do renderer
necessário para a futura promoção `WO-014-P`. É governança/tooling: não altera
Project Brain, produto, migration, checkpoint canônico ou Memory.

## 2. Identidade e escopo

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.
- Base G1 autorizada: `13888d63572db0e90fb4536369867d995a9e1c90`.
- Arquivos permitidos: `scripts/review_evidence.py`,
  `backend/tests/test_review_evidence.py` e `scripts/review_pr_body.py`.
- Arquivos do Project Brain alterados: nenhum.

## 3. Governança registrada

`WO-014-P-G1` é o work order atual de suporte e se valida contra sua base
exata. `WO-013-P-G1` e `WO-013-P` permanecem legíveis para artefatos
históricos, mas não autorizam PRs atuais. Os únicos IDs de promoção ativos são
`WO-014-P-G1` e `WO-014-P`; IDs desconhecidos, inclusive `WO-015-P`, falham
fechado.

O futuro `WO-014-P` exigirá exatamente um marcador de work order e um marcador
`HIVE-AUTHORIZED-BASE` lowercase, igual à base da PR e ao `origin/main` atual,
além de exatamente `13-CHECKPOINT.md` e `CANONICAL-SHA256SUMS.txt`. A semântica
do checkpoint, o manifesto de uma única linha de hash e a evidência objetiva de
Provider/Prompt Cache são contratos fechados; nenhuma conclusão é inferida por
LLM.

## 4. Gates e estado

Ruleset antes: {ruleset_before}; depois: {ruleset_after}. Merge antes:
{merge_before}; depois: {merge_after}. Migration permanece
`0005_semantic_retrieval`; auto-merge permanece UNARMED; não houve promoção de
checkpoint, implementação de Memory, merge ou release.

Evidence Bundle: `{artifact_name}`.

Sol Review State: AWAITING_SOL

WO-014-P-G1 READY FOR SOL AUDIT
"""


def _render_wo014p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor — {work_order}

## 1. Promoção de checkpoint somente

Esta PR futura promove somente o checkpoint Provider/Prompt Cache Adapter já
aprovado, merged e validado no pós-merge. Exige exatamente os dois arquivos
canônicos `docs/project-brain/13-CHECKPOINT.md` e
`docs/project-brain/CANONICAL-SHA256SUMS.txt`; não implementa Memory, produto
novo, migration ou alteração de configuração.

## 2. Identidade e base autorizada

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata em runtime: `{base_sha}`.
- Head exato: `{head_sha}`.
- O marcador `HIVE-AUTHORIZED-BASE` é único, lowercase e emitido a partir da
  base fornecida pelo handoff; não há SHA futura hard-coded no renderer.
- A validação exige `marker == PR base == current origin/main` e base branch
  `main`, com suporte G1 já presente na base.

## 3. Transição canônica fechada

O STATUS muda exatamente de `DELTA CONTEXT FOUNDATION APPROVED / V0.1
IMPLEMENTATION ACTIVE` para `PROVIDER / PROMPT CACHE ADAPTER FOUNDATION
APPROVED / V0.1 IMPLEMENTATION ACTIVE`. O prefixo COMPLETED histórico é
preservado e recebe exatamente cinco bullets Provider/Prompt Cache. Somente
`provider/prompt cache adapter layer.` é removido de PENDING; Memory permanece
pendente e o próximo passo é Memory Lifecycle and Provenance Foundation.

## 4. Gates

Review Evidence exige a evidência objetiva atual de Provider/Prompt Cache,
manifesto com somente a hash do checkpoint alterada, migration
`0005_semantic_retrieval`, canonical verifier e secret scan PASS, Ruleset
inalterado, checks Validate/Integration health/Review Evidence PASS, threads
resolvidas, squash-only e auto-merge UNARMED.

Ruleset antes: {ruleset_before}; depois: {ruleset_after}. Merge antes:
{merge_before}; depois: {merge_after}. Nenhum merge é presumido neste body.

Evidence Bundle: `{artifact_name}`.

Sol Review State: AWAITING_SOL
"""


def _render_wo013p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor — {work_order}

## 1. Promoção de checkpoint somente

Esta PR futura promove somente o checkpoint Delta Context já aprovado, merged e
validado no pós-merge. Exige exatamente os dois arquivos canônicos
`docs/project-brain/13-CHECKPOINT.md` e
`docs/project-brain/CANONICAL-SHA256SUMS.txt`. Não implementa Provider/Prompt
Cache, Memory, produto novo ou migration.

## 2. Identidade e contrato

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata autorizada: `{base_sha}`.
- Head exato: `{head_sha}`.
- O marcador `HIVE-AUTHORIZED-BASE` é único, lowercase e igual à base da PR e
  ao `main` protegido no momento da validação.
- Auto-merge permanece UNARMED; nenhum merge é presumido neste body.

## 3. Transição canônica fechada

O STATUS muda exatamente de `CONTEXT FINGERPRINTS FOUNDATION APPROVED /
V0.1 IMPLEMENTATION ACTIVE` para `DELTA CONTEXT FOUNDATION APPROVED / V0.1
IMPLEMENTATION ACTIVE`. Somente `delta context.` é removido de PENDING.
IN PROGRESS e NEXT STEP apontam exclusivamente para a preparação do menor
Provider/Prompt Cache Adapter Foundation provider-independent, mantendo cache
de provider não canônico, identidade HIVE determinística, accounting medido,
sem Memory lifecycle, MCP product surface, autonomous dispatch, telemetry
ampla ou user-managed cache mode.

## 4. Evidência COMPLETED

O prefixo COMPLETED histórico permanece byte/order-preserved e recebe exactly five bullets
Delta com gramática fechada: versões/arquitetura, baseline/safety,
correção, token/bounds truthfulness e traceabilidade/later-work non-completion.

## 5. Gates

Review Evidence exige a evidência WO-013 existente no candidate HEAD, manifesto
com somente a hash do checkpoint alterada, canonical verifier PASS, secret scan
PASS, migration `0005_semantic_retrieval`, Ruleset 21934284 unchanged, checks
Validate/Integration health/Review Evidence PASS, backend e dashboard verdes,
threads resolvidas, squash-only, zero bypass e zero aprovações nativas.

Evidence Bundle: `{artifact_name}`.

Sol Review State: AWAITING_SOL
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


def _render_wo013_body(
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

## 1. Resumo

Esta PR adiciona a fundação determinística de Delta Context sobre o Context
Manager atual. O alvo completo continua sendo montado pelo pipeline aprovado;
somente depois o sistema calcula um patch JSON determinístico contra um
baseline HIVE validado e entrega `DELTA` quando a reconstrução é exata e
estritamente menor. Caso contrário, retorna o capsule completo atual em
`FULL` com motivo bounded.

## 2. Base, branch, head e PR

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.
- Base autorizada do WO-013: `8aabcf1d7e908b7f74333d2b3bb937af0f39c4c8`.

## 3. Contrato

O endpoint aditivo é `POST /api/v1/projects/{{project_id}}/tasks/{{task_id}}/context/delta`.
O request referencia um baseline somente por `baseline_output_fingerprint`.
O response usa `context-delivery-v1`, policy `delta-context-v1` e patch
`delta-json-patch-v1`; o seam semântico continua sendo `context-output-v2`.
`DELTA` contém somente operações `add`, `remove` e `replace`, com arrays
substituídos integralmente quando mudam, reconstrução local e fingerprint do
alvo verificados. `FULL` contém o capsule atual e motivo de fallback.

## 4. Baseline e segurança

Somente capsules válidos, completos, cacheáveis e com output fingerprint
verificado são apontados. O ponteiro é Redis project/task-scoped, bounded,
versionado e TTL 300 segundos; Redis permanece HOT noncanonical e aponta para
o cache Context Fingerprint existente. Baselines de HEAD antigo são aceitos
sem declarar aquele source como current. Mismatch, corrupção, expiração,
cross-project, cross-task, Redis loss, patch bounds ou delta não menor falham
fechado para `FULL`. Nenhum texto bruto de task, segredo ou run ID antigo é
usado como identidade semântica.

## 5. Ordem e estabilidade

O caminho Delta chama o Context Manager atual primeiro e preserva checkpoint,
governança obrigatória, retrieval/rerank, Progressive Disclosure, Adaptive
Token Budget, source/Git checks e Context Fingerprints. Há rechecagem de
source/index/corpus/task imediatamente antes da entrega e o race controlado
falha fechado; provenance operacional corrente fica separada do delta semântico.

## 6. Evidência

O integration harness Docker valida os cenários A–K: identical, small change,
new dependency, large/full fallback, missing baseline, Redis loss, API restart,
cross-project, cross-task, corrupt baseline e source race. O Evidence Bundle
registra token estimates before/after, operações, patch size, avoided tokens,
reconstruction, target fingerprint, zero false reconstructions, zero critical
misses, zero LLM/provider calls e migration unchanged.

## 7. Testes e compatibilidade

O endpoint Context Capsule existente, modelo, fingerprints, disclosure,
adaptive budget, retrieval/rerank e L4 permanecem cobertos. Não há migration,
provider prompt cache, memory lifecycle, executor dispatch, mudança canônica,
refatoração ampla, dashboard não relacionado ou cleanup amplo.

## 8. Governança GitHub

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. Ruleset permanece inalterado, checks reais e squash-only. O
auto-merge fica desarmado; o executor não aprova, não promove checkpoint e não
faz merge.

## 9. Evidence Bundle e estado

O consolidado é `{artifact_name}` e o comentário sticky usa
`<!-- hive-review-evidence:{{work_order}} -->`. A PR permanece aberta, Ready e
não mesclada. Sol Review State: AWAITING_SOL.

WO-013 READY FOR SOL AUDIT
"""


def _render_wo014_body(
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

## 1. Resumo

Esta PR adiciona a menor fundação provider-independent de Provider/Prompt Cache
sobre o Context Manager, Progressive Disclosure, Adaptive Token Budget, Context
Fingerprints e Delta Context existentes. O contrato prepara envelope, identidade
de prefixo estável, capabilities, adapter, receipt de uso e accounting; não faz
rede de provider e não declara hit sem receipt final reconciliado.

## 2. Base, branch, head e PR

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.
- Base autorizada do WO-014: `d025cfa6dc306fff0f5664002fef970a438ad266`.

## 3. Contrato implementado

O endpoint aditivo é `POST /api/v1/projects/{{project_id}}/tasks/{{task_id}}/`
`context/provider-prompt`.
O envelope usa `provider-prompt-envelope-v1` e compõe prefixo estável e sufixo
dinâmico por serialização canônica, verificando a igualdade semântica antes de
qualquer metadata de provider. Identidades são SHA-256, project-scoped e não
contêm credenciais, timestamps, request IDs ou contadores.

Capabilities, adapter policy, usage receipt e accounting são versionados. O
adapter no-op é explícito e nunca declara requested, eligible ou hit. Fixtures
determinísticas cobrem automatic/explicit, hit positivo, zero conhecido,
unknown e accounting inválido fail-closed. Estimativas HIVE são rotuladas e não
substituem usage reportado pelo provider.

## 4. Evidência

O benchmark A-K usa canonical input independente `provider-canonical-input-v1`,
cinco mutações negativas (omissão, duplicação, reorder, mutação estável e mutação
dinâmica), fixture de invalidação real de capability/provider, rotação de duas
credenciais externas à identidade material, no-op, isolamento cross-project,
requested/eligible sem receipt, zero explícito, prefixo repetido sem receipt,
hit positivo, matriz de accounting inválido e composição FULL/DELTA medida. A
integração Docker chama os endpoints FULL e DELTA reais e verifica a fingerprint
de saída corrente/target.
Não há LLM calls, provider calls, rede de provider, migration ou cache local de
conteúdo de prompt.

## 5. Fora de escopo

Não foram implementados live provider transport, semantic response cache,
memory lifecycle, MCP, autonomous executor dispatch, full cache telemetry,
cost accounting, migration, alteração canônica, checkpoint promotion, release,
merge ou cleanup amplo.

## 6. Compatibilidade e governança

Os endpoints `/context` e `/context/delta`, seus fingerprints, budget, disclosure,
retrieval/rerank e contratos existentes permanecem preservados. Antes: {ruleset_before};
merge: {merge_before}. Depois: {ruleset_after}; merge: {merge_after}. Ruleset e
checks protegidos permanecem inalterados; auto-merge fica desarmado e o executor
não aprova, promove checkpoint ou faz merge.

## 7. Evidence Bundle e estado

O consolidado é `{artifact_name}` e o comentário sticky usa
`<!-- hive-review-evidence:{work_order} -->`. A PR permanece aberta, Ready e
não mesclada. Sol Review State: AWAITING_SOL.

WO-014 READY FOR SOL AUDIT
"""


def _render_wo016_g1_body(
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

## 1. Objetivo

Esta PR habilita exclusivamente o contrato de Review Evidence e o renderer
dedicado necessários ao futuro WO-016 — ACCE Storage Tier & Compression Policy
Foundation. Nenhum comportamento de produto ACCE é implementado nesta G1.

## 2. Identidade exata

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base autorizada exata: `5121316c1a577557039f03770ff7031be74d3e0b`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.

## 3. Escopo fechado

Os únicos arquivos permitidos são `backend/tests/test_review_evidence.py`,
`schemas/review-evidence-v1.schema.json`, `scripts/review_evidence.py` e
`scripts/review_pr_body.py`. Project Brain, checkpoint, migrations e todas as
superfícies de produto permanecem inalterados; o migration head esperado é
`0006_memory_lifecycle_provenance`.

## 4. Registro fail-closed do futuro WO-016

`WO-016` possui registro explícito, exige base `main` protegida e renderer
dedicado. O futuro contrato `acce-storage-policy-v1`, em
`acce-storage-policy.json`, exigirá política HOT/WARM/COLD, seleção interna
determinística, matriz Zstd medida, identidade SHA-256/CAS, deduplicação,
lossless round-trip, corrupção fail-closed, atomicidade, medições lógicas e
físicas, durabilidade após restart/Redis loss e zero perda canônica/chamadas
LLM/provider. Evidência ausente, malformada ou inconsistente falha fechado.

## 5. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. O ruleset permanece inalterado e
auto-merge permanece UNARMED; nenhum merge, release ou promoção canônica é
executado.

## 6. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-016-G1 READY FOR SOL AUDIT
"""


def _render_wo016_body(
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

## 1. Objetivo e limites

Esta PR implementa somente a fundação ACCE Storage Tier & Compression Policy
autorizada pelo Work Order. Não há refatoração ampla, limpeza geral, novo MCP,
telemetria, Control Center, execução autônoma, tool gating ou promoção de
checkpoint nesta entrega.

## 2. Identidade e Evidence Bundle

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base protegida exata: `{base_sha}`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.
- Migration head observado: deve ser explicitamente reportado no bundle.

## 3. Evidência obrigatória

O renderer não substitui evidência por narrativa. O contrato versionado
`acce-storage-policy-v1` deve estar PASS em `acce-storage-policy.json` e
reportar política HOT/WARM/COLD interna, perfis/níveis Zstd medidos e dentro
do range suportado, round-trip lossless com identidade SHA-256 preservada,
identidade CAS única e deduplicação entre tiers, corrupção/truncamento
fail-closed, replacement atômico, bytes lógicos/físicos e métricas truthful
inclusive expansão, restart persistence, Redis não canônico e zero perda de
fonte canônica.

A matriz deve conter perfil, nível, bytes lógicos/físicos, ratio, savings,
expansão, amostras bounded, medição repetida e justificativa derivada dos
resultados medidos. O bundle também registra LLM/provider calls, testes,
lint, typecheck, build, CI, ruleset, threads, auto-merge e estado de Sol.

## 4. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED;
nenhum merge/release é executado e Sol audita o HEAD exato.

## 5. Estado final

A PR permanece aberta e Ready. Sol Review State: AWAITING_SOL.

WO-016 READY FOR SOL AUDIT
"""


def _render_wo017_g1_body(
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

## 1. Objetivo

Esta PR habilita exclusivamente o suporte determinístico de Review Evidence e
renderer necessário ao futuro `WO-017` — MCP Server product surface. Esta G1
não implementa MCP, não inicia servidor, não executa transporte e não adiciona
qualquer comportamento de produto.

## 2. Identidade exata

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base protegida autorizada exata: `bb7db2cc8b4850c472e7e567e1991c6cbf36dd4c`.
- Base informada: `{base_sha}`.
- HEAD exato desta revisão: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.

## 3. Escopo G1 fechado

Os únicos quatro arquivos permitidos são `backend/tests/test_review_evidence.py`,
`schemas/review-evidence-v1.schema.json`, `scripts/review_evidence.py` e
`scripts/review_pr_body.py`. Project Brain, checkpoint, migrations, produto MCP,
`requirements.txt`, Docker, CI, `.env.example` e atlas permanecem intocados.
O migration head observado e exigido é `0006_memory_lifecycle_provenance`.

## 4. Registro explícito do futuro WO-017

`WO-017` fica registrado como a próxima superfície de produto limitada. Seu
limite superior de arquivos é `requirements.txt`,
`backend/app/mcp_server.py`, `backend/tests/test_mcp_server.py`,
`backend/app/config.py` somente para binding local, `backend/app/main.py`
somente para transporte MCP padrão montado na API, `docker-compose.yml`
somente se um serviço MCP local separado for necessário, `.env.example`
somente para configuração MCP local bounded, `scripts/mcp_integration.py`,
`.github/workflows/ci.yml` somente para evidência MCP real,
`docs/atlas/code-atlas.md` e `docs/atlas/test-map.md`.

O primeiro catálogo read-only exato é `project.list`, `project.status`,
`context.build`, `context.search`, `memory.search`, `memory.get` e
`checkpoint.read`. Nenhum tool de escrita canônica, mutation, run, validation,
telemetria, execução autônoma, tool gating ou Control Center é registrado.

## 5. Contrato de evidência versionado

O contrato futuro usa exatamente `mcp-core-surface-v1` em
`mcp-surface.json`. O schema continua fechado com `additionalProperties: false`
e exige esse bloco somente para `WO-017`; evidência ausente, forjada,
incompleta, com versão errada, tool faltante/excedente ou escrita exposta falha
closed. O bundle futuro deverá provar handshake `initialize`, listagem e
invocação de cada tool pelo transporte MCP padrão local em serviços reais;
handler direto, REST loopback, teste unitário isolado ou narrativa não contam.

## 6. Guardas arquiteturais e de segurança

O adapter futuro deverá chamar o Core diretamente, sem persistência duplicada,
com PostgreSQL como verdade canônica e Redis não canônico. Isolamento por
projeto, checkpoint primeiro, contexto/search/memory/checkpoint corretos,
argumentos inválidos e tool desconhecido fail-closed, saída bounded, erros
estruturados sem segredos/caminhos absolutos, restart e Redis loss recovery
serão obrigatórios. Migration permanece inalterada e chamadas MCP a LLM/provider
devem ser `0/0`.

## 7. Governança e estado

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. O auto-merge permanece UNARMED;
nenhum merge, release, promoção canônica ou início de `WO-017` é executado.

Há testes negativos para base/branch/escopo, Project Brain, migration, produto,
CI/dependência e contrato MCP, além das regressões históricas de Review Evidence.
A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-017-G1 READY FOR SOL AUDIT
"""


def _render_wo017_body(
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

## 1. Escopo de produto MCP fechado

Esta PR futura implementa somente o primeiro MCP Server read-only sobre o Core
existente. O catálogo exato é: `project.list`, `project.status`, `context.build`,
`context.search`, `memory.search`, `memory.get` e `checkpoint.read`. Não inclui
tools de escrita, mutation, run/validation, telemetry, execução autônoma, tool
gating, Control Center ou claims de conclusão V0.1.

## 2. Identidade e limites

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base protegida exata: `{base_sha}`.
- HEAD exato desta revisão: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.
- Migration head: `0006_memory_lifecycle_provenance`, sem migration alterada.

Os arquivos ficam limitados a `requirements.txt`,
`backend/app/mcp_server.py`, `backend/tests/test_mcp_server.py`,
`backend/app/config.py` somente para binding local, `backend/app/main.py`
somente para transporte padrão montado na API, `docker-compose.yml` somente
para serviço MCP local genuinamente necessário, `.env.example` somente para
configuração local, `scripts/mcp_integration.py`, CI somente para evidência
MCP real e os dois mapas Atlas.

## 3. Protocolo e evidência observada

O contrato `mcp-core-surface-v1` é gravado em `mcp-surface.json`. PASS exige
serviços reais, transporte local padrão, `initialize`/handshake, list tools e
invocação MCP de cada uma das sete tools, com verificação da verdade do Core.
Também exige casos reais de argumentos inválidos, tool desconhecido,
isolamento entre projetos, restart e Redis loss. Handler direto, REST loopback,
teste unitário único ou lista declarada não são evidência suficiente.

## 4. Reuso do Core e segurança

O adapter chama Registry, Context Manager, Retrieval e Memory diretamente, sem
duplicar persistência ou regra de negócio; PostgreSQL continua canônico e Redis
continua não canônico. `project.list`/`project.status` respeitam identidade do
Registry; `context.build` mantém checkpoint primeiro; search e Memory permanecem
project-scoped; `checkpoint.read` só lê o checkpoint do projeto correto.
O bundle registra `registered_project_count >= 2` para provar dois ou mais
projetos registrados, e `arbitrary_filesystem_access_rejected=true` para provar
que tentativas de escape por caminho falham closed. `checkpoint.read` também
prova `checkpoint_missing_fail_closed=true`,
`checkpoint_untracked_fail_closed=true`, `checkpoint_stale_fail_closed=true` e
`checkpoint_hive_substitution_absent=true`, sem substituir silenciosamente pelo
checkpoint do HIVE. `context.search` exige
`context_search_provenance_preserved=true` e
`context_search_result_bound_enforced=true`; Memory exige
`memory_search_provenance_preserved=true`,
`memory_get_provenance_preserved=true` e
`memory_status_visibility_preserved=true`. Argumentos inválidos e tools
desconhecidas falham closed. Outputs e erros são bounded, estruturados, sem
segredos, sem caminhos absolutos e sem acesso a filesystem arbitrário; o
contrato exige `structured_errors_enforced=true` e
`bounded_errors_enforced=true`.

## 5. Controles e recuperação

O bundle exige isolamento positivo e rejeição cross-project, repetição
determinística, restart recovery e Redis loss recovery. Não há tools de escrita
canônica; `canonical_write_tools_exposed=false`, `mcp_llm_calls=0`,
`mcp_provider_calls=0`, `secret_leaks=0` e `filesystem_path_leaks=0`.

## 6. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED;
nenhum merge, release ou promoção de checkpoint é executado nesta etapa.

A PR permanece aberta, Ready e não mesclada para auditoria do HEAD exato.
Sol Review State: AWAITING_SOL.

WO-017 READY FOR SOL AUDIT
"""


def _render_wo018_g1_body(
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

# Revisão do executor - {work_order}

## 1. Objetivo

Esta PR habilita exclusivamente Review Evidence e renderer para o futuro
WO-018 Autonomous Execution Foundation. Esta G1 nao implementa orquestrador,
nao despacha executor e nao altera produto.

## 2. Identidade exata

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base autorizada exata: 5e699f1315638a4e767a94bcf6536cd52988ee3b.
- Base informada: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 3. Escopo G1 fechado

Exatamente quatro arquivos: backend/tests/test_review_evidence.py,
schemas/review-evidence-v1.schema.json, scripts/review_evidence.py e
scripts/review_pr_body.py. Project Brain, checkpoint, migrations, produto,
CI de produto, runner, Context Manager, MCP, dashboard e telemetria permanecem
intocados. Migration head: 0006_memory_lifecycle_provenance.

## 4. Contrato futuro WO-018

WO-018 fica registrado explicitamente com escopo bounded para uma fundacao
provider-independent de Execution Orchestrator sobre Context Manager e Local
Verified Runner existentes. O verifier exige autonomous-execution-v1 em
autonomous-execution.json.

PASS futuro exige reuso do Context Manager, checkpoint-first, Local Verified
Runner e ToolPolicy, tool subset gating, rejeicao de tool nao autorizada e
shell bypass, saida estruturada/staged nao canonica, captura de files/diff/
tests/validation/review, isolamento project/task, rejeicao de escrita Project
Brain, rejeicao de HEAD race, uma tarefa coding end-to-end, zero secret/path
leaks e nenhuma acao commit/push/merge/checkpoint.

## 5. Governanca

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED.
Nenhum merge, release, checkpoint ou inicio de WO-018 e executado.

A PR permanece aberta, Ready e nao mesclada. Sol Review State: AWAITING_SOL.

WO-018-G1 READY FOR SOL AUDIT
"""


def _render_wo018_body(
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

# Revisão do executor - {work_order}

## 1. Escopo de produto Autonomous Execution fechado

Esta PR futura implementa somente a menor fundacao necessaria de execucao
autonoma provider-independent sobre capacidades HIVE existentes. Nao inclui
telemetria ampla, Control Center, migrations, checkpoint promotion, backup,
release ou claims de conclusao V0.1.

## 2. Identidade

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.
- Migration head: 0006_memory_lifecycle_provenance.

## 3. Evidencia obrigatoria

O contrato autonomous-execution-v1 prova Execution Orchestrator real,
ExecutorAdapter provider-independent, identidade project/task scoped, Context
Manager e Local Verified Runner reutilizados, ToolPolicy e tool gating,
rejeicoes fail-closed, saida staged/noncanonical, captura de diff/tests/
validation/review e uma pequena tarefa coding end-to-end.

A fundacao nao executa commit, push, merge ou promocao de checkpoint.
Secret/path leaks permanecem 0.

## 4. Governanca

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED.
Sol audita o HEAD exato antes de qualquer merge.

WO-018 READY FOR SOL AUDIT
"""


def _render_wo019_g1_body(
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

# Revisão do executor - {work_order}

## 1. Objetivo

Esta PR habilita exclusivamente o Review Evidence necessário para o futuro
WO-019 Telemetry/Event Bus Foundation. Não implementa código de telemetria,
event table, stream, dashboard, instrumentação ou produto WO-019.

## 2. Identidade exata

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida exata: 62c51d982afe47d93aa40dee3d55b479e6d756e5.
- Base informada: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 3. Escopo G1 fechado

Exatamente quatro arquivos de governança: o verificador Review Evidence, o
renderer do corpo da PR, o schema de evidência e seus testes determinísticos.
Project Brain, checkpoint, migrations, backend product modules, dashboard,
dependências e CI permanecem intocados. A migration head permanece
`0006_memory_lifecycle_provenance`.

## 4. Contrato futuro separado

O produto futuro é registrado como `WO-019`, separado de `WO-019-G1`, com o
contrato versionado `telemetry-event-bus-v1`. A validação exige PostgreSQL
como verdade durável, Redis não canônico, isolamento por projeto, envelope e
proveniência explícitos, replay ordenado bounded, stream near-real-time,
reconnect/replay, resiliência, payload sanitizado, zero leaks e zero chamadas
LLM/provider. O subconjunto de eventos implementado deve ser explícito e
pertencer ao vocabulário canônico; G1 não satisfaz evidência de produto.

## 5. Fail closed e bounds

Campos ausentes, extras, versão/tipo incorretos, payload ou cursor sem bounds,
eventos fora do vocabulário, claims de observabilidade completa, cross-project
leaks, secret/path leaks, migration truth inconsistente ou chamadas LLM/provider
não passam. O renderer não inclui segredos nem caminhos locais absolutos.

## 6. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED.
Não houve merge, release, promoção de checkpoint ou início do WO-019.

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-019-G1 READY FOR SOL AUDIT
"""


def _render_wo019_body(
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

# Revisão do executor - {work_order}

## 1. Escopo de produto

Esta PR futura implementa somente a menor fundação Telemetry/Event Bus
necessária para HIVE. A verdade durável permanece em PostgreSQL; Redis é
apenas hot/streaming não canônico. Eventos são project-scoped, vinculados a
task/run quando disponível, bounded, versionados, sanitizados e provenance-
preserving.

## 2. Evidência obrigatória

O contrato `telemetry-event-bus-v1` exige um subconjunto não vazio e explícito
do vocabulário canônico, replay determinístico com cursor bounded, stream
server near-real-time com acesso fail-closed, reconnect/replay, recuperação
após restart e Redis loss, producer slice real, zero duplicação canônica,
zero cross-project/secret/path leaks e zero chamadas LLM/provider. Claims de
Control Center completo, charts/alerts completos e observabilidade V0.1 total
não são aceitos por esta fundação.

## 3. Identidade

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 4. Migration truth e governança

`observed_migration_head` deve corresponder à execução e
`migration_changed` deve refletir exatamente o delta a partir de
`0006_memory_lifecycle_provenance`. Não há checkpoint promotion neste Work
Order. Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge
antes: {merge_before}. Merge depois: {merge_after}. Auto-merge permanece
UNARMED antes da auditoria de Sol.

## 5. Estado para revisão

A PR permanece aberta, Ready e não mesclada. O executor não faz merge, não
arma auto-merge e não trata a evidência G1 como evidência do produto.

WO-019 READY FOR SOL AUDIT
"""


def _render_wo020_g1_body(
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

# Revisão do executor - {work_order}

## 1. Objetivo

Esta PR habilita exclusivamente o Review Evidence necessário para o futuro
WO-020 Control Center operational core. Não implementa dashboard, backend API
de Control Center, stream SSE/WebSocket, surfaces operacionais ou produto
WO-020.

## 2. Identidade exata

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida exata: ab2c6eac4eedac460871cf00d613a9b478ec533d.
- Base informada: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 3. Escopo G1 fechado

Exatamente quatro arquivos de governança: o verificador Review Evidence, o
renderer do corpo da PR, o schema de evidência e seus testes determinísticos.
Project Brain, checkpoint, migrations, backend product modules, dashboard,
dependências e CI permanecem intocados. A migration head permanece
`0007_telemetry_events`.

## 4. Contrato futuro separado

O produto futuro é registrado como `WO-020`, separado de `WO-020-G1`, com o
contrato versionado `control-center-core-v1`. A validação exige PostgreSQL
canônico, Redis não canônico, fleet/detail/run surfaces bounded, timeline
near-real-time, stream SSE ou WebSocket com replay e reconciliação, health e
test status visíveis, métricas estimadas etiquetadas, zero leaks e zero chamadas
LLM/provider. Claims de Control Center completo e V0.1 total são rejeitadas;
G1 não satisfaz evidência de produto.

## 5. Fail closed e bounds

Campos ausentes, extras, versão/tipo incorretos, surfaces fora do vocabulário,
paths absolutos, claims de observabilidade completa, cross-project/secret/path
leaks, migration truth inconsistente ou chamadas LLM/provider não passam. O
renderer não inclui segredos nem caminhos locais absolutos.

## 6. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED.
Não houve merge, release, promoção de checkpoint ou início do WO-020.

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-020-G1 READY FOR SOL AUDIT
"""


def _render_wo020_body(
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

# Revisão do executor - {work_order}

## 1. Escopo de produto

Esta PR futura implementa somente o menor núcleo operacional do HIVE Control
Center necessário para V0.1. A verdade durável permanece em PostgreSQL; Redis
é apenas hot/streaming não canônico. Surfaces são project-scoped, bounded,
sanitizadas e fail-closed.

## 2. Evidência obrigatória

O contrato `control-center-core-v1` exige um subconjunto não vazio e explícito
das surfaces canônicas, stream near-real-time SSE ou WebSocket com replay e
reconciliação de cliente, health/test/errors visíveis, métricas estimadas
etiquetadas e indisponíveis não fabricadas, recuperação após restart e perda
de Redis, zero cross-project/secret/path leaks e zero chamadas LLM/provider.
Claims de Control Center completo e conclusão V0.1 não são aceitos por este
incremento operacional.

## 3. Identidade

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 4. Migration truth e governança

`observed_migration_head` deve corresponder à execução e `migration_changed`
deve refletir exatamente o delta a partir de `0007_telemetry_events`. Não há
checkpoint promotion neste Work Order. Ruleset antes: {ruleset_before}. Ruleset
depois: {ruleset_after}. Merge antes: {merge_before}. Merge depois:
{merge_after}. Auto-merge permanece UNARMED antes da auditoria de Sol.

## 5. Estado para revisão

A PR permanece aberta, Ready e não mesclada. O executor não faz merge, não arma
auto-merge e não trata a evidência G1 como evidência do produto.

WO-020 READY FOR SOL AUDIT
"""


def _render_wo015_g1_body(
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

## 1. Objetivo

Esta PR habilita exclusivamente o contrato de Review Evidence e o renderer de
PR necessários para o futuro WO-015 de Memory Lifecycle and Provenance.

## 2. Base, branch e head

- PR: #{pr_number}, aberta como Ready for review.
- Branch: `{branch}`.
- Base semântica exata: `{base_sha}`.
- HEAD exato desta revisão: `{head_sha}`.

## 3. Escopo G1

O verificador reconhece explicitamente `WO-015-G1`, exige a base autorizada e
rejeita qualquer arquivo fora do conjunto de governança/evidência autorizado.
Project Brain, checkpoint, migrations e código de produto permanecem fora da
alteração.

## 4. Registro do futuro WO-015

`WO-015` agora possui registro explícito, escopo fail-closed para PR de produto
contra `main` e renderer dedicado. IDs desconhecidos não herdam semântica de
Memory.

## 5. Contrato de evidência Memory

O contrato versionado `memory-lifecycle-provenance-v1` exige evidência bounded
para PostgreSQL durável, Redis não canônico, isolamento project-scoped,
proveniência, saída de modelo staged, promoção canônica qualificada, rejeição
de promoção inválida, histórico/supersession, restart, perda de Redis,
segredos e consistência de migration. Faltas, tipos inválidos ou contagens não
computadas falham fechado.

## 6. Testes e regressão

Há testes de escopo G1, registro explícito, seleção de renderer, contrato de
evidência Memory completo/incompleto, rejeições de promoção inválida e
work-order desconhecido, além da regressão de WO-014 e WO-014-P.

## 7. Negativo explícito

Esta PR não implementa Memory, não cria migration/tabela/API, não altera
Project Brain, não promove checkpoint, não altera ruleset e não executa
merge/release.

## 8. Governança GitHub

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. O auto-merge permanece UNARMED;
merge SQUASH e auditoria de Sol continuam obrigatórios.

## 9. Artefato

O Evidence Bundle bounded é `{artifact_name}` e fica vinculado ao HEAD exato.

## 10. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-015-G1 READY FOR SOL AUDIT
"""


def _render_wo015p_g1_body(
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

## 1. Objetivo e limite

Esta PR habilita exclusivamente o suporte determinístico de Review Evidence e
renderer para a futura promoção do checkpoint Memory Lifecycle and Provenance.
Não promove o checkpoint e não inicia o WO-015-P.

## 2. Identidade exata

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base autorizada exata: `2c701d221e481913d2cbe9c0b8f3504632042306`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.

## 3. Escopo fechado

Arquivos G1 permitidos: `backend/tests/test_review_evidence.py`,
`scripts/review_evidence.py` e `scripts/review_pr_body.py`. Project Brain,
checkpoint, migrations, produto, MCP, telemetria, Control Center e execução
autônoma permanecem intocados.

O futuro `WO-015-P` fica registrado como o único próximo promotion work order
ativo. Ele exige exatamente `13-CHECKPOINT.md` e
`CANONICAL-SHA256SUMS.txt`, com marcador de base autorizado, base `main`
atual, sem mudança de manifest além do hash do checkpoint e sem IDs
desconhecidos herdarem semântica.

## 4. Contratos fechados

O renderer e o verificador exigem status Memory exato, prefixo histórico de
COMPLETED, remoção somente de `memory.` em PENDING, próximo passo limitado a
ACCE além das fundações atuais e o gate versionado de evidência Memory. O gate
exige migration `0006_memory_lifecycle_provenance`, PostgreSQL durável,
Redis não canônico, isolamento, proveniência, corridas source/ADR/HEAD,
atomicidade, restart/Redis-loss e zero chamadas LLM/provider.

## 5. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED;
nenhum merge/release é executado e Sol continua obrigatório.

## 6. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-015-P-G1 READY FOR SOL AUDIT
"""


def _render_wo015p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor — {work_order}

## 1. Promoção Memory fechada

Esta PR promove somente o checkpoint Memory Lifecycle and Provenance já
validado. A alteração deve conter exatamente `docs/project-brain/13-CHECKPOINT.md`
e `docs/project-brain/CANONICAL-SHA256SUMS.txt`, com o hash do checkpoint
recalculado e todos os demais hashes preservados.

## 2. Identidade e evidência

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base protegida exata: `{base_sha}`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.
- Status de checkpoint: Memory Lifecycle and Provenance Foundation APPROVED /
  V0.1 IMPLEMENTATION ACTIVE.
- A evidência deve estar PASS, bounded, reproduzível e vinculada ao migration
  `0006_memory_lifecycle_provenance`.

## 3. Limites semânticos

COMPLETED preserva seu prefixo histórico e adiciona somente as cinco classes
Memory autorizadas. PENDING remove somente `memory.`. O próximo passo é apenas
o menor incremento ACCE além das fundações de intake/storage/context; não há
claim de MCP Memory, Memory compartilhada, VALIDATED_EVIDENCE aberto,
dispatch autônomo, telemetria completa, Control Center completo, ACCE completo
ou V0.1 completo.

## 4. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED;
nenhum merge/release é executado nesta etapa.

## 5. Estado de Sol

A PR permanece aberta e Ready até auditoria do HEAD exato. Sol Review State:
AWAITING_SOL.

WO-015-P READY FOR SOL AUDIT
"""


def _render_wo016p_g1_body(
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

## 1. Objetivo e limite

Esta PR habilita exclusivamente o suporte determinístico de Review Evidence e
renderer para a futura promoção do checkpoint ACCE Storage Tier and Compression
Policy Foundation. Não promove o checkpoint e não executa `WO-016-P`.

## 2. Identidade exata

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base autorizada exata: `54c32e939c7be6d505727df24d3ce2ad48af5518`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.

## 3. Escopo G1 fechado

Arquivos permitidos: `backend/tests/test_review_evidence.py`,
`scripts/review_evidence.py` e `scripts/review_pr_body.py`. Project Brain,
manifest canônico, migrations, produto ACCE, MCP, telemetria, Control Center e
execução autônoma permanecem intocados. O migration head exigido é
`0006_memory_lifecycle_provenance`.

O futuro `WO-016-P` é registrado explicitamente e permitirá somente
`docs/project-brain/13-CHECKPOINT.md` e
`docs/project-brain/CANONICAL-SHA256SUMS.txt`, com base protegida atual,
marcador autorizado, sem mudança de outras linhas do manifest e sem alteração
fora do contrato fechado do checkpoint.

## 4. Contrato ACCE e lineage

O contrato exige `acce-storage-policy-v1` PASS, política `acce-policy-v1`,
HOT/WARM/COLD, seis linhas medidas (dois candidatos por tier), bytes lógicos e
físicos truthfully medidos, identidade SHA-256/CAS única, deduplicação válida,
corruption/truncation fail-closed, recovery após restart/Redis loss, perda de
fonte canônica zero e chamadas LLM/provider `0/0`. A evidência permanece ligada
à linhagem aprovada de PR #55, HEAD auditado, revisão Sol, squash merge, CI,
backend 418 e dashboard 7.

## 5. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED;
nenhum merge, release ou promoção canônica é executado nesta etapa.

## 6. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-016-P-G1 READY FOR SOL AUDIT
"""


def _render_wo016p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor — {work_order}

## 1. Promoção ACCE fechada

Esta PR futura promove somente o checkpoint ACCE Storage Tier and Compression
Policy Foundation já aprovado, merged e validado no pós-merge. Exige exatamente
`docs/project-brain/13-CHECKPOINT.md` e
`docs/project-brain/CANONICAL-SHA256SUMS.txt`; não implementa MCP, produto,
migration ou qualquer outra mudança canônica.

## 2. Contrato semântico

O STATUS, o prefixo histórico de COMPLETED, as cinco bullets ACCE, a remoção
única de ACCE em PENDING e o próximo passo MCP são contratos fechados. O
manifest preserva comentários, ordem, conjunto de paths e todas as hashes
exceto a hash exata do checkpoint. A evidência `acce-storage-policy-v1` deve
continuar PASS com política `acce-policy-v1`, seis linhas medidas, perda
canônica zero e chamadas LLM/provider `0/0`.

## 3. Identidade e governança

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base protegida exata: `{base_sha}`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.
- Ruleset antes: {ruleset_before}; depois: {ruleset_after}.
- Merge antes: {merge_before}; depois: {merge_after}.

Auto-merge permanece UNARMED. A PR permanece aberta e não mesclada para
auditoria de Sol no HEAD exato.

Sol Review State: AWAITING_SOL.

WO-016-P READY FOR SOL AUDIT
"""


def _render_wo017p_g1_body(
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

## 1. Objetivo e limite

Esta PR habilita exclusivamente o suporte determinístico de Review Evidence e
renderer para a futura promoção do checkpoint MCP Read-Only Core Surface.
Não promove o checkpoint e não executa `WO-017-P`.

## 2. Identidade exata

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base autorizada exata: `0d9240f3a18530fae3e9f65751dbc11491c485c0`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.

## 3. Escopo G1 fechado

Arquivos permitidos: `backend/tests/test_review_evidence.py`,
`scripts/review_evidence.py` e `scripts/review_pr_body.py`.
Project Brain, manifest canônico, migrations, produto MCP, telemetria,
Control Center e execução autônoma permanecem intocados.

O futuro `WO-017-P` é registrado explicitamente e permitirá somente
`docs/project-brain/13-CHECKPOINT.md` e
`docs/project-brain/CANONICAL-SHA256SUMS.txt`, com base protegida atual,
marcador autorizado e contrato fechado de checkpoint/manifest.

## 4. Contrato MCP

A promoção futura exige `mcp-core-surface-v1` PASS, catálogo exato de sete
tools read-only, transporte local real, reutilização direta do Core, isolamento
por projeto, checkpoint-first, erros bounded, restart/Redis-loss recovery,
zero leaks e zero chamadas MCP LLM/provider. A linhagem validada inclui PR #59
e a correção PR #60 com CI pós-merge 34285893606.

## 5. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED;
nenhum merge, release ou promoção canônica é executado nesta etapa.

## 6. Estado de Sol

A PR permanece aberta, Ready e não mesclada. Sol Review State: AWAITING_SOL.

WO-017-P-G1 READY FOR SOL AUDIT
"""


def _render_wo017p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor — {work_order}

## 1. Promoção MCP fechada

Esta PR futura promove somente o checkpoint MCP Read-Only Core Surface já
aprovado, merged e validado no pós-merge. Exige exatamente
`docs/project-brain/13-CHECKPOINT.md` e
`docs/project-brain/CANONICAL-SHA256SUMS.txt`.

## 2. Contrato semântico

O STATUS, o prefixo histórico de COMPLETED, as cinco bullets MCP, a remoção
única de `MCP server product surface.` em PENDING e o próximo passo
Autonomous Execution são contratos fechados. O manifest preserva comentários,
ordem, paths e todas as hashes exceto a hash exata do checkpoint.

## 3. Identidade e governança

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base protegida exata: `{base_sha}`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.
- Ruleset antes: {ruleset_before}; depois: {ruleset_after}.
- Merge antes: {merge_before}; depois: {merge_after}.

Auto-merge permanece UNARMED. A PR permanece aberta e não mesclada para
auditoria de Sol no HEAD exato.

Sol Review State: AWAITING_SOL.

WO-017-P READY FOR SOL AUDIT
"""


def _render_wo018p_g1_body(
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

# Revisão do executor - {work_order}

## 1. Objetivo

Esta PR habilita somente o Review Evidence para a promoção canônica do
WO-018 Autonomous Execution Foundation. Não altera Project Brain, checkpoint,
manifesto canônico, migrations ou produto.

## 2. Identidade

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base autorizada exata: ed534965136a36eff66276d5b073dc034a7fc96f.
- Base informada: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 3. Escopo

Exatamente três arquivos de governança: backend/tests/test_review_evidence.py,
scripts/review_evidence.py e scripts/review_pr_body.py.

O futuro WO-018-P permitirá somente docs/project-brain/13-CHECKPOINT.md e
docs/project-brain/CANONICAL-SHA256SUMS.txt, com marcador de base autorizado,
gramática de checkpoint fechada e contrato exato do manifesto.

## 4. Contrato futuro

A promoção exige autonomous-execution-v1 PASS e registra como concluídos:
Execution Orchestrator provider-independent, Context Manager/Runner/ToolPolicy
reutilizados, tool gating end-to-end, staged output e captura de
files/diff/tests/validation/review. O próximo passo canônico será a menor
fundação Telemetry/Event Bus necessária.

## 5. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED.
Nenhum merge, release ou promoção canônica é executado nesta etapa.

Sol Review State: AWAITING_SOL.

WO-018-P-G1 READY FOR SOL AUDIT
"""


def _render_wo018p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor - {work_order}

## 1. Promoção Autonomous Execution fechada

Esta PR promove somente o checkpoint do WO-018 já aprovado, merged e validado
no pós-merge. Exige exatamente docs/project-brain/13-CHECKPOINT.md e
docs/project-brain/CANONICAL-SHA256SUMS.txt.

## 2. Contrato semântico

STATUS muda para AUTONOMOUS EXECUTION FOUNDATION APPROVED / V0.1 IMPLEMENTATION
ACTIVE. O prefixo histórico de COMPLETED é preservado, cinco bullets de evidência
WO-018 são anexadas, e somente os itens pending de autonomous execution e tool
gating end-to-end são removidos. IN PROGRESS e NEXT STEP passam para a menor
fundação Telemetry/Event Bus necessária.

## 3. Identidade e governança

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida exata: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.
- Ruleset antes: {ruleset_before}; depois: {ruleset_after}.
- Merge antes: {merge_before}; depois: {merge_after}.

Auto-merge permanece UNARMED. A PR permanece aberta e não mesclada para
auditoria de Sol no HEAD exato.

Sol Review State: AWAITING_SOL.

WO-018-P READY FOR SOL AUDIT
"""


def _render_wo019p_g1_body(
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

# Revisão do executor - {work_order}

## 1. Objetivo

Esta PR habilita somente o Review Evidence para a promoção canônica do
WO-019 Telemetry/Event Bus Foundation. Não altera Project Brain, checkpoint,
manifesto canônico, migrations ou produto.

## 2. Identidade

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base autorizada exata: d800fac8f165146055ad050d6c2f232883dc91b7.
- Base informada: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.

## 3. Escopo

Exatamente três arquivos de governança: backend/tests/test_review_evidence.py,
scripts/review_evidence.py e scripts/review_pr_body.py.

O futuro WO-019-P permitirá somente docs/project-brain/13-CHECKPOINT.md e
docs/project-brain/CANONICAL-SHA256SUMS.txt, com marcador de base autorizado,
gramática de checkpoint fechada e contrato exato do manifesto.

## 4. Contrato futuro

A promoção exige telemetry-event-bus-v1 PASS e registra o lineage aceito:
PR #70, HEAD 590eda41c55c1b21f4a04789cf5576a6640f0732, Sol 5162319026,
squash d800fac8f165146055ad050d6c2f232883dc91b7 e CI 34433610894. O próximo
passo canônico será a menor implementação full HIVE Control Center necessária.

## 5. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece UNARMED.
Nenhum merge, release ou promoção canônica é executado nesta etapa.

Sol Review State: AWAITING_SOL.

WO-019-P-G1 READY FOR SOL AUDIT
"""


def _render_wo019p_body(
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
<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->

# Revisão do executor - {work_order}

## 1. Promoção Telemetry/Event Bus fechada

Esta PR promove somente o checkpoint do WO-019 já aprovado, merged e validado
no pós-merge. Exige exatamente docs/project-brain/13-CHECKPOINT.md e
docs/project-brain/CANONICAL-SHA256SUMS.txt.

## 2. Contrato semântico

STATUS muda para TELEMETRY / EVENT BUS FOUNDATION APPROVED / V0.1 IMPLEMENTATION
ACTIVE. O prefixo histórico de COMPLETED é preservado, cinco bullets de evidência
WO-019 são anexadas, e somente o item pending `telemetry.` é removido. IN PROGRESS
e NEXT STEP passam para a menor implementação full HIVE Control Center necessária.

## 3. Identidade e governança

- PR: #{pr_number}, Ready for review.
- Branch: {branch}.
- Base protegida exata: {base_sha}.
- HEAD exato: {head_sha}.
- Evidence Bundle: {artifact_name}.
- Ruleset antes: {ruleset_before}; depois: {ruleset_after}.
- Merge antes: {merge_before}; depois: {merge_after}.

Auto-merge permanece UNARMED. A PR permanece aberta e não mesclada para
auditoria de Sol no HEAD exato.

Sol Review State: AWAITING_SOL.

WO-019-P READY FOR SOL AUDIT
"""


def _render_wo015_body(
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

## 1. Resumo

Esta PR implementa a menor fundação Memory Lifecycle and Provenance,
project-scoped e durável, sobre PostgreSQL. Derivações e Redis permanecem
não canônicos.

## 2. Referências exatas

- PR: #{pr_number}, Ready for review.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- HEAD exato: `{head_sha}`.
- Evidence Bundle: `{artifact_name}`.

## 3. Durabilidade e escopo

Registros canônicos vivem em PostgreSQL; Redis é somente HOT/noncanonical.
Todas as leituras, listas, transições e promoções exigem project scope e
rejeitam cross-project. A evidência cobre restart e perda de Redis.

## 4. Lifecycle e proveniência

Working, Session, Project, Semantic, Episodic, Decision, Failure e Procedural
preservam status, identidade, fonte, versão/commit, confiança, importância,
autoridade, tags e histórico. Supersession/deprecation preserva o registro
anterior e sua proveniência.

## 5. Gate canônico

Saída de modelo/executor inicia staged/noncanonical. Promoção só aceita fonte
confiável, evidência validada ou decisão aprovada; ausência ou invalidez falha
explicitamente sem mutar o registro canônico.

## 6. Evidence contract

`memory-lifecycle-provenance-v1` comprova PostgreSQL, Redis não canônico,
isolamento, proveniência, staged output, promoção qualificada, rejeição de
promoção inválida, histórico, restart, Redis loss, segredos e migration head.
O contrato exige contagens bounded e zero chamadas LLM/provider no gate.

## 7. Migration, testes e segurança

Migration additive/reversible, testes unitários e de integração cobrem
transições, escopo, proveniência, promoção, histórico e recuperação. Nenhum
segredo é armazenado, retornado ou registrado.

## 8. Escopo negativo

Não há MCP memory tools, UI de Memory, dispatch autônomo, shared memory,
upgrade não relacionado, limpeza ampla, checkpoint promotion ou merge.

## 9. Governança

Ruleset antes: {ruleset_before}. Ruleset depois: {ruleset_after}. Merge antes:
{merge_before}. Merge depois: {merge_after}. Auto-merge permanece desarmado;
Sol audita o HEAD exato e somente SQUASH é permitido.

## 10. Estado final

A PR permanece aberta e Ready. Sol Review State: AWAITING_SOL.

WO-015 READY FOR SOL AUDIT
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
    _require_exact_head(work_order, head_sha)
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
    if work_order == "WO-013":
        return _render_wo013_body(
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
    if work_order == "WO-014":
        return _render_wo014_body(
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
    if work_order == "WO-012-P-G1":
        return _render_wo012p_g1_body(
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
    if work_order == "WO-013-P-G1":
        return _render_wo013p_g1_body(
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
    if work_order == "WO-014-P-G1":
        return _render_wo014p_g1_body(
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
    if work_order == "WO-012-P":
        return _render_wo012p_body(
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
    if work_order == "WO-013-P":
        return _render_wo013p_body(
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
    if work_order == "WO-014-P":
        return _render_wo014p_body(
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
    if work_order == "WO-016-G1":
        return _render_wo016_g1_body(
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
    if work_order == "WO-016":
        return _render_wo016_body(
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
    if work_order == "WO-018-G1":
        return _render_wo018_g1_body(
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
    if work_order == "WO-018":
        return _render_wo018_body(
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
    if work_order == "WO-019-G1":
        return _render_wo019_g1_body(
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
    if work_order == "WO-019":
        return _render_wo019_body(
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
    if work_order == "WO-020-G1":
        return _render_wo020_g1_body(
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
    if work_order == "WO-020":
        return _render_wo020_body(
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
    if work_order == "WO-017-G1":
        return _render_wo017_g1_body(
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
    if work_order == "WO-017":
        return _render_wo017_body(
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
    if work_order == "WO-018-P-G1":
        return _render_wo018p_g1_body(
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
    if work_order == "WO-018-P":
        return _render_wo018p_body(
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
    if work_order == "WO-019-P-G1":
        return _render_wo019p_g1_body(
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
    if work_order == "WO-019-P":
        return _render_wo019p_body(
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
    if work_order == "WO-017-P-G1":
        return _render_wo017p_g1_body(
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
    if work_order == "WO-017-P":
        return _render_wo017p_body(
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
    if work_order == "WO-015-G1":
        return _render_wo015_g1_body(
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
    if work_order == "WO-015-P-G1":
        return _render_wo015p_g1_body(
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
    if work_order == "WO-015-P":
        return _render_wo015p_body(
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
    if work_order == "WO-016-P-G1":
        return _render_wo016p_g1_body(
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
    if work_order == "WO-016-P":
        return _render_wo016p_body(
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
    if work_order == "WO-015":
        return _render_wo015_body(
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
