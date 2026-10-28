# migpaper RUNNING — paper forward test of the near-graduation rule (FROZEN.md), updated 10-29 04:29 PKT
PAPER ONLY, local only. Expected SOL per entry over the 10 landing samples; costs 2.9 mSOL/trip + 0.005 mSOL per landed pre-send try + 0.3 mSOL per reactive revert (replay costs). `try0.3` = pre-send tries at 0.3 mSOL each; `rev0.005` = reactive reverts at 0.005 mSOL.

**Row status (LOOKAHEAD_AUDIT.md, FROZEN.md 10-29 addendum): reactive row = clean; pre-send (crossing-gate) row has a known timing leak (LOOKAHEAD_AUDIT.md: its p30 gate uses the crossing trade, but the pre-sent tries go out before it); ARM-gate row = clean pre-send (same frozen p30 at the arm trade, vSOL ≥ 100).**

Scored: 2 windows = 4 h (10-29 00:00 → 10-29 04:00 PKT). Crossings of 105 in the windows: 84, entrable 60, p30 ≥ 0.8: 12 entries, of which graduated 10.

## Running totals (SOL)
| row | entries | fills | graduated | P&L graduated | P&L failed | total | SOL/day (running) | per entry | top-5 share | w/o top-5 | try0.3 / rev0.005 | unresolved | 10-29 | 10-30 | 10-31 | pass bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pre-send 2 SOL, −20 % stop (HEADLINE) | 12 | 6.5 | 10 | +0.998 | -0.832 | **+0.167** | **+1.00** | +0.0256 | 495% | -0.658 | +0.109 | 0 | +0.17 | +0.00 | +0.00 | fail so far |
| pre-send 2 SOL, predictor-drop stop | 12 | 6.5 | 10 | +1.277 | -0.823 | **+0.454** | **+2.73** | +0.0699 | 243% | -0.649 | +0.397 | 0 | +0.45 | +0.00 | +0.00 | PASS so far |
| reactive 2 SOL, −20 % stop | 12 | 6.7 | 10 | +1.054 | -1.010 | **+0.044** | **+0.27** | +0.0066 | 2002% | -0.841 | +0.046 | 0 | +0.04 | +0.00 | +0.00 | fail so far |
| reactive 2 SOL, predictor-drop stop | 12 | 6.7 | 10 | +1.979 | -0.884 | **+1.095** | **+6.57** | +0.1635 | 165% | -0.715 | +1.097 | 0 | +1.10 | +0.00 | +0.00 | PASS so far |
| pre 2 SOL ARM-gate, −20 % stop (clean pre-send; not the pass-bar row) | 8 | 3.0 | 8 | +0.509 | +0.000 | **+0.509** | **+3.06** | +0.1698 | 91% | +0.048 | +0.509 | 0 | +0.51 | +0.00 | +0.00 | (info) |

Pass bar (FROZEN.md): headline row ≥ +1.5 SOL/day over the 3 PKT days with each day ≥ 0 (+ replay check at the end). Days not yet scored show +0.00.

## Per window (headline row = pre-send −20 % stop; react −20 % alongside)
| window (PKT) | cross | entrable | entries | grad | pre −20% | pre pd | react −20% | react pd | pre fills | pre tries | unres | ARM-gate entries | ARM-gate −20% | secs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10-29 00:00–02:00 | 52 | 35 | 6 | 5 | +0.010 | +0.247 | +0.155 | +1.099 | 2.8 | 58 | 0 | 4 | +0.105 | 51 |
| 10-29 02:00–04:00 | 32 | 25 | 6 | 5 | +0.157 | +0.207 | -0.111 | -0.003 | 3.7 | 136 | 0 | 4 | +0.404 | 19 |

## Per day (PKT)
| day | entries | graduated | pre −20% | pre pd | react −20% | react pd | ARM-gate entries | ARM-gate −20% |
|---|---|---|---|---|---|---|---|---|
| 10-29 | 12 | 10 | +0.167 | +0.454 | +0.044 | +1.095 | 8 | +0.509 |

## 5 best / 5 worst entries — pre-send 2 SOL, −20 % stop (HEADLINE)
| when (PKT) | token | p30 | vSOL | SOL left | age s | completed after | fill | fill vSOL | exit | SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-29 01:53:02 | [EYRFvigY](https://gmgn.ai/sol/token/EYRFvigYfVuVstVWdQXi9N86Dy5u6SBYHjkXdt39pump) | 0.87 | 106.7 | 8.3 | 17 | 6.574 s | 1.0 | 105.599563 | grad | +0.386 |
| 10-29 02:13:33 | [6N3bbXrE](https://gmgn.ai/sol/token/6N3bbXrEQ5crQZ5RwfcRbEhNUkabWVVHHftwkpYMpump) | 0.99 | 113.6 | 1.4 | 0 | 0.212 s | 0.9 | 113.593299 | grad | +0.174 |
| 10-29 02:31:37 | [8MHruW28](https://gmgn.ai/sol/token/8MHruW28hJf26tDCHR6nGLMM1AkDRdcPXwzEoLWwpump) | 0.83 | 110.1 | 4.9 | 65 | 0.424 s | 1.0 | 110.095459 | grad | +0.103 |
| 10-29 02:27:22 | [DZYkvNnu](https://gmgn.ai/sol/token/DZYkvNnuL3GanzVw6h1ZhN9NMs2DQFAaXjHrYtUDpump) | 0.99 | 113.6 | 1.4 | 0 | 0.212 s | 0.3 | 113.593299 | grad | +0.083 |
| 10-29 02:44:44 | [5D4wLGzJ](https://gmgn.ai/sol/token/5D4wLGzJuNjEPEsCueRwUC1bE6Ewthw5Gzaxgezgpump) | 0.99 | 113.6 | 1.4 | 0 | 0.0 s | 0.7 | 113.593299 | grad | +0.079 |
| 10-29 01:08:10 | [EdWG7Ska](https://gmgn.ai/sol/token/EdWG7SkaP8AJVZ5R6C1XNwhPNrraqjH4BSk48XMhpump) | 1.00 | 113.6 | 1.4 | 0 | 0.0 s | 0.4 | 113.593299 | grad | +0.048 |
| 10-29 01:20:56 | [792PhuQd](https://gmgn.ai/sol/token/792PhuQdyRpZYcFy55n3y58tWevkcjyJq9gxY1qPpump) | 1.00 | 113.6 | 1.4 | 0 | 0.0 s | 0.0 | - | - | -0.000 |
| 10-29 01:40:45 | [7YQBjUWn](https://gmgn.ai/sol/token/7YQBjUWnybEnKCgvFaSjsDXX7fK8XrNA3cqRfoUKpump) | 1.00 | 113.6 | 1.4 | 0 | 0.0 s | 0.0 | - | - | -0.000 |
| 10-29 03:26:46 | [Bu1tNXH6](https://gmgn.ai/sol/token/Bu1tNXH6FWzPUMEN9xYqypAf5DcBGwLPh6uveKJApump) | 0.85 | 108.1 | 6.9 | 8 | never | 0.5 | 108.119631 | stop | -0.350 |
| 10-29 01:38:24 | [3w7SRf7m](https://gmgn.ai/sol/token/3w7SRf7mN3Kc2LXDnLUptykLVsbCuZMpxq2U6zEypump) | 0.94 | 109.1 | 5.9 | 3 | never | 1.0 | 109.500252 | stop | -0.481 |

## 5 best / 5 worst entries — reactive 2 SOL, −20 % stop
| when (PKT) | token | p30 | vSOL | SOL left | age s | completed after | fill | fill vSOL | exit | SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-29 01:53:02 | [EYRFvigY](https://gmgn.ai/sol/token/EYRFvigYfVuVstVWdQXi9N86Dy5u6SBYHjkXdt39pump) | 0.87 | 106.7 | 8.3 | 17 | 6.574 s | 1.0 | 94.146489 | stop | +0.480 |
| 10-29 02:13:33 | [6N3bbXrE](https://gmgn.ai/sol/token/6N3bbXrEQ5crQZ5RwfcRbEhNUkabWVVHHftwkpYMpump) | 0.99 | 113.6 | 1.4 | 0 | 0.212 s | 0.9 | 113.593299 | grad | +0.174 |
| 10-29 02:27:22 | [DZYkvNnu](https://gmgn.ai/sol/token/DZYkvNnuL3GanzVw6h1ZhN9NMs2DQFAaXjHrYtUDpump) | 0.99 | 113.6 | 1.4 | 0 | 0.212 s | 0.3 | 113.593299 | grad | +0.083 |
| 10-29 02:44:44 | [5D4wLGzJ](https://gmgn.ai/sol/token/5D4wLGzJuNjEPEsCueRwUC1bE6Ewthw5Gzaxgezgpump) | 0.99 | 113.6 | 1.4 | 0 | 0.0 s | 0.7 | 113.593299 | grad | +0.079 |
| 10-29 02:00:12 | [DSUhFPeK](https://gmgn.ai/sol/token/DSUhFPeKNFy3sMXh2dQTRvGfkpaLMiBtoa969UQZpump) | 1.00 | 113.6 | 1.4 | 0 | 0.212 s | 0.3 | 113.593299 | grad | +0.068 |
| 10-29 01:08:10 | [EdWG7Ska](https://gmgn.ai/sol/token/EdWG7SkaP8AJVZ5R6C1XNwhPNrraqjH4BSk48XMhpump) | 1.00 | 113.6 | 1.4 | 0 | 0.0 s | 0.4 | 113.593299 | grad | +0.048 |
| 10-29 01:20:56 | [792PhuQd](https://gmgn.ai/sol/token/792PhuQdyRpZYcFy55n3y58tWevkcjyJq9gxY1qPpump) | 1.00 | 113.6 | 1.4 | 0 | 0.0 s | 0.0 | - | - | -0.000 |
| 10-29 01:40:45 | [7YQBjUWn](https://gmgn.ai/sol/token/7YQBjUWnybEnKCgvFaSjsDXX7fK8XrNA3cqRfoUKpump) | 1.00 | 113.6 | 1.4 | 0 | 0.0 s | 0.0 | - | - | -0.000 |
| 10-29 01:38:24 | [3w7SRf7m](https://gmgn.ai/sol/token/3w7SRf7mN3Kc2LXDnLUptykLVsbCuZMpxq2U6zEypump) | 0.94 | 109.1 | 5.9 | 3 | never | 1.0 | 105.833729 | stop | -0.430 |
| 10-29 03:26:46 | [Bu1tNXH6](https://gmgn.ai/sol/token/Bu1tNXH6FWzPUMEN9xYqypAf5DcBGwLPh6uveKJApump) | 0.85 | 108.1 | 6.9 | 8 | never | 1.0 | 103.707012 | stop | -0.579 |

## Mechanics (all entries)
- react: fill 56%, late (completed before landing) 42%, guard revert 2%, pre-miss 0%, pre-sent share of fills 0%, we complete the curve 25%, mean fill vSOL 109.6, landing 0.13 slots after the crossing, sniped at open 20% of graduated, tries/entry 0
- pre: fill 54%, late (completed before landing) 42%, guard revert 0%, pre-miss 4%, pre-sent share of fills 29%, we complete the curve 25%, mean fill vSOL 111.5, landing 1.03 slots after the crossing, sniped at open 20% of graduated, tries/entry 16

Replay check (FROZEN.md pass bar, 2nd clause): deferred to the run end (needs ~1 GB temporary disk); not done yet.
