#!/usr/bin/env python3
"""REPLAY_065 step 5: tie each live exit to the chain (MEASURED) and measure the sell delays the replay uses when an exit moves.
  * live TP / SL exits: the trade whose post-trade state gives the engine's logged exit value (at the live size) = the trigger
  * delays (chain clock ms): TP / SL -> sell landing; time limit -> sell landing after the slot (entry + 2 | buy + hold) starts
Builds the positions (positions.py) and writes /home/moiz/sniper-data/replay065/pos_cal.pkl (positions + live trigger rows) and delays.json."""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core, positions as PO, pmath as PM

def main():
    D = core.Data()
    PS = PO.presend_positions(D)
    RG, RF = PO.regular_positions(D)
    for p in PS:
        st = p.sell_tr
        p.costs = p.buy_fee + p.tip + p.rent + p.sell_fee + p.sell_tips
        p.net_live = st["sol"] - PM.fees(st["sol"], st["fbps"], st["cbps"])
    for p in RG:
        st = p.sell_tr
        p.net_live = st["sol"] - PM.fees(st["sol"], st["fbps"], st["cbps"])
        p.costs = p.net_live - p.spend - p.realized
    dl = collections.defaultdict(list); found = collections.Counter()
    for p in PS + RG:
        p.live_dec_row = None; p.live_trig_rx = None
        if p.exit_why in ("take-profit", "stop-loss"):
            W = core.walk(D, p.mint, p.pre, p.rows, p.spend, p.ours_buy["fbps"], p.ours_buy["cbps"], (10 ** 15, 0, 0))
            best = None
            for k, v, t, ap in W["states"]:
                row = p.rows[k]
                if not ap or row["kind"] != "trade": continue
                rx = p.tape_rx.get(row["tr"]["sig"])
                if rx is None or rx > p.exit_t: continue
                val = PO.value_ps(v, t, W["q"], row["tr"]["fbps"], row["tr"]["cbps"], p.spend) if p.kind == "ps" else PO.value_reg(v, t, W["q"], row["tr"]["fbps"], row["tr"]["cbps"], p.spend)
                if abs(val - p.exit_value) < 1e-9: best = (k, rx)
            if best:
                p.live_dec_row, p.live_trig_rx = best; found["trig_found"] += 1
                row = p.rows[best[0]]
                dl[p.kind + ":tpsl"].append(D.ck.cc(*p.sell_pos) - D.ck.cc(row["s"], row["i"]))
            else:
                found["trig_missing"] += 1
        elif p.exit_why == "time-limit":
            base = (p.land_slot + (2 if p.kind == "ps" else p.hold)) * core.SMS
            dl[p.kind + ":time"].append(D.ck.cc(*p.sell_pos) - base)
    delays = {k: float(np.median(v)) for k, v in dl.items()}
    delays.setdefault("reg:tpsl", delays["ps:tpsl"])
    pct = {k: [round(float(x), 1) for x in np.percentile(v, [10, 25, 50, 75, 90])] + [len(v)] for k, v in dl.items()}
    json.dump(dict(median=delays, pcts=pct), open(f"{core.BASE}/delays.json", "w"), indent=1)
    pickle.dump((PS, RG, RF), open(f"{core.BASE}/pos_cal.pkl", "wb"))
    print(dict(found)); print("delays (chain ms) p10/25/50/75/90, n:", pct)

if __name__ == "__main__":
    main()
