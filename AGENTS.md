# Project instructions

- Read README.md and docs/DEVELOPMENT.md before changing behavior.
- Preserve the 100-unit allocation model. Never persist or transmit the calculator's capital input.
- Never fabricate live quotes, portfolio positions, news, source links, or AI success rates. Label missing/stale data explicitly.
- Only the analysis module may call AI. AI is opt-in and must pass cash, position, source-ID and freshness checks.
- Do not turn expired or closed-market data into actionable trade suggestions. Do not infer trading days from weekdays.
- Keep network calls behind app/security.py; never log headers, keys, request bodies, or upstream error bodies.
- Keep local secrets, runtime databases, logs, dependencies, and generated build files out of Git and release archives.
- Backend: run `python -m pytest -q` from backend. Frontend: run `npm run build` from frontend.
- Docker Hub repository is `stylle/money-web`. Do not report publication without a successful push and manifest verification.
- Update docs/PLAN.md when scope changes. Unimplemented roadmap features must stay explicitly marked.

- Default releases use one container (web + worker + SQLite). Deployment docs and Docker Hub Overview must start with the same minimal commented Compose, followed by optional parameters. Preserve legacy data paths and explain upgrades.

- Container may initialize only its dedicated data directory as root, then must drop groups/GID/UID before executing web/worker. Never recursively chown arbitrary mounts, follow links during repair, or keep runtime root.

- Bootstrap code and web/backend application directories must be root-owned and unwritable by the runtime UID; protect root startup code across container restarts.
