#!/usr/bin/env python3
"""recon step 6 (read-only): lamport reconciliation of E2x1's SOL balance per day (D0, D1).
start = preBalance of the first tx in the day, end = postBalance of the last tx (public RPC getTransaction), all signatures from
getSignaturesForAddress; per-tx wallet delta from the recordings (sd, exact) or RPC. Decomposition of every lamport.
Out: r6.txt, r6.pkl"""
import json, pickle, collections, sys, os, time
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
W0 = 1793113200; W1 = W0 + 86400; WA = W0 - 86400
S = json.load(open(f"{OUT}/sigs.json"))
R = {r["sig"]: r for r in pickle.load(open(f"{OUT}/tx.pkl", "rb"))}
RP = {r["sig"]: r for r in pickle.load(open(f"{OUT}/rpc_tx.pkl", "rb"))}
G = {}
for l in open(f"{OUT}/gettx.jsonl"):
    j = json.loads(l)
    if j.get("res"): G[j["sig"]] = j["res"]
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
sol = lambda v: f"{v / 1e9:+.9f}"
OUTD = {}
for name, a, b in (("D0", WA, W0), ("D1", W0, W1)):
    sigs = [s["signature"] for s in S if s.get("blockTime") is not None and a <= s["blockTime"] < b]
    rows = []; miss = []
    for sg in sigs:
        r = R.get(sg) or RP.get(sg)
        if r is None: miss.append(sg); continue
        rows.append(r)
    rows.sort(key=lambda r: (r["s"], r["i"]))
    f, l = rows[0], rows[-1]
    gf, gl = RP.get(f["sig"]), RP.get(l["sig"])
    P(f"\n# {name}: {pkt(a)} -> {pkt(b)} PKT; signatures {len(sigs)}; with a decoded row {len(rows)}; missing {len(miss)}")
    if gf is None or gl is None: P("boundary tx not fetched", f["sig"], l["sig"]); continue
    start, end = gf["pre"], gl["post"]
    P(f"start = preBalance of first tx {f['sig'][:20]} slot {f['s']} idx {f['i']} {pkt(f['bt'])}: {start / 1e9:.9f} SOL")
    P(f"end   = postBalance of last tx  {l['sig'][:20]} slot {l['s']} idx {l['i']} {pkt(l['bt'])}: {end / 1e9:.9f} SOL")
    P(f"chain change = {sol(end - start)} SOL; sum of per-tx deltas = {sol(sum(r['sd'] for r in rows))}; diff {end - start - sum(r['sd'] for r in rows)} lamports")
    C = collections.Counter(); N = collections.Counter(); X = collections.defaultdict(list)
    for r in rows:
        if r["own"] and r["ok"] and r["kind"] in ("buy", "sell"):
            k = r["kind"]; N[k] += 1
            C["trade_" + k] += r["trade"] if r["events"] else 0
            if not r["events"]:   # PumpSwap sell: cash = sd + fee + tips - rent back
                C["trade_swap_sell"] += r["sd"] + r["txfee"] + r["tips"] - r["rent_x"]; N["swap_sell"] += 1
            C["txfee_ok"] -= r["txfee"]; C["tips"] -= r["tips"]; C["rent_created"] -= r["rent_c"]; C["rent_back"] += r["rent_x"]
            if r["events"]: C["curve_extend/other"] += r["other"]
        elif r["own"] and not r["ok"]:
            N["fail"] += 1; C["txfee_failed"] -= r["txfee"]; C["fail_other"] += r["other"]
        elif r["own"]:
            N["own_other"] += 1; C["own_other"] += r["sd"]; X["own_other"].append(r)
        else:
            ix = r["ixn"]
            k = "holder_fee_dist" if "DistributeFeeToHolders" in ix else ("dust_in" if 0 < r["sd"] < 100000 else "third_other")
            N[k] += 1; C[k] += r["sd"]; X[k].append(r)
    tot = sum(C.values())
    P("| line | n | SOL |"); P("|---|---|---|")
    for k in ("trade_buy", "trade_sell", "trade_swap_sell", "txfee_ok", "tips", "txfee_failed", "rent_created", "rent_back", "curve_extend/other", "fail_other", "holder_fee_dist", "dust_in", "third_other", "own_other"):
        n = N.get(k.replace("trade_", "").replace("txfee_failed", "fail"), "")
        P(f"| {k} | {n} | {sol(C.get(k, 0))} |")
    P(f"| = predicted change | | {sol(tot)} |"); P(f"| chain change | | {sol(end - start)} |"); P(f"| RESIDUAL | | {end - start - tot} lamports |")
    trading = C["trade_buy"] + C["trade_sell"] + C["trade_swap_sell"] + C["txfee_ok"] + C["tips"] + C["txfee_failed"] + C["rent_created"] + C["rent_back"] + C["curve_extend/other"]
    P(f"trading total (all bot cash incl. fees/tips/rent/failed) = {sol(trading)}; non-trading inflow = {sol(tot - trading)}")
    for k in ("third_other", "own_other", "dust_in"):
        for r in X[k][:30]: P(f"  {k}: {r['sig'][:24]} {pkt(r['bt'])} delta {r['sd']} ixn={r['ixn'][:40]} from={[t[1] for t in r.get('transfers', []) if t[2] == H][:2]}")
    hf = X["holder_fee_dist"]
    P(f"holder-fee distributions: {len(hf)} txs, {sol(sum(r['sd'] for r in hf))}, mints {len({(r.get('mints') or [r.get('mint')])[0] for r in hf})}")
    OUTD[name] = dict(start=start, end=end, C=dict(C), N=dict(N), trading=trading, rows=[r["sig"] for r in rows])
pickle.dump(OUTD, open(f"{OUT}/r6.pkl", "wb"))
open(f"{OUT}/r6.txt", "w").write("\n".join(L) + "\n")
