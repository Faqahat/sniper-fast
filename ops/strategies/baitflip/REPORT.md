# Bait-flip study (owner strategy, 2026-10-25)

Strategy: our buy → more buyers → SELL + BUY in the same bundle (fake dump) → dip bots buy the "dump" → sell into them.
Data: raw recordings R1–R3 (Oct 21–24, ~72 h), extracted trade tables. Offline only, nothing sent.

## 1. Nobody does it on chain
- 1.1M sells ≥0.2 SOL; tight same-wallet sell→buy in one bundle (same slot, adjacent, nothing between): **53**, mostly insider
  launch ladders + 13 small haqqiUUX trims. No real examples to copy → measured through a proxy.

## 2. Proxy = dump instantly "restored" by a same-slot buy (looks the same on chain)
18.2k cases (sell ≥0.5 SOL, next trade a buy putting price back within −1.5%..+2%), matched against ordinary moments on the
same kind of token (age, curve SOL, trades / buy SOL / price change in the last 20 slots). `b2_proxy.py`, `b4_match.py`.
- All cases: lift at +4 slots only **+0.25–0.4%**, ≈ **+0.1 extra dip-bot buy** per event. Bait cost = 2.5% of bait size
  (pump fee both sides) + ~0.0015 → **negative vs just holding at every position up to 5 SOL**.
- Dip bots' failed buys (price guard / spare copies) are 58% after restored dumps vs 68% after plain dumps → restoring the
  price does not make them fail more (`b5_fails.py`). But they buy only ~4% of plain dumps: they are picky.

## 3. Where it does work (stable on all 3 days)
`b6_slice.py`, `b7_oos.py` — rule **curve < 40 SOL AND price fell >10% in the last 20 slots**:

| day | n | lift | P&L per bait vs hold, pos 1 / 2 / 3 SOL |
|---|---|---|---|
| R1 | 495 | +2.67% | +0.006 / +0.033 / +0.060 |
| R2 | 755 | +2.83% | +0.007 / +0.035 / +0.063 |
| R3 | 830 | +2.59% | +0.005 / +0.031 / +0.056 |

Median trade is ~break-even at 1 SOL, positive at ≥2 SOL. Exit = end of slot +4.

**After a run-up (price up in the last 20 slots) — which is where the diagram puts the bait — lift is −0.2..+0.1%: it loses.**

## Caveats (why this is not proven)
- Proxy, not our bait: real restored dumps are dumps a fast bot chose; part of the lift may be that information, which a fake
  dump does not carry. Only a probe can measure bots' response to OUR bait.
- Same signer selling and buying in one bundle is easy for bots to filter → may need two wallets.
- Needs us to already hold ≥2 SOL on a small (<40 SOL) curve that has just fallen — not the usual state after our buy.
- R4 (Oct 24–25) not yet extracted → a fresh forward check is the next free step.

# Part 2 — a bait strategy that does work (2026-10-25)
Owner: "find a profitable strategy same like this which can work". Same idea (make the bots buy into us), but the bait
is a BUY by us on a quiet token, not a fake dump. Rules were frozen 10-24 ~15:35 PKT (patterns study); today's
recording R5 (10-24 19:25 → 10-25 ~15:00 PKT, ~21 h) was never seen by them. Replay engine patterns/p4_eval.py
(our curve, follower slippage limits, pump fee 1.25%/side + 0.0035/round trip, one position at a time). `b10_fwd.py`.

FRESH = only baits that are the wallet's FIRST trade IN THAT TOKEN (`w_first`; correction 10-25: NOT the wallet's first
trade of the day — that test is `b9_fresh.py`: 1st bait of the day 73% followed vs 56–65% for active wallets).

| Rule (frozen) | R1 | R2 | R3 | **R5 forward** |
|---|---|---|---|---|
| Young-token bait [291]: token 6–25 s old, paused ≥2 s, curve ≤45, buy 0.9–2 SOL; exit +8% / −8% / 60 slots / into B345 or big sell — FRESH | +30.8 (406, win 68%) | +32.3 (573, 63%) | +28.5 (734, 62%) | **+22.9 (484, win 64%, +0.047/trade, median +0.031)** |
| Quiet-token bait [336]: token ≥32 s, quiet ≥8 s, curve ≤40, buy 0.75–3 SOL; exit +8% / −6% / 120 slots / into B301 — FRESH | +45.8 (1,262) | +84.5 (1,821) | +99.0 (1,963) | **+39.3 (1,403, win 50%, +0.028/trade, median ≈0)** |
| Small young bait [370] 0.5–1 SOL — FRESH | +11.6 | +12.0 | +11.3 | **+9.9 (476, win 61%)** |

## Repeat-baiter decay (KEY risk, `b8_repeat.py`, `b9_fresh.py`)
Follower bots stop answering a wallet that baits repeatedly:

| k-th bait of the wallet that day | follower ≤1 slot R1–R3 | R5 |
|---|---|---|
| 1st | 67% | 61% |
| 2–5 | 55% | 43% |
| 6–20 | 42% | 24% |
| 21+ | 7% | 2% |

The wallet's other trading barely matters (first bait 56–73% whatever its history) → **one fresh wallet per bait
(or per ~2)**. The big repeat baiters (o41P5ecz ~100/day) get ~5% followers and make nothing.

## Not proven
- Replay uses other people's baits as stand-ins; they choose the tokens (maybe with off-chain reasons). Fresh-wallet
  baits remove wallet reputation, not token choice. Only a live probe shows the follower rate on OUR picks.
- Crowding: our baits share the same followers with ~4,800 baits/day.
- Forward day is weaker than R2/R3 on the quiet bait (+0.028 vs +0.046/trade); young bait held.
- Fake-dump flip (part 1) only fits as a possible second leg when a quiet bait gets no follower (small curve, price
  falling): proxy only, untested.
