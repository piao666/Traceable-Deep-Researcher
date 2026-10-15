# Migration validation — 2026-10-15

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
