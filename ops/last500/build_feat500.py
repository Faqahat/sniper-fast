#!/usr/bin/env python3
"""STEP 1 — his LAST ~500 landed trades, every pre-buy + early-flow feature + econ outcome.
Reuses /root/profit_backtest/common.py (parse_create, gettx, trajectory, bonding_curve_of).
Incremental: writes feat_500.json after every mint so partial survives interruption.
Base = ext_buys.json (505 distinct landed mints, his real last-500 landed buys)."""
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/profit_backtest")
import common as C

OUT = "/root/last500/feat_500.json"
os.makedirs("/root/last500", exist_ok=True)

BUYS = json.load(open("/root/attempt_filter/ext_buys.json"))["buys"]
# landed buys only; group per mint: his first landed buy = his entry
landed = [b for b in BUYS if not b["failed"]]
by_mint = {}
for b in landed:
    m = b["mint"]
    if m not in by_mint or b["slot"] < by_mint[m]["slot"]:
        by_mint[m] = b
# his spray/attempt count per mint (landed+failed)
from collections import Counter
nbuys = Counter(b["mint"] for b in BUYS)
nland = Counter(b["mint"] for b in landed)
MINTS = list(by_mint.keys())
print(f"landed mints: {len(MINTS)}", flush=True)

# resume
done = {}
if os.path.exists(OUT):
    try:
        for r in json.load(open(OUT)):
            done[r["mint"]] = r
        print(f"resume: {len(done)} already done", flush=True)
    except Exception:
        pass

lock = threading.Lock()
TIP_ACCTS = set()  # jito tip accounts (8)
for t in ["96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
          "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
          "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pGADxUsBh6XxnzHHm4b5",
          "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"]:
    TIP_ACCTS.add(t)

def find_create_sig(mint, create_slot_hint):
    """oldest sig of the bonding curve = the create tx."""
    bc = C.bonding_curve_of(mint)
    before = None; last = None; pages = 0
    while pages < 12:
        pr = [bc, {"limit": 1000}]
        if before: pr[1]["before"] = before
        r = C.rpc("getSignaturesForAddress", pr)
        if not r: break
        last = r[-1]; before = r[-1]["signature"]; pages += 1
        if len(r) < 1000: break
    return last["signature"] if last else None

def metadata_feats(tx):
    """name/symbol/uri from create ix args; jito tip in create tx; funding not here."""
    out = {"name": None, "symbol": None, "uri": None, "has_social": None, "has_image": None,
           "jito_tip_create": 0.0}
    try:
        msg = tx["transaction"]["message"]; keys = C._keys(tx); meta = tx["meta"]
        # jito tip = SOL transfer to a tip account in this tx (balance delta)
        for acc in TIP_ACCTS:
            if acc in keys:
                i = keys.index(acc)
                d = (meta["postBalances"][i]-meta["preBalances"][i])/1e9
                if d > 0: out["jito_tip_create"] += d
        # create ix args: 3 strings name/symbol/uri
        for ix in msg.get("instructions", []):
            if ix.get("programId") != C.PUMP_B58: continue
            dd = C.b58dec(ix.get("data", ""))
            if dd[:8].hex() not in (C.CREATE_V2, C.CREATE): continue
            q = 8; vals = []
            for _ in range(3):
                ln = int.from_bytes(dd[q:q+4], "little"); q += 4
                vals.append(dd[q:q+ln].decode("utf-8", "replace")); q += ln
            out["name"], out["symbol"], out["uri"] = vals
            u = (out["uri"] or "").lower()
            out["has_image"] = ("ipfs" in u or "arweave" in u or "image" in u)
            break
    except Exception:
        pass
    return out

def early_flow(series, create_slot):
    """#buyers & net SOL inflow slots 0..3 from the create-anchored trade series.
    series rows: (slot, blockTime, px). We only have px here; inflow needs dsol.
    trajectory() drops dsol; recompute buyers/co-snipe count from slot occupancy."""
    # series = list of (slot, bt, px); count distinct trade rows in slots 0..3
    s03 = [r for r in series if r[0] is not None and 0 <= (r[0]-create_slot) <= 3]
    return {"n_trades_0_3": len(s03), "n_trades_slot0": sum(1 for r in series if r[0] == create_slot)}

def do(mint):
    if mint in done:
        return done[mint]
    b = by_mint[mint]
    rec = {"mint": mint, "his_buy_slot": b["slot"], "n_buys": nbuys[mint], "n_landed": nland[mint],
           "spray": nbuys[mint], "creator_pre": b.get("creator"),
           "create_slot_pre": b.get("create_slot"), "dev_buy_pre": b.get("dev_buy")}
    csig = find_create_sig(mint, b.get("create_slot"))
    if not csig:
        rec["create_found"] = False
    else:
        tx = C.gettx(csig)
        f = C.parse_create(tx)
        if f:
            rec.update(f); rec["create_found"] = True
            rec.update(metadata_feats(tx))
            rec["vanilla"] = int(f["mayhem"] == 0 and f["holder_reward"] == 0 and f["cashback"] == 0)
            # his buy delta (buy slot - create slot)
            rec["buy_delta"] = (b["slot"] - f["create_slot"]) if f.get("create_slot") else None
            # trajectory / early flow / co-snipe / outcome
            cs = f["create_slot"]
            tr = C.trajectory(mint, cs)
            rec["cosnipers_slot0"] = tr["cosnipers_slot0"]
            rec["reached_floor"] = tr["reached_floor"]
            ser = tr["series"]
            rec["n_path"] = len(ser)
            ef = early_flow(ser, cs)
            rec.update(ef)
            # peak over path
            if ser and f.get("entry_px"):
                floor = f["entry_px"]  # curve floor (create-tx dev-buy px)
                # re-anchor floor to earliest path px (true tradable floor)
                p0 = min(ser, key=lambda x: x[0]) if ser else None
                floor_px = p0[2] if p0 else floor
                rec["floor_px"] = floor_px
                pk = max((p[2]/floor_px for p in ser), default=1.0) if floor_px else None
                rec["peak_r"] = pk
            else:
                rec["floor_px"] = None; rec["peak_r"] = None
            rec["series"] = ser
        else:
            rec["create_found"] = False
    with lock:
        done[mint] = rec
    return rec

t0 = time.time(); n = 0
with ThreadPoolExecutor(max_workers=16) as ex:
    futs = [ex.submit(do, m) for m in MINTS]
    for fut in futs:
        r = fut.result(); n += 1
        if n % 20 == 0:
            with lock:
                json.dump(list(done.values()), open(OUT, "w"))
            print(f"  {n}/{len(MINTS)}  found={sum(1 for x in done.values() if x.get('create_found'))}  {time.time()-t0:.0f}s", flush=True)
with lock:
    json.dump(list(done.values()), open(OUT, "w"))
nf = sum(1 for x in done.values() if x.get("create_found"))
print(f"DONE feat_500: {len(done)} mints, create_found={nf}, {time.time()-t0:.0f}s -> {OUT}", flush=True)
