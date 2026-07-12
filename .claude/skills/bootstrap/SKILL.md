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

## Step 0b — the genome present?

If `.claude/skills/` is missing the base skills (workflow, skill-manager, socials,
bootstrap), ask the user whether to install them: `initc spawn .` copies the packaged genome
(skills, standards, docs templates), additive and idempotent — anything it reports as
"kept" already existed and stays the user's. (Refreshing an existing child later,
`initc spawn . --force` updates existing skills to the base's version; docs and
standards stay untouched.) Merge kept files by hand only if the user asks. Declining is
fine — bootstrap works standalone.

## Step 1 — the interview (short, concrete, every answer recorded)

Ask only what changes the outcome:

1. **Owner identity** — the name and email for LICENSE, README, and package metadata.
   Read it from `git config user.name` / `git config user.email` first and confirm;
   only ask outright when they are unset. This is the ONE place a specific human's name
   belongs — the skills and conventions stay generic ("the user"), so the base reads the
   same for whoever clones it.
2. **Stack and version** — language(s), one stack per folder.
3. **Package manager** — per stack (see the stack reference for the default and why).
4. **Quality tools** — baseline linter/typechecker/test-runner is assumed; then offer
   the opt-in menu from [references/quality-tools.md](references/quality-tools.md).
   A menu, never a default. If the user names a better tool you don't know, that is an
   `evolve` event: adopt it AND update the reference in the same session.
5. **Docs shape** — mirrored `docs/` tree, or README-only.
6. **Env vars known now** — anything the code will read goes into the contract today.
7. **Primary agent file** — CLAUDE.md or AGENTS.md (the other becomes a one-line pointer).
   If the chosen file already exists with the user's own content, we APPEND a short marked
   pointer block and never overwrite it; a fresh repo gets the full constitution inline.
   Do not invade an existing constitution — it may be carefully tuned, and it costs the
   user's context budget on every prompt.

The *choice* lands in `project.yaml` (machine-checkable); the *reason* lands in an ADR
under `docs/decisions/` (readable next session). The owner identity lands in the stack's
project metadata (e.g. `pyproject.toml` authors) and the LICENSE, nowhere else.

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

## Step 5 — the constitution

The root constitution (CLAUDE.md/AGENTS.md) is the always-loaded instruction layer — the
skill index, the line, the binding rules. There is NO separate project skill; the repo's
growing lessons live in the `workflow` skill (via evolve). The template source is
`beacons.py` in init-configurator:

- Fresh repo → materialize `constitution()` as the primary file and the one-line pointer as
  the other (`context_beacons` returns both).
- The primary file already exists → APPEND `pointer_block()`, never overwrite what the user
  wrote.

Materialize the template, then adapt to the interview answers. Never overwrite an existing
constitution.

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
