#!/usr/bin/env python3
# TRIGGER TEST: "a tweet gets its 2nd (or 3rd) token" -> buy the FIRST token for that tweet, d seconds after the sibling launched
# (d covers seeing the launch + fetching its metadata). Also: buy the new sibling itself. 1 SOL, curve replay with our impact,
# fees 1.25%/side + 0.0015 SOL/tx x2. Exits: timers + TP. Choose on R1+R2, test on R3. SOL curves only (rp tapes).
import os, sys, json, re, gzip, pickle, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(s, i): return s * 212.0 + i / max(SS.get(s, 0), i + 1, 380) * 212.0
FEE = 0.0125; TX = 0.0015; B = 1.0
RX = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")
L = rp.load_launches()
TW = collections.defaultdict(list)
for l in open("meta.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    if not r.get("ok") or r["m"] not in L: continue
    mm = RX.search(r.get("twitter", "")) or RX.search(r.get("website", "")) or RX.search(r.get("desc", ""))
    if mm: TW[int(mm.group(2))].append(r["m"])
EV = []   # (target mint, entry ms, kind, rank, run, tweet id, gap s)
for tid, v in TW.items():
    if len(v) < 2: continue
    v.sort(key=lambda m: (L[m]["slot"], L[m].get("idx") or 0))
    A = v[0]
    for rank in (1, 2):
        if len(v) <= rank: continue
        S = v[rank]; tS = ms(L[S]["slot"], L[S].get("idx") or 0); tA = ms(L[A]["slot"], L[A].get("idx") or 0)
        for d in (0.5, 1.0, 2.0):
            EV.append((A, tS + d * 1000, "first", rank + 1, L[A]["run"], tid, (tS - tA) / 1000, d))
        EV.append((S, tS + 75, "sibling", rank + 1, L[S]["run"], tid, (tS - tA) / 1000, 0.075))
need = collections.defaultdict(set)
for e in EV: need[(L[e[0]]["run"], rp.bucket(e[0]))].add(e[0])
HOLD = [1, 3, 10, 30, 60, 120]
def sim(tr, t_entry):
    kf = -1
    while kf + 1 < len(tr) and ms(tr[kf + 1]["s"], tr[kf + 1]["i"]) <= t_entry: kf += 1
    if kf < 0: return None
    V, Tk = tr[kf]["vsol"], tr[kf]["vtok"]
    if V <= 0 or V > 110e9: return None
    X = B * 1e9 / (1 + FEE); kk = V * Tk; V2 = V + X; Tk2 = kk / V2; q = Tk - Tk2; V, Tk = V2, Tk2
    path = [(t_entry, (V - V * Tk / (Tk + q)) * (1 - FEE) / 1e9)]
    for t in tr[kf + 1:]:
        mt = ms(t["s"], t["i"])
        if mt - t_entry > 130_000: break
        if t["buy"]: V2 = V + t["sol"]; Tk = V * Tk / V2; V = V2
        else: Tk2 = Tk + t["tok"]; V = V * Tk / Tk2; Tk = Tk2
        path.append((mt, (V - V * Tk / (Tk + q)) * (1 - FEE) / 1e9))
    at = lambda sec: [v for m_, v in path if m_ - t_entry <= sec * 1000][-1]
    res = {f"h{h}": at(h) - B - 2 * TX for h in HOLD}
    for tp in (0.1, 0.2, 0.5):
        hit = next((v for m_, v in path if v >= B * (1 + tp) and m_ - t_entry <= 60_000), None)
        res[f"tp{int(tp*100)}_60"] = (hit if hit is not None else at(60)) - B - 2 * TX
    res["vsol_at_entry"] = tr[kf]["vsol"] / 1e9
    return res
def work(key):
    tapes = rp.read_bucket(key[0], key[1], need[key]); out = []
    for e in EV:
        if e[0] in tapes and (L[e[0]]["run"], rp.bucket(e[0])) == key:
            tr = tapes[e[0]]
            if not tr or sum(1 for t in tr if t["vsol"] == 0) > len(tr) / 2: continue
            r = sim(tr, e[1])
            if r: out.append((e, r))
    return out
if __name__ == "__main__":
    R = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(need), chunksize=4): R += o
    pickle.dump(R, gzip.open("sibtrig.pkl.gz", "wb"))
    def show(lab, rows, keys):
        for part, runs in (("TRAIN R1+R2", ("R1", "R2")), ("TEST R3", ("R3",))):
            v = [r for e, r in rows if e[4] in runs]
            if not v: continue
            cells = " | ".join(f"{k} {sum(x[k] for x in v):+7.1f} ({sum(1 for x in v if x[k] > 0) / len(v):.0%} up)" for k in keys)
            print(f"  {lab:46s} {part:11s} n={len(v):5d} | {cells}")
    K = ["h1", "h3", "h10", "h30", "h60", "tp20_60", "tp50_60"]
    for kind, d in (("first", 0.5), ("first", 1.0), ("first", 2.0), ("sibling", 0.075)):
        for rank in (2, 3):
            rows = [(e, r) for e, r in R if e[2] == kind and e[3] == rank and abs(e[7] - d) < 1e-9]
            show(f"buy {'FIRST token' if kind == 'first' else 'the NEW sibling'} when token #{rank} appears, +{d}s", rows, K)
    print("\n  by how fast the 2nd token came (first token, +1 s), sell h10 / h3:")
    for a, b in ((0, 5), (5, 30), (30, 120), (120, 1e9)):
        rows = [(e, r) for e, r in R if e[2] == "first" and e[3] == 2 and e[7] == 1.0 and a <= e[6] < b]
        show(f"   2nd token {a}-{b if b < 1e9 else 'inf'} s after the first", rows, ["h3", "h10", "h30"])
    print("\n  by the first token's curve level when we buy (first token, #2 appears, +1 s):")
    for a, b in ((0, 35), (35, 45), (45, 60), (60, 200)):
        rows = [(e, r) for e, r in R if e[2] == "first" and e[3] == 2 and e[7] == 1.0 and a <= r["vsol_at_entry"] < b]
        show(f"   curve {a}-{b} SOL", rows, ["h3", "h10", "h30"])
