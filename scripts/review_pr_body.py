"""Render the twenty-section executor review for an auditable pull request."""

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
