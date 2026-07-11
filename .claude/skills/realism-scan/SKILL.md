---
name: realism-scan
description: Fire between phases, before planning any new realism increment, or on "what should we simulate next" / "realism scan" / "what's missing from the sim". Inventories what the simulator already models, hunts real-world traffic phenomena it does not, and ranks the gaps by realism value vs integration cost against the current architecture's extension points. Output is a reviewed backlog document, never code. Not for planning the implementation itself (that's a phase plan via workflow) and not for bug hunting.
---
# realism-scan — what does the real world have that our sim doesn't?

The project's goal is to simulate real-world traffic flow as faithfully as an honest
system can (docs/vision.md). This skill is the periodic gap hunt that keeps the ladder
climbing: it produces the menu; Stepan picks; the phase plan implements.

## The procedure

1. **Inventory what exists.** Read `docs/plans/` (current phase + drafts) and skim
   `src/traffic_rl/` module docstrings. Write the capability list down — the scan is
   only as honest as this step.
2. **Sweep the categories** (each one, every time — misses hide in skipped categories):
   - road users & vehicle types (trucks, buses, bikes, emergency vehicles);
   - driver & pedestrian behavior/psychology (aggression, distraction, patience,
     compliance);
   - signals & infrastructure (head types, protected arrows, sensors, preemption);
   - perception (detection confidence, occlusion, latency, false positives);
   - events & chaos (crashes, stalls, construction, weather, special events);
   - demand patterns (rush shapes, loops/multi-stop trips, seasonal/night);
   - network & topology (chains, grids, roundabouts, irregular geometry).
   Web research is allowed and encouraged for grounding (what do real cities/standards
   actually have?); cite sources, mark claims `raw (YYYY-MM)`.
3. **For each candidate gap**, write four lines:
   - what real-world phenomenon it models;
   - **which extension point absorbs it** (ObservationModel, per-agent parameter
     arrays, topology graph, phase table, demand/trip schema, event hooks) — if NO
     extension point fits, that is an architecture finding, flag it loudly;
   - integration cost (S/M/L) and any prerequisite;
   - expected payoff: which metric it moves, what it makes visible in the viewer, what
     post it feeds.
4. **Rank and write** `docs/plans/realism-backlog.md` (append/update, newest scan
   dated at top; prune entries that shipped or died). Ranking = realism value ×
   post value ÷ cost, judged, not computed.
5. **Review with Stepan.** The backlog feeds the next phase plan; this skill never
   starts implementation on its own.
