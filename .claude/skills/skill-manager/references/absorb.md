# absorb — the genome moves between detached projects

> Consolidated from the standalone `absorb` skill on 2026-07-11 (nested-skill
> architecture). Spawn was promoted to a command the same day, after one proven
> by-hand run.

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

`initc spawn <path>` is the mechanical half — a real command since 2026-07-11. It copies
the packaged genome (skills, standards, docs templates) into the target, additive by
default: a file that already exists is reported as kept and not overwritten. `--force`
is the deliberate exception — it lets the base's version win for existing skill files
only (docs and standards stay additive, and it never deletes), which is how you push
base skill updates down into an already-spawned child. The judgment half stays with the
agent:

1. Run `initc spawn <path>` — or, in the child with nothing installed:
   `uvx --refresh --from git+https://github.com/Stepkar2004/init-configurator initc spawn .`
   (add `--force` to update skills the child has not changed; `--refresh` defeats uvx's cache).
2. **Review the "kept" (and, with `--force`, "replaced") lines.** Kept files are the
   child's own; merge genome content by hand only if the human wants it. Replaced files
   moved to the base's version — `git diff` shows exactly what changed.
3. `project.yaml` and the child's root constitution (CLAUDE.md/AGENTS.md) are NOT in the
   genome on purpose — `bootstrap`/`describe` write them fresh for the child (`beacons.py`
   is the template source). Run the `bootstrap` skill next.
4. **Record lineage** as the first line of the child's `docs/state/log.md`: "spawned
   from <parent> @ <commit> on <date>." From that moment the copies are detached — the
   child evolves alone. Divergence is the design.

`initc absorb` as a command comes later; until then the absorb half of this reference IS
the procedure, executed by hand.
