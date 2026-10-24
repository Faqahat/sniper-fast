#!/usr/bin/env python3
# Wallet-type lists built from R2 (train day) ONLY, so that R3 (test) and R1 (lockbox) features carry no test-day info:
#  - family F1..F10: R2-only consistent winners (>=30 clean trips in R2, P&L > 0, >=60% of active 6-h blocks positive,
#    open share <= 30%, closed P&L > 0), profiled with s3_cards.profile and assigned with the s5_families rules
#  - bot: >= 50 clean round trips in R2
# -> /home/moiz/sniper-data/strategies/patterns/lists_r2.json  {wallet: "F2" | "bot"}
import sys, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import s3_cards as S3
OUT = "/home/moiz/sniper-data/strategies"
F = json.load(open(f"{OUT}/trips/FIELDS.json")); X = {k: i for i, k in enumerate(F)}
W = collections.defaultdict(list)
for f in sorted(glob.glob(f"{OUT}/trips/R2_*.jsonl.gz")):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        if r[X["cslot"]] or r[X["ins"]] or r[X["st"]] == "G": continue
        W[r[0]].append(r)
blk = lambda bt: (bt + 5 * 3600) // (6 * 3600)
lists = {}; fams = collections.Counter()
P = lambda u, k: C[u]["P"][k]
FAM = [
 ("F1", lambda u, a: P(u, "E:sell>=0.5 same slot before") >= 0.3 and P(u, "E:dip>=5% from 3-slot high") >= 0.5 and P(u, "E:creator sold in window") >= 0.4 and (a["hold_med"] or 0) <= 70),
 ("F2", lambda u, a: P(u, "E:sell>=0.5 same slot before") >= 0.3 and P(u, "E:dip>=5% from 3-slot high") >= 0.5 and (a["hold_med"] or 0) <= 70),
 ("F3", lambda u, a: P(u, "E:sell>=0.5 same slot before") + P(u, "E:sell>=0.5 in prev 1-3 slots") >= 0.55 and P(u, "E:dip>=5% from 3-slot high") >= 0.45),
 ("F4", lambda u, a: P(u, "E:buy>=0.5 same slot before") >= 0.5 and P(u, "E:prev trade = BUY same slot") >= 0.7 and (a["hold_med"] or 99) <= 12),
 ("F5", lambda u, a: P(u, "E:token age <=25 slots (5 s)") >= 0.45 and P(u, "E:price +10% in last 10 slots") >= 0.45),
 ("F6", lambda u, a: (P(u, "E:buy>=0.5 same slot before") >= 0.45 or P(u, "E:net flow >=+1 SOL (3 slots)") >= 0.6) and P(u, "X:>=3 sells (ladder)") >= 0.5),
 ("F7", lambda u, a: P(u, "E:quiet >=20 slots before") >= 0.25),
 ("F8", lambda u, a: P(u, "X:scaled in (>=2 buys)") >= 0.4 and (a["hold_med"] or 0) >= 60),
 ("F9", lambda u, a: a["n_clean"] >= 300 and 20 <= (a["hold_med"] or 0) <= 300),
 ("F10", lambda u, a: True)]
C = {}
for u, rs in W.items():
    if len(rs) >= 50: lists[u] = "bot"
    if len(rs) < 30: continue
    pn = [r[X["pnl"]] for r in rs]
    B = collections.defaultdict(lambda: [0, 0.0])
    for r in rs: b = B[blk(r[X["bt"]])]; b[0] += 1; b[1] += r[X["pnl"]]
    act = [x for x in B.values() if x[0] >= 3]
    opn = sum(1 for r in rs if r[X["st"]] == "O") / len(rs)
    pc = sum(r[X["pnl"]] for r in rs if r[X["st"]] == "C")
    if not (sum(pn) > 0 and len(act) >= 3 and sum(1 for x in act if x[1] > 0) >= 0.6 * len(act) and opn <= 0.3 and pc > 0): continue
    hold = [r[X["hold"]] for r in rs if r[X["st"]] == "C" and r[X["hold"]] is not None and r[X["hold"]] >= 0]
    a = dict(hold_med=statistics.median(hold) if hold else None, n_clean=len(rs), pnl=sum(pn))
    C[u] = dict(P=S3.profile(rs), a=a)
    fam = next(f for f, rule in FAM if rule(u, a))
    lists[u] = fam; fams[fam] += 1
json.dump(lists, open(f"{OUT}/patterns/lists_r2.json", "w"))
print("R2-only lists:", len(lists), "wallets;", sum(1 for v in lists.values() if v == "bot"), "bot-only;", dict(sorted(fams.items())))
for k in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX", "9qz7cWBq", "pXGQ6J2z"):
    print(" ", k, next((v for u, v in lists.items() if u.startswith(k)), None))
