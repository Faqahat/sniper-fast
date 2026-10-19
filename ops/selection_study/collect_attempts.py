#!/usr/bin/env python3
"""Scan target wallet sigs over the SAME window as the 200 landed picks; collect FAILED + landed
pump buy attempts. Extract target mint=accs[1], buyer=accs[8]==WALLET, intended spend. Dedup to
distinct mints. All gettx results are disk-cached by common.gettx so reruns are fast."""
import os, sys, json, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, "/root/profit_backtest")
import common as C
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP = C.PUMP_B58
SPEND = C.DEV_BUY_SOL_AT_8
CAP = C.DEV_BUY_SOL_AT_16
enr = json.load(open("/root/snipe_study50/enriched200.json"))
WIN_LO, WIN_HI = enr["meta"][0], enr["meta"][1]
sigs = []
before = None
while True:
    pr = [WALLET, {"limit": 1000}]
    if before:
        pr[1]["before"] = before
    ch = C.rpc("getSignaturesForAddress", pr)
    if not ch:
        break
    sigs += ch
    before = ch[-1]["signature"]
    if ch[-1].get("blockTime") and ch[-1]["blockTime"] < WIN_LO:
        break
    if len(ch) < 1000:
        break
sigs = [s for s in sigs if s.get("blockTime") and WIN_LO <= s["blockTime"] <= WIN_HI]
n_err = sum(1 for s in sigs if s.get("err"))
n_succ = len(sigs) - n_err
print("window sigs=%d succ=%d err=%d" % (len(sigs), n_succ, n_err), flush=True)


def extract(sig):
    tx = C.gettx(sig)
    if not tx or not tx.get("transaction"):
        return None
    msg = tx["transaction"]["message"]
    for ix in msg.get("instructions", []):
        if ix.get("programId") != PUMP:
            continue
        d = C.b58dec(ix.get("data", ""))
        disc = d[:8].hex()
        accs = ix.get("accounts", [])
        if disc not in SPEND and disc not in CAP:
            continue
        if len(accs) < 9 or accs[8] != WALLET:
            continue
        off = 8 if disc in SPEND else 16
        spend = int.from_bytes(d[off:off + 8], "little") if len(d) >= off + 8 else 0
        landed = (tx.get("meta") or {}).get("err") is None
        return {"sig": sig, "slot": tx.get("slot"), "blockTime": tx.get("blockTime"),
                "mint": accs[1], "spend": spend, "landed": landed}
    return None


attempts = []
with ThreadPoolExecutor(max_workers=24) as ex:
    futs = {ex.submit(extract, s["signature"]): s for s in sigs}
    for i, fu in enumerate(as_completed(futs)):
        r = fu.result()
        if r:
            attempts.append(r)
        if (i + 1) % 1000 == 0:
            print("  scanned %d/%d got %d" % (i + 1, len(sigs), len(attempts)), flush=True)

mints = {}
for a in attempts:
    m = mints.setdefault(a["mint"], {"mint": a["mint"], "n_attempt": 0, "n_land": 0,
                                     "first_slot": a["slot"], "landed": False, "spend_max": 0})
    m["n_attempt"] += 1
    if a["landed"]:
        m["n_land"] += 1
        m["landed"] = True
    if a["slot"] and (m["first_slot"] is None or a["slot"] < m["first_slot"]):
        m["first_slot"] = a["slot"]
    m["spend_max"] = max(m["spend_max"], a["spend"])
rows = list(mints.values())
nl = sum(1 for m in rows if m["landed"])
n_land_tx = sum(1 for a in attempts if a["landed"])
print("distinct attempted mints=%d  landed=%d  never-landed=%d" % (len(rows), nl, len(rows) - nl), flush=True)
print("buy-attempt txs parsed=%d  landed-txs=%d  failed-txs=%d" % (len(attempts), n_land_tx, len(attempts) - n_land_tx), flush=True)
json.dump({"win": [WIN_LO, WIN_HI], "n_sigs": len(sigs), "n_err": n_err, "n_succ": n_succ,
           "attempts": attempts, "mints": rows}, open("/root/selection_study/attempts.json", "w"))
print("wrote attempts.json", flush=True)
