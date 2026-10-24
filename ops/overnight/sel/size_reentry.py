#!/usr/bin/env python3
# Owner 10-24 04:45 PKT ("yup"): two ideas from haqqiUUX, backtested for US.
#   1. SIZE BY CURVE DEPTH: he buys ~0.74 SOL when the curve is shallow (vSOL < 32) and ~0.3 otherwise. Our strict picks' P&L at
#      0.35 vs 0.75 SOL by post-dump vSOL / age / dump size -> does a shallow-curve size-up pay for us?
#   2. RE-ENTRY: his profit is on tokens he buys 3+ times (each next dump). Our picks: first pick on a token vs re-entries, after a
#      win vs after a loss; and "hot token" re-entry = after OUR winning pick on a token, also buy that token's next in-envelope
#      dumps at a lower score cut.
# Per window: every scored dump (IMIT1 features / score / envelope), OUR P&L at 75 / 110 ms for 0.35 and 0.75 SOL (guard 1.05,
# TP +5% / SL -10% / 6 slots, the study's follower model). usage: WIN=test|recent python3 -I size_reentry.py
import os, sys, json, time, calendar, collections
WINS = {"test": ("R2", "phaseA_sel", "10-23 06:00", "10-23 18:19"), "recent": ("R3", "phaseA_r3comp", "10-24 02:10", "10-24 05:00")}
RUN, PH, A, Bend = WINS[os.environ.get("WIN", "test")]
os.environ["RP_PHASEA_R2" if RUN == "R2" else "RP_PHASEA_R3"] = PH; os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
for k, v in dict(SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75", DIP_HS="4", DIP_BUSY="0", DIP_HLAG="0",
                 DIP_MAX_AGE="1800", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json").items():
    os.environ[k] = v
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import numpy as np
import selexit2 as X
import gbdt_np as G
import live_exits as LE
from multiprocessing import Pool
M = json.load(open(f"{D}/IMIT1.json")); FE = M["features"]; TH = M["thresholds"]
pk = lambda s: calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
T0, T1 = pk(A), pk(Bend)
EXI = [e for e in LE.EXITS if e[0] == "tp5_sl10_1.3s"][0]; LATS = (75, 110); SIZES = (0.35, 0.75); GUARD = 1.05
toks = {m for m, c in X.L.items() if c["run"] == RUN and T0 - 1800 <= c["bt"] <= T1}
byb = collections.defaultdict(set)
for m in toks: byb[(RUN, X.rp.bucket(m))].add(m)
X.byb = byb

def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]

def ours(tr, k, L, size):
    t = tr[k]; a0 = X.arr(t); fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]
    ke = k + 1
    while ke < len(tr) and X.arr(tr[ke]) < a0 + L: ke += 1
    if ke >= len(tr): return None
    if (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after > GUARD: return "b"
    X.B = size
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, int((a0 + L) // X.SMS))
    nm, tp, sl, cap, mh = EXI; n = len(K_); co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
    ti = np.flatnonzero(CHK & (VAL >= 1 + tp) & win); si = np.flatnonzero(CHK & (VAL <= 1 - sl) & win)
    a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
    s_out = co if (a is None and b is None) else (int(S_[a]) + 1 if (b is None or (a is not None and a <= b)) else int(S_[b]) + 1)
    return round(float(PNL[min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)]), 6)

def work(key):
    rows, _ = X.work(key)
    if not rows: return []
    tapes = X.rp.read_bucket(key[0], key[1], byb[key])
    rows.sort(key=lambda r: (r["m"], r["age"])); pm = None; past = []
    for r in rows:
        if r["m"] != pm: pm = r["m"]; past = []
        t0 = r["age"] * 1000.0; b = [x for x in past if x < t0]
        r["tgt_n"] = len(b); r["tgt_since"] = (t0 - max(b)) / 1000.0 if b else 1e9
        for w, d in r["lab"].items(): past.append(t0 + d)
    XX = np.array([[fv(r, k) for k in FE] for r in rows], float)
    env = np.ones(len(rows), bool)
    for k, op, v in M["envelope"]:
        j = FE.index(k); env &= (XX[:, j] >= v) if op == ">=" else (XX[:, j] <= v)
    Bm = np.zeros(XX.shape, np.int16)
    for j, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), XX[:, j], side="right") + 1; b[np.isnan(XX[:, j])] = 0; Bm[:, j] = b
    f = np.full(len(rows), M["F0"])
    for t in M["trees"]: f += M["lr"] * G.pred(t, Bm)
    out = []
    for i, r in enumerate(rows):
        if not env[i] or f[i] < TH["top8"]: continue          # strict / wider / top8 only (re-entry candidates included)
        tr = tapes.get(r["m"]); S0 = X.L[r["m"]]["slot"]
        if not tr: continue
        k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and round((t["s"] - S0) * X.SMS / 1000, 2) == r["age"]), None)
        if k is None: continue
        bt = tr[k].get("bt") or (X.L[r["m"]]["bt"] + r["age"])
        if not (T0 <= bt <= T1): continue
        out.append(dict(m=r["m"], t=bt, s=tr[k]["s"], age=r["age"], sell=r["sell"], drop=round((1 - r["drop"]) * 100, 1), vsol=round(tr[k]["vsol"] / 1e9, 2),
                        score=round(float(f[i]), 4), ours={f"{L}|{sz}": ours(tr, k, L, sz) for L in LATS for sz in SIZES}))
    return out

if __name__ == "__main__":
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    R.sort(key=lambda o: o["t"])
    json.dump(R, open(f"{D}/size_reentry_{os.environ.get('WIN', 'test')}.json", "w"))
    hrs = (T1 - T0) / 3600
    strict = [o for o in R if o["score"] >= TH["top2"]]
    print(f"window {os.environ.get('WIN', 'test')} ({A} -> {Bend} PKT, {hrs:.1f} h): scored dumps >= top8 {len(R)}, strict picks {len(strict)}")
    def tot(sel, key):
        v = [o["ours"][key] for o in sel if o["ours"][key] is not None]
        fills = [x for x in v if x != "b"]; return sum(fills) - FAIL * (len(v) - len(fills)), len(fills)
    FAIL = 0.0005
    print("\n1. SIZE: strict picks by post-dump curve vSOL (P&L SOL / fills; 0.35 vs 0.75 SOL)")
    for L in LATS:
        print(f"  at {L} ms:")
        for lo, hi in ((0, 32), (32, 40), (40, 50), (50, 70), (70, 999)):
            sel = [o for o in strict if lo <= o["vsol"] < hi]
            if not sel: continue
            a, na = tot(sel, f"{L}|0.35"); b, nb = tot(sel, f"{L}|0.75")
            print(f"    vSOL {lo:>2}-{hi:<3}: picks {len(sel):3d} | 0.35 SOL {a:+.3f} ({na} fills, {a / max(1, na) / 0.35 * 100:+.1f}%/fill) | 0.75 SOL {b:+.3f} ({nb} fills, {b / max(1, nb) / 0.75 * 100:+.1f}%/fill)")
        base, _ = tot(strict, f"{L}|0.35"); rule = sum(tot([o], f"{L}|{0.75 if o['vsol'] < 32 else 0.35}")[0] for o in strict)
        print(f"    TOTAL flat 0.35: {base:+.3f} | haqq-style 0.75 if vSOL < 32 else 0.35: {rule:+.3f}")
    for L in LATS:
        print(f"  by token age at {L} ms (0.35 / 0.75):", " | ".join(f"{lo}-{hi}s {tot([o for o in strict if lo <= o['age'] < hi], f'{L}|0.35')[0]:+.3f} / {tot([o for o in strict if lo <= o['age'] < hi], f'{L}|0.75')[0]:+.3f}"
              for lo, hi in ((0, 3), (3, 10), (10, 60), (60, 400))))
    print("\n2. RE-ENTRY (0.35 SOL): strict picks, first pick on a token vs later picks; after our previous pick on it won / lost")
    for L in LATS:
        key = f"{L}|0.35"; last = {}; cls = collections.defaultdict(list)
        for o in strict:
            prev = last.get(o["m"])
            c = "first pick on the token" if prev is None else ("re-entry after a WIN" if isinstance(prev, float) and prev > 0 else "re-entry after a loss / block")
            cls[c].append(o); last[o["m"]] = o["ours"][key]
        print(f"  at {L} ms: " + " | ".join(f"{c}: {len(v)} picks {tot(v, key)[0]:+.3f} ({tot(v, key)[1]} fills)" for c, v in cls.items()))
    print("\n   hot-token re-entry: after OUR winning strict pick on a token, also buy its next dumps (within 120 s) at a lower cut")
    for L in LATS:
        key = f"{L}|0.35"
        for cut_name, cut in (("wider", TH["top4"]), ("top8", TH["top8"])):
            won = {}; extra = []
            for o in R:
                if o["score"] >= TH["top2"]:
                    v = o["ours"][key]
                    if isinstance(v, float) and v > 0: won[o["m"]] = o["t"]
                    continue
                if o["score"] >= cut and o["m"] in won and 0 < o["t"] - won[o["m"]] <= 120: extra.append(o)
            a, na = tot(extra, key); print(f"  at {L} ms, next dumps >= {cut_name}: {len(extra)} extra picks, {a:+.3f} SOL ({na} fills)")
