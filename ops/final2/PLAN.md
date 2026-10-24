# FINAL-2 "become them" strategy: path to a live test

> **CORRECTION 2026-10-23 11:05 PKT. Read `ops/overnight/report/DECISION.html` first.**
> - An independent check found 3 replay bugs in our favour. Corrected FINAL-2 (8 s, pros' later buys removed): 75 ms overnight +1.07, daytime −0.48.
> - The forward test 08:26–10:53 PKT is negative at every landing (75 ms −0.40, 45 ms −1.14, 20 ms −0.38).
> - FINAL-2 is now at best an overnight-only option. The lead candidate is the dip-backrun (`ops/dip/PLAN.md`), which needs ≤35–50 ms landing.
> - The numbers below are the pre-correction ones.


Prepared 2026-10-23 (PKT). Nothing here is deployed or run. Every step marked *(OK)* needs the owner's explicit go.

## The strategy (evidence: `ops/overnight/BECOME_THEM.md`)
1. **Pick:** FINAL-2, our own model. It scores every launch at the dev's glued-bundle close: 61 public features, a fast-dump veto, and guards (payer = creator; no "no bundle + dev < 1 SOL").
2. **Buy:** 0.5 SOL right after the bundle, **only if we are first**. The price guard sets min-out to the post-bundle quote minus 0.5%.
3. **Sell:** everything about **8 s** after the buy. General buyers arrive over 2–10 s. The quick sell loses once bot buys are removed.

**Replay result** (pros' later buys removed, follower slippage, 8 s hold), scaled to SOL per day at 0.5 SOL. *Corrected 09:30 PKT: the earlier daytime numbers used in-sample picks.*

| Setup | Daytime PKT (clean R1 tail, 3 h, small) | Overnight PKT (R2, 8.3 h) |
|---|---|---|
| Today's costs, 75 ms | −3.8 | +5.0 |
| CW-style costs, 75 ms | −2.4 | +6.9 |
| CW-style costs, 45 ms | −3.9 | +10.0 |
| CW-style costs, 30 ms | +1.0 | +15.2 |

**Run it overnight PKT only, until the forward test says otherwise.**

## Exit refinement candidate: "activity check" (A7, frozen 09:23 PKT, hash aeb761c6…)
- **Rule:** if at most 1 outside buy lands between our buy and the end of the next slot, sell at the end of that slot. Otherwise hold 8 s.
- **In replay** it beats the plain 8 s sell in every set and landing (pros' later buys removed, CW-style cost):

| Set | 75 ms | 45 ms |
|---|---|---|
| Live overnight picks | +2.38 → +3.19 | +3.44 → +4.16 |
| Offline overnight picks | +2.38 → +2.71 | +4.44 → +4.57 |
| Clean daytime slice | −0.31 → −0.15 | −0.50 → −0.25 |

- **Why it helps** (MEASURED, overnight picks, 75 ms, pros' later buys removed, CW cost):

| Outside buyers after us by end of next slot | Fills | Hold 8 s | Sell at end of next slot |
|---|---|---|---|
| 0 | 19 | −0.87 (2 wins) | −0.50 |
| 1 | 15 | −0.77 (1 win) | −0.33 |
| 2–3 | 32 | +0.61 | −0.32 |
| 4+ | 26 | **+3.84** | +0.69 |

  - All the profit is in fills that buyers follow right away. 0–1 followers: sell now. 2 or more: hold 8 s.
  - At 45 ms it's the same pattern: 4+ buyers make +5.24 at 8 s; 0–1 buyers lose −1.39 at 8 s vs −0.67 if sold early.
  - This is the owner's "no activity → you only lose fees" observation, measured.
- **Engine: BUILT (off by default).** Flags `--hold-activity-k 1 --hold-activity-cap-ms 800`.
  - From the fire, the event loop logs every tx touching our mint in feed order.
  - At the end of the slot after our buy it counts outside buy legs after our buy. With ≤ k it sells now; otherwise it uses the normal `--hold-ms` hold.
  - Log line: `HOLD-ACTIVITY`.
  - **Live vs replay difference:**
    - The replay counts successful buys (TradeEvents).
    - The engine counts **directly decoded pump buy legs** seen in the shred feed. These include some that later fail, and exclude buys routed through other programs.
    - Routed legs count only with `--hold-activity-unknown`. Bots re-sending failing conditional txs every slot (seen in our live tapes) would otherwise read as activity.
    - Compare the engine's `HOLD-ACTIVITY` counts with the replay after the first paper or live run.
  - **Checked against the replay** (MEASURED, overnight picks, fills only, pros' later buys removed, CW cost). The live-style count uses shadow-feed arrivals in the ~350 ms after our landing; only 42% of buy-like txs decode directly.

| Rule | 75 ms | 45 ms |
|---|---|---|
| Plain 8 s | +2.81 | +3.74 |
| Activity check, true successful-buy count | +3.62 | +4.46 |
| **Activity check, live-style count (decoded buys ≤ 1), the engine default** | +3.28 | +4.45 |
| Live-style count including routed wallets | +3.15 / +4.20 | |

  - **Default:** decoded buys only, k = 1.

## What is built (host, `/home/moiz/sniper`, uncommitted)
- **Engine flag `--final2-sock <path>`** (`src/bin/snipe_engine.rs`, struct `Final2`), with `--final2-timeout-ms` (default 5).
  - At the glued-bundle decision, the engine sends its RACE seen and RACE decide lines to the scorer over a Unix socket. It buys only on `pick=true`.
  - Non-blocking: the answer is read on the next loop pass, and the loop waits 100 µs while a question is open.
  - **Fails closed:** a timeout, a send error, or no scorer at startup means the engine refuses to start or doesn't buy.
  - Needs `--race-gate --race-glued`.
  - Also ported from the shadow engine: the exact create fields, glued-wallet tracking, and the extra decide-line fields the model needs.
- **Scorer serve mode:** `ops/shadow/scorer.py` with env `FINAL2_SOCK=<path>`.
  - It uses the same `feat()`, model, veto and guards as the shadow's live picks, so live picks are the shadow's picks.
  - It also tails the engine log to keep its history of all launches.
  - Decide lines with `pass=true` are held for the socket, which avoids a race between the socket and the log tail.
- **Binary:** `~/sniper-data/work/final2/snipe_engine_final2` (md5 588842f5…, includes --final2-sock and --hold-activity-k).
- **Scorer copy:** `~/sniper-data/work/final2/scorer.py`.
- **Flags:** `ops/final2/f2_flags.sh` (`--hold-ms 7700`; price guard `--slip-cap-bps 50 --fill-cap 1.005`; caps 15 buys / −0.3 SOL).
- **Tested on the host:**
  - It compiles.
  - The scorer socket answers recorded launches in **0.85 ms median (p90 0.96 ms)** with no errors.
  - Not tested end to end with live feeds: the host has no feeds, so that needs a server paper run.

## Wallet balances (read 10-23 ~09:45 PKT)
- **FRZ (DEV)** `FRZh63L6…`: **0.10 SOL**. Not enough.
- **PROD** `2g7rYv7y…`: **3.96 SOL**.

This strategy needs at least about **0.5 SOL per buy**: fixed costs (~0.006 SOL per buy) would eat ~6% of a 0.1 SOL trade. A 100–200-fill test with 2 positions in flight needs about **1.5–2 SOL**. So either top up FRZ (owner) or run the test on PROD (owner starts PROD runs).

## Prerequisites on the server *(OK)*
1. **Keep the collector running.** The scorer's history (creator wins, dump speed) comes from the collector's closed tx chunks. The current 24 h run (`run_20261022_1543`) ends at **10-23 20:43 PKT**.
2. **Run a scorer instance for the engine,** tailing the engine's log with `FINAL2_SOCK` set. Command in `f2_flags.sh`.
3. **Refresh the scorer's history seed right before the run.** The scorer starts from `shadow_seed.json` and then reads only ONE collector run (`CRUN`).
   - If the collection was restarted into a new run dir, the old seed misses every launch of the old run. That is creator / bundle-wallet / name history for up to a day, and the live picks would drift from the replayed ones.
   - Rebuild it (host): run the selection table chain on all runs (`ops/select/paper_cycle2.sh` steps a→c, f_dump, merge), then `ops/shadow/seed_history.py <table_all.jsonl.gz> <phaseB,phaseB_fwd,...> shadow_seed.json [dump raw]`.
   - Copy the new seed to the server, and start the scorer with `CRUN` = the running collection.

## How big the live test must be (MEASURED: bootstrap from the replay fills)
Each fill is a small loss most of the time, with a few big wins, the same profile the pros have. So a short test is close to a coin flip.

Chance the live total is above 0 after N fills (pros' later buys removed, slippage on, 8 s hold, 0.5 SOL). *Rows marked "both periods" pooled the contaminated R1 set: read the overnight rows.*

| Landing / costs | 15 fills | 50 | 100 | 200 |
|---|---|---|---|---|
| 75 ms, today's costs (2%, 0.005 per failed buy), both periods* | 52% | 62% | 68% | 75% |
| 75 ms, pro costs (0.6%, 0.003 per failed buy) | 62% | 77% | **87%** | **94%** |
| 45 ms, pro costs | 59% | 74% | 83% | 92% |
| 30 ms, pro costs | 65% | 82% | 91% | 98% |
| 75 ms, pro costs, overnight PKT only | 67% | 84% | **92%** | **98%** |

- **Cost matters as much as speed.** With pro-style costs even 75 ms is solid over 100–200 fills; with today's costs it isn't.
- **Pro-style costs come from the send design:** tips that revert when the buy fails, or Jito copies that are simply dropped, plus a small priority fee. That is a send-path change and needs the owner's OK.
- **Test sizing:** plan **100–200 fills**. That's about 10–20 h at 75 ms or 6–12 h at 45 ms, overnight PKT preferred, with a −1.5 to −2 SOL loss cap. A 15-fill test cannot confirm or reject the strategy.

## Sensitivity (MEASURED; pros' later buys removed + slippage, CW-style ~1.2% cost at 0.5 SOL). *The R1 column used the contaminated (partly in-sample) R1 picks; read the R2 column.*

| Change | 75 ms R1 daytime / R2 overnight | 45 ms R1 / R2 |
|---|---|---|
| base (1.5% fill penalty, sell at 8 s) | +0.43 / +2.38 | +0.44 / +3.44 |
| sell at 5 s / 10 s / 15 s | +0.74, +0.67, +0.27 / +1.78, +2.47, +2.25 | +1.33, +1.03, +0.40 / +1.29, +3.09, +1.87 |
| fill penalty 3% | −0.19 / +1.69 | −0.42 / +2.44 |
| fill penalty 4.5% | −0.80 / +1.00 | −1.28 / +1.43 |
| **Run 2's fee settings** (~3% + 0.011 per failed buy) | **−1.45 / +0.40** | **−1.46 / +1.43** |

- **Robust to sell timing** (5–15 s).
- **Sensitive to fill quality and above all to fees.** At Run 2's priority fee (0.011 SOL, paid by every failed guarded buy; about 60% of attempts fail at 75 ms) it does not work in daytime PKT.
- **Fees must come down:** a low priority fee, with tips that revert on failure.
- Run overnight PKT first.

## Steps
1. **Paper run on the server** *(OK)*: copy with `ops/final2/deploy_f2.sh` (copy only), then on the server `/root/sniper-f2/paper_f2.sh` (scorer + `--paper-trade`, no sends): `--paper-trade` plus the F2 flags, no sends. Check four things:
   - FINAL2 answer times (<2 ms);
   - picks match the shadow scorer's;
   - paper fills at our real landing;
   - no timeouts.
2. **Landing probe** *(OK, send path)*: durable-nonce fan-out, one signed copy per service, a small tip each, so only one lands. First, buy-shaped probes from FRZ that fail by design (priority fee only). Target ≤ 45 ms and ≤ 1% cost.
3. **FRZ live test** *(OK)*, with `ops/final2/live_f2.sh <tag>` on the server (detaches; stop with `kill -TERM <engine pid>`):
   - The script has no rule #2 filters. The priority fee is `CU_PRICE` (default 0.003 SOL; Run 2 used 0.011). `ACT="--hold-activity-k 1"` enables the A7 exit.
   - 0.5 SOL, 15 buys, −0.3 SOL max loss.
   - Run in PKT evening or night.
   - After the run, replay each live fill at its real landing and compare with the model (`ops/overnight/core/verify_live.py` style).
4. **Then PROD**, if live fills match the replay.

## Forward test (running, read-only)
- **Frozen rules:** `ops/overnight/dryrun/frozen_generic*.json`. Hashes 7b519784… (08:26 PKT), 300626a1… (08:33), 071c58da… (08:46).
- **Scoring:** every hour by `ops/overnight/dryrun/fwd_loop.sh` → `ops/overnight/dryrun/forward_generic.txt` and `fwd_loop.log`.
