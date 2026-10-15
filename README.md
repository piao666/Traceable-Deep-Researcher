# Traceable Deep Researcher

A self-hosted application for web and local-document research, report generation
and follow-up questions. Maintained by **Piao666**.

- [Repository](https://github.com/piao666/Traceable-Deep-Researcher)
- [Contact: dahaipiao9@gmail.com](mailto:dahaipiao9@gmail.com)

## Docker quick start

1. Copy `.env.example` to `.env` and configure your model and search provider.
2. Run `docker compose up --build -d`.
3. Open [localhost:8000](http://localhost:8000).

For the optional Next.js interface run `docker compose --profile web up --build -d`,
then open [localhost:3000](http://localhost:3000).
Images are built locally; none have been published by this migration.
See [deployment](docs/deployment.md) for settings and persistent data.

## Current capabilities

- Web, local-document and hybrid research with configurable providers.
- Standard, detailed, deep and multi-agent research workflows.
- Source links, progress logs, report exports and follow-up chat.
- Static and Next.js interfaces, including mobile layouts.
- External MCP tools as research inputs.

Immutable snapshots, exact source spans, claim proofs and report-level lineage
from the reference project are **planned enhancements**, not implemented by
this rename. See [architecture](docs/architecture.md).

## Python development

Python 3.12+ is required. Install this checkout with `pip install -e ".[test]"`.

```python
import asyncio
from traceable_deep_researcher import TraceableDeepResearcher

async def main():
    researcher = TraceableDeepResearcher(query="Your research question", report_type="research_report")
    await researcher.conduct_research()
    print(await researcher.write_report())

asyncio.run(main())
```

This example uses configured providers and may incur their API charges.
`traceable-deep-researcher` is the local distribution name, not a package already
published to PyPI. Python/npm publication and a Codex plugin are future directions.

See [migration](docs/migration.md), [contributing](CONTRIBUTING.md),
[security](SECURITY.md), [license](LICENSE) and [upstream attribution](UPSTREAM.md).
