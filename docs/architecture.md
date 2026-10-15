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
