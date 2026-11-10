"""BIGLOSS scoring core: sequential causal simulation of SKIP / SIZE rules over all positions in signing-time order.
Ledgers learn ONLY from positions we actually kept (a blocked position has no P&L) and only after they closed
(t_close < current t_sign). Ledger state carries across runs (= a persisted state file, like the creator ledger)."""
import json, collections, math
D = "/home/it/sniper-data/bigloss"
F20 = 0.017  # fixed round-trip cost (SOL, at ~0.55 SOL) used for the crude -20% followers estimate


def load_feats():
    R = [json.loads(l) for l in open(f"{D}/feats.jsonl")]
    R.sort(key=lambda r: r["t_sign"])
    return R


def hours():
    span = {}
    for l in open(f"{D}/run_span.txt"):
        r, a, b = l.split(); span[int(r)] = (int(a), int(b))
    SPLIT = 1793516400000000000
    H = collections.defaultdict(float); HR = {}
    for r, (a, b) in span.items():
        if r == 42:
            HR["r42a"] = (SPLIT - a) / 3.6e12; HR["r42b"] = (b - SPLIT) / 3.6e12
            H["DEV"] += HR["r42a"]; H["VAL"] += HR["r42b"]
        else:
            h = (b - a) / 3.6e12; HR[f"r{r}"] = h
            H["DEV" if r <= 41 else "HOLD"] += h
    return H, HR


class Ledger:
    def __init__(self): self.ev = collections.defaultdict(list)  # key -> [(t_close, pnl, flag)]
    def add(self, k, t, pnl, flag=1.0): self.ev[k].append((t, pnl, flag))
    def stats(self, k, t_now, win_h=None, tau_h=None):
        n = 0; net = 0.0; fl = 0.0; wsum = 0.0
        for (t, p, f) in self.ev.get(k, ()):
            if t >= t_now: continue
            age_h = (t_now - t) / 3.6e12
            if win_h is not None and age_h > win_h: continue
            w = math.exp(-age_h / tau_h) if tau_h else 1.0
            n += 1; net += w * p; fl += w * f; wsum += w
        return n, net, fl, wsum


def f20(p, size):
    c = F20 * (size / 0.55 if size else 1.0)
    g = p + c
    return (0.8 * g - c) if g > 0 else p


def simulate(R, rule, learn, size_mode=False):
    """rule(r, L) -> fraction to cut (1.0 = skip, 0.5 = half size, 0 = keep). learn(r, L) updates ledgers with a kept position.
    Returns list of (r, cut). Positions are processed in t_sign order; ledger updates queued until t_close."""
    L = {}
    pend = []  # (t_close, r)
    out = []
    import heapq
    for r in R:
        while pend and pend[0][0] < r["t_sign"]:
            _, _, rr = heapq.heappop(pend); learn(rr, L)
        cut = rule(r, L)
        out.append((r, cut))
        if cut < 1.0:
            heapq.heappush(pend, (r["t_close"], id(r), r))
    while pend:
        _, _, rr = heapq.heappop(pend); learn(rr, L)
    return out


def report(res, sets=("DEV", "VAL", "HOLD"), H=None, HR=None, per_run=True, quiet=False):
    """saved = -(cut * pnl) summed over affected positions."""
    out = {}
    for st in sets:
        aff = [(r, c) for r, c in res if r["set"] == st and c > 0]
        allp = [r for r, c in res if r["set"] == st]
        saved = -sum(c * r["pnl"] for r, c in aff)
        W = sum(1 for r, c in aff if r["pnl"] > 0); Lc = len(aff) - W
        wsol = sum(c * r["pnl"] for r, c in aff if r["pnl"] > 0)
        lsol = sum(c * r["pnl"] for r, c in aff if r["pnl"] <= 0)
        bigb = sum(1 for r, c in aff if r["pnl"] <= -0.04)
        bigall = sum(1 for r in allp if r["pnl"] <= -0.04)
        sv = sorted([-(c * r["pnl"]) for r, c in aff], reverse=True)
        wo5 = sum(sv[5:])
        sf20 = -sum(c * f20(r["pnl"], r["sol_in"]) for r, c in aff)
        pr = collections.defaultdict(float)
        for r, c in aff: pr[r["rk"]] += -c * r["pnl"]
        runs_all = sorted(set(r["rk"] for r in allp), key=lambda s: (int(s[1:3]), s))
        o = {"n": len(aff), "W": W, "L": Lc, "win_sol": wsol, "loss_sol": lsol, "saved": saved, "wo5": wo5, "f20": sf20,
             "big_blocked": bigb, "big_all": bigall, "per_run": {k: round(pr.get(k, 0.0), 3) for k in runs_all},
             "base": sum(r["pnl"] for r in allp), "n_all": len(allp)}
        if H: o["per_day"] = saved / H[st] * 24
        out[st] = o
    return out


def fmt(name, o):
    s = []
    for st, v in o.items():
        pos = sum(1 for k, x in v["per_run"].items() if x > 0.0005); neg = sum(1 for k, x in v["per_run"].items() if x < -0.0005)
        s.append(f"{st}: n{v['n']} {v['W']}W/{v['L']}L big{v['big_blocked']}/{v['big_all']} saved {v['saved']:+.3f} wo5 {v['wo5']:+.3f} f20 {v['f20']:+.3f}"
                 + (f" /d {v['per_day']:+.2f}" if 'per_day' in v else "") + f" runs+{pos}-{neg}")
    return f"{name:60} | " + " | ".join(s)
