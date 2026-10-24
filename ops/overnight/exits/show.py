#!/usr/bin/env python3
# READ-ONLY: print the market timeline of one aligned token (own trades, dev, group, others >= min SOL) from buy to final sell (+ tail).
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
A = {(a["w"], a["mint"]): a for a in json.load(open(f"{EXITS}/align.json")) if not a["coverage"]["missing"]}
def show(w, m, minsol=0.25, tail=6):
    a = A[(w, m)]; W = WALLETS[w]; tr, xs = trades_of(m); dev = {a["signer"], a["creator"]}
    kb = a["buy_pos_in_path"]; entry = a["entry_px"]; kl = a["sells"][-1]["k"] if a["sells"] else kb
    grp_slot = a["create_slot"]
    print(f"== {w} {m} dev {a['signer'][:6]}/{a['creator'][:6]} buy {a['buy_sol']:.2f} pnl {a['pnl']:+.3f} | create s{a['create_slot']} i{a['create_idx']} | buy +{a['buy_slot']-a['create_slot']} i{a['buy_idx']}")
    hold = 0.0; peak = 0
    for k in range(0, min(len(tr), kl + tail)):
        t = tr[k]
        if t["user"] == W: hold += t["tok"] if t["buy"] else -t["tok"]
        if k < kb - 3: continue
        who = "ME " if t["user"] == W else ("DEV" if t["user"] in dev else ("cs " if t["s"] == grp_slot and t["buy"] else "   "))
        mult = (t["vsol"] / t["vtok"]) / entry
        if k >= kb and t["user"] != W: peak = max(peak, mult)
        if who.strip() or t["sol"] >= minsol * 1e9:
            frac = ""
            if t["user"] == W and not t["buy"]: frac = f"frac {t['tok'] / (hold + t['tok']):.2f}"
            print(f"   +{t['s'] - a['buy_slot']:4d} i{t['i']:4d} {who} {'B' if t['buy'] else 'S'} {t['sol'] / 1e9:6.2f}  m_after {mult:5.2f} pk {peak:5.2f} {frac}")
if __name__ == "__main__":
    for x in sys.argv[2:]:
        for (w, m) in A:
            if w == sys.argv[1] and m.startswith(x): show(w, m)
