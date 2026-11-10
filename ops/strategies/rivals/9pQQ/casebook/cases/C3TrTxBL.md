# Case 01 — C3TrTxBL (run 10-30, launch 10-30 19:49:22 PKT, "George") — stratum A multi-win
Files: tapes/run_20261030_1355/C3TrTxBL*.{tl.txt,digest.txt,ev.jsonl.gz}. 4,004 landed trades, 1,720 failed, 26 trips, +0.98 SOL.

## What happened
- Two farming sessions: 19:49–21:12 (T1–T11, age +11..+23k) and 04:40–05:14 next morning (T12–T26, token revived, age ~150k).
- **First entry at age 11** (+11/248), right after a sell (APfq8 S0.65) in its own slot, after the launch-snipe flush (6Z91D dumped 4.57 at +8).
- **Era split inside one token** (this is the main lesson):
  - Evening trips T3–T6, T8–T11 (8 of 11) end at **exactly ~1,400 slots = the 300 s cap**, although each hold had 17–330 outside trades,
    including sells of 4.7–6.1 SOL at +105 % return and −30 % drawdowns. In that era the exit almost never fires.
  - Morning trips T12–T26 (15) are all signal exits, holds 14–1,149 slots, and many exit close to the in-hold peak (T12, T14, T16, T18, T20, T22).
  - Scale check (all trips, 3 runs): cap-exit share per half hour is 15–35 % from 10-29 ~18:00 to 10-31 00:10 PKT, then a 15-min hole
    in its trading (00:10–00:30), and **4–7 % from 10-31 00:30 on**; net P&L jumps from ~0 to +2..+7 SOL per half hour. A redeploy.
- T2 sell (+691/38): the real cause was the crash at +688–689 (five sells 1.3–4.7 SOL); it landed **first in slot +691**, 2 slots later,
  i.e. a next-slot reaction to a price fall, not an in-slot reaction to GKd5E's 0.31 buy (which my "last outside trade" labels as trigger).
- Buys: taken triggers sit in a **dip with a bounce starting**: ch10 median −4.4 % (skipped 0), nf10 −0.96 SOL (skipped 0), dd from 450-slot
  high −17.7 % (skipped −8.6 %), and the last trade is an outside BUY 20/25 (skipped 54 %). Trigger wallets are often repeat bots on the
  token (sssss…, GKd5E, omego/7xdwT): ucnt median 11 vs 2.
- Two "group" episodes: T12 sold into three identical-fee 0.8–0.9 SOL buys (JTvTZ/4uger/AFh3a, cup 1979k, tip 1 mSOL); T13 bought
  when those same three wallets dumped via FLASH 1 slot earlier. T17 bought after 3 consecutive ~1 SOL FLASH buys (3VwmH/H4dxJ/VTd8f,
  positions 211–213); T19 sold right after the same three sold. Not general (cohort test below fails).
- Cohort test (trigger buyers' first sell vs its sell): lines up only on T1 and T16; elsewhere 28–1,189 slots apart. Not the exit rule.
- Skipped: the biggest flat triggers are 4–5 SOL router buys (6Vo32/BiSoN/JUP6L) **at highs with ch10 ≈ 0** — it does not chase.
- Global: g_open 1–18, no visible cap.

## Hypotheses from this token
| id | cat | hypothesis | here |
|---|---|---|---|
| HM01 | meta | Logic versions: V2 (10-29 ~18:00 → 10-31 00:10) exits rarely (cap 15–35 %); V3 (10-31 00:30 →) exits often (cap ~5 %). Rules must be studied per era. | strong (scale) |
| HB14 | buy | Buys a dip that has started to bounce: price fell in the last ~10 slots (ch10 ≤ −3 %) and the last outside trade is a BUY. | support (taken ch10 −4.4 vs 0) |
| HB15 | buy | Trigger wallet is an active repeat trader on this token (ucnt ≥ 5; the co-reacting bot cohort sssss/GKd5E/omego). | support |
| HB16 | buy | Buys the dump of a coordinated group (≥3 fresh wallets, identical fee/tip, consecutive positions) / co-buys a group's buy-in. | weak (2 episodes) |
| HB17 | buy | Buys below the recent high (dd450 ≤ −10 %), not at highs. | support |
| HK02 | skip | Lets big router buys at highs (ch10≈0, dd≈0) go by: no chasing. | support |
| HS06 | sell | (V2) during the cap era the exit is a rare event; hundreds of trades incl. big dumps pass without a sell. | support |
| HS07 | sell | Sells when its trigger cohort sells. | contradict (2/26) |
| HS08 | sell | Exit is a next-slot reaction to a fast price fall (drawdown from the in-hold peak) landing early in the next slot. | support T2; untested V3 |
| HS09 | sell | (V3) exits near the in-hold peak, on the first down-tick after a run-up. | support (6 of 15 V3 exits within 3 pts of peak) |
| HB04 | buy | trigger size: taken median 0.40 vs skipped 0.15 | support |
| HB05 | buy | side B 20/25 vs 54 % | support |
| HB11 | buy | failed txs before trigger: 0 on taken and skipped | contradict (no signal) |
