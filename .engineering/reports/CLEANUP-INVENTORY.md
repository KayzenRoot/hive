# Cleanup Inventory — ENG-PROTOCOL-ADOPTION-001

## Escopo e regra de segurança

Este é um inventário, não uma autorização para apagar. Nenhuma limpeza foi
executada nesta PR. A busca cobriu código Python/TypeScript, scripts, migrations,
dependências declaradas, docs, templates, workflows, artefatos versionados,
flags/configuração, testes/fixtures e referências dinâmicas.

Classificações permitidas:

- `VERIFIED_DEAD`: comprovadamente inatingível e removível somente em Work Order posterior;
- `PROBABLY_DEAD`: forte indicação, ainda requer revisão/characterization;
- `DUPLICATE_OR_OBSOLETE`: sobreposição ou obsolescência indicada, não remoção automática;
- `GENERATED_OR_VENDORED`: gerado, transitivo ou fornecido por ferramenta;
- `UNKNOWN`: evidência insuficiente ou possibilidade de uso dinâmico.

## Evidências determinísticas

- `python -m ruff check backend scripts migrations`: PASS; não há imports Python
  não usados reportados por `F401`.
- `rg -n -i "TODO|FIXME|deprecated|obsolete|legacy" .`: encontrou apenas usos
  contextuais, documentação de lifecycle, fixtures e warnings de dependência;
  não provou código morto.
- `git ls-files`: não contém `node_modules`, `dist`, `tmp`, `__pycache__`,
  `.pyc`, `.env`, `coverage`, `review-bundles` ou `release-assets`.
- `python scripts/check_secrets.py`: PASS em 140 tracked files.
- `python scripts/generate_maps.py --check`: PASS; atlas e mapas são derivados.
- `python -m vulture`, `deptry`, `semgrep`, `bandit`, `pip-audit`, `codeql` e
  `coverage` não estão instalados; nenhuma remoção foi inferida pela ausência
  dessas ferramentas.

## Candidatos e classificação

| Área/candidato | Evidência atual | Classificação | Ação segura agora |
| --- | --- | --- | --- |
| Imports backend/scripts/migrations | Ruff `F401` limpo | `UNKNOWN` para exports dinâmicos; nenhum import comprovadamente morto | Não remover; revisar exports públicos/dinâmicos em incremento próprio |
| `backend/app/runner.py` | Testado em `backend/tests/test_runner.py`, documentado em `docs/local-verified-runner.md` e listado no atlas; pode ser seam futuro de executor | `UNKNOWN` | Manter; criar characterization/integration test antes de qualquer redução |
| `scripts/embedding_fixture.py` e `scripts/rerank_fixture.py` | Iniciados por `retrieval_integration.py` e `context_manager_integration.py` | `UNKNOWN` | Manter; fixtures são parte da evidência de integração |
| `scripts/review_bundle.py`, `review_pr_body.py`, `review_evidence.py` | Referenciados por tests, README, CI e release/governance | `UNKNOWN` | Manter; são contratos de revisão, não duplicatas provadas |
| `scripts/capture_service_logs.py` | Chamado pelo CI e testado em `test_review_evidence.py` | `UNKNOWN` | Manter |
| `docs/atlas/*.md` | Cabeçalho declara geração por `scripts/generate_maps.py`; check determinístico passa | `GENERATED_OR_VENDORED` | Não editar/apagar manualmente; regenerar somente pelo script |
| `tmp/`, `dashboard/node_modules/`, `dashboard/dist/`, `__pycache__` | Ignorados pelo Git e criados por validação/build | `GENERATED_OR_VENDORED` | Não versionar; não constituem limpeza de código |
| Dependências Python diretas em `requirements.txt` | Importações e/ou runtime Docker/CLI; sem `deptry`/pip-audit instalado; validação e testes passam | `UNKNOWN` | Manter; revisar uma por vez com lock, runtime e CI |
| Dependências npm transitivas, incluindo warning `whatwg-encoding` | `npm audit` PASS; warning é depreciação transitiva, não prova de desuso | `UNKNOWN` | Não remover manualmente; tratar via Dependabot/upgrade dedicado |
| Dependências de desenvolvimento (`ruff`, `mypy`, `pytest`, tooling dashboard) | Usadas por `scripts/validate.py`/CI e package scripts | `UNKNOWN` | Manter |
| `migrations/versions/0001..0005` | Alembic chain e head `0005_semantic_retrieval`; runtime e integrações dependem da sequência | `UNKNOWN` | Nunca apagar; exigir plano de compatibilidade e backup |
| Flags `HIVE_EMBEDDING_*`/`HIVE_RERANK_*` e config equivalente | Declaradas em `docker-compose.yml`, `backend/app/config.py` e exercitadas por integrações; uso pode ser dinâmico | `UNKNOWN` | Manter; confirmação de owner/telemetria antes de mudança |
| `docs/project-brain/05-CONTEXT-MEMORY-ENGINE.md` com status `DEPRECATED` | É lifecycle semântico de memória em fonte canônica | `UNKNOWN` | Não interpretar como autorização; somente decisão canônica pode alterar |
| `backend/tests/test_registry.py::LegacyRows` | Fixture explicitamente usada para compatibilidade/regressão | `UNKNOWN` | Manter até provar contrato obsoleto |
| Test helpers/fixtures em `backend/tests` e scripts de integração | Referenciados pelos testes/integrações ou por imports compartilhados | `UNKNOWN` | Manter; remover apenas com teste de referência e owner |
| Documentação operacional sobreposta (`docs/*` e `docs/project-brain/*`) | Papéis diferentes: docs operacionais versus fonte canônica; não há regra segura de substituição | `UNKNOWN` | Mapear links e ownership antes de consolidar |
| Configuração duplicada entre Compose, Settings, Dockerfiles e workflows | Valores possuem defaults/env e fronteiras de runtime distintas | `UNKNOWN` | Não consolidar sem matriz de precedência e teste de configuração |
| Dependências circulares | Nenhum analisador de grafo disponível; imports incluem seams e imports locais | `UNKNOWN` | Medir grafo em incremento dedicado sem alterar imports |
| Desvio arquitetural | Atlas/documentação cobrem módulos, mas não existe linter formal de arquitetura | `UNKNOWN` | Comparar contra `04-ARCHITECTURE.md` com owner antes de refatorar |
| Segredos/artefatos sensíveis versionados | Secret scan PASS; `.env` e dados runtime ignorados; nenhum caminho proibido versionado | `UNKNOWN` — não há candidato confirmado | Não remover; repetir scan no PR |

## Não há `VERIFIED_DEAD`

Nenhum candidato atingiu o padrão `VERIFIED_DEAD`. Reflection/DI, configuração
dinâmica, rotas, eventos, CLI, jobs, migrations, fixtures e contratos públicos
foram tratados como potencialmente usados. A ausência de uma ferramenta ou de
uma referência textual não é prova suficiente.

## Ordem recomendada para futuros incrementos

1. Criar characterization tests e cobertura repetível para endpoints,
   isolamento, migrations, flags e governança canônica.
2. Fazer manutenção de artefatos gerados apenas quando o mapa estiver
   comprovadamente desatualizado, usando o gerador existente.
3. Tratar warnings/dependências transitivas individualmente via Dependabot,
   lockfile e CI; nunca por remoção manual em massa.
4. Revisar imports/exports com análise estática e busca de uso dinâmico; remover
   somente itens que atinjam `VERIFIED_DEAD`.
5. Consolidar scripts/docs com duplicação demonstrada, owner confirmado,
   links atualizados e testes de workflow.
6. Revisar flags/configuração após evidência de ausência em runtime e decisão do
   owner; preservar defaults e compatibilidade.
7. Só então avaliar módulos órfãos isolados; cada remoção em Work Order e PR
   próprios, com baseline BEFORE/AFTER.
8. Deixar migrations, endpoints, jobs e contratos para o último estágio, com
   plano de compatibilidade, backup/recovery e auditoria independente.
