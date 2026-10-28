#!/usr/bin/env python3
"""REARM step 9 (read-only; G2): WHERE the re-arm fills come from, for given configs over given days (res_D<k>_<tag>.pkl + ev_D<k>.pkl).
Each re fill is put in one class by what the tape did (INFERRED replay fills, tape facts MEASURED):
  on_next_dump  = the fill lands in the slot of the token's next whale dump or the slot after (what analyst A's rule meant to buy);
  before_dump   = a next whale dump exists inside the window but the fill came earlier (another >= 12 % drop, so the window was used up);
  other_drop    = no whale dump inside the window: the fill is on a cascade of smaller sells / a non-whale >= 12 % drop.
Also: re windows that had a next whale dump inside their slots, and how many of those dumps we filled.
P&L = gross (live exit) - NOW costs, model, mSOL per fill [90 % bootstrap]; wave = the wave exit.
usage: r9_decomp.py TAGS CFG[,CFG] DAYS [--out file]"""
import sys, pickle, collections, os
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
COST = 2_015_140


def boot(v, n=2000):
    v = np.asarray(v, float)
    if len(v) < 2: return (np.nan, np.nan)
    r = np.random.default_rng(1); m = [v[r.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return np.percentile(m, 5), np.percentile(m, 95)


def main(tags, cfgs, days, outf=None):
    L = []
    def P(s=""): print(s, flush=True); L.append(s)
    for cfg in cfgs:
        G = collections.defaultdict(list); per_day = collections.defaultdict(lambda: collections.defaultdict(list))
        nwin = collections.Counter()
        for d in days:
            rows = None
            for t in tags:
                fn = f"{OUT}/res_D{d}_{t}.pkl"
                if not os.path.exists(fn): continue
                Z = pickle.load(open(fn, "rb"))
                if cfg in Z["out"]: rows = Z["out"][cfg][0]; break
            if rows is None: continue
            EV = pickle.load(open(f"{OUT}/ev_D{d}.pkl", "rb"))["EV"]
            nxt = {(e["mint"], e["slot"], e["idx"]): e["nxt"] for e in EV}
            G_ = int(cfg.split(":")[1])
            for r in rows:
                key = r[0]
                if key[0] != "re" or not r[1]: continue
                src = key[6]; nx = nxt.get((key[1], src[0], src[1]))
                in_win = nx is not None and nx[0] <= key[2] + G_
                nwin["armed"] += 1; nwin["dump_in_window"] += in_win
                if not r[3]: continue
                fS = r[8][0]; g = (r[8][2]["base"][0] - COST) / 1e6; gw = (r[8][2]["wave"][0] - COST) / 1e6
                if in_win and nx[0] <= fS <= nx[0] + 1: cls = "on_next_dump"; nwin["dump_filled"] += 1
                elif in_win and fS < nx[0]: cls = "before_dump"
                else: cls = "other_drop"
                G[cls].append((g, gw, r[8][2]["base"][1])); per_day[d][cls].append(g)
        P(f"\n### {cfg} (tags {tags}, days {days}): re windows armed {nwin['armed']:,}; with the next whale dump inside the window {nwin['dump_in_window']:,}; "
          f"that dump filled by us {nwin['dump_filled']:,} ({100 * nwin['dump_filled'] / max(nwin['dump_in_window'], 1):.0f}%)")
        P("| Fill class | Fills | mSOL/fill model NOW [90%] | Win | Wave exit mSOL/fill | Exits tp/sl/time | Sum SOL model |")
        P("|---|---|---|---|---|---|---|")
        for k in ("on_next_dump", "before_dump", "other_drop"):
            v = G.get(k, [])
            if not v: P(f"| {k} | 0 | | | | | |"); continue
            a = np.array([x[0] for x in v]); b = np.array([x[1] for x in v]); lo, hi = boot(a)
            c = collections.Counter(x[2] for x in v)
            P(f"| {k} | {len(v)} | {a.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] | {100 * (a > 0).mean():.0f}% | {b.mean():+.2f} | {c.get('tp', 0)}/{c.get('sl', 0)}/{c.get('time', 0)} | {a.sum() / 1e3:+.2f} |")
        P("Per day, mSOL/fill model (fills): " + "; ".join(f"D{d}: " + ", ".join(f"{k} {np.mean(v):+.1f} ({len(v)})" for k, v in sorted(per_day[d].items())) for d in sorted(per_day)))
    if outf: open(f"{OUT}/{outf}", "a").write("\n".join(L) + "\n")


if __name__ == "__main__":
    a = sys.argv
    outf = a[a.index("--out") + 1] if "--out" in a else None
    main(a[1].split(","), a[2].split(","), [int(x) for x in a[3].split(",")], outf)
