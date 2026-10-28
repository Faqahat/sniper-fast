#!/usr/bin/env python3
"""8yYMhu step 6 (read-only): lamport reconciliation of the wallet's SOL balance over the 24 h window 10-27 20:00 -> 10-28 20:00 PKT.
start = preBalance of the first tx in the window, end = postBalance of the last tx (public RPC getTransaction); every signature from
getSignaturesForAddress; per-tx wallet delta from the recordings (sd, exact) or RPC (recorder-missed). Decomposition of every lamport.
Out: DATA/r6.txt, DATA/r6.pkl"""
import json, pickle, collections, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as X
D = X.D; W = X.W
S = json.load(open(f"{D}/sigs.json"))
R = {r["sig"]: r for r in pickle.load(open(f"{D}/tx.pkl", "rb"))}
RP = {r["sig"]: r for r in pickle.load(open(f"{D}/rpc_tx.pkl", "rb"))}
I = pickle.load(open(f"{D}/ixs.pkl", "rb"))
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
sol = lambda v: f"{v / 1e9:+.9f}"
OUT = {}
for name, a, b in (("D1", X.W0, X.W1),):
    sigs = [s["signature"] for s in S if s.get("blockTime") is not None and a <= s["blockTime"] < b]
    rows = []; miss = []
    for sg in sigs:
        r = R.get(sg) or RP.get(sg)
        if r is None: miss.append(sg); continue
        rows.append(r)
    rows.sort(key=lambda r: (r["s"], r["i"] if r["i"] is not None else 0))
    f, l = rows[0], rows[-1]
    gf, gl = I.get(f["sig"]), I.get(l["sig"])
    P(f"# {name}: {X.pkt(a)} -> {X.pkt(b)} PKT; signatures {len(sigs)} (failed {sum(1 for s in S if a <= (s.get('blockTime') or 0) < b and s.get('err'))}); with a decoded row {len(rows)} (recorder {sum(r['src']=='rec' for r in rows)}, RPC {sum(r['src']=='rpc' for r in rows)}); missing {len(miss)}")
    if miss: P("MISSING sigs (first 10):", miss[:10])
    if gf is None or gl is None: P("boundary tx not fetched", f["sig"], l["sig"]); continue
    start, end = gf["pre"], gl["post"]
    P(f"start = preBalance of first tx {f['sig'][:20]} slot {f['s']} idx {f['i']} {X.pkt(f['bt'])}: {start / 1e9:.9f} SOL")
    P(f"end   = postBalance of last tx  {l['sig'][:20]} slot {l['s']} idx {l['i']} {X.pkt(l['bt'])}: {end / 1e9:.9f} SOL")
    P(f"chain change = {sol(end - start)} SOL; sum of per-tx deltas = {sol(sum(r['sd'] for r in rows))}; diff {end - start - sum(r['sd'] for r in rows)} lamports")
    C = collections.Counter(); N = collections.Counter(); XX = collections.defaultdict(list)
    for r in rows:
        if r["own"] and r["ok"] and r["kind"] in ("buy", "sell"):
            k = r["kind"]; N[k] += 1
            if r["events"]:
                ev = r["events"]
                C["curve_" + k + "_sol"] += sum((-e["sol"] if e["buy"] else e["sol"]) for e in ev)
                C["pump_fee"] -= sum(e["fee"] for e in ev); C["creator_fee"] -= sum(e["cfee"] for e in ev)
            else:
                C["nonpump_sell"] += r["sd"] + r["txfee"] + r["tips"] - r["rent_x"]; N["nonpump_sell"] += 1
            C["txfee_landed"] -= r["txfee"]; C["tips"] -= r["tips"]; C["rent_created"] -= r["rent_c"]; C["rent_back"] += r["rent_x"]
            if r["events"]: C["other_in_trade_tx"] += r["other"]
        elif r["own"] and not r["ok"]:
            N["fail"] += 1; C["txfee_failed"] -= r["txfee"]; C["fail_other"] += r["other"]
        elif r["own"]:
            N["own_other"] += 1; C["own_other"] += r["sd"]; XX["own_other"].append(r)
        else:
            ix = r["ixn"]
            k = "holder_fee_dist" if "DistributeFeeToHolders" in ix else ("dust_in" if 0 < r["sd"] < 100000 else "third_other")
            N[k] += 1; C[k] += r["sd"]; XX[k].append(r)
    tot = sum(C.values())
    P("| line | n | SOL |"); P("|---|---|---|")
    for k in ("curve_buy_sol", "curve_sell_sol", "pump_fee", "creator_fee", "nonpump_sell", "txfee_landed", "tips", "txfee_failed", "rent_created", "rent_back",
              "other_in_trade_tx", "fail_other", "holder_fee_dist", "dust_in", "third_other", "own_other"):
        n = {"curve_buy_sol": N["buy"], "curve_sell_sol": N["sell"], "txfee_failed": N["fail"], "nonpump_sell": N["nonpump_sell"]}.get(k, N.get(k, ""))
        P(f"| {k} | {n} | {sol(C.get(k, 0))} |")
    P(f"| = predicted change | | {sol(tot)} |"); P(f"| chain change | | {sol(end - start)} |"); P(f"| RESIDUAL | | {end - start - tot} lamports |")
    gross_curve = C["curve_buy_sol"] + C["curve_sell_sol"]
    after_pump = gross_curve + C["pump_fee"] + C["creator_fee"] + C["nonpump_sell"]
    trading = after_pump + C["txfee_landed"] + C["tips"] + C["txfee_failed"] + C["rent_created"] + C["rent_back"] + C["other_in_trade_tx"] + C["fail_other"]
    P(f"curve gross (sell SOL - buy SOL, before pump/creator fees) = {sol(gross_curve)}")
    P(f"after pump+creator fees (+ non-pump sells) = {sol(after_pump)}")
    P(f"trading NET (all bot cash incl. tx fees, tips, failed txs, rent) = {sol(trading)}; non-trading flows = {sol(tot - trading)}")
    for k in ("third_other", "own_other", "dust_in"):
        for r in XX[k][:30]: P(f"  {k}: {r['sig'][:24]} {X.pkt(r['bt'])} delta {r['sd']} ixn={r['ixn'][:60]}")
    OUT[name] = dict(start=start, end=end, C=dict(C), N=dict(N), trading=trading, gross_curve=gross_curve, after_pump=after_pump, rows=[r["sig"] for r in rows], miss=miss)
pickle.dump(OUT, open(f"{D}/r6.pkl", "wb"))
open(f"{D}/r6.txt", "w").write("\n".join(L) + "\n")
