# Self-hosted deployment

Copy `.env.example` to `.env` and configure the providers required for your research.
Keep the environment file local. Run `docker compose up --build -d` for port 8000,
or `docker compose --profile web up --build -d` to also serve Next.js on port 3000.

Bind mounts persist `my-docs/`, `outputs/`, `logs/` and `data/` in this checkout.
Reports and chat now live in SQLite (`TDR_DATABASE_URL`, default `sqlite:///./data/tdr.db`).
Compose defaults to `/usr/src/app/data/tdr.db` inside the mounted data directory.
Preserve these directories during upgrades. `REPORT_STORE_PATH` only identifies
the retired JSON history file; the API never writes it.

Before first startup initialize the schema:

```sh
docker compose run --rm --build research python scripts/migrate_report_store.py --init-only
```

For an existing `reports.json`, stop old writers and follow [history migration](migration.md)
instead. API startup validates schema and legacy import receipts; it refuses an
uninitialized/incompatible database or an unimported/changed legacy file. API
processes do not perform schema upgrades. Keep the SQLite database on a local
disk; this release does not provide a distributed database or task queue.

`GET /api/reports` retains `{reports: [...]}` and accepts optional `limit` (1–500)
and `offset` (nonnegative); omitted limit retains the legacy full-list behavior.
Results sort by descending timestamp then ascending report ID. Existing clients
may continue using `report_ids`. The Next.js proxy already forwards these query
parameters. Report records include `origin`, `lineage_status` and `report_version`;
all existing reports have unavailable evidence lineage.

Chat appends and report patches execute in write transactions. A reply generated
against a report changed during the model call returns HTTP 409 and is not attached
to the newer report; reload the current report before retrying.

For isolated storage acceptance against a locally built image:

```sh
docker build -t tdr-a1-validation:local .
python scripts/verify_a1_container.py --image tdr-a1-validation:local --out evals/results/a1-container/summary.json
```

The host script requires Python and a Linux Docker engine. It uses generated
history and temporary named volumes, disables the runtime network, verifies the
real API and restore flow, then removes only resources tagged for its own run.
It never applies a migration to the deployment's mounted `data/` directory.

Set `CORS_ALLOW_ORIGINS` for a remote frontend and `NEXT_PUBLIC_TDR_API_URL` to an
API address reachable from the browser. `BACKEND_URL` is the backend address
used inside Docker by Next.js. Rebuild the frontend after public settings change.

Images are `traceable-deep-researcher:local` and `traceable-deep-researcher-web:local`.
Use Docker Compose v2 with BuildKit enabled. The first backend build downloads
Chromium, Firefox and Python dependencies; later builds reuse download caches.
No AWS/Terraform deployment or analytics service is configured.
The application assumes a trusted operator; add your own authentication and
access control before public exposure. See SECURITY.md.
