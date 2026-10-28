#!/usr/bin/env python3
"""recon step 6 (read-only): the exact cash reconciliation of haqq's wallet over the window + per-bot P&L two ways + evidence.
Inputs: recon/sigs.json, gettx*.jsonl, table.pkl (r4), lots.pkl (r5). Out: recon/r6.txt (+ printed)."""
import json, pickle, glob, collections, sys, os, random, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import txparse as TP
H = TP.H; RENT = TP.RENT
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
WSOL_ACC = "3aoEhd6mTk7q6beUTVYHFoF79tFrQdoXcqXP5wiHxSQy"
Z = pickle.load(open(f"{OUT}/table.pkl", "rb")); rows, miss = Z["rows"], Z["miss"]
LZ = pickle.load(open(f"{OUT}/lots.pkl", "rb")); LOTS, UNM = LZ["lots"], LZ["unm"]
R3 = {r["sig"]: r for r in pickle.load(open(f"{OUT}/tx.pkl", "rb"))}
G = collections.defaultdict(dict)
for fx in sorted(glob.glob(f"{OUT}/gettx*.jsonl")):
    for l in open(fx):
        j = json.loads(l)
        if j.get("res") is not None: G[j["why"]][j["sig"]] = j["res"]
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
sol = lambda v: f"{v / 1e9:+.9f}"
ss = lambda sig: f"https://solscan.io/tx/{sig}"
P(f"# haqq EXACT cash reconciliation, window {pkt(W0)} -> {pkt(W1)} PKT (unix {W0} -> {W1})")
P(f"chain signatures in window: {len(rows) + len(miss):,}; tabled {len(rows):,}; not fetched {len(miss)}")
# ---------- 1. chain balances at the ends
def bal(res):
    keys = [k["pubkey"] for k in res["transaction"]["message"]["accountKeys"]]
    i = keys.index(H); return res["meta"]["preBalances"][i], res["meta"]["postBalances"][i]
fs = list(G["first"].items())[0]; ls_ = list(G["last"].items())[0]
bf = list(G["before_first"].items())[0]; al = list(G["after_last"].items())[0]
start = bal(fs[1])[0]; end = bal(ls_[1])[1]
P("\n## 1. Chain balances (MEASURED, public RPC getTransaction pre/post balances)")
P(f"first tx in window  {fs[0][:20]}.. slot {fs[1]['slot']} idx {fs[1].get('transactionIndex')} {pkt(fs[1]['blockTime'])}: preBalance  {start / 1e9:.9f} SOL  {ss(fs[0])}")
P(f"last tx in window   {ls_[0][:20]}.. slot {ls_[1]['slot']} idx {ls_[1].get('transactionIndex')} {pkt(ls_[1]['blockTime'])}: postBalance {end / 1e9:.9f} SOL  {ss(ls_[0])}")
P(f"continuity: post of the tx before the window {bal(bf[1])[1] / 1e9:.9f} (= start: {bal(bf[1])[1] == start}); pre of the tx after the window {bal(al[1])[0] / 1e9:.9f} (= end: {bal(al[1])[0] == end})")
P(f"CHAIN BALANCE CHANGE (SOL lamports of the wallet) = {sol(end - start)} SOL")
tot = sum(r["sd"] for r in rows)
P(f"sum of the {len(rows):,} per-tx wallet deltas = {sol(tot)} SOL; difference to the chain change = {end - start - tot} lamports")
# ---------- 2. classes
P("\n## 2. Every signature by class (MEASURED)")
cc = collections.defaultdict(lambda: [0, 0])
for r in rows:
    k = (r["src"], r["cls"]); cc[k][0] += 1; cc[k][1] += r["sd"]
for k in sorted(cc, key=lambda k: -cc[k][0]): P(f"  {k[0]:4s} {k[1]:18s} n={cc[k][0]:6,}  wallet delta {sol(cc[k][1])}")
# ---------- 3. per bot
P("\n## 3. Per-bot cash flow in the window (MEASURED, exact lamports; rent of token accounts excluded here, shown below)")
B = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    if r["cls"] not in ("buy", "sell", "fail", "swap_sell"): continue
    b = B[r["code"]]
    if r["cls"] == "fail":
        b["n_fail"] += 1; b["fail_fee"] += r["txfee"]; continue
    b["n_" + ("buy" if r["cls"] == "buy" else "sell")] += 1
    if r["cls"] == "swap_sell":
        b["swap_in"] += r["wsol_d"]; b["n_swap"] += 1
    else:
        tr = r["trade"]
        if tr < 0: b["buy_out"] += -tr
        else: b["sell_in"] += tr
    b["txfee"] += r["txfee"]; b["tips"] += r["tips"]; b["rent_created"] += r["rent"]
for c in B:
    b = B[c]; b["cash"] = b["sell_in"] + b["swap_in"] - b["buy_out"] - b["txfee"] - b["tips"] - b["fail_fee"]
lots_w = [l for l in LOTS if l["inw"]]
LB = collections.defaultdict(list)
for l in lots_w: LB[l["code"]].append(l)
pre_closed = collections.Counter(l["code"] for l in LOTS if not l["inw"] and l["bt"] < W0 and l["close_bt"] is not None and W0 <= l["close_bt"] < W1)
order = sorted(B, key=lambda c: -B[c]["cash"])
P("| code | buys | sells | failed | SOL into buys | SOL from sells | of which PumpSwap->WSOL | tx fees | tips | failed fees | CASH (a) | lots opened | closed by W1 | pre-window lots closed in window | token accts created |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
S_ = collections.Counter()
for c in order:
    b = B[c]; lw = LB.get(c, [])
    P(f"| {c} | {b['n_buy']:,} | {b['n_sell']:,} | {b['n_fail']:,} | {b['buy_out'] / 1e9:.4f} | {(b['sell_in'] + b['swap_in']) / 1e9:.4f} | {b['swap_in'] / 1e9:.4f} | {b['txfee'] / 1e9:.4f} | {b['tips'] / 1e9:.4f} | {b['fail_fee'] / 1e9:.4f} | **{b['cash'] / 1e9:+.4f}** | {len(lw):,} | {sum(1 for l in lw if l['close_bt'] is not None and l['close_bt'] < W1):,} | {pre_closed.get(c, 0)} | {b['rent_created'] // RENT:,} |")
    for k in ("n_buy", "n_sell", "n_fail", "buy_out", "sell_in", "swap_in", "txfee", "tips", "fail_fee", "cash", "rent_created"): S_[k] += b[k]
P(f"| ALL | {S_['n_buy']:,} | {S_['n_sell']:,} | {S_['n_fail']:,} | {S_['buy_out'] / 1e9:.4f} | {(S_['sell_in'] + S_['swap_in']) / 1e9:.4f} | {S_['swap_in'] / 1e9:.4f} | {S_['txfee'] / 1e9:.4f} | {S_['tips'] / 1e9:.4f} | {S_['fail_fee'] / 1e9:.4f} | **{S_['cash'] / 1e9:+.4f}** | {len(lots_w):,} | | {sum(pre_closed.values())} | {S_['rent_created'] // RENT:,} |")
# ---------- 4. reconciliation
P("\n## 4. RECONCILIATION (MEASURED, lamport-exact)")
lines = []
bots = S_["cash"]
rent_c = -S_["rent_created"]
closes = [r for r in rows if r["cls"] == "close"]
n_closed = sum(r["n_closed"] for r in closes)
rent_back = n_closed * RENT
close_cost = -sum(r["txfee"] + r["tips"] for r in closes)
swapw = -S_["swap_in"]
unw = [r for r in rows if r["cls"] == "unwrap"]; unwrap = sum(r["sd"] for r in unw)
pay = [r for r in rows if r["cls"] == "payout"]; payout = sum(r["sd"] for r in pay)
inb = [r for r in rows if r["cls"] in ("inbound", "third_party_neg")]; inbound = sum(r["sd"] for r in inb)
zero = [r for r in rows if r["cls"] == "third_party_zero"]
other = [r for r in rows if r["cls"] not in ("buy", "sell", "fail", "swap_sell", "close", "unwrap", "payout", "inbound", "third_party_neg", "third_party_zero")]
oth = sum(r["sd"] for r in other)
items = [("bots' cash flow (sum of section 3)", bots),
         ("  minus PumpSwap proceeds that landed in his WSOL account, not in SOL", swapw),
         (f"rent: {S_['rent_created'] // RENT:,} token accounts created by bot buys x {RENT:,}", rent_c),
         (f"rent back: {n_closed:,} token accounts closed in {len(closes)} close txs", rent_back),
         (f"infrastructure: fees + tips of the {len(closes)} close txs", close_cost),
         (f"WSOL unwraps ({len(unw)} txs, WSOL account -> wallet)", unwrap),
         (f"PAYOUTS out ({len(pay)} Jupiter txs: SOL to partners + SOL->USDC to partners)", payout),
         (f"inbound transfers from others ({len(inb)} txs)", inbound),
         (f"third-party txs that list his address, zero delta ({len(zero)} txs)", 0),
         (f"other ({len(other)} txs)", oth)]
acc = 0
for name, v in items:
    acc += v; P(f"  {name:80s} {sol(v)}")
P(f"  {'= predicted change of the wallet SOL balance':80s} {sol(acc)}")
P(f"  {'chain change (end - start)':80s} {sol(end - start)}")
P(f"  {'RESIDUAL':80s} {end - start - acc} lamports")
# WSOL account
wd = sum(r["wsol_d"] for r in rows)
P(f"\nWSOL account {WSOL_ACC}: sum of its deltas in the window {sol(wd)} (PumpSwap proceeds {sol(S_['swap_in'])}, unwraps {sol(sum(r['wsol_d'] for r in unw))}, payouts {sol(sum(r['wsol_d'] for r in pay))})")
P(f"TOTAL HOLDINGS change (SOL + WSOL) = {sol(end - start + wd)}")
pickle.dump(dict(start=start, end=end, B=dict(B), items=items, pay=pay, unw=unw, inb=inb, other=other, closes=closes), open(f"{OUT}/r6.pkl", "wb"))
open(f"{OUT}/r6.txt", "w").write("\n".join(L) + "\n")
# ---------- 5. spot-check: computed delta (TradeEvent + fee + tips + rent) and recorded sd vs RPC pre/post balances
P("\n## 5. Spot-check of the computed per-tx delta against getTransaction pre/post balances (MEASURED)")
spot = {sig: res for why, d in G.items() if why.startswith("spot_") for sig, res in d.items()}
errs = []; errs_sd = []; byk = collections.Counter(); bad = []
for sig, res in spot.items():
    r = R3.get(sig)
    if r is None or r["calc"] is None and r["kind"] != "close": continue
    keys = [k["pubkey"] for k in res["transaction"]["message"]["accountKeys"]]
    i = keys.index(H); d = res["meta"]["postBalances"][i] - res["meta"]["preBalances"][i]
    calc = r["calc"] if r["kind"] != "close" else r["closed"] * RENT - r["txfee"] - r["tips"]
    errs.append(calc - d); errs_sd.append(r["sd"] - d); byk[r["kind"]] += 1
    if calc != d: bad.append((sig, r["kind"], calc, d))
e = np.array(errs, float)
P(f"spot-checked txs: {len(e)} ({dict(byk)}); computed - chain: max |err| {np.abs(e).max() if len(e) else 0:.0f} lamports, sum {e.sum():.0f}; exact matches {(e == 0).sum()}/{len(e)}")
P(f"recorded sd - chain: max |err| {np.abs(np.array(errs_sd)).max() if errs_sd else 0:.0f} lamports")
for b in bad[:10]: P("  mismatch:", b)
open(f"{OUT}/r6.txt", "w").write("\n".join(L) + "\n")
