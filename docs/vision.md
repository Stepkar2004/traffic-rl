# Vision

> **Human-owned. Only Stepan edits this file.**
> This version was DRAFTED by Claude on 2026-07-11 strictly from Stepan's own words
> (project brief + phase-0 conversations). It stands as provisional until Stepan edits
> or explicitly blesses it; treat any conflict between this file and Stepan's live
> instructions as a bug in this file.

## Why this project exists

Simulate real-world traffic flow as faithfully as an honest, self-built system can, and
optimize it as much as possible: every car and every pedestrian should reach its
destination as fast as fairness allows. Start simple (one intersection, simple cars and
pedestrians) and climb toward reality (limited machine perception, human psychology,
chaos, real road shapes). It is also the public proving ground for two other things:
research rigor as a portfolio signal (each phase is a publishable post), and the
self-evolving agent base (skills/genome) that builds it.

## What winning looks like

- A simulator whose realism visibly grows each phase, and whose visuals (viewer, GIFs)
  let anyone SEE that it behaves reasonably.
- An honest leaderboard: classical controllers implemented well, RL compared against
  them with CIs over seeds — and negative results published as such, never hidden.
- Each phase ships: gates green, README updated, a post draft written.
- The base proves itself: frictions become skill diffs; a fresh session can cold-start
  from the repo alone.

## Non-goals

- 3D rendering (2D top-down only; 3D is far-future at most).
- Calibration to a specific real city's data (until a late phase decides otherwise).
- Auto-pushing anything public: pushes happen only by Stepan or on his explicit word.
- Making money with this repo (portfolio/research lane, capped behind the day's money
  action per the brain's laws).

## Horizon

- **This month:** phase 1 — world + honest floor (single intersection, classics,
  viewer, leaderboard).
- **Next:** phase 2 (grid + omniscient RL), phase 3 (detection-confidence perception).
- **Someday:** driver/pedestrian psychology and chaos, uber-style loop trips, protected
  arrows, roundabouts and topology transfer, SUMO validity check.
