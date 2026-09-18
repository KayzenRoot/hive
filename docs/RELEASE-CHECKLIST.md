# Release checklist

This checklist is the operational companion to [RELEASING.md](RELEASING.md) and
[VERSIONING.md](VERSIONING.md). Every step is deterministic; a failure stops the
release.

## 1. Preflight

- [ ] `origin/main` is the accepted base and the release branch descends from it.
- [ ] No open security blockers; zero unresolved CRITICAL/HIGH findings.
- [ ] Working tree clean; no secrets, `.env` files or runtime data staged.

## 2. Version bump

- [ ] `VERSION` updated to the exact stable SemVer.
- [ ] Backend (`backend/app/__init__.py`, `backend/app/config.py`) and dashboard
      (`package.json`, `package-lock.json`) version surfaces updated.

## 3. Changelog and notes

- [ ] CHANGELOG.md has exactly one `## [X.Y.Z]` heading with evidence-backed
      entries.
- [ ] `docs/releases/vX.Y.Z.md` exists and starts with an explicit
      `Status: Release candidate ...` (never claims Published before publication).

## 4. Local validation

- [ ] `python scripts/verify_release_metadata.py`
- [ ] `python scripts/validate.py`
- [ ] `python scripts/prepare_release.py --tag vX.Y.Z --ref HEAD --output-dir tmp/release-dry-run --dry-run`
      produces ZIP, SHA256 and manifest.

## 5. PR audit

- [ ] PR Ready (not Draft), exactly one work-order marker and authorized-base
      marker, zero unresolved threads.
- [ ] Validate, Integration health and Review Evidence PASS on the exact HEAD.
- [ ] Native auto-merge UNARMED; ruleset 21934284 unchanged.

## 6. Merge and post-merge

- [ ] Sol exact-head audit; SQUASH merge only.
- [ ] Mandatory post-merge CI PASS on the exact new `main` SHA.

## 7. Governed publisher

- [ ] An armed `.engineering/release/HIVE-VX.Y.Z-PUBLISH-REQUEST.json` exists
      and records the exact authorized parent of the release-publisher squash.
- [ ] Release Publisher starts only from successful push CI on `main` and
      proves that CI head is still current protected `main`.
- [ ] Release metadata verification, deterministic validation and integration
      smoke PASS again on the exact release commit.
- [ ] Annotated tag `vX.Y.Z` targets the exact accepted release commit.
- [ ] GitHub Release is published as stable, not draft/prerelease, with ZIP,
      SHA256, manifest and review bundle.
- [ ] Publisher verifies the release URL, tag target and required asset names.

## 8. Receipt and closure

- [ ] `hive-vX.Y.Z.release-receipt.json` is attached to the GitHub Release and
      records the actual tag object, release commit, release URL, publication
      time, post-merge CI, publisher workflow run and artifact SHA-256 values.
- [ ] A repeated publisher run is idempotent and does not move/recreate the tag.
- [ ] Do not rewrite accepted Project Brain or historical release history.
