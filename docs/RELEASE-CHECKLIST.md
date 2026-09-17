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

## 7. Tag and release

- [ ] Annotated tag `vX.Y.Z` pushed from the exact accepted release commit.
- [ ] Release workflow validation, integration smoke, package, checksum and
      manifest all PASS on the tag commit.
- [ ] GitHub Release published with ZIP, SHA256, manifest and review bundle.
      Stable releases are not marked prerelease.
- [ ] Verify the release URL, tag target, asset names and checksums.

## 8. Receipt and closure

- [ ] Record the final immutable release receipt/provenance with the actual tag
      object, release URL, publication time and artifact checksums.
- [ ] Do not rewrite accepted Project Brain or historical release history.
