#!/usr/bin/env python3
"""CR-EARNBACK replay: the creator ledger over r39 -> r50 in time order, per variant.
Windows = every live arm (T2 + re-arm; value = its realized SOL, 0 when it did not fill) + every live cr_loss / rearm_cr_loss skip
(r48–r50; value = the shadow row c paper of that trigger, calibrated: CAL_W x wins, CAL_L x losses, CAL_B when the shadow did not fill /
did not arm; re-arm skips have no shadow -> 0, counted).
Ledger: per creator, entries (known ns, SOL, paper?) — a traded window that filled enters at its realize time (live: last sell landing
+ 2 s, as the seed; a skipped-live window the variant trades: calibrated paper at the shadow's exit). r39–r46: the gate was off live ->
the variant's own online ledger (kept positions only, as creator_seed.py's replay). r47: the state is reset to the LIVE SEED (every
r39–r46 position, real), as the engine loaded it, then r47–r50 continue (the live state carried run to run).
Variant knobs: credit (paper credit of a blocked T2 window whose shadow filled: k x paper, or "cal"), win_h (entries older than H hours
drop out), hl (exponential half-life hours on the sum), lastk (only the last K entries), prob (X hours, size f: a blocked creator idle
>= X h gets one trade at f x size; a win clears its ledger, a loss enters as loss / f).
Score per window = included x value; net vs the baseline (the current rule), per period, w/o the top 5 window gains."""
import sys, json, heapq, collections, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/crearn")
import ce_lib as L
N_MIN, SOL = 2, 0.05
# calibration measured on DEV + VAL (r39–r42) T2 live arms vs the same triggers' shadow row c (ce_calib.txt); HOLD checked
CAL_W, CAL_L, CAL_B = 0.564, 0.434, 0.00117
def cal(p):
    if p is None or not p[0]: return CAL_B
    return p[1] * (CAL_W if p[1] > 0 else CAL_L)
H = 3600 * 10**9

def load_windows():
    W = L.windows()
    # re-arm skips without ann.creator: resolve by the logged history (n, sum) against the baseline ledger (filled in by resolve())
    return W

def run(W, v, seed_full, log=None):
    """-> list of (window, decision: 'trade' / 'block' / 'prob', value counted)"""
    led = collections.defaultdict(list)                 # creator -> [(known, SOL, paper)]
    pend = []                                           # heap (known, seq, creator, SOL, paper)
    prob_t = {}                                         # creator -> t0 of the last probation trade
    prob_pending = {}                                   # creator -> pending probation
    out = []; seq = 0; reset_done = False
    for w in W:
        if w["run"] in L.GATE_RUNS and not reset_done and not v.get("noreset"):
            reset_done = True; pend = []; led = collections.defaultdict(list); prob_t = {}; prob_pending = {}
            for c, es in seed_full.items(): led[c] = [(t, s, False) for t, s in es]
        t0 = w["t0"]
        while pend and pend[0][0] < t0:
            kn, _, c, val, paper, tag = heapq.heappop(pend)
            if tag == "prob":
                prob_pending.pop(c, None)
                if val > 0: led[c] = []                                     # a win clears the ledger
                else: led[c].append((kn, val / v["prob"][1], False))
            else: led[c].append((kn, val, paper))
        if w["creator"] is None and v.get("resolve") and w["arm_cr"]:
            n0, s0 = w["arm_cr"]["n"], w["arm_cr"]["sum"]
            m = [c2 for c2, es in led.items() if len(es) == n0 and abs(sum(e[1] for e in es) - s0) < 2e-9]
            if len(m) == 1: w["creator"] = m[0]; w["resolved"] = True
        c = w["creator"]
        dec = "trade"
        if c and v.get("on", True):
            es = led.get(c, [])
            if v.get("win_h"): es = [e for e in es if e[0] >= t0 - v["win_h"] * H]
            if v.get("lastk"): es = es[-v["lastk"]:]
            if v.get("hl"): s = sum(e[1] * 0.5 ** ((t0 - e[0]) / (v["hl"] * H)) for e in es)
            else: s = sum(e[1] for e in es)
            if len(es) >= N_MIN and s <= -SOL:
                dec = "block"
                if v.get("prob") and c not in prob_pending:
                    last = max([e[0] for e in led.get(c, [])] + [prob_t.get(c, 0)])
                    if t0 - last >= v["prob"][0] * H: dec = "prob"
        # value of the window if traded
        if w["live"] is not None: val, kn, filled = w["live"], w["live_known"], w["filled"]
        elif w["kind"] == "t2": val, kn, filled = cal(w["paper"]), (w["paper"][2] if w["paper"] and w["paper"][0] else None), bool(w["paper"] and w["paper"][0])
        else: val, kn, filled = 0.0, None, False
        if filled and kn is None: kn = t0 + 5 * 10**9
        if dec == "trade":
            out.append((w, dec, val))
            if c and filled:
                for k2, v2 in (w["pl"] if w["live"] is not None else [(kn, val)]):          # live: one entry per position, as the engine
                    seq += 1; heapq.heappush(pend, (k2, seq, c, v2, w["live"] is None, "real"))
        elif dec == "prob":
            f = v["prob"][1]; out.append((w, dec, f * val)); prob_t[c] = t0
            if filled: prob_pending[c] = True; seq += 1; heapq.heappush(pend, (kn, seq, c, f * val, False, "prob"))
        else:
            out.append((w, dec, 0.0))
            cr = v.get("credit")
            if cr and w["kind"] == "t2" and w["paper"] and w["paper"][0]:
                pv = cal(w["paper"]) if cr == "cal" else cr * w["paper"][1]
                seq += 1; heapq.heappush(pend, (w["paper"][2] or t0 + 5 * 10**9, seq, c, pv, True, "paper"))
        if log is not None and c: log.append((w["run"], c, t0, dec, len(led.get(c, [])), round(sum(e[1] for e in led.get(c, [])), 4)))
    return out, led

def seed_full():
    s = collections.defaultdict(list)
    for r in L.RUNS[:8]:
        for p in L.load(r)["pos"]:
            if p["creator"]: s[p["creator"]].append((p["known"], p["pnl"] / 1e9))
    return s
