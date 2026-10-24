#!/usr/bin/env python3
# READ-ONLY, offline: CANDIDATES.md from summarize.py output (like-us = fee/buy >= 0.9%, then cheaper real snipers)
import sys, json
R = json.load(open(sys.argv[1])); OUT = sys.argv[2]
ok = [r for r in R if r.get("n") and not r["why"]]
like = [r for r in ok if r["ratio"] >= 0.009]; cheap = [r for r in ok if r["ratio"] < 0.009]
def line(i, r):
    notes = []
    if r["nonsol"]: notes.append(f"+{r['nonsol']} non-SOL-quoted buys")
    if r["top_cre"] >= 0.2: notes.append(f"one dev = {r['top_cre']:.0%} of buys")
    if r["n"] < 20: notes.append(f"{r['n']} SOL buys seen")
    w = r["w"]
    return (f"| {i} | [{w[:6]}…{w[-4:]}](https://gmgn.ai/sol/address/{w}) | {r['snipe']:.0%} | {r['sol']:.2f} | {r['fee']:.4f} | {r['ratio']*100:.1f}% | {r['in_curve']:.1f} | "
            f"{r['creators']}/{r['n']} | {r['seen']} | {'; '.join(notes) or '—'} |")
H = "| # | wallet (GMGN) | snipes | buy SOL | fee SOL | fee/buy | SOL before them | devs/buys | seen in sample | notes |\n|---|---|---|---|---|---|---|---|---|---|"
out = [f"# Sniper candidates like us — buys only (sells/profit not analyzed)", "",
       f"{len(ok)} real snipers: {len(like)} with fee/buy >= 0.9% (like us: 1.7-3%), {len(cheap)} cheaper. Excluded {len([r for r in R if r.get('why')])} (reasons at the bottom).", "",
       "## Like us (fee/buy 0.9% and up)", H] + [line(i + 1, r) for i, r in enumerate(like)]
out += ["", "## Real snipers, cheaper fee (under 0.9%)", H] + [line(i + 1 + len(like), r) for i, r in enumerate(cheap)]
out += ["", "## Full addresses"] + [f"{i + 1}. `{r['w']}`" for i, r in enumerate(like + cheap)]
out += ["", "## Excluded"] + [f"- `{r['w']}`: {'; '.join(r['why'])}" for r in R if r.get("why")]
open(OUT, "w").write("\n".join(out) + "\n")
print(f"{len(ok)} OK ({len(like)} like us, {len(cheap)} cheaper); excluded {len([r for r in R if r.get('why')])}")
