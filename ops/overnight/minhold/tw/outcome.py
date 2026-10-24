#!/usr/bin/env python3
# Per launch (R1–R3 tapes, SOL curves): what happens after launch, and a realistic "buy at launch" replay.
# Our buy: 1 SOL landing T ms (block position) after the create tx (T = 75 and 200 ms; 2000 ms = "after seeing the tweet link").
# Replay inserts our buy into the curve (followers kept; plus a pessimistic variant dropping outside buys in the 2 slots after us).
# Exits: timers 1/3/10/30/60/120/300 s, TP 20/50/100% with 60 s / 300 s caps, SL 20% with 300 s cap. Costs: 1.25% fee each side + 0.0015 SOL/tx x2.
import os, sys, json, collections, pickle, gzip
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(s, i): return s * 212.0 + i / max(SS.get(s, 0), i + 1, 380) * 212.0
FEE = 0.0125; TX = 0.0015; B = 1.0
L = rp.load_launches(); byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
HOLD = [1, 3, 10, 30, 60, 120, 300]
def sim(tr, c, T, drop2):
    t_create = ms(c["slot"], c.get("idx") or 0)
    kf = -1
    while kf + 1 < len(tr) and ms(tr[kf + 1]["s"], tr[kf + 1]["i"]) - t_create <= T: kf += 1
    if kf < 0: V, Tk = 30e9, 1_073_000_000_000_000
    else: V, Tk = tr[kf]["vsol"], tr[kf]["vtok"]
    if V <= 0 or V > 110e9: return None
    X = B * 1e9 / (1 + FEE); kk = V * Tk; V2 = V + X; Tk2 = kk / V2; q = Tk - Tk2; V, Tk = V2, Tk2
    fill = t_create + T; fs = tr[kf]["s"] if kf >= 0 else c["slot"]
    path = [(fill, (V - V * Tk / (Tk + q)) * (1 - FEE) / 1e9)]
    for t in tr[kf + 1:]:
        mt = ms(t["s"], t["i"])
        if mt - fill > 310_000: break
        if t["buy"]:
            if drop2 and t["s"] - fs <= 2: continue
            V2 = V + t["sol"]; Tk = V * Tk / V2; V = V2
        else:
            Tk2 = Tk + t["tok"]; V = V * Tk / Tk2; Tk = Tk2
        path.append((mt, (V - V * Tk / (Tk + q)) * (1 - FEE) / 1e9))
    def at(sec): return [v for m_, v in path if m_ - fill <= sec * 1000][-1]
    res = {f"h{h}": at(h) - B - 2 * TX for h in HOLD}
    for tp in (0.2, 0.5, 1.0):
        for cap in (60, 300):
            hit = next((v for m_, v in path if v >= B * (1 + tp) and m_ - fill <= cap * 1000), None)
            res[f"tp{int(tp*100)}_{cap}"] = (hit if hit is not None else at(cap)) - B - 2 * TX
    sl = next((v for m_, v in path if v <= B * 0.8 and m_ - fill <= 300_000), None)
    res["sl20_300"] = (sl if sl is not None else at(300)) - B - 2 * TX
    res["peak5m"] = max(v for m_, v in path if m_ - fill <= 300_000) / B
    return res
def work(key):
    out = {}
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        c = L[m]
        if not tr or sum(1 for t in tr if t["vsol"] == 0) > len(tr) / 2: continue
        if c.get("mayhem"): continue
        t_create = ms(c["slot"], c.get("idx") or 0); dev = c.get("creator")
        o = dict(run=c["run"], bt=c["bt"], name=c.get("name"), creator=dev)
        o["dev_buy"] = sum(t["sol"] for t in tr if t["user"] == dev and t["buy"] and t["s"] == c["slot"]) / 1e9
        for win in (10, 60, 300):
            w = [t for t in tr if 0 <= ms(t["s"], t["i"]) - t_create <= win * 1000 and t["user"] != dev]
            o[f"buy{win}"] = sum(t["sol"] for t in w if t["buy"]) / 1e9; o[f"sell{win}"] = sum(t["sol"] for t in w if not t["buy"]) / 1e9
            o[f"buyers{win}"] = len({t["user"] for t in w if t["buy"]})
        o["maxv"] = max(t["vsol"] for t in tr) / 1e9; o["grad"] = o["maxv"] >= 114.9
        for T in (75, 200, 2000):
            for d2 in (False, True):
                o[f"s{T}{'d' if d2 else ''}"] = sim(tr, c, T, d2)
        out[m] = o
    return out
if __name__ == "__main__":
    R = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): R.update(o)
    pickle.dump(R, gzip.open("outcome.pkl.gz", "wb"))
    print("launches with SOL-curve tapes:", len(R))
