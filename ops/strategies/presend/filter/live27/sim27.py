#!/usr/bin/env python3
"""LIVE27: real/sim.py's run() with four additions for the QUIET counterfactual (everything else is sim.run line for line;
the landing, view, exit and cost models are sim.py's, imported unchanged). INFERRED outputs.
  1. Common random numbers: every window draws from its own generator, seeded by (draw seed, the trigger's chain position).
     The same window gets the same donor, the same jitter and the same sell delays in every stream, so the difference between
     two streams is the rule change (and the interactions it causes), not noise.
  2. x['stop_at_d'] (ms after the engine saw the trigger): the live QUIET stop. From then on no try is sent (end 'quiet').
  3. x['nofill_before_d']: tries sent before this d cannot fill (they land as 6042). Used for the 45 windows QUIET stopped:
     live, none of their tries filled before the stop (MEASURED), so every stream keeps that and only the tries after the stop
     are modeled.
  4. qstop=(N, M) and x['qmodel']: the modeled QUIET stop for windows that were not armed live: at d_dec = the chain clock of the
     start of slot trigger + N, minus the trigger's chain clock, plus the measured decision offset x['qdelta'] (live stops), the
     window ends 'quiet' if fewer than M trades by others (not the whale, not us) were seen by then (the view model's seen times).
  5. x['dyn_only']: the static arm checks are skipped (the trigger passed them live) but blocked_armed / blocked_position apply."""
import math, heapq, collections, hashlib
import numpy as np
import lib27  # noqa: F401  (sets rlib.TAB, sys.path)
import sim, rlib
from sim import Win, exit_path, SMS


def wkey(x):
    return int.from_bytes(hashlib.blake2b(f"{x['mint']}:{x['slot']}:{x['idx']}:{x.get('j', 0)}".encode(), digest_size=8).digest(), "little")


def run27(ck, store, wins_in, cfg, landing, model, view, seed, exclude_self=False, qstop=(6, 2), our_id=None, whale_ids=None, shared_rng=None, qdelta_pool=None):
    """shared_rng (regression check only): one generator for every window, in sim.run's call order"""
    paths = [(sim.Bucket(r), sim.Budget(c)) for r, c in cfg.paths]
    glob = sim.Bucket(cfg.global_rate)
    W = []
    for x in wins_in:
        w = Win(); w.trig = x; w.mint = x["mint"]; w.st = x["slot"]; w.ct = ck.cc(x["slot"], x["idx"])
        w.tok = None; w.done = False; w.why = None; w.tries = []; w.fill = None; w.fill_seen_d = math.inf; w.ext = None
        w.rate_skips = collections.Counter(); w.paused = 0; w.armed = False; w.n = 0; w.donor = None
        w.meta = dict(rng=(shared_rng if shared_rng is not None else np.random.default_rng([seed, wkey(x)])), q_dec=None, q_others=None, q_stop=False)
        W.append(w)
    W.sort(key=lambda w: (w.ct, w.trig.get("j", 0)))
    for q, w in enumerate(W): w.ix = q
    heap = []
    pause = {}
    tok_free = {}
    armed_tok = {}
    nxt = 0
    def paused_at(t):
        hit = False
        for k_ in [k_ for k_, (a, b) in pause.items() if b <= t]: del pause[k_]
        for a, b in pause.values():
            if a <= t < b: hit = True
        return hit
    def end(w, why):
        w.done = True; w.why = why
        if armed_tok.get(w.mint) == w.ix: del armed_tok[w.mint]
    def others_seen(w, d):
        """trades after the trigger by others (not the whale, not us) the engine had seen by d (view model)"""
        tk = w.tok; n = int(np.searchsorted(w.seen, d, side="right"))
        wid = w.meta["whale_id"]; c = 0
        for x in range(w.kt + 1, w.kt + 1 + n):
            u = tk.user[x]
            if u != wid and u != our_id: c += 1
        return c
    while nxt < len(W) or heap:
        t_arm = W[nxt].ct + 0.6 if nxt < len(W) else math.inf
        if heap and heap[0][0] < t_arm:
            t, ix = heapq.heappop(heap)
            w = W[ix]
            if w.done: continue
            d = t - w.ct
            lam, _g = landing.at(w.donor, d)
            a_now = w.ct + d
            E = int((a_now - view.eps(int(a_now // SMS) - w.st, w.q) - cfg.slot_lag_ms) // SMS)
            if E > w.en_slot: end(w, "expired"); continue
            if d >= w.stop_d: end(w, "whale_sold"); continue
            if d >= w.fill_seen_d: end(w, "filled"); continue
            x = w.trig
            if x.get("stop_at_d") is not None and d >= x["stop_at_d"]: end(w, "quiet"); continue
            if x.get("qmodel") and w.meta["q_dec"] is None and d >= w.meta["d_dec"]:
                oth = others_seen(w, w.meta["d_dec"])
                w.meta["q_dec"] = w.meta["d_dec"]; w.meta["q_others"] = oth
                if oth < qstop[1]:
                    w.meta["q_stop"] = True; end(w, "quiet"); continue
            k = cfg.kfun(w, E) if cfg.kfun else cfg.k
            heapq.heappush(heap, (t + cfg.slot_ms / max(k, 1), ix))
            w.n += 1
            if k <= 0: continue
            if cfg.one_position and paused_at(t): w.paused += 1; continue
            pb, pc = paths[(w.n + w.ix) % len(paths)]
            if not pb.peek(t): w.rate_skips["rate_path"] += 1; continue
            if not glob.peek(t): w.rate_skips["rate_global"] += 1; continue
            if not pc.try_take(t): w.rate_skips["rate_path_config"] += 1; continue
            pb.take(t); glob.take(t)
            deadline = min(E + cfg.deadline_slots, w.en_slot)
            tk = w.tok
            ks = w.kt + int(np.searchsorted(w.seen, d, side="right"))
            psign = tk.vsol[ks] / tk.vtok[ks]
            lim = psign * (1.0 - cfg.drop)
            tr = dict(n=w.n, d=d, E=E, deadline=deadline, lim=lim, psign=psign)
            if lam is None:
                tr["res"] = "drop"; w.tries.append(tr); continue
            a = max(w.ct + d + lam + cfg.extra_lag_ms, tk.cc[ks] + 1e-3, E * SMS)
            S, I = ck.cc_inv(a)
            tr["S"] = S; tr["I"] = I
            if S > deadline: tr["res"] = "deadline"; w.tries.append(tr); continue
            kb = tk.before(S, I)
            nofill = x.get("nofill_before_d") is not None and d < x["nofill_before_d"]
            if (not nofill) and kb >= 0 and tk.vsol[kb] > 0 and tk.vtok[kb] > 0 and tk.vsol[kb] / tk.vtok[kb] <= lim and tk.vsol[kb] < rlib.UNTRADE_V:
                tr["res"] = "cand"
                if w.fill is None or (S, I) < (w.fill["S"], w.fill["I"]):
                    xk = next((j for j in range(ks + 1, kb + 1) if tk.vsol[j] / tk.vtok[j] <= lim), kb)
                    w.fill = dict(S=S, I=I, kb=kb, n=w.n, d=d, lim=lim, psign=psign, xgap=ck.cc(S, I) - tk.cc[xk])
                    w.fill_seen_d = max(d + 20.0, (ck.cc(S, I) - w.ct) + view.eps(S - w.st, w.q))
                    w.ext = exit_path(ck, tk, w, cfg, model, w.meta["rng"])
                    pause[w.ix] = (w.ct + w.fill_seen_d, w.ext["t_sell"] + 60.0)
                    tok_free[w.mint] = w.ext["t_sell"] + 60.0 + cfg.margin_ms
            else:
                tr["res"] = "6042"
            w.tries.append(tr)
        else:
            w = W[nxt]; nxt += 1
            x = w.trig
            why = None
            if not x.get("force_arm"):
                if not x.get("dyn_only"):
                    if not cfg.create_slot and x["age_slots"] == 0: why = "create_slot"
                    elif x.get("v2") is False: why = "legacy_create"
                    elif x.get("cashback"): why = "non_vanilla"
                    elif cfg.arm_filter is not None and not x.get("null") and not cfg.arm_filter(x): why = "filter"
                if why is None:
                    if w.mint in armed_tok: why = "blocked_armed"
                    elif tok_free.get(w.mint, -1.0) > w.ct: why = "blocked_position"
            if why:
                w.done = True; w.why = "skip:" + why; continue
            w.armed = True
            armed_tok[w.mint] = w.ix
            w.tok = store[w.mint]
            rng = w.meta["rng"]
            w.en_slot = int(math.floor((rlib.arr(x["slot"], x["idx"]) + cfg.live_ms + cfg.window_slots * SMS) / SMS))
            if exclude_self:
                w.donor = landing.pick(rng, (w.ct / SMS) % 1.0, exclude_keys={(x.get("probe"), x.get("w"))}, exclude_mint=x["mint"])
            else:
                w.donor = landing.pick(rng, (w.ct / SMS) % 1.0, exclude_mint=x["mint"])
            tk = w.tok
            w.kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
            w.q = w.donor["q"]
            w.seen = view.seen_times(tk, w.kt, w.st, w.ct, w.q)
            w.meta["whale_id"] = (whale_ids or {}).get(x.get("whale_b58"), -1)
            if x.get("qmodel"):
                if qdelta_pool is not None:       # the measured decision offset, drawn per window from its own side generator
                    qd = float(qdelta_pool[int(np.random.default_rng([seed, wkey(x), 7]).integers(len(qdelta_pool)))])
                else: qd = x.get("qdelta", 0.0)
                w.meta["d_dec"] = (w.st + qstop[0]) * SMS - w.ct + qd
            ws = x.get("whale_sell")
            if ws is not None:
                kw = tk.before(ws[0], ws[1] + 0.5)
                if kw > w.kt and tk.pos[kw] == (ws[0], ws[1]): sd = w.seen[kw - w.kt - 1]
                else: sd = max(ck.cc(ws[0], ws[1]) - w.ct + view.eps(ws[0] - w.st, w.q), 0.0)
                w.stop_d = sd + cfg.whale_sell_ms
            else: w.stop_d = math.inf
            heapq.heappush(heap, (w.ct + cfg.live_ms + 0.5 + float(rng.random()) * 0.5, w.ix))
    return [finish27(w, cfg) for w in W]


def finish27(w, cfg):
    r = sim.finish(w, cfg)
    r["q_dec"] = w.meta.get("q_dec"); r["q_others"] = w.meta.get("q_others"); r["q_stop"] = w.meta.get("q_stop")
    if w.armed:
        fill = w.fill
        nofill_d = w.trig.get("nofill_before_d")
        stop_d = w.trig.get("stop_at_d")
        # fees of tries sent after the live stop (the stop's saving) and before it
        cut = nofill_d if nofill_d is not None else stop_d
        if cut is not None:
            landed = [t for t in w.tries if t["res"] != "drop" and (fill is None or t["n"] != fill["n"])]
            r["fees_after"] = sum(cfg.cost.fail_fee for t in landed if t["d"] >= cut)
            r["fees_before"] = sum(cfg.cost.fail_fee for t in landed if t["d"] < cut)
            r["sent_after"] = sum(1 for t in w.tries if t["d"] >= cut)
        r["sas"] = collections.Counter(min(t["S"] - t["E"], 2) for t in w.tries if t["res"] != "drop" and "S" in t)
    return r
