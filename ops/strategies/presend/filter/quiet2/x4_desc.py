#!/usr/bin/env python3
"""QUIET2 step 4: labels (chain) and descriptive tables: flat / win / loss per run, QUIET signals on flat vs paying fills,
the no-history path, fill-time (dump) features flat vs paying."""
import sys, json, collections
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/quiet2")
import q2lib as Q
F = json.load(open(f"{Q.D}/features.json")); W = F["windows"]; SK = F["skips"]
def label(r):
    if not r["filled"]: return "NOFILL"
    f = r["f"]
    if not f.get("chain_ok"): return "FLAT" if r["eng_fol_trades"] == 0 else ("WIN" if r["net"] > 0 else "LOSS")
    if f["fol_trades"] == 0: return "FLAT"
    return "WIN" if r["net"] > 0 else "LOSS"
for r in W: r["lab"] = label(r)
json.dump(F, open(f"{Q.D}/features.json", "w"))
print("## per run (chain labels; flat = no other wallet's trade between our buy and our sell)")
print(f"{'run':8s} {'role':5s} {'arms':>5s} {'fills':>5s} {'flat':>4s} {'flat%':>5s} {'flat net':>9s} {'flat fees':>9s} {'win':>4s} {'win net':>8s} {'loss':>4s} {'loss net':>9s} {'fees all':>8s} {'presend net':>11s} {'fills/h':>7s} {'eng-flat':>8s}")
tot = collections.Counter()
for run, R in Q.RUNS.items():
    w = [r for r in W if r["run"] == run]; fl = [r for r in w if r["filled"]]
    fe = sum(r["fee_fail"] for r in w); flats = [r for r in fl if r["lab"] == "FLAT"]; wins = [r for r in fl if r["lab"] == "WIN"]; loss = [r for r in fl if r["lab"] == "LOSS"]
    hours = (max(r["t"] for r in w) - min(r["t"] for r in w)) / 3.6e12
    net = sum(r["net"] for r in fl)
    print(f"{R['name']:8s} {R['role']:5s} {len(w):5d} {len(fl):5d} {len(flats):4d} {100*len(flats)/max(len(fl),1):5.1f} {sum(r['net'] for r in flats):+9.3f} {sum(r['fee_fail'] for r in flats):9.3f} {len(wins):4d} {sum(r['net'] for r in wins):+8.3f} {len(loss):4d} {sum(r['net'] for r in loss):+9.3f} {fe:8.3f} {net-fe:+11.3f} {len(fl)/hours:7.1f} {sum(1 for r in fl if r['eng_fol_trades']==0):8d}")
print()
print("## QUIET signals on the fills: flat vs win vs loss (pooled, all 9 runs; r29/r30 had no QUIET -> excluded from signal rows)")
fl = [r for r in W if r["filled"] and r["since_last"] is not None]
def row(name, fn):
    out = [name.ljust(34)]
    for lab in ("FLAT", "WIN", "LOSS"):
        g = [r for r in fl if r["lab"] == lab]
        v = [fn(r) for r in g]; v = [x for x in v if x is not None]
        out.append(f"{np.mean(v):7.3f} (n={len(v):3d})" if v else "   -   ")
    print("  ".join(out))
print(" ".ljust(34), "  ".join(f"{l:>14s}" for l in ("FLAT", "WIN", "LOSS")))
row("(a) since_last>=1 share", lambda r: float(r["q_a"]))
row("(b) coh_hold==0 share", lambda r: float(r["q_b"]))
row("(c) fb_n<2 share", lambda r: float(r["q_c"]))
row("(d) wh_fol<2.24 or none share", lambda r: float(r["q_d"]))
row("quiet count (a+b+c+d)", lambda r: float(r["q_a"] + r["q_b"] + r["q_c"] + r["q_d"]))
row("3 of 4 quiet", lambda r: float(r["q_a"] + r["q_b"] + r["q_c"] + r["q_d"] >= 3))
row("wh_dumps==0 (no history) share", lambda r: float(r["wh_dumps"] == 0))
row("wh_dumps mean", lambda r: float(r["wh_dumps"]))
row("wh_fol mean (history only)", lambda r: r["wh_fol"] if r["wh_dumps"] > 0 else None)
row("wh_fol<1 share (history only)", lambda r: float(r["wh_fol"] < 1) if r["wh_dumps"] > 0 else None)
row("since_last (capped 50) mean", lambda r: float(min(r["since_last"], 50)))
row("coh_hold mean", lambda r: float(r["coh_hold"]))
row("fb_n mean", lambda r: float(r["fb_n"]))
row("spend", lambda r: r["spend"])
row("whale_sol", lambda r: r["whale_sol"])
row("whale_pct", lambda r: r["whale_pct"])
row("vsol (curve after buy)", lambda r: r["vsol"])
row("age_slots", lambda r: float(r["age_slots"]))
row("hour PKT", lambda r: float(r["hour"]))
row("prior_arms on token", lambda r: float(r["prior_arms"]))
row("prior_fills on token", lambda r: float(r["prior_fills"]))
row("prior arms same whale (run)", lambda r: float(r["prior_whale_arms"]))
row("slots_after_trigger (fill)", lambda r: float(r["slots_after_trigger"]))
row("fill_lag_ms (arm->fill)", lambda r: float(r["fill_lag_ms"]))
row("ms_send_to_rx", lambda r: r.get("ms_send_to_rx"))
print()
print("## chain features at ARM time, flat vs win vs loss (means)")
keys = ["n_tr", "token_age_s", "n_tr_30s", "n_buyers_30s", "n_tr_60s", "n_buyers_60s", "n_tr_120s", "n_buyers_120s", "n_buyers_300s", "buy_sol_60s", "sell_sol_60s", "coh_60s", "fb_60s", "coh_300s", "fb_300s",
        "trades_per_s_60", "since_last_s", "coh_hold_chain", "fb_n_chain", "coh_ever", "n_wallets", "n_holders", "holders_gt1pct", "holders_gt0_5pct", "top_holder_pct", "whale_bal_pct_before", "whale_pct_after_buy",
        "whale_prev_trades", "pump_pct", "ret_30s", "ret_60s", "ret_120s", "maxdd_60s", "maxdd_120s", "buy_vs_curve", "vsol_pre", "same_slot_before", "wd_n", "wd_mean", "wd_last", "wd_max", "wd_zero_share", "wd_n_1h", "wd_n_this_mint", "wd_last_age_s"]
for k in keys: row(k, lambda r, k=k: r["f"].get(k) if r["f"].get("chain_ok") else None)
print()
print("## FILL-time (dump) features, flat vs win vs loss (means)")
for k in ["dump_slot_off", "dump_sol", "dump_drop", "dump_vs_curve", "dump_post_vsol", "dump_tok_pct", "whale_sold_all", "hold_others", "hold_buyers", "hold_buy_sol", "hold_coh_buyers", "hold_fb_buyers", "runup", "dump_to_fill_others", "dump_to_fill_buyers", "dump_to_fill_same_slot", "others_trig_to_fill", "buyers_trig_to_fill", "whale_sells_trig_to_fill", "fol_trades", "fol_buyers", "fol_buy_sol", "fol_sell_sol"]:
    row(k, lambda r, k=k: (float(r["f"][k]) if k in r["f"] else None) if r["f"].get("chain_ok") else None)
print()
print("## net per fill by label and run-size")
for sp in sorted({r["spend"] for r in fl}):
    g = [r for r in fl if r["spend"] == sp]
    print(f"spend {sp:.2f}: " + "  ".join(f"{lab} n={sum(1 for r in g if r['lab']==lab)} mean={np.mean([r['net'] for r in g if r['lab']==lab] or [0]):+.4f}" for lab in ("FLAT", "WIN", "LOSS")))
print()
print("## the no-history path: wh_dumps==0 -> (d) true. Fills by (d) reason")
for role in ("train", "test"):
    g = [r for r in fl if r["role"] == role]
    for name, fn in (("no history (wh_dumps=0)", lambda r: r["wh_dumps"] == 0), ("history, wh_fol<2.24", lambda r: r["wh_dumps"] > 0 and r["wh_fol"] < 2.24), ("history, wh_fol>=2.24", lambda r: r["wh_dumps"] > 0 and r["wh_fol"] >= 2.24)):
        h = [r for r in g if fn(r)]
        print(f"{role:5s} {name:24s} fills {len(h):4d} flat {sum(1 for r in h if r['lab']=='FLAT'):3d} ({100*sum(1 for r in h if r['lab']=='FLAT')/max(len(h),1):4.1f}%) net {sum(r['net'] for r in h):+.3f} per fill {np.mean([r['net'] for r in h] or [0]):+.4f}  | with a,b,c all quiet: fills {sum(1 for r in h if r['q_a'] and r['q_b'] and r['q_c'])} flat {sum(1 for r in h if r['q_a'] and r['q_b'] and r['q_c'] and r['lab']=='FLAT')} net {sum(r['net'] for r in h if r['q_a'] and r['q_b'] and r['q_c']):+.3f}")
print()
print("## skipped (quiet) triggers: proxies (whale sold within 10 slots at a fillable price? followers after that dump?)")
for role in ("train", "test"):
    g = [s for s in SK if s["role"] == role and s["f"].get("chain_ok")]
    pf = [s for s in g if s["f"].get("px_fill")]
    print(f"{role:5s} quiet skips {len(g)} would-fill {len(pf)} ({100*len(pf)/max(len(g),1):.0f}%) of which 0 followers {sum(1 for s in pf if s['f']['px_fol_buyers']==0)} ; mean px_ret2 {np.mean([s['f']['px_ret2'] for s in pf] or [0]):+.2f}% ; >+3.3% {sum(1 for s in pf if s['f']['px_ret2']>3.3)} ; no-history share {np.mean([s['wh_dumps']==0 for s in g]):.2f}")
    # the same proxies on ARMED windows for calibration
    g2 = [r for r in W if r["role"] == role and r["f"].get("chain_ok")]
    pf2 = [r for r in g2 if r["f"].get("px_fill")]
    print(f"      armed {len(g2)} would-fill(proxy) {len(pf2)} actually filled {sum(1 for r in g2 if r['filled'])} proxy&filled {sum(1 for r in pf2 if r['filled'])} filled-not-proxy {sum(1 for r in g2 if r['filled'] and not r['f'].get('px_fill'))} ; of proxy fills 0 followers {sum(1 for r in pf2 if r['f']['px_fol_buyers']==0)}")
