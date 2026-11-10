# CUSTOM37: could custom pre-send configs have cut AMS run 37's losses? (10-29, times PKT)

Owner ask (10-29 ~18:15): take run 37's fills and see if per-window configs (limit, size, tries, window, exit ...) would have cut
the losses WITHOUT cutting the profit. MEASURED = live records / chain tape / replay on real tries. INFERRED = model steps
(phantom tries, sell latency draws for new fills). Nothing was sent, deployed or written on a server.

## Short answer
- **No limit / quote / tries / exit change cuts r37's losses robustly.** Every policy picked on the earlier runs either gives
  about 0 on r37 (best limit-only policy +0.03 SOL) or loses on r37 (best limit+exit policy -0.37 SOL). The custom quote
  (limit = latest x (1 - 0.7 x the whale's full-dump drop), 0.12..0.16) is +0.16 SOL on r37 and +0.68 on the earlier runs, but
  it is not positive without its top 5 windows on either set, so it is not proven. MEASURED replay (11-16% INFERRED).
- **Keep the current pre-send config** (drop 0.12, k 8, window 10, deadline +1, exit 200 ms, TP 20 / SL 20, QUIET stop 5:2).
  Drop 0.12 is the best flat limit on both sets; exit 200 ms is the only exit time not clearly worse on one of the two sets;
  every other single change is worse or noise on at least one side.
- **59% of r37's loss is 18 "cascades"** (another wallet, or the whale, dumps 2-6 SOL inside our 0.4 s hold): -1.55 SOL. No arm-time
  feature tried (whale size / %, full-dump drop, curve, age, whale history, holders, leader clients, hour) separates them from
  winners in a way that holds on the earlier runs; a deeper limit avoids about half of them but costs more winners (drop 0.15:
  losers +0.81, winners -1.16 SOL on r37).
- **The only robust lever is size**, and it scales losses too: 0.85 SOL = +0.82 SOL on r37 (+1.8/day), +3.06 on the earlier runs
  (+2.4/day), +0.37 at -20% followers, positive in all 7 runs, worst trade -0.18 -> -0.22, max drawdown 0.69 -> 0.81 SOL.
  Flags only: `--presend-live-size-sol 0.85 --max-sol 0.8925`. Owner decision: it is more risk, not a loss cut.
- INFERRED only: k 12 (+0.55 SOL on r37, but ~0 at -20% followers) and a 15-slot window (+0.28, not positive without the top 5)
  come almost entirely from modelled tries. Worth a live A/B, not a switch.
- Hindsight upper bound (fitted on r37 itself): a fulldrop-based limit would have made +0.97 SOL (+2.2/day) on r37, but the same
  rule is +0.39 on the earlier runs and -0.74 without their top 5: the r37 big losers sit in a segment that was profitable before.

## 1. Data (MEASURED)
- r37 records copied read-only at **18:19 PKT** (13:18:56 UTC; no new fill since the owner's 18:10 numbers, which match): 2 engine sessions, 598 armed windows, 891 skips, 29,705 sends =
  29,170 unique tries (535 byte-identical resends share a signature: one tx), 168 fills. Realized +3.040 SOL (93 winners +5.661,
  75 losers -2.622). Failed-try fees -0.147 (28,786 landed failed tries x 5,120 lamports).
- **r37 runs TP 20% / SL 20%** (run_start presend_live tp 0.2, sl 0.2; the 3 stop-loss exits sold at value 0.71-0.79), not SL 50%.
- Tape: recorder chunks 10-29 07:21 -> 18:21 PKT (132 chunks; every size equal to the FRA server's copy; the last chunk was read
  from FRA because the local copy was still partial), 1.21 M trades. Our two wallets removed.
- TRAIN = AMS r34 (3.2 h), r35 (4.2 h), r36 (3.9 h), FRA r26 (1.9 h), r27 (12.0 h), r28 (5.5 h) = 30.7 h, only the 2,529 windows the
  r37 config would arm (token age >= 2 slots; QUIET all-4 recomputed with fol 4.0 and no follower-bot list). All replayed AT the
  r37 config (0.696 SOL, 5:2, TP/SL 20/20, exit 200 ms). Tape: presend_quiet3 chain + presend_young ext. TEST = r37 (10.8 h).
- P&L here is cash: realized + the ATA rent refund (+1.509 mSOL per fill, not in realized) - failed-try fees. Fixed costs per
  round trip MEASURED on all 168 fills: realized - curve P&L = -3.524 mSOL exactly (tip 0.2, fees, sell tip 1.2, ATA rent).

## 2. Calibration (the replay must match live first)
- **Try level (MEASURED): 100.00% agreement.** Every landed try before our fill, re-checked at its real landing position (slot,
  index) with its real limit: r37 26,386 tries (26,218 price above limit + 168 fills), TRAIN 101,981 tries, all agree.
- **Window level at each run's own live config:** r37 168 of 168 fills by the same try, 0 extra; P&L +3.0398 vs live +3.0398.
  r36 129/129, r35 158/158, r34 120/120, f28 78/78, f27 200/200, f26 43/43; P&L exact except f27 (+0.013 SOL: one live record
  sold twice). The exit leg reproduces every fill's curve P&L to 0.0000 mSOL.
- How: curve states use token accounting (k = V x T constant to 6e-9): trades missing from a decoded tape stay inside the
  recorded states (f27 had a 4.6 SOL sell missing from the tape; a SOL-delta walk was off by 55 mSOL there). Exits use the
  window's own measured sell latency; rules that live shows had not fired (whale stop, expiry, backstop) are bounded by it.
- **Phantom tries (the INFERRED part)** fill periods with no real tries (a deeper limit after the live fill, a longer window,
  k 12, a removed one-position pause): sent every 212/k ms at the run's measured unique-try rate (AMS 7.4-7.8 per slot, FRA 4.7:
  FRA's path budget refused ~40% of sends), landing after a latency drawn from the run's real tries (median 88 ms). Check: ALL
  real tries replaced by phantoms -> AMS fills +2..+9% vs live, failed tries within 3%, P&L -0.25 / +0.34 / -0.60 / +0.11 SOL
  (r37 / r36 / r35 / r34); FRA fills +33..+51%. So phantom-heavy rows are noisy, and FRA ones are optimistic.
- One-position knock-on is in: a new position removes other windows' real tries while it is open; a live pause whose position
  no longer exists gets phantom tries. Windows are replayed in trigger order, 8 possible worlds each.

## 3. Where r37's losses come from (MEASURED, live fills; buckets: first match)
FLAT = no outside trade >= 0.01 SOL between our fill and our sell. CASCADE = outside sells >= 1 SOL in our hold with net
selling >= 0.5 SOL. SHALLOW ENTRY = dump depth < 15% at our fill and our entry >= 5% above the low of the next 2 s. DRIFT = rest.
Dump depth = price drop from the filling try's signing price. Entry above low = how much the price fell after our fill (2 s).

| bucket | n | sum SOL | mean mSOL | of them <= -0.02 | median dump depth | median entry above low | median hold sells SOL |
|---|---|---|---|---|---|---|---|
| CASCADE (whale 2nd leg) | 5 | -0.363 | -72.5 | 5 | 15.9% | 13.5% | 2.88 |
| CASCADE (second dumper) | 13 | -1.189 | -91.4 | 13 | 15.5% | 20.9% | 2.95 |
| SHALLOW ENTRY | 9 | -0.110 | -12.3 | 1 | 13.3% | 16.9% | 0.00 |
| DRIFT | 28 | -0.547 | -19.5 | 13 | 17.9% | 3.4% | 0.46 |
| FLAT | 20 | -0.413 | -20.7 | 19 | 16.8% | 1.4% | 0.00 |
| failed-try fees | 28786 tries | -0.147 | 0.00512 each | | | | |

- Winners in the same buckets: DRIFT 87, SHALLOW ENTRY 6 (none are CASCADE or FLAT by construction).
- Cascades: dump depth ~16%, then 2-6 SOL more selling lands within our 0.4 s hold (entry 14-21% above the later low). The
  second seller was the whale in 5 of 18. Flats (20, -0.41) are pure costs: pump fee both ways + tips + fees = 20.7 mSOL.

### All r37 losers at or below -0.02 SOL (51; time = our fill, PKT)
"best single knob" = the knob that helped THIS window most in the paired replay (mSOL; drop0.15 = limit 0.15, exit100 = exit
100 ms, q3:2 = QUIET stop 3:2, win6 = 6-slot window, k4 / k12 = tries per slot, dl2 = deadline +2, flat1000 = flat extension 1 s,
size0.5 = 0.5 SOL). "custom quote A" = what policy A did to it. Age in slots; full-dump drop = the whale's whole balance sold
into the post-trigger curve.
| time | mint (GMGN) | P&L | bucket | age sl | whale % / SOL | curve SOL | full-dump drop | dump depth / SOL (W = whale) | entry above low | hold: sells n/SOL, buys n/SOL | exit | best single knob for it | custom quote A |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15:47:47 | [69DKCV](https://gmgn.ai/sol/token/69DKCVmykx9jUuZZc8JYqSRtrxrECxJq5ZqW6dcgk5au) | -0.1828 | CASCADE (second dumper) | 66 | 6.4 / 2.47 | 36.4 | 13% | 14% / 3.13 | 31.8% | 1/5.14, 1/0.10 | stop-loss | drop0.15 +166 | +0 |
| 15:16:51 | [HRH3ps](https://gmgn.ai/sol/token/HRH3ps6BBKno7rnrQPpb7vetwvjMVHrm1GDBwWfkdkCP) | -0.1578 | CASCADE (second dumper) | 27 | 6.4 / 2.79 | 38.7 | 14% | 14% / 2.91 W | 37.6% | 1/5.60, 2/1.58 | stop-loss | drop0.15 +158 | +0 |
| 09:39:57 | [A8Uvh2](https://gmgn.ai/sol/token/A8Uvh2PhNypMk2bL5MNv6VYsAh2zvCyjjLD5g3S4pump) | -0.1546 | CASCADE (second dumper) | 23 | 11.4 / 4.89 | 39.7 | 23% | 24% / 6.12 | 30.2% | 8/7.47, 6/3.05 | time-ms | size0.5 +43 | +0 |
| 16:35:13 | [GoB64R](https://gmgn.ai/sol/token/GoB64RCkd3oYRpbC3W4JNJjLNjQYeC8mbQRFvL8tpump) | -0.1438 | CASCADE (whale 2nd leg) | 353 | 6.0 / 2.47 | 37.6 | 13% | 16% / 3.65 | 23.8% | 2/5.28, 6/1.33 | stop-loss | drop0.18 +144 | +0 |
| 15:46:39 | [2AeKpb](https://gmgn.ai/sol/token/2AeKpbmsWCC5yNriDH4djMzPXaBVHfAzSrq3fzjQ2dcR) | -0.1198 | CASCADE (second dumper) | 43 | 7.2 / 3.95 | 44.0 | 17% | 16% / 0.01 | 16.9% | 1/3.92, 4/0.70 | time-ms | exit100 +121 | +0 |
| 09:20:39 | [FGk5XL](https://gmgn.ai/sol/token/FGk5XL9t8RuCoYNeJA2SNATPmvZXFTAPyQgPvoWRpiLf) | -0.1142 | CASCADE (second dumper) | 24 | 7.3 / 2.94 | 37.4 | 15% | 19% / 3.74 | 33.7% | 3/3.13, 1/0.00 | time-ms | exit100 +89 | +0 |
| 17:59:07 | [6mr3oy](https://gmgn.ai/sol/token/6mr3oyN6iLe4KhqFUPzFkDc7DdzDekrMLTXWXyuipump) | -0.0774 | CASCADE (whale 2nd leg) | 718 | 6.6 / 3.56 | 43.3 | 16% | 20% / 1.43 | 20.5% | 2/3.72, 6/1.99 | time-ms | size0.5 +21 | +0 |
| 17:41:44 | [7jL1pR](https://gmgn.ai/sol/token/7jL1pRpX6ueHKTkBKnrK1woNfMTyeMshqNYa2tmppump) | -0.0754 | CASCADE (second dumper) | 12 | 7.5 / 3.46 | 40.4 | 16% | 21% / 3.77 W | 22.0% | 3/1.63, 0/0.00 | time-ms | k4 +23 | +0 |
| 17:08:59 | [E4iqSb](https://gmgn.ai/sol/token/E4iqSb3dDvnZ6MWztrd95c9MNpKWwD37KpuSDogS5pd3) | -0.0691 | CASCADE (second dumper) | 2 | 10.4 / 5.93 | 45.9 | 24% | 26% / 7.59 W | 114.5% | 1/2.17, 1/0.49 | time-ms | size0.5 +19 | +0 |
| 11:22:44 | [4X1Dpw](https://gmgn.ai/sol/token/4X1DpwhpcA8EutSzSpp6p9SLVmqMPnL9vP1tQeEUpump) | -0.0680 | CASCADE (second dumper) | 25 | 6.9 / 3.25 | 40.6 | 15% | 15% / 3.16 | 11.3% | 3/1.34, 0/0.00 | time-ms | win6 +67 | +0 |
| 10:39:06 | [4yFArb](https://gmgn.ai/sol/token/4yFArbnF9Aee1qcvfSVZWYmM2HrZ7DBHWtM2Hhuipump) | -0.0619 | CASCADE (second dumper) | 29 | 15.6 / 5.93 | 38.1 | 29% | 12% / 6.51 W | 20.9% | 1/1.80, 3/0.61 | time-ms | exit100 +63 | +60 |
| 14:05:19 | [96yx2U](https://gmgn.ai/sol/token/96yx2Ua2fTWtcEDEjqxA6Ls77RwZQeBw778zzoYupump) | -0.0538 | CASCADE (second dumper) | 6 | 12.5 / 4.94 | 38.2 | 24% | 21% / 5.37 W | 10.1% | 2/2.95, 7/2.04 | time-ms | size0.5 +14 | +0 |
| 14:18:43 | [9D9xpY](https://gmgn.ai/sol/token/9D9xpYuwQJxhzwYno4GCXL8XvVuB9E519nJ3oM7Upump) | -0.0528 | CASCADE (whale 2nd leg) | 830 | 6.4 / 6.78 | 61.7 | 21% | 15% / 6.72 W | 5.7% | 5/2.88, 6/1.48 | time-ms | drop0.18 +51 | +0 |
| 16:42:14 | [DR9QYX](https://gmgn.ai/sol/token/DR9QYXaoPnEhmAiMh1hE267sHeKFL8XoLoKxC6Xwqw1N) | -0.0508 | CASCADE (second dumper) | 5 | 6.0 / 2.78 | 40.0 | 13% | 14% / 3.10 | 9.5% | 1/1.64, 1/0.74 | time-ms | dl2 +55 | +0 |
| 15:51:17 | [6Wf9TA](https://gmgn.ai/sol/token/6Wf9TAYvtM4JnekZQWUgw3aPDhUjwaJBVvaUhvUpBRuA) | -0.0482 | CASCADE (whale 2nd leg) | 37 | 7.0 / 2.47 | 34.9 | 14% | 16% / 2.92 | 13.5% | 1/2.34, 3/1.64 | time-ms | drop0.18 +47 | +0 |
| 09:29:11 | [fhrBWu](https://gmgn.ai/sol/token/fhrBWuMSo9cvuAc5k5XznMLdaMx6791LbMnS6bcpump) | -0.0475 | DRIFT | 10 | 13.4 / 5.93 | 40.8 | 27% | 24% / 6.00 W | 18.9% | 1/0.95, 1/0.22 | time-ms | size0.5 +12 | +0 |
| 11:40:28 | [7CnFmb](https://gmgn.ai/sol/token/7CnFmbTBJe4cceZh4xaZCNugx6179UB6WpLWSjn9gjsc) | -0.0406 | CASCADE (second dumper) | 6 | 6.2 / 3.15 | 42.1 | 14% | 14% / 3.13 | 17.2% | 1/2.91, 3/2.32 | time-ms | win6 +39 | +0 |
| 09:52:28 | [5SAs2e](https://gmgn.ai/sol/token/5SAs2eZxLCpDCqwqLwERgHNtj9VWohpMXszPz33vpump) | -0.0405 | CASCADE (whale 2nd leg) | 284 | 10.2 / 3.98 | 37.5 | 20% | 20% / 3.95 W | 3.0% | 3/1.25, 2/0.73 | time-ms | size0.5 +10 | +0 |
| 10:33:34 | [9nN1zy](https://gmgn.ai/sol/token/9nN1zyne2oTTYXrLioheYVDx7AJ1RpHQScKEw8mtpump) | -0.0396 | CASCADE (second dumper) | 18 | 7.9 / 3.95 | 42.3 | 18% | 26% / 2.06 | 11.3% | 7/3.27, 5/2.60 | time-ms | win6 +38 | +0 |
| 08:04:01 | [7zD5wZ](https://gmgn.ai/sol/token/7zD5wZJp5UNR4TvyhxthPfmkvURvGKqnYm2Gvv2wftkS) | -0.0391 | DRIFT | 11 | 6.5 / 2.96 | 39.9 | 14% | 31% / 8.09 | 16.8% | 1/0.52, 0/0.00 | time-ms | size0.5 +10 | +0 |
| 12:45:41 | [DeZHhE](https://gmgn.ai/sol/token/DeZHhE8cKtgb5GPJ1HBqVtcSSeivgCpErRhAGvHwpump) | -0.0387 | DRIFT | 399 | 39.3 / 19.75 | 51.3 | 62% | 13% / 2.97 W | 3.5% | 1/0.65, 0/0.00 | time-ms | drop0.18 +37 | +37 |
| 11:05:16 | [GeGN38](https://gmgn.ai/sol/token/GeGN38tAcC9Cug4NKNPvmsqGrzxyWwa5Xe34uHxzpump) | -0.0347 | DRIFT | 5 | 11.4 / 7.33 | 49.3 | 28% | 28% / 7.33 W | 3.7% | 2/0.74, 1/0.30 | time-ms | q3:2 +33 | +0 |
| 12:57:10 | [3MRyD7](https://gmgn.ai/sol/token/3MRyD7DK84NmyB9KCnZy3CJcU1Q9TVf5m3fK16kqpump) | -0.0340 | DRIFT | 292 | 6.5 / 4.89 | 51.6 | 18% | 19% / 5.44 W | 3.2% | 7/2.49, 4/2.00 | time-ms | win6 +33 | +0 |
| 15:56:26 | [44ve5j](https://gmgn.ai/sol/token/44ve5jqGutYSfxoyVcZFTU243yY9F2g5qnrMsSGjiVyZ) | -0.0329 | DRIFT | 21 | 6.3 / 2.47 | 36.9 | 13% | 40% / 1.86 W | 1.8% | 1/0.52, 2/0.24 | time-ms | k4 +23 | +0 |
| 17:07:01 | [2M9Ep6](https://gmgn.ai/sol/token/2M9Ep63fTsUshs4tNH9rR9ThxHEBBHZvjCXmdyaseAvR) | -0.0324 | DRIFT | 47 | 9.9 / 3.95 | 38.0 | 20% | 16% / 4.30 W | 9.7% | 1/1.07, 1/0.74 | time-ms | exit100 +39 | +0 |
| 11:43:43 | [QE662q](https://gmgn.ai/sol/token/QE662qtPdPizjPBgGzbjbbQPQQVrfSUWseiQX4apump) | -0.0322 | DRIFT | 14 | 9.3 / 5.93 | 48.4 | 23% | 18% / 0.13 | 14.1% | 1/0.39, 0/0.00 | time-ms | k12 +32 | +0 |
| 09:12:20 | [ELqCRs](https://gmgn.ai/sol/token/ELqCRsaEPCJijmo2QefeUQy95pTB8FzeECSaTUJLpump) | -0.0284 | DRIFT | 41 | 7.7 / 6.78 | 56.8 | 22% | 20% / 6.72 W | 42.1% | 1/0.86, 3/0.52 | time-ms | k12 +41 | +0 |
| 15:36:33 | [HkTgqa](https://gmgn.ai/sol/token/HkTgqaH5dLr5M6XuaQv1AUWX1Lnx1ZatnWEczoVdqJUF) | -0.0283 | DRIFT | 28 | 6.6 / 2.96 | 39.4 | 14% | 23% / 4.82 | 1.1% | 1/0.20, 0/0.00 | time-ms | exit100 +8 | +0 |
| 11:47:01 | [EdL5zc](https://gmgn.ai/sol/token/EdL5zccqwoepD3g5xf6kqQmZjhYzsywjpPG3g4pXN8WZ) | -0.0247 | DRIFT | 297 | 11.1 / 4.94 | 40.5 | 23% | 13% / 0.14 | 0.6% | 1/2.13, 5/2.00 | time-ms | exit100 +71 | +23 |
| 13:39:53 | [2F9MCZ](https://gmgn.ai/sol/token/2F9MCZMZc6g3Af31tGdF4ypepNpfSTSkvMSPR5DsaKEq) | -0.0236 | DRIFT | 21 | 7.2 / 2.96 | 38.0 | 15% | 17% / 3.99 | 4.6% | 2/0.07, 0/0.00 | time-ms | q3:2 +22 | +0 |
| 12:06:31 | [6jzcLm](https://gmgn.ai/sol/token/6jzcLmTR7XvQinzuRYA26RGXC4TGkH9fNpjSyQywpump) | -0.0222 | DRIFT | 344 | 16.1 / 11.85 | 55.0 | 38% | 14% / 1.30 | 3.4% | 1/0.88, 2/0.82 | time-ms | drop0.15 +21 | +21 |
| 08:00:29 | [DEY4pH](https://gmgn.ai/sol/token/DEY4pHEYdx7Pmv36fMaMSwyX8axZLi27idpMCr5spump) | -0.0221 | SHALLOW ENTRY | 37 | 12.6 / 3.99 | 34.0 | 22% | 12% / 2.60 | 6.8% | 1/1.30, 1/1.26 | time-ms | drop0.15 +21 | +21 |
| 07:32:50 | [GtijRo](https://gmgn.ai/sol/token/GtijRo1wtiWSveLPLcTm18qHUiuemfCswtRTZx1nv7Qz) | -0.0207 | FLAT | 4 | 6.1 / 2.79 | 39.7 | 14% | 19% / 4.24 | 14.8% | 0/0.00, 0/0.00 | time-ms | flat1000 +42 | +0 |
| 07:54:57 | [8rv7VX](https://gmgn.ai/sol/token/8rv7VXADVv6g3y9xrqZTe9pBYnb1YVasxjcsPgN4pump) | -0.0207 | FLAT | 3568 | 8.3 / 2.79 | 34.3 | 16% | 16% / 2.79 | 0.0% | 0/0.00, 0/0.00 | time-ms | q3:2 +19 | +0 |
| 08:40:35 | [ALm1iQ](https://gmgn.ai/sol/token/ALm1iQ6KyjaNjQ48oUbn98ChPKHUF5FwWRVCkcTmpump) | -0.0207 | FLAT | 156 | 10.3 / 3.95 | 37.1 | 20% | 15% / 3.93 W | 3.7% | 0/0.00, 0/0.00 | time-ms | flat1000 +20 | +0 |
| 08:46:26 | [2Gc6y1](https://gmgn.ai/sol/token/2Gc6y1YfyHbeHvJxBaUZNw3WRWo6zGPuuubdgtQh7ZQN) | -0.0207 | FLAT | 35 | 7.6 / 2.96 | 36.9 | 15% | 17% / 3.63 W | 7.4% | 0/0.00, 0/0.00 | time-ms | drop0.18 +19 | +0 |
| 09:04:24 | [528wnh](https://gmgn.ai/sol/token/528wnhjBGUDrAjPWbft6y6WDXvJjPVrtxmeYXAbCpump) | -0.0207 | FLAT | 153 | 9.3 / 3.46 | 36.4 | 18% | 33% / 0.54 | 21.5% | 0/0.00, 0/0.00 | time-ms | none | +0 |
| 09:16:27 | [CXkycH](https://gmgn.ai/sol/token/CXkycHXMnGDNk2w81BXuDC7sJKudF6fkudZM2R7Hs5wP) | -0.0207 | FLAT | 822 | 11.7 / 3.96 | 35.0 | 21% | 21% / 3.95 W | 0.0% | 0/0.00, 0/0.00 | time-ms | flat1000 +13 | +0 |
| 09:21:26 | [7YM8Qu](https://gmgn.ai/sol/token/7YM8QupXGMMUgvTs8TeM7DpDnNEpd3or5Y1oxKmemEtA) | -0.0207 | FLAT | 11 | 6.7 / 2.94 | 39.0 | 14% | 31% / 7.02 | 1.8% | 0/0.00, 0/0.00 | time-ms | none | +0 |
| 09:24:19 | [Gyw67V](https://gmgn.ai/sol/token/Gyw67V8gXg58BKTa44v7RVwnnCCZq7eopsMdhwKKpump) | -0.0207 | FLAT | 182 | 8.1 / 3.46 | 38.9 | 17% | 12% / 0.19 | 19.1% | 0/0.00, 0/0.00 | time-ms | drop0.15 +27 | +0 |
| 09:45:38 | [DMAPRa](https://gmgn.ai/sol/token/DMAPRaWeCamprCZF95v4UFjw3MhnDusaZvYPigFvpump) | -0.0207 | FLAT | 12 | 7.0 / 2.96 | 38.5 | 15% | 15% / 2.96 | 33.9% | 0/0.00, 0/0.00 | time-ms | drop0.15 +19 | +0 |
| 09:50:34 | [5S1VEG](https://gmgn.ai/sol/token/5S1VEGL5G9FEvpXW3yUPoq5tsPB7zEKNenFv2g8xpump) | -0.0207 | FLAT | 27 | 6.7 / 2.82 | 38.4 | 14% | 27% / 3.00 | 0.0% | 0/0.00, 0/0.00 | time-ms | q3:2 +19 | +0 |
| 16:55:57 | [pM1Aob](https://gmgn.ai/sol/token/pM1Aobhxk4ExSPb5tWp3RNWPd61FeJu9zAMqa3Dpump) | -0.0207 | FLAT | 217 | 6.6 / 1.98 | 32.0 | 12% | 17% / 1.08 | 23.2% | 0/0.00, 0/0.00 | time-ms | drop0.18 +19 | +0 |
| 17:09:49 | [BTRrsd](https://gmgn.ai/sol/token/BTRrsdpUqVrKF85MDSDaX2zC3HzhqEPsBsCLWfypump) | -0.0207 | FLAT | 8939 | 6.9 / 2.47 | 35.1 | 14% | 14% / 2.49 W | 0.0% | 0/0.00, 0/0.00 | time-ms | q3:2 +19 | +0 |
| 17:10:41 | [58AqeW](https://gmgn.ai/sol/token/58AqeW3ZPXGsXiWJvmLfZ1MhJv52YEnVxYvcoaSqpump) | -0.0207 | FLAT | 88 | 15.5 / 5.93 | 38.2 | 29% | 16% / 3.92 | 0.0% | 0/0.00, 0/0.00 | time-ms | drop0.18 +19 | +19 |
| 17:27:14 | [GXoRTr](https://gmgn.ai/sol/token/GXoRTr2MeW14LQG59nwr5QdfsYxj8My1LcR56jumpump) | -0.0207 | FLAT | 191 | 10.1 / 6.78 | 50.0 | 25% | 25% / 6.72 W | 111.8% | 0/0.00, 0/0.00 | time-ms | none | +0 |
| 17:42:55 | [4putnt](https://gmgn.ai/sol/token/4putnt5MAedTmK9Yp1db5H82WZD1tGMSP2DbVa9BQnBD) | -0.0207 | FLAT | 6 | 6.5 / 2.06 | 33.0 | 12% | 12% / 2.06 W | 0.0% | 0/0.00, 0/0.00 | time-ms | flat1000 +190 | +0 |
| 17:56:32 | [G31Vht](https://gmgn.ai/sol/token/G31VhtagwRvRu3ojEzocXps1Ykauo9e7AGtJVD7xpump) | -0.0207 | FLAT | 2990 | 7.8 / 2.67 | 34.6 | 15% | 23% / 2.34 W | 0.0% | 0/0.00, 0/0.00 | time-ms | flat1000 +103 | +0 |
| 09:05:13 | [9x1mj1](https://gmgn.ai/sol/token/9x1mj1kW5KCr3wSWhz3Rqn93sZPmoqeUgSpR8FUzpump) | -0.0207 | FLAT | 45 | 8.6 / 3.25 | 36.6 | 17% | 15% / 3.25 W | 3.0% | 0/0.00, 1/0.00 | time-ms | q3:2 +19 | +0 |
| 13:28:32 | [3kJ3GH](https://gmgn.ai/sol/token/3kJ3GHBRrXdjapttEmaSKSiBjo6FAy7sZNABfKzRpump) | -0.0207 | FLAT | 4 | 8.1 / 2.47 | 32.6 | 15% | 15% / 2.45 W | 0.0% | 0/0.00, 1/0.00 | time-ms | drop0.15 +19 | +0 |
| 17:57:37 | [8Y3vAD](https://gmgn.ai/sol/token/8Y3vADQrpKsuHd65DutJGgAaEFG913TmBUjUMQ1kU1oN) | -0.0207 | FLAT | 29 | 6.9 / 2.96 | 38.8 | 15% | 20% / 4.15 | 1.1% | 0/0.00, 3/0.00 | time-ms | none | +0 |

What the knobs do to the 168 live fills only (added fills from unfilled windows are in section 4):

| knob | on losers | on winners | on all fills | windows helped / hurt (by more than 5 mSOL) |
|---|---|---|---|---|
| drop0.10 | -0.026 | -0.220 | -0.224 | 1 / 5 |
| drop0.15 | +0.697 | -1.215 | -0.356 | 30 / 22 |
| drop0.18 | +1.294 | -2.896 | -1.454 | 42 / 50 |
| quote_a0.7_f0.12_c0.16 | +0.181 | -0.017 | +0.164 | 7 / 2 |
| quote_a0.8_f0.12_c0.18 | +0.309 | -0.229 | +0.165 | 12 / 6 |
| size0.5 | +0.623 | -1.702 | -1.037 | 32 / 77 |
| size0.85 | -0.491 | +1.346 | +0.822 | 74 / 28 |
| exit100 | +0.345 | -0.381 | +0.019 | 31 / 24 |
| exit300 | -0.587 | -0.387 | -1.064 | 16 / 34 |
| tp10 | +0.000 | -0.550 | -0.550 | 9 / 13 |
| tp_off | +0.000 | +0.047 | +0.047 | 2 / 2 |
| sl10 | -0.084 | +0.000 | -0.084 | 0 / 3 |
| flat1000 | -0.338 | -0.026 | -0.364 | 6 / 8 |
| q3:2 | +0.171 | -0.189 | -0.004 | 10 / 5 |
| win6 | +0.177 | -0.401 | -0.193 | 6 / 9 |
| win15 | +0.000 | +0.000 | +0.000 | 0 / 0 |
| dl2 | +0.055 | -0.190 | -0.133 | 2 / 1 |
| k4 | -0.461 | -1.032 | -1.526 | 3 / 28 |
| k12 | +0.203 | -0.246 | +0.018 | 21 / 15 |

## 4. Each knob alone (paired vs the current r37 config, SOL; TRAIN 30.7 h, TEST r37 10.8 h; /day at 0.696)
CI = 90% bootstrap, windows resampled in (run, PKT hour) blocks. "INFERRED share" = share of |delta| from phantom-try fills.

| knob | TRAIN dSOL (/day) | TRAIN -20% | TRAIN w/o top 5 | TEST r37 dSOL (/day) | TEST -20% | TEST 90% CI | TEST w/o top 5 | r37 1st / 2nd half | r37 d losers / d winners / d fees | r37 fills +/- | INFERRED share | runs + / - (of 7) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Limit depth** | | | | | | | | | | | | |
| drop 0.08 | -3.30 (-2.58) | -4.65 | -3.99 | -0.63 (-1.39) | -0.98 | [-1.45, +0.19] | -1.19 | -0.19 / -0.44 | -1.50 / +0.86 / +0.012 | +74 / -2 | 0% | 0 / 7 |
| drop 0.10 | -1.41 (-1.10) | -2.12 | -2.00 | -0.29 (-0.66) | -0.42 | [-0.60, -0.02] | -0.66 | -0.23 / -0.06 | -0.67 / +0.37 / +0.004 | +34 / -0 | 0% | 0 / 7 |
| drop 0.15 | -1.98 (-1.55) | -0.39 | -2.85 | -0.36 (-0.79) | +0.08 | [-1.25, +0.53] | -0.91 | -0.19 / -0.17 | +0.81 / -1.16 / -0.004 | +0 / -49 | 20% | 2 / 5 |
| drop 0.18 | -5.46 (-4.27) | -1.80 | -6.60 | -1.45 (-3.23) | -0.50 | [-2.38, -0.58] | -2.11 | -0.93 / -0.53 | +1.43 / -2.87 / -0.008 | +0 / -92 | 12% | 0 / 7 |
| drop 0.20 | -6.24 (-4.88) | -1.71 | -7.66 | -1.69 (-3.75) | -0.55 | [-2.88, -0.58] | -2.39 | -1.04 / -0.65 | +1.67 / -3.35 / -0.010 | +0 / -109 | 11% | 0 / 7 |
| drop 0.25 | -9.79 (-7.66) | -3.68 | -11.45 | -2.76 (-6.13) | -1.15 | [-4.24, -1.35] | -3.46 | -1.78 / -0.98 | +1.97 / -4.72 / -0.011 | +0 / -138 | 3% | 0 / 7 |
| **Custom quote (limit = latest x (1 - a x full-dump drop), floor, cap)** | | | | | | | | | | | | |
| quote 0.3x, floor 0.12, cap 0.18 | +0.05 (+0.04) | +0.07 | -0.03 | +0.04 (+0.08) | +0.04 | [+0.00, +0.11] | +0.00 | +0.04 / +0.00 | +0.04 / +0.00 / -0.000 | +0 / -1 | 0% | 3 / 1 |
| quote 0.5x, floor 0.12, cap 0.18 | -0.01 (-0.00) | +0.13 | -0.15 | +0.14 (+0.32) | +0.15 | [+0.03, +0.29] | +0.00 | +0.14 / +0.00 | +0.12 / +0.03 / -0.000 | +0 / -3 | 0% | 3 / 3 |
| quote 0.5x, floor 0.10, cap 0.18 | -0.91 (-0.71) | -1.37 | -1.49 | +0.18 (+0.40) | +0.06 | [+0.01, +0.35] | -0.15 | +0.16 / +0.02 | -0.23 / +0.41 / +0.002 | +25 / -3 | 0% | 2 / 5 |
| quote 0.6x, floor 0.12, cap 0.18 | -0.17 (-0.13) | +0.19 | -0.75 | +0.16 (+0.36) | +0.18 | [-0.13, +0.49] | -0.10 | +0.29 / -0.12 | +0.17 / -0.01 / -0.001 | +0 / -7 | 16% | 2 / 4 |
| quote 0.7x, floor 0.12, cap 0.16 | +0.68 (+0.53) | +0.95 | -0.34 | +0.16 (+0.36) | +0.18 | [-0.13, +0.49] | -0.10 | +0.29 / -0.12 | +0.17 / -0.01 / -0.001 | +0 / -7 | 16% | 6 / 1 |
| quote 0.7x, floor 0.12, cap 0.18 | +0.59 (+0.46) | +0.97 | -0.42 | -0.01 (-0.01) | +0.07 | [-0.21, +0.18] | -0.17 | +0.12 / -0.12 | +0.17 / -0.18 / -0.001 | +0 / -9 | 20% | 4 / 3 |
| quote 0.8x, floor 0.12, cap 0.16 | +0.11 (+0.09) | +0.62 | -0.90 | +0.31 (+0.70) | +0.32 | [+0.02, +0.66] | -0.04 | +0.39 / -0.07 | +0.28 / +0.04 / -0.001 | +0 / -12 | 27% | 5 / 2 |
| quote 0.8x, floor 0.12, cap 0.18 | +0.28 (+0.22) | +0.91 | -0.86 | +0.16 (+0.37) | +0.23 | [-0.05, +0.39] | -0.09 | +0.25 / -0.08 | +0.31 / -0.14 / -0.002 | +0 / -16 | 28% | 5 / 2 |
| quote 0.8x, floor 0.12, cap 0.25 | +0.03 (+0.02) | +0.82 | -1.11 | -0.28 (-0.62) | -0.11 | [-0.92, +0.24] | -0.54 | -0.06 / -0.22 | +0.24 / -0.52 / -0.002 | +0 / -18 | 16% | 4 / 3 |
| quote 0.8x, floor 0.08, cap 0.18 | +0.13 (+0.10) | +0.61 | -1.01 | +0.17 (+0.37) | +0.18 | [-0.04, +0.37] | -0.09 | +0.26 / -0.09 | +0.23 / -0.06 / -0.002 | +8 / -16 | 23% | 5 / 2 |
| quote 1.0x, floor 0.12, cap 0.16 | -0.52 (-0.40) | +0.78 | -1.56 | -0.61 (-1.36) | -0.20 | [-1.21, -0.04] | -0.92 | -0.38 / -0.24 | +0.52 / -1.12 / -0.005 | +0 / -46 | 5% | 2 / 5 |
| **Size** | | | | | | | | | | | | |
| size 0.35 | -6.77 (-5.30) | -3.15 | -7.50 | -1.82 (-4.05) | -0.81 | [-2.64, -1.01] | -2.19 | -1.30 / -0.52 | +1.17 / -3.00 / +0.000 | +0 / -0 | 0% | 0 / 7 |
| size 0.50 | -3.85 (-3.01) | -1.79 | -4.26 | -1.04 (-2.30) | -0.46 | [-1.50, -0.58] | -1.25 | -0.74 / -0.30 | +0.67 / -1.70 / +0.000 | +0 / -0 | 0% | 0 / 7 |
| size 0.85 | +3.06 (+2.39) | +1.40 | +2.60 | +0.82 (+1.83) | +0.37 | [+0.46, +1.19] | +0.51 | +0.59 / +0.24 | -0.52 / +1.35 / +0.000 | +0 / -0 | 0% | 7 / 0 |
| size 1.00 | +6.06 (+4.73) | +2.80 | +5.16 | +1.63 (+3.62) | +0.73 | [+0.91, +2.36] | +1.02 | +1.16 / +0.47 | -1.03 / +2.66 / +0.000 | +0 / -0 | 0% | 7 / 0 |
| **Tries / window / deadline** | | | | | | | | | | | | |
| k 4 | -3.49 (-2.73) | -2.10 | -4.19 | -1.46 (-3.25) | -1.24 | [-2.62, -0.65] | -1.57 | -0.59 / -0.87 | -0.73 / -0.80 / +0.072 | +0 / -14 | 13% | 0 / 7 |
| k 12 | +3.20 (+2.50) | +1.34 | +2.46 | +0.55 (+1.23) | +0.03 | [+0.05, +1.11] | +0.21 | +0.24 / +0.31 | -0.11 / +0.73 / -0.069 | +18 / -0 | 97% | 6 / 1 |
| window 4 | -4.60 (-3.60) | -2.48 | -5.07 | -1.49 (-3.31) | -0.85 | [-2.46, -0.57] | -1.83 | -0.70 / -0.79 | +0.43 / -1.98 / +0.060 | +0 / -43 | 0% | 0 / 7 |
| window 6 | -1.42 (-1.11) | -0.64 | -1.66 | -0.16 (-0.35) | -0.01 | [-0.46, +0.13] | -0.35 | -0.17 / +0.01 | +0.21 / -0.40 / +0.038 | +0 / -16 | 0% | 2 / 5 |
| window 15 | +1.82 (+1.42) | +0.78 | +1.09 | +0.28 (+0.61) | +0.17 | [+0.07, +0.50] | -0.02 | +0.13 / +0.15 | -0.11 / +0.43 / -0.039 | +13 / -0 | 93% | 6 / 1 |
| deadline +2 | +0.45 (+0.35) | +0.28 | +0.01 | -0.22 (-0.49) | -0.22 | [-0.58, +0.06] | -0.28 | -0.23 / +0.01 | -0.13 / -0.09 / +0.000 | +4 / -0 | 0% | 4 / 3 |
| k 12 + window 15 | +5.74 (+4.49) | +2.38 | +4.80 | +0.79 (+1.75) | +0.02 | [+0.07, +1.57] | +0.40 | +0.33 / +0.46 | -0.19 / +1.11 / -0.127 | +30 / -0 | 95% | 7 / 0 |
| **Exit** | | | | | | | | | | | | |
| exit 100 ms | -1.40 (-1.09) | -0.62 | -2.09 | +0.02 (+0.04) | +0.20 | [-0.44, +0.43] | -0.38 | -0.17 / +0.19 | +0.28 / -0.26 / +0.000 | +0 / -0 | 0% | 1 / 6 |
| exit 300 ms | +0.72 (+0.56) | +0.08 | -0.15 | -1.06 (-2.36) | -1.20 | [-2.09, -0.25] | -1.40 | -0.18 / -0.88 | -0.92 / -0.14 / +0.000 | +0 / -0 | 0% | 4 / 3 |
| exit 300 ms, 3-slot backstop | +0.21 (+0.16) | -0.54 | -0.68 | -1.04 (-2.31) | -1.20 | [-2.06, -0.28] | -1.38 | -0.22 / -0.82 | -0.91 / -0.13 / +0.000 | +0 / -0 | 0% | 3 / 4 |
| exit 500 ms | -0.40 (-0.32) | -1.28 | -1.34 | -1.22 (-2.71) | -1.39 | [-2.26, -0.43] | -1.56 | -0.30 / -0.92 | -0.95 / -0.27 / +0.000 | +0 / -0 | 0% | 3 / 4 |
| exit 500 ms, 3-slot backstop | -1.22 (-0.96) | -3.43 | -2.36 | -1.47 (-3.27) | -1.79 | [-2.58, -0.52] | -1.99 | -0.56 / -0.91 | -1.36 / -0.11 / +0.000 | +0 / -0 | 0% | 2 / 5 |
| TP off | +0.52 (+0.40) | +0.11 | -0.11 | +0.05 (+0.10) | -0.02 | [-0.08, +0.20] | -0.05 | +0.02 / +0.02 | +0.00 / +0.05 / +0.000 | +0 / -0 | 0% | 5 / 1 |
| TP 10% | -0.11 (-0.08) | +0.07 | -0.64 | -0.55 (-1.22) | -0.19 | [-1.04, -0.07] | -0.80 | -0.32 / -0.23 | +0.00 / -0.55 / +0.000 | +0 / -0 | 0% | 3 / 4 |
| TP 30% | +0.43 (+0.34) | +0.09 | -0.10 | +0.07 (+0.15) | -0.01 | [-0.05, +0.22] | -0.03 | +0.06 / +0.01 | +0.00 / +0.07 / +0.000 | +0 / -0 | 0% | 5 / 1 |
| SL 10% | -0.66 (-0.52) | -0.61 | -0.76 | -0.08 (-0.19) | -0.02 | [-0.19, -0.01] | -0.08 | +0.00 / -0.08 | -0.08 / +0.00 / +0.000 | +0 / -0 | 0% | 1 / 6 |
| SL 15% | -0.27 (-0.21) | -0.34 | -0.27 | -0.06 (-0.13) | -0.05 | [-0.18, +0.00] | -0.06 | +0.00 / -0.06 | -0.06 / +0.00 / +0.000 | +0 / -0 | 0% | 0 / 4 |
| SL 30% | +0.06 (+0.04) | +0.03 | -0.09 | +0.02 (+0.05) | +0.01 | [+0.00, +0.06] | +0.00 | +0.00 / +0.02 | +0.02 / +0.00 / +0.000 | +0 / -0 | 0% | 2 / 1 |
| SL 50% | +0.06 (+0.04) | +0.03 | -0.09 | +0.02 (+0.05) | +0.01 | [+0.00, +0.06] | +0.00 | +0.00 / +0.02 | +0.02 / +0.00 / +0.000 | +0 / -0 | 0% | 2 / 1 |
| **Flat extension** | | | | | | | | | | | | |
| flat ext 0.6 s | -0.59 (-0.46) | -0.72 | -0.82 | -0.51 (-1.12) | -0.63 | [-1.15, -0.04] | -0.55 | -0.11 / -0.39 | -0.49 / -0.01 / +0.000 | +0 / -0 | 0% | 2 / 5 |
| flat ext 1.0 s | -0.84 (-0.65) | -1.02 | -1.07 | -0.36 (-0.81) | -0.58 | [-0.93, +0.03] | -0.73 | -0.27 / -0.10 | -0.63 / +0.27 / +0.000 | +0 / -0 | 0% | 2 / 5 |
| flat ext 2.0 s | -1.34 (-1.05) | -1.57 | -1.57 | -0.36 (-0.81) | -0.61 | [-0.93, +0.03] | -0.73 | -0.27 / -0.10 | -0.63 / +0.27 / +0.000 | +0 / -0 | 0% | 2 / 5 |
| **QUIET stop** | | | | | | | | | | | | |
| QUIET 3:2 | -0.13 (-0.10) | +0.08 | -0.24 | +0.01 (+0.02) | +0.08 | [-0.21, +0.20] | -0.10 | -0.06 / +0.07 | +0.18 / -0.19 / +0.013 | +0 / -15 | 0% | 4 / 3 |
| QUIET 4:2 | -0.01 (-0.01) | +0.01 | -0.11 | +0.01 (+0.01) | +0.04 | [-0.06, +0.08] | -0.07 | +0.00 / +0.00 | +0.07 / -0.07 / +0.006 | +0 / -7 | 0% | 5 / 1 |
| QUIET 6:2 | +0.05 (+0.04) | -0.02 | -0.10 | +0.03 (+0.07) | -0.01 | [-0.03, +0.11] | -0.02 | +0.05 / -0.01 | -0.02 / +0.06 / -0.004 | +3 / -0 | 94% | 5 / 2 |
| QUIET stop off | +0.42 (+0.33) | +0.15 | -0.15 | +0.03 (+0.06) | -0.03 | [-0.09, +0.15] | -0.08 | +0.06 / -0.04 | -0.06 / +0.11 / -0.021 | +6 / -0 | 89% | 4 / 3 |

Reading it:
- Limit: 0.12 is the best flat limit on both sets. Shallower adds fills that lose; deeper skips more winners than losers.
- Custom quote: small and not robust. Best TRAIN value (0.7x, cap 0.16) is +0.68 / +0.16, negative without the top 5 on both.
- Size: the only knob positive everywhere (all 7 runs, CI > 0, w/o top 5 > 0, -20% > 0); it raises losers and winners together.
- Tries / window: fewer tries or a shorter window lose. More (k 12, window 15) look good but are 93-97% INFERRED.
- Exit: 100 ms is +0.02 on r37 but -1.40 on TRAIN; 300 ms helped AMS r34-r36 (+0.74) but lost -1.06 on r37. 200 ms is the only
  time not clearly worse on one set. TP 10% and SL 10-15% lose; TP off / 30% and SL 30-50% are within noise (TP 20% / SL 20% rarely fire).
- Flat extension loses on both sets: after a quiet 200 ms the next trade is often the next dump (one r37 window: -355 mSOL).
- QUIET stop N: no effect worth a change.

## 5. Custom policies (picked on TRAIN only, scored frozen on r37; exact replay with mixed configs)
Search: 1 or 2 arm-time features (full-dump drop, whale SOL / %, curve SOL, token age, whale dump history wh_dumps / wh_fol,
since_last, 60 s trade count, PKT hour, holder spread at the trigger, leader-client shares of the next 11 slots), at most 3
segments, one config per segment from the knob menu, a segment changed only if it gains on TRAIN, without its top 3, at -20%,
and is not negative in more than 2 of the 6 TRAIN runs. 5,763 policies per family.
- Limit / quote only: the top 50 by TRAIN give a median of +0.03 SOL on r37 (best +0.16).
- Limit + exit + tries: top 50 by TRAIN, median -0.28 on r37, only 1 of 50 positive (TRAIN loves exit 300 ms; r37 does not).
- With size: all top 50 are positive on r37 (median +1.57), because they are "size 1.0 with a carve-out" (size 1.0 alone: +1.63).

#### A_quote_0.7x_0.12-0.16
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +0.675 | +0.53 | [-0.60, +1.92] | -0.339 | +0.946 | +1.066 | -0.384 | -0.007 | +0.0 / -41.4 | 11% |
| TEST r37 (10.8 h) | +0.164 | +0.36 | [-0.13, +0.48] | -0.103 | +0.184 | +0.172 | -0.007 | -0.001 | +0.0 / -7.0 | 16% |
r37 1st half +0.288, 2nd half -0.124. Per run: r37 +0.164, r34 -0.108, r35 +0.136, r36 +0.384, f26 +0.066, f27 +0.185, f28 +0.012

#### B_trainbest_limit_exit
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +2.543 | +1.99 | [+1.33, +3.75] | +1.292 | +2.166 | +0.765 | +1.782 | -0.003 | +3.0 / -32.5 | 6% |
| TEST r37 (10.8 h) | -0.372 | -0.83 | [-0.81, +0.00] | -0.590 | -0.397 | -0.078 | -0.294 | -0.000 | +0.0 / -7.0 | 0% |
r37 1st half -0.340, 2nd half -0.031. Per run: r37 -0.372, r34 +0.049, r35 +0.364, r36 +0.831, f26 +0.198, f27 +0.998, f28 +0.104

#### C_trainbest_size
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +7.126 | +5.57 | [+5.28, +9.11] | +6.046 | +4.307 | -1.942 | +9.072 | -0.003 | +0.0 / -23.0 | 2% |
| TEST r37 (10.8 h) | +1.430 | +3.18 | [+0.76, +2.06] | +0.822 | +0.612 | -0.902 | +2.332 | -0.001 | +0.0 / -4.0 | 0% |
r37 1st half +1.113, 2nd half +0.316. Per run: r37 +1.430, r34 +0.481, r35 +1.432, r36 +1.208, f26 +0.457, f27 +2.722, f28 +0.826

#### size0.85_all
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +3.056 | +2.39 | [+2.27, +3.88] | +2.604 | +1.399 | -1.757 | +4.813 | +0.000 | +0.0 / -0.0 | 0% |
| TEST r37 (10.8 h) | +0.822 | +1.83 | [+0.45, +1.19] | +0.515 | +0.367 | -0.524 | +1.346 | +0.000 | +0.0 / -0.0 | 0% |
r37 1st half +0.586, 2nd half +0.236. Per run: r37 +0.822, r34 +0.329, r35 +0.651, r36 +0.339, f26 +0.214, f27 +1.115, f28 +0.407

#### size1.0_all
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +6.056 | +4.74 | [+4.50, +7.70] | +5.162 | +2.804 | -3.472 | +9.528 | +0.000 | +0.0 / -0.0 | 0% |
| TEST r37 (10.8 h) | +1.629 | +3.62 | [+0.89, +2.35] | +1.021 | +0.729 | -1.035 | +2.664 | +0.000 | +0.0 / -0.0 | 0% |
r37 1st half +1.161, 2nd half +0.469. Per run: r37 +1.629, r34 +0.653, r35 +1.290, r36 +0.673, f26 +0.423, f27 +2.210, f28 +0.807

#### win15 (INFERRED)
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +1.822 | +1.42 | [+0.95, +2.72] | +1.089 | +0.778 | -1.134 | +3.077 | -0.121 | +73.8 / -0.0 | 86% |
| TEST r37 (10.8 h) | +0.276 | +0.61 | [+0.07, +0.50] | -0.020 | +0.171 | -0.113 | +0.428 | -0.039 | +12.9 / -0.0 | 93% |
r37 1st half +0.125, 2nd half +0.151. Per run: r37 +0.276, r34 +0.321, r35 +0.173, r36 +0.502, f26 +0.122, f27 -0.005, f28 +0.708

#### k12 (INFERRED)
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +3.196 | +2.50 | [+1.82, +4.63] | +2.461 | +1.339 | -2.072 | +5.489 | -0.221 | +137.4 / -1.8 | 97% |
| TEST r37 (10.8 h) | +0.555 | +1.23 | [+0.05, +1.11] | +0.207 | +0.029 | -0.110 | +0.733 | -0.069 | +18.4 / -0.4 | 97% |
r37 1st half +0.244, 2nd half +0.310. Per run: r37 +0.555, r34 +0.186, r35 +0.501, r36 +0.368, f26 +0.073, f27 +2.130, f28 -0.062

#### ORACLE_r37_limit
| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |
|---|---|---|---|---|---|---|---|---|---|---|
| TRAIN (30.7 h) | +0.391 | +0.31 | [-0.84, +1.64] | -0.742 | +1.257 | +1.954 | -1.553 | -0.010 | +0.0 / -119.4 | 12% |
| TEST r37 (10.8 h) | +0.973 | +2.16 | [+0.44, +1.61] | +0.363 | +1.047 | +0.966 | +0.009 | -0.002 | +0.0 / -26.6 | 49% |
r37 1st half +0.330, 2nd half +0.643. Per run: r37 +0.973, r34 -0.064, r35 +0.048, r36 +0.194, f26 -0.029, f27 +0.533, f28 -0.291

- A = the custom quote the brief asked for (best quote on TRAIN). Positive on both sets but fails "w/o top 5" on both, and the
  r37 second half is -0.12: NOT proven. Its r37 gain comes from 9 windows (+126 mSOL from one).
- B = the best TRAIN policy without size. Fails on r37.
- C = the best TRAIN policy with size: passes every check, but it is size 1.0 with a carve-out that costs on r37 (+1.43 vs +1.63).
- ORACLE = fitted on r37 (upper bound only): +0.97 on r37, +0.39 on TRAIN, -0.74 on TRAIN without its top 5.

## 6. Verdict
1. **Do not change the limit, quote, tries, window, deadline, exit, TP/SL or QUIET stop** for loss reasons: nothing passes TRAIN ->
   r37. Expected gain of any of them: about 0 SOL/day, with real downside (exit 300: -2.4/day on r37).
2. **Losses cannot be cut without cutting profit by more** with arm-time configs: the big ones are cascades that no arm-time
   feature separates from winners. (A fill-time rule, e.g. who dumped into us, is outside this brief's no-look-ahead rule.)
3. **If the goal is more net SOL**: size 0.85 = about +1.8 SOL/day (r37) / +2.4/day (TRAIN) at 0% fewer followers, +0.8 / +1.1
   at -20%; 1.00 = +3.6 / +4.7 per day, +1.6 / +2.2 at -20%. Flags only: `--presend-live-size-sol 0.85 --max-sol 0.8925`
   (or `1.0` / `1.05`). Risk: worst trade x1.2-1.4, drawdown 0.69 -> 0.81 (0.85) / 0.93 (1.00) SOL in r37's replay, and the 10-26
   size study saw every size lose at -30% followers. Owner call.
4. **Worth a live A/B (INFERRED)**: k 12 (`--presend-live-k 12` plus `--presend-live-max-per-sec` / `--presend-live-path-max-per-sec`
   >= 57 and the helius-ps [[send]] budget) and window 15 (`--presend-window-slots 15`). Model: +1.2 and +0.6 SOL/day on r37.
   The model draws each try's latency independently, so more tries look better than they may be.
5. If the owner still wants the custom quote (A), it needs an engine change: at arm time compute the whale's full-dump drop
   f = 1 - (T / (T + whale balance))^2 on the post-trigger curve and use drop = clip(0.7 x f, 0.12, 0.16) for that window's
   limit_min_out (all other rules unchanged). Expected about +0.4..+0.5 SOL/day, not proven.

## 7. Known failures, quick re-check (MEASURED replay)
- Tighter SL: SL 10% -0.66 TRAIN / -0.08 r37; SL 15% -0.27 / -0.06. Still a loser.
- Whale >= 6 SOL skip: those windows were -0.52 SOL on TRAIN but +0.42 on r37: skipping them would have lost on r37.
- Firedancer skip: windows whose first slot is a Firedancer-family leader made +1.50 (TRAIN) / +0.56 (r37): a skip loses.
- Early sell (exit 100 ms) = -1.40 TRAIN / +0.02 r37: no.
- Not re-run (no new evidence): wave exit at 0.69 (wave37 report), age-0/1 recipes, QUIET 3-of-4, re-arm on competitors.

## 8. What this cannot model
- Followers reacting to our size or timing (the -20% row is the only stress); rivals reacting to us.
- Order inside a slot for phantom tries (from the block-position clock); FRA phantoms are optimistic (section 2).
- FRA r26 / r27 sold at 2 slots live: their 200 ms exits reuse each window's measured sell latency (INFERRED timing).
- One test run (r37, 10.8 h daytime PKT). TRAIN is mostly night PKT plus FRA.

## Files
Code /home/it/sniper/ops/strategies/presend/custom37/: c1_extract (windows + real tries), c2_tape (chain tapes), c2b_holders /
c2c_leaders (arm-time features), c37lib (replay), c3_calib, c4_grid (knobs), c5_tables, c6_losses, c7_policy, c8_final, c9_tables_md,
c10_report. Data /home/it/sniper-data/custom37/ (runs/ r37 copy + cut time, win_*/tape_* pickles, tab37 r37 tape, grid.pkl,
knobs.txt/json, losses.md/json, policies.json, final.txt/json, tables.md, calib_*.json).
