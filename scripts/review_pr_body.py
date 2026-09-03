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
    owner_login = auto_merge_owner_login or "recorded by Review Evidence"
    owner_type = auto_merge_owner_type or "User"
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
aceitos. O checkpoint é processado e emitido primeiro; autoridade canônica e
trust de task/user input são distintos.

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

## 13. Review Evidence

Artifact: `{artifact_name}`. A evidência Context Manager deve mostrar
checkpoint-first, project/task scoped, reranked retrieval, provenance,
deterministic two-run, bounds, isolation, missing-governance/HEAD fail-closed,
Redis/API rebuild e `llm_calls: 0`.

## 14. Ruleset / auto-merge

Antes: {ruleset_before}; merge: {merge_before}. Depois: {ruleset_after}; merge:
{merge_after}. Ruleset unchanged, checks reais, squash-only e zero bypass.
Auto-merge owner: `{owner_login}` ({owner_type}); somente User é aceito.

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
threads resolvidas e squash-only. Auto-merge só pode ser armado após o gate de
uma aprovação independente elegível; o executor não aprova nem faz merge.

## 18. Limitações e avisos conhecidos

Não há índice aproximado nesta versão: a consulta usa scan exato bounded.
Provider local/fixture serve apenas à prova determinística. Avisos de ambiente
ou dependências permanecem registrados no manifesto sem serem ocultados.

## 19. Arquivos e artefato

A lista completa de arquivos, diff, resultados, benchmark, logs sanitizados e
governança está no artefato `{artifact_name}` e no comentário sticky marcado
por `<!-- hive-review-evidence:{work_order} -->`.

## 20. Estado para revisão de Sol

A PR permanece aberta e não mesclada. Nenhuma aprovação é atribuída a Sol;
threads e checks devem ser verificados no current head antes de qualquer merge.

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
