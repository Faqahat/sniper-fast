# one-line live summary of the arbx-fast campaign's current segment (read-only)
import json, glob, os, subprocess, sys, time
camp="/root/arbx-fast/runs/fastL2"
segs=sorted(glob.glob(camp+"/fastL2-p*/"), key=os.path.getmtime)
if not segs: print("no segment yet"); sys.exit()
seg=segs[-1]; name=seg.rstrip("/").split("/")[-1]
try: s=json.loads(open(seg+"status.jsonl").read().strip().splitlines()[-1])
except Exception as e: print(name, "no status yet"); sys.exit()
e=s["exec"]; m=s.get("money") or {}; b=m.get("bot") or {}; h=s["health"]
lat=[]
for f in sorted(glob.glob(seg+"attempts.*.jsonl.zst")):
    for l in subprocess.run(["zstdcat",f],capture_output=True).stdout.decode(errors="ignore").splitlines():
        try: a=json.loads(l)
        except: continue
        st=a.get("stages") or {}
        if st.get("t_first_shred") and st.get("t_signed"): lat.append((st["t_signed"]-st["t_first_shred"])/1e6)
lat.sort(); p50=f"{lat[len(lat)//2]:.2f}ms" if lat else "-"
stop=json.load(open(seg+"stop.json")).get("reason") if os.path.exists(seg+"stop.json") else None
sup=open(camp+"/supervisor.jsonl").read().strip().splitlines()[-1] if os.path.exists(camp+"/supervisor.jsonl") else "{}"
ev=json.loads(sup).get("event")
print(f"{time.strftime('%H:%M', time.gmtime())}Z {name} {int(s.get('run_s',0)//60)}m | sent {e['sent_total']} landed {e['landed_total']} ok {e['ok_total']} refused {e['refused_total']} decisions {e['decisions_total']} | "
      f"send p50 {p50} | profit(rt) {b.get('round_trip_total_lamports',0)} tips {b.get('tips_paid_total_lamports',0)} failed_fees {b.get('failed_fees_total_lamports',0)} | "
      f"equity {m.get('equity_total_now',0)/1e9:.4f} SOL budget_left {m.get('budget_left_now')} | bh {h.get('blockhash_src_now')}/{h.get('blockhash_age_slots_now')} leaders_ok {h.get('leaders_ok')}"
      + (f" | SEGMENT STOP: {stop}" if stop else "") + (f" | campaign: {ev}" if ev not in ("segment_start","start",None) else ""))
