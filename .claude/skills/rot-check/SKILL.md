---
name: rot-check
description: Fire before any release, after a long gap in the repo, or on "rot check" / "is anything stale" - hunts stale version claims, gates that can no longer fail, docs that describe a tool that no longer exists, and expired raw claims.
---
# rot-check — a check you have never watched fail is not a check

Everything in this system rots: pinned versions, skill claims, docs, and — worst,
because it is invisible — the gates themselves. A gate that silently passes everything
is worse than no gate. This skill is the periodic hunt.

## 1. Watch every gate fail (the core move)

For each gate, plant a violation and confirm the gate catches it, then revert:

- an absolute path in a scanned file → `initc lint-paths` must exit 1;
- a failing assert → the test task must exit 1;
- a mis-formatted file → the format check must object;
- a field added to a pydantic model → the CI schema-drift step must object;
- a wrong value in `project.yaml` → `initc validate` must teach, not just reject.

A gate that swallows its violation is a P0 — fix the gate before trusting anything it
ever said. (History: a CRLF regression test here once "passed" against unbroken code
because the probe never applied; watch the failure happen, don't assume it.)

## 2. Stale-pin hunt

Grep skills, references, docs, and configs for version constraints and dated claims
(`>=`, `^`, `checked 20`, image tags). For each: query the live registry (`npm view
<pkg> version`, PyPI JSON API, endoflife.date) — a caret that cannot reach the current
major is stale on arrival. Update the claim AND its date, or delete it.

## 3. Docs truth pass

Run every command the README and skills show, exactly as written. A doc that names a
command, flag, or file that no longer exists fails this pass. (History: this repo's
docs once described `corepack enable` behavior a full Node major after corepack was
removed.)

## 4. Trust decay

Every `raw (YYYY-MM)` claim older than the skill-manager's staleness window: re-verify
it, promote it (human), or delete it. Standing on expired raw claims is how a
self-evolving system entrenches its own guesses.

## 5. Quality-tool liveness

Every tool `project.yaml`/pre-commit/CI declares must have actually RUN recently (check
CI logs or run it now). An installed-but-never-firing tool is decoration; either wire it
or remove it and its ADR gets a closing note.

## Output

A short report: what was checked, what failed, proposed diffs (through `evolve` for
skill content). Rot found is not embarrassing; rot unfound is.
