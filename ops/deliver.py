import sys; sys.path.insert(0,"/root")
from stress import run, N, RUN2, RUN3, kept

def frontier(S, pfail=0.03, cap=True, fee=1.0, metric='mean'):
    # find min p_floor where metric>=0 via fine sweep
    lo=None
    prev=None
    for i in range(0,101):
        pf=i/100.0
        r=run(p_floor=pf,S=S,impact=True,p_fail=pfail,cap_on=cap,fee_mult=fee)
        val=r['mean'] if metric=='mean' else r['exdec']
        if val>=0 and lo is None:
            lo=pf
            break
    return lo

print("="*70)
print("A. BREAK-EVEN FRONTIER  (impact ON, p_fail=0.03, cap reverts ON)")
print("   min p_floor (same-slot floor-landing rate) for net>=0")
print(f"{'size SOL':>9} | {'min p_floor (mean>=0)':>22} | {'min p_floor (ex-decile>=0, ROBUST)':>34}")
for S in [0.05,0.1,0.2,0.5,1.0]:
    bm=frontier(S,metric='mean'); be=frontier(S,metric='exdec')
    print(f"{S:>9} | {str(bm):>22} | {str(be):>34}")

print("\n"+"="*70)
print("B. RUNNER-REVERT TRAP  (size 0.1, impact ON, p_fail=0.03, cap ON)")
print(f"{'p_floor':>8} | {'R2 captured%':>12} {'R3 captured%':>12} | {'revert%':>8} | {'mean/l':>9} {'ex-decile':>10}")
for pf in [0.9,0.8,0.72,0.6,0.5,0.4,0.35,0.3,0.2,0.1]:
    r=run(p_floor=pf,S=0.1,impact=True,p_fail=0.03,cap_on=True)
    print(f"{pf:>8} | {r['r2cap']:>12.0f} {r['r3cap']:>12.0f} | {r['revpct']:>8.1f} | {r['mean']:>+9.5f} {r['exdec']:>+10.5f}")

print("\n"+"="*70)
print("C. SIZE SENSITIVITY  (p_floor=0.5, impact ON, p_fail=0.03, cap ON)")
print(f"{'size':>6} | {'mean/l SOL':>11} {'net/SOL':>9} {'median':>9} {'win%':>6} {'ex-decile':>10}")
for S in [0.05,0.1,0.2,0.5,1.0]:
    r=run(p_floor=0.5,S=S,impact=True,p_fail=0.03,cap_on=True)
    print(f"{S:>6} | {r['mean']:>+11.5f} {r['nps']:>+9.4f} {r['med']:>+9.5f} {r['win']:>6.1f} {r['exdec']:>+10.5f}")

print("\n"+"="*70)
print("D. RECONCILE: sweep p_floor at realistic size 0.1 (mean/l & net/SOL)")
print(f"{'p_floor':>8} | {'mean/l':>9} {'net/SOL':>9} {'win%':>6} {'ex-decile':>10}  note")
for pf in [0.8,0.6,0.5,0.4,0.3,0.25,0.2,0.15,0.1]:
    r=run(p_floor=pf,S=0.1,impact=True,p_fail=0.03,cap_on=True)
    note=""
    if 0.1<=pf<=0.3: note="<- our live fill band (10-30%)"
    if pf==0.8: note="<- 4yFAz landing band"
    print(f"{pf:>8} | {r['mean']:>+9.5f} {r['nps']:>+9.4f} {r['win']:>6.1f} {r['exdec']:>+10.5f}  {note}")
