import json,sys
def pct(v,p): v=sorted(v); return v[min(len(v)-1,int(len(v)*p))] if v else float('nan')
lag=[];tot=[];n=0
for l in sys.stdin:
    d=json.loads(l); s=d.get("stages")
    if not s: continue
    n+=1; fs=s.get("t_first_shred"); up=s.get("t_update_recv"); sg=s.get("t_signed")
    if fs and up: lag.append((up-fs)/1e6)
    if fs and sg: tot.append((sg-fs)/1e6)
print(f"attempts {n}; first shred -> account update: p10 {pct(lag,.1):.2f} p50 {pct(lag,.5):.2f} p90 {pct(lag,.9):.2f} ms (n={len(lag)}); first shred -> signed: p50 {pct(tot,.5):.2f} p90 {pct(tot,.9):.2f} ms")
