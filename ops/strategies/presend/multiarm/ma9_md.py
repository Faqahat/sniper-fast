#!/usr/bin/env python3
"""MULTIARM: markdown tables from ma7_tables JSON (r37 = pick, r38 = frozen test) -> stdout / a file.
usage: ma9_md.py TABLES_r37.json TABLES_r38.json OUT.md [--variants a,b,c]"""
import sys, json


def f(x, nd=2, plus=True):
    if x is None: return "-"
    if isinstance(x, list): return "[" + ", ".join(f(v, nd, plus) for v in x) + "]"
    return (f"{x:+.{nd}f}" if plus else f"{x:.{nd}f}")


def row(n, s):
    tp = s["trades_per_token"]
    return (f"| {n} | {s['extra_windows_day']:+.0f} | {s['extra_fills_day']:+.1f} | {tp['median']:.0f} / {tp['p90']:.0f} / {tp['max']} ({100 * tp['share_3plus']:.1f}% 3+) | "
            f"**{f(s['net_day'])}** | {f(s['extra_day'])} / {f(s['knock_day'])} | {f(s['net_cut_day'])} | {f(s['net_wo_top5_day'])} | {f(s['ci90_net_day'])} | "
            f"{f(s['day_net_day'])} / {f(s['night_net_day'])} | {100 * s['hours_positive_share']:.0f}% | {f(s['extra_fail_fees_day'], 3)} | {100 * s['refused_share']:.1f}% |")


HDR = ("| variant | extra windows/day | extra fills/day | trades per traded token: median / p90 / max | **added SOL/day** (slip) | of it: extra trades / knock-on | "
       "added at -20% followers | added w/o top 5 | CI90 (hours) | day / night | hours > 0 | extra try fees/day | tries refused |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def table(T, names):
    out = [HDR]
    for n in names:
        if n in T: out.append(row(n, T[n]))
    return "\n".join(out)


if __name__ == "__main__":
    a = sys.argv[1:]
    names = None
    if "--variants" in a: k = a.index("--variants"); names = a[k + 1].split(","); del a[k:k + 2]
    T37 = json.load(open(a[0])); T38 = json.load(open(a[1])) if a[1] != "-" else {}
    names = names or list(T37)
    txt = f"### r37 (pick; {T37[names[0]]['hours']} h)\n\n" + table(T37, names)
    if T38: txt += f"\n\n### r38 (frozen test; {T38[next(iter(T38))]['hours']} h)\n\n" + table(T38, names)
    open(a[2], "w").write(txt + "\n")
    print(txt)


def hourly_table(T, names):
    """per run hour (PKT label): the variant's added SOL in that hour (rep mean, slip basis)"""
    n0 = names[0]
    pk = T[n0]["hourly_pkt"]; hw = T[n0]["hourly_w"]
    out = ["| hour (PKT) | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for h in range(len(pk)):
        out.append(f"| {pk[h]:02d}{'' if hw[h] >= 0.99 else f' ({hw[h]:.2f} h)'} | " + " | ".join(f"{T[n]['hourly_net'][h]:+.3f}" for n in names) + " |")
    out.append("| hours > 0 | " + " | ".join(f"{100 * T[n]['hours_positive_share']:.0f}%" for n in names) + " |")
    return "\n".join(out)
