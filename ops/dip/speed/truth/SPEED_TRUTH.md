# SPEED TRUTH: where our dip buy's time goes

10-25 PKT, read-only. All 309 live attempts are covered:
- FRA runs 10–15: 202 attempts. Run 12 had no fires.
- AMS runs 9–14: 107 attempts.
- Window: 10-24 17:22 → 10-25 07:49 PKT.
- Results: 129 fills (42 %) and 180 failed buys. Of the fails, 178 were pump 6042 (the +5 % guard), 1 ran out of CU, and 1 landed 4 slots late (slot guard 6001).

**MEASURED** = counted from the data. **INFERRED** = my reading, not proven.

Clocks used:
- **Feed:** our server's wall clock, our tx's arrival on the executed feed minus the dump's.
- **B400:** the brief's block clock, slot × 212 + idx ÷ max(400, idx+1) × 212.
- **Bmix:** B400, but using the recorded block size when a block has more than 400 txs.

---

## 1. Verdict

1. **Speed decides whether we fill.** MEASURED on chain; the guard model reproduces 309 of 309 real outcomes.

   Share of all attempts that pass +5 % if our buy lands *d* ms after the dump:

   | d | feed | B400 | Bmix |
   |---|---|---|---|
   | 10 ms | 85 % | 91 % | 93 % |
   | 20 ms | 76 % | 81 % | 79 % |
   | 30 ms | 61 % | 68 % | 62 % |
   | 40 ms | 43 % | 59 % | 51 % |
   | 50 ms | 38 % | 47 % | 43 % |

   - We land at a median 40 ms on the feed clock (51–58 ms on the block clocks). That predicts about 43 %, and we filled 42 %.

2. **Our engine is not the problem.** MEASURED:
   - Our first write leaves 2.7 ms after the dump's first sighting (p90 7.3 ms).
   - That is 6 % of the time from the dump's first sighting to our landing (mean 64 ms on the feed clock).

3. **94 % of the time is after our send.** MEASURED as the remainder.
   - It contains the dump's feed delay plus relay → leader → block.
   - INFERRED: these two cannot be split with today's records (§8).

4. **We lose to the FIRST reacting buyer, not to one pro.** MEASURED:
   - Buys arrive 6× faster than before the dump in its first 20 ms, and 8–10× at 20–50 ms.
   - The first rival buy lands at a median 18–27 ms depending on the client (feed clock; 21–26 ms on the block clock, reacting buys only). On failed buys, 1–4 rival buys of about 0.76 SOL push the price past +5 % at a median 24 ms (feed) or 27–30 ms (block).
   - In 80 % of fails, that crossing buy paid a LOWER CU price than ours. The order is decided by arrival, not by fee.

5. **Per leader client** (feed-clock medians, ms; MEASURED):

   | client | us | first rival | HkQ7 | haqq |
   |---|---|---|---|---|
   | BAM | 29 | 18 | 21 | 33 |
   | Harmonic | 41 | 27 | 34 | 47 |
   | Jito | 54 | 26 | 32 | 42 |

   - On BAM and Harmonic we are about 7–8 ms behind HkQ7 and ahead of haqq.
   - Jito is the weak spot: 21 ms behind HkQ7.
   - Rakurai: 7 of 8 attempts spilled, median 212 ms.

6. **Fills vs fails** (MEASURED): fails are not slower attempts; they come on busier dumps.

   | | fills | fails |
   |---|---|---|
   | our landing (feed) | 38 ms | 43 ms |
   | first reacting rival (B400) | 32 ms | 17.5 ms |
   | rival buys within 50 ms of the dump | 1 | 3 |
   | dump size | 3.2 SOL | 4.2 SOL |

7. **Fix order** (gains INFERRED from the measured guard):
   1. Send leg on Jito leaders: +23–25 fills per 309.
   2. Send leg on Harmonic: +24–25.
   3. Same-slot send leg on all clients: 10 ms faster gives +45–49.
   4. Engine: fire on shreds and move logging off the hot path: +13–21.
   5. Spills that rivals avoided, and Rakurai: up to +16.

   - Distance to the leader is NOT a cause. MEASURED: leaders are 0.13 / 0.19 ms RTT median (FRA / AMS) and relays 0.3–1.3 ms.

## 2. Timeline per attempt (p10 / p50 / p90)

### Wall-clock stages (ms after the dump's first sighting on any of our feeds)

| stage | all | fills | fails |
|---|---|---|---|
| (3) exec-feed wait | 0.4 / 1.3 / 6.2 | 0.4 / 1.3 / 4.4 | 0.4 / 1.3 / 7.2 |
| (4) decision (exec → fire) | 1.0 / 1.4 / 2.3 | 1.0 / 1.3 / 1.9 | 0.9 / 1.5 / 2.4 |
| (5) first write | 1.3 / 2.7 / 7.3 | 1.3 / 2.4 / 5.2 | 1.3 / 2.9 / 8.3 |
| (6) our tx seen (same shred feed) | 20 / 40 / 142 | 19 / 38 / 136 | 22 / 42 / 148 |
| (6) first write → our tx seen | 17 / 37 / 139 | 16 / 34 / 134 | 18 / 39 / 142 |

- (1) Dump position in its block (0–1): .04 / .31 / .72.
- (2) Which feed saw the dump first: kaldera 187, turbo-kaldera 112, erpc 7, executed feed 3.
- (7) Landing: in the dump's slot 240, next slot 68, 4 slots later 1.
- PoH clock: not usable. MEASURED: dump PoH "ms" is 0.1–2.7 in a 212 ms slot, with correlation 0.13 to the block index. It has been broken since Alpenglow.

### Landing distributions (MEASURED)

**All**

| group | n | fill | 1st write ms | landing ms (feed) | landing ms (B400) | same slot |
|---|---|---|---|---|---|---|
| all | 309 | 42% | 1.3/2.7/7.3 | 20/40/142 | 21/58/162 | 78% |
| fills | 129 | 100% | 1.3/2.4/5.2 | 19/38/139 | 21/45/150 | 78% |
| fails | 180 | 0% | 1.3/2.9/8.3 | 22/43/146 | 25/74/164 | 77% |

**By server**

| group | n | fill | 1st write ms | landing ms (feed) | landing ms (B400) | same slot |
|---|---|---|---|---|---|---|
| FRA | 202 | 38% | 1.4/3.4/9.0 | 22/42/147 | 25/60/170 | 78% |
| AMS | 107 | 49% | 1.2/1.9/3.0 | 19/39/133 | 19/56/135 | 77% |

**By leader client (dump slot)**

| group | n | fill | 1st write ms | landing ms (feed) | landing ms (B400) | same slot |
|---|---|---|---|---|---|---|
| bam | 89 | 48% | 1.1/2.0/4.9 | 18/29/48 | 21/40/95 | 90% |
| harmonic | 100 | 45% | 1.4/3.1/8.9 | 31/41/147 | 26/55/149 | 81% |
| jito | 92 | 34% | 1.3/2.8/6.4 | 24/54/139 | 21/82/174 | 65% |
| fd | 12 | 33% | 2.0/7.7/20.2 | 14/23/101 | 34/73/118 | 92% |
| firebam | 8 | 38% | 1.8/3.5/5.5 | 28/33/52 | 28/47/125 | 88% |
| rakurai | 8 | 38% | 2.0/2.8/5.5 | 152/212/224 | 177/252/272 | 12% |

**By landed path** (nonce runs r11+; each path sends its own copy, the first to execute lands)

| group | n | fill | 1st write ms | landing ms (feed) | landing ms (B400) | same slot |
|---|---|---|---|---|---|---|
| nozomi | 66 | 62% | 1.4/2.9/7.5 | 19/40/125 | 20/55/125 | 80% |
| staked-rpc (no tip) | 75 | 7% | 1.4/3.6/9.2 | 29/43/162 | 29/62/165 | 75% |
| helius (Sender) | 14 | 93% | 1.6/3.2/4.3 | 40/121/141 | 27/116/319 | 43% |
| landx-fra3 | 7 | 29% | 2.1/11.1/18.5 | 17/24/40 | 13/36/107 | 100% |
| helius-swqos | 6 | 33% | 1.2/2.0/3.1 | 32/40/101 | 25/73/147 | 83% |
| jito-bundle | 3 | 100% | 1.9/4.9/5.9 | 36/46/55 | 24/37/107 | 67% |
| bolt | 2 | 100% | 4.5/4.7/4.9 | 138/176/214 | 51/160/270 | 0% |

**By run**

| group | n | fill | 1st write ms | landing ms (feed) | landing ms (B400) | same slot |
|---|---|---|---|---|---|---|
| FRA r10 | 73 | 40% | 1.3/2.5/6.7 | 22/39/128 | 21/58/130 | 86% |
| FRA r11 | 5 | 40% | 1.3/3.0/3.9 | 38/41/50 | 34/74/94 | 80% |
| FRA r13 | 23 | 22% | 1.8/4.3/15.1 | 25/42/172 | 23/71/178 | 70% |
| FRA r14 | 63 | 43% | 1.3/3.7/9.0 | 28/43/149 | 26/65/176 | 70% |
| FRA r15 | 38 | 37% | 1.6/4.6/10.9 | 19/42/128 | 29/56/105 | 82% |
| AMS r9 | 7 | 29% | 0.9/1.2/3.1 | 22/33/123 | 28/60/161 | 86% |
| AMS r10 | 56 | 54% | 1.3/1.8/2.8 | 16/35/115 | 22/47/128 | 75% |
| AMS r11 | 3 | 33% | 1.8/1.9/3.5 | 47/112/223 | 65/127/275 | 67% |
| AMS r12 | 7 | 14% | 1.3/2.0/2.4 | 30/37/48 | 30/50/122 | 86% |
| AMS r13 | 31 | 55% | 1.2/1.9/4.0 | 22/46/137 | 18/56/125 | 77% |
| AMS r14 | 3 | 33% | 2.0/2.2/2.8 | 44/64/117 | 37/113/146 | 67% |

### Engine internals (MEASURED)

**Exec-feed wait:**
- FRA 2.2 ms median (p90 7.8) vs AMS 0.7 ms (p90 2.1).
- FRA has worsened: 1.4 ms in run 10, then 2.5–3.5 ms in runs 13–15, with p90 8–14.
- On Firedancer leaders: 6.8 ms (p90 19).

**Decision** (FRA p50, µs):

| part | µs |
|---|---|
| queue | 100 |
| book | 29 |
| score | 122 |
| checks + JSON logs | 348 (550 with the M2 gate, run 15) |
| prepare | 190 |
| all writes | 361 |

**Writes and relay acks:**
- Write order: jito-bundle / landx first, then nozomi +61 µs, helius +99, helius-swqos +104, bolt +106, staked-rpc +156.
- Relay HTTP ack p50: nozomi 0.34 ms, bolt 0.47, helius-swqos 0.51, helius 0.54, jito-bundle 0.94, staked-rpc 3.5.
- HTTP 429 from Helius: 24 attempts (helius 9, helius-swqos 15), 17 of them on Jito leaders.

**Leader targeting:** the engine's leader = the schedule's leader on 309 of 309 attempts.

## 3. Competitors on the same dumps

Each wallet's first buy attempt on each dump (successful or failed); B400 / Bmix medians; MEASURED from the raw chain recording.

| who | dumps | lands (ms) | same slot | before our tx |
|---|---|---|---|---|
| first rival buy (any) | 308 | 23 / 21 | – | – |
| first REACTING rival (more than 3 txs after) | 308 | 24 / 22 | – | – |
| instant (≤ 3 txs, e.g. Dk2jdQ93) | 23 | 1 | 100 % | 23 |
| HkQ7hMjy | 123 | 45 / 41 | 91 % | 56 |
| haqqiUUX | 166 | 59 / 56 | 69 % | 64 |
| 8PgC4ngp | 104 | 54 / 50 | 74 % | 58 |
| 6n2cCJrr | 151 | 55 / 49 | 95 % | 80 |
| 9k78QZyw | 44 | 41 / 38 | 86 % | 31 |
| G9G3dCBG (89 % of its buys fail) | 144 | 61 / 53 | 97 % | 25 |
| A9KKBdLy (97 % fail, spam) | 115 | 37 / 34 | 86 % | 81 |
| any named or cohort wallet, first | 304 | 29 / 26 | 90 % | 267 |
| **us** | 309 | **58 / 51** | 78 % | – |

**On the feed clock** (MEASURED): us 40 ms, first rival 20, HkQ7 29, G9G3dCBG 31, 8PgC4ngp 36, 6n2cCJrr 38, haqq 43.

**Our failed buys** (MEASURED):
- When the guard was first crossed (ms after the dump, p25 / p50 / p75):

  | clock | crossed at |
  |---|---|
  | feed | 10 / 24 / 37 |
  | B400 | 17.5 / 30 / 53 |
  | Bmix | 17 / 27 / 47 |

- How long after that crossing we landed:

  | clock | landed after |
  |---|---|
  | feed | 2 / 14 / 42 |
  | B400 | 7 / 25 / 58 |

  On the feed clock, 46 fails landed within 2 ms of the crossing, mostly in the same burst.
- 13 fails were crossed ≤ 1.6 ms after the dump (≤ 3 txs). Those can't be won by reacting.
- Who made the crossing buy:

  | wallet | crossings |
  |---|---|
  | HkQ7hMjy | 21 |
  | 8PgC4ngp | 17 |
  | 2KtcBCfh | 15 |
  | 6n2cCJrr | 11 |
  | Dk2jdQ93 | 9 |
  | CVPz447t | 8 |
  | haqqiUUX | 4 |

  In total: 37 other cohort wallets and 74 unlisted wallets.
- Rival buys landed before ours: median 4 on fails (plus 3 failed rival attempts), 1 on fills.

**Fastest rivals' paths** (first 3 reacting buys per dump; MEASURED; mixes path speed with bot quality):

| client | paths (median landing) |
|---|---|
| BAM | helius 30 ms; Astralane 25; nozomi 31; no tip 38 |
| Harmonic | helius 29 ms; no tip 41 |
| Jito | helius 33 ms; no tip 33 |

## 4. Root causes, ranked

Fails rescued are INFERRED: our landing is moved on the measured chain guard. Chain-clock numbers come first; the feed clock gives an upper end, because txs arrive there in bursts.

| # | cause | ms lost per average attempt | fails explained (of 180) |
|---|---|---|---|
| 1 | Send leg on Jito leaders | 16 (feed) / 19–20 (block) | 23–25 of 61 Jito fails |
| 2 | Send leg on Harmonic leaders | 13 / 11–12 | 24–25 of 55 Harmonic fails |
| 3 | Same-slot send leg, all clients | most of the 37 ms write → seen | 10 ms: 45–49 (≤ 79); 20 ms: 70–73 (≤ 101) |
| 4 | Spills that rivals avoided (38 attempts) | all spills: 34 % of all delay (feed) | 16 of 41 spilled fails |
| 5 | Exec-feed wait | 3.0 mean, 1.3 median | 8–17 (≤ 44) |
| 6 | Decision | 1.6 mean, 1.4 median | 5–17 (≤ 31); with #5: 13–21 (≤ 56) |
| 7 | Rakurai leaders | 4.3 | 2 of 5 |
| 8 | Distance | – | none: not a cause |

**1. Jito.** MEASURED:
- Same-slot landing 49 ms (feed) vs HkQ7 32 and the first rival 26.
- Write → seen (same slot): 46 ms vs 24 on BAM.
- Spill rate 35%. 19 of those spills were spills that rivals avoided.
- Our copies there:

  | copy | landed | fills | median landing (feed) | next slot |
  |---|---|---|---|---|
  | helius Sender | 14 | 13 | 121 ms | 8 |
  | nozomi | 15 | 0 | 90 ms | 5 |
  | staked-rpc | 21 | 1 | 51 ms | 9 |

  On Jito, nozomi landed only failing buys and staked-rpc 20 of 21.
- Rivals land at 33 ms on Jito through helius or no tip.

**2. Harmonic.** MEASURED:
- 41 ms (feed) vs HkQ7 34.
- nozomi wins 23 of 25 fills.
- helius-swqos never won a fill (3 landings). For haqq, Helius wins 87% on Harmonic.

**4. Spills.** MEASURED:
- 69 of 309 (22%). Median 137 ms (feed) vs 39 ms in the same slot. 60 land in the same leader's next block.
- By time left in the dump's block:

  | time left | spill rate |
  |---|---|
  | under 40 ms | 15 of 16 |
  | 40–80 ms | 15 of 39 |
  | 80 ms or more | 39 of 254 |

- In 38 spills a reacting rival still got into the dump's block (Jito 19, Harmonic 8, Rakurai 7, BAM 3, FireBAM 1). 30 of those 38 failed.
- In 31 spills nobody got in, and 20 of those still filled. That includes 10 of the 15 spills on the first slot of a Jito turn, so that part is structural, not our speed.

**5. Exec-feed wait.** MEASURED: FRA's wait has more than doubled since run 13 (§2). AMS stays at 0.7 ms.

**6. Decision.** MEASURED: checks and JSON logs run before the send: 0.35 ms, and 0.55 ms with the M2 gate.

**Paths and drops.**

MEASURED:
- 70 of 105 nonce fails landed through the tipless staked-rpc copy.
- 1 staked-rpc copy landed 4 slots late and tripped the slot guard (6001). Its other copies never landed.
- 24 attempts got a Helius 429.

INFERRED:
- Tipped copies that pass through builders or bundles are dropped when they would revert.
- So a failed buy's landing time is often the tipless copy's, and our true lateness on fails is somewhat smaller than measured.
- This affects cost (0.0005 SOL per fail) and our measurements more than the fill rate.

**Fee.** MEASURED: AMS at 15M µL/CU (runs 12–14) did not land faster than at 5M. Same-slot write → seen: BAM 27 ms (n=16) vs 21 (n=31); Jito 59 (n=6) vs 46 (n=9). The samples are small; keep fee as a separate A/B lever.

## 5. Upper bound

Our 180 failed buys that would have passed the guard if we had landed like … (MEASURED guard state at that position):

| landing like … | passes |
|---|---|
| the fastest rival buy on that dump | 180 of 180 |
| the fastest REACTING rival | 173 of 180 |
| HkQ7, on its 83 dumps | 33 |
| haqq, on its 118 dumps | 14 |
| every buy at 20 ms (B400 / Bmix) | 125 / 118 |
| every buy at 35 ms (B400 / Bmix) | 75 / 64 |

- The price only crosses the guard when someone buys, so landing before the first rival always fills.
- Matching HkQ7 or haqq is not enough: they are often the crossing buy themselves.

Fills out of 309 (INFERRED; B400 / Bmix):

| scenario | fills | rate |
|---|---|---|
| today | 129 | 42 % |
| engine fix (first write 0.2 ms) | 150 / 142 | 46–49 % |
| + spills land at the end of the dump's slot | 165 / 157 | 51–53 % |
| engine + Jito/Rakurai like our BAM | 174 / 170 | 55–56 % |
| engine + same-slot send leg 10 ms faster + spill fix | 202 / 202 | 65 % |
| … 20 ms faster | 223 / 226 | 72–73 % |
| every buy at 20 ms | 251 / 243 | 79–81 % |

Not measured here: whether those extra fills make money. That is the replay-vs-live reconciliation's job.

## 6. Fixes

Recommendations only. Any send-path or engine change needs the owner's OK. All gains are INFERRED.

**A. Send leg, by client** (the biggest lever)

- **A1. Jito:**
  - Change: route on Jito leaders = helius-swqos 0.0002 (keyed) + a direct no-tip staked/SWQoS copy + nozomi. Keep the keyed helius Sender as one copy. Drop jito-bundle (1 win in 54 Jito nonce fires).
  - Expected gain: 54 → ~30 ms (feed); +23–25 fills per 309.
  - Test: fail-by-design probes (`--dip-probe`, 0.0005 SOL), Jito leaders only, one path per probe, 20+ per path. Compare same-slot share and feed-clock landing. Then a 2 h A/B.
- **A2. Harmonic:**
  - Change: test keyed helius-swqos (no more 429s) next to nozomi and landx.
  - Expected gain: like our BAM → +24–25 fills.
  - Test: same probes.
- **A3. All clients:**
  - Add a direct staked SWQoS copy with no tip. Rivals' no-tip copies land at 33–41 ms.
  - After the A1/A2 probes, prune paths that rarely win fills: bolt (2 of 68 nonce fills) and jito-bundle (3). Keep helius-swqos until it is tested keyed; keyless it got 429s.
  - Pruning saves about 0.1 ms of writes per path; the speed gain has to come from the added direct copy.
  - Expected gain: 10 ms faster → +45–49 fills.

**B. Engine**

- **B1. Fire on the first shred sighting.**
  - Decode the sell from the shred tx and price it on our own curve book. min_out keeps a failed or reordered dump safe; the worst case is a 0.0005 SOL fail.
  - Gain: 1.3 ms median, 3.0 mean, about 6 p90. On FRA about 3 ms, on Firedancer 6.8.
- **B2. Move work off the hot path.** Write the dump/pick JSON logs and run M2 scoring after the sends, and pre-build the nonce variants. Gain: 0.4–0.7 ms.
- **B3. Find out why FRA's executed feed slowed since run 13.** Worth doing even without B1.
- Together B1 and B2 take the first write from 2.7 ms to about 0.3 ms median, and the p90 from 7.3 to about 1 ms.
- Expected gain: +13–21 fills (chain clock; up to 56 on the feed clock).
- Test: a 2 h shadow that logs the would-fire time next to the real fire, then A/B.

**C. Spills and leaders**

- **C1.** Skip Rakurai leaders: 7 of 8 spill, 212 ms median.
- **C2.** Dumps with less than 40 ms left in the block spill 15 of 16 times (5 fills of 16). Too few to matter; leave them.
- **C3.** Jito turn-start spills: no fix needed. They are structural.

**D. Measurement**

- **D1.** Fix the engine's PoH clock (Alpenglow ticks). That gives the leader-side time of the dump and of our tx.
- **D2.** Add a reference shred source to measure the dump's feed delay. Today "feed delay + send leg" (37 ms write → seen) can't be split.
- **D3.** Probe one guaranteed-fail copy per relay, with and without a tip. That proves or kills the revert-drop inference.

## 7. Worked examples (verify on solscan)

**1. FRA r14, 02:11:47 PKT, BAM, FILL via nozomi.**
- Exec-feed wait 1.6 ms, decision 0.8, first write 2.2. Our tx seen at 33.7 ms.
- Landed at idx 132; the dump was at idx 66. That is 35 ms on B400.
- 8GPTNX4j bought at 34.4 ms, right before us. HkQ7 came at 37.1, after us. The guard was crossed at 66 ms.
- Dump: https://solscan.io/tx/4UakUmviwdbCK1jurQe7ygZz13VkvSh163QABRF8avR5NSeemfSMiT3gtRFiJ1w1i3pveHViACM1ATvL5C1Mm7hz
- Our buy: https://solscan.io/tx/5u625CLzt3nfqLABUJsr47Jbca7kJ5fMuttWbBF3y5WAAArxuBWuH6jZM17SPLjhByhdDcnxnhHdrxKZ5wegfszM

**2. FRA r14, 04:05:53 PKT, Harmonic, FAIL via staked-rpc.**
- Exec-feed wait 10.9 ms, decision 2.9, first write 11.5. Our tx seen at 53.5 ms.
- Landed at idx 193; the dump was at idx 25. That is 89 ms on B400.
- Rivals: CVPz447t at 6.9 ms, 9k78QZyw at 26.0. HkQ7 crossed the guard at 57.8.
- Dump: https://solscan.io/tx/5oum8QXR5FvM3waeX2bzbXq7BwAdH2D6pohXAxa6AU5e8NqSqWSMQQPVQ8nuMJHN2x8yX65gCN6tX59KbWadr8w
- Our buy: https://solscan.io/tx/5WXg8GJ47St8SbahD7yQyroKgzVVyZDJgYneWQyQ8QSNCeQtiz5UXrVuzxvjrFbRZqwbUcFnnfwkQHcd3L2pDBQs

**3. FRA r14, 05:15:10 PKT, Jito, FAIL via staked-rpc, a near miss.**
- First write at 1.5 ms. Our tx seen at 47.9 ms.
- haqq bought at idx 160 (42.4 ms), 6n2cCJrr at idx 162 (43.5 ms, the crossing), and we landed at idx 164.
- Dump: https://solscan.io/tx/JP7ybL2BVNwmWzvYymphzMaTKVer8VDVKqiL4n2rF5MrXgjXMWNTMZQRhsjsidpmdV75n5K5fzVicGSEpry6P8s
- Our buy: https://solscan.io/tx/37TmnNg24i9k1NkVVnv14i2BpYQySbj873iXL1GPag7ww66WgE4xp6eeob862c6ZjgEzoqDnicUbHVRTkDvQuz4Z

**4. FRA r13, 01:24:55 PKT, Jito, first slot of the turn, FILL via helius in the next slot.**
- No reacting rival got into the dump's block either.
- Our tx was seen at 121 ms on the feed clock, but B400 says 323 ms. Block clocks are unreliable across slots.
- Dump: https://solscan.io/tx/232f2Qs5caBvUJPan6z4qNYikuut79jtghWP5Rat82AQXp3sXwXSdP38ipv8joXVq9UrLoLEE8zhzshFi9gU4gGZ
- Our buy: https://solscan.io/tx/4YZSn8PnKfzR3rZXNgV6xe3wHPRvxTWD2sRGaw5X4rWTiGdFMC5QnG7qoL1LbqwqYKoxXJ1LBramqQaLYNAP5QQr

## 8. Method and caveats

**Data:**
- Engine records: fire, timing, buy_land, buy_failed, close and tape, plus the .log FAST-ACK lines for all 309 fires.
- The raw recordings `run_20261023_1426` and `run_20261024_1425`: 172 files, every pump tx including failed ones.

**Validation** (MEASURED):
- Dump tx found 309/309, our tx found 309/309.
- Engine fill/fail matches the chain 309/309.
- The curve model predicts our result at our real chain position 309/309.
- The feed-clock version agrees 308/309.

**What-ifs:** our own buy is taken out of later curve states, so it has no price impact on itself.

**Clocks:**
- For same-slot landings, the block clocks read 5–9 ms later than the feed clock (median).
  - B400 squeezes everything past index 400 into the end of the slot, and 54 % of dump blocks have more than 400 txs.
  - Across slots the block clocks can be off by 100 ms or more (example 4).
- The feed clock is real time on our server. Its weakness is bursts: many txs arrive at once, so it overstates what small shifts would rescue. Ranges in this report use both kinds of clock.

**Not measurable today:**
- The dump's feed delay vs our send leg.
- Copies that lost the nonce race; they never reach the chain.

**Times:** PKT.

**Scripts** (`ops/dip/speed/truth/`):

| script | does |
|---|---|
| tl.py | shared helpers |
| a1_engine | engine records |
| a2_chain | raw recording |
| a3_timeline | per-attempt timeline |
| a4_analysis | all tables |
| a5_feedclock | feed clock |
| a6_rank | ranking and scenarios |
| a7_export | CSV |
| a8_tables | report tables |
| run_all.sh | runs everything |

**Data** (`/home/moiz/sniper-data/speed_truth/`):

| file | contains |
|---|---|
| attempts.csv | one row per attempt, every stage |
| analysis.txt | all tables |
| feedclock.txt | feed-clock results |
| rank.txt | ranking and scenarios |
| tables.md | the report's tables |
| timeline.json | per-attempt timelines |
| chain_txs.json | extracted chain rows |
