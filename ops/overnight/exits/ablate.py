#!/usr/bin/env python3
# READ-ONLY, offline. Which exit pieces carry the profit, by replay on the wallets' REAL entries: each token runs its fitted
# config rule (mode "config") or the consensus rule (mode "consensus") with one component switched off at a time
# (lightning / take-profit ladder / drawdown trims / stop loss / dev-follow / timeout), plus simple baselines.
# usage: python3 -I ablate.py [config|consensus]
import sys, os, json, pickle, copy, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from replay import run, corr

def total(res): return sum(s["pnl"] for c, s in res)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "config"
    cases = pickle.load(open(os.path.join(EXITS, "cache", "cases.pkl"), "rb"))
    J = json.load(open(os.path.join(EXITS, "exit_rules.json")))["rules"]
    def rule_of(c):
        if mode == "consensus": return J["consensus"]["rule"]
        return (J.get(c["cfg"]) or J[f"wallet:{c['w']}"])["rule"]
    def run_with(drop=None, cases=cases):
        out = []
        for c in cases:
            r = copy.deepcopy(rule_of(c))
            if drop:
                for d in drop: r.pop(d, None)
            out += run([c], r)
        return out
    act = sum(c["rt"]["pnl"] for c in cases); big = [c for c in cases if c["rt"]["buy_sol"] >= 2.4]
    base = run_with(); bb = run_with(cases=big)
    print(f"mode {mode}: {len(cases)} tokens with paths; real {act:+.2f} SOL; replay of the full rule {total(base):+.2f} "
          f"(corr {corr([c['rt']['pnl'] for c, s in base], [s['pnl'] for c, s in base]):.3f}); buys >= 2.4 SOL: {len(big)} tokens real "
          f"{sum(c['rt']['pnl'] for c in big):+.2f}, replay {total(bb):+.2f}")
    # piece PnL by trigger in the replay (net proceeds minus the pro-rata cost of the tokens each piece sold)
    piece = collections.defaultdict(float)
    for c, s in base:
        rem = 1.0
        for x in s["sells"]:
            share = rem * x["frac"]; rem -= share
            piece[x["why"].rstrip("0123456789")] += x["net"] - c["rt"]["cost"] * share
    print("   replay piece PnL by trigger:", {k: round(v, 2) for k, v in sorted(piece.items(), key=lambda kv: -kv[1])})
    for comp, drop in [("lightning", ["lightning"]), ("take-profit ladder", ["tp", "tp_repeat"]), ("drawdown trims", ["drawdown"]),
                       ("stop loss", ["stop_loss"]), ("dev-follow", ["follow_dev"]), ("timeout", ["timeout_s"])]:
        res = run_with(drop); rb = run_with(drop, big)
        print(f"   without {comp:18s}: {total(res):+7.2f} SOL (change {total(res) - total(base):+6.2f}; buys >= 2.4 SOL {total(rb) - total(bb):+6.2f})")
    for name, r2 in [("sell 100% at +1 slot", dict(lightning=dict(frac=1.0, delay=1))), ("sell 100% at +6 slots", dict(lightning=dict(frac=1.0, delay=6))),
                     ("stop -10% only, else hold to path end", dict(stop_loss=0.10)), ("timeout 60 s only", dict(timeout_s=60))]:
        res = run(cases, r2)
        print(f"   baseline {name:38s}: {total(res):+7.2f} SOL")
