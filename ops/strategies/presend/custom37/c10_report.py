#!/usr/bin/env python3
"""CUSTOM37: builds REPORT.md from the hand-written text below + the generated tables (losses.md, tables.md)."""
D = "/home/it/sniper-data/custom37"
OUT = "/home/it/sniper/ops/strategies/presend/custom37/REPORT.md"
LM = open(f"{D}/losses.md").read().split("\n")
TM = open(f"{D}/tables.md").read()


def section(lines, start, stop=None):
    i = next(k for k, l in enumerate(lines) if l.startswith(start))
    j = next((k for k in range(i + 1, len(lines)) if stop and lines[k].startswith(stop)), len(lines))
    return "\n".join(lines[i + 1:j]).strip()


buckets = section(LM, "LOSS BUCKETS", "WINNERS for")
losers = section(LM, "ALL r37 LOSERS", "KNOBS on r37")
onlosers = section(LM, "KNOBS on r37")
knobs = TM.split("\n\n#### ")[0].strip()
pols = "#### " + "\n\n#### ".join(TM.split("\n\n#### ")[1:]).strip()

TXT = f"""# CUSTOM37: could custom pre-send configs have cut AMS run 37's losses? (10-29, times PKT)

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

{buckets}

- Winners in the same buckets: DRIFT 87, SHALLOW ENTRY 6 (none are CASCADE or FLAT by construction).
- Cascades: dump depth ~16%, then 2-6 SOL more selling lands within our 0.4 s hold (entry 14-21% above the later low). The
  second seller was the whale in 5 of 18. Flats (20, -0.41) are pure costs: pump fee both ways + tips + fees = 20.7 mSOL.

### All r37 losers at or below -0.02 SOL (51; time = our fill, PKT)
"best single knob" = the knob that helped THIS window most in the paired replay (mSOL; drop0.15 = limit 0.15, exit100 = exit
100 ms, q3:2 = QUIET stop 3:2, win6 = 6-slot window, k4 / k12 = tries per slot, dl2 = deadline +2, flat1000 = flat extension 1 s,
size0.5 = 0.5 SOL). "custom quote A" = what policy A did to it. Age in slots; full-dump drop = the whale's whole balance sold
into the post-trigger curve.
{losers}

What the knobs do to the 168 live fills only (added fills from unfilled windows are in section 4):

{onlosers}

## 4. Each knob alone (paired vs the current r37 config, SOL; TRAIN 30.7 h, TEST r37 10.8 h; /day at 0.696)
CI = 90% bootstrap, windows resampled in (run, PKT hour) blocks. "INFERRED share" = share of |delta| from phantom-try fills.

{knobs}

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

{pols}

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
"""
open(OUT, "w").write(TXT)
print("wrote", OUT, len(TXT), "chars")
