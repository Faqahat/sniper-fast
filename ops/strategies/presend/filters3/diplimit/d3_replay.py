#!/usr/bin/env python3
"""DIPLIMIT step 3: replay every ARMED live window of a run (T2 + re-arm, filled or not) at other dip limits.
Same windows, same skips, same tries (the filters decide arming; the limit only decides fill or not).
  * Curve = raw tape, outside trades only (our txs removed), walked by deltas from the window anchor's recorded post state
    (T2: trigger tx; re-arm: the dump tx) [MEASURED tape; method of whaleflip/w5_replay.py].
  * REAL tries keep their real send time, signing state (vsol, vtok), landing (slot, idx) and deadline; only min_out changes:
    min_out(drop) = tokens our SOL buys at the limit price p_sign x (1 - drop) (pump curve math; checked = engine's min_out at 0.12).
    A landed try fills iff its landing res is 6042 / ok (or ata_exists landing after the live fill = the live fill made the ATA) and
    the curve before its landing gives >= min_out. Landed 'deadline' failures stay failures. First fill in chain order = our fill.
  * After the last real send of a window that FILLED live (the engine stopped sending at the fill), PHANTOM tries [INFERRED] go on to
    the window's modelled stop: one every 212/8 ms, signed on the state seen then, landing L ms later (L drawn from the run's real
    send->first_rx pool, unseen share kept), deadline = send slot + 1. Stop = T2: trigger slot + 10 / whale's first sell + 30 ms /
    QUIET 5:2; re-arm: en_slot / any armed holder's sell + 30 ms / QUIET 6:2 (from the dump slot).
  * Exit: the live fill keeps its REAL realized P&L. Any other fill: sell lands H ms (block clock) after the fill (H = the run's median
    live fill->sell-land, time-ms exits), P&L = curve SOL out - SOL in (our buy inserted) + the run's median fixed costs per kind
    (live realized - live curve_pnl: pump fees, tips, tx fees) [INFERRED; error measured on the live fills].
  * Fees: every landed try that does not fill and was sent before the fill was seen costs 5,120 lamports.
usage: d3_replay.py TAG RECORDING [RECORDING ...]   -> /home/it/sniper-data/filters3/diplimit/replay_<TAG>.json"""
import sys, os, json, glob, math, bisect, random, pickle, zlib, statistics, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/whaleflip")
import wtape as T

D = "/home/it/sniper-data/filters3/diplimit"
FR = 0.012500000186264515
FAIL = 5120
SMS = 212.0
KC = T.K
DROPS = [0.06, 0.08, 0.10, 0.12, 0.15, 0.18]
REPS = 20


def build_tapes(recs, mints, tlo=0, thi=1e12):
    raw = collections.defaultdict(dict); maxi = {}
    for rec in recs:
        for fn in sorted(glob.glob(f"{D}/raw/{rec}/txs_*.jsonl")):
            t0 = int(os.path.basename(fn).split("_")[1].split(".")[0])
            if t0 < tlo - 400 or t0 > thi + 400: continue
            for l in open(fn):
                d = json.loads(l)
                for m in {x[0] for x in d["tb"]}:
                    if m in mints: raw[m][d["sig"]] = d
            for s, i in json.load(open(fn + ".maxi.json")).items():
                s = int(s)
                if i > maxi.get(s, -1): maxi[s] = i
    tapes = {}
    for m, txs in raw.items():
        cnt = collections.Counter()
        for d in txs.values():
            for x in d["tb"]:
                if x[0] == m: cnt[x[1]] += 1
        curve = cnt.most_common(1)[0][0]
        rows = []
        for d in sorted(txs.values(), key=lambda d: (d["s"], d["i"])):
            own = {}
            for mm, o, pre, post in d["tb"]:
                if mm != m: continue
                a, b = own.get(o, (0, 0)); own[o] = (a + (pre or 0), b + (post or 0))
            if curve not in own: continue
            dl = {o: b - a for o, (a, b) in own.items() if o != curve}
            sel = min(dl.items(), key=lambda kv: kv[1], default=(None, 0))
            rows.append({"s": d["s"], "i": d["i"], "sig": d["sig"], "cpre": own[curve][0], "cpost": own[curve][1], "vtok": own[curve][1] + T.VOFF,
                         "seller": sel[0] if sel[1] < 0 else None, "sold": -sel[1] if sel[1] < 0 else 0,
                         "ours": any(o in T.OURS for o in own) or d["sg"] in T.OURS})
        tapes[m] = rows
    return tapes, maxi


def key(s, i): return s * 100000 + i


def cc(maxi, s, i): return T.cc(maxi, s, i)


def sol_in_of(spend): return int(spend / (1.0 + FR))


def min_out(V, Tk, spend, drop):
    k = V * Tk; vl = V * math.sqrt(1.0 - drop); tl = k / vl; x = spend / (1.0 + FR)
    return math.floor(tl * x / (vl + x))


def buy_tok(V, Tk, spend):
    x = sol_in_of(spend); return int(Tk * x // (V + x))


class Win: pass


def prep(w, rows, maxi):
    P = Win(); P.w = w
    anc = (w.get("trig") if w["kind"] == "t2" else w.get("dump")) or {}
    sigs = {x["sig"]: k for k, x in enumerate(rows)}
    ka = sigs.get(anc.get("sig"))
    if ka is None: return None, "no_anchor"
    P.T0 = rows[ka]["vtok"]; P.ts = anc["slot"]; P.spend = w["spend"] or 550000000
    P.whales = {anc.get("wallet")} if w["kind"] == "t2" else {h["w"] for h in (w.get("holders") or [])}
    P.out = []
    for x in rows[ka + 1:]:
        if x["ours"]: continue
        if x["s"] > P.ts + 60: break
        dt = x["cpost"] - x["cpre"]
        if dt > 0: kind, amt = "s", dt
        elif dt < 0: kind, amt = "b", KC / (x["cpost"] + T.VOFF) - KC / (x["cpre"] + T.VOFF)
        else: kind, amt = "n", 0
        P.out.append((key(x["s"], x["i"]), cc(maxi, x["s"], x["i"]), kind, amt, x["seller"], x["sold"]))
    P.maxi = maxi
    fl = w["fill"]; P.fill_sig = fl["sig"] if fl else None
    P.fill_key = key(fl["slot"], fl["idx"]) if fl and fl.get("idx") is not None else None
    P.tries = []; offs = []
    for t in w["tries"]:
        L = t.get("land") or {}
        res = L.get("res")
        land = (L["slot"], L["idx"]) if res not in (None, "unseen") and L.get("idx") is not None else None
        P.tries.append({"sig": t["sig"], "t": t["t"] / 1e6, "V": t["vsol"], "Tk": t["vtok"], "dl": t["deadline"], "mo_real": t["min_out"],
                        "land": land, "res": res, "real": True, "rx": (L.get("first_rx") or 0) / 1e6})
        if land and L.get("first_rx") and land[0] in maxi: offs.append(L["first_rx"] / 1e6 - cc(maxi, *land))
    if not offs: P.off = None
    else: P.off = statistics.median(offs)
    P.last_send = max((x["t"] for x in P.tries), default=None)
    q = (w.get("quiet") or {}).get("stop") or ("5:2" if w["kind"] == "t2" else "6:2")
    if w["kind"] == "rearm": q = "6:2"
    P.qn, P.qm = (int(z) for z in q.split(":"))
    P.en = (w.get("en_slot") or (P.ts + 10))
    return P, None


def state_before(P, K, ours=None):
    """(V, Tk) just before chain key K, outside trades only; ours = (key, sol_in, tokens) inserted if given"""
    Tk = P.T0; done = ours is None
    for o in P.out:
        if o[0] >= K: break
        if not done and ours[0] < o[0]:
            Tk = Tk - ours[2]; done = True
        if o[2] == "b": Tk = KC / (KC / Tk + o[3])
        elif o[2] == "s": Tk = Tk + o[3]
    if not done and ours[0] < K: Tk = Tk - ours[2]
    return KC / Tk, Tk


def stop_cc(P):
    E = (P.en + 1) * SMS
    for o in P.out:
        if o[4] in P.whales and o[5] > 0: E = min(E, o[1] + 30); break
    others = 0; qcut = (P.ts + P.qn) * SMS
    for o in P.out:
        if o[1] >= qcut: break
        if o[4] not in P.whales and o[2] != "n": others += 1
    if others < P.qm: E = min(E, qcut)
    return E


def y_to_key(P, y):
    s = int(y // SMS); fr = (y - s * SMS) / SMS
    mx = P.maxi.get(s, 400)
    return key(s, int(fr * (mx + 1))), s


def exit_curve(P, K, tok, H, ycc):
    sk, _ = y_to_key(P, ycc + H)
    sk = max(sk, K + 1)
    V, Tk = state_before(P, sk, (K, sol_in_of(P.spend), tok))
    return V * tok / (Tk + tok) - sol_in_of(P.spend)


def sim(P, drop, rng, pool, unseen, H, fixed):
    tries = []
    for t in P.tries:
        t = dict(t); t["mo"] = min_out(t["V"], t["Tk"], P.spend, drop); tries.append(t)
    phantoms = 0
    if P.fill_sig and P.off is not None and drop > 0.12 + 1e-9:
        E = stop_cc(P); tau = P.last_send - P.off + SMS / 8
        while tau < E:
            K_seen, _ = y_to_key(P, tau)
            V, Tk = state_before(P, K_seen)
            if rng.random() < unseen: land = None
            else:
                lk, _ = y_to_key(P, tau + rng.choice(pool)); land = (lk // 100000, lk % 100000)
            tries.append({"sig": None, "t": tau + P.off, "V": V, "Tk": Tk, "dl": int(tau // SMS) + 1, "mo": min_out(V, Tk, P.spend, drop),
                          "land": land, "res": "6042" if land else None, "real": False, "rx": None})
            tau += SMS / 8; phantoms += 1
    landed = sorted([t for t in tries if t["land"]], key=lambda t: key(*t["land"]))
    fill = None
    for t in landed:
        K = key(*t["land"])
        ok = t["res"] in ("6042", "ok") or (t["res"] == "ata_exists" and P.fill_key is not None and K > P.fill_key)
        if not ok: continue
        if t["land"][0] > t["dl"]: continue
        V, Tk = state_before(P, K)
        tok = buy_tok(V, Tk, P.spend)
        if tok >= t["mo"]: fill = (t, K, tok); break
    if fill is None:
        return {"filled": False, "pnl": 0.0, "src": None, "fails": len(landed), "ph": phantoms}
    t, K, tok = fill
    if t["sig"] == P.fill_sig: pnl = P.w["pnl"] * 1e9; src = "live"
    else:
        ycc = cc(P.maxi, *t["land"])
        pnl = exit_curve(P, K, tok, H, ycc) + fixed; src = "real" if t["real"] else "phantom"
    seen = t["rx"] if t["real"] and t["rx"] else (cc(P.maxi, *t["land"]) + (P.off or 0))
    fails = sum(1 for x in landed if x is not t and x["t"] <= seen)
    return {"filled": True, "pnl": pnl, "src": src, "fails": fails, "ph": phantoms, "early_ms": None}


if __name__ == "__main__":
    tag, recs = sys.argv[1], sys.argv[2:]
    WD = pickle.load(open(f"{D}/win_{tag}.pkl", "rb"))
    wins = WD["wins"]
    ta = [w["t_arm"] / 1e9 for w in wins if w["t_arm"]]
    tapes, maxi = build_tapes(recs, {w["mint"] for w in wins}, min(ta), max(ta))
    last_slot = max(maxi) if maxi else 0
    pool = [p[1] for p in WD["pool"] if p[0] != "unseen" and p[1] is not None and 0 < p[1] < 2000]
    unseen = sum(1 for p in WD["pool"] if p[0] == "unseen") / max(1, len(WD["pool"]))
    PW = []; drop_why = collections.Counter(); Hs = []; fixed = collections.defaultdict(list); chk = []
    for w in wins:
        anc = (w.get("trig") if w["kind"] == "t2" else w.get("dump")) or {}
        if not anc.get("slot") or anc["slot"] + 25 > last_slot: drop_why["after_tape_end"] += 1; continue
        rows = tapes.get(w["mint"])
        if not rows: drop_why["no_tape"] += 1; continue
        P, why = prep(w, rows, maxi)
        if P is None: drop_why[why] += 1; continue
        PW.append(P)
        cl = w.get("close") or {}
        if w["fill"] and w["pnl"] is not None and cl.get("curve_pnl") is not None and cl.get("rounds") == 1:
            fixed[w["kind"]].append(w["pnl"] * 1e9 - cl["curve_pnl"])
            sl = cl.get("sell_land"); fl = w["fill"]
            if sl and cl.get("exit_why") == "time-ms" and sl[0] in maxi and fl["slot"] in maxi:
                Hs.append(cc(maxi, sl[0], sl[1]) - cc(maxi, fl["slot"], fl["idx"]))
    H = statistics.median(Hs) if Hs else 250.0
    FX = {k: statistics.median(v) for k, v in fixed.items()}
    print(f"{tag}: windows {len(wins)} replayed {len(PW)} dropped {dict(drop_why)} | tape last slot {last_slot} | H {H:.0f} ms | fixed mSOL "
          f"{ {k: round(v / 1e6, 2) for k, v in FX.items()} } | pool {len(pool)} unseen {unseen:.3f}", flush=True)
    # checks: engine min_out reproduced; exit model on the live fills
    mo_err = []
    for P in PW:
        for t in P.tries:
            if t["mo_real"]: mo_err.append(abs(min_out(t["V"], t["Tk"], P.spend, 0.12) - t["mo_real"]) / t["mo_real"])
    ex = []
    for P in PW:
        w = P.w; cl = w.get("close") or {}
        if not (w["fill"] and w["pnl"] is not None and cl.get("rounds") == 1 and w["fill"].get("idx") is not None): continue
        fl = w["fill"]; K = key(fl["slot"], fl["idx"]); V, Tk = state_before(P, K); tok = buy_tok(V, Tk, P.spend)
        own = None; sl = cl.get("sell_land")
        if sl:
            sk = key(sl[0], sl[1]); V2, T2 = state_before(P, sk, (K, sol_in_of(P.spend), tok)); own = V2 * tok / (T2 + tok) - sol_in_of(P.spend)
        mod = exit_curve(P, K, tok, H, cc(maxi, fl["slot"], fl["idx"])) + FX.get(w["kind"], -15e6)
        ex.append({"kind": w["kind"], "tok_model": tok, "tok_live": fl.get("tokens"), "curve_live": cl.get("curve_pnl"), "curve_own_sell": own,
                   "real": w["pnl"], "model": mod / 1e9})
    res = []
    for P in PW:
        w = P.w
        row = {"w": w["w"], "kind": w["kind"], "mint": w["mint"], "t": w["t_arm"], "live_filled": bool(w["fill"]), "pnl_live": w["pnl"],
               "d": {}}
        for dr in DROPS:
            reps = REPS if (P.fill_sig and dr > 0.12 + 1e-9) else 1
            acc = collections.defaultdict(float); srcs = collections.Counter()
            for rep in range(reps):
                rng = random.Random(zlib.crc32(f"{tag}|{w['w']}|{dr}|{rep}".encode()))
                o = sim(P, dr, rng, pool, unseen, H, FX.get(w["kind"], -15e6))
                acc["fill_pnl"] += o["pnl"] / 1e9 / reps; acc["fails"] += o["fails"] / reps; acc["filled"] += o["filled"] / reps
                srcs[o["src"]] += 1
            row["d"][str(dr)] = {"fill_pnl": round(acc["fill_pnl"], 6), "fails": round(acc["fails"], 2), "filled": round(acc["filled"], 3), "src": dict(srcs)}
        res.append(row)
    json.dump({"tag": tag, "rows": res, "H": H, "FX": FX, "mo_err": {"n": len(mo_err), "max": max(mo_err) if mo_err else None,
               "p99": sorted(mo_err)[int(len(mo_err) * 0.99)] if mo_err else None}, "exit_check": ex, "dropped": dict(drop_why), "last_slot": last_slot},
              open(f"{D}/replay_{tag}.json", "w"))
    print("done", len(res), flush=True)
