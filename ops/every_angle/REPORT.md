# EVERY_ANGLE — remaining-hypothesis sweep on 4yFAz…EQrG3

Target picks (his tape): 200 trades, 189 with outcomes. Chronological OOS split by create_slot
(IS = first half, OOS = second half). Universe = /root/profit_backtest (1141 creates, 883 with
reconstructed price path). Window ≈ 23.8h (2026-10-13 10:17 → 10-14 10:03 UTC).
"pump" = peak ≥ 1.5× (and ≥ 2.0× shown). All lifts reported OOS unless noted.

## VERDICT TABLE

| # | Hypothesis | Pre-buy? | OOS verdict | Number |
|---|------------|----------|-------------|--------|
| 1 | Smart-money co-sniper CONSENSUS (recurring good co-buyers predict pump) | yes (within-slot) | **NO** | ≥1 "smart" co-buyer → realR +0.017..+0.030 vs 0-smart +0.070..+0.084 (worse) |
| 2 | Dev FUNDING-GRAPH cluster (common funder of creators) | yes | **NO** | 118 funders / 146 creators; top cluster=15% of picks; in-cluster OOS peak 1.258 vs 1.234, wr 0.50 vs 0.56 |
| 3 | Token METADATA / SOCIALS (twitter/tg/web/img/name) | yes | **NO** | his socials ≈ universe (tw .91/.88, web .65/.60, img 1.0/1.0); name/sym-len corr flips sign IS→OOS |
| 4 | TIME-OF-DAY / session / BURST | yes (calendar) | **NO** | only 23.8h span; burst(≤150 slots) realR +0.047 vs +0.082; recent-5-hitrate→next R corr −0.16 |
| 5 | EARLY-FLOW first 1-3 slots (co-snipers, inflow, buyers) | **mixed** | **NO (pre-buy); scale-in only** | his slot-0 & slots0-3 bands: no persistent runner band OOS. Universe bands strong but contemporaneous |
| 6 | BUY-SIZE as CONVICTION (his size → outcome) | n/a | **NO** | corr(sol_in,peak) IS +0.23 → OOS −0.03; realR OOS −0.18; tercile lift IS +0.21 → OOS −0.05 |
| 7a | LAUNCHPAD CONFIG filter (mayhem / holder_reward / fee) | yes | **YES (selectivity, pre-buy)** — but variance/trade-count only, NOT mean-R | mayhem==1: his **1%** vs universe **38%**; holder_reward: his 46% vs 12%; fee>0: his 0% vs 6% |
| 7b | DEPLOYER / uri-host fingerprint (which tool deployed) | yes | **YES (selectivity co-signal)** — R-neutral | j7tracker .21 vs .12, uxento .11 vs .03 (3-4×), plain ipfs.io .57 vs .77 |
| 7c | Intertrade MOMENTUM / size-up-after-win | n/a | **NO** | realR after-win +0.070 vs after-loss +0.089; size identical (2.49/2.49); no streak effect |

## THE PRIZE (selectivity, 24%→1%)

**Launch-config + deployer-tool filter is the strongest pre-buy-knowable explainer of his extreme
selectivity** — and it is 100% observable in the create instruction (same slot, before his +1 entry):

- **mayhem==1 → he essentially never trades it (1% of his picks vs 38% of all launches).**
  Avoiding "mayhem-mode" launches alone removes ~38% of the pool. This is the single biggest
  selectivity differentiator found.
- **He strongly prefers holder_reward launches (46% vs 12%)** and **never takes creator-fee launches
  (0% vs 6%).**
- His metadata is deployed via pro terminals (j7tracker 21%, uxento 11% — 3-4× the universe), not
  the plain pump.fun web client — a correlated fingerprint of the same "clean launch type" filter.

**But does acting on it raise mean R? NO — it is a trade-count / variance win, not alpha:**
- In the universe, mayhem==1 has ~zero effect on pump rate (IS 0.163 vs 0.197, OOS 0.137 vs 0.117 —
  a wash). So the mayhem filter is **R-neutral**: it removes ~38% of trades without changing EV.
- holder_reward==1 in the universe is actually a **persistent mild NEGATIVE** (pump rate −0.05 to
  −0.07) — i.e. the flag he *prefers* selects marginally worse tokens by the universe stat; within
  his own picks hr=1 vs 0 is a wash/slightly worse (OOS wr 0.50 vs 0.58).

=> This filter plausibly explains the mechanical 24%→1% tightening (he only fires on a narrow,
clean launch archetype), and it cuts trade count and variance, but it does **not** lift mean R.

## BANDED BLOCK-STRUCTURE (owner addendum) — runner vs dump

Universe, OOS pump≥1.5 rate by band (persistent IS→OOS unless noted):

- **Co-sniper count over the trade window:** 0→0.258, 1-2→0.491, 3-5→0.525, 6-10→0.667 (monotonic, persistent).
- **# trades over window:** 1-5→0.106, 6-15→0.315, 16-40→0.457, 41+→0.846 (monotonic, persistent).
- **Early-trade-count slots 0-3:** 0-1→0.270, 2-4→0.226, 5-9→0.480, 10-20→0.778 (persistent).
- **Early price-return by slot+3:** <1.0→0.235, 1.0-1.3→0.237, 1.3-2→0.678, 2+→1.000 (persistent).

These are **real, persistent runner bands — but CONTEMPORANEOUS / look-ahead**: a token showing high
early flow/return is already being pumped. For a create+1 sniper these are not a pre-buy ENTRY filter;
at best a **scale-in / hold-longer trigger** fired in the slots just after entry.

**On HIS own picks none of these bands separate runners OOS** (his slot-0 co-sniper/inflow/distinct-
buyer bands and slots-0-3 bands all wash out IS→OOS; IS 6+ co-snipers 0.33 → OOS 0.07). He is almost
always the early flow himself (median he's in at create+1 on low-early-flow tokens), so early-flow
cannot differentiate within his already-homogeneous set, and he does **not** select on it.
Scale-in on his own tape did not lift realized R (his exits are already short: realR by slots-0-3
buy band 0-2→+0.049, 3-6→+0.069, 7-15→+0.048).

## BOTTOM LINE

No additional **mean-R on-chain alpha** was found — consistent with the mirror's finding that
selection carries ~no R alpha given same-slot entry. The one genuine, pre-buy-knowable mechanism
behind his selectivity is a **launch-type filter (avoid mayhem, prefer holder_reward/clean deployer
tools)**: it explains the 24%→1% tightening and is a **variance / trade-count reducer**, not an
edge in expected R. The strong banded runner signals (early flow / early return) are
contemporaneous and only actionable as a post-entry scale-in, which did not help on his tape.
