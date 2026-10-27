#!/usr/bin/env python3
"""PRESEND FILTER, analysis 3: chain-wide T2 events (proxy outcome, INFERRED) in the TUNING periods only:
  before 10-25 22:00 PKT (before every validation run) and the dev period 10-26 21:47 -> 10-27 06:20 PKT.
  The validation period 10-25 22:00 -> 10-26 21:47 PKT is excluded here.
Per feature: proxy net per fill-like event by quintile, and the share of 'dead' fills (no other buyer within 2 slots)."""
import json, sys
import numpy as np
B = "/home/moiz/sniper-data/presend_filter"
T_VAL0, T_VAL1 = 1792948200, 1793033220   # 10-25 22:00 PKT, 10-26 21:47 PKT
E = [e for e in json.load(open(f"{B}/chain_events.json")) if not (T_VAL0 <= e["bt"] < T_VAL1)]
F = [e for e in E if e["fill"]]
print("tuning events", len(E), "fill-like", len(F), "proxy net sum %+.2f" % sum(e["y_net"] for e in F), "dead (no other buyer) %d" % sum(1 for e in F if e["y_nf"] == 0))
feats = sys.argv[1:] or ["age", "n_tr", "n_users", "vol", "n_tr_10", "n_tr_50", "cre_prev", "dev_hold", "dev_sold", "wh_nf", "wh_bounce", "wh_fill", "wh_n", "wh_tokens_before",
                         "wh_first_age", "wh_dump_fol", "coh_n", "coh_hold", "fb_n", "fb_hold", "fb_n20", "n_big", "top10", "pct", "whale_sol", "vsol", "trig_tip", "trig_cup",
                         "tok_dumps", "tok_dump_fol", "since_last", "p_ret_20", "dd_peak", "whale_prev_bal", "oc_depth"]
y = np.array([e["y_net"] for e in F]); dead = np.array([e["y_nf"] == 0 for e in F])
for k in feats:
    x = np.array([float(e.get(k)) if e.get(k) is not None else np.nan for e in F])
    qs = np.unique(np.nanpercentile(x, [0, 20, 40, 60, 80, 100]))
    line = f"{k:16s}|"
    for lo, hi in zip(qs[:-1], qs[1:]):
        m = (x >= lo) & ((x < hi) if hi < qs[-1] else (x <= hi))
        line += f" [{lo:.3g},{hi:.3g}] n{m.sum()} {y[m].mean() * 1000:+.1f}m dead{dead[m].mean() * 100:.0f}% |"
    print(line)
