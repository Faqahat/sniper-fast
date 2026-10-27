"""DV8 shared helpers (read-only). Tape = /home/moiz/sniper-data/dv8/tab (built by presend/real/decode.py + build.py from
collect/run_* 10-22 03:07 -> 10-28 01:12 PKT)."""
import json, time, functools
import numpy as np
D = "/home/moiz/sniper-data/dv8"; TAB = f"{D}/tab"
SMS = 212.0                       # ms per slot (chain clock, same as haqq_strat)
DAY0 = 1793038500 - 5 * 86400     # 10-21 23:15 PKT; day k = [DAY0 + k*86400, +86400)
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
WAL = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
FEE = 0.0125


def day_of(t): return int((t - DAY0) // 86400)
def day_name(k): return f"D{k} {pkt(DAY0 + k * 86400)}->{pkt(DAY0 + (k + 1) * 86400)}"


@functools.lru_cache(None)
def slot_sizes():
    S = np.load(f"{TAB}/slots.npy"); s0 = int(S["slot"].min())
    bsz = np.zeros(int(S["slot"].max()) - s0 + 1, np.float64); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.int64) + 1
    bsz[bsz <= 0] = 400
    return s0, bsz


def cc(sl, ix):
    """chain clock ms of (slot, tx index): slot*212 + idx/blocksize*212 (vectorised)"""
    s0, bsz = slot_sizes()
    sl = np.asarray(sl, np.int64); ix = np.asarray(ix, np.float64)
    n = bsz[np.clip(sl - s0, 0, len(bsz) - 1)]
    return sl * SMS + ix / np.maximum(n, ix + 1.0) * SMS


@functools.lru_cache(None)
def _sched():
    out = {}
    for f in ("/home/moiz/sniper-data/haqq/schedule_1065.json", "/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json",
              "/home/moiz/sniper-data/competitors2/schedule_1067.json", "/home/moiz/sniper-data/haqq_sel/schedule_1068.json",
              "/home/moiz/sniper-data/haqq_sel/schedule_1069.json"):
        d = json.load(open(f)); out[int(d["start"])] = (d["ids"], d["slot_leader"])
    nodes = json.load(open("/home/moiz/sniper/ops/overnight/landing/work/rpc/clusternodes_now.json"))["nodes"]
    cl = {k: v.get("clientId") or "" for k, v in nodes.items()}
    rt = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
    for k, v in rt.items():
        if v.get("client"): cl.setdefault(k, v["client"])
    near = {r: set(l.strip() for l in open(f"/home/moiz/sniper/ops/region/near_leaders_{r.lower()}.txt") if l.strip()) for r in ("FRA", "AMS")}
    return out, cl, near


def leader_of(slot):
    sch, _, _ = _sched()
    ep = int(slot) // 432000 * 432000
    if ep not in sch: return None
    ids, sl = sch[ep]; x = sl[int(slot) - ep]
    return None if x is None or x < 0 else ids[x]


def client_class(c):
    if not c: return "?"
    if "Harmonic" in c: return "harmonic"
    if "Bam" in c or "BAM" in c: return "bam"
    if c == "JitoLabs": return "jito"
    if "dancer" in c.lower() or c == "Frankendancer": return "fd"
    if c == "Agave": return "agave"
    return "other"


def leader_info(slot, region="FRA"):
    """(leader pubkey or None, client class, near bool or None) for a slot; near per the region's live near list"""
    sch, cl, near = _sched()
    ld = leader_of(slot)
    if ld is None: return None, "?", None
    return ld, client_class(cl.get(ld, "")), ld in near[region]


def ids_map():
    ids = json.load(open(f"{TAB}/ids.json")); return ids, {k: i for i, k in enumerate(ids)}


@functools.lru_cache(None)
def _sbt():
    S = np.load(f"{TAB}/slots.npy"); ok = S["bt"] > 1.7e9
    return S["slot"][ok].astype(np.float64), S["bt"][ok].astype(np.float64)


def slot_time(slot):
    s, b = _sbt(); return float(np.interp(float(slot), s, b))
