#!/usr/bin/env python3
# READ-ONLY, offline. Replay the fitted exit rules on the wallets' real entries and compare with the real per-token PnL:
#  (1) "config rule set": each token gets the rule fitted on its copy-trade config (wallet x followed dev, >= 6 tokens),
#      else its wallet's rule; (2) one CONSENSUS rule for everything (the implementable one); (3) per-wallet rules.
# Writes exit_rules.json (machine-readable rules + match metrics) and prints the report tables.
import sys, os, json, pickle, collections, statistics, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from replay import run, corr
from fit import make_rule, prep, schedule_dist

OBJ = sys.argv[1] if len(sys.argv) > 1 else "dist"
cases = pickle.load(open(os.path.join(EXITS, "cache", "cases.pkl"), "rb"))
for c in cases: prep(c)
F = json.load(open(os.path.join(EXITS, "fits", f"fit_all_{OBJ}.json")))

# consensus rule: token-weighted median (numeric) / mode (categorical) of the per-CONFIG fitted parameters (configs >= 6 tokens)
def consensus():
    cf = [(v["params"], v["fit"]["n"]) for k, v in F.items() if ":" in k and not k.startswith("wallet:") and v["fit"]["n"] >= 6]
    out = {}
    for key in cf[0][0]:
        vals = [(p[key], n) for p, n in cf]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v, n in vals):
            xs = sorted(vals, key=lambda x: x[0]); half = sum(n for v, n in xs) / 2; acc = 0
            for v, n in xs:
                acc += n
                if acc >= half: out[key] = v; break
        else:
            cnt = collections.Counter()
            for v, n in vals: cnt[json.dumps(v)] += n
            out[key] = json.loads(cnt.most_common(1)[0][0])
    return out
CONSENSUS = consensus()
print("consensus params:", CONSENSUS)

def stats(pairs):
    a = [x for x, y in pairs]; b = [y for x, y in pairs]
    return dict(n=len(a), real=round(sum(a), 3), replay=round(sum(b), 3), corr=round(corr(a, b), 3),
                mae=round(statistics.mean(abs(x - y) for x, y in pairs), 4), sign_agree=round(sum((x > 0) == (y > 0) for x, y in pairs) / len(a), 3))

def replay_set(rule_of):
    out = []
    for c in cases:
        r = rule_of(c)
        res = run([c], r)
        if not res: continue
        s = res[0][1]; out.append((c, s, schedule_dist(c, s["sells"])))
    return out

def report(name, out, top=8):
    st = stats([(c["rt"]["pnl"], s["pnl"]) for c, s, d in out]); st["sched_dist"] = round(statistics.mean(d for c, s, d in out), 3)
    for w in WALLETS:
        sub = [(c["rt"]["pnl"], s["pnl"]) for c, s, d in out if c["w"] == w]
        if sub: st[w] = stats(sub)
    big = [(c["rt"]["pnl"], s["pnl"]) for c, s, d in out if c["rt"]["buy_sol"] >= 2.4]
    if big: st["buys>=2.4"] = stats(big)
    print(f"\n== {name}: {json.dumps(st)}")
    mm = sorted(out, key=lambda x: -abs(x[0]["rt"]["pnl"] - x[1]["pnl"]))[:top]
    rows = []
    for c, s, d in mm:
        last = [l for l in c["rt"]["legs"] if l["side"] == "sell"][-1]
        rows.append(dict(w=c["w"], mint=c["mint"], cfg=c["cfg"], real=round(c["rt"]["pnl"], 3), replay=round(s["pnl"], 3), real_sells=c["rt"]["n_sells"],
                         replay_sells=len(s["sells"]), replay_why=[x["why"] for x in s["sells"]][:6], buy_tx=sol_link(c["rt"]["legs"][0]["sig"]),
                         last_sell_tx=sol_link(last["sig"]), gmgn=gmgn_link(c["mint"])))
        print(f"   {c['w']} {c['mint'][:8]} {c['cfg']:16s} real {c['rt']['pnl']:+.3f} replay {s['pnl']:+.3f} | sells real {c['rt']['n_sells']} replay {len(s['sells'])} {[x['why'] for x in s['sells']][:5]}")
    return st, rows

if __name__ == "__main__":
    rules = {}
    for k, v in F.items(): rules[k] = make_rule(**v["params"])
    def cfg_rule(c):
        return rules.get(c["cfg"]) or rules[f"wallet:{c['w']}"]
    out_cfg = replay_set(cfg_rule)
    st_cfg, mm_cfg = report("CONFIG RULE SET (per wallet x dev; fallback per wallet)", out_cfg)
    out_w = replay_set(lambda c: rules[f"wallet:{c['w']}"])
    st_w, mm_w = report("PER-WALLET RULE", out_w)
    out_g = replay_set(lambda c: rules["global"])
    st_g, mm_g = report("GLOBAL FITTED RULE", out_g)
    cons = make_rule(**CONSENSUS)
    out_c = replay_set(lambda c: cons)
    st_c, mm_c = report("CONSENSUS RULE (explicit, implementable)", out_c)
    J = dict(note="AKbot-style exit rules inferred from 9Sh2fd / DGmspi (READ-ONLY study). Prices are multiples of the buy's curve exec price "
                  "(SOL into curve / tokens). Rules are evaluated after every market trade; sells execute right after the trigger trade "
                  "(measured: 67-72% of reactions land in the same slot). Fractions are of the REMAINING position.",
             semantics=dict(lightning="sell frac of the position delay slots after the buy, at any price",
                            tp="phases at entry x (1+g1+k*step), k=0..7; each sells s of remaining; a jump past several phases sells once",
                            drawdown="armed once price >= entry x (1+act); reference = new peak; when price <= ref x (1-dd) sell dd_f of remaining; reference resets to that price; repeatable",
                            stop_loss="price <= entry x (1-sl): sell 100%", timeout_s="T seconds (T/0.2125 slots) after the buy (tof=buy) or after the last TP sell (tof=last_tp): sell 100%",
                            follow_dev="clear_at: dev cumulative sold share >= value -> sell 100%; mirror=1: sell the dev's sold fraction of remaining",
                            min_sell_sol="a partial sell leaving less than this SOL value clears the position"),
             rules={**{k: dict(params=F[k]["params"], rule=rules[k], fit=F[k]["fit"]) for k in F},
                    "consensus": dict(params=CONSENSUS, rule=cons, match=st_c)},
             match=dict(config_rule_set=st_cfg, per_wallet=st_w, global_fit=st_g, consensus=st_c),
             mismatches=dict(config_rule_set=mm_cfg, consensus=mm_c))
    json.dump(J, open(os.path.join(EXITS, "exit_rules.json"), "w"), indent=1)
    print("\nwrote exit_rules.json")
