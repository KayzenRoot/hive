# Repository indexing

Repository indexing is a deterministic, project-scoped foundation for future HIVE context construction.

## Contract

`POST /api/v1/projects/{project_id}/index` starts a synchronous index run and returns its durable summary. The latest summary is available through either `GET /api/v1/projects/{project_id}/index` or `GET /api/v1/projects/{project_id}/index/status`.

The response records discovered, indexed, reused, changed, added, removed and parsed file counts, together with the current symbol count and run status (`COMPLETED` or `FAILED`). A failed run preserves the last valid durable file and symbol metadata.

## Deterministic behavior

- Only files returned by `git ls-files --cached` are considered. Untracked, ignored and `.git` internals are not crawled.
- Every file is addressed by its canonical repository-relative POSIX path and SHA-256 of the current working-tree bytes.
- Git branch, commit, index blob object, mode and working-tree status are retained as provenance.
- File count, per-file size and total repository byte limits prevent unbounded reads.
- The configured `HIVE_PROJECTS_ROOT` boundary is revalidated for every tracked path. Symlink targets outside the project fail closed.
- The current index contains metadata only; complete source snapshots are not stored in PostgreSQL.

## Incremental reconciliation

The first run creates all current file metadata and parses changed Python files. Later runs compare the current content hash and size with the previous durable row. Equal files are reused and Python is not reparsed. Added, changed and removed paths update only their affected metadata. Removed files are marked non-current and their symbols are deleted; symbols for changed files are replaced atomically.

A Python symbol contains its name, qualified nested identity, kind (`class`, `function` or `async_function`) and line range. The parser uses the Python 3.12 standard-library AST.

## Failure and persistence

Inventory, source-stability, Git-head and AST failures produce a durable `FAILED` run. Reconciliation happens in one PostgreSQL transaction, so malformed Python, a source mutation during indexing or a database write failure cannot partially replace a previously valid index. PostgreSQL is canonical; Redis is not involved.

Repository indexing itself remains responsible only for durable file and symbol
metadata. Semantic embeddings and references are derived by the separate
retrieval layer documented in [`docs/RETRIEVAL-SEMANTIC-HYBRID.md`](RETRIEVAL-SEMANTIC-HYBRID.md).
Submodules are reported as unsupported for this increment rather than
recursively indexed.

See the canonical project decisions and scope in [`docs/project-brain/04-ARCHITECTURE.md`](project-brain/04-ARCHITECTURE.md), [`docs/project-brain/06-ACCE-TOKEN-STORAGE-OPTIMIZATION.md`](project-brain/06-ACCE-TOKEN-STORAGE-OPTIMIZATION.md) and [`docs/project-brain/18-REPOSITORY-INDEXING.md`](project-brain/18-REPOSITORY-INDEXING.md) when that canonical source is available.
