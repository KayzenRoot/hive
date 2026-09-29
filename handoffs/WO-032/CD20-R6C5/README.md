# WO-032 / CD20-R6-C5 — kit de transferência ao Codex

Este ramo **contém somente artefatos de handoff**, não uma implementação nem alteração da branch da WO-032. Foi criado a pedido do proprietário para evitar falhas recorrentes nos downloads de arquivos do chat.

## Artefato

- `hive-r6c5.zip`: PDF, Markdown, patch binário original dos 19 caminhos autorizados e manifesto de hashes.
- SHA-256 do ZIP: `1b73b6db147a1555a86301cb77945e9042c77e79498bc4cde6af810b57d6bc41`
- SHA-256 do patch interno `HIVE_WO032_CD20_R3_PATCH_VERIFICADO.patch`: `a66ca89917af5eb1db436e85dc2fbe5f64820be9b0b117db7028e417cc5ddb95`
- Git blob SHA do ZIP: `12253e744dfa0f8c1f7ab7e9d39859cdbb25fe47`
- Main de referência no momento da transferência: `f51c13487a21f22c7c8e873c42722bfac5fd88f8`

## Uso no Codex

Use o ramo `handoff/wo032-r6c5-artifacts` como **fonte de transporte somente leitura**. Se os downloads falharem, obtenha o kit com Git em um diretório temporário independente, fora do checkout `D:\\Projects\\hive`, com as credenciais GitHub já existentes. Verifique SHA-256 do ZIP e do patch ANTES de usar. Extraia somente depois de validar. Execute o PDF/Markdown do próprio ZIP sem modificar critérios de aceite.

**Restrições:** não aplicar mudanças ao checkout original sujo, não usar a instalação local HIVE 1.0.3 como MCP/RAG/memória, não efetuar indexação/sync/rebind/provider, não operar os dados antigos, não fazer push/PR/merge do produto, não promover checkpoint nem declarar C07 qualificado por conta desta transferência. A WO-032 e a issue #163 permanecem ativas; os gates atuais continuam obrigatórios.

Este ramo de handoff não deve ser mesclado à main e não substitui a auditoria do Evidence Bundle.
