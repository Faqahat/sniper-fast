#!/usr/bin/env python3
# haqq SELL study, step 6: descriptive tables (ledger P&L, entries, sell structure, what precedes sells).
import sys, json, collections, statistics as st
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_load
eps = h_load.load(with_ticks=False)
WTN = {0: "other", 1: "creator", 2: "bundle", 3: "sniper", 4: "cohort", 5: "hk", 6: "dyx", 7: "ours", 8: "haqq"}
def q(v, ps=(10, 25, 50, 75, 90)):
    if not v: return "-"
    a = np.percentile(v, ps); return " / ".join(f"{x:.0f}" if abs(x) >= 10 else f"{x:.2f}" for x in a)
print(f"episodes {len(eps)}; closed {sum(e['closed'] for e in eps)}; censored {sum(e['censored'] for e in eps)}; mayhem {sum(e['mayhem'] for e in eps)}; "
      f"with reserve breaks {sum(1 for e in eps if e['brk'])}; with gap slots {sum(1 for e in eps if e['gaps'])}")
# P&L by run
for run in ("R1", "R2", "R3", "R4"):
    E = [e for e in eps if e["run"] == run]
    t0 = min(e["bt0"] for e in E); t1 = max(e["bt_end"] for e in E); h = (t1 - t0) / 3600
    tot = sum(e["pnl"] for e in E); clean = [e for e in E if not e["censored"] and not e["brk"] and not e["mayhem"]]
    print(f"{run} {H.pkt(t0)} -> {H.pkt(t1)} ({h:.1f} h): episodes {len(E)}, P&L {tot:+.2f} SOL ({tot / h * 24:+.1f}/day) | clean {len(clean)} P&L {sum(e['pnl'] for e in clean):+.2f} | "
          f"buys {sum(len(e['buys']) for e in E)} sells {sum(len(e['sells']) for e in E)} | win {np.mean([e['pnl'] > 0 for e in E]):.0%}")
# entries
B = [b for e in eps for b in e["buys"]]
first = [e["buys"][0] for e in eps]; adds = [b for e in eps for b in e["buys"][1:]]
print(f"\nbuys {len(B)}: first buys {len(first)} (dip {np.mean([b['dip'] for b in first]):.0%}), adds {len(adds)} (dip {np.mean([b['dip'] for b in adds]):.0%})")
d = [b["delay"] for b in B if b["dip"]]
print(f"dip-buy delay after the >=1 SOL sell (block-position proxy, ms): p10/25/50/75/90 {q(d)}; same slot {np.mean([b['trig_ds'] == 0 for b in B if b['dip']]):.0%}")
print("dip trigger wallet types:", collections.Counter(WTN[b["trig_wt"]] for b in B if b["dip"]).most_common())
nd = [b for b in first if not b["dip"]]
print("non-dip first buys: prev trade buy?", collections.Counter(b["prev_buy"] for b in nd).most_common(), "prev wt", collections.Counter(WTN.get(b["prev_wt"]) for b in nd).most_common(6))
print("  prev trade size (SOL) p10..p90:", q([b["prev_sol"] for b in nd if b["prev_sol"] is not None]), " delay ms:", q([b["delay"] for b in nd if b["delay"] is not None]))
print("first-buy token age (s) p10..p90:", q([b["age"] / 1000 for b in first]), "| first-buy size:", collections.Counter(round(b["sol"], 2) for b in first).most_common(10))
print("add sizes:", collections.Counter(round(b["sol"], 2) for b in adds).most_common(10))
# sells
C = [e for e in eps if e["closed"] and not e["censored"] and not e["mayhem"]]
print(f"\nclosed clean-ish episodes {len(C)}")
ns = collections.Counter(min(len(e["sells"]), 5) for e in C); nb = collections.Counter(min(len(e["buys"]), 5) for e in C)
print("sells per episode:", sorted(ns.items()), "| buys per episode:", sorted(nb.items()))
print("crosstab buys x sells (rows buys 1..4+, cols sells 1..4+):")
for b_ in (1, 2, 3, 4):
    row = [sum(1 for e in C if min(len(e["buys"]), 4) == b_ and min(len(e["sells"]), 4) == s_) for s_ in (1, 2, 3, 4)]
    print(f"   buys {b_}{'+' if b_ == 4 else ' '}: {row}")
# timing of first sell after first buy (slots) by entry type / size / age
def fs_slots(e): return e["sells"][0]["s"] - e["buys"][0]["s"]
def last_slots(e): return e["sells"][-1]["s"] - e["buys"][0]["s"]
print("\nfirst sell, slots after the first buy: p10/25/50/75/90")
for lab, sel in (("all", C), ("1 buy 1 sell", [e for e in C if len(e["buys"]) == 1 and len(e["sells"]) == 1]),
                 ("dip entry", [e for e in C if e["buys"][0]["dip"]]), ("non-dip entry", [e for e in C if not e["buys"][0]["dip"]]),
                 ("0.01 SOL first buy", [e for e in C if e["buys"][0]["sol"] < 0.05]), ("0.05-0.35", [e for e in C if 0.05 <= e["buys"][0]["sol"] < 0.35]),
                 ("0.35-0.6", [e for e in C if 0.35 <= e["buys"][0]["sol"] < 0.6]), (">=0.6", [e for e in C if e["buys"][0]["sol"] >= 0.6]),
                 ("age<5s", [e for e in C if e["buys"][0]["age"] < 5000]), ("age 5-30s", [e for e in C if 5000 <= e["buys"][0]["age"] < 30000]),
                 ("age 30s-5m", [e for e in C if 30000 <= e["buys"][0]["age"] < 300000]), ("age>=5m", [e for e in C if e["buys"][0]["age"] >= 300000])):
    if sel: print(f"   {lab:18s} n {len(sel):5d}: first {q([fs_slots(e) for e in sel])} | last {q([last_slots(e) for e in sel])} | P&L {sum(e['pnl'] for e in sel):+7.2f} ({np.mean([e['pnl'] for e in sel]) * 1000:+.1f} mSOL/ep) win {np.mean([e['pnl'] > 0 for e in sel]):.0%}")
# partial fractions
fr = []
for e in C:
    held = 0.0
    for kk in sorted([("b", b) for b in e["buys"]] + [("s", x) for x in e["sells"]], key=lambda z: (z[1]["s"], z[1]["i"])):
        if kk[0] == "b": held += kk[1]["tok"]
        else:
            fr.append((kk[1]["tok"] / held if held > 0 else None)); held -= kk[1]["tok"]
pf = [x for x in fr if x is not None and x < 0.999]
print(f"\npartial sells {len(pf)} of {len(fr)} sells: fraction of holding p10/25/50/75/90 {q([x * 100 for x in pf])} %")
print("   histogram (5% bins):", sorted(collections.Counter(int(x * 20) * 5 for x in pf).items()))
