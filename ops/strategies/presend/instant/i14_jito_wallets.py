#!/usr/bin/env python3
# INSTANT-BOTS study, step 14 (read-only, Jito explorer API, cached): for chosen wallets, EVERY fast follow at gap <= MAXGAP on
# Jito/BAM/Harmonic leaders: is the buy in the SAME Jito bundle as the dump, who tipped that bundle (the seller, the buyer, or a
# relay's tip account), and the bundle size.
# usage: python3 -I i14_jito_wallets.py CLASSES.json OUT.json MAXGAP PREFIX [PREFIX ...]
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import jito_api as J
C = json.load(open(sys.argv[1])); outp = sys.argv[2]; G = int(sys.argv[3]); P = sys.argv[4:]
res = []
for p in P:
    ev = [r for r in C if r["u"].startswith(p) and r["gap"] <= G and r["client"] in ("jito", "bam", "harmonic")]
    for r in ev:
        bd = J.bundle_of(r["dsig"]); bb = J.bundle_of(r["sig"])
        same = isinstance(bd, dict) and isinstance(bb, dict) and bd.get("bundle_id") == bb.get("bundle_id")
        tip = (bb.get("tippers") if isinstance(bb, dict) else None) or []
        who = None
        if same: who = "seller" if r["dumper"] in tip else ("buyer" if r["u"] in tip else "other:" + ",".join(t[:8] for t in tip))
        res.append(dict(p=p, u=r["u"], gap=r["gap"], client=r["client"], dumper=r["dumper"], sig=r["sig"], dsig=r["dsig"], same=same, who=who,
                        n=len(bb.get("txs") or []) if isinstance(bb, dict) else 0, buy_in_bundle=isinstance(bb, dict), dump_in_bundle=isinstance(bd, dict)))
    J.save()
    rows = [x for x in res if x["p"] == p]
    print(f"{p}: {len(rows)} follows gap<={G} on jito/bam/harmonic | SAME bundle {sum(1 for x in rows if x['same'])} (tipped by {collections.Counter(x['who'] for x in rows if x['same'])}) | "
          f"buy in some bundle {sum(1 for x in rows if x['buy_in_bundle'])} | dump in a bundle {sum(1 for x in rows if x['dump_in_bundle'])}", flush=True)
json.dump(res, open(outp, "w"), indent=1)
print("jito calls", J.calls())
