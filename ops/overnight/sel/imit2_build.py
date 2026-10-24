#!/usr/bin/env python3
# IMIT2 dataset builder (local, read-only, 10-24): every dump INSIDE the IMIT1 envelope with IMIT1's 42 features (same code path
# as day24 / dayguard: selexit2.work + tgt_n / tgt_since, cohort sel/cohort_train.json), labels for (a) the 3 IMIT1 wallets and
# (b) the 10 top dip earners (ops/agents/topearners/work/top10.txt; same rule: first buy <= 1000 ms after the dump, before the
# next >= 1 SOL sell), the IMIT1 score, the dump slot's leader + near flag (Frankfurt list; leaders from dipshadow/leaders_book.json
# for epochs 1064-1065 and dip/speed/leaders/schedule_cur.json for 1066), and OUR replay at 35 / 50 ms: 0.55 SOL, entry price
# ratio vs the post-dump price (guard applied later), exits tpnone_sl10_1.3s and tp5_sl10_1.3s (replay tx costs only; the +0.0035
# per fill / 0.0005 per blocked buy are applied by imit2_eval.py).
# usage: WIN=r1|r2|r3|r7 python3 -I imit2_build.py -> sel/imit2_rows_<win>.jsonl.gz
#   r1 = R1 phaseA (all), r2 = R2 phaseA_sel (all; = the IMIT1 study data), r3 = R3 phaseA_r3day 10-23 19:26 -> 10-24 06:27 PKT,
#   r7 = R3 phaseA_r7 10-24 08:04 -> 16:05 PKT (data ends ~15:36)
import os, sys, json, time, calendar, collections, gzip
WIN = os.environ.get("WIN", "r7")
WINS = {"r1": ("R1", None, None, None), "r2": ("R2", "phaseA_sel", None, None),
        "r3": ("R3", "phaseA_r3day", "10-23 19:26", "10-24 06:27"), "r7": ("R3", "phaseA_r7", "10-24 08:04", "10-24 16:05"),
        # robustness extension from the complete R3 extract phaseA_r3 (data to ~16:32 PKT): the gap between the windows, run 7's
        # full hours (phaseA_r7 stops ~15:36), and the minutes after run 7
        "g": ("R3", "phaseA_r3", "10-24 06:27", "10-24 08:04"), "r7f": ("R3", "phaseA_r3", "10-24 08:04", "10-24 16:05"),
        "t2": ("R3", "phaseA_r3", "10-24 16:05", "10-24 16:27")}
RUN, PH, A, Bend = WINS[WIN]
os.environ["RP_PHASEA_R2"] = "phaseA_sel"                      # the IMIT1 study's R2 copy (sel3 built from it)
if RUN == "R3": os.environ["RP_PHASEA_R3"] = PH
for k, v in dict(SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50", DIP_HS="4", DIP_BUSY="0", DIP_HLAG="0",
                 DIP_MAX_AGE="1800", DIP_B="0.55", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json").items():
    os.environ[k] = v
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import numpy as np
import selexit2 as X
import gbdt_np as G
from multiprocessing import Pool
X.LATS = ()                    # features / labels only from selexit2.work (its per-row P&L grids are not needed: ours() below)
X.MAX_AGE = 344.0              # envelope age <= 343.67; rows are in age order per token, so earlier rows are unchanged
_rb = X.rp.read_bucket; _cache = {}
def _read_cached(run, b, mints):       # selexit2.work and this script read the same bucket: parse it once
    if (run, b) not in _cache: _cache.clear(); _cache[(run, b)] = _rb(run, b, mints)
    return _cache[(run, b)]
X.rp.read_bucket = _read_cached
M = json.load(open(f"{D}/IMIT1.json")); FE = M["features"]
pk = lambda s: calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
T0, T1 = (pk(A), pk(Bend)) if A else (-1e18, 1e18)
TOP10 = [l.strip() for l in open("/home/moiz/sniper/ops/agents/topearners/work/top10.txt") if l.strip()]
assert len(TOP10) == 10 and len({u[:8] for u in TOP10}) == 10
TOPS = set(TOP10); T3 = set(X.TARGETS)
NEAR = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
# slot -> leader: epochs 1064-1065 (leaders_book) + 1066 (schedule_cur)
_lb = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))["leaders"]
_sc = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json"))
LS0 = 459648000; IDS = sorted(set(_lb.values()) | set(_sc["ids"])); IX = {u: i for i, u in enumerate(IDS)}
LEAD = np.full(_sc["start"] + len(_sc["slot_leader"]) - LS0, -1, np.int32)
for s, u in _lb.items(): LEAD[int(s) - LS0] = IX[u]
LEAD[_sc["start"] - LS0:] = [IX[_sc["ids"][i]] for i in _sc["slot_leader"]]
del _lb
def leader(s):
    i = s - LS0
    return IDS[LEAD[i]] if 0 <= i < len(LEAD) and LEAD[i] >= 0 else None
if RUN == "R3": toks = {m for m, c in X.L.items() if c["run"] == RUN and T0 - 1800 <= c["bt"] <= T1}
else: toks = {m for m, c in X.L.items() if c["run"] == RUN}
byb = collections.defaultdict(set)
for m in toks: byb[(RUN, X.rp.bucket(m))].add(m)
X.byb = byb
EXS = (("tpnone_sl10_1.3s", 9.0, 0.10, 6, 1), ("tp5_sl10_1.3s", 0.05, 0.10, 6, 1)); LATS = (35, 50); SIZE = 0.55

def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]

def ours(tr, k, L, size):
    """our buy L ms after the dump at trade k: None = no trade after; else the entry price ratio vs the post-dump price
    (guard applied later) and the P&L of each exit from one replayed price path (same follower model as the study)"""
    t = tr[k]; a0 = X.arr(t); fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]
    ke = k + 1
    while ke < len(tr) and X.arr(tr[ke]) < a0 + L: ke += 1
    if ke >= len(tr): return None
    ratio = (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after
    X.B = size
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, int((a0 + L) // X.SMS))
    n = len(K_); out = {"ratio": round(ratio, 5)}
    for nm, tp, sl, cap, mh in EXS:
        co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
        ti = np.flatnonzero(CHK & (VAL >= 1 + tp) & win); si = np.flatnonzero(CHK & (VAL <= 1 - sl) & win)
        a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
        s_out = co if (a is None and b is None) else (int(S_[a]) + 1 if (b is None or (a is not None and a <= b)) else int(S_[b]) + 1)
        out[nm] = round(float(PNL[min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)]), 6)
    return out

def labels(tr, k, wallets):
    """same rule as selexit2.work's lab: first buy of each wallet <= 1000 ms after the dump, stop at the next >= 1 SOL sell"""
    a0 = X.arr(tr[k]); lab = {}
    for x in tr[k + 1:k + 600]:
        if X.arr(x) > a0 + 1000 or ((not x["buy"]) and x["sol"] >= X.MIN_SELL): break
        if x["buy"] and x["user"] in wallets and x["user"][:8] not in lab: lab[x["user"][:8]] = round(X.arr(x) - a0, 1)
    return lab

def work(key):
    rows, _ = X.work(key)
    if not rows: return [], 0, 0
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
    out = []; miss = 0
    for i, r in enumerate(rows):
        if not env[i]: continue
        tr = tapes.get(r["m"]); S0 = X.L[r["m"]]["slot"]
        if not tr: miss += 1; continue
        k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and t["vsol"] < 100e9
                  and round((t["s"] - S0) * X.SMS / 1000, 2) == r["age"] and round(t["sol"] / 1e9, 3) == r["sell"]), None)
        if k is None: miss += 1; continue
        bt = tr[k].get("bt") or (X.L[r["m"]]["bt"] + r["age"])
        if not (T0 <= bt <= T1): continue
        labT = labels(tr, k, TOPS)
        assert {w: d for w, d in labT.items() if w in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX")} == r["lab"], (r["m"], r["age"], labT, r["lab"])
        ld = leader(tr[k]["s"])
        out.append(dict(m=r["m"], run=r["run"], t=bt, s=tr[k]["s"], ms=round(X.arr(tr[k]), 1), age=r["age"], sell=r["sell"],
                        x=[None if np.isnan(v) else float(v) for v in XX[i]], lab3=r["lab"], labT=labT, f1=round(float(f[i]), 6),
                        lead=ld, near=(ld in NEAR) if ld else None, ours={str(L): ours(tr, k, L, SIZE) for L in LATS}))
    return out, len(rows), miss

if __name__ == "__main__":
    t_start = time.time(); R = []; nall = nmiss = 0; keys = sorted(byb)
    with Pool(int(os.environ.get("PROCS", "6"))) as p:
        for i, (o, n, ms) in enumerate(p.imap_unordered(work, keys, chunksize=1)):
            R += o; nall += n; nmiss += ms
            if (i + 1) % 32 == 0: print(f"  {i + 1}/{len(keys)} buckets, {len(R)} env rows, {time.time() - t_start:.0f} s", flush=True)
    R.sort(key=lambda o: (o["t"], o["ms"]))
    with gzip.open(f"{D}/imit2_rows_{WIN}.jsonl.gz", "wt") as fo:
        for o in R: fo.write(json.dumps(o) + "\n")
    print(f"WIN {WIN} ({RUN} {PH} {A} -> {Bend} PKT): tokens {len(toks)}, all dumps (age <= 344 s) {nall}, envelope rows {len(R)}, "
          f"k not found {nmiss}, near {sum(1 for o in R if o['near'])}, leader unknown {sum(1 for o in R if o['lead'] is None)}, "
          f"{time.time() - t_start:.0f} s")
