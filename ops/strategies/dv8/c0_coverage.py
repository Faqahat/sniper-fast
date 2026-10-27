#!/usr/bin/env python3
"""DV8 step 0 (read-only): coverage of the merged tape (dv8/tab) per PKT hour.
expected slots = slots between the hour's boundaries (slot<->block-time interpolation over recorded slots);
present = slots with >=1 recorded tx; trades = pump.fun TradeEvents decoded; usable hour = present/expected >= 0.95 and trades >= 50% of the
median hour. Days are 24 h windows ending 23:15 PKT (same boundary as the earlier DV8 test day).
Out: dv8/c0_coverage.txt, dv8/hours.json"""
import json, time, collections
import numpy as np
D = "/home/moiz/sniper-data/dv8"; TAB = f"{D}/tab"
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
DAY0 = 1793038500 - 5 * 86400        # 10-21 23:15 PKT


def day_of(t): return int((t - DAY0) // 86400)


def day_name(k): return f"{pkt(DAY0 + k * 86400)}->{pkt(DAY0 + (k + 1) * 86400)}"


def main():
    S = np.load(f"{TAB}/slots.npy")
    sl = S["slot"].astype(np.int64); bt = S["bt"].astype(np.int64)
    ok = bt > 1.7e9; sl, bt = sl[ok], bt[ok]
    T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
    tbt = np.asarray(T["bt"]).astype(np.int64)
    # per-slot ms from the long-run slope
    ms_per_slot = (bt[-1] - bt[0]) / (sl[-1] - sl[0]) * 1000
    h0 = (bt.min() + 18000) // 3600 * 3600 - 18000; h1 = (bt.max() + 18000) // 3600 * 3600 - 18000 + 3600
    hrs = np.arange(h0, h1, 3600)
    # slot at each hour boundary: interpolate bt->slot on recorded slots (monotone enough)
    sb = np.interp(hrs, bt, sl); se = np.interp(hrs + 3600, bt, sl)
    pres = np.searchsorted(sl, se) - np.searchsorted(sl, sb)
    tr = np.histogram(tbt, bins=np.append(hrs, hrs[-1] + 3600))[0]
    med = np.median(tr[tr > 0])
    rows = []; out = [f"# Tape coverage per PKT hour (dv8/tab: {len(T):,} trades, slots {sl[0]}->{sl[-1]}, {ms_per_slot:.1f} ms/slot avg)",
                      "| hour PKT | expected slots | present | cov % | trades | usable |", "|---|---|---|---|---|---|"]
    for h, a, b, p, n in zip(hrs, sb, se, pres, tr):
        exp = max(b - a, 1); cov = p / exp
        # clip: hours at the edges
        us = bool(cov >= 0.95 and n >= 0.5 * med)
        rows.append(dict(h=int(h), exp=float(exp), present=int(p), cov=float(cov), trades=int(n), usable=us))
        out.append(f"| {pkt(h)} | {exp:.0f} | {p} | {100 * cov:.1f} | {n:,} | {'yes' if us else 'NO'} |")
    # per day
    out += ["", "## Per day (24 h windows ending 23:15 PKT)", "| day | usable hours | partial/missing hours | trades |", "|---|---|---|---|"]
    byd = collections.defaultdict(list)
    for r in rows:
        # assign an hour to the day containing its midpoint
        byd[day_of(r["h"] + 1800)].append(r)
    for k in sorted(byd):
        v = byd[k]; u = sum(r["usable"] for r in v)
        out.append(f"| D{k} {day_name(k)} | {u} | {24 - u} | {sum(r['trades'] for r in v):,} |")
    print("\n".join(out)); open(f"{D}/c0_coverage.txt", "w").write("\n".join(out) + "\n")
    json.dump(dict(day0=DAY0, rows=rows), open(f"{D}/hours.json", "w"))


if __name__ == "__main__":
    main()
