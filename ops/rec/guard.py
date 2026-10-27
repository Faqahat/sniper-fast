#!/usr/bin/env python3
# OVERLAP GUARD (runs only while the host recorder and FRA's collector run side by side).
# Every GUARD_EVERY s it reads FRA's collector counters READ-ONLY (fra_counters.sh) and the host recorder's state, and
# stops the host recorder at once (HOLD file + SIGTERM; the recorder exits cleanly and is not restarted) when:
#   - FRA's SHYFT 429 counter (blk_http429_ep0) rises above its value at the start (any FRA run);
#   - FRA's Constant-K share of getBlock calls (blk_ep2 / blocks_ok) rises noticeably: > base + GUARD_CK_WIN over one
#     check window (>= 300 blocks) twice in a row, or > base + GUARD_CK_CUM since the start (after 30 min);
#   - the host recorder saw any SHYFT 429 / usage / credit error (it trips itself; the guard logs it);
#   - the host recorder's lag keeps growing (> GUARD_MAX_LAG_S for 3 checks in a row);
#   - GUARD_MAX_H hours have passed since the start.
# Log: $REC_ROOT/logs/guard.log (one line per check), state: $REC_ROOT/state/guard.json
import os, sys, json, time, subprocess, signal
ROOT = os.environ["REC_ROOT"]
EVERY = float(os.environ.get("GUARD_EVERY", "180")); MAX_H = float(os.environ.get("GUARD_MAX_H", "6"))
CK_WIN = float(os.environ.get("GUARD_CK_WIN", "0.06")); CK_CUM = float(os.environ.get("GUARD_CK_CUM", "0.012"))
# A 3-min window of FRA's counters is noisy (+-0.05: getBlock calls are counted when they start, blocks when processed,
# with 40 prefetched), so the window rule needs 3 windows in a row; the primary failover signal is FRA's SHYFT failures
# themselves (every failed SHYFT call is retried on the next endpoint -> ck): stop when they rise by > GUARD_SHYFT_FAILS.
SHYFT_FAILS = int(os.environ.get("GUARD_SHYFT_FAILS", "3"))
def shyft_fails(stats): return sum(v for k, v in stats.items() if (k.startswith(("blk_exc0", "blk_err0")) or (k.startswith("blk_http") and k.endswith("_ep0"))))
MAX_LAG = float(os.environ.get("GUARD_MAX_LAG_S", "180"))
HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.join(ROOT, "state", "guard.json"); LOG = os.path.join(ROOT, "logs", "guard.log"); HOLD = os.path.join(ROOT, "HOLD")
os.makedirs(os.path.dirname(SP), exist_ok=True); os.makedirs(os.path.dirname(LOG), exist_ok=True)
PKT = 5 * 3600
def pkt(ts): return time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(ts + PKT))
def log(*a):
    with open(LOG, "a") as f: f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ ", time.gmtime()) + " ".join(str(x) for x in a) + "\n")
def fra():
    r = subprocess.run([os.path.join(HERE, "fra_counters.sh")], capture_output=True, text=True, timeout=90)
    return json.loads(r.stdout)
def host():
    try: return json.load(open(os.path.join(ROOT, "state", "recorder.json")))
    except Exception: return {}
def stop(why):
    now = time.time()
    if not os.path.exists(HOLD):
        json.dump(dict(reason="guard: " + why, by="guard", t=now, pkt=pkt(now)), open(HOLD, "w"))
    h = host(); pid = h.get("pid")
    log("STOP:", why, "| recorder pid", pid)
    if pid:
        try: os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError: pass
        for _ in range(60):
            try: os.kill(int(pid), 0); time.sleep(1)
            except ProcessLookupError: break
        else: log("recorder still alive 60 s after SIGTERM")
    st = json.load(open(SP)); st.update(stopped=now, stopped_pkt=pkt(now), stop_reason=why); json.dump(st, open(SP, "w"), indent=1)
    sys.exit(0)

def tot(j, key): return sum((r["stats"].get(key) or 0) for r in j["runs"].values())

st = json.load(open(SP)) if os.path.exists(SP) else None
if st is None:
    j = fra()
    cur = max(j["runs"]) if j["runs"] else None
    base_ratio = (j["runs"][cur]["stats"].get("blk_ep2", 0) / max(1, j["runs"][cur]["stats"].get("blocks_ok", 1))) if cur else 0.68
    st = dict(start=time.time(), start_pkt=pkt(time.time()), base_runs={r: v["stats"] for r, v in j["runs"].items()},
              base_ratio=round(base_ratio, 4), base_t=j["t"])
    json.dump(st, open(SP, "w"), indent=1)
    log("BASELINE", json.dumps({r: dict(shyft429=v["stats"].get("blk_http429_ep0", 0), ck=v["stats"].get("blk_ep2"), ok=v["stats"].get("blocks_ok")) for r, v in j["runs"].items()}), "ck share", st["base_ratio"])
prev = None; strikes = 0; lag_strikes = 0
while True:
    if os.path.exists(HOLD):
        log("HOLD present:", open(HOLD).read().strip()[:200]); h = host()
        st.update(stopped=time.time(), stop_reason="HOLD: " + open(HOLD).read()[:200]); json.dump(st, open(SP, "w"), indent=1); sys.exit(0)
    now = time.time()
    if now - st["start"] > MAX_H * 3600: stop(f"overlap time cap {MAX_H} h reached")
    try: j = fra()
    except Exception as e:
        log("FRA read failed:", type(e).__name__); time.sleep(EVERY); continue
    base = st["base_runs"]
    # 1) FRA SHYFT 429 counter, per run (a run that started after us had 0 at our start)
    for r, v in j["runs"].items():
        b429 = (base.get(r) or {}).get("blk_http429_ep0", 0); c429 = v["stats"].get("blk_http429_ep0", 0)
        if c429 > b429: stop(f"FRA {r} SHYFT 429 counter rose {b429} -> {c429}")
    # 1b) FRA's SHYFT failures (each one is a failover to the next endpoint, i.e. ck)
    for r, v in j["runs"].items():
        bf = shyft_fails((base.get(r) or {})); cf = shyft_fails(v["stats"])
        if cf - bf > SHYFT_FAILS: stop(f"FRA {r} SHYFT failures rose {bf} -> {cf} (failovers to ck)")
    # 2) ck share
    d_ok = sum(v["stats"].get("blocks_ok", 0) - (base.get(r) or {}).get("blocks_ok", 0) for r, v in j["runs"].items())
    d_ck = sum(v["stats"].get("blk_ep2", 0) - (base.get(r) or {}).get("blk_ep2", 0) for r, v in j["runs"].items())
    cum = d_ck / d_ok if d_ok > 0 else None
    win = None
    if prev is not None:
        w_ok = sum(v["stats"].get("blocks_ok", 0) - (prev["runs"].get(r, {}).get("stats", {}).get("blocks_ok", (base.get(r) or {}).get("blocks_ok", 0))) for r, v in j["runs"].items())
        w_ck = sum(v["stats"].get("blk_ep2", 0) - (prev["runs"].get(r, {}).get("stats", {}).get("blk_ep2", (base.get(r) or {}).get("blk_ep2", 0))) for r, v in j["runs"].items())
        if w_ok >= 300:
            win = w_ck / w_ok
            strikes = strikes + 1 if win > st["base_ratio"] + CK_WIN else 0
            if strikes >= 3: stop(f"FRA ck share {win:.3f} > {st['base_ratio'] + CK_WIN:.3f} in three windows in a row")
    if cum is not None and now - st["start"] > 1800 and cum > st["base_ratio"] + CK_CUM:
        stop(f"FRA ck share since start {cum:.3f} > {st['base_ratio'] + CK_CUM:.3f}")
    # 3) host recorder
    h = host(); hs = h.get("stats") or {}
    lim = {k: v for k, v in hs.items() if k.startswith("limit_") or ".http429" in k}
    if lim: stop(f"host saw a limit error {lim}")
    lag = h.get("lag_s"); alive = False
    try: os.kill(int(h.get("pid")), 0); alive = True
    except Exception: pass
    lag_strikes = lag_strikes + 1 if (lag is not None and lag > MAX_LAG) else 0
    if lag_strikes >= 3: stop(f"host lag {lag:.0f} s > {MAX_LAG:.0f} s for 3 checks")
    calls = {k: v for k, v in hs.items() if k.startswith("SHYFT.")}
    rates = {k: v for k, v in (h.get("rates_10m") or {}).items() if k.startswith("SHYFT.")}
    log(f"ok | FRA runs {list(j['runs'])} collectors {j.get('collectors')} shyft429 {[v['stats'].get('blk_http429_ep0', 0) for v in j['runs'].values()]} shyft_fails+{[shyft_fails(v['stats']) - shyft_fails(base.get(r) or {}) for r, v in j['runs'].items()]} "
        f"ck share win {None if win is None else round(win, 3)} cum {None if cum is None else round(cum, 3)} (base {st['base_ratio']}) "
        f"FRA lag {[v.get('lag_slots') for v in j['runs'].values()]} | host alive {alive} lag_s {None if lag is None else round(lag)} calls {calls} rate10m {rates}")
    prev = j
    time.sleep(EVERY)
