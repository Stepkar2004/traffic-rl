# Docker — bootstrap reference

Only load this when the project actually deploys in containers. init-configurator no
longer generates Dockerfiles — you write them against what is true TODAY, which is why
this is a reference file and not a template. (init-configurator itself is never
dockerized — its tests shell out to real package managers on the host.)

## Writing the Dockerfile

- **Pin the base image** to the stack's declared version: `python:<version>-slim`,
  `node:<version>-slim`. Verify the tag exists before writing it.
- **Dependency layer before source layer** — copy dependency files, install, THEN
  `COPY . .` — so source-only changes reuse the cached install.
- **Copy lockfiles strictly, not optionally.** `COPY package.json pnpm-lock.yaml ./`
  fails the build loudly when the lockfile is missing — that is a feature. A glob like
  `pnpm-lock.yaml*` silently builds an unlocked image instead.
- **Install frozen:** `pnpm install --frozen-lockfile` / `npm ci` / `uv sync --locked`.
  An image that resolves dependencies at build time is not reproducible.
- **CMD** comes from the manifest's `start` (or `dev`) task. Inside a container the
  server must bind `0.0.0.0` — localhost is reachable from nowhere but the container.

## Stack specifics (verified 2026-07 — re-verify, these rot fastest)

- **uv in Docker:** copy the binary from Astral's image,
  `COPY --from=ghcr.io/astral-sh/uv:<pinned version> /uv /usr/local/bin/uv` — pin the
  tag, `latest` breaks reproducibility. Then `uv sync --locked --no-dev`.
- **pnpm in Docker:** `RUN npm install -g pnpm@<real version>` — NOT `corepack enable`;
  Node >= 25 ships without corepack and that line exits 127.

## Compose

- One service per stack (`build.context` = the stack's root), one per sidecar.
- `.dockerignore` at EACH build-context root (docker only reads it there): `.git`,
  `.venv`, `node_modules`, `__pycache__`, `dist`, `.env`.
- `env_file: [.env]` when the project declares env vars; `.env` stays gitignored.
- A postgres sidecar needs `POSTGRES_PASSWORD` set (the image refuses to start without
  it) and a named volume for its data dir, or the data dies with the container.
- Ports are the user's choice — ask, don't guess.

## Verify like everything else

Build the image and run the test task inside it before calling docker setup done —
`docker build` succeeding says the syntax parsed, not that the app works.
