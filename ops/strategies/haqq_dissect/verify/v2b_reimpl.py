#!/usr/bin/env python3
"""VERIFY v2b: INDEPENDENT re-implementation of G2's holder-gated re-arm any:20:30:8:2 (own code, own landing model; INFERRED).
Rule (from rearm/REPORT.md): after a whale dump (one sell >= 6% of supply) on a token <= 30 s old (age = slots x 0.212 s), with a
>= 6% holder at the end of slot dump+2, arm at dump+3 (+50 ms) for 20 slots (tries land in slots <= dump+23), k 8; stop at the next
whale dump or when no wallet holds >= 6% (stop 50 ms after the chain time = feed + 30 ms); QUIET stop (< 2 trades by anyone from
arm to slot dump+9); limit 0.88 x the latest price the try saw; one position; post-dump curve < 100 SOL; v2, not cashback, not
mayhem, standard curve.
Landing model (own, MEASURED inputs): our LIVE pre-send try streams (landed tries of AMS r24-r33 + FRA r26: landing chain clock
and ms_send_to_first_rx = send -> first seen on the feed). A re window gets a live stream laid on it with the same slot phase
(another stream appended when one ends). A try landing at L saw the chain up to L - s2rx (the engine's view at send), so its limit
= 0.88 x price at L - s2rx; it fills if the recorded spot just before L <= limit (this rule reproduces 740/740 live fills and all
73k live 6042s, v2a). Every landed non-fill try pays 5,120 lamports. Tries pause while any position is open.
Exits (own exact replay): our 0.40 SOL buy into the curve at the fill state; later trades re-applied (buys by SOL, sells by
tokens; a follower whose slippage our buy breaks is dropped: measured slack table a8_slack.json); live exit = TP 10% / SL 20% on
any trade before (S_in+2) + 40 ms (sell lands +59 ms after that trade), else time exit landing at (S_in+2) + 100 ms; WAVE =
from fill+150 ms, first 150 ms with no outside buy (1 s cap), lands +59 ms. Cost per fill 2.015 mSOL (as G2: buy fee, 0.2 tip,
sell 0.605 + 1.2 tips, ATA).
NOT ADDED: a re fill inside an armed T2 window of the same token (own simple T2 detector: a wallet's first buy to >= 6%, not the
creator/create-slot buyer, 10 slots or until its first sell) - today's pre-send would already try there.
Not modelled: rate caps (G2: 4-5% of tries), the knock-on on T2 windows via one position (G2: -0.2..+0.15 SOL/day).
usage: v2b_reimpl.py TAB TAG --days 2,3,4,5 | --fresh  [--seeds 3]"""
import sys, os, json, pickle, collections, argparse, time, bisect, hashlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V

DATA = "/home/moiz/sniper-data/haqq_dissect/verify"
SMS = V.SMS
WH = V.WHALE; HX = 30_000_000_000_000
SIZE = 400_000_000
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020
FAIL = 5120
DAY0 = 1793038500 - 5 * 86400
FRESH0 = 1793131823
SLACK = np.array(sorted(r[1] for r in json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"]), float)
LIVE_RUNS = ["/home/moiz/sniper-data/runs/ams/runs/dip_ams_r24.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r25.jsonl",
             "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.jsonl",
             "/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"] + \
            [f"/home/moiz/sniper-data/haqq_strat/live/dip_ams_r{k}.jsonl" for k in range(29, 34)] + ["/home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl"]


def slack(sigh):
    u = (int(sigh) & ((1 << 64) - 1)) / 18446744073709551616.0
    return min(float(SLACK[min(len(SLACK) - 1, int(u * len(SLACK)))]), 1e6)


def u01(*a):
    return int.from_bytes(hashlib.blake2b(":".join(map(str, a)).encode(), digest_size=8).digest(), "little") / 2 ** 64


# ------------------------------------------------------------------------------------------------ donor streams (MEASURED)
def donor_streams(dv8tab, runs=None, tag=""):
    fn = f"{DATA}/v2b_donors{tag}.pkl"
    if os.path.exists(fn): return pickle.load(open(fn, "rb"))
    R = V.load_runs(runs or LIVE_RUNS)
    tries = [r for r in R if r.get("ev") == "presend_attempt_land" and r.get("res") in ("ok", "6042") and r.get("slot") and r.get("idx") is not None]
    tp = V.Tape(dv8tab, mints=set(), load_ids=True)
    g = collections.defaultdict(list)
    for r in tries:
        s2 = r.get("ms_send_to_first_rx") or r.get("ms_send_to_rx")
        if s2 is None: continue
        g[(r["_run"], r["mint"])].append((tp.cc(int(r["slot"]), int(r["idx"])), float(s2)))
    out = []
    for k, v in g.items():
        v.sort()
        cur = [v[0]]
        for x in v[1:]:
            if x[0] - cur[-1][0] > 600: out.append(cur); cur = [x]
            else: cur.append(x)
        out.append(cur)
    out = [np.array(w) for w in out if len(w) >= 12]
    pickle.dump(out, open(fn, "wb"))
    return out


class Lander:
    def __init__(self, streams):
        self.S = [s for s in streams if s[-1, 0] - s[0, 0] >= 2 * SMS]
        self.rate = sum(len(s) for s in self.S) / sum(s[-1, 0] - s[0, 0] for s in self.S)   # landed tries per ms while armed

    def stream(self, rng, t0, t1):
        """landed tries (L, s2rx) laid on [t0, t1] with t0's slot phase"""
        out = []; t = t0; ph = (t0 % SMS)
        while t < t1:
            s = self.S[int(rng.integers(len(self.S)))]
            lo = s[0, 0]; hi = s[-1, 0]
            # anchor x' = a slot start in the donor + phase, with >= 1 slot of stream after it
            k0 = int(np.ceil((lo - ph) / SMS)); k1 = int(np.floor((hi - SMS - ph) / SMS))
            if k1 < k0: continue
            xa = int(rng.integers(k0, k1 + 1)) * SMS + ph
            seg = s[s[:, 0] >= xa]
            L = t + (seg[:, 0] - xa)
            use = L < t1
            for a, b in zip(L[use], seg[use, 1]): out.append((float(a), float(b)))
            t = t + (seg[-1, 0] - xa) + 1.0
            t = t0 + SMS * np.ceil((t - t0) / SMS)        # keep the phase
        return out


# ------------------------------------------------------------------------------------------------ events
KEEP_REG = None   # set of presend sighs: when given, only these of our txs are removed (G2's choice); our regular buys/sells stay


def build(tp, creates, ok_bt):
    """re windows + T2 windows per mint"""
    T = tp.T
    big = np.flatnonzero((T["tok"] >= WH) & (T["buy"] == 0))
    mids = np.unique(T["mint"][big])
    REW = []; T2 = collections.defaultdict(list); MR = {}
    for mid in mids.tolist():
        mint = tp.ids[mid]; c = creates.get(mint)
        if c is None or c.get("mayhem") or c.get("mayhem_ix") or not c.get("v2") or c.get("cashback"): continue
        a, e = tp.span[mid]; X = T[a:e]
        ours = np.isin(X["signer"], list(tp.our)) | np.isin(X["user"], list(tp.our))
        if KEEP_REG is not None: ours = np.isin(X["sigh"], KEEP_REG)
        X = X[~ours]
        if not len(X): continue
        s0 = int(c["slot"])
        X = X[(X["slot"].astype(np.int64) > s0) | ((X["slot"].astype(np.int64) == s0) & (X["idx"].astype(np.int64) >= int(c["idx"])))]
        if not len(X): continue
        v50 = X["vsol"][:50]; t50 = X["vtok"][:50]
        if ((v50 < 25e9) | (v50 > 200e9) | (t50 == 0)).any(): continue
        n = len(X); sl = X["slot"].astype(np.int64); ix = X["idx"].astype(np.int64)
        cc = np.array([tp.cc(int(s), int(i)) for s, i in zip(sl, ix)])
        bal = collections.defaultdict(int); nb = 0; nbig = np.zeros(n, np.int32)
        creator = c.get("creator"); cid = tp.idm.get(creator); sid = tp.idm.get(c.get("user"))
        insiders = set(); became = set()
        for q in range(n):
            u = int(X["user"][q]); b = bool(X["buy"][q]); b0 = bal[u]
            bal[u] = b0 + (int(X["tok"][q]) if b else -int(X["tok"][q]))
            nb += int(bal[u] >= WH) - int(b0 >= WH); nbig[q] = nb
            if b and sl[q] == s0 and u != cid and u != sid: insiders.add(u)
            if b and X["vsol"][q] < 100e9 and u not in became:
                ht = 1 if u == cid else 2 if u in insiders else 3 if bal[u] >= HX else 0
                if ht: became.add(u)
                if ht == 3 and bal[u] >= WH and sl[q] > s0:
                    # T2 window: [cc + 50, end of slot + 10], until 50 ms after the whale's first sell
                    fs = next((z for z in range(q + 1, n) if int(X["user"][z]) == u and not X["buy"][z]), None)
                    t_end = (sl[q] + 11) * SMS
                    if fs is not None: t_end = min(t_end, cc[fs] + 50.0)
                    T2[mint].append((cc[q] + 50.0, t_end))
        dumps = [q for q in range(n) if (not X["buy"][q]) and X["tok"][q] >= WH]
        for zi, q in enumerate(dumps):
            s = int(sl[q])
            if (s - s0) * 0.212 > 30.0: continue
            if X["vsol"][q] >= 100e9: continue
            bt = tp.bt_of(s)
            if not ok_bt(bt): continue
            r_end = int(np.searchsorted(sl, s + 2, side="right")) - 1
            if nbig[r_end] < 1: continue
            t_arm = (s + 3) * SMS + 50.0
            t_last = (s + 24) * SMS            # tries land in slots <= dump + 23
            stops = [t_last]
            if zi + 1 < len(dumps): stops.append(cc[dumps[zi + 1]] + 50.0)
            z0 = np.flatnonzero(nbig[r_end + 1:] == 0)
            if len(z0): stops.append(cc[r_end + 1 + z0[0]] + 50.0)
            # QUIET: < 2 trades from slot dump+3 to slot dump+9 -> disarm at slot dump+9 + 30 ms
            # (v2: the engine's slot reaches dump+9 ~50 ms into that slot: trades seen by then count, as rsim's E with its 30 ms lag)
            nq = int(((sl >= s + 3) & (cc < (s + 9) * SMS + 50.0)).sum())
            if nq < 2: stops.append((s + 9) * SMS + 50.0)
            REW.append(dict(mint=mint, mid=mid, s=s, q=q, t_arm=t_arm, t_stop=min(stops), bt=bt, why=int(np.argmin(stops))))
        MR[mint] = (X, cc)
    REW.sort(key=lambda w: w["t_arm"])
    return REW, T2, MR


# ------------------------------------------------------------------------------------------------ exits
def exits(X, cc, kb, L, s_in, cut_seed=None):
    """our 0.40 SOL buy at state kb (last trade before our landing L); returns dict exit -> gross lamports (after pump fees)"""
    v = int(X["vsol"][kb]); t = int(X["vtok"][kb]); fr = V.fee_of(X[kb])
    x = int(SIZE / (1.0 + fr)); qtok = (t * x) // (v + x); v += x; t -= qtok
    res = {}
    for name, cut in (("live", 0.0), ("live10", 0.1), ("live20", 0.2), ("wave", 0.0), ("wave10", 0.1)):
        vv, tt = v, t; frs = fr
        t_dec = (s_in + 2) * SMS + 40.0; t_sell = (s_in + 2) * SMS + 100.0
        wave = name.startswith("wave"); last_buy = L; t_w = None
        if wave: t_sell = L + 1000.0 + 59.0
        k = kb + 1
        while k < len(X) and cc[k] < t_sell:
            if cc[k] <= L: k += 1; continue
            if wave and t_w is None:
                g0 = min(max(L + 150.0, last_buy + 150.0), L + 1000.0)
                if cc[k] > g0:
                    t_w = g0; t_sell = g0 + 59.0
                    if cc[k] >= t_sell: break
            if X["buy"][k]:
                sol = int(X["sol"][k]); dtk = (tt * sol) // (vv + sol)
                if dtk < int(X["tok"][k]) / (1.0 + slack(X["sigh"][k])): k += 1; continue
                if cut > 0 and u01(int(X["sigh"][k]), name) < cut: k += 1; continue
                vv += sol; tt -= dtk
                if wave: last_buy = cc[k]
            else:
                tk = int(X["tok"][k]); so = (vv * tk) // (tt + tk); vv -= so; tt += tk
            frs = V.fee_of(X[k])
            if not wave and cc[k] < t_dec and t_sell > cc[k] + 59.0:
                val = (vv * qtok) // (tt + qtok) * (1.0 - frs) / SIZE
                if val >= 1.10 or val <= 0.80: t_sell = cc[k] + 59.0; t_dec = -1
            k += 1
        out = (vv * qtok) // (tt + qtok)
        res[name] = int(out * (1.0 - frs)) - SIZE
    return res


def simulate(REW, T2, MR, lander, seed):
    rng = np.random.default_rng(seed)
    busy = -1.0; rows = []
    for w in REW:
        X, cc = MR[w["mint"]]
        t0 = max(w["t_arm"], busy); t1 = w["t_stop"]
        r = dict(mint=w["mint"], s=w["s"], bt=w["bt"], fill=None, fees=0, landed=0, base_has=False)
        if t1 <= t0: rows.append(r); continue
        st = lander.stream(rng, t0, t1 + 120.0)
        t2w = T2.get(w["mint"], [])
        price = X["vsol"] / np.maximum(X["vtok"], 1)
        for L, s2 in st:
            if L - s2 + 15.0 >= t1: continue          # sent after the stop
            if L >= (w["s"] + 24) * SMS: continue       # past the window's last slot (deadline)
            r["landed"] += 1
            kb = int(np.searchsorted(cc, L, side="left")) - 1
            kv = int(np.searchsorted(cc, L - s2, side="right")) - 1
            if kb < 0 or kv < 0: r["fees"] += FAIL; continue
            lim = 0.88 * price[kv]
            if price[kb] <= lim and X["vsol"][kb] < 100e9:
                s_in = int(L // SMS)
                ex = exits(X, cc, kb, L, s_in)
                r["fill"] = dict(L=L, kb=kb, ex=ex, k_ahead=None)
                r["base_has"] = any(a <= L <= b for a, b in t2w)
                t_sell = max(L + 1059.0, (s_in + 2) * SMS + 100.0)
                busy = t_sell + 60.0
                break
            r["fees"] += FAIL
        rows.append(r)
    return rows


def summarize(rows, key_of, label):
    """per key: fills, added fills, P&L per exit (lamports, after COST), fees"""
    S = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        k = key_of(r); S[k]["win"] += 1; S[k]["fees"] += r["fees"]
        f = r["fill"]
        if f is None: continue
        S[k]["fills"] += 1
        if r["base_has"]: S[k]["base_has"] += 1; continue
        S[k]["added"] += 1
        for e, g in f["ex"].items(): S[k][e] += g - COST
        S[k]["wins"] += int(f["ex"]["live"] - COST > 0)
    return S


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("tab"); ap.add_argument("tag"); ap.add_argument("--days", default=""); ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--keep-regular", action="store_true"); ap.add_argument("--donors", default="ams"); ap.add_argument("--seeds", type=int, default=3); ap.add_argument("--cov", type=float, default=0.95)
    A = ap.parse_args()
    t0 = time.time()
    if A.donors == "fra":
        lander = Lander(donor_streams(f"{DATA}/tab", ["/home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl", f"{DATA}/live/dip_r27.jsonl"], "_fra"))
    else:
        lander = Lander(donor_streams("/home/moiz/sniper-data/dv8/tab"))
    print(f"donor streams {len(lander.S)}, landed tries/s while armed {1000 * lander.rate:.1f} ({time.time() - t0:.0f} s)", flush=True)
    if A.fresh:
        S = np.load(f"{A.tab}/slots.npy"); bt = S["bt"].astype(np.int64); sl = S["slot"].astype(np.int64)
        h = (bt + 18000) // 3600 * 3600 - 18000; good = set()
        for hh in np.unique(h):
            m = h == hh
            if m.sum() / (sl[m].max() - sl[m].min() + 1) >= A.cov: good.add(int(hh))
        BTE = int(bt.max()) - 90
        ok_bt = lambda b: FRESH0 < b < BTE and ((b + 18000) // 3600 * 3600 - 18000) in good
    else:
        days = [int(x) for x in A.days.split(",")]
        hj = json.load(open("/home/moiz/sniper-data/dv8/hours.json")); good = {r["h"] for r in hj["rows"] if r["usable"]}
        ok_bt = lambda b: int((b - DAY0) // 86400) in days and ((b + 18000) // 3600 * 3600 - 18000) in good
    # candidate mints: a >= 6% single sell anywhere
    T = np.load(f"{A.tab}/trades.npy", mmap_mode="r")
    big = np.flatnonzero((np.asarray(T["tok"]) >= WH) & (np.asarray(T["buy"]) == 0))
    if not A.fresh:
        btb = np.asarray(T["bt"])[big].astype(np.int64)
        dd = (btb - DAY0) // 86400
        big = big[np.isin(dd, days)]
    mids = np.unique(np.asarray(T["mint"])[big])
    ids = json.load(open(f"{A.tab}/ids.json"))
    mints = {ids[m] for m in mids.tolist()}
    print(f"candidate mints {len(mints):,} ({time.time() - t0:.0f} s)", flush=True)
    del T
    tp = V.Tape(A.tab, mints)
    print(f"tape rows {len(tp.T):,} ({time.time() - t0:.0f} s)", flush=True)
    C = json.load(open(f"{A.tab}/creates.json"))
    creates = {m: C[m] for m in mints if m in C}; del C
    if A.keep_regular:
        import v1_rsim_fwd as V1
        KEEP_REG = np.fromiter(V1.our_sighs(), dtype=np.uint64)
    REW, T2, MR = build(tp, creates, ok_bt)
    print(f"re windows {len(REW):,}; stop reasons {collections.Counter(w['why'] for w in REW)} ({time.time() - t0:.0f} s)", flush=True)
    allrows = []
    for sd in range(A.seeds):
        rows = simulate(REW, T2, MR, lander, 777 + sd)
        for r in rows: r["seed"] = sd
        allrows += rows
        print(f"seed {sd}: fills {sum(r['fill'] is not None for r in rows)}, base-overlap {sum(r['base_has'] for r in rows)} ({time.time() - t0:.0f} s)", flush=True)
    pickle.dump(dict(rows=allrows, seeds=A.seeds, n_re=len(REW)), open(f"{DATA}/v2b_{A.tag}.pkl", "wb"))
    print("done", flush=True)
