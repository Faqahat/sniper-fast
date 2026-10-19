# Buy size / fee / exit decision — 2026-10-19 (data: /root/comp/wal/*_rows.json, wan.py)
Measured over the last 24 h (4yFAz: 57 h):
| wallet | buys/h | size SOL | size set by | landing fee | position (create slot) | exit | PnL/trade | SOL/day | on rule-2 |
|---|---|---|---|---|---|---|---|---|---|
| dKMjeGJ4 | 8.4 | 4.94 (130x) / 7.90 (61x) | dev buy (weak, R2 .14); NOT liq/MC | tip 0.10 / 0.20 = ~2.1-2.6% of size (Helius sender) | 80% same slot, pos med 51 | 30% at 1 s (1.21x), then ~15% every ~3 s, out by ~16-18 s | +8.0% mean, +2.0% med, 54% win | +99.8 | 33 trades +8.1% mean +5.2% med, +14.9 SOL |
| 4yFAz7dp | 9.6 | tiers 0.49-2.93 (med 1.78) | not liq/MC (R2<.04) | med 0.02; 0.06 @3 SOL (~1-3%) | 76%, pos med 75 | 33% at ~2 s if up; all out ~3 s if flat; ladder 33/23/15/10% | +3.4% / -1.6% med, 44% | +27.9 | 12 trades +7.8% |
| 9XPMCaxt | 2.5 | 0.99/1.98/2.96/3.95 (x0.494) | not liq/MC/dev | 0.024 @1, 0.06 @2, 0.11 @3 (~2.5-3%) | 61%, pos med 110 | 50% at 1 s (1.12x), rest at 2 s | +3.2% / +0.6%, 51% | +4.8 | 5 trades +1.1% |
Confidence factor = SIZE TIER; fee scales with size (~2-3% of buy) for all three. Fee does NOT predict outcome (corr ~0).
Bigger tier wins more: dK 7.9 tier +12.1%/+5.7% med vs 4.94 tier +6.4%/-2.0%; 4yFAz >=1.5 SOL tiers positive, <0.75 negative.

## 9XPMCaxt size signal (2026-10-19, 105 buys 10-17 12:43 -> 10-19 18:44; f9.py/m9.py/c9.py, 9X_feat.jsonl, 9X_meta.json)
- Size = k x 0.494 SOL (0.5 SOL incl 1.25% fee), k in 1..8 (one 11). NOT liq/MC/dev/bundle/position (Spearman |rho|<0.25; dev -0.23).
- Metadata class explains it: PROJECT (own website domain + own X account) k med 6 (2.96 SOL), +6.0% avg 52% win (n=23);
  tweet-reference meme (X link = another account's /status/, no own site) k med 2 (0.99 SOL), +1.4% (n=23; ~13 from ONE serial launcher ForestManSol555 / creator 6gAgy3, always k=2-3);
  bare (no links) k 2; creator bundle >=9 SOL -> k 5-8 but -5.2% avg; otcdesks (j7/Lunar = rule #2 type) k 2-8, -7.7% (n=6).
- k>=5: +5.5% avg / 57% win vs k<=2: -0.3% / 38% win. Fee scales with k (Spearman +0.53).
- Caveats [I]: small n, 33/105 metadata fetches failed (old IPFS), meme class dominated by one creator.

## 4yFAz size signal (2026-10-19, 542 buys with create-block features, 299 with metadata; fw.py/mw.py/c4.py, 4y_feat.jsonl, 4y_meta.json)
- NOT metadata class (unlike 9X): tweet memes med 2.15 SOL, PROJECT site+X med 1.52.
- CREATOR identity: repeat creators get the same size each time; creator id explains 88% of size variance (40 creators, 120 buys). E.g. FaBGrHWj 5x2.93, HgAhL3V5 4x2.93, aH31qjgP always ~1.2 -> [I] per-creator score list.
- Weak drivers (Spearman): time +0.24 (sizes grew over the 2.4 days), MC at entry +0.23, bundle +0.22, dev +0.18, earlier position -0.16.
- Launch tool: j7tracker / uxento / rapidlaunch launches almost never small (avg 2.2-2.6 SOL); plain ipfs.io / flap.mypinata often small (1.1-1.9).
- Bundle bands (his pnl avg): none +3.3% (n=289), 2-3 -0.4% (32), 3-5 -0.2% (81, = our rule-#2 band), 5-9 +10.4% (64), >=9 +3.5% (24).
- Outcome by size: >=2 SOL +6.4% avg / +1.1% med / 54% win; 1-2 +2.3% / 39%; <1 -2.4% / 29% -> his sizing has value.
- Two buy paths [I]: 402 on-tier buys via his program 2YAbTp..., 154 off-tier (continuous 1.2-2.1 SOL) mostly direct pump buy_exact_sol_in.

## TODO (high priority, after 6-h pause from 2026-10-19 ~21:30 UTC)
- Detect rapidlaunch creates: program CQdxJSkqi3Ve2WBfMwm5ZxKUyEehHrEY1afGgbNigL74 CPIs into pump; engine saw 0 of ~40 rapidlaunch launches 4yFAz/9X bought. Copy engine, paper only.
- Paper-test bundle band 5-9 SOL (4yFAz +10.4% avg n=64) and ladder exit.
