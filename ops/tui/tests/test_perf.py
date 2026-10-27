#!/usr/bin/env python3
"""CPU and memory of dipmon's curses UI in a pty (80x24, 1 s refresh, default load duty):
  (a) initial load of finished runs (AMS r24: 59 MB records + 2 MB log; AMS r26: 48 MB + 2 MB): wall time, CPU seconds, peak share
  (b) after the load, 60 s at 1 Hz on the finished file: CPU % of one core, RSS (and the peak RSS)
  (c) following a live run: r26 replayed from 50% at 1x real time (fake engine), 60 s after the load: CPU %, RSS
  (d) the same at 10x real time (a stress case: ~10x the engine's record rate)
  (e) --snapshot on r24: wall / CPU
Targets: (b) and (c) < 2% of one core, RSS < 80 MB. Numbers from this dev machine; a busy 2-core server is slower per op."""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ptyrun import Pty  # noqa: E402

DATA = os.environ.get("DIPMON_DATA", "/home/moiz/sniper-data/runs")
HZ = os.sysconf("SC_CLK_TCK")
SECS = float(os.environ.get("PERF_SECS", "60"))


def run_ui(args, label, rate_file=None):
    p = Pty(args + ["--usd", "100"], 24, 80, env={"TERM": "xterm-256color"})
    t0 = time.time()
    peak = 0.0
    last, lt = 0, t0
    load_end = None
    while time.time() - t0 < 300:
        p.pump(0.25)
        c = p.cpu_ticks() or last
        now = time.time()
        if now - lt >= 0.5:
            peak = max(peak, (c - last) / HZ / (now - lt))
            last, lt = c, now
        if "RUN P&L" in p.text():
            load_end = time.time() - t0
            break
    load_cpu = (p.cpu_ticks() or 0) / HZ
    p.pump(3.0)                                   # settle (the first ticks after the load catch up)
    c0, t1 = p.cpu_ticks(), time.time()
    s0 = os.path.getsize(rate_file) if rate_file else 0
    p.pump(SECS)
    c1, t2 = p.cpu_ticks(), time.time()
    s1 = os.path.getsize(rate_file) if rate_file else 0
    rss, hwm = p.rss()
    p.send("q", 0.3)
    p.wait(20)
    cpu = (c1 - c0) / HZ / (t2 - t1) * 100
    print(f"  {label:<44} load {load_end:5.1f} s wall, {load_cpu:5.2f} s cpu, peak {peak * 100:4.0f}% | after: cpu {cpu:4.2f}% of one core, "
          f"rss {rss / 1e6:5.1f} MB (peak {hwm / 1e6:5.1f})" + (f" | records +{(s1 - s0) / (t2 - t1) / 1e3:.1f} KB/s" if rate_file else ""), flush=True)
    return dict(load=load_end, load_cpu=load_cpu, cpu=cpu, rss=rss, hwm=hwm)


def main():
    res = {}
    r24 = os.path.join(DATA, "ams/runs/dip_ams_r24.jsonl")
    r26 = os.path.join(DATA, "ams/runs/dip_ams_r26.jsonl")
    print(f"(a)+(b) finished runs, {SECS:.0f} s after the load:")
    res["r24"] = run_ui(["--file", r24], "AMS r24 (59 MB + 2.2 MB, 4 sessions)")
    res["r26"] = run_ui(["--file", r26], "AMS r26 (48 MB + 2.1 MB)")
    for speed, key in ((1, "live1"), (10, "live10")):
        tmp = tempfile.mkdtemp(prefix="dipmon-p-")
        rep = subprocess.Popen([sys.executable, os.path.join(HERE, "replay.py"), r26, tmp, "--from-frac", "0.5", "--speed", str(speed),
                                "--fake-engine", "--split-every", "0", "--quiet"], stdout=subprocess.DEVNULL)
        jp = os.path.join(tmp, "dip_ams_r26.jsonl")
        while not (os.path.exists(jp) and os.path.getsize(jp) > 20e6):
            time.sleep(0.2)
        time.sleep(1.0)
        print(f"({'c' if speed == 1 else 'd'}) following r26 replayed at {speed}x real time from 50% (fake engine):")
        res[key] = run_ui(["--dir", tmp], f"live, {speed}x the engine's write rate", rate_file=jp)
        rep.terminate()
        rep.wait()
        for f in os.listdir(tmp):
            os.unlink(os.path.join(tmp, f))
        os.rmdir(tmp)
    print("(e) --snapshot (text) on AMS r24:")
    t0 = time.time()
    pr = subprocess.Popen([sys.executable, os.path.join(ROOT, "dipmon.py"), "--file", r24, "--snapshot", "--usd", "100"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _, _, ru = os.wait4(pr.pid, 0)                # this child's own usage (RUSAGE_CHILDREN would report the largest child ever)
    pr.returncode = 0
    print(f"  wall {time.time() - t0:.2f} s, cpu {ru.ru_utime + ru.ru_stime:.2f} s, max rss {ru.ru_maxrss / 1e3:.0f} MB")
    ok = all(res[k]["cpu"] < 2.0 and res[k]["rss"] < 80e6 for k in ("r24", "r26", "live1"))
    print("RESULT:", "PASS" if ok else "FAIL (a target missed)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
