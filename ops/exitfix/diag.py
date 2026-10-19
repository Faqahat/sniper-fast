import json,importlib.util
spec=importlib.util.spec_from_file_location("a","/root/exitfix/analyze.py")
# reuse builders by exec
g={}
exec(open("/root/exitfix/analyze.py").read().split("print(\"=== PER-TOKEN")[0],g)
T=g["T"];B=g["B"];SHORT=g["SHORT"];fwd_of=g["fwd_of"]
def r_at(fwd,tsec):
    v=None
    for t,pr in fwd:
        if t<=tsec: v=pr
    return (v/er) if v else 1.0
print(f"{'tok':4} {'maxT_s':>7} {'npts':>5} {'r@40':>6} {'r@90':>6} {'r@300':>6} {'r@end':>6} {'pk':>6} {'tpk':>5}")
for mint,m in T.items():
    b=B[mint]; fwd=fwd_of(b); er=m["entry"]
    maxT=fwd[-1][0]; 
    def ra(ts):
        v=er
        for t,pr in fwd:
            if t<=ts: v=pr
        return v/er
    pk=max(pr for _,pr in fwd)/er; pki=max(range(len(fwd)),key=lambda i:fwd[i][1]); tpk=fwd[pki][0]
    print(f"{SHORT[mint]:4} {maxT:>7} {len(fwd):>5} {ra(40):>6.2f} {ra(90):>6.2f} {ra(300):>6.2f} {fwd[-1][1]/er:>6.2f} {pk:>6.2f} {tpk:>5}")
# Gz trajectory sample
print("\nGz trajectory (t_sec, r_vs_entry) sampled:")
mint=[k for k in T if k.startswith("GzYC")][0]; fwd=fwd_of(B[mint]); er=T[mint]["entry"]
step=max(1,len(fwd)//40)
for i in range(0,len(fwd),step):
    t,pr=fwd[i]; print(f"  {t:>5}s  r={pr/er:.3f}")
