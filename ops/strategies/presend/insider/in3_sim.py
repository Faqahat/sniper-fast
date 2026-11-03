#!/usr/bin/env python3
"""INSIDER step 3: the multiarm JOINT try-level replay (multiarm/ma4_sim.py, calibrated on r37/r38) with one more window kind:
INSIDER windows (PREREG.txt): arm when a create-slot insider (book.rs w.ins: a buy in the create slot, not the creator / the create's
payer / ours) holds >= X% of supply -- mode x: at its crossing buy in the create slot (seen); e0: at the first tx of the slot after the
create slot; e1: at the first tx of slot create+2 -- 0.65 SOL, the standard tries (8/slot, 0.88x limit, deadline send slot + 1), last
slot = arm slot + W, stopped 30 ms after the trigger insider's first sell is seen, superseded by a T2 arm, skipped when the token is
armed / our position, margin or token account is open on it. Everything else (T2 windows as armed live, the live R0 re-arm rule, the
sender's caps, the one-position pause, the 1 SOL / 24 h failed-try budget, exits, costs, follower adjustment) is ma4_sim's, unchanged.
(INFERRED: phantom tries on the real tape; inputs MEASURED per run.)"""
import sys, json, pickle, math, heapq, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/moiz/sniper/ops/obs/paper_audit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
import c37lib as L
import pa_lib as PA
import ma_lib as M
import ma4_sim as S

SMS = 212.0
FAIL = 5120
FIX = L.FIX
MARGIN = 300.0
BUDGET = 1_000_000_000
XS = (6, 8, 10, 15)
MODES = ("x", "e0", "e1")


class Light:
    """a token's trades as arrays (the fields ma4_sim.World.window_P / seen read)"""
    def __init__(self, tape, mint, t):
        self.mint = mint; self.n = len(t)
        self.s = t["slot"].astype(np.int64); self.i = t["idx"].astype(np.int64); self.j = t["j"].astype(np.int64)
        self.buy = t["buy"].astype(bool); self.sol = t["sol"].astype(np.int64); self.tok = t["tok"].astype(np.int64)
        self.vsol = t["vsol"].astype(np.int64); self.vtok = t["vtok"].astype(np.int64); self.user = t["user"].astype(np.int64)
        mx = np.array([tape.maxi.get(int(x), 400) for x in self.s.tolist()], dtype=np.float64)
        self.c = self.s * SMS + (self.i + 0.5) / (mx + 1.0) * SMS


def ins_facts(Wd):
    """per token created inside the span: every (mode, X) arm with its trigger trade, insider, solo flag, stop (the insider's first
    sell after the arm) -- tape only, computed once per run"""
    tape, A = Wd.tape, Wd.A
    ours = tape.ours
    out = []; lights = {}
    n_tok = 0; n_ins_tok = 0
    for m, c in tape.creates.items():
        s0 = c.get("slot")
        if s0 is None or s0 < Wd.s_start or s0 > Wd.cal["s_end"]: continue
        if c.get("mayhem") or c.get("mayhem_ix"): continue
        t = tape.trades(m)
        if t is None or len(t) == 0: continue
        n_tok += 1
        tl = Light(tape, m, t)
        crea = {tape.gid.get(c.get("creator")), tape.gid.get(c.get("payer")), tape.gid.get(c.get("user"))}
        # followed: the first 50 trades from the create at curve 25..200 SOL, vtok > 0
        k_first = int(np.searchsorted(tl.s, s0))
        out_k = tl.n; cnt = 0
        for k in range(k_first, tl.n):
            if cnt < 50 and (tl.vsol[k] < 25_000_000_000 or tl.vsol[k] > 200_000_000_000 or tl.vtok[k] == 0): out_k = k; break
            cnt += 1
            if cnt >= 50: break
        bal = collections.defaultdict(int); ins = set()
        got_x = {}; done_e = set()
        arms = []
        k_end = int(np.searchsorted(tl.s, s0 + 2))          # trades of slots s0, s0+1
        def holders(th_pct, excl=None):
            th = th_pct * M.SUPPLY / 100
            return [(u, b) for u, b in bal.items() if u in ins and b >= th and u != excl]
        def solo_of(u):
            th3 = 3 * M.SUPPLY / 100
            return not any((b >= th3) for v, b in bal.items() if v != u and (v in ins or v in crea))
        for k in range(k_first, k_end):
            u = int(tl.user[k])
            if u not in ours:
                b0 = bal[u]; b1 = b0 + int(tl.tok[k]) if tl.buy[k] else b0 - int(tl.tok[k]); bal[u] = b1
                if tl.buy[k] and tl.s[k] == s0 and u not in crea: ins.add(u)
                if tl.buy[k] and tl.s[k] == s0 and u in ins and k < out_k and tl.vsol[k] < M.UNTRADE_V:
                    for X in XS:
                        th = X * M.SUPPLY / 100
                        if b0 < th <= b1 and X not in got_x:
                            got_x[X] = True
                            arms.append({"mode": "x", "X": X, "k": k, "u": u, "arm_slot": int(tl.s[k]), "solo": solo_of(u), "pct": b1 / M.SUPPLY * 100})
            # end of slot es (e0: the create slot, e1: create+1): the state after the token's last trade of slots <= es
            nxt_s = int(tl.s[k + 1]) if k + 1 < tl.n else None
            for mode, es in (("e0", s0), ("e1", s0 + 1)):
                if mode in done_e: continue
                if tl.s[k] <= es and (nxt_s is None or nxt_s > es):
                    done_e.add(mode)
                    if k >= out_k or tl.vsol[k] >= M.UNTRADE_V: continue
                    for X in XS:
                        hs = holders(X)
                        if not hs: continue
                        uu = max(hs, key=lambda z: z[1])[0]
                        arms.append({"mode": mode, "X": X, "k": k, "u": uu, "arm_slot": es + 1, "solo": solo_of(uu), "pct": bal[uu] / M.SUPPLY * 100})
        if not arms: continue
        n_ins_tok += 1
        lights[m] = tl
        for a in arms:
            k = a["k"]
            if a["mode"] == "x":
                t_arm = Wd.seen(tl, k)
            else:
                cs = tape.slot_ge(a["arm_slot"])
                if cs is None: continue
                t_arm = tape.slot_start_cc(cs) + A(cs) + Wd.cal["arm_dt"]
            if not (Wd.t_start <= t_arm <= Wd.t_end): continue
            # the trigger insider's first sell after the arm trade
            ks = None
            for q in range(k + 1, tl.n):
                if tl.user[q] == a["u"] and not tl.buy[q]: ks = q; break
            t_sell = Wd.seen(tl, ks) if ks is not None else math.inf
            a.update({"mint": m, "t_arm": t_arm, "t_isell": t_sell, "isell_slot": int(tl.s[ks]) if ks is not None else None, "s0": int(s0),
                      "key": (m, "ins", int(tl.s[k]), int(tl.i[k]), int(tl.j[k]))})
            out.append(a)
    return out, lights, {"tokens": n_tok, "tokens_with_arm": n_ins_tok}


def ins_cands(Wd, irule, facts):
    """the variant's arms, sorted by arm time"""
    arms, lights, _ = facts
    mode, X, W, solo = irule["mode"], irule["X"], irule["W"], irule.get("solo", False)
    out = []
    for a in arms:
        if a["mode"] != mode or a["X"] != X: continue
        if solo and not a["solo"]: continue
        en = a["arm_slot"] + W
        es = Wd.tape.slot_ge(en + 1)
        t_exp = Wd.tape.slot_start_cc(es) + Wd.A(es) if es is not None else math.inf
        if a["t_isell"] + 30.0 < t_exp: t_stop, why = a["t_isell"] + 30.0, "insider_sell"
        else: t_stop, why = t_exp, "expired"
        out.append(dict(a, en_slot=en, t_stop=t_stop, why=why, tl=lights[a["mint"]]))
    out.sort(key=lambda c: c["t_arm"])
    return out


def simulate(Wd, rule, rep, irule=None, facts=None, t2_on=True):
    """ma4_sim.simulate + INSIDER windows (irule: {"mode", "X", "W", "solo"}; None = the base)"""
    tape, A, R, cal = Wd.tape, Wd.A, Wd.R, Wd.cal
    iv = cal["iv"]
    heap = []; seq = [0]
    def push(t, typ, a=None, b=None):
        seq[0] += 1; heapq.heappush(heap, (t, seq[0], typ, a, b))
    wins = []
    armed = {}; recount = collections.Counter(); pos_open = collections.Counter(); free_at = {}; ata_until = {}; inflight = {}; pos_close = {}
    t2_arm_times = collections.defaultdict(list)
    npos = [0]; positions = []
    caps = S.Caps()
    fees = collections.deque(); fee_sum = [0]; fee_pause = [0.0]
    stats = collections.Counter()
    skips = collections.Counter()
    cands, tape_skips = Wd.candidates(rule) if rule is not None else ([], collections.Counter())
    for k, v in tape_skips.items(): skips[k] += v
    if t2_on:
        for P in Wd.t2:
            if Wd.t_start <= P.t_trig <= Wd.t_end: push(P.t_trig, "T2", P)
    for cd in cands: push(cd["t_chk"], "CHK", cd)
    icands = ins_cands(Wd, irule, facts) if irule is not None else []
    for cd in icands: push(cd["t_arm"], "INS", cd)
    Ls = R.L; nL = len(Ls); Ds = R.D; nD = len(Ds)

    def block_until(m, t):
        b = 0.0
        if pos_open[m] > 0: b = max(b, pos_close.get(m, t) + MARGIN)
        b = max(b, free_at.get(m, 0.0), ata_until.get(m, 0.0), inflight.get(m, 0.0))
        return b

    def stop(w, t, why):
        if w.stopped: return
        w.stopped = True; w.end_t = t; w.end_why = why
        if armed.get(w.mint) == w.wid: armed.pop(w.mint, None)
        if w.last_dl is not None:
            inflight[w.mint] = max(inflight.get(w.mint, 0.0), (w.last_dl + 1) * SMS + w.P.off_s)

    def new_win(kind, key, mint, P, size, en, t0, t_stop, why_stop, t_arm, cand=None, nth=0):
        w = S.WinSt()
        w.wid = len(wins); w.key = key; w.kind = kind; w.mint = mint; w.P = P; w.size = size; w.drop = 0.12; w.en = en; w.t0 = t0; w.t_stop = t_stop
        w.why_stop = why_stop; w.n = 0; w.sent = 0; w.refused = 0; w.paused = 0; w.landed = 0; w.best = None; w.bver = 0; w.stopped = False
        w.end_t = None; w.end_why = None; w.last_dl = None; w.rng = S.rng_for(rep, Wd.run, key); w.cand = cand; w.nth = nth; w.t_arm = t_arm; w.filled = False; w.res = None
        wins.append(w)
        armed[mint] = w.wid
        push(t0, "TICK", w.wid); push(t_stop, "END", w.wid)
        return w

    def arm_rearm(cd, t, deferred):
        m = cd["mint"]; tl = tape.tok(m)
        if deferred:
            arm_slot = Wd.slot_at(t)
            k_from = Wd.first_seen_ge(tl, t)
        else:
            arm_slot = cd["check_slot"]; k_from = None
        if arm_slot > cd["en_slot"]: skips["rearm_deferred_expired"] += 1; return
        kt = cd["k"] if not cd["chained"] else cd["k_trig"]
        P = Wd.window_P(m, tl, kt, cd["key"], cd["en_slot"], 650_000_000)
        if P is None: skips["rearm_no_tape"] += 1; return
        t_stop, why, _ = M.natural_end(tape, tl, rule, A, t, arm_slot, cd["en_slot"], k_from)
        t_stop += cal["end_dt"].get(why, 0.0)
        recount[m] += 1
        new_win("rearm", cd["key"], m, P, 0.65, cd["en_slot"], t + cal["first_re"], t_stop, why, t, cd, recount[m])
        stats["rearm_windows"] += 1
        if deferred: stats["rearm_armed_after_wait"] += 1

    while heap:
        t, _, typ, a, b = heapq.heappop(heap)
        if typ == "TICK":
            w = wins[a]
            if w.stopped: continue
            P = w.P
            slot = int((t - P.off_s) // SMS)
            if t >= w.t_stop or slot > w.en: continue
            w.n += 1
            nxt = t + iv
            if npos[0] > 0: w.paused += 1; push(nxt, "TICK", a); continue
            while fees and fees[0][0] < t - 86_400_000.0: fee_sum[0] -= fees.popleft()[1]
            if fee_sum[0] >= BUDGET: fee_pause[0] += iv; push(nxt, "TICK", a); continue
            ri = (w.n + w.wid) % 2
            if not caps.ok(t, ri): w.refused += 1; push(nxt, "TICK", a); continue
            w.sent += 1
            dl = min(slot + 1, w.en)
            w.last_dl = dl if w.last_dl is None else max(w.last_dl, dl)
            rng = w.rng
            if rng.random() < R.p_unseen:
                push(nxt, "TICK", a); continue
            V, T, _ = L.state_at_c(P, t - P.off)
            c = t - P.off + max(5.0, float(Ls[rng.integers(nL)]))
            s, i = P.pos_of(c)
            w.landed += 1
            fees.append((c + P.off, FAIL)); fee_sum[0] += FAIL
            if s <= dl and V < M.UNTRADE_V:
                mo, _ = L.limit_min_out(V, T, int(round(w.size * 1e9)), L.FR, w.drop)
                V2, T2, kn = L.state_before(P, s, i)
                tok, xn = L.buy_out(V2, T2, int(round(w.size * 1e9)))
                if tok >= mo and V2 < M.UNTRADE_V and (w.best is None or (s, i) < w.best[0]):
                    w.best = ((s, i), c, kn, V2, T2, tok, xn, t)
                    w.bver += 1
                    push(c + P.off, "FILL", a, w.bver)
            push(nxt, "TICK", a)
        elif typ == "END":
            w = wins[a]
            if not w.stopped: stop(w, t, w.why_stop)
        elif typ == "FILL":
            w = wins[a]
            if b != w.bver or w.filled: continue
            w.filled = True
            stop(w, t, "filled")
            P = w.P
            (fs, fi), c, kn, Vb, Tb, tok, xn, tsend = w.best
            rng = w.rng
            Dw = float(Ds[rng.integers(nD)])
            cfg = Wd.cfg_t2 if w.kind == "t2" else Wd.cfg_re
            ex = L.exit_walk(P, kn, Tb, tok, int(round(w.size * 1e9)), t, Dw, R.tau, cfg, R, rng, False, fs)
            t_sell = ex["t_dec"] + Dw
            t_close = t_sell + R.C
            acl = float(Wd.ata_clear[rng.integers(len(Wd.ata_clear))])
            m = w.mint
            if npos[0] > 0: stats["double_position"] += 1
            npos[0] += 1; pos_open[m] += 1; pos_close[m] = max(pos_close.get(m, 0.0), t_close)
            ata_until[m] = max(ata_until.get(m, 0.0), t_sell + acl)
            positions.append((t, t_close, w.wid))
            sell_slot = int(ex["c_sell"] // SMS)
            w.res = {"fs": fs, "fi": fi, "t_fill": t, "t_close": t_close, "c_sell": ex["c_sell"], "gross": ex["gross"], "why": ex["why"], "p_entry": (Vb + xn) / (Tb - tok),
                     "sell_slot": sell_slot}
            push(t_close, "CLOSE", a, sell_slot)
        elif typ == "CLOSE":
            w = wins[a]; m = w.mint
            npos[0] -= 1; pos_open[m] -= 1
            free_at[m] = max(free_at.get(m, 0.0), t + MARGIN)
        elif typ == "T2":
            P = a; m = P.mint
            if pos_open[m] > 0 or t < free_at.get(m, 0.0): skips["t2_blocked_position"] += 1; continue
            if t < ata_until.get(m, 0.0): skips["t2_blocked_ata_open"] += 1; continue
            cur = armed.get(m)
            if cur is not None:
                if wins[cur].kind == "t2": skips["t2_blocked_armed"] += 1; continue
                stop(wins[cur], t, "superseded")
            t2_arm_times[m].append(t)
            t_stop, en = L.stop_times(P, Wd.cfg_t2, R)
            new_win("t2", ("t2", P.W["w"]), m, P, Wd.cfg_t2["size"], en, t + cal["first_t2"], t_stop, "t2_stop", t)
            stats["t2_windows"] += 1
        elif typ == "INS":
            cd = a; m = cd["mint"]
            if armed.get(m) is not None: skips["ins_blocked_armed"] += 1; continue
            if Wd.launch_refusal(m): skips["ins_blocked_launch"] += 1; continue
            if block_until(m, t) > t: skips["ins_blocked_position"] += 1; continue
            if cd["t_stop"] <= t + cal["first_t2"]: skips["ins_stopped_before_first_try"] += 1; continue
            P = Wd.window_P(m, cd["tl"], cd["k"], cd["key"], cd["en_slot"], 650_000_000)
            if P is None: skips["ins_no_tape"] += 1; continue
            new_win("ins", cd["key"], m, P, 0.65, cd["en_slot"], t + cal["first_t2"], cd["t_stop"], cd["why"], t, cd)
            stats["ins_windows"] += 1
        elif typ == "CHK":
            cd = a; m = cd["mint"]
            cur = armed.get(m)
            if cur is not None: skips["rearm_blocked_live_armed" if wins[cur].kind == "t2" else ("rearm_blocked_ins_armed" if wins[cur].kind == "ins" else "rearm_blocked_rearm_armed")] += 1; continue
            if Wd.launch_refusal(m): skips["rearm_blocked_launch"] += 1; continue
            if rule.cap is not None and recount[m] >= rule.cap: skips["rearm_cap"] += 1; continue
            bu = block_until(m, t)
            if bu > t:
                stats["rearm_deferred"] += 1
                push(bu, "WAKE", cd, t)
                continue
            arm_rearm(cd, t, False)
        elif typ == "WAKE":
            cd = a; t_chk = b; m = cd["mint"]
            if any(t_chk < x <= t for x in t2_arm_times.get(m, ())): skips["rearm_blocked_superseded_wait"] += 1; continue
            cur = armed.get(m)
            if cur is not None: skips["rearm_blocked_armed_wait"] += 1; continue
            tl = tape.tok(m)
            st = M.stops_while_waiting(tape, tl, rule, A, t_chk, t, cd["check_slot"])
            if st: skips["rearm_wait_" + st[1]] += 1; continue
            if Wd.slot_at(t) > cd["en_slot"]: skips["rearm_wait_expired"] += 1; continue
            if rule.cap is not None and recount[m] >= rule.cap: skips["rearm_cap"] += 1; continue
            bu = block_until(m, t)
            if bu > t + 1e-6: push(bu, "WAKE", cd, t_chk); continue
            arm_rearm(cd, t, True)
    out = []
    for w in wins:
        fails = w.landed - (1 if w.filled else 0)
        r = {"wid": w.wid, "key": w.key, "kind": w.kind, "mint": w.mint, "t_arm": w.t_arm, "end_why": w.end_why, "ticks": w.n, "sent": w.sent, "refused": w.refused,
             "paused": w.paused, "fails": fails, "filled": w.filled, "nth": w.nth, "chained": False,
             "dump_age": (w.cand or {}).get("age"), "n_hold": (w.cand or {}).get("n_hold")}
        if w.kind == "ins":
            r.update({"ins_u": w.cand["u"], "ins_pct": w.cand["pct"], "ins_solo": w.cand["solo"], "s0": w.cand["s0"], "isell_slot": w.cand["isell_slot"]})
        if w.filled:
            x = w.res
            r.update({k: x[k] for k in ("fs", "fi", "t_fill", "t_close", "c_sell", "why", "p_entry", "sell_slot")})
            r["gross_naive"] = x["gross"] / 1e9 - w.size
            recs = Wd.recs(w.mint)
            mi = PA.last_before(recs, (x["fs"], x["fi"], -1)) if recs else None
            if mi is not None:
                vn = PA.value_at(recs, mi, w.size, False, x["c_sell"], tape.maxi, by_cc=True)
                vs = PA.value_at(recs, mi, w.size, True, x["c_sell"], tape.maxi, by_cc=True)
                vc = S.value_cut(recs, mi, w.size, x["c_sell"], tape.maxi, 0.2, S.rng_for(rep, "cut", Wd.run, w.key))
                if vn and vs and vc is not None:
                    r["d_slip"] = vs["gross"] - vn["gross"]; r["d_cut"] = vc - vn["gross"]
                    r["followers"] = vs["followers"]; r["dropped"] = vs["dropped"]
            r.setdefault("d_slip", 0.0); r.setdefault("d_cut", 0.0)
            r["cash_naive"] = r["gross_naive"] - FIX / 1e9 - fails * FAIL / 1e9
        else:
            r["cash_naive"] = -fails * FAIL / 1e9; r["d_slip"] = 0.0; r["d_cut"] = 0.0
        r["cash"] = r["cash_naive"] + r["d_slip"]
        r["cash_cut"] = r["cash_naive"] + r["d_cut"]
        out.append(r)
    meta = {"stats": dict(stats), "skips": dict(skips), "fee_pause_ms": fee_pause[0], "fees_total": fee_sum[0] / 1e9, "n_cands": len(cands), "n_ins_cands": len(icands),
            "hours": (Wd.t_end - Wd.t_start) / 3.6e6, "t_start": Wd.t_start, "t_end": Wd.t_end}
    return out, meta
