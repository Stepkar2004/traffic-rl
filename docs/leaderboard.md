# Phase-1 leaderboard: classical controllers

Protocol (ADR 0002 §6): 20 seeds per cell, 300 s warmup excluded, 3600 s measurement window, mean [95% bootstrap CI] over seeds.

**Read the brackets before the means: no two controllers are called different when their CIs overlap.**

Honesty notes:

- Webster's flow channel is omniscient in phase 1 (true arrival rates); phase 3 replaces it with noisy detection, same channel.
- Webster runs on the sim's MEASURED saturation flow (1440 veh/h, startup lost 1.60 s), never textbook constants.
- ActuatedGapOut sees only a stop-line loop + 50 m advance detector.
- FixedTime runs a deliberately naive 50/50 split - it is the floor, and losing to it means something is broken.
- refusals > 0 would mean a controller tried to break the signal machine's safety interlocks. forced > 0 means the max-red cap fired: either a genuinely starved road user (night max-pressure: blind to pedestrians, so the machine rescues them), or the first arrival on an approach whose green had been resting past the cap (night actuated: the cap front-runs a controller that honestly cannot see a distant car).

## single-balanced

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 66.3 [66.0, 66.6] | 7.9 [7.7, 8.1] | 26.8 [26.4, 27.2] | 1190 [1176, 1204] | 0.60 [0.54, 0.70] | 18.0 [17.6, 18.5] | 47.4 [46.6, 48.1] | 0.1/1.1 | 0 | 0.0 |
| webster | 65.4 [64.9, 65.8] | 6.8 [6.6, 7.1] | 23.6 [22.8, 24.5] | 1191 [1177, 1204] | 0.56 [0.54, 0.58] | 13.3 [13.0, 13.7] | 35.9 [35.0, 36.9] | 0.1/0.6 | 0 | 0.0 |
| actuated | 64.1 [63.8, 64.4] | 6.2 [6.1, 6.4] | 24.4 [23.8, 25.0] | 1189 [1176, 1202] | 0.56 [0.50, 0.64] | 16.0 [15.6, 16.4] | 44.1 [42.7, 45.5] | 0.1/0.7 | 0 | 0.0 |
| max_pressure | 66.1 [65.6, 66.6] | 7.0 [6.8, 7.3] | 24.6 [23.6, 25.6] | 1189 [1175, 1202] | 0.68 [0.61, 0.77] | 12.6 [12.3, 13.0] | 34.7 [33.8, 35.5] | 0.1/0.5 | 0 | 0.0 |

## single-night

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 59.0 [58.6, 59.4] | 7.3 [6.8, 7.9] | 25.2 [24.5, 26.1] | 235 [227, 242] | 0.68 [0.61, 0.76] | 11.4 [10.5, 12.3] | 33.7 [32.2, 35.4] | 0.0/0.3 | 0 | 0.0 |
| webster | 56.7 [56.5, 57.0] | 4.2 [3.9, 4.6] | 15.2 [14.3, 16.2] | 235 [227, 243] | 0.59 [0.54, 0.65] | 8.5 [7.9, 9.1] | 21.7 [20.8, 22.6] | 0.0/0.1 | 0 | 0.0 |
| actuated | 53.6 [53.3, 53.8] | 2.5 [2.2, 2.8] | 11.7 [11.0, 12.5] | 235 [227, 242] | 0.43 [0.36, 0.50] | 7.3 [6.5, 8.1] | 23.4 [20.4, 26.4] | 0.0/0.1 | 0 | 1.3 |
| max_pressure | 56.5 [56.2, 56.7] | 3.8 [3.6, 4.1] | 13.1 [12.3, 14.1] | 235 [227, 243] | 0.63 [0.59, 0.68] | 19.5 [17.5, 21.5] | 69.8 [61.8, 77.7] | 0.0/0.3 | 0 | 2.5 |

## single-rush-ns

| controller | travel time (s) | wait (s) | p95 wait (s) | throughput (veh/h) | stops/veh | ped wait (s) | p95 ped wait (s) | unserved (veh/ped) | refused | forced |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_time | 105.7 [98.0, 113.7] | 29.8 [25.2, 34.7] | 102.1 [84.6, 120.8] | 1219 [1207, 1231] | 1.73 [1.47, 2.00] | 18.8 [18.4, 19.2] | 48.3 [47.5, 49.0] | 0.0/2.4 | 0 | 0.0 |
| webster | 66.6 [65.9, 67.3] | 6.8 [6.4, 7.1] | 25.2 [24.0, 26.6] | 1221 [1208, 1234] | 0.65 [0.58, 0.73] | 16.6 [16.1, 17.1] | 44.4 [43.2, 45.5] | 0.0/0.8 | 0 | 0.0 |
| actuated | 64.8 [64.3, 65.4] | 5.9 [5.7, 6.3] | 23.8 [22.8, 24.9] | 1222 [1210, 1234] | 0.55 [0.50, 0.60] | 17.8 [17.3, 18.2] | 48.4 [47.1, 49.7] | 0.0/1.0 | 0 | 0.0 |
| max_pressure | 72.8 [71.6, 74.0] | 9.2 [8.7, 9.7] | 29.8 [28.5, 31.2] | 1222 [1210, 1235] | 0.90 [0.84, 0.96] | 14.8 [14.3, 15.4] | 40.8 [39.0, 43.0] | 0.0/1.4 | 0 | 0.0 |
