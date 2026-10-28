#!/usr/bin/env python3
"""ourspeed step 7 (MEASURED): our FRA r27/r28 pre-send fills on E2x1's tokens vs his lot on the same token/time."""
import json, pickle, collections, numpy as np, time
R = "/home/moiz/sniper-data/e2x1_dissect/recon"; O = "/home/moiz/sniper-data/e2x1_dissect/ourspeed"
ME = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"; SIB = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
Lots = [l for l in pickle.load(open(f"{R}/lots.pkl", "rb")) if l["day"] in ("D0", "D1", "post")]
bym = collections.defaultdict(list)
for l in Lots: bym[l["mint"]].append(l)
Z = pickle.load(open(f"{R}/tape.pkl", "rb"))
B = np.load(f"{O}/blocks.npy"); s_lo = int(B["slot"][0]); NB = np.zeros(int(B["slot"][-1]) - s_lo + 2); NB[B["slot"].astype(np.int64) - s_lo] = B["maxi"] + 1.0
clk = lambda s, i: s + min(i / max(NB[s - s_lo], 1), 0.999999)
pk = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
rows = []
for run in ("r27", "r28"):
    arms = collections.defaultdict(list); fills = {}; close = {}; real = {}
    for ln in open(f"/home/moiz/sniper-data/runs/fra/runs/dip_{run}.jsonl"):
        if '"presend_live_' not in ln: continue
        d = json.loads(ln); e = d["ev"]
        if e == "presend_live_arm" and d.get("trig"): arms[d["trig"]["mint"]].append(d)
        elif e == "presend_live_fill": fills[d["sig"]] = d
        elif e == "presend_live_close": close[d["buy_sig"]] = d
        elif e == "presend_live_realized":
            for b in d["buys"]: real[b["sig"]] = d
    for sig, f in fills.items():
        m = f["mint"]
        if m not in bym: continue
        tf = f["t"] / 1e9
        cand = [l for l in bym[m] if l["bt"] - 60 <= tf <= (l["close_bt"] or l["bt"]) + 60]
        if not cand: continue
        l = min(cand, key=lambda l: abs(l["bt"] - tf))
        c = close.get(sig); rz = real.get(sig)
        a = [x for x in arms[m] if x["trig"]["t"] / 1e9 <= tf]; a = a[-1] if a else None
        whale = a["trig"]["wallet"] if a else None
        # the dump we bought: last sell by the whale before our fill
        tr = [t for t in Z["trades"][m] if t[16]]
        dump = [t for t in tr if not t[6] and t[4] == whale and (t[0], t[1]) < (f["slot"], f["idx"])]
        dump = dump[-1] if dump else None
        our_c = clk(f["slot"], f["idx"]); his_c = clk(l["s"], l["i"])
        # did he buy that same dump: his trigger sig == dump sig, or his buy within 3 slots after the dump
        same_dump = bool(dump) and (l.get("trig_sig") == dump[15] or (0 <= l["s"] - dump[0] <= 3 and (l["s"], l["i"]) > (dump[0], dump[1])))
        his_sell_c = clk(l["sells"][0][1], l["sells"][0][2]) if l["sells"] else None
        rows.append(dict(run=run, mint=m, t=tf, our_sol=f["sol_in"] / 1e9, our_curve=(c or {}).get("curve_pnl", np.nan) / 1e9 if c else np.nan,
                         our_real=rz["pnl"] / 1e9 if rz else np.nan, our_hold=(c or {}).get("held_s", np.nan) if c else np.nan,
                         dt_ms=(our_c - his_c) * 212.07, same_slot=f["slot"] == l["s"], same_dump=same_dump,
                         his_bot=l["bot"], his_cost=l["cost"], his_pnl=l["pnl"], his_hold=l["hold_s"], dump_sol=dump[7] / 1e9 if dump else np.nan,
                         whale_is_him=whale in (ME, SIB), our_sell_before_his=(c and c.get("sell_land") and his_sell_c and clk(c["sell_land"][0], c["sell_land"][1]) < his_sell_c),
                         gmgn=f"https://gmgn.ai/sol/token/{m}", our_buy=f"https://solscan.io/tx/{sig}", his_buy=l["buy_tx"]))
pickle.dump(rows, open(f"{O}/overlap_rows.pkl", "wb"))
out = []
def P(s=""): print(s); out.append(s)
def summ(name, x):
    if not x: P(f"| {name} | 0 |"); return
    ours = np.nansum([r["our_real"] for r in x]); oc = np.nansum([r["our_curve"] for r in x]); his = sum(r["his_pnl"] for r in x)
    osol = sum(r["our_sol"] for r in x); hsol = sum(r["his_cost"] for r in x)
    P(f"| {name} | {len(x)} | {ours:+.3f} ({ours / osol:+.1%}) | {oc:+.3f} | {np.mean([r['our_real'] > 0 for r in x]):.0%} | {his:+.3f} ({his / hsol:+.1%}) | {np.mean([r['his_pnl'] > 0 for r in x]):.0%} | {np.median([r['dt_ms'] for r in x]):+.0f} | {np.nanmedian([r['our_hold'] for r in x]):.1f} / {np.median([r['his_hold'] for r in x]):.0f} |")
P("| group | fills | our realized P&L (per SOL) | our curve P&L | our win | his P&L same lots (per SOL) | his win | our buy minus his buy, median ms | hold s ours / his (median) |")
P("|---|---|---|---|---|---|---|---|---|")
summ("all overlap fills", rows)
for k in ("r27", "r28"): summ(f"run {k}", [r for r in rows if r["run"] == k])
summ("he bought the SAME dump as us", [r for r in rows if r["same_dump"]])
summ("different moment (not the same dump)", [r for r in rows if not r["same_dump"]])
summ("we bought before him", [r for r in rows if r["dt_ms"] < 0]); summ("we bought after him", [r for r in rows if r["dt_ms"] >= 0])
for b in ("FRESH", "MINUTE", "OLD"): summ(f"his band {b}", [r for r in rows if r["his_bot"] == b])
summ("whale we bought from = E2x1 or sibling", [r for r in rows if r["whale_is_him"]])
P("\nExamples (MEASURED):")
for r in sorted(rows, key=lambda r: r["t"])[:: max(1, len(rows) // 10)]:
    P(f"- {pk(r['t'])} [{r['mint'][:8]}]({r['gmgn']}) we {r['our_sol']:.2f} SOL [buy]({r['our_buy']}) {r['dt_ms']:+.0f} ms vs his [buy]({r['his_buy']}) ({r['his_bot']}, {r['his_cost']:.2f} SOL); "
      f"same dump {r['same_dump']}; ours {r['our_real']:+.4f} held {r['our_hold']:.1f} s | his {r['his_pnl']:+.4f} held {r['his_hold']} s")
open(f"{O}/o7_overlap.md", "w").write("\n".join(out) + "\n")
