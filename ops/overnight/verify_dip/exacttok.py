#!/usr/bin/env python3
"""verify_dip / exacttok: followers that used the exact-TOKENS 'buy' instruction get the same tokens and pay more SOL after our
buy (failing if the extra cost exceeds their imputed slack), instead of the claim's 'same SOL, fewer tokens'. L35 picks."""
import sys, os, json, gzip, zlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
def rt(tr, ke, fr, s_buy, mode, SL=75.0, H=4):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(R.B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    E = s_buy + H; frs = fr; cnt = collections.Counter()
    for t in tr[ke:]:
        if t["s"] > E or (t["s"] == E and (SL <= 0 or R.pos_ms(t) >= SL)): break
        if t["buy"] and not t["syn"]:
            cnt[t["ixn"]] += 1
            if mode == "tok" and t["ixn"] == "buy" and t["tok"] < T:
                cost = V * t["tok"] // (T - t["tok"]) + 1
                if cost > t["sol"] * (1 + R.slack(t["sig"])): continue
                V += cost; T -= t["tok"]
            else:
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
    return so * (1 - frs) / 1e9 - R.B, cnt
def work(arg):
    (tag, b), keys = arg
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{b:03d}.json.gz"), "rt")); out = []
    want = collections.defaultdict(set)
    for m, a in keys: want[m].add(a)
    for m, ages in want.items():
        c = R.G["L"][m]; tr, _ = R.tape(data[m]["t"]); S = c["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < R.MIN_SELL: continue
            age = round((t["s"] - S) * R.SMS / 1000, 2)
            if age not in ages: continue
            ages.discard(age)
            fr = R.fbps(t); a0 = R.arr(t); ke = k + 1
            while ke < len(tr) and R.arr(tr[ke]) < a0 + 35: ke += 1
            if ke >= len(tr): continue
            a, cnt = rt(tr, ke, fr, tr[ke - 1]["s"], "sol"); b2, _ = rt(tr, ke, fr, tr[ke - 1]["s"], "tok")
            out.append((a, b2, dict(cnt)))
    return out
if __name__ == "__main__":
    sel = json.load(open(os.path.join(HERE, "out", "cv_claim_b05.json")))["35"]["sel"]
    R.init("mine"); by = collections.defaultdict(list)
    for s in sel: by[(R.G["L"][s["m"]]["run"], zlib.crc32(s["m"].encode()) % 256)].append((s["m"], s["age"]))
    res = []
    with Pool(8, initializer=R.init, initargs=("mine",)) as p:
        for o in p.imap_unordered(work, sorted(by.items())): res += o
    ix = collections.Counter()
    for _, _, c in res: ix.update(c)
    print(f"L35 picks {len(res)}: claim model {sum(a for a, _, _ in res) - 0.0016 * len(res):+.2f} | exact-token followers pay more SOL {sum(b for _, b, _ in res) - 0.0016 * len(res):+.2f}")
    print("follower buy instructions inside the holds:", dict(ix.most_common()))
