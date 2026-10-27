#!/usr/bin/env python3
# INSTANT-BOTS study, step 10 (read-only): Jito bundle evidence on a stratified sample of fast follows (i9 classes), Jito and BAM
# leaders (Harmonic / FD as a control: their bundles are not in the Jito explorer). Per event: is the dump in a Jito bundle, is the
# follow in one, is it the SAME bundle (= dump + buy executed as one bundle), the bundle's size / tipper / tip.
# usage: python3 -I i10_jito_sample.py CLASSES.json OUT.json [seed]
import sys, json, random, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import jito_api as J
C = json.load(open(sys.argv[1])); outp = sys.argv[2]; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 7)
def fam969(r): return r["cup"] == 500 and r["cul"] == 200000 and not r["tsv"]
STRATA = [
    ("rotation-969 jito", lambda r: fam969(r) and r["client"] == "jito", 20),
    ("rotation-969 bam", lambda r: fam969(r) and r["client"] == "bam", 12),
    ("rotation-969 harmonic", lambda r: fam969(r) and r["client"] == "harmonic", 4),
    ("B same-prog jito/bam", lambda r: r["cls"] == "B" and r["client"] in ("jito", "bam"), 12),
    ("R gap1-5 other jito/bam", lambda r: r["cls"] == "R" and not fam969(r) and r["gap"] <= 5 and r["client"] in ("jito", "bam"), 30),
    ("R gap6-40 jito/bam", lambda r: r["cls"] == "R" and not fam969(r) and r["gap"] >= 6 and r["client"] in ("jito", "bam"), 24),
    ("P gap<=10 jito/bam", lambda r: r["cls"] == "P" and r["gap"] <= 10 and r["client"] in ("jito", "bam"), 30),
]
res = []
for lab, f, n in STRATA:
    pool = [r for r in C if f(r)]
    smp = random.sample(pool, min(n, len(pool)))
    for r in smp:
        bd = J.bundle_of(r["dsig"]); bb = J.bundle_of(r["sig"])
        same = isinstance(bd, dict) and isinstance(bb, dict) and bd.get("bundle_id") == bb.get("bundle_id")
        res.append(dict(stratum=lab, u=r["u"], dumper=r["dumper"], gap=r["gap"], client=r["client"], cls=r["cls"], s=r["s"], sig=r["sig"], dsig=r["dsig"],
                        dump_bundle=bd, buy_bundle=bb, same=same))
    J.save()
    rows = [x for x in res if x["stratum"] == lab]
    nb = lambda b: isinstance(b, dict)
    print(f"{lab:26s} n {len(rows):3d} | dump in a bundle {sum(1 for x in rows if nb(x['dump_bundle'])):3d} | buy in a bundle {sum(1 for x in rows if nb(x['buy_bundle'])):3d} | "
          f"SAME bundle {sum(1 for x in rows if x['same']):3d} | buy bundle sizes {collections.Counter(len(x['buy_bundle'].get('txs') or []) for x in rows if nb(x['buy_bundle']))} | "
          f"ERR {sum(1 for x in rows if 'ERR' in (x['dump_bundle'], x['buy_bundle']))}", flush=True)
json.dump(res, open(outp, "w"), indent=1)
print("jito calls", J.calls())
