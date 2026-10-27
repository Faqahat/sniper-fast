#!/usr/bin/env python3
# rec: catalog / where / status / fetch / pin / archive / due / remote-test / link / check / slim for the host recorder.
# Run it through the `rec` wrapper (same dir): commands that need the remote credentials or the Telegram token load
# the root-only /etc/sniper-rec/env via sudo + systemd-run and run as moiz; secrets are never printed.
#   rec status                          recorder, current day, disk, catalog, cache, archive backlog, alerts
#   rec catalog [--day D | --legacy | --all]   (re)index days and the old FRA run_* dirs (sha256, records, slot/time ranges)
#   rec where <PKT time | epoch | slot> which day / run / chunk file holds it, and where it lives
#   rec days                            one line per day (location, completeness, size)
#   rec check <day>                     slot contiguity inside the day and against the neighbour days
#   rec fetch <day | day..day>          pull archived days into the cache (LRU, cap REC_CACHE_CAP_GB, pinned days never evicted)
#   rec pin <day> / rec unpin <day>     keep a day on the host / in the cache
#   rec path <day>                      local path of a day (host or cache) for tools
#   rec archive [--dry-run] [--no-delete] [--day D | --run R]   upload + verify + free the host copy (days older than 7)
#   rec due                             remote days older than REC_REMOTE_KEEP_DAYS (listed for the owner, never auto-deleted)
#   rec remote-test                     connect / upload / SIZE / re-download sha256 / rename / delete on the remote
#   rec link [--from DAY]               collect/run_YYYYMMDD_0000 -> rec day symlinks (only from the cut-over day on)
#   rec slim <day>                      build the trades-only extract and record its size
import os, sys, json, time, glob, shutil, subprocess, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reclib as R

def P(*a): print(*a, flush=True)
def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB": return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024

# ------------------------------------------------------------------ indexing
def _index_one(args):
    rel, p = args
    e = R.index_chunk(p) if rel.startswith("txs/") and rel.endswith(".jsonl.gz") else R.index_plain(p)
    return rel, e

def index_unit(key, base, final=False):
    """index every file under base (cached by size + mtime, chunks in parallel); returns list of file entries"""
    from concurrent.futures import ProcessPoolExecutor
    ip = os.path.join(R.INDEX, key.replace(":", "_").replace("/", "_") + ".json")
    prev = (R.jload(ip) or {}).get("files", {})
    out = {}; todo = []; stats = {}
    for rel in R.file_list(base):
        p = os.path.join(base, rel); st = os.stat(p); stats[rel] = st.st_mtime_ns
        e = prev.get(rel)
        if e and e.get("size") == st.st_size and e.get("mtime_ns") == st.st_mtime_ns: out[rel] = e
        else: todo.append((rel, p))
    if todo:
        workers = int(os.environ.get("REC_INDEX_WORKERS", "8"))
        if len(todo) > 2 and workers > 1:
            with ProcessPoolExecutor(min(workers, len(todo))) as ex:
                for rel, e in ex.map(_index_one, todo, chunksize=1): e["mtime_ns"] = stats[rel]; out[rel] = e
        else:
            for rel, p in todo:
                rel, e = _index_one((rel, p)); e["mtime_ns"] = stats[rel]; out[rel] = e
    if todo or set(prev) != set(out): R.jdump(ip, dict(key=key, base=base, files=out, t=time.time()))
    return [dict(p=rel, **{k: v for k, v in e.items() if k != "mtime_ns"}) for rel, e in sorted(out.items())]

def slots_stats(path, step=1):
    """slots.tsv -> contiguity + counts (step = sample_every for a sampled test day)"""
    if not os.path.exists(path): return {}
    first = last = None; n = ok = skip = fail = perr = 0; dup = 0; holes = []; prev = None; maxfail = cur_fail = 0
    with open(path) as f:
        for l in f:
            x = l.split("\t", 3)
            try: s = int(x[0])
            except ValueError: continue
            n += 1
            if first is None: first = s
            if prev is not None:
                if s <= prev: dup += 1
                elif s != prev + step: holes.append([prev + 1, s - 1])
            prev = s; last = s if last is None or s > last else last
            st = x[1]
            if st == "ok": ok += 1; cur_fail = 0
            elif st == "skip": skip += 1
            elif st == "fail": fail += 1; cur_fail += 1; maxfail = max(maxfail, cur_fail)
            else: perr += 1
    return dict(first=first, last=last, lines=n, ok=ok, skip=skip, fail=fail, perr=perr, dup_or_backwards=dup, holes=holes[:50],
                n_holes=len(holes), max_fail_run=maxfail, contiguous=(dup == 0 and not holes))

def count_lines(p):
    if not os.path.exists(p): return 0
    with open(p, "rb") as f: return sum(b.count(b"\n") for b in iter(lambda: f.read(1 << 22), b""))

def catalog_day(c, day, base=None, where=None):
    base = base or R.local_day_path(day)
    if not base: return
    files = index_unit("day:" + day, base)
    run = R.jload(os.path.join(base, "run.json")) or {}; st = R.jload(os.path.join(base, "status.json")) or {}
    ss = slots_stats(os.path.join(base, "slots.tsv"), run.get("sample_every") or 1)
    lo, hi = R.day_start(day), R.day_start(R.next_day(day))
    chunks = [f for f in files if f["p"].startswith("txs/")]
    bts = [b for f in chunks for b in (f.get("bt") or []) if b]
    end_slot = run.get("end_slot"); start_slot = run.get("start_slot")
    t0 = run.get("start_time"); t1 = run.get("last_block_time") or st.get("last_block_time") or (max(bts) if bts else None)
    full = bool(t0 and t0 <= lo + 120 and end_slot is not None and not run.get("holes") and not run.get("hole_before") and not run.get("hole_after") and ss.get("contiguous"))
    e = c["days"].setdefault(day, {})
    where = where or (["cache"] if base.startswith(R.CACHE) else ["host"])
    if (e.get("remote") or {}).get("verified"): where = sorted(set(where) | {"remote"})
    e.update(kind="rec", path=base, where=where, mode=run.get("mode"), sample_every=run.get("sample_every"),
             slot_range=[start_slot, end_slot if end_slot is not None else ss.get("last")],
             time_range=[t0, t1], time_range_pkt=[R.pkt_str(t0), R.pkt_str(t1)],
             phase=st.get("phase"), final_pass=run.get("final_pass") or st.get("final_pass"), enrich_rpc=run.get("enrich_rpc"),
             txs=sum(f.get("n") or 0 for f in chunks), chunks=len(chunks), chunks_incomplete=[f["p"] for f in chunks if not f.get("ok", True)],
             launches=count_lines(os.path.join(base, "launches.jsonl")), enriched=count_lines(os.path.join(base, "enrich.jsonl")),
             gaps=dict(skip=ss.get("skip"), fail=ss.get("fail"), parse_err=ss.get("perr"), max_fail_run=ss.get("max_fail_run")),
             complete=dict(slots_tsv=ss, holes=run.get("holes"), hole_before=run.get("hole_before"), hole_after=run.get("hole_after"),
                           full_day=full, rotated=end_slot is not None),
             bytes=sum(f["size"] for f in files), files=files, indexed=time.time())
    return e

def catalog_legacy(c):
    """index the old FRA run_* copies in place (never rewritten) and map every PKT day to the chunk files covering it"""
    if not os.path.isdir(R.LEGACY): return
    for d in c["days"].values(): d.pop("legacy", None)
    for run in sorted(os.listdir(R.LEGACY)):
        base = os.path.join(R.LEGACY, run)
        if not R.RUN_RE.match(run) or os.path.islink(base) or not os.path.isdir(os.path.join(base, "txs")): continue
        files = index_unit("run:" + run, base)
        rj = R.jload(os.path.join(base, "run.json")) or {}; st = R.jload(os.path.join(base, "status.json")) or {}
        chunks = [f for f in files if f["p"].startswith("txs/") and f.get("slot") and f["slot"][0] is not None]
        bt_lo = min((f["bt"][0] for f in chunks if f.get("bt") and f["bt"][0]), default=None)
        bt_hi = max((f["bt"][1] for f in chunks if f.get("bt") and f["bt"][1]), default=None)
        days = R.days_between(R.pkt_day(bt_lo), R.pkt_day(bt_hi)) if bt_lo and bt_hi else []
        e = c["runs"].setdefault(run, {})
        where = sorted(set(e.get("where") or []) - {"host"} | {"host"})
        e.update(kind="legacy", path=base, where=where, start_slot=rj.get("start_slot"), start_time=rj.get("start_time"),
                 window_end_time=rj.get("window_end_time"), tail_end_time=rj.get("tail_end_time"), phase=st.get("phase"),
                 slot_range=[min(f["slot"][0] for f in chunks), max(f["slot"][1] for f in chunks if f["slot"][1])] if chunks else None,
                 time_range=[bt_lo, bt_hi], time_range_pkt=[R.pkt_str(bt_lo), R.pkt_str(bt_hi)], days=days,
                 txs=sum(f.get("n") or 0 for f in chunks), launches=count_lines(os.path.join(base, "launches.jsonl")),
                 gaps=count_lines(os.path.join(base, "gaps.jsonl")), final_rows=count_lines(os.path.join(base, "final.jsonl")),
                 bytes=sum(f["size"] for f in files), files=files, indexed=time.time())
        for d in days:
            lo, hi = R.day_start(d), R.day_start(R.next_day(d))
            cov = [f["p"] for f in chunks if f.get("bt") and f["bt"][0] is not None and f["bt"][1] is not None and f["bt"][1] >= lo and f["bt"][0] < hi]
            win = [max(lo, rj.get("start_time") or lo), min(hi, rj.get("window_end_time") or hi, bt_hi or hi)]   # a run that stopped early ends at its last block
            c["days"].setdefault(d, {}).setdefault("legacy", []).append(dict(run=run, files=cov, creates_window=win if win[0] < win[1] else None,
                                                                               creates_window_pkt=[R.pkt_str(win[0]), R.pkt_str(win[1])] if win[0] < win[1] else None))
    # legacy completeness per day: union of the runs' create windows
    for d, e in c["days"].items():
        if not e.get("legacy"): continue
        lo, hi = R.day_start(d), R.day_start(R.next_day(d))
        iv = sorted(tuple(x["creates_window"]) for x in e["legacy"] if x.get("creates_window"))
        cov = 0; holes = []; pos = lo
        for a, b in iv:
            if a > pos: holes.append([R.pkt_str(pos), R.pkt_str(a)])
            cov += max(0, b - max(a, pos)); pos = max(pos, b)
        if pos < hi and hi <= time.time(): holes.append([R.pkt_str(pos), R.pkt_str(hi)])
        e["legacy_coverage"] = dict(fraction=round(cov / 86400, 4), holes=holes)

def cmd_catalog(a):
    with R.lock("catalog"):
        c = R.cat_load()
        if a.day: catalog_day(c, a.day)
        else:
            for d in sorted(os.listdir(R.DAYS)) if os.path.isdir(R.DAYS) else []:
                if R.DAY_RE.match(d): catalog_day(c, d)
            for d in sorted(os.listdir(os.path.join(R.CACHE, "days"))) if os.path.isdir(os.path.join(R.CACHE, "days")) else []:
                if R.DAY_RE.match(d) and d not in os.listdir(R.DAYS): catalog_day(c, d, os.path.join(R.CACHE, "days", d))
            if a.legacy or a.all: catalog_legacy(c)
        c["pins"] = sorted(set(c.get("pins", [])))
        R.cat_save(c)
    P(f"catalog: {len(c['days'])} days, {len(c['runs'])} legacy runs -> {R.CATALOG}")

# ------------------------------------------------------------------ status / days / where / check
def recorder_state(root=R.ROOT):
    s = R.jload(os.path.join(root, "state", "recorder.json")) or {}
    alive = False
    try: os.kill(int(s.get("pid")), 0); alive = True
    except Exception: pass
    return s, alive

def cmd_status(a):
    s, alive = recorder_state()
    hold = R.jload(os.path.join(R.ROOT, "HOLD"))
    svc = subprocess.run(["systemctl", "is-active", "sniper-rec.service"], capture_output=True, text=True).stdout.strip()
    P(f"== recorder ({R.pkt_str(time.time())})")
    if hold: P(f"   HOLD: {hold.get('reason')} (since {hold.get('pkt')})")
    P(f"   service sniper-rec: {svc}; process alive: {alive}; mode {s.get('mode')}; day {s.get('day')}")
    if s:
        age = time.time() - (s.get("now") or 0)
        P(f"   last slot {s.get('last_slot')} (block time {R.pkt_str(s.get('last_block_time'))}); lag {s.get('lag_slots')} slots / {(s.get('lag_s') or 0):.0f} s; status age {age:.0f} s")
        P(f"   tracked mints {s.get('tracked_mints')}; enrich queue {s.get('enrich_queue')}; calls/s (10 min) {s.get('rates_10m')}")
    du = shutil.disk_usage("/home/moiz"); P(f"== disk: {du.used / du.total * 100:.1f}% used, {du.free / 1e9:.0f} GB free")
    c = R.cat_load(); days = c["days"]
    host = [d for d, e in days.items() if "host" in (e.get("where") or []) and e.get("kind") == "rec"]
    rem = [d for d, e in days.items() if "remote" in (e.get("where") or [])]
    cache = [d for d, e in days.items() if "cache" in (e.get("where") or [])]
    legacy_host = [r for r, e in c["runs"].items() if "host" in (e.get("where") or [])]
    cut = R.day_start(R.today()) - R.HOST_KEEP_DAYS * 86400
    backlog = [d for d in host if R.day_start(d) < cut] + [r for r in legacy_host if all(R.day_start(x) < cut for x in c["runs"][r].get("days") or [R.today()])]
    P(f"== catalog (updated {c.get('updated_pkt')}): rec days on host {len(host)} ({human(sum(days[d].get('bytes', 0) for d in host))}), "
      f"legacy runs on host {len(legacy_host)} ({human(sum(c['runs'][r].get('bytes', 0) for r in legacy_host))}), remote {len(rem)}, cache {len(cache)}, pinned {len(c.get('pins', []))}")
    P(f"   archive backlog (older than {R.HOST_KEEP_DAYS} days, still on host): {len(backlog)} {sorted(backlog)[:6]}")
    w = R.jload(os.path.join(R.STATE, "watch.json")) or {}
    act = {k: v for k, v in (w.get("alerts") or {}).items() if v.get("active")}
    P(f"== watchdog ({R.pkt_str(w.get('t'))}): {'OK' if not act else 'ALERTS: ' + '; '.join(v.get('msg', k) for k, v in act.items())}")
    arch = R.jload(os.path.join(R.STATE, "archive.json")) or {}
    if arch: P(f"== archive: last run {R.pkt_str(arch.get('t'))}: {arch.get('summary')}")

def cmd_days(a):
    c = R.cat_load()
    for d in sorted(c["days"]):
        e = c["days"][d]
        if e.get("kind") == "rec":
            cm = e.get("complete") or {}; ss = cm.get("slots_tsv") or {}
            P(f"{d} rec  {','.join(e.get('where') or []):12s} {human(e.get('bytes', 0)):>9s} txs {e.get('txs', 0):>10,} launches {e.get('launches', 0):>6} slots {e['slot_range']} "
              f"full_day {cm.get('full_day')} contiguous {ss.get('contiguous')} skip {ss.get('skip')} fail {ss.get('fail')} phase {e.get('phase')}" + (f" SAMPLED 1/{e['sample_every']}" if e.get("sample_every") else ""))
        for x in e.get("legacy") or []:
            r = c["runs"].get(x["run"], {})
            P(f"{d} old  {','.join(r.get('where') or []):12s} {x['run']}: {len(x['files'])} chunk files, creates window {x.get('creates_window_pkt')}")
        if e.get("legacy_coverage"): P(f"{d}      legacy create coverage {e['legacy_coverage']['fraction'] * 100:.1f}% holes {e['legacy_coverage']['holes']}")

def cmd_where(a):
    kind, v = R.parse_when(a.what); c = R.cat_load(); hits = []
    for d, e in sorted(c["days"].items()):
        if e.get("kind") != "rec": continue
        sr = e.get("slot_range") or [None, None]
        if kind == "slot" and sr[0] is not None and sr[0] <= v <= (sr[1] or 1 << 62): pass
        elif kind == "time" and R.pkt_day(v) == d: pass
        else: continue
        f = [x for x in e.get("files", []) if x["p"].startswith("txs/") and ((kind == "slot" and x.get("slot") and x["slot"][0] is not None and x["slot"][0] <= v <= (x["slot"][1] or 0))
                                                                        or (kind == "time" and x.get("bt") and x["bt"][0] is not None and x["bt"][0] <= v <= (x["bt"][1] or 0)))]
        hits.append(f"day {d} (rec, {','.join(e.get('where') or [])}) path {e.get('path') if 'host' in (e.get('where') or []) or 'cache' in (e.get('where') or []) else '-'} chunk {[x['p'] for x in f] or '-'}")
    for r, e in sorted(c["runs"].items()):
        f = [x for x in e.get("files", []) if x["p"].startswith("txs/") and ((kind == "slot" and x.get("slot") and x["slot"][0] is not None and x["slot"][0] <= v <= (x["slot"][1] or 0))
                                                                        or (kind == "time" and x.get("bt") and x["bt"][0] is not None and x["bt"][0] <= v <= (x["bt"][1] or 0)))]
        if f: hits.append(f"legacy {r} ({','.join(e.get('where') or [])}) path {e.get('path')} chunk {[x['p'] for x in f]}")
    P(f"{a.what} -> {kind} {v}" + (f" ({R.pkt_str(v)}, PKT day {R.pkt_day(v)})" if kind == "time" else ""))
    for h in hits or ["not in the catalog (run `rec catalog --all`)"]: P("  " + h)

def cmd_check(a):
    day = a.day; c = R.cat_load(); base = R.local_day_path(day)
    if not base: P("day not local"); return 2
    run = R.jload(os.path.join(base, "run.json")) or {}; k = run.get("sample_every") or 1; ss = slots_stats(os.path.join(base, "slots.tsv"), k)
    ok = True
    def chk(cond, what):
        nonlocal ok; ok &= bool(cond); P(("PASS " if cond else "FAIL ") + what)
    chk(ss.get("contiguous"), f"slots.tsv contiguous: {ss.get('lines')} lines {ss.get('first')}..{ss.get('last')}, holes {ss.get('n_holes')}, dup {ss.get('dup_or_backwards')}")
    chk(ss.get("first") is not None and ss["first"] - run.get("start_slot", 0) < k, f"first slots.tsv slot {ss.get('first')} == run.json start_slot ({run.get('start_slot')})" + (f" (sampled 1/{k})" if k > 1 else ""))
    if run.get("end_slot") is not None: chk(ss.get("last") == run.get("end_slot"), f"last slots.tsv slot == run.json end_slot ({run.get('end_slot')})")
    prv = R.pkt_day(R.day_start(day) - 3600); nxt = R.next_day(day)
    for other, rel in ((prv, "previous"), (nxt, "next")):
        ob = R.local_day_path(other); orun = R.jload(os.path.join(ob, "run.json")) if ob else None
        if not orun: P(f"skip {rel} day {other}: not local"); continue
        if rel == "previous": chk(orun.get("end_slot") is not None and orun["end_slot"] + 1 == run.get("start_slot"), f"{other} end_slot {orun.get('end_slot')} + 1 == {day} start_slot {run.get('start_slot')}")
        else: chk(run.get("end_slot") is not None and run["end_slot"] + 1 == orun.get("start_slot"), f"{day} end_slot {run.get('end_slot')} + 1 == {other} start_slot {orun.get('start_slot')}")
    files = index_unit("day:" + day, base)
    lo = min((f["slot"][0] for f in files if f["p"].startswith("txs/") and f.get("slot") and f["slot"][0] is not None), default=None)
    hi = max((f["slot"][1] for f in files if f["p"].startswith("txs/") and f.get("slot") and f["slot"][1] is not None), default=None)
    if lo is not None: chk(lo >= run.get("start_slot") and (run.get("end_slot") is None or hi <= run["end_slot"]), f"chunk records {lo}..{hi} inside the day's slot range")
    return 0 if ok else 1

# ------------------------------------------------------------------ cache / pins / fetch
def cache_state(): return R.jload(os.path.join(R.STATE, "cache.json")) or {}
def cache_touch(day, nbytes=None):
    s = cache_state(); e = s.setdefault(day, {}); e["last_used"] = time.time()
    if nbytes is not None: e["bytes"] = nbytes
    R.jdump(os.path.join(R.STATE, "cache.json"), s)
def cache_evict(c, keep=()):
    s = cache_state(); pins = set(c.get("pins", [])); cap = R.CACHE_CAP_GB * 1e9
    entries = []
    for d in os.listdir(os.path.join(R.CACHE, "days")) if os.path.isdir(os.path.join(R.CACHE, "days")) else []:
        p = os.path.join(R.CACHE, "days", d); n = sum(os.path.getsize(os.path.join(p, f)) for f in R.file_list(p))
        entries.append([s.get(d, {}).get("last_used", 0), d, n])
    total = sum(e[2] for e in entries)
    for lu, d, n in sorted(entries):
        if total <= cap: break
        if d in pins or d in keep: continue
        if "remote" not in (c["days"].get(d, {}).get("where") or []): continue      # never evict the only copy
        shutil.rmtree(os.path.join(R.CACHE, "days", d)); total -= n
        e = c["days"].get(d, {}); e["where"] = [w for w in e.get("where", []) if w != "cache"]
        if e.get("path", "").startswith(R.CACHE): e["path"] = None
        s.pop(d, None); R.log("cache", f"evicted {d} ({human(n)}), cache now {human(total)}")
        P(f"cache: evicted {d} ({human(n)})")
    R.jdump(os.path.join(R.STATE, "cache.json"), s)
    return total

def day_range(spec):
    if ".." in spec: a, b = spec.split(".."); return R.days_between(a, b)
    return [spec]

def cmd_pin(a, on=True):
    with R.lock("catalog"):
        c = R.cat_load(); pins = set(c.get("pins", []))
        for d in day_range(a.day): (pins.add if on else pins.discard)(d)
        c["pins"] = sorted(pins); R.cat_save(c)
    P(("pinned " if on else "unpinned ") + a.day + f"; pins: {c['pins']}")

def cmd_path(a):
    p = R.local_day_path(a.day)
    if p: cache_touch(a.day) if p.startswith(R.CACHE) else None; P(p); return 0
    P(f"{a.day} is not on this host (rec fetch {a.day})"); return 1

def cmd_fetch(a):
    import backends as B
    c = R.cat_load(); be = None; done = []
    for d in day_range(a.day):
        if R.local_day_path(d): cache_touch(d); P(f"{d}: already local at {R.local_day_path(d)}"); done.append(d); continue
        e = c["days"].get(d) or {}; rem = e.get("remote") or {}
        if not rem.get("verified"):
            legacy = e.get("legacy") or []
            if legacy: P(f"{d}: on this host only as legacy runs: {[x['run'] for x in legacy]} (see `rec where`)")
            else: P(f"{d}: not archived / unknown")
            continue
        if be is None:
            be = B.from_env(log=lambda m: R.log("remote", m)); be.connect(); P(f"remote: {be.describe()}")
        dst = os.path.join(R.CACHE, "days", d); n = 0
        for f in e["files"]:
            loc = os.path.join(dst, f["p"])
            if os.path.exists(loc) and os.path.getsize(loc) == f["size"] and R.sha256_file(loc) == f["sha256"]: continue
            be.download(rem["dir"] + "/" + f["p"], loc)
            if R.sha256_file(loc) != f["sha256"]: raise SystemExit(f"{d}/{f['p']}: sha256 mismatch after download")
            n += f["size"]
        with R.lock("catalog"):
            c = R.cat_load(); e = c["days"][d]; e["where"] = sorted(set(e.get("where", [])) | {"cache"}); e["path"] = dst; R.cat_save(c)
        cache_touch(d, sum(f["size"] for f in e["files"])); R.log("cache", f"fetched {d} ({human(n)})"); P(f"{d}: fetched to {dst} ({human(n)}, sha256 verified)")
        done.append(d)
    if be: be.close()
    with R.lock("catalog"):
        c = R.cat_load(); total = cache_evict(c, keep=done); R.cat_save(c)
    P(f"cache: {human(total)} of {R.CACHE_CAP_GB:.0f} GB")

# ------------------------------------------------------------------ archive
def archive_units(c, only_day=None, only_run=None):
    cut = R.day_start(R.today()) - R.HOST_KEEP_DAYS * 86400; units = []
    for d, e in sorted(c["days"].items()):
        if e.get("kind") != "rec" or "host" not in (e.get("where") or []) or e.get("sample_every"): continue
        if only_day and d != only_day: continue
        if only_run: continue
        if not only_day and R.day_start(d) >= cut: continue
        if e.get("phase") != "DONE": continue
        units.append(("day", d, e))
    for r, e in sorted(c["runs"].items()):
        if "host" not in (e.get("where") or []): continue
        if only_run and r != only_run: continue
        if only_day: continue
        if not only_run and not all(R.day_start(x) < cut for x in e.get("days") or [R.today()]): continue
        if (e.get("tail_end_time") or 0) > time.time() - 2 * 86400: continue      # still being copied by the keeper
        units.append(("run", r, e))
    return units

def cmd_archive(a):
    import backends as B
    with R.lock("archive", wait=False):
        c = R.cat_load()
        units = archive_units(c, a.day, a.run)
        P(f"{len(units)} unit(s) to archive (host keeps {R.HOST_KEEP_DAYS} days): {[u[1] for u in units]}")
        if a.dry_run or not units:
            R.jdump(os.path.join(R.STATE, "archive.json"), dict(t=time.time(), ok=True, dry_run=bool(a.dry_run), summary=f"{len(units)} due, dry run" if a.dry_run else "nothing to do"))
            return 0
        be = B.from_env(log=lambda m: R.log("remote", m)); mode = be.connect(); P(f"remote: {be.describe()}")
        verify = os.environ.get("REC_VERIFY", "full"); results = []; failures = []
        for kind, name, e in units:
            t0 = time.time(); base = e["path"]; rdir = ("days/" if kind == "day" else "runs/") + name
            try:
                files = index_unit(("day:" if kind == "day" else "run:") + name, base)      # fresh sha256s
                up = 0
                for f in files:
                    rel = rdir + "/" + f["p"]
                    if be.size(rel) == f["size"] and f["p"] in ((e.get("remote") or {}).get("verified_files") or []): continue
                    be.upload(os.path.join(base, f["p"]), rel); up += f["size"]
                man = "".join(f"{f['sha256']}  {f['p']}\n" for f in files).encode()
                mp = os.path.join(R.STATE, f"manifest_{name}.sha256"); open(mp, "wb").write(man)
                be.upload(mp, f"manifests/{name}.sha256")
                # verify: SIZE of every file, then re-download + sha256 (full; or a rotating sample)
                vf = []; t1 = time.time()
                for j, f in enumerate(files):
                    rel = rdir + "/" + f["p"]
                    if be.size(rel) != f["size"]: raise B.BackendError(f"{rel}: remote SIZE != local")
                    if verify == "full" or (j + int(time.time() // 86400)) % 10 == 0:
                        h, n = be.sha256(rel)
                        if h != f["sha256"] or n != f["size"]: raise B.BackendError(f"{rel}: sha256 mismatch after upload")
                    vf.append(f["p"])
                nb = sum(f["size"] for f in files); dt_up = t1 - t0; dt_v = time.time() - t1
                with R.lock("catalog"):
                    c = R.cat_load(); ent = (c["days"] if kind == "day" else c["runs"])[name]
                    ent["remote"] = dict(backend=be.name, mode=mode, dir=rdir, verified=time.time(), verify=("sha256-full" if verify == "full" else "size-all+sha256-sample10%"),
                                         verified_files=vf, files=len(files), bytes=nb)
                    ent["files"] = files; ent["where"] = sorted(set(ent.get("where", [])) | {"remote"})
                    pinned = name in c.get("pins", [])
                    if not a.no_delete and not pinned:
                        # the ONLY place a host copy is removed: every file verified on the remote just now
                        shutil.rmtree(base); ent["where"] = [w for w in ent["where"] if w != "host"]; ent["path"] = None
                        link = os.path.join(R.LEGACY, "run_" + name.replace("-", "") + "_0000") if kind == "day" else None
                        if link and os.path.islink(link): os.remove(link)
                    R.cat_save(c)
                msg = f"{name}: {len(files)} files {human(nb)} uploaded {human(up)} in {dt_up:.0f} s, verified ({verify}) in {dt_v:.0f} s" + ("" if a.no_delete or pinned else ", host copy removed")
                R.log("archive", msg); P(msg); results.append(msg)
            except Exception as ex:
                msg = f"{name}: FAILED {type(ex).__name__}: {str(ex)[:200]}"; R.log("archive", msg); P(msg); failures.append(msg)
        be.close()
        R.jdump(os.path.join(R.STATE, "archive.json"), dict(t=time.time(), ok=not failures, failures=failures, done=results,
                                                             summary=f"{len(results)} archived, {len(failures)} failed"))
        return 1 if failures else 0

def cmd_due(a):
    c = R.cat_load(); cut = R.day_start(R.today()) - R.REMOTE_KEEP_DAYS * 86400; due = []
    for d, e in sorted(c["days"].items()):
        if "remote" in (e.get("where") or []) and R.day_start(d) < cut: due.append(("day", d, e.get("bytes", 0)))
    for r, e in sorted(c["runs"].items()):
        if "remote" in (e.get("where") or []) and all(R.day_start(x) < cut for x in e.get("days") or [R.today()]): due.append(("run", r, e.get("bytes", 0)))
    P(f"remote retention {R.REMOTE_KEEP_DAYS} days: {len(due)} unit(s) past it (NOT deleted; the owner decides):")
    for k, n, b in due: P(f"  {k} {n} {human(b)}")

def cmd_remote_test(a):
    import backends as B, hashlib
    be = B.from_env(log=P); t = time.time(); mode = be.connect()
    P(f"connected: {be.describe()} in {time.time() - t:.1f} s; server features: {sorted(getattr(be, 'feats', []))[:20]}")
    d = os.path.join(R.STATE, "remote_test"); os.makedirs(d, exist_ok=True); p = os.path.join(d, "probe.bin")
    mb = int(os.environ.get("REC_TEST_MB", "64"))
    with open(p, "wb") as f: f.write(os.urandom(mb << 20))
    h = R.sha256_file(p); rel = f"_probe/probe_{int(t)}.bin"
    t1 = time.time(); be.upload(p, rel); up = time.time() - t1
    P(f"upload {mb} MB to a .part name + rename: {up:.1f} s ({mb * 8 / max(up, 1e-3):.0f} Mbit/s); remote SIZE {be.size(rel)} (local {os.path.getsize(p)})")
    t2 = time.time(); rh, n = be.sha256(rel); dn = time.time() - t2
    P(f"re-download + sha256: {dn:.1f} s ({mb * 8 / max(dn, 1e-3):.0f} Mbit/s); match: {rh == h and n == os.path.getsize(p)}")
    # resume: upload half, then the rest
    half = os.path.join(d, "half.bin"); open(half, "wb").write(open(p, "rb").read((mb << 20) // 2))
    rel2 = f"_probe/resume_{int(t)}.bin"
    try:
        be.upload(half, rel2 + ".tmpsrc")      # a separate file only to check that the server accepts uploads at all twice
        be.delete(rel2 + ".tmpsrc")
        P("second upload ok")
    except Exception as e: P(f"second upload failed: {e}")
    P(f"listing _probe: {be.listdir('_probe')[:5]}")
    be.delete(rel); P("deleted the probe file")
    os.remove(p); os.remove(half)
    day_gb = 13; P(f"projection for a {day_gb} GB day: upload {day_gb * 8000 / max(1, mb * 8 / max(up, 1e-3)) / 60:.0f} min + full verify {day_gb * 8000 / max(1, mb * 8 / max(dn, 1e-3)) / 60:.0f} min")
    be.close(); P(f"remote-test OK ({mode})")

# ------------------------------------------------------------------ links / slim
def cmd_link(a):
    frm = a.frm or os.environ.get("REC_LINK_FROM", "")
    if not frm: P("REC_LINK_FROM is empty: no links (they start at the cut-over day, so FRA runs and host days never double up)"); return 0
    made = []
    for d in sorted(os.listdir(R.DAYS)):
        if not R.DAY_RE.match(d) or d < frm: continue
        link = os.path.join(R.LEGACY, "run_" + d.replace("-", "") + "_0000"); tgt = os.path.join(R.DAYS, d)
        if os.path.islink(link) and os.readlink(link) == tgt: continue
        if os.path.exists(link) and not os.path.islink(link): P(f"skip {link}: a real dir exists"); continue
        if os.path.islink(link): os.remove(link)
        os.symlink(tgt, link); made.append(os.path.basename(link))
    for l in glob.glob(os.path.join(R.LEGACY, "run_*_0000")):
        if os.path.islink(l) and not os.path.exists(l): os.remove(l); P(f"removed dangling link {os.path.basename(l)} (day archived; `rec fetch` it)")
    P(f"links: {made or 'up to date'}")

def cmd_slim(a):
    import slim
    p, h = slim.build_day(a.day)
    with R.lock("catalog"):
        c = R.cat_load(); c["days"].setdefault(a.day, {})["slim"] = dict(path=p, rows=h["rows"], bytes=h["bytes"], sha256=h["sha256"], sources=h["sources"], built=time.time())
        R.cat_save(c)
    P(json.dumps(dict(day=a.day, file=p, rows=h["rows"], MB=round(h["bytes"] / 1e6, 1), seconds=h["seconds"], sources=h["sources"], dup_removed=h["dup_removed"])))

def main():
    ap = argparse.ArgumentParser(prog="rec"); sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("catalog"); x.add_argument("--day"); x.add_argument("--legacy", action="store_true"); x.add_argument("--all", action="store_true")
    sp.add_parser("status"); sp.add_parser("days"); sp.add_parser("due"); sp.add_parser("remote-test")
    x = sp.add_parser("where"); x.add_argument("what")
    x = sp.add_parser("check"); x.add_argument("day")
    for n in ("fetch", "pin", "unpin", "path", "slim"):
        x = sp.add_parser(n); x.add_argument("day")
    x = sp.add_parser("archive"); x.add_argument("--dry-run", action="store_true"); x.add_argument("--no-delete", action="store_true"); x.add_argument("--day"); x.add_argument("--run")
    x = sp.add_parser("link"); x.add_argument("--from", dest="frm")
    a = ap.parse_args()
    fn = dict(catalog=cmd_catalog, status=cmd_status, days=cmd_days, where=cmd_where, check=cmd_check, fetch=cmd_fetch,
              pin=lambda a: cmd_pin(a, True), unpin=lambda a: cmd_pin(a, False), path=cmd_path, archive=cmd_archive, due=cmd_due,
              link=cmd_link, slim=cmd_slim)
    fn["remote-test"] = cmd_remote_test
    return fn[a.cmd](a) or 0

if __name__ == "__main__":
    sys.exit(main())
