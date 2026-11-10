#!/usr/bin/env python3
"""SHADOW21 s2: tables from scored.json -> stdout markdown"""
import json, collections, numpy as np
M = json.load(open("/home/it/sniper-data/apex2/shadow21/scored.json"))
HRS = 4.0; K = 24 / HRS
def stats(ms, z, e="w0.4_6.0", key="net"):
    v = np.array([m[f"{key}_{z}_{e}_0.0"] for m in ms]); f = np.array([m[f"{key}_{z}_{e}_0.2"] for m in ms])
    pl = np.array([m[f"pl_{z}"] for m in ms]); cd = [m[f"cond_{z}_{e}_0.0"] for m in ms if m[f"cond_{z}_{e}_0.0"] is not None]
    s = np.sort(v)[::-1]; k5 = int(np.ceil(len(s) * .05))
    return dict(n=len(ms), lands=pl.sum(), win=(np.mean(np.array(cd) > 0) if cd else 0), net=v.sum(), day=v.sum() * K,
                wo5=s[5:].sum() * K, wo5p=s[k5:].sum() * K, fol=f.sum() * K, trip=(v.sum() / pl.sum() if pl.sum() else 0))
HDR = "| set | size | exit | costs | n | exp. lands (first) | win % (landed) | net SOL (4 h) | SOL/day | w/o top 5 | w/o top 5% | −20% fol /day | net per landed mSOL |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|"
def row(nm, ms, z, e="w0.4_6.0", key="net"):
    s = stats(ms, z, e, key)
    return (f"| {nm} | {z} | {e} | {'+exec gap' if key=='netx' else ('always-A' if key=='A' else 'M1')} | {s['n']} | {s['lands']:.1f} | {s['win']*100:.0f} | "
            f"{s['net']:+.3f} | **{s['day']:+.2f}** | {s['wo5']:+.2f} | {s['wo5p']:+.2f} | {s['fol']:+.2f} | {s['trip']*1e3:+.2f} |")
P = [m for m in M if m["pass_"]]; F = [m for m in M if not m["pass_"]]
pr = print
pr(f"scored {len(M)} of {len(M)}; PASS {len(P)}, FAIL {len(F)}; create slot match tape {sum(m['slot_match'] for m in M)}/{len(M)}\n")
pr("## 1. Main (M1 live-calibrated landing, guard first)\n" + HDR)
for z in (0.4, 1.0):
    for nm, ms in (("ALL", M), ("PASS", P), ("FAIL", F)):
        pr(row(nm, ms, z))
pr("\n## 1b. Variants (PASS / ALL)\n" + HDR)
for z in (0.4, 1.0):
    for nm, ms in (("PASS", P), ("ALL", M)):
        pr(row(nm, ms, z, key="netx")); pr(row(nm, ms, z, key="A")); pr(row(nm, ms, z, e="h2")); pr(row(nm, ms, z, e="b0.3"))
pr("\n## 2. By creator (0.4 SOL, M1, wave)\n| creator | n | PASS | exp. lands | net PASS SOL | net ALL SOL | share of PASS net |\n|---|---|---|---|---|---|---|")
by = collections.defaultdict(list)
for m in M: by[m["creator"]].append(m)
tp = sum(m["net_0.4_w0.4_6.0_0.0"] for m in P)
for c, ms in sorted(by.items(), key=lambda x: -len(x[1]))[:12]:
    pp = [m for m in ms if m["pass_"]]; np_ = sum(m["net_0.4_w0.4_6.0_0.0"] for m in pp)
    pr(f"| {c[:8]} | {len(ms)} | {len(pp)} | {sum(m['pl_0.4'] for m in ms):.1f} | {np_:+.3f} | {sum(m['net_0.4_w0.4_6.0_0.0'] for m in ms):+.3f} | {np_/tp*100 if tp else 0:.0f}% |")
pr(f"\ncreators: {len(by)}; top creator share of buys {max(len(v) for v in by.values())/len(M)*100:.0f}%")
for z in (0.4,):
    top = sorted(by.items(), key=lambda x: -len(x[1]))[0][0]
    pr("PASS excluding top creator: " + row("PASS−top", [m for m in P if m["creator"] != top], z))
pr("\n## 3. Top 8 PASS trades 0.4 (M1 wave)\n| id | creator | mint | score | P(land) | net mSOL | −20% mSOL |\n|---|---|---|---|---|---|---|")
for m in sorted(P, key=lambda m: -m["net_0.4_w0.4_6.0_0.0"])[:8]:
    pr(f"| {m['id']} | {m['creator'][:8]} | [{m['mint'][:6]}](https://gmgn.ai/sol/token/{m['mint']}) | {m['score']:.2f} | {m['pl_0.4']:.2f} | {m['net_0.4_w0.4_6.0_0.0']*1e3:+.1f} | {m['net_0.4_w0.4_6.0_0.2']*1e3:+.1f} |")
pr("\n## 4. Landing context\n| set | n | P(land) mean | P(land)=0 | first rival >=0.05 SOL clk median (slots) | creator bundle rows median |\n|---|---|---|---|---|---|")
for nm, ms in (("ALL", M), ("PASS", P), ("FAIL", F)):
    pr(f"| {nm} | {len(ms)} | {np.mean([m['pl_0.4'] for m in ms]):.2f} | {sum(m['pl_0.4']==0 for m in ms)} | {np.median([m['feat']['rc'] for m in ms]):.3f} | {np.median([m['feat']['nb'] for m in ms]):.0f} |")
r1 = collections.Counter(m["feat"]["first"][0][:8] for m in M if m["feat"]["first"] and m["feat"]["rc"] < 0.5)
pr("first rival (>=0.05 SOL, within 0.5 slot) most common: " + ", ".join(f"{k} {v}" for k, v in r1.most_common(6)))
# by hour PKT
pr("\n## 5. By hour (PKT), PASS 0.4 M1 wave\n| hour PKT | n | net SOL |\n|---|---|---|")
import time
hh = collections.defaultdict(list)
for m in P: hh[time.strftime("%H", time.gmtime(m["t"] + 5 * 3600))].append(m["net_0.4_w0.4_6.0_0.0"])
for h in sorted(hh): pr(f"| {h} | {len(hh[h])} | {sum(hh[h]):+.3f} |")
