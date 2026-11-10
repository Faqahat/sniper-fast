#!/usr/bin/env python3
"""APEX2 watchlist for the live probe: creators passing the S2 rule (CREP) as of the latest recording, no look-ahead.

Rule (frozen S2, label at position A = first non-bundle position in the create slot):
  judged launches (create >= 300 s before the data end) >= 3, sum(label) > 0, mean(label) > +2 mSOL,
  label = replay net at 0.2 SOL, hold 6 s, minus 2.9 mSOL - pen(0.2) (old APEX definition; guard revert = 0).
Uses every simulated launch in res/run_*.pkl (s1_sim.py), i.e. data up to the last closed chunk of the newest run.
Extra per-creator stats are informational only (not used by the rule).
Out: /home/it/sniper-data/apex2/watchlist.json
usage: w1_watchlist.py [label_pos=A]"""
import sys, json, time, collections, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2")
import a2_eval as E

def main(lpos="A"):
    L = E.load(strings=True); pi = E.POS.index(lpos)
    t_end = max(r[2] for r in L); cut = t_end - 300
    H = collections.defaultdict(list)
    for r in L: H[r[1]].append(r)
    out = []
    for cre, rs in H.items():
        rs.sort(key=lambda r: r[2])
        judged = [r for r in rs if r[2] <= cut]
        labs = []
        for r in judged:
            v = r[6][pi, 1, 0, 2]
            labs.append((float(v) - 0.0029 - E.pen(0.2)) if np.isfinite(v) else 0.0)
        if len(labs) < 3 or sum(labs) <= 0 or np.mean(labs) <= 0.002: continue
        a04 = [float(r[6][pi, 2, 0, 0]) for r in judged if np.isfinite(r[6][pi, 2, 0, 0])]
        last24 = [r for r in rs if r[2] > t_end - 86400]
        rank0 = collections.Counter()
        for r in rs[-30:]:
            nonb = [x for x in r[5]["cst"] if not x[8] and x[4]]
            if nonb: rank0[nonb[0][0]] += 1
        gaps = np.diff([r[2] for r in rs]) if len(rs) > 1 else np.array([np.nan])
        out.append(dict(creator=cre, n_judged=len(labs), label_sum_sol=round(sum(labs), 4), label_mean_msol=round(np.mean(labs) * 1e3, 2),
                        a_0p4_h2_mean_msol=round(np.mean(a04) * 1e3, 2) if a04 else None, launches_total=len(rs),
                        launches_24h=len(last24), last_launch_bt=rs[-1][2], first_seen_bt=rs[0][2],
                        median_gap_s=float(np.nanmedian(gaps)), dev_sol_median=round(float(np.median([r[5]["dev_sol"] for r in rs])), 3),
                        bundle_txs_median=float(np.median([r[5]["nb"] for r in rs])),
                        pct_with_cs_snipers=round(float(np.mean([r[5]["ncs"] > 0 for r in rs])), 2),
                        top_rank0_rivals=[[u, n] for u, n in rank0.most_common(3)]))
    out.sort(key=lambda d: -d["label_sum_sol"])
    W = dict(built_utc=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), data_end_bt=int(t_end),
             data_end_pkt=time.strftime("%Y-%m-%d %H:%M", time.gmtime(t_end + 5 * 3600)),
             rule=dict(label_pos=lpos, n_judged_min=3, sum_label_gt=0, mean_label_gt_msol=2, judged_age_s=300,
                       label="net 0.2 SOL hold 6 s minus 2.9 mSOL + pen(0.2)"),
             n_creators=len(out), n_active_24h=sum(1 for d in out if d["launches_24h"] > 0),
             launches_24h_total=sum(d["launches_24h"] for d in out), creators=out)
    json.dump(W, open("/home/it/sniper-data/apex2/watchlist.json", "w"), indent=1)
    print(f"watchlist: {len(out)} creators ({W['n_active_24h']} launched in last 24 h, {W['launches_24h_total']} launches/24 h); data end {W['data_end_pkt']} PKT")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
