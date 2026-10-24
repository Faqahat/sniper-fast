#!/usr/bin/env python3
# THE 1.5 SOL GROUP (read-only, R2+R3 tapes + R3 raw txs): BNnN2Mqf / 3GzBLpxT / 2pLugeBD / 7PteyyyR.
# 1) how they move together: same slot? block index gaps? order? same size? sells together?
# 2) bundled? same tx / consecutive txs / shared tip / same fee payer (raw txs: signers, cup, cul, tips, progs)
# 3) who do they copy? wallets buying the same token shortly BEFORE the group's first buy, counted across the group's tokens
import os, sys, json, gzip, glob, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
G = ["BNnN2MqfWLvgThYBsv6v8JQaYZXYKYahC5YCy27Ct1cX", "3GzBLpxTWWTPWwBYQ8Jgrz5XLUCg9aY6HiB3GEBUBAv6", "2pLugeBDKkFxaD2JKxSifNXoegYQyVpVoFikc6SEdqdv", "7PteyyyR4pvnCUr48bqQN7mxMAuQV4amBkYFNWjohoms"]
GS = set(G); SL = 0.212
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
L = rp.load_launches()
mints = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/R[23]_*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        if any(g in line[:50] for g in G): mints.add(json.loads(line)[1])
byb = collections.defaultdict(set)
for m in mints: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    out = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        S0 = L[m]["slot"]; dev = L[m].get("creator")
        gb = [(k, t) for k, t in enumerate(tr) if t["user"] in GS and t["buy"]]
        if not gb: continue
        k0 = gb[0][0]; t0 = tr[k0]
        first = {}
        for k, t in gb:
            first.setdefault(t["user"], (k, t))
        sells = collections.defaultdict(list)
        for k, t in enumerate(tr):
            if t["user"] in GS and not t["buy"]: sells[t["user"]].append((k, t))
        pre = []
        for t in tr[max(0, k0 - 60):k0]:
            dt = (t0["s"] - t["s"]) * SL
            if t["buy"] and dt <= 30 and t["user"] not in GS: pre.append((t["user"], dt, t["sol"] / 1e9, t["user"] == dev, t["s"] == t0["s"]))
        out.append(dict(m=m, run=L[m]["run"], age=(t0["s"] - S0) * SL, vsol=t0["vsol"] / 1e9, dev=dev,
                        buys={u: dict(s=t["s"], i=t["i"], sol=t["sol"] / 1e9, sig=t["sig"], payer=t["payer"], fee=t["fee"], tips=t["tips"]) for u, (k, t) in first.items()},
                        sells={u: [dict(s=t["s"], i=t["i"], sol=t["sol"] / 1e9, sig=t["sig"]) for k, t in v] for u, v in sells.items()},
                        pre=pre, pre_last=(tr[k0 - 1]["user"], (t0["s"] - tr[k0 - 1]["s"]) * SL, tr[k0 - 1]["buy"], tr[k0 - 1]["sol"] / 1e9) if k0 else None,
                        dev_sell_before_exit=None))
    return out
if __name__ == "__main__":
    P = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): P += o
    json.dump(P, open("grp4/grp4_tokens.json", "w"))
    print(f"tokens the group bought (R2+R3): {len(P)} | by run {collections.Counter(x['run'] for x in P)}")
    nmem = collections.Counter(len(x["buys"]) for x in P); print("how many of the 4 bought each token:", sorted(nmem.items()))
    same = sum(1 for x in P if len({b["s"] for b in x["buys"].values()}) == 1 and len(x["buys"]) > 1)
    print(f"all members' first buys in ONE slot: {same} of {sum(1 for x in P if len(x['buys']) > 1)}")
    gaps = []; orders = collections.Counter(); payers = collections.Counter(); sizes = collections.Counter()
    for x in P:
        b = sorted(x["buys"].items(), key=lambda kv: (kv[1]["s"], kv[1]["i"]))
        if len(b) > 1 and len({v["s"] for _, v in b}) == 1:
            idx = [v["i"] for _, v in b]; gaps += [idx[j + 1] - idx[j] for j in range(len(idx) - 1)]
            orders[" > ".join(u[:4] for u, _ in b)] += 1
        for u, v in b: payers[(u[:8], v["payer"][:8] if v["payer"] else None)] += 1; sizes[round(v["sol"], 2)] += 1
    print(f"block index gap between consecutive members in the same slot: median {statistics.median(gaps) if gaps else 'n/a'} | gap 1 (back-to-back) {sum(g == 1 for g in gaps)} of {len(gaps)} | dist {collections.Counter(gaps).most_common(8)}")
    print("buy order inside the slot (top):", orders.most_common(6))
    print("member -> fee payer:", payers.most_common(8)); print("buy sizes (curve SOL):", sizes.most_common(6))
    # sells together?
    ss = []
    for x in P:
        fs = [v[0]["s"] for v in x["sells"].values() if v]
        if len(fs) > 1: ss.append(max(fs) - min(fs))
    print(f"first sells of members: same slot {sum(s == 0 for s in ss)} of {len(ss)} | spread median {statistics.median(ss) * SL if ss else 0:.1f} s")
    print(f"entry: token age median {statistics.median([x['age'] for x in P]):.0f} s | curve SOL median {statistics.median([x['vsol'] for x in P]):.1f}")
    # who comes right before them?
    c = collections.Counter(); cd = collections.defaultdict(list); last = collections.Counter(); lastd = collections.defaultdict(list); devpre = 0
    for x in P:
        seen = set()
        for u, dt, sol, isdev, sameslot in x["pre"]:
            if u not in seen: c[u] += 1; cd[u].append(dt); seen.add(u)
            devpre += isdev
        if x["pre_last"]: last[x["pre_last"][0]] += 1; lastd[x["pre_last"][0]].append(x["pre_last"][1])
    print(f"\nwallets buying the same token in the 30 s BEFORE the group (share of the group's {len(P)} tokens):")
    for u, n in c.most_common(12): print(f"   {u}  {n:3d} ({n / len(P):4.0%}) | lead time median {statistics.median(cd[u]):5.1f} s")
    print("trade right before the group's first buy (who):")
    for u, n in last.most_common(8): print(f"   {u}  {n:3d} ({n / len(P):4.0%}) | gap median {statistics.median(lastd[u]):5.2f} s")
