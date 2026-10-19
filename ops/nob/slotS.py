# same-slot (create slot) activity: his nb picks vs rule-matched random peers. Descriptive only (not visible for same-slot entries).
import json, statistics as st
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
D = "/root/nob/"
rows = {json.loads(l)["mint"]: json.loads(l) for l in open(D + "ds.jsonl")}
blk = {}
for f in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for l in open(D + f):
        r = json.loads(l)
        if not r.get("missing"):
            blk.setdefault(r["mint"], r)
def info(m):
    r = blk[m]
    pos = None
    buys = []
    for i, x in enumerate(r["later"]):
        if x.get("his"):
            if pos is None:
                pos = len(buys)
            continue
        if x.get("ok") and not x.get("glued") and any(e[0] for e in x["ev"]):
            buys.append((x["payer"], sum(e[2] for e in x["ev"] if e[0])))
    return buys, pos
H = [m for m, f in rows.items() if f["his"] and f["nb"] and f["slot"] >= 457470000 and not f["quote"]]
P = [m for m, f in rows.items() if f["in_rand"] and not f["his"] and f["nb"] and not f["quote"] and f["v0_std"] and not f["mayhem"] and f["dev_sol"] >= 0.5 and f["slot"] >= 457470000]
P2 = [m for m, f in rows.items() if f["in_rand"] and not f["his"] and f["nb"] and not f["quote"] and f["v0_std"] and not f["mayhem"] and f["slot"] >= 457470000]
def summ(ms, lab):
    nb = [len(info(m)[0]) for m in ms]
    any1 = sum(1 for x in nb if x >= 1)
    print(f"{lab:<44} n={len(ms):4d}  other indep buys in create slot: mean {st.mean(nb):.2f}  >=1: {100*any1/len(ms):.0f}%  >=3: {100*sum(1 for x in nb if x>=3)/len(ms):.0f}%")
summ(H, "his nb picks (all)")
summ([m for m in H if rows[m]["h_off"] == 0], "his nb picks, offset 0")
summ([m for m in H if rows[m]["h_off"] == 1], "his nb picks, offset 1")
summ(P, "random nb peers: not mayhem & dev>=0.5")
summ(P2, "random nb peers: not mayhem")
# offset 0: buys ahead of him vs after him
ah = [info(m)[1] for m in H if rows[m]["h_off"] == 0]
af = [len(info(m)[0]) - (info(m)[1] or 0) for m in H if rows[m]["h_off"] == 0]
print("offset-0 picks: indep buys AHEAD of him mean %.2f (>=1: %.0f%%), AFTER him in same slot mean %.2f" % (st.mean(ah), 100 * sum(1 for x in ah if x >= 1) / len(ah), st.mean(af)))
# co-buyer wallets: who else buys his picks in the create slot, and how often they buy peers
from collections import Counter
ch = Counter(); cp = Counter()
for m in H:
    for w in set(b[0] for b in info(m)[0]): ch[w] += 1
for m in P2:
    for w in set(b[0] for b in info(m)[0]): cp[w] += 1
print("\ntop same-slot co-buyers on his nb picks (count on his %d picks | count on %d random non-mayhem nb peers, x27 = pop. est.)" % (len(H), len(P2)))
for w, n in ch.most_common(12):
    print(f"   {w[:12]}  his {n:3d}   peers {cp[w]:3d} (~{cp[w]*27} in population)")
