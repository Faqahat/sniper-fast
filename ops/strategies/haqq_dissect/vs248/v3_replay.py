#!/usr/bin/env python3
"""vs248 step 3 (read-only): exact-curve replays on the SAME dumps (S_FILL pairs) and on all our fills.

Exact semantics (dv8sim.pnl_exact; validated +0.02 mSOL/fill on our live fills): later outside buys keep their SOL in, later sells keep
their TOKENS in; the holder's own sell rows of the lot are removed; everyone else stays (248 is outside flow for us and vice versa).
A sell 'at time of row q' is valued twice - just before row q and just after it - and the mean is used (who of two simultaneous sellers
goes first is a coin flip). Our own position at a row the holder actually sold at: identical either way.

Per pair (exactly one our lot and one 248 lot on the same dump row) the chain, every step an exact replay (tx costs MEASURED):
  A   our measured net (tape)                       R1 = A - A' (replay residual, ours)
  A'  replay: our entry, our size, our sells
  S1  our entry, 248's size (its SOL in), our sells            d_size  = S1 - A'
  S2  our entry, 248's size, 248's sell times/fractions        d_exit  = S2 - S1
  S3  248's entry (its actual tape position), 248's sells      d_entry = S3 - S2
  S4  S3 with 248's tx costs instead of ours                   d_cost  = S4 - S3
  Hh  248's measured net (tape)                     R2 = Hh - S4 (replay residual, 248)
  => Hh - A = R1 + d_size + d_exit + d_entry + d_cost + R2 exactly.
Also: our tokens at 248's sell time (our size) and 248's tokens at our sell time; all our fills at 0.30 SOL and with a 4.2 s timer.
Out: vs248/v3.pkl"""
import pickle, sys, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_vs248"


class M:
    def __init__(s, S, CC, a, e):
        X = S[a:e]; s.a = a
        s.bu = X["buy"].astype(bool); s.so = X["sol"].astype(np.float64) / 1e9; s.tk = X["tok"].astype(np.float64)
        s.vs = X["vsol"].astype(np.float64) / 1e9; s.vt = X["vtok"].astype(np.float64); s.cc = CC[a:e]; s.n = e - a


def sim(m, ek, size, tok, fee, plan, removed):
    """value (SOL out after pump fee) of a position entered at local row ek. size None -> actual post-entry state + tok; else a fresh
    buy of `size` SOL (incl. fee) inserted at row ek's place (pre-state = post-state of row ek-1). plan [(pos, frac)]: sell frac of the
    position after processing every non-removed row with local index <= pos (pos < ek -> right after entry)."""
    if size is None:
        V = m.vs[ek]; T = m.vt[ek]; K = V * T; hold = tok
    else:
        V0 = m.vs[ek - 1] if ek > 0 else 30.0; T0 = m.vt[ek - 1] if ek > 0 else 1.073e15; K = V0 * T0
        V = V0 + size / (1 + fee); T = K / V; hold = T0 - T
    got = 0.0; k = ek + 1
    for pos, fr in sorted(plan):
        while k <= pos and k < m.n:
            if k not in removed:
                if m.bu[k]: V += m.so[k]; T = K / V
                else: T += m.tk[k]; V = K / T
            k += 1
        t = fr * hold
        got += (V - K / (T + t)) * (1 - fee); T += t; V = K / T
    return got


def plans(m, sells):
    """own sells [(grow, k, cc, frac, ...)] -> (before-plan, after-plan) as seen by ANOTHER holder"""
    return [(s[1] - 1, s[3]) for s in sells], [(s[1], s[3]) for s in sells]


def tplan(m, ek, t_ms):
    """sell everything at chain time t (after every row with cc <= t)"""
    q = int(np.searchsorted(m.cc, t_ms, side="right")) - 1
    return [(max(q, ek), 1.0)]


def main():
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/v2.pkl", "rb")); H, O = Z["H"], Z["O"]
    Z1 = pickle.load(open(f"{OUT}/v1.pkl", "rb"))
    span = {int(m): (int(a), int(e)) for m, a, e in zip(Z1["mints"], Z1["st"], Z1["en"])}
    S = np.load(f"{SCR}/tape_sub.npy", mmap_mode="r"); CC = np.load(f"{SCR}/tape_cc.npy", mmap_mode="r")
    cache = {}
    def mint(mi):
        if mi not in cache:
            if len(cache) > 400: cache.clear()
            a, e = span[mi]; cache[mi] = M(S, CC, a, e)
        return cache[mi]
    def frac_sum(sells): return sum(s[3] for s in sells)
    res = {}
    # ---- all our lots: validation + size 0.30 + 4.2 s timer + 1 s timer
    for x in O:
        if x["open"] or not x["sells"]: continue
        m = mint(x["mi"]); rm = set(s[1] for s in x["sells"]); own = [(s[1] - 1, s[3]) for s in x["sells"]]
        Ap = sim(m, x["k"], None, x["tok"], x["fee"], own, rm)
        s30 = sim(m, x["k"], 0.30 * (1 + x["fee"]), None, x["fee"], own, rm)
        r = dict(Ap=Ap - x["cost"] - x["txc"], A=x["net"], out_meas=x["out"], out_rep=Ap,
                 s30=s30 - 0.30 * (1 + x["fee"]) - x["txc"])
        for nm, ms in (("t1s", 1000), ("t2s", 2000), ("t42", 4200), ("t8s", 8000)):
            r[nm] = sim(m, x["k"], None, x["tok"], x["fee"], tplan(m, x["k"], x["cc"] + ms + 59), rm) - x["cost"] - x["txc"]
        res[("O", x["slot"], x["idx"])] = r
    print(f"our lots replayed {len(res)} ({time.time() - t0:.0f}s)", flush=True)
    # ---- pairs
    P = []
    for h in H:
        if h["bucket"] != "S_FILL": continue
        xs = h["pair"]
        for x in xs:
            if h["open"] or x["open"] or not h["sells"] or not x["sells"]: continue
            m = mint(h["mi"])
            rmo = set(s[1] for s in x["sells"]); rmh = set(s[1] for s in h["sells"])
            o_b, o_a = plans(m, x["sells"]); h_b, h_a = plans(m, h["sells"])
            own_o = o_b; own_h = h_b
            Ap = sim(m, x["k"], None, x["tok"], x["fee"], own_o, rmo)
            S1 = sim(m, x["k"], h["cost"], None, x["fee"], own_o, rmo)
            S2 = 0.5 * (sim(m, x["k"], h["cost"], None, x["fee"], h_b, rmo) + sim(m, x["k"], h["cost"], None, x["fee"], h_a, rmo))
            S3 = sim(m, h["k"], None, h["tok"], h["fee"], own_h, rmh)
            # cross values at actual sizes
            o_at_h = 0.5 * (sim(m, x["k"], None, x["tok"], x["fee"], h_b, rmo) + sim(m, x["k"], None, x["tok"], x["fee"], h_a, rmo))
            h_at_o = 0.5 * (sim(m, h["k"], None, h["tok"], h["fee"], o_b, rmh) + sim(m, h["k"], None, h["tok"], h["fee"], o_a, rmh))
            h_before_o = h["k"] < x["sells"][0][1]
            A = x["net"]; Hh = h["net"]
            r = dict(h=(h["slot"], h["idx"]), o=(x["slot"], x["idx"]), npair=len(xs), A=A, Ap=Ap - x["cost"] - x["txc"],
                     S1=S1 - h["cost"] - x["txc"], S2=S2 - h["cost"] - x["txc"], S3=S3 - h["cost"] - x["txc"], S4=S3 - h["cost"] - h["txc"], Hh=Hh,
                     o_at_h=o_at_h - x["cost"] - x["txc"], h_at_o=h_at_o - h["cost"] - h["txc"], h_rep=S3 - h["cost"] - h["txc"],
                     o_rep=Ap - x["cost"] - x["txc"], h_bought_before_our_sell=h_before_o, fr_o=frac_sum(x["sells"]), fr_h=frac_sum(h["sells"]))
            P.append(r)
    print(f"pairs {len(P)} ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(O=res, P=P), open(f"{OUT}/v3.pkl", "wb"))
    a = np.array([[r["A"], r["Ap"]] for r in res.values()])
    print("our lots: measured net", a[:, 0].sum().round(3), "replay", a[:, 1].sum().round(3), "mean abs diff mSOL", (1e3 * np.abs(a[:, 0] - a[:, 1])).mean().round(3))
    if P:
        for k in ("A", "Ap", "S1", "S2", "S3", "S4", "Hh", "o_at_h", "h_at_o"):
            print(k, round(sum(r[k] for r in P), 3))
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
