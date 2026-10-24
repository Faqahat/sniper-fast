#!/usr/bin/env python3
# READ-ONLY, offline: one record per launch 9qz7cW attempted (collector windows R1 + R2): behaviour (snipe = first attempt
# in the create slot or the next; later = >= 2 slots after), quote, landing (slot offset, outside buy txs ahead, entry
# price vs the price right after the dev's bundle, arrival ms in our engine's feed), size, landing spend (priority + tips
# + other transfers), the exit ladder (each sell: slots after the buy, share of the bought tokens, price multiple), the
# price action before a later buy, and the realized SOL result from exact lamport deltas of ALL its txs on the mint
# (failed ones included). -> perlaunch_q9z.json
import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
TM = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_q9z.json"))
Q = json.load(open(os.path.join(HERE, "quote_by_mint.json")))
L = rp.load_launches(); O = rp.load_obs()
RAW = collections.defaultdict(list)
for l in gzip.open(os.path.join(HERE, "raw_q9z.jsonl.gz"), "rt"):
    r = json.loads(l)
    for m in r[9][:1]: RAW[m].append(r)
byb = collections.defaultdict(lambda: collections.defaultdict(set))
for m in A:
    if m in L: byb[L[m]["run"]][rp.bucket(m)].add(m)
PUMPFEE_ACC = None
def spend(r, sol_in):
    """priority fee + tips (known services) + other positive transfers (unknown recipients) of one successful buy tx"""
    prio = (r[6] or 5000) - 5000; tips = []; other = []
    for acc, lam in (r[16] or []):
        if lam <= 0 or acc == W: continue
        if acc in TM: tips.append((TM[acc], lam / 1e9))
    return prio / 1e9, tips
def work(job):
    run, b, mints = job
    tra = rp.read_bucket(run, b, mints); fa = rp.read_failed(run, b, mints); out = {}
    for m in mints:
        c = L[m]; tr = tra.get(m, []); S = c["slot"]; a = A[m]["9qz7cW"]
        rec = dict(m=m, run=run, S=S, bt=c.get("bt"), name=c.get("name"), symbol=c.get("symbol"), creator=c.get("creator"), signer=c.get("user"),
                   quote="SOL" if Q.get(m) == "SOL" else (Q.get(m) or "unknown"), may=int("InitializeMayhemState" in (c.get("ixn") or [])),
                   filled=a[0], off=a[1], beh="snipe" if a[1] <= 1 else "later", create_sig=c.get("sig"))
        my = sorted(RAW.get(m, []), key=lambda r: (r[1], r[2]))
        rec["sol_result"] = round(sum(r[13] for r in my) / 1e9, 6)               # exact SOL deltas of all its txs on the mint
        rec["n_tx"] = len(my); rec["n_fail"] = sum(1 for r in my if r[5]); rec["fail_fee"] = round(sum((r[6] or 0) for r in my if r[5]) / 1e9, 6)
        rec["n_fail_buyfee"] = sum(1 for r in my if r[5] and (r[6] or 0) > 5000)
        if rec["quote"] == "unknown" and tr and 25e9 <= tr[0]["vsol"] <= 200e9: rec["quote"] = "SOL"; rec["quote_src"] = "curve"   # create tx not in raw: SOL-range curve
        sol_ok = bool(tr) and rec["quote"] == "SOL" and min(t["vsol"] for t in tr) >= 25e9 and max(t["vsol"] for t in tr[:50]) <= 200e9
        rec["sol_ok"] = sol_ok
        if tr:
            st = rp.structure(tr, c)
            rec["dev_sol"] = sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9
            rec["bundle_sol"] = sum(t["sol"] for t in st["glued"]) / 1e9; rec["bundle_txs"] = len({t["sig"] for t in st["glued"]})
            ge = tr[st["g_end"] - 1] if st["g_end"] >= 1 else None
            p_b = (ge["vsol"] / ge["vtok"]) if ge and ge["vtok"] else None
            mine = [k for k, t in enumerate(tr) if t["user"] == W]
            buys = [k for k in mine if tr[k]["buy"]]
            if buys:
                k = buys[0]; t = tr[k]
                pre = (tr[k - 1]["vsol"] / tr[k - 1]["vtok"]) if k > 0 and tr[k - 1]["vtok"] else None
                rec.update(buy_sig=t["sig"], buy_slot=t["s"], buy_idx=t["i"], buy_sol=t["sol"] / 1e9, buy_tok=t["tok"], d_slot=t["s"] - S,
                           ahead=len({x["sig"] for x in tr[st["g_end"]:k] if x["buy"] and x["user"] not in st["insiders"]}),
                           ahead_all=len({x["sig"] for x in tr[st["g_end"]:k] if x["user"] not in st["insiders"]}),
                           entry_x=round(pre / p_b, 4) if (pre and p_b and sol_ok) else None,
                           mc_sol=round(t["vsol"] / 1e9, 2) if sol_ok else None, n_buys=len(buys), fee=t["fee"], tips=t["tips"])
                rr = next((r for r in my if r[4] == t["sig"]), None)
                if rr:
                    pr, tp = spend(rr, t["sol"]); rec.update(prio=pr, tipsv=tp, router="2eFuLSK4McKonBcB6XLax8gSgxwR56zNfrjHsvkNkftj" in rr[10])
                    rec["other_out"] = round(-(rr[13]) / 1e9 - t["sol"] / 1e9 - (t.get("fbps", 95) + t.get("cbps", 30)) / 1e4 * t["sol"] / 1e9 - pr - 0.000005 - sum(x[1] for x in tp) - 0.0021576, 6) if rec["quote"] == "SOL" else None
                # price action before a later buy (SOL curve): price now vs P_bundle, vs 10 s / 60 s before, net SOL flow
                if sol_ok and p_b:
                    def px_at(slot):
                        j = max((i for i, x in enumerate(tr) if x["s"] <= slot), default=None)
                        return (tr[j]["vsol"] / tr[j]["vtok"]) if j is not None else p_b
                    s0 = t["s"]
                    rec["px_vs_bundle"] = round(pre / p_b, 3) if pre else None
                    rec["px_chg_10s"] = round(pre / px_at(s0 - 47), 3) if pre else None
                    rec["px_chg_60s"] = round(pre / px_at(s0 - 283), 3) if pre else None
                    rec["peak_before_x"] = round(max(x["vsol"] / x["vtok"] for x in tr[:k]) / p_b, 3) if k else None
                    rec["flow_10s"] = round(sum((x["sol"] if x["buy"] else -x["sol"]) for x in tr[:k] if x["s"] >= s0 - 47) / 1e9, 3)
                    rec["buys_10s"] = sum(1 for x in tr[:k] if x["s"] >= s0 - 47 and x["buy"])
                    prev = tr[k - 1] if k > 0 else None
                    rec["prev_trade"] = dict(user=prev["user"][:8], buy=prev["buy"], sol=round(prev["sol"] / 1e9, 3), ds=t["s"] - prev["s"]) if prev else None
                # exit ladder: each of its sells (SOL curve events) after the first buy
                q0 = t["tok"]; sells = []
                for kk in mine:
                    x = tr[kk]
                    if x["buy"] or kk < k: continue
                    px = x["vsol"] / x["vtok"] if x["vtok"] else None
                    p_in = t["sol"] / t["tok"] if t["tok"] else None
                    sells.append(dict(ds=x["s"] - t["s"], frac=round(x["tok"] / q0, 4) if q0 else None, x=round(px / p_in, 3) if (px and p_in and sol_ok) else None,
                                      sol=round(x["sol"] / 1e9, 4), sig=x["sig"]))
                rec["sells"] = sells; rec["rebuys"] = len(buys) - 1
            # arrival ms in our feed (R2 launches with a timeline): the wallet's first tx seen
            o = O.get(m)
            if o:
                mine_o = sorted(x for x in o["outs"] if x[3] == "9qz7cW")
                rec["arr_ms"] = mine_o[0][0] if mine_o else None; rec["has_obs"] = True
                # where our engine would have landed (45 / 75 ms) vs its buy
            # failed attempt detail (first failed tx of the wallet on the mint)
            fl = [r for r in my if r[5]]
            if fl and not buys: rec["first_fail_ds"] = fl[0][1] - S; rec["first_fail_fee"] = fl[0][6]
        out[m] = rec
    return out
if __name__ == "__main__":
    jobs = [(run, b, ms) for run, d in byb.items() for b, ms in d.items()]
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, jobs): res.update(o)
    json.dump(res, open(os.path.join(HERE, "perlaunch_q9z.json"), "w"))
    print("launch records", len(res), collections.Counter((r["beh"], r["filled"], r["quote"] == "SOL") for r in res.values()))
