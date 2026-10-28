#!/usr/bin/env python3
"""REARM replay core (read-only, offline). The pre-send replay of presend/density/dsim.run_d (itself presend/real/sim.run: donor
transplant landing, the engine's view of the chain, k tries per pace slot, the three rate limiters, one position, the window rules,
TP/SL + 2-slot exit with the follower-slippage model, every cost) with these additions, all INFERRED engine behaviour unless
marked MEASURED:
  1. window kinds: 't2' = the live T2 whale-buy window (unchanged); 're' = the RE-ARM window: armed at the chain clock of slot
     dump+3 (the paid check needs the trades through slot dump+2), its last engine slot = dump + 3 + G, stopped 30 ms after the
     engine sees the token's next whale dump (a single sell >= 6% of supply), its own k (tries per pace slot).
  2. donor wrap: a re window outlives the 10-slot donor windows; past the donor's last try the landing pattern repeats with a
     10-slot period (keeps the slot phase).
  3. QUIET stop (live --presend-live-quiet-stop 6:2) for both kinds: once the engine's slot reaches trigger slot + 6 with < 2 trades
     by other wallets seen (t2: not the whale; re: anyone), the window is disarmed.
  4. dip19 token-account block (MEASURED: our ATA is closed a median 5 slots after the fill, p90 6, r28/r33/FRA r26): no window
     arms on a token until fill slot + 5 (and our sell + 300 ms). A re window that meets the block arms when it ends (its last
     slot unchanged); a t2 trigger is skipped (as live).
  5. a t2 trigger on a token with an armed re window takes the token over (the re window ends 'superseded'); a re window on a token
     with an armed t2 window is skipped ('blocked_armed') (one armed window per token, as the engine).
  6. per fill, besides the live exit: the same fill under 10% / 20% fewer later buyers and under the short WAVE exit (analyst C:
     from 150 ms after our fill, sell at the first 150 ms with no outside buy, at most 1 s; sell lands after the measured TP/SL
     decision->land delay). Gross = SOL out after pump's fee - size (no tx costs); costs are added by the caller.
Decisions (arm / skip / try / fill / exit / disarm) are logged per window when log=True."""
import math, heapq, collections, hashlib, copy, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/density")
import sim, rlib, dsim
from sim import Win, SMS

PERIOD = 10 * SMS
ATA_SLOTS = 5            # MEASURED median fill -> ATA close (slots)


def wkey(x):
    return int.from_bytes(hashlib.blake2b(f"{x['kind']}:{x['mint']}:{x['slot']}:{x['idx']}:{x.get('j', 0)}".encode(), digest_size=8).digest(), "little")


def land_at(landing, donor, d):
    """donor landing with the 10-slot wrap past its last try"""
    dm = donor["dmax"]
    if d > dm:
        d = d - PERIOD * math.ceil((d - dm) / PERIOD)
    return landing.at(donor, d), landing.nearest(donor, d)


def exit_x(ck, tk, w, cfg, model, rng, cut=0.0, mode="time"):
    """sim.exit_path with: follower cut, the wave exit; returns gross (out - size), why, t_sell, sell slot"""
    f = w.fill; kb = f["kb"]
    v = tk.vsol[kb]; t = tk.vtok[kb]; fr = tk.fr[kb]
    q, x = sim.buy_tokens(v, t, cfg.size, fr)
    v += x; t -= q
    S_in = f["S"]; I_in = f["I"]; c_in = ck.cc(S_in, I_in)
    why = "time"
    if mode == "time":
        t_time = (S_in + cfg.exit_slots) * SMS
        t_sell = t_time + model.sell_time[int(rng.integers(len(model.sell_time)))]
        t_dec = t_time + 40.0
    else:
        t_dec = None; t_sell = c_in + 1000.0 + model.sell_tpsl[int(rng.integers(len(model.sell_tpsl)))]
        last_buy = c_in
    frs = fr
    k = kb + 1
    while k < tk.n and tk.cc[k] < t_sell:
        if tk.pos[k] < (S_in, I_in): k += 1; continue
        if mode == "wave" and t_dec is None:
            # the decision: the first moment >= fill + 150 ms with no outside buy in the last 150 ms (checked before applying trade k)
            g0 = min(max(c_in + 150.0, last_buy + 150.0), c_in + 1000.0)
            if tk.cc[k] > g0:
                t_dec = g0; why = "wave"
                t_sell = min(t_sell, t_dec + model.sell_tpsl[int(rng.integers(len(model.sell_tpsl)))])
                if tk.cc[k] >= t_sell: break
        if tk.buy[k]:
            sol = tk.sol[k]; dtk = (t * sol) // (v + sol)
            if dtk < tk.tok[k] / (1.0 + sim.slack_of(tk.sigh[k])):
                k += 1; continue
            if cut > 0 and rng.random() < cut:
                k += 1; continue
            v += sol; t -= dtk
            if mode == "wave": last_buy = tk.cc[k]
        else:
            tkn = tk.tok[k]; so = (v * tkn) // (t + tkn); v -= so; t += tkn
        frs = tk.fr[k]
        if why in ("time",) or (mode == "wave" and t_dec is None):
            if mode == "time" and tk.cc[k] >= t_dec: k += 1; continue
            val = sim.sell_out(v, t, q) * (1.0 - frs) / cfg.size
            if (cfg.tp > 0 and val >= 1.0 + cfg.tp) or (cfg.sl > 0 and val <= 1.0 - cfg.sl):
                why = "tp" if val >= 1.0 + cfg.tp else "sl"
                t_new = tk.cc[k] + model.sell_tpsl[int(rng.integers(len(model.sell_tpsl)))]
                t_sell = min(t_sell, t_new)
                if mode == "wave": t_dec = tk.cc[k]
        k += 1
    if mode == "wave" and t_dec is None:
        # no trade after the gap opened: the decision is at fill + 150 ms (or 150 ms after the last buy)
        t_dec = min(max(c_in + 150.0, last_buy + 150.0), c_in + 1000.0); why = "wave"
        t_sell = min(t_sell, t_dec + 60.0)
    out = sim.sell_out(v, t, q)
    net_out = int(out * (1.0 - frs))
    return dict(gross=net_out - cfg.size, why=why, t_sell=t_sell, sell_S=ck.cc_inv(t_sell)[0], tokens=q, out=net_out, x_in=x)


def run_x(ck, store, wins_in, cfg, landing, model, view, seed, pm, log=False):
    """wins_in: trigger dicts (kind 't2' or 're'); see the module doc. Returns one result dict per window."""
    pnames = sorted({p for v in cfg.routes.values() for p in v})
    buckets = {p: (sim.Bucket(cfg.path_rate), sim.Budget(cfg.path_rate)) for p in pnames}
    glob = sim.Bucket(cfg.global_rate)
    W = []
    for x in wins_in:
        w = Win(); w.trig = x; w.mint = x["mint"]; w.st = x["slot"]; w.ct = ck.cc(x["slot"], x["idx"])
        w.tok = None; w.done = False; w.why = None; w.tries = []; w.fill = None; w.fill_seen_d = math.inf; w.ext = None
        w.rate_skips = collections.Counter(); w.paused = 0; w.armed = False; w.n = 0; w.donor = None
        w.meta = dict(rng=np.random.default_rng([seed, wkey(x)]), log=[] if log else None, k=x.get("k", cfg.k), t_arm=None)
        W.append(w)
    W.sort(key=lambda w: (w.ct, w.trig.get("j", 0)))
    for q, w in enumerate(W): w.ix = q
    arms = [(w.ct, w.ix) for w in W]; heapq.heapify(arms)
    heap = []; pause = {}; tok_free = {}; armed_tok = {}
    max_pos = getattr(cfg, "max_pos", 1)
    qs = getattr(cfg, "quiet_stop", None)

    def paused_at(t):
        for k_ in [k_ for k_, (a, b) in pause.items() if b <= t]: del pause[k_]
        return sum(1 for a, b in pause.values() if a <= t < b) >= max_pos

    def lg(w, **r):
        if w.meta["log"] is not None: w.meta["log"].append(r)

    def end(w, why, t=None):
        w.done = True; w.why = why
        if armed_tok.get(w.mint) == w.ix: del armed_tok[w.mint]
        lg(w, ev="disarm", why=why, t=t)

    while arms or heap:
        t_arm = arms[0][0] + 0.6 if arms else math.inf
        if heap and heap[0][0] < t_arm:
            t, ix = heapq.heappop(heap)
            w = W[ix]
            if w.done: continue
            d = t - w.ct
            (lam, _g), jn = land_at(landing, w.donor, d)
            a_now = w.ct + d
            E = int((a_now - view.eps(int(a_now // SMS) - w.st, w.q) - cfg.slot_lag_ms) // SMS)
            if E > w.en_slot: end(w, "expired", t); continue
            if d >= w.stop_d: end(w, "whale_sold", t); continue
            if d >= w.fill_seen_d: end(w, "filled", t); continue
            if qs is not None and E >= w.st + qs[0] and not w.meta.get("q_ok"):
                ks_ = w.kt + int(np.searchsorted(w.seen, d, side="right"))
                n_oth = int(w.meta["qmask"][:max(ks_ - w.kt, 0)].sum())
                if n_oth < qs[1]: end(w, "quiet", t); continue
                w.meta["q_ok"] = True
            k = w.meta["k"]
            heapq.heappush(heap, (t + cfg.slot_ms / max(k, 1), ix))
            w.n += 1
            if cfg.one_position and paused_at(t): w.paused += 1; continue
            client = w.donor["cl"][jn]; near = w.donor["near"][jn]
            rs = cfg.routes.get(dsim.CLASS.get(client, "default")) or cfg.routes["default"]
            path = rs[(w.n + w.ix) % len(rs)]
            pb, pc = buckets[path]
            if not pb.peek(t): w.rate_skips["rate_path"] += 1; continue
            if not glob.peek(t): w.rate_skips["rate_global"] += 1; continue
            if not pc.try_take(t): w.rate_skips["rate_path_config"] += 1; continue
            pb.take(t); glob.take(t)
            deadline = min(E + cfg.deadline_slots, w.en_slot)
            tk = w.tok
            ks = w.kt + int(np.searchsorted(w.seen, d, side="right"))
            psign = tk.vsol[ks] / tk.vtok[ks]
            lim = psign * (1.0 - cfg.drop)
            tr = dict(n=w.n, d=d, E=E, deadline=deadline, lim=lim, psign=psign, path=path)
            if lam is None:
                tr["res"] = "drop"; w.tries.append(tr); lg(w, ev="try", t=t, n=w.n, res="drop", lim=lim, psign=psign, E=E); continue
            lam = lam + pm.delta(path, client, near, w.donor["u"][jn], cfg.path_scale, cfg.far_too)
            a = max(w.ct + d + lam + cfg.extra_lag_ms + (getattr(cfg, "re_lag_ms", 0.0) if w.trig["kind"] == "re" else 0.0), tk.cc[ks] + 1e-3, E * SMS)
            S, I = ck.cc_inv(a)
            tr["S"] = S; tr["I"] = I
            if S > deadline:
                tr["res"] = "deadline"; w.tries.append(tr); lg(w, ev="try", t=t, n=w.n, res="deadline", lim=lim, psign=psign, E=E, S=S, I=I); continue
            kb = tk.before(S, I)
            if getattr(cfg, "guard", False) and (cfg.guard is True or cfg.guard == "all" or (cfg.guard == "re" and w.trig["kind"] == "re")):
                # G2 holder guard (an on-chain assertion on the whale's token account, e.g. Lighthouse): the buy only executes after the
                # whale's sale (t2: the trigger whale's first sell; re: the token's next whale dump); before it the attempt fails and pays
                gp = w.trig.get("whale_sell") if w.trig["kind"] == "t2" else w.trig.get("guard")
                if gp is None or (S, I) < (gp[0], gp[1]):
                    tr["res"] = "guard"; w.tries.append(tr); lg(w, ev="try", t=t, n=w.n, res="guard", lim=lim, psign=psign, E=E, S=S, I=I); continue
            if kb >= 0 and tk.vsol[kb] > 0 and tk.vtok[kb] > 0 and tk.vsol[kb] / tk.vtok[kb] <= lim and tk.vsol[kb] < rlib.UNTRADE_V:
                tr["res"] = "cand"
                if w.fill is None or (S, I) < (w.fill["S"], w.fill["I"]):
                    xk = next((j for j in range(ks + 1, kb + 1) if tk.vsol[j] / tk.vtok[j] <= lim), kb)
                    w.fill = dict(S=S, I=I, kb=kb, xk=xk, n=w.n, d=d, lim=lim, psign=psign, xgap=ck.cc(S, I) - tk.cc[xk], path=path,
                                  p_pre=tk.vsol[kb] / tk.vtok[kb])
                    w.fill_seen_d = max(d + 20.0, (ck.cc(S, I) - w.ct) + view.eps(S - w.st, w.q))
                    rng = w.meta["rng"]
                    base = exit_x(ck, tk, w, cfg, model, rng, 0.0, "time")
                    w.ext = dict(base=base, cut10=exit_x(ck, tk, w, cfg, model, rng, 0.1, "time"), cut20=exit_x(ck, tk, w, cfg, model, rng, 0.2, "time"),
                                 wave=exit_x(ck, tk, w, cfg, model, rng, 0.0, "wave"), wave10=exit_x(ck, tk, w, cfg, model, rng, 0.1, "wave"),
                                 wave20=exit_x(ck, tk, w, cfg, model, rng, 0.2, "wave"))
                    t_sell = base["t_sell"]
                    pause[w.ix] = (w.ct + w.fill_seen_d, t_sell + 60.0)
                    tok_free[w.mint] = max(t_sell + 60.0 + cfg.margin_ms, (S + ATA_SLOTS + 1) * SMS)
            else:
                tr["res"] = "6042"
            w.tries.append(tr)
            lg(w, ev="try", t=t, n=w.n, res=tr["res"], lim=lim, psign=psign, E=E, S=S, I=I, p_land=(tk.vsol[kb] / tk.vtok[kb] if kb >= 0 else None), path=path)
        else:
            ta, ix = heapq.heappop(arms)
            w = W[ix]
            if w.done or w.armed: continue
            x = w.trig
            why = None
            if x["kind"] == "t2":
                if not cfg.create_slot and x["age_slots"] == 0: why = "create_slot"
                elif x.get("v2") is False: why = "legacy_create"
                elif x.get("cashback"): why = "non_vanilla"
                elif w.mint in armed_tok:
                    o = W[armed_tok[w.mint]]
                    if o.trig["kind"] == "re" and getattr(cfg, "t2_over_re", True): end(o, "superseded", ta)
                    else: why = "blocked_armed"
                if why is None and tok_free.get(w.mint, -1.0) > ta: why = "blocked_position"
            else:
                if w.mint in armed_tok: why = "blocked_armed"
                elif tok_free.get(w.mint, -1.0) > ta:
                    # the re-arm waits for the block to clear (its last slot unchanged)
                    tf = tok_free[w.mint]
                    if tf // SMS < x["en"]:
                        heapq.heappush(arms, (tf + 1.0, ix)); lg(w, ev="arm_wait", t=ta, until=tf); continue
                    why = "blocked_position"
            if why:
                w.done = True; w.why = "skip:" + why; lg(w, ev="skip", t=ta, why=why); continue
            w.armed = True
            armed_tok[w.mint] = w.ix
            w.tok = store[w.mint]
            rng = w.meta["rng"]
            t0 = max(ta, w.ct)
            if x["kind"] == "t2":
                w.en_slot = int(math.floor((rlib.arr(x["slot"], x["idx"]) + cfg.live_ms + cfg.window_slots * SMS) / SMS))
            else:
                w.en_slot = int(x["en"])
            w.donor = landing.pick(rng, (w.ct / SMS) % 1.0, exclude_mint=x["mint"])
            tk = w.tok
            w.kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
            w.q = w.donor["q"]
            w.seen = view.seen_times(tk, w.kt, w.st, w.ct, w.q)
            if qs is not None:
                us = np.array(tk.user[w.kt + 1:], dtype=np.int64)
                ex = x.get("whale_id", -1) if x["kind"] == "t2" else -2
                w.meta["qmask"] = (us != ex)
            ws = x.get("whale_sell")
            if ws is not None:
                kw = tk.before(ws[0], ws[1] + 0.5)
                if kw > w.kt and tk.pos[kw] == (ws[0], ws[1]): sd = w.seen[kw - w.kt - 1]
                else: sd = max(ck.cc(ws[0], ws[1]) - w.ct + view.eps(ws[0] - w.st, w.q), 0.0)
                w.stop_d = sd + cfg.whale_sell_ms
            else: w.stop_d = math.inf
            w.meta["t_arm"] = t0
            lg(w, ev="arm", t=t0, en_slot=w.en_slot, stop_d=(None if w.stop_d == math.inf else w.stop_d), psign0=tk.vsol[w.kt] / tk.vtok[w.kt])
            heapq.heappush(heap, (t0 + cfg.live_ms + 0.5 + float(rng.random()) * 0.5, w.ix))
    return [finish_x(w, cfg) for w in W]


def finish_x(w, cfg):
    r = dict(ix=w.ix, mint=w.mint, trig=w.trig, armed=w.armed, why=w.why, log=w.meta["log"])
    if not w.armed: return r
    fill = w.fill
    landed = [t for t in w.tries if t["res"] != "drop"]
    nfail = sum(1 for t in landed if fill is None or t["n"] != fill["n"])
    r.update(sent=len(w.tries), landed=len(landed), nfail=nfail, fees=nfail * cfg.cost.fail_fee, rate=sum(w.rate_skips.values()), paused=w.paused,
             filled=fill is not None, deadline=sum(1 for t in w.tries if t["res"] == "deadline"), why=w.why or "open", t_arm=w.meta["t_arm"])
    if fill is not None:
        r.update(fill_S=fill["S"], fill_I=fill["I"], fill_d=fill["d"], xk=fill["xk"], lim=fill["lim"], psign=fill["psign"], p_pre=fill["p_pre"], path=fill["path"],
                 ex={k: dict(gross=v["gross"], why=v["why"], sell_S=v["sell_S"], tokens=v["tokens"], out=v["out"], x_in=v["x_in"]) for k, v in w.ext.items()})
    return r
