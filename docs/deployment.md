# Self-hosted deployment

Copy `.env.example` to `.env` and configure the providers required for your research.
Keep the environment file local. Run `docker compose up --build -d` for port 8000,
or `docker compose --profile web up --build -d` to also serve Next.js on port 3000.

Bind mounts persist `my-docs/`, `outputs/`, `logs/` and `data/` in this checkout.
The report index defaults to `data/reports.json`. Preserve these directories during upgrades.

Set `CORS_ALLOW_ORIGINS` for a remote frontend and `NEXT_PUBLIC_TDR_API_URL` to an
API address reachable from the browser. `BACKEND_URL` is the backend address
used inside Docker by Next.js. Rebuild the frontend after public settings change.

Images are `traceable-deep-researcher:local` and `traceable-deep-researcher-web:local`.
Use Docker Compose v2 with BuildKit enabled. The first backend build downloads
Chromium, Firefox and Python dependencies; later builds reuse download caches.
No AWS/Terraform deployment or analytics service is configured.
The application assumes a trusted operator; add your own authentication and
access control before public exposure. See SECURITY.md.
