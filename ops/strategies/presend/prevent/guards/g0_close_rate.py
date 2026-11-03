#!/usr/bin/env python3
"""GUARDS step 0 [MEASURED, read-only on raw recorder chunks]: how often does a big pump.fun sell (>= 3% of supply, single tx)
sell the seller's WHOLE balance, and how often does the same tx CLOSE the seller's token account (ixn has CloseAccount)?
Why: a Lighthouse token-account assertion on a CLOSED account cannot be read (it fails), so a guard 'whale balance <= Z' would also
block fills right after the whale's own full dump when the whale closes its account.
usage: g0_close_rate.py OUT.json CHUNK.jsonl.gz [...]"""
import sys, gzip, json, collections
SUP = 1e15
out = collections.Counter(); ex = []
for fn in sys.argv[2:]:
    with gzip.open(fn, "rt") as f:
        for line in f:
            if '"Sell' not in line: continue
            r = json.loads(line)
            if r.get("err") is not None: continue
            ixn = r.get("ixn") or []
            if not any(x.startswith("Sell") for x in ixn): continue
            sg = (r.get("signers") or ["?"])[0]
            for m, owner, pre, post in (r.get("tb") or []):
                if owner != sg or pre is None or post is None: continue
                d = pre - post
                if d < 0.03 * SUP: continue
                full = post == 0
                close = "CloseAccount" in ixn
                b = "6pct" if d >= 0.06 * SUP else "3pct"
                out[(b, "n")] += 1; out[(b, "full")] += full; out[(b, "close")] += close; out[(b, "full_close")] += (full and close)
                out[(b, "partial_close")] += ((not full) and close)
out = {f"{a}|{b}": v for (a, b), v in sorted(out.items())}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(out)
