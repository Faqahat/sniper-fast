#!/usr/bin/env python3
"""dip45 FLEET SIGNAL shadow: offline checker (docs/dip45_fleet.md).

  fleet_check.py --engine RUN.jsonl [--tape TAPE_DIR] [--fills LIVE_RUN.jsonl ...] [--from T0 --to T1]

--engine  the jsonl of the run that had --presend-live-fleet-log on (e.g. the FRA no-key dry run); its presend_live_fleet records
--tape    the recorder tape for the same hours (dir with txs/*.jsonl.gz, e.g. /data/tapes/collect/run_YYYYMMDD_HHMM)
--fills   jsonl(s) of LIVE runs with real fills (e.g. AMS r82): their presend_live_fill + presend_live_realized are joined to the
          engine's fleet detections by mint + slot (the shadow run sees the same chain: the flags do not depend on whose engine saw them)

Prints: (1) the engine's detections (tries, try-slots, pre-exec share, before-slot-end share, first-sighting delay);
(2) coverage vs the tape: share of tape fleet try-slots the engine saw pre-exec (pass >= 80%), seen by the end of the slot, try coverage;
(3) the engine's own arms / fills / would-fills by fleet flag; (4) the joined live fills: n, net, per fill (mSOL), win share by fleet flag,
T2 vs re-arm, per day (lead 1 pass: >= 300 fills, signal fills >= +20 mSOL per fill better, same sign on >= 3 days).
Read-only; no network.
"""
import argparse, glob, gzip, json, os, sys, collections, datetime

CB = "ComputeBudget111111111111111111111111111111"; LH = "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; SYS = "11111111111111111111111111111111"; T22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
FLEET_PROGS = {CB, LH, PUMP, SYS, T22}
PRICES = {32000}; RANGES = [(11000, 13500)]; CUL = (40000, 80000)
PKT = datetime.timezone(datetime.timedelta(hours=5))


def tape_is_fleet(r):
    """the shadow's signature on the tape's decoded fields: exactly the fleet's programs, 1 signer, CU price / limit, no tip"""
    if set(r.get("progs") or []) != FLEET_PROGS or len(r.get("signers") or []) != 1 or r.get("tips"): return False
    c, l = r.get("cup"), r.get("cul")
    if c is None or l is None: return False
    return (c in PRICES or any(a <= c <= b for a, b in RANGES)) and CUL[0] <= l <= CUL[1]


def load_tape(d, s_lo, s_hi):
    tries = {}  # sig -> (slot, mint, signer, err)
    files = sorted(glob.glob(os.path.join(d, "txs", "*.jsonl.gz"))) or sorted(glob.glob(os.path.join(d, "*.jsonl.gz")))
    for f in files:
        try:
            for l in gzip.open(f):
                r = json.loads(l)
                s = r.get("s", 0)
                if s < s_lo or s > s_hi or not tape_is_fleet(r): continue
                mints = r.get("mints") or []
                if mints: tries[r["sig"]] = (s, mints[0], r["signers"][0], r.get("err") is not None)
        except (EOFError, OSError, json.JSONDecodeError):
            continue
    return tries


def recs(path, ev=None):
    with open(path) as fh:
        for l in fh:
            if ev and ev not in l: continue
            try: yield json.loads(l)
            except json.JSONDecodeError: continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True); ap.add_argument("--tape"); ap.add_argument("--fills", nargs="*", default=[])
    a = ap.parse_args()

    # ---- (1) engine detections ----
    arms, ours, follows, cfg, fin, silent = [], [], {}, None, None, []
    slot_pre = collections.defaultdict(lambda: [0, 0, 0, 0])  # (mint, slot) -> [tries, pre, exec, pre_by_end]
    for r in recs(a.engine, "presend_live_fleet"):
        if r.get("ev") != "presend_live_fleet": continue
        st = r.get("stage")
        if st == "config": cfg = r
        elif st == "fleet_arm":
            arms.append(r)
            for off, n, pre, ex, pe in r["slots"]:
                v = slot_pre[(r["mint"], r["s0"] + off)]; v[0] += n; v[1] += pre; v[2] += ex; v[3] += pe
        elif st in ("arm", "fill", "shadow_arm", "shadow_fill"): ours.append(r)
        elif st == "follow": follows[(r["of"], r["w"], r["mint"], r["slot"])] = r
        elif st in ("silent", "back"): silent.append(r)
    for r in recs(a.engine, "run_end"):
        if r.get("ev") == "run_end": fin = r
    if not arms:
        print("no fleet_arm records in", a.engine, "(was --presend-live-fleet-log on?)");
    n_tries = sum(r["n"] for r in arms); n_slots = len(slot_pre)
    pre_slots = sum(1 for v in slot_pre.values() if v[1] > 0); end_slots = sum(1 for v in slot_pre.values() if v[3] > 0)
    delays = sorted(r["first"]["ms_after_slot_start"] for r in arms if r["first"].get("ms_after_slot_start") is not None)
    s_lo = min((r["s0"] for r in arms), default=0); s_hi = max((r["s1"] for r in arms), default=0)
    signers = collections.Counter(s for r in arms for s in r["signers"])
    print(f"== ENGINE {os.path.basename(a.engine)}: fleet arms {len(arms)}, tries {n_tries}, try-slots {n_slots}, slots {s_lo}..{s_hi}, signers {len(signers)}")
    if n_slots:
        print(f"   try-slots with a pre-exec sighting {pre_slots} ({100*pre_slots/n_slots:.1f}%), seen pre-exec before the slot ended {end_slots} ({100*end_slots/n_slots:.1f}%)")
    if delays:
        q = lambda p: delays[min(len(delays) - 1, int(p * len(delays)))]
        print(f"   first sighting of an arm, ms after its slot's first arrival: p10 {q(.1):.0f} p50 {q(.5):.0f} p90 {q(.9):.0f}")
    print(f"   silent/back records: {[(r['stage'], r.get('slot')) for r in silent]}")

    # ---- (2) vs the tape ----
    if a.tape and arms:
        tt = load_tape(a.tape, s_lo, s_hi)
        ts = collections.defaultdict(int)
        for s, m, w, err in tt.values(): ts[(m, s)] += 1
        seen_pre = sum(1 for k in ts if slot_pre.get(k, [0, 0])[1] > 0)
        seen_end = sum(1 for k in ts if slot_pre.get(k, [0, 0, 0, 0])[3] > 0)
        seen_any = sum(1 for k in ts if k in slot_pre)
        n_tape_tries = sum(ts.values()); n_eng_on_tape = sum(min(slot_pre.get(k, [0])[0], v) for k, v in ts.items())
        eng_only = sum(1 for k in slot_pre if k not in ts)
        print(f"== TAPE {a.tape}: fleet-shape tries {n_tape_tries} on {len(ts)} try-slots (signers {len({w for _, _, w, _ in tt.values()})})")
        if ts:
            pct = 100 * seen_pre / len(ts)
            print(f"   COVERAGE try-slots seen pre-exec {seen_pre}/{len(ts)} = {pct:.1f}% (PASS >= 80%: {'PASS' if pct >= 80 else 'FAIL'}); "
                  f"before the slot ended {100*seen_end/len(ts):.1f}%; on any feed {100*seen_any/len(ts):.1f}%; tries {100*n_eng_on_tape/max(1,n_tape_tries):.1f}%")
            print(f"   engine try-slots not on the tape: {eng_only} (tape covers only tokens the recorder follows)")

    # ---- (3) the engine's own arms / fills / would-fills ----
    def flag_tab(rows, label):
        g = collections.defaultdict(list)
        for r in rows: g[(r["stage"], r.get("kind", "?").split(":")[0], bool(r["fleet"]["on8"]))].append(r)
        for k in sorted(g):
            v = g[k]; lb = [follows.get((k[0], r["w"], r["mint"], r["slot"]), {}).get("later_buy_sol") for r in v]; lb = [x for x in lb if x is not None]
            print(f"   {label} {k[0]:11s} {k[1]:7s} fleet8={'YES' if k[2] else 'no '} n={len(v):5d}" + (f"  later-buy SOL 3 slots median {sorted(lb)[len(lb)//2]/1e9:.2f}" if lb else ""))
    print("== ENGINE arms / fills / would-fills by fleet flag (8 slots before)")
    flag_tab(ours, "")

    # ---- (4) the join: live fills (another run) x the engine's detections, by mint + slot ----
    if a.fills:
        def flags(m, s):
            n2 = sum(slot_pre.get((m, x), [0, 0])[1] for x in range(s - 2, s))
            n8 = sum(slot_pre.get((m, x), [0, 0])[1] for x in range(s - 8, s))
            n8a = sum(slot_pre.get((m, x), [0])[0] for x in range(s - 8, s))
            return n2, n8, n8a
        rows = []
        for path in a.fills:
            fills, pnl = {}, {}
            for r in recs(path, "presend_live_"):
                if r.get("ev") == "presend_live_fill": fills[(r["w"], r["mint"])] = r
                elif r.get("ev") == "presend_live_realized": pnl[(r["w"], r["mint"])] = pnl.get((r["w"], r["mint"]), 0) + r["pnl"]
            for k, f in fills.items():
                if k not in pnl: continue
                if not (s_lo - 8 <= f["slot"] <= s_hi + 8): continue  # outside the engine's hours: no answer
                n2, n8, n8a = flags(f["mint"], f["slot"])
                day = datetime.datetime.fromtimestamp(f["t"] / 1e9, PKT).strftime("%m-%d") if f.get("t") else "?"
                rows.append(dict(run=os.path.basename(path), kind=f.get("kind", "t2"), pnl=pnl[k] / 1e9, n2=n2, n8=n8, n8any=n8a, day=day, size=f.get("sol_in", 0) / 1e9))
        print(f"== JOIN live fills x engine detections (mint + slot): {len(rows)} realized fills inside the engine's slots")
        for col in ("n2", "n8", "n8any"):
            for kind in ("all", "t2", "rearm"):
                sel = [r for r in rows if kind == "all" or r["kind"] == kind]
                y = [r["pnl"] for r in sel if r[col] > 0]; n = [r["pnl"] for r in sel if r[col] == 0]
                f = lambda v: f"n={len(v):4d} net={sum(v):+.3f} per fill={1000*sum(v)/len(v):+.1f} mSOL win={sum(1 for x in v if x > 0)/len(v):.2f}" if v else "n=   0"
                print(f"   {col:6s} {kind:5s} YES {f(y)} | no {f(n)}" + (f" | diff {1000*(sum(y)/len(y)-sum(n)/len(n)):+.1f} mSOL" if y and n else ""))
        days = collections.defaultdict(lambda: ([], []))
        for r in rows: days[r["day"]][0 if r["n8"] > 0 else 1].append(r["pnl"])
        signs = []
        for d, (y, n) in sorted(days.items()):
            if y and n: signs.append(sum(y) / len(y) - sum(n) / len(n))
            print(f"   day {d}: signal {len(y)} fills {1000*sum(y)/max(1,len(y)):+.1f} mSOL/fill | none {len(n)} fills {1000*sum(n)/max(1,len(n)):+.1f}")
        y = [r["pnl"] for r in rows if r["n8"] > 0]; n = [r["pnl"] for r in rows if r["n8"] == 0]
        if y and n:
            d = 1000 * (sum(y) / len(y) - sum(n) / len(n)); pos = sum(1 for s in signs if s > 0)
            ok = len(rows) >= 300 and d >= 20 and pos >= 3 and pos == len(signs)
            print(f"   LEAD 1 (n8, pre-exec): {len(rows)} fills, diff {d:+.1f} mSOL/fill, days with signal better {pos}/{len(signs)} -> {'PASS' if ok else 'not yet / FAIL'} "
                  f"(bar: >= 300 fills, >= +20 mSOL, same sign on >= 3 days)")
    if fin and fin.get("presend_live", {}).get("fleet"):
        print("== run_end fleet:", json.dumps({k: v for k, v in fin["presend_live"]["fleet"].items() if k not in ("signers",)})[:800])


if __name__ == "__main__":
    sys.exit(main())
