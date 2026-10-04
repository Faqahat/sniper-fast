#!/usr/bin/env python3
"""Pattern scan over w5h segments (read-only on runs/; writes only tmp-patterns/scan-<seg>.json).
Aggregates: every profitable arbitrage round trip (win) on our pools with gap age (PoH), competition, fees, tips,
leader kind; per-signer volume/results; fee/tip vs outcome bins; our attempts and the winner of each."""
import json, sys, os, collections, subprocess, urllib.request, time, bisect
os.chdir("/root/arb-lab")
OUT = "tmp-patterns"
WSOL = "So11111111111111111111111111111111111111112"
_env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
KEY = _env.get("HAAN_API_KEY", ""); del _env
VENUE = {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
         "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
         "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
         "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
NEUTRAL = {"ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
           "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo",
           "ComputeBudget111111111111111111111111111111", "11111111111111111111111111111111"}
def is_arb(progs):
    p = {x for x in progs if x not in NEUTRAL}
    return bool(p) and not p <= VENUE
def lines(seg, name):
    p = f"runs/{seg}/{name}"
    if os.path.exists(p):
        with open(p) as f: yield from f
    elif os.path.exists(p + ".zst"):
        pr = subprocess.Popen(["zstd", "-dc", p + ".zst"], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        yield from pr.stdout; pr.wait()
def jl(seg, name):
    for l in lines(seg, name):
        try: yield json.loads(l)
        except Exception: pass
def rpc(m, p):
    for i in range(3):
        try:
            r = urllib.request.Request("https://rpc.haandigital.eu/", json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                       {"content-type": "application/json", "Authorization": "Bearer " + KEY})
            return json.load(urllib.request.urlopen(r, timeout=30)).get("result")
        except Exception: time.sleep(1 + i)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
def s8(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return (b"\0" * (len(s) - len(s.lstrip("1"))) + raw)[:8].hex()
INFO = json.load(open("runs/long-1-leaders.json")).get("info", {})
def bk(v, E):
    if not v or v <= 0: return "0"
    for e in E:
        if v <= e: return f"<={e}"
    return f">{E[-1]}"
PRIO_E = [1000, 10000, 100000, 1000000]
TIP_E = [10000, 100000, 1000000, 10000000]
I = sys.intern

# pool -> (venue, mint) from every segment's priced gaps + attempts
PM = {}
SEGS = sys.argv[1:] or [f"w5h-p{i}" for i in range(1, 16)]
for seg in [f"w5h-p{i}" for i in range(1, 16)]:
    for c in jl(seg, "caps.jsonl"):
        PM.setdefault(c["buy"], (c["buy_venue"], c["mint"])); PM.setdefault(c["sell"], (c["sell_venue"], c["mint"]))
    for a in jl(seg, "attempts.jsonl"):
        PM.setdefault(a["buy_pool"], (a["buy_venue"], a.get("mint"))); PM.setdefault(a["sell_pool"], (a["sell_venue"], a.get("mint")))
def vp(pools):
    return "+".join(sorted({PM.get(p, ("?", None))[0] for p in pools})) or "?"

def run(seg):
    T0 = time.time()
    st = list(jl(seg, "status.jsonl"))
    t_first, t_last = st[0]["t_ns"], st[-1]["t_ns"]
    hours = (t_last - t_first) / 3.6e12
    # ---- rivals: every tx touching our pools (from shreds)
    R = {}
    for l in lines(seg, "rivals.jsonl"):
        try: x = json.loads(l)
        except Exception: continue
        tips = x.get("tips") or []
        R[x["sig"]] = (I(x.get("signer") or ""), is_arb(x.get("progs") or []), tuple(I(p) for p in (x.get("pools") or [])),
                       sum((t[1] or 0) for t in tips), I("+".join(sorted({(t[2] or "unknown-tip") for t in tips})) or "no tip"),
                       x.get("cu_price") or 0, x.get("cu_limit") or 0, bool(x.get("nonce")), I(x.get("feed") or ""), x.get("n_sig") or 1, x.get("v1_fee"),
                       I("+".join(sorted(x.get("venues") or [])) or "?"))
    T1 = time.time()
    # ---- moves: state changes per pool
    MV = collections.defaultdict(list); msig = collections.defaultdict(set)
    for l in lines(seg, "moves.log"):
        p = l.split()
        if len(p) >= 4: MV[p[2]].append((int(p[1]), p[0], int(p[3]))); msig[p[0]].add(p[2])
    # ---- exec: results
    E = {}; n_exec = n_skip = 0
    for l in lines(seg, "exec.jsonl"):
        n_exec += 1
        i = l.find('"sig":"')
        if i < 0: continue
        sig = l[i + 7: l.index('"', i + 7)]
        if sig not in R and sig not in msig: n_skip += 1; continue
        try: x = json.loads(l)
        except Exception: continue
        ok = bool(x.get("ok")); tok = x.get("tok") or {}
        left = any(k != WSOL and v != "0" for k, v in tok.items())
        res = (x.get("sol") or 0) + int(tok.get(WSOL, "0") or 0)
        E[sig] = (x.get("slot"), x.get("idx") if x.get("idx") is not None else 10 ** 6, ok, I(x.get("signer") or ""), res if (ok and not left) else None, x.get("fee") or 0,
                  tuple(k for k in tok if k != WSOL) if (ok and not left) else ())
    T2 = time.time()
    # ---- leaders
    slots = [e[0] for e in E.values() if e[0]]
    lo, hi = min(slots), max(slots)
    L = {}
    s = lo
    while s <= hi:
        n = min(5000, hi - s + 1)
        for k, v in enumerate(rpc("getSlotLeaders", [s, n]) or []): L[s + k] = v
        s += n
    def lk(slot):
        i = INFO.get(L.get(slot)) if slot in L else None
        if not i: return ("unknown", "?")
        kind = "BAM" if i.get("bam") else "Jito" if i.get("jito") else "non-Jito"
        rtt = i.get("rtt_ms")
        where = "?" if rtt is None else "sameDC<1ms" if rtt < 1 else "near<5ms" if rtt < 5 else "EU<30ms" if rtt < 30 else "far>=30ms"
        return (kind, where)
    # ---- per signer + Q4 bins + per pool + arb txs per pool
    SG = collections.defaultdict(collections.Counter); SGsvc = collections.defaultdict(collections.Counter); SGbin = collections.defaultdict(collections.Counter)
    Q4 = collections.Counter(); POOL = collections.defaultdict(collections.Counter); POOLsg = collections.defaultdict(set)
    PA = collections.defaultdict(list)
    for sig, r in R.items():
        signer, arb, pools, tip, svc, cup, cul, nonce, feed, nsig, v1, ven = r
        e = E.get(sig)
        if not arb:
            if e and e[2]:
                for p in pools: POOL[p]["retail_ok"] += 1
            continue
        c = SG[signer]; c["seen"] += 1; c["nonce"] += nonce; SGsvc[signer][svc] += 1
        if tip: c["tip_offered_txs"] += 1
        for p in pools: POOL[p]["arb_seen"] += 1; POOLsg[p].add(signer)
        if not e: c["no_exec"] += 1; continue
        slot, idx, ok, _, gain, fee, _m = e
        prio = max(0, fee - 5000 * nsig)
        c["landed"] += 1; c["fee"] += fee; c["prio"] += prio
        if ok: c["ok"] += 1; c["tip_paid"] += tip
        else: c["fail_fee"] += fee
        out = "win" if (gain is not None and gain > 0) else ("okloss" if ok else "fail")
        if out == "win": c["wins"] += 1; c["gain"] += gain; c["tip_wins"] += tip; c["fee_wins"] += fee
        elif out == "okloss" and gain is not None: c["okloss"] += gain
        elif out == "okloss": c["ok_tokleft"] += 1
        k = lk(slot)
        Q4[(svc, bk(prio, PRIO_E), bk(tip, TIP_E), k[0], ven, out)] += 1
        SGbin[signer][(bk(prio, PRIO_E), bk(tip, TIP_E), out)] += 1
        for p in pools:
            PA[p].append((slot, idx, signer, ok, sig))
            POOL[p]["arb_landed"] += 1
            if out == "win": POOL[p]["wins"] += 1; POOL[p]["gain"] += gain
    for p in PA: PA[p].sort()
    # ---- wins + gap age
    order = collections.defaultdict(list); mvt = {}
    for p, mv in MV.items():
        for slot, sig, tn in mv: mvt.setdefault(sig, tn)
    for sig, e in E.items():
        if not e[2]: continue                                  # failed tx = no state change
        r = R.get(sig)
        for p in (set(r[2]) if r else set()) | msig.get(sig, set()):
            order[p].append(((e[0], e[1], mvt.get(sig, 0)), sig))
    for p in order: order[p].sort()
    W = []
    for sig, r in R.items():
        if not r[1]: continue
        e = E.get(sig)
        if not e or e[4] is None or e[4] <= 0: continue
        signer, arb, pools, tip, svc, cup, cul, nonce, feed, nsig, v1, ven = r
        slot, idx, ok, _, gain, fee, tokm = e
        allp = set(pools) | msig.get(sig, set())
        wk = (slot, idx, 0)
        prev = None
        for p in allp:
            mv = order.get(p, [])
            j = bisect.bisect_left(mv, (wk, "")) - 1
            while j >= 0 and mv[j][1] == sig: j -= 1
            if j >= 0 and (prev is None or mv[j][0] > prev[0]): prev = (mv[j][0], mv[j][1], p)
        # competition in window (prev, end of the slot after the win]
        kp = (prev[0][0], prev[0][1]) if prev else (slot, -1)
        cnt = 0; others = set(); own = 0; ofail = 0; seen_s = set()
        for p in allp:
            pa = PA.get(p, [])
            j0 = bisect.bisect_right(pa, (kp[0], kp[1], "￿"))
            j1 = bisect.bisect_right(pa, (slot + 1, 10 ** 7))
            for t in pa[j0:j1]:
                if t[4] in seen_s or t[4] == sig: continue
                seen_s.add(t[4]); cnt += 1
                if t[2] == signer: own += 1
                else:
                    others.add(t[2])
                    if not t[3]: ofail += 1
        pr = E.get(prev[1]) if prev else None; prr = R.get(prev[1]) if prev else None
        W.append({"sig": sig, "signer": signer, "slot": slot, "idx": idx, "gain": gain, "fee": fee, "prio": max(0, fee - 5000 * nsig), "tip": tip, "svc": svc,
                  "cu_price": cup, "cu_limit": cul, "v1": v1, "nonce": nonce, "feed": feed, "pools": sorted(allp), "vp": ven, "vp_pm": vp(allp),
                  "mints": sorted(set(tokm) | {PM[p][1] for p in allp if p in PM and PM[p][1]}), "n_watched": len(allp),
                  "prev_sig": prev[1] if prev else None, "prev_slot": prev[0][0] if prev else None, "prev_idx": prev[0][1] if prev else None,
                  "prev_arb": (prr[1] if prr else None), "prev_signer": (pr[3] if pr else (prr[0] if prr else None)), "prev_vp": (prr[11] if prr else None),
                  "prev_mv_tns": (prev[0][2] or None) if prev else None, "win_mv_tns": mvt.get(sig),
                  "copies": cnt, "rivals": len(others), "rival_fail": ofail, "own_copies": own, "lk": lk(slot)})
    T3 = time.time()
    # ---- our attempts
    A = {x["attempt"]: x for x in jl(seg, "attempts.jsonl")}
    O = {x["attempt"]: x for x in jl(seg, "outcomes.jsonl")}
    OPP = {x["id"]: x for x in jl(seg, "opportunities.jsonl")}
    winsby = collections.defaultdict(list)
    for w in W:
        for p in w["pools"]: winsby[p].append((w["slot"], w["idx"], w["sig"]))
    for p in winsby: winsby[p].sort()
    WD = {w["sig"]: w for w in W}
    ours = []
    oursigs = set()
    for i, a in A.items():
        for c in a.get("copies") or []:
            if c.get("sig"): oursigs.add(c["sig"])
    for i, a in A.items():
        if a.get("kind") != "live": continue
        o = O.get(i, {}); op = OPP.get(a.get("opp")) or {}
        t0 = min((op.get("arrivals") or {}).values() or [0]) or None
        ts = [c.get("t_sent") for c in (o.get("copies") or []) if c.get("t_sent")]
        verdict = "WIN" if o.get("ok") else ("landed-fail" if o.get("landed") else "not-landed")
        trig = a.get("trigger"); te = E.get(trig) if trig else None
        tkey = (te[0], te[1]) if te else (a.get("slot") or 0, -1)
        winner = None
        for p in (a["buy_pool"], a["sell_pool"]):
            for (sl, ix, s_) in winsby.get(p, [])[bisect.bisect_right(winsby.get(p, []), (tkey[0], tkey[1], "￿")):]:
                if sl > tkey[0] + 5: break
                if s_ in oursigs or s_ == trig: continue
                if winner is None or (sl, ix) < (WD[winner]["slot"], WD[winner]["idx"]): winner = s_
                break
        ours.append({"att": i, "slot": a.get("slot"), "kind": "state" if a.get("trigger_feed") == "state" else "decoded", "arm": a.get("path_arm"),
                     "pair": f'{a["buy_venue"]}>{a["sell_venue"]}', "mint": a.get("mint"), "pools": [a["buy_pool"], a["sell_pool"]],
                     "size": a.get("size_lamports", 0), "exp": a.get("expected_profit", 0), "tip": sum((c.get("tip") or 0) for c in a.get("copies") or []),
                     "cu_price": a.get("cu_price_micro"), "paths": sorted({c.get("path") for c in a.get("copies") or []}), "verdict": verdict, "landed": o.get("landed"),
                     "profit": o.get("profit_lamports") if o.get("ok") else None, "fee": o.get("fee_lamports"), "tip_paid": o.get("tip_paid_lamports"),
                     "jito": (o.get("jito") or {}).get("outcome"), "ms_poh": (o.get("poh") or {}).get("ours_ms_after_trigger"),
                     "sent_ms": (min(ts) - t0) / 1e6 if (ts and t0) else None, "trigger": trig, "slots_after": o.get("slots_after_trigger"),
                     "winner": winner, "landed_sig": o.get("sig") if o.get("landed") else None})
    # ---- timing: PoH position of wins, prevs, triggers
    need = {}
    for w in W:
        need[s8(w["sig"])] = None
        if w["prev_sig"]: need[s8(w["prev_sig"])] = None
    for x in ours:
        if x["trigger"]: need[s8(x["trigger"])] = None
        if x["landed_sig"]: need[s8(x["landed_sig"])] = None
    poh = {}
    for l in lines(seg, "poh.log"):
        p = l.split()
        if len(p) == 3 and p[0] in need and p[0] not in poh: poh[p[0]] = (int(p[1]), float(p[2]))
    arr = {}
    for l in lines(seg, "txarr.log"):
        p = l.split(maxsplit=3)
        if len(p) >= 3 and p[0] in need and p[0] not in arr: arr[p[0]] = int(p[2])
    def tabs(sig):
        k = s8(sig); v = poh.get(k)
        return (v[0] * 400 + v[1]) if v else None
    for w in W:
        a, b = tabs(w["sig"]), (tabs(w["prev_sig"]) if w["prev_sig"] else None)
        pw = poh.get(s8(w["sig"]))
        w["poh_in_slot"] = pw[1] if pw else None
        if a is not None and b is not None: w["dt"] = a - b; w["dt_src"] = "poh"
        else:
            ta, tb = arr.get(s8(w["sig"])), (arr.get(s8(w["prev_sig"])) if w["prev_sig"] else None)
            if ta and tb: w["dt"] = (ta - tb) / 1e6; w["dt_src"] = "arrival"
            elif w["win_mv_tns"] and w["prev_mv_tns"]: w["dt"] = (w["win_mv_tns"] - w["prev_mv_tns"]) / 1e6; w["dt_src"] = "moves"
            else: w["dt"] = None; w["dt_src"] = None
    for x in ours:
        tt = tabs(x["trigger"]) if x["trigger"] else None
        if x["winner"]:
            tw = tabs(x["winner"])
            x["winner_ms"] = (tw - tt) if (tw is not None and tt is not None) else None
        if x["landed_sig"]:
            tl = tabs(x["landed_sig"])
            x["ours_land_ms"] = (tl - tt) if (tl is not None and tt is not None) else None
    # ---- report.json (seg.py) denied list if present
    rep = {}
    if os.path.exists(f"runs/{seg}/report.json"):
        try: rep = json.load(open(f"runs/{seg}/report.json"))
        except Exception: rep = {}
    res = {"seg": seg, "hours": hours, "t_first": t_first, "t_last": t_last, "n_rivals": len(R), "n_exec": n_exec, "n_exec_used": len(E),
           "rivals_in_exec": sum(1 for s_ in R if s_ in E), "arb_seen": sum(1 for r in R.values() if r[1]), "arb_in_exec": sum(1 for s_, r in R.items() if r[1] and s_ in E),
           "n_moves": sum(len(v) for v in MV.values()), "poh_found": len(poh), "need": len(need),
           "wins": W, "signers": {k: dict(v) | {"svc": dict(SGsvc[k].most_common(8))} for k, v in SG.items() if v["seen"] >= 20 or v["wins"] > 0},
           "signer_bins": {k: [[*kk, n] for kk, n in v.items()] for k, v in SGbin.items() if SG[k]["landed"] >= 30},
           "q4": [[*k, n] for k, n in Q4.items()], "pools": {p: dict(c) | {"bots": len(POOLsg[p])} for p, c in POOL.items()},
           "ours": ours, "denied": rep.get("denied"), "rivals_on_gaps": rep.get("rivals_on_gaps"),
           "timing_s": [round(T1 - T0), round(T2 - T1), round(T3 - T2), round(time.time() - T3)]}
    json.dump(res, open(f"{OUT}/scan-{seg}.json", "w"))
    print(seg, f"{hours * 60:.1f} min", "rivals", len(R), "exec", n_exec, "used", len(E), "wins", len(W), "ours", len(ours), "poh", len(poh), "/", len(need), "t", res["timing_s"], flush=True)

for seg in SEGS:
    try: run(seg)
    except Exception as ex:
        import traceback; traceback.print_exc(); print("FAIL", seg, ex, flush=True)
