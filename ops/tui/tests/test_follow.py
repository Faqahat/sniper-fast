#!/usr/bin/env python3
"""Follow test: replay AMS r26 (.jsonl + .log) into a temp dir at FOLLOW_SPEED x (default 50; the run is 7 h 04 min, so ~8.5 min;
QUICK=1 uses 200x), with a fake engine process carrying --dip-log (dipmon finds the run the way it does on the server) and records
left without their newline now and then. Meanwhile:
  - dipmon --snapshot --json runs every ~20 s (auto-detect): status RUNNING, counts never go backwards;
  - the curses UI follows it in a pty (auto-detect), keys pressed all along.
At the end both the curses UI's own numbers (--exit-json) and a final snapshot equal the finished file's totals.
Then: a copy whose engine dies before DIP DONE must show ENGINE GONE (+ the alert)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import dipmon  # noqa: E402
from ptyrun import Pty  # noqa: E402

DATA = os.environ.get("DIPMON_DATA", "/home/moiz/sniper-data/runs")
SRC = os.path.join(DATA, "ams/runs/dip_ams_r26.jsonl")
SPEED = float(os.environ.get("FOLLOW_SPEED", "200" if os.environ.get("QUICK") else "50"))
FIELDS = [("total_lamports", None), ("fills", "presend"), ("wins", "presend"), ("realized", "presend"), ("rent", "presend"),
          ("fees", "presend"), ("net", "presend"), ("fires", "regular"), ("fills", "regular"), ("wins", "regular"),
          ("fill_pnl", "regular"), ("failed_pnl", "regular"), ("total", "regular")]


def snap(d, extra=()):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dipmon.py"), "--dir", d, "--snapshot", "--json", "--usd", "100", "--load-duty", "0"] + list(extra),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout)


def pick(j, k, sec):
    return j[k] if sec is None else j[sec][k]


def engine_gone(fails):
    """a copy whose (fake) engine dies before DIP DONE: RUNNING while it lives, then ENGINE GONE + the alert"""
    tmp2 = tempfile.mkdtemp(prefix="dipmon-g-")
    pid = None
    try:
        r2 = subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), SRC, tmp2, "--until-frac", "0.3", "--fake-engine", "--quiet"],
                            capture_output=True, text=True, timeout=120)
        pid = int(r2.stdout.split("pid ")[1].split()[0]) if "pid " in r2.stdout else None
        a = snap(tmp2)
        if pid:
            os.kill(pid, 15)
            pid = None
            time.sleep(0.5)
        b = snap(tmp2)
        ok = a["status"] == "RUNNING" and b["status"] == "ENGINE GONE" and any("engine gone" in x["text"] for x in b["alerts"])
        print(f"  engine-gone check: while the engine lives {a['status']}, after it dies {b['status']} "
              f"(alert: {next((x['text'] for x in b['alerts'] if 'engine' in x['text']), '-')})  {'ok' if ok else 'FAIL'}", flush=True)
        if not ok:
            fails.append("engine gone not shown")
    finally:
        if pid:
            os.kill(pid, 15)
        shutil.rmtree(tmp2, ignore_errors=True)


def main():
    if not os.path.exists(SRC):
        print("no local r26 copy: skipped")
        return 0
    fails = []
    engine_gone(fails)
    src = dipmon.Source(SRC)
    src.load_all()
    ctx = dipmon.Ctx(src, None, dipmon.Price(fixed=100.0), None)
    final = json.loads(dipmon.snapshot_json(dipmon.build_view(ctx), ctx))
    tmp = tempfile.mkdtemp(prefix="dipmon-f-")
    t0 = time.time()
    rep = subprocess.Popen([sys.executable, os.path.join(HERE, "replay.py"), SRC, tmp, "--speed", str(SPEED), "--fake-engine", "--split-every", "5", "--quiet"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    jp = os.path.join(tmp, "dip_ams_r26.jsonl")
    while not (os.path.exists(jp) and os.path.getsize(jp) > 2000):
        time.sleep(0.2)
    ej = os.path.join(tmp, "exit.json")
    p = Pty(["--dir", tmp, "--usd", "100", "--strict", "--exit-json", ej], 24, 80, env={"TERM": "xterm-256color"})
    keys = list("1234567") + ["4", "down", "enter", "esc", "f", "f", "6", "f", "w", "1", "u", "u", "2", "3", "5", "s"]
    ki = 0
    last_snap = 0
    prev = None
    nsnap = 0
    while rep.poll() is None:
        p.pump(1.5)
        p.send(keys[ki % len(keys)], 0.1)
        ki += 1
        if time.time() - last_snap > 20:
            last_snap = time.time()
            try:
                j = snap(tmp)
            except Exception as e:
                fails.append(f"snapshot failed mid-run: {e}")
                continue
            nsnap += 1
            cur = (j["presend"]["fills"], j["presend"]["sent"], j["regular"]["fires"], j["presend"]["failed_tries"])
            if j["status"] not in ("RUNNING", "ENDED"):
                fails.append(f"mid-run status {j['status']}")
            if prev and any(a < b for a, b in zip(cur, prev)):
                fails.append(f"counts went backwards {prev} -> {cur}")
            prev = cur
            print(f"  {time.time() - t0:5.0f}s  {j['status']:<8} P&L {j['total_sol']:+.4f}  PS fills {cur[0]:>3} tries {cur[1]:>6}  REG buys {cur[2]:>3}",
                  flush=True)
    p.pump(3.0)
    p.send("q", 0.5)
    st = p.wait(30)
    txt = p.text()
    if st != 0 or "Traceback" in txt or "UI ERROR" in txt:
        fails.append(f"curses UI exit {st} / traceback {'Traceback' in txt} / UI ERROR {'UI ERROR' in txt}")
    ui = json.load(open(ej)) if os.path.exists(ej) else None
    end = snap(tmp)
    print(f"  replay done in {time.time() - t0:.0f}s at {SPEED:g}x; {nsnap} snapshots mid-run; curses output {p.total:,} bytes")
    print(f"  {'figure':<22} {'finished file':>14} {'curses UI':>14} {'snapshot':>14}")
    for k, sec in FIELDS:
        a = pick(final, k, sec)
        b = pick(ui, k, sec) if ui else None
        c = pick(end, k, sec)
        ok = a == b == c
        print(f"  {(sec + '.' if sec else '') + k:<22} {a:>14} {str(b):>14} {c:>14}  {'ok' if ok else 'DIFF'}")
        if not ok:
            fails.append(f"{k}: {a} / {b} / {c}")
    if end["status"] != "ENDED":
        fails.append(f"final status {end['status']}")
    print(f"  final status {end['status']} ({end['how_ended']}); curses UI status at exit {ui['status'] if ui else '?'}")
    shutil.rmtree(tmp, ignore_errors=True)
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
