#!/usr/bin/env python3
# DF7e replay step 1: market trigger counts vs his attempts (take rate) in his active window; his landing delays.
import json, collections, numpy as np, sys
import rlib, core
D = rlib.load(); T = D.T
B = json.load(open("/home/moiz/sniper-data/landing2/df7e/buys2.json"))
H = np.load if False else None
key = {}
sh = T["sigh"]
o = np.argsort(sh); shs = sh[o]
def find(sig, buy, sol):
    h = rlib.sigh(sig); a = np.searchsorted(shs, h); out = []
    while a < len(shs) and shs[a] == h:
        k = o[a]; out.append(k); a += 1
    for k in out:
        if T["buy"][k] == buy and (sol is None or abs(int(T["sol"][k]) - sol) < 10): return k
    return out[0] if out else None
uid = D.users.index(rlib.W) if rlib.W in D.users else -1
print("his trades in clean universe:", int((T["user"] == uid).sum()), "of his filled buys+sells; his buys", int(((T["user"] == uid) & (T["buy"] == 1)).sum()))
hit = 0; rows = []
for x in B:
    ts = x.get("trig_sig")
    if not ts: continue
    buy = 0 if x["trig"].startswith("dump") else 1
    k = find(ts, buy, x.get("tsol"))
    if k is None: continue
    hit += 1
    # his position (filled: his own trade; failed: unknown position -> use bt/slot only)
    rows.append((k, x["trig"], x["ok"], x["s"], x["i"], x.get("net")))
print("his attempts with a trigger:", sum(1 for x in B if x.get("trig_sig")), "found in clean universe:", hit)
s0 = min(x["s"] for x in B); s1 = max(x["s"] for x in B)
win = (T["slot"] >= s0) & (T["slot"] <= s1) & D.full_hist[T["mint"]]
hrs = (s1 - s0) * core.SLOT_SEC / 3600
ages = D.age * core.SLOT_SEC
sell = T["buy"] == 0; sol = T["sol"] / 1e9
dump = win & sell & (sol >= 0.3) & (D.drop >= 0.03)
bigb = win & (T["buy"] == 1) & (sol >= 0.5)
C = {"dump": dump & (ages > 10), "young dump": dump & (ages <= 10), "wake-up": bigb & (D.gap >= 10), "big-buy": bigb & (D.gap < 10)}
Hk = collections.defaultdict(set)
for k, t, ok, s, i, net in rows:
    c = "dump" if t == "dump backrun" else "young dump" if t.startswith("dump backrun (") else "wake-up" if t.startswith("wake") else "big-buy"
    Hk[c].add(k)
print(f"window {hrs:.1f} h")
for c, m in C.items():
    print(f"{c:10s}: market {m.sum():7d} ({m.sum()/hrs:6.0f}/h) | his distinct triggers {len(Hk[c]):5d} ({len(Hk[c])/hrs:5.0f}/h) take {len(Hk[c])/max(1,m.sum()):.3f}")
    idx = np.where(m)[0]; hk = np.zeros(len(T), bool); hk[list(Hk[c])] = True
    for name, x, ed in (("trig SOL", sol, [0.3, 0.5, 1, 2, 4, 8, 1e9]), ("curve", D.curve, [-1, 3, 10, 25, 50, 90]), ("age s", ages, [-1, 5, 10, 15, 60, 300, 1800, 1e9]),
                        ("drop", D.drop, [-9, -0.01, 0.03, 0.06, 0.1, 0.2, 1]), ("gap", D.gap.astype(float), [-1, 0, 1, 3, 10, 30, 1e9])):
        cells = []
        for a, b in zip(ed[:-1], ed[1:]):
            mm = m & (x > a) & (x <= b); n = mm.sum()
            if n >= 50: cells.append(f"({a},{b}]:{hk[mm].sum()}/{n}={hk[mm].sum()/n:.3f}")
        print("    ", name, " ".join(cells))
json.dump([[int(k), t, ok, s, i, net] for k, t, ok, s, i, net in rows], open(rlib.DD + "/his_triggers.json", "w"))
