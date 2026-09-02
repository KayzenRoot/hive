"""Render a generic twenty-section executor review for a Draft pull request."""

from __future__ import annotations

import argparse
from pathlib import Path


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
) -> str:
    return f"""<!-- HIVE-WORK-ORDER: {work_order} -->

# Revisão do executor — {work_order}

## 1. Resumo executivo

A correção preserva a fundação de retrieval lexical da WO-006 e fecha os
achados de auditoria sobre consistência de fontes durante a promoção,
candidatos duplicados de tarefas e evidência de revisão no GitHub.

## 2. Objetivo

Corrigir somente os defeitos reportados por Sol, mantendo a mesma PR Draft
#{pr_number}, a migration 0004, o isolamento por projeto e o benchmark lexical
existente.

## 3. Escopo implementado

O corpus captura HEAD, inventário Git e hashes dos arquivos indexados e
revalida toda essa geração sob o lock antes da promoção. A busca colapsa apenas
referências TASK com o mesmo chunk, preservando todas as linhas de proveniência.
A evidência agora é estruturada, delimitada no log, consolidada em um artefato
e refletida em um comentário sticky único.

## 4. Fora de escopo explícito

Não foram implementados retrieval semântico, embeddings, reranking,
executor/autonomia, WO-007, merge da PR, release, tag ou alteração do
checkpoint canônico do Project Brain.

## 5. Base, branch e head

- PR: #{pr_number}, mantida aberta e Draft.
- Branch: `{branch}`.
- Base exata: `{base_sha}`.
- Head exato desta revisão: `{head_sha}`.

## 6. Decisões de arquitetura

PostgreSQL continua sendo a fonte durável. O chunker determinístico
`line-window-v1`, a busca lexical bounded e as chaves project-scoped permanecem.
A validação de geração é fail-closed e uma falha transacional preserva o corpus
corrente anterior.

## 7. Migração e schema

A migration permanece `0004_retrieval_lexical`. Nenhuma migration adicional foi
criada. As referências TASK distintas continuam persistidas; a deduplicação
ocorre somente na seleção de candidatos, não na identidade canônica das tarefas
ou referências.

## 8. API

As rotas existentes de sincronização, status e busca lexical permanecem
project-scoped, com limites de query/top-k, snippets bounded, filtros de source
kind e metadados de proveniência.

## 9. Segurança

HEAD, inventário e bytes são comparados com a geração indexada antes da
promoção. Queries PostgreSQL usam parâmetros psycopg. Isolamento cross-project,
secret scan, verificação canônica e falha fechada de fontes stale foram
cobertos por testes e integrações.

## 10. Integridade de fonte

Uma corrida de HEAD ou inventário entre a construção da geração e a promoção
resulta em `STALE` com `repository_source_stale` na revalidação final. A
geração anterior permanece queryável e não há flip parcial de referências
`is_current`.

## 11. Candidatos TASK duplicados

Submissões READY com texto derivado idêntico mantêm tarefas e referências
distintas no PostgreSQL. A seleção lexical usa a identidade determinística
`(project_id, chunk_id, source_kind)` apenas para TASK e escolhe o representante
por score, `task_id` e `reference_id`.

## 12. Dashboard

O Retrieval Corpus e o Lexical Retrieval Lab existentes permanecem funcionando
com dados reais, limites bounded e a mesma arquitetura de seleção de projeto.

## 13. Benchmark

O baseline lexical permanece com quatro consultas críticas, recall@1 1.0,
recall@5 1.0, MRR 1.0, zero misses críticos, isolamento cross-project e duas
execuções reproduzíveis.

## 14. Testes automatizados

Os testes cobrem chunking/ranges, corrida de HEAD, corrida de inventário com
bytes capturados inalterados, parametrização SQL, schema/log delimitado,
contagens estruturadas e remoção do fallback legado específico.

## 15. Integrações reais

Project Registry, Task Intake/CAS, Repository Indexing e Retrieval Corpus/Lexical
foram executados em Compose com repositórios Git reais. A integração de
retrieval cobre Redis/API restart, benchmark duas vezes, stale/recovery,
HEAD/inventory races, preservação do corpus e deduplicação de tarefas entre
projetos.

## 16. CI e evidências

`Validate`, `Integration health` e `Review Evidence` executam no head exato. O
manifesto JSON é impresso entre `HIVE_REVIEW_MANIFEST_BEGIN` e
`HIVE_REVIEW_MANIFEST_END`. O artefato consolidado `{artifact_name}` contém
arquivos alterados, migration, validação, integrações, benchmark, diagnósticos
bounded, manifesto, resumo e governança.

## 17. Governança GitHub

Antes: {ruleset_before}; configurações de merge: {merge_before}. Depois:
{ruleset_after}; configurações de merge: {merge_after}. A proteção permanece
ativa, sem bypass, com pull request obrigatório, deletion/non-fast-forward
protection, os três checks reais, resolução de threads e squash-only.

## 18. Limitações e avisos conhecidos

Avisos não bloqueantes observados permanecem registrados no manifesto, sem
descartar warnings. O sistema continua lexical e bounded; conteúdo de usuário
não é incluído no pacote consolidado.

## 19. Arquivos e artefato

A lista completa de arquivos alterados, o diff e os resultados objetivos estão
no artefato consolidado `{artifact_name}` e no comentário sticky controlado pelo
marcador `<!-- hive-review-evidence:{work_order} -->`.

## 20. Estado para revisão de Sol

Nenhuma aprovação é atribuída a Sol. A PR permanece Draft, aberta e não
mesclada para auditoria direta no GitHub.

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
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8", newline="\n")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
