"""Test exit rules on every position. Decision-time info only (trades with arrival t < decision)."""
import sys, random
from feat import *
from exitsim import replay
def big_sell(X):
    def rule(r, oth):
        for x in oth:
            if not x["buy"] and x["sol"] >= X * 1e9: return x["t"], x["slot"]
        return None
    return rule
def cum_sell(X):
    def rule(r, oth):
        c = 0
        for x in oth:
            c += (-x["sol"] if x["buy"] else x["sol"])
            if c >= X * 1e9: return x["t"], x["slot"]
        return None
    return rule
def px_drop(P):   # value below entry by P% after a seen trade
    def rule(r, oth):
        T = r["tokens"]; cost = r["sol_in"]
        for x in oth:
            if x["vsol"] * T / (x["vtok"] + T) <= cost * (1 - P / 100): return x["t"], x["slot"]
        return None
    return rule
def timer(ms):
    def rule(r, oth): return r["fill"]["t"] + ms * 1e6, r["fill"]["slot"]
    return rule
RULES = {**{f"bigsell>={X}": big_sell(X) for X in (0.5, 1, 1.5, 2, 3)}, **{f"netsell>={X}": cum_sell(X) for X in (1, 2, 3)},
         **{f"drop>={P}%": px_drop(P) for P in (5, 8, 10, 15)}, **{f"timer{ms}": timer(ms) for ms in (0, 100)}}
def boot(v, n=4000):
    random.seed(7); b = sorted(sum(random.choice(v) for _ in v) for _ in range(n)); return b[int(.05 * n)], b[int(.95 * n)]
if __name__ == "__main__":
    for strict in (True, False):
        print("== strict (lands >= trigger slot+1)" if strict else "== measured latency only (same slot allowed)")
        for name, rule in RULES.items():
            out = []
            for run in RUNS:
                rs = load(run); d = [replay(r, rule, strict=strict)[0] for r in rs]
                L = sum(x for x, r in zip(d, rs) if r["pnl"] < 0); W = sum(x for x, r in zip(d, rs) if r["pnl"] >= 0)
                out.append((run, sum(d), L, W, sum(1 for x in d if x != 0), d))
            tr = [x for o in out[:3] for x in o[5]]; ho = out[3][5]
            trs = sorted(tr, reverse=True); lo, hi = boot(tr)
            print(f"{name:12s} " + " ".join(f"{o[0]} {o[1]:+.3f}(L{o[2]:+.3f}/W{o[3]:+.3f} n{o[4]})" for o in out) +
                  f" | train {sum(tr):+.3f} CI[{lo:+.3f},{hi:+.3f}] -top5 {sum(trs[5:]):+.3f} | r36 {sum(ho):+.3f}")
