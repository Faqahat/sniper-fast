#!/usr/bin/env python3
# Summary of v2_out/fresh_cls.jsonl (claim 1 fresh-sample check). Local only.
import json, collections
res = [json.loads(l) for l in open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/fresh_cls.jsonl")]
ok = [r for r in res if r["ok"]]
print("rows", len(res), "fetched", len(ok), "failed fetch", len(res) - len(ok))
for grp in ("A", "B"):
    g = [r for r in ok if r["grp"] == grp]
    lab = (lambda r: bool(r["flag"])) if grp == "A" else (lambda r: r["truth"] == "top")
    print(f"\n== sample {grp}: n {len(g)} | trigger event found (seller+SOL exact) {sum(r['trig_exact'] > 0 for r in g)} | tx err {sum(1 for r in g if r['err'])}"
          f" | direct (top-level pump ix on mint) {sum(r['direct_any'] for r in g)} | direct with the seller in that ix {sum(r['direct_seller'] for r in g)}")
    cm = collections.Counter((r["direct_seller"], lab(r)) for r in g)
    print("   (mine direct, label direct):", dict(cm), "| label None:", sum(1 for r in g if (r["flag"] if grp == "A" else r["truth"]) is None))
    agree = sum(1 for r in g if r["direct_seller"] == lab(r))
    print(f"   agreement {agree}/{len(g)} = {agree / max(len(g), 1):.1%}; direct share mine {sum(r['direct_seller'] for r in g) / len(g):.1%} label {sum(lab(r) for r in g) / len(g):.1%}")
    print("   discriminators of direct:", collections.Counter(d for r in g if r["direct_seller"] for d in r["discs"]).most_common())
    print("   a8 == tokens sold (direct):", dict(collections.Counter(r["a8_eq_tok"] for r in g if r["direct_seller"])))
    print("   mint via ALT (direct):", sum(r["mint_in_alt"] for r in g if r["direct_seller"]), "| seller via ALT:", sum(r["seller_in_alt"] for r in g if r["direct_seller"]),
          "| seller is the signer:", sum(r["seller_signs"] for r in g if r["direct_seller"]))
    print("   routers (routed):", collections.Counter((r["router"] or "?")[:10] for r in g if not r["direct_seller"]).most_common(8))
    for r in g:
        if r["direct_seller"] != lab(r) or r["direct_any"] != r["direct_seller"]:
            print("   CASE", r["sig"][:24], "mine", r["direct_seller"], "any", r["direct_any"], "label", r["flag"], r["truth"], "discs", r["discs"], "outer", [o[:8] for o in r["outer"]])
