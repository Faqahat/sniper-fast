# What-if on RECORDED launches (record_window.py): our buy inserted right after the creator's glued bundle in the
# create slot S (ahead of every outside buyer), every recorded trade replayed on the constant-product curve (others'
# buy SOL and sell tokens held fixed, so our own impact moves their fills), sell ALL at the curve state at the END of
# slot S+k. Costs: pump fee per side (from the trade events), landing fee = FEE% of size, sell tx fee 0.0005 SOL.
# Also a realistic landing variant (after the first 100 txs of the create slot) for comparison.
# usage: python3 sim_window.py <rec dir> <out.json> [sizes=2,3,4,5] [fees=3,4]
import sys, os, json, glob, math

REC, OUT = sys.argv[1], sys.argv[2]
SIZES = [float(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "2,3,4,5").split(",")]
FEES = [float(x) for x in (sys.argv[4] if len(sys.argv) > 4 else "3,4").split(",")]
SELL_FEE = 0.0005


def pre_state(e):
    return (e["vsol"] - e["sol"], e["vtok"] + e["tok"]) if e["buy"] else (e["vsol"] + e["sol"], e["vtok"] - e["tok"])


def simulate(r, size, fee_pct, k_list, entry="bundle"):
    S = r["S"]; tr = r["trades"]
    if not tr: return None
    fee_rate = ((tr[0].get("fbps") or 0) + (tr[0].get("cbps") or 0)) / 1e4 or 0.0125
    if entry == "bundle":
        k0 = next((n for n, t in enumerate(tr) if not (t["slot"] == S and t["idx"] is not None and t["idx"] < r["glued_end"])), len(tr))
    else:   # realistic: after the first 100 txs of the create slot (our measured live landing)
        k0 = next((n for n, t in enumerate(tr) if t["slot"] > S or (t["idx"] is not None and t["idx"] - r["cidx"] > 100)), len(tr))
    if k0 < len(tr):
        V, T = pre_state(tr[k0])
    else:
        V, T = tr[-1]["vsol"], tr[-1]["vtok"]
    pb_state = None
    # post-bundle reference price = state right after the glued bundle
    gb = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["idx"] < r["glued_end"]]
    pbV, pbT = (gb[-1]["vsol"], gb[-1]["vtok"]) if gb else pre_state(tr[0])
    pb = pbV / pbT
    x = size * 1e9 / (1 + fee_rate)
    q = T * x / (V + x); V += x; T -= q
    fill = size * 1e9 / q
    end_state = {}
    cur = (V, T)
    for t in tr[k0:]:
        if t["buy"]:
            d = T * t["sol"] / (V + t["sol"]); V += t["sol"]; T -= d
        else:
            so = V * t["tok"] / (T + t["tok"]); V -= so; T += t["tok"]
        end_state[t["slot"]] = (V, T)
    out = {}
    land = size * fee_pct / 100
    for k in k_list:
        s = S + k
        st = None
        for ss in range(s, S - 1, -1):         # last state at or before the end of slot s
            if ss in end_state: st = end_state[ss]; break
        if st is None: st = cur
        Vk, Tk = st
        proceeds = Vk * q / (Tk + q) * (1 - fee_rate) / 1e9
        pnl = proceeds - size - land - SELL_FEE
        out[k] = dict(px=(Vk / Tk) / pb, proceeds=proceeds, pnl=pnl)
    return dict(fill_x=fill / pb, out=out, fee_rate=fee_rate)


rows = []
for f in sorted(glob.glob(os.path.join(REC, "*.json"))):
    if f.endswith("_index.json"): continue
    r = json.load(open(f))
    k5 = round(5000 / r["slot_ms"])
    ks = sorted(set([0, 1, 2, 3, 4, 5, 7, 10, k5, round(10000 / r["slot_ms"]), round(20000 / r["slot_ms"]), round(30000 / r["slot_ms"]), round(60000 / r["slot_ms"])]))
    ks = [k for k in ks if k <= r.get("window_slots", 280)]
    tr = r["trades"]
    gb = [t for t in tr if t["slot"] == r["S"] and t["idx"] is not None and t["idx"] < r["glued_end"]]
    pbV = gb[-1]["vsol"] if gb else (tr[0]["vsol"] if tr else 0)
    pbT = gb[-1]["vtok"] if gb else (tr[0]["vtok"] if tr else 1)
    pb = pbV / pbT if pbT else 0
    prices = [(t["slot"] - r["S"], (t["vsol"] / t["vtok"]) / pb) for t in tr if t["vtok"] and pb]
    peak5 = max([p for d, p in prices if d <= k5] or [1.0]); low5 = min([p for d, p in prices if d <= k5] or [1.0])
    peak60 = max([p for d, p in prices] or [1.0])
    outside_S = sum(1 for t in tr if t["slot"] == r["S"] and t["buy"] and t["idx"] is not None and t["idx"] >= r["glued_end"])
    mc_sol = pbV / pbT * 1e6 if pbT else 0   # lamports per raw token x 1e6 = SOL per 1e9 tokens... -> MC in SOL
    row = dict(mint=r["mint"], S=r["S"], block_time=r.get("block_time"), fired=r["fired"], engine=r["engine"], name=r.get("name"), symbol=r.get("symbol"),
               dev=r["dev"], gsol=r["gsol"], glued=r["glued"], rule2=r["rule2_largest"], any_moon=r["any_moon"], leader_client=r.get("leader_client"),
               leader_rtt=r.get("leader_rtt"), leader_city=r.get("leader_city"), mc_sol=mc_sol, k5=k5, ks=ks, n_trades=len(tr), outside_buys_S=outside_S,
               peak5=peak5, low5=low5, peak60=peak60, sim={}, sim_real={})
    for size in SIZES:
        for fee in FEES:
            a = simulate(r, size, fee, ks, "bundle")
            b = simulate(r, size, fee, [3, k5], "d100")
            key = f"{size:g}|{fee:g}"
            if a: row["sim"][key] = dict(fill_x=a["fill_x"], out={str(k): v for k, v in a["out"].items()})
            if b: row["sim_real"][key] = dict(fill_x=b["fill_x"], out={str(k): v for k, v in b["out"].items()})
    rows.append(row)
rows.sort(key=lambda r: r["S"])
json.dump(dict(rows=rows, sizes=SIZES, fees=FEES), open(OUT, "w"))
fired = [r for r in rows if r["fired"]]
print(f"launches {len(rows)} (fired {len(fired)})")
for size in SIZES:
    for fee in FEES:
        key = f"{size:g}|{fee:g}"
        n3 = sum(r["sim"][key]["out"]["3"]["pnl"] for r in fired if key in r["sim"])
        n5 = sum(r["sim"][key]["out"][str(r["k5"])]["pnl"] for r in fired if key in r["sim"])
        w3 = sum(1 for r in fired if key in r["sim"] and r["sim"][key]["out"]["3"]["pnl"] > 0)
        w5 = sum(1 for r in fired if key in r["sim"] and r["sim"][key]["out"][str(r["k5"])]["pnl"] > 0)
        print(f"  FIRED  size {size:g} SOL fee {fee:g}%:  n+3 total {n3:+.3f} SOL ({w3}/{len(fired)} win)   5s total {n5:+.3f} SOL ({w5}/{len(fired)} win)")
