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
