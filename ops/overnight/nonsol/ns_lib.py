#!/usr/bin/env python3
# Shared evaluation helpers for the non-SOL replay table (data/table.jsonl).
import json, os, statistics, collections
HERE = "/home/moiz/sniper/ops/overnight/nonsol"; DATA = os.path.join(HERE, "data")
B = 0.5; S0 = 0.003; SELL_FEE = 0.0005; FAIL = -0.005
def load_rows():
    return [json.loads(l) for l in open(os.path.join(DATA, "table.jsonl"))]
def tradeable(r):
    return (not r.get("mayhem")) and r.get("rate") and r.get("g_end", 0) >= 1 and r.get("rep") is not None
def pnl(r, Lm, var="strict", ex="8.0", oh=0.02, s=0.003):
    """None = no entry possible (no placement); FAIL = guarded buy failed (someone got in first / price moved > 0.5%);
    else SOL PnL: proceeds rescaled for the swap leg s (buy leg ~linear, sell leg exact), buy overhead oh, sell tx fee."""
    e = (r.get("rep") or {}).get(str(Lm))
    if not e: return None
    v = e.get(var)
    if v is None: return FAIL
    out = v[ex][0] * (1 - s) / (1 - S0) * (1 - s)
    return out - B * (1 + oh) - SELL_FEE
def summ(rows, Lm, var="strict", ex="8.0", oh=0.02, s=0.003):
    v = [x for x in (pnl(r, Lm, var, ex, oh, s) for r in rows) if x is not None]
    fills = [x for x in v if x != FAIL]; nf = len(v) - len(fills)
    tot = sum(fills) + FAIL * nf
    fs = sorted(fills, reverse=True)
    return dict(n=len(v), fills=len(fills), tot=round(tot, 3), med=round(statistics.median(fills), 4) if fills else None,
                win=round(sum(1 for x in fills if x > 0) / len(fills), 3) if fills else None, wo5=round(tot - sum(fs[:5]), 3),
                mean=round(sum(fills) / len(fills), 4) if fills else None)
def halves(rows, Lm, var="strict", ex="8.0", oh=0.02, s=0.003):
    rs = sorted(rows, key=lambda r: r["bt"]); h = len(rs) // 2
    return summ(rs[:h], Lm, var, ex, oh, s)["tot"], summ(rs[h:], Lm, var, ex, oh, s)["tot"]
def fmt(d):
    if d["fills"] == 0: return f"n={d['n']} no fills"
    return f"tot {d['tot']:+7.2f} | fills {d['fills']:4d}/{d['n']:4d} | med {d['med']:+.4f} | mean {d['mean']:+.4f} | win {d['win']:.0%} | w/o top5 {d['wo5']:+7.2f}"
