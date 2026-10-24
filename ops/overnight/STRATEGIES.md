# Strategy registry: 2026-10-23 (times PKT, UTC+5)

> ## CURRENT STATUS (15:16 PKT): read this first. Owner's summary page: `report/DECISION.html`
> **Nothing makes money at our ~75 ms landing.** The owner's own 24 h paper engine agrees: first in line +11.9 vs at 74 ms +0.11 over 267 paper trades.
>
> **Best candidate: dip-backrun** (learned from census wallet HkQ7hMjy). Buy 0.5 SOL right after a ≥1 SOL sell on a launch aged 1–120 s when the GBDT scores it in the top 5%; sell 2–4 slots later.
> - **Independently checked** (`verify_dip/VERIFY_DIP.md`): reproduced exactly, no look-ahead. At REAL latency (28.6 h of data, 0.0008 SOL per tx):
>
> | Real latency | 20 ms | 35 ms | 50 ms | 75 ms |
> |---|---|---|---|---|
> | Dip-backrun | +14.6 … +18.0 | **+9.6 … +11.3** (walk-forward +5 … +6) | +1.9 … +2.5 | −6.8 … −6.2 |
>
> - **Confirmed** with 13,294 real decoded follower limits.
> - **Shorter holds plus a 2% guard widen the window:** a 2-slot exit with the guard gives +9.3 at replay "50 ms" (≈ real 43 ms).
> - **Expect** ≈ 7–8 SOL/day at a real 35 ms.
> - **Frozen models:** DIP 10:34 / 10:47, DIP4 10:52, DIP2 12:09 PKT. Forward: `dip/fwd_dip.log` via `dip/fwd_dip_loop5.sh`. The first 1.2–1.5 h are positive at 20–35 ms.
> - **Plan:** `ops/dip/PLAN.md`. Daily retrain: `dip/dip_retrain.sh`. Rust core `src/dip.rs` (parity 218/218).
>
> **Afternoon (13:13 PKT), details in `ops/dip/PLAN.md`:**
> - **Tighter version:** spacing 5 slots, 2-slot exit. "35 ms" +30.6, "50 ms" +16.9; "75 ms" with the 2% guard +7.3 (all 6 blocks positive).
>   - The checker reproduced "50 ms" exactly (+16.84; with our own trades applied in sequence +17.35); its real-latency correction is pending (`verify_dip/`).
> - **Engine visibility:** 76% of pump trades are routed (not readable from shreds), but the model's picks are 57–71% direct sells, carrying 74–86% of P&L.
>   - Direct-only: "35 ms" +22.5, "50 ms" +13.9, "75 ms" +4.4 / guard +6.3; top 5% of direct sells at "75 ms" +4.8 unguarded, 6/6 blocks.
>   - Engine v1 = trigger from shreds (3 pump sell layouts), history from the executed feed.
> - **With REAL follower limits (13:45 PKT, ~18,700 more decoded):** direct-only "35 ms" +20.1 (6/6), "50 ms" +11.1 (6/6), "75 ms" +3.5 / guard +5.5 per ~33.5 h, in REPLAY units (block position, the same units as HkQ7hMjy's 39 ms).
> - **Independent check (14:03 PKT, `verify_dip/VERIFY_DIRECT.md`):**
>   - holds in replay units; at a REAL 35 ms it expects ≈ +10…+13 per 33 h; my convolution with its measured timing errors gives +16–17, so ≈ 8–12 SOL/day (first forward hours are midday, matching yesterday's midday rate; the 2% guard is now required because 29% of direct sells fail on chain);
>   - v1 txs are 12% of direct triggers;
>   - HkQ7hMjy's routed delay is ~2–5 ms, not 8;
>   - 2 vs 4-slot exit is a tie;
>   - my dip census double-counted buys (corrected: pros +190 SOL net / 33 h, 79% positive, skill persists).
> - **HkQ7hMjy sends** plain direct pump buys, one service per leader client: Nozomi on BAM / Harmonic, Helius on Jito-client (29 ms), Nozomi or no tip on Firedancer. Tip 0.001 SOL.
>
> - **Forward red flag (15:14 PKT; real limits 15:18):** since 12:09, direct picks −0.14 / 51 and routed +0.49 / 66; all picks +0.35 (guard +0.42) in 2.9 h of midday. The engine takes both trigger kinds (direct from shreds, routed from the executed feed), guarded.
>
> **FINAL-2:** corrected (verify2/).
> - Overnight 75 ms +1.07; daytime clean tail −0.48.
> - The daytime forward test (08:26 → now, 67 picks) loses at EVERY landing, even 20 ms (−0.9). Overnight-only at best.
>
> **Who pays us (important):** both strategies profit from ~540 consistently profitable bots buying after us.
> - Remove their later buys and both lose; remove the 9 pros, the 321 snipers, or 541 random active wallets instead and both stay positive.
> - It is a speed race inside that bot group. The owner decides whether it fits "become them" (memory `profit-source-bot-cohort`).
>
> **Speed fix:** probably config only (one route per leader client): single-route probes landed 17–34 ms on 10-21, multi-route 73–148 ms.
> - Owner-run check: `ops/final2/probe_speed.sh` (≤0.25 SOL, fail-by-design; stop the paper engine first).
> - Then `ops/final2/probe_to_pnl.py` gives the expected dip SOL/day per route.
>
> **Owner's OK needed:** the probe; any paper or live run; a collector restart (the current run ends **20:43 PKT today**).
>
> **Rejected today:**
> - copying census winners; generic dips; whale-follow;
> - hot-token dips; next-slot (top-of-block) dips; wider dip triggers;
> - a time-of-day filter; the wave-stop exit;
> - models on our own 45 / 75 ms snipe outcomes; cohort features; dips on FINAL-2 launches.
> - (afternoon) long / take-profit / ride-with-pro dip exits; PumpSwap (graduated) dip-backrun (instant bounce, ≈0 at 35–75 ms); FLASHX8 triggers in v1 (help only at 35 ms).

> **Update 08:30 PKT. The owner's direction changed.** The goal is to *become* the pros, not beat or front-run them. S4 and its family make money by buying first on deployers the case-study bots follow, then selling into those bots' buys. That is front-running them, so the S4 family is **no longer a target** (kept below for the owner's manual check). New strategies must make money from general flow and pass three tests:
> - **Follower slippage:** a buyer our buy would push past its own limit is dropped. Limits are decoded from 34k real transactions, and the check matches the chain's logged outcome exactly.
> - **Pros removed:** the 9 shared wallets are deleted from history, or their buys after our entry are deleted.
> - **Snipers removed:** all buys by 321 sniper wallets after our entry are deleted.
>
> Every candidate is frozen (`dryrun/frozen_generic.json`, sha256 7b519784…, 08:26 PKT) and scored on launches created after the freeze (`core/fwd_generic.py`).

## S4 with real follower slippage (measured 08:20 PKT)
Applying each follower's real slippage limit lowers S4 at 75 ms, 0.5 SOL, with every failed attempt counted:

| Variant | Old period, before → with slippage | Replay period, before → with slippage |
|---|---|---|
| S4 | +0.88 → **−0.32** | +4.01 → **+2.80** |
| S4 + gate | +1.67 → +0.43 | +4.31 → +3.17 |
| S4 + gate + 1 SOL sizing | +1.92 → +0.12 | +7.03 → +2.82 |

Sizing up no longer helps, because bigger buys price out more followers. **The exit flag was also wrong:** the replay's exit is `--hold-slots 2`, not 1 (fixed in `ops/s4/s4_flags.sh`).

**Live check, our 5 real PROD fills** (`live/LIVE_TAPES.md`):
- zero outside trades between our buy and our sell in all 5;
- on 8HSxaXd3, our 1.48 SOL buy priced out the only two followers;
- S4's list would have skipped 4 of the 5, and its guard would have cancelled the 5th.

> **Live path built (not deployed):** `ops/final2/PLAN.md`. The engine flag `--final2-sock` asks our FINAL-2 scorer at the bundle close (answer in 0.85 ms); sell at about 8 s with `--hold-ms 7700`. Needs the owner's OK for a server paper run, the landing probe and an FRZ test.

## Summary 08:42 PKT
**Blueprint:** `BECOME_THEM.md`.

**Best candidate:** FINAL-2 picks (our own model), first after the bundle (0.5% guard), sell at 8–10 s.
- Positive in every robustness variant.
- Strongly speed-dependent. 45 ms, 8 s:

| Variant | Result |
|---|---|
| With follower slippage | +4.24 |
| Pros' later buys removed | +2.70 |
| All sniper buys after us removed | +1.97 |

- At 75 ms the first half is flat.
- It matches how dK (+77 SOL/day) and CW (+5.9/day) actually make money.
- Later entries, rules or models, do not work.

**Forward test:** frozen 08:26 / 08:33 / 08:46 PKT; `core/fwd_generic.py`.

**Second period, corrected (09:30 PKT).** The earlier table used mostly in-sample R1 picks. The clean R1 tail (14:58–18:00 PKT, 3 h daytime, small) with pros' later buys removed, CW-style cost:

| Window | 75 ms | 45 ms | 30 ms |
|---|---|---|---|
| R1 clean tail (daytime) | −0.31 | −0.50 | +0.13 |
| R2 overnight (out of sample) | +2.38 | +3.44 | +5.25 |

- **Confidence: Low–Medium**, overnight only for now.
- The "wave stopped" exit does not replicate on the offline picks.

## GDM: our own demand model, added to FINAL-2 (`gdm/RESULTS.md`, frozen FRZ-GDM-U 09:10 PKT)
- **Model:** a 5-seed bagged GBDT trained to predict at least 10 ordinary buyers 2–10 s after the create. Its strongest inputs are deployer history (how much ordinary buying the deployer's earlier launches drew), market cap after the bundle, and dev+bundle SOL.
- **Rule:** buy if FINAL-2 OR GDM picks the launch, with the same mechanics (first after the bundle, sell at 8 s).

| R2 out of sample, 45 ms, 8 s, pro costs | FINAL-2 OR GDM | FINAL-2 alone |
|---|---|---|
| Pros' later buys removed | +8.17 | +4.82 |
| All sniper buys removed | +6.73 | +3.72 |
| Without the best 5 fills | +2.14 | −0.62 |

- **R1:** ahead in 16 of 18 settings. On FINAL-2's clean R1 slice (14:58–18:00 PKT) it makes +0.17 vs −0.40 at 8 s, and +1.11 vs 0.00 at 10 s.
- **Caveat for live use:** the main GDM model uses token metadata (X / website / description) that the engine cannot have at bundle close.
  - The no-metadata model L is mixed: R2 union +7.10 vs +4.64, but R1 union +2.87 vs +3.11 (single seed).
  - The gain depends on the deployer-demand history features, which a live system would have to compute.
- **Status:** phase 2, after FINAL-2. Forward test hourly (`gdm/fwd/fwd_gdm.sh`, `dryrun/fwd_gdm_loop.log`).
- **Pre-freeze check, 10:00 PKT:** on unseen 05:35–09:10 PKT launches (45 ms, 8 s, pros' later buys removed), GDM −0.58 (LM) / −0.95 (L) and the union −0.56, against **FINAL-2 alone +0.79**. GDM hurt there.
- **Confidence: Low.** FINAL-2 alone stays the candidate.

## Track A: "become them" at snipe time (our own selection: FINAL-2's live picks)
Window: 23:31–08:16 PKT, 235 picks. 0.5 SOL, 0.5% price guard, 2% buy overhead, 0.005 per failed buy. All columns use a 10 s hold.

| Landing | Real history | + slippage | Pro buys after us removed + slippage | Pros removed from history + slippage | All sniper/pro buys after us removed |
|---|---|---|---|---|---|
| 75 ms (92 fills) | +3.02 | +2.53 | +1.81 | +2.96 | +1.43 |
| 45 ms (134 fills) | +4.37 | +3.77 | +2.35 | +4.65 | +1.67 |

**Exits** (75 ms, with slippage):

| Exit | Result |
|---|---|
| End of the next slot | −0.27 |
| 1 s | +0.67 |
| 5 s | +2.02 |
| 8 s | +2.46 |
| 10 s | +2.53 |
| 20 s | +0.83 |
| 30 s | +0.69 |

- **Better variant (A1):** sell at the end of the next slot if at most 1 buyer came after us, otherwise hold 10 s. +3.12, halves +0.74 / +2.38.
- **Weakness, fat tail:** the median fill is about −2% and about 40% of fills win. Without the best 5 fills the total is about −0.3 to −0.9.
- **By hour:** 7 of 9 PKT hours positive.
- **The dump veto is essential:**
  - the top 5% by score without the veto is negative;
  - the top 1% is weak;
  - the top 2% at 8 s is positive (+1.65 with pro buys after us removed, + slippage).

**Confidence: Low–Medium.** One 8 h window, and the exit was chosen after seeing the data. Forward test running (A1, A2, A3 in frozen_generic.json). Live use needs the FINAL-2 model inside the engine; today it is only a Python shadow.

## Track B: later entries on general flow (cheap send, no race)
- **Baseline:** 110,789 decision points (1–180 s after the create), realistic costs (pump fees, 0.0002 SOL per tx, fill after ~0.42 s latency). Every time and exit is negative: −3% for a quick hold, −13% to −18% at 300 s.
- **Search:** 1–2 condition rules, positive in both periods. 19 rules have min(R1, R2) ≥ +4% per trade on 40–130 trades each. Patterns:
  - after a selling wave with little active-bot buying (12–20 s, hold up to 2 min);
  - small launches (market cap ≤ ~30 SOL) with 20+ unique buyers;
  - after the pros have sold;
  - many tiny buys in the first second.
- **Multiple testing:** these came from scanning thousands of rules. A shuffled-outcome null test is running. 12 rules are frozen (B1–B12) for the forward test.
- **Model check (08:42 PKT):** a GBDT per entry time, trained on one period and tested on the other.
  - AUC about 0.70, but 0 of 247 settings are positive in both directions.
  - On FINAL-2's own picks, entering at 1–12 s loses at every hold.
  - **Verdict: later entries are not a strategy for us.** The forward test continues only for completeness.
- **Confidence: Low** until the forward test.


## Earlier (overnight) registry: S4 family, now not a target

Every strategy tested overnight, with its measured result. Nothing here was traded.

**Common conditions** unless noted:
- buy 0.5 SOL;
- costs: pump fees, 2% buy overhead, 0.0005 SOL per sell, a 1.5% worse fill than the model, and 0.005 SOL per failed guarded buy;
- "replay" = 10-22 17:09 → 10-23 00:34 UTC (7.4 h) with our real place in line (block-order placement, verifier-matched);
- "old" = 10-21 22:07 → 10-22 07:00 UTC (14.8 h) with a landing proxy that is pessimistic at 60–75 ms;
- "dry" = forward data after each rule was frozen.

## Recommended for the live test

Confidence levels:
- **High** = verified replay, old data and forward dry run all positive, plus live proof (none yet).
- **Med-High** = verified replay, old data positive, dry run positive so far.
- **Medium** = positive in both periods, walk-forward, but untested forward or extra engine work needed.
- **Low** = one period only, or a weak margin.

| ID | Rule | 75 ms replay | 75 ms old | 45 ms replay | Status | Confidence |
|---|---|---|---|---|---|---|
| **S4** | 9Sh2fd/DGmspi deployer list (≥2 attempts, ≥10% of the deployer's launches, walk-forward) + 1% price guard + sell at the end of the next slot | **+4.01** (86/269 fills) | +0.88 | +5.85 | Frozen 01:10. Dry run so far +0.7 to +0.8 SOL at 75 ms in its first ~1.2 h. | **Med-High** |
| **S4G** | S4 + quality gate (skip a deployer whose own simulated fills average below 0 after ≥3) | +4.31 | +1.67 | +6.26 | Frozen 02:24. List file `dryrun/deployer_list_gated.txt`. | **Med-High** |
| **S4G_1SOL** | S4G with every buy at 1.0 SOL (one fixed size, no engine change) | **+9.11** | +4.40 | +12.79 | Frozen 02:46. 1 SOL stress: +6.0 if case wallets fail after us, +2.0 if 30% of followers also vanish. | **Medium** |
| S4GM | S4G with 1.0 SOL when the market cap after the bundle is ≥36 SOL, else 0.5 (learned from dKMjeGJ4's sizing) | +7.61 | +3.41 | +10.91 | Frozen 02:46. Needs per-launch sizing in the engine. | Medium |
| S4GSM | S4G with 1.0 when (good own history) or (MC ≥36), else 0.5 | +8.57 | +3.70 | +12.31 | Frozen 02:46. Needs per-launch sizing. | Medium |
| S4GS | S4G + 1 SOL on deployers with ≥3 fills averaging ≥ +0.02 | +7.03 | +1.92 | +11.00 | Frozen 02:24. Needs a per-deployer size change in the engine (templates); not built. | Medium |

**Notes:**
- **Guard refinement:** a 0.5% guard instead of 1% is slightly better in both periods. At 75 ms: replay +4.07 vs +4.01, old +1.18 vs +0.88. When even a small buy got in first, those fills lose on average (−0.02 each). The proposed flags now use `--slip-cap-bps 50`.
- **Landing curve for S4** (replay): 30 ms +10.2 · 45 +5.9 · 60 +4.8 · 75 +4.0 · 90 +3.3 · 110 +2.8 · 130 +1.8 · 160 −0.5.
- **Risk** (S4, 75 ms): worst single trade −0.030 SOL; max drawdown −0.20 SOL.
- **Stress** (S4, 75 ms; the first value is at 0.5 SOL, the second at 1 SOL):
  - case wallets fail after us: +2.7 / +6.0;
  - plus 30% of other followers vanish: +0.6 / +2.0.

## Backups (positive but weaker or less tested)

| ID | Rule | Result |
|---|---|---|
| MULTI_GS | Lists from 7 snipers + gate + size | 75 ms: replay +6.89, old +1.32. 45 ms: replay +14.0, old +10.7. Frozen 02:24. |
| S4G+AUTO | S4G plus deployers whose own simulated history is good (no copying needed) | 75 ms: replay +4.14, old +1.70. With size: +6.75 / +2.20. |
| AUTO | Only our own per-deployer history, no copying at all | 75 ms: replay +2.18, old +0.11. 45 ms: +5.32 / +2.59. Survives if the copied wallets stop. |
| FINAL-2 + guard | The earlier token-quality model's top 1–2% picks with the price guard | 75 ms: +1.5 to +1.7. Without the guard: −1.3 to +0.4. |
| Frozen list | S4 list frozen 10–29 h earlier, no updates | +3.3 to +3.6 at 75 ms. The list lasts at least a day. |

## Tested and rejected (measured)

| Idea | Result |
|---|---|
| Any selection without the price guard at 75 ms | All launches −127; S4 picks +0.25 (eos1) / −1.55 (1 s hold). |
| Copy-trading the case wallets' visible buys (enter after their tx) | Loses at every delay of 30–150 ms (−3 to −10 SOL). |
| Partial-sell ladders and TWAP exits on our entries, including DGmspi's exact WORLD ladder | All worse than one quick sell; WORLD ladder −1.11 at 75 ms. |
| Longer holds (5 / 10 / 30 s), trailing stops | Worse everywhere. |
| Random lists of 92 serial deployers with the guard | −3.8 to −0.4 (all 20 negative). |
| Lists of other snipers without a gate (7-wallet union) | −9.5 (old) / −0.1 (replay). |
| Following the "picker" wallets (2maW7x2X, 4Yy3xBZn, retAumPG, HnFPB3iA, FYHggFuZ, 6Kj5ChEZ, FeCAXCyH, A21wCG8H, 3yrJE1A8, 5g8bviwg): buy right after their buy, hold 10 s to 2 min or mirror their first sell | Loses in both periods for almost all of them. Their picks look great at our place (+12 to +38 SOL), but that is look-ahead: they choose 1+ s after the create using the first second of trading. |
| S4G only on big launches at 0.5 SOL | +3.0 (replay) / +0.9 (old) at 75 ms. Weaker than taking all S4G picks. |
| AHwJSnFN list (S5) | Replay +2.6 at 75 ms, old −4.1; dry run flat. |
| Non-SOL-quoted curves (PUMP / USDC / others) with S4 rules | −0.9 (replay) / −0.4 (old) at 75 ms. Not worth engine support. |
| **"Good deployer" lists from ordinary-buyer demand only** (walk-forward: deployers whose earlier launches drew ≥10 ordinary buyers in 2–10 s, 4 thresholds; 10-23) | −4 to −23 SOL per period at 45/75 ms in every variant. Deployer history only helps combined with launch features (as in GDM). **Rejected.** |
| **Fill predictor to skip likely-failed sends** (AUC 0.76 on all launches; 10-23) | On FINAL-2's picks it removes good fills along with the fails; the total does not improve. **Rejected.** |
| **Non-SOL-quoted curves, full study** (`nonsol/RESULTS.md`, 10-23) | A flat round trip costs ~6.6% of size (fees + 2 swap legs + creator fees up to 3%); 53–55% of our fills get no buyer within 8 s. No selection: about −75 SOL per period. A demand model has AUC 0.83 but its top picks don't pay robustly; one weak rule is frozen for paper only (NONSOL-1). **Rejected for live.** |
| Skipping deployers we rarely fill on | Worse in both periods. |
| Contest-rate filter (skip deployers usually sniped fast) | Worse. |
| Momentum-extended exit (hold while net buying continues) | Same as the plain quick sell (+4.07 vs +4.01). |

## Still open (agents running)

Full dissections of four successful wallets the owner shared: FiFawH, dKMjeGJ4, CWiNFAEk, 9qz7cWBq (`ops/overnight/<wallet>/`). Goal: turn their tricks (selection, landing, sizing, exits) into new strategies and test them the same way.
