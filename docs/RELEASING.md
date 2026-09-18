# Releasing HIVE

Releases use Semantic Versioning as defined in [VERSIONING.md](VERSIONING.md).
The release train is governed by HIVE-ADR-019
(`docs/project-brain/16-DECISIONS-LEDGER.md`): exact-head audit, squash-only
protected merge, mandatory post-merge CI and a validated GitHub Release.

Cryptographic tag signing and build-provenance attestations are **not claimed**:
the tag is annotated but unsigned, and the workflow does not fabricate signing,
SBOM or attestation evidence.

## Release preparation

1. Create a release branch from the accepted `main` and make the version,
   changelog, release-note and documentation changes.
2. Run the full local validation:

   ~~~bash
   python scripts/verify_release_metadata.py
   python scripts/validate.py
   python scripts/prepare_release.py --tag vX.Y.Z --ref HEAD \
     --output-dir tmp/release-dry-run --dry-run
   ~~~

3. Open one Ready PR. The PR body must contain exactly one
   `<!-- HIVE-WORK-ORDER: ... -->` marker and one
   `<!-- HIVE-AUTHORIZED-BASE: ... -->` marker, and must stop before merge.
4. Sol audits the exact HEAD. Only a clean, mergeable PR with every required
   check green (Validate, Integration health, Review Evidence) and zero
   unresolved threads is squash-merged.

## Post-merge and publication

Publication is governed by `.github/workflows/release-publisher.yml`. It runs
only after the repository CI workflow completes successfully for a push to
`main`. The publisher then fails closed unless all of these statements remain
true:

- the successful CI head is still the current protected `main`;
- `VERSION` is strict stable SemVer and has a matching release-candidate
  receipt plus an explicitly armed publish request;
- the release-publisher squash commit has the exact authorized parent recorded
  by the publish request;
- dependency-security evidence reports PASS with zero applicable unresolved
  CRITICAL/HIGH findings;
- the tag/release is absent, or an interrupted prior attempt can be resumed
  without changing the tag target.

Before publication the publisher reruns release-metadata verification,
deterministic validation and the integration smoke test on that exact commit. It
then creates an **annotated** tag, builds `hive-vX.Y.Z.zip`,
`hive-vX.Y.Z.zip.sha256` and `hive-vX.Y.Z.manifest.json`, generates the review
bundle and publishes a stable GitHub Release.

After publication, `scripts/finalize_release_receipt.py` generates
`hive-vX.Y.Z.release-receipt.json` with the exact release commit, annotated tag
object, publication metadata, post-merge CI lineage and SHA-256/size records for
the released artifacts. That receipt is attached to the GitHub Release. The
publisher is idempotent: once the tag, release and final receipt exist, later CI
runs no-op.

The existing tag-driven `.github/workflows/release.yml` remains an audited
fallback for an explicitly authorized external/manual annotated-tag push. The
normal HIVE path is the governed publisher above; do not create an ad-hoc tag
before post-merge CI is green.

## Local dry-run

~~~bash
python scripts/prepare_release.py --tag vX.Y.Z --ref HEAD \
  --output-dir tmp/release-dry-run --dry-run
~~~

Release packages are generated from `git archive` and exclude local data,
secrets, keys, `node_modules`, review bundles, temporary files and user-owned
project data. Release bundles contain installation-relevant source, config and
documentation plus SHA256 checksums; GitHub source archives remain available
automatically.

Never write release notes that claim untested functionality, and never present a
release candidate as published before the tag workflow has completed.
