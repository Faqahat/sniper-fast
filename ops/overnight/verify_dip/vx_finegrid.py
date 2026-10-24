#!/usr/bin/env python3
"""verify_dip / vx_finegrid: PnL of given events on a fine grid of entry delays L (0..300 ms step 5, proxy units), claim-spec
variant (c) and own-arrival-slot variant (t), with optional removal of named wallets' buys after our entry (competitor
reaction stress). Own replay code (vx_replay.py).
usage: python3 -I -B vx_finegrid.py <keys.json [[m, age], ...]> <out.json> [drop_wallets.json]"""
import sys, os, json, gzip, zlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
GRID = list(range(0, 305, 5))
DROP = set()
def init2(src, drop):
    R.init(src); DROP.update(drop)
def rt(tr, ke, fr, s_buy, SL=75.0, H=4, drop=None):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(R.B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    E = s_buy + H; frs = fr
    for t in tr[ke:]:
        if t["s"] > E or (t["s"] == E and (SL <= 0 or R.pos_ms(t) >= SL)): break
        if t["buy"] and drop and t["user"] in drop: continue
        if t["buy"] and not t["syn"]:
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + R.slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]:
            d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else:
            so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = R.fbps(t)
        if V >= 110e9 or T <= R.VT_DONE: break
    so = V * q // (T + q)
    return so * (1 - frs) / 1e9 - R.B
def work(arg):
    (tag, b), keys = arg
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{b:03d}.json.gz"), "rt")); out = {}
    want = collections.defaultdict(set)
    for m, a in keys: want[m].add(a)
    for m, ages in want.items():
        c = R.G["L"][m]; tr, _ = R.tape(data[m]["t"]); S = c["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < R.MIN_SELL: continue
            age = round((t["s"] - S) * R.SMS / 1000, 2)
            if age not in ages: continue
            ages.discard(age)                     # the event = the first >= 1 SOL sell of that slot
            fr = R.fbps(t); a0 = R.arr(t); res = {}
            for Lm in GRID:
                ke = k + 1
                while ke < len(tr) and R.arr(tr[ke]) < a0 + Lm: ke += 1
                if ke >= len(tr): continue
                s_in = tr[ke - 1]["s"]; s_true = int((a0 + Lm) // R.SMS)
                res[Lm] = (round(rt(tr, ke, fr, s_in), 6), round(rt(tr, ke, fr, s_true), 6), ke - k - 1,
                           round(rt(tr, ke, fr, s_in, drop=DROP), 6) if DROP else None)
            out[f"{m}|{age}"] = res
    return out
if __name__ == "__main__":
    keys = json.load(open(sys.argv[1])); outp = sys.argv[2]
    drop = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else []
    R.init("mine")
    by = collections.defaultdict(list)
    for m, a in keys:
        c = R.G["L"][m]; by[(c["run"], zlib.crc32(m.encode()) % 256)].append((m, a))
    res = {}
    with Pool(8, initializer=init2, initargs=("mine", drop)) as p:
        for o in p.imap_unordered(work, sorted(by.items())): res.update(o)
    json.dump(res, open(outp, "w"))
    print("events", len(keys), "priced", len(res))
