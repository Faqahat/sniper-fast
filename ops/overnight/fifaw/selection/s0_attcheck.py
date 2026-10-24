#!/usr/bin/env python3
# read-only: recompute FiFawH attempt status per mint from the collector rows (fifaw_rows.json) and cross-check the
# collector-derived attempt list against the wallet's own on-chain ledger (ledger_FiFawH.json, fetched earlier)
import sys, json, collections, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
L = rp.load_launches()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
R = json.load(open("/home/moiz/sniper/ops/overnight/fifaw/fifaw_rows.json"))
out = {}
for m, rows in R.items():
    c = L[m]; S = c["slot"]
    buys = [r for r in rows if r[1] == "T" and r[15] == W and r[16] == 1 and r[13] == 0]
    sells = [r for r in rows if r[1] == "T" and r[15] == W and r[16] == 0 and r[13] == 0]
    fails = [r for r in rows if r[1] == "X" and r[7] == W and r[13] == 1]
    offs = [r[3] - S for r in buys + fails]
    out[m] = dict(filled=int(bool(buys)), n_buy=len(buys), n_fail=len(fails), n_sell=len(sells), off0=min(offs) if offs else None,
                  buy_off=min((r[3] - S for r in buys), default=None), buy_sol=sum(r[17] for r in buys) / 1e9,
                  fail_off=min((r[3] - S for r in fails), default=None))
print("mints", len(out), "filled", sum(v["filled"] for v in out.values()))
dis = [(m, A[m]["FiFawH"], out[m]["filled"], out[m]["off0"]) for m in A if m in out and (A[m]["FiFawH"][0] != out[m]["filled"])]
print("filled flag differs from attempts_fifaw.json:", len(dis), dis[:5])
print("both fail+fill:", sum(1 for v in out.values() if v["filled"] and v["n_fail"]))
print("first-offset dist", collections.Counter(min(v["off0"], 99) for v in out.values()))
# ledger cross-check
led = json.load(open("/home/moiz/sniper/ops/overnight/fifaw/ledger_FiFawH.json"))
bts = [L[m]["bt"] for m in A]; lo, hi = min(bts), max(bts)
lb = collections.defaultdict(list)
for x in led:
    if x.get("err"): continue
    for e in x.get("ev") or []:
        if e.get("buy") and e.get("user") == W: lb[e["mint"]].append(x)
inL = {m for m in lb if m in L}
inwin = {m for m in inL if lo - 60 <= L[m]["bt"] <= hi + 60}
print("ledger mints bought:", len(lb), "of which collected launches:", len(inL), "in window:", len(inwin))
print("  ledger-bought collected mints in window NOT in attempts:", len(inwin - set(A)), "| attempts filled not in ledger:", len({m for m in A if out.get(m, {}).get("filled")} - set(lb)))
nc = [m for m in lb if m not in L]
# ledger buys of mints NOT collected: within the window? (launches outside the collector, or older mints)
bt_nc = [min(x["bt"] for x in lb[m]) for m in nc]
print("  ledger-bought mints not collected:", len(nc), "with first buy inside window:", sum(1 for t in bt_nc if lo <= t <= hi))
# failed txs in ledger in window vs collector fails
lf = [x for x in led if x.get("err") and lo <= x["bt"] <= hi]
print("ledger failed txs in window:", len(lf), "collector failed rows on attempted mints:", sum(v["n_fail"] for v in out.values()))
ls = [x for x in led if not x.get("err") and lo <= x["bt"] <= hi]
print("ledger ok txs in window:", len(ls), "venues", collections.Counter(tuple(sorted(set(x.get("venues") or []))) for x in ls).most_common(8))
json.dump(out, open("/home/moiz/sniper/ops/overnight/fifaw/selection/att_status.json", "w"))
