#!/usr/bin/env python3
"""SIZE study sensitivities (read-only, offline; INFERRED):
  (1) follower-limit modes at 0.25 / 0.35 / 0.50 / 0.65: main (refined + revival), fixed (every decoded limit fixed as signed: the
      harshest on bigger sizes), adaptive, revival off;
  (2) our own FAILED pre-send tries (on chain, error 6042 = below min tokens out) re-checked at smaller sizes: the try's own signing
      state and the engine's limit_min_out x0.88 at size S, pump's buy on the chain state just before the failed tx. A try that would
      pass at S but failed live = a fill the smaller size would have gained (window never filled live) or an earlier fill.
Prints only; writes /home/moiz/sniper-data/presend_size/sens.json"""
import sys, json, collections, re
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/size")
import numpy as np
import core, pmath as PM
import sizelib as SL
import s5_run as RUN

OUT = "/home/moiz/sniper-data/presend_size"
SIZES = [250_000_000, 350_000_000, 500_000_000, 650_000_000]
res = {}
for name, base, runs, extra in RUN.GROUPS:
    core.BASE = base
    D = core.Data()
    for fn in extra:
        for l in open(fn):
            r = json.loads(l)
            if r.get("kind") == "ok" or r["sig"] not in D.args: D.args[r["sig"]] = r
    SL.install()
    import positions as PO
    PS = [p for p in PO.presend_positions(D) if p.run in runs]
    RG, RF = PO.regular_positions(D)
    RG = [p for p in RG if p.run in runs and p.sell_tr is not None and p.realized is not None]
    delays, found, ndl = RUN.calib(D, PS, RG, PO)
    for p in PS + RG: SL.mark_bad(D, p)
    for run in runs:
        P = [p for p in PS if p.run == run]
        out = {}
        for mode in ("main", "fixed", "adaptive", "norevive"):
            SL.CFG["resurrect"] = mode != "norevive"
            fm = "refined" if mode in ("main", "norevive") else mode
            out[mode] = {S: sum((lambda r: r["pnl"] if r["filled"] else 0)(SL.replay2(D, p, S, delays, fmode=fm)) for p in P) / 1e9 for S in SIZES}
        SL.CFG["resurrect"] = True
        res[run] = out
        print(run, " | ".join(f"{m}: " + " ".join(f"{S / 1e9:.2f} {v:+.3f}" for S, v in o.items()) + f" (0.50-0.35 {o[500_000_000] - o[350_000_000]:+.3f})" for m, o in out.items()), flush=True)
    # (2) our failed tries at smaller sizes
    X = D.live
    for run in runs:
        R = X[run]
        filled_w = {(seg, w) for (seg, w), W in R["ps"].items() if W["fills"]}
        cnt = collections.Counter(); per_win = collections.defaultdict(set)
        ours_fail = {}
        for (seg, w), W in R["ps"].items():
            pass
        # map our failed txs on chain: sig -> (slot, idx, err)
        for (seg, w), W in R["ps"].items():
            mint = W["arm"]["trig"]["mint"]
            for x in D.tape.get(mint, {}).get("fails", []):
                if x[4] == SL.AMS: ours_fail[x[2]] = (x[0], x[1], SL.code_of(x[3]), mint)
        for sig, a in R["att"].items():
            f = ours_fail.get(sig)
            if f is None or f[2] != 6042: continue
            s, i, c, mint = f
            key = (a["seg"], a["w"]) if "w" in a else None
            st = D.state_before(mint, (s, i))
            if st is None: continue
            # fee rate at signing: the trade the engine had last seen (att pos)
            ps_ = a.get("pos")
            tsig = next((t for t in D.tape[mint]["trades"] if ps_ and (t["s"], t["i"], t["j"]) == tuple(ps_)), None)
            fr = core.fee_rate_ps(tsig["fbps"], tsig["cbps"]) if tsig is not None else core.fee_rate_ps(95, 30)
            fb, cb = st["fbps"], st["cbps"]
            cnt["tries"] += 1
            for S in SIZES:
                n = PM.net_of_budget(S, fb, cb); q = st["vtok"] * (n - 1) // (st["vsol"] + n - 1)
                mo = core.limit_min_out(a["vsol"], a["vtok"], S, fr, 0.12)
                if mo is not None and q >= mo:
                    cnt[f"pass_{S // 10_000_000}"] += 1
                    if key is not None: per_win[S].add(key)
        live_size = R["segs"][0]["ps_spend"]
        new = {S // 10_000_000: len([k for k in per_win[S] if k not in filled_w]) for S in SIZES}
        earlier = {S // 10_000_000: len([k for k in per_win[S] if k in filled_w]) for S in SIZES}
        print(f"  {run} (live {live_size / 1e9:.2f}) our failed 6042 tries checked {cnt['tries']}: pass at " + ", ".join(f"{S / 1e9:.2f}: {cnt[f'pass_{S // 10_000_000}']}" for S in SIZES)
              + f" | windows never filled live that would fill: {new} | filled windows with an earlier passing try: {earlier}", flush=True)
        res[run + "_tries"] = dict(cnt=dict(cnt), new=new, earlier=earlier)
json.dump(res, open(f"{OUT}/sens.json", "w"), default=float, indent=1)
