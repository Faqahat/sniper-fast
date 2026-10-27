#!/usr/bin/env python3
# INSTANT-BOTS study, step 16 (read-only, Jito explorer API, cached, <= 2 calls/s): EVERY "OTHER" buy (not the seller's own tool,
# no own attempts before) landing 1-3 positions after a dump on a Jito / BAM / Harmonic leader: same Jito bundle as the dump? who
# tipped it (seller / buyer / a third account = relay or bundler)? -> the share of near-dump buys that are bundled with the dump.
# usage: python3 -I i16_jito_other.py CLASSES.json OUT.json
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import jito_api as J
C = json.load(open(sys.argv[1])); outp = sys.argv[2]
def rot(r): return r["cup"] == 500 and r["cul"] == 200000 and not r["tsv"]
ev = [r for r in C if r["cls"] == "R" and not rot(r) and r["gap"] <= 3 and r["client"] in ("jito", "bam", "harmonic")]
print(len(ev), "events", flush=True)
res = []
for k, r in enumerate(ev):
    bd = J.bundle_of(r["dsig"]); bb = J.bundle_of(r["sig"])
    same = isinstance(bd, dict) and isinstance(bb, dict) and bd.get("bundle_id") == bb.get("bundle_id")
    tip = (bb.get("tippers") if isinstance(bb, dict) else None) or []
    who = None
    if same: who = "seller" if r["dumper"] in tip else ("buyer" if r["u"] in tip else "third:" + ",".join(t[:8] for t in tip))
    res.append(dict(u=r["u"], gap=r["gap"], client=r["client"], dumper=r["dumper"], sig=r["sig"], dsig=r["dsig"], same=same, who=who,
                    n=len(bb.get("txs") or []) if isinstance(bb, dict) else 0, buy_in_bundle=isinstance(bb, dict), dump_in_bundle=isinstance(bd, dict),
                    bundle=bb.get("bundle_id") if isinstance(bb, dict) else None))
    if k % 50 == 49: J.save(); print(k + 1, "done", flush=True)
J.save()
json.dump(res, open(outp, "w"), indent=1)
for g in (1, 2, 3):
    rows = [x for x in res if x["gap"] == g]
    w = collections.Counter((x["who"] or "")[:5] for x in rows if x["same"])
    print(f"gap {g}: {len(rows)} OTHER buys | SAME bundle as the dump {sum(1 for x in rows if x['same'])} ({100 * sum(1 for x in rows if x['same']) / max(len(rows), 1):.0f}%) tipped by {dict(w)} | "
          f"buy in some bundle {sum(1 for x in rows if x['buy_in_bundle'])} | dump in a bundle {sum(1 for x in rows if x['dump_in_bundle'])}")
third = collections.Counter(x["who"] for x in res if x["same"] and x["who"].startswith("third"))
print("third-party tippers:", third.most_common(10))
print("jito calls", J.calls())
