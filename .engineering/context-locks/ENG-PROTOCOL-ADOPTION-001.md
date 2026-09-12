# Context Lock — ENG-PROTOCOL-ADOPTION-001

## Lock metadata

- ID: `ENG-PROTOCOL-ADOPTION-001`
- Status: `LOCKED` after controlled re-lock. O lock inicial ficou `STALE` quando
  `AGENTS.md` mudou dentro do escopo aprovado; a mudança foi registrada abaixo
  e o lock foi refeito sem alteração das fontes canônicas.
- Captured at UTC: `2026-09-04T14:35:45.0680803Z`
- Repository: `KayzenRoot/hive`
- Baseline Git SHA: `209a485227103872903a560872133aae5f203717`
- Base/default branch: `main`
- Executor branch: `chore/eng-protocol-adoption-001`

## Critical source fingerprints

SHA-256 sobre os bytes exatos dos arquivos no baseline.

| Fonte | SHA-256 |
| --- | --- |
| Source hierarchy — `docs/project-brain/00-README-UPLOAD-ORDER.md` | `7d0077e474a567b1d7f61dde1137a98314f11bec1f5767e94272a221e27e6d32` |
| Project Overview — `docs/project-brain/01-PROJECT-OVERVIEW.md` | `98d07c639e41df1995a9d44119b672e61f721ed7b5e1af2b6d868ff594cecef2` |
| Requirements — `docs/project-brain/02-REQUIREMENTS.md` | `6c66b19097c64a5ecaf715a1302b8efc752c5a36df267da3524ab902e832032a` |
| Scope — `docs/project-brain/03-SCOPE.md` | `6d9e527d182a01320723e44864f04d81bff77433a54d86b3f01f1013bd905733` |
| Architecture — `docs/project-brain/04-ARCHITECTURE.md` | `ae87c8804052ec54e91d15145cbf574389c9f4d975b223939c77954d5e715aec` |
| Context/memory — `docs/project-brain/05-CONTEXT-MEMORY-ENGINE.md` | `760de33855efe8d838770a7b8656c43f9735e76e813b016237a7e6eda8d8a97b` |
| Security/governance — `docs/project-brain/10-SECURITY-GOVERNANCE.md` | `a49a07ba2a2ca43a2a1253804ed141b4fc1efa3fa13434cdb19071fadf9a6d26` |
| Test plan — `docs/project-brain/11-TEST-PLAN.md` | `38d1f19b1f3a013f203fb0168ea9b836e5a803ac2f588216af02bbf03b351162` |
| Local deployment — `docs/project-brain/12-LOCAL-DEPLOYMENT.md` | `771b591071435c53f2b3befb1875bc5a04a0c3e8a8370988bd5fde29ce637329` |
| Checkpoint — `docs/project-brain/13-CHECKPOINT.md` | `57a4457fbf6d9defe24aeb98bdb7982c13d1c7b6512172b42a160a92b09fa9b2` |
| Definition of Done — `docs/project-brain/15-DEFINITION-OF-DONE.md` | `696ebdc00f06afc861e5bdaaffbbb29ad89a0eee937343f39536379813b3ab46` |
| Decisions — `docs/project-brain/16-DECISIONS-LEDGER.md` | `f0b384e8e3326821a58fc180d7ab1b81017b14cd689793463731f161b7512ca1` |
| Canonical SHA manifest — `docs/project-brain/CANONICAL-SHA256SUMS.txt` | `6429d88eaf770331981217d5e3a8d3f5fed9a30b1c496990f92bb4eba34ccaf8` |
| Executor instructions — `AGENTS.md` | baseline `b1c1a2cf1686d8e0d0c0b7884de339d8b70330a9abbf7971c3fde2db495c63d8`; controlled re-lock `f2ee9cc78e8df09debecbb77bc42eeb97a0cc26f782ed55dd9c0a36c7d6ff457` |
| `CLAUDE.md` | `ABSENT` |

## Operational snapshots

- Migration head: `0005_semantic_retrieval`.
- GitHub Ruleset: `Protect main`, ID `21934284`, normalized JSON SHA-256
  `4adf9865aaeb51a46e1277e7ad2abca8b2f9cea7517512302e893ceca4c3cafb`.
- Required checks: `Validate`, `Integration health`, `Review Evidence`.
- Merge policy observed: squash-only, pull request required, thread resolution,
  deletion/non-fast-forward protection, zero bypass actors.
- Existing CI: `.github/workflows/ci.yml` and `.github/workflows/release.yml`.
- Existing PR template: `.github/PULL_REQUEST_TEMPLATE.md`.
- Existing defect template: `.github/ISSUE_TEMPLATE/bug_report.yml`.

## Lock lifecycle

- Initial lock: `LOCKED` on the baseline SHA and initial `AGENTS.md` hash.
- Controlled transition: `STALE` when the approved protocol integration
  changed `AGENTS.md`; no canonical source, product code or migration changed.
- Re-lock: `LOCKED` on the exact controlled `AGENTS.md` hash above, with all
  canonical fingerprints still equal to the baseline. Revalidate again before
  commit and PR handoff.

## Staleness protocol

Recalcular os fingerprints antes do commit, validação AFTER e handoff. Se
qualquer fonte crítica ou Ruleset mudar, marcar `STALE`, invalidar a evidência e
parar para novo lock/decisão. O executor não continua silenciosamente.
