# Architecture and evidence roadmap

`traceable_deep_researcher/agent.py` exposes `TraceableDeepResearcher`.
ResearchConductor and DeepResearchSkill coordinate search, scraping, context
selection and writing. `backend/server/app.py` serves the API and static UI;
`frontend/nextjs` provides React UI. Additional orchestration lives in
`multi_agents` and `deep_agents`.

Current records include research_sources, visited URLs, research JSON logs,
streamed progress and JSON ReportStore. These are not verified claim lineage.

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
Existing research/write methods and the production HTTP/WS flow retain their
existing return values and behavior.

`backend/server/tasks/models.py` and `frontend/nextjs/types/research.ts` define
version-one task/event contracts without registering new API routes. Evaluation
inputs and scored/unscored outcomes live in `evals/framework`; `evals.run` only
replays frozen engineering fixtures and blocks Python socket access. The dataset
contains eight synthetic task cases and eight node cases, all development data.

The SQLite/LangGraph and structured-output probes are isolated experiments,
not application recovery or evidence-lineage implementations. See
[evaluation usage](evaluation.md) and [M0 execution plan](m0-implementation-plan.zh-CN.md).
