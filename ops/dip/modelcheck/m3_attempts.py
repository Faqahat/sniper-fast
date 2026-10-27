#!/usr/bin/env python3
# MODEL CHECK step 3 (read-only): every wallet's buy ATTEMPTS right after each dump, successful and failed, with the price each
# one faced. Dump = sell >= 1 SOL, move <= -2%, curve < 100 SOL, token >= 5 slots and <= 600 s old (day arrays R1..R4).
# Window: the dump's slot .. +3 slots. Successful buys from the day arrays; failed txs from raw/<run>/*.fail.npz (m0_raw.py)
# matched by mint crc32 and (slot, index). A failed tx counts as a BUY attempt if its ixn names a buy, or if it is unnamed
# (routed) and the payer holds none of the token at that point (else it may be a sell -> left out).
# One row per (dump, wallet): first attempt (slot, idx, block-position delay, price before it / post-dump price), outcome
# (any buy landed), SOL bought, number of failed txs, their main error code, the ratio at the landed buy, wallet held before.
# -> /home/moiz/sniper-data/modelcheck/att_<day>.npz         usage: nice python3 -I m3_attempts.py R2
import sys, os, json, glob, zlib, time, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mc_lib as M
RUN = {"R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4"}
TGS = {zlib.crc32(l.strip().encode()) for l in open(os.path.join(HERE, "targets.txt")) if l.strip()}
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize.json")).items()}
def arrival(s, i): return s * M.SMS + i / max(SS.get(s, 400), i + 1) * M.SMS

def main(day):
    t0 = time.time()
    d = M.load_day(day); meta = d["meta"]
    mi = {zlib.crc32(x["m"].encode()): t for t, x in enumerate(meta)}
    # failed txs of this run on the day's tokens
    F = collections.defaultdict(list); nf = 0; KEYS = np.fromiter(mi.keys(), np.int64)
    for f in sorted(glob.glob(f"{M.OUT}/raw/{RUN[day]}/*.fail.npz") + glob.glob(f"{M.OUT}/raw/{RUN[day]}/*.tgfail.npz")):
        z = np.load(f); mt = z["mint"]
        sel = np.flatnonzero(np.isin(mt, KEYS))
        zs = z["s"][sel].tolist(); zi = z["i"][sel].tolist(); zp = z["payer"][sel].tolist(); zc = z["code"][sel].tolist(); zk = z["kind"][sel].tolist()
        for a, b, c, e, g, h in zip(mt[sel].tolist(), zs, zi, zp, zc, zk):
            F[mi[a]].append((b, c, e, g, h))
        nf += len(sel)
    print(f"{day}: {nf} failed pump txs on {len(F)} tokens ({time.time() - t0:.0f} s)", flush=True)
    cols = collections.defaultdict(list)
    ndump = 0
    for t in range(len(meta)):
        n = int(d["cnt"][t])
        if n < 5: continue
        tp = M.Tape(d, t); o = tp.o
        mv = d["move"][o:o + n]; age = d["age"][o:o + n]
        dumps = [j for j in range(n) if (not tp.B[j]) and tp.SOL[j] >= 1e9 and mv[j] <= -2.0 and tp.V[j] < 100e9 and 5 <= age[j] <= 2830]
        if not dumps: continue
        fl = sorted(F.get(t, []))
        fkeys = [(x[0], x[1]) for x in fl]
        # running token balance per wallet (successful trades), to classify unnamed failed txs
        import bisect
        base = collections.defaultdict(float); bp = 0
        for j0 in dumps:
            ndump += 1
            s0 = tp.S[j0]; i0 = tp.I[j0]; a0 = tp.A[j0]; post = tp.V[j0] / tp.T[j0]
            while bp <= j0:
                base[tp.U[bp]] += tp.TK[bp] if tp.B[bp] else -tp.TK[bp]; bp += 1
            bal = collections.defaultdict(float, base)
            ev = []
            j = j0 + 1
            while j < n and tp.S[j] <= s0 + 3:
                ev.append((tp.S[j], tp.I[j], 1, j)); j += 1
            k0 = bisect.bisect_right(fkeys, (s0, i0))
            k = k0
            while k < len(fl) and fl[k][0] <= s0 + 3:
                ev.append((fl[k][0], fl[k][1], 0, k)); k += 1
            ev.sort()
            V = tp.V[j0]; T = tp.T[j0]
            per = {}; tg_seen = 0; solb = 0.0
            dumper = tp.U[j0]
            for s, i, ok, x in ev:
                ratio = (V / T) / post; dl = arrival(s, i) - a0
                if ok:
                    u = tp.U[x]
                    if tp.B[x]:
                        r = per.get(u)
                        if r is None: r = per[u] = dict(s=s, i=i, dl=dl, ratio=ratio, ok=1, sol=0.0, nfail=0, code=0, rok=ratio, held=bal[u] > 0, tga=tg_seen, sola=solb)
                        elif r["ok"] == 0: r["ok"] = 1; r["rok"] = ratio
                        r["sol"] += tp.SOL[x]
                        bal[u] += tp.TK[x]; solb += tp.SOL[x]
                        if u in TGS: tg_seen += 1
                    else:
                        bal[u] -= tp.TK[x]
                    V = tp.V[x]; T = tp.T[x]
                else:
                    s_, i_, payer, code, kind = fl[x]
                    if kind == 2: continue
                    if kind == 0 and bal[payer] > 0: continue
                    if payer == dumper: continue                 # the dumper's own duplicate sells
                    r = per.get(payer)
                    if r is None: r = per[payer] = dict(s=s, i=i, dl=dl, ratio=ratio, ok=0, sol=0.0, nfail=0, code=code, rok=0.0, held=bal[payer] > 0, tga=tg_seen, sola=solb)
                    r["nfail"] += 1
                    if r["code"] == 0: r["code"] = code
            for u, r in per.items():
                cols["k"].append(o + j0); cols["u"].append(u); cols["s"].append(r["s"]); cols["i"].append(r["i"]); cols["dl"].append(r["dl"])
                cols["ratio"].append(r["ratio"]); cols["ok"].append(r["ok"]); cols["sol"].append(r["sol"]); cols["nfail"].append(r["nfail"])
                cols["code"].append(r["code"]); cols["rok"].append(r["rok"]); cols["held"].append(r["held"]); cols["dsol"].append(tp.SOL[j0])
                cols["age"].append(age[j0]); cols["curve"].append(tp.V[j0]); cols["dmove"].append(mv[j0])
                cols["tga"].append(r["tga"]); cols["sola"].append(r["sola"])
        if (t + 1) % 3000 == 0: print(f"  {day}: {t + 1}/{len(meta)} tokens, {ndump} dumps, {len(cols['k'])} rows, {time.time() - t0:.0f} s", flush=True)
    A = {k: np.array(v) for k, v in cols.items()}
    np.savez(f"{M.OUT}/att_{day}.npz", **A)
    print(f"{day}: DONE dumps {ndump}, rows {len(A['k'])}, ok {int(A['ok'].sum())} ({time.time() - t0:.0f} s)", flush=True)

if __name__ == "__main__":
    main(sys.argv[1])
