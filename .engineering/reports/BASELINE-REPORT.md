# Baseline Report — ENG-PROTOCOL-ADOPTION-001

## Baseline congelado

- Repository: `KayzenRoot/hive`
- URL: `https://github.com/KayzenRoot/hive`
- Default branch: `main`
- Baseline Git SHA: `209a485227103872903a560872133aae5f203717`
- Baseline commit: `docs: promote Progressive Disclosure checkpoint (#36)`
- Capturado a partir de `origin/main`, sem incluir mudanças desta adoção.
- A PR #36 está mergeada; este baseline não inclui qualquer mudança posterior.

## Stack verificada no repositório

- Backend: Python 3.12, FastAPI, Pydantic Settings, psycopg, SQLAlchemy e
  Alembic.
- Dashboard: TypeScript, React, Vite, ESLint e Vitest.
- Runtime/deployment: Docker Compose com PostgreSQL/pgvector, Redis, API e
  dashboard.
- Package/build: `requirements*.txt`, `pyproject.toml`, `dashboard/package.json`
  e `dashboard/package-lock.json`.
- Database/migrations: Alembic; head declarado e testado
  `0005_semantic_retrieval`.
- Testes: `backend/tests/` e `dashboard/src/App.test.tsx`; integrações em
  `scripts/*_integration.py`.
- CI: `.github/workflows/ci.yml`; release/deployment: `.github/workflows/release.yml`
  e `docker-compose.yml`.
- Fontes canônicas: `docs/project-brain/`; instruções locais: `AGENTS.md`;
  `CLAUDE.md` não existe.

## Validação BEFORE

Executado em 2026-09-04 no SHA exato acima por `python scripts/validate.py`.

| Área | Comando/etapa existente | Resultado |
| --- | --- | --- |
| Canonical | `python scripts/verify_canonical_sources.py` | PASS — 17 arquivos |
| Release dry-run | `python scripts/prepare_release.py --tag v0.0.1-bootstrap --ref HEAD --output-dir tmp/release-dry-run --dry-run` | PASS |
| Secrets | `python scripts/check_secrets.py` | PASS — 140 tracked files |
| Generated maps | `python scripts/generate_maps.py --check` | PASS |
| Review Evidence schema | `python scripts/review_evidence.py --work-order LOCAL-VALIDATION` | PASS |
| Backend format/lint | Ruff format/check em `backend scripts migrations` | PASS — 58 formatados; lint limpo |
| Backend typecheck | `python -m mypy` | PASS — 32 source files |
| Backend tests | `python -m pytest --junitxml tmp/validation/backend-junit.xml` | PASS — 250 passed, 0 failed, 0 skipped |
| Dashboard install | `cd dashboard; npm ci` | PASS — 280 packages, 0 vulnerabilidades |
| Dashboard lint/typecheck | `npm run lint`; `npm run typecheck` | PASS |
| Dashboard tests | `npm run test:run` | PASS — 7 passed |
| Dashboard build | `npm run build` | PASS |
| Dependency audit | `npm audit --audit-level=high` | PASS — 0 vulnerabilidades |
| Compose config | `docker compose config --quiet` | PASS |

O log completo do runner e os XMLs foram gerados em `tmp/`, que é ignorado e
não é entregue como dado de usuário.

## Integration/E2E BEFORE

Tentativa realizada com o fluxo existente de `.github/workflows/ci.yml`:

```text
docker compose up -d --build
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
INTEGRATION_BOOTSTRAP_EXIT=1
```

Status: `UNKNOWN / ENVIRONMENT-BLOCKED`. O daemon Docker Desktop não estava
disponível nesta máquina; portanto os scripts de integração não foram
executados localmente e esta condição não é atribuída ao produto. A evidência
de integração requerida deve vir do job `Integration health` no GitHub.

## Cobertura e characterization tests

O projeto tem testes unitários de backend, teste de dashboard e integrações
reais cobrindo registry, CAS, indexing, retrieval, semantic/hybrid, reranking,
context manager e progressive disclosure. Não há `coverage` instalado nem
relatório de cobertura configurado no baseline local. Antes de qualquer futura
remoção, criar characterization tests para contratos críticos e obter cobertura
repetível, especialmente em endpoints, isolamento por projeto, migrations,
configuração dinâmica e governança canônica.

## Falhas e avisos preexistentes

Não houve falha de validação determinística no baseline. Foram registrados:

- warning de depreciação transitiva do npm para `whatwg-encoding@3.1.1`;
- warning de aprovação de install script para `esbuild@0.25.12` no npm 11;
- warning não bloqueante do pytest no Windows ao limpar
  `pytest-of-csn19\pytest-current` após os 250 testes (`PermissionError`), com
  processo de testes concluído em código 0;
- integração local bloqueada pela indisponibilidade do daemon Docker, conforme
  seção anterior.

Esses itens pertencem ao baseline e não devem ser atribuídos à adoção.
