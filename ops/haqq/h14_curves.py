#!/usr/bin/env python3
# haqq SELL study, step 14: counterfactual exit values per lot. For every clean closed lot: replay the curve from its buy with
# THIS lot's own sell(s) removed (others' buys = their SOL in, others' sells = their tokens out; haqq's other lots kept), and the
# lot's net value (pump fees, one sell tx cost) if its sell landed at time t = (ref slot + d) x 212 ms + L, for d = 1..210 and
# L = 0 / 35 / 50 / 75 ms (block-position time proxy). -> sniper-data/haqq/curves.pkl {li: dict(ref, bslot, v0, v35, v50, v75)}
import sys, json, pickle, zlib, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
from multiprocessing import Pool
DM = 210; LATS = (0, 35, 50, 75); SELL_TX = 0.000325e9           # haqq's median sell tx cost (fee 125k + 0.0002 tip)
SS = {}
def init():
    for run in ("R1", "R2", "R3", "R4"):
        for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(s, 400), i + 1) * H.SMS
LOTS = None
def work(b):
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb")); out = {}
    for li, l in LOTS.get(b, []):
        d = tp.get(l["m"])
        if d is None: continue
        T = d["T"]; Wl = d["W"]; k = l["buy"]["k"]
        if k >= len(T) or Wl[T[k, 5]] != H.W: continue
        own = {(x["s"], x["i"]) for x in l["sells"]}
        q = float(T[k, 8]); cost = l["cost"] * 1e9
        ref = l["buy"]["s"] - l["buy"]["trig_ds"] if l["buy"]["dip"] else None
        if ref is None:
            prev = next((j for j in range(k - 1, -1, -1) if Wl[T[j, 5]] != H.W), None)
            ref = int(T[prev, 0]) if prev is not None else int(T[k, 0])
        V = float(T[k, 9]); Tk = float(T[k, 10]); fr = (T[k, 13] + T[k, 14]) / 1e4
        # replay trades after the buy; record (arrival, V, Tk, fr) after each
        ev = [(A(int(T[k, 0]), int(T[k, 1])), V, Tk, fr)]
        tmax = (ref + DM + 1) * H.SMS + 100
        for j in range(k + 1, len(T)):
            a = A(int(T[j, 0]), int(T[j, 1]))
            if a > tmax: break
            if (int(T[j, 0]), int(T[j, 1])) in own and Wl[T[j, 5]] == H.W and not T[j, 6]: continue
            if T[j, 6]:
                x = float(T[j, 7]); dq = Tk * x / (V + x); V += x; Tk -= dq
            else:
                tq = float(T[j, 8]); so = V * tq / (Tk + tq); V -= so; Tk += tq
            fr = (T[j, 13] + T[j, 14]) / 1e4
            ev.append((a, V, Tk, fr))
        ar = np.array([e[0] for e in ev]); Vs = np.array([e[1] for e in ev]); Ts = np.array([e[2] for e in ev]); Fs = np.array([e[3] for e in ev])
        val = (Vs * q / (Ts + q) * (1 - Fs) - SELL_TX) / 1e9           # net SOL back if sold right after that trade
        rec = dict(ref=ref, bslot=int(T[k, 0]) - ref, cost=l["cost"])
        for L in LATS:
            t = (ref + np.arange(DM + 1)) * H.SMS + L
            jj = np.searchsorted(ar, t, side="right") - 1
            v = np.where(jj >= 0, val[np.maximum(jj, 0)], np.nan)
            rec[f"v{L}"] = v.astype(np.float32)
        out[li] = rec
    return out
if __name__ == "__main__":
    lots = json.load(open(f"{H.OUT}/lots.json"))
    by = collections.defaultdict(list)
    for li, l in enumerate(lots):
        if l["closed"] and not l["censored"] and not l["brk"]: by[zlib.crc32(l["m"].encode()) % 64].append((li, l))
    LOTS = by
    R = {}
    with Pool(6, initializer=init) as p:
        for o in p.imap_unordered(work, range(64)): R.update(o)
    pickle.dump(R, open(f"{H.OUT}/curves.pkl", "wb"), protocol=4)
    print("curves", len(R))
