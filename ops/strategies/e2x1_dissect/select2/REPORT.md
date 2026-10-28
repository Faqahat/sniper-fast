# E2X1 — SELECTION, second pass (agent "select2", 10-28 PKT)

Wallet **E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb** ([GMGN](https://gmgn.ai/sol/address/E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb)).
Working hypothesis (owner): his selection is built from on-chain data with patterns and filters. This pass adds the five feature
families the first pass did not use (trigger wallet, trigger tx shape, token participants, creator/launch, timing) and tests them
the same way: train days 1–5, TEST = day 6 (**10-27 18:41 → 10-28 18:41 PKT**, nothing chosen on it).
Code: this folder (t1–t10). Data: /home/moiz/sniper-data/e2x1_dissect/select2/ (U2.npz features, sim_66.npz, t6_*.json, t7.json, t9.json, t10.json, examples.md).

## Verdict (short)
- **No rule or model from any on-chain family reproduces his selection.** Best model: test AUC 0.90, but at 60 % recall of his
  picks the precision is 3 % and the **picks the rule makes that he did not take lose money at our speed** (−12 to −30 mSOL per
  lot) while **his picks earn** (+10 to +18 mSOL). Pass bar (≥ 60 % recall AND rule-only picks ≥ +2 % per lot) is **not met**.
- **No single family carries the signal.** Adding each new family to the market-shape model moves test AUC by −0.01 to +0.03;
  the only family that helps (+0.03) is **his own position state** (re-entries on tokens he already traded), which is his engine's
  memory, not an external filter.
- **The wallet-quality filter is real but weak:** 51 % of his picks come from wallets he had already followed ≥ 5 times, and
  29 % from the 541-wallet consistent-winner cohort (vs 14 % of look-alike moments). But even for the wallets that trigger him
  most he takes **< 1 % of their trades**, and the trades of theirs he skips lose. Wallet identity narrows the universe 2–3×, not 100×.
- **Grozoe2L is the same engine**: its picks are scored like his by his model except where E2x1 already holds the token
  (58 % of Grozoe-only picks are on tokens E2x1 holds; a model telling the two apart runs on "E2x1 holds" alone). One engine,
  positions split across two wallets.
- **The copiers have no filter of their own**: when active they copy 75 % of his buys (4mYySb7Z, Hj4uACn8); their non-follows
  are downtime (3 of 5 were off on the test day). A model predicting which of his buys a copier takes has AUC 0.45 (chance).

## Data and method (MEASURED)
- Tape: every pump.fun trade 10-22 03:07 → 10-28 18:41 PKT (6.64 d), 24.4 M rows (haqqml fresh tape, cut at the first pass's end
  so days line up; the source tape was being extended while this ran). Raw recordings re-scanned once (t2) for every successful
  pump tx: CU price/limit, tip account → relay, program set ("route"), instruction shape, signers, flags; joined by signature hash:
  **100 % of tape rows matched**.
- Universe: every outside trade e (not E2x1) on a SOL-quoted, non-mayhem curve aged 0–30 min: **13.93 M events**. 45,113
  curves quoted in other pump tokens (decode with sol = 0) are excluded (the first pass kept them as negatives).
- Label y: E2x1 has a BUY on that mint ≤ 1 slot after e. **42,678 positive events** = his 8,069 buys (every trade in the slot
  before a buy is a positive, ~5 per buy). Negatives: 4 % hash sample, weight 25 (unbiased rates). Grozoe2L-trigger rows are
  dropped from the modelling universe (he is the twin). Base take rate **0.39 %**.
- TEST day: 1,286 of his buys (6,649 events) among ~1.77 M events.
- Forward returns g24/g94/g160: market price from the end of slot s+1 to +5 s / +20 s / +34 s. **Sim P&L at our 66 ms**
  (t5, ourspeed method): counterfactual tape without E2x1 + Grozoe, our buy lands 66 ms (live delay shape) after e, guard +5 %,
  size = his tier code (0.7 % / 1.0 % of vSOL, capped 1 SOL; mean 0.49 SOL), exits at +5 / 20 / 34 s and the per-age band,
  phi = 0 / 0.2 (20 % of fast followers' SOL removed). Our live tx cost (~4.5 mSOL per trip) is NOT subtracted below.
- Sim sanity (his picks vs look-alikes, whole tape): his picks at 66 ms **+17.8 mSOL/lot** (34 s, phi 0) / +3.7 (phi 0.2) /
  +12.6 (5 s); sampled look-alike moments −30 / −36 / −18. Same shape as ourspeed's table, so the sim is consistent with it.

## 1. Families and what they add (GBDT, 149 features, TEST day)
Precision at 60 % recall of his picks; base 0.39 %. "MKT" = the first pass's market-shape features (43).

| Model | test AUC | precision @ 60 % recall | @ 25 % recall |
|---|---|---|---|
| MKT only | 0.871 | 2.1 % | 4.1 % |
| MKT + WAL (trigger wallet reputation, 30) | 0.879 | 2.4 % | 5.3 % |
| MKT + TX (trigger tx shape, 24) | 0.867 | 2.1 % | 4.0 % |
| MKT + TOK (participants before e: cohort/pro/good wallets in, 5) | 0.874 | 2.1 % | 4.1 % |
| MKT + OWN (his own state on the token: prior buys, holds, P&L, slots since his sell, 6) | **0.902** | 2.9 % | 6.5 % |
| MKT + CRE (creator history, create-slot bundle, dev buy, metadata, 26) | 0.864 | 2.0 % | 3.9 % |
| MKT + TIM (hour, slot-in-window, leader, his recent activity, 17) | 0.860 | 2.0 % | 3.9 % |
| ALL − WAL | 0.898 | 2.8 % | 6.0 % |
| ALL − OWN | 0.871 | 2.3 % | 4.9 % |
| ALL − TX / − TOK / − CRE / − TIM | 0.904 / 0.900 / 0.903 / 0.906 | 3.0 / 2.9 / 3.0 / 3.1 % | |
| **ALL** | **0.903** | **3.0 % (lift 7.9×)** | 7.3 % |

- OWN is the only family with a real gain (+0.03 AUC): re-entries (34 % of his buys, 45 % of his P&L) are predictable from
  "he traded this token before, sold it N slots ago, price vs his last fill". That is his engine's memory, not a signal we can
  copy without first being in the token.
- WAL adds +0.008 AUC (wallet reputation / his own follow history). TX, TOK, CRE, TIM add nothing; removing TIM even helps.
- Top features by gain (ALL): SOL bought in the trigger slot 0.12, SOL bought in the last 1 s 0.07, token age 0.07, his
  follow-rate on the trigger wallet 0.05 + 0.05, trigger instruction-shape take rate 0.05, slots since his last sell 0.04,
  slot-leader take rate 0.035, CU-price-bucket take rate 0.03, he holds 0.03, slots since his last buy 0.03. Plain-word list
  with examples in section 6.

## 2. Rules (human-readable) and the acid test (TEST day)
Sim P&L in mSOL per lot at our 66 ms, 34 s exit, phi 0 / phi 0.2. (i) rule picks he also took, (ii) rule picks he did NOT
take, (iii) his picks the rule missed. Recall is by event; recall by buy in brackets.

| Rule | recall | precision | picks on test day | (i) his & rule | (ii) rule, not his | (iii) his, missed |
|---|---|---|---|---|---|---|
| GBDT-ALL, cut at 60 % train recall | 0.41 (0.52) | 4.6 % | 58,666 | +9.9 / −2.1 (g94 +1.5 %) | **−15.0 / −25.8** (g94 −3.7 %) | +22.8 / +8.1 |
| GBDT-ALL, cut at 40 % train recall | 0.24 (0.36) | 7.6 % | 20,752 | −1.4 / −12.4 | **−8.5 / −20.4** (g94 −2.6 %) | +23.4 / +9.0 |
| Decision tree depth 4, leaves to 60 % train recall | 0.72 (0.73) | 0.9 % | 531,131 | +8.2 / −5.2 | **−30.2 / −41.3** | +40.9 / +26.7 |
| Tree, best single leaf: SOL-in-slot > 1.0 & his follow-rate on wallet > 0.66 % & he is up on the token & abs impact > 6.5 % | 0.02 (0.05) | 21 % | 602 | −7.5 / −16.8 | −70.6 / −86.0 | |
| Greedy conjunction: SOL-in-slot ≥ 0.54 & not the create slot & trigger not an ExtendAccount tx | 0.59 (0.70) | 1.1 % | 357,246 | +8.0 / −3.6 | **−27.4 / −36.9** | +31.0 / +14.6 |
| Same search without wallet features | identical rule | | | | | |

- At every operating point the picks he did not take lose; the rules only re-find "active young token right now", and his
  skipped look-alikes within that envelope lose exactly as in the first pass.
- The sim's rule-only losses are not a speed artefact: g94 (market price, no fill model) is −2.6 to −3.7 % for (ii) vs +0.4 to
  +1.5 % for (i).
- Train-set check: rule-only picks lose on train too (−22 to −37 mSOL), so the rules were not over-fitted to a lucky day.

**One-feature rules (t9, TEST day; recall / precision / (ii) sim 34 s phi 0):** his follow-count on the wallet ≥ 5: 0.57 /
0.85 % / −20.7; wallet in the 541 cohort: 0.24 / 0.74 % / −19.4; wallet ≥ 200 prior round trips: 0.59 / 0.60 % / −23.7;
wallet prior P&L ≥ +2 %/SOL: 0.60 / 0.64 % / −24.4; ≥ 10 cohort wallets already in: 0.51 / 0.40 % / −27.4; trigger CU
price ≥ 1 M: 0.34 / 0.68 % / −26.5; dev buy ≥ 1 SOL: 0.57 / 0.43 % / −32.0; creator has earlier tokens: 0.51 / 0.46 % /
−36.1; SOL in trigger slot ≥ 1: 0.48 / 1.2 % / −23.2. Nothing is both selective and profitable on its own.
Combination "followed ≥ 5 & ≥ 1 SOL in slot & age < 120 s": recall 0.26, his +3.9, not-his −16.0.

## 3. The trigger wallets (family 1 in detail, MEASURED, whole tape, Grozoe excluded as a trigger)
Take rate = his buys ≤ 1 slot after that wallet's trades / that wallet's universe trades.

| Trigger wallet | times he followed | his take rate (test) | taken: sim 34 s / g94 | skipped: sim 34 s / g94 | cohort 541 |
|---|---|---|---|---|---|
| [9pQQc1xy](https://gmgn.ai/sol/address/9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN) | 738 | 0.69 % (0.78 %) | +4.4 / +3.7 % | −30.9 / −1.9 % | yes |
| ssssswdk | 733 | 0.43 % (0.51 %) | +14.3 / +3.9 % | −29.3 / −0.1 % | yes |
| haqqiUUX | 648 | 0.79 % (0.84 %) | +3.0 / +2.6 % | −24.5 / −1.5 % | yes |
| sssssDdM | 413 | 0.70 % (0.65 %) | +12.4 / +3.3 % | −33.5 / −1.0 % | yes |
| BUkpShoE | 396 | 0.94 % (0.82 %) | +6.6 / +3.7 % | −21.2 / −0.8 % | yes |
| EMKY7r6U | 385 | 0.69 % (0.78 %) | +0.9 / +2.6 % | −18.7 / −0.2 % | yes |
| 9qz7cWBq | 347 | 1.19 % (1.36 %) | −2.3 / +0.5 % | −27.7 / −2.1 % | no |
| 4HgMCR7a | 299 | 3.59 % (3.20 %) | −27.5 / −4.3 % | −41.0 / −3.7 % | no |
| HLU8QbLd | 267 | 2.24 % (2.46 %) | +16.5 / +4.7 % | −28.1 / −2.0 % | no |
| DF7eRXHn | 269 | 1.34 % (1.55 %) | +2.5 / 0.0 % | −13.6 / +0.2 % | no |

- The 10 most-followed wallets give 12 % of his picks at a combined take rate of **0.9 %**. He follows wallets, but only ~1 trade
  in 100 of each — the choice among their trades is the selection, and it is not visible in the trade or the token state.
- 1,280 distinct trigger wallets; 71 % of his picks come from a wallet he had followed before, 51 % from one followed ≥ 5 times.
  INFERRED: a wallet list is part of his engine (as a universe), but the per-trade filter inside it is what earns and that is
  not reproducible here. Full table (25 wallets, full addresses): t10.json.

## 4. Trigger tx shape (family 2)
- Take rate by trigger CU price bucket: best buckets 1.5–2.5 % (81k, 3.26 M, 50 M µlamports; each ≤ 1 % of his picks); by tip
  relay: landx 2.2 %, bolt 2.0 %, glaive 1.2 %, nozomi 1.0 %, jito 0.5 %, astralane 0.47 %; by program set: routers
  `41Pr4Xq…` (+`6gY1osm…` / `L2TExMF…`) 2.0–2.4 % (6 % of his picks), `L2TExMF` alone 0.94 %, `haqqqMGN` 0.78 %, direct
  pump 0.4 %. Direct-pump triggers are 40 % of his picks vs 34 % of the universe.
- These are bot fingerprints (CU price and router identify the same wallets as family 1): target-encoded they add 0.00 AUC
  on top of market + wallet features. No nonce / signer-count effect (take rates within ±0.1 pt of base).

## 5. Creator / launch, participants, timing (families 3–5)
- Creator history (earlier tokens, graduation and dev-sold rates, creator wallet age), create-slot bundle (count, SOL, max,
  cohort members in it), dev buy size, cashback/holder flags, name/symbol/URI shape and host: **no lift** (MKT + CRE 0.864 vs
  MKT 0.871). Dev buy ≥ 1 SOL covers 57 % of his picks at 0.43 % precision; creator with earlier tokens 51 % at 0.46 %.
- Participants before e: ≥ 10 consistent-winner wallets already in covers 51 % of his picks at 0.40 % (base 0.39 %) — he does
  not need the cohort to be in first; "good-record wallets in" and "wallets he followed before in" are equally flat.
- Timing: hour-of-day take rate 0.28–0.54 % (flat), slot-in-leader-window and leader identity/client/country (full leader
  schedule from public RPC, 664 leaders): removing TIM raises test AUC to 0.906. He does not skip leaders.

## 6. The 10 most important features in plain words (ALL model, gain share) with 5 example picks each
Examples: TEST-day picks of his where the feature sits in its "his" direction; GMGN token + trigger wallet links; g94 = market
move 20 s after our entry; sim = 66 ms, 34 s exit, phi 0.2. Features 1, 2, 3, 7, 9, 10 are market/own-state; 4, 5 (his own
follow history on the wallet), 6 (instruction shape of the trigger tx), 8 (slot leader) are the new families.

1. **SOL bought in the trigger slot** (0.12) — his picks sit in slots where ~1 SOL was just bought (median 0.98 vs 0.04).
2. **SOL bought in the last 1 s** (0.07) — median 3.4 SOL vs 0.5.
3. **Token age** (0.07) — 44 % of first buys < 10 s, but re-entries at any age.
4. / 5. **How often he already followed this trigger wallet** (0.05 + 0.05) — median 5 prior follows vs 0.
6. **Instruction shape of the trigger tx** (0.05) — router/bot fingerprint (section 4).
7. **Slots since his last sell on the token** (0.04) — re-entry timing.
8. **Slot leader take rate** (0.035) — spurious: removing all timing features improves the test AUC.
9. **CU-price bucket of the trigger** (0.03) — bot fingerprint.
10. **He already holds the token** (0.03) — adds while holding (4 % of buys).

(example tables appended at the end)

## 7. Grozoe2L and the copiers (MEASURED)
- Events: E2x1 42,678, Grozoe 22,816, both 9,660 (42 % of Grozoe's), Grozoe-only 13,156; tokens: 2,865 of Grozoe's 3,153
  are also his. Grozoe is the trigger of 1,005 of E2x1's buys (2.4 %).
- E2x1's model scores Grozoe-only picks at AUC 0.67 vs 0.90 for E2x1's own picks — but **58 % of Grozoe-only picks are on
  tokens E2x1 holds** (E2x1's own picks: 2.5 %), and a model separating Grozoe-only from E2x1 picks (AUC 0.88) uses
  "E2x1 holds" for 48 % of its gain, "slots since E2x1's buy / his net / his open count" for the rest. INFERRED: one engine with
  shared position state — the second wallet takes the moments the first wallet is already in. Same picks ⇒ same rule.
- Copiers (follow = buy on the mint ≤ 2 slots after his buy): 4mYySb7Z 23 % overall, **75 % when active in the last 5 min**
  (active 29 % of the time); Hj4uACn8 12 % / 74 % (active 15 %); 2QGfyorL 17 % / 25 %; 8T4XXALt 24 % / 30 %; 6nH3jMhH 19 %
  / 35 %. On the test day 4mYy, 2QGf, 8T4X, 6nH3 followed 0 % (off), Hj4u 37 %. Follow rate by his context: first buys 26 %
  vs re-entries 20 %, age < 30 s 27 % vs ≥ 120 s 16 % (4mYy) — a speed effect (older tokens = re-entries they are slower on).
  Follow model (Hj4u, test AUC 0.45): no feature predicts which of his buys they take. **No filter of their own.**

## 8. Caveats (what could still hide a rule)
- Cohort lists (541 winners, 53 pros, 31 snipers, census) were built 10-23 on data overlapping train days 1–2; for the TEST
  day they are causal. They add nothing anyway.
- Create-slot bundle fields read the whole create slot (slightly ahead for the 0.5 % of events inside the create slot).
- Top-N holder share was not computed (per-row balance tracking); dev share and largest-buy share stand in.
- Sim block clock = recorder's max tx index per slot; delay shape = our live pre-send quantiles rescaled to 66 ms median.
- Off-chain inputs (token socials, X/Telegram calls, a private model) remain untested by design (no external fetches).

## Recommendation
Stop searching for his entry rule in on-chain context; three passes (haqq, select, select2) over market, wallet, tx, token,
creator and timing families agree. What is reproducible is the universe he draws from (active young tokens, trades by ~1,300
mostly-bot wallets he has followed before) — but within that universe his 1-in-100 choice is the edge and it does not show up
in anything the chain exposes before his buy. The only on-chain route stays the copy/cluster trade from the first pass
(follow E2x1 + Grozoe2L, exit on his sell), which needs the owner's OK for a paper run.

## Appendix: examples per top feature (t8)
### solin_cur (gain share 0.120) — SOL bought in the trigger slot
- His picks have higher values (median his 0.9778 vs others 0.03781).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 06:47:39 | [2Q7iB8](https://gmgn.ai/sol/token/2Q7iB8eeLyamG5xzQoRWF75CTPqDynLxwLD4eWmKpump) | [7YD8Lwz6](https://gmgn.ai/sol/address/7YD8Lwz6VV9cGwD4t2SvRPLFv7atbbrXtLZHQMdZTaEb) | buy 4.44 SOL (+25.5%) | 10 | 6.889 | -7.2 | -5.7 |
| 10-28 04:16:41 | [D4AMrW](https://gmgn.ai/sol/token/D4AMrW5RnX7PCBrZheY6ReVvEK1F1cDMBH43YjRKpump) | [HVE8996r](https://gmgn.ai/sol/address/HVE8996rtqG8N2sCNaTJZdLBbKW2SrSg2uXjJtNqPGDJ) | sell 0.13 SOL (-0.7%) | 75 | 6.371 | -3.2 | -139.3 |
| 10-28 00:00:22 | [CGpZ27](https://gmgn.ai/sol/token/CGpZ27ERFBpiQ9FWi6ZJ3Qvv63HyzdmDdjPmzPYapump) | [GLsnURrA](https://gmgn.ai/sol/address/GLsnURrAT7WyuDU6mXX1jW9V1N6o1EoEryet6K5noQJj) | buy 0.10 SOL (+0.4%) | 4 | 5.332 | +63.3 | +344.3 |
| 10-28 01:18:35 | [FuGEke](https://gmgn.ai/sol/token/FuGEkeToNUSWpMFPnW94fCG9FSHfinfFuG6K6vD6pump) | [9pQQc1xy](https://gmgn.ai/sol/address/9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN) | buy 0.69 SOL (+2.8%) | 14 | 5.007 | +165.5 | +207.2 |
| 10-28 11:29:39 | [E91q6U](https://gmgn.ai/sol/token/E91q6UuRkV6FqvMvFHGGfpFwnVsoQ5B9JDd5vrYSpump) | [DAYAW4fD](https://gmgn.ai/sol/address/DAYAW4fDY3snUcuQjK4HXeT9VcX68gFBjpcBd6T6Er2x) | buy 2.96 SOL (+11.9%) | 27 | 6.874 | -10.8 | -107.1 |

### solin_1s (gain share 0.072) — SOL bought in last 1 s
- His picks have higher values (median his 3.395 vs others 0.5052).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 10:47:00 | [shhGg4](https://gmgn.ai/sol/token/shhGg43mWXrvgpsMn2A6YehAVXVFw4WkQeJK7XLufwX) | [B4nN6YyF](https://gmgn.ai/sol/address/B4nN6YyF1E9kyqKYn81nAnNhvdwdfs57dCahLDevn2WH) | buy 0.49 SOL (+1.7%) | 149 | 13.94 | +7.5 | +11.2 |
| 10-28 03:44:07 | [G3B1EL](https://gmgn.ai/sol/token/G3B1EL3pQqUew4VogGdTCv9GteusaGHh5WrsSeaFKd7s) | [Rr9o8bzz](https://gmgn.ai/sol/address/Rr9o8bzzYJvYSgZ8ui8j3UGNf5tu9eW66zL52eEjv12) | buy 0.37 SOL (+1.0%) | 26 | 14 | +18.3 | -125.8 |
| 10-28 06:46:19 | [5XPDtJ](https://gmgn.ai/sol/token/5XPDtJC832dptAG1ZVtayP5cRS7SS6x3YZpwLZXXpump) | [HtJ9i3Bs](https://gmgn.ai/sol/address/HtJ9i3BsmakoqAQXXU74zGvPibRpspXETrtP9gZXvqFe) | buy 0.00 SOL (+0.0%) | 6 | 11.22 | +37.0 | -104.2 |
| 10-28 14:26:16 | [HhDLhd](https://gmgn.ai/sol/token/HhDLhdM1CozLjr2yfsjDK7H58EewyCprWRkwbCxCgk7w) | [9nH7Fpth](https://gmgn.ai/sol/address/9nH7FpthjMGRKhEzzBQ2TxBbpdSfnGkFPjxzAUpAnjsU) | buy 3.46 SOL (+11.0%) | 545 | 13.18 | -2.4 | -181.5 |
| 10-28 05:47:25 | [6ntgWk](https://gmgn.ai/sol/token/6ntgWkHa7u7v9zM5gFG1qTtMN4JZPUdsPuEdkZKZWWLD) | [5z8vacma](https://gmgn.ai/sol/address/5z8vacmajbUZAwESsif1NmsHmzN71nNfZxxm3jJzs949) | buy 0.99 SOL (+4.5%) | 9 | 20.08 | -5.2 | -9.6 |

### age_s (gain share 0.066) — token age at the trigger (s since create)
- His picks have lower values (median his 23 vs others 79).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 08:49:07 | [9r4se8](https://gmgn.ai/sol/token/9r4se8prwYVxQMoesJ9GnDVw9Hyjede5TogRuK5ypump) | [DF7eRXHn](https://gmgn.ai/sol/address/DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9) | sell 0.47 SOL (-2.4%) | 5 | 5 | -16.3 | -48.1 |
| 10-28 12:01:13 | [HVUXsF](https://gmgn.ai/sol/token/HVUXsFgCaf9io6xb5FUTpsnTzEjZnuoqQX3N5jWQpump) | [EMKY7r6U](https://gmgn.ai/sol/address/EMKY7r6UekmmR1hREwCaPy835tCDGXGCw8fqibybgqzc) | buy 0.20 SOL (+1.0%) | 5 | 5 | +3.2 | -13.5 |
| 10-27 23:09:28 | [7NVEza](https://gmgn.ai/sol/token/7NVEzaHdsaQkSM8D7HZX9Fp4QEc1Xbey96AQbew2pump) | [EMnteKpX](https://gmgn.ai/sol/address/EMnteKpX2amf6SwQpMnZEfWuUPxrMZo5VpjG18WYZKsn) | sell 0.04 SOL (-0.1%) | 4 | 4 | -1.9 | +55.1 |
| 10-28 14:48:26 | [DcWRXd](https://gmgn.ai/sol/token/DcWRXdFJEwKJzmGuQSpXALz2UkAHJ9HwC4DZrroqpump) | [9pQQc1xy](https://gmgn.ai/sol/address/9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN) | buy 0.69 SOL (+3.9%) | 4 | 4 | -8.3 | -3.3 |
| 10-28 06:36:09 | [77Sjnh](https://gmgn.ai/sol/token/77SjnhEgJRgyhdpBRTx4bRjPwgUudhwXXkVm2M1kpump) | [FDuBX5NZ](https://gmgn.ai/sol/address/FDuBX5NZwNqUfpcFFUDwmEFDgAJvmdanS7qiS2upFAuR) | buy 1.24 SOL (+7.1%) | 3 | 3 | +18.6 | +0.0 |

### u_follow_rate (gain share 0.051) — trigger wallet: E2x1-follow count / prior trades
- His picks have higher values (median his 0.006503 vs others 0).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 10:17:41 | [4aN132](https://gmgn.ai/sol/token/4aN132mR2SHVmtrdKNnpXX27ncFcKpfNpiqct3Txpump) | [98u2mKTo](https://gmgn.ai/sol/address/98u2mKTogrnHFfXdEEjnxyrgctp8jReQBc43fuxFvFR3) | buy 0.10 SOL (+0.4%) | 40 | 0.02439 | -14.1 | -68.4 |
| 10-28 10:51:34 | [4ato6Z](https://gmgn.ai/sol/token/4ato6ZMs611MjFiEUabTs8QxDUbVJ3wCm25dL7gypump) | [3muYDxht](https://gmgn.ai/sol/address/3muYDxhtxKLvBvmwxo2DNVNsjG38LLWMmvhuewvyYPnK) | buy 1.34 SOL (+5.9%) | 4 | 0.02381 | -6.0 | -78.9 |
| 10-27 21:39:41 | [7dy9JA](https://gmgn.ai/sol/token/7dy9JAAjfmq2mFmvAFAs2ihRe1QXBQyp5JVCqm8npump) | [3Kcgq69S](https://gmgn.ai/sol/address/3Kcgq69SatZ7A9d4oDnBVoKU4d5WzCrE9G8aWrxpPf4p) | buy 0.89 SOL (+4.7%) | 19 | 0.02202 | -32.7 | -46.9 |
| 10-28 13:42:45 | [316uME](https://gmgn.ai/sol/token/316uMEKLAHwGi8Qb18zjJbhXpFmnp4gACPdWBsg8HySy) | [BTf4A2ex](https://gmgn.ai/sol/address/BTf4A2exGK9BCVDNzy65b9dUzXgMqB4weVkvTMFQsadd) | buy 1.46 SOL (+8.7%) | 9 | 0.01562 | +11.1 | +0.0 |
| 10-27 19:32:18 | [5JJjzS](https://gmgn.ai/sol/token/5JJjzSrGHZpgFrqYiwuUS2K8FeUUz7df9vvT6iJLpump) | [HM3x6GSB](https://gmgn.ai/sol/address/HM3x6GSBcFgEMcP67eBE1JMQkdyxtT9vbjPrLmJtEnxf) | sell 4.64 SOL (-19.2%) | 8 | 0.0534 | -26.8 | -10.4 |

### u_follow_rate_sm (gain share 0.050) — trigger wallet: smoothed E2x1-follow rate
- His picks have higher values (median his 0.006224 vs others 0.002655).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 00:58:42 | [8cj3mS](https://gmgn.ai/sol/token/8cj3mSqgEavZ4yAkWELHuSjjtzmfqNDAS36618yBmZBi) | [5yNBPneF](https://gmgn.ai/sol/address/5yNBPneFvdeYjj2oiW3Gce2b9EcPwK6QaYWKASxLs8ve) | sell 0.31 SOL (-1.8%) | 5 | 0.01561 | +24.8 | +293.3 |
| 10-28 04:27:42 | [5zyfGY](https://gmgn.ai/sol/token/5zyfGYfX6Sq8fanjGjdvbwnC6MHPdKkmgUR6Whodpump) | [CVaNx3KD](https://gmgn.ai/sol/address/CVaNx3KD8xgdffPEwpJbfeYMs1rkgcAQp2Z5pSkVqXp3) | sell 3.47 SOL (-15.9%) | 42 | 0.01557 | +8.6 | +24.7 |
| 10-28 03:42:28 | [F8wvZ5](https://gmgn.ai/sol/token/F8wvZ5HLxfsvTCz7z6um2T5kyaLkBDUFqXGrqQzupump) | [7eYVJnGA](https://gmgn.ai/sol/address/7eYVJnGAEWQySSTJZU8TfSSG3epVdiw8Q22r3eqARcZu) | buy 1.43 SOL (+5.7%) | 4 | 0.0277 | +56.3 | +163.3 |
| 10-28 03:10:47 | [GsGCZ5](https://gmgn.ai/sol/token/GsGCZ5pcNSasgUtuJnCGzQ6Lq42DG2oDLQMfyAjQpump) | [8VqKttXD](https://gmgn.ai/sol/address/8VqKttXDgU2t3hxtP1sgcHBNc6jv1iDnbDyVzcBxGHsM) | buy 0.30 SOL (+1.5%) | 71 | 0.04962 | +4.0 | +39.4 |
| 10-27 20:09:37 | [9MGMMb](https://gmgn.ai/sol/token/9MGMMbtNPaVKjp2iwydnTM9rZTnGnB77xgUMQnASbJjP) | [8VqKttXD](https://gmgn.ai/sol/address/8VqKttXDgU2t3hxtP1sgcHBNc6jv1iDnbDyVzcBxGHsM) | buy 0.30 SOL (+1.3%) | 4 | 0.04394 | -17.9 | +29.0 |

### tx_ixh_rate — (derived in t6, no raw column)

### my_since_sell_sl (gain share 0.036) — slots since his last sell on the token
- His picks have lower values (median his -1 vs others -1).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 08:34:29 | [4XwXkz](https://gmgn.ai/sol/token/4XwXkzNgcDzuMkPdktuun2nntt8k1sNT11X4u4XYpump) | [GLMRc6UH](https://gmgn.ai/sol/address/GLMRc6UHodEVoAoVyHnph8VSQ1yM3TqLViGymfTdpRKq) | buy 0.08 SOL (+0.3%) | 7 | -1 | -20.6 | +4.9 |
| 10-28 08:13:35 | [6LeGre](https://gmgn.ai/sol/token/6LeGrewSZVozexWNZWJNmFJ4hDA5spKxibWwY4rspump) | [BUkpShoE](https://gmgn.ai/sol/address/BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP) | sell 0.91 SOL (-3.3%) | 6 | -1 | +62.4 | +134.1 |
| 10-28 07:14:53 | [CrryAh](https://gmgn.ai/sol/token/CrryAh8PyBjmJLzS7Xvbn4zWEUoTvA9w2EMaW8XTpump) | [zvViRS8b](https://gmgn.ai/sol/address/zvViRS8biXCk9CZ4DUQfH69nRNs9KdY9WFLcM3VWMPU) | sell 2.07 SOL (-11.3%) | 4 | -1 | +3.6 | -9.1 |
| 10-28 05:10:48 | [5BebuS](https://gmgn.ai/sol/token/5BebuS1gPbmHZpWre9h8rnScUjZZhfuVziq5MrGHpump) | [Grozoe2L](https://gmgn.ai/sol/address/Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ) | buy 0.33 SOL (+1.4%) | 3 | -1 | -63.0 | -145.6 |
| 10-27 23:38:53 | [3um5jn](https://gmgn.ai/sol/token/3um5jn8ybmGHj19qNKXULsKUEYbfdKu7JVcRAqAhpump) | [dKMjeGJ4](https://gmgn.ai/sol/address/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK) | sell 1.90 SOL (-8.6%) | 4 | -1 | -37.3 | -39.2 |

### ld_rate — (derived in t6, no raw column)

### tx_cup_rate — (derived in t6, no raw column)

### my_open (gain share 0.034) — he holds the token
- His picks have lower values (median his 0 vs others 0).

| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |
|---|---|---|---|---|---|---|---|
| 10-28 11:16:12 | [2sEoaH](https://gmgn.ai/sol/token/2sEoaHwAGF9DNWLNgq5gbmKm7rj8pbaPPV5zHmqKpump) | [sssssDdM](https://gmgn.ai/sol/address/sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d) | sell 0.88 SOL (-3.6%) | 15 | 0 | -1.9 | -47.8 |
| 10-28 17:31:41 | [D2ybeQ](https://gmgn.ai/sol/token/D2ybeQxcTNxDMJkwXbY3iaW1u1mTb5AVmCMzqnKRpump) | [CatkiNiJ](https://gmgn.ai/sol/address/CatkiNiJLQCK7ZLn8XGUrMtPbHYXuBETm8fMDWuouKte) | buy 0.79 SOL (+3.9%) | 7 | 0 | +10.2 | -13.1 |
| 10-28 02:10:39 | [3f1w7y](https://gmgn.ai/sol/token/3f1w7yEVvP61Zncm4qX8mDjk3yU5TZscx2ooDEtEpump) | [CVaNx3KD](https://gmgn.ai/sol/address/CVaNx3KD8xgdffPEwpJbfeYMs1rkgcAQp2Z5pSkVqXp3) | buy 1.48 SOL (+6.2%) | 16 | 0 | +11.7 | +0.0 |
| 10-28 15:55:43 | [4fnKiL](https://gmgn.ai/sol/token/4fnKiLpGvWCvUjjE8fc1XXjDEV72azS54Wpu7n1Vpump) | [3Njjkoag](https://gmgn.ai/sol/address/3Njjkoag3KynjE5QrUA7ddswyyRFnd96v9mg9wKuJaG1) | buy 0.99 SOL (+4.9%) | 22 | 0 | +25.7 | +136.8 |
| 10-28 08:40:00 | [J46qG9](https://gmgn.ai/sol/token/J46qG9nF2nF6ei7nyJCBgv455DUk8QgbXE6XZZ24pump) | [ECMtCTbp](https://gmgn.ai/sol/address/ECMtCTbppi5QYLYf4UJuXRnu43op9cRPqdTqkPCfm9KG) | buy 0.99 SOL (+4.5%) | 3 | 0 | -6.5 | +0.0 |
