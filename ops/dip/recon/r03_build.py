#!/usr/bin/env python3
# r03: the study's own pipeline (= dd20_shadow_eval.py stage_extract -> stage_days -> stage_dd1, code imported unchanged, read-only)
# on a recording window -> WORK/<tag>/day_<TAG>.npz (+meta) and dd1_<TAG>.npz (the replay rows WITH our own trades in the tape,
# i.e. exactly how the earlier paper numbers were made). Our own trades are removed later, in the replay (r05).
# usage: python3 r03_build.py <tag NEW|OLD> <recording dir> <from unix> <to unix> [procs]
import sys, os, glob, json, time, shutil
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd20_shadow_eval as SH
import rlib as R

if __name__ == "__main__":
    tag, run, t0, t1 = sys.argv[1], sys.argv[2].rstrip("/"), int(sys.argv[3]), int(sys.argv[4])
    procs = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    SH.TAG = tag
    work = f"{R.WORK}/{tag}"; os.makedirs(work, exist_ok=True)
    pha = f"{work}/phaseA"
    files = []
    for f in sorted(glob.glob(f"{run}/txs/txs_*.jsonl.gz")):
        ts = int(os.path.basename(f).split("_")[1].split(".")[0])
        if t0 - 16 * 60 <= ts <= t1 + 11 * 60: files.append(f)
    T = time.time()
    print(f"{tag}: {len(files)} chunks {os.path.basename(files[0])} .. {os.path.basename(files[-1])} ({R.pkt(t0)} -> {R.pkt(t1)} PKT)", flush=True)
    if not os.path.exists(f"{work}/day_{tag}.npz"):
        if not os.path.exists(f"{pha}/.done"):
            SH.stage_extract(run, files, pha, procs); open(f"{pha}/.done", "w").write("ok")
        SH.stage_days(run, pha, work, procs)
    print(f"  day arrays done {time.time() - T:.0f} s", flush=True)
    live = sorted(glob.glob(f"{R.LIVE}/dip_*.jsonl"))
    if not os.path.exists(f"{work}/dd1_{tag}.npz"):
        SH.stage_dd1(run, work, live, procs)
    print(f"  dd1 done {time.time() - T:.0f} s", flush=True)
    shutil.rmtree(f"{work}/tmp", ignore_errors=True)
