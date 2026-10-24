# Dip-backrun: plan (2026-10-23 PKT). Analysis only; nothing is built in the engine or deployed.

> **CURRENT BEST (14:40 PKT, after the independent check `ops/overnight/verify_dip/VERIFY_DIRECT.md`). Read this first; the sections below are the history.**
> - **Version:** direct pump sells only (readable from shreds), ≥1 SOL, launch 1–120 s; frozen GBDT top 3–5% (`dip/frozen_dip2r_L35/L50.json`); buy 0.5 SOL with the **2% price guard (required)**; sell 2–4 slots after the buy (a tie); next dip on a launch allowed 5 slots later.
> - **Replay units** (block-position latency "L", the same units as HkQ7hMjy's median 39 ms), real follower limits, six-block CV, SOL per ~33.5 h, unguarded / guarded:
>   - "35 ms" +20.1 / +17.2 (6/6 blocks);
>   - "50 ms" +11.1 / +8.2 (6/6);
>   - "75 ms" +3.5 / +5.5 (5/6).
>   - The checker reproduced all of it exactly; seeds ±1; bootstrap 95% at "35 ms" +18…+25.
> - **REAL latency (our sell→buy time), two methods (14:38, section "REAL-latency estimate"):** a real 35 ms ≈ **8–12 SOL/day**, a real 50 ms ≈ 2–8.5, our ~75 ms ≈ 0–5. The spread is how the fast bots react to our buy, which only a live test can tell. Matching HkQ7hMjy's speed means about a real 30–35 ms.
> - **Size:** 1 SOL adds 25–50% in replay. The earlier check found it did not survive at real latency (base version), so stay at 0.5 until shadow data.
> - **Engine:** `ENGINE_V1.md`.
>   - Trigger from shreds: 3 pump sell layouts, which must also parse **v1 transactions** (8–12% of direct triggers), seller from the account position.
>   - History from an executed feed (Kaldera likely already includes it); ≤100 ms late is fine unguarded, but the guarded "75 ms" version loses ~1/3.
>   - Send like HkQ7hMjy: one landing service per leader client.
> - **Corrected by the check:**
>   - routed sells reach the pros ~2–5 ms later, not 8;
>   - census: buys were double-counted (23%) and unsold tokens valued at 0. Corrected, the ≥100-trip wallets make +190 SOL net in ~33 h, 79% positive; skill persists across runs. 0–10 ms is the best delay band, not the worst. Top: DYXDDrZC +18, haqqiUUX +17, HkQ7hMjy +16 net.
> - **False triggers:** 29% of direct sells fail on chain. A min-out check plus the guard makes them nearly free (~0.003 SOL/h); a seller-holdings check would cost ~20% of the profit, so it is not used.
> - **v1.5:** routed sells taken from the executed feed (~15 ms later), guarded, add ~25%.
> - **Rejected this afternoon:** long / TP / ride-with-pro exits; FLASHX8 triggers in v1; PumpSwap dip-backrun.

## Strategy
- **Trigger:** a sell of ≥1 SOL on a pump.fun launch aged 1–120 s (standard SOL curve, not mayhem, curve < 100 SOL vsol).
- **Selection:** score the sell with a frozen GBDT (35 features known at the sell); buy only in the top 5%.
- **Buy:** 0.5 SOL, as fast as possible after seeing the sell. Price guard: min tokens out set from the price right after the sell; the buy fails on chain if the price is >2% higher when we land.
- **Sell:** all of it 4 slots (~0.85 s) after our buy lands.
- **Learned from:** wallet HkQ7hMjy (+16 / +15 SOL in the two runs, 2,198 round trips). It does exactly this, at a median ~36 ms after the sell, with a 0.0003–0.001 SOL tip, ~0.00013 SOL priority, an exact CU limit (~71.6k), an on-chain guard program, and ~3 cheap failed attempts per filled buy.

## Evidence (replay; `ops/overnight/dip/`)
**Six time blocks** (each tested by a model trained on the other five): follower slippage imputed, our sell landing 75 ms into its slot, 0.5 SOL, 0.0008 SOL per tx.

| Our buy lands after the sell | Blocks positive | Total over ~31 h | Per day (approx.) |
|---|---|---|---|
| 20 ms | 6 / 6 | +28.2 | ~22 SOL |
| 35 ms | 6 / 6 | +18.1 | ~14 SOL |
| 50 ms (2% guard) | 6 / 6 | +9.9 | ~7.7 SOL |
| 75 ms (today, 2% guard) | 4 / 6 | +0.3 | ~0 |

- **Train on one run, test on the other** (8-slot exit) agrees.
- **Costs:** at 0.003 SOL per tx, 20–35 ms stays positive in every block; 50 ms is about break-even.
- **Forward test:** frozen FRZ-DIP4-L20 / L35 (10:52 PKT) and FRZ-DIP-L20 / L35 / L50 (10:34 / 10:47). Scored hourly on dips after the freeze: `ops/overnight/dip/fwd_dip.log`.

## What is still uncertain (be honest about these)
- **Speed.** Our snipe buys landed 73–75 ms after the create in Run 2 (5 routes in one transaction). Single-route buy-shaped probes on 10-21 (before Alpenglow) landed 17–34 ms. The strategy needs ≤35–50 ms. → measure first (step 1).
- **The timing proxy.** Arrival = position in block × 212 ms. Against the engine's real arrivals: corr 0.96, ~+7 ms. That is pessimistic for snipes but OPTIMISTIC for backruns: real competitors get counted as behind us (verify_dip). Use the corrected real-latency table below.
- **Imputed follower slippage** (from 711 decoded limits) roughly halves the no-slippage result. Real limits for these mid-life buyers are unknown.
- **Competition.** HkQ7hMjy and similar bots take the same dips; the replay includes their real trades, but not how they would react to us.

## Steps (each needs the owner's OK where marked)
1. **Speed probe** (owner OK, about 0.1–0.3 SOL on FRZ): `ops/run1/probe_buy.sh` with `PATHS=helius`, then `landx-fra3`, then `nozomi` (one route per probe), and once without PATHS (today's multi-route). Score with `ops/run1/probe_report.py`. Go/no-go: median create→seen ≤45 ms on the chosen single routes.
2. **Engine dip mode** (code on the host, default off; ~1 day):
   - per-launch state for launches aged ≤120 s: the curve, and trades with user, SOL and tokens, decoded from shreds; success simulated from each tx's own slippage limit;
   - the 35 features exactly as `ops/overnight/dip/dipbuy3.py` computes them, with a parity test against the Python on recorded data;
   - GBDT scoring from the frozen JSON (bins + trees);
   - the guarded buy through the single fastest route, then a timed sell 4 slots after landing;
   - zero-cost shadow mode first: log every decision with its timing, and compare with the replay.
3. **Shadow run on the server** (owner OK): decisions only, no sends; 2–4 h; check the trigger rate (~45–50 per hour), feature parity and decision latency.
4. **Small live test** (owner OK): 0.25–0.5 SOL per trade, hard caps (max buys, max loss), FRZ first.

## Note: the guard program
HkQ7hMjy's buys call program `L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95`. It is a shared conditional-execution program, not private. In 15 minutes of R2 data:
- 252 wallets sent 57,656 transactions through it;
- 98% failed cheaply (most abort before the pump instruction);
- the top two users sent 24.6k and 22.1k.

HkQ7hMjy uses it lightly (about 3 failed attempts per filled buy), so its edge is a fast reaction plus a guard. A plain min-tokens-out guard on our buy gives the same protection.

## Engine work, scoped (10-23 11:15 PKT; not started)
- **Existing pieces in `src/snipe.rs`:**
  - `bundle_legs` / `simulate_legs` decode top-level pump buys (exact-in and cap kinds) and simulate them on the curve, including slippage-limit failure;
  - `mint_touch` flags sells, but does not size them;
  - per-mint curve state exists only for the short race window.
- **Needed for a dip shadow mode** (decisions logged, no sends), roughly 400–600 lines of Rust:
  1. decode sell size (token amount at ix data offset 8, min SOL out at 16) and price it on the tracked curve (SOL out);
  2. keep per-mint curve state plus a compact trade list for launches aged ≤120 s;
  3. the 35 features exactly as `ops/overnight/dip/dipbuy3.py` computes them (parity test on recorded data);
  4. GBDT scoring from `frozen_dip4_L*.json` (bin edges + trees, depth 3, ~400 trees: microseconds);
  5. log line per decision: mint, sell sig, score, pass/fail, features, our decision time.
- **The live path** (owner OK only): a guarded buy (min tokens out from the post-sell price, 2%) via the single fastest route, then a timed sell 4 slots after landing.

## Who pays us (10-23 11:10 PKT; important for the owner's rule)
Removing the later buys of the 541 consistently profitable bots (census) turns the dip result from +18.1 to −14.1 SOL (35 ms). Removing the 9 pros, the 321 snipers, or 541 random active wallets barely changes it (+18.1 / +17.9 / +11.4). FINAL-2 behaves the same way.
- The profit comes from being just ahead of that bot group, which then buys after us.
- It does not come from ordinary traders or from the case-study pros.
- The owner decides whether this fits "become them, don't beat them".

## Fewer, bigger option (11:25 PKT)
Top 2% of dips at 1 SOL, 4-slot exit, six-block CV: all 6 blocks positive.

| Our buy lands | Total over ~31 h | Trades per hour | Per 1-SOL trade |
|---|---|---|---|
| 35 ms | +16.1 | ~19 | +0.018 to +0.043 |
| 20 ms | +26.4 | | |

Top 1% at 1 SOL: +10.3 at 35 ms, ~10 trades per hour.

## Risk checks (11:30 PKT)
- **The cohort's own slippage limits** (163 decoded) look like everyone else's (median 43%, about 9% at ≤2.5%), so the pooled slippage imputation is representative.
- **HkQ7hMjy alone** carries only ~1.3 SOL of the 35 ms result (+18.07 → +16.78 without its later buys). The dependence is spread across the cohort.
- **Cohort reaction after a big sell** (proxy): p10 29 ms, p25 57 ms, median 166 ms. At 35 ms we are ahead of ~85% of their dip buys; at 75 ms, of ~68%, but behind the fastest ones.

## Engine progress and a live-data caveat (11:35 PKT)
- **Done (host, uncommitted, not wired, not deployed):** `src/dip.rs`, the frozen GBDT scoring plus the 35 features, ported from the Python.
  - `cargo test --release --lib dip` passes on 218 exported events: 0 feature mismatches, 0 score mismatches (worst diff 9e-16).
  - Data: `testdata/dip_parity.json`, `testdata/frozen_dip4_L35.json`.
- **Hook for a shadow mode:** `RaceWatch::observe(&a.tx)` in `src/bin/snipe_engine.rs` gets every feed tx; a `DipWatch` would sit beside it.
- **Caveat: shreds give transactions, not execution results.**
  - Direct pump buys and sells can be sized and simulated from the instruction data (`snipe::bundle_legs` / `simulate_legs`, plus sell sizing).
  - Router-CPI trades (Axiom / Photon / GMGN, etc.) cannot. The replay's features include them.
  - Plan: keep each launch's trade history from a feed WITH execution results (the engine supports a `yellowstone-tx` feed; slower, but history only needs to be ~50 ms fresh), and take only the trigger (a direct ≥1 SOL sell) from shreds for speed.
  - The shadow run must measure how far live features drift from the replay's.
- ~~Size of the router gap: ~11% routed~~ **WRONG, corrected 13:00 PKT:** 76% of trades have no top-level pump instruction (the ixn names include inner instructions). But the model's picks are mostly direct sells; see "Which triggers a fast engine can see" below.
- **Feed detail** (`src/feeds/mod.rs`): `Arrival` carries the tx, slot, timing and `executed` (success, for executed feeds such as yellowstone-tx); no logs or inner instructions. For router trades:
  - **(a)** extend the gRPC decoder to keep the meta (TradeEvents from logs); or
  - **(b)** subscribe the bonding-curve accounts on the existing state stream. That gives the exact curve state (vsol / vtok), so price features don't drift; per-user history would still miss the router trades (76% of all trades).

## Capacity: spacing between trades on the same launch (11:40 PKT)
- **Base:** one trade per launch per 20 slots → +18.1 SOL / ~31 h at 35 ms.
- **Every 5 slots** (we are flat again after a 4-slot hold): 42.6k events; top 5% → **+33.2 SOL / ~32 h**, all 6 blocks positive (+4.8 to +6.9 each), ~70 trades per hour, +0.0125 to +0.020 per trade.
- **Caveat:** each trade is replayed on the real history, so our own previous sell's price impact on the same launch is not modelled. Treat this as an upside case.


## Independent check (11:50 PKT): `ops/overnight/verify_dip/VERIFY_DIP.md`
- **Reproduced exactly** from the raw chunks with an independent decoder: all 29,810 events, all block totals, five hand-checked trades.
- **No look-ahead that matters.** The `snp_seller` labels see the whole period; dropping the feature costs −1.15.
- **Bugs fixed in `dipbuy4.py`:** the exit clock now starts at our own landing slot; the mayhem filter now uses `InitializeMayhemState`.
- **Corrected to real latency** (0.5 SOL, 28.6 h of data):

| Real latency | 0.0008 SOL/tx | 0.002 SOL/tx | 0.003 SOL/tx |
|---|---|---|---|
| 20 ms | +14.6 … +18.0 | +11.0 … +14.4 | +8.1 … +11.5 |
| 35 ms | +9.6 … +11.3 | +6.1 … +7.7 | +3.2 … +4.8 |
| 50 ms | +1.9 … +2.5 | −1.9 … −1.3 | −5.0 … −4.4 |
| 75 ms | −6.8 … −6.2 | −10.2 … −9.6 | −13.1 … −12.5 |

- **Real 35 ms:**
  - walk-forward (training only on earlier blocks): +5.0 … +6.3;
  - bootstrap 95% range: +6.1 … +15.0;
  - without the best 10 launches: +6.3 … +7.9.
- **Size:** 0.5 SOL is the right size; 1 SOL does not add.
- **Speed:** every 10 ms costs ~5 SOL per ~28 h.
- **Competition:** HkQ7hMjy made +28.0 SOL over the two runs (1,705 round trips, +0.016 each, median 39 ms after the sell). About 70 wallets backrun dips within 150 ms. HkQ7hMjy refuses buys more than 2% above the dip.
- **Rejected placement (11:55 PKT):** buying first in the next slot (top-of-block, as ARu4n5mF does) instead of in the same slot. Six-block CV: −8.5 (4-slot exit), −12.3 (8-slot). The edge needs same-slot speed.

## Real follower limits (12:05 PKT)
- **Decoded:** 13,294 of 13,347 buys that followed the model-selected dips (`core/slip_fetch.py`, read-only RPC; appended to `slip_args.jsonl`).
  - Their slack: p10 2.0%, p25 6.7%, median 36%.
  - 13% at ≤2.5% and 22% at ≤5% (a bit tighter than the early-sniper list).
- **Six-block CV with real limits** (imputed where missing), the exit-clock fix and the mayhem fix, replay units: 20 ms +24.6 (6/6); 35 ms +13.0 (6/6); 50 ms +4.4 (5/6).
- **Replay units run ~7 ms optimistic.** At a real 35 ms this is ≈ +9 SOL per ~29 h, matching the independent check (+9.6 … +11.3).
- **Expectation:** ≈ 7–8 SOL/day at a real 35 ms; ~0–2 at a real 50 ms.

## Engine design decision (12:10 PKT)
- **Decoding everyone's trades from shreds is error-prone.** pump.fun runs several instruction versions with different account layouts (buy, buy_exact_sol_in, buy_exact_quote_in v2/v3, sell, sell_v3, sell_exact_tokens_in_v3); `src/snipe_build.rs` itself marks one sell layout "UNCONFIRMED".
- **Better: history from an executed feed with logs,** like the collector (`/root/sniper-collect` already decodes exact TradeEvents: user, SOL, tokens, reserves). Features then match the replay exactly (the replay was built from the same events).
- **Shreds only for the trigger:** a direct ≥1 SOL sell, sized from its `amount` argument on the latest executed curve state.
- **Before building:** measure the executed feed's delay against shreds; the trigger has a ~35 ms end-to-end budget.
- **Refinement: the sell's position in its slot** (12:15 PKT; real limits, six-block CV, top 5%):
  - at 35 ms, sells in the first quarter of a slot make +0.013 per trade (+6.2 of +13.0); later quarters about +0.007;
  - at 75 ms, the first quarter is about 0 and the rest negative.
  - Prefer early-slot sells when fast; it does not rescue 75 ms.
- **Deployer's cohort history** (12:25 PKT): how many R1-cohort bots bought this deployer's earlier launches in their first 10 s.
  - Strong on all launches: ≥10 bots → 4-slot mean −0.005 to −0.007 vs −0.028 for none.
  - Adds almost nothing to a snipe selection model on R2 (top 5%: +0.25 → +0.31; AUC +0.03). Not adopted.
- **Shorter holds** (12:10 PKT; real follower limits, six-block CV, replay units):

| Hold | 35 ms | 50 ms | 50 ms + 2% guard |
|---|---|---|---|
| 2 slots | +16.9 | +7.2 | +9.3 |
| 3 slots | +16.2 | +7.5 | +8.2 |
| 4 slots | +14.5 | +4.8 | +6.8 |

  - Selection bias: the exit was picked among four, but "shorter is better" holds at every latency.
  - Frozen FRZ-DIP2-L35 / L50 (12:09 PKT); forward test via `fwd_dip_loop5.sh`.
- **Daily retrain** (12:20 PKT): `ops/overnight/dip/dip_retrain.sh` rebuilds the events from the latest data, runs the six-block CV, and re-freezes the DIP2 / DIP4 models (old ones kept with a date suffix). It takes about 15 min; then restart the forward loop.
- **Executed-feed delay** (12:25 PKT): not measured in our feed notes (`ops/gap/NOTES.md`). The only number is a dropped provider (Haan) at ~+8 ms behind Kaldera shreds, kind not recorded. The config marks `yellowstone-tx` as "executed, so later by design".
  - At ~+8 ms, history from the executed feed is fine.
  - The trigger should still come from shreds (each 10 ms costs ~5 SOL per ~28 h).
  - Measure it first with the feed-race harness (zero cost).
- **Executed-feed history is cheap to add** (12:25 PKT): `src/feeds/grpc.rs` already decodes the full `TransactionStatusMeta` (prost `PbMeta`, `log_messages` = tag 6) for the exec.jsonl recorder.
  - Decode the pump TradeEvents from those logs ("Program data: <base64>", the same events the collector stores).
  - Attach them to `Item::Tx` / `Arrival`. Roughly 50–100 lines.
  - Then the dip watcher's history matches the replay's TradeEvents exactly, with no instruction-variant decoding.
- **Risk** (12:35 PKT; six-block CV, real limits, 2-slot exit, 2% guard, 0.5 SOL):
  - "35 ms": 1,410 trades / 32 h, +16.8, max drawdown 0.51 SOL, 97% of hours positive, worst hour −0.05, worst trade −0.30;
  - "50 ms": +9.3, max drawdown 0.34, 88% of hours positive.
  - Capital ~1–2 SOL.
- **Best version so far** (12:40 PKT; NOT independently checked): spacing 5 slots (DIP_BUSY=5), 2-slot exit, real follower limits, six-block CV.
  - "35 ms": +30.6 SOL / ~33 h, all 6 blocks positive (+3.6 to +6.3).
  - "50 ms": +16.9, 6/6 positive (+1.8 to +4.1); with the 2% guard +27.7 / +16.2.
  - Scaled like the verifier's base correction: ≈ 12–15 SOL/day at a real 35 ms.
  - Forward test: `fwd_dip_loop6.sh` (adds DIP2 spacing 5).

## Afternoon (owner: "continue grinding")
- **75 ms (≈ our current speed)** (12:50 PKT): spacing 5, 2-slot exit, real follower limits, **2% guard**: +7.3 SOL / ~33 h (replay units), **all 6 blocks positive**; unguarded +1.4. At "100 ms" with the guard: +0.8 (4/6 blocks).
  - Our real 75 ms ≈ replay "82 ms", so expect a thin +3 … +5 per ~33 h before the verifier-style corrections.
  - First configuration positive at roughly today's speed.
- **Rejected:** cohort-follow (buy right after an R1-cohort wallet's buy; R2-only 4-block CV): −4 … −9 at 35–75 ms, every exit.
- **75 ms guard sweep** (2-slot exit): guard 1.0 +5.9, 1.01 +6.3, **1.02 +7.3**, 1.03 +6.8. With the 4-slot exit, 1.02 gives +4.1. A guard-aware label (fill & profit) is worse: −5.5, because it selects quiet tokens.
- **Guarded "spray" (rejected on cost)** (12:50 PKT): keep conditional buys (min-tokens-out at a −d% price) streaming on chosen tokens, so one fills right at a dump.
  - **Upper bound** (entry 0 ms, selection from PRE-dump features only, dumps ≥8%): top 20% +64 SOL / ~33 h, 6/6 blocks.
  - **Costs:** streaming 10–50 tx/s per armed token on ~5–10 tokens costs ~2–9 SOL/h even at the 0.000005 SOL base fee, about the whole expected profit (~2 SOL/h). Slower streaming puts our fill back near ~50 ms.
  - **Competition:** 252 wallets already stream conditional txs through the shared guard program.
  - **What survives:** pre-dump features predict well, so the decision at the dump can be a precomputed threshold check (µs).
- **Most robust at today's speed** (12:56 PKT): the full model restricted to dumps ≥10%, guard 1.02, 2-slot exit, spacing 5.
  - "75 ms": top 20% +8.3 (6/6), top 10% +7.2 (6/6).
  - "100 ms": top 10% +4.6 (6/6), top 5% +3.3 (6/6).

## KEY engine finding (13:00 PKT): most trades are not decodable from shreds
- **Measured:** fetched real successful pump trades (read-only RPC; `ops/overnight/dipshadow/`). On 1,500 random successful pump trades (read-only RPC, 64 time buckets), **76% have NO top-level pump.fun instruction** (first sample of 162: 72%). They go through routers or bots' own programs (CPI): Axiom / Photon / GMGN, the shared guard program L2TExMFK, sniper programs.
- **Why it matters:** shreds carry only the outer instructions. A shred-only dip engine would miss most of the trade history and many of the big-sell triggers. (My earlier "~11% routed" was wrong; the instruction-name list includes inner instructions.)
- **Requirement:** the dip engine must read an EXECUTED transaction feed WITH logs (TradeEvents: user, SOL, tokens, reserves), as the collector does. Our `src/feeds/grpc.rs` already parses the meta (log_messages) for its recorder; Arrival would need to carry the decoded TradeEvents.
- **Consequence:** the trigger arrives on the executed feed, later than shreds by an unmeasured delay. Prefer the deep-dump version (positive at "100 ms" in replay) and measure the executed-feed delay first (zero cost, feed-race harness).
- **Top-level variants seen** (for the ~28% that are direct; account positions verified against the TradeEvent user and mint):
  - `33e685a4…` sell (v1): mint 2, user 6, a8 = tokens, a16 = min SOL;
  - `1c92de77…` sell_v3: mint 1, user 8;
  - `e1f7501e…` buy_exact_quote_in_v3: mint 1, user 8, a8 = SOL in;
  - `38fc7408…` buy_exact_sol_in: mint 2, user 6;
  - `66063d12…` buy: mint 2, user 6, a8 = tokens, a16 = max SOL;
  - `07051dc4…` buy_v3: mint 1, user 8;
  - `c2ab1c46…` / `b817ee61…`: 27-account buy variants, user 13;
  - `5df6823c…`: 26-account sell variant, mint 1, user 13, a8 = tokens;
  - `d6904cec…` create_v2.

## Which triggers a fast engine can see (13:10 PKT; `ops/overnight/dipshadow/trig_*.py`, read-only RPC truth for 7,719 trigger txs)
- **The model's picks are mostly DIRECT sells** (top-level pump sell = readable from shreds), and those carry most of the profit. Out-of-fold top 5%, spacing 5, 2-slot exit:

| Entry | Picks that are direct | P&L on direct picks | P&L on routed picks | Direct share of P&L |
|---|---|---|---|---|
| "35 ms" | 57% (1,226 / 2,159) | +22.5 (guard +19.1) | +8.0 (guard +8.6) | 74% |
| "50 ms" | 58% | +13.9 (guard +11.0) | +3.0 (guard +5.2) | 82% |
| "75 ms" | 64% | +4.4 (guard **+6.3**) | −3.0 (guard +1.1) | 86% (guarded) |
| "100 ms" | 71% | −2.3 (guard +0.7) | −4.8 (guard +0.1) | — |

- Base rate: 41% of ALL dip triggers are direct (44,535 triggers; labelled from the collector's `progs` with a rule that matches the RPC truth 99.8%).
- **Pros see routed sells later:** first same-slot buy after a direct trigger, median 33 ms (p10 0.7) vs 40 ms after a routed one (p10 6.3). HkQ7hMjy: **36.6 ms after direct vs 44.2 ms after routed** (n 58 / 80), so about +8 ms for routed sells, even for the best dip bot.
- **Routers** carrying the routed triggers: `FLASHX8D…` (2,851 triggers, 1,058 sellers) dominates; then `J7pourVw…`, `4DvQwk6W…`, `term9YPb…`, `AKbotMAG…` (AKbot), `GMgnVFR8…` (GMGN; its data is pump's own sell layout). Several (`4DvQwk6W`, `FGtidgev`, `6HSS4x6U`, `DXDpquPw`, `FCdY3UTq`) encode "sell N% of balance" (`0x64` = 100%) and could be sized from our own history of the seller's balance.
- **Design consequence:** trigger = direct pump sells from shreds (three variants: `33e685a4` sell, `1c92de77` sell_v3, `5df6823c` 26-account sell); history = executed feed. Routed triggers are optional (a later, slower path).
- Direct-only CV (model acting only on direct triggers; or trained only on them): running, `dip/cv_direct_*.txt`.

## How the dip backrunners send (13:12 PKT; `dipshadow/backrun_paths.py`, collector tip accounts → `tipmap.json`, no RPC)
- **HkQ7hMjy** (1,415 same-slot backrun buys within 150 ms): calls pump.fun **directly** (100%; no own program), **Nozomi 58%** / no tip 19% / Helius 8% / soyas 5%, **median tip 0.001 SOL**, median priority fee 0.00013 SOL, lands a **median 39 ms** after the sell. This is the template: a plain direct pump buy, one landing service, ~0.0011 SOL per tx.
- **The fastest backrunners (median 3–20 ms)** use their own programs (0% direct), mostly no tip and ~0.00001 SOL fees: these txs were already queued before the dump (conditional "spray" style), not reactions. We rejected spraying on cost.
- All 35,472 same-slot backrun buys within 150 ms: 59% direct pump calls, 55% tip (median 0.001), median priority fee 0.0001; services: no tip 45%, Helius 19%, Astralane 11%, Nozomi 6%, Jito 3%.
- **Cost note:** HkQ7hMjy's ~0.0011 SOL per tx is above the replay's 0.0008. The verifier's table: 35 ms at 0.002/tx still gives +6.1 … +7.7 per 28.6 h (base version).

## Direct-only strategy (13:13 PKT; six-block CV, top 5%, 2-slot exit, spacing 5, real follower limits; `dip/cv_direct_*.txt`)
Labels: `dipshadow/direct_flags_prelim.json` (99.8% vs RPC truth). Totals per ~33 h, replay units, unguarded / 2% guard:

| Variant | "35 ms" | "50 ms" | "75 ms" | "100 ms" |
|---|---|---|---|---|
| All triggers (needs routed sells too) | +30.6 / +27.7 | +16.9 / +16.2 | +1.4 / **+7.3** | −7.1 / +0.8 |
| **Direct only**, same model and threshold | **+22.5** / +19.1 | **+13.9** / +11.0 | +4.4 / +6.3 | −2.3 / +0.7 |
| Direct only, top 5% of direct sells | +18.2 / +15.0 | +11.9 / +9.2 | **+4.8 (6/6 blocks)** / +5.2 | +1.2 / +1.9 |
| Model trained on direct sells only | +19.6 / +16.6 | +13.2 / +10.6 | +5.8 / +5.1 | +0.7 / +1.9 |

- A direct-only engine keeps ~74% of the profit at "35 ms" and more than all-triggers at "75–100 ms" unguarded (routed picks lose there).
- Routed sells would reach us ~8+ ms later anyway (executed feed), where their share shrinks further.
- **Decision for the engine:** v1 = direct sells from shreds only (3 variants), history from the executed feed; routed triggers = optional v2.

## How HkQ7hMjy routes per leader client (13:13 PKT; `dipshadow/leaders_book.json` from getLeaderSchedule + getClusterNodes, read-only)
| Leader client (slot share) | HkQ7hMjy's choice (median delay after the sell) |
|---|---|
| BAM (38%) | Nozomi 73% (41 ms), no tip 12% (43), Helius 5% (39) |
| Harmonic (30%) | Nozomi 84% (37 ms) |
| Jito-Solana (23%) | no tip 30% (44), **Helius 24% (29 ms)**, Nozomi 19% (44), soyas 12% (34) |
| Firedancer (7%) | no tip 67% (43), Nozomi 27% (35) |
| Agave (1%) | stellium 89% (46) |

- Compare our proposed `ROUTES` (`ops/final2/SEND_DESIGN.md`): bam=helius; harmonic=nozomi ✓; jito=helius ✓; fd=astralane; agave=helius. HkQ7hMjy's evidence suggests **bam=nozomi** and **fd=nozomi** (or plain priority fee). The speed probe should include Nozomi on BAM and Firedancer leaders.
- Other backrunners (different bots, so confounded): on Harmonic, speedlanding 40 ms vs Nozomi 44 vs Helius/Astralane 49; on Jito-client, soyas 29, flashblock 33, Helius 46.

## Engine v1 trigger decoder, validated (13:20 PKT; `dipshadow/trig_decode.py`, 800 real direct-trigger txs vs their own TradeEvents)
| Discriminator (data 24 bytes) | Accounts | Mint at | Seller at | u64 @8 = tokens sold | u64 @16 = min SOL out |
|---|---|---|---|---|---|
| `33e685a4017f83ad` sell | 16 | 2 | 6 | 93% exact (the rest: multi-sell txs) | ≤ SOL out 100% |
| `1c92de7726c469d5` sell_v3 | 17 | 1 | 8 | 100% | 100% |
| `5df6823ce7e940b2` sell (26–27 accounts) | 26/27 | 1 | 13 | 100% | 100% |

- Signer = seller in 94–97%.
- **Multi-sell txs:** 60 of 414 classic-sell triggers carry several sell instructions (several wallets dumping in one tx). Sum all direct sells on the mint in the tx to price the dump.
- SOL out = constant-product on the latest known curve state (executed feed), minus pump fees. A 20 ms history lag costs nothing in the six-block CV (below); 50/100 ms pending.

## Census of ALL dip backrunners (13:22 PKT; `dipshadow/dip_census.py` → `dip_census.json`; real round trips, fees approximated ±1.25%, tx costs NOT included)
- Every same-slot buy within 150 ms after a dip trigger (44.8k triggers, ~33 h), then that wallet's own sells of those tokens: **42,370 round trips by 5,154 wallets: +21.4 SOL gross (+0.10%), ≈ −63 after ~0.002 SOL/trip tx costs.**
- **It is a skill game:** wallets with ≥100 trips: 67 wallets, **+292.6 SOL, 79% positive**. Wallets with 1–10 trips: 4,791, −315 SOL (34% positive).
- **By delay after the sell:** 0–10 ms −98.8 (pre-queued); **10–25 +43.2, 25–40 +49.3, 40–60 +47.8** (+1.2…+1.5% of SOL in); 60–100 −10.2; 100–150 −10.0.
- **By hold:** 0–3 slots +51.8 (+3.2%); 3–6 +41.8; 6–15 +54.9; 15–40 +13.4; **40–100 +74.5 (+1.8%)**; 100–300 +3.8; 300+ −218.6 (bag holders).
- **Top wallets** (P&L / trips / median delay / median hold): DYXDDrZC +36.1 / 1,137 / 43 ms / 55 slots (0.85 SOL); HkQ7hMjy +23.0 / 1,771 / 39 / 10; haqqiUUX +22.9 / 2,030 / 45 / 20; sssssDdM +22.4 / 419 / 53 / 38; ETwEAQPL +17.2 / 353 / 49 / 36; 5mWe9kLZ +16.4 / 531 / 43 / 140; ssssswdk +15.4 / 1,500 / 57 / 26.
  - Several pros are profitable even at 60–150 ms delays with longer holds (haqqiUUX +12.5 there, sssssDdM +14.0, DYXDDrZC +10.2): selection and exits matter, not only speed.
  - Long-hold P&L is skewed (DYXDDrZC's top 10 trades = +15.3 of +36; ETwEAQPL's top 10 > its total).
- Next: test longer holds (20–100 slots) and take-profit exits with our model at "75 ms".

## The top dip wallets, closer (13:26 PKT; `census/wallet_exit*.py`, `dipshadow/dip_census.json`)
- **DYXDDrZC** (top by P&L): direct pump buys; Astralane 42% / speedlanding 31% / no tip 11%; tip ~0.0011, priority ~0.00018 SOL.
  - Holds a median 74 slots (p25 33, p75 152). Sell/buy median 1.005, mean 1.047: a few big pumps carry it.
  - No simple exit trigger: it reacts to ~3% of other wallets' sells at every size and drawdown.
- **On OUR model's "75 ms" picks:** DYXDDrZC made +9.0 on 202 of them (+0.045 per trade, vs +0.019 on its other dips); HkQ7hMjy +1.2 on 211 (it does better on our "35 ms" picks: +5.8 on 267).
- **Competition:** 78% of all dips have no profitable pro (53 wallets with ≥100 trips) backrunning within 150 ms, but **55% of our "75 ms" picks have at least one** (11% have 4+). The model picks what the pros like.
- **Fixed long holds with our picks lose:** a 10-slot exit gives "50 ms" −1.6 (guard +1.0), "75 ms" −14.3 (guard −6.3). So the pros' long-hold profits need their own exit timing or selection, not just a longer timer.
- **History lag (six-block CV, direct-only, top 5%):** 0 ms: "35" +21.6, "50" +12.6, "75" +4.9 / guard +6.5; **50 ms lag: +22.1, +12.5, +3.6 / guard +4.9.** A history feed up to ~50 ms late is fine.

## Independent check of the spacing-5 version: partial (13:28 PKT; the checker stopped before writing its report; outputs in `ops/overnight/verify_dip/out/b5_*`)
- **Reproduced exactly:** spacing 5 "35 ms" +30.56, "50 ms" +16.90; 3-slot-exit variant +16.85 / +7.24. Applying our own trades in sequence (our earlier sells move the curve) does not hurt: "50 ms" +17.35.
- **Coverage gap:** only ~35% of the buys after the NEW picks had a decoded real slippage limit; the rest were imputed. Where both exist, real limits drop more buyers (570 vs 381 at "35 ms"), so imputed is optimistic. On fully covered picks: real +10.47 vs imputed +12.34 (−15%).
- **Measured backrunner tolerance** (the checker's model of how far backrunners accept a worse price): "50 ms" +16.9 → **+12.9**; 3-slot "35 ms" +16.9 → +14.7.
- **Not done:** the real-latency correction. Use the earlier rule: replay "L" ≈ real L − 7 ms.
- **Fix running:** decoding real limits for every buy within 6 slots after each current pick (`dip/follower_sigs2.py` → `core/slip_fetch.py`, read-only RPC). Then rebuild and re-run the CV.

## History-lag tolerance, full table (13:29 PKT; `dip/dipbuy5.py` DIP_HLAG; direct-only, six-block CV, top 5%, 2-slot exit; unguarded / 2% guard)
| History late by | "35 ms" | "50 ms" | "75 ms" |
|---|---|---|---|
| 0 ms | +21.6 / +18.2 | +12.6 / +10.3 | +4.9 / +6.5 |
| 20 ms | +22.9 / +19.0 | +12.2 / +9.7 | +4.2 / +5.6 |
| 50 ms | +22.1 / +17.5 | +12.5 / +9.6 | +3.6 / +4.9 |
| 100 ms | +21.8 / +16.4 | +13.0 / +9.0 | +3.5 / +4.1 |
| 400 ms | +20.7 / +15.3 | +13.6 / +8.7 | +2.9 / +3.0 |
| 1 s | +18.1 / +8.9 | +9.5 / +3.9 | +0.3 / −1.3 |

- The model's picks barely change. The guard weakens a little, because its reference price comes from the stale curve.
- So the history feed can be up to ~100 ms behind, and even ~400 ms (about one slot) keeps the unguarded edge at "35–50 ms"; 1 s is too late (the guarded version collapses). This test hides every trade in the lag window; live, direct trades seen in shreds would fill part of it.

## Exits tested against the 2-slot exit (13:30 PKT; six-block CV, all triggers, top 5%, spacing 5; `dip/cv_tp.txt`, `cv_long.txt`, `cv_fol.txt`)
| Exit | "35 ms" | "50 ms" | "75 ms" (unguarded / guard) |
|---|---|---|---|
| **2 slots (current)** | **+31.0** | **+17.3** | +1.7 / **+7.7** |
| 4 slots | +29.7 | +13.7 | +1.0 / +5.8 |
| 8 slots | +20.1 | +7.4 | −7.5 / −1.4 |
| 10 / 20 / 40 / 80 slots | — | −1.6 / −8.5 / −18.6 / −55.8 | −14.3 / −17.7 / −25.4 / −49.0 |
| take profit +2% (else 2 slots) | +30.7 | +17.0 | +1.7 / +7.1 |
| take profit +3% (else 2 slots) | +31.3 | +15.8 | +0.5 / +6.6 |
| take profit +5% (else 20 slots) | — | −10.9 | −28.8 / −16.8 |
| hold until a profitable pro in the same dip sells (53 pros, chosen in-sample) | — | +2.5 / +7.2 | −8.9 / +4.8 |

- **Rejected:** long holds, take-profit, and ride-with-the-pro. The pros' long holds (DYXDDrZC ~15 s) don't carry over to our picks and speed. Keep the 2-slot exit.

## Direct-only by hour of day (13:37 PKT; out-of-fold picks, "50 ms", unguarded)
- **Positive in 21 of 22 PKT hours** (no data for 18–19 h). Best 21 h +1.83, 05 h +1.57, 06 h +1.31, 09 h +1.22; the only negative hour is 02 h (−0.10).
- **Forward (13:35 PKT, imputed slippage):** DIP4 spacing-5 model (frozen 10:52, 2.5 h after): "35 ms" +1.31 (125 trades), guarded "75 ms" +0.89. DIP2 (frozen 12:09, 1.2 h): "35 ms" +0.32, guarded +0.46.

## Direct vs routed, FORWARD (13:42 PKT; `dip/dipfwd_direct.py` → `fwd_dip_direct.log`, re-run every ~45 min by `fwd_dip_direct_loop.sh`)
- Frozen DIP2 L35 model, dips after its 12:09 freeze (1.2 h, 877 dips, 43 picks):
  - **direct picks n 15: "35 ms" −0.03 (guard +0.04)**;
  - routed picks n 28: +0.29 (guard +0.37).
- Only 35% of these picks are direct (CV: 57%). Too small to conclude, but it is the first out-of-time look, and it does not support direct-only yet. Keep watching before building.
- **Per-block check (13:42 PKT; out-of-fold picks):** direct picks beat routed picks in **every time block at every speed (18 of 18)**, and direct P&L is positive in all 18. In the latest block (10-23 06:02–12:42): "35 ms" direct +3.73 (n 191) vs routed +2.55 (n 142). The 1.2 h forward window (15 direct picks) is most likely noise; the hourly loop keeps scoring it.


## Real follower limits, full coverage (13:45 PKT; `dip/follower_sigs2.py` → `core/slip_fetch.py`, ~18,700 more limits decoded 13:30–13:40; `dip/cv_real2.txt`)
| Six-block CV, top 5%, 2-slot exit (unguarded / guard) | "35 ms" | "50 ms" | "75 ms" |
|---|---|---|---|
| All triggers, before (partial real limits) | +29.6 / +27.0 | +15.6 / +15.5 | +1.5 / +7.5 |
| All triggers, real limits | +26.4 / +24.4 | +13.3 / +13.2 | −0.2 / +6.3 |
| Direct only, before | +21.6 / +18.2 | +12.6 / +10.3 | +4.9 / +6.5 |
| **Direct only, real limits** | **+20.1 / +17.2** (6/6) | **+11.1 / +8.2** (6/6) | **+3.5 / +5.5** (5/6) |

- The real limits cut 7–15% at "35–50 ms" against the earlier partly real numbers, as the checker predicted.
- **Same data, estimated (imputed) limits only** (`dip/cv_imp2.txt`): all triggers +36.0 / +17.0 / +2.6; direct-only +25.4 / +13.4 / +5.8.
  - So estimated limits overstate the direct-only P&L by 17–21% at "35–50 ms" (40% at "75 ms" unguarded). Always use decoded limits for new pick sets.
- The OOF picks are in `dip/sel_oof_real2_*.jsonl`.

## Executed feed: probably already paid for (13:47 PKT)
- Constant-K's **Kaldera** (our deshred feed today) is a full Yellowstone gRPC service with account / transaction / slot / block streams, per the vendor page https://www.constant-k.com/yellowstone-grpc/ (not checked by us).
- So the dip engine's history feed is likely a `yellowstone-tx` subscription (pump program, processed) on the same endpoint and token, with no new provider.
- To do (owner's OK, server, zero cost): confirm the plan includes transaction streams, then run `ops/gap/feed_race.sh` with a `yellowstone-tx` block on that endpoint to measure its delay against deshred.

## How many dips to take (13:55 PKT; direct-only, real limits, six-block CV; `dip/cv_q_real2.txt`; unguarded / guard)
| Pick share | "35 ms" | "50 ms" | "75 ms" |
|---|---|---|---|
| top 3% | +17.6 / +14.7 | **+11.5** / +8.7 | **+5.1** / +5.6 |
| top 5% | +20.1 / +17.2 | +11.1 / +8.2 | +3.5 / +5.5 |
| top 7.5% | +22.2 / +18.5 | +11.1 / +8.4 | +2.4 / +5.6 |
| top 10% | +22.5 / +19.4 | +7.7 / +6.1 | +1.1 / +4.4 |

- Real limits were decoded for the top-5% picks' followers, so the 7.5% / 10% rows lean on estimated limits and are optimistic.
- At realistic speed ("50 ms"), 3–7.5% are equal. **Top 3% is the most robust at "75 ms".** No gain from taking more.

## Size 1 SOL instead of 0.5 (14:00 PKT; direct-only, real limits where decoded, six-block CV; `dip/cv_b1_real2.txt`; unguarded / guard)
| Size, pick share | "35 ms" | "50 ms" | "75 ms" |
|---|---|---|---|
| 0.5 SOL, top 5% | +20.1 / +17.2 | +11.1 / +8.2 | +3.5 / +5.5 |
| 1 SOL, top 2% | +19.8 / +16.5 | +12.3 / +9.3 | **+6.2 / +7.0** |
| **1 SOL, top 5%** | **+29.6 / +25.6** | **+13.9 / +11.0** | +2.8 / **+7.3** |

- Doubling the size adds 25–50%, not 100%: our bigger buy moves the price more and prices out more followers.
- At "50 ms", 1 SOL top 5% ≈ **10 SOL/day**; at "35 ms" ≈ 21. Capital ~2–3 SOL.
- Caveat: the 1 SOL picks differ a little from the 0.5 SOL ones whose followers' limits were decoded, so part of this rests on estimated limits (optimistic by up to ~20%).


## Independent check of the afternoon claims (report done 14:03 PKT; `ops/overnight/verify_dip/VERIFY_DIRECT.md`, scripts `v2_*.py`, outputs `v2_out/`)
- **1. Direct vs routed: holds.** Fresh check 199/200 and 100/100. New: 45% of fresh triggers are **v1 transactions** (12% of direct triggers, 8% of direct picks), so the decoder must parse v1 messages. The mint sits in a lookup table in 1/144 cases; the seller is not the fee payer in 5/144.
- **2. Direct-only CV: holds in replay units.** Exact reproduction, 6/6 blocks, seeds ±0.5–1, bootstrap 95% "35 ms" +18.2…+25.1, "50 ms" +9.6…+15.7, without the best 10 launches +19.0 / +10.4. At REAL 35 ms the checker infers ≈ +11…+13 per ~33 h.
- **3. History lag: code holds.** 45,223/45,223 identical rows at 0 lag. Event selection on the stale values gives the same or better results. With a 100 ms lag, the guarded version loses 7% / 14% / **32%** at 35 / 50 / 75 ms; the unguarded version is unchanged at 35–50 ms.
- **4. HkQ7hMjy routed delay: partly.** The 8 ms gap is a small sample (CI −0.8…+16). On all triggers +2…+3.5 ms (+5.6 early in the slot); first buyer of any wallet +5.5 ms.
- **5. Census: method right per trip; population claims wrong.**
  - 23% duplicate rows, −368 SOL of phantom loss from unsold tokens valued at 0, never-sold trips dropped, no tx costs.
  - Corrected (`v2_out/census_fifo.jsonl.gz`): ≥100-trip wallets 53, +214.9 (+189.8 net), 79% positive net. DYXDDrZC +20.4 / 948; HkQ7hMjy +17.7 / 1,411; haqqiUUX +18.5; ETwEAQPL +14.0; sssssDdM +10.8.
  - By delay (closed trips): 0–10 ms +7.3% (best); 10–25 +2.0%; 25–40 +0.9%; 40–60 +1.6%; 60–100 −0.1%; 100–150 −0.6%.
  - Skill persists: R1-positive wallets make +119.8 net on R2, 85% positive.
  - `pros53.json`, `pros_R1.json` and "DYXDDrZC +9.0 on our picks" inherit the duplicate bug.
- **6. Exits: partly.** The follower-limit model penalizes long holds (+1…+12 when fixed); 8+ slots are still worse. **2 vs 4 slots is a tie:** on the same trades 4 ≥ 2 ("75 ms" guarded +9.5 vs +6.4); with retraining the order flips between data snapshots.
- **Data drift:** the collector data and `slip_args.jsonl` changed during the work (±1–2 SOL). Freeze inputs before quoting decimals.
- **1 SOL with the picks' own limits decoded (14:07 PKT; only 987 more needed; `dip/cv_b1_real3.txt`):** top 2%: +18.4 / +13.8 / +7.0 (guard +8.2); top 5%: +27.5 / +14.5 / +4.3 (guard +8.6) at "35 / 50 / 75 ms".
  - Holds in replay units. But the earlier check found 1 SOL no better than 0.5 at real latency (base version: +10.8 vs +11.3; without the best 10 launches +4.7). Start at 0.5 SOL; test 1 SOL only with shadow / live data.

## The 0–10 ms band, closer (14:08 PKT; corrected census)
- Its big total (+204 SOL on closed trips) is NOT a repeatable bot strategy.
  - Only 19 wallets have ≥20 trips there, together +20 SOL net in ~33 h (best CZ77onJz +3.2, 5ZKd8DNB +2.7, 9K5QgBKa +2.7). These are pre-queued / own-program buyers.
  - The rest comes from many occasional buyers.
- With the spray costs these repeat wallets pay on failed attempts (not counted in the census), it stays small. Spraying remains rejected.
- **Our speed today:** the Run 2 "75 ms" was measured from shred arrival times (`ops/run1/landtime.py`), about replay "82 ms". There, direct-only is thin (≈ 1.5–3 SOL/day). The speed fix is still the gate.

## Direct + FLASHX8 triggers (14:11 PKT; `dipshadow/direct_plus_flash_flags.json`, `dip/cv_flash_real2.txt`)
- FLASHX8 alone carries 30% of all dip triggers (direct 41%). 97% of its trigger txs use the simple 22-byte / 29-account swap (mint at 7); 3% use 30 accounts (mint at 10).
- **Acting on direct + FLASHX8** (real limits, six-block CV, unguarded / guard): "35 ms" +21.2 / +19.6, "50 ms" +10.3 / +9.4, "75 ms" +0.3 / +5.0.
- Direct-only for comparison: +20.1 / +17.2, +11.1 / +8.2, +3.5 / +5.5.
- FLASHX8 sells help only at "35 ms" and hurt when slower. Keep v1 to direct sells; FLASHX8 is optional, for a fast engine only.

## False triggers: direct sells that fail on chain (14:12 PKT; 14 raw R2 chunks, local data)
- **28.7% of direct pump sell txs FAIL on chain** (8,876 of 30,895); routed sells fail 5.7%. A shred-triggered engine sees them as dumps that never happen.
- Errors:
  - 72% are `Custom 3012` (Anchor AccountNotInitialized): the seller has no token account, i.e. does not hold the token;
  - then `6023` and `6003` (slippage-type pump errors).
- **Engine rules: REVISED 14:16 PKT, see the next section.** Use the min-out check plus the guard; do NOT use a strict holdings check.
- The replay only saw successful sells, so it does not model these. Size the leftover false-trigger rate in shadow mode.


## Which trigger checks to use (14:16 PKT; `dipshadow/failed_sells.py`, read-only RPC on 600 failed direct sell txs; real dumps from local data)
- **Failed sells that would look like a ≥1 SOL dump:** 202 of 1,465 decoded failed sell instructions (86% are under 1 SOL anyway).
  - The **min-out check** (the sell's min SOL out > expected SOL out on our curve) catches 125 / 202 (62%).
  - The holdings check catches 70 more.
  - Only 7 pass both.
- **But the holdings check rejects real dumps:** 1,179 of 18,234 successful direct ≥1 SOL dumps (6.5%) are by sellers with NO trades in our history (tokens received by transfer, etc.).
  - The model's picks among them are profitable: "35 ms" **+3.98** (207 picks), "50 ms" +2.70, "75 ms" +1.06. That is ~20% of the direct-only profit.
- **Decision:**
  - no holdings check;
  - min-out check with ~10% tolerance (stale curve);
  - the **2% guard always**.
- A false trigger then fails our guarded buy, because the price never dropped. It costs ~0.0002 SOL, roughly 5–15 per hour, about 0.002–0.003 SOL/h.

## Frozen real-limit models for the engine and forward test (14:18 PKT)
- `dip/frozen_dip2r_L35/L50/L75.json` (+ .sha256), trained on `ev_real2` (real follower limits, all triggers, 2-slot exit, spacing 5). Act on direct triggers only.
- sha256 prefixes: L35 `e6b9e39fcb61`, L50 `ecb2ce39bced`, L75 `57c398cd7afa`.
- Last-15% validation, top 5%, unguarded mean per trade: +0.0156 / +0.0054 / −0.0019.
- Forward-scored with the direct/routed split by `dip/fwd_dip_direct_loop.sh`, on dips after 14:18.
- These are the models `src/dip.rs` would load; the Rust parity test needs re-export (`export_parity.py`) before use.

## Engine prep (14:26 PKT; host repo only, not wired, not deployed)
- `src/dip.rs` gained the live decoders: `direct_sells`, `sell_sol_out`, `trade_events`, `trade_events_from_inner`.
- `cargo test --release --lib dip`: 10 real trigger txs (incl. v1, lookup tables, a truncated-log multi-sell) decode exactly; the GBDT/feature parity is still 218/218.

## Hybrid: routed triggers from the executed feed, ~15 ms later (14:27 PKT; OOF picks of the all-trigger real-limit model)
| Model picks at | Direct at L | Routed at L (shred-fast, impossible) | Routed at L+15 (executed feed) | **Hybrid, guarded** | Direct-only, guarded |
|---|---|---|---|---|---|
| "35 ms" | +20.1 (guard +17.2) | +6.3 (+7.1) | +1.6 (+4.3) | **+21.5** | +17.2 |
| "50 ms" | +11.1 (+8.2) | +2.3 (+5.1) | −3.3 (+2.2) | **+10.3** | +8.2 |

- With the 2% guard (required anyway), routed triggers seen ~15 ms later through the executed feed add ~25%. Unguarded they don't pay at "50 ms".
- The executed feed is needed for history anyway, so this is cheap to add: the TradeEvent of a ≥1 SOL sell is the trigger.
- Engine v1.5: direct triggers from shreds + routed triggers from the executed feed, guard always.

## Forward check (14:16 PKT run, imputed slippage, so optimistic)
- DIP2 spacing-5 model (frozen 12:09, 1.9 h after): "35 ms" +0.68 on 69 trades (59% win; ≈ 0.36 SOL/h), guarded "50 ms" +0.32, "75 ms" +0.16.
- DIP4 spacing-5 (frozen 10:52, 3.3 h): "35 ms" +1.79 on 150 trades (≈ 0.54 SOL/h).
- **Caution:** that is about half the CV's per-hour rate (all-trigger "35 ms" ≈ 0.79/h with real limits). The window is midday PKT, which is also weaker in the CV hour profile (direct-only "50 ms" totals per PKT hour: 12–15 h +0.2…+0.4 vs 04–09 h +0.4…+1.6).
- If the forward rate stays at half, the real-35 ms estimate drops to ≈ 4–6 SOL/day. Keep watching; restart the collector to keep the forward data coming.
- **Resolved (14:28 PKT):** the CV's out-of-fold picks at "35 ms" made +0.43/h during 10-22 12:00–14:00 PKT vs +0.82/h on average (midday has 29–45 picks/h vs 80–160 at night). The forward window (12:09–14:00, +0.36/h with estimated limits) matches its time of day: no sign of model decay. The 7–9 SOL/day estimate stands, pending a full forward day.

## Who pays us, current version (14:32 PKT; direct-only, real limits, six-block CV; `dip/cv_drop_real2.txt`; unguarded / guard)
| Buys after our entry removed | "35 ms" | "50 ms" | "75 ms" |
|---|---|---|---|
| none | +20.1 / +17.2 | +11.1 / +8.2 | +3.5 / +5.5 |
| 541 random active wallets | +15.5 / +13.9 | +7.9 / +6.9 | +2.0 / +4.5 |
| **541 consistently profitable bots** | **−7.8 / −5.0** | **−10.7 / −8.3** | **−15.6 / −9.8** |

- Same answer as the base version: the profit is the profitable-bot cohort buying right after us. Without them, it loses at every speed. The owner's "become them" decision applies unchanged.

## PumpSwap (graduated tokens) dip-backrun: REJECTED (14:36 PKT; `dipshadow/pumpswap_dips.py`, ~2 h of R2 data, 627 pools, 709k pool trades)
- Pool reserves are inferred from the collector's token-vault balance plus the quote vault's SOL change (constant product); the checks look right (median pool ≈ 286 SOL; consecutive trades line up within ~0.4%).
- Big sells are plentiful (~3,800/h ≥1 SOL), but much of it is volume-bot churn.
- Backrun 0.5 SOL, exit 2 slots, **upper bound** (no follower limits, no tx costs):
  - all ≥2 SOL sells: "35 / 50 / 75 ms" −0.0018 / −0.0021 / −0.0023 per trade (win 21–25%);
  - drops ≥10%: +0.019 at 0 ms (n 569) but −0.003 by "35 ms": the bounce happens instantly (atomic arbitrage), unlike bonding curves, where bots keep buying for slots;
  - drops 5–10%: +0.0013 / +0.0013 / +0.0009 per trade, eaten by ~0.0013 tx costs.
- No realistic-speed edge, even as an upper bound. Not worth a model.

## REAL-latency estimate with the checker's own method (14:38 PKT; `dip/real_latency.py`)
- Each direct-only pick (real follower limits) is priced on a 0–300 ms proxy grid, then averaged over the measured gap d = proxy − real (98k pairs at a real 35 ms, `verify_dip/out/proxy_anchors_mine.json`).
- Picks of the "35 ms" model, SOL per ~33.5 h (unguarded / guarded):

| REAL delay | Real-limit follower model | Checker's earlier scaling (fast bots skip when the price moved, τ) |
|---|---|---|
| 20 ms | +22.0 / +20.8 | ≈ +14…+18 |
| **35 ms** | **+17.4 / +16.4** (≈ 12 SOL/day) | ≈ +11…+13 (≈ 8–9 SOL/day) |
| 50 ms | +11.9 / +12.0 (≈ 8.5 SOL/day) | ≈ +3 (≈ 2 SOL/day) |
| 75 ms | +5.7 / +8.0 | ≤ 0 |

- **Why two columns:** the checker's base-version correction also modelled the ~70 fast backrunners skipping their buy when our buy had already moved the price (their 95th-pct tolerance, τ). That is harsher than the real decoded limits, which only drop a follower whose tx would fail on chain, and much harsher at slower speeds.
- Which is closer depends on how the fast bots react to our buy. Only a shadow / live test can show it.
- **Honest range:** a real 35 ms ≈ 8–12 SOL/day; a real 50 ms ≈ 2–8.5; our ~75 ms ≈ 0–5.
- The proxy-gap pairs come from the first second after creates. The checker inferred, without measuring, that they carry over to dips.
- **Which end is better supported (14:40 PKT; INFERRED from `verify_dip/out/tau_backrunners.json`, `bk_tolerance.txt`):** the strict model uses each fast bot's 95th-percentile *accepted* price (e.g. 5k2Ckkiu 1.029, haqqiUUX 1.168) as a hard cut.
  - Those bots buy fast, so most of their accepted prices sit near the dip price. Their actual decoded slippage limits are usually much looser (median slack 36%).
  - So the strict cut drops followers whose real txs would have succeeded. With exact decoded limits for ~all followers in the picks' windows, the real-limit (higher) end is better supported for on-chain behaviour.
  - What neither model sees is a bot deciding NOT to send after seeing our buy. Bots faster than our buy decide before it is visible; only slower followers could. The shadow / live test settles it.

## Forward red flag on direct-only (15:14 PKT; `dip/fwd_dip_direct.log`, `dip/fwd_direct_dump.jsonl`; estimated follower limits)
- **DIP2-L35 picks since the 12:09 freeze (2.9 h):**
  - direct n 51, "35 ms" **−0.09** (win 43%, median −0.002; spread over 47 launches, worst −0.065);
  - routed n 66, **+0.66** (win 62%).
  - DIP2R (frozen 14:18, ~1 h): direct −0.04 (n 18) vs routed +0.21 (n 16).
- The CV's direct advantage was already shrinking in its last hours: 10-23 10–12 h, direct +0.23 / +0.15 / +0.17 vs routed +0.28 / −0.05 / +0.17. Earlier hours: direct far ahead almost always.
- Noise (about 50 picks) or a regime shift? Unknown yet. **Design change: take BOTH trigger kinds from the start.** Direct sells from shreds (fast) plus routed sells from the executed feed (~15 ms later), all guarded: the CV hybrid gives "35 ms" +21.5 and "50 ms" +10.3. Don't bet on direct-only.
- The forward total over both kinds stays positive: DIP2 spacing-5 "35 ms" +0.60 on 109 picks (+0.67 guarded) over 2.5 h of midday.
- **With REAL limits for the forward picks (15:18 PKT; 602 more decoded):** DIP2-L35 direct −0.14 (guard −0.23) vs routed +0.49 (guard +0.65); DIP2-L50 direct −0.07 vs routed +0.46.
  - All picks together: "35 ms" +0.35 (guard +0.42) in 2.9 h of midday ≈ 0.12–0.15 SOL/h, replay units.
  - The reversal holds. Keep both trigger kinds and keep watching through the busier evening / night hours (the hourly loop runs).

## Owner's challenge: "HkQ7hMjy isn't winning with speed, and it uses SL/TP" (17:56 PKT)
- **Owner's examples, checked on chain:**
  - 2chRQe…: dev `timeworn` dumps 1.91 SOL at +4.2 s. HkQ7hMjy is the first buyer after it, ~110 ms later (block position 21 → 200 of 351). Three bots follow within a few positions. It sells 23 slots later (+42%).
  - AoT8VJ…: 3.56 SOL dump at +8.7 s. HkQ7hMjy first, ~117 ms later; 8 bots follow (+25%). It sells 6 slots later.
- **HkQ7hMjy's delay after dumps** (1,411 unique dip buys, corrected census): p10 19, median 39, p90 80 ms. Net by delay band:

| Delay band (ms) | 0–25 | 25–50 | 50–75 | 75–100 | 100–150 |
|---|---|---|---|---|---|
| Net SOL | +2.95 | +6.33 | **+6.59** | +0.53 | −0.36 |

  - So it does not need ~35 ms. It needs to be among the first buyers after that dump.
- **SL/TP exits on our picks** (`dip/tpsl_eval.py`, `ev_tpsl.jsonl.gz`; same ~2,500 OOF picks of the 2-slot model; real follower limits; guarded, SOL over ~38 h):

| Exit | "35 ms" | "50 ms" | "75 ms" |
|---|---|---|---|
| **sell at 4 slots** | **+30.1** | **+18.6** | **+8.9** |
| sell at 2 slots | +28.6 | +13.9 | +6.6 |
| best TP/SL (TP 8–12%, SL 10%, 10-slot cap) | +28.0 | +16.9 | +5.8 |

  - 30-slot caps are worse. TP/SL does not beat a plain ~0.85 s exit on our picks. Default exit → **4 slots**.

## HkQ7hMjy dissected on its real wallet (18:20 PKT; `overnight/hkq7/`)
- 24 h ledger (read-only RPC, 10-22 18:11 → 10-23 18:10 PKT): trades +25.93 SOL, failed attempts −0.56 (4,164), one 5.62 SOL withdrawal (16:34) excluded → **≈ +25.4 SOL/day**. 1,821 buys (76/h) at 0.5 SOL, win 53%, mean +0.0145/trip, 21/24 hours positive.
- Entry = our dip trigger. Delay after the dump median 39 ms; its profit holds to 50–75 ms (+6.59/33 h), stops by 75–100 ms (+0.53).
- Exit: no sells before slot 3; a timer at slot 6 (25–35% of open trades sold there, up or down); soft take-profit after that; losers held up to ~40+ slots. Best fixed TP/SL/time rule matches 32% of its sells → not a clean TP/SL. Selling all at slot 6 ≈ same money (rough) → profit = selection + speed under ~75 ms.
- Next (free): replay our picks with 4/6/8/12-slot exits (`dip/real_latency_hs.py` → `dip/hs_eval.txt`).
- Hold-slots replay (18:18 PKT, `dip/hs_eval.txt`; same picks, real follower limits, guarded, per 37.5 h; HOLD 2 reproduces the final +23.43):

  | exit | real 20 ms | 35 ms | 50 ms | 75 ms |
  |---|---|---|---|---|
  | 2 slots | +29.95 | +23.43 | +17.05 | +11.21 |
  | 4 slots | **+32.91** | **+26.48** | **+20.14** | **+14.09** |
  | 6 slots (HkQ7 timer) | +30.63 | +24.26 | +17.81 | +11.40 |
  | 8 slots | +27.27 | +21.05 | +14.90 | +9.11 |
  | 12 slots | +25.49 | +19.71 | +13.85 | +8.18 |

  4 slots best at every delay; 6 ≈ 2; longer holds lose ground. HkQ7 itself sells 35% of trips within 6 slots (12% at 3–5, 23% at 6).

## IMIT1 engine build (10-24 00:00–01:00 PKT)
- Executed feed (Kaldera yellowstone-tx, pump account filter) tested: 5,999 of 6,277 pump txs, median 1.6 ms behind deshred (p90 6 ms) → the engine runs on it alone.
- `src/dip_imit.rs`: 42 features + IMIT1 + dump rules + labels + live `TokenBook`; parity with Python 2097/2097 events (0 feature / score / event / label mismatches); live book fed trade by trade = batch (0 diffs); no block sizes live → 1 of 55 picks flips.
- Feed plumbing: `ExecInfo` (block index, fee, TradeEvents with fee bps, CreateEvents, mayhem) on `Arrival.exec`; 674/674 lib tests pass.
- `src/bin/snipe_engine/dipmode.rs` (`--dip`): shadow (no --live) logs dumps/picks with route/leader/client; live = FAST guarded buy (min out = post-dump quote / 1.02, slot deadline), TP/SL/time exits on executed-feed prices, sell_until_zero, Pos accounting + balance kill switch, JSONL records (dump, pick, fire, buy_land, land_poll, exit, sell_land, tape, close, run).
- Shadow on the server since 00:44 PKT (`/root/sniper-dip/`, FRZ config, no sends): first 6 min 5/5 shadow picks = paper picks, scores within 0.0004; 3 paper picks skipped live as NON-VANILLA tokens (our v3 buy can't trade them yet).
- Live script `/root/prod/run_dip_prod.sh` (2g wallet; tmux; passphrase typed; budget file /root/prod/dip_budget.json: total loss across runs ≤ 0.5 SOL; engine `/root/sniper-dip/snipe_engine_dip2`).

## FRZ plumbing test + fixes before run 1 (10-24 01:00– PKT)
- Owner: FRZ tiny test first (1–2 trades x 0.02 SOL), stop the paper engine + dip shadow during live runs (restart paper after).
- Shadow vs paper over 16 min: 12/12 paper picks scored identically live; **6 of 12 were non-vanilla tokens** (holder-reward /
  cashback) → skipped. The buy instruction is flag-agnostic (sniper RE 10-14) but the SELL on those kinds is unverified →
  engine now trades vanilla create_v2 only (also skips legacy `create` and creator-fee tokens). To-do: zero-cost
  `--simulate --sim-sell` on holder/cashback tokens, then allow them (≈ doubles the trade count).
- Fixes: run_dip_prod.sh could not read balances (/root/indep RPC helper needs CONSTANTK_TOKEN from the .env) → fixed;
  `| tee` replaced by a direct log + setsid tail (a Ctrl-c killed tee → engine panic on the next log line, the run_prod H6-1
  lesson); **dip mode had no signal handler** (SIGTERM/SIGINT killed it with a position open) → handler added (no new buys,
  positions finish), feeds get their own stop (exits need prices), wall-clock exit backstop (hold x 400 ms + 3 s) if the
  feed stalls, positions never abandoned on a feed death.
- FRZ trade 1 (01:07 PKT, FrjfSh, score 1.13, dump 3.67 SOL −20%): decision 1.2 ms after the dump on our feed, Nozomi →
  BAM leader DRpbCBMx; **landed 1 slot late → guard refused (pump 6042 BuySlippageBelowMinTokensOut)**, cost fee only.
  In the dump's own slot 6 buyers got in first (1.6 SOL: CVPz447t 5.7 ms, 3Xti8uhq 13 ms, 9k78QZyw 14 ms, haqqiUUX x2
  36 ms, 3MHgGwdL 50 ms after the dump on our feed).
- Room for improvement (speed): trigger from deshred (1.6 ms earlier, p90 6) instead of the executed feed; the dip
  decision is 1.2 ms (the sniper's is 46 µs: log after the fire, not before; profile book/feature/score); BAM-leader route.
- 01:14–01:23 PKT: FRZ 4 fires, 4 guard blocks (we executed 123 / 108 / 44 / 43 ms after the dump; the fast bots buy at
  4–36 ms: 3Xti8uhq, CVPz447t, haqqiUUX x2, 3MHgGwdL, omegoMAe, 85YwZaQa ...). Cost 0.0005 SOL each (fee only).
- Paper at the REAL landing (ops/overnight/sel/realat3.py, 407 TEST picks, 12.3 h, 0.25 SOL, TP5/SL10/1.3 s): 35 ms +3.67 |
  75 ms +1.61 | 100 ms +0.65 | 110 ms +0.50 | 125 ms +0.41 | 150 ms +0.13 SOL; ~80% of picks guard-blocked at 110 ms.
  Guard sweep (realat4.py) at 110 ms: x1.02 +0.50, x1.03 +0.53, x1.05 +0.54, x1.08 +0.48 → keep 1.02.
- Holder-reward tokens (5 of 9 FRZ picks!): `--simulate --sim-roundtrip` (new: buy + sell 90% in ONE simulated tx as our
  wallet) OK on 8a4rp5 / 6QzdZt (113–124k CU); same Token-2022 extensions as vanilla (metadata only) → `--dip-allow-holder`
  (dip6, sha c6f1b40f) on in run_dip_frz.sh / run_dip_prod.sh. Cashback / creator-fee still skipped.
- Nozomi (fra2) refused connections ~01:18 PKT for 1–2 min (engine rebuilt the client, recovered); bam/fd routes are
  nozomi-only → single point of failure (to-do: second path for BAM/FD, needs owner OK).
- Decision breakdown now in each fire record (lat_us: queue / book / score / checks_logs / prepare / fire), dip5+.
- 01:28 PKT FIRST REAL FILL (FRZ, HehqjB, BAM via nozomi): landed slot +1, 115 ms after the dump, 0.0198 SOL in; next trade
  put the value at x0.90 → stop-loss; our sell landed in the SAME slot (idx 355) at 0.019763 SOL out (curve +0.00001):
  **buy → exit → sell → ATA closed works**. Chain −0.003594 SOL = fees: buy 0.000505 + buy tip 0.001 + sell 0.000605 +
  sell tip 0.001 (M-5: every sell also via nozomi with its 0.001 tip) + pump fees. Per round trip ~0.0031 SOL + 2x1.25%
  pump fee (study assumed 0.0016) → at 0.25 SOL ~1.2% + 2.5%.
- FRZ test 1 total (30 min, strict, vanilla only): 14 picks, 7 skipped holder, 7 fires, 1 fill, 6 guard blocks; −0.006624 SOL.
  Landing (ms after the dump, our executed feed): 43, 44, 66, 108, 115, 123, 246.
- FRZ test 2 started 01:35 PKT on dip6 (holder tokens on), max 2 fills, 40 min.

## Landing: fee vs path (10-24 01:55–02:15 PKT; owner: "improve our landing by fee or path, do whatever u have to do")
- Who beat us (ops/dip/speed/fast_bots_paths.py, their txs on chain): BAM → Helius (8/16 within 60 ms), no-tip 5, 0slot 2;
  Firedancer → Astralane 5/10, no-tip 5; Harmonic → Nozomi (A9KKBd 9 ms), Helius. Their priority is LOWER than ours
  (median 1.8M uL/CU, ~0.00012 SOL, tight CU limits) — only whales pay 15–500M. **Fee is not the lever: we already outbid
  ~85% of the bots that beat us; they arrive earlier.** Our buy uses 78k CU (limit 100k).
- `--dip-probe N` (dip7): fail-by-design buys (min out = u64::MAX, pump 6042, fee 0.000505 each, tips revert) on real
  in-envelope dumps; block-position ms after the dump (ops/dip/speed/probe_speed.py), FRZ wallet:
  | leader | A today | B fast-bot paths | C astralane |
  |---|---|---|---|
  | BAM | nozomi 61 (12) | helius 50 (6) | astralane 52 (6) |
  | Harmonic(Agave) | staked-rpc 69 (9) | nozomi 50 (11) | astralane 47 (5) |
  | Harmonic(FD) | – | nozomi 71 (7) | astralane 48 (2) |
  | Firedancer | nozomi+helius 22 (1) | astralane 123 (3) | astralane 137 (2) |
  | Jito | helius+nozomi 71 (6) | helius+nozomi 101 (3) | astralane 70 (5) |
  | all | 68 (30) | 64 (30) | 58 (20) |
  Same route moved ±30 ms between sessions (Jito) → only big gaps are real: Harmonic off staked-rpc, BAM off nozomi-only,
  FD not on astralane. Every path has 190–250 ms tails → fan out to two.
- NEW ROUTES (run_dip_prod.sh / run_dip_frz.sh): bam=helius+astralane; jito=helius+nozomi; harmonic=nozomi+astralane;
  fd=nozomi+helius; agave/other/default=helius+nozomi. Cost: 2 tips (0.002) on a FILLED buy; blocked buys refund tips.
- Probes land ~60 ms on ordinary dumps but our real picks landed ~112 ms (FRZ fires): picks are contested (5–10 bots buy
  the same curve within 40 ms; write-lock contention).
- FRZ spend tonight: trades 0.009 + probes A 0.015 + B 0.015 + C 0.010 = ~0.049 SOL (owner: watch the balance).

## Run 1 (PROD 2g, 10-24 02:15–02:43 PKT) and the nearby-landing work
- Run 1: 3 trades x 0.25 SOL, strict, guard 5%, routes v2: 11 fires, 3 fills, 3 wins (+0.0535 C3aA8C, +0.0276 AMKcxJ,
  +0.0478 CiYHxY), 8 guard blocks (0.0040 fees) → **+0.1249 SOL**, wallet 3.9574 → 4.0823. Trade 1 trigger: an insider
  (first-trade wallet, in the 462 cohort) sold 2.69 SOL (a third of its 5.9 SOL launch buy) at 1.3 s after 7 buyers / 9.9 SOL.
- Guard 15% what-if (ops/dip/speed/guard_whatif.py, 15 real blocked buys re-bought at our exact block position): 5% −0.009,
  10% −0.057, 15% −0.063, 20% −0.079 SOL (real costs); 12 of 15 lose if bought. Backtest 407 picks (realat5.py): 5% best at
  every latency; 15% −0.49 at 110 ms. **Keep 5%.**
- Leader distance (probes A–C): <50 ms leaders median 50–62 ms block-position, ~75% same slot; US east 167 ms (1/10 same
  slot), US west/Asia 195. Fills tonight: 2 near + 2 far (CiYHxY Kent +0.048) → no near-only gate yet. <50 ms leaders =
  405 of 661, 74% of slots (/root/fix2/close_leaders_50ms.txt). Owner: multi-region later (1 SOL trades); focus nearby now.
- dip8: timing records (first sighting on any feed, exec-feed lag, reaction, fire → our tx seen back; the PoH "leader
  clock" field is WRONG: our entries feed skips most ticks so hashes-per-tick is inflated → ignore land_ms_poh), near-leader
  gate (--dip-near-leaders), forced path rotation for probes (--dip-probe-paths). Probe config dip_probe.toml = dip_shadow
  + bolt + haan + tpu-direct. FRZ topped up 0.1 SOL by the owner (transfer_prod.sh).
- Probe D (03:00 PKT, 70 probes, nearby leaders, 10 per path; fire → our tx seen back, median ms): nozomi 30, landx 31,
  bolt 35, helius 35, astralane 46, haan 49, tpu-direct 50; by client (n 1–5): BAM nozomi 24 / bolt 30 / landx 30; FD
  landx 20 / nozomi 28 (helius 123); Harmonic nozomi 31 / helius 34; Jito bolt 37 / astralane 43 (tpu 136, landx 81).
  Trigger: executed feed 1.6 ms behind the first sighting (p90 5.5); first sighting → fire 2.1 ms.
- ROUTES v3 (run_dip_prod.sh, dip8): bam=nozomi+bolt; jito=bolt+astralane; harmonic=nozomi+helius; fd=nozomi+landx-fra3;
  agave=nozomi+helius; other/default=nozomi+bolt.

## Run 2 (PROD 2g, 10-24 03:03–03:50 PKT; routes v3, engine dip8)
- 18 fires, 5 fills, 4 wins: 5yi9Q2 +0.103894 (TP, Jito Frankfurt, landed 59 ms, nobody ahead), GZRarp −0.014740 (time, Ashburn
  far leader, DYXDDrZC 1.16 ahead, 3 tips at a BAM→Jito slot edge), DrWCph +0.024605 (TP, 186 ms but a 0.81 seller ahead pulled
  the price back), AC3g7R +0.018244 (TP), 25yfy9 +0.007858 (time); 13 misses (guard / 1 deadline) → **+0.133295 SOL**, wallet
  3.982301 → 4.115597. (The owner's first start attempt at 03:03:35 ended in 8 s — an extra run-2 entry in dip_budget.json.)
- Runs 1+2: 29 attempts, 8 fills (28%), 7 wins, 1 loss, **+0.258231 SOL** on 0.25 SOL buys. Misses 21 of 29 (72%).
- haqqiUUX (owner: "no failed txns?"): 114 of its last 1,000 txs failed (11.4%, pump 6042 like ours; GMGN hides failed txs);
  own router program haqqqMGN…; Helius 25/40 (tiny tips), 0slot, Astralane; CU price ~1.84M. (ops/dip/speed/haqq_path.py)
- BLUEPRINT: ops/dip/BLUEPRINT_V1.html, generated by ops/dip/blueprint/make_blueprint.py from data/ (refresh from the server).
- .gitignore: data excluded (gz/npy/pkl/json/txt/csv/html under ops/ etc.), models + blueprint kept; secrets scan clean.

## Run 3 (0.35 SOL, routes v4 = 3 paths) + misses / competitors / sizing (10-24 04:15–05:10 PKT)
- Run 3: 14 fires, 7 fills, 4 wins: GFXU9F +0.018719, CgWwnp +0.026741, 92jg98 +0.014108, 4ZZ5Ke −0.038583 (time),
  2ssK7Y −0.008262 (time, curve +0.0056 eaten by ~0.014 costs), Q1pQm3 +0.007514 (time), AEQKoc −0.056308 (stop-loss
  hit by a −20% single trade) → **−0.039605**; wallet 4.115597 → 4.075981. Quiet hour (best scores 0.44–0.50 at first).
- Runs 1–3: 43 attempts, 15 fills, 11 wins / 4 losses, **+0.2186 SOL** trading (2g +0.1186 vs first start after the
  0.1 SOL FRZ top-up).
- Misses (ops/dip/speed/miss_analysis.py, 30 guard misses): the price crossed our guard a median 45 ms after the dump
  (p25 26, p75 66); we had to be a median 34 ms earlier (10 ms → 2/30, 20 → 7/30, 30 → 12/30, 50 → 20/30 would fill);
  the 3 imitated bots crossed first in 11/30. Run 2 split: exec-feed lag 1.7 ms, reaction 2.7 ms, send → seen 57 ms.
- Competitors (crossers.py, competitor_fanout.py): HkQ7hMjy fails ~70% of buy attempts (4,164 failed / 1,821 filled per
  day) = our 72%; failed attempt ~0.000135 SOL vs our 0.000505. **All top bots use a durable nonce in every tx and send
  each trade as one copy per relay (6–9 paths) + a no-tip copy; one tip per landed trade.** Relays that won their trades:
  Helius, Nozomi, Astralane, SpeedLanding, Bolt, 0slot, FlashBlock, Jito, Stellium, bloXroute, Soyas, LandX, Node1, ...
- haqqiUUX sizing (haqq_sizing.py, 1,074 buys / 2.2 h): tiers 0.25/0.3/0.4/0.5/0.75 SOL; 0.74 when curve vSOL < 32, else
  ~0.3; tokens bought 3+ times: 58% win +7.66, once: 32% −1.95 (scale-in on repeated dumps).
- Our backtest (size_reentry.py; TEST 12.3 h + recent 2.8 h): per-fill % barely drops 0.35 → 0.75 SOL (size up works);
  haqq-style shallow-curve size-up +23% vs flat 0.75 ~+100%; re-entry / hot-token re-picks ≈ 0 or negative for us.
- Selection vs competitors (comp_select.py, 9,453 dumps 02:15–04:28): strict = bots bought 90%, 63% win, us +0.67 @75 ms
  (0.35 SOL); wider / top8 marginal (negative at 110 ms); their extra profit = small dumps (−3…−5%, 1.0–1.3 SOL, DYXDDrZC)
  held for minutes → negative for us with our 1.3 s exit.
- Probe E (05:02, nearby, 8 each, fire → seen): nozomi 35, staked-rpc 42 (tipless, 7/8 same slot), helius-swqos 58
  (0.0002 tip), bolt 60, helius 65 ms. ROUTES v5: nozomi core + helius-swqos instead of helius + tipless staked-rpc on
  every class (run_dip_prod.sh).

## Run 4 (0.35 SOL, routes v5) + exits / haqq studies (10-24 05:10– PKT, run 4 still live at 06:00)
- Run 4 so far: Biiv46 +0.028214 (TP), 3PsjL5 −0.000731 (time; curve +0.0132 eaten by costs); misses landed 17–48 ms
  after the dump on nearby leaders (fire → seen 10–37 ms) vs ~80–95 ms in runs 1–3.
- TP potential (tp_potential.py, 9 TP exits): we got median +11.5%; best price within 10 s median +38%, max +225% (CgWwnp).
- Exits on our live fills (exit_live_sim.py, runs 1–4, 17 fills, curve level, tips out): TP5 now +0.356, TP10 +0.418,
  TP20 +0.369, **no TP / sell at 1.3 s +0.630**, half TP5 + half 1.3 s +0.493, half TP10 + half 1.3 s +0.524. Backtest
  (exit_realspeed.py, 180 strict TEST picks): TP5 +1.571 / no-TP +1.476 at 75 ms; +0.710 / +0.850 at 110 ms; hold 6 s
  +1.108 → still open which; holding longer than 1.3 s is worse in both.
- haqq on Helius (haqq_helius.py, 150 txs): Helius lands 61% of his trades (BAM 41/71, Harmonic 34/41, Jito 13/23) with a
  0.0002 tip on the SWQoS-only tier; his tipless copy wins 11/13 on Firedancer leaders → ROUTES v6 (helius-swqos on
  bam/jito/agave/other, deployed for run 5, run 4 keeps v5).
- haqq's top tokens (haqq_trades.py): buys fresh tokens (age ~2 s) right after launch dumps, stacks 2–5 buys of
  0.25–0.5 SOL, sells in pieces at +30–60% within 2–6 s, lets the last piece ride 30–60 s.
- **haqq's way replayed on OUR 17 live fills at our speed** (ops/overnight/sel/replay_haqq.py; adds 40 ms after the dump,
  guard 1.05, extra tx costs in): wins (12) / all (17): now +0.455 / +0.356; half rides 30 s +0.376 / +0.257; haqq thirds
  (+30%/5 s, +60%/15 s, ride 60 s, stop −15%) +0.294 / +0.195; **thirds + his re-buys on later dumps −0.654 / −1.027**
  (35 re-buys, 30 lost; still −0.69 at 0 ms). Only CgWwnp gained (+0.293 vs +0.044). Our picks bounce briefly then fade;
  his fresh-token picks sometimes run +150–280%. → keep the quick exit; no re-buys.
- **Dev bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa** (owner's contact 10-24 02:19: "haqq mostly buys from this dev";
  ops/overnight/sel/haqq_dev.py, window 01:35–05:55 PKT, 8,031 tokens): a serial launcher, signs ~30 creates/h (~60% with a
  fresh one-off creator wallet), 110 tokens = 1.4% of launches but 5.8% of >= 1 SOL sells. "Mostly" is FALSE (haqq: 218 of
  1,599 buys = 14%, 13% of SOL) but haqq trades 60% of its tokens vs 8.9% of others, +7.22 SOL on 66 tokens (+0.11/token)
  vs +13.20 on 703 (+0.02/token); 66% of his buys there come right after the dev's own sell; 2 of his top-6 tokens (2AtTPk,
  2qqM27) are this dev's. HkQ7hMjy 33% vs 4.2%, DYXDDrZC 22% vs 3.7% of tokens. Us: 5 of 18 fills (C3aA8C, AMKcxJ, CiYHxY,
  AEQKoc, 3PsjL5). Backtest (size_reentry_{test,recent}.json, 0.35 SOL): strict on this dev +17%/fill vs +5% others; total
  now → +wider tier on this dev → + 0.75 SOL on this dev: TEST 75 ms +1.571 → +1.846 → +2.714; TEST 110 ms +0.710 → +0.735
  → +1.414; recent 75 ms +0.692 → +0.976 → +1.503; recent 110 ms +0.392 → +0.535 → +0.906. Small samples (dev fills 28 /
  18); one dev can stop or switch wallets any time. Not in the engine yet (needs a dev list + per-dev tier/size flag).
- **Run 5 config (owner 10-24 06:25 PKT: "for next run lets do 1.3 and 0.75 for this dev tier")**: no take-profit (stop-loss
  −10% or sold by 6 slots ~1.3 s); dev list (/root/sniper-dip/dev_list.txt = bwamJzzt…) → its tokens picked from the wider
  tier at 0.75 SOL, everything else strict at 0.35. Engine dip9: `--dip-dev-list / --dip-dev-tier / --dip-dev-spend-lamports`
  (a token is the dev's when the create's signer OR creator is listed), buy templates per (tip shape × size), all built at
  start (`warm_templates`), `--fast-bench` byte-checks the second size. run_dip_prod.sh: `--tp off --dev-list F --dev-size 0.75
  [--dev-tier wider]`; max-sol / balance / size x open checks use the larger size.
- **Last 24 h replayed with the run-5 settings** (ops/overnight/sel/day24.py + day24_sum.py; 10-23 06:30 → 10-24 06:27 PKT,
  23.1 h recorded, 18:33–19:26 missing; 479 candidate dumps, 222 on the dev's tokens; one position at a time, 5-slot spacing,
  real costs: +0.0035 SOL per fill over the model, 0.0005 per blocked buy). SOL per day, runs 1–4 setting / no-TP only / run 5
  (no TP + dev tier 0.75): 50 ms +4.116 / +3.858 / **+7.205**; 75 ms +2.498 / +2.439 / **+5.374**; 110 ms +1.297 / +1.743 /
  **+3.165**; the dev's tokens = +4.92 / +3.90 / +2.14 of run 5. Both halves positive (day 06:30–18:33, night 19:26–06:27).
  Live calibration: per fill live +0.015–0.017 SOL vs model +0.017 (75 ms) / +0.012 (110 ms); live fill rate (runs 1–3 35%,
  run 4 24%) sits between the 75 and 110 ms rows → ~+3–5 SOL/day if it ran all day uncapped (our runs cap at 7 trades).
- 24 h replay, more speeds / sizes (owner: "and with 35ms?", "and with 1 sol size"), SOL per day — runs 1–4 / run 5 (dev 0.75)
  / run 5 with the dev tier at 1 SOL / everything at 1 SOL: 35 ms +5.92 / +10.81 / +12.30 / +18.15; 50 ms +4.12 / +7.21 / +8.22
  / +11.90; 75 ms +2.50 / +5.37 / +6.15 / +8.62; 110 ms +1.30 / +3.17 / +3.43 / +5.35. Model fill rate 71% (35 ms), 57% (50),
  40% (75), 29% (110) vs live 35% (runs 1–3) / 24% (run 4) → we are at the 75–110 ms rows today. 1 SOL: ~2.9x the size for
  ~1.6–1.7x the profit (price impact, fewer followers fit), ~3x the loss per bad trade; unproven live above 0.35.
- Our live landing (dip_speed.py, block position, 212 ms slots, runs 1–4): 15 WINS median 70.7 ms after the dump (p25 39,
  p75 92), 9/15 in the dump's own block; 6 losses 41.5 ms; all 21 fills 66.2 ms; 44 misses 97.7 ms. Per run wins: r1 66,
  r2 85, r3 54, r4 82 ms. Feed-seen delay of wins: median 59 ms. → we trade at the replay's ~75 ms row.
- 24 h replay, sell at 2.5 s instead of 1.3 s (no TP, run-5 sizes): SL −10% 35 ms +8.56 / 50 +5.49 / 75 +4.71 / 110 +2.94;
  no SL +9.78 / +6.97 / +5.11 / +3.15 vs 1.3 s +10.81 / +7.21 / +5.37 / +3.17 → 1.3 s stays best at every speed.

## Raw recording 24/7 (owner OK 10-24 06:50 PKT: "record all the runs raw so we can do this daily while tuning")
- Server: /root/sniper-collect/rotate.sh (repo ops/collect/rotate.sh), root cron every 5 min: starts the next 24 h
  collector 6 min before the current window ends (overlap, no gap; TAIL_MIN 20) and restarts one if none runs. Timezone-free
  (server clock is Europe/Vilnius with DST). Off: touch /root/sniper-collect/ROTATE_OFF. Log: rotate.log.
- Container: ops/collect/keeper.sh every 10 min (keeper_loop.sh): copies every server run to
  /home/moiz/sniper-data/collect/<run>/ (size-checked) and deletes a SERVER run only when it is not current, its tail ended
  > 2 h ago and every file is here with the same size. Never deletes in the container; pauses below 30 GB free. First pass
  10-24 06:44 PKT: run_20261021_2207 (9.9 GB) and run_20261022_1543 (14.7 GB) verified here and removed from the server
  (server 29 → 52 GB free). ~17 GB/day; the container (165 GB free) holds ~9 days → retention rule to agree later.
- Daily replay: ops/overnight/sel/day24.py + day24_sum.py (windows still hard-coded; to generalize per day/run).
- "What if we took ALL the dev's tokens?" (owner 10-24 06:50; sel/day24dev.py + day24dev_sum.py; last 24 h): 3,442 dumps on
  256 of its tokens. Each dump alone at 0.75 SOL, no TP 1.3 s, at 75 ms: strict +1.93 (45 fills), wider +1.71 (53), top8 +1.85
  (102), below top8 −21.49 (1,328), outside the envelope −32.00 (1,345); at 110 ms top8 −0.36. Whole day at 75 ms: run 5 as
  set +5.37; + every in-envelope dev dump −12.65; + every dev dump −35.13. → the score is what makes its tokens pay; keep
  wider-and-up (top8 on its tokens only once we land faster: + at 35–75 ms, − at 110 ms).
- Token TEXT check before trying Jev (owner 10-24 07:00, sel/textcheck_rows.py + textcheck.py; lexical stand-in: name /
  symbol / description n-grams, socials, copycat names; TRAIN 10-23 06:30–18:33, TEST 19:26–06:27): (a) text alone → "pros
  traded this token" AUC 0.546 (tweet link 43.9% vs 34.3%, website 44.6% vs 36.3%, profile link 17.7% vs 39.5%); (b) dump level
  IMIT1 0.830 → score + text 0.830 (text alone 0.527); (c) TEST picks by text score: low +5.0%/fill, mid +3.2%, high +6.7%
  (~42 fills each, noise). → text adds nothing to our picks; Jev not worth it for this strategy (latency 70–500 ms too).
- Wider tier for ALL tokens (owner 10-24 07:05; agent, sel/day24w.py + day24w_sum.py; same 24 h, run-5 exits): run 5 as set
  / + wider on other tokens (0.35) / wider for all at 0.35 without the dev size-up / + wider with TP +5% on the extra picks:
  35 ms +10.81 / +11.81 / +8.33 / +12.33; 50 ms +7.21 / +7.57 / +5.09 / +7.82; 75 ms +5.37 / +4.97 / +2.98 / +5.22; 110 ms
  +3.17 / +2.05 / +0.92 / +2.40. Extra picks alone: +1.3%/fill at 35 ms, +0.5% at 50, −0.4% at 75, −2.1% at 110 (strict
  others +4–6%). → wider for all only pays at <= 50 ms; at our speed keep strict on other tokens.

## Run 5 (10-24 06:50–07:46 PKT; dip9, no TP / SL −10% / 1.3 s, dev list at 0.75 wider, others strict 0.35)
- 15 fires, 10 fills (67%), 5 wins / 5 losses, wallet 4.195773 → 4.194333 = **−0.0014 SOL**. Wins: AorAyR +0.0108, FCHTPt
  +0.0077, E5yXCm#2 +0.0080, 7Aaktsg +0.0451, BNGrnA +0.0413; losses 7nKLXu −0.0128, E5yXCm#1 −0.0101, 2c5iTH −0.0080, 2Qg82V
  −0.0042, **wVKcA4 −0.0766** (score 1.22, age 1.5 s, 6.48 SOL dump; stop-loss fired at −10% but the sell landed at −20%).
  No dev-list token came up (0.75 tier unused). Runs 1–5 trading ≈ +0.34 SOL.
- Exits on run 5's fills (exit_live_sim.py, 9 of 10 on the tape, curve level): TP +5% +0.114 vs no TP +0.069 (opposite of runs
  1–4: +0.36 vs +0.63). All 26 live fills: TP5 +0.47, no TP +0.70, half/half +0.58; 24 h replay: tie at 75 ms → keep no TP,
  re-check daily.
- Speed run 5 (block position, 3 first fills): 48 / 69 / 162 ms; bot reaction 2–5 ms; fire → seen 32 ms when in the dump's
  block, ~117–160 ms when the buy misses it (next leader) → the outward leg (send → block) is the lever.

## Run 7 setup (owner 10-24 08:10 PKT: "do near leaders only ... add the route ... run 7 with all your recommendations for 8 hour")
- Independent agents (ops/agents/headtohead/REPORT.md, freshaudit/REPORT.md): our bot reacts in ~3 ms; the outward leg (send →
  block) is 30–37 ms vs the first rivals ~25 ms; we land ~140 entries into the dump's block vs HkQ7 ~75–90. Jito leaders worst
  (91 ms, 25% fill), rivals' Helius copies land first there; far leaders worth ~0; tips 0.0026 SOL per fill (one tx tips 2–4
  relays); size scales ~linearly to 1–1.5 SOL; fee: agents disagree (needs an A/B).
- Near leaders (leader_rtt_new.json, RTT from Frankfurt): < 1 ms 35.3% of slots, 1–5 ms 0.6%, 5–12 ms 28.0%, 12–30 ms 9.6%,
  ≥ 50 ms 24.3%, unknown 2.1% — same in epoch 1067. List /root/sniper-dip/near_leaders_5ms.txt (199 leaders < 5 ms = 35.9%).
- run_dip_prod.sh (md5 7a56bbd7): `--near FILE` → `--dip-near-leaders`; routes v7: jito = helius (default / dual, 0.001) +
  nozomi + staked-rpc (was nozomi + helius-swqos + bolt + staked-rpc). Not yet: Jito bundle path (config tip 0.012 SOL, untested),
  duplicate-sell fix (Biiv46 3012), one tip per landed buy (nonce fan-out), leader-aware fee (A/B first).
- Run 6 (07:53–, 0.5 strict, to be stopped by the owner for run 7): 9vWX2S −0.0677, B5TfMe +0.0613.
- PROPOSAL run 8 (cost cut, config only, needs the owner's OK; agents' lever "one tip per tx, low priority, tight CU"):
  measured now (runs 5–7, 16 fills): tips 0.0022 SOL per filled buy (bam route nozomi 0.001 + helius-swqos 0.0002 + bolt
  0.001), buy fee 0.0005 (100k CU × 5M µL), sell ~0.0016 (0.0006 priority + 0.001 nozomi tip) → ~0.0043 SOL fixed per round
  trip + ~2.5% pump fees. Proposed routes v8: bam = helius-swqos + staked-rpc (0.0002); harmonic = nozomi + staked-rpc (0.001);
  jito = helius + staked-rpc (0.001); fd = staked-rpc + tpu-direct (untipped; haqqi's untipped direct lands 79% same slot on
  Firedancer vs 9% via Helius); agave / other / default = helius-swqos + staked-rpc. --prio-micro 2000000 (top bots 1.6–2M),
  --cu-limit 85000 (our buys use 57–83k). Saves ~0.0016 tips + ~0.0003 priority per fill and ~0.0003 per failed buy.
  Risk: landing order (agents: fee / tip / relay barely change it except Jito / Firedancer) → compare run 8 fill rate and
  landing ms with runs 5–7 on near leaders.

## Run 7 (10-24 08:04–15:43 PKT; near leaders only, routes v7, 0.5 strict + dev 0.75, no TP)
- 54 picks, 36 skipped far_leader, 18 fired, **9 fills (50%), 6 wins**; wallet 4.187401 → 4.423950 = **+0.2365 SOL**.
  Trades: EwX2T1 +0.0201, 2mJMZh −0.0345 (SL), B7cX5w +0.0118, VQWGXt −0.0001, C3Z7zU −0.0253, 9RRMqs +0.0083, **5LnSgd
  +0.1443**, **5mXG5C +0.1077**, F55CWW +0.0089. Speed: fills median 35 ms after the dump (11–137), misses 56 ms, 14/18 in the
  dump's block, reaction 2.7 ms, send → seen 34.7 ms (runs 1–6: fills 66 ms, misses 98 ms, ~57% same block).
- Replay of run 7's hours (sel/run7w.py + run7w_sum.py, near leaders): as set +0.157 / +0.057 / +0.029 at 35 / 50 / 75 ms;
  wider tier on every token +0.269 / +0.170 / +0.119 (the 20 wider-only picks +0.09–0.11). Live matched the 35 ms row on
  fills (9). → run 8 = run 7 + `--tier wider`.
- All dip runs: 2g 3.957371 (first start) → 4.423950; trading ≈ +0.57 SOL (0.1 moved to FRZ after run 1).

## Multi-region kit (owner 10-24 16:00 PKT: Amsterdam edge VPS; "prepare the bot for multi region setup") — ops/region/README.md
- One full engine per region, own wallet + loss budget, disjoint near-leader lists (each leader on the closer server).
- Built: make_edge_config.sh (ran on Frankfurt → /root/sniper-dip/dip_edge_ams.toml, every endpoint → its Amsterdam twin,
  resolved by DNS), deploy_edge.sh (container → edge, secrets piped Frankfurt → edge unseen, sha-checked), leader_rtt.py
  (region-neutral RTT), split_near.py, run_dip_prod.sh `--region fra|ams` (md5 05a443de deployed; fra unchanged).
- Needs from the owner: the VPS (glibc ≥ 2.34; check inbound traffic cap), the container's SSH key added, the edge wallet
  (`arbx keystore-encrypt --generate --show-backup` on the edge) + funding.
- 10-24 16:35 PKT Amsterdam edge set up (it@84.32.104.202:1996, Ubuntu 26.04, 2 vCPU / 2 GB): deploy_edge.sh all files sha-ok;
  edge .env KALDERA_TOKEN + CONSTANTK_TOKEN = the Amsterdam key, common.py → rpc-amsterdam (getSlot OK); endpoints 0.19–0.32 ms
  from the box (Frankfurt kaldera 7.5 ms); LandX ams1 (0.24 ms) chosen over ams2 (0.29). Measured split (split_near.py, each
  leader on the closer server, < 5 ms): Frankfurt 198 leaders 35.9% of slots (/root/sniper-dip/near_leaders_fra.txt; one
  leader 4QNekaDq moved to Amsterdam: 4.9 ms vs 0.19), Amsterdam 120 leaders 20.5% (/root/sniper-dip/near_leaders_ams.txt on
  the edge) → 56.4% of slots together. Next: owner creates the edge wallet; zero-cost bench + shadow on the edge.

## Failed-buy review + run 10 so far (10-24 18:50 PKT; owner: "we gotta do smth about it" — Solscan list of red buys, AMS wallet)
- Run 10 (A/B, both started ~18:10 PKT): FRA 4 s hold / SL −20% / 0.55 + dev 0.75: 9yJrLW **+0.2740** (dev, 0.75), 7gRYtM
  guard-fail, 3pQoFA −0.0773 → **+0.1962**. AMS 1.3 s / SL −10% / 0.35 + dev 0.55: DPuSnf + 8cCv3o guard-fails, fbsPyx −0.0023,
  9yJrLW +0.0593 (first AMS Jito-leader fill), J5SxQW +0.0572 and +0.0763 (two dumps), q2rc3D −0.0327 → **+0.1568**.
- All 35 failed buys of runs 5–10 (FRA 28, AMS 7) are pump 6042 = our +5% guard; none hit the slot deadline. Each costs
  0.000505–0.000508 SOL (base + 5M µL/CU × ~100k CU; the tips revert) → ≈ 0.018 SOL in total.
- Block forensics (speed/failed_blocks.py, 28 fails with collector data): 2–8 rival buys (usually 3–5) landed between the dump
  and us; 21 in the dump's block, 7 one block late (6 of the 7 on Jito leaders). The 105 rival buys ahead of us: only 16 paid
  more priority (median 1.56M vs our 5M µL/CU), median tip 0.0002; relays helius 37, no tip 34, astralane 13 → speed, not price.
- CU (getTransaction): fills use 75–93k of the 100–100.6k limit → the buy limit cannot shrink; fails 54–77k; sells 46–53k of 120k.
- Jito bundle check (bundles.jito.wtf/api/v1/bundles/transaction/<sig>): of 6 Jito-leader fills only 1 (AMS 9yJrLW) landed as a
  bundle, 5 via the normal lane → bundle-only (revert protection) on Jito leaders would likely cost speed; not proposed.
- Guard retest still says +5% is best (+2.72 vs +2.64 at 10% vs +2.38 at 20%, 35 ms, near leaders, last ~19 h).
- Same token on both servers: 9yJrLW dumped twice, 3.6 s apart — 18:39:51 in Frankfurt-near Fd7btgyS's block (FRA bought, AMS
  skipped far_leader), 18:39:55 in Amsterdam-near LeDbQ99Q's block (AMS bought, FRA skipped). Lists share 0 leaders, so never
  the same dump; AMS's buy landed in the same block just before FRA's 4 s sell (idx 29 vs 207).
- One duplicate sell failed (AMS q2rc3D SELL #2, 3012 AccountNotInitialized: #1 had landed, balance not yet confirmed 0); 1 of
  ~60 dip sells.
- Retrain (agent, sel/imit2_build.py + imit2_eval.py): keep IMIT1; IMIT2b (top-10 label) +0.4–1.2 SOL at top4 but ~1.8x the
  picks, worse 01–07 PKT and at strict, not significant; not saved.
- Options put to the owner: buy priority A/B 5M → 1.5M (fail 0.0005 → 0.00016; needs OK), dev-only wider-guard replay (free),
  optional cross-server "token busy" signal.
- Dev-only wider guard (sel/dayguard_dev_sum.py, same rows): no gain — dev at +5% +1.150 vs +7.5% +1.101 / +10% +1.006 (35 ms);
  50 ms +0.747 vs +0.850 at 7.5% (6 extra fills, noise). Dev entries 5–10% above the dump price: 7 picks −0.169. Keep +5% for all.

## Relay race on dip triggers (10-24 ~20:35 PKT; owner screenshot: "winners on Jito leaders use soyas") — speed/relay_race.py
- 640 dip races of the 10-23/24 recording (every IMIT1-envelope dump; buys after it in S and S+1, relay from tip accounts).
- First successful buy after the dump, Jito leaders (202): no tip 30%, helius 28%, astralane 10%, speedlanding 8%, nozomi 7%,
  landx 2%, **soyas 2%** (5 races). BAM: no tip 34%, helius 28%, astralane 8%, nozomi 7%. Harmonic: no tip 32%, helius 16%,
  nozomi 15%, astralane 14%, speedlanding 13%. Firedancer: no tip 49%, astralane 18%.
- Share of a relay's buys that were among the first 3: speedlanding 72% (Jito) / 86% (rest), nozomi 68% / 72%, landx 48%,
  bolt 44%, helius 38% / 36%, astralane 34% / 42%, no tip 33% / 35%, jito 21% / 34%, 0slot 22–24%; soyas 11 buys on Jito
  leaders all day (median rank 2, 5 firsts).
- Bots: HkQ7 (median rank 2) = nozomi on BAM / Jito / Harmonic (soyas only 3x); DYXD (2) = speedlanding on Jito + Harmonic,
  helius/astralane on BAM; E6JasdE8 (1) = speedlanding everywhere; 7PedQZmc (1) and CVPz447t (2) = no tip (own staked
  connections); haqq (4) = helius / no tip. → soyas claim not supported on a full day; speedlanding is the relay to probe
  (selection caveat: fast bots pick these relays; only a forced-path probe measures the relay itself).

## Other bots' strategies (agent, 10-24 ~20:30 PKT) — ops/strategies/REPORT.md
- 424 consistent winners (+3,166 SOL realized / 46 h) in 10 families; dip family rediscovered (haqq #4, DYXD #13, HkQ7 #17).
- New and open to us: F7 "quiet-token bait" — 0.9–3 SOL first buy on a token ≥150 slots old, quiet ≥20 slots, curve ≤45 SOL;
  followers buy within 1 slot in 62–65%; sell after ~21 s. Day-1 rule on day 2: +209 SOL / 4,977 events (+3.4%/SOL); real
  baiters +199 / +213 SOL per day. Untested with our wallet; conflicts with the "race pools only" rule → owner decision.
- Too fast for us: F4 big-buy backrun (2 tx behind), fastest F1 creator-dump buyers; F6/F1/F3 replays lose at 35 ms.
- API spend: study $0.33; launch labels $4.67.

## Haiku pattern search on trading data + bot playbook (agent, 10-24 ~20:40 PKT) — ops/strategies/patterns/REPORT.md
- 428 rules (Haiku rounds 1–3 on 1,829 tape stories/day + variants), train R2 → test R3 → check R1. Every "react to someone
  else's trade at 35–50 ms" category loses 1–1.5%/trade (6 of 242 positive, tiny). Survivors = "first buyer on a quiet
  token" baits only: refined quiet bait (0.75–3 SOL) +82 / +101 / +44 SOL per day; new young-token bait (6–25 s old, paused
  2 s, 0.9–2 SOL) +0.04–0.07/trade all 3 days, follower within 1 slot 67–69%. At 0.35–0.75 SOL: follower rate 41%, edge
  +0.008–0.014/trade. Joining someone else's bait 35–50 ms later loses. Front-running specific bots loses.
- Bot playbook: bait responders B301 = 9pQQc1xy (F9, 15–16% hit), B1 = ssssswdk (~10%); dip reactors haqq (13%), HkQ7 (4%),
  AUih1Qc6; early-launch CWiNFAEk, dKMjeGJ4, Anubis51. Haiku's bot descriptions were too neat (none > ~35% hit).
- Next (owner): live bait probe (30 baits, fresh wallet; conflicts with "race pools only") or free live watch of others'
  baits first. API: $0.43 (total all Haiku today ≈ $5.4).

## Wallet studies (owner 10-24 ~21:05 / 21:25 PKT, Haiku-assisted agents)
- BUkpShoE (ops/strategies/bukp/REPORT.md): busy ~1-min tokens with the creator out, curve 32–64, 6–7 bots holding. Buys
  right after another trade (74% after buys). Size = 2% of curve SOL; one buy and one sell; 5–7 positions at once; 300 s
  timeout. Small buys earn +40–62 SOL/day, big buys lose. Entries are predictable (AUC 0.91), but his EXIT edge is not
  reproducible: every exit rule, model or Haiku rule loses on all days → can't run it. Costs 4× lower than ours.
- sssssDdM: study running (agent; +151 SOL / 46 h, 8,845 trips, ~0.94 SOL, 20 s hold).
- sssssDdM (ops/strategies/sssss/REPORT.md): a 4-wallet buy-burst momentum fleet, +75–90 SOL/day, size 1.88% of curve SOL,
  lands ~15 ms after the burst. The profit is ~45 "runners"/day (top 1%) held 1.5–2.5 min. Its edge is landing first plus exit
  timing, not selection. Can't copy it: everything buildable loses; copy-trading −160 to −214 SOL/day. Same lesson as
  BUkpShoE: the money is in the runner exits.
- 6tzAKfHt (owner screenshot: GMGN 97% win, +$22K/7 d; data /home/moiz/sniper-data/strategies/w6tz/): an insider of a brand-name
  token farm. 63 tokens in ~2.5 days (ChatGPT 16, Google Gemini 10, Grok 9, MrBeast 8, SpaceX, NVIDIA, YouTube…), each from a
  fresh creator wallet and graduated in its first slot. In that same slot it buys ~1 SOL on PumpSwap, always in a tx
  co-signed with 4G9JAzft…, which buys exactly 132,479,379 tokens every time. Sells 1–90 min later, then sweeps the SOL out.
  Not a strategy we can copy; outsiders are its exit liquidity.
- GKd5EMzR (F9 scalper, ~0.28 SOL, ~6 s holds, costs ~0.00014 SOL per round trip; +1.4 to +4.2 SOL per 6 h since 10-23 18h).
  Replay (ops/strategies/gkd5/gk1_replay.py, owner "can we try it?"):
  - Its own buy moments with any simple exit: about break-even at its speed (15 ms) and fee (R3 best +1.1 SOL/day), negative
    at our 35 ms (R3 −6 to −17), and −25 to −45 SOL/day at our fee.
  - Generic copy rule (any ≥0.5 SOL trade, token ≥1 min old, curve 37–79): −50 to −1,800 SOL/day.
  - Its profit (+10 SOL on R3) is again in its exits. Not copyable.
  - Lesson: cost per round trip. Our ~0.0035 vs bots' 0.00014–0.0004. For our dip bot, ~0.0015 (one tip per landed tx via a
    durable-nonce fan-out, as top bots do) would add ~+10% in replay terms if landing speed holds — engineering proposal, needs
    the owner's OK.
