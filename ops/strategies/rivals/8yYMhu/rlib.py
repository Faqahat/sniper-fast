"""8yYMhu shared helpers (read-only inputs). Chain clock = dv8/exec convention: slot*212 ms + idx/blocksize*212 ms, blocksize = max pump
tx index seen in the slot + 1 (haqqml/fresh slots.npy, through 10-29 00:55 PKT). Leader schedule epochs 1067-1070; client ids from
getClusterNodes (e2x1 exec cn.json + landing clusternodes); leader location = leader_geo.json (IP geo, epoch 1063, slightly stale)."""
import json, pickle, time, functools, collections
import numpy as np
D = "/home/moiz/sniper-data/rivals/8yYMhu"
W = "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3"
TP = "/home/moiz/sniper-data/haqqml/fresh/tape"
SMS = 212.0
W0 = 1793113200; W1 = W0 + 86400            # 24 h window 10-27 20:00 -> 10-28 20:00 PKT
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
gm = lambda m: f"https://gmgn.ai/sol/token/{m}"
ss = lambda s: f"https://solscan.io/tx/{s}"

@functools.lru_cache(None)
def slot_sizes():
    a = np.load(f"{TP}/slots.npy")
    s0 = int(a["slot"].min()); bsz = np.zeros(int(a["slot"].max()) - s0 + 1); bsz[a["slot"].astype(np.int64) - s0] = a["maxi"].astype(np.int64) + 1
    have = bsz > 0; bsz[~have] = 400
    return s0, bsz, have

def bsize(s):
    s0, bsz, have = slot_sizes(); k = int(s) - s0
    return float(bsz[k]) if 0 <= k < len(bsz) else 400.0

def cc(s, i):
    n = bsize(s); return s * SMS + i / max(n, i + 1.0) * SMS

def frac(s, i):
    n = bsize(s); return i / max(n, i + 1.0)

@functools.lru_cache(None)
def _sched():
    out = {}
    for f in ("/home/moiz/sniper-data/competitors2/schedule_1067.json", "/home/moiz/sniper-data/haqq_sel/schedule_1068.json",
              "/home/moiz/sniper-data/haqq_sel/schedule_1069.json", "/home/moiz/sniper-data/e2x1_dissect/exec/schedule_1070.json"):
        d = json.load(open(f)); out[int(d["start"])] = (d["ids"], d["slot_leader"])
    cl = {n["pubkey"]: n.get("clientId") or "" for n in json.load(open("/home/moiz/sniper-data/e2x1_dissect/exec/cn.json"))["result"]}
    old = json.load(open("/home/moiz/sniper/ops/overnight/landing/work/rpc/clusternodes_now.json"))["nodes"]
    for k, v in old.items(): cl.setdefault(k, v.get("clientId") or "")
    geo = {r["pk"]: r.get("cc") for r in json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]}
    return out, cl, geo

def leader(slot):
    sch, cl, geo = _sched(); ep = int(slot) // 432000 * 432000
    if ep not in sch: return None, "?"
    ids, sl = sch[ep]; x = sl[int(slot) - ep]
    if x is None or x < 0: return None, "?"
    ld = ids[x]; c = cl.get(ld, "")
    if not c: k = "?"
    elif "Harmonic" in c: k = "harmonic"
    elif "BAM" in c or "Bam" in c: k = "bam"
    elif c == "JitoLabs": k = "jito"
    elif "dancer" in c.lower(): k = "fd"
    elif c == "Agave": k = "agave"
    else: k = "other:" + c
    return ld, k

EU = set("DE NL GB IE FR BE CH AT PL LT CZ FI SE IT ES LU DK NO RO BG UA HU PT LV EE".split())
def area(slot):
    ld, _ = leader(slot); cc_ = _sched()[2].get(ld)
    if cc_ is None: return "?"
    if cc_ == "DE": return "DE"
    if cc_ == "NL": return "NL"
    if cc_ in EU: return "EU-other"
    if cc_ in ("US", "CA"): return "N.America"
    return "Asia/other"

def pct(a, q): return float(np.percentile(a, q)) if len(a) else float("nan")
def med(a): return pct(a, 50)
