# Release notes

This directory holds one release-note document per published version, named
after the immutable tag: `vX.Y.Z.md`.

- `v1.0.x` patch releases document fixes, security updates, dependency
  maintenance and bounded operational corrections.
- `v1.x.0` minor releases document backward-compatible capabilities accepted
  through normal HIVE governance.
- `vX.0.0` major releases document breaking public contract changes and the
  required migration or upgrade path.

Every release must keep `VERSION`, the release note, the CHANGELOG heading and
the README latest-stable identity coherent; `scripts/verify_release_metadata.py`
enforces this deterministically in the Validate gate.

Start new notes from [TEMPLATE.md](TEMPLATE.md). A release note must begin with
an explicit `Status:` line:

- `Status: Release candidate (not published).` while preparing the release.
- `Status: Published.` only after the GitHub Release exists, together with the
  final release receipt under `.engineering/`.

Historical notes are immutable evidence. `v0.0.1-bootstrap.md` describes the
historical bootstrap pre-release and keeps its original meaning; a correction is
a new patch release or an explicitly marked erratum, never a rewrite.
