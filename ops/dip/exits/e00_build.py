#!/usr/bin/env python3
# EXIT STUDY e00: tape + dump rows for one recording window, with the study's own pipeline imported UNCHANGED
# (dd20_shadow_eval.stage_extract -> stage_days -> dd1_build.main), exactly as recon/r03_build.py does, but into
# /home/moiz/sniper-data/exits/<TAG>. Read-only on every input.
#   - day_<TAG>.npz (+meta): every trade of the window's standard launches, chain order, causal features (p1_build)
#   - dd1_<TAG>.npz: every >= 2% dump row (features X, IMIT1 score f1 where known, paper replay at 0.55 SOL; we only use the rows,
#     features and scores here; P&L is recomputed by the exit study's own corrected replay at 0.35 SOL)
# IMIT1 scores: imit2 replay rows (R3 windows, to 10-24 16:27 PKT) + every local copy of the live engines' dump records.
# usage: nice python3 -I e00_build.py <TAG> <recording dir> "<from MM-DD HH:MM PKT>" "<to MM-DD HH:MM PKT>" [procs] [imit2 wins, comma]
import sys, os, glob, time, shutil, calendar
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd20_shadow_eval as SH

OUT = "/home/moiz/sniper-data/exits"
LIVE_DIRS = ["/home/moiz/sniper-data/recon/live"]          # freshest copies (FRA r10-r15, AMS r9-r14); speed/ copies are read by dd1_build itself


def pk(s):
    return calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000


def pkt(t):
    return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 5 * 3600))


if __name__ == "__main__":
    tag, run, a, b = sys.argv[1], sys.argv[2].rstrip("/"), sys.argv[3], sys.argv[4]
    procs = int(sys.argv[5]) if len(sys.argv) > 5 else 5
    imit2 = [w for w in (sys.argv[6].split(",") if len(sys.argv) > 6 else []) if w]
    t0, t1 = pk(a), pk(b)
    SH.TAG = tag
    work = f"{OUT}/{tag}"; os.makedirs(work, exist_ok=True)
    pha = f"{work}/phaseA"
    files = []
    for f in sorted(glob.glob(f"{run}/txs/txs_*.jsonl.gz")):
        ts = int(os.path.basename(f).split("_")[1].split(".")[0])
        if t0 - 30 * 60 <= ts <= t1 + 16 * 60: files.append(f)
    T = time.time()
    print(f"{tag}: {len(files)} chunks {os.path.basename(files[0])} .. {os.path.basename(files[-1])} (window {pkt(t0)} -> {pkt(t1)} PKT; "
          f"extract from -30 min to +16 min)", flush=True)
    if not os.path.exists(f"{work}/day_{tag}.npz"):
        if not os.path.exists(f"{pha}/.done"):
            SH.stage_extract(run, files, pha, procs); open(f"{pha}/.done", "w").write("ok")
        SH.stage_days(run, pha, work, procs)
    print(f"  day arrays done {time.time() - T:.0f} s", flush=True)
    if not os.path.exists(f"{work}/dd1_{tag}.npz"):
        import dd1_build as DB
        DB.DAYS[tag] = work; DB.RUNDIR[tag] = os.path.basename(run); DB.IMIT2[tag] = imit2; DB.OUT = work
        os.makedirs(f"{work}/live", exist_ok=True)
        for d in LIVE_DIRS:
            for f in sorted(glob.glob(f"{d}/dip_*.jsonl")):
                dst = f"{work}/live/{os.path.basename(f)}"
                if not os.path.exists(dst): os.symlink(f, dst)
        DB.main(tag, procs)
    print(f"  dd1 done {time.time() - T:.0f} s", flush=True)
    shutil.rmtree(f"{work}/tmp", ignore_errors=True)
    shutil.rmtree(pha, ignore_errors=True)
