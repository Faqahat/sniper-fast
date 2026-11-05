# QUIET3 — "will anyone follow us here?" (FILTERS-3, 11-03, PKT)

(Saved by the coordinator from the QUIET3 agent's final message. Offline, read-only; holdout not opened.
DEV = r37..r41 + r42 to 11-01 12:00 PKT (76 h). VAL = r42 11-01 12:00 → 11-02 08:35 (20.6 h, incl. attack).)

## Summary
- Modest, not major: QUIET3 = today's QUIET skip + stop unchanged, plus two arm-time skips.
  - Rule A (T2 only): skip when the token had <= 15 trades in the last 120 s (v2.n_120s) AND the whale has <= 3 dumps in the 24 h
    history (quiet.wh_dumps), only when quiet.rule_on is not false. Engine computes both today.
  - Rule B (T2 + re-arm): skip when the token's creator had our own positions in the last 24 h and ALL of its last <= 3 were
    not followed. Needs one small new map in the engine.
- Proven on realized P&L:
| | DEV (76 h) | VAL (20.6 h) | VAL w/o attack (20 h) |
|---|---|---|---|
| blocked (A / B only) | 158 (110 / 48) | 133 (56 / 77) | 121 (46 / 75) |
| winners lost | 59 (+2.47) | 40 (+1.67) | 37 (+1.62) |
| SOL saved | +2.26 | +3.17 | +1.17 |
| SOL/day | +0.71 | +3.70 | +1.41 |
| saved w/o top 5 | +2.26 | +3.63 | +1.62 |
  Per DEV run: r37 +0.68, r38 +0.07, r39 −0.22, r40 +1.02, r41 +0.55, r42-DEV +0.16. Win rate DEV 52.0→53.6%, VAL 41.2→43.7%.
  No state file (B history empty per run): DEV +2.06, VAL same.
- Not just the attack: A chosen on DEV still blocked 10 of 29 attack trades (+2.0 in 40 min); outside the attack A ≈ 0 on VAL
  (+0.21), B does the work (+0.97 VAL, +0.46 DEV); without its biggest creator (dtrzJPj7) B is still +0.83 DEV / +0.54 VAL.
- ESTIMATE: turning QUIET's own skip off and relying on QUIET3 ≈ 0 → keep QUIET's skip and stop.

## 1. Label (measured)
FOLLOWED = >= 1 buy by another wallet (not us, not the trigger whale, not the arm's holders) after our first buy, up to our last
sell landing (presend_live_tape).
| | followed n / net / each / win | not followed n / net / each |
|---|---|---|
| DEV | 1279 / +28.18 / +22.0 mSOL / 62% | 259 / −8.26 / −31.9 (0 wins) |
| VAL | 544 / +5.61 / +10.3 / 56% | 189 / −6.54 / −34.6 (0 wins) |
Raw recordings agree where they cover. Not-followed share rose DEV→VAL (T2 15→21%, re-arm 21→32%). At arm time these trades
are only a little quieter (median 10–12 vs 16–18 token trades in the last 60 s). Perfect-filter upper bound: 2.6/day DEV,
7.6/day VAL.

## 2. Rule (exact text in FROZEN.json)
A: T2, v2.n_120s <= 15 and quiet.wh_dumps <= 3 (both written at the arm decision from trades before the trigger).
B: any kind; creator's last <= 3 kept positions in 24 h all not followed; a position counts only once max(buy + 3 s, last sell
landing) < trigger time; blocked positions never feed B's history; learned online from our own trades (no fixed list).

## 3. Robustness
A: DEV 110 blocked +1.802 | VAL 56 +2.253 | VAL w/o attack 46 +0.206. B only: DEV 48 +0.458 | VAL 77 +0.921 | 75 +0.966.
VAL by time: 11-01 12–24 +0.675; 11-02 00–08 +0.497; attack 08:00–08:40 +2.002. By kind: DEV T2 +1.975, re-arm +0.285;
VAL T2 +2.756, re-arm +0.417.
A neighbours (DEV / VAL / VAL w/o attack): n<=12,wh<=3 +1.67/+1.27/+0.20; n<=15,wh<=5 +2.05/+1.99/−0.06; n<=10,wh<=3
+1.61/+0.46/+0.35. Rule B "half of last 3" variant dropped (order-dependent; blocked 56 good bwamJzzt trades, −1.67).

## 4. vs today's QUIET
All live trades already passed QUIET, so QUIET3's blocks are extra. QUIET's skip worth (est) ≈ +1.4 DEV, ≈0 VAL. Replacing it
with QUIET3 (est): the QUIET-skipped triggers QUIET3 would let through ≈ DEV −0.33, VAL +0.49 → ≈0. Keep QUIET skip and stop.
Note: live T2 QUIET stop is 5:2 (re-arm 6:2).

## 5. What did not work (do not repeat)
Market-wide "bots awake" (AUC 0.44–0.51, bins disagree DEV/VAL); our own followers' activity / recent follow rate (AUC ~0.5);
token's earlier big sells (80% have none); known bot wallets on the token before the trigger (fbots idea: loses on DEV −0.13..
−2.3 → keep fbots empty); early disarm on slots trigger..+N (loses on DEV almost every variant); small logistic model on 11
features (AUC 0.68/0.67 but only ~+0.4 SOL); time of day / dip size / trigger SOL / curve level (unstable); whale reputation
(+0.27 / +0.32, only +0.19 / +0.14 on top of A+B; log-only candidate).

## 6. Engine changes if wanted (none made)
1. Rule A, no new state: skip "quiet3_a" at the T2 arm where QUIET's skip runs, when n_120s <= 15 and wh_dumps <= 3 and QUIET's
   rule is on (needs --presend-live-quiet-v2-log + the QUIET dump book, both on in r42).
2. Rule B: map creator → (known time, followed) for our own kept positions, pruned to 24 h; label at close from the
   presend_live_tape trades; skip "quiet3_b" at every arm (T2 + re-arm) when the creator (--presend-live-ann) has >= 1 entry and
   all of its last <= 3 are not followed; optional state file.
3. Cheaper first step: log-only quiet3: {a, b, n_120s, wh_dumps, cr_hist} in presend_live_arm / _skip.

## 7. Proven vs estimate
Proven (DEV + VAL, real P&L): DEV +2.26 (+0.71/day), VAL +3.17 (+3.70/day; +1.41/day w/o attack); every DEV run + except r39.
Estimate: QUIET skip off ≈ 0. Untested: holdout. Inference: VAL's extra not-followed losses look like a market change (followers
left, more triggers/hour) that no arm-time feature found predicts.

Holdout command: python3 quiet3_score.py --list --warm r42.presend.jsonl r43.presend.jsonl r44.presend.jsonl r45.presend.jsonl
r46.presend.jsonl (and once without --warm). Scorer sha256 34b2e63276eb553c3515ba59a319faf0cddc083425887f565a11e635dc22cf49.
Files: quiet3/FROZEN.json, quiet3_score.py, s1..s5 scripts, explore/; data /home/moiz/sniper-data/filters3/quiet3/
(score_dev_val.txt lists every blocked trade).
