#!/usr/bin/env python3
"""CASEBOOK final: rule bot built from the surviving hypotheses, replayed on the tape.
 - prices: curve state after each row with 9pQQ's own holdings removed (vtok_ex = vtok + his holdings), plus our own impact.
 - entry: points table (log-lift per feature bin, learned on TRAIN = V3 eras of 10-30 + 10-31 on 9pQQ's flat-eligible events),
          threshold; hard rules: age>=8, vsol 30..95, not mayhem(not in tape), one position per token, >= 2 slots after our sell.
 - exit : first outside SELL with since_ob >= T (and >= 2 slots after buy), or an outside sell >= X SOL, or 600 s cap.
 - fills: "his speed" = state right after the trigger row; "+70ms (info)" = state after the last trade of the trigger's slot.
 - costs: buy 0.7 SOL incl. pump fees (0.6914 to curve), sell proceeds -1.25 % fees, 1.46 mSOL tx+tips per trip.
 - followers -20 %: outside BUY SOL after our entry scaled by 0.8 when pricing our exit (approx).
usage: c19_rulebot.py learn                      -> casebook/points.json
       c19_rulebot.py run RUN THR T X [fill]    -> prints P&L, precision/recall, lanes; fill in {his,late,f20}
       c19_rulebot.py hispicks RUN T X          -> his entries (his triggers) + our exit rule, and his own exits replayed"""
import sys, json, numpy as np, collections
D = "/home/it/sniper-data/rivals/9pQQ/casebook"; K = 30e9 * 1073e12
TRAIN = ["run_20261030_1355", "run_20261031_1350"]
def load(run):
    z = np.load(f"{D}/scale_{run}.npz"); a = np.load(f"{D}/scale_aug_{run}.npz")
    d = {k: z[k] for k in ["s", "i", "bt", "seg", "own", "holding", "age", "since_sell", "tb", "ts", "size", "utot", "ch10", "nf10", "n10", "nb10", "ntrips", "ps", "buy", "vsol", "mc", "mc_pre", "since_buy"]}
    d.update({k: a[k] for k in a.files}); d["psets"] = z["psets"]; d["run"] = run; return d
def bins(d):
    ps = d["psets"]
    cls = np.array([2 if "41Pr4XqE" in p else (3 if "L2TExMFK" in p else (1 if any(x in p for x in ("FLASHX8D", "6Vo3245e", "GMgnVFR8", "term9YPb", "JUP6Lkb")) else (0 if p == "" else 4))) for p in ps])[d["ps"]]
    ch = np.nan_to_num(d["ch10"]); ns10 = d["n10"] - d["nb10"]
    F = {
     "size": np.digitize(d["size"], [0.05, 0.1, 0.3, 0.6, 1, 2, 5]),
     "utot": np.digitize(d["utot"], [10, 100, 1000, 5000, 20000]),
     "ch10": np.digitize(ch, [-20, -10, -3, -0.5, 0.5, 3, 10, 20]),
     "side": d["buy"].astype(int),
     "prog": cls,
     "vsol": np.digitize(d["vsol"], [32, 35, 40, 50, 60, 70, 80, 95]),
     "ns10": np.minimum(ns10, 3),
     "nf10": np.digitize(d["nf10"], [-5, -2, -0.5, 0.5, 2, 5, 10]),
     "age": np.digitize(d["age"], [10, 20, 50, 150, 450, 1500, 5000, 20000]),
     "gap": np.digitize(d["gapo"], [0, 1, 3, 10, 75]),
    }
    return F
def eligible(d):
    tok = np.zeros(d["seg"].max() + 1, bool); tok[d["seg"][d["own"]]] = True
    return (~d["own"]) & (~d["holding"]) & (d["age"] >= 8) & ((d["since_sell"] < 0) | (d["since_sell"] >= 2))
def learn():
    tab = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    rt = collections.defaultdict(lambda: [0, 0])
    for run in TRAIN:
        d = load(run); F = bins(d); E = eligible(d) & (d["era"] == 3); t = d["tb"]
        for k, v in F.items():
            for b in np.unique(v[E]):
                m = E & (v == b); tab[k][int(b)][0] += int(m.sum()); tab[k][int(b)][1] += int((m & t).sum())
        # re-entry state (his) -> used with OUR state in the replay
        nt = np.minimum(d["ntrips"], 1); ss = np.digitize(np.where(d["since_sell"] < 0, 10**9, d["since_sell"]), [5, 25, 100, 400, 1500])
        for b in np.unique(nt[E]): m = E & (nt == b); tab["re"][int(b)][0] += int(m.sum()); tab["re"][int(b)][1] += int((m & t).sum())
        for b in np.unique(ss[E]): m = E & (ss == b); tab["ss"][int(b)][0] += int(m.sum()); tab["ss"][int(b)][1] += int((m & t).sum())
    out = {}
    for k, bb in tab.items():
        n = sum(v[0] for v in bb.values()); p = sum(v[1] for v in bb.values()) / n
        out[k] = {str(b): round(float(np.log(((v[1] + 1) / (v[0] + 1 / p)) / p)), 3) for b, v in bb.items()}
    json.dump(out, open(f"{D}/points.json", "w"), indent=1); print(json.dumps(out))
def score_static(d, P):
    F = bins(d); sc = np.zeros(len(d["s"]))
    for k, v in F.items():
        lut = P[k]; sc += np.array([lut.get(str(int(b)), 0.0) for b in range(v.max() + 1)])[v]
    return sc
def his_holdings(d, run=None):
    """vtok per row and his cumulative holdings H per row, from his own tx token deltas (own_<run>.jsonl)."""
    vtok = K / (d["vsol"].astype(np.float64) * 1e9)
    seg = d["seg"]; own = d["own"]; s = d["s"]; ii = d["i"]
    z = np.load(f"{D}/scale_{run}.npz"); mints = z["mints"]; m = z["m"]
    dt = {}
    for l in open(f"{D}/own_{run}.jsonl"):
        r = json.loads(l)
        if not r["err"] and r["kind"] in ("buy", "sell"): dt[(r["mint"], r["s"], r["i"])] = r["dtok"]
    delta = np.zeros(len(vtok))
    for k in np.where(own)[0]:
        delta[k] = dt.get((str(mints[m[k]]), int(s[k]), int(ii[k])), 0)
    first = np.r_[True, seg[1:] != seg[:-1]]; starts = np.where(first)[0]
    Hc = np.cumsum(delta); base = np.repeat(np.r_[0, Hc][starts], np.diff(np.r_[starts, len(Hc)]))
    H = Hc - base
    vpre = np.sqrt(K * 1e6 / d["mc_pre"].astype(np.float64))
    return vtok, H, vpre, H - delta
def sell_out(vt, tokens):
    vs0 = K / vt; vs1 = K / (vt + tokens); return (vs0 - vs1) * (1 - 0.0125)
def buy_tokens(vt):
    vs0 = K / vt; vs1 = vs0 + 0.6914e9; return vt - K / vs1
COST = 0.7e9 + 1.46e6
EXIT_RW = 1e9; EXIT_DD = 0.0
def simulate(d, sc, thr, T, X, fill="his", entry_mask=None, his_exit=False):
    vtok, H, vpre, Hpre = his_holdings(d, d['run']); vex = vtok + H; vexpre = vpre + Hpre
    s = d["s"]; seg = d["seg"]; own = d["own"]; buy = d["buy"]; size = d["size"]; bt = d["bt"]; sob = d["since_ob"]; age = d["age"]; vsol = d["vsol"]
    N = len(s)
    # last row index of each (seg, slot) for the 'late' fill
    endslot = np.r_[np.where((seg[1:] != seg[:-1]) | (s[1:] != s[:-1]))[0], N - 1]
    last_in_slot = np.repeat(endslot, np.diff(np.r_[-1, endslot]))
    ii = d["i"]; key3 = (seg.astype(np.int64) << 42) | (s.astype(np.int64) << 13) | np.minimum(ii, 8191)
    def fidx(k, lag):
        """curve state (vtok, his holdings removed) at (slot s_k, position i_k + lag) = pre-state of the next recorded row; 'his speed' lag=50, '+70ms' lag=150"""
        q = (np.int64(seg[k]) << 42) | (np.int64(s[k]) << 13) | min(int(ii[k]) + lag, 8191)
        j = int(np.searchsorted(key3, q, "right"))
        if j < N and seg[j] == seg[k]: return vexpre[j]
        return vex[j - 1]
    own_next = np.full(N, -1); nxt = -1
    for q in range(N - 1, -1, -1):
        if q + 1 < N and seg[q + 1] != seg[q]: nxt = -1
        own_next[q] = nxt
        if own[q]: nxt = q
    def pick(k):
        v = _pick(k); ref = vex[k]
        return v if 0.7 * ref <= v <= 1.43 * ref else ref  # guard against broken pre-states (non-curve account picked as curve)
    def _pick(k):
        if fill == "exact":  # state right before his own next tx on this token (his real fill), else his-speed model
            o = own_next[k]
            return vexpre[o] if o >= 0 and s[o] - s[k] <= 1 else fidx(k, 50)
        if fill == "late": return fidx(k, 150)
        return fidx(k, 50)
    P = json.load(open(f"{D}/points.json"))
    re_pts = {int(k): v for k, v in P["re"].items()}; ss_pts = {int(k): v for k, v in P["ss"].items()}
    trips = []; held = None; ntr = collections.Counter(); lastsell = {}
    our_buys = np.zeros(N, bool)
    for k in range(N):
        if own[k]: continue
        g = seg[k]
        if held is not None and held["g"] != g:  # token's tape ended while holding: exit at the last state of that token
            vt = vex[k - 1] - held["tok"]; out = sell_out(vt, held["tok"])
            trips.append(dict(net=out - COST, g=held["g"], hold=-1, cap=True, first=held["first"], age=held["age"], sc=held["sc"]))
            held = None
        if held is None:
            if age[k] < 8 or not (30 <= vsol[k] < 95): continue
            ls = lastsell.get(g)
            if ls is not None and s[k] - ls < 2: continue
            if entry_mask is not None:
                if not entry_mask[k]: continue
            else:
                ssb = 5 if ls is None else int(np.digitize(s[k] - ls, [5, 25, 100, 400, 1500]))
                tot = sc[k] + re_pts.get(min(ntr[g], 1), 0) + ss_pts.get(ssb, 0)
                if tot < thr: continue
            vt = pick(k); tk = buy_tokens(vt)
            held = dict(g=g, k=k, s=s[k], bt=bt[k], tok=tk, fb=0.0, age=age[k], first=ntr[g] == 0, sc=sc[k])
            our_buys[k] = True
            continue
        # holding
        if s[k] - held["s"] < 2:
            continue
        if fill == "f20" and buy[k] and s[k] - held["s"] <= 3: held["fb"] += size[k] * 1e9  # followers = outside buys within 3 slots of our entry
        cap = bt[k] - held["bt"] >= 600
        if vsol[k] < 112: held["lastgood"] = vex[k]
        if vsol[k] >= 112:  # curve completing / migrated (states unreliable): exit at the last sane state, flagged
            vt = held.get("lastgood", vex[held["k"]]) - held["tok"]; out = sell_out(vt, held["tok"])
            trips.append(dict(net=out - COST, g=g, hold=s[k] - held["s"], cap=False, grad=True, first=held["first"], age=held["age"], sc=held["sc"]))
            ntr[g] += 1; lastsell[g] = s[k]; held = None; continue
        # current value of our bag (state after row k, our tokens out of the curve)
        vt_now = vex[k] - held["tok"]; val = sell_out(vt_now, held["tok"]) if vt_now > 0 else 0
        held["pk"] = max(held.get("pk", 0), val); retv = val / 0.6914e9 - 1; ddv = val / held["pk"] - 1 if held["pk"] > 0 else 0
        if his_exit: trig = bool(d["ts"][k])
        else:
            trig = (not buy[k]) and (sob[k] >= T or size[k] >= X) and retv < EXIT_RW
            trig = trig or (EXIT_DD > 0 and retv >= EXIT_RW and ddv <= -EXIT_DD and not buy[k])
        if trig or cap:
            vt = pick(k) - held["tok"]  # our tokens are out of the curve while we hold
            if fill == "f20":  # remove 20 % of outside buy flow that came in during the hold
                vs = K / vt; vs -= 0.2 * held["fb"]; vt = K / max(vs, 1e9)
            out = sell_out(vt, held["tok"])
            trips.append(dict(net=out - COST, g=g, hold=s[k] - held["s"], cap=cap and not trig, first=held["first"], age=held["age"], sc=held["sc"]))
            ntr[g] += 1; lastsell[g] = s[k]; held = None
    return trips, our_buys
def lane(t):
    if t["first"] and t["age"] <= 60: return "LAUNCH"
    return "RE/OTHER"
def report(trips, label):
    n = len(trips); net = sum(t["net"] for t in trips) / 1e9
    if not n: print(label, "no trips"); return
    nets = sorted(t["net"] for t in trips)
    top5 = sum(nets[-5:]) / 1e9
    ng = sum(1 for t in trips if t.get("grad")); gn = sum(t["net"] for t in trips if t.get("grad")) / 1e9
    print(f"{label}: grad-exits {ng} ({gn:+.2f} SOL); trips {n} net {net:+.2f} SOL ({1e3*net/n:+.1f} mSOL/trip) win {np.mean([t['net']>0 for t in trips]):.2f} cap {sum(t['cap'] for t in trips)} w/o top5 {net-top5:+.2f}")
    by = collections.defaultdict(list)
    for t in trips: by[lane(t)].append(t["net"])
    print("      lanes: " + "; ".join(f"{k} n{len(v)} {sum(v)/1e9:+.2f}" for k, v in sorted(by.items())))
if __name__ == "__main__":
    if sys.argv[1] == "learn": learn(); sys.exit()
    P = json.load(open(f"{D}/points.json"))
    run = sys.argv[2]; d = load(run); sc = score_static(d, P)
    if sys.argv[1] == "run":
        thr, T, X = float(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]); fill = sys.argv[6] if len(sys.argv) > 6 else "his"
        trips, ob = simulate(d, sc, thr, T, X, fill)
        report(trips, f"{run} RULEBOT thr {thr} T {T} X {X} fill {fill}")
        E = eligible(d); t = d["tb"]
        # static precision/recall on his flat-eligible events (his state), score incl. his re-entry state
        re = np.array([P["re"].get(str(min(x, 1)), 0) for x in range(2)])[np.minimum(d["ntrips"], 1)]
        ssb = np.digitize(np.where(d["since_sell"] < 0, 10**9, d["since_sell"]), [5, 25, 100, 400, 1500])
        ssp = np.array([P["ss"].get(str(b), 0) for b in range(6)])[ssb]
        tot = sc + re + ssp; m = E & (tot >= thr) & (d["vsol"] >= 30) & (d["vsol"] < 95)
        print(f"   static on his eligible events: flagged {m.sum()} precision {100*t[m].mean():.1f}% recall {100*t[m].sum()/t[E].sum():.1f}% (base {100*t[E].mean():.2f}%)")
        hit = ob & t; print(f"   free-run overlap: our buys {ob.sum()}, on one of his trigger rows {hit.sum()} ({100*hit.sum()/max(1,ob.sum()):.1f}%), his buys covered {100*hit.sum()/t.sum():.1f}%")
    if sys.argv[1] == "hispicks":
        T, X = int(sys.argv[3]), float(sys.argv[4])
        for fill in ("his", "f20", "late"):
            tr, _ = simulate(d, sc, 0, T, X, fill, entry_mask=d["tb"]); report(tr, f"{run} HIS PICKS + exit(T{T},X{X}) fill {fill}")
        for fill in ("exact", "his", "f20", "late"):
            tr, _ = simulate(d, sc, 0, T, X, fill, entry_mask=d["tb"], his_exit=True); report(tr, f"{run} HIS PICKS + HIS EXIT TRIGGERS fill {fill}")
