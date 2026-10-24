# S4 live test: plan (needs the owner's OK; nothing below has been run)

> **ON HOLD (2026-10-23 ~08:00 PKT).** The owner is not confident in S4 and will check it manually. Two findings since this plan was written:
> - **Exit flag fixed.** `--hold-slots 1` would have sold about one slot earlier than the replay. The replay's exit (after every trade of the slot after our buy) is `--hold-slots 2`, which is Run 2's exit. So S4 differs from rule #2 only in the deployer list and the price guard.
> - **Live tapes** (`ops/overnight/live/LIVE_TAPES.md`): in all 5 real PROD fills, nobody traded between our buy and our sell. On 8HSxaXd3, two buyers (0.39 and 0.47 SOL) landed right after us and failed on slippage; at the price before our buy, both would have filled. The replay keeps such followers, so its numbers are optimistic until it models each follower's slippage limit. That re-scoring is in progress.


**What S4 does:** buys 0.5 SOL on launches whose create transaction is signed by a deployer on the list. The list is copied from 9Sh2fd / DGmspi's attempts; use the gated file: 85 deployers. The buy has a 1% price guard: it **fails** unless we are first after the dev's bundle. The sell is one sell at the end of the slot after the buy (`--hold-slots 2`).

## Prediction to beat (replay, verifier-checked)

At our measured 75 ms landing:
- about **36 attempts/h**, of which about **32% fill** (12/h);
- per fill: mean **+0.057 SOL**, median +0.035;
- 15 fills at 0.5 SOL: expected **+0.70 SOL** (5–95%: +0.19 to +1.28), P(loss) about 1%. This assumes 2% buy overhead and 0.005 per failed buy.
- At Run 2's fees (0.024 per buy, 0.011 per failed buy) expect about **+0.30**. **Lower the priority fee:** a failed guarded buy pays it, while tips revert.

- Risk in the replay window (75 ms, 0.5 SOL, 7.4 h): worst single trade −0.030 SOL; no fill lost more than 10%; max drawdown −0.20 SOL; longest losing run 20 attempts. A −0.3 SOL loss cap should not trigger unless reality differs from the replay.

- **Time of day matters.** S4G at 1 SOL, 75 ms, by hour in **PKT (UTC+5)**, both data periods (`ops/overnight/report/hours_pkt.json`):
  - 23:00–07:00 PKT: 7–27 fills per hour, +0.8 to +3.5 SOL per hour (best 04:00 PKT, +3.5);
  - 07:00–18:00 PKT: 2–13 fills per hour, about −0.1 to +0.7 SOL per hour. These hours come only from the old-data period, whose landing model is pessimistic, so part of the gap may be the model, not the hour;
  - 18:00–22:00 PKT: no data yet.
  - A daytime test (PKT) fills slowly and is near flat in the replay. Late evening to early morning PKT gives a faster, clearer read.

**If the live run is clearly below this range, the replay is wrong somewhere.** Stop and check with `verify_live.py` (below) before going on.

## Steps

1. **Binary:** host build `~/sniper-data/work/s4/snipe_engine_s4`. It is the current engine plus `--deployer-list`, off unless the flag is set. Copy it to `/root/sniper-s4/` on the server.
2. **List:** `ops/overnight/dryrun/deployer_list_gated.txt`, rebuilt every 15 min on the host by the dry-run loop. Copy it to `/root/sniper-s4/deployer_list.txt`. The engine re-reads the file every 30 s.
   - A list frozen for 10–29 h still made about 85% as much in the replay, so refreshing it every hour or two during the test is enough. For example, from the host: `scp -P 1996 ~/sniper/ops/overnight/dryrun/deployer_list_gated.txt it@84.32.100.36:/tmp/dl.txt`, then on the server move it into place with sudo.
   - Keep creates that land late in their slot; do **not** use `--max-create-ms`. In the replay, late creates were S4's best group (+1.9 SOL replay / +0.9 old on about 100 launches each), because fast snipers miss the slot.
3. **Flags:**
   - `ops/s4/s4_flags.sh` (S4_FLAGS);
   - plus Run 2's send/route flags from `ops/run1/run1_common.sh` (unchanged path);
   - plus your fee choice (suggestion: `--cu-price-micro` about 10M instead of 110M).
4. **Wallet and caps:** FRZ (DEV), `--spend-lamports 500000000 --max-buys 15 --max-loss-sol 0.3 --minutes 120`.
   - Stop with SIGTERM.
   - A background-launched engine ignores SIGINT.
5. **Watch while it runs:**
   - fill rate (landed buys ÷ fires) should be roughly 25–40%;
   - each landed buy should be followed by a sell within about 1 s;
   - a non-slippage failure means stop. M-2 already stops after 3.
6. **After the run:**
   - Sync: run the dry-run loop's cycle, or `~/sniper-data/work/sync.sh` plus phase-A rebuild into phaseA_dry.
   - Then run `RP_PHASEA_R2=phaseA_dry python3 -I ops/overnight/core/verify_live.py FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS <run start unix>`.
   - For every round trip it prints:
     - the real SOL in and out;
     - the exact replay at the real positions, which must match to the lamport;
     - the model's place for our landing ms vs the real place.

## Optional cheap landing step (a send-path change: your OK)

From the landing study (`ops/overnight/landing/LANDING_PATHS.md`, sniper-sized buys):

| Path | In create slot | Median landing | Tip |
|---|---|---|---|
| LandX alone | 74% | 37 ms | ~1% of size |
| Helius Sender (best on BAM / Jito leaders) | 62% | 51 ms | 0.2% |
| Our current one transaction carrying 5 tips | 35% | 168 ms | about 2% (pays every tip) |

- **Option:** try `--route-by-client` with one route per client, e.g. `bam=landx-fra3;jito=landx-fra3;harmonic=nozomi;fd=landx-fra3;default=landx-fra3`.
- **Effect:** one tip, no fan-out.
- **Comparison:** the replay says S4 goes from +4.0 (75 ms) to about +5.9 (45 ms) per 7.4 h.
- **How:** measure our landing ms per fill against the current routes, alternating by hour, before switching.
- **Later:** durable-nonce fan-out (one copy per service) is the bigger upgrade. It is engineering work.

## Then

- **PROD at 0.5 SOL:** only if FRZ fills match the replay.
- **Then 1 SOL per buy (S4G_1SOL):** use the gated list `deployer_list_gated.txt`. It needs no engine change, just `--spend-lamports 1000000000`.
  - Replay at 75 ms: +9.1 SOL per 7.4 h (old data +4.4).
  - Stress: +6.0 if the case wallets fail after us, +2.0 if 30% of followers also vanish.
- **Guard:** the flags now use 0.5% (`--slip-cap-bps 50`); it was slightly better than 1% in both periods.
- **Next upgrades**, measured in the replay:
  - Quality gate + 1 SOL on proven deployers (S4GS): +7.0 vs +4.0 SOL per 7.4 h at 75 ms. Needs per-deployer size support in the engine.
  - Durable-nonce fan-out landing, about 45 ms: +5.9 (S4) / +11.0 (S4GS) per 7.4 h. This is a send-path change, so it needs your OK.
