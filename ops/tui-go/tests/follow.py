#!/usr/bin/env python3
"""Follow test for the Go dipmon: replay AMS r26 and r27 (.jsonl + .log) into a temp dir at FOLLOW_SPEED x (default 50;
QUICK=1: 200x) with a fake engine process carrying --dip-log (dipmon finds the run the way it does on the server) and
records left without their newline now and then (tests/replay.py, the Python tests' tool). Meanwhile:
  - dipmon --snapshot --json runs every ~15 s (auto-detect): status RUNNING, counts never go backwards;
  - the UI follows it in a pty, keys pressed all along (tabs, filters, scope, unit, help, details, log modes);
  - every closed trade after the load rings the bell (sound all), at most one bell per 2 s (a burst merged), and none
    for the trades read in the initial load (the UI's --bell-log; the BEL bytes on the pty are counted too).
At the end the UI's own numbers (--exit-json) and a final snapshot equal the finished file's (Go and the Python oracle).
First: a copy whose engine dies before DIP DONE must show ENGINE GONE (+ the alert)."""
import json
import os
import shutil
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
SPEED = float(os.environ.get("FOLLOW_SPEED", "200" if os.environ.get("QUICK") else "50"))
RUNS = [x for x in os.environ.get("FOLLOW_RUNS", "26,27").split(",") if x]
FIELDS = [("total_lamports", None), ("fills", "presend"), ("wins", "presend"), ("realized", "presend"), ("rent", "presend"),
          ("fees", "presend"), ("net", "presend"), ("sent", "presend"), ("fires", "regular"), ("fills", "regular"), ("wins", "regular"),
          ("fill_pnl", "regular"), ("failed_pnl", "regular"), ("total", "regular"), ("est_now", "wallet")]


def snap(args):
    r = subprocess.run([BIN] + args + ["--snapshot", "--json", "--usd", "100", "--load-duty", "0"], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout)


def pick(j, k, sec):
    return j[k] if sec is None else j[sec][k]


def live_status(final):
    """what a live copy must show: RUNNING, or STOPPING once its planned end (by the records' own clock) has passed"""
    if final.get("started") and final.get("planned_min") and (final["started"] + final["planned_min"] * 60e9) / 1e9 < time.time():
        return "STOPPING"
    return "RUNNING"


def engine_gone(src, fails, live):
    tmp = tempfile.mkdtemp(prefix="dipmon-go-g-")
    pid = None
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), src, tmp, "--until-frac", "0.3", "--fake-engine", "--quiet"],
                           capture_output=True, text=True, timeout=180)
        pid = int(r.stdout.split("pid ")[1].split()[0]) if "pid " in r.stdout else None
        a = snap(["--dir", tmp])
        if pid:
            os.kill(pid, 15)
            pid = None
            time.sleep(0.5)
        b = snap(["--dir", tmp])
        ok = a["status"] == live and b["status"] == "ENGINE GONE" and any("engine gone" in x["text"] for x in b["alerts"])
        print(f"  engine-gone check: while the engine lives {a['status']} ({a['build']}), after it dies {b['status']}  {'ok' if ok else 'FAIL'}",
              flush=True)
        if not ok:
            fails.append("engine gone not shown")
    finally:
        if pid:
            os.kill(pid, 15)
        shutil.rmtree(tmp, ignore_errors=True)


def follow(run, fails):
    src = os.path.join(DATA, f"ams/runs/dip_ams_r{run}.jsonl")
    if not os.path.exists(src):
        print(f"no local r{run}: skipped")
        return
    final = snap(["--file", src])
    live = live_status(final)
    print(f"=== AMS r{run} at {SPEED:g}x (live status expected: {live})", flush=True)
    engine_gone(src, fails, live)
    py = json.loads(subprocess.run([sys.executable, ORACLE, "--file", src, "--snapshot", "--json", "--usd", "100", "--load-duty", "0"],
                                   capture_output=True, text=True, timeout=300).stdout)
    tmp = tempfile.mkdtemp(prefix="dipmon-go-f-")
    t0 = time.time()
    # the first quarter is written at once (trades the UI loads at start: they must never ring), the rest at SPEED
    rep = subprocess.Popen([sys.executable, os.path.join(HERE, "replay.py"), src, tmp, "--speed", str(SPEED), "--fake-engine",
                            "--split-every", "5", "--from-frac", "0.25", "--quiet"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    jp = os.path.join(tmp, f"dip_ams_r{run}.jsonl")
    target = 0.2 * os.path.getsize(src)
    while not (os.path.exists(jp) and os.path.getsize(jp) > target):
        time.sleep(0.1)
    ej, bl = os.path.join(tmp, "exit.json"), os.path.join(tmp, "bells.log")
    p = Pty(BIN, ["--dir", tmp, "--usd", "100", "--strict", "--exit-json", ej, "--bell-log", bl, "--sound", "all"], 40, 120,
            env={"TERM": "xterm-256color"})
    keys = list("1234567") + ["4", "down", "down", "enter", "esc", "f", "f", "6", "f", "w", "end", "1", "u", "u", "s", "s", "2", "3", "5",
                               "?", "x", "7", "pgdn", "home", "S", "S", "tab", "btab", "wheeldown", "wheelup"]
    ki, last_snap, prev, nsnap = 0, 0, None, 0
    while rep.poll() is None:
        p.pump(1.5)
        p.send(keys[ki % len(keys)], 0.1)
        ki += 1
        if time.time() - last_snap > 15:
            last_snap = time.time()
            try:
                j = snap(["--dir", tmp])
            except Exception as e:
                fails.append(f"snapshot failed mid-run: {e}")
                continue
            nsnap += 1
            cur = (j["presend"]["fills"], j["presend"]["sent"], j["regular"]["fires"], j["presend"]["failed_tries"])
            if j["status"] not in (live, "ENDED"):
                fails.append(f"mid-run status {j['status']}")
            if prev and any(a < b for a, b in zip(cur, prev)):
                fails.append(f"counts went backwards {prev} -> {cur}")
            prev = cur
            print(f"  {time.time() - t0:5.0f}s  {j['status']:<8} P&L {j['total_sol']:+.4f}  PS fills {cur[0]:>3} tries {cur[1]:>6}  REG buys {cur[2]:>3}",
                  flush=True)
    p.pump(3.0)
    p.send("q", 0.5)
    st = p.wait(30)
    screen = p.text()
    if st != 0 or "UI ERROR" in screen or "panic" in screen:
        fails.append(f"r{run}: UI exit {st} / UI ERROR {'UI ERROR' in screen}")
    ui = json.load(open(ej)) if os.path.exists(ej) else None
    end = snap(["--dir", tmp])
    print(f"  replay done in {time.time() - t0:.0f}s; {nsnap} snapshots mid-run; pty output {p.total:,} bytes")
    print(f"  {'figure':<20} {'Python (file)':>14} {'Go (file)':>14} {'Go UI (live)':>14} {'Go snapshot':>14}")
    for k, sec in FIELDS:
        a, b2 = pick(py, k, sec), pick(final, k, sec)
        c = pick(ui, k, sec) if ui else None
        d = pick(end, k, sec)
        ok = a == b2 == c == d
        print(f"  {(sec + '.' if sec else '') + k:<20} {a:>14} {b2:>14} {str(c):>14} {d:>14}  {'ok' if ok else 'DIFF'}")
        if not ok:
            fails.append(f"r{run} {k}: {a} / {b2} / {c} / {d}")
    if end["status"] != "ENDED":
        fails.append(f"r{run} final status {end['status']}")
    # the bell
    lines = open(bl).read().split("\n") if os.path.exists(bl) else []
    loaded = [l.split() for l in lines if l.startswith("# loaded")]
    exited = [l.split() for l in lines if l.startswith("# exit")]
    bells = [tuple(map(float, l.split())) for l in lines if l and not l.startswith("#")]
    if not loaded or not exited:
        fails.append(f"r{run}: bell log incomplete")
        return
    t_load, seq_load = float(loaded[0][2]), int(loaded[0][3])
    seq_exit = int(exited[-1][3])
    covered = sum(int(b[1]) for b in bells)
    gaps = [b2[0] - b1[0] for b1, b2 in zip(bells, bells[1:])]
    early = [b for b in bells if b[0] < t_load]
    ok = covered == seq_exit - seq_load and all(g >= 1.99 for g in gaps) and not early and p.bells == len(bells) and seq_load > 0
    print(f"  bell: {len(bells)} bells cover {covered} trades closed after the load ({seq_exit - seq_load}; {seq_load} were loaded at start "
          f"and never rang); min gap {min(gaps) if gaps else 0:.2f} s; BEL bytes on the pty {p.bells}  {'ok' if ok else 'FAIL'}")
    if not ok:
        fails.append(f"r{run}: bell check ({covered} vs {seq_exit - seq_load}, gaps {min(gaps) if gaps else 0}, early {len(early)}, "
                     f"BEL {p.bells} vs {len(bells)})")
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    if not os.path.exists(BIN):
        print(f"no binary {BIN}")
        return 1
    fails = []
    for r in RUNS:
        follow(int(r), fails)
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
