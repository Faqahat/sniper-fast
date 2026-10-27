#!/usr/bin/env python3
"""make_test_ck.py — synthetic test data for ck_compare.py from REAL inputs + fake Shreder recorder files with KNOWN leads.

  A (FRA, same clock): a real feed-race log (kaldera / turbo-kaldera / kaldera-tx / erpc X lines) + real chain truth;
     Shreder bin = CK_BEST - 1.000 ms for every Constant-K tx except k8 % 50 == 0 (dropped from the pump view; the half
     with k8 % 100 == 0 kept in the full dataset bin_*.rec.gz); preconf = CK_BEST - 7.000 ms for every tx of the slots
     with (slot // 4) % 3 == 0.
  B (engine on AMS, cross-machine): a real AMS engine snapshot trimmed to [T0, T1]; Shreder bin (FRA clock) =
     engine first arrival (or executed arrival) - OFF - 2.000 ms with fra/clock_start.json bracket.offset_ms = OFF = 5.0;
     per-feed arrivals (timing clock2.feeds of the fires in the window) checked against the same construction.
Writes OUT/A, OUT/B and OUT/expect.json (what ck_compare.py must report).

usage: make_test_ck.py OUT RACE_LOG ENGINE_JSONL T0_UNIX T1_UNIX
"""
import gzip
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ck_compare as C  # noqa: E402

OUT, RACE, ENG, T0, T1 = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
CK = ("kaldera", "turbo-kaldera", "kaldera-tx")
MS = 1_000_000


def sig_of(k):
    return C.b58enc(k.to_bytes(8, "big") + bytes(56))


def hour_name(st, t):
    import datetime as dt
    return f"{st}_{dt.datetime.fromtimestamp(t / 1e9, C.PKT).strftime('%Y%m%d_%H')}.jsonl"


def write_view(d, st, recs):
    os.makedirs(d, exist_ok=True)
    by = {}
    for r in sorted(recs, key=lambda r: r["t"]):
        by.setdefault(hour_name(st, r["t"]), []).append(r)
    for n, rs in by.items():
        with open(os.path.join(d, n), "w") as w:
            for q, r in enumerate(rs):
                w.write(json.dumps({"q": q, **r}) + "\n")
            w.write('{"q": 99999999, "t": 17931')      # a truncated last line (the contract allows it)


def write_rec(path, rows):
    """rows: (rx_ns, ca_ns, slot, flags, sig64 bytes)"""
    with gzip.open(path, "wb") as w:
        for q, (rx, ca, slot, flags, sig) in enumerate(rows):
            tx = b"\x01" + sig + bytes(120)
            w.write(C.REC_HDR.pack(C.REC_HDR.size - 4 + len(tx), q, rx, ca, slot, flags, 1, 0, len(tx)) + tx)   # rec_len = bytes after the field (= 40 + tx_len, the recorder)


def median(v):
    v = sorted(v)
    return v[int(round((len(v) - 1) * 0.5))] if v else None


def part_a():
    d = os.path.join(OUT, "A")
    os.makedirs(os.path.join(d, "ck"), exist_ok=True)
    os.makedirs(os.path.join(d, "fra"), exist_ok=True)
    os.system(f"cp '{RACE}' '{d}/ck/race_exec1.log'")
    if RACE.endswith(".log") and os.path.exists(RACE[:-4] + ".err"):     # the harness stderr (its feed list)
        os.system(f"cp '{RACE[:-4]}.err' '{d}/ck/race_exec1.err'")
    T, slot = {}, {}
    for raw in open(RACE, "rb"):
        x = raw.rstrip(b"\n").split(b"\t")
        if x[0] != b"X":
            continue
        f, t, s, k = x[1].decode(), int(x[2]), int(x[3]), int(x[4], 16)
        o = T.setdefault(f, {}).get(k)
        if o is None or t < o:
            T[f][k] = t
        slot.setdefault(k, s)
    keys_ck = set().union(*(T[f].keys() for f in CK if f in T))
    union = set().union(*T.values())
    best = {k: min(T[f][k] for f in CK if f in T and k in T[f]) for k in keys_ck}
    pre_slots = {s for s in set(slot.values()) if (s // 4) % 3 == 0}
    bin_v, bin_rec, pre_v = [], [], []
    for k in keys_ck:
        t = best[k] - 1 * MS
        r = {"t": t, "ca": t - 2_500_000, "s": slot[k], "sig": sig_of(k), "pf": 0, "c": 1, "v": 0, "p": []}
        if k % 50 != 0:
            bin_v.append(r)
        if k % 50 != 0 or k % 100 == 0:
            bin_rec.append((t, t - 2_500_000, slot[k], 0, k.to_bytes(8, "big") + bytes(56)))
        if slot[k] in pre_slots:
            tp = best[k] - 7 * MS
            pre_v.append({"t": tp, "ca": tp - 1 * MS, "s": slot[k], "sig": sig_of(k), "pf": 1, "c": 1, "v": 0, "p": []})
    # noise in the dataset: non-pump txs
    for i in range(500):
        t = min(best.values()) + i * 10 * MS
        bin_rec.append((t, t - MS, 460552130, 0, (0xABCDEF0000000000 + i).to_bytes(8, "big") + bytes(56)))
    write_view(os.path.join(d, "fra"), "bin", bin_v)
    write_view(os.path.join(d, "fra"), "pre", pre_v)
    bin_rec.sort()
    write_rec(os.path.join(d, "fra", "bin_20261023_23_000.rec.gz"), bin_rec)
    t_lo, t_hi = min(best.values()) - 5 * 10**9, max(best.values()) + 5 * 10**9
    with open(os.path.join(d, "fra", "events.jsonl"), "w") as w:
        for st in ("bin", "pre"):
            w.write(json.dumps({"t": t_lo, "st": st, "ev": "connecting", "c": 1}) + "\n")
            w.write(json.dumps({"t": t_lo + 1000, "st": st, "ev": "subscribed", "c": 1}) + "\n")
        w.write(json.dumps({"t": t_hi, "st": "all", "ev": "stop", "c": 1}) + "\n")
    # expectations (computed independently of ck_compare's code paths)
    bin_final = {k for k in keys_ck if k % 50 != 0 or k % 100 == 0}
    pre_keys = {k for k in keys_ck if slot[k] in pre_slots}
    U = union
    exp = {
        "bin_vs_ckbest_p50": 1.0, "pre_vs_ckbest_p50": 7.0,
        "bin_vs_kaldera_p50": round(median([(T["kaldera"][k] - (best[k] - MS)) / 1e6 for k in bin_final if k in T["kaldera"]]), 3),
        "bin_miss_union_pct": round(100.0 * len([k for k in U if k not in bin_final]) / len(U), 2),
        "pre_miss_own_slots_pct": round(100.0 * len([k for k in U if slot[k] in pre_slots and k not in pre_keys]) /
                                        max(1, len([k for k in U if slot[k] in pre_slots])), 2),
        "rec_added": len([k for k in keys_ck if k % 50 == 0 and k % 100 == 0]),
        "n_union": len(U),
    }
    return exp


def part_b():
    d = os.path.join(OUT, "B")
    os.makedirs(os.path.join(d, "engine"), exist_ok=True)
    os.makedirs(os.path.join(d, "fra"), exist_ok=True)
    lo, hi = T0 * 10**9, T1 * 10**9
    inw = lambda t: isinstance(t, int) and lo <= t <= hi
    keep = []
    for line in open(ENG):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ev = r.get("ev")
        ts = [r.get("t"), r.get("t_dump_rx"), (r.get("d") or {}).get("t"), (r.get("trig") or {}).get("t"), r.get("dump_first_rx"), r.get("buy_first_rx")]
        if ev == "run_start" or any(inw(t) for t in ts):
            keep.append(line)
    with open(os.path.join(d, "engine", "dip_ams_r28.jsonl"), "w") as w:
        w.writelines(keep)
    OFF, LEAD = 5.0, 2.0
    json.dump({"bracket": {"offset_ms": OFF, "best_rtt_ms": 14.2}}, open(os.path.join(d, "fra", "clock_start.json"), "w"))
    # what the engine logged (raw AMS clock), via ck_compare's own loader on the unshifted clock
    F = C.Feeds()
    C.load_engine(F, [os.path.join(d, "engine", "dip_ams_r28.jsonl")], "fra", None, 0, 2**63 - 1, set())
    first, exe = F.t.get("eng_first", {}), F.t.get("eng_exec", {})
    keys = set(first) | set(exe)
    recs = []
    for k in keys:
        t_ams = first.get(k) or exe[k]
        t = t_ams - int(OFF * MS) - int(LEAD * MS)
        recs.append({"t": t, "ca": t - 3 * MS, "s": F.slot.get(k, 0), "sig": sig_of(k), "pf": 0, "c": 1, "v": 0, "p": []})
    write_view(os.path.join(d, "fra"), "bin", recs)
    shr = {k: (first.get(k) or exe[k]) - int(OFF * MS) - int(LEAD * MS) for k in keys}
    per_feed = {}
    for f, d in F.t.items():
        if f.startswith("eng:"):
            v = [((t - int(OFF * MS)) - shr[k]) / 1e6 for k, t in d.items() if k in shr]
            if v:
                per_feed[f] = round(median(v), 3)
    exp = {"eng_feed_vs_bin_p50": per_feed, "eng_first_vs_bin_p50": LEAD,
           "eng_exec_vs_bin_p50": round(median([((exe[k] - int(OFF * MS)) - ((first.get(k) or exe[k]) - int(OFF * MS) - int(LEAD * MS))) / 1e6
                                               for k in exe]), 3),
           "n_first": len(first), "n_exec": len(exe), "offset_ms": OFF}
    # classifier check vs the engine's own whale (presend_arm, 6%) and dump (>= 0.3 SOL) records in [T0, T1]
    arms, dumps = [], []
    for line in keep:
        r = json.loads(line)
        if r.get("ev") == "presend_arm" and inw(r.get("t")):
            arms.append(C.k8_sig(r["sig"]))
        if r.get("ev") == "dump" and inw(r.get("t")) and (r.get("sell") or 0) >= 0.3:
            dumps.append(C.k8_sig(r["sig"]))
    exp["engine_arms"] = arms
    exp["engine_dumps"] = dumps
    return exp


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    e = {"A": part_a(), "B": part_b()}
    json.dump(e, open(os.path.join(OUT, "expect.json"), "w"))
    print("A:", {k: v for k, v in e["A"].items()})
    print("B:", {k: v for k, v in e["B"].items() if k not in ("engine_arms", "engine_dumps")}, "arms", len(e["B"]["engine_arms"]), "dumps>=0.3", len(e["B"]["engine_dumps"]))
