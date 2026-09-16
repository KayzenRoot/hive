$ErrorActionPreference = "Stop"

$ExpectedHead = "44c61e999c89a6b6ba6c28377cea415cad3d1cef"
$Branch = "governance/wo024-g1-sol-recovery"
$Root = (Get-Location).Path
$Payload = Join-Path $PSScriptRoot "payload"

Write-Host "HIVE WO-024-G1 Sol Fix" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $Root ".git"))) {
    throw "Execute este script na raiz do repositorio HIVE."
}

$Current = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "git rev-parse falhou." }
if ($Current -ne $ExpectedHead) {
    throw "HEAD divergente. Esperado $ExpectedHead, observado $Current. Nenhuma alteracao foi aplicada."
}

$TrackedDirty = git status --porcelain --untracked-files=no
if ($TrackedDirty) {
    throw "Existem alteracoes rastreadas locais. Preserve/limpe antes de aplicar para nao misturar escopos."
}

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch falhou." }

git switch -C $Branch "origin/$Branch"
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel alternar para $Branch." }

$AfterSwitch = (git rev-parse HEAD).Trim()
if ($AfterSwitch -ne $ExpectedHead) {
    throw "Branch remota nao aponta para a base autorizada. Esperado $ExpectedHead, observado $AfterSwitch."
}

$Copies = @(
    @("scripts/review_evidence.py", "scripts/review_evidence.py"),
    @("backend/tests/test_review_evidence.py", "backend/tests/test_review_evidence.py"),
    @("scripts/review_pr_body.py", "scripts/review_pr_body.py"),
    @("schemas/review-evidence-v1.schema.json", "schemas/review-evidence-v1.schema.json")
)

foreach ($Pair in $Copies) {
    $From = Join-Path $Payload $Pair[0]
    $To = Join-Path $Root $Pair[1]
    if (-not (Test-Path $From)) { throw "Payload ausente: $From" }
    Copy-Item -Force $From $To
}

$Changed = @(git diff --name-only)
$Expected = @(
    "backend/tests/test_review_evidence.py",
    "schemas/review-evidence-v1.schema.json",
    "scripts/review_evidence.py",
    "scripts/review_pr_body.py"
) | Sort-Object
$Observed = $Changed | Sort-Object

if ((Compare-Object $Expected $Observed)) {
    Write-Host "Arquivos observados:" -ForegroundColor Yellow
    $Observed | ForEach-Object { Write-Host "  $_" }
    throw "Escopo divergente. Esperados exatamente 4 arquivos."
}

Write-Host "Rodando os quatro testes que estavam bloqueando..." -ForegroundColor Cyan
python -m pytest -q `
  backend/tests/test_review_evidence.py::test_wo021_registration_and_bounded_scopes `
  backend/tests/test_review_evidence.py::test_wo022_registration_and_scopes_are_exact_and_fail_closed `
  backend/tests/test_review_evidence.py::test_wo023_renderers_are_dedicated_and_fail_closed `
  backend/tests/test_review_evidence.py::test_wo023p_build_manifest_reads_its_authorized_base_marker
if ($LASTEXITCODE -ne 0) { throw "Os testes focados falharam. Nenhum commit/push foi feito." }

python -c "import ast,json,pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['scripts/review_evidence.py','backend/tests/test_review_evidence.py','scripts/review_pr_body.py']]; json.loads(pathlib.Path('schemas/review-evidence-v1.schema.json').read_text(encoding='utf-8')); print('syntax/schema: PASS')"
if ($LASTEXITCODE -ne 0) { throw "Validacao de sintaxe/schema falhou." }

git add backend/tests/test_review_evidence.py schemas/review-evidence-v1.schema.json scripts/review_evidence.py scripts/review_pr_body.py
git commit -m "WO-024-G1: close historical validation migration"
if ($LASTEXITCODE -ne 0) { throw "git commit falhou." }

git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw "git push falhou." }

Write-Host ""
Write-Host "SUCCESS" -ForegroundColor Green
Write-Host "Branch publicada: $Branch"
Write-Host "Volte ao ChatGPT e diga: continue o WO-024-G1 daqui."
