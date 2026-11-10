#!/usr/bin/env python3
"""WHALEFLIP step 5: PAIRED try-level replay of every live T2 window that filled and has a chain tape (w4 coverage), with an on-chain
whale check in our buy, or an engine-only window stop. Method as the 10-30 GUARDS replay (custom37/c37lib), rebuilt on the raw tape:
  * curve = outside trades only (our txs removed), walked by deltas from the trigger's recorded post state (buys keep their SOL, sells
    their tokens); exact while none of our trades is inserted [MEASURED tape].
  * REAL tries keep their real landing (slot, idx) and min_out; a try fills iff it landed by its deadline and the curve before its
    landing gives >= min_out (pump 6042) AND the check passes at its landing. First filling try in chain order = our fill.
  * After the last real send, PHANTOM tries [INFERRED] keep the window going exactly as the engine would: one every 212/k ms (k 8),
    signed on the state seen then (block clock: tau = t_send - off_w, off_w = median(first_rx - cc(landing)) of the window's landed
    tries) at the window's own drop (median lim / p_sign of its real tries), landing L ms later (L drawn from the run's real
    send->first_rx pool, the unseen share kept), deadline = send slot + 1. The window ends at trigger slot + 10 (sends), 30 ms after
    the whale's first sell (block clock), or the QUIET stop N:M (fewer than M trades by others by trigger slot + N).
  * Exit: the live fill keeps its REAL realized P&L; a different fill: sell lands H ms (block clock) after the fill (H = this window's
    live hold if its exit was the timer, else the run's median), or earlier on a +-20% move seen within 200 ms; P&L = sell SOL x
    (1 - 1.25%) - spend - the run's median fixed costs (live realized - curve P&L, MEASURED) [INFERRED].
  * Fees: every landed try that does not fill costs 5,120 lamports (a blocked fill becomes one).
Variants: none | A<X>: whale balance at landing <= X x its trigger balance, closed account = 0 = pass (custom program or two
Lighthouse variants) | N<X>: same but a CLOSED account fails the check (one Lighthouse AssertTokenAccount) | S<Y>: engine-only, no
on-chain check: stop sending once the feed shows a sell by another wallet of >= Y % of supply while the whale has not sold (Y 0 = any).
Out: whaleflip/replay.json (per window x variant, mean over reps) usage: w5_replay.py REPS"""
import sys, zlib, json, math, bisect, random, collections, statistics
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W, wtape as T

FR = 0.012500000186264515
FAIL = 5120
SMS = 212.0
VARS = ["none", "C", "A0", "A0.05", "A0.25", "A0.5", "A0.75", "N0.05", "N0.5", "S0", "S1", "S3"]
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
KC = T.K


def limit_min_out(V, Tk, spend, drop):
    k = V * Tk; vl = V * math.sqrt(1.0 - drop); tl = k / vl; x = spend / (1.0 + FR)
    return math.floor(tl * x / (vl + x))


def buy_tok(V, Tk, spend):
    x = int(spend / (1.0 + FR)); return int(Tk * x // (V + x))


def key(s, i): return s * 100000 + i


class Win:
    pass


def prep(f, tp, maxi, pool_run):
    P = Win(); P.f = f
    rows = tp["rows"]; sigs = {x["sig"]: k for k, x in enumerate(rows)}
    tg = f["trig"]; P.whale = tg["wallet"]; P.bal0 = tg["bal"]; P.spend = f["spend"] or 696000000
    kt = sigs.get(tg["sig"])
    if kt is None: return None
    P.T0 = rows[kt]["vtok"]
    P.ts = tg["slot"]
    P.out = []                      # outside rows after the trigger: (key, cc, kind, amount, seller, whale_bal_after or None, whale_closed)
    wb = P.bal0
    for x in rows[kt + 1:]:
        if x["ours"]: continue
        if x["s"] > P.ts + 40: break
        dt = x["cpost"] - x["cpre"]
        if dt > 0: kind, amt = "s", dt
        elif dt < 0: kind, amt = "b", KC / (x["cpost"] + T.VOFF) - KC / (x["cpre"] + T.VOFF)
        else: kind, amt = "n", 0
        wh = None; cl = False
        if P.whale in x["own"]:
            wh = x["own"][P.whale][1]; cl = bool(x["cl"] and wh == 0 and x["seller"] == P.whale)
        P.out.append((key(x["s"], x["i"]), T.cc(maxi, x["s"], x["i"]), kind, amt, x["seller"], x["sold"], wh, cl))
    P.keys = [o[0] for o in P.out]
    # whale balance timeline
    P.wk, P.wb, P.wc = [], [], []
    for o in P.out:
        if o[6] is not None: P.wk.append(o[0]); P.wb.append(o[6]); P.wc.append(o[7])
    ws = next((o for o in P.out if o[4] == P.whale and o[5] > 0), None)
    P.whale_sell_cc = ws[1] if ws else None
    P.whale_sell_key = ws[0] if ws else None
    # tries
    P.tries = []; offs = []; drops = []
    for t in f["tries"]:
        L = t.get("land") or {}
        land = (L["slot"], L["idx"]) if L.get("idx") is not None and L.get("res") not in (None, "unseen") else None
        P.tries.append({"sig": t["sig"], "t": t["t"] / 1e6, "slot": t["slot"], "dl": t["deadline"], "min_out": t["min_out"], "land": land, "real": True,
                        "pos": t.get("pos")})
        if land and L.get("first_rx") and land[0] in maxi: offs.append(L["first_rx"] / 1e6 - T.cc(maxi, *land))
        if t.get("vsol") and t.get("vtok") and t.get("lim"): drops.append(1 - t["lim"] / (t["vsol"] / t["vtok"]))
    if not offs: return None
    P.off = statistics.median(offs)
    P.drop = statistics.median(drops) if drops else 0.12
    P.last_send = max(x["t"] for x in P.tries) - P.off
    q = (f.get("quiet") or {}).get("stop") or "5:2"
    try: P.qn, P.qm = (int(z) for z in q.split(":"))
    except Exception: P.qn, P.qm = 5, 2
    fl = f["fills"][0]; P.fill_sig = fl["sig"]
    cl = f.get("close") or {}
    sl = cl.get("sell_land")
    P.H = (T.cc(maxi, sl[0], sl[1]) - T.cc(maxi, fl["slot"], fl["idx"])) if (sl and cl.get("exit_why") == "time-ms" and sl[0] in maxi and fl["slot"] in maxi) else None
    P.maxi = maxi
    return P


def state_before(P, K, ours=None):
    """vtok before chain key K (outside trades only; our buy (key, tokens) inserted if given)"""
    Tk = P.T0; done = ours is None
    for o in P.out:
        if o[0] >= K: break
        if not done and ours[0] < o[0]:
            V = KC / Tk; Tk = KC / (V + ours[2]); done = True
        if o[2] == "b": Tk = KC / (KC / Tk + o[3])
        elif o[2] == "s": Tk = Tk + o[3]
    if not done and ours[0] < K:
        V = KC / Tk; Tk = KC / (V + ours[2])
    return KC / Tk, Tk


def whale_at(P, K):
    k = bisect.bisect_left(P.wk, K)
    if k == 0: return P.bal0, False
    return P.wb[k - 1], P.wc[k - 1]


def check(P, var, K):
    if var in ("none", "C") or var[0] == "S": return True
    X = float(var[1:]); b, closed = whale_at(P, K)
    if closed: return var[0] == "A"
    return b <= X * P.bal0 + 0.5


def y_to_key(P, y):
    s = int(y // SMS); fr = (y - s * SMS) / SMS
    mx = P.maxi.get(s, 400)
    return key(s, int(fr * (mx + 1))), s


def stop_time(P, var):
    """block-clock time when sends stop (window rules + the S variant)"""
    E = (P.ts + 10 + 1) * SMS
    if P.whale_sell_cc is not None: E = min(E, P.whale_sell_cc + 30)
    others = 0; qcut = (P.ts + P.qn) * SMS
    for o in P.out:
        if o[1] >= qcut: break
        if o[4] != P.whale and o[2] != "n": others += 1
    if others < P.qm: E = min(E, qcut)
    if var[0] == "S":
        Y = float(var[1:]) / 100 * 1e15
        for o in P.out:
            if P.whale_sell_key is not None and o[0] >= P.whale_sell_key: break
            if o[2] == "s" and o[4] != P.whale and o[5] >= max(Y, 1):
                E = min(E, o[1]); break
    return E


def exit_pnl(P, yk, ycc, tok, Hmed, fixed):
    H = P.H if P.H is not None else Hmed
    sell_cc = ycc + H
    cost = P.spend
    for o in P.out:                    # TP / SL seen within 200 ms
        if o[0] <= yk: continue
        if o[1] > ycc + 200: break
        V, Tk = state_before(P, o[0] + 1, (yk, tok, int(P.spend / (1 + FR))))
        val = V * tok / (Tk + tok) * (1 - FR)
        if val >= cost * 1.2 or val <= cost * 0.8: sell_cc = o[1] + max(H - 200, 20); break
    sk, _ = y_to_key(P, sell_cc)
    V, Tk = state_before(P, sk, (yk, tok, int(P.spend / (1 + FR))))
    return V * tok / (Tk + tok) * (1 - FR) - P.spend + fixed     # fixed = live realized - curve P&L (negative)


def sim(P, var, rng, pool, unseen, Hmed, fixed):
    """-> dict(filled, pnl lamports-as-SOL, src, fails) ; pnl includes the fees of landed non-filling tries of THIS replay"""
    E = stop_time(P, var)
    tries = []
    for t in P.tries:
        tau = t["t"] - P.off
        if tau > E and var[0] == "S": continue          # the engine-only stop removes later sends
        tries.append(t)
    # phantoms after the last real send
    if var not in ("none", "C") and var[0] != "S":
        tau = P.last_send + SMS / 8
        while tau < E:
            K_seen, _ = y_to_key(P, tau)
            V, Tk = state_before(P, K_seen)
            mo = limit_min_out(V, Tk, P.spend, P.drop)
            if rng.random() < unseen: land = None
            else:
                y = tau + rng.choice(pool)
                lk, ls = y_to_key(P, y)
                land = (lk // 100000, lk % 100000)
            tries.append({"sig": None, "t": tau + P.off, "slot": int(tau // SMS), "dl": int(tau // SMS) + 1, "min_out": mo, "land": land, "real": False})
            tau += SMS / 8
    landed = sorted([t for t in tries if t["land"]], key=lambda t: key(*t["land"]))
    fill = None
    for t in landed:
        ls, li = t["land"]; K = key(ls, li)
        if ls > t["dl"]: continue
        V, Tk = state_before(P, K)
        tok = buy_tok(V, Tk, P.spend)
        if tok >= t["min_out"] and check(P, var, K):
            fill = (t, K, tok); break
    if fill is None:
        return {"filled": False, "pnl": 0.0, "src": None, "fails": len(landed), "fill_cc": None}
    t, K, tok = fill
    ycc = T.cc(P.maxi, *t["land"])
    if t["sig"] == P.fill_sig and var != "C": pnl = P.f["pnl"] * 1e9; src = "live"
    else: pnl = exit_pnl(P, K, ycc, tok, Hmed, fixed); src = "real" if t["real"] else "phantom"
    # fees: every other landed try; phantoms sent after our fill is seen were never sent (the engine stops at a fill)
    fails = sum(1 for x in landed if x is not t and (x["real"] or x["t"] - P.off <= ycc))
    return {"filled": True, "pnl": pnl, "src": src, "fails": fails, "fill_cc": ycc}


if __name__ == "__main__":
    import pickle
    F = [f for f in W.load() if f["kind"] == "t2"]
    TP = T.build(); tapes = TP["tapes"]; maxi = TP["maxi"]
    pools = {}
    for r in range(39, 49):
        d = pickle.load(open(f"{W.D}/fills_r{r}.pkl", "rb"))
        ms = [p[1] for p in d["pool"] if p[0] not in ("unseen",) and p[1] is not None and 0 < p[1] < 2000]
        un = sum(1 for p in d["pool"] if p[0] == "unseen") / max(1, len(d["pool"]))
        pools[r] = (ms, un)
    # run medians: hold H (block ms) and fixed costs
    Hs = collections.defaultdict(list); fx = collections.defaultdict(list)
    PW = []
    for f in F:
        tp = tapes.get(f["mint"])
        if tp is None: continue
        P = prep(f, tp, maxi, pools[f["run"]])
        if P is None: continue
        if P.H is not None: Hs[f["run"]].append(P.H)
        cl = f.get("close") or {}
        so = sum(x[3] for x in (cl.get("sell_lands") or []) if x and len(x) > 3)
        if so and cl.get("rounds") == 1 and len(f["fills"]) == 1:
            fx[f["run"]].append(f["pnl"] * 1e9 - (so * (1 - FR) - (cl.get("spend") or P.spend)))
        PW.append(P)
    Hmed = {r: statistics.median(v) for r, v in Hs.items()}
    FX = {r: statistics.median(v) for r, v in fx.items()}
    print("windows replayed", len(PW), "| H median ms", {r: round(v) for r, v in Hmed.items()}, "| fixed mSOL", {r: round(v / 1e6, 2) for r, v in FX.items()}, flush=True)
    res = []
    for n, P in enumerate(PW):
        r = P.f["run"]
        row = {"run": r, "ses": P.f["ses"], "w": P.f["w"], "seg": P.f["seg"], "period": P.f["period"], "pnl_live": P.f["pnl"], "v": {}}
        for var in VARS:
            acc = collections.defaultdict(float); srcs = collections.Counter()
            reps = 1 if var in ("none", "C") or var[0] == "S" else REPS
            for rep in range(reps):
                rng = random.Random(zlib.crc32(f"{r}|{P.f['ses']}|{P.f['w']}|{var}|{rep}".encode()))
                o = sim(P, var, rng, pools[r][0], pools[r][1], Hmed.get(r, 420), FX.get(r, -3.5e6))
                acc["pnl"] += (o["pnl"] - FAIL * o["fails"]) / 1e9 / reps; acc["fill_pnl"] += o["pnl"] / 1e9 / reps; acc["fails"] += o["fails"] / reps; acc["filled"] += o["filled"] / reps
                srcs[o["src"]] += 1
            row["v"][var] = {"pnl": round(acc["pnl"], 6), "fill_pnl": round(acc["fill_pnl"], 6), "fails": round(acc["fails"], 2), "filled": round(acc["filled"], 3), "src": dict(srcs)}
        res.append(row)
        if n % 200 == 0: print(n, len(PW), flush=True)
    json.dump({"rows": res, "Hmed": Hmed, "FX": FX, "reps": REPS}, open(f"{W.D}/replay.json", "w"))
    print("done", len(res))
