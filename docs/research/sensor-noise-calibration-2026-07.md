# Sensor-noise calibration — is the phase-3 detection model realistic? (2026-07-18)

> Research note capturing WHY the phase-3 sensing-noise parameters were recalibrated, so the
> calibration logic is traceable later. Fulfills the open `[CITE — realism-scan to supply at
> review]` TODO in [ADR 0005](../decisions/0005-sensing-noise.md) §2 (line 85), and is the
> evidence base for the §7 amendment that recalibrates the bundle. Triggered by Stepan mid
> phase-3 (C4 session): "are we modeling it well?"

## The question

Phase 3 fogs the controllers' sensors with a single dial `q ∈ (0, 1]` (ADR 0005 §2). The phase-3
sweep sampled `q ∈ {1.0, 0.9, 0.75, 0.5, 0.25}` and the headline negative result — learned policies
lose to actuated under noise — was largely driven by the low-q rows. Before shipping that as a
finding, the question: **is the noise model at low q realistic, or is PPO failing against a
strawman sensor?**

## The original model, quantified (the problem)

The five mechanisms (`core/sensors.py`), with detection probability at representative points:

| q | lone car @ stop-line | lone car @ 200 m | **queued car (occluded)** |
|---|---|---|---|
| 1.0 | 1.00 | 1.00 | 1.00 |
| 0.75 | 0.875 | 0.75 | 0.66 |
| 0.5 | 0.75 | 0.50 | **0.375** |
| 0.25 | 0.625 | 0.25 | **0.16** |

The occlusion term multiplies `p_detect *= q` for any vehicle with a leader within 25 m — i.e. every
queued vehicle. So at `q = 0.5` a tight queue loses ~60% of its cars; at `q = 0.25`, ~85%. Plus
Gaussian position/speed error (σ = 4 m / 2 m·s⁻¹ at q=0, linear in 1−q) and false positives at
`0.3·(1−q)` per approach-lane per second (0.15/lane/s at q=0.5).

## What the literature says (external review + sources)

An independent review (another model + web search) mapped these mechanisms against published
detector performance. Summary of the findings, with sources below:

- **Modern stop-bar detection (video + radar fusion, the standard for new deployments) sits at
  ~95–99% detection in clear conditions.** Our `q=1` identity is right; the degradation *shape*
  (distance falloff, occlusion, dropout, jitter, false calls) matches real failure modes — but the
  *magnitudes* at low q are far harsher than any deployed stack.
- **Camera-only detection loses ~10–30% mAP in adverse weather** (heavy fog worst); **radar is
  essentially fog-immune**, so fused stacks stay ~0.8–0.9+ even in bad weather.
- **Occlusion is real for cameras but heavily mitigated in production:** trackers coast through
  occlusion instead of dropping the vehicle, cameras mount high to see over queues, and mmWave radar
  detects fully-occluded vehicles via multipath. **No production system loses 60–85% of a queue.**
  Our occlusion `×q` models occlusion as *independent per-vehicle existence failure*, when in reality
  it is a *tracking-continuity* problem that fusion + temporal persistence largely solve. This is the
  single least-realistic piece, and it is precisely what drives our queue-count collapse — and queue
  counts are exactly what a real detector is engineered to preserve.
- **Our false-positive rate (0.15/lane/s at q=0.5) is well above real false-call rates.**

**q → reality mapping** (adopted): `q ≈ 0.9–0.95` = modern fused stack, good conditions; `q ≈ 0.7`
= camera-only in bad weather, or an aging/legacy video detector; `q ≤ 0.5` = a *malfunctioning*
detector or cheap/legacy loop-only equipment, NOT "adverse conditions."

**Method caveat (independent of the sensor model):** at low q the environment is a heavily corrupted
POMDP, and a feedforward PPO policy has no mechanism to integrate over the 5 s correlated dropouts —
so *some* of the failure is the agent's lack of memory, not the sensor model. A recurrent policy or
frame-stacking (the C4 arm) is the experiment that separates the two. The review explicitly endorsed
this, which is exactly why C4 exists.

## Decision (2026-07-18) — recalibrate; amends ADR 0005 §2 under §7

Keep all five mechanisms (the structure is right); soften the magnitudes to match deployed sensors:

1. **Occlusion `×q` → `×√q`** (the #1 lever, Stepan's call). Queued near-stop detection at q=0.5
   rises from 0.375 to ~0.53; the queue stays mostly visible, as a real fused/tracked stack keeps it.
2. **Sweep floor raised to ~0.7** for "realistic adverse conditions" — grid becomes
   `{1.0, 0.9, 0.8, 0.7}` + one explicitly-labelled `~0.4` "legacy / degraded equipment" stress run
   (PPO collapsing there is a valid robustness finding, not "fails in fog").
3. **Lower the false-positive rate** (`FP_RATE 0.3 → 0.1`, i.e. 0.03/lane/s at q=0.7).
4. Position/speed σ kept (mild; ±2 m / ±1 m·s⁻¹ at q=0.5 is already reasonable).

**Runs invalidated (ADR 0005 §7):** the classical quality sweep (`phase3-quality.json`), the C2
zero-shot eval, and the C3 train-for-condition / C3-DR / C4 training arms (all trained or evaluated
under the old bundle). **NOT invalidated:** phase-1/2 (q=1.0 identity, unchanged), and the **C5
demand-generalist** arm (q=1.0 throughout — sensor-independent).

**Efficient re-run order** (let the data decide the expensive part): recalibrate → re-run the CHEAP
evals first (C1 classical sweep + C2 zero-shot, ~30–40 min batched). If PPO zero-shot now transfers
across the realistic q range (0.7–1.0), the C4 trigger does not fire and no retraining is needed —
a clean positive result. Only if a gap persists under realistic noise do we retrain C3 (train-for-
condition) and, if its q=0.7 arm still loses to actuated, C4 (memory).

## Sources

- Sensor fusion-based vehicle detection & tracking at a traffic intersection — https://pmc.ncbi.nlm.nih.gov/articles/PMC10222169/
- See Through Vehicles: fully-occluded vehicle detection with mmWave radar (Google) — https://research.google/pubs/see-through-vehicles-fully-occluded-vehicle-detection-with-millimeter-wave-radar/
- Object detection in adverse weather with YOLOv8 — https://pmc.ncbi.nlm.nih.gov/articles/PMC10611033/
- Deep camera–radar fusion for foggy conditions — https://pmc.ncbi.nlm.nih.gov/articles/PMC10383339/
- Weather/lighting impact on YOLO-SORT traffic monitoring — https://etasr.com/index.php/ETASR/article/view/18369
- TTI video image vehicle detection evaluation — https://static.tti.tamu.edu/tti.tamu.edu/documents/1467-4.pdf
