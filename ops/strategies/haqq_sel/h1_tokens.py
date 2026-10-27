#!/usr/bin/env python3
"""HAQQ_SEL step 1 (read-only): the token list. haqqiUUX's pump.fun trades (as trade user or tx signer) on the 24 h chain tape
(our recording, decoded with real/decode.py + build.py into /home/moiz/sniper-data/haqq_sel/tab). Only mints and each mint's
active span are kept (first / last haqq trade); his sizes, prices and P&L are NOT used anywhere. MEASURED.
Out: DATA/tokens.json"""
import json, time, collections
import numpy as np
DATA = "/home/moiz/sniper-data/haqq_sel"; TAB = f"{DATA}/tab"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
W0 = 1793038500; W1 = 1793124900          # 10-26 23:15 -> 10-27 23:15 PKT (24 h)
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
T = np.load(f"{TAB}/trades.npy")
h = idm[HAQQ]
m = ((T["user"] == h) | (T["signer"] == h)) & (T["bt"] >= W0) & (T["bt"] < W1)
X = T[m]
print("haqq trades in window", len(X), "buys", int(X["buy"].sum()), "sells", int((1 - X["buy"]).sum()))
per = collections.defaultdict(list)
for r in X: per[int(r["mint"])].append((int(r["slot"]), int(r["bt"]), int(r["buy"])))
cr = json.load(open(f"{TAB}/creates.json"))
out = []
for mi, rows in per.items():
    mint = ids[mi]; rows.sort()
    c = cr.get(mint) or {}
    out.append(dict(mint=mint, first_slot=rows[0][0], last_slot=rows[-1][0], first_bt=rows[0][1], last_bt=rows[-1][1], n_tx=len(rows),
                    create_slot=c.get("slot"), create_bt=c.get("bt"), seen_create=bool(c), mayhem=bool(c.get("mayhem") or c.get("mayhem_ix"))))
out.sort(key=lambda x: x["first_bt"])
json.dump(dict(window=[W0, W1], haqq=HAQQ, tokens=out), open(f"{DATA}/tokens.json", "w"), indent=0)
S = np.load(f"{TAB}/slots.npy"); bt = S["bt"].astype(np.int64)
print("tokens", len(out), "span", pkt(out[0]["first_bt"]), "->", pkt(out[-1]["last_bt"]), "| create seen on tape", sum(x["seen_create"] for x in out), "mayhem", sum(x["mayhem"] for x in out))
print("by hour PKT", sorted(collections.Counter(time.gmtime(x["first_bt"] + 18000).tm_hour for x in out).items()))
age = [ (x["first_slot"] - x["create_slot"]) * 0.212 for x in out if x["create_slot"]]
print("age at his first trade (s): p10/50/90", np.percentile(age, [10, 50, 90]).round(1))
act = [(x["last_bt"] - x["first_bt"]) for x in out]
print("active span (s) p50/90", np.percentile(act, [50, 90]))
# tape coverage per hour
for hh in range(W0, W1, 3600):
    n = int(((bt >= hh) & (bt < hh + 3600)).sum()); print(pkt(hh)[6:11], f"cov {n / (3600 / 0.2118):.3f}", end=" |")
print()
