#!/usr/bin/env python3
"""FRA <-> AMS clock offset + network delay probe (read-only; runs on the HOST).

Method (labelled in the output):
  1. chrony on each server: `chronyc tracking` -> System time offset vs NTP (both servers use the same NTP source),
     root delay / dispersion. offset_ms > 0 means the server clock is AHEAD (fast) of NTP.
  2. host-hub ssh midpoint bracket: one long-lived ssh per server runs a tiny responder that answers each probe line with
     time.time_ns(); offset(server - host) = t_server - (t_send + t_recv)/2 from the lowest-RTT samples. AMS-minus-FRA =
     off(AMS-host) - off(FRA-host); worst-case error = (best RTT host-FRA + best RTT host-AMS)/2 (path asymmetry).
  3. FRA -> AMS ICMP ping RTT (one-way delay ~ RTT/2), run on FRA.
Output JSON (also printed short): {"t": host ns, "fra_sync": {...}, "ams_sync": {...}, "bracket": {...}, "ping": {...},
  "chrony_offset_ams_minus_fra_ms": float}.  bracket.offset_ms = AMS clock minus FRA clock (ms).
usage: clock_probe.py OUT.json [--n 40]
"""
import json, re, shlex, subprocess, sys, time

FRA = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-p", "1996", "it@84.32.100.36"]
AMS = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-p", "1996", "it@84.32.104.202"]
RESP = "import sys,time\nfor l in sys.stdin:\n    sys.stdout.write(str(time.time_ns())+'\\n'); sys.stdout.flush()\n"


def chrony(host):
    try:
        out = subprocess.run(host + ["chronyc tracking"], capture_output=True, text=True, timeout=20).stdout
    except Exception as e:
        return {"tool": "none", "offset_ms": None, "raw": f"error {type(e).__name__}"}
    d = {"tool": "chrony", "offset_ms": None, "root_delay_ms": None, "root_dispersion_ms": None, "raw": out.strip()[:1200]}
    m = re.search(r"System time\s*:\s*([\d.]+) seconds (fast|slow)", out)
    if m:
        v = float(m.group(1)) * 1e3
        d["offset_ms"] = v if m.group(2) == "fast" else -v
    m = re.search(r"Root delay\s*:\s*([\d.]+)", out)
    if m: d["root_delay_ms"] = float(m.group(1)) * 1e3
    m = re.search(r"Root dispersion\s*:\s*([\d.]+)", out)
    if m: d["root_dispersion_ms"] = float(m.group(1)) * 1e3
    if d["offset_ms"] is None:
        d["tool"] = "unknown"
    return d


def bracket(host, n):
    p = subprocess.Popen(host + ["python3 -u -c " + shlex.quote(RESP)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    samples = []
    try:
        # warm-up
        p.stdin.write("x\n"); p.stdin.flush(); p.stdout.readline()
        for _ in range(n):
            t0 = time.time_ns()
            p.stdin.write("x\n"); p.stdin.flush()
            line = p.stdout.readline()
            t1 = time.time_ns()
            if not line:
                break
            tr = int(line.strip())
            samples.append((t1 - t0, tr - (t0 + t1) / 2))
            time.sleep(0.03)
    finally:
        try:
            p.stdin.close(); p.wait(timeout=5)
        except Exception:
            p.kill()
    samples.sort()
    if not samples:
        return None
    best = samples[: max(1, len(samples) // 5)]
    offs = sorted(o for _, o in best)
    return {"n": len(samples), "best_rtt_ms": samples[0][0] / 1e6, "offset_ms": samples[0][1] / 1e6,
            "offset_ms_p50_best20pct": offs[len(offs) // 2] / 1e6,
            "rtt_p50_ms": sorted(r for r, _ in samples)[len(samples) // 2] / 1e6}


def ping():
    try:
        out = subprocess.run(FRA + ["ping -q -c 20 -i 0.2 -W 1 84.32.104.202"], capture_output=True, text=True, timeout=30).stdout
    except Exception as e:
        return {"error": type(e).__name__}
    m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)", out)
    if not m:
        return {"error": "no ping result", "raw": out[-300:]}
    return {"rtt_min_ms": float(m.group(1)), "rtt_avg_ms": float(m.group(2)), "rtt_max_ms": float(m.group(3)),
            "one_way_est_ms": float(m.group(1)) / 2, "from": "FRA", "to": "AMS"}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "clock_probe.json"
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 40
    t = time.time_ns()
    res = {"t": t, "fra_sync": chrony(FRA), "ams_sync": chrony(AMS)}
    bf, ba = bracket(FRA, n), bracket(AMS, n)
    if bf and ba:
        res["bracket"] = {"method": "host-hub ssh midpoint (min-RTT samples)", "n": min(bf["n"], ba["n"]),
                          "best_rtt_ms": bf["best_rtt_ms"] + ba["best_rtt_ms"],
                          "offset_ms": ba["offset_ms"] - bf["offset_ms"],
                          "offset_ms_p50": ba["offset_ms_p50_best20pct"] - bf["offset_ms_p50_best20pct"],
                          "max_error_ms": (bf["best_rtt_ms"] + ba["best_rtt_ms"]) / 2,
                          "fra_vs_host": bf, "ams_vs_host": ba}
    else:
        res["bracket"] = None
    if res["fra_sync"].get("offset_ms") is not None and res["ams_sync"].get("offset_ms") is not None:
        res["chrony_offset_ams_minus_fra_ms"] = res["ams_sync"]["offset_ms"] - res["fra_sync"]["offset_ms"]
    res["ping"] = ping()
    json.dump(res, open(out, "w"), indent=1)
    b = res["bracket"] or {}
    print(f"clock probe -> {out}: chrony AMS-FRA {res.get('chrony_offset_ams_minus_fra_ms', float('nan')):+.3f} ms "
          f"(FRA {res['fra_sync'].get('offset_ms')}, AMS {res['ams_sync'].get('offset_ms')} ms vs NTP); "
          f"bracket AMS-FRA {b.get('offset_ms', float('nan')):+.2f} ms (+-{b.get('max_error_ms', float('nan')):.1f} worst case); "
          f"ping FRA->AMS rtt {res['ping'].get('rtt_min_ms')}/{res['ping'].get('rtt_avg_ms')} ms (min/avg)")


if __name__ == "__main__":
    main()
