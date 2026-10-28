# HAQQ DISSECT — shared brief for every analyst agent (10-28 ~02:30 PKT)

## The owner's challenge (his words, condensed)
> haqq makes ~30 SOL/day, we make ~3.5. We already established haqq is mostly BEHIND us on the same trades (slower), and our
> selection is already decent. So "we are slow" or "he trades more but it doesn't work for us" are NOT acceptable answers.
> He buys a single token multiple times far more often than us; most of his multi-buy tokens give him more reward; sometimes
> he buys in multiples and sells in multiples. He doesn't spam txs like our pre-send, but still lands.
> Yesterday evening (10-27 ~18:00–22:00 PKT), while our run was losing, his GMGN went from $1.5k to $2.5k.
> Dissect his system, find what we are missing, and give a plan that works — proven on replays and paper.
> Act like analysts: prove every claim with numbers. Resolve contradictions with data; don't hide behind them.

GMGN screenshots from the owner (10-28 ~01:40 PKT, last ~25 min of haqq tokens):
- **Multi-buy tokens won:** cheems 8 buys/8 sells +$137 (+41%), DOCKE 3/3 +$77 (+65%), ChaCha 3/3 +$14 (+12%, held 1 s).
- **1/1 tokens mostly lost small,** −0.1% to −15%. One DOCKE 1/1 lost −38.7% (held 11 s).
- **His txs** go through his own program (haqqqMGN35ehCftXca3KWxJFXTBcWTWeNHNtUHLGQdh) with a TradeV3 / BuyExactQuoteInV3 instruction, plus setLoadedAccountsDataSizeLimit, plus a 0.0002 SOL Helius tip.
- **Wallet:** about 38 SOL balance; ~0.33–0.56 SOL per tx. It was funded by HKVWNV…dZrx1j (an address that funded 334k accounts — likely an exchange).

## What is already MEASURED (don't re-derive unless you doubt it; if you find it wrong, say so with numbers)

**haqq (24 h, 10-26 23:15 → 10-27 23:15)**
- +28.1 SOL net from 5,691 lots (≈0.4 SOL each); tx cost 0.78 mSOL per lot; 7.5% of his txs fail.

| Type | Lots | Net SOL |
|---|---|---|
| DIP | 2,158 | +15.5 |
| ADD | 1,684 | +6.4 |
| DIP_LATE | 402 | +2.3 |
| DEAD | 472 | +2.2 |
| LAUNCH | 152 | +1.6 |
| MOMO | 119 | −0.2 |
| OTHER | 408 | +0.5 |

- **Positions:** 1.44 buys per position; 28% of positions have adds; 25% of lots sold in more than one piece.
- **Open positions:** 5.4 at a time (time-weighted mean), p90 11.
- **Hold vs result:**

| Hold | Lots | Net SOL |
|---|---|---|
| < 2 s | 1,370 | +25.6 |
| 2–15 s | ~3,000 | ≈ 0 |
| 15–60 s | 593 (mostly ADD) | +10.9 |
| > 5 min | 357 (mostly DEAD) | −12.5 |

- **DIP lots by position after the dump:** first buyer after the dump +5.9 SOL (594 lots); 1+ buyers ahead +9.6 (1,564 lots). So he profits even when NOT first.
- **His limits are loose:** about 57% of his buys have no effective price limit (guard-sweep study, 10-25).
- **Data:** ops/strategies/haqq_strat/ (s1–s9, hs_lib.py), data /home/moiz/sniper-data/haqq_strat/ (lots24.pkl, pos.pkl, haqq_raw.jsonl = his raw txs 24 h, s3.txt dissection).

**Speed (MEASURED)**
- His DIP buys land a median 77–80 ms after the dump (52% in the same slot).
- Our regular fires land a median 49–55 ms after the dump; pre-send fills 29 ms.
- On dumps where both of us landed a buy, we were first 80–96% of the time.
- He runs in EU + US-East (equally fast on both); US-East leaders give 25% of his profit at 2.5× his EU per-buy rate. Scratch: scratchpad/main/hq_region/.

**Our live engine (MEASURED, 1,546 regular fires, AMS r9–r33 + FRA r1–r26)**
- Landed 99.9%; fill only 38.6% (the rest fail our +5% price guard = error 6042).
- Fill by outside trades landing ahead of us:

| Trades ahead | 0 | 1 | 2–3 | 4–7 | 8+ |
|---|---|---|---|---|---|
| Fill | 100% | 78% | 29% | 15% | 17% |

- **Costs:** 4.16 mSOL per fill including failed fires (3.5 per fill + 0.53 per failed fire).
- **Pre-send:** the earner (AMS 10-27 +3.7 SOL); it spams k tries per slot and costs 5,120 lamports per failed try.
- **Our P&L per day (wallet, all costs):** 10-24 +0.55, 10-25 −0.17, 10-26 +1.28, 10-27 +3.18.
- **haqq on OUR events (24 h):**
  - our regular fills: his lots there −27 mSOL/lot;
  - our failed regular fires: +2.6/lot;
  - our pre-send fills: +13.4/lot;
  - our failed pre-sends: −8.9/lot.

**Replay machinery that is VALIDATED (reuse it; don't rebuild)**
- ops/strategies/dv8/ (REPORT.md; dv8lib.py, dv8sim.py):
  - exact bonding-curve replay (later sells keep their token amounts; on our 595 live fills it reproduces live to +0.02 mSOL/fill);
  - contention-aware landing model (rank_model.json, our position drawn from the live distribution of trades ahead given the crowd);
  - calibration live ≈ 0.61 × model − 1.17 mSOL/fire;
  - coverage per hour (c0_coverage.txt);
  - mayhem tokens must be EXCLUDED (their curve is not standard; the replay invents fake profit on them).
- **Tape:** /home/moiz/sniper-data/dv8/tab/ (trades.npy 21.9 M pump.fun trades with signer, 10-22 03:07 → 10-28 01:12 PKT; ids.json; creates.json with mayhem flags; ours.jsonl = our txs).
- **Raw recordings with full txs (incl. failed):** /home/moiz/sniper-data/collect/run_*/txs/*.jsonl.gz. More arrive every ~30 min (keeper). Decoders: ops/strategies/presend/real/decode.py, build.py.
- **Live run records:**
  - AMS: /home/moiz/sniper-data/runs/ams/runs/, presend_filter/live28/, haqq_strat/live/;
  - FRA: /home/moiz/sniper-data/runs/fra/runs/, dv8/live/ (FRA r26 copy).

**A finding the owner rejects as incomplete:** DV8 (buy many dumps with our +5% guard, one buy per token, fixed exit) loses at our landing. It never modelled adds/multi-buys, loose limits, or haqq's exit logic. Those are exactly what you must now study.

## Rules (strict)
- **Read-only research.** Nothing is sent. No engine, config or server change. Live engine FRA r26 is running: servers read-only via `ssh -p 1996 it@84.32.100.36 'sudo cat …'` only if you must.
- **No Constant-K RPC key** (live engines use it). If you need chain reads, prefer the recordings. Public RPC only, rate-limited, short.
- **Your own folders only:**
  - code: /home/moiz/sniper/ops/strategies/haqq_dissect/<your_tag>/
  - data: /home/moiz/sniper-data/haqq_dissect/<your_tag>/
  - scratch: /tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_<your_tag>/

  NEVER bulk-delete anything outside them. The scratchpad is shared with other agents.
- **Limits:** container disk ~78%, so keep your data ≤ 10 GB. Use ≤ 3 CPU processes (5 agents run in parallel).
- **Labels:** times in PKT; label every number MEASURED or INFERRED. Multi-day wherever the data allows (10-22 → now); show per day.
- **Write tables to *.txt in your data folder.** The harness may block REPORT.md writes, so put the full report in your final reply.
- **Prove, don't assert.** For every claim give the count, the effect, a 90% bootstrap range, and whether it holds on every day. If a result contradicts an earlier finding, name it and explain the difference with numbers.
- **Causality:** for anything we could trade on, use only information available at decision time (no lookahead). Say exactly what the engine would need to see.
