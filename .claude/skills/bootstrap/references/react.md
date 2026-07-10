# React (and other frontend frameworks) — bootstrap reference

## The rule that makes this file short

**Always use the framework's own creator; never vendor a framework template.** A vendored
Next.js or Vite template is stale in six months; `create-next-app` and `create-vite`
never are, because the obligation to keep them fresh sits with the team that ships the
framework. Run the creator, then LAYER the project's standards on top of what it wrote.

- SPA / library-adjacent app: `pnpm create vite <name> --template react-ts`
- Full-stack / SSR: `pnpm create next-app` (answer its prompts with the interview's answers)
- Anything else the user names: find that framework's official creator first; only
  hand-roll if none exists, and say so in the ADR.

Everything in [node.md](node.md) applies on top (strict tsconfig, biome caveats,
verify-before-pinning, packageManager field).

## React-specific lint layer

Biome covers general lint. React correctness rules still live in ESLint plugins, so add a
NARROW-scope ESLint next to biome (not instead of it) when the user opts in:

- `eslint-plugin-react-hooks` (recommended preset — includes the React Compiler
  diagnostics; verified 2026-07)
- `eslint-plugin-jsx-a11y` for accessibility

Scope the ESLint config to React rules only, so the two linters never fight over style.

## Opt-in extras (offer, never default — see quality-tools.md)

- **Playwright** for e2e.
- **knip** for dead exports/dependencies (ts-prune is deprecated and archived — do not
  suggest it).
- **dependency-cruiser** for enforceable import/architecture rules.
- **size-limit** for a CI bundle budget.

## What the manifest records

The framework does not get its own axis in `project.yaml` — it is a node stack whose
`tasks` happen to be `dev`/`build`/`preview` from the creator's package.json, and whose
reason-for-being lives in the ADR. `initc describe` on an existing React repo will map
the scripts for you.
