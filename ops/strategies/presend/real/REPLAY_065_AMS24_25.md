# AMS runs 24 + 25 replayed at 0.50 / 0.65 / 1.00 SOL (agent, 10-27 PKT)

Owner request 10-27 ~06:15 PKT: "replay (not scale) the Amsterdam 24, Amsterdam 25 with scaled size of 0.65 for both pre-send
and non". Later additions: the engine's paper next to live, the no-trade fills (hindsight), and 0.50 / 1.00 SOL.
Read-only. Nothing was sent, and no engine, script or config was touched. The server was only read: `sudo cat` of the run
files after the engine had stopped (md5 checked), plus read-only RPC (`getTransaction` for the other wallets' trades,
`getBalance` for the wallet).
MEASURED = live records, chain, or wallet. INFERRED = replay. Times are PKT.

## Short answer (phone)
P&L per run and type, in SOL, as the engine books it (rent of the pre-send token accounts not yet back):

| Run / type | Fills | Live (MEASURED) | Replay at live size | 0.50 | **0.65** | 1.00 |
|---|---|---|---|---|---|---|
| r24 pre-send | 200 | +0.977 (103 wins) | +0.977 | +1.419 | **+1.658** (103 wins) | +1.770 |
| r24 regular | 37 | +0.548 (18) | +0.548 | +0.778 | **+1.011** (19) | +1.317 |
| r25 pre-send | 95 | +0.952 (60) | +0.952 | +1.456 | **+1.859** (59) | +2.314 |
| r25 regular | 13 | +0.106 (5) | +0.106 | +0.125 | **+0.162** (5) | +0.230 |
| **Wallet r24** (21:47-02:57) | | **+1.692** | +1.692 | +2.363 | **+2.835** | +3.254 |
| **Wallet r25** (02:58-06:09) | | **+1.137** | +1.137 | +1.660 | **+2.100** | +2.624 |
| **Wallet both** | | **+2.829** | +2.829 | +4.023 | **+4.936** | +5.878 |
- Wallet rows = all trades + token-account rent back - failed-try fees (failed pre-send tries and failed regular buys;
  both stay as live). Live wallet: 1.8040 -> 3.4964 -> 4.6331 SOL (chain, read 06:40 PKT).
- All other columns are INFERRED. No fill is lost at any size, and no failed try would have filled.
- **Validation: PASS.** At the live sizes the replay gives back every one of 345 trades to the lamport.
- **20% fewer later buyers:**

  | | Live size | 0.50 | 0.65 | 1.00 |
  |---|---|---|---|---|
  | r24 pre-send | -0.10 | -0.02 | **-0.09** | **-0.61** |
  | r25 pre-send | +0.31 | +0.55 | +0.70 | +0.67 |
  | r24 regular | +0.15 | +0.25 | +0.33 | +0.39 |
  | r25 regular | -0.02 | -0.05 | -0.06 | -0.10 |
- **What size costs:**
  - Our own price impact costs little.
  - The big cost is the later buyers our bigger buy prices out (their own signed slippage). At 0.65, 69 of their buys fail,
    which costs about 1.2 SOL against "everything grows with size".
  - At 1.00 that is 134 failed buys. Pre-send per fill then grows only from +0.0119 (0.65) to +0.0138 (1.00).
  - At 1.00, r24's first segment would have hit the 0.5 SOL kill switch (low point -0.61 SOL vs its start).

## 1. What was replayed (method)
- **Every live fill at its actual chain spot**: 295 pre-send fills, 50 regular fills. Both come from the engine records and
  the 24/7 raw recording (keeper copy, 10-26 21:30 to 06:16 PKT, complete and with no gaps except skipped slots).
- **Entry at size S** uses pump's own integer math, checked on the chain tape:
  - SOL budget -> net SOL n: the largest n with n + ceil fees <= S;
  - tokens = t·(n-1) / (v+n-1), the formula of buy_exact_quote_in, which matched 55k of the recorded buys;
  - sells: v·q / (t+q), with fees ceil(a·bps/10^4) per component.
- **Our buy limit is checked again at S** with the engine's exact formula:
  - pre-send: `limit_min_out` at the attempt's own signing state, x0.88, fee rate of the trade it had last seen;
  - regular: the guard, the post-dump quote / 1.05.
- **Every later trade of the token is replayed in chain order with its own decoded limit.** The limits come from
  `getTransaction`: 4,112 transactions, all fetched.
  - Quote buys keep their SOL, get fewer tokens, and fail below their min-out.
  - Exact-token buys pay more and fail above their max cost.
  - Sells fail below their min SOL out.
  - Cascade: a failed buy is removed, and the same wallet's later sell shrinks by the tokens it never got.
  - Failed sells with pump's TooLittleSolReceived (6003) are tried again on the new state. 1 passes, after our sell.
- **Which follower limits our size can break** is MEASURED from the decoded numbers. For each limit I looked for the curve
  state on which its slippage is a round number (2 %, 4 %, 5 %, 6 %, 10 %, the 1/1.04 form, or exactly 0).

  | Group | Follower buys before our sell (pre-send / regular) | What the replay does |
  |---|---|---|
  | Quoted on the crash state, before our buy (in flight with us) | 202 / 49 | Limit fixed; our bigger buy eats more of their slippage |
  | Quoted after seeing our buy, or a program that sets the limit at execution | 413 / 278 | Limit moves with us; never fails because of our size |
  | No round match | 464 / 137 | Treated as fixed |

  - This rule was added **after** the first 0.65 run, which held every decoded limit fixed (the literal method). Both are
    shown in section 3.
- **Exits as the engine does them, on the replayed state:**
  - pre-send: TP +10 % / SL -20 % on each later trade the engine had received before its time exit, then entry slot + 2;
  - regular: SL -50 % (TP is off), then hold 5.
  - If the exit decision is the live one, the sell lands at the live sell's chain spot. Otherwise it lands at the decision
    plus the median live delay: 58 ms after a TP/SL trigger, or 111 ms into slot entry + 2 for a time exit.
- **Costs stay as live**: fees, tips, priority, token-account rent and close fee. Failed tries keep their live fees.

## 2. Validation, run first at the live sizes (0.34 pre-send / 0.35 regular)
| Check (MEASURED vs replay) | Pre-send | Regular |
|---|---|---|
| Our tokens and net SOL in, exact | 295 / 295 | 50 / 50 |
| Our limit recomputed = the logged min_out | 295 / 295 | 50 / 50 |
| Exit reason and trigger trade = live | 295 / 295 (63 TP/SL triggers found to 1e-9) | 50 / 50 |
| Per-trade P&L error | 0 lamports on all 295 | 0 on all 50 |
| Totals r24 / r25 | +0.9775 / +0.9518 = live | +0.5480 / +0.1057 = live |
| Followers that would wrongly fail before our sell | 0 | 0 |
- **Pass rule (±10 % or ±0.05 SOL per type per run, small per-trade median): PASS** on every line.
- **First run, written down:** 1 of 295 pre-send exits differed.
  - HZi3fcn6, r24 22:23: the replay sold at SL on 3 sells the engine had received 0.7-1.1 ms before its time exit but had
    not processed yet. Error +0.0072 SOL, still a pass.
  - Fixed by one rule: trades received in the last 2 ms before a time exit are not checked. After that every trade matches.
- **Wallet reconciliation** (MEASURED, per engine start): r24 segments -0.00215 / +0.56472 / 0 / +1.12982, r25 +1.13672.
  - Components: realized + rent back (1,508,820 lamports per fill) - failed-try fees (including 1,058 tries the engine
    logged as unseen but which landed) - failed regular buys.
  - They explain each segment to within 0.00014 SOL.
- **What this proves, and what it does not:**
  - At the live size the chain sequence is unchanged, so this checks the mechanics: math, limits, exits, costs and the
    record-to-chain joins.
  - The counterfactual part (which followers fail at a bigger size) cannot be checked against live: no fill above 0.40 SOL
    has ever been made.

## 3. Where the size goes (0.65, both runs; INFERRED)
| | Pre-send (295 fills) | Regular (50 fills) |
|---|---|---|
| Live | +1.929 | +0.654 |
| If gross P&L grew with size (fixed costs not scaled), reference only | +4.636 | +1.347 |
| Own price impact only (followers forced to fill, live exits) | +4.506 (-0.13) | +1.307 (-0.04) |
| + later buyers priced out by their own limits | +3.409 (**-1.10**) | +1.173 (-0.13) |
| + the engine's exit rule at 0.65 (= main) | **+3.517** (+0.11) | **+1.173** (0) |
| Literal method: every decoded limit fixed | +3.253 | +1.097 |
| Unclear-quote followers in later slots re-quote | +3.771 | +1.221 |
| CPI followers never fail | +3.524 | +1.222 |
- **Entry:** at 0.65 we pay a median 0.81 % more per token than at 0.34 on pre-send (p10-p90 0.63-0.93 %), and 0.6 % more on
  regular.
- **Followers priced out** (buys before our sell that fail): pre-send 24 / 56 / 110 at 0.50 / 0.65 / 1.00; regular 8 / 13 / 24.
  - They are mostly in-flight dip buyers in our own slot, with 0.2-1.8 % of slippage left after our live buy.
  - Example EK4vvi (r24): one 3.95 SOL buy priced out takes the trade from +0.578 to +0.428 at 0.65.
- **Exits:**
  - 5 take-profits become time exits at 0.65, and 14 at 1.00, because our own buy raises our cost basis.
  - No new stop-loss.
  - The net effect is small and positive here.
- **Fills lost:**
  - pre-send: none at any size. The limit is a price limit; 27,318 price-failed tries still fail at 1.00.
  - regular: none. 68 guard failures still fail at 1.00; the guard loosens by only ~0.01 % with size.

## 4. Paper (engine shadow) vs live, pre-send, on one basis
- Paper = the shadow's own fills and model, re-computed at 0.34 and 0.65. My port reproduces all 1,817 logged paper exits at
  0.55 SOL exactly.
- Same per-fill costs as live: 2.015 mSOL per fill, rent back. Paper has no failed tries; live paid 0.108 (r24) and 0.053
  (r25) SOL of them.
- Only windows armed while live pre-send was on: r24 21:53-23:30 and 00:10-02:23, r25 02:58-06:09.

**(a) All paper fills vs all live fills** (SOL):

| | Fills | At 0.34 | At 0.65 |
|---|---|---|---|
| r24 live (MEASURED / replay) | 200 | +1.279 | +1.960 |
| r24 paper row a (0 ms) | 375 | +3.945 | +6.786 |
| r24 paper row c (10 ms) | 324 | +1.705 | +2.714 |
| r25 live | 95 | +1.095 | +2.002 |
| r25 paper row a | 190 | +2.673 | +4.402 |
| r25 paper row c | 162 | +2.083 | +3.446 |
- The engine's own logged paper (0.55 SOL, its cheap cost row): r24 row a +6.291 / row c +2.786; r25 +4.114 / +3.235.

**(b) Only windows both filled, per fill** (row a):

| | Windows | Paper per fill at 0.34 | Live per fill at 0.34 | Paper at 0.65 | Live replay at 0.65 |
|---|---|---|---|---|---|
| r24 | 184 | +0.0090 | +0.0056 | +0.0150 | +0.0092 |
| r25 | 83 | +0.0164 | +0.0150 | +0.0267 | +0.0274 |
- With row c (10 ms): r24 +0.0079 vs +0.0047 (175 windows); r25 +0.0164 vs +0.0152 (76 windows).

**Where paper row a's extra comes from** (at 0.34):

| | r24 | r25 |
|---|---|---|
| Shared windows | 184 fills, +1.648 | 83, +1.358 |
| Create-slot windows (live skips them) | 98 fills, **-0.873** | 59, -0.058 |
| Other live skips | 8, +0.214 | 7, +0.098 |
| Live armed but never filled | 85, **+2.957** | 41, +1.274 |

**Known gaps:**
- Live skips create-slot triggers; paper counts them (they lost in r24).
- Paper rows are an idealized landing, 0 / 5 / 10 ms after the crash. Live lands a slot or so later and misses the fast
  bounces, which is the "armed but never filled" line.
- Paper has no failed tries.
- Paper's follower model is a random slippage table, not the decoded limits.
- Paper's tape includes **our own live buy and sell**. In shared windows that adds: r24 +1.648 -> +1.237 without them,
  r25 +1.358 -> +1.154.

## 5. No-trade fills (HINDSIGHT)
These are fills where no other wallet traded the token between our buy and our sell (chain tape). All of them are pre-send,
all were time exits, and there are none among the regular fills. Engine P&L basis, SOL:

| | Fills | Live | 0.50 | 0.65 | 1.00 |
|---|---|---|---|---|---|
| r24 no-trade fills | 26 | -0.310 | -0.413 | -0.509 | -0.734 |
| r24 pre-send without them | 174 | +1.287 | +1.831 | +2.167 | +2.504 |
| r25 no-trade fills | 6 | -0.072 | -0.095 | -0.117 | -0.169 |
| r25 pre-send without them | 89 | +1.023 | +1.551 | +1.976 | +2.483 |
- At buy time we cannot know that nobody will trade.
- One cheap at-entry check: the token's trades in the 10 slots before the trigger. The no-trade fills have a median of 2,
  the others 3.
- Skipping fills with fewer than 2 such trades would drop 113 fills, catch only 15 of the 32 no-trade fills, and give up
  +0.90 SOL (live). No simple filter found.

## 6. Risks
- **Bigger swings per trade** (pre-send):

  | | Live | 0.65 | 1.00 |
  |---|---|---|---|
  | Standard deviation per fill | 0.035 | 0.062 | 0.094 |
  | Worst single trade | -0.106 | -0.200 | -0.307 |
  - The worst at 0.65: Cxoe53 r25 04:50 -0.200; HZi3fcn6 r24 22:23 -0.169; RKor5T r25 04:47 -0.158. All are time or
    stop-loss exits after a dump that kept falling.
  - Regular, worst at 0.65: 9cqF4L r24 23:30 -0.118.
- **Kill switch (0.5 SOL below each start).** Running P&L of r24's first segment (21:53-00:10), lowest point vs its start:
  - -0.09 live, -0.18 at 0.65, **-0.61 at 1.00**, so the switch would have stopped it.
  - The other segments stay above their start at 0.65.
  - Peak-to-trough drawdowns: 0.35 / 0.66 / 1.13 SOL (live / 0.65 / 1.00).
- **The edge is still the later buyers.** With 20% fewer of them, r24 pre-send is negative at every size, and r25 holds.
  - The bigger the buy, the more of them we price out ourselves.
  - Bots that react to bigger buys are not modelled.
- **Not modelled:**
  - failed followers trying again;
  - longer or shorter positions changing which later windows arm (5 exits move);
  - FRA's own trades on the same tokens: 3 FRA trades fall inside AMS holds; the replay keeps them, as always-fill;
  - fewer followers when we buy bigger.

## 7. Files
- **Code** (`ops/strategies/presend/real/r065/`):
  - `live.py`: records;
  - `extract.py`, `tape.py`: raw recording to tape;
  - `pmath.py`: pump math, checked on the tape;
  - `fetch.py`: follower limits, read-only RPC;
  - `core.py`, `positions.py`: replay;
  - `calib065.py`: live exit triggers and delays;
  - `run065.py`: all sizes and stress tests;
  - `failcheck.py`, `wallet.py`, `paper.py`, `paperrun.py`, `notrade.py`, `summary.py`.
- **Data** (`/home/moiz/sniper-data/replay065/`):
  - `live/`: run files, md5 = server;
  - `tape.pkl`, `args_hold.jsonl`;
  - `results.json`: per trade, every size;
  - `wallet.json`, `paper.json`, `notrade.json`, `summary.json`, `failcheck.json`, `delays.json`.
- **Re-run**:
  ```
  python3 live.py && python3 extract.py && python3 tape.py && python3 calib065.py && python3 run065.py 200
  python3 failcheck.py && python3 wallet.py && python3 paperrun.py && python3 notrade.py && python3 summary.py
  ```
  `fetch.py` is needed only for new signatures.
