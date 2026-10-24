#!/usr/bin/env python3
# are we still early enough? For T = 35 / 75 / 150 ms after their first buy: buyers AHEAD of us (between their buy and our fill) and
# buyers AFTER us (our exit liquidity) within 1 slot / 5 s of our fill, and the share of all the follower SOL of the first 5 s that
# lands after us. Tapes, read-only -> out/after.json
import os, sys, json, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
T, _ = lib3.load_tapes(); P = [p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if not p.get("nobuy") and not p["mayhem"]]
def msf(t):
    n = lib3.slot_size(t["s"]) or 450
    return t["s"] * 212.0 + min(t["i"] / max(n, t["i"] + 1), 0.999) * 212.0
out = {}
for w8, W in lib3.W3.items():
    v = [p for p in P if p["w"] == w8]; o = {}
    for TT in (0, 35, 75, 150):
        ah_n = []; ah_sol = []; af1_n = []; af1_sol = []; af5_sol = []; share = []
        for p in v:
            tr = T[p["m"]]; k0 = p["k0"]; m0 = msf(tr[k0]); idx = k0 + 1
            while idx < len(tr) and msf(tr[idx]) - m0 <= TT: idx += 1
            fs = tr[idx - 1]["s"]
            ahead = [t for t in tr[k0 + 1:idx] if t["buy"] and t["user"] != W]
            after = [t for t in tr[idx:] if t["buy"] and t["user"] != W and t["s"] - tr[k0]["s"] <= 24]
            a1 = [t for t in after if t["s"] - fs <= 1]
            ah_n.append(len(ahead)); ah_sol.append(sum(t["sol"] for t in ahead) / 1e9); af1_n.append(len(a1)); af1_sol.append(sum(t["sol"] for t in a1) / 1e9)
            tot = sum(t["sol"] for t in ahead) + sum(t["sol"] for t in after); af5_sol.append(sum(t["sol"] for t in after) / 1e9)
            share.append(sum(t["sol"] for t in after) / tot if tot else 0)
        o[TT] = dict(ahead_n=statistics.median(ah_n), ahead_sol=statistics.median(ah_sol), after1_n=statistics.median(af1_n), after1_sol=statistics.median(af1_sol),
                     after5s_sol=statistics.median(af5_sol), share_after=statistics.median(share), none_after1=sum(1 for x in af1_n if x == 0) / len(af1_n))
        print(f"{w8} T={TT:3d} ms | ahead of us: {o[TT]['ahead_n']:.0f} buys / {o[TT]['ahead_sol']:.2f} SOL | after us within 1 slot: {o[TT]['after1_n']:.0f} buys / {o[TT]['after1_sol']:.2f} SOL "
              f"(none: {o[TT]['none_after1']:.0%}) | after us within 5 s of their buy: {o[TT]['after5s_sol']:.2f} SOL = {o[TT]['share_after']:.0%} of the follower SOL")
    out[w8] = o
json.dump(out, open(os.path.join(lib3.HERE, "out/after.json"), "w"), indent=1)
