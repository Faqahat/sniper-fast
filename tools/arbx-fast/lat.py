import json, glob, subprocess, sys, collections
d=sys.argv[1]
def rd(name):
    for f in sorted(glob.glob(f"{d}/{name}.*.jsonl.zst")):
        for l in subprocess.run(["zstdcat",f],capture_output=True).stdout.decode(errors="ignore").splitlines():
            try: o=json.loads(l)
            except: continue
            if "attempt" in o: yield o
def pct(a):
    a=sorted(a); n=len(a)
    return "n=%d p10 %.3f p50 %.3f p90 %.3f p99 %.3f ms" % (n,a[n//10],a[n//2],a[n*9//10],a[min(n-1,n*99//100)]) if n else "n=0"
A=list(rd("attempts"))
by=collections.defaultdict(list); upd=collections.defaultdict(list); kinds=collections.Counter(); hel=0; ok=0
for a in A:
    k=(a.get("trigger") or {}).get("kind"); kinds[k]+=1
    s=a.get("stages") or {}
    if a.get("helius_big"): hel+=1
    if (a.get("dry_run") or {}).get("checks_ok"): ok+=1
    if s.get("t_first_shred") and s.get("t_signed"): by[k].append((s["t_signed"]-s["t_first_shred"])/1e6)
    if s.get("t_update_recv") and s.get("t_signed"): upd[k].append((s["t_signed"]-s["t_update_recv"])/1e6)
print(d, "would-sends", len(A), "| kinds", dict(kinds), "| big gaps to Helius", hel, "| dry-run checks ok", ok)
for k,v in by.items(): print("  %-8s first shred -> signed: %s" % (k, pct(v)))
for k,v in upd.items(): print("  %-8s 'update recv' -> signed: %s" % (k, pct(v)))
