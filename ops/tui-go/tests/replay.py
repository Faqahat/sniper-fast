#!/usr/bin/env python3
"""Replay a finished dip run (<TAG>.jsonl + <TAG>.log) into a directory the way the engine writes them, for dipmon's tests.

  replay.py SRC.jsonl OUTDIR [--speed 50] [--until-frac F] [--from-frac F] [--fake-engine] [--dip20] [--name TAG]

  --speed X        X times real time (the run's own clock: record times; log lines placed by their RUNTIME-lag minute)
  --until-frac F   write up to fraction F of the run's time instantly, then exit (a mid-run copy)
  --from-frac F    write up to F instantly, then continue at --speed
  --fake-engine    a sleeping process whose command line carries "--dip-log OUTDIR/TAG.jsonl" (dipmon finds the engine by it)
  --kill-engine-at F  stop the fake engine at fraction F (before the end lines: "engine gone")
  --dip20          add dip20 QUIET lines / record fields (the engine's formats, src/bin/snipe_engine/pslive.rs): a demo of the
                   QUIET view; accounting is unchanged (only skips / stops of windows that never filled are added)
  --split-every N  every Nth write leaves a record without its newline for ~30 ms (dipmon must hold the partial line)
"""
import argparse
import datetime as dt
import heapq
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time

PKT = dt.timezone(dt.timedelta(hours=5))


def t_of(line):
    i = line.rfind(b'"t":')
    if i < 0:
        return None
    i += 4
    j = i
    while j < len(line) and 48 <= line[j] <= 57:
        j += 1
    return int(line[i:j]) if j > i else None


def hhmm(ns):
    return dt.datetime.fromtimestamp(ns / 1e9, PKT).strftime("%H:%M")


def load(src_jsonl, src_log):
    jl = open(src_jsonl, "rb").read().split(b"\n")
    if jl and jl[-1] == b"":
        jl.pop()
    jt, last = [], 0
    starts = []
    for ln in jl:
        t = t_of(ln)
        if b'"ev":"run_start"' in ln and t:
            starts.append(t)
        last = max(last, t or 0)
        jt.append(last)
    first = next((t for t in jt if t), 0)
    jt = [t or first for t in jt]
    ll = open(src_log, "rb").read().split(b"\n") if os.path.exists(src_log) else []
    if ll and ll[-1] == b"":
        ll.pop()
    # log lines: placed by session (its "DIP LIVE |" line = the next run_start) and by minute (one RUNTIME lag line a minute)
    lt = []
    sess = -1
    out_minutes = []
    for ln in ll:
        if ln.startswith(b"DIP LIVE |"):
            sess += 1
        out_minutes.append((sess, ln.lstrip().startswith(b"RUNTIME lag")))
    # count lines per (session, minute) to spread them inside the minute
    cur_s, cur_m, idx = -2, 0, []
    for sess, rt in out_minutes:
        if sess != cur_s:
            cur_s, cur_m = sess, 0
        idx.append((sess, cur_m))
        if rt:
            cur_m += 1
    counts = {}
    for k in idx:
        counts[k] = counts.get(k, 0) + 1
    seen = {}
    prev = first
    for k in idx:
        sess, m = k
        t0 = starts[sess] if 0 <= sess < len(starts) else (starts[0] if starts else first)
        n = seen.get(k, 0)
        seen[k] = n + 1
        t = int(t0 + (m + n / max(1, counts[k])) * 60e9)
        t = max(t, prev)
        lt.append(t)
        prev = t
    return jl, jt, ll, lt, starts


def inject_dip20(jl, jt, ll, lt, starts):
    """QUIET (dip20) lines and fields, in the engine's formats; accounting unchanged"""
    rnd = random.Random(7)
    on_at = [s + 60 * 60e9 for s in starts]
    sess_of_t = lambda t: max([i for i, s in enumerate(starts) if s <= t] or [0])
    njl, njt = [], []
    st = {"skips": 0, "stops": 0, "would": 0}
    events = []                                  # (t, log line) to add to the log
    filled_w = set()
    for ln in jl:
        if b'"ev":"presend_live_fill"' in ln:
            m = re.search(rb'"w":(\d+)', ln)
            if m:
                filled_w.add(int(m.group(1)))
    for ln, t in zip(jl, jt):
        if b'"ev":"run_start"' in ln:
            o = json.loads(ln)
            if isinstance(o.get("presend_live"), dict):
                o["presend_live"]["quiet"] = {"stop": "6:2", "skip": True, "hist_h": 24.0, "fol": 2.24, "warmup_min": 60.0,
                                              "fbots": "/root/dip/fbots_frozen.json", "preload": None}
            ln = json.dumps(o, separators=(",", ":"), sort_keys=True).encode()
        elif b'"ev":"presend_live_arm"' in ln:
            o = json.loads(ln)
            s = sess_of_t(t)
            on = t >= on_at[s]
            q = {"since_last": rnd.randint(0, 9), "coh_hold": rnd.randint(0, 2), "fb_n": rnd.randint(0, 3), "wh_fol": round(rnd.uniform(0, 4), 2),
                 "wh_dumps": rnd.randint(0, 6), "rule_on": on, "stop": "6:2"}
            if not on and rnd.random() < 0.15:
                q["would_skip"] = True
                st["would"] += 1
            o["quiet"] = q
            o["quiet_skip"] = False
            ln = json.dumps(o, separators=(",", ":"), sort_keys=True).encode()
            if on and rnd.random() < 0.18:       # an extra trigger the arm rule skipped
                trig = dict(o.get("trig") or {})
                trig["mint"] = "Qu1etSk1pDemo" + str(rnd.randint(10 ** 9, 10 ** 10)) + "pump"
                sk = {"ev": "presend_live_skip", "why": "quiet", "trig": trig, "quiet": dict(q, since_last=4, coh_hold=0, fb_n=0, wh_fol=0.5), "quiet_skip": True}
                njl.append(json.dumps(sk, separators=(",", ":"), sort_keys=True).encode())
                njt.append(t)
                st["skips"] += 1
                events.append((t, f"  PRESEND LIVE QUIET SKIP {trig['mint']} whale {str(trig.get('wallet', 'x' * 8))[:8]} {trig.get('pct', 7.0):.1f}% "
                                  f"({(trig.get('sol') or 2e9) / 1e9:.2f} SOL) | since last trade 4 slots, cohort holders 0, follower bots 0, "
                                  f"whale's dumps drew 0.50 (3)".encode()))
        elif b'"ev":"presend_live_disarm"' in ln and b'"why":"expired"' in ln:
            o = json.loads(ln)
            s = sess_of_t(t)
            if t >= on_at[s] and o.get("w") not in filled_w and rnd.random() < 0.25:
                o["why"] = "quiet"
                st["stops"] += 1
                ln = json.dumps(o, separators=(",", ":"), sort_keys=True).encode()
                events.append((t, f"  PRESEND LIVE QUIET STOP w{o.get('w')} {o.get('mint')}: 1 other trade(s) since the trigger by slot +6 "
                                  f"(needs 2 by +6): no more attempts".encode()))
        njl.append(ln)
        njt.append(t)
    # log: the QUIET start line, the status lines' QUIET part
    nll, nlt = [], []
    ev_i = 0
    events.sort()
    sess = -1
    for ln, t in zip(ll, lt):
        while ev_i < len(events) and events[ev_i][0] <= t:
            nll.append(events[ev_i][1])
            nlt.append(events[ev_i][0])
            ev_i += 1
        if ln.startswith(b"DIP LIVE |"):
            sess += 1
        if ln.lstrip().startswith(b"DIP status") and b"PRESEND LIVE" in ln and 0 <= sess < len(starts):
            on = t >= on_at[sess]
            sk = sum(1 for e in events if e[0] <= t and b"QUIET SKIP" in e[1])
            stp = sum(1 for e in events if e[0] <= t and b"QUIET STOP" in e[1])
            rule = "on" if on else f"off (warm-up until {hhmm(on_at[sess])} PKT)"
            ln = ln + (f" | QUIET: skips {sk} (would-skip in the warm-up {st['would'] if on else 0}) stops {stp} | arm rule {rule} | "
                       f"signals 812 (1.3/4.8 us p50/p99) | book 4211 dumps 1630 sellers ~1.9 MB | watches 2").encode()
        nll.append(ln)
        nlt.append(t)
        if ln.startswith(b"DIP PRESEND LIVE (") and 0 <= sess < len(starts):
            q = (f"DIP PRESEND LIVE QUIET: stop at trigger + 6 slots with < 2 other trades | skip on: all 4 signals (since_last >= 1, no "
                 f"cohort holder (462 wallets), < 2 follower bots (318 wallets), whale's dumps of the last 24 h drew < 2.24 buyers or none) | "
                 f"arm rule from {hhmm(on_at[sess])} PKT (warm-up 60 min)")
            nll.append(q.encode())
            nlt.append(t)
    while ev_i < len(events):
        nll.append(events[ev_i][1])
        nlt.append(events[ev_i][0])
        ev_i += 1
    return njl, njt, nll, nlt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("outdir")
    ap.add_argument("--speed", type=float, default=50.0)
    ap.add_argument("--until-frac", type=float)
    ap.add_argument("--from-frac", type=float, default=0.0)
    ap.add_argument("--fake-engine", action="store_true")
    ap.add_argument("--kill-engine-at", type=float)
    ap.add_argument("--dip20", action="store_true")
    ap.add_argument("--name", help="output TAG (default: the source's)")
    ap.add_argument("--split-every", type=int, default=7)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    src_log = a.src[:-6] + ".log"
    jl, jt, ll, lt, starts = load(a.src, src_log)
    if a.dip20:
        jl, jt, ll, lt = inject_dip20(jl, jt, ll, lt, starts)
    tag = a.name or os.path.basename(a.src)[:-6]
    os.makedirs(a.outdir, exist_ok=True)
    oj = os.path.join(a.outdir, tag + ".jsonl")
    ol = os.path.join(a.outdir, tag + ".log")
    for p in (oj, ol):
        open(p, "wb").close()
    t_first = min([x for x in (jt[:1] + lt[:1]) if x] or [0])
    t_last = max([x for x in (jt[-1:] + lt[-1:]) if x] or [0])
    span = max(1, t_last - t_first)
    until = t_first + a.until_frac * span if a.until_frac is not None else None
    instant = until if (until is not None and not a.from_frac) else t_first + a.from_frac * span
    kill_at = t_first + a.kill_engine_at * span if a.kill_engine_at is not None else None
    eng = None
    if a.fake_engine:
        # a sleeping python whose argv[0] is named like the engine binary and whose command line carries --dip-log
        bdir = tempfile.mkdtemp(prefix="fake-engine-")
        exe = os.path.join(bdir, "snipe_engine_dip19")
        os.symlink(sys.executable, exe)
        eng = subprocess.Popen([exe, "-c", "import time; time.sleep(10 ** 6)", "--dip-log", oj,
                                "--minutes", "720", "--cu-limit", "100000", "--cu-price-micro", "5000000"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(0.5)
        import shutil
        shutil.rmtree(bdir, ignore_errors=True)          # the process has started; the link is not needed any more
    def _stop(signum, frame):                            # SIGTERM / SIGINT: never leave the fake engine behind
        if eng is not None and eng.poll() is None:
            eng.terminate()
        sys.exit(0)
    import signal
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    stream = heapq.merge(((t, 0, i) for i, t in enumerate(jt)), ((t, 1, i) for i, t in enumerate(lt)))
    fj = open(oj, "ab", buffering=0)
    fl = open(ol, "ab", buffering=0)
    wall0 = time.time()
    t_wall_base = instant
    nwrites = 0
    pend_j, pend_l = [], []
    last_flush = time.time()

    def flush():
        nonlocal nwrites
        if pend_j:
            data = b"\n".join(pend_j) + b"\n"
            nwrites += 1
            if a.split_every and nwrites % a.split_every == 0 and len(data) > 40:
                cut = len(data) - 1 - min(25, len(pend_j[-1]) // 2)
                fj.write(data[:cut])
                time.sleep(0.03)
                fj.write(data[cut:])
            else:
                fj.write(data)
            pend_j.clear()
        if pend_l:
            fl.write(b"\n".join(pend_l) + b"\n")
            pend_l.clear()
    n_out = 0
    for t, kind, i in stream:
        if until is not None and t > until:
            break
        if kill_at is not None and eng is not None and t >= kill_at:
            flush()
            eng.terminate()
            eng.wait()
            eng = None
            if not a.quiet:
                print("fake engine stopped", flush=True)
        if t > instant:
            due = wall0 + (t - t_wall_base) / 1e9 / a.speed
            now = time.time()
            if due > now:
                flush()
                time.sleep(min(due - now, 2.0))
        (pend_j if kind == 0 else pend_l).append(jl[i] if kind == 0 else ll[i])
        n_out += 1
        if time.time() - last_flush > 0.05 or len(pend_j) > 2000:
            flush()
            last_flush = time.time()
    flush()
    fj.close()
    fl.close()
    if eng is not None and until is None:
        time.sleep(1.5)
        eng.terminate()
        eng.wait()
    elif eng is not None:
        print(f"fake engine left running: pid {eng.pid}", flush=True)
    if not a.quiet:
        print(f"replayed {n_out} lines to {a.outdir} ({tag}); last record time {t if n_out else 0}", flush=True)
    print(f"T_CUT={min(t, until) if until else t}")


if __name__ == "__main__":
    main()
