# No-bundle selection study: 4yFAz (2026-10-18)

Read-only throughout: RPC reads and public HTTP GETs of metadata URIs. No transactions sent. No process touched apart from these scripts. Full output: `report.txt` (sections 1-12).

## Verdict (short)
- **No.** I found no no-bundle rule, using features visible at create time, that holds out of sample and makes money at a 1.00-1.05x entry.
- The best rules find his picks at **lift 4-7** (precision 2-5%), and that lift is stable across time splits. But the launches they select do not run. The return 10 s after a 1.02x entry is about 0% (+2% at 1.00x, -2 to -4% at 1.05x), before about 1-2% in priority fees.
- **He IS selecting, not just fast.** His no-bundle picks run far more than launches that pass the same rules, even with his own SOL (and his recurring co-buyers' SOL) removed from the curve. Our create-time features capture only part of that signal.
- Confidence: medium-high on "no money-making rule from these features"; medium on "he has extra signal beyond our features" (follower effects are only partly controlled).

## Method and sample
- **His buys:** all 11,323 wallet signatures back to the ledger start (slot 457.45M, about 4.4 days). 2,755 succeeded; 8,568 failed.
  - **550 mints bought; 545 matched to their create** (425 at offset 0, 120 at offset 1).
  - Only 98 of the 291 `sel2/pos_meta.json` mints fall inside the ledger; the other 193 predate it and cannot be analysed.
  - PnL per mint = wallet SOL delta over all his txs on that mint (fees and tips included) + the ATA rent refund.
- **Universe:** 107,544 successful creates from the mint-authority signatures. Uniform random sample of 4,000; 3,976 parsed (f = 3.70%, so each random row stands for 27 creates).
  - The 27% of creates quoted in a non-SOL token were dropped (he bought none of them).
  - 80% of standard SOL launches are **no-bundle** (glued run ≤ 0.3 SOL; same rule as bsplit).
- **Outcomes:** price/floor path for the first 60 s. Slot S comes from the block; later slots use the last trade in each slot or 3-slot bucket.
  - Entry is 1.02x at create. Exit is the first touch of +30%, else at 3 s / 10 s / 40 s. Pump fee 1.25% per side. Priority fees and tips are NOT included.
  - "adj" means the same path with his own net SOL taken out of the curve (vsol − his net).
- **Features (all visible at create):**
  - dev buy;
  - create tx: ix type, Token-2022, mayhem flag, cu price/limit, priority, tip sender/amount, program fingerprint, payer ≠ creator, tx version;
  - creator balance before/after the create;
  - metadata JSON: socials, description, image host, keys, tweet age from the X snowflake ID;
  - name/symbol style;
  - creator history before the create: prior txs, age, idle time, prior launches and how they were doing, funder and funder size;
  - leader client; hour.
- **Validation:** time split A (fit on the first 60% → test on the last 40%) and split B (the reverse), plus 3 time terciles. The first 2 h of the ledger are excluded because history lookups fail there.
  - Analysis set: **283 of his no-bundle snipes, 2,263 random no-bundle launches.**

## His split and PnL (545 snipes, standard SOL launches)
| side | n | fill med (avg, incl. own impact) | price when he arrives | PnL SOL | mean / median ret | win |
|---|---|---|---|---|---|---|
| **no-bundle** | 289 (53%) | 1.057 | 1.000 (he is first) | **+25.2** | +3.1% / -2.2% | 40% |
| bundled >0.3 SOL | 256 (47%) | 1.367 | 1.291 | **+28.9** | +2.6% / -1.3% | 46% |
| bundle 5+ SOL | 89 | 1.765 | 1.69 | +16.5 | +4.6% | 47% |

- Total: +54.1 SOL on fills, minus 1.4 SOL of failed-tx fees on those mints, minus 10.4 SOL of failed sprays on launches he never filled. The wallet nets about **+42 SOL in 4.4 days** on 988 SOL bought.
- PnL is tail-driven. On the no-bundle side the top 5 trades make +15.6 SOL and the top 10% make +33.7 (more than the total).
- He pays about 0.02 SOL of priority fee per buy, about 1.4% of size.
- Population: no-bundle launches are 80% of SOL launches, but only 53% of his snipes. Base rate: he fills 0.46% of no-bundle launches.

## Do his no-bundle picks run? (first 10 s, entry 1.02x)
| set | n | peak10 med | TP+30% hit | X10 mean |
|---|---|---|---|---|
| random no-bundle | 2289 | 1.00 | 22% (mayhem-driven) | **-5.3%** |
| random no-bundle, not mayhem | 1375 | 1.00 | 5% | -2.3% |
| random, not mayhem, dev ≥ 0.5 (matched peers) | 469 | 1.02 | 11% | -0.3% |
| **his picks, raw** | 283 | 1.23 | 37% | +11.1% |
| **his picks, his SOL removed** | 283 | 1.13 | 25% | **+6.1%** |
| his picks, his + 14 followers removed | 283 | 1.12 | 25% | +5.6% |
| his picks, his + all 129 recurring co-buyers removed | 283 | 1.08 | 20% | +2.5% (peers -1.5%) |

- Other fast snipers also favour his picks. On his offset-0 picks there are 1.9 other independent buys in the create slot, against 0.9 on matched peers. They mostly land after him; 23% of his picks have an independent buy ahead of him.
- Big broad snipers (dKMjeGJ4, AMDEmVoc, 9qz7cWBq) co-buy his picks but also buy many launches he skips.

## Separators (label A), stable out of sample
Lift is shown as train → test (split A) → test (split B).
- **mayhem = false:** 100% recall, lift 1.7. Mayhem launches are 40% of no-bundle launches; he took none of them (1 mayhem buy of 545 in total, and it was bundled).
- **dev buy ≥ 1.16 SOL:** lift 4.4 → 3.6 → 4.5, recall about 50%.
- **creator has no prior launch in the window:** lift 2.9 → 2.8 → 2.7, recall 80%. Random creators have a median of 8 prior launches (serial bot launchers).
- **creator idle ≥ 30 min before the create:** lift 4.0 → 3.7 → 2.0. His median is 1131 s; random is 58 s.
- **creator balance ≥ 11 SOL:** lift 3.4 → 2.8 → 3.1.
- Metadata (weaker):
  - has website: lift 2.2 → 2.1 → 2.5;
  - ≥ 2 socials: 2.3 → 2.2 → 2.5;
  - coin_community key: 2.2 → 2.0 → 2.4;
  - X profile link: 36% of his vs 13-18%.
- **Decayed** (launch-tool fingerprints): cu_price ≥ 333k, cu_limit ≥ 300k, program pattern `6EF8rr>AToken>6EF8rr>111111>111111`, tweet age < 24 s.
- **Not separators:** URI host (ipfs.io 66% of his vs 72% of random; j7tracker 13% vs 12%), leader client, hour, name/symbol style.

## Best OOS rules (split A test = last 40%: his 151, random 906; precision is population-weighted)
| target recall | rule (fit on train) | TEST recall | TEST precision | TEST lift | adj X10 (1.02x) | X10 at 1.00x / 1.05x |
|---|---|---|---|---|---|---|
| 80% | dev ≥ 0.5 & not mayhem & creator prior launches < 64 | 77.5% (117) | 2.3% | 3.8 | +0.2% | +2.0% / -2.3% |
| 60% | creator no prior launch & creator bal ≥ 1.2 & cnv_frac ≥ 0.05 | 53.6% (81) | 3.2% | 5.2 | -1.6% | +0.2% / -4.2% |
| 40% | dev ≥ 1.16 & meta keys ≥ 8 & nkeys ≥ 28 | 33.8% (51) | 3.7% | 6.1 | +0.6% | +2.2% / -2.3% |
| 40% (on-chain only) | dev ≥ 1.16 & creator launches < 3 & create not Jito-tipped | 33.8% (51) | 3.6% | 5.9 | +0.1% | +2.0% / -2.5% |
| simple, pre-set | not mayhem & dev ≥ 0.5 & creator bal ≥ 2 | 60% (all periods) | 1.9% | 4.1 (folds 5.4/3.8/3.7) | +0.8% | +2.5% / -1.8% |

- Logistic check (split A test): recall 80/60/40/21% → precision 2.8/3.3/4.4/5.0%, lift 4.5/5.4/7.2/8.1. Split B test: lift about 5.3 at every recall.
- Split B's r40 rule (funder-based) collapsed out of sample (recall 7%): it was overfit.
- **Counting his attempted-but-unfilled launches as picks** (failed buy txs; 535 mints in total, about 243 no-bundle in the population) roughly doubles precision. The simple rule gets 4.35% at 73% recall (lift 5.1), and the best on-chain rule 6.2% at 40% (lift 7.3). This rests on only 9 attempted rows in the random sample.
- **Label B** (rules aimed directly at the 10 s return): nothing survives. The best train combo, creator idle ≥ 93 min & has website, went from +7.3% (n=40) to +2.8% (n=50) out of sample, before fees.

## Uncertainty and caveats
- Base rates are tiny (0.46%), so precision rests on 27x-weighted random counts. Test negatives passing a rule are 50-190 rows; treat precision as ±30% relative.
- X10 has about ±1% standard error for rules with about 200 rows. Fees are not included. A clone would also pay about 1-2% per round trip in priority fees and tips to win the slot.
- Paths beyond 10 s are sampled one tx per slot (or per 3 slots), so peaks are slightly underestimated. Slot S and slots S+1..S+25 of his picks and peers are complete (follow.jsonl).
- The "his SOL removed" adjustment ignores how others would have reacted without him. The follower test only removes wallets that recur on his picks.
- Metadata was fetched days later, not at create time. Meta-JSON features may not be visible within about 100-300 ms for same-slot entries; rules without them were tested separately and perform about the same.
- Create-slot buyer counts are descriptive only and not used in rules (not visible to a same-slot entry).
- Ledger is about 4.4 days. Creator history is capped at 1000 prior txs and censored at the ledger start. Funding is traced one hop.

## Next steps, if continued
- The missing signal looks off-chain, probably the X account or tweet behind the launch (profile links and fresh tweets are over-represented). Testing it needs X data.
- Or it is in his early trade flow, which would be copy trading and is excluded.

## Files (/root/nob)
- **Scripts:**
  - sigs.py (address signature pager), wtx.py (his txs), his.py (his per-mint buys + create resolve);
  - mk_sample.py, blk.py / blk_fixed.py (create block + glued bundle), paths.py (60 s paths), creator.py (creator history), meta.py (URI JSON);
  - fails.py (attempted launches), follow.py + fan.py (follower test), slotS.py (create-slot co-buyers);
  - build.py → ds.jsonl, analyze.py → report.txt;
  - nrpc.py (rate-limited RPC).
- **Data:**
  - csigs.jsonl (all 120k mint-authority sigs), wsigs.jsonl, wtx.jsonl, his_mints.json, attempted.json;
  - rand_targets.json, blk_rand*.jsonl, blk_his.jsonl, paths_*.jsonl, creator.jsonl, meta.jsonl, follow.jsonl, ds.jsonl;
  - report.txt, fan.txt, slotS.txt.
