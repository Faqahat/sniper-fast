#!/usr/bin/env python3
# READ-ONLY: markdown tables from q6_summary.json for the report
import json
S = json.load(open("q6_summary.json")); C = json.load(open("q6_slip_coverage.json"))
EX = ["eos1", "t1", "t2", "t5", "t10"]
VN = {"v0": "no slip", "v1": "slip", "v2": "slip, FiFawH-after-us removed", "v3": "slip, all fast snipers after us removed", "v4": "slip, top-10 after-us buyers removed", "v5": "slip, fast snipers + top-10 removed"}
def cell(x): return f"{x['total']:+.2f} ({x['tot']['R1']:+.2f} / {x['tot']['R2']:+.2f})"
out = []
for sn, short in (("(a) oracle: its attempts", "a"), ("(a') oracle: its filled buys", "a'"), ("(b) walk-forward deployer list (>=2 att, >=10%)", "b"),
                  ("(c) generic rule trained on R1, traded on R2", "c R1→R2"), ("(c) generic rule trained on R2, traded on R1", "c R2→R1"), ("(z) random control launches", "z")):
    for mode in ("L45", "L75"):
        a = S[sn][mode]["v0"]["eos1"]
        out.append(f"\n**{sn} — {mode}**: simulated launches R1 {a['n']['R1']} / R2 {a['n']['R2']}, guarded fills R1 {a['fills']['R1']} / R2 {a['fills']['R2']}. Cells: total SOL (R1 / R2); z = share of fills with no outside buy between our buy and our sell.\n")
        out.append("| variant | eos1 | ~1 s | ~2 s | ~5 s | ~10 s | z eos1 | z 5 s | mean/fill 5 s |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for vk in ("v0", "v1", "v2", "v3", "v4", "v5"):
            v = S[sn][mode][vk]
            out.append(f"| {VN[vk]} | " + " | ".join(cell(v[e]) for e in EX) + f" | {v['eos1']['zero_share']} | {v['t5']['zero_share']} | {v['t5']['mean']} |")
out.append("\n**Later entries (no guard, 0.5% send cost), best and worst exits; v1 = slip, v3 = slip + all fast snipers after us removed**\n")
out.append("| set | mode | fills R1/R2 | v1 eos1 | v1 ~2 s | v1 ~10 s | v3 ~2 s | v3 ~10 s | mean/fill v1 eos1 |")
out.append("|---|---|---|---|---|---|---|---|---|")
for sn in ("(a) oracle: its attempts", "(a') oracle: its filled buys", "(b) walk-forward deployer list (>=2 att, >=10%)", "(z) random control launches"):
    for mode in ("D0.15", "D1", "D2", "D5"):
        v = S[sn][mode]; a = v["v0"]["eos1"]
        out.append(f"| {sn[:32]} | {mode} | {a['fills']['R1']}/{a['fills']['R2']} | {cell(v['v1']['eos1'])} | {cell(v['v1']['t2'])} | {cell(v['v1']['t10'])} | {cell(v['v3']['t2'])} | {cell(v['v3']['t10'])} | {v['v1']['eos1']['mean']} |")
out.append("\n**Slippage-limit coverage** (share of outside buys inside the exit window whose decoded limit is known):\n")
out.append("| set | L45 eos1 | L45 2 s | L45 5 s | L45 10 s | L75 eos1 | L75 5 s | D1 eos1 | D1 5 s |")
out.append("|---|---|---|---|---|---|---|---|---|")
for sn, v in C.items():
    out.append(f"| {sn[:32]} | {v.get('L45|eos1')} | {v.get('L45|t2')} | {v.get('L45|t5')} | {v.get('L45|t10')} | {v.get('L75|eos1')} | {v.get('L75|t5')} | {v.get('D1|eos1')} | {v.get('D1|t5')} |")
open("q6_tables.txt", "w").write("\n".join(out)); print("\n".join(out)[:6000])
