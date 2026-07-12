# GitHub — make a repo findable

> raw (2026-07). Compiled from official GitHub docs (mechanism facts, durable), live
> API measurements, and unofficial SEO analyses (marked contested). GitHub publishes no
> ranking formula — anything beyond the mechanism facts is reverse-engineered consensus.

## The one mechanism fact that explains most invisibility

**Default GitHub repo search scans NAME + DESCRIPTION + TOPICS. Not the README** (that
needs an explicit `in:readme` from the searcher). An empty topics list plus a
description without the words people type = invisible, regardless of code quality.
Check the current state first:

```
gh api repos/<owner>/<repo> --jq '{description, topics, homepage}'
```

## On-repo checklist (free, do first)

1. **Topics** — cap is 20 (official); use ~10-15. Topics are exact-match slugs, so
   prefer existing popular ones over invented compounds. Measure before choosing:

   ```
   gh api "search/repositories?q=topic:NAME" --jq .total_count
   ```

   Mix broad (`python`, `cli`, `developer-tools`) with precise niche terms the target
   audience actually filters by. No junk topics (`wip`, years, `beta`).
2. **Description** — hard cap 350 chars; lead with the literal words a searcher would
   type, keep it ~5-15 words of keyword-bearing text (contested "density" theory, but
   short-and-on-topic costs nothing). Evocative taglines belong in the README, not here.
3. **Social preview image** — 1280×640 px, under 1 MB, Settings → Social preview. This
   is the card every LinkedIn/Slack/X share unfurls into; it does nothing for search.
   Set it before any promotion push, brief it via [visuals.md](visuals.md).
4. **README headings** — H1/H2 carry the search phrases in natural prose. This is the
   Google-facing lever; GitHub's own search never reads it.
5. **Homepage field** — docs site or package page if one exists. Trust signal for
   humans, no evidence of a search effect.

## Off-repo levers (public actions — each needs the user's explicit go)

- **Package registry (PyPI/npm)** — independent discovery surface plus an authoritative
  backlink to the repo.
- **Awesome-list PR** — the highest in-ecosystem backlink. Read THAT list's
  contributing rules first; every list has its own etiquette and low-effort PRs get
  closed on sight.
- **Show HN / subreddit post** — traffic and backlinks; no evidence of a direct search
  effect. A separate post through this skill's full workflow, not a link dump.

## Expectations to set (so nobody chases ghosts)

- Google indexing of bare `github.com/user/repo` pages takes weeks and is reported
  (2026, community anecdote) as unreliable, possibly gone. A GitHub Pages site indexes
  far more dependably if search-engine discovery matters.
- Trending runs on star *velocity* relative to the repo's own baseline, not star count.
  Not controllable — don't chase it, and never propose gaming stars; they're earned
  signals.
- Renaming: git/web/API redirects persist, but GitHub Pages URLs break. The name is
  rarely the problem — empty topics and a keyword-free description almost always are.
- Whether GitHub tokenizes hyphens (does `init-configurator` match a search for
  "init configurator"?) is undocumented — when it matters, test against live search
  instead of trusting a claim.
