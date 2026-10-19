#!/usr/bin/env python3
import json
P=json.load(open("/root/exit_timing/paths.json"))
UNIT=1000.0  # px_common(SOL/whole-tok) -> lamports/raw-token
SLOT_MS=400.0  # solana ~400ms/slot (approx)
ORDER=["883Xw2k39itvFRMPBJYXx91MAw3uzc2sKqiRSAQaFb55","3nfCAA4emVMQpbqVCzEHx9XHursYSdtUw9rfcQzepump",
"CenpWbd7YgwRi13DLEgudX1wwDhBFapv8fL4dzeopump","2mczEAedUhHRP5GQ43gP2qTVWCij9NgfidmNJpya4YKU",
"7Cs9KCipGn4s5GSjBEKdeqQ4CJ8aXwvSunY9Lre1fDKE","FXUVymBHRSNaYyuVdkdNhRU8boEP5doyU4ceV6bswrh2",
"BEms6yQdym89E2d71pypdpjdQ8ZyeuKXtBSdaYqWpump","8FYmQHVr33Li3YykhXKpshLvHGjZksHV9MDHdZ9epump"]

rows=[]
for i,m in enumerate(ORDER,1):
    d=P[m]; entry=d["entry_lamports_raw"]; exitslot=d["exit_slot"]
    ser=[(s,bt,px*UNIT) for (s,bt,px,ds) in d["series"]]  # px now lamports/raw
    rs=[(s,bt,px/entry) for (s,bt,px) in ser]
    if not rs: rows.append({"i":i,"m":m,"empty":True}); continue
    # lifetime peak
    pk_slot,pk_bt,pk_r=max(rs,key=lambda x:x[2])
    # price near exit: last trade <= exit_slot
    at_exit=[r for r in rs if r[0]<=exitslot]
    exit_r=at_exit[-1][2] if at_exit else rs[0][2]
    exit_ref_slot=at_exit[-1][0] if at_exit else rs[0][0]
    # post-exit: strictly after exit_slot
    post=[r for r in rs if r[0]>exitslot]
    if post:
        pe_slot,pe_bt,pe_r=max(post,key=lambda x:x[2])
    else:
        pe_slot,pe_bt,pe_r=exit_ref_slot,None,exit_r
    def rat(off):
        c=[r for r in rs if r[0]<=exitslot+off]
        return c[-1][2] if c else None
    r10,r30,r60=rat(10),rat(30),rat(60)
    slots_to_pe=pe_slot-exitslot
    # time seconds via blocktime if available
    bt_exit=at_exit[-1][1] if at_exit else None
    secs_to_pe=(pe_bt-bt_exit) if (pe_bt and bt_exit) else (slots_to_pe*SLOT_MS/1000.0)
    # classify
    if pe_r>=1.3: cls="PUMPED-AFTER-EXIT"
    elif pk_r<1.2: cls="NEVER-PUMPED"
    else: cls="MARGINAL"
    # death check: last price r
    last_r=rs[-1][2]
    rows.append({"i":i,"m":m,"entry":entry,"exit_slot":exitslot,"n":len(rs),
        "exit_r":exit_r,"pk_r":pk_r,"pk_slot":pk_slot,"pe_r":pe_r,"pe_slot":pe_slot,
        "r10":r10,"r30":r30,"r60":r60,"slots_to_pe":slots_to_pe,"secs_to_pe":secs_to_pe,
        "last_r":last_r,"cls":cls})

print(f"{'#':<2}{'mint':<12}{'n':>4}{'exit_r':>8}{'peak_r':>8}{'postX_r':>8}{'s2pk':>6}{'r+10':>7}{'r+30':>7}{'r+60':>7}  {'class'}")
for r in rows:
    if r.get("empty"): print(f"{r['i']:<2}{r['m'][:10]:<12} EMPTY"); continue
    f=lambda x: f"{x:.2f}" if x is not None else "  -"
    print(f"{r['i']:<2}{r['m'][:10]:<12}{r['n']:>4}{f(r['exit_r']):>8}{f(r['pk_r']):>8}{f(r['pe_r']):>8}{r['slots_to_pe']:>6}{f(r['r10']):>7}{f(r['r30']):>7}{f(r['r60']):>7}  {r['cls']}")

from collections import Counter
cc=Counter(r["cls"] for r in rows if not r.get("empty"))
print("\nCLASS COUNTS:",dict(cc))
pumped=[r for r in rows if r.get("cls")=="PUMPED-AFTER-EXIT"]
print(f"PUMPED-AFTER-EXIT (post-exit peak_r>=1.3): {len(pumped)}  mints: {[r['m'][:8] for r in pumped]}")
print(f"max lifetime peak_r across 8: {max(r['pk_r'] for r in rows if not r.get('empty')):.2f}")
print(f"max post-exit peak_r across 8: {max(r['pe_r'] for r in rows if not r.get('empty')):.2f}")

# ---- Counterfactual: our actual was -0.021 SOL across 8 (exited flat r~0.98-1.04).
# Approximate sol_in per trade: unknown exactly; assume equal ~ sized. We model r-multiples only.
# Counterfactual A: "hold to peak-after-exit" (oracle upper bound).
# Counterfactual B: realistic "hold to +30 slots then market-sell" and "+60 slots".
# Counterfactual C: trail-only from peak at 85%.
FEE=0.012
def net_r(exit_mult): return exit_mult*(1-FEE)-1.0
import statistics as st
for label,key in [("sell@+10","r10"),("sell@+30","r30"),("sell@+60","r60")]:
    vals=[r[key] for r in rows if not r.get("empty") and r[key] is not None]
    nets=[net_r(v) for v in vals]
    print(f"counterfactual {label}: mean exit_mult={st.mean(vals):.3f} mean net_r(after {FEE} fee)={st.mean(nets):+.4f}  (n={len(vals)})")
# oracle post-exit peak
peaks=[r["pe_r"] for r in rows if not r.get("empty")]
print(f"ORACLE (sell exactly at post-exit peak): mean peak_mult={st.mean(peaks):.3f} mean net_r={st.mean([net_r(v) for v in peaks]):+.4f}")
json.dump(rows,open("/root/exit_timing/rows.json","w"),default=str)
