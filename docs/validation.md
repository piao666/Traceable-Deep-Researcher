# Migration validation — 2026-10-15

## M1 persistent tasks, recovery, exports and history — 2026-10-30

The detailed plans were written before their implementations:
[A2/A3](m1-a2-a3-implementation-plan.zh-CN.md),
[A4/A5](m1-a4-a5-implementation-plan.zh-CN.md),
[A6/A7](m1-a6-a7-implementation-plan.zh-CN.md).

- Combined offline regression: **230 passed in 120.30s**, no skips. Covers
  runtime/evals, task contracts/API/worker/leases/events, result adapters, exports,
  report storage/migration/API compatibility and quality metrics.
- Full-dependency Linux stage/connection tests: **42 passed in 14.16s**, no skips;
  one existing langchain-community deprecation warning. Includes real ASGI socket
  cleanup and basic/detailed/deep completed-stage reuse after injected failures.
- Final task image acceptance: **8 checks in 34.39s**, no cleanup errors. Actual
  Linux API and native PDF/DOCX/Unicode Markdown, fixed research boundary,
  durable queue, process kill/replacement, interrupted/resume/cancel and history.
- A1 storage acceptance on schema v4: **13 checks in 64.80s**, no cleanup errors.
  Includes legacy import, backups/restore and missing/unknown schema refusal.
- `node frontend/nextjs/tests/task-events.cjs` passes duplicate/gap/attempt-reset
  and final-body replacement assertions. Next.js production build passes
  compilation, lint, TypeScript and route generation, including `/tasks/[id]`,
  `/history` and the dynamic research proxy.
- Real browser checks against an isolated production frontend and fixed runner:
  reload during research retains one ID and completes; explicit cancel publishes
  no report; mobile uses the same task API; native downloads pass header/Unicode
  checks; clearing browser caches still shows server history. 390×844 screenshot
  inspected, without horizontal overflow. Artifacts are ignored under
  `output/playwright/`; temporary service data is separate from deployment data.
- Real WebSocket testing exposed a cancellation-time queue reference leak; the
  manager now drops ownership before awaits, then joins the sender. Recheck passes.
- All research/search/judge outputs are fixed fixtures. Provider calls: **0**.
  Linux test containers have no runtime external network; browser fixture blocks
  outgoing DNS/connections. No real `.env` or deployment data is used by tests.
- Additional WAL-specific regression: the 10 lease/storage tests pass in 2.94s;
  the new backup case keeps a committed WAL writer open and verifies those pages
  exist in the restored database. No application change followed this check.

Reproduce the host suite with `TDR_BLOCK_NETWORK=1`,
`LANGCHAIN_TRACING_V2=false` and:

```powershell
.venv/Scripts/python.exe -m pytest tests/runtime tests/evals tests/backend/test_task_contracts.py tests/backend/test_task_api.py tests/backend/test_task_worker.py tests/backend/test_task_leases.py tests/backend/test_task_websocket.py tests/backend/test_export_jobs.py tests/backend/test_research_result_adapters.py tests/backend/test_report_repository.py tests/backend/test_report_store_migration.py tests/backend/test_report_storage_api.py tests/backend/test_report_migration_cli.py tests/backend/test_report_chat_route_uniqueness.py tests/backend/test_container_smoke_cleanup.py tests/test_quality_metrics.py -q --tb=short
```

In a full-dependency Linux test image, mount the current backend/core/multi_agents
and tests read-only, use `--network none`, then run:

```sh
python -m pytest tests/integration tests/test_deep_research_parsing.py tests/test_planning_sources.py -q --tb=short
python scripts/verify_task_container.py --image tdr-task-validation:20261030
python scripts/verify_a1_container.py --image tdr-task-validation:20261030
```

The last two commands run on the Docker host, not inside its test container.
The minimal host venv is insufficient for the integration suite; the production
dependency image supplies the actual research classes and native export libraries.

Scope limits: manual resume, single API process/research worker; multi-agent
final-result checkpoint only. Human-review/graph-node recovery, static/embedded
entry modernization, evidence lineage and live model quality remain M2–M4.
Incomplete remote calls can be repeated and charged; these fixtures establish
engineering behavior, not model research quality. Commit/push requires an explicit
user request and is separate from these acceptance checks.

### Local deployment cutover (applied after explicit authorization)

- Compose production images for both services built successfully; frontend Docker
  production compilation/type/lint and route generation passed in 98.7s.
- Read-only preflight: schema `[1]`, reports `0`, chat messages `0`, integrity `ok`,
  no legacy JSON. There was no old JSON to import.
- Previous images are retained as `traceable-deep-researcher:pre-m1-20261030`
  (`2858473e8341…`) and `traceable-deep-researcher-web:pre-m1-20261030`
  (`d83674a5d3d9…`). Both services now run the newly built `:local` images:
  backend `98e361366d40…`, frontend `0ce69af21d56…`.
- Automatic approval rejected the command to stop web/research and migrate the
  actual persistent DB: authorization covered implementation/acceptance but did
  not explicitly cover this service interruption and live schema change.
  That initial command did not execute. The user subsequently replied “授权”.
- After that authorization: stopped both services, ran the explicit `--init-only`
  migration, verified its consistent v1 backup, then started the built images with
  `docker compose --profile web up -d --no-build --pull never research web`.
  Actual schema is now `[1,2,3,4]`, integrity `ok`; reports/chats remain `0/0`,
  task/export counts `0/0`. No real research was submitted.
- Backup: `data/backups/tdr-6ffcef5fecad400082d760983405d814.sqlite3`, SHA-256
  `fb89062c0fd311a84d4de073e1cdc967be9140233779ccee54b928043fd0c54b`.
  Restoring with SQLite backup API into an independent in-memory DB confirms v1,
  integrity `ok` and matching report/chat counts. Original backup is unchanged.
- GET checks all return 200: API `/api/research`, `/api/reports` on port 8000;
  frontend `/`, `/history`, `/api/research` and paginated `/api/reports` on port
  3000. Running container image IDs match the built images. Exact migration and
  rollback precautions are in [migration](migration.md). Do not run the v1 image
  against v4; preserve the new database before rollback after any new writes.
- Isolated browser, port 3001 frontend and labeled fixture container/volume/network
  were cleaned up successfully (`cleanup_errors=[]`). Actual upgraded services
  on ports 3000/8000 are running. No provider calls were performed; Git delivery
  is separate and only performed when explicitly requested.

## Completed checks

- Python package installation and public `TraceableDeepResearcher` import.
- FastAPI application import and Python source compilation.
- 574 tests collected. Offline tests ran in separate processes per file to
  avoid inherited module-state pollution on Windows: 570 passed after fixes.
- Two test modules skip: obsolete security-helper APIs and missing Windows
  PDF native libraries. Four live-provider tests in three files were excluded.
- Next.js production build, including TypeScript validation, passed.
- Desktop and 390px mobile views checked for the new identity and legible links.
- Local HTTP smoke checks passed for the static homepage, brand SVG, OpenAPI
  title, agent discovery and report listing.
- The embedded page uses its self-hosted origin and preserves an encoded API URL.
- Next.js server routes honor the internal `BACKEND_URL` setting.
- The Next.js Docker image builds and starts as the non-root `node` user.
- Docker Compose configuration and Git whitespace checks pass.
- Original projects: 2,307 audited files matched their hashes and Git state
  matched the pre-migration audit when checked on 2026-10-14.
- Applicable root and vendored license text is unchanged.

## Container integration

Both local production images built successfully:

- `traceable-deep-researcher:local`
- `traceable-deep-researcher-web:local`

All 13 container integration checks passed on 2026-10-15:

- Backend startup and static homepage.
- Text brand SVG.
- OpenAPI product identity.
- Agent discovery endpoint.
- Report creation by the application user.
- Non-root backend runtime.
- Report persistence after replacing the backend container with the same volume.
- PDF export using the Linux native libraries.
- Next.js production homepage.
- Next.js report API proxy over the Docker network.
- Next.js PDF output proxy.
- PWA manifest identity.
- PWA text icon.

The checks used temporary containers, a private Docker network and a named
volume; all were removed afterward. Local images remain available. The Linux
PDF export check passed despite the Windows-specific test-module skip above.

Slow Debian browser downloads were completed using a temporary helper outside
the project to populate the BuildKit APT cache from official package URLs,
checking package sizes and hashes. The helper is not part of the application.

No real model/search-provider research request was made during validation.
No package, image or Git commit was published to a remote registry/repository.

## M0 contracts and offline baseline — 2026-10-25

- Completed 154 targeted offline tests covering runtime/task contracts, dataset
  integrity, task/node engineering replay, evaluator failures, SQLite/LangGraph
  compatibility probes and the existing 39 quality-metric tests; no skips.
- Python compilation and Git whitespace checks passed.
- Next.js production build, lint and TypeScript checks passed with the existing
  lockfile and Dockerfile's `npm ci --legacy-peer-deps` installation rule.
- The shared JSON request/event/subscription fixture passed TypeScript checking;
  an event-version-2 negative control was rejected.
- Eight synthetic task cases and eight node cases passed offline engineering
  replay. These are fixed-output contract checks, not measured model quality.
- A LangGraph SQLite interrupt resumed in a separate Python process. This is an
  isolated compatibility probe, not production task recovery.
- No real research model, search provider or paid judge was called. No production
  API/WS persistence migration was performed and no implementation was committed
  or pushed during this stage.

See [M0 execution record](m0-implementation-plan.zh-CN.md) for scope, commands,
environment constraints and review corrections, and [evaluation usage](evaluation.md)
for reproduction instructions.

## M0 pre-commit recheck — 2026-10-26

- All 154 targeted offline tests passed again after dataset line-ending fixes
  in 19.31 seconds, with no skips.
- Pinned dataset JSON/JSONL files now use LF via `.gitattributes`; manifest pins
  were refreshed and verified against the actual staged Git blobs.
- Shared TypeScript contract fixture, dataset validation (8 task / 8 agent cases)
  and Git whitespace checks passed again.
- The production build result above remains the 2026-10-25 validation; it was not
  rerun for the task-list update.
- The user authorized committing and pushing the M0 implementation and updated
  task lists. Generated Graphify outputs, evaluation runs, caches and databases
  are excluded from the commit.

## M1 / batch 02 / A1 storage — 2026-10-26

- A detailed plan was written before implementation; see
  [A1 execution record](m1-a1-implementation-plan.zh-CN.md) for the exact command
  and remaining acceptance checklist.
- Final targeted offline regression: **190 passed in 28.94 seconds, no skips**.
  This includes 36 A1/report-chat cases and the existing 154 M0 cases.
- Verified SQLite WAL/foreign keys, reopen persistence, immutable content versions,
  pagination, concurrent writes and chat appends, and HTTP 409 for a reply whose
  report version changed during generation.
- Verified dry-run with no new DB/backup, exact-byte backup/hash, duplicate-key and
  corrupt JSON rejection, conflicts, safe incremental import, idempotent retries,
  schema/data rollback, source changes, backup failure and two independent importers.
- API tests exercise real FastAPI routes, lifespan and SQLite with isolated
  research/export imports and fixed chat replies. This is not a full provider-stack
  or production-research validation.
- Affected Python compilation, Git whitespace checks and static Compose YAML/data
  mount checks passed. No frontend source changed; no frontend build was rerun.
- On 2026-10-26 Docker/Podman were unavailable and WSL was not installed. Linux container startup,
  non-root volume permissions, replacement persistence and backup restore remain
  unverified; A1 deployment acceptance is still open.
- No real history was migrated, no paid provider was called, and no commit or push
  was performed. Existing local Graphify analysis files were preserved.

## A1 Linux container acceptance — 2026-10-29

- Docker Desktop 4.96.3 / Engine 29.9.2 is available; docker-desktop runs on WSL2.
- Built the repository Dockerfile as `tdr-a1-validation:20261029`; Compose config
  validation passed. Image ID:
  `sha256:65c9c1bf5248054e4e47d7efe216495f15ea11319e9403edc6dd834db097108f`.
- `scripts/verify_a1_container.py` completed **13 checks in 96.94 seconds**, exit 0,
  with no cleanup errors. All runtime containers used `--network none` and only
  generated temporary volumes, with no real environment file or report data.
- Verified the real default ASGI entry point and non-root writes, strict dry-run,
  exact-byte backup/hash, repeat import, Unicode history/chat, HTTP CRUD/pagination,
  container replacement, backup restore to an independent volume, and startup
  rejection for missing/unknown schema and unimported legacy JSON.
- The image excludes real `.env` and local `evals/results`. A real helper-client
  timeout also confirmed cleanup of the still-running daemon-side container.
- Re-ran the existing offline suite: **190 passed in 55.79 seconds, no skips**.
  Two additional cleanup regressions failed before the fix and passed afterward;
  independent review closed the helper-lifecycle issue.
- Container versions: Python 3.14.10, SQLite 3.40.1, SQLAlchemy 2.1.6,
  FastAPI 0.162.0. Python compilation and whitespace checks passed.
- A1-08 is now closed. This does not migrate production data or implement
  A2–A7 task execution/recovery. No paid provider, commit or push was used.

Reproduce with the commands in the [A1 execution record](m1-a1-implementation-plan.zh-CN.md).
