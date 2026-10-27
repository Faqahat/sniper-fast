#!/usr/bin/env python3
"""SIZE_48H (10-26, read-only, offline): shared pieces for the probe-3 calibration and the 48 h size replay.
  * the newer tape (s48/tab: the recordings run_20261023_1426 .. run_20261025_1420, built by build.py), with the three live
    probes' own pre-send fills and sells removed (the replay puts its own buy in);
  * probe 3 (AMS run 19) loaded with probes.py's loader (same record types as probes 1-2);
  * Model over any set of probes (sim.Model is fixed to P1 / P2).
Nothing here sends, starts or stops anything."""
import sys, os, json, hashlib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib, sim, probes as PR

BASE = "/home/moiz/sniper-data/presend_real"
S48 = f"{BASE}/s48"
TAB48 = f"{S48}/tab"
R19 = f"{S48}/live/dip_ams_r19.jsonl"
LIVE_FILES = ("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r17.jsonl", R19)
PR.PROBES["P3"] = R19

def use_tab48():
    """point rlib (and everything that reads rlib.TAB: donors' ours.jsonl, variants' trades.npy) at the new tape"""
    rlib.TAB = TAB48

class Tape48(rlib.Tape):
    def __init__(self):
        super().__init__(tab=TAB48, with_ours=False)
        sh = lambda s: int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")
        self.skip_sigh = set()
        for fn in LIVE_FILES:
            for l in open(fn):
                if '"presend_live_fill"' in l or '"presend_live_sell_land"' in l:
                    r = json.loads(l); self.skip_sigh.add(sh(r["sig"]))

class ModelN(sim.Model):
    """sim.Model over the given probes (view jitter trigger -> whale sell; the live sells' landing delays)"""
    def __init__(self, D, tp, names=("P1", "P2", "P3")):
        SMS = sim.SMS
        self.jit = collections.defaultdict(list); self.sell_time = []; self.sell_tpsl = []
        for name in names:
            arms = {}
            for (m, w, row), r in D[name]["shadow"]["presend_arm"].items(): arms[(m, w)] = r
            for (m, w, row), r in D[name]["shadow"]["presend_disarm"].items():
                ws = r.get("whale_sell"); a = arms.get((m, w))
                if not ws or not a: continue
                ds = ws["slot"] - a["slot"]
                self.jit[self.jb(ds)].append((ws["t"] - a["t"]) / 1e6 - (tp.cc(ws["slot"], ws["idx"]) - tp.cc(a["slot"], a["idx"])))
            for W in D[name]["wins"]:
                f, ex, se = W["fill"], W["exit"], W["sell"]
                if not (f and ex and se): continue
                if ex["why"] == "time-limit": self.sell_time.append(tp.cc(se["slot"], se["idx"]) - (f["slot"] + 2) * SMS)
                else: self.sell_tpsl.append((se["t"] - ex["t"]) / 1e6)

def live_summary(W_list):
    """MEASURED live totals of a list of donor windows: fills, wins, realized (chain), failed-try fees (chain), net"""
    fills = [W for W in W_list if W["fill"]]
    real = [W["realized"]["pnl"] for W in fills if W["realized"]]
    fees = sum((t["fee"] or 5120) for W in W_list for t in W["tries"] if t["res"] not in ("ok", "drop", "unknown"))     # every landed failed try (6042, deadline, ata_exists, buy_6005, other)
    r = sum(real)
    return dict(windows=len(W_list), fills=len(fills), wins=sum(1 for x in real if x > 0), realized=r / 1e9, fees=fees / 1e9,
                net=(r - fees) / 1e9, per_fill=((r - fees) / 1e9 / len(fills) if fills else float("nan")), unrealized=len(fills) - len(real))
