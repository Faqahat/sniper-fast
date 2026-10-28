"""MAIN-SESSION independent check of the bot-code claim, from the raw txs (exec/ext), own code.
For each haqq SELL on a mint: is there an earlier haqq BUY on the same mint with the same CU-price code (mod 1000)?
Control: the same test with codes shuffled within each mint."""
import json, glob, collections, random
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
ev = collections.defaultdict(list)
for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl"):
    for l in open(f):
        if H not in l: continue
        try: d = json.loads(l)
        except Exception: continue
        if d.get("err") is not None or not d.get("signers") or d["signers"][0] != H or not d.get("mints"): continue
        ix = d.get("ixn") or []
        k = "B" if any(x.startswith("Buy") for x in ix) else "S" if any(x.startswith("Sell") for x in ix) else None
        if k and d.get("cup"): ev[d["mints"][0]].append((d["s"], d["i"], k, d["cup"] % 1000))
def score(ev, shuffle=False):
    ok = tot = 0; per = collections.Counter(); hit = collections.Counter()
    for m, v in ev.items():
        v = sorted(v)
        if shuffle:
            codes = [c for *_, c in v]; random.shuffle(codes); v = [(a, b, k, c) for (a, b, k, _), c in zip(v, codes)]
        bought = set()
        for s, i, k, c in v:
            if k == "B": bought.add(c)
            else:
                tot += 1; per[c] += 1
                if c in bought: ok += 1; hit[c] += 1
    return ok, tot, per, hit
random.seed(1)
ok, tot, per, hit = score(ev)
ok2, tot2, _, _ = score(ev, True)
nb = sum(1 for v in ev.values() for x in v if x[2] == "B")
print(f"mints {len(ev)}, buys {nb}, sells {tot}")
print(f"sells whose code matches an earlier buy's code on the same mint: {100*ok/tot:.2f}%  (shuffled control {100*ok2/tot2:.2f}%)")
for c, n in per.most_common(10): print(f"  code {c}: sells {n}, matched {100*hit[c]/n:.1f}%")
multi = {m: v for m, v in ev.items() if len({c for *_, c in v}) >= 2}
ok, tot, _, _ = score(multi); ok2, tot2, _, _ = score(multi, True)
print(f"MULTI-CODE mints only ({len(multi)}): matched {100*ok/tot:.2f}% of {tot} sells (shuffled control {100*ok2/tot2:.2f}%)")
