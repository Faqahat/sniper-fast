#!/usr/bin/env python3
# GENERIC REPLAY of the candidate families on the recorded tapes (R2 + R3), read-only. One row per trigger event with
# features + our P&L per (exit rule, latency). Rules are CHOSEN on R2 and TESTED on R3 by s8_select.py.
#  Q  (F7 quiet bait, substitution): a real buy of 0.9-3 SOL on a token quiet >= 20 slots, age >= 150 slots, curve <= 45 SOL.
#     We take that buyer's place (same size, same spot; the followers' real reactions stay), the buyer's later trades are
#     removed, our exits apply. No race: latency 0.
#  M  (F6 momentum / F4 at OUR speed): a buy >= 0.5 SOL by a non-insider, price +10% over 10 slots, net flow >= +1 SOL over
#     3 slots, curve 33-60 SOL, age >= 8 slots, no sell >= 0.5 SOL earlier in the slot. We land L ms after the trigger.
#  D  (F3 / F1 dip): a sell >= 0.5 SOL that leaves the price >= 5% under its 3-slot high, curve 30-60 SOL, age >= 25 slots.
#     We land L ms after the trigger (creator-sell flag kept: F1).
# Landing: arrival(t) = slot*212 + idx/blocksize*212 ms (blocksize from core/slotsize.json, else 400; same model as
# sel/selexit2.py). Our buy goes in front of the first trade arriving >= trigger arrival + L. Guard: if the price at our
# landing is > 1.05 x the price right after the trigger, the buy fails (-0.0005 SOL). Costs: pump fee (event bps) both
# sides + 0.0035 SOL per round trip. Exits fill at the end of the decision slot (timer / TP / SL / cap); ladders are
# simulated as sequential partial sells. Followers keep their SOL amounts (they get fewer tokens after our buy);
# follower slippage failures are NOT modeled (optimistic for big sizes).
import sys, os, json, gzip, glob, zlib, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import s1_trips as S1
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/strategies/replay"
SMS = 212.0
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize.json")).items()}
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9
LATS = (35, 50)
TIMERS = {"Q": (20, 50, 100, 200, 400, 800), "M": (4, 10, 20, 45, 70), "D": (4, 6, 10, 20, 45, 70, 141)}
TPSL = {"Q": [(1.1, 0.85, 800), (1.2, 0.85, 800), (1.3, 0.8, 1500), (1.5, 0.8, 1500)],
        "M": [(1.05, 0.95, 70), (1.1, 0.9, 70), (1.2, 0.9, 140)],
        "D": [(1.05, 0.9, 30), (1.1, 0.9, 141), (1.04, 0.96, 141)]}
LADDER = {"M": [(0.25, 10), (0.25, 20), (0.25, 30), (0.25, 45)], "Q": [(0.34, 100), (0.33, 300), (0.33, 600)]}
SIZES = {"M": (1.0,), "D": (0.5,)}

def arr(t): return t[0] * SMS + t[1] / max(SS.get(t[0], 400), t[1] + 1) * SMS

def run_path(path, k_in, V, T, X, q, fr, s_buy, kind):
    """our position of q tokens bought with X lamports into (V, T) right before path[k_in]. Returns ({exit: proceeds SOL}, graduated)"""
    V += X; T -= q; p_in = X / q
    timers = TIMERS[kind]; tpsl = TPSL[kind]
    kt = [f"t{N}" for N in timers]; kx = [f"tp{tp}_sl{sl}_c{cap}" for tp, sl, cap in tpsl]
    need = len(kt) + len(kx); res = {}; trig = [None] * len(tpsl)
    k = k_in; grad = False
    while True:
        t = path[k] if k < len(path) else None
        ts = t[0] if t is not None else None
        val = None
        # (V, T) now = end-of-slot state for every slot before ts: settle exits that are due
        for N, key in zip(timers, kt):
            if key not in res and (t is None or ts > s_buy + N):
                if val is None: val = V * q // (T + q) * (1 - fr) / 1e9
                res[key] = val
        for j, (tp, sl, cap) in enumerate(tpsl):
            key = kx[j]
            if key in res: continue
            if (trig[j] is not None and (t is None or ts > trig[j])) or t is None or ts > s_buy + cap:
                if val is None: val = V * q // (T + q) * (1 - fr) / 1e9
                res[key] = val
        if len(res) >= need or t is None: break
        Vp, Tp = V, T
        if t[10]: d = T * t[11] // (V + t[11]); V += t[11]; T -= d
        else: so = V * t[12] // (T + t[12]); V -= so; T += t[12]
        if V >= GRADV or T <= 0:
            grad = True; val = Vp * q // (Tp + q) * (1 - fr) / 1e9
            for key in kt + kx: res.setdefault(key, val)
            break
        m = (V / T) / p_in
        for j, (tp, sl, cap) in enumerate(tpsl):
            if trig[j] is None and ts <= s_buy + cap and (m >= tp or m <= sl): trig[j] = ts
        k += 1
    return res, grad

def ladder(path, k_in, V, T, X, q, fr, s_buy, legs):
    V += X; T -= q; left = q; got = 0.0; li = 0; k = k_in
    legs = sorted(legs, key=lambda x: x[1])
    while li < len(legs):
        t = path[k] if k < len(path) else None
        due = s_buy + legs[li][1]
        if t is None or t[0] > due:
            kk = int(q * legs[li][0]) if li < len(legs) - 1 else left
            kk = min(kk, left)
            so = V * kk // (T + kk); got += so * (1 - fr) / 1e9; V -= so; T += kk; left -= kk; li += 1
            continue
        if t[10]: d = T * t[11] // (V + t[11]); V += t[11]; T -= d
        else: so = V * t[12] // (T + t[12]); V -= so; T += t[12]
        if V >= GRADV or T <= 0:
            so = V * left // (T + left); got += so * (1 - fr) / 1e9; left = 0; break
        k += 1
    return got

def work(key):
    run, b = key
    L = S1.load_launches(run)
    mints = {m for m in L if zlib.crc32(m.encode()) % 256 == b}
    tra = S1.read(run, b, mints); rows = []
    for m, tr in tra.items():
        c = L[m]; S, cidx, creator, signer, csig, cbt, may = c
        if may or not tr or any(t[13] < 25e9 or t[13] > 200e9 or not t[14] for t in tr[:50]): continue
        n = len(tr)
        ins = {creator, signer}; prev = cidx
        for t in tr:
            if t[4] == csig: continue
            if t[0] == S and t[1] in (prev, prev + 1) and t[10]: ins.add(t[9]); prev = t[1]
            elif t[0] > S: break
        pre = [S1.pre_state(t) for t in tr]
        ppre = [v / tk if tk else 0 for v, tk in pre]; ppost = [t[13] / t[14] if t[14] else 0 for t in tr]
        ath = 0.0; peakv = 0.0
        fr = 0.0125
        for k, t in enumerate(tr):
            if t[13] >= GRADV: break
            age = t[0] - S
            fr = 0.0125
            kind = None
            if t[10] and t[9] not in ins:
                quiet = t[0] - tr[k - 1][0] if k > 0 else -1
                vpre = pre[k][0] / 1e9
                if 0.9e9 <= t[11] <= 3e9 and quiet >= 20 and age >= 150 and vpre <= 45:
                    kind = "Q"
                elif t[11] >= 0.5e9 and age >= 8 and 33 <= vpre <= 60:
                    # momentum context
                    j = k - 1; kk = None
                    while j >= 0 and tr[j][0] >= t[0] - 10: kk = j; j -= 1
                    ret10 = (ppre[k] / ppre[kk] - 1) if kk is not None and ppre[kk] else 0
                    flow = t[11]; j = k - 1; big_sell_same = False
                    while j >= 0 and tr[j][0] >= t[0] - 3:
                        if tr[j][9] != t[9]: flow += tr[j][11] if tr[j][10] else -tr[j][11]
                        if tr[j][0] == t[0] and not tr[j][10] and tr[j][11] >= 0.5e9: big_sell_same = True
                        j -= 1
                    if ret10 >= 0.10 and flow >= 1e9 and not big_sell_same: kind = "M"; feat = dict(ret10=round(ret10, 3), flow=round(flow / 1e9, 2))
            elif not t[10] and t[11] >= 0.5e9 and age >= 25 and 30 <= pre[k][0] / 1e9 <= 60:
                j = k; pmax = ppre[k]
                while j >= 0 and tr[j][0] >= t[0] - 3: pmax = max(pmax, ppre[j], ppost[j]); j -= 1
                dd = 1 - ppost[k] / pmax if pmax else 0
                if dd >= 0.05: kind = "D"; feat = dict(dd=round(dd, 3), dev=int(t[9] == creator), drop1=round(1 - ppost[k] / ppre[k], 3))
            if kind is None:
                ath = max(ath, ppost[k]); peakv = max(peakv, t[13]); continue
            base = dict(run=run, m=m, kind=kind, s=t[0], i=t[1], age=age, sz=round(t[11] / 1e9, 3), vpre=round(pre[k][0] / 1e9, 2),
                        ath_r=round(ppre[k] / ath, 3) if ath else 1.0, peakv=round(peakv / 1e9, 1), ntr=k, bt=t[3], u=t[9][:8])
            if kind == "Q":
                base["quiet"] = t[0] - tr[k - 1][0]
                U = t[9]; path = [x for x in tr[k + 1:] if x[9] != U]
                V, T = pre[k]; X = t[11]; q = t[12]
                cost = (t[11] + t[15] + t[16]) / 1e9 + FIX
                res, grad = run_path(path, 0, V, T, X, q, fr, t[0], "Q")
                res["lad"] = ladder(path, 0, V, T, X, q, fr, t[0], LADDER["Q"])
                rows.append(dict(base, lat=0, B=round(t[11] / 1e9, 3), grad=int(grad), pnl={e: round(v - cost, 5) for e, v in res.items()}))
            else:
                base.update(feat)
                a0 = arr(t)
                for Lm in LATS:
                    ke = k + 1
                    while ke < n and arr(tr[ke]) < a0 + Lm: ke += 1
                    if ke >= n: continue
                    Vb, Tb = tr[ke - 1][13], tr[ke - 1][14]
                    ratio = (Vb / Tb) / ppost[k]
                    for B in SIZES[kind]:
                        if ratio > GUARD:
                            rows.append(dict(base, lat=Lm, B=B, fail=1, pnl=None)); continue
                        X = int(B * 1e9 / (1 + fr)); q = Tb * X // (Vb + X)
                        s_buy = max(tr[ke - 1][0], t[0])
                        res, grad = run_path(tr, ke, Vb, Tb, X, q, fr, s_buy, kind)
                        if kind in LADDER: res["lad"] = ladder(tr, ke, Vb, Tb, X, q, fr, s_buy, LADDER[kind])
                        cost = B + FIX
                        rows.append(dict(base, lat=Lm, B=B, fail=0, ratio=round(ratio, 4), grad=int(grad), pnl={e: round(v - cost, 5) for e, v in res.items()}))
            ath = max(ath, ppost[k]); peakv = max(peakv, t[13])
    fn = f"{OUT}/{run}_b{b:03d}.jsonl.gz"
    with gzip.open(fn, "wt", compresslevel=3) as f:
        for r in rows: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    return run, b, len(rows)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    keys = [(r, b) for r in ("R2", "R3") for b in range(256)]
    if len(sys.argv) > 1 and sys.argv[1] == "test": keys = [("R2", 0), ("R3", 0)]
    tot = 0; done = 0
    with Pool(int(os.environ.get("PROCS", "9"))) as p:
        for run, b, nr in p.imap_unordered(work, keys):
            tot += nr; done += 1
            if done % 64 == 0: print(f"{done}/{len(keys)} buckets, {tot} rows", flush=True)
    print("DONE rows", tot, flush=True)
