#!/usr/bin/env python3
"""CPU and memory of the Go dipmon UI in a pty (80x24, 1 s refresh, default load duty), the Python tests' cases:
  (a) the initial load of a finished run (AMS r24: 59 MB records + 2.2 MB log; AMS r26: 48 MB + 2 MB): wall, CPU, peak share
  (b) after the load, PERF_SECS (60) at 1 Hz on the finished file: CPU % of one core, RSS (and the peak RSS)
  (c) following a live run: r26 replayed from 50% at 1x real time (fake engine): CPU %, RSS
  (d) the same at 10x real time (a stress case)
  (e) --snapshot on r24: wall / CPU / max RSS
  (f) Go only: (c) with --no-anim (the share of the animations; the Python dipmon has none)
--python also measures the Python dipmon v1 (the oracle) the same way, for comparison. CPU from /proc/<pid>/task/*/schedstat
(ns), RSS from /proc/<pid>/status. Targets: (b) and (c) < 2% of one core, RSS < 80 MB."""
import argparse
import glob
import os
import resource
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ptygo import Pty  # noqa: E402

DATA = os.environ.get("DIPMON_DATA", "/home/moiz/sniper-data/runs")
BIN = os.environ.get("DIPMON_BIN", "/home/moiz/sniper-data/tui/dipmon-go")
ORACLE = os.path.join(HERE, "oracle", "dipmon_v1.py")
SECS = float(os.environ.get("PERF_SECS", "60"))


def cpu_ns(pid):
    tot = 0
    for f in glob.glob(f"/proc/{pid}/task/*/schedstat"):
        try:
            tot += int(open(f).read().split()[0])
        except Exception:
            pass
    return tot


def run_ui(cmd, args, label, rate_file=None):
    p = Pty(cmd[0], cmd[1:] + args + ["--usd", "100"], 24, 80, env={"TERM": "xterm-256color"})
    t0 = time.time()
    peak, last, lt, load_end = 0.0, 0, t0, None
    while time.time() - t0 < 300:
        p.pump(0.25)
        c = cpu_ns(p.pid)
        now = time.time()
        if now - lt >= 0.5:
            peak = max(peak, (c - last) / 1e9 / (now - lt))
            last, lt = c, now
        txt = p.text()
        if "RUN P&L" in txt and "loading" not in txt:
            load_end = time.time() - t0
            break
    load_cpu = cpu_ns(p.pid) / 1e9
    p.pump(3.0)
    c0, t1 = cpu_ns(p.pid), time.time()
    s0 = os.path.getsize(rate_file) if rate_file else 0
    p.pump(SECS)
    c1, t2 = cpu_ns(p.pid), time.time()
    s1 = os.path.getsize(rate_file) if rate_file else 0
    rss, hwm = p.rss()
    p.send("q", 0.3)
    p.wait(20)
    cpu = (c1 - c0) / 1e9 / (t2 - t1) * 100
    print(f"  {label:<46} load {load_end or -1:5.2f} s wall, {load_cpu:5.2f} s cpu, peak {peak * 100:4.0f}% | after: cpu {cpu:5.3f}% of one core, "
          f"rss {rss / 1e6:5.1f} MB (peak {hwm / 1e6:5.1f})" + (f" | records +{(s1 - s0) / (t2 - t1) / 1e3:.1f} KB/s" if rate_file else ""), flush=True)
    return dict(load=load_end, load_cpu=load_cpu, cpu=cpu, rss=rss, hwm=hwm)


def snapshot(cmd, path):
    t0 = time.time()
    pr = subprocess.Popen(cmd + ["--file", path, "--snapshot", "--usd", "100"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _, _, ru = os.wait4(pr.pid, 0)
    print(f"  wall {time.time() - t0:.2f} s, cpu {ru.ru_utime + ru.ru_stime:.2f} s, max rss {ru.ru_maxrss / 1e3:.0f} MB", flush=True)
    return ru


def measure(cmd, name, go=False):
    res = {}
    r24 = os.path.join(DATA, "ams/runs/dip_ams_r24.jsonl")
    r26 = os.path.join(DATA, "ams/runs/dip_ams_r26.jsonl")
    print(f"[{name}] (a)+(b) finished runs, {SECS:.0f} s after the load:", flush=True)
    res["r24"] = run_ui(cmd, ["--file", r24], "AMS r24 (59 MB + 2.2 MB, 4 sessions)")
    res["r26"] = run_ui(cmd, ["--file", r26], "AMS r26 (48 MB + 2.1 MB)")
    cases = [(1, "live1", []), (10, "live10", [])] + ([(1, "live1na", ["--no-anim"])] if go else [])
    for speed, key, extra in cases:
        tmp = tempfile.mkdtemp(prefix="dipmon-go-p-")
        rep = subprocess.Popen([sys.executable, os.path.join(HERE, "replay.py"), r26, tmp, "--from-frac", "0.5", "--speed", str(speed),
                                "--fake-engine", "--split-every", "0", "--quiet"], stdout=subprocess.DEVNULL)
        jp = os.path.join(tmp, "dip_ams_r26.jsonl")
        while not (os.path.exists(jp) and os.path.getsize(jp) > 20e6):
            time.sleep(0.2)
        time.sleep(1.0)
        letter = "f" if extra else ("c" if speed == 1 else "d")
        print(f"[{name}] ({letter}) following r26 replayed at {speed}x real time from 50% (fake engine){' ' + ' '.join(extra) if extra else ''}:",
              flush=True)
        res[key] = run_ui(cmd, ["--dir", tmp] + extra, f"live, {speed}x the engine's write rate" + (", " + " ".join(extra) if extra else ""),
                          rate_file=jp)
        rep.terminate()
        rep.wait()
        for f in os.listdir(tmp):
            os.unlink(os.path.join(tmp, f))
        os.rmdir(tmp)
    print(f"[{name}] (e) --snapshot (text) on AMS r24:", flush=True)
    res["snap"] = snapshot(cmd, r24)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", action="store_true", help="also measure the Python dipmon v1")
    a = ap.parse_args()
    go = measure([BIN], "Go dipmon v3", go=True)
    if a.python:
        measure([sys.executable, ORACLE], "Python dipmon v1")
    ok = all(go[k]["cpu"] < 2.0 and go[k]["rss"] < 80e6 for k in ("r24", "r26", "live1"))
    print("RESULT:", "PASS" if ok else "FAIL (a target missed)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
