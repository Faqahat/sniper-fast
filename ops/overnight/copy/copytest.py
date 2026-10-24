#!/usr/bin/env python3
# READ-ONLY copy test: wallets chosen ONLY on R1 (census), their buys copied on R2 (out of sample), at a realistic lag.
# Selection sets (R1 only): n_R1 >= 20 launches, R1 pnl > 0, both halves of R1 > 0, median first-buy delay > 2 slots (not racers),
#   not a known sniper/pro, not an insider (glued-bundle / creator) on most launches.
# Copy: trigger = the wallet's FIRST buy on a launch (R2). Entry = E1 (start of the next slot after its buy) or E2 (one slot later).
# Exits: follow = sell right after the wallet's first sell (start of the slot after it; capped at 3000 slots), or fixed holds.
# Costs: pump fees both ways + TXC SOL per tx + 0.5% fill penalty. Size 0.5 SOL. One position per launch (first trigger).
import sys, os, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"
import rp
from multiprocessing import Pool
B = 0.5; TXC = float(os.environ.get("TXC", "0.003")); PEN = 0.005; HS = (5, 10, 25, 50, 150, 600)
CORE = "/home/moiz/sniper/ops/overnight/core"
W = json.load(open(f"{CORE}/gf_wallets.json"))
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO6 = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
A = collections.defaultdict(list)
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/R1_*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        r = json.loads(l); A[r[0]].append(r)
SEL = {}
for u, v in A.items():
    if len(v) < 20 or u in SNIPER or u.startswith(PRO6): continue
    v.sort(key=lambda r: r[3]); pn = [r[11] for r in v]; h = len(v) // 2
    if sum(pn) <= 0 or sum(pn[:h]) <= 0 or sum(pn[h:]) <= 0: continue
    fb = statistics.median(r[4] for r in v)
    if fb <= 2: continue
    SEL[u] = dict(n=len(v), pnl=sum(pn), fb=fb, hold=statistics.median([(r[14] - r[4]) for r in v if r[14] is not None] or [0]),
                  w5=sum(pn) - sum(sorted(pn)[-5:]))
print("selected on R1:", len(SEL), "wallets; with R1 pnl w/o top5 > 0:", sum(1 for s in SEL.values() if s["w5"] > 0))
L = rp.load_launches()
R2m = [m for m, c in L.items() if c["run"] == "R2"]
byb = collections.defaultdict(set)
for m in R2m: byb[rp.bucket(m)].add(m)
def sell_at(tr, k_from, V, T, q, s_exit, frs):
    for t in tr[k_from:]:
        if t["s"] >= s_exit: break
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
    so = V * q // (T + q)
    return so * (1 - frs) / 1e9 - TXC - (B + TXC)
def work(b):
    out = []
    tra = rp.read_bucket("R2", b, byb[b])
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem"): continue
        S = c["slot"]; st = rp.structure(tr, c)
        firsts = {}
        for k, t in enumerate(tr):
            if t["buy"] and t["user"] in SEL and t["user"] not in firsts and t["user"] not in st["insiders"]: firsts[t["user"]] = k
        if not firsts: continue
        trig = sorted(firsts.items(), key=lambda kv: kv[1])
        KC = int(os.environ.get("KCONS", "1")); WIN = int(os.environ.get("KWIN", "30"))
        # causal consensus: the trigger is the KC-th distinct selected wallet's first buy, within WIN slots of the first one
        if len(trig) < KC or tr[trig[KC - 1][1]]["s"] - tr[trig[0][1]]["s"] > WIN: continue
        u, k = trig[KC - 1]; t = tr[k]
        nsel_10 = sum(1 for w, kk in trig if tr[kk]["s"] - t["s"] <= 10)
        row = dict(m=m, bt=c["bt"], u=u[:8], age=round((t["s"] - S) * rp.SLOT_MS / 1000, 2), size=round(t["sol"] / 1e9, 3), nsel=len(trig), nsel10=nsel_10,
                   vsol=round(t["vsol"] / 1e9, 2), pnl={})
        ks = next((j for j in range(k + 1, len(tr)) if tr[j]["user"] == u and not tr[j]["buy"]), None)
        for tag, lag in (("E1", 1), ("E2", 2)):
            ke = k + 1; s_lim = t["s"] + lag - 1
            while ke < len(tr) and tr[ke]["s"] <= s_lim: ke += 1
            if ke >= len(tr): continue
            V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
            if V >= 100e9: continue
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V2 = V + X; T2 = T - q; q = int(q * (1 - PEN))
            s_in = tr[ke - 1]["s"]
            d = {f"h{H}": round(sell_at(tr, ke, V2, T2, q, s_in + H, fr), 5) for H in HS}
            if ks is not None and ks >= ke: d["follow"] = round(sell_at(tr, ke, V2, T2, q, min(tr[ks]["s"] + lag, s_in + 3000), fr), 5)
            elif ks is not None: d["follow"] = round(sell_at(tr, ke, V2, T2, q, s_in + 1, fr), 5)      # it sold before we got in
            else: d["follow"] = round(sell_at(tr, ke, V2, T2, q, s_in + 3000, fr), 5)
            row["pnl"][tag] = d; row["px_" + tag] = round((V / T) / (t["vsol"] / t["vtok"]), 4)
        out.append(row)
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): res += o
    json.dump(dict(sel=SEL, rows=res), open(f"/home/moiz/sniper/ops/overnight/copy/copy_R2_txc{TXC}_k{os.environ.get('KCONS', '1')}.json", "w"))
    print("R2 launches with a trigger:", len(res))
    for tag in ("E1", "E2"):
        print(f"\n{tag} (lag {tag[1]} slot): mean PnL per copy (0.5 SOL) | win | total")
        for ex in ["follow"] + [f"h{H}" for H in HS]:
            v = [r["pnl"][tag][ex] for r in res if tag in r["pnl"] and ex in r["pnl"][tag]]
            print(f"   {ex:7s} n {len(v)} mean {statistics.mean(v):+.4f} win {sum(1 for x in v if x > 0) / len(v):.0%} total {sum(v):+.1f}")
    print("\nby consensus (selected wallets buying within 10 slots of the trigger), E1:")
    for k in (1, 2, 3, 5):
        v = [r for r in res if "E1" in r["pnl"] and r["nsel10"] >= k]
        if v: print(f"   >= {k}: n {len(v)} follow {statistics.mean(r['pnl']['E1']['follow'] for r in v):+.4f} h25 {statistics.mean(r['pnl']['E1']['h25'] for r in v):+.4f} h150 {statistics.mean(r['pnl']['E1']['h150'] for r in v):+.4f}")
