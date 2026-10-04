#!/usr/bin/env python3
"""Per send path, on the leader's PoH clock: where our copy ran relative to the trigger (same slot? ms after?), against
the winner of the same gap. One path per trade (rotation), so each row is a clean sample of one path.
usage: poh6.py <run> [takers file]"""
import json, collections, types, sys
_ns = {}
exec(open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/"')[0], _ns)
T = types.SimpleNamespace(**_ns)
RUN = sys.argv[1]; TK = sys.argv[2] if len(sys.argv) > 2 else None
B = f"/root/arb-lab/runs/{RUN}/"
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None
log = {}
for line in open(B + "poh.log"):
    s8, slot, ms = line.split()
    log.setdefault(s8, (int(slot), float(ms)))
at = lambda sig: log.get(T.b58d(sig)[:8].hex()) if sig else None
after = lambda x, y: (x[0] - y[0]) * 400 + x[1] - y[1]
a = {x["attempt"]: x for x in map(json.loads, open(B + "attempts.jsonl"))}
o = {x["attempt"]: x for x in map(json.loads, open(B + "outcomes.jsonl"))}
cp = collections.defaultdict(list)
for x in map(json.loads, open(B + "copies.jsonl")): cp[x["attempt"]].append(x)
win = {}
if TK:
    for r in map(json.loads, open(f"/root/arb-lab/runs/{TK}")):
        if r["takers"]: win[r["attempt"]] = r["takers"][0]
rows = collections.defaultdict(list)
print(f"{'att':>3} {'path':<11} {'trig slot':>10} {'landed':>7} {'ours ms':>8} {'winner ms':>9} {'ack ms':>6} code")
for i in sorted(a):
    x, out = a[i], o.get(i, {})
    tp = at(x["trigger"])
    path = out.get("landed") or (cp[i][0]["path"] if cp[i] else "?")
    op = at(out.get("sig")) if out.get("landed") else None
    w = win.get(i); wp = at(w["sig"]) if w else None
    ours = after(op, tp) if tp and op else None
    wms = after(wp, tp) if tp and wp else None
    dslot = (out.get("slot") - x["slot"]) if out.get("slot") and x.get("slot") else None
    ack = min((c.get("ms") or 0 for c in cp[i]), default=None)
    rows[path].append({"landed": bool(out.get("landed")), "dslot": dslot, "ours": ours, "win": wms, "ack": ack, "ok": out.get("ok")})
    print(f"{i:>3} {path:<11} {x.get('slot',0):>10} {'+'+str(dslot) if dslot is not None else '-':>7} {ours if ours is None else round(ours,1)!s:>8} {wms if wms is None else round(wms,1)!s:>9} {round(ack or 0,1):>6} {out.get('code')}")
print("\nPER PATH: sent | landed | same slot as trigger (slot 0) | ours ms after trigger p50 (min) | winner p50 | ack p50")
for p, r in sorted(rows.items()):
    L = [z for z in r if z["landed"]]
    om = [z["ours"] for z in L if z["ours"] is not None]
    print(f"  {p:<11} {len(r):>3} | {len(L):>3} | {sum(1 for z in L if z['dslot']==0):>3} | {q(om,.5)!s:>7} ({min(om) if om else None}) | {q([z['win'] for z in r if z['win'] is not None],.5)!s:>7} | {q([z['ack'] for z in r],.5)}")
