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
