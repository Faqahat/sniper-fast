# Dip bot runs — index

Each run has its own standard report (link). P&L = chain, after every cost, incl. the pre-send live probe (fills + account rent back − failed-attempt fees). Fills / Wins include pre-send fills. Times PKT.

| Region | Run | Started (PKT) | Ended (PKT) | Ran for | Buys | Fills | Wins | P&L SOL | What it tested |
|---|---|---|---|---|---|---|---|---|---|
| Frankfurt | [1](FRA_run01.md) | 10-24 02:15 | 10-24 02:43 | 0 h 27 m | 11 | 3 | 3 | **+0.1249** | First live PROD run: 3 trades × 0.25 SOL, strict tier, routes v2 |
| Frankfurt | [2](FRA_run02.md) | 10-24 03:03 | 10-24 03:50 | 0 h 46 m | 18 | 5 | 4 | **+0.1333** | 5 trades × 0.25 SOL, routes v3, engine dip8 |
| Frankfurt | [3](FRA_run03.md) | 10-24 04:15 | 10-24 05:01 | 0 h 46 m | 14 | 7 | 4 | **-0.0396** | 10 trades × 0.35 SOL, routes v4 (3 paths) |
| Frankfurt | [4](FRA_run04.md) | 10-24 05:09 | 10-24 06:38 | 1 h 28 m | 24 | 7 | 5 | **+0.1198** | 0.35 SOL, routes v5 (nozomi + helius-swqos + tipless staked-rpc) |
| Frankfurt | [5](FRA_run05.md) | 10-24 06:50 | 10-24 07:46 | 0 h 56 m | 15 | 10 | 5 | **-0.0014** | No take-profit / SL −10% / 1.3 s; dev list (bwamJzzt) at 0.75 wider, others strict 0.35; engine dip9 |
| Frankfurt | [6](FRA_run06.md) | 10-24 07:53 | 10-24 08:04 | 0 h 11 m | 3 | 2 | 1 | **-0.0069** | 0.5 SOL strict + dev 0.75 — short, stopped for run 7 |
| Frankfurt | [7](FRA_run07.md) | 10-24 08:04 | 10-24 15:43 | 7 h 38 m | 18 | 9 | 6 | **+0.2366** | 8 h, near leaders only (199), routes v7, 0.5 strict + dev 0.75, no TP |
| Frankfurt | [8](FRA_run08.md) | 10-24 15:44 | 10-24 16:40 | 0 h 55 m | 8 | 3 | 1 | **-0.0962** | Wider tier on every token, 0.55 SOL (owner) + dev 0.75, near leaders |
| Frankfurt | [9](FRA_run09.md) | 10-24 16:47 | 10-24 18:15 | 1 h 28 m | 9 | 2 | 1 | **-0.0419** | First two-region run — Frankfurt: 0.55 wider + dev 0.75, own near list (198) |
| Amsterdam | [9](AMS_run09.md) | 10-24 16:59 | 10-24 18:16 | 1 h 16 m | 7 | 2 | 1 | **-0.0566** | First Amsterdam run: 0.35 wider + dev 0.55, own near list (120 leaders) |
| Frankfurt | [10](FRA_run10.md) | 10-24 18:16 | 10-25 00:14 | 5 h 58 m | 73 | 29 | 12 | **-0.0734** | Exit A/B — Frankfurt: 4 s hold / SL −20% at 0.55 + dev 0.75 (Amsterdam = 1.3 s control); routes v8 |
| Amsterdam | [10](AMS_run10.md) | 10-24 18:17 | 10-25 00:15 | 5 h 57 m | 56 | 30 | 16 | **-0.1384** | Exit A/B control — Amsterdam: 1.3 s / SL −10% at 0.35 + dev 0.55; routes v8 |
| Amsterdam | [11](AMS_run11.md) | 10-25 00:29 | 10-25 00:55 | 0 h 25 m | 3 | 1 | 0 | **-0.0202** | Durable-nonce fan-out (dip10) + Constant-K standby RPC; 1.3 s / SL −10% at 0.35 + dev 0.55 |
| Frankfurt | [11](FRA_run11.md) | 10-25 00:30 | 10-25 00:55 | 0 h 25 m | 5 | 2 | 1 | **-0.0719** | Durable-nonce fan-out (dip10) + Constant-K standby RPC; run 10's A/B settings |
| Frankfurt | [12](FRA_run12.md) | 10-25 00:55 | 10-25 00:56 | 0 h 00 m | 0 | 0 | 0 | **+0.0000** | Restart with run 10's A/B settings (0.55 SOL, 4 s hold / SL −20%), stopped at once |
| Amsterdam | [12](AMS_run12.md) | 10-25 00:56 | 10-25 01:40 | 0 h 44 m | 7 | 1 | 1 | **+0.0220** | 15M µL/CU buy priority test (sells 5M); 0.35 SOL, 1.3 s / SL −10% |
| Frankfurt | [13](FRA_run13.md) | 10-25 00:59 | 10-25 01:40 | 0 h 41 m | 23 | 5 | 2 | **+0.0153** | 0.35 SOL normal + dev, 1.3 s / SL −10% (same exit as Amsterdam) |
| Frankfurt | [14](FRA_run14.md) | 10-25 01:41 | 10-25 06:08 | 4 h 26 m | 63 | 27 | 13 | **+0.0475** | M2 detector SHADOW (dip11) beside IMIT1 trading; 0.35 SOL, 1.3 s / SL −10% |
| Amsterdam | [13](AMS_run13.md) | 10-25 01:42 | 10-25 06:08 | 4 h 26 m | 31 | 17 | 9 | **-0.0141** | M2 detector SHADOW (dip11) beside IMIT1 trading; 0.35 SOL, 1.3 s / SL −10% |
| Frankfurt | [15](FRA_run15.md) | 10-25 06:09 | 10-25 15:09 | 9 h 00 m | 101 | 40 | 19 | **+0.1485** | A/B, M2 side: the new M2 model GATES the buys (dev-list keeps IMIT1); 0.35 SOL, 5-slot hold / no stop; M2 + pre-send shadows |
| Amsterdam | [14](AMS_run14.md) | 10-25 06:09 | 10-25 08:30 | 2 h 21 m | 3 | 1 | 0 | **-0.0560** | A/B, IMIT1 side: no-BAM near list (54 leaders), 5-slot hold / no stop, M2 + pre-send shadows |
| Amsterdam | [15](AMS_run15.md) | 10-25 08:37 | 10-25 08:47 | 0 h 10 m | 0 | 0 | 0 | **+0.0000** | Pre-send LIVE DRY run (dip13, 10 min): builds and signs pre-sent buys, sends none |
| Amsterdam | [16](AMS_run16.md) | 10-25 08:48 | 10-25 10:18 | 1 h 30 m | 0 | 20 | 9 | **-0.0073** | Pre-send LIVE probe (dip13): 0.2 SOL, 4 attempts per slot via helius-ps, caps 20 fills / 0.03 SOL fees |
| Frankfurt | [16](FRA_run16.md) | 10-25 15:29 | 10-25 17:29 | 2 h 00 m | 13 | 3 | 0 | **-0.1930** | Speed shadow run: dip14 with shred fire in SHADOW + clock2 + feed-lag + defer + skip Rakurai; M2 gate; 0.35 SOL, 5-slot hold / no stop; pre-send shadow (2 h) |
| Amsterdam | [17](AMS_run17.md) | 10-25 15:30 | ? | ? | 1 | 13 | 6 | **-0.0186** | Pre-send live probe 2: 0.35 SOL, whale >= 6%, 8 tries per slot via helius-ps, exit 2 slots / TP 10% / SL 20%; normal bot IMIT1 (M2 shadow), no-BAM near list (2 h) |
| Frankfurt | [17](FRA_run17.md) | 10-25 19:24 | 10-25 20:24 | 1 h 00 m | 0 | 0 | 0 | **+0.0000** | Relay probe P1 (Jito leaders): 8 paths, fail-by-design probe buys; no trading (cap 1 trade × 0.05 SOL, strict tier) |
| Frankfurt | [18](FRA_run18.md) | 10-25 20:31 | 10-25 20:56 | 0 h 25 m | 0 | 0 | 0 | **+0.0000** | Relay probe P2 (Harmonic + BAM leaders): 7 paths incl. falcon; no trading |
| Amsterdam | [18](AMS_run18.md) | 10-25 20:31 | 10-25 21:31 | 1 h 00 m | 0 | 0 | 0 | **+0.0000** | Relay probe P1b (Jito leaders, Amsterdam): 6 paths; no trading (cap 1 trade × 0.05 SOL, strict tier) |
| Frankfurt | [19](FRA_run19.md) | 10-25 21:34 | 10-25 21:46 | 0 h 12 m | 0 | 0 | 0 | **+0.0000** | Relay probe (Jito + Harmonic leaders): glaive, falcon, helius-swqos, astralane, landx-fra3, flashblock; no trading |
| Frankfurt | [20](FRA_run20.md) | 10-25 21:57 | 10-26 00:25 | 2 h 28 m | 52 | 19 | 10 | **+0.1482** | Live: M2 gate + routes v10 (falcon on BAM / Jito / Harmonic leaders) on dip16 (loaded-data limit, route headers, window clock); 0.35 SOL, 5-slot hold / no stop; pre-send shadow |
| Amsterdam | [19](AMS_run19.md) | 10-25 22:20 | 10-26 00:20 | 2 h 00 m | 14 | 69 | 36 | **+0.8863** | Pre-send live probe 3: 0.35 SOL, whale >= 6%, 8 tries per slot via helius-ps 30/s, exit 2 slots / TP 10% / SL 20%; normal bot IMIT1 (M2 shadow) (2 h) |
| Frankfurt | [21](FRA_run21.md) | 10-26 00:26 | 10-26 02:01 | 1 h 34 m | 31 | 63 | 26 | **-0.1185** | Live: M2 gate + live pre-send (0.35 SOL, 4 tries/slot, helius-ps 20/s) + routes v11 (Falcon UDP next to Falcon HTTP) on dip18 |
| Amsterdam | [20](AMS_run20.md) | 10-26 01:16 | 10-26 02:00 | 0 h 44 m | 8 | 37 | 16 | **-0.2494** | Live, same config as Frankfurt run 21 (M2 gate + live pre-send 0.35 / k 4 / 20/s + routes v11 on dip18) — but regular size 0.45 SOL (owner); a head-to-head race with Frankfurt |
| Frankfurt | [22](FRA_run22.md) | 10-26 02:18 | 10-26 02:48 | 0 h 30 m | 4 | 25 | 10 | **-0.1593** | Live 1 h: routes v12 (soyas, solami, glaive, falcon, falcon-udp) + M2 gate + live pre-send 0.40 (k 4) on dip18; 0.40 SOL |
| Amsterdam | [21](AMS_run21.md) | 10-26 02:19 | 10-26 02:49 | 0 h 30 m | 2 | 0 | 0 | **-0.0010** | Live 1 h: routes v12 (soyas, solami, glaive, falcon, falcon-udp) + M2 gate on dip18; 0.35 SOL; no pre-send live |
| Frankfurt | [23](FRA_run23.md) | 10-26 03:56 | 10-26 16:08 | 12 h 12 m | 152 | 166 | 68 | **+0.6523** | Live 12 h: M2 gate (m2_v3_reg4_top25) + live pre-send (k 4, 20/s, 100-fill cap, 0.1 SOL fee budget) + routes v13 (adds 0slot, skips Rakurai) on dip19; 0.40 SOL, dev list 0.40 |
| Amsterdam | [22](AMS_run22.md) | 10-26 03:56 | 10-26 16:08 | 12 h 12 m | 94 | 44 | 21 | **+0.0896** | Live 12 h: M2 gate + routes v13 (adds 0slot, skips Rakurai) on dip19; 0.35 SOL; pre-send SHADOW only; near list near_leaders_ams.txt (disjoint from Frankfurt) |
| Frankfurt | [24](FRA_run24.md) | 10-26 16:10 | 10-26 21:40 | 5 h 30 m | 119 | 135 | 64 | **+0.5252** | Live 5.5 h: same config as run 23 — M2 gate + live pre-send (0.40, k 4, 20/s, 100-fill cap, 0.1 SOL fee budget) + routes v13 on dip19; 0.40 SOL, dev list 0.40 |
| Amsterdam | [23](AMS_run23.md) | 10-26 16:10 | 10-26 21:40 | 5 h 30 m | 99 | 30 | 9 | **-0.1013** | Live 5.5 h: reactive M2 + routes v13 on dip19; 0.35 SOL, dev list 0.35; pre-send SHADOW only |
| Amsterdam | [24](AMS_run24.md) | 10-26 21:47 | 10-27 02:57 | 5 h 09 m | 84 | 237 | 121 | **+1.6953** | Live: pre-send LIVE 0.34 (k 4, 20/s, 100-fill cap, 0.1 SOL fee budget) + reactive M2 0.35 + routes v13 on dip19; restarted at 00:10 to reset the cap |
| Frankfurt | [25](FRA_run25.md) | 10-26 21:48 | 10-27 05:30 | 7 h 42 m | 208 | 73 | 27 | **-0.5489** | Live overnight: reactive M2 only (pre-send live off) + routes v13 on dip19; 0.40 SOL, dev list 0.40; 720 min |
| Amsterdam | [25](AMS_run25.md) | 10-27 02:58 | 10-27 06:09 | 3 h 10 m | 35 | 108 | 65 | **+1.1391** | Live: pre-send LIVE 0.34 (k 4, 100-fill cap) + reactive M2 0.35 + routes v13 on dip19 (same as run 24) |
| Amsterdam | [26](AMS_run26.md) | 10-27 06:58 | 10-27 14:03 | 7 h 04 m | 43 | 157 | 66 | **+0.3005** | Live day run: pre-send LIVE 0.50 (k 4, cap 1000 fills = the new run-script limit, fee budget 0.4) + reactive M2 0.50 + dev list 0.50 + routes v13 on dip19 |

**All runs: +4.2706 SOL** over 1402 fills and 1451 buys sent.
