import json,glob,subprocess,sys
def rd(pat):
    out=[]
    for f in sorted(glob.glob(pat)):
        for l in subprocess.run(["zstdcat",f],capture_output=True,text=True).stdout.splitlines():
            try: d=json.loads(l)
            except: continue
            if "attempt" in d: out.append(d)
    return out
AT={d["attempt"]:d for d in rd("attempts.*.jsonl.zst") if "stages" in d}
CO={}
for d in rd("copies.*.jsonl.zst"):
    if "path" in d: CO.setdefault(d["attempt"],[]).append(d)
OU={d["attempt"]:d for d in rd("outcomes.*.jsonl.zst") if "copies" in d}
picks=[int(x) for x in sys.argv[1:]] or [79,98,5]
for a in picks:
    if a not in AT: print("no attempt",a); continue
    d=AT[a]; s=d["stages"]; exp=d.get("expected") or {}
    g=exp.get("gross",0) if isinstance(exp,dict) else exp
    L=d.get("leader") or {}
    print("\n===== attempt %d  gross %s lamports  size %.3f SOL  band %s ====="%(a,format(g,","),d.get("size_lamports",0)/1e9,d.get("band")))
    print("  leader %s kind=%s client=%s city=%s be_rtt_ms=%s"%(str(L.get("leader","?"))[:8],L.get("kind"),L.get("client"),L.get("city"),L.get("be_rtt_ms")))
    print("  trigger kind=%s feed=%s"%(d["trigger"].get("kind"),d["trigger"].get("feed")))
    base=s["t_first_shred"]; prev=None
    for k in ["t_first_shred","t_update_recv","t_commit","t_engine","t_priced","t_decided","t_build_start","t_built","t_signed","t_enqueued","t_dequeued"]:
        v=s.get(k)
        if v is None: print("    %-16s  —"%k); continue
        dp=("+%.3f"%((v-prev)/1e6)) if prev else "  —"
        print("    %-16s %8.3f ms   step %s ms"%(k,(v-base)/1e6,dp)); prev=v
    o=OU.get(a,{}); ocp={c.get("path"):c for c in o.get("copies",[])}
    print("  --- per provider: send -> ack, send -> landed ---")
    for c in sorted(CO.get(a,[]),key=lambda c:c.get("t_sent") or 0):
        p=c["path"]; ts=c.get("t_sent"); ack=c.get("ms"); oc=ocp.get(p,{})
        seen=oc.get("send_to_seen_ms"); tr=(ts-base)/1e6 if ts else float("nan")
        acks="%.3f"%ack if ack is not None else "—"; seens="%.1f"%seen if seen is not None else "—"
        print("    %-12s send@%7.3fms  ack %8s ms  send->landed %9s ms  tip %10s  qwait_us %s"%(p,tr,acks,seens,format(c.get("tip_lamports",0),","),c.get("queue_wait_us")))
    ld=o.get("landed") or {}
    print("  landed slot %s leader %s idx %s | trigger landed slot %s"%(ld.get("slot"),str(ld.get("leader"))[:8],ld.get("idx"),d["trigger"].get("slot")))
