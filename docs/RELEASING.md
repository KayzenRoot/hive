# Releasing HIVE

Releases use Semantic Versioning. HIVE V0.1 completion maps to v0.1.0 only
after its Definition of Done is objectively satisfied. The bootstrap target is
v0.0.1-bootstrap and must be a pre-release.

## Before approval

Run the local validation suite, generate a review bundle, and complete the Sol
audit. Do not create a public release or tag during the bootstrap increment.

## Approved release process

After approval, from a clean checkout with authenticated GitHub CLI:

~~~bash
git checkout main
git pull --ff-only
git tag -a v0.0.1-bootstrap -m "HIVE bootstrap foundation"
git push origin v0.0.1-bootstrap
~~~

The tag workflow validates backend, dashboard, Compose configuration, and
secret checks before creating the GitHub pre-release and attaching the generated
review bundle. A validation failure prevents publication.

Before publication, the workflow verifies that the tag without v exactly
matches VERSION, resolves notes from docs/releases/<tag>.md, and creates
hive-<tag>.zip plus hive-<tag>.zip.sha256. A missing notes file, version
mismatch, or forbidden package path stops the workflow before gh release create.
The package is generated from git archive and excludes local data, secrets,
node_modules, review bundles, and temporary files.

For a local non-publishing dry-run:

~~~bash
python scripts/prepare_release.py --tag v0.0.1-bootstrap --ref HEAD --output-dir tmp/release-dry-run --dry-run
~~~

Release bundles must include installation-relevant source/config/docs and
SHA256 checksums. GitHub source archives remain available automatically.
Never write release notes that claim untested functionality.
