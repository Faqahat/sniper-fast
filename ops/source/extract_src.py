#!/usr/bin/env python3
"""Slot-0 SOURCE/DEPLOYER fingerprint extractor for 4yFAz study.
Produces per-mint: uri host/terminal, mint vanity suffix, create-tx structure
(ix count, program sequence, compute-budget cu_limit/cu_price, jito tip, dev-buy
disc+bundling), creator wallet behavior hooks. Runs on HIS picks (feat_500) and
the population (profit_backtest/creates.json). Incremental saves."""
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/profit_backtest")
import common as C

CB_PROG = "ComputeBudget111111111111111111111111111111"
SYS_PROG = "11111111111111111111111111111111"
TOK_PROG = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOK22    = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ATA_PROG = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
TIP_ACCTS = {"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
  "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
  "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pGADxUsBh6XxnzHHm4b5",
  "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}

def prog_tag(pid):
    if pid == C.PUMP_B58: return "PUMP"
    if pid == CB_PROG: return "CB"
    if pid == SYS_PROG: return "SYS"
    if pid == TOK_PROG: return "TOK"
    if pid == TOK22: return "T22"
    if pid == ATA_PROG: return "ATA"
    return "OTH"

def cb_vals(dd):
    """decode a ComputeBudget ix: disc byte 0. 0x02=SetCULimit(u32),0x03=SetCUPrice(u64)."""
    if not dd: return None
    disc = dd[0]
    if disc == 2 and len(dd) >= 5:
        return ("cu_limit", int.from_bytes(dd[1:5], "little"))
    if disc == 3 and len(dd) >= 9:
        return ("cu_price", int.from_bytes(dd[1:9], "little"))
    if disc == 1 and len(dd) >= 5:
        return ("heap", int.from_bytes(dd[1:5], "little"))
    return ("cb%d" % disc, None)

def fingerprint(tx, mint):
    """extract source fingerprint from a create tx."""
    out = {"mint": mint}
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        out["ok"] = False; return out
    msg = tx["transaction"]["message"]; keys = C._keys(tx); meta = tx["meta"]
    ixs = msg.get("instructions", [])
    seq = []; cu_limit = None; cu_price = None
    n_pump = 0; n_cb = 0
    uri = name = symbol = None
    dev_buy_disc = None; dev_buy_bundled = 0; dev_buy_off = None
    for ix in ixs:
        pid = ix.get("programId"); tag = prog_tag(pid); seq.append(tag)
        try: dd = C.b58dec(ix.get("data", "")) if ix.get("data") else b""
        except Exception: dd = b""
        if tag == "CB":
            n_cb += 1; v = cb_vals(dd)
            if v:
                if v[0] == "cu_limit": cu_limit = v[1]
                elif v[0] == "cu_price": cu_price = v[1]
        elif tag == "PUMP":
            n_pump += 1; disc = dd[:8].hex() if len(dd) >= 8 else ""
            if disc in (C.CREATE_V2, C.CREATE):
                # parse name/symbol/uri
                q = 8; vals = []
                try:
                    for _ in range(3):
                        ln = int.from_bytes(dd[q:q+4], "little"); q += 4
                        vals.append(dd[q:q+ln].decode("utf-8", "replace")); q += ln
                    name, symbol, uri = vals
                except Exception: pass
            elif disc in C.DEV_BUY_SOL_AT_8 or disc in C.DEV_BUY_SOL_AT_16:
                dev_buy_disc = disc; dev_buy_bundled = 1
                dev_buy_off = 8 if disc in C.DEV_BUY_SOL_AT_8 else 16
    # jito tip
    tip = 0.0
    for acc in TIP_ACCTS:
        if acc in keys:
            i = keys.index(acc)
            try:
                d = (meta["postBalances"][i]-meta["preBalances"][i])/1e9
                if d > 0: tip += d
            except Exception: pass
    # uri host
    host = None
    if uri and "://" in uri:
        try: host = uri.split("/")[2].lower()
        except Exception: host = None
    out.update({
        "ok": True,
        "uri": uri, "uri_host": host, "name": name, "symbol": symbol,
        "mint_suffix4": mint[-4:], "mint_suffix_pump": int(mint.lower().endswith("pump")),
        "n_ix": len(ixs), "n_pump_ix": n_pump, "n_cb_ix": n_cb,
        "prog_seq": "-".join(seq),
        "cu_limit": cu_limit, "cu_price": cu_price,
        "jito_tip": tip, "has_jito_tip": int(tip > 0),
        "dev_buy_disc": dev_buy_disc, "dev_buy_bundled": dev_buy_bundled, "dev_buy_off": dev_buy_off,
        "n_signers": msg.get("header", {}).get("numRequiredSignatures"),
        "n_acct": len(keys),
        "fee_payer": keys[0] if keys else None,
    })
    return out

def find_create_sig(mint):
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

def run_his(out_path):
    feat = json.load(open("/root/last500/feat_500.json"))
    mints = [r["mint"] for r in feat]
    done = {}
    if os.path.exists(out_path):
        try:
            for r in json.load(open(out_path)): done[r["mint"]] = r
        except Exception: pass
    lock = threading.Lock(); n = [0]; t0 = time.time()
    def do(m):
        if m in done: return
        sig = find_create_sig(m)
        if not sig:
            r = {"mint": m, "ok": False}
        else:
            tx = C.gettx(sig); r = fingerprint(tx, m); r["sig"] = sig
        with lock:
            done[m] = r; n[0] += 1
            if n[0] % 40 == 0:
                json.dump(list(done.values()), open(out_path, "w"))
                print(f"  his {n[0]}/{len(mints)} ok={sum(1 for x in done.values() if x.get('ok'))} {time.time()-t0:.0f}s", flush=True)
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(do, mints))
    json.dump(list(done.values()), open(out_path, "w"))
    print(f"HIS done: {len(done)} ok={sum(1 for x in done.values() if x.get('ok'))}", flush=True)

def run_pop(out_path):
    creates = json.load(open("/root/profit_backtest/creates.json"))
    done = {}
    if os.path.exists(out_path):
        try:
            for r in json.load(open(out_path)): done[r["mint"]] = r
        except Exception: pass
    lock = threading.Lock(); n = [0]; t0 = time.time()
    def do(c):
        m = c["mint"]
        if m in done: return
        sig = c.get("sig")
        if not sig:
            r = {"mint": m, "ok": False}
        else:
            tx = C.gettx(sig); r = fingerprint(tx, m); r["sig"] = sig
            r["create_slot"] = c.get("create_slot")
        with lock:
            done[m] = r; n[0] += 1
            if n[0] % 100 == 0:
                json.dump(list(done.values()), open(out_path, "w"))
                print(f"  pop {n[0]}/{len(creates)} ok={sum(1 for x in done.values() if x.get('ok'))} {time.time()-t0:.0f}s", flush=True)
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(do, creates))
    json.dump(list(done.values()), open(out_path, "w"))
    print(f"POP done: {len(done)} ok={sum(1 for x in done.values() if x.get('ok'))}", flush=True)

if __name__ == "__main__":
    which = sys.argv[1]
    if which == "his": run_his("/root/source/his_src.json")
    elif which == "pop": run_pop("/root/source/pop_src.json")
