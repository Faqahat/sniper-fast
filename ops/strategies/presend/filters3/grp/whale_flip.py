#!/usr/bin/env python3
"""WHALE FLIP (owner 11-03 on 6ddGRNQD): do our T2 trades lose when the dump that fills us is the TRIGGER WHALE selling its own buy?
Join: live T2 arm (trig.sig) -> the shadow's presend_arm on the same trigger (sig -> w) -> the shadow's row-c presend_fill
"seller_is_whale" (the crossing dump's seller is the trigger whale) and the dump's ms after the trigger (d_ms). Live realized P&L per
window. Read-only. usage: whale_flip.py RUN.presend.jsonl [...]"""
import sys, json, collections
G = collections.defaultdict(lambda: collections.defaultdict(list))
for fn in sys.argv[1:]:
    name = fn.split("/")[-1].split(".")[0]
    sh_w, sh_f, lv, real = {}, {}, {}, collections.Counter()
    for l in open(fn, errors="replace"):
        if '"ev":"presend_' not in l: continue
        if not any(k in l for k in ('"ev":"presend_arm"', '"ev":"presend_fill"', '"ev":"presend_live_arm"', '"ev":"presend_live_realized"')): continue
        d = json.loads(l); e = d["ev"]
        if e == "presend_arm": sh_w[d["sig"]] = d.get("w")
        elif e == "presend_fill" and d.get("row", "c") == "c": sh_f.setdefault(d.get("w"), d)
        elif e == "presend_live_arm" and d.get("kind", "t2") == "t2": lv[d["w"]] = d["trig"]["sig"]
        elif e == "presend_live_realized": real[d["w"]] += d["pnl"] / 1e9
    for w, sig in lv.items():
        if w not in real: continue
        f = sh_f.get(sh_w.get(sig))
        k = "no shadow fill" if f is None else ("FLIP: whale's own dump" if f.get("seller_is_whale") else "dump by another wallet")
        G[name][k].append(real[w]); G["ALL"][k].append(real[w])
for name in list(G):
    print(name + ": " + " | ".join(f"{k} n {len(v)} {sum(v):+.3f} ({sum(v) / len(v) * 1000:+.1f} mSOL, win {sum(x > 0 for x in v) / len(v):.0%}, w/o top5 {sum(sorted(v)[:-5]):+.3f})" for k, v in sorted(G[name].items()) if v))
