import json, statistics as st
from collections import Counter
d=json.load(open("/root/expanded_raw.json"))
RENT=1_493_520  # true pump bonding-curve rent-exempt min (observed, identical across bare creates)
BUNDLE_MIN=0.01  # SOL; below this = effectively no bundled buy (bare create / dust)

# pump token = pump program in create logs AND has Create instruction (suffix-independent)
pump=[]
for m,i in d.items():
    if i.get("status")!="ok": continue
    if not (i.get("pump_in_logs") and i.get("has_create_log")): continue
    g=i.get("curve_gain_lamports")
    if g is None: continue
    dev=(g-RENT)/1e9
    pump.append((m,dev,g))
print("pump create-confirmed tokens:",len(pump))

bundled=[dev for m,dev,g in pump if dev>=BUNDLE_MIN]
bare=[(m,dev) for m,dev,g in pump if dev<BUNDLE_MIN]
print(f"bundled dev buy (>= {BUNDLE_MIN} SOL): {len(bundled)}  ({100*len(bundled)/len(pump):.0f}%)")
print(f"bare/absent (< {BUNDLE_MIN} SOL): {len(bare)}  ({100*len(bare)/len(pump):.0f}%)")
for m,dev in sorted(bare): print(f"    bare: {m[:14]} dev={dev:.5f}")

def pct(a,q):
    i=(len(a)-1)*q; lo=int(i); hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(i-lo)
def report(vals,label):
    a=sorted(vals); n=len(a)
    if not n: print(label,"empty"); return
    print(f"\n[{label}] n={n}")
    print(f"  min={a[0]:.3f} p10={pct(a,.1):.3f} p25={pct(a,.25):.3f} median={st.median(a):.3f} p75={pct(a,.75):.3f} p90={pct(a,.9):.3f} max={a[-1]:.3f} mean={st.mean(a):.3f} SOL")
    for usd in (180,220):
        print(f"  @${usd}/SOL: median ${st.median(a)*usd:.0f} | p25-p75 ${pct(a,.25)*usd:.0f}-${pct(a,.75)*usd:.0f} | p10-p90 ${pct(a,.1)*usd:.0f}-${pct(a,.9)*usd:.0f}")
    c=Counter()
    for v in a: c[round(v//0.25)]+=1
    for b in sorted(c):
        lo=b*0.25; print(f"    {lo:5.2f}-{lo+0.25:5.2f} SOL: {'#'*c[b]} {c[b]}")
    print(f"  in 1.50-1.75 SOL (~$300-350): {sum(1 for v in a if 1.5<=v<1.75)} ({100*sum(1 for v in a if 1.5<=v<1.75)/n:.0f}%)")
    print(f"  in 1.0-2.0 SOL: {100*sum(1 for v in a if 1.0<=v<2.0)/n:.0f}% ; <1.0: {100*sum(1 for v in a if v<1.0)/n:.0f}% ; >=2.0: {100*sum(1 for v in a if v>=2.0)/n:.0f}% ; >=3.0: {100*sum(1 for v in a if v>=3.0)/n:.0f}%")

report([dev for m,dev,g in pump],"ALL pump create-confirmed (incl bare)")
report(bundled,"BUNDLED only (dev buy >= 0.01 SOL)")
