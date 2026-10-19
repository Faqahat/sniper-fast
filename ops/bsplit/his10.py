# READ-ONLY: 4yFAz's last 10 completed trades, straight from chain. Where he landed, what was ahead, fill, exits, PnL.
import sys, json, concurrent.futures as cf
sys.path.insert(0, "/root/indep")
from common import rpc, events, get_block, is_vote, VSOL0, VTOK0

W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
sigs = []
before = None
for _ in range(3):
    p = {"limit": 1000}
    if before:
        p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p])
    if not isinstance(r, list) or not r:
        break
    sigs += r
    before = r[-1]["signature"]
okc = [s for s in sigs if s.get("err") is None]
print(f"sigs {len(sigs)} (ok {len(okc)}, failed {len(sigs)-len(okc)})", file=sys.stderr)


def gt(s):
    t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not isinstance(t, dict) or "meta" not in t:
        return None
    tr, _ = events(t["meta"].get("logMessages"))
    mine = [e for e in tr if e["user"] == W]
    if not mine:
        return None
    return {"sig": s["signature"], "slot": t["slot"], "bt": t.get("blockTime"), "fee": t["meta"].get("fee", 0), "ev": mine}


with cf.ThreadPoolExecutor(max_workers=8) as ex:
    T = [x for x in ex.map(gt, okc) if x]
by = {}
for t in T:
    for e in t["ev"]:
        by.setdefault(e["mint"], []).append(dict(e, slot=t["slot"], bt=t["bt"], fee=t["fee"] / len(t["ev"]), sig=t["sig"]))
trips = []
for m, es in by.items():
    es.sort(key=lambda e: (e["slot"], e["bt"] or 0))
    b = [e for e in es if e["buy"]]
    s = [e for e in es if not e["buy"]]
    if b and s and es[0]["buy"]:
        trips.append((b[0]["bt"] or 0, m, b, s))
trips.sort(reverse=True)
trips = trips[:10]


def analyze(tp):
    _, m, b, s = tp
    b0 = b[0]
    res = {"mint": m, "buy_slot": b0["slot"]}
    for cs in (b0["slot"], b0["slot"] - 1, b0["slot"] - 2):
        blk = get_block(cs)
        if not isinstance(blk, dict) or "transactions" not in blk:
            continue
        txs = blk["transactions"]
        ci = None
        for i, t in enumerate(txs):
            meta = t.get("meta") or {}
            if meta.get("err") is not None:
                continue
            tr, cr = events(meta.get("logMessages"))
            if any(c["mint"] == m for c in cr):
                ci = i
                devb = [e for e in tr if e["mint"] == m and e["buy"]]
                dev = (devb[0]["vsol"] - VSOL0) if devb else 0
                base = VSOL0 + dev
                break
        if ci is None:
            continue
        res.update(create_slot=cs, dev=dev / 1e9, slot_off=b0["slot"] - cs)
        glued, gsol, gv, run, rank, ahead, nbuyers = 0, 0, base, True, None, 0, 0
        for t in txs[ci + 1:]:
            if is_vote(t):
                continue
            meta = t.get("meta") or {}
            tr, _ = events(meta.get("logMessages"))
            ev = [e for e in tr if e["mint"] == m and e["buy"]]
            okk = meta.get("err") is None
            if run:
                if ev and okk:
                    glued += 1; gsol += sum(e["sol"] for e in ev); gv = ev[-1]["vsol"]
                else:
                    run = False
            if ev and okk:
                if any(e["user"] == W for e in ev):
                    rank = nbuyers
                    break
                nbuyers += 1
                ahead += sum(e["sol"] for e in ev)
        res.update(bundle_buys=glued, bundle_sol=gsol / 1e9, post_bundle=(gv / base) ** 2,
                   rank=rank if b0["slot"] == cs else f"next-slot (after {nbuyers} same-slot buys)", sol_ahead=ahead / 1e9)
        break
    floor = (VSOL0 + res.get("dev", 0) * 1e9) ** 2 / (VSOL0 * VTOK0)
    bs = sum(e["sol"] for e in b); bt_ = sum(e["tok"] for e in b)
    ss = sum(e["sol"] for e in s)
    fees = sum(e["fee"] for e in b + s) / 1e9
    res.update(sol_in=bs / 1e9, fill=(b0["sol"] / b0["tok"]) / floor if b0["tok"] else None, n_buys=len(b), n_sells=len(s),
               sol_out=ss / 1e9, fees=fees, pnl=(ss - bs) / 1e9 - fees, pnl_pct=((ss - bs) / 1e9 - fees) / (bs / 1e9),
               hold_s=(s[-1]["bt"] or 0) - (b0["bt"] or 0),
               exits=[round(((e["sol"] / e["tok"]) / (b0["sol"] / b0["tok"])), 2) for e in s if e["tok"]])
    return res


with cf.ThreadPoolExecutor(max_workers=5) as ex:
    out = list(ex.map(analyze, trips))
json.dump(out, open("/root/bsplit/his10.json", "w"), indent=1)
print(f"{'mint':9} {'dev':>5} {'off':>3} {'bundle':>11} {'post-b':>6} {'pos':>22} {'ahead':>6} {'fill':>5} {'in':>5} "
      f"{'out':>6} {'fees':>6} {'PnL':>7} {'PnL%':>6} {'hold':>4} {'#s':>2} exits(x his entry)")
for r in out:
    print(f"{r['mint'][:8]:9} {r.get('dev', 0):5.2f} {str(r.get('slot_off', '?')):>3} {r.get('bundle_buys', 0):2}b/{r.get('bundle_sol', 0):6.2f} "
          f"{r.get('post_bundle', 0):6.2f} {str(r.get('rank')):>22} {r.get('sol_ahead', 0):6.2f} {r['fill'] or 0:5.2f} {r['sol_in']:5.2f} "
          f"{r['sol_out']:6.2f} {r['fees']:6.4f} {r['pnl']:+7.3f} {r['pnl_pct']:+6.1%} {r['hold_s']:4} {r['n_sells']:2} {r['exits'][:6]}")
tot_in = sum(r["sol_in"] for r in out)
print(f"\nTOTAL in {tot_in:.2f} SOL  PnL {sum(r['pnl'] for r in out):+.3f} SOL ({sum(r['pnl'] for r in out)/tot_in:+.1%})  "
      f"wins {sum(r['pnl'] > 0 for r in out)}/10")
