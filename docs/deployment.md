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
disk. Tasks use a durable SQLite queue on this host; distributed operation is
not supported. See the schema-v4 upgrade steps in [migration](migration.md).

## Persistent research tasks (M1)

Run exactly one API process (`TDR_API_WORKERS=1`); the container entry point
rejects larger values. It owns one research worker and a separate export worker.
Queued tasks survive replacement. Expired running attempts become interrupted,
then an operator can resume compatible checkpoints. Temporary per-request keys
and inline MCP credentials remain in memory; after process loss create a new
request with those credentials. Environment-configured providers remain usable.

The following settings are implemented; the broader roadmap includes future
settings which must not be mistaken for current switches:

| Setting | Default | Behavior |
|---|---|---|
| `TDR_WORKER_LEASE_SECONDS` | `30` | Research lease; renewed during execution |
| `TDR_WORKER_POLL_SECONDS` | `0.1` | Queue polling interval |
| `TDR_WORKER_SHUTDOWN_SECONDS` | `5` | Bounded graceful shutdown |
| `TDR_HTTP_WAIT_SECONDS` | `30` | Legacy foreground wait; timeout returns 202 |
| `TDR_EVENT_RETENTION` | `20000` | Events per task; 0 retains all; old cursors resync |
| `TDR_EXPORT_MAX_SECONDS` | `180` | Per-format rendering timeout |
| `TDR_EXPORT_RENDERER_VERSION` | `v1` | Export identity; increment after renderer changes |

POST `/api/research` returns 202 and `research_id`. Send `Idempotency-Key` to
retry a lost response safely. GET the task, its `/events?after_seq=...`, or list
with `limit/offset/status`. POST task `/cancel` or `/resume` explicitly. Each
task exposes `/exports`, `/exports/{format}/retry` and an owned download URL.
Next.js proxies all of these without caching. Desktop and mobile open
`/tasks/{id}`; refresh only reconnects. `/history` reads server pages and offers
explicit import of old browser records. Legacy `/report/` and WS `start` delegate
to the same queue; closing the browser does not cancel a task.

The time budget is enforced. Explicit tool/token/cost hard limits, human review,
network-disallowed policies and unresolved managed MCP references are rejected
until their execution adapters are implemented. Multi-agent mode currently only
supports default web sources and final-result recovery. Execution success is not
fact approval or verified evidence lineage. Default request time budget is 300s.

Back up both `data/` and `outputs/`. Independent exports are under
`outputs/exports/`; do not prune them with a generic report cleanup script.
`python scripts/cleanup_orphan_exports.py` lists old unreferenced generated
files; deletion requires explicit `--apply` and preserves active jobs, referenced
files, user filenames and symlinks. Default age threshold is 24 hours.

Offline Linux acceptance:

```sh
docker build -t tdr-task-validation:local .
python scripts/verify_task_container.py --image tdr-task-validation:local
```

The script uses isolated volumes, fixed provider output, no runtime network and
native PDF/DOCX/Markdown generation, then cleans only its labeled resources.

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
