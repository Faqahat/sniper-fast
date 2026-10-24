import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
from ana_fwd import rows, table
LS = json.load(open("lists_cut1709.json"))
def inl(w, k): return lambda r: LS.get(w, {}).get(r["signer"], 0) >= k
for w in ("9Sh2fd", "DGmspi", "D24ipY"):
    for k in (1, 3):
        R = table(f"LIST {w} (deployers it attempted >= {k}x before the window): ALL their launches", inl(w, k), cfgs=("L75", "L35", "L0"), top=4)
        print(f"      of these, {w} attempted {sum(1 for r in R if w in r['att'])} ({sum(1 for r in R if w in r['att']) / max(1, len(R)):.0%})")
U = lambda r: any(LS.get(w, {}).get(r["signer"], 0) >= 1 for w in ("9Sh2fd", "DGmspi"))
table("LIST union 9Sh2fd+DGmspi (>=1)", U, cfgs=("L75", "L60", "L35"), top=6)
table("LIST union 9Sh2fd+DGmspi (>=1) AND glued bundle >= 2 txs", lambda r: U(r) and r["glued_n"] >= 2, cfgs=("L75", "L60", "L35"), top=6)
table("LIST union 9Sh2fd+DGmspi (>=1) AND dev buy 0.5-5 SOL", lambda r: U(r) and 0.5 <= r["dev_buy"] <= 5, cfgs=("L75", "L60", "L35"), top=6)
