#!/usr/bin/env python3
"""Shared helpers for HAQQ_STRAT (read-only)."""
import json, pickle, time, collections
import numpy as np
D = "/home/moiz/sniper-data/haqq_strat"
W0 = 1793038500; W1 = W0 + 86400             # last 24 h: 10-26 23:15 -> 10-27 23:15 PKT
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
DEAD_V = 30.52


def svc(acc):
    if acc in TIP: return TIP[acc]
    if acc.startswith("noz"): return "nozomi"
    return "?" + acc[:6]


_L = {}
def _ld():
    if _L: return
    sch = {}
    for e in (1067, 1068, 1069):
        for f in (f"/home/moiz/sniper-data/haqq_sel/schedule_{e}.json", f"/home/moiz/sniper-data/competitors2/schedule_{e}.json"):
            try: d = json.load(open(f))
            except FileNotFoundError: continue
            sch[d["start"]] = (d["ids"], d["slot_leader"]); break
    _L["sch"] = sch
    nodes = json.load(open("/home/moiz/sniper/ops/overnight/landing/work/rpc/clusternodes_now.json"))["nodes"]
    cl = {k: v.get("clientId") or "" for k, v in nodes.items()}
    rt = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
    for k, v in rt.items():
        if v.get("client"): cl.setdefault(k, v["client"])
    _L["cl"] = cl


def client_class(c):
    if not c: return "?"
    if "Harmonic" in c: return "harmonic"
    if "Bam" in c or "BAM" in c: return "bam"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    return "other"


def client_of(slot):
    _ld()
    ep = slot // 432000 * 432000
    if ep not in _L["sch"]: return "?"
    ids, sl = _L["sch"][ep]; x = sl[slot - ep]
    if x is None or x < 0: return "?"
    return client_class(_L["cl"].get(ids[x], ""))


def etype(b):
    """strategy type of a buy from its pre-buy context (first buys); adds are typed ADD"""
    if b.get("add"): return "ADD"
    if b["vsol_pre"] <= DEAD_V: return "DEAD"
    if b.get("d_drop", 0) >= 0.05 and b.get("d_slots", 99) <= 2: return "DIP"
    if b["age"] is not None and b["age"] <= 5: return "LAUNCH"
    if b.get("dd10", 0) >= 0.10: return "DIP_LATE"
    if b.get("wb_sol", 0) >= 1.0 and (b.get("wb_slots") or 99) <= 2: return "MOMO"
    return "OTHER"


def pct(x, p=(10, 50, 90)):
    x = np.array([v for v in x if v is not None and v == v], float)
    if not len(x): return "-"
    return " / ".join(f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}" for v in np.percentile(x, p))


def boot(v, n=2000, seed=1):
    v = np.asarray(v, float)
    if not len(v): return (0.0, 0.0)
    r = np.random.default_rng(seed); s = [v[r.integers(0, len(v), len(v))].sum() for _ in range(n)]
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def load_pos():
    return pickle.load(open(f"{D}/pos.pkl", "rb"))
