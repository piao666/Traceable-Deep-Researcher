# Identity migration — 2026-10-14

- Product: Traceable Deep Researcher; maintainer: Piao666.
- Repository: https://github.com/piao666/Traceable-Deep-Researcher.
- Python distribution: `traceable-deep-researcher` (local).
- Python module: `traceable_deep_researcher`.
- Python/React class or component: `TraceableDeepResearcher`.
- Frontend package: `traceable-deep-researcher-ui` (private).
- Configuration prefix: `TDR`; browser API setting: `TDR_API_URL`.

This is an intentional breaking rename. Update imports, environment variables
and browser API settings. Report IDs and stored report schemas are unchanged.
The repository folder is Traceable-Deep-Researcher; Docker/distribution names
use lowercase hyphenated identifiers.

Removed: organization-specific AWS deployment, upstream blogs and marketing,
analytics, obsolete editor rules, and unimplemented plugin distribution stubs.
Applicable licenses and upstream source attribution remain in LICENSE,
UPSTREAM.md and vendored files.

The original two local projects remain unchanged. This checkout does not copy
their real environment secrets, runtime reports or the reference evidence engine.

## A1 report history migration — 2026-10-26

The API stores report history and chat in SQLite. Since M1/A2–A7, tasks,
checkpoints, events and export jobs are also persisted (schema v4); history is
written by the server. Old JSON stays untouched and is never dual-written.

The CLI defaults to **dry-run**: it validates the entire JSON and checks IDs,
timestamps, chats, duplicate JSON keys and conflicts. It does not create a DB,
upgrade schema, write backups or print report bodies. Exit code 0 means valid/success;
2 means invalid input, a conflict, incompatible schema or an execution error.
The API refuses to start before explicit schema setup/history import.

### Existing Docker installation

Schedule a short maintenance window. Stop **all** old API workers and any external
script that writes the JSON, and prevent UI writes until the cutover is verified.
Build the new backend, then run:

```sh
docker compose stop web research
docker compose build research
docker compose run --rm --no-deps research python scripts/migrate_report_store.py
docker compose run --rm --no-deps research python scripts/migrate_report_store.py --apply
docker compose up -d research
docker compose --profile web up -d web
```

Inspect the dry-run `records`, `errors`, `conflicts`, `insert`, `update` and `skip`
before applying. A nonzero result requires correction; do not remove the old JSON
or initialize an empty replacement to bypass the error. Back up the full data,
outputs and documents directories before changing an existing deployment.

`--apply` first creates/checks the schema, then backs up the exact original JSON
bytes to `data/backups/reports.json.<sha256>.bak` and writes a SHA-256 manifest.
Reports, immutable content versions, chats and import receipts commit in one
transaction; any failure rolls back all imported records. The schema setup is a
separate transaction and may remain initialized after an import error. A complete
backup remains available even after failure. Source changes detected during import
abort the transaction; maintenance-mode exclusion of all old writers is still required.

IDs, timestamps, chat payloads and extension fields survive import. Imported history
is marked `origin=legacy_import` and `lineage_status=unavailable`; no task events,
research attempts or evidence are invented. Repeat imports of the same source hash
skip previously processed IDs, including reports later intentionally deleted.
Same-ID/different-content conflicts never overwrite the database by default.

For an intentionally staged import, re-run the final dry-run during maintenance.
New IDs can be added normally. To apply updates from the **same source path**, use
`--update-imported` on both dry-run and `--apply`; this only updates targets still
equal to the last import from that source. A later database-side change produces a
conflict, requiring manual reconciliation. Do not rename/move the source between
staged imports: source identity includes its resolved path. Do not resume old JSON
writers after switching the application to SQLite.

### Local commands and fresh installations

```powershell
# Dry-run; no database or backup is created.
.venv/Scripts/python.exe scripts/migrate_report_store.py --source data/reports.json
# Apply after stopping old writers.
.venv/Scripts/python.exe scripts/migrate_report_store.py --source data/reports.json --apply
# Fresh installation with no old history: initialize schema only.
.venv/Scripts/python.exe scripts/migrate_report_store.py --init-only
```

Optional `--database-url`, `--source`, `--backup-dir` override the environment/defaults.
New storage settings use `TDR_DATABASE_URL`; `REPORT_STORE_PATH` is a legacy source
locator only. `--init-only` does not import old JSON and cannot bypass the API's
legacy-file check. Do not run a real migration from a test suite.

The local CLI reads the process environment. If the application obtains a custom
`TDR_DATABASE_URL` from `.env`, export the same value or pass `--database-url`
explicitly to the local command. Docker Compose injects the configured environment.

Verify report count/IDs, a Chinese report, chat history, pagination, and persistence
after replacing the backend container on the same volume before reopening writes.
Default list behavior is retained; pagination is opt-in (`limit`, `offset`).

### Backup, restore and rollback

Stop all database writers before taking a filesystem backup of `data/` (including
any `tdr.db-wal`/`tdr.db-shm` files). Restore the complete backup into a separate
directory and validate it with the matching application/CLI before switching mounts.
Copying only `tdr.db` while WAL writers are active can lose recent transactions.

On upgrade failure keep the database and backups; use an application compatible
with its schema. Do not delete SQLite and silently fall back to a stale JSON file.
If rollback to the old JSON-only release is unavoidable, keep maintenance mode,
retain the entire SQLite backup and explicitly export/reconcile current reports
and chats into an old-format JSON snapshot first. This batch provides no automatic
SQLite-to-JSON downgrade command. Rollback before any new SQLite writes may use the
verified original JSON backup; after new writes the original backup is stale.

## Schema v1 → v4 task upgrade — 2026-10-30

Read the implementation and acceptance records before changing deployment data.
Stop all writers, retain the old application image, and back up outputs/documents.
The migration validates known schema checksums before alteration. For a valid
older SQLite schema, `--init-only` automatically creates a consistent backup
using SQLite's backup API, including committed WAL contents, before the DDL
transaction. Unknown versions/checksums are refused. A failed DDL transaction
rolls back; keep the backup even after a successful upgrade.

```sh
docker compose stop web research
docker compose build research
# Existing database, no legacy JSON to import:
docker compose run --rm --no-deps research python scripts/migrate_report_store.py --init-only
docker compose up -d research
docker compose --profile web up -d web
```

If the legacy JSON exists, use the dry-run/apply flow above instead. Do not
replace the database or remove JSON to bypass validation. The upgrade prints
`database_backup` when it creates one. `--backup-only` can take a consistent
backup without schema changes. Restore a backup to an isolated directory and
check its version/counts before use. For rollback to schema v1, stop all writers
and restore the verified pre-upgrade database **with the matching old image**;
first preserve the new database and files, because v1 cannot retain new tasks.
Never run the v1 image against the upgraded v4 database.

Local deployment inspection on 2026-10-30 found schema v1, 0 reports, 0 chats,
and no `reports.json`. There was consequently no legacy JSON to import; a
schema upgrade still requires the consistent backup and count checks above.
After the initial automatic-approval rejection, the user explicitly authorized
service interruption and actual DB migration. The local cutover is now applied:
schema v4, integrity ok, reports/chats still 0, no legacy JSON import required.
The consistent pre-upgrade backup is
`data/backups/tdr-6ffcef5fecad400082d760983405d814.sqlite3`;
restoring it into an independent in-memory database confirms schema v1, integrity
ok and matching counts. New frontend/backend containers are running on ports
3000/8000; GET-only application/proxy checks pass. Old image tags
`:pre-m1-20261030` remain available for a controlled rollback with that backup.
