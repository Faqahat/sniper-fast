# FILTERS-3 research program (owner 11-03 ~08:30 PKT)

Owner's words: "we need to refactor the filters first, now we have 50+ hours running time ... the QUIET filter skips a lot of
QUIET tokens, these are the ones no other bot trades on, I checked manually, and this has been affecting our pnl a lot, so it
needs a MAJOR update. along with that, check the result of all live and log filters throughout the runs ... launch a fresh
research. not just fix those filters but come up with better techniques/filters to minimize the losses ... our target is 10+ SOL
a day ... prove it."

## What we trade (the pre-send dip engine, AMS)
- T2 trigger: a wallet ("whale") buys >= 6% of supply. We pre-sign buys at a 0.88x price limit (a 12% dip below the trigger
  price) and send them in the slots after it (window ~10 slots); if a dump drops the price through the limit we fill.
  Exit ~200 ms after the fill (2 slots), TP/SL 20%. Size 0.55-0.65 SOL. Re-arm windows after holder dumps (kind "rearm").
- Our wallet: EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR (AMS). (2g7rYv7y... is the old FRA wallet.)
- Engine code (read it, do not edit it): /home/it/sniper/src/bin/snipe_engine/pslive.rs, psrearm.rs, dipmode.rs;
  /home/it/sniper/src/presend_quiet.rs. The flag docs at the top of pslive.rs explain every live and log-only filter.

## Live filters today (run 42 config is in its run_start record)
- QUIET skip: skip a trigger when ALL four hold: since_last >= 1, no cohort wallet holds it, < 2 follower bots ever on it
  (in r42 and earlier runs the follower-bot file was EMPTY, fbots_none.json, ON PURPOSE by the owner's choice: not a bug;
  a follower-bot signal may be proposed again only with proof), the whale's past dumps (24 h) drew < fol (4.0) buyers.
- QUIET stop (6:2): disarm a window if fewer than 2 trades by others within 6 slots after the trigger.
- create_slot / young_age (age-1) / min_age_slots 2, lone whale (<= 1 buyer in 50 slots), re-arm rules (rearm_*),
  guard, profit lock, kill switch.
- Log-only: safe sell timer, holder clock, group risk, landing guard, bad creator, QUIET v2 (v2 features), deep limit,
  wide shadow (3-6% whales, dip30), nb50, and more. filters_report.py knows the list.
- Live skip reasons in r42: rearm_no_holder 5515, rearm_age 4239, create_slot 3346, quiet 651, young_age 431, lone_whale 279, ...

## What we already know (11-03, measured)
- Our trades where NO other bot buys within 10 slots of our buy lose -10..-12 mSOL each, every day, stable.
  Trades where a bot buys in our slot or after us made +20..+25 mSOL each (10-28..10-31) but only +8 on 11-02, and their
  count halved. The follower bots that paid us (DF7eRX, HLU8QbLd, DSvgfynk, CvHEVC7S, 6VzXcLk9) stopped by 11-02; several
  were losing money themselves. haqq (wallets haqqiUUX -> 2VggYpPu -> haqq6qnV, ONE bot) now holds half as long and trades
  2x as often; it is still profitable. E2x1 (+46..53 SOL/day) is steady but plays 5% dips, ~120-slot holds.
  Scripts/data: ops/strategies/presend/botpnl (trips.json per recording in /home/it/sniper-data/botpnl/run_*/).
- The owner checked by hand: many of our losing trades are QUIET tokens nobody else trades, and QUIET lets them through.
- 11-02 ~08:29 PKT bait attack: 13 fills, -2.11 SOL; fresh same-slot holders 11.7/10.0/8.0/5.8% + a 13.9% holder that
  dumps ~24 SOL into our hold; whale 6-8% at age 5-10 slots; dip 12-13.4%. No filter caught it.
  Circuit breaker (built locally, not released) and bundle skip replays: ops/strategies/presend/prevent/breaker/.
- Edge-fade study: ops/strategies/presend/edgefade/ (followers leaving; not landing speed, not fills, not market activity).
- Earlier filter studies (do not repeat what failed; read the conclusions): ops/strategies/presend/filter/ (QUIET2.md),
  ops/strategies/presend/prevent/ (forward/filters_report.py, loss_brief.py, wide_report.py), ops/strategies/presend/
  (other folders). Rule of thumb from them: arm-time rules that looked good in-sample often failed held-out.

## Data (all local, read-only)
- Pre-send records per run (grep of '"ev":"presend_' + run_start/run_end):
  /home/it/sniper-data/filters3/runs/r37..r46.presend.jsonl (r42 = 636 MB: stream it, prefilter lines with a substring test).
  Events: presend_live_arm / _skip (with "why") / _fill / _exit / _sell_land / _close / _realized (pnl lamports, THE real
  money) / _tape (trades on the mint around our position) / _disarm; the paper SHADOW of every T2 trigger, traded or not:
  presend_arm / presend_fill / presend_exit (rows a/b/c; row c = the realistic one, net_cheap) / presend_disarm / presend_skip;
  the wide shadow presend_wide_* (r41+). Field "t" = ns epoch. The shadow's presend_arm carries what QUIET decided ("quiet").
- Full run logs + observatory (hold tape, watched wallets, ...): /home/it/sniper-data/runs/ams/runs/dip_ams_rNN.jsonl and
  .obs.jsonl[.N] (large).
- Raw 24/7 recordings of EVERY pump.fun tx: /data/tapes/collect/run_20261028_1405, run_20261030_1355,
  run_20261031_1350, run_20261102_1250 (txs/*.jsonl.gz, ~12 GB/day; format: see ops/strategies/presend/botpnl/pass1.py,
  pass2.py). Coverage PKT: 10-28 19:05->10-29 19:24, 10-30 18:55->10-31 19:15, 10-31 18:50->11-01 19:09,
  11-02 17:50->11-03 07:55. NOT recorded: 10-29 19:24->10-30 18:55 and 11-01 19:09->11-02 17:50.
  Already extracted per recording: /home/it/sniper-data/botpnl/run_*/p2_*.jsonl = every trade on ~3-6k mints the bots or we
  touched (s, i, bt, err, u = signer, mint, tok, sol, cpre/cpost = curve balance; price ~ 1/(cbal+73e12)^2).

## Runs (PKT, live fill span)
r37 10-29 07:32->10-30 01:55 (338 fills, +4.90) | r38 10-30 02:00->03:38 (126, +0.24) | r39 10-30 05:39->08:47 (88, +0.41)
r40 10-30 09:00->10-31 02:17 (351, +5.58) | r41 10-31 02:25->03:45 (40, -0.52) | r42 10-31 03:52->11-02 08:35 (1328, +8.39)
r43 11-02 09:06->17:19 (136, +0.26) | r44 11-02 17:24->22:09 (242, +0.16) | r45 11-02 22:21->23:05 (38, -0.52)
r46 11-03 01:31->01:41 (14, -0.23)

## PROOF RULES (non-negotiable)
1. Chronological split. DEV = r37..r41 + r42 up to 11-01 12:00 PKT. VAL = r42 from 11-01 12:00 PKT to its end
   (includes the 11-02 attack). HOLDOUT = r43..r46 and the raw recording run_20261102_1250: SEALED. Research agents do not open
   them. When your rule is final, write FROZEN.json (exact rule, thresholds, feature definitions, sha256 of your scorer
   script) in your folder; a separate verifier scores it on the holdout.
2. Signing-time features only: only what the engine knows at the moment it arms / signs (records with t <= the decision
   time; nothing from after the trigger slot unless the rule acts later, e.g. a disarm at slot+N uses slots <= +N). Show for
   each feature the exact field and why it is not look-ahead. If a feature needs state the engine does not keep today, say
   so and say what it would take.
3. Money: for trades we took, use the live realized P&L (presend_live_realized). A filter that BLOCKS a trade saves exactly
   that trade's realized P&L. A change that ADDS trades (unskipping, wider selection, bigger size) can only be estimated from
   the shadow: calibrate it the way wide_report.py does (shadow row c vs live on the same triggers, per-window gap) and label
   every such number ESTIMATE.
4. Always report: SOL/day, n, win rate, per run, the same without the top 5 trades, DEV vs VAL side by side. A rule that
   only works because of r42's attack, or one run, is not proven. Prefer few simple rules; if you use a model, keep it small,
   use chronological folds, and show it is stable.
5. Label inferences as inferences. Measure before attributing. Times in PKT. Plain short words in reports.

## SAFETY (non-negotiable)
- Read-only on all data. Write only in your own folders: ops/strategies/presend/filters3/<you>/ and
  /home/it/sniper-data/filters3/<you>/ (and your own scratchpad subfolder). Never delete or move anything else.
- No ssh / no server access at all. Never read ~/.config/sniper/*, any .env, key or keystore file, or anything with an
  api-key. Never print secrets.
- Do not edit engine code, do not build or deploy anything, do not start or stop runs.
- CPU: at most 4 worker processes. Disk: keep your outputs under 10 GB.
- Your final message: a short plain-words summary (numbers, DEV vs VAL, what is proven vs estimate), and the paths of your
  report (REPORT.md) and FROZEN.json.
