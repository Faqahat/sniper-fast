#!/usr/bin/env python3
"""Synthetic Shreder run dir for testing analyze.py (stdlib only). Built from a REAL chain-recording window (+ a real engine
log overlapping it) with KNOWN injected properties, written to truth.json next to the run:
  * bin  = every recorded chain tx (pump view = pump txs, 92% of them; the other 8% only in the dataset = 'ALT-CPI'),
           t = engine first-receive (AMS clock -> FRA clock, minus the injected offset, +-1 ms) for engine-seen sigs, else a
           per-slot clock fitted on the engine's (slot, t) + index offset + noise
  * pre  = txs in slots of 40% of the 4-slot leader windows ('connected leaders'), each kept with p=0.97;
           t = bin t - lead, lead ~ lognormal(P50 7 ms, sigma 0.6); 2% chain slot mismatch; 2% fake txs that never land
           (half with the mint in the view 'p', half only in the dataset's static keys); a reconnect gap (60 s) in events.jsonl;
           0.1% duplicates; a truncated last view line; a truncated last gzip member in a dataset file
  * fra/clock_start.json + clock_end.json with the injected AMS-FRA offset (3.2 -> 3.4 ms); engine/ = real engine lines
Usage: make_synth.py --out DIR [--date 2026-10-27 --from 20:45 --minutes 20] [--engine FILE] [--collect-root ROOT]"""
import argparse, base64, collections, datetime, glob, gzip, json, math, os, random, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A

PUMP = A.PUMP
NS = A.NS

def b58dec(s):
    n = 0
    for ch in s: n = n * 58 + A.B58I[ch]
    return n.to_bytes(64, "big") if n < (1 << 512) else None

def fake_tx(sig_bytes, keys):
    """minimal legacy tx: 1 sig | header | static keys | blockhash | 0 instructions"""
    kb = b"".join(keys)
    return bytes([1]) + sig_bytes + bytes([1, 0, 1]) + bytes([len(keys)]) + kb + os.urandom(32) + bytes([0])

def pkb(s):  # base58 pubkey -> 32 bytes
    n = 0
    for ch in s: n = n * 58 + A.B58I[ch]
    return n.to_bytes(32, "big")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/home/moiz/sniper-data/preconf/synth_test")
    ap.add_argument("--collect-root", default="/home/moiz/sniper-data/collect")
    ap.add_argument("--engine", default="/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl")
    ap.add_argument("--date", default="2026-10-27"); ap.add_argument("--from", dest="t_from", default="20:45")
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    d0 = datetime.date.fromisoformat(a.date); hh, mm = map(int, a.t_from.split(":"))
    lo = int((datetime.datetime(d0.year, d0.month, d0.day, hh, mm, tzinfo=datetime.timezone.utc).timestamp() - A.PKT_S) * NS)
    hi = lo + int(a.minutes * 60 * NS)
    OFF0, OFF1 = 3.2, 3.4          # injected AMS - FRA clock offset (ms) at lo / hi
    def off(t): return OFF0 + (OFF1 - OFF0) * (t - lo) / (hi - lo)
    GAP0 = lo + int(0.4 * (hi - lo)); GAP1 = GAP0 + 60 * NS
    CONN_FRAC = 0.40; KEEP = 0.97; VIEW = 0.92; MIS = 0.02; FAKE = 0.02; DUP = 0.001
    out = a.out; fra = os.path.join(out, "fra"); eng_dir = os.path.join(out, "engine")
    for d in (fra, eng_dir): os.makedirs(d, exist_ok=True)
    for fn in glob.glob(os.path.join(fra, "*")) + glob.glob(os.path.join(eng_dir, "*")): os.remove(fn)
    t0 = time.time()
    # ---------- engine (real lines around the window) + first-rx per sig (same definition as analyze.py)
    E = A.load_engine(a.engine, lo, hi) if os.path.exists(a.engine) else None
    elines = 0
    if E:
        with open(a.engine, "rb") as f, open(os.path.join(eng_dir, "dip_ams_synth.jsonl"), "wb") as g:
            for line in f:
                try: o = json.loads(line)
                except ValueError: continue
                t = A.ev_time(o)
                if o.get("ev") == "run_start" or (t is None and o.get("ev") in ("close", "presend_live_close", "presend_live_realized", "timing")) \
                        or (t is not None and lo - 180 * NS <= t <= hi + 180 * NS):
                    g.write(line); elines += 1
    efr = E["first_rx"] if E else {}
    # slot clock from engine (slot, t) pairs (AMS clock -> FRA clock)
    pts = []
    if E:
        for o in E["dumps"].values():
            if isinstance(o.get("slot"), int) and lo <= o["t"] <= hi: pts.append((o["slot"], o["t"] - int(off(o["t"]) * 1e6)))
        for L in E["tape"].values():
            for o in L:
                if isinstance(o.get("slot"), int) and isinstance(o.get("t"), int) and lo <= o["t"] <= hi: pts.append((o["slot"], o["t"] - int(off(o["t"]) * 1e6)))
    # ---------- chain records in the window
    files = A.chain_files(a.collect_root, lo, hi)
    recs = []; seen = set()
    for ep, fn, rd in files:
        try:
            with gzip.open(fn, "rt") as f:
                for line in f:
                    o = json.loads(line)
                    if not (lo // NS <= o["bt"] <= hi // NS) or o["sig"] in seen: continue
                    seen.add(o["sig"])
                    recs.append((o["s"], o["i"], o["sig"], o.get("err") is None, PUMP in o.get("progs", ()), (o.get("mints") or [None])[0], o["bt"]))
        except (EOFError, OSError): pass
    seen = None
    recs.sort()
    if not recs: print("no chain records in the window"); sys.exit(2)
    s_min, s_max = recs[0][0], recs[-1][0]
    if len(pts) < 20:   # fall back to block time
        pts = [(r[0], r[6] * NS + 500_000_000) for r in recs[::500]]
    n = len(pts); mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    b = sum((p[0] - mx) * (p[1] - my) for p in pts) / max(1, sum((p[0] - mx) ** 2 for p in pts)); a0 = my - b * mx
    def T(s): return int(a0 + b * s)
    print(f"chain {len(recs)} recs slots {s_min}..{s_max}; slot clock {b / 1e6:.1f} ms/slot from {n} pts; engine lines {elines}", file=sys.stderr)
    tracked_m = [r[5] for r in recs if r[5]]
    conn_win = {}
    def connected(s):
        w = s // 4
        if w not in conn_win: conn_win[w] = rnd.random() < CONN_FRAC
        return conn_win[w]
    def in_gap(t): return GAP0 <= t <= GAP1
    pre_view, bin_view, pre_ds, bin_ds = [], [], [], []
    truth_leads = []; truth_eng = []; n_mis = 0; order_rows = collections.defaultdict(list)
    for (s, i, sig, ok, pump, mint, bt) in recs:
        te = efr.get(sig)
        if te is not None and lo <= te <= hi:
            u = rnd.uniform(-1.0, 1.0)
            tb = te - int(off(te) * 1e6) + int(u * 1e6)
        else:
            u = None; tb = T(s) + i * 120_000 + int(rnd.gauss(0, 2e6))
        if not (lo <= tb <= hi): continue
        sb = b58dec(sig)
        in_view = pump and rnd.random() < VIEW
        p = [["other:0000000000000000", mint, None, 0, 0]] if (mint and rnd.random() < 0.5) else []
        bin_ds.append((tb, s, sb))
        if in_view: bin_view.append((tb, s, sig, p))
        if connected(s) and rnd.random() < KEEP:
            lead = math.exp(math.log(7.0) + 0.6 * rnd.gauss(0, 1))
            tp = tb - int(lead * 1e6)
            if in_gap(tp) or not (lo <= tp <= hi): continue
            ps = s
            if rnd.random() < MIS: ps = s - 1; n_mis += 1
            pre_ds.append((tp, ps, sb))
            if in_view: pre_view.append((tp, ps, sig, p)); order_rows[s].append((tp, i))
            if pump: truth_leads.append(lead)
            if u is not None and te is not None: truth_eng.append((sig, lead - u, tp))
    # never-landed fakes (tracked mints, connected slots)
    nf = int(FAKE * len(pre_view)); fakes = []
    conn_slots = [s for s in range(s_min + 8, s_max - 50) if connected(s)]
    for k in range(nf):
        s = rnd.choice(conn_slots); t = T(s) + rnd.randint(0, 300) * 1_000_000 - int(7e6)
        if in_gap(t) or not (lo <= t <= hi): continue
        sb = os.urandom(64); sig = A.b58enc(sb); mint = rnd.choice(tracked_m)
        if k % 2 == 0:
            p = [["buy", mint, None, 1000, 500_000_000]]; keys = [os.urandom(32), pkb(PUMP)]
        else:
            p = []; keys = [os.urandom(32), pkb(mint), pkb(PUMP)]
        pre_view.append((t, s, sig, p)); pre_ds.append((t, s, sb, fake_tx(sb, keys))); fakes.append(sig)
    # noise (votes / other txs) in the datasets
    for k in range(len(bin_ds) // 4):
        s = rnd.randint(s_min, s_max); t = T(s) + rnd.randint(0, 400) * 1_000_000
        if lo <= t <= hi:
            bin_ds.append((t, s, os.urandom(64)))
            if connected(s) and not in_gap(t - 7_000_000): pre_ds.append((t - 7_000_000, s, os.urandom(64)))
    # ---------- write views (hourly PKT files, q sequence, dups, truncated last line)
    def write_view(name, rows, pf, extra_dup):
        rows.sort(key=lambda r: r[0]); q = 0; fh = {}; ndup = 0; last = None
        for (t, s, sig, p) in rows:
            hour = time.strftime("%Y%m%d_%H", time.gmtime(t / NS + A.PKT_S))
            fn = os.path.join(fra, f"{name}_{hour}.jsonl")
            if fn not in fh: fh[fn] = open(fn, "w")
            q += 1
            c = 2 if (name == "pre" and t > GAP1) else 1
            rec = {"q": q, "t": t, "ca": t - rnd.randint(2_000_000, 4_000_000), "s": s, "sig": sig, "pf": pf, "c": c, "v": 0, "p": p}
            fh[fn].write(json.dumps(rec, separators=(",", ":")) + "\n"); last = fn
            if extra_dup and rnd.random() < DUP:
                q += 1; ndup += 1
                rec2 = dict(rec, q=q, t=t + 50_000_000, c=c)
                fh[fn].write(json.dumps(rec2, separators=(",", ":")) + "\n")
        for f in fh.values(): f.close()
        return ndup, last
    ndup_pre, last_pre = write_view("pre", pre_view, 1, True)
    write_view("bin", bin_view, 0, False)
    with open(last_pre, "a") as f: f.write('{"q":999999999,"t":' + str(hi - 1000) + ',"ca":0,"s":1,"sig":"trunc')   # crash-truncated
    # ---------- write datasets (gzip member per 1 s; last member of pre truncated)
    def write_ds(name, rows, truncate):
        rows.sort(key=lambda r: r[0]); seq = 0
        byhour = collections.defaultdict(list)
        for r in rows: byhour[time.strftime("%Y%m%d_%H", time.gmtime(r[0] / NS + A.PKT_S))].append(r)
        for hour, rr in byhour.items():
            fn = os.path.join(fra, f"{name}_{hour}_0.rec.gz"); idx = open(fn[:-7] + ".idx.jsonl", "w")
            with open(fn, "wb") as f:
                cur = None; buf = []; m = 0
                def flush():
                    nonlocal buf, m
                    if not buf: return
                    data = b"".join(x[0] for x in buf); off_ = f.tell()
                    comp = gzip.compress(data, compresslevel=1); f.write(comp)
                    idx.write(json.dumps({"m": m, "off": off_, "clen": len(comp), "ulen": len(data), "n": len(buf), "q0": buf[0][1], "q1": buf[-1][1],
                                          "t0": buf[0][2], "t1": buf[-1][2], "s0": buf[0][3], "s1": buf[-1][3]}) + "\n")
                    m += 1; buf = []
                for r in rr:
                    t, s, sb = r[0], r[1], r[2]
                    tx = r[3] if len(r) > 3 else fake_tx(sb, [os.urandom(32)])
                    seq += 1
                    rec = struct.pack("<QqqQBBHI", seq, t, t - 3_000_000, s, 1 if name == "pre" else 0, 1, 0, len(tx)) + tx
                    sec = t // NS
                    if cur is not None and sec != cur: flush()
                    cur = sec; buf.append((struct.pack("<I", len(rec)) + rec, seq, t, s))
                flush()
            idx.close()
        if truncate:
            fn = sorted(glob.glob(os.path.join(fra, f"{name}_*_0.rec.gz")))[-1]
            sz = os.path.getsize(fn)
            with open(fn, "r+b") as f: f.truncate(sz - 40)
    write_ds("pre", pre_ds, True); write_ds("bin", bin_ds, False)
    # ---------- events.jsonl (pre: reconnect gap) + clock files
    ev = []
    def E_(t, st, e, c, **k): ev.append(dict(t=t, st=st, ev=e, c=c, msg="", **k))
    E_(lo - 6 * NS, "all", "start", 0)
    for st in ("pre", "bin"):
        E_(lo - 5 * NS, st, "connecting", 1); E_(lo - 5 * NS + 2_000_000, st, "subscribed", 1); E_(lo - 5 * NS + 9_000_000, st, "first_msg", 1)
    E_(GAP0, "pre", "stream_end", 1, ); E_(GAP0 + 1_000_000, "pre", "error", 1); E_(GAP1 - 2 * NS, "pre", "connecting", 2)
    E_(GAP1, "pre", "subscribed", 2); E_(GAP1 + 5_000_000, "pre", "first_msg", 2)
    t = lo
    while t < hi:
        for st in ("pre", "bin"):
            if st == "pre" and GAP0 <= t <= GAP1: continue
            E_(t, st, "status", 1 if (st == "bin" or t < GAP0) else 2, n=0, rate=1000.0, slot=0, rc=0 if (st == "bin" or t < GAP0) else 1)
        t += 10 * NS
    E_(hi + 5 * NS, "all", "stop", 0)
    with open(os.path.join(fra, "events.jsonl"), "w") as f:
        for e in sorted(ev, key=lambda e: e["t"]): f.write(json.dumps(e) + "\n")
    for nm, tt, o in (("clock_start", lo, OFF0), ("clock_end", hi, OFF1)):
        json.dump({"t": tt, "fra_sync": {"tool": "chrony", "offset_ms": 0.05, "raw": "synthetic"}, "ams_sync": {"tool": "chrony", "offset_ms": -0.1, "raw": "synthetic"},
                   "bracket": {"n": 20, "best_rtt_ms": 9.0, "offset_ms": o, "offset_ms_p50": o + 0.2}, "ping": {"rtt_min_ms": 8.9, "rtt_avg_ms": 9.3, "rtt_max_ms": 11.0}},
                  open(os.path.join(fra, nm + ".json"), "w"))
    with open(os.path.join(fra, "rec.log"), "w") as f: f.write("synthetic\n")
    # ---------- truth
    conn_slots_all = [s for s in range(s_min, s_max + 1) if connected(s)]
    tl = sorted(truth_leads); te_ = sorted(x[1] for x in truth_eng)
    conc = disc = 0
    for s_, L in order_rows.items():
        L.sort()
        for u_ in range(len(L)):
            for v_ in range(u_ + 1, len(L)):
                if L[u_][0] == L[v_][0]: continue
                if L[u_][1] < L[v_][1]: conc += 1
                else: disc += 1
    q = lambda v, p: v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))] if v else None
    truth = {"window_pkt": [A.pkt(lo), A.pkt(hi)], "lo": lo, "hi": hi, "gap": [GAP0, GAP1], "gap_s": 60, "conn_frac_windows": CONN_FRAC,
             "connected_windows": sum(1 for w, c in conn_win.items() if c), "windows": len(conn_win),
             "keep_in_covered_slot": KEEP, "view_share": VIEW, "lead_p50_ms": q(tl, .5), "lead_p10_ms": q(tl, .1), "lead_p90_ms": q(tl, .9),
             "n_lead": len(tl), "engine_lead_p50_ms": q(te_, .5), "n_engine_lead": len(te_), "fakes": len(fakes),
             "never_landed_share_expected": len(fakes) / max(1, len(pre_view)), "slot_mismatch": MIS, "pre_view_dups": ndup_pre,
             "connected_min_pre": round((hi - lo - (GAP1 - GAP0)) / 6e10, 3), "offset_ms": [OFF0, OFF1],
             "pre_view": len(pre_view), "bin_view": len(bin_view), "pre_ds": len(pre_ds), "bin_ds": len(bin_ds), "engine_lines": elines,
             "order_pair_agreement": conc / max(1, conc + disc), "slot_share_connected": len([s for s in range(s_min, s_max + 1) if connected(s)]) / max(1, s_max - s_min + 1)}
    json.dump(truth, open(os.path.join(out, "truth.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in truth.items() if k not in ("lo", "hi", "gap")}), file=sys.stderr)
    print(f"synth written to {out} in {time.time() - t0:.1f}s", file=sys.stderr)

if __name__ == "__main__":
    main()
