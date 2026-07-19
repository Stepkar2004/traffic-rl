# Leaderboard: classical controllers

Protocol (ADR 0002 §6): 20 seeds per cell, 300 s warmup excluded, 3600 s measurement window, mean [95% bootstrap CI] over seeds.

**Read the brackets before the means: no two controllers are called different when their CIs overlap.**

Honesty notes:

- Webster's flow channel is omniscient (true arrival rates) in every phase so far: ADR 0005 deliberately keeps flow noise-free in phase 3 (detection-derived flow is a recorded deferred extension).
- Webster runs on the sim's MEASURED saturation flow (1440 veh/h, startup lost 1.60 s), never textbook constants.
- ActuatedGapOut sees only a stop-line loop + 50 m advance detector.
- FixedTime runs a deliberately naive 50/50 split - it is the floor, and losing to it means something is broken.
- Coordinated (multi-intersection scenarios only) is FixedTime plus travel-time offsets - the hand-built green wave. One-way progression: the counter-direction pays for the wave, and that is reported, not hidden.
- max_pressure runs its network form on corridors/grids (subtracts true downstream-link occupancy via the Observation); single-intersection rows keep the phase-1 sink form for comparability.
- refusals > 0 would mean a controller tried to break the signal machine's safety interlocks. forced > 0 means the max-red cap fired: either a genuinely starved road user (night max-pressure: blind to pedestrians, so the machine rescues them), or the first arrival on an approach whose green had been resting past the cap (night actuated: the cap front-runs a controller that honestly cannot see a distant car).

## corridor-balanced

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 79.1 [78.7, 79.6] | 12.9 [12.7, 13.2] | 43.0 [42.1, 44.0] | 2008 [1989, 2026] | 0.73 [0.73, 0.74] | 17.6 [17.2, 17.9] | 47.8 [47.2, 48.3] | 0.1/4.5 | 0 | 0.0 |
| coordinated | 78.9 [78.5, 79.3] | 12.3 [12.1, 12.5] | 48.1 [47.0, 49.3] | 2008 [1988, 2026] | 0.73 [0.73, 0.74] | 17.7 [17.5, 18.0] | 47.9 [47.3, 48.5] | 0.1/3.2 | 0 | 0.0 |
| webster | 75.8 [75.4, 76.2] | 8.5 [8.2, 8.7] | 30.3 [29.4, 31.1] | 2007 [1987, 2025] | 0.74 [0.73, 0.75] | 12.4 [12.2, 12.6] | 33.9 [33.5, 34.3] | 0.1/1.7 | 0 | 0.0 |
| actuated | 74.6 [74.2, 75.0] | 8.0 [7.8, 8.2] | 29.1 [28.4, 29.8] | 2007 [1989, 2025] | 0.67 [0.66, 0.67] | 14.4 [14.1, 14.6] | 40.2 [39.4, 41.1] | 0.1/1.9 | 0 | 0.0 |
| max_pressure | 76.7 [76.1, 77.3] | 8.9 [8.6, 9.2] | 32.5 [30.7, 34.7] | 2006 [1987, 2024] | 0.78 [0.76, 0.79] | 12.0 [11.8, 12.2] | 33.2 [32.9, 33.6] | 0.1/1.9 | 0 | 0.0 |

## corridor-rush

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 193.0 [181.0, 204.1] | 81.2 [71.6, 90.6] | 348.2 [293.3, 403.0] | 1492 [1478, 1505] | 2.63 [2.48, 2.75] | 17.7 [17.4, 18.0] | 47.9 [47.4, 48.4] | 44.8/3.8 | 0 | 0.0 |
| coordinated | 183.7 [170.1, 196.4] | 73.8 [63.1, 84.3] | 311.3 [250.6, 370.3] | 1497 [1482, 1511] | 2.53 [2.35, 2.69] | 17.9 [17.6, 18.2] | 47.8 [47.4, 48.2] | 39.5/2.8 | 0 | 0.0 |
| webster | 102.0 [99.9, 104.3] | 16.7 [15.8, 17.7] | 49.4 [45.3, 53.5] | 1575 [1555, 1594] | 1.20 [1.15, 1.25] | 17.5 [17.0, 17.9] | 47.6 [46.4, 48.7] | 0.0/2.6 | 0 | 0.0 |
| actuated | 93.1 [92.4, 93.7] | 12.0 [11.7, 12.3] | 35.5 [34.7, 36.3] | 1568 [1550, 1587] | 0.94 [0.92, 0.96] | 17.8 [17.6, 18.0] | 49.4 [48.8, 49.9] | 0.0/2.5 | 0 | 0.0 |
| max_pressure | 245.5 [234.0, 256.6] | 112.8 [102.4, 122.7] | 568.3 [503.9, 630.0] | 1433 [1422, 1445] | 4.02 [3.92, 4.10] | 12.5 [12.2, 12.7] | 33.8 [33.4, 34.3] | 99.2/2.4 | 0 | 0.0 |

## grid-balanced

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 125.1 [124.8, 125.4] | 30.5 [30.3, 30.7] | 55.9 [55.2, 56.6] | 3010 [2989, 3030] | 1.49 [1.48, 1.49] | 16.3 [16.1, 16.5] | 46.0 [45.6, 46.3] | 0.1/9.1 | 0 | 0.0 |
| coordinated | 119.6 [119.1, 120.1] | 26.4 [26.2, 26.7] | 55.9 [55.1, 56.8] | 3012 [2992, 3031] | 1.38 [1.37, 1.39] | 16.3 [16.1, 16.5] | 46.5 [46.1, 46.8] | 0.1/6.0 | 0 | 0.0 |
| webster | 116.2 [115.7, 116.6] | 17.4 [17.1, 17.7] | 41.2 [40.5, 41.9] | 3014 [2994, 3034] | 1.52 [1.50, 1.54] | 11.3 [11.2, 11.5] | 32.4 [32.1, 32.6] | 0.1/4.3 | 0 | 0.0 |
| actuated | 113.2 [112.8, 113.7] | 15.8 [15.5, 16.0] | 42.6 [42.0, 43.3] | 3009 [2987, 3029] | 1.32 [1.31, 1.33] | 13.8 [13.6, 14.0] | 40.8 [40.0, 41.4] | 0.1/5.3 | 0 | 0.0 |
| max_pressure | 117.6 [117.2, 118.0] | 17.9 [17.7, 18.2] | 43.4 [42.7, 44.2] | 3014 [2992, 3034] | 1.59 [1.57, 1.60] | 10.9 [10.8, 11.1] | 31.4 [31.1, 31.8] | 0.1/4.1 | 0 | 0.0 |

## grid-rush-diag

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 154.0 [151.6, 156.9] | 45.3 [44.0, 46.9] | 94.9 [88.8, 102.5] | 3595 [3573, 3616] | 2.05 [2.00, 2.11] | 16.1 [15.9, 16.4] | 45.7 [45.5, 45.9] | 0.1/8.0 | 0 | 0.0 |
| coordinated | 142.1 [140.2, 144.1] | 37.3 [36.3, 38.4] | 83.3 [78.6, 88.2] | 3590 [3567, 3612] | 1.77 [1.72, 1.81] | 16.1 [16.0, 16.3] | 45.8 [45.3, 46.3] | 0.1/5.2 | 0 | 0.0 |
| webster | 151.5 [149.1, 154.1] | 39.7 [38.0, 41.4] | 87.9 [83.1, 93.0] | 3600 [3576, 3624] | 2.06 [2.01, 2.10] | 18.5 [18.2, 18.9] | 54.5 [53.4, 55.7] | 0.1/8.2 | 0 | 0.0 |
| actuated | 131.2 [130.5, 132.0] | 25.9 [25.5, 26.4] | 61.4 [60.4, 62.3] | 3605 [3581, 3628] | 1.57 [1.56, 1.59] | 19.4 [19.1, 19.8] | 56.5 [55.8, 57.3] | 0.1/7.5 | 0 | 0.0 |
| max_pressure | 192.5 [187.3, 198.0] | 54.3 [51.9, 56.8] | 125.0 [117.9, 132.6] | 3536 [3514, 3558] | 3.93 [3.77, 4.10] | 11.0 [10.9, 11.2] | 31.7 [31.4, 32.0] | 0.4/4.2 | 0 | 0.0 |

## single-balanced

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 66.3 [66.0, 66.6] | 7.9 [7.7, 8.1] | 26.8 [26.4, 27.1] | 1190 [1176, 1204] | 0.53 [0.52, 0.53] | 18.0 [17.6, 18.5] | 47.4 [46.6, 48.1] | 0.1/1.1 | 0 | 0.0 |
| webster | 65.4 [64.9, 65.8] | 6.8 [6.6, 7.1] | 23.6 [22.8, 24.5] | 1191 [1177, 1204] | 0.54 [0.53, 0.55] | 13.3 [13.0, 13.7] | 35.8 [35.0, 36.8] | 0.1/0.6 | 0 | 0.0 |
| actuated | 64.1 [63.8, 64.4] | 6.2 [6.0, 6.4] | 24.4 [23.8, 25.0] | 1189 [1176, 1202] | 0.48 [0.47, 0.48] | 16.0 [15.6, 16.4] | 44.0 [42.7, 45.5] | 0.1/0.7 | 0 | 0.0 |
| max_pressure | 66.1 [65.6, 66.6] | 7.0 [6.7, 7.3] | 24.6 [23.6, 25.6] | 1189 [1175, 1202] | 0.58 [0.57, 0.60] | 12.7 [12.3, 13.0] | 34.7 [33.8, 35.5] | 0.1/0.5 | 0 | 0.0 |

## single-night

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 59.0 [58.6, 59.4] | 5.6 [5.4, 5.9] | 23.3 [22.8, 23.9] | 235 [227, 242] | 0.42 [0.41, 0.44] | 11.4 [10.5, 12.3] | 33.7 [32.2, 35.4] | 0.0/0.3 | 0 | 0.0 |
| webster | 56.7 [56.5, 57.0] | 3.1 [2.9, 3.3] | 12.8 [12.3, 13.4] | 235 [227, 243] | 0.40 [0.39, 0.41] | 8.5 [7.9, 9.1] | 21.7 [20.8, 22.6] | 0.0/0.1 | 0 | 0.0 |
| actuated | 53.6 [53.3, 53.8] | 1.7 [1.6, 1.8] | 10.4 [10.1, 10.7] | 235 [227, 242] | 0.24 [0.23, 0.25] | 7.3 [6.5, 8.1] | 23.5 [20.5, 26.6] | 0.0/0.1 | 0 | 1.3 |
| max_pressure | 56.5 [56.2, 56.7] | 3.0 [2.9, 3.1] | 10.8 [10.2, 11.4] | 235 [227, 243] | 0.46 [0.45, 0.47] | 19.5 [17.6, 21.5] | 69.8 [61.8, 77.8] | 0.0/0.3 | 0 | 2.5 |

## single-rush-ns

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 105.7 [98.0, 113.7] | 29.3 [24.9, 34.0] | 101.6 [84.2, 120.3] | 1219 [1207, 1231] | 1.38 [1.22, 1.54] | 18.8 [18.4, 19.2] | 48.3 [47.5, 49.0] | 0.0/2.4 | 0 | 0.0 |
| webster | 66.6 [65.9, 67.3] | 6.8 [6.4, 7.1] | 25.2 [24.0, 26.6] | 1221 [1208, 1234] | 0.53 [0.51, 0.55] | 16.6 [16.1, 17.1] | 44.4 [43.2, 45.5] | 0.0/0.8 | 0 | 0.0 |
| actuated | 64.8 [64.3, 65.4] | 5.9 [5.7, 6.3] | 23.8 [22.8, 24.9] | 1222 [1210, 1234] | 0.46 [0.45, 0.47] | 17.7 [17.3, 18.2] | 48.4 [47.1, 49.7] | 0.0/1.0 | 0 | 0.0 |
| max_pressure | 72.8 [71.6, 74.0] | 9.1 [8.6, 9.7] | 29.8 [28.4, 31.2] | 1222 [1210, 1235] | 0.75 [0.72, 0.78] | 14.8 [14.3, 15.4] | 40.8 [39.0, 43.0] | 0.0/1.4 | 0 | 0.0 |
