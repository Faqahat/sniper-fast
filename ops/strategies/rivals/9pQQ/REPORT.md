# 9pQQc1xy dissection (11-03, PKT) — saved by the coordinator from the agent's final message
Scripts + 9pqq.json here (run_all.sh); data /home/it/sniper-data/rivals/9pQQ/ (incl. a compact tape of every curve trade, 4 recordings).
M = measured, I = inferred, E = paper estimate.

## What it is (M)
Net closed trips, fees+tips, ATA rent credited: 10-28 4,235 +19.6 (w/o top5 +12.4, w/o top20 -1.7); 10-30 8,867 +87.3 (+79.4/+65.3);
10-31 7,218 +68.6 (+58.5/+41.1); 11-02 16 h 7,730 +61.6 = +91.7/day (+51.0/+32.4).
One buy + one full sell per position (no scale-ins, no partials). 0.7 SOL (0.5 10-30 18:55 -> 10-31 07:00, mixed to ~10:00).
Hold time limit 300 s, 600 s from 10-31 14:03. "Non-trade" SOL inflows = CloseAccount rent refunds (5.7-10.6 SOL/day), not profit.
Failed txs 285-691/day (4-8% of buys, 0.06-0.13 SOL/day). No sister wallet with the same fee fingerprint. Old census picture
(scale-ins / graduations) no longer holds.

## 1. Sub-strategies (M) — LAUNCH (age <= 50 slots), DIP (other wallet sold >= 0.5 SOL in 3 slots), MOMO (net buying >= 1 SOL / 10
slots, last trade a buy), DRIFT (rest)
| entry | n | net | mSOL/trip | win | hold p50 | 10-28 | 10-30 | 10-31 | 11-02 |
| DIP | 9,294 | +87.6 | +9.4 | 43% | 66 | +12.6 | +33.8 | +12.6 | +28.6 |
| LAUNCH | 6,168 | +84.6 | +13.7 | 45% | 31 | +15.7 | +19.5 | +27.5 | +21.9 |
| DRIFT | 6,732 | +33.9 | +5.0 | 40% | 141 | -11.2 | +19.2 | +19.0 | +6.9 |
| MOMO | 5,856 | +31.1 | +5.3 | 39% | 125 | +2.5 | +14.8 | +9.6 | +4.2 |
68% of trips are re-entries; best = first-time DIP (+20.7 mSOL, n 1,250) and first-time LAUNCH (+13.4, n 5,403); first-time DRIFT loses
(-4.3 total); re-entry within 25 slots of its own sell +12.8; after a win +10.0, after a loss +4.9.
Signal exits +331 SOL (win 44%); forced time-limit exits -93.9 (-20..-28/day; dead tokens; LAUNCH at the limit -109 mSOL, 4% win).
By hold: 250-1,300 slots +210; 50-250 +96; < 6 +27; 6-50 -16; >= 1,300 -81. Top 20/day (+21..+29) = LAUNCH/DIP held 190-545 slots.

## 2. Selection (M) — 27,228 buys of 8.49 M decision moments (0.32%)
Never mayhem; ignores trades < 0.05 SOL (0.065%), sweet spot 0.2-2 SOL (0.6%); follows buys more than sells (0.43 vs 0.19%); token age
< 10 slots 0.026%, 10-50 slots 0.68%; curve 32-50 SOL preferred (0.45%), < 32 (0.09%) and >= 80 (0.13%) avoided; skips quiet flow
(|net 10 slots| < 0.5 SOL 0.12% vs 0.4-0.6%); own history matters most (round-tripped before ~1%, new 0.13%, within 25 slots of its
own sell 1.9%). No effect: creator sold, holder concentration, time of day. GBDT copy AUC 0.951 (10-31) / 0.941 (11-02), top input =
time since its own last sell; but only 14% of the model's top 0.1% picks are real buys.

## 3. Buy-ins (M)
45 ms median after the trade it reacts to (p10 7, p90 160), 67-69% same slot. On dumps SLOW: 130-152 ms (p25 68), first outside buyer
only 33-37% (we are 50-90 ms). One tx per decision (no copies, no durable nonce), CU price 1,500,001, two tips (Astralane 1 mSOL buy /
0.1 sell + Jito 17.5k lamports) -> 1.46 mSOL per round trip (ours ~4.5). 287 failed vs 7,735 buys on 11-02 (mostly 6042); we had 59,442
failed txs in the same 16 h (~197 per trip).

## 4. Sells
No TP/SL (M): flat 2-4% sell chance after each outside trade whatever the return. Reactive (M): 86% of sells within 1 slot of an outside
trade, 70% of those a sell; sell chance rises when buying stops (1.4% -> 13% after 300+ slots w/o a buy), when a high-volume bot sells
(7.5-11%), when its followers have all left (8-10%); next trade after its sell is a sell 63%. Exit timing (E): selling 1 slot before its
real sell = +70..+115 SOL per run vs ~0..+32 at its actual time; 50-212 ms later costs 12-19 SOL on 11-02. Not reproducible: "sells
next" model AUC 0.80-0.82 OOS but as our exit on its picks at 70 ms -11.8 mSOL/trip (its real exit -2.3); best simple rule -10.5.

## 5. Interactions (M)
On shared dumps it is our FOLLOWER: we buy before it 34/64/52/27 vs after 2/7/6/3 (10-28/10-30/10-31/11-02). 11-02: 8yYMhu before 163 /
after 29; haqq6qnV 331/209; E2x1 93/91. Our trips when it buys after us inside our hold: n 19/47/21/15, +15.5/+45.6/+38.6/+59.4 mSOL;
absent: n 566/417/435/281, +9.8/+9.5/+10.8/-1.5; it sold in our hold only 31 trips (4 days), -13..-34 on three days, +25 on 10-30.
Its own followers: 2.0-2.4 wallets / 0.8-1.1 SOL within 3 slots; ssssswdk follows ~10% of its trips.

## 6. Usable for us (50-90 ms, 0.55 SOL, 4.5 mSOL/trip) — replay matches its own total within 0.1%
A. Copying: NO. Its picks + real exit, us delta ms late, SOL/day (10-28/10-30/10-31/11-02): 0 ms +0.7/+51.8/+27.0/+25.2; 50 ms
   -7.2/+28.6/+9.6/-9.1; 70 ms -10.8/+12.4/-3.3/-26.5; 90 ms -13.4/+4.1/-7.6/-34.6; 70 ms -20% followers -33/-26/-33/-80. Fixed exits on
   its picks lose 9-25 mSOL/trip. Only signal-exit LAUNCH trips hold at 70 ms (+12..+20/day) but need its exit.
B. Its COST structure (arithmetic proven, landing not): 1.5 vs 4.5 mSOL = +3 mSOL/trip -> ~+0.9..+1.5 SOL/day for our 300-500 trips (E);
   needs a live A/B (single copy) with owner OK.
C. "9pQQ round-tripped this token before" as a pre-send priority signal (lead): our trips n 80/94/75/43 at +19.4/+29.5/+17.1/+15.5 vs
   never-touched n 500/360/377/247 at +8.8/+8.9/+12.2/-1.9; it re-enters our hold 17-29% vs 2-6%. Within quieter tokens (< 200 trades):
   +15.1/+31.0/+12.2/-0.3 vs +8.6/+8.7/+11.7/-3.2. Not useful for a generic reactive dip at 70 ms. Next: log-only annotation + forward.
D. Its LAUNCH lane at 70 ms with its exit: +5.1/+1.1/+9.2/+5.3 per day, w/o top 5 -0.2/-3.5/+4.5/-2.3 -> not proven.
E. Never mayhem; ignore < 0.05 SOL trades (we probably do).
Open: what its exit keys on; why it skips the first 10 slots; whether its single-copy 1.46 mSOL recipe keeps our pre-send fill rate.
