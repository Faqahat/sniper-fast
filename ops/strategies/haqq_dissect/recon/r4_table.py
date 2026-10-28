#!/usr/bin/env python3
"""recon step 4 (read-only): ONE exact per-tx table of every haqq signature in the window (chain list = truth):
recorded txs (r3 tx.pkl, exact deltas) + unrecorded txs (public-RPC getTransaction, parsed by txparse). Classifies each tx and
splits its wallet delta into: bot trade cash, tx fee, tips, token-account rent, closes, WSOL wrap/unwrap, payouts, inbound transfers.
Out: recon/table.pkl (list of row dicts, window only) + recon/table_all.pkl (window + recorded outside rows for lot tracking)."""
import json, pickle, glob, collections, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import txparse as TP
H = TP.H; RENT = TP.RENT
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
WSOL_ACC = "3aoEhd6mTk7q6beUTVYHFoF79tFrQdoXcqXP5wiHxSQy"     # haqq's WSOL account (token balance owner = haqq, mint So111..; MEASURED in getTransaction)
S = json.load(open(f"{OUT}/sigs.json"))
chain = {s["signature"]: s for s in S}
rec = pickle.load(open(f"{OUT}/rec.pkl", "rb"))
R3 = {r["sig"]: r for r in pickle.load(open(f"{OUT}/tx.pkl", "rb"))}
G = {}
for fx in sorted(glob.glob(f"{OUT}/gettx*.jsonl")):
    for l in open(fx):
        j = json.loads(l)
        if j.get("res") is not None: G[(j["sig"], j["why"])] = j["res"]
GS = {}
for (sig, why), res in G.items(): GS[sig] = res


def from_rec(r):
    d = rec[r["sig"]]; sd = dict(d.get("sd") or [])
    x = dict(sig=r["sig"], s=r["s"], i=r["i"], bt=r["bt"], src="rec", ok=r["ok"], code=r["code"], cup=r["cup"], txfee=r["txfee"],
             tips=r["tips"], rent=r.get("rent") or 0, n_created=(r.get("rent") or 0) // RENT, sd=r["sd"], wsol_d=sd.get(WSOL_ACC, 0), ev=[], n_closed=0, payer=H)
    evs = [TP.parse_trade(b) for b in _chunks(d.get("ev")) if b[:8] == TP.DISC and len(b) >= 225]
    x["ev"] = [e for e in evs if e["user"] == H]
    x["trade"] = sum((-(e["sol"] + e["fee"] + e["cfee"]) if e["buy"] else (e["sol"] - e["fee"] - e["cfee"])) for e in x["ev"])
    ix = set(d.get("ixn") or [])
    if not r["ok"]: x["cls"] = "fail"
    elif ix == {"CloseAccount"}:
        x["cls"] = "close"; x["n_closed"] = round((r["sd"] + r["txfee"] + r["tips"]) / RENT)
    elif x["ev"]: x["cls"] = "buy" if x["ev"][0]["buy"] else "sell"
    elif any(t.startswith("Sell") for t in ix):
        x["cls"] = "swap_sell"            # PumpSwap (graduated) sell: proceeds land in the WSOL account
        tb = [t for t in d.get("tb") or [] if t[1] == H]
        x["ev"] = [dict(mint=tb[0][0], tok=tb[0][2] - tb[0][3], buy=False, sol=x["wsol_d"], fee=0, cfee=0, swap=True)] if tb else []
        x["trade"] = 0
    else: x["cls"] = "other_rec"
    return x


def _chunks(evs):
    import base64
    for e in evs or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == TP.CPI: b = b[8:]
            yield b


def from_rpc(res):
    p = TP.parse(res)
    msg = res["transaction"]["message"]; meta = res["meta"]
    keys = [k["pubkey"] for k in msg["accountKeys"]]
    la = meta.get("loadedAddresses") or {}; keys += (la.get("writable") or []) + (la.get("readonly") or [])
    wd = 0
    if WSOL_ACC in keys:
        k = keys.index(WSOL_ACC); wd = meta["postBalances"][k] - meta["preBalances"][k]
    x = dict(sig=p["sig"], s=p["s"], i=p["i"], bt=p["bt"], src="rpc", ok=p["ok"], code=p["code"], cup=p["cup"], txfee=p["txfee"] if p["payer"] == H else 0,
             rent=p["rent"], n_created=p["n_created"], sd=p["sd"], wsol_d=wd, ev=p["events"], trade=p["trade"], n_closed=p["n_closed"], payer=p["payer"],
             top=p["top"], transfers=p["transfers"], progs=p["progs"], pre=p["pre"], post=p["post"])
    x["tips"] = 0
    if p["payer"] != H:
        x["cls"] = "inbound" if p["sd"] > 0 else "third_party_zero" if p["sd"] == 0 else "third_party_neg"
    elif not p["ok"]: x["cls"] = "fail"
    elif p["events"]:
        x["cls"] = "buy" if p["events"][0]["buy"] else "sell"
        x["tips"] = -(p["sd"] + x["txfee"] + p["rent"] - p["trade"])
    elif any(pr.startswith("JUP6") for pr in p["progs"]):
        x["cls"] = "payout"
    elif any(t.endswith("unwrapLamports") for t in p["top"]) or (wd < 0 and p["sd"] > 0):
        x["cls"] = "unwrap"
    elif p["n_closed"]:
        x["cls"] = "close"
    elif any(pr == "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA" for pr in p["progs"]):
        x["cls"] = "swap_sell_rpc"
    else:
        x["cls"] = "other_rpc"
    return x


rows = []; miss = []
for s in S:
    if not (W0 <= s["blockTime"] < W1): continue
    sig = s["signature"]
    if sig in R3: rows.append(from_rec(R3[sig]))
    elif sig in GS: rows.append(from_rpc(GS[sig]))
    else: miss.append(sig)
rows.sort(key=lambda r: (r["s"], r["i"] if r["i"] is not None else 0))
print(f"window rows {len(rows):,}; not yet fetched {len(miss)}")
print(collections.Counter((r["src"], r["cls"]) for r in rows))
pickle.dump(dict(rows=rows, miss=miss), open(f"{OUT}/table.pkl", "wb"))
# all recorded rows (W0-6h..end) for lot tracking, with the window's rpc rows merged in
allrows = [from_rec(r) for r in R3.values()]
have = {r["sig"] for r in allrows}
allrows += [r for r in rows if r["sig"] not in have]
allrows.sort(key=lambda r: (r["s"], r["i"] if r["i"] is not None else 0))
pickle.dump(allrows, open(f"{OUT}/table_all.pkl", "wb"))
print("all rows for lots:", len(allrows))
