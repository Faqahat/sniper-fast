#!/usr/bin/env python3
"""Parity: dipmon v3 (Go) --snapshot --json == the Python dipmon v1 (the oracle, pinned in tests/oracle) on every
local run (AMS r9-r27, FRA r1-r25 that exist): every field, exact (lamports are ints; floats compared exactly too,
since both print Python's repr). Also the wallet estimate and the text snapshot (diffed line by line).

  parity.py [--bin PATH] [--runs ams:27,fra:24] [--text]
The v3-only fields (ath_sol / ath_t / low_sol / low_t / from_ath_sol and the text's "ATH" line) are checked against
the oracle's series_hi / series_lo, then left out of the comparison. Exit 0 when every run matches."""
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(HERE, "oracle", "dipmon_v1.py")
ORACLE_MD5 = "9165793fed33a27f63accf4579af2712"
DATA = os.environ.get("DIPMON_DATA", "/home/moiz/sniper-data/runs")
# run copies kept for dipmon's own tests (r28: the latency run); used for the runs DATA does not have
TUI_DATA = os.environ.get("DIPMON_TUI_DATA", "/home/moiz/sniper-data/tui/runs")
BIN = os.environ.get("DIPMON_BIN", "/home/moiz/sniper-data/tui/dipmon-go")


# v3-only figures (not in the Python dipmon v1): checked against the oracle's own series_hi / series_lo (the same series'
# extremes), then removed before the diff
V3_KEYS = ("ath_sol", "ath_t", "low_sol", "low_t", "from_ath_sol")


def v3_check(go):
    """pop the v3 ATH / low fields from the Go JSON; errors when they are not series_hi / series_lo"""
    vals = {k: go.pop(k, "missing") for k in V3_KEYS}
    hi, lo = go.get("series_hi"), go.get("series_lo")
    if "missing" in vals.values():
        return ["v3: an ath / low field is missing"]
    if hi is None:
        return [] if all(v is None for v in vals.values()) else ["v3: ath / low without series_hi"]
    errs = []
    if vals["ath_sol"] != hi[0] / 1e9 or vals["ath_t"] != int(hi[1]):
        errs.append(f"v3: ath {vals['ath_sol']} @ {vals['ath_t']} != series_hi {hi}")
    if vals["low_sol"] != lo[0] / 1e9 or vals["low_t"] != int(lo[1]):
        errs.append(f"v3: low {vals['low_sol']} @ {vals['low_t']} != series_lo {lo}")
    if not vals["from_ath_sol"] <= 0:
        errs.append(f"v3: from_ath_sol {vals['from_ath_sol']} > 0")
    return errs


def strip_v3_json(txt):
    """the Go JSON text without the v3 key lines (and the comma they left), for the byte-identical check"""
    lines = txt.split("\n")
    keep = [l for l in lines if not any(l.startswith(f' "{k}": ') for k in V3_KEYS)]
    if len(keep) != len(lines):
        i = next(i for i, l in enumerate(lines) if any(l.startswith(f' "{k}": ') for k in V3_KEYS))
        if keep[i - 1].endswith(",") and keep[i].strip() == "}":
            keep[i - 1] = keep[i - 1][:-1]
    return "\n".join(keep)


def strip_v3_text(txt):
    """the Go text snapshot without its v3 "ATH ..." line"""
    return "\n".join(l for l in txt.split("\n") if not l.startswith("ATH       "))


def runs_available():
    out = []
    for region, rng, tag in (("ams", range(9, 41), "dip_ams_r{}"), ("fra", range(1, 41), "dip_r{}")):
        for n in rng:
            for d in (DATA, TUI_DATA):
                p = os.path.join(d, region, "runs", tag.format(n) + ".jsonl")
                if os.path.exists(p):
                    out.append((region, n, p))
                    break
    return out


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[:3]}... exit {r.returncode}: {r.stderr[-400:]}")
    return r.stdout


def diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b:
                out.append(f"{path}.{k}: missing in Go")
            else:
                diff(a[k], b[k], f"{path}.{k}", out)
        for k in b:
            if k not in a:
                out.append(f"{path}.{k}: extra in Go")
        if list(a) != [k for k in b if k in a]:
            out.append(f"{path}: key order differs")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out)
    else:
        if type(a) is not type(b) or a != b:
            out.append(f"{path}: py {a!r} != go {b!r}")


MIDRUN = [("26", "0.10", ["--dip20"]), ("26", "0.4", ["--dip20"]), ("27", "0.5", []), ("24", "0.7", []), ("25", "0.95", []),
          ("27", "0.02", [])]


def midrun(binary):
    """running-state copies: a run cut at a fraction of its time (replay.py; --dip20 adds the QUIET lines in the
    engine's formats), seen RUNNING (--assume-running) at the cut's time (--now): JSON and text byte-identical"""
    import tempfile
    import shutil
    bad = 0
    for run, frac, extra in MIDRUN:
        src = os.path.join(DATA, "ams/runs", f"dip_ams_r{run}.jsonl")
        if not os.path.exists(src):
            continue
        d = tempfile.mkdtemp(prefix="dipmon-go-mid-")
        try:
            r = subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), src, d, "--until-frac", frac, "--quiet"] + extra,
                               capture_output=True, text=True, timeout=300)
            t = [l for l in r.stdout.splitlines() if l.startswith("T_CUT=")][0][6:]
            now = str(int(float(t)) / 1e9)
            f = os.path.join(d, f"dip_ams_r{run}.jsonl")
            common = ["--file", f, "--snapshot", "--usd", "100", "--load-duty", "0", "--assume-running", "--now", now]
            pj, gj = run_cmd([sys.executable, ORACLE] + common + ["--json"]), run_cmd([binary] + common + ["--json"])
            pt, gt = run_cmd([sys.executable, ORACLE] + common), run_cmd([binary] + common)
            j = json.loads(pj)
            v3 = v3_check(json.loads(gj))
            gj, gt = strip_v3_json(gj), strip_v3_text(gt)
            ok = pj == gj and pt == gt and not v3
            for e in v3:
                print("   ", e)
            bad += not ok
            print(f"AMS r{run} cut at {frac}{' +dip20 QUIET lines' if extra else ''}: {j['status']}, QUIET {j['quiet']['state']}, "
                  f"armed {j['presend']['open_windows']}, P&L {j['total_lamports']}: JSON {'identical' if pj == gj else 'DIFF'}, "
                  f"text {'identical' if pt == gt else 'DIFF'}")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return bad


def run_cmd(cmd):
    return run(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=BIN)
    ap.add_argument("--runs", default="")
    ap.add_argument("--text", action="store_true", help="also diff the text snapshots")
    ap.add_argument("--no-midrun", action="store_true", help="skip the running-state copies")
    a = ap.parse_args()
    md5 = hashlib.md5(open(ORACLE, "rb").read()).hexdigest()
    if md5 != ORACLE_MD5:
        print(f"oracle md5 {md5} != {ORACLE_MD5}")
        return 1
    sel = None
    if a.runs:
        sel = {(x.split(":")[0], int(x.split(":")[1])) for x in a.runs.split(",")}
    runs = [r for r in runs_available() if sel is None or (r[0], r[1]) in sel]
    bad = 0
    nfields = 0
    for region, n, p in runs:
        common = ["--file", p, "--snapshot", "--usd", "100", "--load-duty", "0"]
        py = json.loads(run([sys.executable, ORACLE] + common + ["--json"]))
        go = json.loads(run([a.bin] + common + ["--json"]))
        out = v3_check(go)
        diff(py, go, "", out)
        nf = sum(1 for _ in walk(py))
        nfields += nf
        tdiff = []
        if a.text:
            pt = run([sys.executable, ORACLE] + common).splitlines()
            gt0 = run([a.bin] + common)
            gt = strip_v3_text(gt0).splitlines()
            if py.get("series_hi") is not None and "\nATH       " not in gt0:
                tdiff.append("text: the v3 ATH line is missing")
            if len(pt) != len(gt):
                tdiff.append(f"text: {len(pt)} vs {len(gt)} lines")
            for i, (x, y) in enumerate(zip(pt, gt)):
                if x != y:
                    tdiff.append(f"text line {i + 1}:\n    py: {x}\n    go: {y}")
        tag = f"{region.upper()} r{n}"
        tot = py.get("total_lamports")
        wal = (py.get("wallet") or {}).get("est_now")
        if out or tdiff:
            bad += 1
            print(f"{tag:<9} DIFF ({len(out)} fields{', text' if tdiff else ''})  total {tot}  wallet est {wal}")
            for x in (out + tdiff)[:25]:
                print("   ", x)
        else:
            print(f"{tag:<9} ok    {nf:>4} fields equal  total {tot:>12} lamports  wallet est {wal}" + ("  text equal" if a.text else ""))
    print(f"finished runs: {len(runs) - bad}/{len(runs)} identical ({nfields} fields compared)" + ("" if not bad else f"; {bad} differ"))
    mbad = 0 if a.no_midrun else midrun(a.bin)
    print("RESULT:", "PASS" if not (bad or mbad) else f"FAIL ({bad} finished runs, {mbad} running copies differ)")
    return 1 if (bad or mbad) else 0


def walk(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)
    else:
        yield x


if __name__ == "__main__":
    sys.exit(main())
