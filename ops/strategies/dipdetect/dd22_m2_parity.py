#!/usr/bin/env python3
# M2 parity export (agent 10-25 ~01:30 PKT) for `cargo test --release --lib dip_model` (src/dip_model.rs):
#   tokens of R4 and R3 (the clean holdouts; no block-size table there, as live) with ALL their curve trades exactly as the
#   engine's token book receives them (slot, tx index, event index, signature, user, side, SOL, tokens, virtual reserves,
#   fee bps), rebuilt from the phase-A rows the day arrays were built from (p1_build.stage_a rules: no failed txs, one row per
#   (signature, event index), chain order) and CHECKED against the day arrays; per study dump row (every >= 2% sell row of
#   dd1_<day>.npz on the token) the 25 Python feature values (float32, written as exact strings), the Python score of the model
#   (dd_gbdt, = pred_<name>.npy) and the study envelope flag (dd_lib.load).
# Tokens: those whose bucket (crc32(mint) % 256) is in a fixed random set (bounded reading of phase A), stratified: tokens with
# a Stage A pick first, then in-envelope ones, then any; at most MAXTR trades per token.
# -> testdata/dip_m2_parity.json + testdata/dip_m2_bundle.json (copy of the bundle the test loads)
# usage: python3 dd22_m2_parity.py [tokens_per_day] [procs]
import sys, os, json, gzip, glob, zlib, hashlib, shutil, time
import numpy as np
from multiprocessing import Pool
import dd_lib as L
import dd_gbdt as GT
OUT = L.OUT; REPO = "/home/moiz/sniper"
NAME = "v3_reg4_top25"
BUNDLE = f"{OUT}/m2_{NAME}.json"
DAYDIR = {"R3": "/home/moiz/sniper-data/strategies/patterns", "R4": OUT}
RUN = {"R3": "run_20261023_1426", "R4": "run_20261024_1425"}
PHA = {"R3": ["/home/moiz/sniper-data/collect/phaseA_r3", "/home/moiz/sniper-data/strategies/phaseA_r3tail"],
       "R4": ["/home/moiz/sniper-data/strategies/bukp/phaseA_r4", f"{OUT}/phaseA_r4b"]}
NBK = {"R3": 14, "R4": 48}          # buckets read per day
MAXTR = 2500
NTOK = int(sys.argv[1]) if len(sys.argv) > 1 else 130
PROCS = int(sys.argv[2]) if len(sys.argv) > 2 else 5

def read_bucket(arg):
    day, b, mints = arg
    out = {m: [] for m in mints}; seen = set()
    for d in PHA[day]:
        for f in sorted(glob.glob(f"{d}/b{b:03d}/*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    e = line.index('"', 6); m = line[6:e]
                    if m not in out: continue
                    r = json.loads(line)
                    if r[12] or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    out[m].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[16], r[17], r[18], r[19], r[22] if r[22] is not None else 95, r[23] if r[23] is not None else 30))
            except (EOFError, OSError, zlib.error, ValueError): pass
    for m in out: out[m].sort(key=lambda t: (t[0], t[1], t[2]))
    return day, b, out

if __name__ == "__main__":
    t0 = time.time()
    bsha = hashlib.sha256(open(BUNDLE, "rb").read()).hexdigest()
    B = json.load(open(BUNDLE)); thr = float(B["thr_default"])
    m = json.load(open(f"{OUT}/model_{NAME}.json")); E = [np.array(e, np.float64) for e in m["edges"]]
    rng = np.random.default_rng(20261025)
    plan = {}; rowsel = {}
    for day in ("R4", "R3"):
        zf = np.load(f"{OUT}/dd1_{day}.npz"); z = {k: zf[k] for k in ("k", "tok", "F", "X", "f1")}; M = json.load(open(f"{DAYDIR[day]}/day_{day}_meta.json"))["meta"]
        dzf = np.load(f"{DAYDIR[day]}/day_{day}.npz"); dz = {k: dzf[k] for k in ("tok", "s", "i", "buy", "sol", "tokn", "vsol", "vtok", "uid")}   # loaded once
        Xall = np.concatenate([z["F"], z["X"], z["f1"][:, None]], 1).astype(np.float32)
        f = lambda k: Xall[:, L.FNI[k]]
        env = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)   # = dd_lib.load
        P = np.mean([GT.predict(mm, GT.binize(Xall[:, m["cols"]], E)) for mm in m["models"]], 0)
        cnt = np.bincount(dz["tok"], minlength=len(M)); off = np.concatenate([[0], np.cumsum(cnt)[:-1]])
        bks = set(rng.choice(256, NBK[day], replace=False).tolist())
        tok = z["tok"]; ut = np.unique(tok)
        cand = [t for t in ut.tolist() if zlib.crc32(M[t]["m"].encode()) % 256 in bks and cnt[t] <= MAXTR]
        has_pick = {t for t in tok[env & (P >= thr)].tolist()}; has_env = {t for t in tok[env].tolist()}
        a = [t for t in cand if t in has_pick]; b_ = [t for t in cand if t in has_env and t not in has_pick]; c_ = [t for t in cand if t not in has_env]
        rng.shuffle(a); rng.shuffle(b_); rng.shuffle(c_)
        n1 = min(len(a), int(NTOK * 0.45)); n2 = min(len(b_), int(NTOK * 0.40)); n3 = min(len(c_), NTOK - n1 - n2)
        pick = sorted(a[:n1] + b_[:n2] + c_[:n3])
        print(f"{day}: {len(cand)} candidate tokens in {len(bks)} buckets (pick {len(a)}, env {len(b_)}, other {len(c_)}) -> {len(pick)} tokens "
              f"({n1}/{n2}/{n3}), trades {int(cnt[pick].sum())}", flush=True)
        plan[day] = (M, dz, off, cnt, pick)
        rowsel[day] = (z, Xall, env, P)
    # phase-A rows of the chosen tokens
    jobs = []
    for day, (M, dz, off, cnt, pick) in plan.items():
        byb = {}
        for t in pick: byb.setdefault(zlib.crc32(M[t]["m"].encode()) % 256, []).append(M[t]["m"])
        jobs += [(day, b, ms) for b, ms in byb.items()]
    tr = {}
    with Pool(PROCS) as p:
        for k, (day, b, out) in enumerate(p.imap_unordered(read_bucket, jobs), 1):
            tr.update({(day, mm): v for mm, v in out.items()})
            if k % 10 == 0: print(f"  {k}/{len(jobs)} buckets read, {time.time() - t0:.0f} s", flush=True)
    # launches
    lau = {}
    for day in plan:
        want = {plan[day][0][t]["m"] for t in plan[day][4]}
        for l in open(f"/home/moiz/sniper-data/collect/{RUN[day]}/launches.jsonl"):
            try: c = json.loads(l)
            except Exception: continue
            if c.get("mint") in want and not c.get("err"): lau[(day, c["mint"])] = c
    toks = []; nrows = 0; nbad = 0; nenv = 0; npick = 0
    for day, (M, dz, off, cnt, pick) in plan.items():
        z, Xall, env, P = rowsel[day]
        for t in pick:
            mint = M[t]["m"]; rows = tr.get((day, mint), [])
            o, n = int(off[t]), int(cnt[t])
            sl = slice(o, o + n)
            ok = len(rows) == n and all(
                (r[0], r[1], int(r[5]), float(r[6]), float(r[7]), float(r[8]), float(r[9]), zlib.crc32(r[4].encode())) ==
                (int(dz["s"][o + q]), int(dz["i"][o + q]), int(dz["buy"][o + q]), float(dz["sol"][o + q]), float(dz["tokn"][o + q]),
                 float(dz["vsol"][o + q]), float(dz["vtok"][o + q]), int(dz["uid"][o + q])) for q, r in enumerate(rows))
            if not ok:
                nbad += 1; print(f"  {day} {mint}: rebuilt tape differs from the day array ({len(rows)} vs {n} trades): skipped", flush=True); continue
            c = lau.get((day, mint))
            if c is None or c["slot"] != M[t]["S0"]:
                nbad += 1; print(f"  {day} {mint}: launch record missing / slot differs: skipped", flush=True); continue
            ri = np.flatnonzero(z["tok"] == t)
            dumps = []
            for r in ri.tolist():
                k = int(z["k"][r]) - o
                dumps.append({"k": k, "x": [repr(float(v)) for v in Xall[r, m["cols"]]], "score": repr(float(P[r])), "env": bool(env[r])})
                nenv += bool(env[r]); npick += bool(env[r] and P[r] >= thr)
            nrows += len(dumps)
            toks.append({"mint": mint, "day": day, "launch": {"slot": c["slot"], "idx": c.get("idx"), "creator": c.get("creator"), "user": c.get("user"), "sig": c.get("sig")},
                         "trades": [[r[0], r[1], r[2], r[3], r[4], bool(r[5]), r[6], r[7], r[8], r[9], r[10], r[11]] for r in rows], "dumps": dumps})
    out = {"made": time.strftime("%Y-%m-%d %H:%M PKT", time.gmtime(time.time() + 5 * 3600)), "model": NAME, "bundle_sha256": bsha, "thr": thr,
           "fn": m["fn"], "note": "trades: [slot, tx index, event index, sig, user, buy, sol, tok, vsol, vtok, fee bps, creator fee bps] in chain order; "
           "dumps: k = index in trades, x = the 25 study features (float32, exact strings), score = study score (exact), env = study envelope",
           "tokens": toks}
    json.dump(out, open(f"{REPO}/testdata/dip_m2_parity.json", "w"), separators=(",", ":"))
    shutil.copyfile(BUNDLE, f"{REPO}/testdata/dip_m2_bundle.json")
    print(f"parity: {len(toks)} tokens ({sum(1 for x in toks if x['day'] == 'R4')} R4, {sum(1 for x in toks if x['day'] == 'R3')} R3), "
          f"{sum(len(x['trades']) for x in toks)} trades, {nrows} dump rows ({nenv} in the envelope, {npick} Stage A picks), {nbad} tokens skipped, "
          f"{os.path.getsize(f'{REPO}/testdata/dip_m2_parity.json') / 1e6:.1f} MB, {time.time() - t0:.0f} s", flush=True)
