#!/usr/bin/env python3
# READ-ONLY: final ground-truth numbers from ledger.json (+ 3 RPC reads: balance and token holdings now) -> final.json
import os, sys, json, collections, datetime, statistics as S
HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"; sys.path.insert(0, HERE)
import rpc
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"; WSOL = "So11111111111111111111111111111111111111112"
L = json.load(open(os.path.join(HERE, "ledger.json"))); R = sorted(L["rows"], key=lambda r: (r["slot"], r["sig"])); T = L["tokens"]
rows_raw = {r["sig"]: r for r in json.load(open(os.path.join(HERE, "rows.json")))}
day = lambda bt: datetime.datetime.fromtimestamp(bt, datetime.timezone(datetime.timedelta(hours=5))).strftime("%m-%d")   # PKT days
OUT = {}
t0, t1 = R[0]["bt"], R[-1]["bt"]; hours = (t1 - t0) / 3600
OUT["window"] = dict(first=datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).isoformat(), last=datetime.datetime.fromtimestamp(t1, datetime.timezone.utc).isoformat(), hours=round(hours, 1), txs=len(R), slots=[R[0]["slot"], R[-1]["slot"]])
EXT = ("transfer", "withdrawal (token transfer)")
CARRIED = {m for m, x in T.items() if not x["buys"] and x["sells"] > 0}      # sold in the window, bought before it (no cost basis here)
OUT["carried_in"] = dict(tokens=len(CARRIED), sells_value=round(sum(T[m]["pnl"] for m in CARRIED), 3))
trading = [r for r in R if r["cat"] not in EXT and r.get("mint") not in CARRIED]
pnl = sum(r["val"] for r in trading); ext = sum(r["val"] for r in R if r["cat"] in EXT)
OUT["pnl_total"] = round(pnl, 3); OUT["pnl_per_day"] = round(pnl / hours * 24, 2); OUT["external"] = round(ext, 3)
# start/end balance check (SOL only): first tx pre-balance of W
def wbal(sig, pre=True):
    t = json.load(open(os.path.join(HERE, "txc", sig + ".json"))); keys = [k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
    i = keys.index(W); return (t["meta"]["preBalances"] if pre else t["meta"]["postBalances"])[i] / 1e9
b_start = wbal(R[0]["sig"], True); b_end = wbal(R[-1]["sig"], False)
sol_flow = sum(rows_raw[r["sig"]]["sol_chg"] for r in R) / 1e9
OUT["sol_balance_check"] = dict(start=round(b_start, 4), end_after_last_tx=round(b_end, 4), sum_of_sol_changes=round(sol_flow, 4), start_plus_changes=round(b_start + sol_flow, 4))
bal = rpc.rpc("getBalance", [W]); OUT["balance_now"] = bal["value"] / 1e9 if isinstance(bal, dict) else None
hold = []
for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    r = rpc.rpc("getTokenAccountsByOwner", [W, {"programId": prog}, {"encoding": "jsonParsed"}])
    if isinstance(r, dict):
        hold += [(a["account"]["data"]["parsed"]["info"]["mint"], a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]) for a in r["value"]]
OUT["holdings_now"] = [(m, a) for m, a in hold if a]
OUT["n_token_accounts_now"] = len(hold)
# per day
dd = collections.defaultdict(lambda: collections.Counter())
for r in trading: dd[day(r["bt"])]["pnl"] += r["val"]; dd[day(r["bt"])][r["cat"]] += 1
for m, x in T.items():
    if x["buys"] and x.get("t0"): dk_ = day(x["t0"]); dd[dk_]["tokens"] += 1; dd[dk_]["tok_pnl"] += x["pnl"]; dd[dk_]["spent"] += x["size"] * 1.0125
OUT["daily"] = {d: dict(pnl=round(c["pnl"], 2), tokens=c["tokens"], token_pnl=round(c["tok_pnl"], 2), buys=c["buy"], failed_buys=c["failed buy"], spent=round(c["spent"], 1)) for d, c in sorted(dd.items())}
# venue
QN = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC", "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn": "PUMP"}
ven = collections.defaultdict(list)
QS = set(L["qset"]); qm_of = collections.defaultdict(collections.Counter)
for r in R:
    if r["cat"] == "sell" and r.get("mint"):
        for qm, dq in rows_raw[r["sig"]]["tok"].items():
            if qm in QS and dq > 0: qm_of[r["mint"]][qm] += 1
for m, x in T.items():
    if not x["buys"] or m in CARRIED: continue
    if x["quote"] == "SOL": k = "pump SOL-quoted"
    else:
        qm = qm_of[m].most_common(1)[0][0] if qm_of[m] else None
        k = "pump USDC-quoted" if qm == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" else ("pump PUMP-quoted" if qm == "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn" else "pump other-quote (xStocks etc.)")
    ven[k].append(x)
OUT["venue"] = {k: dict(tokens=len(v), pnl=round(sum(x["pnl"] for x in v), 2), spent=round(sum(x["spent"] for x in v), 1), win=round(sum(x["pnl"] > 0 for x in v) / len(v), 3), median=round(S.median(x["pnl"] for x in v), 4)) for k, v in ven.items()}
never = [x for m, x in T.items() if not x["buys"] and m not in CARRIED]
OUT["never_filled"] = dict(launches=len(never), cost=round(sum(x["pnl"] for x in never), 3))
qsw = [r for r in R if r["cat"] == "quote swap"]; OUT["quote_swap_residual"] = round(sum(r["val"] for r in qsw), 3)
# costs
bt_ = [x for x in T.values() if x["buys"]]
# pump fees: SOL-quoted tokens only (other quotes report the fee in quote units)
OUT["costs"] = dict(pump_fees=round(sum(x["pumpfee"] for x in T.values() if x.get("quote") == "SOL"), 2), tips=round(sum(r["tipsum"] for r in R if not r["err"]), 2), priority=round(sum(r["prio"] for r in R if not r["err"]), 2),
                    base_fees=round(sum(5000 * (r.get("nsig") or 1) for r in R) / 1e9, 3), failed_txs=round(sum(-r["val"] for r in R if r["cat"].startswith("failed")), 2),
                    soft_skips=round(sum(-r["val"] for r in R if r["cat"] == "router skip (no buy)"), 3), pings=sum(1 for r in R if r["cat"] == "compute-budget only (ping)"),
                    tips_by_service={k: round(v, 2) for k, v in collections.Counter({}).items()})
tbs = collections.Counter()
for r in R:
    if r["err"]: continue                      # a failed tx's tip transfer is reverted (only its fee is paid)
    for a, l, _ in r["tips"]: tbs[a] += l / 1e9
OUT["costs"]["tips_by_service"] = {k: round(v, 2) for k, v in tbs.most_common()}
OUT["spent_total"] = round(sum(x["spent"] for x in bt_), 1)
p = sorted([x["pnl"] for x in bt_], reverse=True)
OUT["tokens"] = dict(n=len(bt_), win=round(sum(v > 0 for v in p) / len(p), 3), median=round(S.median(p), 4), ex_top2=round(sum(p[2:]), 2), ex_top10=round(sum(p[10:]), 2), best=[round(v, 2) for v in p[:5]], worst=[round(v, 2) for v in p[-5:]])
wd = [r for r in R if r["cat"] in EXT]
OUT["withdrawals"] = dict(n=len(wd), sol=round(-sum(r["val"] for r in wd), 2), dests=collections.Counter([(o or "?") for r in wd for o, m, a in (r.get("ttx") or [])] + [d for r in wd for d, l in r["xo"] if l > 1e7]).most_common(5),
                          usdc=round(sum(a for r in wd for o, m, a in (r.get("ttx") or [])), 2), deposits_in=[(s, l / 1e9) for r in wd for s, l in r["xi"] if l > 1e7])
OUT["third_party"] = dict(n=len(L["third"]), failed=sum(1 for r in L["third"] if r["err"]), signers=collections.Counter(r["payer"] for r in L["third"]).most_common(4))
OUT["cats"] = dict(collections.Counter(r["cat"] for r in R))
raw = sum(rows_raw[r["sig"]]["sol_chg"] / 1e9 + rows_raw[r["sig"]]["tok"].get(WSOL, 0) for r in trading)
qnet = collections.Counter()
for r in trading:
    for qm, dq in rows_raw[r["sig"]]["tok"].items():
        if qm in set(L["qset"]): qnet[qm] += dq
qv = sum(dq * L["rates"].get(qm, 0) for qm, dq in qnet.items())
OUT["check_raw"] = f"= {raw:+.2f} {qv:+.2f} = {raw + qv:+.2f} SOL (vs {pnl:+.2f} from the per-tx valuation)"
json.dump(OUT, open(os.path.join(HERE, "final.json"), "w"), indent=1)
print(json.dumps(OUT, indent=1)[:6000])
