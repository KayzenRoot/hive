# Adoption Work Order — ENG-PROTOCOL-ADOPTION-001

## Identity

- ID: `ENG-PROTOCOL-ADOPTION-001`
- Title: Universal existing-project engineering delivery adoption
- Status: `APPROVED / IN_PROGRESS`
- Branch: `chore/eng-protocol-adoption-001`
- PR: `PENDING`
- Owner/authority: user-approved increment; canonical promotion remains with Sol/owner

## Source lock

- Repository: `KayzenRoot/hive`
- Base branch: `main`
- Baseline Git SHA: `209a485227103872903a560872133aae5f203717`
- Context Lock: `.engineering/context-locks/ENG-PROTOCOL-ADOPTION-001.md`
- Latest approved checkpoint: `docs/project-brain/13-CHECKPOINT.md` —
  `PROGRESSIVE DISCLOSURE FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE`
- Source hierarchy: `docs/project-brain/00-README-UPLOAD-ORDER.md`

## Objective

Adotar um protocolo verificável de entrega, congelar o baseline, organizar a
governança mínima já existente, integrar instruções/templates de execução e
produzir um inventário de limpeza sem remover código, dependências, migrations,
contratos ou comportamento do produto.

## In scope

- `.engineering/ENGINEERING-DELIVERY-PROTOCOL.md`;
- `.engineering/templates/` para Work Order, Context Lock, Evidence Bundle,
  Correction Delta e Checkpoint Delta;
- Work Order, Context Lock, baseline report, Cleanup Inventory, Evidence Bundle
  e Checkpoint Delta deste ID;
- integração aditiva em `AGENTS.md`;
- adaptação do template existente de PR;
- template de issue de implementação;
- adaptação do template de defeito existente;
- inspeção e documentação da configuração GitHub existente.

## Explicitly out of scope

- novas funcionalidades ou mudança de comportamento;
- refatoração arquitetural ou upgrade de framework/dependência;
- remoção de código suspeito, dependência, migration, endpoint, job,
  configuração, flag ou contrato;
- alteração dos documentos canônicos em `docs/project-brain/`;
- alteração de CI, required-check names, Ruleset ou branch protection;
- merge, release, promoção de checkpoint ou início do primeiro cleanup;
- operação destrutiva ou alteração de dados runtime.

## Acceptance criteria

- [ ] O protocolo descreve inspeção, baseline, Context Lock, stale context,
  escopo, validação, evidência, revisão e stop conditions.
- [ ] Os cinco templates de contrato estão disponíveis e exigem o mesmo ID
  entre os artefatos do incremento.
- [ ] Baseline exato `209a485...` e resultados BEFORE estão registrados,
  incluindo falhas/avisos preexistentes e bloqueio local de Docker.
- [ ] Cleanup Inventory classifica candidatos como
  `VERIFIED_DEAD`, `PROBABLY_DEAD`, `DUPLICATE_OR_OBSOLETE`,
  `GENERATED_OR_VENDORED` ou `UNKNOWN`, sem executar limpeza.
- [ ] `AGENTS.md`, PR template e templates de issue incorporam o fluxo sem
  apagar regras existentes.
- [ ] Nenhum arquivo de produto, migration ou Project Brain canônico muda.
- [ ] A mesma validação do baseline passa AFTER; integração é comprovada pelo
  CI ou permanece claramente marcada como indisponível.
- [ ] A PR é entregue Ready para auditoria independente, sem merge/auto-merge.

## Validation plan

| Área | Comando/workflow |
| --- | --- |
| Canonical/security | `python scripts/verify_canonical_sources.py`; `python scripts/check_secrets.py` |
| Maps/evidence | `python scripts/generate_maps.py --check`; `python scripts/review_evidence.py --work-order LOCAL-VALIDATION` |
| Backend | `python -m ruff format --check backend scripts migrations`; `python -m ruff check backend scripts migrations`; `python -m mypy`; `python -m pytest --junitxml ...` |
| Dashboard | `cd dashboard; npm ci; npm run lint; npm run typecheck; npm run test:run; npm run build; npm audit --audit-level=high` |
| Build/config | `python scripts/validate.py`; `docker compose config --quiet` |
| Integration | workflow `.github/workflows/ci.yml`: `Integration health` e scripts de integração |
| Diff/provenance | `git diff --check`; compare `origin/main...HEAD`; revalidate Context Lock |

## Risk and stop conditions

- Risk: `LOW` — documentação, templates e governança; nenhuma mutação de
  produto esperada.
- Data/migration impact: `NONE`; migration head esperado permanece
  `0005_semantic_retrieval`.
- Stop em stale context, expansão de escopo, operação destrutiva desconhecida,
  baseline indeterminável, GitHub indisponível para a PR ou HIGH/CRITICAL não
  resolvido.

## Handoff contract

- Evidence Bundle: `.engineering/reports/EVIDENCE-BUNDLE-ENG-PROTOCOL-ADOPTION-001.md`
- Cleanup Inventory: `.engineering/reports/CLEANUP-INVENTORY.md`
- Checkpoint Delta: `.engineering/reports/CHECKPOINT-DELTA-ENG-PROTOCOL-ADOPTION-001.md`
- Auto-merge: `DISABLED`
- Merge/release: `NOT AUTHORIZED`
- Review final: português brasileiro; aguardar auditoria independente.
