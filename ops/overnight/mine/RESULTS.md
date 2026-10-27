# Pattern mine (ML) on pump.fun bonding curves, 10-25, read-only
Data: 513,883 trade moments (every trade ≥ 0.3 SOL, token age ≤ 15 min) on R2 + R3, plus 52,882 on R4 (live recording, 4.1 h).
41 features known at that moment: flow, price changes, buyers, curve level, dev, bundle, wallet reputation (earlier days only), tweet launcher.
Label: 1 SOL buy landing 75 ms later, held 1 / 3 / 10 / 30 s; fees 1.25%/side + 0.0015 SOL/tx; followers kept (optimistic) and, at 3 s, followers in 2 slots dropped (pessimistic).
Train R2 (last 20% = validation), test R3 (24 h) and R4 (4.1 h); one position per token at a time.
Scripts: build.py, r4build.py, fit.py (fit_0–3.txt), fit_filters.py (ff_*.txt), rules.py.

- **Buy every moment:** −3% per trade (1 s), −5% (3 s), −9% (10 s), −16% (30 s), the same on both test days.
- **Models rank moments** (AUC 0.65–0.73), but top picks only break even or lose after fees.
  - Best: 1 s model, top 0.5%: R3 +6.3 SOL / 1,036 trades (+0.6%), R4 +3.5 / 308 (+1.2%), optimistic only.
  - At 3 s it is negative, and the pessimistic labels are −3% to −5% per trade.
  - Its picks are hot-flow moments: 24 SOL bought in the last 15 s (vs 6), 24 buyers in 5 s (vs 4), 0.02 s since the last trade, curve ~55 SOL, price rising.
- **10 filter-specific models** (after sell / after buy / young / older / winner bought / big trigger / quiet gap / tweet tokens / curve 30–45 / curve 45–80): all negative or unstable.
  - The only one positive on both test days: curve 45–80 SOL, top 1%, 10 s hold — +4.0 and +1.6 SOL on small samples, negative in validation.
- **Simple rules from the model's favourite moments** (hot flow): ≈ 0 to negative on the test days.
- **Verdict:** at 75 ms landing, no robust profitable pattern in 41 features × 10 subsets × 4 holds. The pattern that ranks best (hot flow, 1 s) needs followers to keep filling after us.

## Update: results by landing time, with REALISTIC follower limits (labels_real.py, fit_real.py → fr_*.txt)
Followers within 2 slots after our buy keep their own slippage limit: the decoded limit where known (77k buys), otherwise a draw from the measured distribution for their size. About 22% of follower SOL fails at a +5% price move; 32% of followers set no limit.

Train R2, test R3 (24 h) and R4 (4.1 h, per-day rate). 1 SOL, 1 s hold, top 1% model picks, realistic labels:

| Landing | VAL / day | R3 / day | R4 / day | Per trade | Win |
|---|---|---|---|---|---|
| 10 ms | +89 | **+104** | +122 | +5.4% | 71% |
| 20 ms | +65 | **+84** | +95 | +4.5% | 65% |
| 35 ms | +34 | **+45** | +56 | +2.5% | 56% |
| 50 ms | +4 | +8 | −6 | ≈ 0 | — |
| 75 ms | −27 | −48 | −57 | −2% | — |

- **3 s hold:** 10 ms ≈ +54/day, 20 ms ≈ +37, 35 ms ≈ 0.
- **Robustness (top 1%, 1 s hold):**
  - 20 ms: R3 1,872 trades on 1,659 tokens, best 5 tokens = +5 of +84, positive in 23 of 24 PKT hours, median trade +2.3%.
  - 35 ms: positive in 18 of 24 hours, median trade ≈ 0.
- **Picks** = "hot flow" moments: about 24 SOL bought in the last 15 s, ~24 buyers in 5 s, trades every ~0.02 s, curve ~55 SOL, price rising.
- **Reading:** a real out-of-sample edge exists for landing ≤ 35 ms (strong at ≤ 20 ms); it disappears by 50 ms.
