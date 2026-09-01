# Durable Task Intake, CAS and Zstandard

Prompt #003 adds a local-first input boundary for registered projects. The API
accepts PDF, Markdown, UTF-8 TXT and structured text, stores the exact submitted
bytes in `HIVE_DATA_ROOT/cas/sha256/<first-two>/<remaining>.zst`, and records task
and extraction metadata in PostgreSQL. The filename is metadata only and never
participates in the storage path.

## Formats and limits

Uploads use `POST /api/v1/projects/{project_id}/tasks/upload` with a multipart
field named `file` and an optional `title`. Only `.pdf`, `.md`/`.markdown` and
`.txt` are accepted. PDF content must have `%PDF-` magic bytes and is parsed by
the pinned `pypdf` library without executing JavaScript, actions or attachments.
PDFs must contain a usable text layer; OCR is intentionally not implemented.

Structured input uses `POST /api/v1/projects/{project_id}/tasks/text`:

```json
{"title":"Implement auth","text":"...","format":"text"}
```

`format` is `text` or `markdown`. UTF-8 BOM input is supported. CRLF/CR to LF
normalization is used only for the derived text representation; the original
artifact remains byte-for-byte recoverable.

Defaults are bounded and configurable through `.env`:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `HIVE_TASK_MAX_UPLOAD_BYTES` | `10485760` | Maximum streamed upload |
| `HIVE_TASK_MAX_PDF_PAGES` | `100` | Maximum PDF page count |
| `HIVE_TASK_MAX_EXTRACTED_TEXT_BYTES` | `2097152` | Maximum derived text |
| `HIVE_TASK_MAX_STRUCTURED_TEXT_BYTES` | `1048576` | Maximum structured input |
| `HIVE_CAS_ZSTD_LEVEL` | `3` | Bounded balanced Zstandard level |

Input temporary files live under `HIVE_DATA_ROOT/tmp/intake` and are removed on
success and failure. Oversized or invalid input is rejected before a task is
accepted. A valid but textless PDF is retained with `EXTRACTION_FAILED` and
`no_extractable_text`; no text is invented.

## Integrity, deduplication and recovery

The CAS identity is SHA-256 of the exact uncompressed original bytes. Writes
stream into a HIVE-controlled temporary file, use Zstandard with a frame
checksum, verify decompression/hash/size, and publish atomically to the
hash-derived path. Concurrent identical writes converge to one physical blob;
duplicate submissions still create distinct project-scoped task records.

Artifact reads fully decompress and verify the blob before returning a response.
Missing, truncated, tampered or mismatched content fails closed. The API does
not expose arbitrary download-by-hash access: artifact and text routes require
both the owning `project_id` and `task_id`. A database failure after CAS
publication may leave an unreferenced blob; garbage collection is intentionally
out of scope for this increment.

PostgreSQL is the durable metadata and extraction-reuse store. Redis is not
needed to list tasks, retrieve text or recover artifacts. The extraction cache
key includes source digest, extraction kind, extractor/version and relevant
configuration, so identical compatible input can reuse deterministic derived
text without relying on Redis.

## API and metrics

- `GET /api/v1/projects/{project_id}/tasks` lists metadata without large text bodies.
- `GET /api/v1/projects/{project_id}/tasks/{task_id}` returns one project-scoped record.
- `GET /api/v1/projects/{project_id}/tasks/{task_id}/artifact` downloads verified original bytes.
- `GET /api/v1/projects/{project_id}/tasks/{task_id}/text` returns ready derived text.
- `GET /api/v1/storage` returns real global task/blob totals.

Storage metrics distinguish referenced logical bytes (counted per task), unique
logical bytes, physical compressed CAS bytes, unique blob count and the
deduplication delta. Compression delta is `unique logical - physical`; it is
labelled `savings`, `overhead` or `neutral`, and a negative delta is never called
savings.

The Control Center selects a registered project, submits files or structured
text, lists real task states, previews derived text, downloads originals and
shows the same API-backed storage metrics. It does not display token, RAG,
embedding, cache or fabricated progress metrics.

## Operations and troubleshooting

Keep `HIVE_DATA_ROOT` on the persistent secondary disk used by Compose and back
up PostgreSQL plus that root together. After updating HIVE, run the migration
service and inspect:

```powershell
docker compose run --rm migration alembic current
docker compose run --rm migration alembic upgrade head
```

The expected revision for this increment is `0002_task_intake_cas`. If an
artifact download returns an integrity error, preserve the failing blob for
investigation and restore from the paired PostgreSQL/data-root backup; do not
silently change its digest metadata. Redis loss or API recreation must not
remove tasks or originals.

The complete behavior and negative scope are defined by the Prompt #003 review
request; canonical Project Brain documents remain unchanged in this increment.
