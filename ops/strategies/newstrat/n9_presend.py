#!/usr/bin/env python3
"""NEWSTRAT PRE-SEND forms (owner follow-up 11-03).
Fill model (pre-send stream, like our engine): after ARM the engine keeps sending pre-signed buys, one every 26.5 ms (8 per slot),
each with min_out = our 0.55 SOL at the LIMIT price.  A buy fills only if, at its landing, our average price <= limit.
Our landing after the trade that pushes the price through the limit = a draw from the MEASURED pool 'first landed try after the
dump' (runs r40 + r42 presend_attempt_land, chain clock 'ms_after_d_a'; p10/25/50/75/90 ~ 2/9/24/71/211 ms).
If the price is back above the limit at that landing, we wait for the next crossing.  Every landed try that does not fill costs
5,120 lamports (count = window time / 26.5 ms up to the fill).  Variant 'slow' adds +30 ms to every landing.
Reactive comparison: same window and limit, we see the crossing trade and land +70 ms later (fills only if still <= limit), no try fees.
Ideas:
  RE  : 9pQQ / 8PgC re-entry pre-send.  ARM = their SELL on a mint where they have >= K closed round trips (K 1/2/3) + 30 ms;
        limit = price after their sell x m (m .98/.95/.92/.88); window W slots after their sell slot (W 10 / 25).
  CAP : 9pQQ's forced time-cap sell (predictable to the slot): ARM 2 slots before buy+cap if still open (cap 300 s before
        10-31 14:03 PKT, 600 s after); limit = price at arm x m (.99/.97/.95); window 6 slots.
Exits (from our fill): H200 = sell lands 200 ms after the fill (125 ms timer + landing), S2 / S6 = 2 / 6 slots,
  NB = their next buy + 70 ms (cap 25 slots).  f20 rows for H200 and S2.
usage: n9_presend.py WALLET RUN [RUN...]  -> OUT/n9_<wallet>_<run>.json"""
import sys, json, random
import numpy as np
import nlib as L

POOL = np.array(json.load(open(f"{L.OUT}/ps_land_pool.json")))
TRY = 212.0 / 8
FAILFEE = 5120
ARM = 30.0
CAP_CHANGE_BT = 1793437380   # 10-31 14:03 PKT = 09:03 UTC (unix)

def avg_ok(c, lim_p, size=L.SIZE):
    tok = L.buy_tok(c, size)
    return (size / (1 + L.FEE)) / tok <= lim_p

def presend_fill(M, arm, t_end, lim_p, rng, slow=0.0):
    """-> (fill_time or None, tries_landed_without_fill)"""
    a = int(M.idx(arm)); b = int(M.idx(t_end))
    # crossing candidates: rows whose post state makes avg price <= limit (incl. rows before arm: state already below at arm)
    c_at_arm = float(M.cbal(a))
    if avg_ok(c_at_arm, lim_p):
        tau = arm + rng.choice(POOL) * 0 + TRY * rng.random() + slow
        y = int(M.idx(tau))
        if avg_ok(float(M.cbal(y)), lim_p): return tau, int((tau - arm) / TRY)
    ok = avg_ok(M.CQ[a:b], lim_p) if b > a else np.zeros(0, bool)
    for j in (np.nonzero(ok)[0] + a)[:40]:
        tau = M.CC[j] + float(rng.choice(POOL)) + slow
        if tau > t_end + 212: break
        y = int(M.idx(tau))
        if avg_ok(float(M.cbal(y)), lim_p):
            return tau, int(max(tau - arm, 0) / TRY)
    return None, int(max(t_end - arm, 0) / TRY)

def reactive_fill(M, arm, t_end, lim_p, D=70.0):
    a = int(M.idx(arm)); b = int(M.idx(t_end))
    ok = avg_ok(M.CQ[a:b], lim_p) if b > a else np.zeros(0, bool)
    for j in (np.nonzero(ok)[0] + a)[:40]:
        tau = M.CC[j] + D
        if avg_ok(float(M.cbal(int(M.idx(tau)))), lim_p): return tau
    return None

def exits(M, tau, bcc):
    j = np.searchsorted(bcc, tau, side="right")
    nb = bcc[j] + 70 if j < len(bcc) and bcc[j] <= tau + 25 * L.SMS else tau + 25 * L.SMS
    return {"H200": tau + 200, "S2": tau + 2 * L.SMS, "S6": tau + 6 * L.SMS, "NB": nb}

def main(wname, run):
    w = {"9pQQ": L.W9, "8PgC": L.W8}[wname]
    t = L.load(run); uid = t.uix[w]
    trips = [x for x in json.load(open(f"{L.OUT}/trips_{run}.json"))[wname] if not x["may"]]
    by = {}
    for x in trips: by.setdefault(x["mint"], []).append(x)
    rng = random.Random(7)
    R = {}
    def add(key, v):
        R.setdefault(key, []).append(v)
    for m, xs in by.items():
        xs.sort(key=lambda x: x["cc0"])
        M = L.Mint(t, t.mix[m])
        own = M.U == uid
        bcc = M.CC[own & (M.TK > 0)]
        busy_until = -1.0
        # ---- RE windows
        for k, x in enumerate(xs):
            if x.get("x") is None: continue
            p_s = L.price(float(x["cq1"]))
            for K in (1, 2, 3):
                if k + 1 < K: continue
                for W in (10, 25):
                    t_end = (x["s1"] + W + 1) * L.SMS
                    arm = x["cc1"] + ARM
                    for mlt in (0.98, 0.95, 0.92, 0.88):
                        lim = p_s * mlt
                        base = (f"RE_K{K}_W{W}_m{mlt}",)
                        for mode, slow in (("ps", 0.0), ("ps_slow", 30.0)):
                            if K != 1 and mode == "ps_slow": continue
                            tau, ntry = presend_fill(M, arm, t_end, lim, rng, slow)
                            fee = ntry * FAILFEE
                            if tau is None:
                                for ex in ("H200", "S2", "S6", "NB"): add(base + (mode, ex), (0, -fee, -fee))
                                continue
                            for ex, to in exits(M, tau, bcc).items():
                                v = L.trip(M, [tau], [to])[0] - fee
                                vf = (L.trip(M, [tau], [to], fol=L.FOLSHARE)[0] - fee) if ex in ("H200", "S2") else v
                                add(base + (mode, ex), (1, v, vf))
                        if K == 1:
                            tau = reactive_fill(M, arm, t_end, lim)
                            for ex in ("H200", "S2", "S6", "NB"):
                                if tau is None: add(base + ("react70", ex), (0, 0.0, 0.0)); continue
                                to = exits(M, tau, bcc)[ex]
                                add(base + ("react70", ex), (1, L.trip(M, [tau], [to])[0], L.trip(M, [tau], [to], fol=L.FOLSHARE)[0]))
        # ---- CAP windows (9pQQ only)
        if wname == "9pQQ":
            for x in xs:
                bt0 = int(t.bt[x["b"]]) if x.get("b") is not None else 0
                cap = 600_000.0 if bt0 >= CAP_CHANGE_BT else 300_000.0
                arm = x["cc0"] + cap - 2 * L.SMS
                if x.get("x") is not None and x["cc1"] <= arm: continue      # sold before: no window (known at arm time)
                t_end = arm + 6 * L.SMS
                e = int(M.idx(arm)); p_a = L.price(float(M.cbal(e)))
                for mlt in (0.99, 0.97, 0.95):
                    tau, ntry = presend_fill(M, arm, t_end, p_a * mlt, rng)
                    fee = ntry * FAILFEE
                    for ex in ("H200", "S2", "S6"):
                        if tau is None: add((f"CAP_m{mlt}", "ps", ex), (0, -fee, -fee)); continue
                        to = exits(M, tau, bcc)[ex]
                        v = L.trip(M, [tau], [to])[0] - fee
                        add((f"CAP_m{mlt}", "ps", ex), (1, v, (L.trip(M, [tau], [to], fol=L.FOLSHARE)[0] - fee) if ex != "S6" else v))
    hrs = L.hours(t)
    out = {"run": run, "hours": hrs, "rows": []}
    for key, vals in sorted(R.items()):
        a = np.array(vals, dtype=np.float64)
        fills = a[a[:, 0] == 1, 1]
        s = L.stats(a[:, 1])        # all windows incl. fee-only ones
        sf = L.stats(fills)
        out["rows"].append(dict(idea=key[0], mode=key[1], exit=key[2], windows=len(a), fills=int(a[:, 0].sum()),
                                per_day=round(s["net"] / hrs * 24, 2), mSOL_fill=sf["per"], win_fill=sf["win"],
                                wo5_day=round(s["wo5"] / hrs * 24, 2), f20_day=round(float(a[:, 2].sum()) / 1e9 / hrs * 24, 2),
                                fee_day=round(float(-a[a[:, 0] == 0, 1].sum()) / 1e9 / hrs * 24, 2)))
    json.dump(out, open(f"{L.OUT}/n9_{wname}_{run}.json", "w"))
    print(run, wname, "done", flush=True)

if __name__ == "__main__":
    for r in sys.argv[2:]: main(sys.argv[1], r)
