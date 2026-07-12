# LinkedIn — optimize and draft for the feed

> raw (2026-07). Compiled from LinkedIn's own engineering blog (the one primary
> source), a sweep of vendor research (numbers contradict — treated as directional),
> and a live read of ~40 real posts (feed + keyword search, fold screenshot-verified).
> Mechanism facts lead; the dated snapshot at the bottom rots — re-verify it before a
> high-stakes post if this file is older than ~6 months.

## Three facts that shape every post

1. **The fold is the post.** "…more" cuts at ~2-3 lines (~140-220 chars, verified live
   2026-07); most readers never expand. Author name/headline lines don't count against
   the budget — the body text does.
2. **Dwell time is an official ranking signal** (LinkedIn engineering blog, 2026): slow
   reading, pausing, and long dwells are weighted alongside likes/comments. A post that
   rewards actual reading beats one engineered for a reflexive like.
3. **Distribution is a staged test.** A small sample of your network sees it first;
   their early engagement decides wider reach. Post when you can be present for the
   first hour or so to answer comments — replies feed the same test.

## Hook (spend the fold budget on tension)

End the pre-fold text on an open loop: a colon, an incomplete thought, or a claim that
begs elaboration — never a closed sentence that already satisfies. Observed live: the
strong performers open with a surprising number/result ("A solo founder. $80M exit. Six
months after launch.", "47 agent tasks… total token cost: $0"), a contrarian claim
("Most people think X. It isn't."), or an unresolved story beat ("I kept finding the
same thing on people's 'private' AI setups").

The anti-hook is announcing that the post exists: "I am excited to officially announce…"
buries the payoff and reads as template copy — observed flopping on otherwise legitimate
launches.

Formulas that fit a dev-tool audience (fill with real numbers, then sharpen):
- Result-first: "I ran [N] [things] through [X]. [Surprising outcome]."
- Contrarian: "Everyone says [belief]. Here's why that's backwards."
- Failure-first: "I spent [time] building the wrong [thing]. Here's the rewrite."
- Plain build: "I built [X] because [specific recurring pain]."
- Before/after: "[Old painful workflow]. Now it's [new workflow] in [time/steps]."
- Reader-outcome: "If you've ever [specific frustration], I built something for you."
- Credibility-first open source: "After [years of the same pain], I open-sourced [X]."

Spam tells engineers bounce off: generic superlatives, manufactured cliffhangers, fake
humility openers, vote-bait ("Comment 🚀 for the link").

## Body

- **White space is load-bearing.** One-sentence paragraphs, short bullet runs, a number
  on its own line. Observed live: two same-genre dev-tool posts, dense paragraphs vs
  scannable bullets — 4 likes vs 526. Formatting was the visible difference.
- Concrete before/after numbers are the proof spine — necessary, not sufficient.
- Optimal total length is contested (see dated snapshot); substance decides. Write it,
  then cut every line a skimmer would skip.
- Hashtags: 0-3, relevant only, at the end. Hashtag pages were deprecated in 2024;
  observed live, 10+ tags co-occurred with floor-level engagement every time.
- Tag people (not company pages), only when genuinely involved, at most a few.

## Links

Any external link is a reach cost (magnitude contested, direction near-universal).
Ranked options:
1. **No link in post** — name the repo/tool; profile "Featured" or a follow-up carries it.
2. **Framed link in body** — the link earns its place with context ("repo, MIT:").
   Observed live: framed links outperform bare pasted URLs on otherwise similar posts.
3. **Link in first comment** — the classic workaround, but 2026 sources disagree on
   whether it still avoids the penalty. If used, say so in the post ("link in comments").

Never a naked URL with no framing.

## Media

Nearly every top post observed carried a visual. Decide the asset with
[visuals.md](visuals.md). For a launch: written hook + a demo visual (GIF, screenshot,
diagram) + a feedback question is the repeating winner pattern. Documents/carousels are
the most consistently top-ranked format across sources — the swipe-through IS dwell
time.

## CTA

A direct, answerable question drives comments ("Would you use this for X?", "What am I
missing?") — observed high comment:like ratios follow personal, specific asks. "Thoughts
welcome" does little. Applause bait is penalized and reads as spam.

## Expectations (small account)

Authority is a separate lever: big-name accounts win with low-craft posts, and a
well-executed launch from a small account can still land in single digits — observed
live on two clean, rule-following launches. One post is not a verdict; 2-5 posts/week
of the mix (lesson, behind-the-scenes, opinion, launch) compounds. Never more than one
post per ~24h.

## Dated snapshot (2026-07) — verify before relying on any number

| Claim | Status |
|---|---|
| Golden-hour window 30-90 min | vendor guesses, existence corroborated, minutes not |
| Comments weigh 2-15x a like; saves ~5x | direction agreed, magnitude wildly inconsistent |
| External-link penalty 19-70% | four sources, four numbers |
| First-comment link still helps | actively contested in 2026 |
| Optimal length 800-1,000 vs 1,300-2,500 chars | same vendor, different years, unreconciled |
| Best time Tue-Thu afternoon (Wed ~4pm) | weak evidence class; your audience ≠ aggregate |
| Media multipliers (docs 1.4x, polls ±) | contradiction-riddled; trust direction only |
| AI-slop detection suppresses generic text | claimed; one methodical study found AI-flagged posts *outperforming* in tech — unresolved |
