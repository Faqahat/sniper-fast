#!/usr/bin/env python3
"""LIM step 6 (read-only): haqq's real price limits from the RPC sample (data/lim/rpc_args.jsonl; pump buy CPI args =
spend, min_tokens_out; failed txs also log Left = tokens it would get, Right = min_out) joined with the tape context
(data/lim/hctx2.pkl). For each limited buy: implied tolerance vs each candidate reference state:
  pre-dump (row before the dump), post-dump (dump row), his position (row before his tx), and 'decided' = the state
  after the last outside trade landing >= 1 slot before his tx (what a ~1-slot-late reader saw).
tolerance = tokens(spend at reference) / min_out - 1. A rule 'min_out = tokens at ref / (1+x)' shows as a spike at x.
Out: data/lim/l6.txt"""
import json, pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    H = {r["sig"]: r for r in pickle.load(open(f"{OUT}/hctx2.pkl", "rb"))}
    A = [json.loads(l) for l in open(f"{OUT}/rpc_args.jsonl")]
    rows = []
    for a in A:
        if not a.get("pump"): continue
        p = bytes.fromhex(a["pump"][0]); spend = int.from_bytes(p[8:16], "little") / 1e9; mo = int.from_bytes(p[16:24], "little")
        h = H.get(a["sig"])
        if h is None: continue
        left = right = None
        for l in a.get("logs") or []:
            if l.startswith("Program log: Left:"): left = int(l.split(":")[-1])
            if l.startswith("Program log: Right:"): right = int(l.split(":")[-1])
        r = dict(sig=a["sig"], day=a["day"], ok=a["ok"], spend=spend, min_out=mo, limited=mo > 1, left=left, right=right, dip=h.get("dip"), add=h.get("add"),
                 pr=h.get("pr"), nb=h.get("nb_ahead"), d_slots=h.get("d_slots"))
        tp = S.entry_tokens(h["vp"], h["tp"], spend) if "vp" in h else None
        r["tok_pos"] = tp
        if "vd" in h:
            r["tol_post"] = S.entry_tokens(h["vd"], h["td"], spend) / mo - 1 if mo > 1 else None
            r["tol_pre"] = S.entry_tokens(h["v0"], h["t0"], spend) / mo - 1 if mo > 1 and h.get("v0") else None
            r["tol_pos"] = tp / mo - 1 if mo > 1 else None
        rows.append(r)
    P(f"# haqq limits from {len(A)} RPC-fetched buy txs (public RPC sample, stratified by day x filled/failed; MEASURED)")
    P(f"joined with tape context: {len(rows)}")
    chk = [r for r in rows if r["left"] and r["tok_pos"]]
    if chk:
        e = np.array([r["tok_pos"] / r["left"] - 1 for r in chk])
        P(f"check: tokens at his position from tape vs the program's logged 'Left' (n={len(chk)}): median {100*np.median(e):+.2f}%, p10/p90 {100*np.percentile(e,10):+.2f}/{100*np.percentile(e,90):+.2f}%")
    P("\n## Limit presence by size (SOL spend) and outcome (sample counts; fails over-sampled 50/50 by design)")
    P("| spend | filled: n / limited % | failed: n / limited % |"); P("|---|---|---|")
    for s in sorted({round(r["spend"], 3) for r in rows}):
        f = [r for r in rows if round(r["spend"], 3) == s and r["ok"]]; x = [r for r in rows if round(r["spend"], 3) == s and not r["ok"]]
        P(f"| {s} | {len(f)} / {100*np.mean([r['limited'] for r in f]) if f else 0:.0f} | {len(x)} / {100*np.mean([r['limited'] for r in x]) if x else 0:.0f} |")
    lim = [r for r in rows if r["limited"] and r.get("tol_post") is not None]
    P(f"\n## Implied tolerance of LIMITED buys vs candidate references (n={len(lim)}); tol = tokens at ref / min_out - 1, %")
    P("| reference | p5 | p10 | p25 | p50 | p75 | p90 | p95 | share within +-1% of the median |"); P("|---|---|---|---|---|---|---|---|---|")
    for k in ("tol_pre", "tol_post", "tol_pos"):
        v = np.array([r[k] for r in lim if r.get(k) is not None]) * 100
        if not len(v): continue
        m = np.median(v)
        P(f"| {k} | " + " | ".join(f"{x:+.1f}" for x in np.percentile(v, [5, 10, 25, 50, 75, 90, 95])) + f" | {100*np.mean(np.abs(v-m)<=1):.0f}% |")
    P("\n## Limited buys by size: tolerance vs post-dump / vs his position (p25/p50/p75 %)")
    for s in sorted({round(r["spend"], 3) for r in lim}):
        v = [r for r in lim if round(r["spend"], 3) == s]
        P(f"- spend {s}: n {len(v)} (filled {sum(r['ok'] for r in v)}); tol_post " + "/".join(f"{x:+.1f}" for x in np.percentile([100*r['tol_post'] for r in v], [25, 50, 75])) +
          "; tol_pre " + "/".join(f"{x:+.1f}" for x in np.percentile([100*r['tol_pre'] for r in v if r['tol_pre'] is not None] or [0], [25, 50, 75])) +
          "; tol_pos " + "/".join(f"{x:+.1f}" for x in np.percentile([100*r['tol_pos'] for r in v], [25, 50, 75])) + f"; DIP {sum(bool(r['dip']) for r in v)} add {sum(bool(r['add']) for r in v)}")
    pickle.dump(rows, open(f"{OUT}/limits.pkl", "wb"))
    open(f"{OUT}/l6.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
