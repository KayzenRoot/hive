# WO-022 Full Control Center

The full read model is exposed at
`GET /api/v1/control-center/projects/{project_id}/full`.

`backend/app/control_center_full.py` composes the existing project registry,
repository index, PostgreSQL telemetry, retrieval corpus, memory lifecycle,
CAS storage observations and service health checks. It does not write state,
call model providers, or treat Redis as canonical. All histories are bounded
to 100 points and missing data is represented explicitly as `UNKNOWN` or
`UNAVAILABLE`.

Canonical project intelligence requires the checkpoint sections `STATUS`,
`IN PROGRESS`, `PENDING` and `NEXT STEP` and the scope section
`NECESSARY — V0.1` to be explicitly present. A missing, blank or malformed
mandatory section renders `checkpoint-scope-dod` as `UNAVAILABLE` with
`git:HEAD-blob:` provenance instead of an empty list or a zero count.

The dashboard surface is integrated as the **Full Control Center** tab in
`dashboard/src/ControlCenter.tsx` and rendered by
`dashboard/src/ControlCenterFull.tsx`.
