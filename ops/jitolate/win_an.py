# READ-ONLY summary of winners.py output: how often does any outsider land <= 25 txs after the creator's glued run,
# who, with what tip / priority / bundle, by leader client; and by create position in the slot.
import sys, json, collections as C, statistics as st
R = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
def q(v, p): v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None
def cl(c):
    return {"AgaveBam": "bam", "FireBam": "bam", "JitoLabs": "jito", "HarmonicAgave": "harmonic", "HarmonicFiredancer": "harmonic", "Firedancer": "fd", "Frankendancer": "fd"}.get(c, c)
print(f"launches {len(R)}  (glued run present: {sum(1 for r in R if r['glued']>0)})")
by = C.defaultdict(list)
for r in R: by[cl(r["client"])].append(r)
W = []
for k, g in sorted(by.items(), key=lambda x: -len(x[1])):
    hit = [r for r in g if any(w["ok"] and w["d"] <= 25 for w in r["out"])]
    print(f"  {k:10} n={len(g):3}  launches with an outsider ok at d<=25: {len(hit)} ({len(hit)/len(g):.0%})")
for r in R:
    for w in r["out"]:
        if w["ok"] and w["d"] <= 25:
            w["client"] = cl(r["client"]); w["frac"] = r["frac"]; w["ms"] = w["j"] / r["n"] * 203.5; W.append(w)
print("\nwinners d<=25 (ok):", len(W))
for k in ["bam", "jito", "harmonic", "fd"]:
    g = [w for w in W if w["client"] == k]
    if not g: continue
    sender = C.Counter(("+".join(sorted({t[0] for t in w["tips"]})) or "notip") for w in g)
    inb = [w for w in g if w.get("bundle")]
    multi = [w for w in inb if not w["bundle"].get("same_as_create") and (w["bundle"].get("ntx") or 0) > 1]
    jt = [sum(t[1] for t in w["tips"] if t[0] == "jito") for w in g]
    jt = [x for x in jt if x]
    cu = [w["cu_price"] or 0 for w in g]
    prio = [max(0, (w["fee"] or 0) - 5000) for w in g]
    payers = C.Counter(w["payer"][:6] for w in g).most_common(5)
    print(f"  {k:9} n={len(g):3} d p50={q([w['d'] for w in g],.5)} | in Jito bundle {len(inb)} (with create {sum(1 for w in inb if w['bundle'].get('same_as_create'))}, multi-tx own {len(multi)}) | "
          f"jito tip p25/p50/p75 {q(jt,.25)}/{q(jt,.5)}/{q(jt,.75)} (n={len(jt)}) | cu_price p50 {q(cu,.5)} p75 {q(cu,.75)} | prio lamports p50 {q(prio,.5)}")
    print(f"            senders {dict(sender.most_common(6))}")
    print(f"            top payers {payers}  ms after create p25/p50/p75 {q([w['ms'] for w in g],.25):.1f}/{q([w['ms'] for w in g],.5):.1f}/{q([w['ms'] for w in g],.75):.1f}")
    bs = C.Counter(w["bundle"]["ntx"] for w in inb if not w["bundle"].get("same_as_create"))
    print(f"            own-bundle sizes {dict(bs)}  sol p50 {q([w['sol'] for w in g],.5)}")
# create position in slot vs any outsider in S at d<=25 / any at all
print("\nby create position in the slot (frac of non-vote txs):")
for lo, hi in [(0, .33), (.33, .66), (.66, 1.01)]:
    g = [r for r in R if lo <= r["frac"] < hi]
    a = sum(1 for r in g if any(w["ok"] and w["d"] <= 25 for w in r["out"]))
    print(f"  {lo:.2f}-{hi:.2f}: n={len(g):3}  outsider d<=25: {a} ({a/max(1,len(g)):.0%})")
# repeat winners: are they always-fast (launch-tool) wallets?
pc = C.Counter(w["payer"] for w in W)
print("\nrepeat payers among winners:", sum(1 for p, n in pc.items() if n >= 2), "of", len(pc), " top:", [(p[:6], n) for p, n in pc.most_common(8)])
