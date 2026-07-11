# Skill authoring essentials

> Distilled 2026-07-11 from the Anthropic `skill-creator` skill (its SKILL.md and
> validation scripts), embedded here so ANY coding agent operating this repo has the
> standards without a plugin dependency. Dated observation — re-verify against current
> Anthropic guidance if this is more than ~6 months old.

A skill is a packet of instructions an AI agent loads on demand — a title, a trigger
description, and a body of guidance (plus optional bundled files) that teach the agent
how to do one thing well.

## 1. What makes a good skill

**One capability per skill.** A skill should teach a single, coherent capability. If it
covers multiple domains, split the shared workflow from the domain-specific detail: a
thin top-level file with the workflow and selection logic, each variant in its own
reference loaded only when relevant.

**Create a skill when:** the task needs a non-obvious, repeatable procedure that isn't
default competence; the same corrective feedback recurs across sessions; the task
benefits from bundled resources (validated script, template, big reference doc).

**Don't create one when:** the task is a one-step request the agent already handles;
the body would restate general model knowledge (not earning its context cost); the
capability is a one-off.

## 2. Frontmatter: name and description

The **description is the entire triggering mechanism** — the agent decides from name +
description alone, before reading the body. "When to use this" must live in the
description, never buried in the body.

- Name: kebab-case, lowercase/digits/hyphens, ~64 chars max.
- Description: ~1024-char ceiling, aim far shorter; it competes with every other
  skill's description for attention.
- State what it does AND when to use it, with concrete trigger phrases and situations.
- **Be a little pushy** — agents under-trigger skills. "Use whenever the user mentions
  dashboards, metrics, or displaying any data, even without the word dashboard" beats
  "How to build a dashboard". Bias toward over-triggering when close.
- Cover when-NOT-to-use for skills near an adjacent domain.
- Imperative voice, user intent ("use this to X"), not implementation trivia.
- Be distinctive: two descriptions that could both fire for one query is a design bug —
  merge or sharpen the boundary.

## 3. Body structure: progressive disclosure

Three loading stages, each with a cost:

1. **Metadata** (name + description) — always in context; keep tight.
2. **Body** — loaded on trigger; keep under ~500 lines. Approaching the limit means add
   hierarchy: split detail into references with clear pointers ("when X, load Y").
3. **Bundled resources** (references, scripts, templates) — loaded only as needed,
   effectively free until opened. Reference files >~300 lines get a table of contents.

Write imperatively and explain WHY a step matters — rationale generalizes; bare
commands don't. Reaching for ALWAYS/NEVER/MUST usually means the instruction needs a
better explanation instead.

## 4. Common failure modes

- **Over-broad triggers** — test with tricky negatives (queries sharing vocabulary that
  need something else), not just obviously irrelevant ones.
- **Duplicated knowledge across skills** — competing triggers, ambiguity; consolidate
  or delineate.
- **Restating what the model knows** — every section must change behavior, or it's out.
- **Overfitting to the authoring examples** — generalize feedback into intent
  categories, don't hard-code a growing list of specific cases.
- **Stale content** — a triggered skill is trusted at face value, so stale guidance is
  worse than none; re-verify referenced commands, paths, workflows periodically.

## 5. Maintenance: testing, splitting, merging, retiring

**Two axes: does it trigger correctly, and does it perform once triggered.**

- Triggering: an eval set of should-trigger (varied phrasings) and should-NOT-trigger
  (genuinely tricky near-misses) queries; run each several times for a stable rate.
- Performance: realistic tasks with the skill vs a baseline (no skill / previous
  version); prefer scriptable assertions for verifiable outputs; hold out part of the
  eval set to confirm improvements generalize.

**Split** when one skill covers distinct capabilities or its body outgrows what one
invocation needs. **Merge** when two skills compete for the same triggers or duplicate
procedure. **Retire** when the underlying tool/workflow no longer exists or base-model
competence caught up — a stale trigger is an active hazard.
