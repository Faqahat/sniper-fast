#!/usr/bin/env python3
"""8yYMhu s2 (read-only): take rate and paper forward returns by feature bin over the universe of outside sells >= 1 SOL (uni.npz).
Out: DATA/s2.txt"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
U = dict(np.load(f"{X.D}/uni.npz"))
n = len(U["mint"]); tk = U["taken"] > 0; fl = U["filled"] > 0
# leader area / client of the sell slot
slots = U["slot"]; us, inv = np.unique(slots, return_inverse=True)
ar = np.array([X.area(s) for s in us]); cl = np.array([X.leader(s)[1] for s in us]); fr = np.array([X.frac(s, 0) for s in us])
U["area"] = ar[inv]; U["client"] = cl[inv]
U["frac"] = np.array([X.frac(s, i) for s, i in zip(U["slot"], U["idx"])])
np.savez_compressed(f"{X.D}/uni2.npz", **U)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
P(f"universe {n} outside sells >= 1 SOL (10-25 13:00 -> 10-29 00:50 PKT); taken {tk.sum()} ({100*tk.mean():.2f}%), filled {fl.sum()} ({100*fl.mean():.2f}%)")
r = U["r_e73_9"]; r0 = U["r_e0_9"]
P(f"paper r (0.75 SOL, after pump fees, before tx costs) entry e73 exit +9 slots: taken mean {1000*np.nanmean(r[tk]):+.2f} mSOL, skipped {1000*np.nanmean(r[~tk]):+.2f}; filled {1000*np.nanmean(r[fl]):+.2f}; his realized net on filled {1000*np.nanmean(U['his_pnl'][fl]):+.2f}")
for x in (1, 2, 3, 6, 9, 20, 40, 61):
    a = U[f"r_e73_{x}"]; b = U[f"r_e0_{x}"]
    P(f"  exit +{x:2}: e73 taken {1000*np.nanmean(a[tk]):+6.2f} skipped {1000*np.nanmean(a[~tk]):+6.2f} | e0 taken {1000*np.nanmean(b[tk]):+6.2f} skipped {1000*np.nanmean(b[~tk]):+6.2f}  (mSOL/trade)")
def tab(name, v, bins, lab=None):
    P(f"-- {name}")
    idx = np.digitize(v, bins)
    for k in range(len(bins) + 1):
        m = idx == k
        if m.sum() < 50: continue
        lo = "-inf" if k == 0 else f"{bins[k-1]:g}"; hi = "inf" if k == len(bins) else f"{bins[k]:g}"
        P(f"   [{lo:>6},{hi:>6}) n {m.sum():7}  take {100*tk[m].mean():5.2f}%  fill {100*fl[m].mean():5.2f}%  share of his takes {100*(tk&m).sum()/tk.sum():5.1f}%  "
          f"paper e73+9 taken {1000*np.nanmean(r[tk&m]) if (tk&m).sum() else float('nan'):+6.1f} skipped {1000*np.nanmean(r[~tk&m]):+6.1f}  his net/fill {1000*np.nanmean(U['his_pnl'][fl&m]) if (fl&m).sum() else float('nan'):+6.1f}")
tab("sell SOL", U["sol"], [1.5, 2, 3, 5, 8, 15])
tab("price drop % of the sell", 100 * U["drop"], [3, 5, 8, 12, 18, 25, 35])
tab("curve vSOL after the sell", U["vsol_after"], [32, 35, 40, 50, 60, 80, 100])
tab("token age (slots) [-1 = create unknown]", U["age_slots"], [0, 5, 25, 50, 150, 300, 1000, 5000, 30000])
tab("seller share of supply sold %", U["seller_supply_pct"], [0.5, 1, 2, 3, 5, 8, 12])
tab("seller frac of its bought tokens sold (-1 none bought)", U["seller_frac"], [0, 0.25, 0.5, 0.9, 0.999, 1.001])
tab("seller hold slots (-1 never bought)", U["seller_hold_slots"], [0, 1, 3, 10, 30, 100, 1000])
tab("seller buyer-rank (order of first buy; -1 none)", U["seller_rank"], [0, 1, 2, 5, 10, 25, 100])
tab("drawdown from peak after the sell %", 100 * U["dd_peak"], [5, 10, 20, 30, 45, 60])
tab("outside buy SOL last 10 slots", U["buy10"], [0.5, 2, 5, 10, 20, 40])
tab("outside sell SOL last 10 slots", U["sell10"], [0.5, 2, 5, 10, 20, 40])
tab("trades before on token", U["n_before"], [5, 20, 50, 100, 300, 1000, 3000])
tab("sell position in its block (frac)", U["frac"], [0.2, 0.4, 0.6, 0.8, 0.9])
for nm_, v in (("seller is creator", U["seller_creator"]), ("seller bought in create slot", U["seller_cslot"]), ("mayhem", U["mayhem"])):
    for val in (True, False):
        m = v == val
        P(f"-- {nm_}={val}: n {m.sum()} take {100*tk[m].mean():.2f}% share of his takes {100*(tk&m).sum()/tk.sum():.1f}% paper taken {1000*np.nanmean(r[tk&m]) if (tk&m).sum() else float('nan'):+.1f} skipped {1000*np.nanmean(r[~tk&m]):+.1f}")
for nm_, v in (("leader area", U["area"]), ("leader client", U["client"])):
    P(f"-- {nm_}")
    for val in sorted(set(v.tolist())):
        m = v == val
        if m.sum() < 200: continue
        P(f"   {val:14} n {m.sum():7} take {100*tk[m].mean():5.2f}% share of his takes {100*(tk&m).sum()/tk.sum():5.1f}% paper taken {1000*np.nanmean(r[tk&m]) if (tk&m).sum() else float('nan'):+6.1f} skipped {1000*np.nanmean(r[~tk&m]):+6.1f}")
open(f"{X.D}/s2.txt", "w").write("\n".join(out) + "\n")
