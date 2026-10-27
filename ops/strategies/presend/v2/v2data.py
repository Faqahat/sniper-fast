#!/usr/bin/env python3
# PRE-SEND V2 shared data access (read-only). Tapes: R1-R3 = the study's patterns/day_R*.npz; R4 = the FULL R4 tape built by
# b1_tape.py (10-24 19:25 -> 10-25 10:26 PKT; the study's R4 was only 19:25-22:41). Leader client per slot from the local epoch
# schedules (1065-1067; R1 = epoch 1064 has none) and the validator -> client map (leader_geo, 10-23), corrected by what the
# probe's leader book said for the leaders it met.
import os, sys, json, time, calendar, zlib, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PS = os.path.dirname(HERE)
sys.path.insert(0, PS)
OUT = "/home/moiz/sniper-data/presend_v2"
TAPE = {"R1": "/home/moiz/sniper-data/strategies/patterns/day_R1", "R2": "/home/moiz/sniper-data/strategies/patterns/day_R2",
        "R3": "/home/moiz/sniper-data/strategies/patterns/day_R3", "R4": f"{OUT}/tape_R4/day_PS",
        "R5": f"{OUT}/tape_R5/day_PS"}      # R5 = fresh hours after the analysis (same recording, rebuilt from 10-24 19:25 so tokens keep history)
COLS = ("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok", "fr", "slack", "wt", "bt", "uid")
pk = lambda s: calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
def pkt(t, f="%m-%d %H:%M"): return time.strftime(f, time.gmtime(int(t) + 18000))
# evaluation windows (PKT): R1 / R2 as the study; R3 and R4 to their tape end - 30 min (the recording's tail is incomplete)
WIN = {"R1": ("10-22 03:07", "10-22 18:05"), "R2": ("10-22 20:43", "10-23 18:19"), "R3": ("10-23 19:26", "10-24 19:10"),
       "R4": ("10-24 19:25", "10-25 09:56")}
if os.path.exists(f"{OUT}/tape_R5/win.json"): WIN["R5"] = tuple(json.load(open(f"{OUT}/tape_R5/win.json")))
DAYS = ("R1", "R2", "R3", "R4")
crc = lambda w: zlib.crc32(w.encode())

def load_day(day, cols=COLS):
    z = np.load(TAPE[day] + ".npz"); M = json.load(open(TAPE[day] + "_meta.json"))
    d = {k: z[k] for k in cols}
    d["meta"] = M["meta"]
    nt = len(M["meta"]); cnt = np.bincount(d["tok"], minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    d["off"] = off; d["cnt"] = cnt; d["day"] = day
    if all(k in d for k in ("buy", "vsol", "vtok", "sol", "tokn")):
        b = d["buy"].astype(bool); V = d["vsol"]; T = d["vtok"]
        Vpre = np.where(b, V - d["sol"], V + d["sol"]); Tpre = np.where(b, T + d["tokn"], T - d["tokn"])
        d["p"] = V / T; d["ppre"] = Vpre / np.maximum(Tpre, 1.0); d["move"] = (d["p"] / d["ppre"] - 1) * 100
    if "bt" in d:
        bt = d["bt"].astype(np.int64); ok = bt > 0
        if (~ok).any() and ok.sum() > 100:
            a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1)
            bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
        d["t"] = bt
    return d

def in_win(day, t):
    a, b = WIN[day]; return (t >= pk(a)) & (t < pk(b))

def hours(day):
    a, b = WIN[day]; return (pk(b) - pk(a)) / 3600.0

# ---- leader clients
CLS = ["unk", "bam", "jito", "harmonic", "fd", "agave", "rakurai"]
CMAP = {"AgaveBam": "bam", "FireBAM": "bam", "JitoLabs": "jito", "HarmonicAgave": "harmonic", "HarmonicFiredancer": "harmonic",
        "Firedancer": "fd", "Frankendancer": "fd", "Agave": "agave", "Rakurai": "rakurai"}
SCHED = ["/home/moiz/sniper-data/haqq/schedule_1065.json", "/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json",
         "/home/moiz/sniper-data/competitors2/schedule_1067.json"]
GEO = "/home/moiz/sniper/ops/dip/speed/leaders/leader_geo.json"
PROBE = "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"
_LC = {}
def leader_classes():
    """-> (s0, cls array int8 over slots s0 .. s0 + n - 1, raw client names per validator id) ; cached"""
    if _LC: return _LC["s0"], _LC["c"]
    geo = {r["pk"]: r.get("client") or "" for r in json.load(open(GEO))["rows"]}
    # the probe's leader book (8-char leader prefix -> client) wins where it differs
    pb = {}
    try:
        for l in open(PROBE):
            if '"presend_attempt"' not in l: continue
            o = json.loads(l)
            if o.get("leader") and o.get("client"): pb[o["leader"]] = o["client"]
    except FileNotFoundError: pass
    S = [json.load(open(f)) for f in SCHED]
    s0 = min(x["start"] for x in S); s1 = max(x["start"] + len(x["slot_leader"]) for x in S)
    c = np.zeros(s1 - s0, np.int8); fixed = 0
    for x in S:
        ids = x["ids"]; cl = []
        for v in ids:
            nm = pb.get(v[:8]) or geo.get(v, "")
            if v[:8] in pb and geo.get(v, "") != pb[v[:8]]: fixed += 1
            cl.append(CLS.index(CMAP.get(nm, "unk")) if CMAP.get(nm) else 0)
        cl = np.array(cl, np.int8)
        c[x["start"] - s0: x["start"] - s0 + len(x["slot_leader"])] = cl[np.array(x["slot_leader"])]
    _LC["s0"] = s0; _LC["c"] = c; _LC["fixed"] = fixed
    return s0, c

def slot_class(slots):
    s0, c = leader_classes()
    slots = np.asarray(slots, np.int64); i = slots - s0
    ok = (i >= 0) & (i < len(c))
    return np.where(ok, c[np.clip(i, 0, len(c) - 1)], 0).astype(np.int8)
