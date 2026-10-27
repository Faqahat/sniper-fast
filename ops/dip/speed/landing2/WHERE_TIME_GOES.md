# Where our landing time goes (measured waterfall, 10-25)

10-25 ~20:20 PKT. Read-only. **MEASURED** = counted from data. **INFERRED** = my reading or a model.

Data:
- **250 live fires**, the whole nonce era: FRA runs 11–16 (205) + AMS runs 11–14 and 17 (45), 10-25 00:29 → 17:44 PKT. 97 fills, 153 failed buys.
- **7,118 pre-sent buy attempts** (AMS runs 16–17): a large, dump-free sample of the send leg.
- **Chain:** raw recording + `getBlock` for the real size of all 751 blocks involved.
- **Network probes** from both servers, 10-25 19:08–19:15 PKT.

Checks (MEASURED):
- Dump and our tx found on chain for 250 / 250 fires.
- The engine's fill/fail result matches the chain 250 / 250.
- The +5% guard model predicts our result 250 / 250.

---

## Verdict

**Where our median same-block buy's ~39 ms goes** (dump recorded by the leader → our tx recorded):

| Step | ms | Label |
|---|---|---|
| Dump recorded → we see it (shred batching + feed) | ~5–10 | INFERRED |
| Shred → executed feed (we wait for it) | 2.1 | MEASURED |
| Decision (executed feed → first write) | 1.0 | MEASURED |
| Network to the relay | < 0.4 | MEASURED |
| Relay → front/builder → leader records our tx | ~25–30 | INFERRED split of a MEASURED 35 ms |

Network is not a cause. Our relays are 0.10–0.18 ms away (round trip); Constant-K is 0.65 ms from FRA. The validators we fire on have a median 0.37 ms round trip. **Moving servers would buy nothing.**

**Top 3 time sinks vs the pros** (fills are out of 250 fires; SOL/day is INFERRED, see §8):

1. **The send leg after our write, on Jito and Harmonic leaders** (62% of our fires).
   - Our write → seen (same block): BAM 28 ms, Harmonic 36, Jito own-TPU 42, Jito relayer 66. The physical floor is ~5–9 ms (MEASURED).
   - On BAM and Harmonic we are **at par with the named pros**: 0–3 ms behind, paired on the same dumps.
   - On Jito we are **12–15 ms behind them** (21–38 ms on relayer-fronted leaders).
   - Bringing Jito and Harmonic to our own BAM speed saves ~9 ms per average fire: **+23 fills, ~+1.2 to +4.0 SOL/day**.
2. **Spills: 24% of buys land one block late.**
   - Each costs ~63 ms. That is ~15 ms per average fire on the block clock, and 23 ms of our 72 ms mean feed landing.
   - In 36 of 61 spills a rival still got into the dump's block.
   - Spills: **+5 fills** if only the avoidable ones are fixed, **+15** if all are. That is ~+0.3 to +2.4 SOL/day.
   - Partly structural: the leader's first block is short (Jito own TPU spills 10 of 15 there), and dumps with < 40 ms left spill 93% of the time.
3. **Seeing the dump later than the fastest bots** (feed + our engine).
   - Our engine takes 3.2 ms (median) from the first shred to our first write. 2.1 ms of that is waiting for the executed feed.
   - Pre-confirmation feeds show BAM and Harmonic dumps 5–10 ms before shreds (DOC, not measured by us).
   - Engine fix: **+10 fills (~+0.5 to +3.1 SOL/day), free.**
   - Pre-confirmation feeds: **+12 to +27 fills (~+0.6 to +3.3 SOL/day)**, a paid service.

**Why we are behind** (the owner's question):
- **We lose fills to the FASTEST buyer on each dump, not to one pro.**
  - That buyer lands a median 22 ms after the dump (block clock); we land at 57.
  - 94 different wallets were "first" on our 248 dumps.
  - Our +5% guard is crossed at a median 36 ms (p25 19 ms) after the dump, so landing at 57 fails most good dumps. MEASURED.
- **29% of those fastest buys reach our feed < 8 ms after the dump** (9% in the same burst).
  - That is faster than any send → seen round trip we have ever measured (5–9 ms).
  - INFERRED: they are pre-sent, bundled with the dump, or driven by an earlier signal. Reacting to shreds cannot beat them.
- **On Jito, ≥ 85% of our gap is after the send** (MEASURED gap, INFERRED split).
  - On BAM and Harmonic, the before-send share is 2–3 ms if the fast bots read shreds like us, and up to 7–13 ms if they read pre-confirmations. A shadow log of the pre-confirmation feed settles it.

**What it takes** (all need the owner's OK; the gains are INFERRED and not additive):

| Fix | Fires it touches | Gain | Cost |
|---|---|---|---|
| Jito own-TPU: a faster plain-tx path (probe direct staked QUIC, keyed helius swqos-only, and the private relays that win on Jito) | 25% | +11 fills | relay sign-ups / tips |
| Jito relayer leaders: Jito block-engine `sendTransaction` (skips the 50 ms hold), or skip these leaders | 6% | +2 fills | tip per landed tx |
| Harmonic: builder-direct path (nozomi first; probe speedlanding / astralane) | 38% | +10 fills | tips |
| Pre-confirmation feeds (BAM via Helius, Harmonic via Triton); shadow-log first | 62% | +12 to +27 fills | Helius credits; Triton unknown |
| Engine: fire on the first shred, write logs after the send (dip14) | 100% | +10 fills | free |
| DoubleZero-class shred feed (1.4 ms) | 100% | +6 fills | $1.5K/mo ≈ 0.5 SOL/day at $100.76 |

Notes on the fixes:
- The dip14 engine fix is built. Its shadow covered only 7 of 39 picks, so fix that coverage first.
- DoubleZero is about break-even on its cost.
- **Not worth buying:** a closer server or colocation (already sub-ms), stake (the fronts rank by arrival and fee), bigger tips.

**Combined** (engine + Jito and Harmonic at our BAM speed + avoidable spills): −21 ms per average fire, +35 fills (39% → 53%), **~+1.8 to +7.7 SOL/day**. INFERRED, one day of fires.
- Even then, on BAM we stay 7–21 ms behind the fastest buyer.
- Landing first on every dump (the ceiling) would need −43 ms per average fire, for +139 fills.

---

## 1. Waterfall, all fires (MEASURED, ms: p50 / p75 / p90)

Wall-clock stages run from the dump's first sighting on any of our feeds.
- **Feed landing** = our tx's first sighting minus the dump's (real time on our server).
- **Block landing** = the chain position clock: slot × 212 ms + index ÷ the block's real size.

| Stage | all 250 | FRA 205 | AMS 45 |
|---|---|---|---|
| Shred → executed feed (wait) | 2.1 / 3.9 / 7.2 | 2.4 / 4.7 / 8.3 | 0.9 / 1.4 / 3.0 |
| Executed feed → first write | 1.0 / 1.4 / 1.8 | 1.0 / – / 1.8 | 1.0 / – / 1.7 |
| **First write leaves** | **3.2 / 5.2 / 8.8** | 3.5 / 5.7 / 9.3 | 2.0 / 2.9 / 3.9 |
| First → last write (all paths) | 0.22 / – / 0.33 | | |
| Relay HTTP ack (nozomi) | 0.32 / – / 1.30 | | |
| **Write → our tx seen, same block** | **35 / 49 / 78** | 35 / 47 / 73 | 37 / 57 / 108 |
| Feed landing, all | 44 / 96 / 150 | 44 / 95 / 154 | 42 / 104 / 134 |
| Feed landing, same block | 39 / 54 / 95 | | |
| **Block landing, all** | **57 / 92 / 145** | 57 / 92 / 152 | 61 / 94 / 127 |
| Same block | 76% | 75% | 78% |
| Fill rate | 39% | 38% | 44% |

- **Mean feed landing 72 ms** = first write 4.8 + write → seen 67. Spills are 23 ms of that mean (same-block mean 48, spilled mean 143).
- **Decision parts** (µs, p50 / p90): queue 104 / 561, book 29 / 48, score 129 / 362, checks + logs 402 / 873, prepare 203 / 308, writes 463 / 863.
- **FRA waits 2.4 ms for the executed feed vs AMS 0.9.** The run 16 feed-lag records say this is on the provider's side, not ours.
- **Fills vs failed buys:** first write 3.3 vs 3.1. Block landing 52 vs 62. Fails are not slower sends; they are on busier dumps.

## 2. Splits (MEASURED, ms: p50 / p75 / p90)

### By leader client and TPU front

| Group | fires | fill | first write | write → seen (same block) | feed landing | block landing | same block |
|---|---|---|---|---|---|---|---|
| BAM | 61 | 46% | 2.7 / 4.4 / 5.6 | 28 / 38 / 43 | 34 / 42 / 70 | 42 / 58 / 80 | 89% |
| Harmonic | 94 | 38% | 3.7 / 6.6 / 9.3 | 36 / 48 / 105 | 43 / 102 / 148 | 54 / 83 / 128 | 80% |
| Jito own TPU | 62 | 34% | 3.5 / 5.3 / 7.4 | 42 / 53 / 80 | 58 / 134 / 183 | 67 / 143 / 204 | 61% |
| Jito relayer | 16 | 31% | 2.1 / 3.0 / 3.6 | 66 / 118 / 129 | 92 / 124 / 128 | 100 / 127 / 135 | 69% |
| Firedancer | 11 | 45% | 3.2 / 11.7 / 18.8 | 11 / 18 / 22 | 24 / 41 / 125 | 66 / 73 / 128 | 82% |
| Rakurai | 5 | 20% | 4.0 / 5.0 / 6.0 | 60 (n=1) | 202 / 217 / 222 | 210 / 248 / 263 | 20% |
| Agave | 1 | 1 fill | 3.5 | 13 | 17 | 43 | 1 of 1 |

### By the dump's position in its block (real block size)

| Quarter | fires | fill | first write | write → seen (same block) | feed landing | block landing | same block |
|---|---|---|---|---|---|---|---|
| Q1 (first 25%) | 86 | 41% | 2.5 / 4.5 / 6.5 | 39 / 65 / 121 | 44 / 102 / 140 | 71 / 107 / 178 | 91% |
| Q2 | 69 | 36% | 4.0 / 6.7 / 9.7 | 35 / 45 / 68 | 41 / 61 / 124 | 52 / 70 / 134 | 91% |
| Q3 | 58 | 34% | 3.5 / 5.6 / 8.0 | 30 / 41 / 55 | 43 / 74 / 140 | 48 / 85 / 125 | 71% |
| Q4 (last 25%) | 37 | 46% | 3.5 / 4.5 / 6.4 | 25 / 34 / 39 | 78 / 153 / 213 | 51 / 98 / 163 | **19%** |

- The block clock reads 13 ms later than the feed clock in Q1 (MEASURED). Early in a block, the index runs ahead of real time.
- Same-block feed landing by quarter: Q1 42, Q2 40, Q3 36, Q4 28 ms.

### By the copy that landed

With nonce, each path sends its own copy and the first to execute lands.

| Copy | landed | fills | write → seen (same block) | block landing | same block |
|---|---|---|---|---|---|
| staked-rpc (no tip) | 115 | 6 | 38 / 53 / 96 | 58 / 90 / 138 | 77% |
| nozomi | 92 | 60 | 31 / 41 / 69 | 52 / 82 / 126 | 77% |
| helius 0.001 (Sender) | 24 | 22 | 41 / 60 / 134 | 75 / 163 / 217 | 62% |
| landx (UDP) | 10 | 4 | 19 / 23 / 34 | 55 / 74 / 129 | 100% |
| helius-swqos | 4 | 0 | 32 | 92 / 121 / 149 | 50% |
| jito-bundle | 3 | 3 | 44 | 52 / 64 / 71 | 67% |
| bolt | 2 | 2 | – | 162 / 218 / 252 | 0% |

**Write → seen by copy × client** (same block, median ms, with the number of landings):

| Copy | BAM | Harmonic | Jito own | Jito relayer | Firedancer |
|---|---|---|---|---|---|
| nozomi | 23 (20) | 32 (35) | 16 (5) | 111 (7) | 7 (2) |
| staked-rpc | 28 (31) | 40 (36) | 48 (22) | – | – |
| helius 0.001 | – | – | 39 (11) | 51 (4) | – |
| landx | 24 (1) | 42 (2) | – | – | 18 (7) |

- **Relay HTTP ack** (p50 / p90 ms): nozomi 0.32 / 1.30, helius 0.48 / 1.23, helius-swqos 0.49 / 1.75, jito-bundle 0.97 / 1.99, **staked-rpc 3.67 / 8.37**.
- **Non-200 replies:** helius-swqos 12, helius 6.
- **Bias:** the protected copies (nozomi's builder leg, Helius Sender) cannot land a failing buy. So failed buys land via the slow unprotected copy, and per-copy speeds here are biased. Only one-path probes can rank paths cleanly.

### By leader window slot

Under Alpenglow, block 1 of a leader's 4-slot window records for ≤ 144 ms.

| Window slot | fires | fill | block landing | same block |
|---|---|---|---|---|
| 1 | 58 | 41% | 60 / 123 / 209 | 66% |
| 2 | 71 | 44% | 59 / 97 / 138 | 79% |
| 3 | 60 | 27% | 54 / 82 / 138 | 78% |
| 4 | 59 | 44% | 52 / 71 / 109 | 81% |

Spills in window slot 1 vs slots 2–4:

| Client | Slot 1 | Slots 2–4 |
|---|---|---|
| Jito own TPU | 10 / 15 | 14 / 47 |
| Harmonic | 8 / 22 | 11 / 72 |
| BAM | 1 / 15 | 6 / 46 |

## 3. Spills (MEASURED)

- **61 of 250 (24%)** land in a later block, at a median 114 ms (block clock); 49 of them in the same leader's next block.
- In **36 of 61** a reacting rival still got into the dump's block (avoidable). In 25, nobody reacting got in (structural).

| Time left in the dump's block | fires | our spill | first reacting rival got in | best named pro got in |
|---|---|---|---|---|
| 0–40 ms | 28 | **93%** | 67% | 22% |
| 40–80 ms | 37 | 38% | 76% | 70% |
| 80–120 ms | 51 | 18% | 92% | 91% |
| 120–212 ms | 134 | 9% | 98% | 95% |

## 4. The pros on the same dumps (MEASURED)

Each wallet's first buy attempt (ok or failed). "Reacting" = more than 3 txs after the dump in its block, or a later block.

### P1. Who lands where (block clock, ms after the dump)

| Who | dumps | p25 / p50 / p75 | same block | ahead of us | our lag, paired p25 / p50 / p75 |
|---|---|---|---|---|---|
| **us** | 250 | 36 / **57** / 92 | 76% | – | – |
| first rival (any) | 248 | 7 / 20 / 40 | 90% | 92% | 11 / 27 / 55 |
| **first reacting rival** | 248 | 10 / **22** / 43 | 90% | 92% | 9 / **25** / 54 |
| first cohort bot | 234 | 20 / 35 / 68 | 85% | 69% | −2 / 11 / 41 |
| **best named pro** | 223 | 26 / **42** / 66 | 83% | 67% | −1 / **6** / 21 |
| HkQ7hMjy | 73 | 27 / 51 / 85 | 89% | 42% | −7 / −2 / 9 |
| haqqiUUX | 118 | 39 / 63 / 115 | 65% | 35% | −11 / −1 / 5 |
| 8PgC4ngp | 100 | 29 / 46 / 86 | 77% | 59% | −3 / 5 / 18 |
| 6n2cCJrr | 113 | 39 / 52 / 77 | 96% | 58% | −6 / 2 / 11 |
| 9k78QZyw | 25 | 30 / 38 / 59 | 96% | 80% | 13 / 30 / 60 |
| G9G3dCBG | 99 | 43 / 60 / 99 | 98% | 15% | −20 / −5 / −2 |

- The first reacting rival's buy succeeded on 204 of 248 dumps; 94 distinct wallets.
- Most often first: 6n2cCJrr 19, 8PgC4ngp 19, CVPz447t 17 (4 ok), 2KtcBCfh 14, 7PedQZmc 14.

### P2. By leader client (block clock, median ms)

| Group | us (same block) | first reacting rival (same block) | best named pro (same block) | our lag vs first reacting, paired | our lag vs best pro, paired |
|---|---|---|---|---|---|
| BAM | 42 (89%) | 19 (97%) | 38 (86%) | 21 | **2** |
| Harmonic | 54 (80%) | 23 (89%) | 44 (81%) | 22 | **3** |
| Jito own | 67 (61%) | 21 (85%) | 44 (84%) | 40 | **15** |
| Jito relayer | 100 (69%) | 43 (81%) | 65 (77%) | 62 | **38** |
| Firedancer | 66 (82%) | 19 (90%) | 30 (90%) | 38 | 22 |
| Rakurai | 210 (20%) | 28 (100%) | 39 (100%) | 183 | 183 |
| all | 57 (76%) | 22 (90%) | 42 (83%) | 25 | 6 |

### P3. By the dump's position in its block (block clock, median ms)

| Quarter | us (same block) | first reacting rival (same block) | best named pro (same block) | lag vs first reacting | lag vs best pro |
|---|---|---|---|---|---|
| Q1 | 71 (91%) | 31 (99%) | 53 (95%) | 32 | 7 |
| Q2 | 52 (91%) | 22 (96%) | 39 (97%) | 22 | 6 |
| Q3 | 48 (71%) | 20 (84%) | 32 (81%) | 22 | 7 |
| Q4 | 51 (19%) | 15 (67%) | 44 (28%) | 27 | 1 |

In Q4, the best pros spill like us (28% same block). Only the very fastest get in.

### P4. Same feed clock, paired on the same dumps (our landing minus theirs, ms: p25 / p50 / p75)

Rivals here are successful buys only.

| Group | vs first reacting rival | vs best named pro | our first write |
|---|---|---|---|
| BAM | 0 / 7 / 22 | −1 / **0** / 4 | 2.7 |
| Harmonic | 2 / 8 / 38 | −1 / **2** / 9 | 3.5 |
| Jito own | 4 / 31 / 70 | −1 / **12** / 45 | 3.5 |
| Jito relayer | 2 / 52 / 98 | 0 / **21** / 56 | 2.5 |
| Firedancer | 2 / 8 / 15 | −8 / 2 / 9 | 3.2 |
| all | 1 / 16 / 42 | −1 / 2 / 17 | 3.1 |

- The feed clock squeezes txs that arrive in one burst together. The block clock assumes an even pace through the block. The real gap lies between the two (§4 P2 vs P4).
- **The deadline:** our guard is first crossed (block clock, p25 / p50 / p75):

  | Group | crossed at (ms) |
  |---|---|
  | all | 19 / 36 / 71 |
  | BAM | 17 / 29 / 56 |
  | Harmonic | 21 / 41 / 76 |
  | Jito own | 21 / 36 / 83 |

  - It is crossed inside the dump's block on 72% of dumps.
  - Of our 153 failed buys, 39 landed within 10 ms after the crossing and 61 within 20 ms.
- **Fastest successful reacting buy, feed clock** (p10 / p25 / p50 ms):

  | Group | p10 / p25 / p50 | arrives < 8 ms after the dump |
  |---|---|---|
  | BAM | 3.0 / 7.8 / 20.6 | 26% |
  | Harmonic | 0.7 / 3.5 / 31.0 | 35% |
  | Jito own | 1.6 / 7.3 / 27.5 | 26% |
  | Firedancer | 0.8 / 2.6 / 8.3 | 50% |
  | all | – | 29% |

## 5. Before vs after our send (bound)

Gap = paired median lag behind the fastest reacting buyer, on the feed / block clock. Our before-send part = first write (MEASURED).
- Rivals' split is INFERRED.
- Assumption A: they read shreds like us, with a ~0.5 ms engine.
- Assumption B: they read pre-confirmations (5–10 ms earlier, DOC; BAM and Harmonic only).

| Client | gap (ms) | our before-send | A: before / after | B: before / after | after-send share (A / B) |
|---|---|---|---|---|---|
| BAM | 7 / 21 | 2.7 | 2.2 / 5–19 | 7–12 / 0–14 | 69–90% / 0–67% |
| Harmonic | 8 / 22 | 3.5 | 3.0 / 5–19 | 8–13 / 0–14 | 62–86% / 0–64% |
| Jito own | 31 / 40 | 3.5 | 3.0 / 28–37 | no Jito pre-conf: ≤ 4.5 / ≥ 27 | **≥ 85%** |
| Jito relayer | 52 / 62 | 2.5 | 2.0 / 50–60 | ≤ 4 / ≥ 48 | **≥ 90%** |

For Jito, "before" allows a 1.5 ms better shred feed (DoubleZero-class).

Floors (MEASURED): the fastest write → seen we ever saw:

| Client | lowest | p10 |
|---|---|---|
| BAM | 8.2 | 17.6 |
| Harmonic | 6.6 | 26.5 |
| Jito own | 8.8 | 26.4 |
| Jito relayer | 37 | – |
| Firedancer | 4.9 | 5.1 |

- Pre-sent attempts: lowest 6.6–10.9 ms.
- So the round trip (send → leader → shreds → us) can be ≤ 5–9 ms. Our median 35 ms is mostly waiting at fronts and builders:
  - BAM ~20 ms rounds;
  - Harmonic 50 ms buffers;
  - the Jito relayer 50 ms hold;
  - on Jito own-TPU, a ~20 ms excess on our path that the rivals do not have.

## 6. The send leg on 7,118 pre-sent attempts (MEASURED)

- One path (helius-ps), 1000 µL/CU, 0.0002 tip, sent at random points in the slot, AMS.
- "Same slot" = landed in the slot it was sent in.

| Client | n | same slot | send → seen, same slot (p25 / p50 / p75) | later slots p50 |
|---|---|---|---|---|
| BAM | 2,405 | 33% | 35 / 47 / 65 | 139 |
| Harmonic | 2,080 | 48% | 41 / 59 / 77 | 89 |
| Jito own TPU | 903 | 47% | 35 / **45** / 60 | – |
| Jito relayer | 447 | 33% | 76 / **112** / 124 | – |
| Firedancer | 930 | 40% | 30 / 51 / 74 | 105 |
| all | 7,118 | 41% | 36 / 52 / 74 | 117 |

- **The Jito relayer hold costs ~67 ms** on this path (112 vs 45).
- Firedancer via Helius (51 ms) is much slower than our landx / nozomi copies there (7–18 ms): path matters per client.
- Relay ack 0.4 ms (all HTTP 200); build 266 µs; write 46 µs.

## 7. Network placement (MEASURED 10-25 19:08–19:15 PKT)

ICMP min round trip in ms; TCP connect is within +0.05–0.3 of it. Probes ran at 1 per second per target, 8 ICMP + 4 TCP each.

| Endpoint (our region) | from FRA | from AMS |
|---|---|---|
| nozomi (fra2 / ams1) | 0.10 | 0.16 |
| helius sender (fra / ams) | 0.12 | 0.16 |
| Jito block engine (frankfurt / amsterdam) | 0.12 | 0.13 |
| Harmonic TPU relay / block engine | 0.11 / 0.13 | 0.17 / 0.18 |
| bolt, astralane, landx (haan: FRA only) | 0.10–0.11 | 0.17–0.18 |
| erpc shreds (fra6) | 0.16 | 5.92 (cross-region) |
| **Constant-K** (staked-rpc, rpc, kaldera feeds) | **0.62–0.65** | 0.23–0.25 |
| Same services in the other region | 5.8–7.5 | 5.8–7.4 |

**Leaders we fired on** (RTT from the server that fired):
- Their front (TPU): median 0.13 ms, p90 0.71.
- **The validator itself (gossip IP): p10 / p50 / p90 0.12 / 0.37 / 1.19 ms.** 15 of 240 fires had a validator more than 2 ms away.
- Exception: 5 FRA fires on BAM leaders whose BAM node is in Frankfurt (0.13 ms) but whose validator is 13–37 ms away. The near list judges a leader by its front's RTT, not the validator's.
- By client (front / validator, median ms):

  | Client | front | validator |
  |---|---|---|
  | Harmonic relay | 0.10 | 0.36 |
  | Jito own TPU | 0.13 | 0.14 |
  | BAM | 0.13 | 0.44 (p90 13) |
  | Jito relayer | 0.60 | 0.64 |
  | Firedancer | 0.38 | 0.37 |
  | Rakurai | 9.7 | 9.7 |

- **Unique leaders:**
  - FRA 68: 53 under 1 ms, 5 at 1–5 ms, 5 at 5–15, 3 at ≥ 15.
  - AMS 32: 25 under 1 ms, 6 at 1–5, 1 at ≥ 15.

**Verdict:** co-located for 94% of our fires (validator ≤ 2 ms round trip; median 0.37 ms). Distance is not a time sink.

**Coverage** (not speed): of the next ~3,000 slots, validators under 2 ms are 36% of slots from FRA and 21% from AMS.

## 8. Ranking (extra fills = a what-if scenario read on the MEASURED chain guard; SOL/day INFERRED)

**Guard pass rate if every buy landed d ms after the dump** (block clock, these 250 fires, MEASURED):

| d (ms) | 0 | 5 | 10 | 20 | 30 | 35 | 40 | 50 | 60 | 75 | 100 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 100% | 93% | 88% | 78% | 64% | 60% | 54% | 45% | 42% | 36% | 31% |
| BAM | 100% | 90% | 89% | 69% | 56% | 51% | 46% | 41% | 38% | 33% | 30% |
| Harmonic | 100% | 96% | 87% | 78% | 69% | 66% | 57% | 47% | 45% | 39% | 32% |
| Jito own | 100% | 90% | 87% | 82% | 60% | 56% | 52% | 45% | 42% | 35% | 32% |

Earlier rows (SPEED_TRUTH, 309 fires): 10 ms 85–93%, 20 ms 76–81%, 35 ms 51–61%, 50 ms 38–47%. Same shape.

| # | Time sink | fires hit | ms saved per hit fire | ms per average fire | fills (now 97 / 250) | SOL/day |
|---|---|---|---|---|---|---|
| 1 | Send leg, Jito own TPU → our BAM level | 62 | 14 | 3.5 | +11 | +0.6 to +1.6 |
| 1 | Send leg, Harmonic → our BAM level | 94 | 8 | 3.0 | +10 | +0.5 to +1.8 |
| 1 | Send leg, Jito relayer → our BAM level | 16 | 39 | 2.5 | +2 | +0.1 to +0.6 |
| 2 | Spills, avoidable (rival got in) → end of the dump's block | 36 | 68 | 9.7 | +5 | +0.3 to +1.4 |
| 2 | Spills, all | 61 | 63 | 15.4 | +15 | +0.8 to +2.4 |
| 3 | Seeing: pre-confirmation feed (BAM + Harmonic) | 155 | 5–10 | 3.1–6.2 | +12 to +27 | +0.6 to +3.3 |
| 3 | Engine: shred fire + logs after the send | 250 | 4.0 | 4.0 | +10 | +0.5 to +3.1 |
| 4 | DoubleZero-class shred feed | 250 | 1.4 | 1.4 | +6 | +0.3 to +1.1 |
| 5 | Network / location | – | < 0.4 | ~0 | 0 | 0 |
| – | Reference: send leg 10 ms faster everywhere | 250 | 10 | 10 | +40 | +2.1 to +5.3 |
| – | Reference: 20 ms faster everywhere | 250 | 20 | 20 | +63 | +3.3 to +7.6 |
| – | **Package: rows 1 + engine + avoidable spills** | 250 | – | **21** | **+35** | **+1.8 to +7.7** |
| – | Ceiling: just before the first reacting rival | 228 | 47 | 43 | +139 | – |

How SOL/day was converted (INFERRED, use it to rank, not as a forecast):
- **Low:** extra fills × ~30 mSOL each, at ~433 fires/day (the nonce-era fire rate of both servers).
  - 30 mSOL is the marginal value per extra fill implied by the corrected replay's fixed-landing rows near our speed (22–48 mSOL).
- **High:** the corrected replay's "X ms faster" curve (RECON.md: now +1.06; 5 / 10 / 20 ms faster → +4.9 / +6.4 / +8.7), times the share of fires a fix touches.
  - It is steep in the first 5 ms because it reorders txs inside one feed burst, so it flatters small gains.
- **Caveats:**
  - VM1's live check found landing-distribution replays optimistic by ~5 mSOL per fire.
  - Rows overlap and do not add up: a faster send leg also removes spills.

## 9. Method, caveats, files

**Clocks:**
- Wall = our server (writes: monotonic → real via a bracket of ±21 µs FRA / ±33 µs AMS).
- Feed = first sightings on our feeds.
- Block = slot × 212 + index ÷ real block size, from `getBlock` for all 751 blocks.
- Block minus feed for our same-block landings: p10 / p50 / p90 = −16 / +7 / +37 ms. Read both clocks.

**"Seeing" (dump recorded → our first shred)** cannot be measured without a leader clock. The 5–10 ms is INFERRED from three things:
- our write → seen floors (5–9 ms, which include it);
- the 10-19 pcap study (~10 ms of leader shred batching);
- Helius / BAM docs (pre-confirmations 5–10 ms before shreds).

**Not measured here** (other agents): the competitors' paths and which relays win (forensics); prices and sign-ups of the services (market scan).

**Times:** PKT. No transactions, no engine starts, no config changes. RPC: 4 small calls plus 753 `getBlock` at ≤ 4/s.

**Scripts** (`ops/dip/speed/landing2/`):

| Script | Does |
|---|---|
| `l1_engine.py` | engine records |
| `l2_chain.py` | raw recording |
| `l6_blocks.py` | real block sizes |
| `l3_timeline.py` | per-fire timeline, guard sequence |
| `l4_tables.py`, `l4b_more.py` | tables |
| `l5_presend.py` | send leg on pre-sent attempts |
| `l7_rank.py` | what-ifs, ranking |
| `n1_targets.py`, `n2_probe.py`, `n3_analyze.py` | network |

**Data** (`/home/moiz/sniper-data/landing2/`):

| File | Contains |
|---|---|
| `timeline.json` | one row per fire |
| `fires_engine.json` | engine records per fire |
| `chain_txs.json` | extracted chain rows |
| `block_sizes.json` | real block sizes |
| `presend_rows.json` | pre-sent attempts |
| `probe_{FRA,AMS}*.jsonl` | network probes |
| `tables*.txt`, `rank.txt`, `network.txt`, `presend.txt` | raw outputs |
