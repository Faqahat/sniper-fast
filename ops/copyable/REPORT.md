# COPYABLE SNIPER HUNT — is there a profitable pump.fun/memecoin wallet we can copy-trade at 1-2 slot lag?

Date: 2026-10-15. Baseline-uncopyable reference: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`
RPC: constantk. Workspace: /root/copyable. Builds on /root/caller (co-buyer cohort), /root/last500, /root/econ_102.

## TL;DR VERDICT
**No robustly-copyable profitable wallet was confirmed.** Every wallet that is *both* profitable *and* on-chain-confirmed falls into one of two uncopyable classes:
1. **Ultra-short-hold floor-flippers** (median hold 1-7 s): `4yFAz`, `dKM…`, `9qz…`, `AMD…`, `BXB…`, `G8g…`. Huge raw PnL, but per-trade edge is tiny (median R 0.97-1.03). Copying them at our realistic 1-2 slot lag + priority fee turns every one **−EV equal-weight** (copy mean R −0.005 to −0.02).
2. **Size-weighted / discretionary wallets**: `milito`, `dKM` show big SOL totals (+39.5, +65 SOL) but that comes from *sizing up the winners*. Equal-weight copying (what a copy-bot does) is −EV (milito copy tot −2.95 R over 141 positions).

The **only** wallet with the right *copyable shape* — **Fox `DAEdBmTPEKM6xkwfzC3d411QUe6coKpkND6UURa4CvHC`** (median hold ~22 min, lag multiplier only 1.155, copy mean +0.85 R in-sample) — has just **14 closed positions over 2.3 days, and its entire +EV is carried by one 13.69× runner**. Drop that single position and copy-EV falls to +0.08 R; drop the top 2 and it goes **negative** (−0.155 R). So Fox is the right *direction* but the evidence is far too thin and tail-dependent to call a confident edge.

**Implication:** profitable pump.fun trading is structurally hard to copy. The reproducible edges are same-slot floor races (we can't match the fill at lag — exactly the 4yFAz problem) or discretionary sizing/selection (we can't mirror by copying buys). The lag-tolerant swing profile does exist (Fox) but is rare, low-frequency, and tail-driven; it needs a far larger sample before it's worth capital.

---

## METHOD
- **Candidates (STEP 1):** web leaderboards (kolscan.io, MadeOnSol) → ~25 named "smart money"/KOL addresses; on-chain co-buyer cohort of 4yFAz's 409 recent picks (/root/caller) → top 5 co-snipers. 20 addresses characterized + 4yFAz baseline.
- **Characterization (STEP 2):** `wallet_tape.py` pulls each wallet's recent signatures, parses every swap via **balance-delta accounting** (venue-agnostic: pump bonding-curve, pumpSwap, Raydium, Jupiter, Meteora, Orca; native-lamport Δ + WSOL Δ for SOL side), FIFO-pairs buys/sells per mint → realized PnL, win%, median hold, median R, trades/day. (Two parser fixes were essential: broaden beyond pump-only programs, and set `maxSupportedTransactionVersion:1` — the biggest names use v1/lookup-table txs and were silently dropped at first.)
- **Copy-ability (STEP 3):** `copy_sim.py` measures the **empirical lag multiplier** per wallet — for a sample of its buys, fetch blocks at buy_slot+1/+2, read the real price print on that mint, `lag_mult = price_lag / their_entry` (1.0 = price didn't move = no competition). Copy net R = their realized R / lag_mult − 1 − priority drag, mirroring the wallet's own exit. Equal-weight (what a copy-bot does).

## CANDIDATE TABLE (on-chain confirmed, recent tape)
| name | wallet | nClosed | realizedPnL SOL | win | medHold | medR | tpd | class |
|---|---|---|---|---|---|---|---|---|
| cohort2 (leads 4yFAz) | dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK | 319 | +65.4 | 43% | 1.5 s | 0.986 | 815 | floor-flip |
| milito (kolscan) | EeXvxkcGqMDZeTaVeawzxm9mbzZwqDUMmfG3bF7uzumH | 141 | +39.6 | 38% | 55 s | 0.949 | 1251 | hi-freq |
| cohort3 (leads 4yFAz) | 9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw | 77 | +9.9 | 56% | 5 s | 1.021 | 1138 | floor-flip |
| 4yFAz (baseline) | 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3 | 47 | +7.9 | 60% | 2 s | 1.025 | 203 | floor-flip |
| cohort1 | AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg | 533 | +6.0 | 31% | 7 s | 0.974 | 632 | floor-flip |
| cohort4 | BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL | 504 | +5.3 | 42% | 1 s | 0.984 | 390 | floor-flip |
| cohort5 | G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh | 330 | +2.4 | 32% | 1 s | 0.965 | 1360 | floor-flip |
| Fox (kolscan) | DAEdBmTPEKM6xkwfzC3d411QUe6coKpkND6UURa4CvHC | 14 | +0.6 | 57% | 1304 s (22 min) | 1.072 | 34 | swing |
| Scharo (madeonsol) | 4sAUSQFdvWRBxR8UoLBYbw8CcXuwXWxnN8pXa4mtm5nU | 47 | −0.5 | 28% | 33 s | 0.822 | 121 | loser |
| EustazZ (kolscan) | FqamE7xrahg7FEWoByrx1o8SeyHt44rpmE6ZQfT7zrve | 53 | −1.9 | 19% | 25 s | 0.909 | 51 | loser |

**Unusable web addresses (flagged, excluded):** Marcell `Fixm…`, Killua `95TW…` = token-transfer/distribution wallets (Token/ATA/System only, no swaps). Goyim `G3gZ…`, dv `BCag…`, Jijo `4Bdk…`, LUKEY `DjM7…`, Limfork `BQVz…` = ~0 parseable swaps (wrong address, inactive, or non-standard). **Cented `CyaE…` (+2560 SOL claim), decu `4vw5…`, Cupsey `2fg5…`, theo `Bi4r…`** = trade through a **custom bot program (`DhpyNWkd…`) holding positions in program PDAs, not the wallet's ATAs**, mixed with failed-spray txs — not characterizable or copyable as wallet-swap mirrors, and structurally fast snipers/MEV. → **~93% of web "smart money" leaderboard names were survivorship/mislabeled/un-copyable**, matching the Dune finding that most top wallets are bots.

## COPY-SIMULATION RESULTS (copy_results.json; SIZE 0.5 SOL, mirror their exit, 1-2 slot lag)
| wallet | medLag | fracBuysMoved>5% | THEIR mean R | COPY mean R | COPY tot R (n) |
|---|---|---|---|---|---|
| Fox | 1.155 | 0.60 | +1.139 | +0.851 | +11.92 (14) |
| milito | 1.000 | 0.20 | −0.019 | −0.021 | −2.95 (141) |
| 4yFAz | 1.091 | 0.53 | +0.071 | −0.020 | −0.93 (47) |
| dKM (+65 SOL) | 1.056 | 0.50 | +0.052 | −0.005 | −1.74 (319) |

- **Lag tolerance is real and measurable.** Fox's medLag 1.155 (we enter ~16% above Fox) vs the floor-racers whose tiny per-trade edge is wiped by lag+fees. The lag penalty is NOT the killer for floor-flippers here (their medLag is only ~1.05-1.09 on their realized tape) — the killer is that their per-trade edge (medR ≈ 1.0) is razor-thin, so any friction flips it −EV.
- **Fox fragility (robustness check):** copy mean +0.851 R all-in → **+0.082 R excl. top-1 winner → −0.155 R excl. top-2**. One 13.69× (18-hr hold) + one 4.53× carry the entire result; the other 12 positions are net slightly negative. Also carries real drawdown (one −17 SOL position: bought 27.8 SOL, exited 10.7).

## WHY FOX IS THE RIGHT *SHAPE* (even if unproven)
Fox is a genuine position/swing trader: enters with real size (median 6.7 SOL, range 2-28), holds p25/med/p75 = 6 min / 22 min / 2 hr (one 18 hr), and profits from a couple of multi-× runners paying for many small losers. Because it does **not** floor-race, a 1-2 slot copy lag costs only ~16% of entry — negligible against a 22-minute, potentially-10× hold. That is precisely the lag-tolerant mechanism the hunt was looking for. The problem is purely statistical: 14 positions in 2.3 days is not enough to establish that the runner-rate is a repeatable edge rather than luck.

## RECOMMENDATION
1. **Do NOT deploy a copy-bot on any wallet found here as-is.** The floor-flippers are −EV to copy (confirmed, the 4yFAz problem generalizes); the big-SOL wallets rely on sizing we can't mirror; Fox is unproven.
2. **If pursuing the copyable-swing thesis (best lead):** harvest a *cohort* of Fox-shaped wallets (filter: median hold > 5 min, real size, lag_mult < 1.3, >50 closed positions) and pool them. A copy edge only matters if the aggregate runner-capture is robust across ≥100+ positions. Copy strategy: mirror their buys (lag-safe), and hold through for the tail (their own exit, or a wide trailing stop) — do NOT use a tight 3-s flip exit, which throws away the only thing that makes them +EV.
3. Fox-type wallets trade ~6 positions/day — a copy program would need several of them for usable frequency.

## FILES
- /root/copyable/REPORT.md (this)
- /root/copyable/candidates.json — full characterization table (21 wallets)
- /root/copyable/copy_results.json — lag + copy-EV for Fox, milito, 4yFAz, dKM
- /root/copyable/tapes/*.json — per-wallet trade tapes & positions
- /root/copyable/copyres/*.json — per-wallet copy-sim detail (incl. lag_detail)
- /root/copyable/wallet_tape.py, copy_sim.py, agg.py — reusable tooling

## CAVEATS / HONESTY
- Samples are recent tape only (constantk RPC window; 100-1600 sigs/wallet, ~hours-to-days). PnL is realized round-trips in that window, not lifetime.
- Copy-sim uses a single median lag multiplier per wallet and mirrors the wallet's own exit; it does not model our fill *probability* at lag (we assume we land), tip wars, or partial fills — so it is an optimistic upper bound on copy-EV. Even so, all floor-flippers are −EV.
- Fox n=14 is too small for inference; its result is flagged throughout as tail-dependent, not confirmed.
- Web leaderboard PnL claims were NOT reproducible on-chain for the mega-names (custom-program/PDA structure) — treat all leaderboard numbers as unverified.
