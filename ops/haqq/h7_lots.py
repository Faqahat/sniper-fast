#!/usr/bin/env python3
# haqq SELL study, step 7: haqq trades LOTS. Each buy is its own lot; each sell exactly equals one lot's remaining tokens (full)
# or half a lot (two-piece exit). Match every sell to its lot (exact token amounts, +-2 raw units) -> lots.json
import sys, json, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_load
eps = h_load.load(with_ticks=False)
lots = []; unmatched = 0; cnt = collections.Counter()
for ei, e in enumerate(eps):
    L = [dict(ei=ei, bi=n, b=b, rem=b["tok"], sells=[]) for n, b in enumerate(e["buys"])]
    ev = sorted([("b", n, b) for n, b in enumerate(e["buys"])] + [("s", n, x) for n, x in enumerate(e["sells"])], key=lambda z: (z[2]["s"], z[2]["i"]))
    live = []
    for kind, n, x in ev:
        if kind == "b": live.append(L[n]); continue
        t = x["tok"]; hit = None
        for l in live:                                   # full remaining of one lot
            if abs(l["rem"] - t) <= 2: hit = (l, "full"); break
        if hit is None:
            for l in live:                               # half of the lot (first piece of a two-piece exit)
                if abs(l["b"]["tok"] / 2 - t) <= 2 and abs(l["rem"] - l["b"]["tok"]) <= 2: hit = (l, "half"); break
        if hit is None:
            unmatched += 1; cnt["unmatched"] += 1
            # fall back: take from the oldest live lots (FIFO)
            rem = t
            for l in list(live):
                q = min(rem, l["rem"]); 
                if q <= 0: continue
                l["sells"].append(dict(x, part=q / l["b"]["tok"], how="fifo")); l["rem"] -= q; rem -= q
                if l["rem"] <= 2: live.remove(l)
                if rem <= 2: break
            continue
        l, how = hit; cnt[how] += 1
        l["sells"].append(dict(x, part=t / l["b"]["tok"], how=how)); l["rem"] -= t
        if l["rem"] <= 2: live.remove(l)
    for l in L:
        b = l["b"]; ss = l["sells"]
        cost = b["cost"]; got = sum(x["proceeds"] * min(1.0, x["part"] * b["tok"] / max(x["tok"], 1)) for x in ss)
        lots.append(dict(ei=ei, m=e["m"], run=e["run"], bi=l["bi"], nlots=len(L), closed=l["rem"] <= 2, censored=e["censored"], brk=e["brk"], gaps=e["gaps"],
                         buy=b, sells=[dict(s=x["s"], i=x["i"], a=x["a"], part=x["part"], how=x["how"], proceeds=x["proceeds"] * min(1.0, x["part"] * b["tok"] / max(x["tok"], 1)), sol=x["sol"]) for x in ss],
                         cost=cost, got=got, n_sells=len(ss), split=any(x["how"] == "half" for x in ss)))
json.dump(lots, open(f"{H.OUT}/lots.json", "w"))
print("sell matching:", dict(cnt), "| lots", len(lots), "closed", sum(l["closed"] for l in lots))
C = [l for l in lots if l["closed"] and not l["censored"] and not l["brk"]]
def q(v, ps=(10, 25, 50, 75, 90)):
    a = np.percentile(v, ps); return " / ".join(f"{x:.0f}" for x in a)
def hold(l): return l["sells"][-1]["s"] - l["buy"]["s"]
def first(l): return l["sells"][0]["s"] - l["buy"]["s"]
print(f"clean closed lots {len(C)}: split into halves {np.mean([l['split'] for l in C]):.0%}")
for lab, sel in (("all", C), ("first lot of episode", [l for l in C if l["bi"] == 0]), ("add lots", [l for l in C if l["bi"] > 0]),
                 ("dip", [l for l in C if l["buy"]["dip"]]), ("non-dip", [l for l in C if not l["buy"]["dip"]]),
                 ("size 0.01", [l for l in C if l["buy"]["sol"] < 0.05]), ("0.05-0.35", [l for l in C if 0.05 <= l["buy"]["sol"] < 0.35]),
                 ("0.35-0.6", [l for l in C if 0.35 <= l["buy"]["sol"] < 0.6]), (">=0.6", [l for l in C if l["buy"]["sol"] >= 0.6]),
                 ("age<5s", [l for l in C if l["buy"]["age"] < 5000]), ("age 5-30s", [l for l in C if 5000 <= l["buy"]["age"] < 30000]), ("age>=30s", [l for l in C if l["buy"]["age"] >= 30000])):
    pnl = [l["got"] - l["cost"] for l in sel]
    print(f"  {lab:20s} n {len(sel):5d} split {np.mean([l['split'] for l in sel]):4.0%} | hold slots (last piece) {q([hold(l) for l in sel])} | first piece {q([first(l) for l in sel])} | P&L {sum(pnl):+7.2f} ({np.mean(pnl) * 1000:+.1f} mSOL) win {np.mean([x > 0 for x in pnl]):.0%}")
hc = collections.Counter(min(hold(l), 120) for l in C if not l["split"])
print("unsplit lot hold histogram (slots: count), 0..120:", " ".join(f"{k}:{hc[k]}" for k in range(0, 121)))
big = [l for l in C if l["buy"]["sol"] >= 0.6]
hb = collections.Counter(hold(l) for l in big); print("size>=0.6 most common holds:", hb.most_common(12))
