#!/usr/bin/env python3
# OVERLAP COMPARISON: host recorder (sampled overlap test E) vs FRA's collector, slot by slot, on the same slots.
#  1. exact: every sampled slot the host fetched is replayed through FRA's own collect.py process_block with each active
#     FRA run's tracked-mint set at that slot; the produced records must equal FRA's recorded records for that slot
#     (same txs, same fields, byte-identical after sorting the mints list) -> proves the host gets the same blocks and
#     produces the same data.
#  2. direct: every host record whose mints FRA also tracks has a FRA record with the same sig and identical fields
#     (except `mints`, which lists each recorder's own tracked mints).
#  3. creates: launches seen in the sampled slots, host vs FRA.   4. gaps: skips / failures on each side.   5. lag.
# Usage: overlap_compare.py <E root> <FRA run dir> [<FRA run dir> ...]  -> JSON summary on stdout + details file
import os, sys, json, gzip, glob, re, zlib, time, hashlib, importlib.util, collections
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
E = sys.argv[1]; RUNS = sys.argv[2:]
SL = re.compile(rb'^\{"s":(\d+),')
def norm(r): return json.dumps(dict(r, mints=sorted(r["mints"])), sort_keys=True, separators=(",", ":"))
def dig(s): return hashlib.blake2b(s.encode(), digest_size=16).digest()
def no_mints(r): return json.dumps({k: v for k, v in r.items() if k not in ("mints", "tb")}, sort_keys=True, separators=(",", ":"))   # mints + tb list each recorder's OWN tracked mints
def tbset(r): return frozenset(tuple(x) for x in r.get("tb") or [])

host_day = sorted(glob.glob(os.path.join(E, "days", "*")))
slots = {}                                             # sampled slot -> (status, bt, wt)
for d in host_day:
    for l in open(os.path.join(d, "slots.tsv")):
        x = l.rstrip("\n").split("\t"); slots[int(x[0])] = (x[1], float(x[2]) if x[2] else None, float(x[6]))
SAMPLE = sorted(slots)
def fra_chunk(args):
    """FRA chunk -> {slot: [(sig, i, digest, nomints_digest, mints)]} for the sampled slots only"""
    path, want_lo, want_hi, step = args
    out = collections.defaultdict(list); ok = True; n = 0
    try:
        with gzip.open(path, "rb") as f:
            for line in f:
                if not line.endswith(b"\n"): ok = False; break
                m = SL.match(line)
                if not m: continue
                s = int(m.group(1))
                if s < want_lo or s > want_hi or s % step: continue
                r = json.loads(line); n += 1
                out[s].append((r["sig"], r["i"], dig(norm(r)), dig(no_mints(r)), sorted(r["mints"]), tbset(r)))
    except (EOFError, OSError, zlib.error): ok = False
    return path, dict(out), ok, n

step = json.load(open(os.path.join(host_day[0], "run.json"))).get("sample_every", 1)
lo, hi = SAMPLE[0], SAMPLE[-1]
fra = {}; fra_meta = {}
with ProcessPoolExecutor(8) as ex:
    for R in RUNS:
        rj = json.load(open(os.path.join(R, "run.json"))); st = json.load(open(os.path.join(R, "status.json")))
        t_lo = min(w for _, _, w in slots.values()) - 900; t_hi = max(w for _, _, w in slots.values()) + 900
        files = sorted(p for p in glob.glob(os.path.join(R, "txs", "*.jsonl.gz")) if t_lo <= int(os.path.basename(p)[4:14]) <= t_hi)
        recs = collections.defaultdict(list); complete_hi = None; partial = []
        for path, out, ok, n in ex.map(fra_chunk, [(p, lo, hi, step) for p in files], chunksize=1):
            for s, v in out.items(): recs[s].extend(v)
            if not ok: partial.append(os.path.basename(path))
        # FRA covers [start_slot, last slot it processed]; the newest copied chunk may be partial: stop before its first slot
        last = st.get("end_slot") or st.get("last_slot")
        if partial:
            firsts = []
            for p in partial:
                with gzip.open(os.path.join(R, "txs", p), "rb") as f:
                    try: m = SL.match(f.readline()); firsts.append(int(m.group(1)) if m else hi)
                    except Exception: firsts.append(hi)
            last = min(last or hi, min(firsts) - 1)
        L = [json.loads(l) for l in open(os.path.join(R, "launches.jsonl"))]
        gaps = {}
        if os.path.exists(os.path.join(R, "gaps.jsonl")):
            for l in open(os.path.join(R, "gaps.jsonl")):
                try: g = json.loads(l); gaps[g["slot"]] = g["why"]
                except Exception: pass
        fra[R] = recs; fra_meta[R] = dict(start=rj["start_slot"], last=last, win_end=rj["window_end_time"], launches=sorted(L, key=lambda c: (c["slot"], c["idx"])),
                                          gaps=gaps, partial=partial, lag=st.get("lag_slots"))

# ---- 1. exact replay through FRA's code ----
os.environ.setdefault("CONSTANTK_TOKEN", "dummy"); os.environ.setdefault("TIPMAP", os.path.join(HERE, "tipmap.json"))
mods = {}
for R in RUNS:
    os.environ["OUT"] = os.path.join(os.environ.get("CMP_TMP", "/home/moiz/sniper-data/rec/test/cmp_tmp"), os.path.basename(R))
    spec = importlib.util.spec_from_file_location("C_" + os.path.basename(R), os.path.join(HERE, "..", "collect", "collect.py"))
    C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
    buf = []; C.chunk_write = buf.append; C.jlog = lambda *a, **k: None; C.EQ = type("Q", (), {"put": lambda self, x: None})()
    mods[R] = (C, buf, iter(fra_meta[R]["launches"]), [None])
raw_files = sorted(glob.glob(os.path.join(E, "raw", "raw_*.jsonl.gz")))
res = collections.Counter(); diffs = []; per_run = {R: collections.Counter() for R in RUNS}
host_ok_compared = 0
def advance(R, s):
    C, buf, it, pend = mods[R]
    while True:
        c = pend[0] if pend[0] is not None else next(it, None)
        if c is None: return
        if c["slot"] < s:
            C.TRACK[c["mint"]] = c["slot"]; C.LCACHE[c["mint"]] = c; C.EARLY.setdefault(c["mint"], []); pend[0] = None
        else: pend[0] = c; return
for p in raw_files:
    try:
        with gzip.open(p, "rt") as f:
            for line in f:
                try: x = json.loads(line)
                except Exception: break
                s, b = x["slot"], x["block"]
                if s > hi: break
                for R in RUNS:
                    m = fra_meta[R]
                    if not (m["start"] <= s <= (m["last"] or -1)): continue
                    C, buf, _, _ = mods[R]
                    advance(R, s); buf.clear()
                    bt = b.get("blockTime") or 0
                    C.process_block(s, b, bt <= m["win_end"])
                    exp = sorted((r["sig"], r["i"], dig(norm(r))) for r in buf)
                    got = sorted((sig, i, d) for sig, i, d, _, _, _ in fra[R].get(s, []))
                    per_run[R]["slots"] += 1; per_run[R]["records_expected"] += len(exp); per_run[R]["records_fra"] += len(got)
                    if exp == got: per_run[R]["slots_identical"] += 1
                    else:
                        per_run[R]["slots_different"] += 1
                        es, gs = {e[0] for e in exp}, {g[0] for g in got}
                        if len(diffs) < 40: diffs.append(dict(run=os.path.basename(R), slot=s, only_replay=sorted(es - gs)[:5], only_fra=sorted(gs - es)[:5],
                                                              same_sig_diff_fields=sorted(x[0] for x in set(exp) ^ set(got) if x[0] in es & gs)[:5]))
    except (EOFError, OSError, zlib.error): pass

# ---- 2. direct: host records vs FRA records ----
host = collections.defaultdict(list)
for d in host_day:
    for p in sorted(glob.glob(os.path.join(d, "txs", "*.jsonl.gz"))):
        try:
            with gzip.open(p, "rt") as f:
                for l in f: r = json.loads(l); host[r["s"]].append(r)
        except (EOFError, OSError, zlib.error): pass
direct = collections.Counter(); ddiff = []
fra_tracked_at = {}
for s in sorted(host):
    act = [R for R in RUNS if fra_meta[R]["start"] <= s <= (fra_meta[R]["last"] or -1)]
    if not act: direct["host_records_no_fra_coverage"] += len(host[s]); continue
    by_sig = {}
    for R in act:
        for sig, i, dg, dnm, mints, tb in fra[R].get(s, []): by_sig.setdefault(sig, []).append((dnm, set(mints), tb))
    tracked = set()
    for R in act: tracked |= {c["mint"] for c in fra_meta[R]["launches"] if c["slot"] <= s}
    for r in host[s]:
        if not (set(r["mints"]) & tracked): direct["host_records_mint_not_tracked_by_fra"] += 1; continue
        cand = by_sig.get(r["sig"])
        if not cand: direct["host_records_missing_in_fra"] += 1; ddiff.append((s, r["sig"], "missing in FRA")) if len(ddiff) < 20 else None; continue
        if any(dnm == dig(no_mints(r)) and (set(r["mints"]) & tracked) <= ms and tbset(r) <= tb for dnm, ms, tb in cand): direct["host_records_identical"] += 1
        else: direct["host_records_fields_differ"] += 1; ddiff.append((s, r["sig"], "fields differ")) if len(ddiff) < 20 else None

# ---- 3. creates in sampled slots ----
hostL = [json.loads(l) for d in host_day for l in open(os.path.join(d, "launches.jsonl"))]
cre = collections.Counter(); cdiff = []
for c in hostL:
    s = c["slot"]; act = [R for R in RUNS if fra_meta[R]["start"] <= s <= (fra_meta[R]["last"] or -1) and (c.get("bt") or 0) <= fra_meta[R]["win_end"]]
    if not act: cre["host_creates_outside_fra_windows"] += 1; continue
    fl = {x["mint"]: x for R in act for x in fra_meta[R]["launches"] if x["slot"] == s}
    x = fl.get(c["mint"])
    if x is None: cre["host_creates_missing_in_fra"] += 1; cdiff.append(c["mint"]); continue
    keys = ("name", "symbol", "uri", "mint", "bonding_curve", "user", "creator", "slot", "idx", "bt", "sig", "payer", "err", "fee", "ixn")
    cre["identical" if all(c.get(k) == x.get(k) for k in keys) else "fields_differ"] += 1
sampled_fra_creates = 0
for R in RUNS:
    m = fra_meta[R]
    for x in m["launches"]:
        if x["slot"] in slots and slots[x["slot"]][0] == "ok" and x["slot"] <= (m["last"] or -1) and x["slot"] >= SAMPLE[0]: sampled_fra_creates += 1
cre["fra_creates_in_host_ok_sampled_slots"] = sampled_fra_creates

# ---- 4. gaps on each side (sampled slots only) ----
gap = collections.Counter()
for s, (st, bt, wt) in slots.items():
    act = [R for R in RUNS if fra_meta[R]["start"] <= s <= (fra_meta[R]["last"] or -1)]
    if not act: continue
    fg = [fra_meta[R]["gaps"].get(s) for R in act]
    gap[f"host_{st}"] += 1
    if any(fg): gap["fra_gap_" + ("skip" if any((g or "").startswith("skip") for g in fg) else "fail")] += 1
    if st == "skip" and all((g or "").startswith("skip") for g in fg): gap["both_skip"] += 1
    if st == "skip" and not any(fg): gap["host_skip_but_fra_has_block"] += 1
    if st == "ok" and any(fg): gap["host_ok_but_fra_gap"] += 1
lags = sorted(wt - bt for s, (st, bt, wt) in slots.items() if st == "ok" and bt)
lag = dict(p50=lags[len(lags) // 2], p90=lags[int(len(lags) * 0.9)], max=lags[-1]) if lags else {}
out = dict(t=time.time(), host_sampled_slots=len(SAMPLE), sample_every=step, slot_range=[lo, hi],
           fra_runs={os.path.basename(R): dict(start=m["start"], last_compared=m["last"], partial_chunks=m["partial"], **per_run[R]) for R, m in fra_meta.items()},
           exact_replay_diffs=diffs[:10], direct=dict(direct), direct_examples=ddiff[:10], creates=dict(cre), creates_missing=cdiff[:10],
           gaps=dict(gap), host_lag_block_to_processed_s={k: round(v, 1) for k, v in lag.items()})
print(json.dumps(out, indent=1))
