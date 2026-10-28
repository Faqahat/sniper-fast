"""exec agent shared helpers (read-only inputs).
Chain clock = dv8 convention: slot*212 ms + idx/blocksize*212, blocksize = max pump tx index seen in the slot + 1
(haqqml/fresh slots.npy up to 10-28 18:41 PKT + exec/slots_tail.npy after). Leader schedule epochs 1068/1069 (haqq_sel) +
1070 (exec/schedule_1070.json, getLeaderSchedule 10-28); client ids from getClusterNodes 10-28 (exec/cn.json)."""
import json, pickle, time, functools, collections
import numpy as np
R = "/home/moiz/sniper-data/e2x1_dissect/recon"; X = "/home/moiz/sniper-data/e2x1_dissect/exec"
WAL = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
SIB = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
SMS = 212.0
D1 = (1793113200, 1793199600); D0 = (1793026800, 1793113200)
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
gm = lambda m: f"https://gmgn.ai/sol/token/{m}"
ss = lambda s: f"https://solscan.io/tx/{s}"

@functools.lru_cache(None)
def lots():
    return pickle.load(open(f"{R}/lots.pkl", "rb"))

@functools.lru_cache(None)
def tape():
    return pickle.load(open(f"{R}/tape.pkl", "rb"))

@functools.lru_cache(None)
def slot_sizes():
    a = np.load("/home/moiz/sniper-data/haqqml/fresh/tape/slots.npy")
    try:
        b = np.load(f"{X}/slots_tail.npy"); a = np.concatenate([a, b[b["slot"] > a["slot"].max()]])
    except FileNotFoundError:
        pass
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
    for f in ("/home/moiz/sniper-data/haqq_sel/schedule_1068.json", "/home/moiz/sniper-data/haqq_sel/schedule_1069.json", f"{X}/schedule_1070.json"):
        d = json.load(open(f)); out[int(d["start"])] = (d["ids"], d["slot_leader"])
    cl = {n["pubkey"]: n.get("clientId") or "" for n in json.load(open(f"{X}/cn.json"))["result"]}
    old = json.load(open("/home/moiz/sniper/ops/overnight/landing/work/rpc/clusternodes_now.json"))["nodes"]
    for k, v in old.items(): cl.setdefault(k, v.get("clientId") or "")
    return out, cl

def leader(slot):
    sch, cl = _sched(); ep = int(slot) // 432000 * 432000
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

def pct(a, q): return float(np.percentile(a, q)) if len(a) else float("nan")
def med(a): return pct(a, 50)
