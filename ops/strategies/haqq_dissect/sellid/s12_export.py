#!/usr/bin/env python3
"""SELLID step 12 (read-only): Task-1 deliverable as a flat file: every 247/248 first sell of a lot with each outside trade in the
0..3 slots before it (wallet, side, SOL, slot gap, tx-index gap if same slot, ms before the sell), plus the lot's hold and P&L.
Also one example of the 4-wallet buy cluster (2fg5QD1e/suqh5sHt/7NAd2EpY/FxN3VZ4B) right before a sell.
Out: sellid/s12_presell.tsv.gz, s12_cluster_example.json"""
import pickle, json, gzip, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/sellid")
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]; SELLS = {(s["mint"], s["k"]): s for s in Z["sells"]}
ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json"))
n = 0
with gzip.open(f"{OUT}/s12_presell.tsv.gz", "wt") as f:
    f.write("bot\tmint\tlot_buy_slot\tlot_buy_idx\tsell_slot\tsell_idx\thold_ms\tlot_pnl_msol\twallet\tside\tsol\tslot_gap\tidx_gap_same_slot\tms_before_sell\n")
    for l in LOTS:
        if l["first_sell_k"] is None: continue
        s = SELLS[(l["mint"], l["first_sell_k"])]
        base = f"{l['code']}\t{ids[l['mint']]}\t{l['slot']}\t{l['idx']}\t{s['slot']}\t{s['idx']}\t{l['sell_dcc']:.0f}\t{1000 * l['net']:.2f}"
        if not len(s["w_us"]):
            f.write(base + "\t-\t-\t-\t-\t-\t-\n"); n += 1; continue
        for j in np.argsort(s["w_dcc"]):
            f.write(base + f"\t{ids[int(s['w_us'][j])]}\t{'buy' if s['w_bu'][j] else 'sell'}\t{s['w_so'][j]:.4f}\t{int(s['w_ds'][j])}\t{int(s['w_di'][j]) if s['w_ds'][j] == 0 else ''}\t{s['w_dcc'][j]:.0f}\n"); n += 1
print("rows", n)
from s10_examples import detail, sigs
cl = [i for i, x in enumerate(ids) if x[:8] in ("2fg5QD1e", "suqh5sHt", "7NAd2EpY", "FxN3VZ4B")]
v = []
for l in LOTS:
    if l["first_sell_k"] is None or (l["slot"], l["idx"]) not in sigs: continue
    s = SELLS[(l["mint"], l["first_sell_k"])]
    m = np.isin(s["w_us"], cl) & s["w_bu"] & (s["w_dcc"] <= 212)
    if m.any(): v.append((l, int(m.sum())))
v.sort(key=lambda x: -x[0]["bt"])
print("lots with a cluster buy <= 212 ms before the sell:", len(v), "cluster buys per such sell:", [x[1] for x in v[:10]])
ex = [detail(l, "4-wallet cluster bought <= 212 ms before his sell") for l, _ in v[:1]]
json.dump(ex, open(f"{OUT}/s12_cluster_example.json", "w"), indent=1); print(json.dumps(ex))
