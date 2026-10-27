#!/usr/bin/env python3
"""FLAT study, step 1 (read-only, local raw recording only): one compact chain table of EVERY successful pump.fun trade
(TradeEvent, chain order), our wallets' failed txs, the per-slot block table (max tx index + 1, block time), and the creates.
  phase 1 (dev + validation): block time in [10-25 21:30, 10-27 18:07 PKT)   <- r27 ends 17:37; r28 (holdout) starts 18:20
  phase 2 (holdout r28)     : block time in [10-27 18:07, --hi]              <- run ONLY after FROZEN.json exists
Chunks that start at/after the phase's upper bound are never opened (holdout guard). Interest mints (every mint the live
pre-send detector armed or skipped in the studied runs) keep their trades' signatures and instruction names.
Output: /home/moiz/sniper-data/presend_flat/chain_p{1,2}.npz, ids_p{1,2}.json, ourfail_p{1,2}.json, blocks_p{1,2}.npz, creates.json
  phase 0 (older runs AMS r19/r20, FRA r21-r24, added 10-27 ~21:30 PKT): block time in [10-24 22:00, 10-25 21:30 PKT) (24 h history)
  phase 3 (r28 after the 20:58 PKT cut): [--lo (default 20:49 PKT), --hi]
usage: f1_extract.py 0|1 | f1_extract.py 2|3 --hi UNIX_S   [--procs 14]"""
import sys, os, re, gzip, json, glob, base64, struct, time, argparse, collections
import numpy as np
from multiprocessing import Pool

REC = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/presend_flat"
RUNS_LIVE = "/home/moiz/sniper-data/runs/ams/runs"
LO1, HI1 = 1792945800, 1793106420           # 10-25 21:30 PKT, 10-27 18:07 PKT
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}   # AMS, FRA
DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
HEAD = re.compile(r'\{"s":\s*(\d+),\s*"i":\s*(\d+),\s*"bt":\s*(\d+)')
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
G = {}


def b58(b):
    n = int.from_bytes(b, "big"); s = []
    while n:
        n, r = divmod(n, 58); s.append(A58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(s))


def errc(err):
    try:
        ie = err.get("InstructionError") if isinstance(err, dict) else None
        if ie:
            c = ie[1]
            if isinstance(c, dict): c = c.get("Custom", next(iter(c)))
            return f"{c}@{ie[0]}"
        return next(iter(err)) if isinstance(err, dict) else str(err)
    except Exception:
        return str(err)[:40]


def interest(runs):
    import flatlib as FL
    M = set()
    for r in runs:
        fn = FL.RUNS[r]["file"]
        for line in open(fn, errors="ignore"):
            if '"ev":"presend_live_arm"' not in line and '"ev":"presend_live_skip"' not in line: continue
            try: x = json.loads(line)
            except Exception: continue
            M.add(x["trig"]["mint"])
    return M


def one(fn):
    lo, hi = G["span"]; want = G["want"]
    T = collections.defaultdict(list); F = []; blk = {}; n = 0; trunc = None
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                n += 1
                m = HEAD.match(line)
                if not m: continue
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if bt < lo or bt >= hi: continue
                b = blk.get(s)
                if b is None or i > b[0]: blk[s] = (i, bt)
                ok = '"err":null' in line
                if ok and '"ev":[]' in line: continue
                if not ok:
                    if not any(w in line for w in OURS): continue
                    try: r = json.loads(line)
                    except Exception: continue
                    sg = (r.get("signers") or ["?"])[0]
                    if sg in OURS: F.append((r["sig"], s, i, r.get("fee") or 0, errc(r.get("err")), sg, (r.get("mints") or [""])[0]))
                    continue
                try: r = json.loads(line)
                except Exception: continue
                evs = r.get("ev")
                if isinstance(evs, str):
                    try: evs = json.loads(evs)
                    except Exception: evs = []
                tips = sum(int(v) for _, v in (r.get("tips") or []))
                sg = (r.get("signers") or ["?"])[0]
                j = 0
                for e in evs or []:
                    for ch in e.split(" "):
                        try: bb = base64.b64decode(ch + "=" * (-len(ch) % 4))
                        except Exception: continue
                        if bb[:8] == CPI: bb = bb[8:]
                        if bb[:8] != DISC or len(bb) < 225: continue
                        o = 8
                        mint = b58(bb[o:o + 32]); o += 32
                        sol, tok = struct.unpack_from("<QQ", bb, o); o += 16
                        buy = bb[o]; o += 1
                        user = b58(bb[o:o + 32]); o += 32 + 8
                        vsol, vtok = struct.unpack_from("<QQ", bb, o); o += 32 + 32
                        fbps, fee = struct.unpack_from("<QQ", bb, o); o += 16 + 32
                        cbps, cfee = struct.unpack_from("<QQ", bb, o)
                        T["s"].append(s); T["i"].append(i); T["j"].append(j); T["bt"].append(bt); T["buy"].append(buy)
                        T["sol"].append(sol); T["tok"].append(tok); T["vsol"].append(vsol); T["vtok"].append(vtok)
                        T["fbps"].append(fbps); T["cbps"].append(cbps); T["txfee"].append(r.get("fee") or 0); T["tip"].append(tips)
                        T["mint"].append(mint); T["user"].append(user); T["signer"].append(sg)
                        if mint in want:
                            T["sig"].append(r["sig"]); T["ixn"].append("|".join((r.get("ixn") or [])[:6])[:120])
                        else:
                            T["sig"].append(""); T["ixn"].append("")
                        j += 1
    except (EOFError, OSError) as ex:
        trunc = repr(ex)[:80]
    num = {}
    for k, dt in (("s", "u8"), ("i", "u4"), ("j", "u1"), ("bt", "u4"), ("buy", "u1"), ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"),
                  ("fbps", "u2"), ("cbps", "u2"), ("txfee", "u8"), ("tip", "u8")):
        num[k] = np.array(T.get(k, []), dtype=dt)
    strs = {k: T.get(k, []) for k in ("mint", "user", "signer", "sig", "ixn")}
    bs = np.array(sorted((s, v[0], v[1]) for s, v in blk.items()), dtype=np.int64).reshape(-1, 3)
    return fn, num, strs, F, bs, n, trunc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", type=int); ap.add_argument("--hi", type=int); ap.add_argument("--lo", type=int); ap.add_argument("--procs", type=int, default=14)
    A = ap.parse_args()
    if A.phase == 0:
        # the older runs (AMS r19, r20, FRA r21-r24, 10-25 22:20 -> 10-26 19:50 PKT): their 24 h whale history starts 10-24 22:20
        lo, hi = 1792861200, LO1; runs_rec = ["run_20261024_1425", "run_20261025_1420"]; live = ["a19", "a20", "f21", "f22", "f23", "f24"]
    elif A.phase == 3:
        # r28 after the holdout cut (20:58 PKT): 10 min of overlap with phase 2 (late-written blocks), duplicates removed on load
        if not os.path.exists("/home/moiz/sniper/ops/strategies/presend/flat/FROZEN.json"):
            sys.exit("holdout guard: FROZEN.json missing; phase 3 refused")
        lo, hi = (A.lo or 1793116740 - 600), A.hi; runs_rec = ["run_20261027_1410"]; live = ["r28"]
    elif A.phase == 1:
        lo, hi = LO1, HI1; runs_rec = ["run_20261025_1420", "run_20261026_1415"]; live = ["r24", "r25", "r26", "r27"]
    else:
        if not os.path.exists("/home/moiz/sniper/ops/strategies/presend/flat/FROZEN.json"):
            sys.exit("holdout guard: FROZEN.json missing; phase 2 refused")
        lo, hi = HI1, A.hi; runs_rec = ["run_20261026_1415", "run_20261027_1410"]; live = ["r24", "r25", "r26", "r27", "r28"]
    G["span"] = (lo, hi); G["want"] = interest(live)
    files = []
    for run in runs_rec:
        for f in sorted(glob.glob(f"{REC}/{run}/txs/txs_*.jsonl.gz")):
            ts = int(os.path.basename(f)[4:14])
            if ts >= hi or ts < lo - 400: continue
            if time.time() - os.path.getmtime(f) < 120: continue          # a chunk still being copied
            files.append(f)
    t0 = time.time()
    print(f"phase {A.phase}: span {time.strftime('%m-%d %H:%M', time.gmtime(lo + 18000))} -> {time.strftime('%m-%d %H:%M', time.gmtime(hi + 18000))} PKT, "
          f"{len(files)} chunks, interest mints {len(G['want'])}", flush=True)
    ids = {k: {} for k in ("m", "w", "x")}
    def intern(tab, arr):
        d = ids[tab]; out = np.empty(len(arr), np.uint32)
        for k, s in enumerate(arr):
            v = d.get(s)
            if v is None: v = d[s] = len(d)
            out[k] = v
        return out
    cols = collections.defaultdict(list); fails = {}; blocks = []; sigs = {}
    base = 0
    with Pool(A.procs) as p:
        for k, (fn, num, strs, F, bs, n, trunc) in enumerate(p.imap_unordered(one, files)):
            if trunc: print("TRUNCATED", fn, trunc, flush=True)
            for c, v in num.items(): cols[c].append(v)
            cols["mint"].append(intern("m", strs["mint"])); cols["user"].append(intern("w", strs["user"])); cols["signer"].append(intern("w", strs["signer"]))
            cols["ixn"].append(intern("x", strs["ixn"]))
            # signatures of interest-mint trades: kept by a global row number assigned below (chunk order -> fix after the sort)
            sg = np.array([1 if x else 0 for x in strs["sig"]], np.uint8)
            cols["has_sig"].append(sg)
            for q, x in enumerate(strs["sig"]):
                if x: sigs[base + q] = x
            base += len(strs["sig"])
            for x in F: fails[x[0]] = x[1:]
            blocks.append(bs)
            if k % 50 == 0: print(k, os.path.basename(fn), n, len(num["s"]), f"{time.time() - t0:.0f}s", flush=True)
    T = {c: np.concatenate(v) for c, v in cols.items()}
    rowid = np.arange(len(T["s"]), dtype=np.int64)
    o = np.lexsort((T["j"], T["i"], T["s"]))
    T = {c: v[o] for c, v in T.items()}; rowid = rowid[o]
    dup = np.zeros(len(T["s"]), bool)
    dup[1:] = (T["s"][1:] == T["s"][:-1]) & (T["i"][1:] == T["i"][:-1]) & (T["j"][1:] == T["j"][:-1])
    T = {c: v[~dup] for c, v in T.items()}; rowid = rowid[~dup]
    sig_list = [sigs.get(int(r), "") for r in rowid]
    T["sig_ix"] = np.full(len(rowid), -1, np.int64)
    sig_tab = []
    for q, x in enumerate(sig_list):
        if x: T["sig_ix"][q] = len(sig_tab); sig_tab.append(x)
    del T["has_sig"]
    B = np.concatenate([b for b in blocks if len(b)]) if blocks else np.zeros((0, 3), np.int64)
    # per slot: max idx over chunks (a slot may straddle two chunk files / two recording runs)
    ob = np.lexsort((B[:, 1], B[:, 0])); B = B[ob]
    last = np.ones(len(B), bool); last[:-1] = B[1:, 0] != B[:-1, 0]
    B = B[last]
    ph = A.phase
    np.savez(f"{OUT}/chain_p{ph}.npz", **T)
    np.savez(f"{OUT}/blocks_p{ph}.npz", slot=B[:, 0], maxi=B[:, 1], bt=B[:, 2])
    json.dump({"m": list(ids["m"]), "w": list(ids["w"]), "x": list(ids["x"]), "sig": sig_tab}, open(f"{OUT}/ids_p{ph}.json", "w"))
    json.dump(fails, open(f"{OUT}/ourfail_p{ph}.json", "w"))
    cr = {}
    for run in runs_rec:
        fnl = f"{REC}/{run}/launches.jsonl"
        if not os.path.exists(fnl): continue
        for line in open(fnl):
            try: r = json.loads(line)
            except Exception: continue
            if r.get("err") is not None or r["mint"] in cr: continue
            if r.get("bt", 0) >= hi: continue
            cr[r["mint"]] = dict(slot=r["slot"], idx=r["idx"], bt=r["bt"], creator=r.get("creator"), user=r.get("user"))
    old = {}
    if os.path.exists(f"{OUT}/creates.json"): old = json.load(open(f"{OUT}/creates.json"))
    old.update({k: v for k, v in cr.items() if k not in old})
    json.dump(old, open(f"{OUT}/creates.json", "w"))
    print(f"trades {len(T['s']):,} (dups {int(dup.sum()):,}), mints {len(ids['m']):,}, wallets {len(ids['w']):,}, sigs kept {len(sig_tab):,}, "
          f"our failed txs {len(fails):,}, slots {len(B):,} ({int(B[0, 0]) if len(B) else 0}..{int(B[-1, 0]) if len(B) else 0}), creates {len(old):,}, "
          f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
