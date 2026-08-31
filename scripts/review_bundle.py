from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "review-bundles"
VALIDATION = ROOT / "tmp" / "validation"


def run(command: list[str], check: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    if check and result.returncode:
        raise RuntimeError(f"{' '.join(command)} failed with {result.returncode}:\n{output}")
    return output


def read_validation(name: str, fallback: str) -> str:
    path = VALIDATION / name
    return path.read_text(encoding="utf-8") if path.exists() else fallback


def github_evidence() -> str:
    commands = [
        [
            "gh",
            "api",
            "repos/KayzenRoot/hive",
            "--jq",
            "{nameWithOwner: .full_name, private: .private, description: .description, "
            "hasIssues: .has_issues, hasWiki: .has_wiki, hasDiscussions: .has_discussions, "
            "allowSquash: .allow_squash_merge, allowMerge: .allow_merge_commit, "
            "allowRebase: .allow_rebase_merge, deleteBranchOnMerge: .delete_branch_on_merge}",
        ],
        [
            "gh",
            "api",
            "repos/KayzenRoot/hive/topics",
            "-H",
            "Accept: application/vnd.github+json",
        ],
        ["gh", "api", "repos/KayzenRoot/hive/branches/main/protection"],
        ["gh", "api", "repos/KayzenRoot/hive/rulesets?includes_parents=true"],
        ["gh", "api", "repos/KayzenRoot/hive/milestones?state=all"],
    ]
    sections: list[str] = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        sections.append(
            "$ "
            + " ".join(command)
            + f"\nexit_code: {result.returncode}\n"
            + result.stdout
            + result.stderr
        )
    rulesets_result = subprocess.run(
        ["gh", "api", "repos/KayzenRoot/hive/rulesets?includes_parents=true"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        rulesets = json.loads(rulesets_result.stdout)
    except json.JSONDecodeError:
        rulesets = []
    protect_main = [
        ruleset
        for ruleset in rulesets
        if ruleset.get("name") == "Protect main" and ruleset.get("id") is not None
    ]
    if not protect_main:
        sections.append("Protect main ruleset discovery: NOT FOUND")
    for ruleset in protect_main:
        ruleset_id = str(ruleset["id"])
        command = ["gh", "api", f"repos/KayzenRoot/hive/rulesets/{ruleset_id}"]
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        sections.append(
            "$ "
            + " ".join(command)
            + f"\nexit_code: {result.returncode}\n"
            + result.stdout
            + result.stderr
        )
    return "\n\n".join(sections)


def bootstrap_review_markdown(stamp: str, status: str) -> str:
    return f"""# Revisão do HIVE bootstrap

Data UTC: {stamp}
Estado da validação registrada: {status}

## 17. Resumo executivo

O incremento #001 cria a fundação local e auditável do HIVE V0.1: governança
canônica, API de health real, PostgreSQL com pgvector, Redis como cache não
canônico, dashboard React, Docker Compose, documentação, CI e evidências.

## 18. Estado inicial encontrado

O remoto KayzenRoot/hive estava vazio, sem commits, tags ou branches remotas.
Foi criado o seed em main e a implementação segue em
bootstrap/001-foundation.

## 19. Arquivos criados/alterados

A lista objetiva está em changed-files.txt. O diff completo está em
git-diff.patch.

## 20. Estrutura e decisões locais de implementação

O backend usa FastAPI com configuração por ambiente. A API verifica PostgreSQL,
a extensão pgvector, Redis e o HIVE_DATA_ROOT. O dashboard usa React + Vite e
renderiza apenas dados reais do endpoint versionado. Compose usa bind mounts
abaixo do HIVE_DATA_ROOT e mantém Redis como não canônico.

## 21. Configuração realizada no GitHub

Consulte github-configuration-evidence.txt para respostas da API do GitHub.

## 22. Configurações do GitHub que não puderam ser aplicadas e motivo

Itens que falharam por permissão, plano ou indisponibilidade permanecem
explicitamente registrados na evidência. Nenhuma configuração é declarada como
aplicada sem resposta objetiva.

## 23. Docker/serviços e persistência

Compose expõe serviços em localhost, persiste PostgreSQL e o diretório de dados
do usuário, e usa Redis apenas para o hot cache. A validação de configuração e
o smoke test de inicialização devem constar nos arquivos de validação.

## 24. Testes executados e resultados

Consulte test-results.txt, summary.txt e a verificação canônica registrada no
bundle.

## 25. Lint / typecheck / build / CI

Consulte lint-typecheck-build-results.txt e os workflows em .github/workflows/.

## 26. Erros encontrados e corrigidos

Qualquer falha registrada durante a execução deve aparecer nos resultados e no
histórico do executor. Falhas ainda abertas são riscos, não sucessos.

## 27. Segurança e segredos

O scan determinístico cobre arquivos rastreados, tokens conhecidos, chaves
privadas e arquivos .env. Nenhum segredo deve entrar no commit ou no bundle.

## 28. Release readiness / patch notes preparados

VERSION, CHANGELOG.md, as notas versionadas e o pacote de release dry-run estão
preparados. Nenhuma release ou tag pública deve ser publicada neste incremento.

## 29. PR, branch e commits

A branch de implementação deve ser publicada e o PR para main deve permanecer
aberto e não mesclado. Os SHAs e a URL ficam nas evidências finais.

## 30. Riscos e pendências

O produto completo, RAG, memória, MCP, indexação, telemetry avançada e executor
autônomo permanecem fora desta vertical slice. A conclusão do V0.1 exige a
Definition of Done completa.

## 31. Evidências para auditoria

Este ZIP reúne estado Git, diff, arquivos alterados, resultados de validação,
Compose, GitHub, release readiness e proposta de checkpoint.

## 32. Caminho/nome do ZIP de review

O caminho do artefato está no retorno do gerador e no arquivo release-readiness.

## 33. Proposta de atualização do checkpoint

Ver proposed-checkpoint-update.md. A proposta é staged e não altera
docs/project-brain/13-CHECKPOINT.md como verdade aprovada.
"""


def review_markdown(stamp: str, status: str) -> str:
    return f"""# Revisão do HIVE Prompt #002

Data UTC: {stamp}
Estado da validação registrada: {status}

## Resumo executivo

O incremento #002 adiciona a primeira revisão de schema de negócio durável do
HIVE, o Project Registry em PostgreSQL, inspeção Git determinística, boundary
de projetos read-only, API versionada e Project Fleet no Control Center.

Prompt ingestion, indexing, RAG, embeddings, memory, MCP product tools,
executor orchestration, token telemetry, event bus, release e Prompt #003 não
fazem parte deste incremento.

## Base e Git

Base auditada: aa696656cc5ebefe8dc1b23a676ffcbe12ba23e9 em main.
Branch: feature/002-project-registry. O PR deve permanecer aberto e não
mesclado para a auditoria de Sol.

## Arquitetura, banco e API

O serviço one-shot aguarda PostgreSQL e executa Alembic até
0001_create_projects; a API verifica alembic_version no startup. Psycopg usa
SQL parametrizado. O Project Registry persiste UUID, nome, path relativo, Git,
linguagens, estado, erro e timestamps. Os endpoints são POST/GET
/api/v1/projects, GET /api/v1/projects/{{project_id}} e POST
/api/v1/projects/{{project_id}}/inspect.

## Segurança e dashboard

HIVE_PROJECTS_ROOT é o único diretório host montado em
/workspace/projects:ro. Paths POSIX relativos passam por resolução contra
traversal e symlink escape. Git usa argv, safe.directory local,
GIT_OPTIONAL_LOCKS=0, shell=False e timeout finito. O dashboard mantém health
e exibe a frota real com cadastro, re-inspeção e estados loading/empty/error.

## Validação e persistência

Consulte os arquivos de resultados deste ZIP para os comandos exatos. O smoke
E2E usa Git real e banco vazio, observa dois commits, rejeita duplicate/traversal,
prova mount read-only, sobrevive a FLUSHALL/restart do Redis e a recreate/restart
da API com o mesmo PostgreSQL. Falhas de driver, readiness, ownership Git e
line endings encontradas durante a execução estão registradas no histórico e
foram corrigidas.

## Riscos, limitações e checkpoint

Os estados futuros permanecem reservados; não há indexação, prompt ingestion,
RAG, memória, MCP, telemetry ou release. O teste de symlink depende do suporte
do filesystem do executor. A proposta de checkpoint é staged e não altera os
arquivos canônicos do Project Brain.
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    work = ROOT / "tmp" / "review-bundle"
    work.mkdir(parents=True, exist_ok=True)

    status = read_validation("summary.txt", "Não há resultados registrados.")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    release_dry_run = run(
        [
            sys.executable,
            "scripts/prepare_release.py",
            "--tag",
            f"v{version}",
            "--ref",
            "HEAD",
            "--output-dir",
            "tmp/release-dry-run",
            "--dry-run",
        ],
        check=True,
    )
    files: dict[str, str] = {
        "REVIEW.md": review_markdown(stamp, status.strip()),
        "git-status.txt": run(["git", "status", "--short", "--branch"]),
        "git-log.txt": run(["git", "log", "--oneline", "--decorate", "--graph", "-n", "30"]),
        "git-diff.patch": run(["git", "diff", "--binary", "origin/main...HEAD"]),
        "changed-files.txt": run(["git", "diff", "--name-status", "origin/main...HEAD"]),
        "test-results.txt": read_validation(
            "test-results.txt", "Nenhum resultado de teste foi registrado."
        ),
        "summary.txt": status,
        "lint-typecheck-build-results.txt": read_validation(
            "lint-typecheck-build-results.txt",
            "Nenhum resultado de lint/typecheck/build foi registrado.",
        ),
        "docker-compose-config.txt": read_validation(
            "docker-compose-config.txt", "Nenhum resultado de Compose foi registrado."
        ),
        "project-registry-integration.txt": read_validation(
            "project-registry-integration.txt",
            "Nenhum resultado E2E do Project Registry foi registrado.",
        ),
        "github-configuration-evidence.txt": github_evidence(),
        "release-package-dry-run.txt": release_dry_run,
        "release-readiness.txt": (
            f"VERSION: {version}\n"
            "Public release: PROIBIDA antes da aprovação de Sol.\n"
            "Docker image publication: não realizada.\n"
            f"Validation summary: {status.strip()}\n"
            "Release package dry-run:\n"
            f"{release_dry_run}"
        ),
        "proposed-checkpoint-update.md": """# Proposta staged de checkpoint

Status proposto: PROJECT REGISTRY IMPLEMENTADO - AGUARDANDO AUDITORIA DE SOL.

Evidência: a branch feature/002-project-registry contém a migração durável,
Project Registry, inspeção determinística, API, Project Fleet e as validações
do incremento #002.

Não promover esta proposta automaticamente. O checkpoint canônico permanece
inalterado até revisão e aprovação explícitas.
""",
    }
    for name, content in files.items():
        (work / name).write_text(content, encoding="utf-8", newline="\n")

    zip_path = OUT_DIR / f"hive-project-registry-review-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work.iterdir()):
            archive.write(path, arcname=path.name)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    checksum_path = zip_path.with_suffix(".zip.sha256")
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(zip_path), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
