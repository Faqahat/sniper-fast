#!/usr/bin/env python3
"""READ-ONLY: what are the CPI legs (top-level programs) and the failed txs that end runs; multi-ix legs; and the
engine model (sum every top-level pump buy ix of the mint in order, exact-in net = a*10000/10125, cap = curve cost,
fail if cost*1.0125 > max_sol) vs TradeEvents. Usage: calib2.py N"""
import sys, json, collections
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, b58dec, PUMP, VSOL0, VTOK0
N = int(sys.argv[1])
EXACT = {bytes([0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f]), bytes([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88]), bytes([0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f])}
CAP = {bytes([0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea]), bytes([0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d]), bytes([0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50])}
K = VSOL0 * VTOK0
def buy_sol(vq, tokens):
    vt = K // vq
    if tokens >= vt: return None
    return -(-K // (vt - tokens)) - vq
def tokens_for(vq, sol):
    vt = K // vq
    return vt - (-(-K // (vq + sol)))
recs = []
for l in open("/root/race/fresh_onchain.jsonl"):
    r = json.loads(l); b = r.get("b") or {}
    if b.get("glued", 0) >= 1 and "cidx" in b: recs.append(b)
recs = recs[-N:]
cpi_prog = collections.Counter(); fail_kind = collections.Counter(); errs = []; launch_err = []
for b in recs:
    blk = get_block(b["slot"])
    if not isinstance(blk, dict) or "transactions" not in blk: continue
    txs = blk["transactions"]; mint = b["mint"]; ci = b["cidx"]
    ctr, _ = events((txs[ci].get("meta") or {}).get("logMessages"))
    cev = [e for e in ctr if e["mint"] == mint]
    vq = cev[-1]["vsol"] if cev else VSOL0
    vq_model = vq; chain_sol = 0; model_sol = 0; model_ok = True
    for j in range(ci + 1, len(txs)):
        t = txs[j]
        if is_vote(t): continue
        m = t.get("meta") or {}; ok = m.get("err") is None
        msg = t["transaction"]["message"]
        keys = msg["accountKeys"] + (m.get("loadedAddresses") or {}).get("writable", []) + (m.get("loadedAddresses") or {}).get("readonly", [])
        legs = []
        for ix in msg["instructions"]:
            if keys[ix["programIdIndex"]] != PUMP: continue
            if mint not in [keys[a] for a in ix["accounts"]]: continue
            d = b58dec(ix["data"])
            if d[:8] in EXACT: legs.append(("exact", int.from_bytes(d[8:16], "little"), int.from_bytes(d[16:24], "little")))
            elif d[:8] in CAP: legs.append(("cap", int.from_bytes(d[8:16], "little"), int.from_bytes(d[16:24], "little")))
        tr, _ = events(m.get("logMessages")) if ok else ([], [])
        evb = [e for e in tr if e["mint"] == mint and e["buy"]]
        # model: would this tx be a successful buy leg?
        mok = bool(legs); msol = 0; v = vq_model
        for k, x, y in legs:
            if k == "exact":
                net = x * 10000 // 10125
                if y and tokens_for(v, net) < y: mok = False; break
                msol += net; v += net
            else:
                c = buy_sol(v, x)
                if c is None or (y and c * 10125 // 10000 > y): mok = False; break
                msol += c; v += c
        if not (ok and evb):
            fail_kind[("failed" if not ok else "not-a-buy") + (" (model: buy-ok)" if mok else (" (model: has buy ix, predicts fail)" if legs else " (model: no buy ix)"))] += 1
            break
        if not legs:
            progs = sorted({keys[ix["programIdIndex"]][:6] for ix in msg["instructions"]})
            cpi_prog[",".join(progs)] += 1
        es = sum(e["sol"] for e in evb)
        if legs and mok: errs.append(abs(msol - es) / max(es, 1))
        chain_sol += es; model_sol += msol if mok else 0
        vq = evb[-1]["vsol"]; vq_model = vq   # resync the model curve on the chain's after each leg (per-leg error only)
    launch_err.append((chain_sol, model_sol))
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
print("run ends:", dict(fail_kind))
print("CPI legs (no top-level pump buy ix) by top-level programs:", cpi_prog.most_common(8))
print(f"per-leg model |err| (legs with a top-level buy ix): p50 {pct(errs,.5)*100:.3f}% p90 {pct(errs,.9)*100:.3f}% max {max(errs)*100 if errs else 0:.2f}% n={len(errs)}")
le = [abs(m - c) / max(c, 1) for c, m in launch_err if c > 0]
print(f"per-launch bundle SOL |err| (CPI legs count 0 in the model): p50 {pct(le,.5)*100:.2f}% p90 {pct(le,.9)*100:.2f}% n={len(le)}")
