#!/usr/bin/env python3
"""TUNE t8: age-1 skip. (1) its paper per run and r42's biggest paper winners; (2) is the paper honest for young tokens? live T2 trades
vs the shadow's paper on the SAME trigger (row c scaled to the live size), by token age at the trigger: live - paper per pair."""
import sys, pickle, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/it/sniper-data/filters3/tune/pos_all.pkl", "rb"))
S = pickle.load(open("/home/it/sniper-data/filters3/tune/skips_all.pkl", "rb"))
ya = [s for s in S if s["why"] == "young_age" and s["run"] == "r42" and s["paper"] is not None]
ya.sort(key=lambda s: -s["paper"])
print("r42 age-1 paper: top 8 winners: " + ", ".join(f"{T.pkt(s['t']).strftime('%m-%d %H:%M')} {s['mint'][:6]} {s['paper']:+.3f}" for s in ya[:8]))
print(f"  r42 age-1 paper total {sum(s['paper'] for s in ya):+.3f}; without its 5 biggest winners {sum(s['paper'] for s in ya[5:]):+.3f}; without 5 biggest winners AND losers {sum(s['paper'] for s in ya[5:-5]):+.3f}")
# paper vs live by age
def bucket(a): return "2" if a == 2 else "3-5" if a <= 5 else "6-20" if a <= 20 else "21-100" if a <= 100 else ">100"
G = collections.defaultdict(lambda: collections.defaultdict(list))
for r in P:
    if r["kind"] != "t2": continue
    D = T.load(r["run"]); sig = r["trig"].get("sig"); sa = D["sh_arm"].get(sig)
    live_size = r["spend"]
    if not sa or sa["w"] not in D["sh_exit"]: G[r["per"]][bucket(r["trig"].get("age_slots") or 0)].append((r["pnl"], None)); continue
    sf = D["sh_fill"].get(sa["w"]); p = D["sh_exit"][sa["w"]]["net_cheap"] * (live_size / sf["sol_in"] if sf and sf.get("sol_in") else 1)
    G[r["per"]][bucket(r["trig"].get("age_slots") or 0)].append((r["pnl"], p))
print("\nlive T2 trades by token age at trigger: n, live mean mSOL, paired n (shadow filled too), live - paper per pair mSOL, live-only fills (shadow did not fill)")
for per in ("DEV", "VAL", "HOLD"):
    for b in ("2", "3-5", "6-20", "21-100", ">100"):
        x = G[per][b]; pr = [(l, p) for l, p in x if p is not None]
        if not x: continue
        print(f"  {per:4s} age {b:6s} n {len(x):4d} live {1000*sum(l for l, _ in x)/len(x):+6.1f} | pairs {len(pr):4d} live-paper {1000*sum(l-p for l, p in pr)/max(1,len(pr)):+6.1f} (paper {1000*sum(p for _, p in pr)/max(1,len(pr)):+6.1f}) | live-only {len(x)-len(pr)} {1000*sum(l for l, p in x if p is None)/max(1,len(x)-len(pr)):+6.1f}")
# age-1 paper per period by kind of whale (seller_is_whale in shadow fill)
for per in ("DEV", "VAL", "HOLD"):
    v = [s for s in S if s["why"] == "young_age" and s["per"] == per and s["paper"] is not None]
    print(f"age-1 {per}: scored {len(v)} paper {sum(s['paper'] for s in v):+.3f} | whale's own dump filled it: {sum(1 for s in v if (s['sh_fill'] or {}).get('whale'))} {sum(s['paper'] for s in v if (s['sh_fill'] or {}).get('whale')):+.3f}"
          f" | other seller: {sum(s['paper'] for s in v if not (s['sh_fill'] or {}).get('whale')):+.3f}")
