# Health line for the 8-hour collector (read-only, runs on the server as root).
import json, time, subprocess
R = open("/root/sniper-collect/current_run").read().strip(); d = "/root/sniper-collect/" + R
try: s = json.load(open(d + "/status.json"))
except Exception as e: print("NO STATUS", R, e); raise SystemExit(2)
alive = subprocess.run(["pgrep", "-f", "python3 -I collect.py"], capture_output=True).returncode == 0
age = time.time() - s.get("now", s.get("start_time", 0)); st = s.get("stats", {})
du = subprocess.run(["du", "-sh", d], capture_output=True, text=True).stdout.split()[0]
free = subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout.splitlines()[1].split()[3]
mem = subprocess.run(["free", "-m"], capture_output=True, text=True).stdout.splitlines()[1].split()
el = (time.time() - s["start_time"]) / 3600
print(f"{R} alive={alive} phase={s.get('phase')} elapsed={el:.2f}h status_age={age:.0f}s lag={s.get('lag_slots')}slots launches={st.get('launches', 0)} "
      f"txs={st.get('txs', 0)} enriched={st.get('enriched', 0)} enrich_q={s.get('enrich_queue')} blocks_ok={st.get('blocks_ok', 0)} skipped={st.get('blocks_skipped', 0)} "
      f"failed={st.get('blocks_failed', 0)} parse_err={st.get('blocks_parse_err', 0)} rpc429={st.get('rpc_429', 0)} rpc_err={st.get('rpc_err', 0)} jito_err={st.get('jito_err', 0)} "
      f"disk_run={du} disk_free={free} mem_used={mem[2]}MB")
# final snapshot pass (final_pass.py), if started
import os
fl = "/root/sniper-collect/" + R + ".final.log"
if os.path.exists(fl):
    fp = subprocess.run(["pgrep", "-f", "final_pass.py"], capture_output=True).returncode == 0
    nf = sum(1 for _ in open(d + "/final.jsonl"))
    last = (open(fl).read().strip().splitlines() or [""])[-1][:200]
    print(f"FINAL PASS running={fp} snapshots={nf}/{s.get('tracked_mints') or 25493} last_log: {last}")
