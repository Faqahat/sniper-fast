#!/usr/bin/env python3
"""READ-ONLY calibration of the creator-bundle leg SOL from instruction data vs the chain's TradeEvent sol.
Glued run = the non-vote txs right after the create in block order that are OK and carry a buy TradeEvent of the mint
(race_lib.block_record). For each leg: its top-level pump buy ix (exact-in: SOL at data[8..16]; cap: tokens at [8..16],
max SOL at [16..24]) or none (CPI via a router). Compares models of the leg's curve SOL with TradeEvent sol, simulating
the curve sequentially from the create's last TradeEvent (dev buy). Usage: calib.py N [fee_bps]"""
import sys, json, base64, collections
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, b58dec, PUMP, VSOL0, VTOK0
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
EXACT = {bytes([0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f]), bytes([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88]), bytes([0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f])}
CAP = {bytes([0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea]), bytes([0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d]), bytes([0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50])}
K = VSOL0 * VTOK0
def cost(vq, tokens):
    vt = K // vq
    if tokens >= vt: return None
    nvt = vt - tokens
    return -(-K // nvt) - vq
recs = []
for l in open("/root/race/fresh_onchain.jsonl"):
    r = json.loads(l); b = r.get("b") or {}
    if b.get("glued", 0) >= 1 and "cidx" in b: recs.append(b)
recs = recs[-N:]
rows = []; kinds = collections.Counter(); stops = collections.Counter()
for b in recs:
    blk = get_block(b["slot"])
    if not isinstance(blk, dict) or "transactions" not in blk: continue
    txs = blk["transactions"]; mint = b["mint"]
    ci = b["cidx"]
    ctr, _ = events((txs[ci].get("meta") or {}).get("logMessages"))
    cev = [e for e in ctr if e["mint"] == mint]
    vq = cev[-1]["vsol"] if cev else VSOL0
    for j in range(ci + 1, len(txs)):
        t = txs[j]
        if is_vote(t): continue
        m = t.get("meta") or {}
        ok = m.get("err") is None
        tr, _ = events(m.get("logMessages")) if ok else ([], [])
        evb = [e for e in tr if e["mint"] == mint and e["buy"]]
        if not (ok and evb):
            stops["failed tx" if not ok else ("other mint/pump tx" if any(PUMP in (t["transaction"]["message"]["accountKeys"])for _ in [0]) else "non-pump tx")] += 1
            break
        msg = t["transaction"]["message"]; keys = msg["accountKeys"] + (m.get("loadedAddresses") or {}).get("writable", []) + (m.get("loadedAddresses") or {}).get("readonly", [])
        leg = None
        for ix in msg["instructions"]:
            if keys[ix["programIdIndex"]] != PUMP: continue
            d = b58dec(ix["data"])
            if d[:8] in EXACT: leg = ("exact", int.from_bytes(d[8:16], "little"), int.from_bytes(d[16:24], "little"))
            elif d[:8] in CAP: leg = ("cap", int.from_bytes(d[8:16], "little"), int.from_bytes(d[16:24], "little"))
            if leg: break
        ev_sol = sum(e["sol"] for e in evb)
        kind = leg[0] if leg else "cpi"
        kinds[kind] += 1
        rows.append((kind, leg, ev_sol, vq, evb[-1]["vsol"], b["mint"][:8]))
        vq = evb[-1]["vsol"]
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
print(f"launches {len(recs)}, glued legs {len(rows)}: {dict(kinds)}; run stopped by: {dict(stops)}")
ex = [(leg[1], ev) for k, leg, ev, *_ in rows if k == "exact" and leg[1] > 0]
if ex:
    rat = [ev / a for a, ev in ex]
    print(f"exact-in: TradeEvent sol / ix SOL: p10 {pct(rat,.1):.5f} p50 {pct(rat,.5):.5f} p90 {pct(rat,.9):.5f}  (implied fee bps at p50 {(1/pct(rat,.5)-1)*1e4:.1f})")
cp = [(leg, ev, vq) for k, leg, ev, vq, *_ in rows if k == "cap"]
if cp:
    err = [abs((cost(vq, leg[1]) or 0) - ev) / max(ev, 1) for leg, ev, vq in cp]
    print(f"cap: |curve_cost(prev vsol, tokens) - TradeEvent sol| / sol: p50 {pct(err,.5)*100:.3f}% p90 {pct(err,.9)*100:.3f}%  (n={len(cp)})")
json.dump([[k, leg, ev, vq, vq2, m] for k, leg, ev, vq, vq2, m in rows], open("/root/gap/final/calib_rows.json", "w"))
