#!/usr/bin/env python3
# READ-ONLY, offline ground truth from rows.json (every tx in the CK window that dKMjeG SIGNED, failed ones too; txs of
# other wallets that merely reference its address are listed separately). Value = SOL + WSOL + quote tokens (USDC,
# PUMP, xStocks, ...) valued at the SOL rate of its own nearest quote->SOL swap. Per-token PnL after ALL costs (curve,
# pump fees, priority, tips, failed attempts, router skips, account rent net of refunds), daily, by venue. -> ledger.json
import json, os, collections, datetime, bisect, statistics as S
HERE = os.path.dirname(os.path.abspath(__file__))
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"; WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"; PUMPT = "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn"
ALL = json.load(open(os.path.join(HERE, "rows.json")))
R = [r for r in ALL if r["payer"] == W]; THIRD = [r for r in ALL if r["payer"] != W]
SWAPP = {"whirlpool", "raydium_clmm", "meteora_dlmm", "jupiter", "pumpswap", "raydium_cpmm", "raydium_amm"}
def tx_mint(r):
    t = json.load(open(os.path.join(HERE, "txc", r["sig"] + ".json"))); m = t["transaction"]["message"]
    for ix in m["instructions"]:
        if ix.get("programId") in ("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8"):
            acc = ix.get("accounts") or []
            for a in acc:
                if a.endswith("pump"): return a
            if len(acc) > 1: return acc[1]
    for inn in t["meta"].get("innerInstructions") or []:
        for ix in inn["instructions"]:
            if ix.get("programId") == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
                acc = ix.get("accounts") or []
                for a in acc:
                    if a.endswith("pump"): return a
                if len(acc) > 1: return acc[1]
    for b in (t["meta"].get("preTokenBalances") or []) + (t["meta"].get("postTokenBalances") or []):
        if b.get("owner") == W and b["mint"] not in (WSOL,) and b["mint"] not in QSET: return b["mint"]
    return None
def cat(r):
    ix = ",".join(r["ixn"]); tops = set(r["tops"])
    if r["err"]:
        if "Buy" in ix or "ENFJAV" in tops or "InitializeAccount3" in ix or "Swap" in ix: return "failed buy"
        if "Sell" in ix: return "failed sell"
        if "CloseAccount" in ix: return "failed close"
        return "failed other"
    if r.get("ttx"): return "withdrawal (token transfer)"
    if any(t["buy"] for t in r["trades"]): return "buy"
    if r["trades"]: return "sell"
    if "ENFJAV" in tops: return "router skip (no buy)"
    if tops & SWAPP: return "quote swap"
    if r["closes"]: return "close token acct"
    if tops <= {"cb"}: return "compute-budget only (ping)"
    if r["xi"] or r["xo"]: return "transfer"
    return "other"
for r in R: r["cat"] = cat(r)
# quote mints = non-SOL tokens it swaps against SOL in standalone swap txs
QSET = set()
for r in R:
    if r["cat"] == "quote swap":
        for m, d in r["tok"].items():
            if m != WSOL and abs(d) > 0: QSET.add(m)
QSET.add(USDC); QSET.add(PUMPT)
# SOL rate per quote mint from its own swaps (time series)
rates = collections.defaultdict(list)
for r in R:
    if r["cat"] != "quote swap": continue
    sol = r["sol_chg"] / 1e9 + r["tok"].get(WSOL, 0)
    qs = [(m, d) for m, d in r["tok"].items() if m in QSET and abs(d) > 0]
    if len(qs) == 1 and abs(sol) > 1e-4: rates[qs[0][0]].append((r["bt"], abs(sol) / abs(qs[0][1])))
for q in rates: rates[q].sort()
def rate(q, bt):
    v = rates.get(q)
    if not v: return None
    i = bisect.bisect_left(v, (bt, 0)); c = [v[j] for j in (i - 1, i) if 0 <= j < len(v)]
    return min(c, key=lambda x: abs(x[0] - bt))[1]
unval = collections.Counter()
for r in R:
    v = r["sol_chg"] / 1e9 + r["tok"].get(WSOL, 0)
    for q, d in r["tok"].items():
        if q in QSET and abs(d) > 0:
            k = rate(q, r["bt"])
            if k is None: unval[q] += 1
            else: v += d * k
    r["val"] = v
    r["tipsum"] = sum(l for _, l, _ in r["tips"]) / 1e9; r["prio"] = max(0, (r["fee"] - 5000 * r["nsig"])) / 1e9
    r["mint"] = None
    if r["cat"] in ("buy", "sell", "failed buy", "failed sell", "router skip (no buy)", "close token acct", "failed close", "failed other"):
        r["mint"] = r["trades"][0]["mint"] if r["trades"] else tx_mint(r)
if unval: print("quote deltas without a rate (unvalued):", dict(unval))
cnt = collections.Counter(r["cat"] for r in R)
print(f"txs signed by dK: {len(R)} | third-party txs that only reference its address: {len(THIRD)} ({sum(1 for r in THIRD if r['err'])} failed), signers {collections.Counter(r['payer'][:8] for r in THIRD).most_common(3)}")
print("categories:", dict(cnt))
tok = collections.defaultdict(lambda: dict(pnl=0.0, buys=0, sells=0, spent=0.0, fails=0, fail_cost=0.0, skips=0, skip_cost=0.0, tips=0.0, prio=0.0, base=0.0,
                                         pumpfee=0.0, t0=None, t1=None, s0=None, quote=None, qmint=None, size=None, d=None, sells_list=[], close=0.0, rent=0.0))
for r in R:
    m = r["mint"]
    if not m: continue
    x = tok[m]; x["pnl"] += r["val"]; x["tips"] += r["tipsum"]; x["prio"] += r["prio"]; x["base"] += 5000 * r["nsig"] / 1e9
    if r["cat"] == "buy":
        b = [t for t in r["trades"] if t["buy"]][0]
        x["buys"] += 1; x["spent"] += -r["val"]; x["t0"] = x["t0"] or r["bt"]; x["s0"] = x["s0"] or r["slot"]
        x["size"] = (x["size"] or 0) + b["sol"] / 1e9; x["pumpfee"] += (b.get("fee", 0) + b.get("cfee", 0)) / 1e9
        qm = [q for q, d in r["tok"].items() if q in QSET and abs(d) > 0]
        sw = bool(set(r["tops"]) & SWAPP)
        x["quote"] = "SOL" if (not sw and 25e9 <= b["vsol"] <= 200e9) else "non-SOL"
        x["qmint"] = (qm[0] if qm else None) if x["quote"] == "non-SOL" else WSOL
        x["d"] = datetime.datetime.fromtimestamp(r["bt"], datetime.timezone.utc).strftime("%m-%d")
        x["buy_tok"] = b["tok"]; x["buy_px"] = b["sol"] / b["tok"] if b["tok"] else None; x["buy_sig"] = r["sig"]; x["buy_vsol"] = b["vsol"]; x["buy_vtok"] = b["vtok"]
        x["buy_tips"] = r["tips"]; x["buy_fee"] = r["fee"]; x["buy_v"] = r["v"]; x["buy_jdf"] = r["jdf"]; x["buy_tops"] = r["tops"]
    elif r["cat"] == "sell":
        x["sells"] += 1; x["t1"] = r["bt"]; x["s1"] = r["slot"]
        for t in r["trades"]:
            if not t["buy"]:
                x["pumpfee"] += (t.get("fee", 0) + t.get("cfee", 0)) / 1e9
                x["sells_list"].append(dict(slot=r["slot"], bt=r["bt"], tok=t["tok"], sol=t["sol"] / 1e9, px=t["sol"] / t["tok"] if t["tok"] else None, sig=r["sig"], val=r["val"],
                                            tips=[(a, l) for a, l, _ in r["tips"]], fee=r["fee"], v=r["v"]))
    elif r["cat"].startswith("failed"):
        x["fails"] += 1; x["fail_cost"] += -r["val"]
    elif r["cat"] == "router skip (no buy)":
        x["skips"] += 1; x["skip_cost"] += -r["val"]
    elif r["cat"] == "close token acct":
        x["close"] += r["val"]
T = dict(tok)
bought = {m: x for m, x in T.items() if x["buys"]}; never = {m: x for m, x in T.items() if not x["buys"]}
qsw = [r for r in R if r["cat"] == "quote swap"]
tr = [r for r in R if r["cat"] in ("transfer", "withdrawal (token transfer)")]
other = [r for r in R if r["cat"] in ("compute-budget only (ping)", "other")]
tot_tok = sum(x["pnl"] for x in bought.values()); tot_never = sum(x["pnl"] for x in never.values())
print(f"\nPnL (window, all costs): tokens bought {len(bought)} -> {tot_tok:+.2f} SOL | launches attempted but never filled {len(never)} -> {tot_never:+.2f} | "
      f"quote swaps residual (swap cost vs nearest-rate valuation) {sum(r['val'] for r in qsw):+.2f} | pings/other {sum(r['val'] for r in other):+.4f}")
total = tot_tok + tot_never + sum(r["val"] for r in qsw) + sum(r["val"] for r in other)
print(f"TOTAL trading result {total:+.2f} SOL over {len(R)} txs")
# check: raw SOL+WSOL flow over non-transfer txs + quote-token balance change valued at the end
raw = sum(r["sol_chg"] / 1e9 + r["tok"].get(WSOL, 0) for r in R if r["cat"] not in ("transfer", "withdrawal (token transfer)"))
qnet = collections.Counter()
for r in R:
    if r["cat"] in ("transfer", "withdrawal (token transfer)"): continue
    for q, d in r["tok"].items():
        if q in QSET: qnet[q] += d
qval = sum(d * (rates[q][-1][1] if rates.get(q) else 0) for q, d in qnet.items())
print(f"check: raw SOL+WSOL flow (non-transfer txs) {raw:+.2f} + net quote tokens left {qval:+.2f} (at last rate) = {raw + qval:+.2f}")
print("external transfers:", len(tr), "total", round(sum(r["val"] for r in tr), 3), [(datetime.datetime.fromtimestamp(r["bt"], datetime.timezone.utc).strftime("%m-%d %H:%M"), round(r["val"], 3), [(s[:8], round(l / 1e9, 4)) for s, l in r["xi"]], [(d[:8], round(l / 1e9, 4)) for d, l in r["xo"]], [(o[:8] if o else None, round(a, 2)) for o, m, a in r.get("ttx") or []]) for r in tr if abs(r["val"]) > 0.001])
json.dump(dict(rows=[{k: r.get(k) for k in ("sig", "slot", "bt", "cat", "mint", "val", "fee", "prio", "tipsum", "tips", "err", "efail", "v", "nonce", "jdf", "ixn", "tops", "xi", "xo", "ttx", "cu", "nsig", "bh", "router_data", "sol_chg", "tok")} for r in R],
               third=[{k: r.get(k) for k in ("sig", "slot", "bt", "payer", "err", "tops")} for r in THIRD],
               tokens=T, qset=sorted(QSET), rates={q: v[-1][1] for q, v in rates.items()}), open(os.path.join(HERE, "ledger.json"), "w"))
