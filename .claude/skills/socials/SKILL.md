---
name: socials
description: Publishing and discoverability - fire whenever the user wants to post, announce, launch, or promote anything (a LinkedIn post, an X thread, a Show HN, a launch/reflection draft), wants something findable (GitHub repo invisible in search, topics/description/social preview), or asks for a hook, post draft, or post image/GIF. Runs decide -> optimize -> draft -> post; the human always does the actual posting. Load references/linkedin.md, references/github.md, references/visuals.md on their triggers. Not for long-form video production, and not for in-repo docs (workflow step 4 owns those).
---
# socials — decide → optimize → draft → post (the human posts)

> Authored 2026-07-11 from a four-source research pass: the longform-factory skill
> (VideoCreator2, its stage architecture and export format), a live review of real
> LinkedIn posts, and two web sweeps (LinkedIn algorithm, GitHub discoverability) —
> raw (2026-07). Platform mechanics rot fast: each platform reference separates
> evergreen mechanism facts from dated snapshots. Re-verify anything dated older
> than ~6 months before a high-stakes post.

## What the user gates (hard rules)

- The user picks WHAT to post, from a shortlist — never solo.
- The user approves final wording, and their edits are canon: a later formatting or
  export pass must never silently regress words the user touched.
- The user does the actual posting. NEVER auto-post, never drive a browser or API to
  publish — the deliverable is a paste-ready package.
- Posts contain no em dashes and no en dashes (user rule — restructure the sentence
  instead). Repo docs keep house style; the rule is for post text only.

## The workflow

| Step | What happens | Produces |
|---|---|---|
| 1. Decide | score 2-4 candidate angles on the axes below, recommend one, **STOP — user picks** | chosen topic + angle |
| 2. Optimize | load the platform reference; none exists → generic checklist below, offer to research + author one | constraints the draft must obey |
| 3. Draft | hook first (it must fit the platform's fold), preview digest before full text, asset brief via [references/visuals.md](references/visuals.md) | draft in `docs/posts/` |
| 4. Post | paste-ready package (format below), user posts, outcome noted in the draft file | posted + one log line |

When the "post" is a page that just needs to be findable (a GitHub repo, a profile),
decide and draft collapse — step 2 with the right reference is the whole job.

**Decide axes** (evidence, not vibes — cite why for each):
1. **Demand proof** — has this angle worked for someone else, or does it answer
   something people actually ask?
2. **Substance density** — enough concrete numbers, artifacts, or moments to fill it
   without padding? If not, the draft will starve.
3. **Audience payoff** — who is this for and what do they walk away with?
4. **Timing** — is there a hook now (launch, milestone, fresh lesson), or does it keep?

## Generic optimize checklist (any platform without a reference)

- The first visible line carries the whole hook — assume readers never expand.
- One idea per post. The second idea is the next post.
- Native format beats a bare external link everywhere; treat any outbound link as a
  reach cost and decide whether it earns its place.
- Concrete beats abstract: real numbers, real filenames, real failures.
- End with a CTA a reader can actually answer, not applause bait.
- Match the visual to the point (decision table in [references/visuals.md](references/visuals.md)).

## Voice guardrails (all platforms)

Write for the skim: short lines, no buried subclauses, key numbers on their own line,
rounded the way people say them. Second person where natural; concrete metaphor over
essay-explainer. Banned: "delve", "landscape", "it's important to note", filler
rhetorical questions, engagement bait ("comment YES", "tag someone who"), fake humility
openers, generic superlatives, hashtag walls. The test: if a stranger could have written
it about any project, cut until only this project's post remains.

## The paste-ready package (step 4 format)

Drafts live in `docs/posts/YYYY-MM-DD-slug.md` (gitignored — drafts are local).
Frontmatter: `platform`, `status: draft | approved | posted`, `date`, `assets`.
Body rules, in this order:

1. Hook options — 2-3 variants, the user picks one (wording gate).
2. The post — **every paste-able field in its own fenced code block** (fenced blocks
   render with click-to-copy); explanation lives between blocks, never inside them.
3. First comment (only if the link-placement decision put anything there) — own block.
4. Asset brief or image prompt — own block, per [references/visuals.md](references/visuals.md).
5. Numbered posting checklist, ending with "report back how it did" — the outcome line
   goes back into this file and, if a lesson landed, through skill-manager evolve.

## Lazy parts (load only on trigger)

| Trigger | Load |
|---|---|
| LinkedIn post: drafting, hooks, timing, link placement, media choice | [references/linkedin.md](references/linkedin.md) |
| GitHub discoverability: repo invisible in search, topics, description, social preview, awesome lists | [references/github.md](references/github.md) |
| Any post visual: explainer image, GIF, carousel, animation, prompt for an image model | [references/visuals.md](references/visuals.md) |
| A platform with no reference yet (X, Reddit, HN, ...) | generic checklist above; offer to research and author `references/<platform>.md` per skill-manager authoring standards |
