## Work order and identity

- Work order: add exactly one `HIVE-WORK-ORDER` marker comment in this body.
  Governed release/preparation work orders additionally require exactly one
  `HIVE-AUTHORIZED-BASE` marker with the authorized lowercase 40-hex base SHA.
- Authorized base SHA:
- Branch:
- Exact HEAD SHA at handoff:

## Scope

- In scope:
- Out of scope:

## Change classification

- [ ] `1.0.x` patch — backward-compatible fix, security, dependency,
      documentation or bounded operational change
- [ ] `1.x.0` minor — backward-compatible capability accepted through normal
      HIVE governance
- [ ] `2.0.0` major — breaking public API, schema or operational contract change

## Compatibility, migrations and data

- Public API / operational contract impact:
- Migration head before -> after:
- Data or user-owned state impact:

## Test matrix

| Check | Command | Result |
|---|---|---|
| Release metadata coherence | `python scripts/verify_release_metadata.py` | |
| Deterministic validation | `python scripts/validate.py` | |
| Integration health | `python scripts/integration_health.py` | |
| Dashboard | `npm run lint && npm run typecheck && npm run test:run && npm run build` | |

## Security

- Secrets, credentials and local data handling:
- New attack surface or trust-boundary changes:
- Security automation triggered by this PR:

## Release notes

- [ ] Not release-affecting
- [ ] Release-affecting: `docs/releases/vX.Y.Z.md` and the CHANGELOG entry are
      updated and coherent with `VERSION`

## Exact-head evidence

- Validate / Integration health / Review Evidence run IDs:
- Native auto-merge: UNARMED
- Ruleset 21934284: unchanged

## Rollback plan

Describe how to revert this change safely, including any data or migration
considerations.
