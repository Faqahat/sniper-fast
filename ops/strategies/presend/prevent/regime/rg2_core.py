"""REGIME step 2: clustering tests, cooldown rules, regime signals and lock variants on the 20 live runs' real trade sequences
(+ PAPER on 9 shadow-only runs). Read-only. Writes /home/moiz/sniper-data/prevent/regime/core.pkl (all per-rule per-run numbers).
usage: rg2_core.py"""
import sys, collections, bisect, random, pickle, math, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/regime")
import rg_lib as G

KNOW = 2.0          # a trade's outcome is known 2 s after its sell lands
BIGF = -0.072       # big loss: pnl / spend < -7.2%
OUT = "/home/moiz/sniper-data/prevent/regime"
rng = random.Random(7)


# ---------------------------------------------------------------- data
def build_live():
    runs = {}
    for n in G.LIVE_ORDER:
        R = G.live_run(n)
        tw = {x["w"]: x for x in R["trades"]}
        wins = []
        seen = set()
        for w in R["wins"]:
            tr = tw.get(w["w"])
            if tr is not None:
                seen.add(w["w"])
            wins.append(dict(t=w["t"], fee=w["fee"], tr=tr, kind=w["kind"]))
        for w, tr in tw.items():          # a trade without an arm record: its own window 1 s before the fill
            if w not in seen:
                wins.append(dict(t=tr["t"] - 1.0, fee=tr["wfee"], tr=tr, kind=tr["kind"]))
        wins.sort(key=lambda z: z["t"])
        for tr in R["trades"]:
            tr["big"] = tr["pnl"] / tr["spend"] < BIGF
            tr["sl"] = tr["why"] == "stop-loss"
            tr["loss"] = tr["pnl"] < 0
            tr["v"] = tr["s"] + tr["rent"]          # scaled trade value incl. rent (window fees added separately)
            tr["vr"] = tr["pnl"] + tr["rent"]       # real
            tr["known"] = tr["st"] + KNOW
        runs[n] = dict(name=n, wins=wins, trades=R["trades"], t0=R["t0"], t1=R["t1"], o=R["o"], cfg=R["cfg"])
    return runs


def build_paper():
    runs = {}
    for n in G.SHADOW_ORDER:
        o = G.load(n)
        seq = G.shadow_seq(o, "c", 2)
        size = (o["cfg"] or {}).get("presend_sz") or 0.55
        trades, wins = [], []
        for x in seq:
            spend = size
            tr = dict(run=n, t=x["t"] - 0.6, st=x["t"], pnl=x["pnl"], rent=0.0, spend=spend, why={"sl": "stop-loss"}.get(x["why"], x["why"]),
                      s=G.scale(x["pnl"], spend), kind="t2", mint=x["mint"])
            tr["big"] = tr["pnl"] / spend < BIGF; tr["sl"] = x["why"] == "sl"; tr["loss"] = tr["pnl"] < 0
            tr["v"] = tr["s"]; tr["vr"] = tr["pnl"]; tr["known"] = tr["st"] + KNOW
            trades.append(tr)
            wins.append(dict(t=tr["t"] - 1.0, fee=0.0, tr=tr, kind="t2"))
        if trades:
            runs[n] = dict(name=n, wins=wins, trades=trades, t0=trades[0]["t"] - 60, t1=trades[-1]["st"], o=o, cfg=o["cfg"], size=size)
    return runs


# ---------------------------------------------------------------- generic replay
class Rule:
    """on_close(trade, t_known, state) -> pause end time or None; on_fee(t, fee) for rolling P&L"""
    def __init__(self, name, fam, fn, K, roll=None):
        self.name, self.fam, self.fn, self.K, self.roll = name, fam, fn, K * 60.0, roll


def replay(run, rule, sig_skip=None, real=False):
    """returns kept value, skipped list of (value, trade or None), per-window decisions. value = scaled (or real) trade value - fee."""
    wins = run["wins"]
    pause_until = -1.0
    pend = []                      # kept trades not yet known: (known, idx, trade)
    hist = collections.deque()     # rolling (t, value) of kept things for rolling rules
    st = dict(streak=0, bigs=collections.deque(), hist=hist)
    kept_v, skipped = 0.0, []
    pauses = []
    import heapq
    for i, w in enumerate(wins):
        ta = w["t"]
        while pend and pend[0][0] <= ta:
            kn, _, tr = heapq.heappop(pend)
            if rule is not None:
                pe = rule.fn(tr, kn, st, run)
                if pe is not None:
                    pauses.append((kn, pe))
                    pause_until = max(pause_until, pe)
        skip = (rule is not None and ta < pause_until) or (sig_skip is not None and sig_skip(run, w))
        tr = w["tr"]
        val = -w["fee"] + ((tr["vr"] if real else tr["v"]) if tr else 0.0)
        if skip:
            skipped.append((val, tr, w))
            continue
        kept_v += val
        hist.append((ta, -w["fee"]))
        if tr:
            heapq.heappush(pend, (tr["known"], i, tr))
    run["_pauses"] = pauses
    return kept_v, skipped


def union_len(iv, lo, hi):
    tot = 0.0; cur_s = cur_e = None
    for a, b in sorted(iv):
        a = max(a, lo); b = min(b, hi)
        if b <= a: continue
        if cur_e is None or a > cur_e:
            if cur_e is not None: tot += cur_e - cur_s
            cur_s, cur_e = a, b
        else:
            cur_e = max(cur_e, b)
    if cur_e is not None: tot += cur_e - cur_s
    return tot


def mk_rules():
    rules = []
    def c1(K):
        def f(tr, kn, st, run):
            return kn + K * 60 if tr["big"] else None
        return f
    def c2(K):
        def f(tr, kn, st, run):
            return kn + K * 60 if tr["sl"] else None
        return f
    def c3(B, M, K):
        def f(tr, kn, st, run):
            if not tr["big"]:
                return None
            q = st["bigs"]; q.append(kn)
            while q and q[0] < kn - M * 60: q.popleft()
            if len(q) >= B:
                q.clear(); return kn + K * 60
            return None
        return f
    def c4(N, K):
        def f(tr, kn, st, run):
            if tr["loss"]:
                st["streak"] += 1
                if st["streak"] >= N:
                    st["streak"] = 0; return kn + K * 60
            else:
                st["streak"] = 0
            return None
        return f
    def c5(Wmin, X, K):
        def f(tr, kn, st, run):
            h = st["hist"]; h.append((kn, tr["v"]))
            lo = kn - Wmin * 60
            s = sum(v for t, v in h if t >= lo)
            while h and h[0][0] < lo - 3600: h.popleft()
            if s < -X:
                return kn + K * 60
            return None
        return f
    for K in (5, 10, 15, 30, 60):
        rules.append(Rule(f"C1 big loss -> pause {K}m", "C1", c1(K), K))
    for K in (5, 10, 15, 30, 60):
        rules.append(Rule(f"C2 SL exit -> pause {K}m", "C2", c2(K), K))
    for B, M in ((2, 10), (2, 15), (2, 30), (3, 30)):
        for K in (10, 15, 30, 60):
            rules.append(Rule(f"C3 {B} big in {M}m -> pause {K}m", "C3", c3(B, M, K), K))
    for N in (3, 4, 5, 6):
        for K in (10, 15, 30):
            rules.append(Rule(f"C4 {N} losses in a row -> pause {K}m", "C4", c4(N, K), K))
    for X in (0.15, 0.25, 0.35, 0.50):
        for K in (15, 30, 60):
            rules.append(Rule(f"C5 15m P&L < -{X} -> pause {K}m", "C5", c5(15, X, K), K))
    for X in (0.15, 0.25, 0.35):
        for K in (10, 15, 30):
            rules.append(Rule(f"C6 10m P&L < -{X} -> pause {K}m", "C6", c5(10, X, K), K))
    return rules


# ---------------------------------------------------------------- scoring helpers
def score(runs, rule=None, sig_skip=None, real=False):
    """per run: base, kept, saving, skipped stats, block savings by hour"""
    res = {}
    for n, run in runs.items():
        base = sum(-w["fee"] + ((w["tr"]["vr"] if real else w["tr"]["v"]) if w["tr"] else 0.0) for w in run["wins"])
        kept, sk = replay(run, rule, sig_skip, real)
        pz = union_len(run.get("_pauses", []), run["t0"], run["t1"]) if rule is not None else 0.0
        sk_tr = [(v, tr) for v, tr, w in sk]
        win_sol = sum(v for v, tr in sk_tr if v > 0)
        los_sol = -sum(v for v, tr in sk_tr if v < 0)
        vals = sorted(v for v, tr in sk_tr if tr is not None)
        blocks = collections.defaultdict(float)
        for v, tr, w in sk:
            blocks[int((w["t"] - run["t0"]) // 3600)] -= v
        res[n] = dict(paused_s=pz, span_s=run["t1"] - run["t0"], base=base, kept=kept, save=kept - base, n_skip=len(sk), n_skip_tr=sum(1 for v, tr in sk_tr if tr is not None),
                      win_sol=win_sol, los_sol=los_sol, top=[-v for v in vals[:5] if v < 0], blocks=dict(blocks),
                      nblocks=int((run["t1"] - run["t0"]) // 3600) + 1, skipped_t=[w["t"] for v, tr, w in sk if tr is not None])
    return res


def summarize(res, names):
    s = sum(res[n]["save"] for n in names)
    help_ = sum(1 for n in names if res[n]["save"] > 1e-9)
    hurt = sum(1 for n in names if res[n]["save"] < -1e-9)
    tops = sorted([t for n in names for t in res[n]["top"]], reverse=True)
    return dict(save=s, help=help_, hurt=hurt, wo1=s - (tops[0] if tops else 0), wo5=s - sum(tops[:5]),
                win_sol=sum(res[n]["win_sol"] for n in names), los_sol=sum(res[n]["los_sol"] for n in names),
                n_skip_tr=sum(res[n]["n_skip_tr"] for n in names))


def boot_ci(res, names, draws=5000, seed=11):
    blocks = []
    for n in names:
        r = res[n]
        for b in range(r["nblocks"]):
            blocks.append(r["blocks"].get(b, 0.0))
    if not blocks:
        return (0.0, 0.0)
    rr = random.Random(seed); L = len(blocks); out = []
    for _ in range(draws):
        out.append(sum(blocks[rr.randrange(L)] for _ in range(L)))
    out.sort()
    return (out[int(0.05 * draws)], out[int(0.95 * draws)])


def paused_share(run, rule):
    """share of the run's trading time inside pauses (re-play the triggers; approximate: union of [known, known+K))"""
    kept, sk = replay(run, rule)
    # rebuild pause intervals from the rule over kept trades only
    return None


# ---------------------------------------------------------------- task 1: clustering
def clustering(runs, names, label="big", Ms=(5, 15, 30, 60), perms=10000):
    out = {}
    per = []
    for n in names:
        tr = runs[n]["trades"]
        t = [x["t"] for x in tr]; lab = [x[label] for x in tr]
        per.append((t, lab))
    for M in Ms:
        def stat(t, lab):
            c = 0; last = []
            idx = [i for i, l in enumerate(lab) if l]
            for a, b in zip(idx, idx[1:]):
                if t[b] - t[a] <= M * 60: c += 1
            return c
        obs = sum(stat(t, l) for t, l in per)
        cnt = 0; null = []
        rr = random.Random(M)
        for _ in range(perms):
            s = 0
            for t, l in per:
                l2 = l[:]; rr.shuffle(l2); s += stat(t, l2)
            null.append(s)
            if s >= obs: cnt += 1
        out[M] = dict(obs=obs, null_mean=sum(null) / len(null), p=(cnt + 1) / (perms + 1), n_events=sum(sum(l) for t, l in per))
    return out


def conditional(runs, names, trig="big", Ms=(5, 15, 30, 60)):
    """mean scaled value of trades whose fill comes within M min after a trigger trade became known (trigger excluded), vs others"""
    out = {}
    for M in Ms:
        a, b = [], []
        for n in names:
            tr = runs[n]["trades"]
            kn = sorted(x["known"] for x in tr if x[trig])
            for x in tr:
                i = bisect.bisect_right(kn, x["t"]) - 1
                if i >= 0 and x["t"] - kn[i] <= M * 60:
                    a.append(x["v"])
                else:
                    b.append(x["v"])
        # permutation p (within-run label shuffle of trade values)
        obs = (sum(a) / len(a) if a else 0) - (sum(b) / len(b) if b else 0)
        out[M] = dict(n_after=len(a), mean_after=sum(a) / len(a) if a else None, sum_after=sum(a), n_other=len(b),
                      mean_other=sum(b) / len(b) if b else None, diff=obs, big_rate_after=None)
    return out


def conditional_perm(runs, names, trig="big", M=15, perms=2000):
    """p-value for 'trades after a trigger are worse': shuffle trade values within each run, keep times and trigger times"""
    def diff(vals_by_run):
        a = b = 0.0; na = nb = 0
        for n in names:
            tr = runs[n]["trades"]; kn = trig_kn[n]
            for x, v in zip(tr, vals_by_run[n]):
                i = bisect.bisect_right(kn, x["t"]) - 1
                if i >= 0 and x["t"] - kn[i] <= M * 60:
                    a += v; na += 1
                else:
                    b += v; nb += 1
        return (a / na if na else 0) - (b / nb if nb else 0)
    trig_kn = {n: sorted(x["known"] for x in runs[n]["trades"] if x[trig]) for n in names}
    vals = {n: [x["v"] for x in runs[n]["trades"]] for n in names}
    obs = diff(vals)
    rr = random.Random(5); le = 0
    for _ in range(perms):
        v2 = {}
        for n in names:
            l = vals[n][:]; rr.shuffle(l); v2[n] = l
        if diff(v2) <= obs: le += 1
    return obs, (le + 1) / (perms + 1)


def nextk(runs, names, trig="big", k=5):
    """the next k trades after each trigger (its known time): mean value, big-loss rate"""
    vals = []; bigs = 0; cnt = 0
    for n in names:
        tr = runs[n]["trades"]
        for i, x in enumerate(tr):
            if not x[trig]: continue
            nxt = [y for y in tr if y["t"] >= x["known"]][:k]
            for y in nxt:
                vals.append(y["v"]); bigs += y["big"]; cnt += 1
    allv = [y["v"] for n in names for y in runs[n]["trades"]]
    allb = sum(y["big"] for n in names for y in runs[n]["trades"])
    return dict(n=cnt, mean=sum(vals) / cnt if cnt else None, big_rate=bigs / cnt if cnt else None,
                mean_all=sum(allv) / len(allv), big_rate_all=allb / len(allv))


if __name__ == "__main__":
    live = build_live(); paper = build_paper()
    pickle.dump(dict(live=live, paper=paper), open(f"{OUT}/runs.pkl", "wb"))
    print("live runs", len(live), "paper runs", len(paper), {n: len(r["trades"]) for n, r in paper.items()})
