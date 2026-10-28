#!/usr/bin/env python3
"""VERIFY v4 (own code; MEASURED fills, INFERRED counterfactual): forward test of analyst C's WAVE exit on our LIVE fills of
FRA r26 (pre-send + regular) and FRA r27 (pre-send). Per live buy (matched on the tape by its signature hash):
  actual = curve value of exactly that buy's tokens at the state just before our real sell (minus the buy's SOL incl. pump fee);
  wave   = decision at the first t >= fill + G with no OUTSIDE buy in (t - G, t], cap fill + C; the sell lands at decision + 59 ms
           (chain clock); value of the same tokens at the state then:
           (A) 'capped': the recorded state, never past our real sell (the main session's method);
           (B) 'exact': our real sell removed, every other later trade re-applied by its amounts (buys by SOL, sells by tokens).
  G / C: pre-send 150 ms / 1 s; regular 300 ms / 2 s (and the other pair as a check).
Curve P&L only (tx costs excluded; both exits are one sell). Our realized wallet P&L from the run records is printed for reference.
usage: v4_wave_live.py"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V

DATA = "/home/moiz/sniper-data/haqq_dissect/verify"
RUNS = {"r26": "/home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl", "r27": f"{DATA}/live/dip_r27.jsonl"}
FRESH0 = 1793131823
LAND = 59.0


def val(tok, v, t, fr): return v * tok / (t + tok) * (1 - fr)


if __name__ == "__main__":
    kinds = {}; realized = collections.defaultdict(float); mints = set(); run_of = {}
    for rn, fn in RUNS.items():
        for r in V.load_runs([fn]):
            ev = r.get("ev")
            if ev == "presend_live_fill": kinds[V.sh(r["sig"])] = "presend"; mints.add(r["mint"]); run_of[V.sh(r["sig"])] = rn
            elif ev == "buy_land": kinds[V.sh(r["sig"])] = "regular"; mints.add(r["mint"]); run_of[V.sh(r["sig"])] = rn
            elif ev == "presend_live_realized": realized[(rn, "presend")] += r.get("pnl", 0) / 1e9
    tapes = {"dv8": V.Tape("/home/moiz/sniper-data/dv8/tab", mints), "fresh": V.Tape(f"{DATA}/tab", mints)}
    split = 462199500
    out = []
    for name, tp in tapes.items():
        for mint in mints:
            X = tp.rows(mint)
            if X is None: continue
            ours = np.isin(X["signer"], list(tp.our))
            cc = np.array([tp.cc(int(s), int(i)) for s, i in zip(X["slot"], X["idx"])])
            for p in np.flatnonzero(ours & (X["buy"] == 1)):
                h = int(X["sigh"][p]); kd = kinds.get(h)
                if kd is None: continue
                if (name == "dv8") != (int(X["slot"][p]) < split): continue
                later = np.flatnonzero((np.arange(len(X)) > p) & ours & (X["buy"] == 0))
                if not len(later): continue
                q = int(later[0])
                tok = float(X["tok"][p]); fr0 = V.fee_of(X[p])
                cost = float(X["sol"][p]) * (1 + fr0)
                # actual: state just before our real sell
                a = q - 1
                actual = val(tok, float(X["vsol"][a]), float(X["vtok"][a]), V.fee_of(X[a])) - cost
                t0 = cc[p]
                ob = cc[(np.arange(len(X)) > p) & (~ours) & (X["buy"] == 1)]
                res = dict(run=run_of[h], kind=kd, mint=mint, slot=int(X["slot"][p]), bt=tp.bt_of(int(X["slot"][p])), actual=actual / 1e9,
                           t_actual=cc[q] - t0)
                for G, C in ((150.0, 1000.0), (300.0, 2000.0), (200.0, 1000.0)):
                    td = t0 + G
                    while td < t0 + C:
                        hit = ob[(ob > td - G) & (ob <= td)]
                        if not len(hit): break
                        td = hit.max() + G
                    td = min(td, t0 + C); ts = td + LAND
                    # (A) capped at our real sell
                    j = int(np.searchsorted(cc, ts, side="right")) - 1
                    j = max(p, min(j, q - 1))
                    capped = val(tok, float(X["vsol"][j]), float(X["vtok"][j]), V.fee_of(X[j])) - cost
                    # (B) exact: from our buy's post state, re-apply other trades by amounts, our later txs removed
                    v = float(X["vsol"][p]); t = float(X["vtok"][p]); frs = fr0
                    for k in range(p + 1, len(X)):
                        if cc[k] > ts: break
                        if ours[k]: continue
                        if X["buy"][k]:
                            sol = float(X["sol"][k]); dt = t * sol / (v + sol); v += sol; t -= dt
                        else:
                            tk = float(X["tok"][k]); so = v * tk / (t + tk); v -= so; t += tk
                        frs = V.fee_of(X[k])
                    exact = val(tok, v, t, frs) - cost
                    res[f"cap_{int(G)}"] = capped / 1e9; res[f"ex_{int(G)}"] = exact / 1e9; res[f"td_{int(G)}"] = td - t0
                for Dm in (150.0, 200.0, 300.0):
                    ts = t0 + Dm + LAND
                    j = int(np.searchsorted(cc, ts, side="right")) - 1
                    j = max(p, min(j, q - 1))
                    res[f"fix_{int(Dm)}"] = (val(tok, float(X["vsol"][j]), float(X["vtok"][j]), V.fee_of(X[j])) - cost) / 1e9
                out.append(res)
    pickle.dump(out, open(f"{DATA}/v4_rows.pkl", "wb"))
    rng = np.random.default_rng(3)
    print(f"matched live fills: {len(out)} (" + ", ".join(f"{k}: {v}" for k, v in sorted(collections.Counter((r['run'], r['kind']) for r in out).items())) + ")")
    print("realized (run records, wallet, all costs) pre-send: " + ", ".join(f"{k[0]} {v:+.3f}" for k, v in realized.items()))

    def tab(sel, label, G):
        R = [r for r in out if sel(r)]
        if not R: return
        a = np.array([r["actual"] for r in R]); c = np.array([r[f"cap_{G}"] for r in R]); e = np.array([r[f"ex_{G}"] for r in R])
        bc = [(c - a)[ix].sum() for ix in (rng.integers(0, len(R), len(R)) for _ in range(4000))]
        be = [(e - a)[ix].sum() for ix in (rng.integers(0, len(R), len(R)) for _ in range(4000))]
        lc, hc = np.percentile(bc, [5, 95]); le, he = np.percentile(be, [5, 95])
        print(f"| {label} | {len(R)} | {a.sum():+.3f} | {c.sum():+.3f} | {c.sum() - a.sum():+.3f} [{lc:+.3f}, {hc:+.3f}] | {1e3 * (c - a).mean():+.2f} | "
              f"{e.sum():+.3f} | {e.sum() - a.sum():+.3f} [{le:+.3f}, {he:+.3f}] | {np.mean(c > a + 1e-6):.2f} / {np.mean(c < a - 1e-6):.2f} |")
    for G, title in ((150, "gap 150 ms / cap 1 s"), (300, "gap 300 ms / cap 2 s"), (200, "gap 200 ms / cap 1 s")):
        print(f"\n### Wave exit {title}: curve P&L SOL (tx costs excluded)")
        print("| Fills | n | Actual | Wave capped | Wave - actual [90%] | per fill mSOL | Wave exact (sell removed) | Exact - actual [90%] | share better / worse (capped) |")
        print("|---|---|---|---|---|---|---|---|---|")
        for rn in ("r26", "r27"):
            for kd in ("presend", "regular"):
                tab(lambda r, rn=rn, kd=kd: r["run"] == rn and r["kind"] == kd, f"{rn} {kd}", G)
        tab(lambda r: r["kind"] == "presend", "all pre-send", G)
        tab(lambda r: r["kind"] == "presend" and r["bt"] > FRESH0, "pre-send AFTER 01:10 PKT (fresh)", G)
        tab(lambda r: r["kind"] == "regular", "all regular", G)
    print("\n### Fixed timers (sell decided at fill + D ms, lands +59 ms; capped at our real sell): sum curve P&L SOL, minus actual [90%]")
    for sel, label in ((lambda r: r["kind"] == "presend", "all pre-send"), (lambda r: r["kind"] == "presend" and r["bt"] > FRESH0, "pre-send fresh"), (lambda r: r["kind"] == "regular", "regular")):
        RR = [r for r in out if sel(r)]; a = np.array([r["actual"] for r in RR])
        parts = []
        for k in ("fix_150", "fix_200", "fix_300", "cap_150"):
            c = np.array([r[k] for r in RR]); bs = [(c - a)[ix].sum() for ix in (rng.integers(0, len(RR), len(RR)) for _ in range(4000))]
            parts.append(f"{k} {c.sum() - a.sum():+.3f} [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]")
        d = np.sort(np.array([r["cap_150"] - r["actual"] for r in RR]))[::-1]
        print(f"| {label} | n {len(RR)} | " + " | ".join(parts) + f" | wave150 gain without its top 1 / top 3 fills: {d[1:].sum():+.3f} / {d[3:].sum():+.3f} |")
