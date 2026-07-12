# Visuals — decide the asset, brief it, verify it

> The post travels on its visual — nearly every top post observed in the 2026-07
> LinkedIn review carried one. The asset is decided during draft, not bolted on after.
> The agent briefs; the user generates/captures; the agent verifies what comes back.

## Decide the asset (first match wins)

| The post's point is… | Asset |
|---|---|
| how something works (architecture, flow, before/after) | AI-generated explainer image — prompt package below |
| a tool in action | screen capture (GIF or short video), trimmed to the one moment that sells it |
| a list, steps, or several points | carousel/document (PDF), one idea per slide — also the longest-dwell format on LinkedIn |
| one number or result | stat card: the number huge, one line of context |
| a precise animated explainer worth real effort | HTML animation (GSAP or similar), screen-recorded to video |

If the image would need a paragraph caption to make sense, it's the wrong image.

## AI image prompt package (user generates externally)

Current image models render exactly what's described — the brief is the craft. Hand the
user ONE paste-ready prompt block; the block contains only the prompt, options and
rationale live outside it.

The prompt must pin down:
- **Format**: aspect ratio / dimensions for the platform (table below).
- **Composition**: what is where — subject, layout, focal point.
- **Style + palette**: named style, 2-3 colors, background.
- **Every text element in quotes**, ≤4 words each, with position. Then "No other text."
  — unrequested text is the most common defect.
- **Avoid list**: clutter, watermarks, extra UI, whatever the concept must not contain.

Offer 2 variants (A/B) when the concept has a real fork. On return, verify: dimensions,
no garbled text, and legibility scaled small — squint-test at feed-thumbnail size
before calling it done.

## Screen captures (terminal or UI)

Large font, clean theme, trimmed dead time. One action per capture, under ~15 seconds.
If the payoff is a printed line (a doctor fix, a green gate), end holding on it. Text
must survive feed-size scaling — when it doesn't, capture less screen.

## Platform sizes (2026-07 snapshot — re-verify when stale)

| Surface | Size |
|---|---|
| LinkedIn feed image | 1200×627 landscape, or 1080×1350 vertical (more mobile real estate) |
| LinkedIn carousel/PDF page | 1080×1080 or 1080×1350 |
| GitHub social preview | 1280×640, under 1 MB |
| X/Twitter card | 1600×900 |
