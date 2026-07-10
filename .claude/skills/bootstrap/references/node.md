# Node/TypeScript stack — bootstrap reference

Procedures first; dated observations at the bottom. Re-verify old observations before
relying on them.

## Creator

For apps, use the framework's own creator (see [react.md](react.md)); for libraries,
`pnpm init` / `npm init` plus the setup below — there is no single official library
creator worth vendoring.

## Package manager

- **pnpm (default)** for its strictness and speed; **npm** when the user prefers zero
  extra installs.
- Pin the exact manager via the `packageManager` field — but ONLY with a real, installed
  version (`pnpm --version`); a made-up pin breaks installs. Declare `engines.node` too.

## Baseline quality setup

- **TypeScript strict.** Extend `@tsconfig/strictest`. Two tsconfigs: `tsconfig.json`
  covers `src` + `tests` with `noEmit` (the typecheck surface); `tsconfig.build.json`
  extends it with `src` only, `rootDir`/`outDir` set (the build surface) — so compiled
  tests never land in `dist/`.
- **Biome** as linter/formatter unless the user wants ESLint+Prettier. Two settings that
  keep biting (verified 2026-07):
  - `"vcs": {"enabled": true, "clientKind": "git", "useIgnoreFile": true}` — biome does
    not read `.gitignore` unless asked, so `lint` after a `build` checks `dist/` and fails
    on generated code.
  - if any JSON files are machine-generated (e.g. via `json.dumps`, which always expands),
    set `"json": {"formatter": {"expand": "always"}}` — biome's default collapses short
    arrays and the fresh scaffold fails its own lint.
- **Vitest** for tests.

## Version constraints

A caret (`^`) is a ceiling as well as a floor: `^5.5.0` can never reach a 7.x release, so
check `npm view <pkg> version` before writing every single one. Floors that cannot reach
the current major are stale on arrival.

## Tasks to declare in project.yaml

```yaml
tasks:
  install: pnpm install
  build: pnpm run build          # tsc -p tsconfig.build.json
  typecheck: pnpm run typecheck  # tsc --noEmit
  test: pnpm run test            # vitest run
  lint: pnpm run lint            # biome check .
```

## Dated observations (verified 2026-07)

- **corepack is gone from Node >= 25**: `RUN corepack enable` (and any doc telling users
  to run it) exits 127 on current Node. Install pnpm with `npm install -g pnpm` (in
  Docker: `npm install -g pnpm@<real version>`).
- Node's LTS cadence moves every October — check endoflife.date/nodejs before declaring
  `engines.node`, don't copy the number from an old project.
