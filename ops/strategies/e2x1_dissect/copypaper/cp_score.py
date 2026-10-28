#!/usr/bin/env python3
"""copypaper scorer: score the frozen copy-trade strategy on one time window [start, end) (unix seconds) from the recordings.
Finds the raw chunks that cover [start-400, end+2100] (the 1800 s timeout needs look-ahead), decodes the ones not yet cached
(local keeper copies first; a chunk not yet copied is fetched from the FRA server read-only into the scratchpad, decoded,
and the raw copy deleted), builds the tape, scores, appends one JSON line per window to --out and one per signal to --trades,
and carries re-entry lockouts in --state.
Usage: cp_score.py --start BT --end BT [--mode frozen|ourspeed] [--cache DIR] [--out F] [--trades F] [--state F] [--procs N]
       [--local DIRS...] [--no-fetch] [--signal-users E2x1|both] [--L 66]"""
import sys, os, glob, json, time, subprocess, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cplib, cp_decode

D = "/home/moiz/sniper-data/e2x1_dissect/copypaper"
LOCAL = ["/home/moiz/sniper-data/collect"]
SCRATCH = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_copypaper/fetch"
SSH = ["ssh", "-p", "1996", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "it@84.32.100.36"]
CHUNK_S = 300

def chunk_ts(fn):
    b = os.path.basename(fn); return int(b.split("txs_")[1].split(".")[0])

def local_chunks(lo, hi, dirs):
    out = {}
    for d in dirs:
        for fn in glob.glob(f"{d}/run_*/txs/txs_*.jsonl.gz"):
            t = chunk_ts(fn)
            if lo <= t <= hi: out[(os.path.basename(os.path.dirname(os.path.dirname(fn))), t)] = fn
    return out

def server_chunks(lo, hi):
    """list the server's chunks (read-only) in the range; returns {(run, ts): remote path}"""
    try:
        r = subprocess.run(SSH + ["sudo ls -d /root/sniper-collect/run_*/txs/txs_*.jsonl.gz"], capture_output=True, text=True, timeout=60)
    except Exception as ex:
        print("server list failed:", ex); return {}
    out = {}
    for ln in r.stdout.split():
        try: t = chunk_ts(ln)
        except Exception: continue
        if lo <= t <= hi: out[(ln.split("/")[3], t)] = ln
    return out

def fetch(remote, run, ts):
    os.makedirs(f"{SCRATCH}/{run}/txs", exist_ok=True)
    loc = f"{SCRATCH}/{run}/txs/txs_{ts}.jsonl.gz"
    with open(loc + ".part", "wb") as f:
        r = subprocess.run(SSH + [f"sudo cat {remote}"], stdout=f, timeout=600)
    if r.returncode != 0: os.unlink(loc + ".part"); return None
    os.replace(loc + ".part", loc); return loc

def ensure_cache(lo, hi, cache, procs, dirs, allow_fetch=True, min_age=240):
    """decode every chunk in [lo, hi]; returns the cache files. Server-fetched raw chunks are deleted after decoding."""
    have = local_chunks(lo, hi, dirs)
    now = time.time()
    have = {k: v for k, v in have.items() if now - os.path.getmtime(v) >= min_age}   # still being copied
    need = {k: v for k, v in have.items() if not os.path.exists(cp_decode.cache_name(cache, v))}
    if need:
        print(f"decoding {len(need)} local chunks", flush=True)
        cp_decode.decode_all(cache, sorted(need.values()), procs, quiet=True)
    files = {k: cp_decode.cache_name(cache, v) for k, v in have.items()}
    if allow_fetch:
        # any chunk the server has that we do not (keeper lag): fetch, decode, delete the raw copy
        srv = server_chunks(lo, hi)
        miss = {k: v for k, v in srv.items() if k not in files and not os.path.exists(f"{cache}/{k[0]}__txs_{k[1]}.npz")}
        # the newest server chunk may still be open: skip chunks younger than min_age
        miss = {k: v for k, v in miss.items() if now - k[1] >= CHUNK_S + min_age}
        for k, remote in sorted(miss.items()):
            loc = fetch(remote, k[0], k[1])
            if not loc: print("fetch failed", remote); continue
            cp_decode.decode_all(cache, [loc], 1, quiet=True); os.unlink(loc)
            files[k] = cp_decode.cache_name(cache, loc); print("fetched+decoded", k, flush=True)
    # cached files from earlier cycles
    for fn in glob.glob(f"{cache}/*.npz"):
        t = chunk_ts(fn)
        if lo <= t <= hi: files[(os.path.basename(fn).split("__")[0], t)] = fn
    return sorted(set(files.values()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True); ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--mode", default="frozen"); ap.add_argument("--cache", default=f"{D}/cache")
    ap.add_argument("--out", default=f"{D}/out/results.jsonl"); ap.add_argument("--trades", default=f"{D}/out/trades.jsonl")
    ap.add_argument("--state", default=f"{D}/out/state.json"); ap.add_argument("--procs", type=int, default=3)
    ap.add_argument("--local", nargs="*", default=LOCAL); ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--signal-users", default="both"); ap.add_argument("--L", type=float, default=cplib.L_MS)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    t0 = time.time()
    lo, hi = a.start - 400, a.end + cplib.TIMEOUT_S + 300
    files = ensure_cache(lo, hi, a.cache, a.procs, a.local, allow_fetch=not a.no_fetch)
    if not files: print("no chunks"); return 2
    tape = cplib.Tape(files)
    cov_lo, cov_hi = tape.bt_lo, tape.bt_hi
    state = json.load(open(a.state)) if os.path.exists(a.state) else {}
    users = ["E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"] if a.signal_users == "E2x1" else list(cplib.CLUSTER)
    if a.mode == "frozen":
        cfg = cplib.frozen_cfg(); cfg["exit_users"] = tape.cluster_ids; cfg["L"] = a.L
    elif a.mode == "ourspeed":   # ourspeed B-copy replica: his lots, his size, exit = HIS first sell, no timeout/band/lockout
        cfg = dict(cap=None, guard=cplib.GUARD, timeout=None, stop=None, lockout=False, band=False, L=a.L,
                   exit_users={tape.sid[cplib.ME]} if cplib.ME in tape.sid else set())
        users = [cplib.ME]
    else: raise SystemExit("mode?")
    rows, lock = cplib.run_window(tape, a.start, a.end, cfg, state.get("lockouts"), users)
    summ = cplib.summarize(rows)
    summ.update(start=a.start, end=a.end, start_pkt=cplib.pkt(a.start), end_pkt=cplib.pkt(a.end), mode=a.mode, L=a.L, label=a.label,
                chunks=len(files), tape_bt=[cov_lo, cov_hi], trunc=sum(1 for m in tape.metas if m.get("trunc")),
                lookahead_ok=bool(cov_hi >= a.end + cplib.TIMEOUT_S), scored_at=int(time.time()), secs=round(time.time() - t0))
    with open(a.out, "a") as f: f.write(json.dumps(summ) + "\n")
    with open(a.trades, "a") as f:
        for r in rows:
            r = dict(r); r["window"] = a.start; r["pkt"] = cplib.pkt(r["bt"])
            f.write(json.dumps({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}) + "\n")
    if a.mode == "frozen":
        state["lockouts"] = lock; state["last_end"] = a.end
        tmp = a.state + ".tmp"; json.dump(state, open(tmp, "w")); os.replace(tmp, a.state)
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in summ.items()}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
