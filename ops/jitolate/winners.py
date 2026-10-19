# READ-ONLY: who lands <= D txs after a pump.fun create (excluding the creator's glued run), how (tip/sender/bundle), by leader client.
# usage: winners.py <out.jsonl> <D> slot:mint [slot:mint ...]   or   winners.py <out.jsonl> <D> @file (lines "slot mint")
import sys, json, concurrent.futures as cf
sys.path.insert(0, "/root/jitolate"); sys.path.insert(0, "/root/indep")
from buys import bundle_of_tx, cached, blk, leader, nonvote
from common import events, tx_summary, load_tipmap
tm = load_tipmap()
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
outp, D = sys.argv[1], int(sys.argv[2])
items = []
for a in sys.argv[3:]:
    if a.startswith("@"):
        items += [tuple(l.split()[:2]) for l in open(a[1:]) if l.strip()]
    else:
        items.append(tuple(a.split(":")))
items = [(int(s), m) for s, m in items]

def chain(it):
    S, M = it
    b = blk(S)
    if not isinstance(b, dict) or "transactions" not in b:
        return None
    txs = nonvote(b)
    ci = None
    for i, t in enumerate(txs):
        if any(c["mint"] == M for c in events((t.get("meta") or {}).get("logMessages"))[1]):
            ci = i; break
    if ci is None:
        return None
    r = {"slot": S, "mint": M, "n": len(txs), "ci": ci, "frac": round(ci / len(txs), 3), "client": leader(S)[1], "win": (S - 458784000) % 4,
         "create_sig": txs[ci]["transaction"]["signatures"][0], "create_tips": tx_summary(txs[ci], tm)[0]["tips"]}
    glued, gsol, run, rows = 0, 0, True, []
    for j, t in enumerate(txs[ci + 1:], start=1):
        meta = t.get("meta") or {}
        ev = [e for e in events(meta.get("logMessages"))[0] if e["mint"] == M and e["buy"]]
        ok = meta.get("err") is None
        if run:
            if ev and ok:
                glued += 1; gsol += sum(e['sol'] for e in ev); continue
            run = False
        if j > D + glued:
            break
        if ev:
            s = tx_summary(t, tm)[0]
            rows.append({"d": j - glued, "j": j, "sig": s["sig"], "payer": s["payer"], "ok": ok, "sol": round(sum(e["sol"] for e in ev) / 1e9, 4),
                         "tips": s["tips"], "cu_price": s["cu_price"], "cu_limit": s["cu_limit"], "fee": s["fee"], "me": s["payer"] == ME})
    r["glued"] = glued; r["glued_sol"] = round(gsol / 1e9, 3); r["out"] = rows
    return r

with cf.ThreadPoolExecutor(max_workers=6) as ex:
    res = [r for r in ex.map(chain, items) if r]
print("chain done", len(res), flush=True)
fo = open(outp, "w")
for r in res:
    cb = bundle_of_tx(r["create_sig"])
    r["create_bundle"] = {"id": cb.get("bundleId"), "ntx": len(cb.get("txSignatures", [])), "bi": cb.get("blockIndex"), "tip": cb.get("landedTipLamports")} if cb else None
    cset = set(cb.get("txSignatures", [])) if cb else set()
    for w in r["out"]:
        if not w["ok"]:
            continue
        if w["sig"] in cset:
            w["bundle"] = {"same_as_create": True}; continue
        b = bundle_of_tx(w["sig"])
        w["bundle"] = {"id": b.get("bundleId")[:10], "ntx": len(b.get("txSignatures", [])), "bi": b.get("blockIndex"), "tip": b.get("landedTipLamports"),
                       "tippers": [x[:6] for x in b.get("tippers", [])]} if b else None
    fo.write(json.dumps(r) + "\n"); fo.flush()
print("DONE", flush=True)
