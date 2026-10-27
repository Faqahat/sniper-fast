#!/usr/bin/env python3
# PRE-SEND V2 (agent 10-25 PKT). Build the study's tape (day arrays) for a span of a raw collector run, with the study's own
# code, unchanged: ops/select/a_extract.py (phase A) -> ops/strategies/patterns/p1_build.py (stage a / b / concat), exactly as
# ps11_shadow_eval.py does (its stage_extract / stage_days are imported). Read-only on the recording; writes only to --work.
# usage: nice python3 b1_tape.py --run /home/moiz/sniper-data/collect/run_20261024_1425 --work /home/moiz/sniper-data/presend_v2/tape_R4
#            [--from "MM-DD HH:MM"] [--to "MM-DD HH:MM"] [--procs 5] [--min-age 180]
import sys, os, glob, time, argparse, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import ps11_shadow_eval as S

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--from", dest="t_from"); ap.add_argument("--to", dest="t_to")
    ap.add_argument("--procs", type=int, default=5); ap.add_argument("--min-age", type=int, default=180)
    a = ap.parse_args()
    run = a.run.rstrip("/"); os.makedirs(a.work, exist_ok=True)
    now = time.time()
    files = sorted(glob.glob(f"{run}/txs/txs_*.jsonl.gz"))
    files = [f for f in files if now - os.path.getmtime(f) > a.min_age]
    ts = lambda f: int(os.path.basename(f).split("_")[1].split(".")[0])
    if a.t_from: files = [f for f in files if ts(f) >= S.pk(a.t_from) - 16 * 60]
    if a.t_to: files = [f for f in files if ts(f) <= S.pk(a.t_to) + 11 * 60]
    S.say(f"tape build: {len(files)} chunks {os.path.basename(files[0])} .. {os.path.basename(files[-1])} "
          f"({S.pkt(ts(files[0]))} .. {S.pkt(ts(files[-1]) + 300)} PKT) -> {a.work}")
    t0 = time.time()
    pha = f"{a.work}/phaseA"
    if not os.path.exists(f"{pha}/.done"):
        S.stage_extract(run, files, pha, a.procs); open(f"{pha}/.done", "w").write("ok")
    S.say(f"  phase A done {time.time() - t0:.0f} s")
    S.stage_days(run, pha, a.work, a.procs)
    S.say(f"  day arrays done {time.time() - t0:.0f} s")
    shutil.rmtree(pha, ignore_errors=True); shutil.rmtree(f"{a.work}/tmp", ignore_errors=True)
    open(f"{a.work}/build.txt", "w").write("\n".join(S.LOG) + f"\nchunks {[os.path.basename(f) for f in files]}\n")
    S.say("TAPE_DONE")
