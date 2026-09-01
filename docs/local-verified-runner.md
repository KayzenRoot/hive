# Fundação do Local Verified Runner

Este documento descreve o incremento WO-004. O núcleo em `backend/app/runner.py` recebe um change set estruturado, valida-o deterministicamente e produz evidência staged. Ele não promove alterações para o estado canônico, não cria PR e não persiste tokens, credenciais ou dados de autenticação.

## Fluxo staged

1. O executor fornece operações `create`, `replace` ou `delete`, sempre com caminhos relativos.
2. `admit_change_set` resolve o workspace, aplica a política allow/deny, verifica limites e registra um snapshot SHA-256 do estado anterior. A admissão não escreve arquivos.
3. `apply_admitted` executa somente uma admissão válida. `create` usa criação exclusiva; `replace` e `delete` revalidam o hash imediatamente antes da mutação correspondente.
4. `verify_changed_files` compara os hashes esperados com o estado final e identifica arquivos extras criados, removidos ou alterados fora da admissão.
5. `StagedRun`, `ApplyResult` e `ProcessEvidence` formam a evidência para futura promoção, PR e telemetria. `promoted` permanece sempre falso nesta fundação.

O change set é limitado por quantidade de operações e bytes de conteúdo. Caminhos vazios, absolutos, com drive/UNC, separador invertido, `.` ou `..` são recusados. A allowlist, quando configurada, é obrigatória; a denylist sempre tem precedência. Caminhos conflitantes dentro do mesmo change set também são recusados. A comparação de política é conservadora e case-insensitive para impedir aliases em Windows; nomes reservados, ADS e caminhos com ponto ou espaço final também são recusados.

## Subprocessos e segredos

`run_subprocess` exige uma `ToolPolicy` explícita, aceita apenas argv estruturado, chama o processo com `shell=False`, captura stdout/stderr com limite, registra exit code, timeout e duração e inclui `model`/`effort` na evidência. O processo filho recebe somente uma allowlist pequena de variáveis operacionais necessárias, como `PATH`, `SYSTEMROOT`, diretórios temporários e locale. `PYTHONPATH`, credenciais e demais variáveis não aprovadas não são encaminhadas. Executáveis de shell são bloqueados pelo nome normalizado, incluindo variantes Windows como `bash.exe` e `sh.exe`. O módulo não grava essa evidência em disco.

## Limitação no Windows

A fundação é local e não instala serviço Windows. A aplicação direta em Windows deve ser feita pelo Runner aprovado dentro do worktree isolado e com a mesma validação; o chamador deve fornecer um processo local controlado e um `cwd` válido. Integração com serviço Windows, GitHub auth, promoção canônica e execução arbitrária continuam fora deste incremento.

## Promoção

O resultado staged deve ser revisado e validado por uma camada posterior antes de qualquer integração com Git/PR ou telemetria durável. Este módulo não deve copiar `auth.json`, armazenar tokens nem aceitar comandos shell montados a partir de texto do modelo.
