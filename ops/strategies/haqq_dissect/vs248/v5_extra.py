#!/usr/bin/env python3
"""vs248 step 5 (read-only, exact-curve replays on MEASURED tape rows; results INFERRED):
 (a) FOLLOWER EFFECT: on the same-dump pairs, how much of OUR P&L is bot 248's own buy? Our tokens re-valued with 248's buy row
     (and its sell rows) removed from the tape; everything else as it happened.
 (b) CAUSAL 'stay while 248 holds' exit for our fills: at our normal exit decision, if a 248 buy has landed on the mint since our fill
     (visible on the feed: CU-price code 248) and 248 has not sold yet, hold and sell when 248's sell lands (+59 ms, after its row).
     Fills without a 248 buy in that window keep their real exit (no change). Followers x1.0 / x0.9 (outside buy SOL after our entry).
Out: vs248/v5.txt, v5.pkl"""
import pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_vs248"
DAYS = (2, 3, 4, 5)


class M:
    def __init__(s, S, CC, a, e):
        X = S[a:e]
        s.bu = X["buy"].astype(bool); s.so = X["sol"].astype(np.float64) / 1e9; s.tk = X["tok"].astype(np.float64)
        s.vs = X["vsol"].astype(np.float64) / 1e9; s.vt = X["vtok"].astype(np.float64); s.cc = CC[a:e]; s.n = e - a


def sim(m, ek, tok, fee, plan, removed, fol=1.0, own=frozenset()):
    V = m.vs[ek]; T = m.vt[ek]; K = V * T; hold = tok; got = 0.0; k = ek + 1
    for pos, fr in sorted(plan):
        while k <= pos and k < m.n:
            if k not in removed:
                if m.bu[k]: V += m.so[k] * (1.0 if k in own else fol); T = K / V
                else: T += m.tk[k]; V = K / T
            k += 1
        t = fr * hold; got += (V - K / (T + t)) * (1 - fee); T += t; V = K / T
    return got


def boot_mean(v, n=2000, seed=1):
    v = np.asarray(v, float)
    if len(v) < 2: return (float("nan"), float("nan"))
    r = np.random.default_rng(seed); s = v[r.integers(0, len(v), (n, len(v)))].mean(1)
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


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
    hbym = collections.defaultdict(list)
    for h in H: hbym[h["mint"]].append(h)
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    # (a) follower effect on pairs
    rowsA = []
    for x in O:
        if x["bucket"] != "H2H": continue
        m = mint(x["mi"]); rm = set(s[1] for s in x["sells"]); plan = [(s[1] - 1, s[3]) for s in x["sells"]]
        base = sim(m, x["k"], x["tok"], x["fee"], plan, rm)
        rm2 = set(rm)
        for h in x["pair"]:
            rm2.add(h["k"]); rm2 |= set(s[1] for s in h["sells"])
        wo = sim(m, x["k"], x["tok"], x["fee"], plan, rm2)
        after = any(h["k"] > x["k"] for h in x["pair"])
        rowsA.append(dict(day=x["day"], path=x["path"], base=base - x["cost"] - x["txc"], wo=wo - x["cost"] - x["txc"], after=after))
    P("# (a) Follower effect: our same-dump fills re-valued with bot 248's own buy+sell removed (exact replay; INFERRED)")
    for p in ("ps", "reg", "other", "ALL"):
        v = [r for r in rowsA if p == "ALL" or r["path"] == p]
        d = [1e3 * (r["base"] - r["wo"]) for r in v]; b = boot_mean(d)
        P(f"- {p}: {len(v)} fills; actual {1e3 * np.mean([r['base'] for r in v]):+.1f} mSOL/fill, without 248's rows {1e3 * np.mean([r['wo'] for r in v]):+.1f}; "
          f"248's own buy is worth {np.mean(d):+.1f} [{b[0]:+.1f}..{b[1]:+.1f}] mSOL/fill to us (248 after us on {100 * np.mean([r['after'] for r in v]):.0f}%)")
    # (b) causal 'stay while 248 holds'
    P("\n# (b) Causal exit add-on: if a bot-248 buy landed since our fill and 248 still holds at our exit decision, sell when 248's sell lands (+59 ms)")
    P("# decision = our real exit decision ~ our sell row minus our measured sell delay (we use the real sell row: the 248 buy must be BEFORE it); INFERRED")
    res = collections.defaultdict(lambda: collections.defaultdict(float)); cnt = collections.Counter(); trig = []
    for x in O:
        if x["day"] not in DAYS: continue
        m = mint(x["mi"]); rm = set(s[1] for s in x["sells"]); plan = [(s[1] - 1, s[3]) for s in x["sells"]]
        q_sell = x["sells"][0][1]
        hs = [h for h in hbym.get(x["mint"], []) if x["k"] < h["k"] < q_sell and h["cc"] < x["sells"][0][2] - 59.0 and h["sells"] and h["sells"][-1][1] > q_sell]
        cnt[(x["path"], "fills")] += 1
        for fol in (1.0, 0.9):
            own = frozenset()
            base = sim(m, x["k"], x["tok"], x["fee"], plan, rm, fol)
            if hs:
                h = hs[0]
                t = h["sells"][-1][2] + 59.0
                q = int(np.searchsorted(m.cc, t, side="right")) - 1
                alt = sim(m, x["k"], x["tok"], x["fee"], [(max(q, h["sells"][-1][1]), 1.0)], rm, fol)
            else:
                alt = base
            res[(x["path"], fol, x["day"])]["base"] += base - x["cost"]; res[(x["path"], fol, x["day"])]["alt"] += alt - x["cost"]
            if hs and fol == 1.0: trig.append(1e3 * (alt - base)); cnt[(x["path"], "trig")] += 1
    for p in ("ps", "reg"):
        for fol in (1.0, 0.9):
            per = [res[(p, fol, d)]["alt"] - res[(p, fol, d)]["base"] for d in DAYS]
            P(f"- {p} fol x{fol}: triggers {cnt[(p, 'trig')]} of {cnt[(p, 'fills')]} fills; gain per day {np.mean(per):+.3f} SOL ({', '.join(f'{z:+.3f}' for z in per)}); days > 0 {sum(z > 0 for z in per)}/4")
    b = boot_mean(trig)
    P(f"- per triggered fill (fol 1.0): {np.mean(trig):+.1f} mSOL [{b[0]:+.1f}..{b[1]:+.1f}], n {len(trig)}")
    open(f"{OUT}/v5.txt", "w").write("\n".join(out) + "\n")
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
