#!/usr/bin/env python3
"""dip36 FP-NOBOT preload builder [read-only on the recordings]: the engine's --presend-fpnb-preload FILE, so the whale-history inputs
(wh_n, wh_mints, wh_big, wh_q10, wh_q50, wh_sold_frac: 24 h look-back, spec FLAG 1) work from minute one, plus our own recent closed
positions and the shadow's row-c results from the previous run's jsonl (o_* / s_* inputs).

Whale history = every landed pump.fun TradeEvent of the last HOURS (default 24) in the 24/7 raw recordings
(/home/moiz/sniper-data/collect/run_*/txs/txs_<unix>.jsonl.gz; overlapping recordings de-duplicated on (slot, idx, j)), per wallet:
(mint id = first 8 bytes of the mint, big-endian; slot; buy; big = a buy of >= 6% of supply).

File (src/fpnb.rs preload_parse): line 1 = JSON header {"fpnb_preload": 1, from_slot, to_slot, from_t, to_t, wallets N, rows M, own [...],
shadow [[known_ns, net_cheap]], shadow_arms [t_ns], src}, then little-endian binary: N x 32-byte wallets, M x 17-byte rows
(wallet index u32, mint id u64, slot u32, flags u8: 1 buy, 2 big).
The engine counts the preloaded history as contiguous when its last slot is within 30 min of the feed's first slot: build it right
before the start (the inputs stay missing until the history covers 24 h).

usage: fp_preload.py --out /root/dip/fpnb_preload.bin [--collect /home/moiz/sniper-data/collect] [--hours 25] [--end UNIX_S]
                     [--prev-run /root/prod/runs/dip_ams_r55.jsonl ...] [--nw 12]"""
import argparse, base64, glob, gzip, json, os, struct, sys, time, collections
from multiprocessing import Pool
import numpy as np

DISC = bytes.fromhex("bddb7fd34ee661ee")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BIG = 0.06 * 1e15


def job(a):
    fn, t_lo = a
    S, I, J, U, M, F = [], [], [], [], [], []
    try:
        with gzip.open(fn, "rt", errors="replace") as f:
            for l in f:
                if '"err":null' not in l: continue
                try: d = json.loads(l)
                except Exception: continue
                if d.get("err") is not None or (d.get("bt") or 0) < t_lo: continue
                j = 0
                for e in d.get("ev") or []:
                    try: raw = base64.b64decode(e)
                    except Exception: continue
                    if raw[:8] != DISC or len(raw) < 129: continue
                    ib = raw[56]
                    if ib not in (0, 1): continue
                    tok, = struct.unpack_from("<Q", raw, 48)
                    S.append(d["s"]); I.append(d.get("i") or 0); J.append(j); U.append(raw[57:89]); M.append(int.from_bytes(raw[8:16], "big"))
                    F.append(ib | (2 if ib == 1 and tok >= BIG else 0))
                    j += 1
    except (EOFError, OSError):
        pass
    return (np.array(S, np.uint64), np.array(I, np.uint32), np.array(J, np.uint8), np.array(U, dtype="S32") if U else np.zeros(0, "S32"),
            np.array(M, np.uint64), np.array(F, np.uint8))


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def own_from_run(fn):
    """our closed live positions (fp_f2_runs.py logic) and the shadow's row-c items of an engine log"""
    me = None; arms = collections.defaultdict(list); closes = []; realized = collections.defaultdict(list); tape = collections.defaultdict(dict)
    sh = {}; shf = {}; shc = {}
    for raw in open(fn, "rb"):
        if b'"ev":"presend_' not in raw and b'"ev":"run_start"' not in raw: continue
        if b'"ev":"presend_attempt' in raw or b'"ev":"presend_wide_' in raw or b'"ev":"presend_live_fpnb' in raw: continue
        try: d = json.loads(raw)
        except Exception: continue
        ev = d.get("ev")
        if ev == "run_start": me = me or d.get("wallet")
        elif ev == "presend_live_arm":
            tr = d.get("trig") or d.get("dump") or {}
            arms[(d.get("mint") or tr.get("mint"), d.get("kind") or "T2", d.get("w"))].append(d)
        elif ev == "presend_live_close": closes.append(d)
        elif ev == "presend_live_realized": realized[(d["mint"], d.get("pid"))].append(d)
        elif ev == "presend_live_tape": tape[d["mint"]][(d["slot"], d["idx"], d.get("j", 0))] = d
        elif ev == "presend_arm": sh[(d["mint"], d["w"])] = d["t"]
        elif ev == "presend_fill" and d.get("row") == "c": shf[(d["mint"], d["w"])] = (d.get("m") or {}).get("t")
        elif ev == "presend_exit" and d.get("row") == "c": shc[(d["mint"], d["w"])] = d.get("net_cheap")
    used = collections.Counter(); own = []
    for c in closes:
        key = (c["mint"], c.get("pid")); rl = realized[key][used[key]] if used[key] < len(realized[key]) else None; used[key] += 1
        if rl is None or not c.get("buys"): continue
        kind = c.get("kind") or "T2"; b0 = min(c["buys"], key=lambda b: (b["slot"], b["idx"]))
        arm = None
        for a in arms[(c["mint"], kind, c.get("w"))]:
            if ((a.get("trig") or a.get("dump") or {}).get("t") or 0) <= b0["t"]: arm = a
        tr = (arm or {}).get("trig") or (arm or {}).get("dump") or {}
        whale = tr.get("wallet") if kind == "T2" else tr.get("seller")
        excl = {me}
        if kind == "T2" and tr.get("wallet"): excl.add(tr["wallet"])
        for h in (arm or {}).get("holders") or []: excl.add(h["w"])
        sl = c.get("sell_lands") or ([c["sell_land"]] if c.get("sell_land") else [])
        endp = max(((x[0], x[1]) for x in sl), default=(b0["slot"] + 3, 1 << 30))
        sell_t = max((x[2] for x in sl if len(x) > 2 and x[2]), default=0)
        first = (b0["slot"], b0["idx"])
        fol = [x for x in tape[c["mint"]].values() if x["user"] != me and first < (x["slot"], x["idx"]) <= endp and x["buy"] and x["user"] not in excl]
        own.append({"k": max(b0["t"] + 3 * 10**9, sell_t), "pnl": rl["pnl"] / 1e9, "fol": len(fol), "mint": c["mint"], "whale": whale,
                    "creator": ((arm or {}).get("ann") or {}).get("creator")})
    shadow = [[(shf[k] or sh.get(k) or 0) + 2 * 10**9, v] for k, v in shc.items() if v is not None and k in shf and (shf[k] or sh.get(k))]
    return own, shadow, sorted(sh.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--collect", default="/home/moiz/sniper-data/collect")
    ap.add_argument("--hours", type=float, default=25.0, help="look-back (the engine needs >= 403,000 slots ~ 24 h; 25 h leaves a margin)")
    ap.add_argument("--end", type=float, default=None, help="unix seconds (default: the newest chunk's end)")
    ap.add_argument("--prev-run", nargs="*", default=[])
    ap.add_argument("--nw", type=int, default=int(os.environ.get("NW", "12")))
    a = ap.parse_args()
    files = []
    for fn in glob.glob(f"{a.collect}/run_*/txs/txs_*.jsonl.gz"):
        try: files.append((int(os.path.basename(fn)[4:-9]), fn))
        except ValueError: pass
    if not files: sys.exit(f"no txs_*.jsonl.gz under {a.collect}/run_*/txs")
    end = a.end or max(t for t, _ in files) + 300
    t_lo = end - a.hours * 3600
    sel = sorted(fn for t, fn in files if t_lo - 300 <= t <= end)
    print(f"{len(sel)} chunk files for {time.strftime('%m-%d %H:%M', time.gmtime(t_lo))} .. {time.strftime('%m-%d %H:%M', time.gmtime(end))} UTC", flush=True)
    parts = []
    t0 = time.time()
    with Pool(a.nw) as p:
        for k, r in enumerate(p.imap_unordered(job, [(f, t_lo) for f in sel])):
            parts.append(r)
            if k % 25 == 0: print(k, len(sel), sum(len(x[0]) for x in parts), f"{time.time() - t0:.0f}s", flush=True)
    S = np.concatenate([x[0] for x in parts]); I = np.concatenate([x[1] for x in parts]); J = np.concatenate([x[2] for x in parts])
    U = np.concatenate([x[3] for x in parts]); M = np.concatenate([x[4] for x in parts]); F = np.concatenate([x[5] for x in parts])
    key = S.astype(np.uint64) * np.uint64(1 << 24) + I.astype(np.uint64) * np.uint64(64) + J.astype(np.uint64)
    _, u = np.unique(key, return_index=True)
    S, U, M, F = S[u], U[u], M[u], F[u]
    o = np.argsort(S, kind="stable"); S, U, M, F = S[o], U[o], M[o], F[o]
    wl, wi = np.unique(U, return_inverse=True)
    own, shadow, sh_arms = [], [], []
    for fn in a.prev_run:
        o_, s_, a_ = own_from_run(fn); own += o_; shadow += s_; sh_arms += a_
    own.sort(key=lambda z: z["k"]); own = own[-2000:]
    head = {"fpnb_preload": 1, "from_slot": int(S.min()) if len(S) else 0, "to_slot": int(S.max()) if len(S) else 0, "from_t": t_lo, "to_t": end,
            "hours": a.hours, "wallets": int(len(wl)), "rows": int(len(S)), "src": a.collect, "files": len(sel), "prev_run": a.prev_run,
            "built": time.time(), "own": own, "shadow": shadow[-5000:], "shadow_arms": sorted(sh_arms)[-20000:]}
    rec = np.zeros(len(S), dtype=[("w", "<u4"), ("m", "<u8"), ("s", "<u4"), ("f", "u1")])
    rec["w"] = wi.astype(np.uint32); rec["m"] = M; rec["s"] = S.astype(np.uint32); rec["f"] = F
    tmp = a.out + ".tmp"
    with open(tmp, "wb") as f:
        f.write((json.dumps(head) + "\n").encode())
        f.write(np.ascontiguousarray(wl.astype("S32")).tobytes())
        f.write(rec.tobytes())
    os.replace(tmp, a.out)
    print(f"wrote {a.out}: {len(S)} rows, {len(wl)} wallets, slots {head['from_slot']}..{head['to_slot']}, own {len(own)}, shadow {len(shadow)}, "
          f"{os.path.getsize(a.out) / 1e6:.1f} MB, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
