# Architecture and evidence roadmap

`traceable_deep_researcher/agent.py` exposes `TraceableDeepResearcher`.
ResearchConductor and DeepResearchSkill coordinate search, scraping, context
selection and writing. `backend/server/app.py` serves the API and static UI;
`frontend/nextjs` provides React UI. Additional orchestration lives in
`multi_agents` and `deep_agents`.

Current records include research_sources, visited URLs, research JSON logs,
streamed progress and SQLite report history. These are not verified claim lineage.

Since M1/A1, the ReportStore facade delegates report/history CRUD to a SQLAlchemy
SQLite repository. Schema upgrades and backed-up JSON imports run explicitly via
`scripts/migrate_report_store.py`; API startup only validates schema/import status.
Content versions and chats are persisted transactionally, with unavailable lineage.
Since M1/A2–A7, schema 002–004 adds durable tasks, attempts, events, stage
checkpoints and independent export jobs. The lifespan owns one research worker
and one export worker; HTTP/WS connections only submit or subscribe. Disconnects
do not cancel research. Explicit cancellation, lease renewal and fencing prevent
stale attempts from publishing results. Expired executions become interrupted;
resume is explicit and reuses compatible completed stages.

Basic research persists plans, research context and completed writing. Detailed
reports reuse completed sections; deep research uses stable depth/branch paths.
Checkpoints bind request, configuration, source code, stage input and checksum.
An unfinished remote call may execute again after recovery. Multi-agent recovery
currently reuses the final result only; graph-node and human-review recovery is B3.

Completion atomically freezes report/version, history, events and export jobs.
PDF/DOCX/Markdown run separately; failures are retried without new research.
Downloads validate job ownership and artifact checksum. Managed report bodies
cannot be overwritten by stale browser caches. The Next.js desktop/mobile entry
creates the same task, then opens `/tasks/{id}`. Its HTTP event polling persists
the cursor; WS v1 and legacy start/path are also supported. Expired cursors use
a durable draft/status snapshot. History is server-paginated; local legacy
history requires explicit import. External LangGraph remains a separate mode.

Planned integration from Traceable Research Agent's current lineage-v1 pipeline:

1. Persist tool calls, failures and source snapshots before context filtering.
2. Carry snapshot hashes and exact source coordinates through selection.
3. Link claims to evidence, and report citations to approved claims.
4. Expose the links in the UI and validate report/version integrity at publication.

Adopt data contracts and checks incrementally; do not copy retired engines or
replace the research flow as part of a branding change.

## M0 contracts and offline baseline

`traceable_deep_researcher/runtime/contracts.py` defines provider-independent
RunContext, ResearchResult and injected event/checkpoint/review protocols. The
public agent is imported lazily; its constructor accepts an optional run_context.
Existing public research/write methods retain their return values. Legacy
HTTP/WS responses are adapted to the task service.

`backend/server/tasks/models.py` and `frontend/nextjs/types/research.ts` define
version-one task/event contracts used by `/api/research`. Evaluation
inputs and scored/unscored outcomes live in `evals/framework`; `evals.run` only
replays frozen engineering fixtures and blocks Python socket access. The dataset
contains eight synthetic task cases and eight node cases, all development data.

The SQLite/LangGraph and structured-output probes are isolated experiments,
not application recovery or evidence-lineage implementations. See
[evaluation usage](evaluation.md) and [M0 execution plan](m0-implementation-plan.zh-CN.md).
