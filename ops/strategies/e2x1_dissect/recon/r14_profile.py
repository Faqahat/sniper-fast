#!/usr/bin/env python3
"""recon step 14 (read-only): per-bot profile for the report (D1 lots unless stated) + example links. Out: r14.txt"""
import pickle, collections, time
import numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
L = pickle.load(open(f"{OUT}/lots.pkl", "rb"))
pk = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
Lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); Lines.append(s)
BOTS = ("FRESH", "MINUTE", "OLD")
P("| D1 | FRESH | MINUTE | OLD |"); P("|---|---|---|---|")
def row(name, fn):
    P(f"| {name} | " + " | ".join(fn([l for l in L if l["day"] == "D1" and l["bot"] == b]) for b in BOTS) + " |")
pc = lambda a, q: np.percentile(np.array([v for v in a if v is not None], float), q)
row("size codes", lambda x: ", ".join(f"{k} {v}" for k, v in collections.Counter(l["tier"] for l in x).most_common(4)))
row("age at entry p10/50/90 s", lambda x: "/".join(f"{v:.0f}" for v in pc([l["age_s"] for l in x], [10, 50, 90])))
row("curve vSOL at entry p50", lambda x: f"{pc([l['vsol_before'] for l in x], 50):.1f}")
row("trigger trade in his slot / 1 slot before", lambda x: (lambda m: f"{np.mean([l['trig_slot_gap'] == 0 for l in m]):.0%} / {np.mean([l['trig_slot_gap'] == 1 for l in m]):.0%} (n={len(m)})")([l for l in x if l.get("trig_slot_gap") is not None]))
row("trigger is a buy", lambda x: f"{np.mean([l['trig_buy'] for l in x if 'trig_buy' in l]):.0%}")
row("trigger SOL p50", lambda x: f"{pc([l.get('trig_sol') for l in x], 50):.2f}")
row("other trades in his slot before him p50", lambda x: f"{pc([l.get('feat_same_slot_before') for l in x], 50):.0f}")
row("his tx index in block p50", lambda x: f"{pc([l['i'] for l in x], 50):.0f}")
row("landed buy copy: astralane / helius 10k / helius 1M", lambda x: (lambda c: f"{c[('astralane', 1100000)]}/{c[('helius', 10000)]}/{c[('helius', 1000000)]}")(collections.Counter((l["buy_relay"], l["buy_tip_amt"]) for l in x)))
row("exit tx: astralane 1.1M / helius 1M / 30-min timeout (helius 10k)", lambda x: (lambda c: f"{c[('astralane', (1100000,))]}/{c[('helius', (1000000,))]}/{c[('helius', (10000,))]}")(collections.Counter((l["sell_relays"], l["sell_tip_amts"]) for l in x)))
row("hold p10/50/90 s", lambda x: "/".join(f"{v:.0f}" for v in pc([l["hold_s"] for l in x], [10, 50, 90])))
row("first sell after buy, slots p10/50", lambda x: "/".join(f"{v:.0f}" for v in pc([l["first_sell_slots"] for l in x], [10, 50])))
row("gross return p10/50/90", lambda x: "/".join(f"{100 * v:+.0f}%" for v in pc([l["proceeds"] / l["cost"] - 1 for l in x if not l["is_open"]], [10, 50, 90])))
row("failed txs per lot", lambda x: f"{np.mean([l['n_fail'] for l in x]):.2f}")
row("sold on PumpSwap (graduated)", lambda x: f"{sum(l['swap_sell'] for l in x)}")
row("lots / mints", lambda x: f"{len(x)} / {len({l['mint'] for l in x})}")
P("\n## Examples (D1)")
for b in BOTS:
    x = [l for l in L if l["day"] == "D1" and l["bot"] == b and not l["is_open"]]
    x.sort(key=lambda l: -l["pnl"])
    ex = x[:3] + x[len(x) // 2 - 1:len(x) // 2 + 1] + x[-2:]
    P(f"\n### {b}")
    for l in ex:
        P(f"- {pk(l['bt'])} {l['tier']} age {l['age_s']} s, buy {l['cost']:.3f} SOL, hold {l['hold_s']} s, P&L {l['pnl']:+.4f} — token https://gmgn.ai/sol/token/{l['mint']} · buy https://solscan.io/tx/{l['buy_sig']} · sell https://solscan.io/tx/{l['sells'][-1][0]}")
open(f"{OUT}/r14.txt", "w").write("\n".join(Lines) + "\n")
