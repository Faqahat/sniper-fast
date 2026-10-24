# Become them: what the profitable bots do, and what it would take for us

> **STATUS 2026-10-23 11:05 PKT. Read `report/DECISION.html` first.**
> - FINAL-2's numbers below are pre-correction: an independent check found 3 replay bugs in our favour (`verify2/VERIFY_FINAL2.md`).
> - The forward test 08:26–10:53 PKT is negative at every landing.
> - New lead: the dip-backrun (`ops/dip/PLAN.md`). Positive in all 6 time blocks at 20–50 ms (≈22 / 14 / 8 SOL/day); about 0 at today's 75 ms.


2026-10-23, times in PKT (UTC+5). Research only. Nothing here was traded. Numbers are **MEASURED** (chain or replay) unless marked **INFERRED**.

## The owner's rule
Don't beat or front-run the case-study bots; **become them**. Our profit must come from general flow (ordinary bots and people), not from landing just ahead of a specific bot and selling into its buy.

Every strategy here is scored three ways.

- **Follower slippage.** A buyer that our own buy would push past its slippage limit is dropped.
  - The limits come from 34k real transactions.
  - The check reproduces the chain's logged outcome exactly.
- **Pros removed.** The 9 shared wallets' buys after our entry are deleted, or the wallets are removed from history entirely.
- **Snipers removed.** All buys by 321 fast-sniper wallets after our entry are deleted.

## 1. What the three dissected bots really make (ground truth from their ledgers)

| Wallet | Profit | Speed | Selection | Exit | Size | Landing cost |
|---|---|---|---|---|---|---|
| [dKMjeGJ4](https://gmgn.ai/sol/address/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK) | **+197 SOL / 61 h (+77/day)**; still +117 without its best 10 tokens | 42 ms median, first after the bundle on 65% | own create-time rules: new deployers, a 2–20 SOL dev bundle, a website, an idle creator | on a clock: half at ~1.7 s, then pieces at ~4/6/9/12 s | 1.8–12 SOL | 2.4% |
| [CWiNFAEk](https://gmgn.ai/sol/address/CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J) | **+14.9 SOL / 61 h (+5.9/day)** | 49 ms median | "hot devs" (J7Tracker/Uxento launches, 3-wallet bundle) | ~1.5 s; at once if the dev sells; take-profit at ~1.4× | always 1 SOL | 0.6% (0.003 priority + 0.003 tip) |
| [9qz7cWBq](https://gmgn.ai/sol/address/9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw) | **+406 SOL / 61 h** | snipes 35 ms, but **its snipes lose (−11.9)** | later entries into live buy waves | fixed ladder every 2–3 s up to ~20 s | **2–35 SOL** | 2.8–4.8% |

**Shared toolkit:**
- durable nonces;
- each buy signed once per landing service, so only one copy can land;
- v1 transactions and seeded token accounts;
- their own router programs;
- no bot fee.

**What they share that we can copy, and what we can't:**
- **dK and CW:** first after the bundle on picks that attract general buying, then hold through the 2–12 s wave.
  - CW's picks are up a median 1.048× at +10 s even with every fast bot removed, versus 0.945× for comparable launches it skipped.
  - dK's picks attract about 2× the generic buying.
- **9qz7cW:** its edge is size. A 10+ SOL buy into a live wave triggers momentum followers. That doesn't work at our size.
- **Copying any of their trades or lists fails the owner's rule.** dK: +6.2 → −2.6 SOL. CW: +1.8 → −1.9. 9qz7cW: +4.2 → −1.9. Each pair is "as replayed" vs "with fast-sniper buys after us removed", at 75 ms.

## 2. Our version: FINAL-2 picks + first after the bundle + sell at 8–10 s

- **Selection:** FINAL-2, our own model. It scores every launch at bundle close (61 public features, dump veto, guards) and copies nobody.
- **Live picks:** 235 (23:31 → 08:16 PKT, after its training data).
- **Trade:** 0.5 SOL; 0.5% price guard, so it fills only when first after the dev's bundle; 2% buy overhead; a failed buy costs 0.005 SOL.

| Landing | Fills | With follower slippage, 8 s | Pros' later buys removed, 8 s | All sniper buys after us removed, 8 s | Halves (slippage) | Without the top 5 (slippage) |
|---|---|---|---|---|---|---|
| 75 ms (ours today) | 92 | +2.46 | +1.72 | +1.30 | +0.5 / +2.0 | −1.30 |
| 45 ms | 134 | **+4.24** | **+2.70** | +1.97 | +2.2 / +2.0 | −1.14 |
| 30 ms | 170 | +6.91 | +4.44 | +3.22 | +3.9 / +3.0 | **+1.15** |
| 20 ms | 204 | +7.92 (10 s) | +5.14 (10 s) | +3.41 (10 s) | — | +2.74 (10 s) |

- **Exits:**
  - The quick sell at the end of the next slot (Run 2's exit) loses once the bots are removed (−1.5 to −1.7).
  - 8–10 s is best. 5 s and 15 s are a bit lower; 20–30 s fall off.
  - Take-profit caps, dev-sell exits, dK's piece ladder and CW's 1.5 s exit all do worse on our entries.
- **Price guard:** strict is best for us. 5% is about equal; 10–30% loses, because we'd buy behind the snipers.
- **Size:** 1 SOL gives more but less than twice as much (+4.4 vs +2.5 at 75 ms), and is less robust.
- **Comparison:** this is about as good as CW's own picks under the same test (+2.50 at 75 ms, 10 s). That's a decent sign that FINAL-2's selection is competitive.
- **Weaknesses:**
  - Fat-tailed: the median fill is about −2% and about 40% win.
  - One 8-hour window (US daytime hours). I chose the exit on the same window.
  - **Confidence: Low–Medium.** Forward test frozen at 08:26 / 08:33 PKT (`dryrun/frozen_generic*.json`).

**Scaled view (INFERRED):**
- at 45 ms and 0.5 SOL, about +8 to +12 SOL/day;
- at 30 ms, about +13 to +20 SOL/day, the owner's goal range;
- dK's real result scaled to 0.5 SOL is about +11 SOL/day, the same order of magnitude.

## 2b. CORRECTION: second period (10-23 ~09:30 PKT, MEASURED)
> **An earlier version of this section was wrong.** It said "positive in both periods". The "R1" picks it used started at 08:24 PKT 10-22, but FINAL-2 was trained on R1's first 80%, up to **14:47 PKT**. So 158 of those 224 picks were **in-sample** (the model had seen them), which inflated the daytime results. Corrected below with only the truly out-of-sample R1 tail (14:47–18:00 PKT).

FINAL-2 + 8 s hold, 0.5 SOL. Results are "today's costs / CW-style costs" (CW-style = 1.2% at 0.5 SOL, 0.003 per failed buy):

| Window | Landing | Fills | With slippage | Pros' later buys removed | All sniper buys removed |
|---|---|---|---|---|---|
| **R1 out-of-sample tail**, 10-22 14:47–18:00 PKT (3 h daytime, 66 picks, old-data placement) | 75 ms | 21 | −0.40 / −0.22 | −0.48 / −0.31 | −0.81 / −0.63 |
| | 45 ms | 28 | −0.47 / −0.29 | −0.68 / −0.50 | −1.07 / −0.88 |
| | 30 ms | 41 | +0.25 / +0.46 | −0.09 / +0.13 | −0.81 / −0.59 |
| **R2**, 10-22 23:31 → 10-23 08:16 PKT (8.3 h overnight, 235 live picks, real timelines) | 75 ms | 92 | +2.46 / +3.12 | +1.72 / +2.38 | +1.30 / +1.95 |
| | 45 ms | 134 | +4.24 / +4.97 | +2.70 / +3.44 | +1.97 / +2.71 |
| | 30 ms | 170 | +6.91 / +7.72 | +4.44 / +5.25 | +3.22 / +4.03 |

- **Overnight PKT (US hours):** clearly positive in every variant.
- **Daytime PKT:** the only clean sample is small (21–41 fills) and negative at 45–75 ms, about flat at 30 ms.
- **Why daytime may look worse than it is** (MEASURED): market-wide buying after launches is normal at 14:00–18:00 PKT. The clean R1 tail has 18–20 distinct outside buyers per launch in the first 60 s vs 18–25 overnight. Only 10:00–13:00 PKT is thinner (13–17). The R1 tail also has to use the old-data position proxy, which is pessimistic at 45–75 ms. So **daytime is unproven, not shown negative.**
- **So the strategy is, for now, an overnight-PKT strategy.** The forward test (frozen 08:26 PKT, running hourly, real timelines) is collecting daytime data to settle it.
- **On the same windows** (MEASURED): the older demand model `frozen_live3_good`, top 2%, is weaker than FINAL-2 overnight (+0.5 to +2.0) and also flat in the daytime tail. Picks chosen by *both* models lose. FINAL-2 alone stays the choice.
- **The "wave stopped" exit** does not replicate on the offline picks. Primary exit: a plain 8–10 s hold.
- **Confidence: Low–Medium.** One solid out-of-sample window (overnight); daytime unproven and possibly negative.

## 3. What did not work (measured)
- **Later entries (1–180 s after the create, cheap send, no race):**
  - Every time and exit is negative on average.
  - Rule search: as good as shuffled-outcome nulls rule by rule, though more good rules than chance as a family.
  - Models: 0 of 247 settings positive in both time directions.
  - On FINAL-2's own picks, entering at 1–12 s loses at every hold. By then the move is gone.
- **S4 (copied dev lists, quick sell):** front-running, now off-target. With slippage it is −0.32 (R1) / +2.80 (R2).
- **A model trained directly on our 75 ms outcomes:** ranks well (AUC 0.77) but doesn't beat FINAL-2. At 75 ms we only fill where no fast sniper wanted in, and 89% of those fills lose.

## 4. What it would take (each step needs the owner's OK where marked)
1. **Landing speed to ≤45 ms, ideally ~30 ms** (*send-path change: owner's OK*).
   - Durable-nonce fan-out: one signed copy per service, a small tip each, one nonce so only one lands. This is what dK, CW, 9Sh2fd and 9qz7cW all do.
   - First a probe from the dev wallet: buy-shaped txs that fail by design, costing only priority fees. This measures our real landing per service.
   - Target cost: CW pays 0.6%; dK pays 2.4% (Jito ~3% tips).
2. **FINAL-2 inside the engine at bundle close.**
   - Today it is a Python sidecar (2–50 ms behind), too slow.
   - Plan (INFERRED effort, about half a day):
     - port the GBDT (399 trees, simple JSON) to Rust;
     - compute the launch features in the engine;
     - read the history features (creator, bundle wallets, name, dump speed) from a table that the Python scorer refreshes every few seconds, like the deployer-list file.
3. **Exit:** `--hold-ms 8000` (exists today).
4. **Guard:** `--slip-cap-bps 50` (exists).
5. **Live test plan:** FRZ at 0.5 SOL, capped (e.g. 15 buys, −0.3 SOL max loss), in the evening or night PKT (US hours). After the run, check each live fill against the replay with `core/verify_live.py`.

## Files
- Dissections:
  - `dkmjeg/REPORT_dKMjeG.md`
  - `cwinfa/REPORT_CWiNFA.md`
  - `q9z/REPORT_9qz7cW.md`
  - FiFawH still running (`fifaw/`)
- Become-them test: `core/become_eval.py` (variants), `core/become_sum.py`.
- Follower slippage:
  - `core/slip_fetch.py` + `slip_args.jsonl`;
  - check against chain: `live/LIVE_TAPES.md`.
- Later-entry study: `core/gf_*.py` (stage 1/2, search, null runs, models).
- Forward test: `core/fwd_generic.py` → `dryrun/forward_generic.txt`.
