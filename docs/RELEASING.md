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

After the squash merge and a green post-merge CI run on the exact new `main`
SHA, publish from a clean checkout with authenticated GitHub CLI:

~~~bash
git checkout main
git pull --ff-only
git tag -a vX.Y.Z -m "HIVE vX.Y.Z"
git push origin vX.Y.Z
~~~

The tag commit must equal the accepted release commit (the current `main`
HEAD). The release workflow fails closed before publication when:

- the tag is not annotated or does not point at the pushed commit;
- `VERSION` does not exactly match the tag without `v`;
- `docs/releases/vX.Y.Z.md` or the CHANGELOG `## [X.Y.Z]` section is missing;
- deterministic validation or the integration smoke test fails;
- the package misses a required file or contains forbidden paths.

The workflow then builds `hive-vX.Y.Z.zip` plus `hive-vX.Y.Z.zip.sha256` and a
machine-readable `hive-vX.Y.Z.manifest.json` from `git archive`, and attaches
the package, checksum, manifest and review bundle to the GitHub Release. A
stable release such as `v1.0.0` is never marked prerelease.

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
