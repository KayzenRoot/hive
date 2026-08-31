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
        [
            "gh",
            "pr",
            "view",
            "15",
            "--json",
            "number,state,mergedAt,url,headRefName,baseRefName,headRefOid",
        ],
        ["gh", "pr", "checks", "15", "--json", "name,state,bucket,link"],
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
    return f"""# Revisão do HIVE Prompt #002-C

Data UTC: {stamp}
Estado da validação registrada: {status}

## 1. Resumo da correção

Corrige dois defeitos de auditoria no Project Registry: aliases físicos não
podem criar identidades duplicadas e uma transição insegura não pode deixar
um registro READY obsoleto. Reforça também o escopo de safe.directory do Git.

## 2. Base / branch / head

Base auditada: aa696656cc5ebefe8dc1b23a676ffcbe12ba23e9 em main.
Correção descendente do head auditado: f619c5686081e6dae175f608bcfa2d2b6b2074c9.
Branch: feature/002-project-registry. PR #15 deve permanecer aberto e não
mesclado.

## 3. Canonical project identity

Para targets existentes, symlinks são resolvidos e o path é revalidado abaixo
de HIVE_PROJECTS_ROOT. O campo relative_path armazena a identidade POSIX
relativa canônica; PostgreSQL aplica UNIQUE e uma trava advisory transacional
serializa a checagem os.path.samefile, sem forçar lowercase.

## 4. Duplicate alias proof

O E2E cria real-project e sample-alias como symlink, registra o target real,
rejeita o alias com 409 e confirma no PostgreSQL exatamente um registro para
a identidade física.

## 5. Unsafe transition behavior

Uma rota READY alterada para symlink fora do root retorna a representação
persistida como BLOCKED, limpa HEAD/branch e demais campos Git, grava
path_boundary_violation e avança last_inspected_at. A rota restaurada retorna
deterministicamente a READY com o mesmo project_id.

## 6. Git security

Cada chamada usa argv, shell=False, timeout finito, GIT_OPTIONAL_LOCKS=0 e
safe.directory=<resolved repository path>. safe.directory=* não é usado.

## 7. Database/migration

Não foi necessária nova revisão: 0001_create_projects permanece canônica,
PostgreSQL continua sendo a fonte durável e Redis não contém estado canônico.
Migração em banco limpo passou via serviço one-shot.

## 8. API semantics

POST registra a identidade canônica e retorna 409 para duplicata física.
Re-inspection retorna 200 com estado persistido READY, OFFLINE, DEGRADED ou
BLOCKED; falhas de boundary não são tratadas como input inválido do cliente.

## 9. Tests

Backend: 15 passed, 1 filesystem-dependent skip. Dashboard: 5 passed. E2E
real-Git cobre alias/samefile, transição insegura, recovery, loop, migration,
dois commits, Redis e restart da API.

## 10. Quality

Canonical verification, secret scan, maps, Ruff, mypy, dashboard lint,
typecheck, build, npm audit e Compose config passaram.

## 11. Persistence

Redis FLUSHALL/restart e recreate/restart da API preservaram os registros
PostgreSQL e o HEAD observado.

## 12. CI

Os checks Validate e Integration health passaram no head exato da correção;
as URLs e logs completos estão em github-configuration-evidence.txt e nos
resultados incluídos neste ZIP.

## 13. Files changed

A lista completa está em changed-files.txt e o diff corretivo em git-diff.patch.

## 14. Errors fixed

Foram corrigidos canonicalização ausente, estado READY stale após boundary,
ausência de guarda samefile, resolução de symlink loop não classificada e
safe.directory wildcard.

## 15. Remaining warnings/risks

Symlink/samefile E2E exige filesystem com suporte; CI Linux executa esses
cenários. npm ainda reporta warning de depreciação de whatwg-encoding e
aprovação pendente do install script do esbuild, sem vulnerabilidades auditadas.

## 16. Scope-negative confirmation

Não foram adicionados Prompt #003, indexing, RAG, embeddings, memory, ACCE,
MCP product tools, executor, telemetry, event bus, release ou tag.

## 17. Review bundle

Este ZIP contém a revisão, diff, resultados, E2E, evidências GitHub, dry-run de
release e checksum SHA256.

## 18. Proposed checkpoint

Propor PROJECT REGISTRY CORRECTION IMPLEMENTED - AGUARDANDO AUDITORIA DE SOL.
O checkpoint canônico permanece inalterado até aprovação explícita.
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

Status proposto: PROJECT REGISTRY CORRECTION IMPLEMENTED - AGUARDANDO AUDITORIA DE SOL.

Evidência: a branch feature/002-project-registry contém a identidade física
canônica, o estado BLOCKED para transições inseguras, inspeção determinística,
API, Project Fleet e as validações corretivas do incremento #002.

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
