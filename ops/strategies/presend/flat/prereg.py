#!/usr/bin/env python3
"""PRE-SEND FLAT FILLS: PRE-REGISTRATION. Written 2026-10-27 20:55 PKT, BEFORE any variant result was computed.
(Known before writing: the facts in the owner's task text, incl. r28's first 85 fills; the earlier studies' all-fill exit
sweeps (filter/REPORT.md, real/r065). No flat-position replay, no hold variant and no filter variant of THIS study had been run.)

DATA ROLES
  dev        = AMS r24 + r25 + r26  (dip19, no QUIET live; sizes 0.40 (r24 segment 1, 4 min) / 0.34 / 0.34 / 0.50)
  validation = AMS r27              (dip20, QUIET live incl. a 60-min warm-up with the arm rule off; 0.35)
  holdout    = AMS r28              (dip21, QUIET live; 0.50). A read-only snapshot (`sudo cat`) is fetched ONLY after
               FROZEN.json (the chosen variants + the sha256 of this file) is written; used up to its last complete fill
               (a fill whose realized and rent-back records are present and whose chain tape reaches fill + 30 slots);
               tested once. Its chain recording (after r27's end + 30 min = 10-27 18:07 PKT) is not read before the freeze.

UNIT AND SCORE
  Unit: one live armed window (Idea B); one live position = the fill of one window (Idea A).
  Score of a window = realized (presend_live_realized.pnl) + token-account rent back (presend_live_ata_close.delta)
                      - failed-try fees (presend_attempt_land fee when its result is an error; a try logged 'unseen' is priced
                        from our own failed tx on chain, 0 if it never landed), at the run's own live size (never rescaled).
  Winner = a fill with realized + rent back > 0.  Gain = variant score - baseline score (SOL, summed over units).
  FLAT fill (MEASURED) = a fill with no trade by any wallet other than the AMS wallet on chain strictly between our buy and
                         our last sell (chain order slot, tx index, event index). FRA's wallet counts as "other" (it moves price).

BASELINES
  Primary ("deployed") = what the engine now running (dip21, QUIET on) keeps:
     dev: the live windows minus QUIET's arm-skip replayed (4 signals, whale dump history 24 h, as apply_filter.py), with
          QUIET's 6:2 stop replayed (try pos rule, as apply_filter.py); r27 / r28: live as run.
  Secondary (reported, not used for pass/fail): dev as run live (no QUIET).

IDEA A: exit-time hold of flat positions
  Fires only on a live position whose time exit at fill + 2 was decided while the engine had seen NO other wallet's trade since
  our buy (MEASURED: presend_live_tape receive time <= the exit record's time). Every other position is unchanged by definition
  (reported: positions where the engine's view was flat but the chain was not, and the reverse).
  Replay (INFERRED): the token's chain trades after our buy in chain order, our live sell removed; every other trade keeps its
  size (SOL-in buys: same SOL into the curve, formula as measured on its real pre-state; exact-token buys: same tokens, cost
  recomputed; sells: same tokens, less tokens a wallet did not get from an earlier replayed buy), re-priced with pump's integer
  math; nobody else changes behaviour (main: no follower fails; sensitivity: decoded slippage limits where fetched).
  Our sell: pump's integer math on the state at its chain position; fees, tips, rent as live.
  Sell placement: a time exit at fill + N lands at (fill slot + N) x 212 ms + this position's own live time-exit delay (chain
  ms); a trade-triggered exit (TP / SL / big sell / first other trade with K = 0) lands at the trigger trade's chain time + the
  median live TP / SL reaction delay measured on dev; whichever lands first. TP +10% / SL -20% stay active (engine value).
  Side cost (MEASURED inputs): while a pre-send position is open every window's tries pause (one_position) and the reactive bot
  is blocked: live tries of other windows sent inside the extra hold are dropped (fees saved; a live fill among them is lost
  with its live net). Reported separately and included in the variant score.
  GRID (36 configs):
    A1(N)      N in 3..10: hold to fill + N                                                          (8)
    A2(K,Nmax) K in {0,1,2}, Nmax in {4,6,8,10}: sell K slots after the first other trade seen, else at fill + Nmax  (12)
    A3(X,N)    X in {0.1,0.3,0.5,1.0} SOL, N in {4,6,8,10}: A1(N) + sell at once when another wallet's sell >= X SOL is seen  (16)
  SELECTION: the largest dev gain (primary baseline) among configs with no dev run worse; tie -> the shorter max hold.
  Range: bootstrap over affected positions (10,000 resamples, 5-95%) per split.

IDEA B: filter aimed at flat fills (no lookahead)
  B1 try-time stop (generalised QUIET stop): at the first try at slot >= trigger + N, count the other trades (not the whale,
     not our wallets) after the trigger in what the engine had seen when signing it (the try's pos); if < M, that try and every
     later try of the window are not sent. A removed fill loses its net; removed tries save their fees. N in 1..5, M in 1..3 (15).
     On top of the baseline (on dev QUIET's 6:2 stays as well; it is subsumed when M >= 2).
  B2 arm-time skip (whole window): one feature with a threshold (skip if f <= thr or f >= thr; thr = the dev deciles 10..90% of
     the feature over dev baseline windows), and the AND of two of the five best single rules (each with its own threshold).
     Features (knowable at the trigger; chain rows strictly before the trigger tx + the trigger; histories closed before it):
       n_tr_10, n_tr_50 (trades in the last 10 / 50 slots), n_u_10, n_u_50 (distinct wallets), since_last (slots since the last
       trade), n_tr (trades since creation), vol_50 (SOL volume, 50 slots), fb_n (follower bots ever on it), coh_hold (cohort
       holders), wh_dump_fol (whale's 24 h dumps' mean followers, -1 none), wh_dumps (count), vsol (curve SOL after the trigger),
       whale_pct (whale's share after the trigger), whale_sol (trigger buy SOL), age_slots, quiet_n (QUIET signals true, 0..4).
     16 features x 2 directions x 9 thresholds = 288 singles (+ 10 pairs).
  SELECTION: the largest dev gain (primary baseline) among configs with no dev run worse AND dev winners removed (SOL) <=
  0.5 x dev savings (losses avoided + fees saved).
  Range: bootstrap over windows (10,000 resamples, 5-95%) per split.

PASS BAR (each idea's selected variant; all must hold)
  1. Better on dev (gain > 0, primary baseline) and no dev run worse (each run gain >= 0).
  2. Better on validation (r27 gain > 0).
  3. Better on the holdout (r28 gain > 0).
  4. Idea B only: winners removed (SOL) <= 0.5 x what is saved (losses avoided + fees saved), dev + validation + holdout pooled.
  Combined A + B: B's rule first, then A on the positions left; reported per split (no separate bar).
  Configs tried are counted and reported (target: 36 + 15 + 298 = 349).
"""
import hashlib, os

A1 = [("A1", dict(N=n)) for n in range(3, 11)]
A2 = [("A2", dict(K=k, N=nm)) for k in (0, 1, 2) for nm in (4, 6, 8, 10)]
A3 = [("A3", dict(X=x, N=n)) for x in (0.1, 0.3, 0.5, 1.0) for n in (4, 6, 8, 10)]
GRID_A = A1 + A2 + A3
GRID_B1 = [(n, m) for n in range(1, 6) for m in (1, 2, 3)]
FEATURES_B2 = ["n_tr_10", "n_tr_50", "n_u_10", "n_u_50", "since_last", "n_tr", "vol_50", "fb_n", "coh_hold", "wh_dump_fol", "wh_dumps",
               "vsol", "whale_pct", "whale_sol", "age_slots", "quiet_n"]
DEV = ["r24", "r25", "r26"]; VAL = ["r27"]; HOLD = ["r28"]
WRITTEN = "2026-10-27 20:55 PKT"


def sha():
    return hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()


if __name__ == "__main__":
    print(WRITTEN, sha(), len(GRID_A), len(GRID_B1), len(FEATURES_B2))
