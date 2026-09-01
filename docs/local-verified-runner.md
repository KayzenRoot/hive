# Local Verified Runner Foundation

Este documento descreve o incremento WO-004. O nÃºcleo em `backend/app/runner.py` recebe um change set estruturado, valida-o deterministicamente e produz evidÃªncia staged. Ele nÃ£o promove alteraÃ§Ãµes para o estado canÃ´nico, nÃ£o cria PR e nÃ£o persiste tokens, credenciais ou dados de autenticaÃ§Ã£o.

## Fluxo staged

1. O executor fornece operaÃ§Ãµes `create`, `replace` ou `delete`, sempre com caminhos relativos.
2. `admit_change_set` resolve o workspace, aplica a polÃ­tica allow/deny, verifica limites e registra um snapshot SHA-256 do estado anterior. A admissÃ£o nÃ£o escreve arquivos.
3. `apply_admitted` executa somente uma admissÃ£o vÃ¡lida. `create` usa criaÃ§Ã£o exclusiva; `replace` e `delete` revalidam o hash imediatamente antes da operaÃ§Ã£o.
4. `verify_changed_files` compara os hashes esperados com o estado final e identifica arquivos extras criados, removidos ou alterados fora da admissÃ£o.
5. `StagedRun`, `ApplyResult` e `ProcessEvidence` formam a evidÃªncia para futura promoÃ§Ã£o, PR e telemetria. `promoted` permanece sempre falso nesta fundaÃ§Ã£o.

O change set Ã© limitado por quantidade de operaÃ§Ãµes e bytes de conteÃºdo. Caminhos vazios, absolutos, com drive/UNC, separador invertido, `.` ou `..` sÃ£o recusados. A allowlist, quando configurada, Ã© obrigatÃ³ria; a denylist sempre tem precedÃªncia. Caminhos conflitantes dentro do mesmo change set tambÃ©m sÃ£o recusados. A comparaÃ§Ã£o de polÃ­tica Ã© conservadora e case-insensitive para impedir aliases em Windows; nomes reservados, ADS e caminhos com ponto/espaÃ§o final tambÃ©m sÃ£o recusados.

## Subprocessos e segredos

`run_subprocess` exige uma `ToolPolicy` explÃ­cita, aceita apenas argv estruturado, chama o processo com `shell=False`, captura stdout/stderr com limite, registra exit code, timeout e duraÃ§Ã£o e inclui `model`/`effort` na evidÃªncia. O processo filho recebe somente uma allowlist pequena de variÃ¡veis operacionais necessÃ¡rias, como `PATH`, `SYSTEMROOT`, diretÃ³rios temporÃ¡rios e locale. `PYTHONPATH`, credenciais e demais variÃ¡veis nÃ£o aprovadas nÃ£o sÃ£o encaminhadas. O mÃ³dulo nÃ£o grava essa evidÃªncia em disco.

## LimitaÃ§Ã£o no Windows

A fundaÃ§Ã£o Ã© local e nÃ£o instala serviÃ§o Windows. AplicaÃ§Ã£o direta em Windows deve ser feita pelo Runner aprovado dentro do worktree isolado e com a mesma validaÃ§Ã£o; o chamador deve fornecer um processo local controlado e um `cwd` vÃ¡lido. IntegraÃ§Ã£o com serviÃ§o Windows, GitHub auth, promoÃ§Ã£o canÃ´nica e execuÃ§Ã£o arbitrÃ¡ria continuam fora deste incremento.

## PromoÃ§Ã£o

O resultado staged deve ser revisado e validado por uma camada posterior antes de qualquer integraÃ§Ã£o com Git/PR ou telemetria durÃ¡vel. Este mÃ³dulo nÃ£o deve copiar `auth.json`, armazenar tokens nem aceitar comandos shell montados a partir de texto do modelo.
