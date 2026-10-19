import json
P="/root/gs_clean/paths.jsonl"
rows=[]
for ln in open(P):
    ln=ln.strip()
    if not ln: continue
    try: d=json.loads(ln)
    except: continue
    if not isinstance(d,dict): continue
    path=d.get("path"); 
    if not isinstance(path,list) or len(path)<2: continue
    if path[0][1]>=2.0 or d.get("peak",1)>=20.0 and path[0][1]>=20.0: continue
    rows.append(path)
N=len(rows)

FEE=0.0125; FIX=0.000365  # per leg %-fee + fixed
def r_at(path, ms):
    last=path[0][1]
    for t,r in path:
        if t>=ms: return r
        last=r
    return last
def net_from(path, entry_r, ride=1.3, trail=0.95, cap_ms=3200):
    # returns pnl per 1 SOL, entering at entry_r (relative to floor), riding
    peak=entry_r; riding=False; exit_r=None
    for t,r in path:
        if t>cap_ms: break
        if r>peak: peak=r
        rr=r/entry_r
        pk=peak/entry_r
        if not riding and rr>=ride: riding=True
        if riding and r<=peak*trail: exit_r=r; break
    if exit_r is None:
        # exit at last point within cap
        exit_r=[r for t,r in path if t<=cap_ms][-1]
    gross=exit_r/entry_r
    return gross*(1-FEE) - (1+0 ) *1 - FEE  - 2*FIX  # approx: sell proceeds net - buy cost - fees

# cleaner pnl: buy 1 SOL at entry_r, get 1/entry_r*(1-fee-slip) tokens... use r-ratio directly
def pnl(path, entry_r, ride=1.3, trail=0.95, cap_ms=3200):
    peak=entry_r; riding=False; exit_r=None
    for t,r in path:
        if t>cap_ms: break
        if r>peak: peak=r
        if not riding and r/entry_r>=ride: riding=True
        if riding and r<=peak*trail: exit_r=r; break
    if exit_r is None:
        within=[r for t,r in path if t<=cap_ms]; exit_r=within[-1] if within else entry_r
    ratio=exit_r/entry_r
    return ratio*(1-FEE) - (1+FEE) - 2*FIX

def stats(vals):
    v=sorted(vals); n=len(v)
    if not n: return "n=0"
    import statistics
    tot=sum(v); mean=tot/n; med=v[n//2]; win=100*sum(1 for x in v if x>0)/n
    return f"n={n} tot={tot:+.1f} mean={mean:+.4f} med={med:+.4f} win={win:.0f}%"

# runners
runners=set(i for i,p in enumerate(rows) if max(r for _,r in p)>=2.0)
print(f"clean N={N}, runners(peak>=2)={len(runners)}")
print("\n=== FLOOR entry on ALL (baseline) ===")
base=[pnl(p,1.0) for p in rows]
print(stats(base), f" runners-caught=100%")

for thr in [1.03,1.05,1.10,1.20]:
    bought=[]; caught=0
    for i,p in enumerate(rows):
        r250=r_at(p,300)
        if r250>=thr:
            bought.append(pnl(p, r250))   # enter at the moved price (lose floor)
            if i in runners: caught+=1
    print(f"\n=== WAIT ~300ms, buy if r>={thr} (enter at moved price) ===")
    print(stats(bought), f" bought={len(bought)}/{N} ({100*len(bought)/N:.0f}%) runners-caught={caught}/{len(runners)} ({100*caught/max(1,len(runners)):.0f}%)")
