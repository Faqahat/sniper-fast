#!/usr/bin/env python3
"""SELECT step 6 (read-only): univariate view of the NEW (non-market) signals on the envelope. Per bucket: sells, y1 rate (247/248 bought
<= 2 slots, MEASURED), per-day y1 rate D1..D6 (stability), and - when s4 MKT scores exist - the rate RELATIVE to what the market model
expected (sum y1 / sum p_MKT on the OOS days: > 1 = the signal adds information beyond market features).
Out: select/s6.txt"""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load
OUT = "/home/moiz/sniper-data/haqq_dissect/select"

SPECS = [
    ("sel_ncreates", [0, 1, 2, 5, 20, 1e9]), ("sel_prev_env", [0, 1, 3, 10, 50, 1e9]), ("sel_prev_y", [0, 1, 2, 5, 20, 1e9]),
    ("sel_prev_rate", [-1, 0, 0.001, 0.05, 0.2, 0.5, 1.01]), ("sel_nmint", [0, 1, 3, 10, 50, 300, 1e9]),
    ("cr_prev", [0, 1, 2, 5, 20, 100, 1e9]), ("cr_hqbig", [0, 1, 2, 5, 20, 1e9]), ("cr_peak_max", [-1, 0, 40, 60, 85, 1e9]),
    ("cr_dumped", [-1, 0, 0.5, 0.99, 1.01]), ("cr_ntr", [-1, 0, 1, 10, 100, 1e9]), ("cr_gap_s", [0, 60, 300, 3600, 86400, 1e9]),
    ("c_mint_pump", [0, 0.5, 1.5]), ("c_devbuy_tx", [0, 0.01, 0.5, 1, 2, 4, 1e9]), ("c_nprogs", [0, 1, 2, 10]), ("c_ntips", [0, 1, 2, 10]),
    ("c_cup", [0, 1, 100000, 1000000, 1e7, 1e12]), ("c_name_len", [0, 4, 8, 13, 20, 100]), ("c_sym_caps", [0, 0.5, 1.5]),
    ("c_uri_tg", [0, 0.5, 1.5]), ("c_host_freq", [0, 100, 1000, 10000, 100000, 1e9]), ("c_payer_ne_creator", [0, 0.5, 1.5]),
    ("c_v2", [0, 0.5, 1.5]), ("c_cashback", [0, 0.5, 1.5]), ("c_buyver", [0, 1, 2, 3, 4]),
    ("n_bund", [0, 1, 3, 6, 10, 1e9]), ("n_early", [0, 3, 8, 15, 30, 1e9]), ("sg_diff", [0, 0.5, 1.5]),
    ("t_hour", [0, 4, 8, 12, 16, 20, 24]), ("t_creates10m", [0, 200, 300, 400, 1e9]),
    ("h_open247", [0, 1, 2, 1e9]), ("h_open248", [0, 1, 2, 1e9]), ("h_since247", [0, 2, 10, 60, 1e9]), ("h_since248", [0, 2, 10, 60, 1e9]),
    ("h_open_tok_big", [0, 1, 1e9]), ("h_prev_lots", [0, 1, 3, 1e9])]


def main():
    A, ccols = load()
    y = (A["y247"] | A["y248"]).astype(bool); day = A["day"].astype(int)
    pm = None
    try:
        S = load_scores()["MKT"]; pm = 1 / (1 + np.exp(-S))
    except Exception: pass
    # the MKT model was fitted with negatives weighted back (unbiased probability)
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    P(f"# Univariate: envelope {len(y):,} sells, y1 rate {y.mean():.4f}. 'obs/MKT' = y1 / sum of the market model's OOS probability (D2-D6): >1 = above what market features expect")
    for f, edges in SPECS:
        x = A["f_" + f].astype(np.float64)
        P(f"\n## {f}")
        P("| bucket | sells | y1 rate | " + " | ".join(f"D{d}" for d in range(1, 7)) + " | obs/MKT (D2-D6) |"); P("|---|---|---|" + "---|" * 6 + "---|")
        for a, b in zip(edges[:-1], edges[1:]):
            m = (x >= a) & (x < b)
            if m.sum() < 200: continue
            dr = [f"{y[m & (day == d)].mean():.4f}" if (m & (day == d)).sum() > 100 else "-" for d in range(1, 7)]
            om = "-"
            if pm is not None:
                mm = m & np.isfinite(pm)
                if mm.sum() > 100: om = f"{y[mm].sum() / max(pm[mm].sum(), 1e-9):.2f} ({int(y[mm].sum())})"
            P(f"| [{a:g},{b:g}) | {m.sum():,} | {y[m].mean():.4f} | " + " | ".join(dr) + f" | {om} |")
    # top hosts / routers
    for prefix in ("c_h_", "c_p_"):
        P(f"\n## {prefix} one-hots")
        P("| value | sells | y1 rate | " + " | ".join(f"D{d}" for d in range(1, 7)) + " | obs/MKT |"); P("|---|---|---|" + "---|" * 6 + "---|")
        for c in [c for c in ccols if c.startswith(prefix)]:
            m = A["f_" + c] > 0.5
            if m.sum() < 200: continue
            dr = [f"{y[m & (day == d)].mean():.4f}" if (m & (day == d)).sum() > 100 else "-" for d in range(1, 7)]
            om = "-"
            if pm is not None:
                mm = m & np.isfinite(pm)
                if mm.sum() > 100: om = f"{y[mm].sum() / max(pm[mm].sum(), 1e-9):.2f} ({int(y[mm].sum())})"
            P(f"| {c[len(prefix):]} | {m.sum():,} | {y[m].mean():.4f} | " + " | ".join(dr) + f" | {om} |")
    open(f"{OUT}/s6.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
