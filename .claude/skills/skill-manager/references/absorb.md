# absorb — the genome moves between detached projects

> Moved intact from the standalone `absorb` skill into `skill-manager/references/` on
> 2026-07-11 (nested-skill consolidation, Stepan's decision).

Projects stay detached: this is open source, and nothing may assume a stranger's clone
syncs with anything of ours. Detached does not mean isolated. The behaviour is bacterial:
an evolved project can pass its genome down (spawn) and take genes in from any repo
(absorb) — with the gates as selection pressure and the human diff review as immunity,
because horizontal transfer is exactly how a bad gene gets in.

**The genome** = the skill set + the standards (linter/hook/CI configs) + the gates +
`project.yaml`'s shape. Not the code; the code is the phenotype.

## absorb <source-repo> (horizontal, works on ANY repo — init-managed or not)

1. **Inventory the source.** Read, in this order: its skills/agent docs (`.claude/`,
   CLAUDE.md, AGENTS.md, docs/) → its enforcement (linter configs, pre-commit, CI) →
   its conventions visible in code (layout, naming, test shape). `initc describe` on it
   tells you cheaply what stacks it runs.
2. **Extract procedures, never pins.** A source repo's `ruff>=0.15` is a fact about its
   date, not a gene. What transfers is the decision ("they gate complexity with xenon
   in CI — we don't; worth it?"), re-verified against today.
3. **Propose diffs, one gene at a time,** into our skills/references/configs. Each
   marked `raw (YYYY-MM), absorbed from <source>` — provenance is what lets a bad gene
   be traced and reverted later.
4. **Selection:** anything touching config must leave the gates green. **Immunity:** the
   human reviews every diff; absorbing without review is how the genome gets poisoned.

## spawn <new-project-path> (vertical, this project → a child)

1. Copy the genome: `.claude/skills/` (including lessons — inheritance is the point),
   `.gitattributes`, hook/CI configs worth carrying.
2. Do NOT copy state: `docs/state/` starts empty, `docs/vision.md` is the new human's to
   write, `project.yaml` is written fresh by `bootstrap`/`describe` for the new repo.
3. Reset instantiation metadata in the child's `project-base` (new date, new repo name),
   and record lineage as the first line of the child's `docs/state/log.md`:
   "spawned from <parent> @ <commit> on <date>."
4. From that moment the copies are detached — the child evolves alone. Divergence is
   the design.

`initc spawn` / `initc absorb` as commands come later; until then this reference IS the
procedure, executed by hand.
