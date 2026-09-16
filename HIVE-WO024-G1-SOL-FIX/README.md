# HIVE WO-024-G1 Sol Fix

Pacote preparado diretamente por Sol a partir dos quatro arquivos WIP fornecidos pelo usuário.

Correções aplicadas:
- WO-021 histórico: exemplo de futuro desconhecido migrou de WO-024 para WO-025.
- WO-022 histórico: exemplo de futuro desconhecido migrou de WO-024 para WO-025.
- WO-023 renderer/teste: exemplos atuais de futuro desconhecido agora são WO-025/WO-025-P.
- Harness WO-023-P: referência inexistente `_REAL_WO023P_SCOPE` substituída pela função real capturada antes do monkeypatch.
- Nenhum Project Brain, migration, produto, dashboard, workflow ou ruleset é alterado.

Validação isolada feita por Sol:
- Python AST: PASS nos três arquivos .py.
- JSON parse: PASS no schema.
- Os quatro testes exatos que estavam falhando: 4 PASS.

Como aplicar:
1. Extraia este pacote.
2. Abra PowerShell na raiz do repositório HIVE.
3. Execute:
   powershell -ExecutionPolicy Bypass -File "<pasta-extraida>\APPLY-WO024-G1-SOL-FIX.ps1"
4. Depois diga no chat: `continue o WO-024-G1 daqui`.

O script é fail-closed:
- exige HEAD exato 44c61e999c89a6b6ba6c28377cea415cad3d1cef;
- exige árvore rastreada limpa;
- usa branch governance/wo024-g1-sol-recovery;
- exige exatamente quatro arquivos alterados;
- roda somente os quatro testes focados antes do commit/push.
