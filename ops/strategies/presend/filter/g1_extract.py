#!/usr/bin/env python3
"""PRESEND FILTER, step 1 (read-only, local raw recording only): a compact table of EVERY pump.fun trade (successful txs), plus the
failed txs that touch a mint of interest (any mint the pre-send detector armed / skipped / shadow-armed in any studied run), plus a
per-signer count of failed pump txs (all mints). Recording: collector runs 10-24 -> 10-27 (24/7 raw recording, keeper copy).
HOLDOUT GUARD: nothing at or after block time CAP (10-27 06:20 PKT) is read: AMS run 26 starts 06:59 PKT and is never touched.
Output per raw chunk: /home/moiz/sniper-data/presend_filter/g1/<run>__<chunk>.npz (+ .json with the failed-signer counts).
usage: g1_extract.py [procs]
DISK: writes ~35 GB of per-chunk npz files (unicode arrays); run g2_build.py + g2b_fails.py right after, then delete g1/ (done 10-27)."""
import sys, os, re, gzip, json, glob, base64, struct, time, collections
import numpy as np
from multiprocessing import Pool

CAP = 1793064600            # 10-27 06:20 PKT (unix s). AMS r26 = 06:59 PKT onward: never read.
RUNS = ["run_20261024_1425", "run_20261025_1420", "run_20261026_1415"]
REC = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/presend_filter/g1"
LIVE = "/home/moiz/sniper-data/presend_filter/live"
DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", PUMP, "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
       "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"}
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


def interest():
    M = set()
    for fn in glob.glob(f"{LIVE}/*.jsonl"):
        if "r26" in fn: continue                 # holdout guard (never present here anyway)
        for line in open(fn):
            if '"presend_' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            ev = r.get("ev")
            if ev in ("presend_live_arm", "presend_live_skip"): M.add(r["trig"]["mint"])
            elif ev == "presend_arm": M.add(r["mint"])
    return M


def one(fn):
    want = G["want"]
    T = collections.defaultdict(list); F = collections.defaultdict(list); fc = collections.Counter(); n = 0; trunc = None
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                n += 1
                ok = '"err":null' in line
                if ok and '"ev":[]' in line: continue
                try: r = json.loads(line)
                except Exception: continue
                if r.get("bt", 0) >= CAP: continue
                sg = (r.get("signers") or ["?"])[0]
                if not ok:
                    pr = r.get("progs") or []
                    mints = r.get("mints") or []
                    if PUMP in pr: fc[sg] += 1
                    hit = [m for m in mints if m in want]
                    if hit:
                        ns = "|".join(x for x in pr if x not in STD)
                        F["s"].append(r["s"]); F["i"].append(r["i"]); F["signer"].append(sg); F["mint"].append(hit[0]); F["err"].append(errc(r.get("err")))
                        F["fee"].append(r.get("fee") or 0); F["cup"].append(r.get("cup") or 0); F["cul"].append(r.get("cul") or 0); F["prog"].append(ns[:90])
                        F["sig"].append(r["sig"]); F["bt"].append(r["bt"])
                    continue
                evs = r.get("ev")
                if isinstance(evs, str):
                    try: evs = json.loads(evs)
                    except Exception: evs = []
                tips = sum(int(v) for _, v in (r.get("tips") or []))
                ns = "|".join(x for x in (r.get("progs") or []) if x not in STD)
                j = 0
                for e in evs or []:
                    for ch in e.split(" "):
                        try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
                        except Exception: continue
                        if b[:8] == CPI: b = b[8:]
                        if b[:8] != DISC or len(b) < 225: continue
                        o = 8
                        mint = b58(b[o:o + 32]); o += 32
                        sol, tok = struct.unpack_from("<QQ", b, o); o += 16
                        buy = b[o]; o += 1
                        user = b58(b[o:o + 32]); o += 32 + 8
                        vsol, vtok = struct.unpack_from("<QQ", b, o); o += 32 + 32
                        fbps, fee = struct.unpack_from("<QQ", b, o); o += 16 + 32
                        cbps, cfee = struct.unpack_from("<QQ", b, o)
                        T["s"].append(r["s"]); T["i"].append(r["i"]); T["j"].append(j); T["bt"].append(r["bt"])
                        T["mint"].append(mint); T["user"].append(user); T["signer"].append(sg); T["buy"].append(buy)
                        T["sol"].append(sol); T["tok"].append(tok); T["vsol"].append(vsol); T["vtok"].append(vtok); T["fbps"].append(fbps); T["cbps"].append(cbps)
                        T["txfee"].append(r.get("fee") or 0); T["cup"].append(r.get("cup") or 0); T["cul"].append(r.get("cul") or 0); T["tip"].append(tips)
                        T["prog"].append(ns[:90]); T["sig"].append(r["sig"]); T["ixn"].append("|".join((r.get("ixn") or [])[:4])[:60])
                        j += 1
    except (EOFError, OSError) as ex:
        trunc = repr(ex)[:80]
    return fn, dict(T), dict(F), fc, n, trunc


def save(fn, T, F, fc):
    run = fn.split("/")[-3]; ch = os.path.basename(fn).split(".")[0]
    o = f"{OUT}/{run}__{ch}"
    tt = {}
    if T:
        for k, dt in (("s", "u8"), ("i", "u4"), ("j", "u1"), ("bt", "u4"), ("buy", "u1"), ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"),
                      ("fbps", "u2"), ("cbps", "u2"), ("txfee", "u8"), ("cup", "u8"), ("cul", "u4"), ("tip", "u8")):
            tt["t_" + k] = np.array(T[k], dtype=dt)
        for k in ("mint", "user", "signer", "prog", "sig", "ixn"): tt["t_" + k] = np.array(T[k])
    if F:
        for k, dt in (("s", "u8"), ("i", "u4"), ("fee", "u8"), ("cup", "u8"), ("cul", "u4"), ("bt", "u4")): tt["f_" + k] = np.array(F[k], dtype=dt)
        for k in ("signer", "mint", "err", "prog", "sig"): tt["f_" + k] = np.array(F[k])
    np.savez(o + ".npz.tmp.npz", **tt)
    os.rename(o + ".npz.tmp.npz", o + ".npz")
    json.dump(fc, open(o + ".json", "w"))


if __name__ == "__main__":
    procs = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    t0 = time.time()
    G["want"] = interest()
    files = []
    for run in RUNS:
        for f in sorted(glob.glob(f"{REC}/{run}/txs/txs_*.jsonl.gz")):
            ts = int(os.path.basename(f)[4:14])
            if ts >= CAP: continue                 # holdout guard: chunks starting at/after the cap are never opened
            if time.time() - os.path.getmtime(f) < 180: continue
            o = f"{OUT}/{run}__{os.path.basename(f).split('.')[0]}.npz"
            if os.path.exists(o): continue
            files.append(f)
    print(f"interest mints {len(G['want'])}, files {len(files)}", flush=True)
    nt = 0
    with Pool(procs) as p:
        for k, (fn, T, F, fc, n, trunc) in enumerate(p.imap_unordered(one, files)):
            save(fn, T, F, fc)
            nt += len(T.get("s", []))
            if trunc: print("TRUNCATED", fn, trunc, flush=True)
            if k % 25 == 0: print(k, os.path.basename(fn), n, len(T.get("s", [])), len(F.get("s", [])), f"{time.time() - t0:.0f}s", flush=True)
    print(f"done trades {nt:,} {time.time() - t0:.0f}s")
