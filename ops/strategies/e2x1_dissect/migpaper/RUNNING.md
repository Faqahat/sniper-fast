# migpaper RUNNING — paper forward test of the near-graduation rule (FROZEN.md), updated 11-01 00:29 PKT
PAPER ONLY, local only. Expected SOL per entry over the 10 landing samples; costs 2.9 mSOL/trip + 0.005 mSOL per landed pre-send try + 0.3 mSOL per reactive revert (replay costs). `try0.3` = pre-send tries at 0.3 mSOL each; `rev0.005` = reactive reverts at 0.005 mSOL.

**Row status (LOOKAHEAD_AUDIT.md, FROZEN.md 10-29 addendum): reactive row = clean; pre-send (crossing-gate) row has a known timing leak (LOOKAHEAD_AUDIT.md: its p30 gate uses the crossing trade, but the pre-sent tries go out before it); ARM-gate row = clean pre-send (same frozen p30 at the arm trade, vSOL ≥ 100).**

Scored: 36 windows = 72 h (10-29 00:00 → 11-01 00:00 PKT). Crossings of 105 in the windows: 1383, entrable 799, p30 ≥ 0.8: 125 entries, of which graduated 118.

## Running totals (SOL)
| row | entries | fills | graduated | P&L graduated | P&L failed | total | SOL/day (running) | per entry | top-5 share | w/o top-5 | try0.3 / rev0.005 | unresolved | 10-29 | 10-30 | 10-31 | pass bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pre-send 2 SOL, −20 % stop (HEADLINE) | 125 | 49.4 | 118 | +5.781 | -2.556 | **+3.226** | **+1.08** | +0.0653 | 54% | +1.481 | +3.016 | 0 | +2.74 | -0.18 | +0.66 | fail so far |
| pre-send 2 SOL, predictor-drop stop | 125 | 49.4 | 118 | +7.918 | -5.327 | **+2.591** | **+0.86** | +0.0525 | 90% | +0.250 | +2.382 | 0 | +2.60 | -0.67 | +0.66 | fail so far |
| reactive 2 SOL, −20 % stop | 125 | 48.6 | 118 | +5.385 | -2.733 | **+2.653** | **+0.88** | +0.0546 | 68% | +0.845 | +2.675 | 0 | +2.09 | +0.24 | +0.32 | fail so far |
| reactive 2 SOL, predictor-drop stop | 125 | 48.6 | 118 | +8.841 | -5.376 | **+3.465** | **+1.15** | +0.0713 | 91% | +0.309 | +3.487 | 0 | +3.52 | -0.32 | +0.26 | fail so far |
| pre 2 SOL ARM-gate, −20 % stop (clean pre-send; not the pass-bar row) | 104 | 32.0 | 103 | +4.175 | -0.000 | **+4.175** | **+1.39** | +0.1305 | 22% | +3.264 | +4.170 | 0 | +2.57 | +1.15 | +0.46 | (info) |

Pass bar (FROZEN.md): headline row ≥ +1.5 SOL/day over the 3 PKT days with each day ≥ 0 (+ replay check at the end). Days not yet scored show +0.00.
WARNING: 1 window(s) scored without a full look-ahead (tape ended early): 10-30 00:00

## Per window (headline row = pre-send −20 % stop; react −20 % alongside)
| window (PKT) | cross | entrable | entries | grad | pre −20% | pre pd | react −20% | react pd | pre fills | pre tries | unres | ARM-gate entries | ARM-gate −20% | secs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10-29 00:00–02:00 | 52 | 35 | 6 | 5 | +0.010 | +0.247 | +0.155 | +1.099 | 2.8 | 58 | 0 | 4 | +0.105 | 51 |
| 10-29 02:00–04:00 | 32 | 25 | 6 | 5 | +0.157 | +0.207 | -0.111 | -0.003 | 3.7 | 136 | 0 | 4 | +0.404 | 19 |
| 10-29 04:00–06:00 | 33 | 28 | 2 | 2 | +0.143 | +0.143 | +0.154 | +0.154 | 1.3 | 5 | 0 | 2 | -0.548 | 16 |
| 10-29 06:00–08:00 | 29 | 22 | 1 | 0 | -0.408 | -1.760 | -0.416 | -1.756 | 1.0 | 7 | 0 | 0 | +0.000 | 16 |
| 10-29 08:00–10:00 | 22 | 18 | 2 | 2 | -0.408 | +0.398 | -0.408 | +0.398 | 1.0 | 7 | 0 | 2 | -0.408 | 16 |
| 10-29 10:00–12:00 | 23 | 16 | 4 | 4 | +0.295 | +0.295 | +0.295 | +0.295 | 1.4 | 0 | 0 | 4 | +0.295 | 12 |
| 10-29 12:00–14:00 | 21 | 18 | 7 | 7 | +0.428 | +0.428 | +0.428 | +0.428 | 2.1 | 0 | 0 | 7 | +0.428 | 12 |
| 10-29 14:00–16:00 | 23 | 19 | 14 | 14 | +0.662 | +0.662 | +0.663 | +0.663 | 4.5 | 210 | 0 | 12 | +0.666 | 13 |
| 10-29 16:00–18:00 | 29 | 18 | 8 | 8 | +0.675 | +0.675 | +0.675 | +0.675 | 3.1 | 0 | 0 | 8 | +0.675 | 17 |
| 10-29 18:00–20:00 | 42 | 27 | 5 | 5 | +0.549 | +0.549 | +0.549 | +0.549 | 1.7 | 0 | 0 | 5 | +0.549 | 20 |
| 10-29 20:00–22:00 | 42 | 29 | 4 | 4 | +0.405 | +0.405 | +0.405 | +0.405 | 1.5 | 5 | 0 | 3 | +0.139 | 23 |
| 10-29 22:00–00:00 | 54 | 39 | 6 | 6 | +0.238 | +0.356 | -0.295 | +0.612 | 2.6 | 105 | 0 | 5 | +0.260 | 26 |
| 10-30 00:00–02:00 | 58 | 41 | 9 | 8 | -0.232 | -0.223 | -0.224 | -0.216 | 2.9 | 14 | 0 | 8 | +0.228 | 24 |
| 10-30 02:00–04:00 | 65 | 46 | 7 | 7 | +0.080 | +0.080 | +0.225 | +0.225 | 2.1 | 19 | 0 | 6 | +0.112 | 28 |
| 10-30 04:00–06:00 | 34 | 21 | 2 | 2 | -0.017 | -0.017 | -0.017 | -0.017 | 1.7 | 0 | 0 | 2 | -0.017 | 18 |
| 10-30 06:00–08:00 | 50 | 16 | 1 | 1 | -0.389 | +0.334 | -0.318 | +0.333 | 1.0 | 9 | 0 | 0 | +0.000 | 20 |
| 10-30 08:00–10:00 | 48 | 22 | 3 | 1 | -0.856 | -2.293 | -0.856 | -2.293 | 2.0 | 23 | 0 | 1 | -0.000 | 18 |
| 10-30 10:00–12:00 | 27 | 3 | 1 | 1 | -0.000 | -0.000 | -0.000 | -0.000 | 0.0 | 0 | 0 | 1 | -0.000 | 13 |
| 10-30 12:00–14:00 | 18 | 7 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 13 |
| 10-30 14:00–16:00 | 20 | 10 | 3 | 3 | +0.326 | +0.326 | +0.326 | +0.326 | 1.8 | 0 | 0 | 3 | +0.326 | 14 |
| 10-30 16:00–18:00 | 46 | 24 | 9 | 9 | +0.405 | +0.405 | +0.404 | +0.404 | 1.8 | 0 | 0 | 8 | +0.405 | 18 |
| 10-30 18:00–20:00 | 62 | 29 | 2 | 2 | +0.698 | +0.698 | +0.687 | +0.687 | 1.1 | 5 | 0 | 1 | +0.020 | 19 |
| 10-30 20:00–22:00 | 69 | 38 | 3 | 3 | +0.039 | +0.039 | +0.039 | +0.039 | 0.2 | 0 | 0 | 3 | +0.039 | 28 |
| 10-30 22:00–00:00 | 49 | 26 | 3 | 3 | -0.231 | -0.019 | -0.026 | +0.194 | 1.4 | 16 | 0 | 2 | +0.040 | 26 |
| 10-31 00:00–02:00 | 48 | 29 | 3 | 3 | +0.020 | +0.020 | +0.020 | +0.020 | 0.2 | 0 | 0 | 3 | +0.020 | 26 |
| 10-31 02:00–04:00 | 35 | 27 | 1 | 1 | +0.198 | +0.198 | -0.000 | -0.000 | 1.0 | 5 | 0 | 0 | +0.000 | 21 |
| 10-31 04:00–06:00 | 15 | 7 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 20 |
| 10-31 06:00–08:00 | 22 | 15 | 1 | 1 | +0.008 | +0.008 | +0.017 | +0.017 | 1.0 | 12 | 0 | 0 | +0.000 | 19 |
| 10-31 08:00–10:00 | 26 | 9 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 16 |
| 10-31 10:00–12:00 | 18 | 5 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 13 |
| 10-31 12:00–14:00 | 10 | 3 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 12 |
| 10-31 14:00–16:00 | 30 | 10 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 15 |
| 10-31 16:00–18:00 | 35 | 22 | 1 | 1 | -0.006 | -0.006 | -0.156 | -0.210 | 1.0 | 74 | 0 | 0 | +0.000 | 18 |
| 10-31 18:00–20:00 | 61 | 34 | 7 | 7 | +0.267 | +0.267 | +0.267 | +0.267 | 2.4 | 0 | 0 | 7 | +0.267 | 23 |
| 10-31 20:00–22:00 | 81 | 32 | 4 | 3 | +0.171 | +0.171 | +0.171 | +0.171 | 1.1 | 0 | 0 | 3 | +0.171 | 27 |
| 10-31 22:00–00:00 | 54 | 29 | 0 | 0 | +0.000 | +0.000 | +0.000 | +0.000 | 0.0 | 0 | 0 | 0 | +0.000 | 26 |

## Per day (PKT)
| day | entries | graduated | pre −20% | pre pd | react −20% | react pd | ARM-gate entries | ARM-gate −20% |
|---|---|---|---|---|---|---|---|---|
| 10-29 | 65 | 62 | +2.745 | +2.604 | +2.094 | +3.518 | 56 | +2.566 |
| 10-30 | 43 | 40 | -0.177 | -0.670 | +0.240 | -0.318 | 35 | +1.151 |
| 10-31 | 17 | 16 | +0.657 | +0.657 | +0.318 | +0.264 | 13 | +0.458 |

## 5 best / 5 worst entries — pre-send 2 SOL, −20 % stop (HEADLINE)
| when (PKT) | token | p30 | vSOL | SOL left | age s | completed after | fill | fill vSOL | exit | SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-30 19:58:29 | [2gTbp2gw](https://gmgn.ai/sol/token/2gTbp2gwH46rqExzabSyrdR3294SLwCp2rSqWDS6Sim1) | 0.91 | 110.3 | 4.7 | 11 | 1.272 s | 1.0 | 110.867955 | grad | +0.678 |
| 10-29 01:53:02 | [EYRFvigY](https://gmgn.ai/sol/token/EYRFvigYfVuVstVWdQXi9N86Dy5u6SBYHjkXdt39pump) | 0.87 | 106.7 | 8.3 | 17 | 6.574 s | 1.0 | 105.599563 | grad | +0.386 |
| 10-29 21:03:32 | [2NkrkugT](https://gmgn.ai/sol/token/2NkrkugTLN7PqLyorv2wCt1GwYSHW9tj6N9RLuYPpump) | 0.82 | 106.4 | 8.6 | 0 | 1.697 s | 1.0 | 107.544106 | grad | +0.266 |
| 10-29 19:42:22 | [DeiuV7Sc](https://gmgn.ai/sol/token/DeiuV7Sc4nS9tDXkBpnYRWrihgEb4ZfEor6iX5Axpump) | 0.99 | 109.7 | 5.3 | 0 | 0.0 s | 0.7 | 109.665768 | grad | +0.217 |
| 10-31 03:05:19 | [nG3jfPQH](https://gmgn.ai/sol/token/nG3jfPQHU2ZQhPERkTZD8YPSAsrrWiePPDcm9jxpump) | 0.87 | 106.7 | 8.3 | 2 | 0.212 s | 1.0 | 111.234033 | grad | +0.198 |
| 10-29 07:53:52 | [2KHLKWnC](https://gmgn.ai/sol/token/2KHLKWnCKo7znW26Nz3xd4JtwsEY8R1tZKNYrMB4pump) | 0.82 | 106.1 | 8.9 | 27 | never | 1.0 | 105.964906 | stop | -0.408 |
| 10-30 08:15:32 | [5VULVWGD](https://gmgn.ai/sol/token/5VULVWGDpYnSZZynbmxpfrbuwPS49oFM1B25vtGXpump) | 0.87 | 106.7 | 8.3 | 17 | never | 1.0 | 106.722237 | stop | -0.421 |
| 10-30 09:26:03 | [HFF7uvAe](https://gmgn.ai/sol/token/HFF7uvAexQqu8zpKMCErqtFP1QiJvHRCbci8jFjnpump) | 0.90 | 105.9 | 9.1 | 16 | never | 1.0 | 105.901718 | stop | -0.435 |
| 10-30 01:28:13 | [BVTfKyTw](https://gmgn.ai/sol/token/BVTfKyTwhWu7ZFgWJU8PpUBAYmoCJRU3cXxsE1rqpump) | 0.82 | 105.3 | 9.7 | 21 | never | 1.0 | 105.327385 | stop | -0.459 |
| 10-29 01:38:24 | [3w7SRf7m](https://gmgn.ai/sol/token/3w7SRf7mN3Kc2LXDnLUptykLVsbCuZMpxq2U6zEypump) | 0.94 | 109.1 | 5.9 | 3 | never | 1.0 | 109.500252 | stop | -0.481 |

## 5 best / 5 worst entries — reactive 2 SOL, −20 % stop
| when (PKT) | token | p30 | vSOL | SOL left | age s | completed after | fill | fill vSOL | exit | SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-30 19:58:29 | [2gTbp2gw](https://gmgn.ai/sol/token/2gTbp2gwH46rqExzabSyrdR3294SLwCp2rSqWDS6Sim1) | 0.91 | 110.3 | 4.7 | 11 | 1.272 s | 1.0 | 111.121785 | grad | +0.667 |
| 10-29 01:53:02 | [EYRFvigY](https://gmgn.ai/sol/token/EYRFvigYfVuVstVWdQXi9N86Dy5u6SBYHjkXdt39pump) | 0.87 | 106.7 | 8.3 | 17 | 6.574 s | 1.0 | 94.146489 | stop | +0.480 |
| 10-29 21:03:32 | [2NkrkugT](https://gmgn.ai/sol/token/2NkrkugTLN7PqLyorv2wCt1GwYSHW9tj6N9RLuYPpump) | 0.82 | 106.4 | 8.6 | 0 | 1.697 s | 1.0 | 107.544106 | grad | +0.266 |
| 10-29 19:42:22 | [DeiuV7Sc](https://gmgn.ai/sol/token/DeiuV7Sc4nS9tDXkBpnYRWrihgEb4ZfEor6iX5Axpump) | 0.99 | 109.7 | 5.3 | 0 | 0.0 s | 0.7 | 109.665768 | grad | +0.217 |
| 10-29 12:31:12 | [5THA5hee](https://gmgn.ai/sol/token/5THA5heeJgXsULasqETYxSJAEZKwPZXZWASFjbMNpump) | 1.00 | 112.6 | 2.4 | 0 | 0.212 s | 0.7 | 112.600633 | grad | +0.178 |
| 10-29 01:38:24 | [3w7SRf7m](https://gmgn.ai/sol/token/3w7SRf7mN3Kc2LXDnLUptykLVsbCuZMpxq2U6zEypump) | 0.94 | 109.1 | 5.9 | 3 | never | 1.0 | 105.833729 | stop | -0.430 |
| 10-30 09:26:03 | [HFF7uvAe](https://gmgn.ai/sol/token/HFF7uvAexQqu8zpKMCErqtFP1QiJvHRCbci8jFjnpump) | 0.90 | 105.9 | 9.1 | 16 | never | 1.0 | 105.901718 | stop | -0.435 |
| 10-30 01:28:13 | [BVTfKyTw](https://gmgn.ai/sol/token/BVTfKyTwhWu7ZFgWJU8PpUBAYmoCJRU3cXxsE1rqpump) | 0.82 | 105.3 | 9.7 | 21 | never | 1.0 | 105.058326 | stop | -0.451 |
| 10-29 22:37:02 | [43g7z6EP](https://gmgn.ai/sol/token/43g7z6EPGoeahLcEDQaP4gm1E7KzWNCH1MZ46RURpump) | 0.81 | 105.1 | 9.9 | 5 | 7.635 s | 1.0 | 101.995122 | stop | -0.555 |
| 10-29 03:26:46 | [Bu1tNXH6](https://gmgn.ai/sol/token/Bu1tNXH6FWzPUMEN9xYqypAf5DcBGwLPh6uveKJApump) | 0.85 | 108.1 | 6.9 | 8 | never | 1.0 | 103.707012 | stop | -0.579 |

## Mechanics (all entries)
- react: fill 39%, late (completed before landing) 52%, guard revert 9%, pre-miss 0%, pre-sent share of fills 0%, we complete the curve 11%, mean fill vSOL 110.6, landing 0.13 slots after the crossing, sniped at open 12% of graduated, tries/entry 0
- pre: fill 40%, late (completed before landing) 50%, guard revert 8%, pre-miss 3%, pre-sent share of fills 15%, we complete the curve 12%, mean fill vSOL 111.0, landing 0.48 slots after the crossing, sniped at open 12% of graduated, tries/entry 6

Replay check (FROZEN.md pass bar, 2nd clause): deferred to the run end (needs ~1 GB temporary disk); not done yet.
