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

Release bundles must include installation-relevant source/config/docs and
SHA256 checksums. GitHub source archives remain available automatically.
Never write release notes that claim untested functionality.
