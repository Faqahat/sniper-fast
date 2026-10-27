#!/usr/bin/env python3
"""SIZE study task 2 (MEASURED + one INFERRED column): other wallets' buys that FAILED on chain with a slippage error (6042 below
min tokens out / 6002 too much SOL) strictly between our pre-send buy and our sell, every live fill of AMS r24-r28.
Per failed buy: its decoded limit (getTransaction), how far it missed on the live state (MEASURED: the chain state at its
position), and whether it would pass if our buy had been smaller (INFERRED: the same chain sequence with our buy at 0.35 / 0.25,
every other trade replayed with its own limit, no revivals = only our size changes).
Writes /home/moiz/sniper-data/presend_size/fails.json"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/size")
import numpy as np
import core
import sizelib as SL

OUT = "/home/moiz/sniper-data/presend_size"
GROUPS = [("A", "/home/moiz/sniper-data/replay065", ("r24", "r25"), [f"{OUT}/args_2425.jsonl"]),
          ("B", "/home/moiz/sniper-data/presend_size", ("r26", "r27", "r28"), [])]
TEST = [250_000_000, 350_000_000, 500_000_000]


def miss(v, t, r, fb, cb):
    """how far the failed buy missed on state (v, t), % (> 0 = failed): quote: min tokens / tokens out - 1; tok: cost / max SOL - 1"""
    ok, n, q = SL.try_buy(v, t, r, fb, cb)
    if r["bkind"] == "quote":
        return (r["a2"] / q - 1) * 100 if q > 0 else None, n
    return ((n + SL.PM.fees(n, fb, cb)) / r["a2"] - 1) * 100 if n else None, n


def state_before(W, k):
    v, t = W["v_after"], W["t_after"]
    for kk, vv, tt, ap in W["states"]:
        if kk >= k: break
        v, t = vv, tt
    return v, t


if __name__ == "__main__":
    rows_out = []
    for name, base, runs, extra in GROUPS:
        core.BASE = base
        D = core.Data()
        for fn in extra:
            for l in open(fn):
                r = json.loads(l)
                if r.get("kind") == "ok" or r["sig"] not in D.args: D.args[r["sig"]] = r
        SL.install()
        import positions as PO
        PS = [p for p in PO.presend_positions(D) if p.run in runs]
        SL.CFG["resurrect"] = False
        for p in PS:
            ob = p.ours_buy; fb, cb = ob["fbps"], ob["cbps"]
            fbr = [k for k, r in enumerate(p.rows) if r["kind"] == "fail_buy" and (r["s"], r["i"]) < p.sell_pos]
            if not fbr: continue
            live_buyers = {r["tr"]["user"] for r in p.rows if r["kind"] == "trade" and r["tr"]["buy"]} | {r["tr"]["signer"] for r in p.rows if r["kind"] == "trade" and r["tr"]["buy"]}
            WS = {S: SL.walk2(D, p.mint, p.pre, p.rows, S, fb, cb, (10 ** 15, 0, 0)) for S in TEST + [p.spend]}
            # live chain state before each row (MEASURED)
            v, t = ob["vsol"], ob["vtok"]; lfb, lcb = fb, cb
            for k, r in enumerate(p.rows):
                if r["kind"] == "trade":
                    v, t = r["tr"]["vsol"], r["tr"]["vtok"]; lfb, lcb = r["tr"]["fbps"], r["tr"]["cbps"]; continue
                if k not in fbr: continue
                m_live, sol = miss(v, t, r, lfb, lcb)
                o = dict(run=p.run, mint=p.mint, t=p.t, size=p.spend, sig=r["sig"], user=r["user"], code=r["code"], bkind=r["bkind"], src=r["src"], disc=r["disc"],
                         a1=r["a1"], a2=r["a2"], sol=sol / 1e9 if sol else None, slot_off=r["s"] - p.buy_pos[0], miss_live=m_live,
                         dup=r["user"] in live_buyers, flat_live=not any(rr["kind"] == "trade" and (rr["s"], rr["i"]) < p.sell_pos for rr in p.rows))
                for S in TEST:
                    vs, ts = state_before(WS[S], k)
                    ok, _, _ = SL.try_buy(vs, ts, r, lfb, lcb)
                    o[f"pass_{S // 10_000_000}"] = bool(ok)
                    o[f"miss_{S // 10_000_000}"] = miss(vs, ts, r, lfb, lcb)[0]
                rows_out.append(o)
        print(name, "done", len(rows_out), flush=True)
    json.dump(rows_out, open(f"{OUT}/fails.json", "w"))
    # summary per run
    fills = {"r24": 200, "r25": 95, "r26": 143, "r27": 49, "r28": 150}
    for run in ("r24", "r25", "r26", "r27", "r28"):
        X = [o for o in rows_out if o["run"] == run]
        nd = [o for o in X if not o["dup"]]
        holds = len({(o["mint"], o["t"]) for o in X}); holds_nd = len({(o["mint"], o["t"]) for o in nd})
        mm = np.array([o["miss_live"] for o in nd if o["miss_live"] is not None])
        print(f"{run} size {X[0]['size'] / 1e9:.2f}: failed slippage buys in holds {len(X)} ({len(X) / fills[run]:.2f}/fill) in {holds} of {fills[run]} holds; "
              f"not dup {len(nd)} in {holds_nd} holds, {sum(o['sol'] or 0 for o in nd):.1f} SOL; miss p25/50/75 {np.percentile(mm, [25, 50, 75]).round(2) if len(mm) else None}% | "
              f"would pass at 0.25: {sum(o['pass_25'] for o in nd)} ({sum(o['sol'] or 0 for o in nd if o['pass_25']):.2f} SOL), 0.35: {sum(o['pass_35'] for o in nd)} "
              f"({sum(o['sol'] or 0 for o in nd if o['pass_35']):.2f} SOL), 0.50: {sum(o['pass_50'] for o in nd)}; in flat holds {sum(1 for o in nd if o['flat_live'])} "
              f"(pass at 0.35: {sum(1 for o in nd if o['flat_live'] and o['pass_35'])}); codes {dict(collections.Counter(o['code'] for o in X))}; kinds {dict(collections.Counter((o['bkind'], o['src']) for o in nd))}")
