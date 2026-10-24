#!/usr/bin/env python3
# Do tonight's live paper wins need the bots buying after us? Re-price every live pick (35 / 75 ms, main exit) with given wallets'
# buys AFTER our entry removed (rt_path DROP): the 3 learned wallets, then the whole 462-wallet profitable-bot cohort (from TRAIN).
import os, sys, json
os.environ.update(RP_PHASEA_R2="phaseA_selfwd", RP_PHASEA_R3="phaseA_r3", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_B="0.5")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
import live_exits as LE
R = [json.loads(l) for l in open("/home/moiz/sniper/ops/overnight/sel/live_trades.jsonl")]
three = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/drop3.json"))); coh = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
tapes = {}
for r in R:
    m = r["m"]
    if m not in tapes: tapes[m] = X.rp.read_bucket(X.L[m]["run"], X.rp.bucket(m), {m}).get(m, [])
def price(drop):
    X.DROP.clear(); X.DROP.update(drop); out = {"35": [0.0, 0, 0], "75": [0.0, 0, 0]}
    for r in R:
        tr = tapes[r["m"]]; S0 = X.L[r["m"]]["slot"]
        k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and round((t["s"] - S0) * X.SMS / 1000, 2) == r["age"]), None)
        if k is None: continue
        for L in ("35", "75"):
            x = LE.detail(X, tr, k, int(L))
            if x is None: continue
            if not x["f"]: out[L][0] -= 0.0002; continue
            p = x[LE.MAIN][0]; out[L][0] += p; out[L][1] += 1; out[L][2] += p > 0
    return out
base = price(set()); d3 = price(three); dc = price(coh | three)
for nm, o in (("normal (what really happened)", base), ("the 3 wallets never buy after us", d3), (f"none of the {len(coh | three)} profitable bots buy after us", dc)):
    print(f"{nm:44s} | 35 ms {o['35'][0]:+6.2f} SOL ({o['35'][2]}/{o['35'][1]} won) | 75 ms {o['75'][0]:+6.2f} ({o['75'][2]}/{o['75'][1]})")
w = [r for r in R if (r["res"].get("35") or {}).get("f") and r["res"]["35"][LE.MAIN][0] > 0]
print(f"live wins at 35 ms: {len(w)}; one of the 3 bought right after the dump in {sum(1 for r in w if r['wallets'])} of them")
