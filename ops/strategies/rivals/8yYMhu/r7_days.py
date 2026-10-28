#!/usr/bin/env python3
"""8yYMhu step 7 (read-only): whole-life cash ledger by PKT day from every signature (recorded rows + RPC rows), checked against the
RPC balances at the 24 h window boundaries (balance = sum of exact per-tx deltas from the wallet's first tx, whose preBalance is 0).
Lines: trading NET (curve buys/sells after pump fees, PumpSwap sells, tx fees, tips, failed txs, rent), nonce-account rent,
funding in, withdrawals out, dust. Out: DATA/r7.txt"""
import json, pickle, collections, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as X
D = X.D; W = X.W
S = json.load(open(f"{D}/sigs.json"))
R = {r["sig"]: r for r in pickle.load(open(f"{D}/tx.pkl", "rb"))}
RP = {r["sig"]: r for r in pickle.load(open(f"{D}/rpc_tx.pkl", "rb"))}
I = pickle.load(open(f"{D}/ixs.pkl", "rb"))
rec_end = max(r["bt"] for r in R.values())
sigs = [s for s in S if s["blockTime"] <= rec_end - 60]
rows = []; miss = []
for s in sigs:
    r = R.get(s["signature"]) or RP.get(s["signature"])
    (rows.append(r) if r else miss.append(s["signature"]))
rows.sort(key=lambda r: (r["s"], r["i"] if r["i"] is not None else 0))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
first = rows[0]; fi = I.get(first["sig"])
P(f"signatures {len(sigs)} up to {X.pkt(rec_end - 60)} PKT; decoded {len(rows)}; missing {len(miss)}; first tx {first['sig'][:16]} {X.pkt(first['bt'])} preBalance {fi['pre'] if fi else '?'}")
day = lambda t: time.strftime("%m-%d", time.gmtime(int(t) + 18000))
C = collections.defaultdict(collections.Counter); bal = 0; marks = {}
for r in rows:
    d = day(r["bt"]); sd = r["sd"]; bal += sd; marks[r["sig"]] = bal
    ix = I.get(r["sig"])
    order = "|".join(ix["ixorder"]) if ix else ""
    if r["own"] and r["ok"] and r["kind"] in ("buy", "sell"):
        C[d]["trading"] += sd
    elif r["own"] and not r["ok"]:
        C[d]["trading"] += sd; C[d]["n_fail"] += 1
    elif r["own"] and "initializeNonce" in order:
        C[d]["nonce_rent"] += sd; C[d]["n_nonce_tx"] += 1
    elif r["own"] and ix and any(t[0] == W and t[2] > 1e8 for t in ix["transfers"]):
        C[d]["withdrawal"] += sd; C[d]["n_wd"] += 1
    elif r["own"]:
        C[d]["own_other"] += sd; C[d]["n_own_other"] += 1
    elif sd > 1e8:
        C[d]["funding_in"] += sd; C[d]["n_fund"] += 1
    else:
        C[d]["dust/3rd"] += sd
    if r["own"] and r["ok"] and r["kind"] in ("buy", "sell"):
        for e in r["events"]:
            C[d]["curve_gross"] += (-e["sol"] if e["buy"] else e["sol"]); C[d]["pump_fees"] -= e["fee"] + e["cfee"]
        C[d]["n_" + r["kind"]] += 1
# boundary checks
for w in ("b0", "b1"):
    for sig, v in I.items():
        if v.get("why") == w and sig in marks and v["post"] is not None:
            P(f"check {w} {sig[:16]} {X.pkt(v['bt'])}: ledger balance {marks[sig]/1e9:.9f} vs RPC postBalance {v['post']/1e9:.9f} -> diff {marks[sig]-v['post']} lamports")
P("| PKT day | buys | sells | failed | curve gross | pump+creator fees | trading NET | nonce rent | funding in | withdrawals | other/dust | end balance |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|")
cum = 0
for d in sorted(C):
    c = C[d]; tot = sum(v for k, v in c.items() if not k.startswith("n_") and k not in ("curve_gross", "pump_fees")); cum += tot
    P(f"| {d} | {c['n_buy']} | {c['n_sell']} | {c['n_fail']} | {c['curve_gross']/1e9:+.3f} | {c['pump_fees']/1e9:+.3f} | {c['trading']/1e9:+.3f} | {c['nonce_rent']/1e9:+.4f} | "
      f"{c['funding_in']/1e9:+.3f} | {c['withdrawal']/1e9:+.3f} | {(c['own_other']+c['dust/3rd'])/1e9:+.4f} | {cum/1e9:.3f} |")
tt = collections.Counter()
for c in C.values(): tt.update(c)
P(f"whole life: trading NET {tt['trading']/1e9:+.3f}, funding in {tt['funding_in']/1e9:+.3f}, withdrawals {tt['withdrawal']/1e9:+.3f}, nonce rent {tt['nonce_rent']/1e9:+.4f}, other {(tt['own_other']+tt['dust/3rd'])/1e9:+.4f}; ledger end balance {bal/1e9:.9f}")
open(f"{D}/r7.txt", "w").write("\n".join(out) + "\n")
