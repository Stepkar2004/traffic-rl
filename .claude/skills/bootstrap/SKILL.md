---
name: bootstrap
description: Phase 0 of any project - fire whenever asked to start, scaffold, set up, or adopt a project ("new Python CLI", "set this repo up properly", "add a frontend stack"). Interview, scaffold via OFFICIAL creators, describe into project.yaml, prove with gates.
---
# bootstrap — phase 0, from idea (or existing repo) to provably-working tree

You are generating; the tool is verifying. Never hand-write what a maintained official
creator emits, and never claim phase 0 is done until the gates say so.

## Step 0 — existing code?

If the target folder already has code, run `initc describe` FIRST. It drafts a
`project.yaml` from what deterministic inspection finds (`FILL_ME` marks its gaps).
Review the draft with the user, fill the gaps, then continue from step 4. The old
design assumed the folder was empty; you must not.

## Step 1 — the interview (short, concrete, every answer recorded)

Ask only what changes the outcome:

1. **Stack and version** — language(s), one stack per folder.
2. **Package manager** — per stack (see the stack reference for the default and why).
3. **Quality tools** — baseline linter/typechecker/test-runner is assumed; then offer
   the opt-in menu from [references/quality-tools.md](references/quality-tools.md).
   A menu, never a default. If the user names a better tool you don't know, that is an
   `evolve` event: adopt it AND update the reference in the same session.
4. **Docs shape** — mirrored `docs/` tree, or README-only.
5. **Env vars known now** — anything the code will read goes into the contract today.
6. **Primary agent file** — CLAUDE.md or AGENTS.md (the other becomes a pointer).

The *choice* lands in `project.yaml` (machine-checkable); the *reason* lands in an ADR
under `docs/decisions/` (readable next session).

## Step 2 — scaffold with the official creator

Read the stack's reference for the current procedure — it is the part of this skill
that changes often, so it lives in its own file and you load only the one you need:

- [references/python.md](references/python.md)
- [references/node.md](references/node.md)
- [references/react.md](references/react.md)
- [references/docker.md](references/docker.md) — only when the project deploys in containers

**The verify-before-pinning rule (applies to every stack):** before writing ANY version
constraint, query the live registry (`npm view <pkg> version`, the PyPI JSON API,
endoflife.date). A caret is a ceiling as well as a floor — one that cannot reach the
current major is stale on arrival. Pin container images. Record the date you checked.

## Step 3 — the shape

`src/` (or the stack's idiomatic layout), `tests/` mirroring it, `docs/` per the
interview. Every generated text file is written with explicit LF endings, and
`.gitattributes` gets `* text=auto eol=lf` — see the stack references for why this
keeps biting.

## Step 4 — the contract

Write `project.yaml`: stacks, versions, `dependency_files`, `tasks` (always including
`install` — installing is a declared task, not a special mode), the `env` contract,
`paths` for data dirs. Then `initc env` to template `.env.example`. Secrets never get
example values.

## Step 5 — the beacons

CLAUDE.md/AGENTS.md (primary + one-line pointer) and the project's own
`.claude/skills/project-base/SKILL.md`. The template source is
`beacons.py` in init-configurator — materialize its content rather than inventing your
own, then adapt to the interview answers. Never overwrite an existing beacon.

## Step 6 — the hooks

`.pre-commit-config.yaml` wiring `initc lint-paths` plus exactly the quality tools
chosen in step 1. `pre-commit install`. CI mirrors the same gates when the user wants CI.

## Step 7 — prove it (phase 0 is done when this is green, not before)

```
initc validate          # the manifest is well-formed
initc doctor            # machine ready; every problem prints its fix
initc run install       # in-project env created
initc run test          # passes on the empty project
initc lint-paths        # clean
git commit              # the first commit is the proof snapshot
```

A failure here is not an obstacle to the demo — it IS the demo. Fix it before moving on.
