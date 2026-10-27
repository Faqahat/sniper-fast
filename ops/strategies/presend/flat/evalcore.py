#!/usr/bin/env python3
"""FLAT study: window scoring under arm-skip and try-time stop rules (read-only; the pre-registered rule in prereg.py).
  score(window) = (realized + rent back if its fill is kept) - the failed-try fees of the tries still sent.
  STOP rule (N, M): at the first try sent at slot >= trigger + N, count the OTHER trades (not the whale, not the AMS wallet:
  the engine's own definition) after the trigger, chain order, up to that try's pos (the latest trade the engine had seen when
  it signed it); if < M, that try and every later try of the window are not sent. Several stop rules: the earliest stop wins.
  SKIP: the window is not armed (no tries, no fill).
  Baselines: 'primary' = dev runs with QUIET replayed (arm-skip on the 4 replayed signals + the 6:2 stop), r27 / r28 as run;
             'asrun' = every run as run."""
import numpy as np
import flatlib as FL

DEV = ("r24", "r25", "r26")


class Others:
    """per window: count of other trades after the trigger up to a chain position (cached per window)"""
    def __init__(self, C):
        self.C = C; self.cache = {}

    def prep(self, w):
        k = (w["run"], w["seg"], w["w"])
        if k in self.cache: return self.cache[k]
        C = self.C
        rows = C.mint_rows(w["mint"])
        kt = w["k_trig"]
        if kt is None: self.cache[k] = None; return None
        r = rows[kt + 1:]
        wh = C.wid.get(w["trig"]["wallet"], -2)
        own = C.wid.get(FL.RUNS[w["run"]]["wallet"], -3)
        u = C.c["user"][r]
        oth = (u != wh) & (u != own)
        key = C.key[r]
        cum = np.cumsum(oth)
        self.cache[k] = (key, cum)
        return self.cache[k]

    def upto(self, w, pos):
        p = self.prep(w)
        if p is None: return 0
        key, cum = p
        n = int(np.searchsorted(key, FL.poskey(pos[0], pos[1], pos[2] if len(pos) > 2 else 0), side="right"))
        return int(cum[n - 1]) if n > 0 else 0


def run_rules(w, O, skip=False, stops=()):
    """-> dict(score, fill_kept, fees, stop_k (index of the first try not sent or None))"""
    net = w["net"] if w["filled"] else 0
    if skip:
        return dict(score=0, fill_kept=False, fees=0, stop_k=0, skipped=True)
    tries = w["tries"]; ts = w["trig"]["slot"]
    stop_k = None
    for (N, M) in stops:
        for k, t in enumerate(tries):
            if t["slot"] >= ts + N:
                if O.upto(w, t["pos"]) < M:
                    stop_k = k if stop_k is None else min(stop_k, k)
                break
    fees = 0; fill_kept = w["filled"]; fill_seen = False
    for k, t in enumerate(tries):
        sent = stop_k is None or k < stop_k
        if sent: fees += t["fee"]
        if t["fill"]:
            fill_seen = True; fill_kept = sent
    if w["filled"] and not fill_seen: fill_kept = True
    return dict(score=(net if fill_kept else 0) - fees, fill_kept=fill_kept, fees=fees, stop_k=stop_k, skipped=False)


def base_cfg(run, mode="primary"):
    """(skip function, stop list) of the baseline"""
    if mode == "primary" and run not in FL.QUIET_LIVE:
        return (lambda w: bool(w.get("quiet_skip_replay"))), [(6, 2)]
    return (lambda w: False), []


def evaluate(W, O, run, mode="primary", extra_skip=None, extra_stops=(), only=None):
    """baseline vs variant per window. extra_skip(w) -> True skips (on top of the baseline); extra_stops: more stop rules.
    Returns (rows, summary). rows: per window (w, base, var)."""
    bskip, bstops = base_cfg(run, mode)
    out = []
    S = dict(base=0.0, var=0.0, fills=0, kept_base=0, kept_var=0, win_rm=0, win_rm_sol=0.0, lose_rm=0, lose_rm_sol=0.0, flat_rm=0, flat_rm_sol=0.0,
             fees_saved=0.0, windows=0, skipped=0)
    for w in W:
        if only is not None and not only(w): continue
        b = run_rules(w, O, skip=bskip(w), stops=bstops)
        v = run_rules(w, O, skip=bskip(w) or bool(extra_skip and extra_skip(w)), stops=list(bstops) + list(extra_stops))
        out.append((w, b, v))
        S["windows"] += 1
        S["base"] += b["score"] / 1e9; S["var"] += v["score"] / 1e9
        if v["skipped"] and not b["skipped"]: S["skipped"] += 1
        if w["filled"]:
            S["fills"] += 1; S["kept_base"] += b["fill_kept"]; S["kept_var"] += v["fill_kept"]
            if b["fill_kept"] and not v["fill_kept"]:
                if w["net"] > 0: S["win_rm"] += 1; S["win_rm_sol"] += w["net"] / 1e9
                else: S["lose_rm"] += 1; S["lose_rm_sol"] += w["net"] / 1e9
                if w.get("flat"): S["flat_rm"] += 1; S["flat_rm_sol"] += w["net"] / 1e9
        S["fees_saved"] += (b["fees"] - v["fees"]) / 1e9
    S["gain"] = S["var"] - S["base"]
    return out, S
