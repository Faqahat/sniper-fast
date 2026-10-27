#!/usr/bin/env python3
# PRE-SEND V2 step c7 (a): seller-tool tokens in the replay. The tape rule (feed-observable, causal): a buy 1-3 block positions after a
# >= 0.3 SOL sell that dropped the price >= 4% in the same slot, by another wallet, the buys since that sell = 25-110% of it
# (the sell + rebuy bundle of INSTANT_BOTS.md). Per day: share of T2 windows on tokens with such a rebuy BEFORE the trigger, and
# the net per fill / per window there vs elsewhere; fills whose crossing was itself followed by a rebuy.
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
R.G["DD"] = {d: E.load(d) for d in V.DAYS}
for name, row, size in (("A_k4_0.55", "L4", 0.55), ("B_k8_0.55", "L8", 0.55)):
    print(f"== {name}")
    for d in V.DAYS:
        D = R.G["DD"][d]
        base = R.fmask(D, dict(fam="T2"))
        tool = (E.wf(D, "tool_n") > 0) | (E.wf(D, "trig_rebuy") > 0)
        o = E.run(D, base, 10, 0.12, row, size, "c2_tp10_sl20", detail=True)
        idx = o["idx"]; arm = o["armed_mask"]; acc = o["acc"]
        t_w = tool[idx]
        wn = o["w_net"]
        fr = o["acc_fr"]; xt = D["f_f"][fr, E.FFI["x_tool"]] > 0
        an = o["acc_net"]
        print(f"  {d}: windows armed {arm.sum()} (tool tokens {100 * (t_w & arm).sum() / max(arm.sum(), 1):.1f}%) | net per armed window: tool {wn[t_w & arm].mean() if (t_w & arm).any() else 0:+.5f} "
              f"other {wn[~t_w & arm].mean():+.5f} | fills on tool tokens {t_w[acc].sum()} ({an[t_w[acc]].mean() if t_w[acc].any() else 0:+.4f}/fill) vs {(~t_w[acc]).sum()} ({an[~t_w[acc]].mean():+.4f}) | "
              f"fills whose crossing had a rebuy right after {xt.sum()} ({an[xt].mean() if xt.any() else 0:+.4f}/fill)")
