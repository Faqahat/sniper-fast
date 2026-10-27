#!/usr/bin/env python3
"""PRESEND FILTER: the scoring rule. PRE-REGISTERED at 10-27 07:21 PKT, before any filter was tried; not edited afterwards
(later additions go below the line marked ADDED).

DATA SPLIT
  DEV (tune here only): AMS r24 (10-26 21:47 -> 10-27 02:57 PKT), AMS r25 (10-27 02:58 -> 06:09 PKT).
  VALIDATION (never tuned on; every candidate is reported there, pass or fail):
    primary  : FRA r23 (10-26 04:26 -> ~07:00), FRA r24 (10-26 16:10 -> 21:40); same engine as dev (dip19)
    secondary: AMS r19 (8 tries/slot), AMS r20 + FRA r21 (both servers pre-sending the same dumps), FRA r22 (dip18; window w51 double
               fill, engine P&L wrong: flagged)
  HOLDOUT: AMS r26 (10-27 06:59 PKT onward) is never read: lv.py refuses r26 files; the chain table stops at 10-27 06:20 PKT.

UNIT AND SCORE
  unit = one armed live window; its value (MEASURED, engine records + chain):
     fill (if any): realized (engine) + token-account rent back (dip19 runs: presend_live_ata_close; older engines closed it in the sell)
     minus the fees of its tries that landed and failed (land record; a try logged "unseen" is looked up on the chain)
  score = total net SOL over the windows kept = realized + rent back - failed-try fees
  A rule acts at one decision point and may only use what is known before it:
     ARM    : skip the window (its fill and all its tries go)
     DURING : stop the window's tries from time t (the fill goes only if its try was sent at/after t; later tries save their fees)
     ONCHAIN: a condition the program checks when a try executes (a failed condition = a failed try, fee paid)
  Not modelled (caveats): a skipped window lets a later trigger on the same token arm; the 100-fill cap; the reactive bot.

WINNERS = fills with realized + rent back > 0 (every trade fee paid). Also reported with the engine's realized alone.

PASS BAR (all must hold)
  1. dev total net improves (r24 + r25), and neither dev run gets worse
  2. winners removed on dev: prefer 0; the SOL of removed winners must be below the SOL saved (losers removed + fees saved)
  3. validation: net improves on the primary set (FRA r23 + r24) AND on all validation runs pooled
  4. robustness on dev: leave-one-run-out, time blocks (most not worse), permutation test (p < 0.05)
  5. few parameters, monotone rules, one threshold for all runs; the number of configs tried is reported
  6. at 0.34 SOL (live) and 0.50 SOL (exact replay on dev)
"""
import numpy as np


def window_value(w):
    """lamports: the window's measured contribution at the live size"""
    v = -w["fail_fee"]
    if w.get("filled"): v += w["net"]
    return v


def evaluate(windows, keep):
    """windows: list of window dicts; keep: list of (keep_fraction_of_fees, fill_kept) per window.
    keep[k] = (fee_kept_lamports, fill_kept: bool). Returns a dict of SOL totals and counts."""
    base = sum(window_value(w) for w in windows)
    after = 0; rm_w = rm_w_sol = rm_l = rm_l_sol = 0; fee_saved = 0; rm_flat = rm_notrade = 0
    for w, (fee_kept, fill_kept) in zip(windows, keep):
        after -= fee_kept
        fee_saved += w["fail_fee"] - fee_kept
        if w.get("filled"):
            if fill_kept:
                after += w["net"]
            else:
                if w["net"] > 0: rm_w += 1; rm_w_sol += w["net"]
                else: rm_l += 1; rm_l_sol += w["net"]
    return dict(before=base / 1e9, after=after / 1e9, gain=(after - base) / 1e9, winners_removed=rm_w, winners_removed_sol=rm_w_sol / 1e9,
                losers_removed=rm_l, losers_removed_sol=rm_l_sol / 1e9, fees_saved=fee_saved / 1e9)
