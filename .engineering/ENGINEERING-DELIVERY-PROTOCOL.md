# HIVE Engineering Delivery Protocol

## Purpose

Este protocolo governa incrementos em um projeto HIVE existente. Ele estabelece
baseline verificável, contexto bloqueado, escopo explícito, evidência reproduzível
e revisão independente sem transformar uma adoção de processo em limpeza ou
reescrita de produto.

O protocolo complementa as instruções existentes em `AGENTS.md` e preserva a
fonte canônica em `docs/project-brain/`. Em caso de conflito, a hierarquia
canônica vigente continua prevalecendo.

## Autoridade e estado

A hierarquia existente em `docs/project-brain/00-README-UPLOAD-ORDER.md` é:

1. último `13-CHECKPOINT.md` aprovado;
2. `16-DECISIONS-LEDGER.md`;
3. `03-SCOPE.md`;
4. `15-DEFINITION-OF-DONE.md`;
5. `04-ARCHITECTURE.md`;
6. `02-REQUIREMENTS.md`;
7. demais fontes do projeto.

O executor pode produzir apenas estado staged/proposto. Não pode promover
checkpoint, decisão ou outra canonical truth. Informação sem evidência deve ser
marcada `PROPOSED`, `UNKNOWN` ou `NEEDS OWNER CONFIRMATION`.

## Ciclo obrigatório

Todo Work Order deve seguir esta sequência:

1. **Inspecionar:** identidade do repositório, branch padrão, HEAD, linguagens,
   frameworks, package/build system, testes, lint, typecheck, build, CI,
   deployment, banco/migrations, instruções e fontes canônicas.
2. **Fixar contexto:** registrar o SHA exato do baseline e fingerprints SHA-256
   das fontes críticas no Context Lock.
3. **Definir escopo:** declarar caminhos permitidos, exclusões, riscos, critérios
   de aceite e necessidade de confirmação do owner.
4. **Congelar baseline:** executar os comandos existentes aplicáveis e separar
   falhas/avisos preexistentes.
5. **Implementar:** usar branch curta e modificar somente o Work Order aprovado.
6. **Auditar mudanças:** revisar diff, caminhos, segredos, alterações
   canônicas, migrations, artefatos e impacto comportamental.
7. **Validar:** repetir a validação do baseline e executar as validações novas
   do incremento, quando houver.
8. **Corrigir:** corrigir problemas introduzidos; não absorver bugs de produto
   não relacionados.
9. **Documentar evidência:** produzir o Evidence Bundle com comandos, SHAs,
   resultados, advertências e links verificáveis.
10. **Commit:** criar commit com a mensagem coerente com o Work Order.
11. **Push:** publicar a branch curta correspondente ao ID do Work Order.
12. **PR:** abrir ou atualizar uma PR Ready com o mesmo ID no corpo e links para
   Work Order, Context Lock, Evidence Bundle e Checkpoint Delta.
13. **Handoff:** parar para auditoria independente; não fazer merge, release ou
   promoção canônica sozinho.

## Context Lock e stale context

O Context Lock registra repository, baseline Git SHA, checkpoint fingerprint,
decisions fingerprint, scope fingerprint, Definition of Done fingerprint,
architecture fingerprint e outras fontes críticas relevantes. Fingerprints são
calculados determinísticamente em UTF-8 por SHA-256.

Antes de cada validação final, os fingerprints devem ser recalculados. Se uma
fonte crítica mudar, o estado é `STALE`: o executor deve parar, registrar a
divergência e aguardar um novo lock/Work Order. Não é permitido continuar
silenciosamente.

## Escopo e segurança

- Não remover produção, dependências, migrations, endpoints, jobs,
  configurações, feature flags ou contratos públicos por suspeita de desuso.
- Reflection, DI, plugins, dynamic imports, rotas/configuração dinâmica,
  eventos, serialização, CLI, cron/jobs, migrations, feature flags,
  callbacks/webhooks são considerados potencialmente utilizados até haver
  evidência específica.
- Limpeza só pode ocorrer em Work Order posterior, pequeno e revisado.
- `VERIFIED_DEAD` é a única classificação que pode autorizar remoção futura;
  ainda assim a remoção exige seu próprio escopo e validação.
- Não commitar segredos, `.env`, credenciais, dados runtime ou artefatos de
  usuário.

## Validação e comparação

O Evidence Bundle deve comparar `BEFORE` e `AFTER` para testes, lint,
typecheck, build, integração/E2E e checks relevantes de CI. Uma falha existente
no baseline permanece identificada como preexistente; não deve ser atribuída ao
incremento. Cobertura ausente ou insuficiente deve ser registrada e deve gerar
proposta de characterization tests antes de qualquer limpeza futura.

Os nomes dos required checks do repositório não devem ser inventados. No HIVE,
os checks existentes no momento desta adoção são `Validate`, `Integration
health` e `Review Evidence`; qualquer mudança futura deve ser inspecionada no
Ruleset antes de ser usada.

## GitHub e revisão

O PR deve estar Ready, apontar para base segura, usar o método permitido pelo
Ruleset, manter auto-merge conforme a governança canônica vigente e conter
Evidence Bundle secret-free. O executor não arma auto-merge nem faz merge nesta
adoção. A revisão Sol/independente decide a promoção, conforme ADR-019.

## Artefatos obrigatórios

Para cada incremento, o ID deve ser único e idêntico em Work Order, branch, PR,
Evidence Bundle, Context Lock e Checkpoint Delta:

- Work Order preenchido;
- Context Lock preenchido;
- Evidence Bundle preenchido;
- Correction Delta quando houver correção de evidência;
- Checkpoint Delta proposto, se o incremento tiver impacto de checkpoint;
- reports necessários, incluindo baseline e inventário de limpeza quando o
  Work Order assim exigir.

Os templates em `.engineering/templates/` definem os campos mínimos. Os
artefatos reais ficam em `.engineering/work-orders/`,
`.engineering/context-locks/` e `.engineering/reports/`.

## Condições de parada

Marcar `BLOCKED` e não improvisar se:

- o baseline não puder ser determinado;
- fontes canônicas contraditórias não tiverem hierarquia resolvível;
- houver trabalho não relacionado impossível de isolar;
- o baseline estiver quebrado a ponto de impedir distinguir regressões;
- GitHub necessário estiver indisponível;
- a adoção exigir reescrita arquitetural;
- limpeza não puder ser comprovada como segura;
- for necessária operação destrutiva;
- houver problema `HIGH`/`CRITICAL` não resolvido que impeça continuação
  segura;
- o Context Lock estiver `STALE`.

## Resposta final do executor

O retorno final é em português brasileiro e deve incluir resumo, repository,
branch, base/head SHA, PR, baseline, arquivos alterados, integração do
protocolo, validações BEFORE/AFTER, falhas preexistentes ou introduzidas,
inventário classificado, riscos, Evidence Bundle, Checkpoint Delta, links
GitHub e próximos incrementos em ordem de menor risco. Após o handoff, aguardar
auditoria independente; não iniciar o primeiro cleanup automaticamente.
