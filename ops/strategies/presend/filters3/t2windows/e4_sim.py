#!/usr/bin/env python3
"""T2-WINDOWS step 4b: per candidate, signing-time features + window replays on the raw tape.
Phase 1 (all buckets): the QUIET dump book = every DUMP (curve sell >= 0.3 SOL, curve < 100 SOL, post price <= 0.92 x pre; src/presend_quiet.rs)
  with its followers (distinct buyers but the seller in its slot + the next 2), per seller.
Phase 2 (per bucket):
  * LIVE windows: REAL-TRY replay (real sends, landings, min_out; fill = first landed try in chain order with res 6042/ok, landed by its
    deadline, curve before it >= min_out) -> does it pick the live fill?  + SIM replay (simulated tries, same mechanics) vs live realized.
  * RE-ARM candidates: holders at the end of slot dump + 2 (tape balances), R5 proxy for the largest holder (cohort holding, its dump
    book followers), dip bots on the token before the check / globally in the last 10 min, creator; SIM replays per mechanics.
  * WIDE / T2 triggers: QUIET signals proxy (since_last, cohort holding, whale's dump-book followers), QUIET3-A proxy (trades in 120 s
    <= 15 and whale dumps <= 3), buyers in 50 slots (lone whale), creator; SIM replay (T2 mechanics).
Out: /home/it/sniper-data/filters3/t2windows/sim/b<NN>.pkl         usage: e4_sim.py WORKERS [REPS]"""
import sys, os, pickle, json, zlib, bisect, collections, math
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L

COH = set(json.load(open("/home/it/sniper-data/overnight/sel/cohort_train.json")))
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
BIG = 60_000_000_000_000
DAY_SLOTS = int(24 * 3600 / 0.2135)
G = {}


def is_dump(r):
    if r["cpost"] <= r["cpre"]: return False
    vt0 = r["cpre"] + L.VOFF; vt1 = r["cpost"] + L.VOFF
    sol = L.K / vt0 - L.K / vt1
    if sol < 300_000_000 or L.K / vt0 >= 100e9: return False
    p0 = L.K / vt0 / vt0; p1 = L.K / vt1 / vt1
    return p1 <= 0.92 * p0


def phase1(b):
    tapes = L.load_bucket(b); out = []
    for m, tp in tapes.items():
        rows = tp["rows"]
        for k, r in enumerate(rows):
            if not is_dump(r) or not r["seller"]: continue
            fol = set()
            for x in rows[k + 1:]:
                if x["s"] > r["s"] + 2: break
                if x["cpost"] < x["cpre"] and x["buyer"] and x["buyer"] != r["seller"]: fol.add(x["buyer"])
            out.append((r["seller"], r["s"], len(fol)))
    return out


def init():
    G["maxi"] = pickle.load(open(f"{L.D}/maxi.pkl", "rb")); G["clk"] = L.Clock(G["maxi"])
    P = pickle.load(open(f"{L.D}/prep.pkl", "rb")); G["P"] = P
    G["book"] = pickle.load(open(f"{L.D}/dumpbook.pkl", "rb"))
    bots = pickle.load(open(f"{L.D}/bots.pkl", "rb"))
    G["bot_s"] = np.array(sorted(s for s, i, sg, tb in bots), dtype=np.int64)
    # LEFF mode: the landing pool = L_eff measured on the block clock from the run's real tries of the same kind (e4c_clock.py)
    G["leff"] = {}
    if os.environ.get("T2W_POOL", "raw") == "leff":
        C = pickle.load(open(f"{L.D}/clock.pkl", "rb"))
        for (r, kind), v in C["leff"].items():
            ms = np.array([x for x in v if x is not None and -100 < x < 2000], dtype=np.float64)
            G["leff"][(r, "re" if kind == "rearm" else "t2")] = (ms, sum(1 for x in v if x is None) / max(1, len(v)))


def whale_hist(w, s0):
    v = G["book"].get(w)
    if not v: return -1.0, 0
    lo = bisect.bisect_left(v, (s0 - DAY_SLOTS, -1)); hi = bisect.bisect_left(v, (s0 - 2, -1))
    xs = v[lo:hi]
    if not xs: return -1.0, 0
    return sum(x[1] for x in xs) / len(xs), len(xs)


def bots_glob(s0):
    a = G["bot_s"]; return int(np.searchsorted(a, s0) - np.searchsorted(a, s0 - 2810))


def stop_re(seg, clk, dump, tau0, G_, hth, q):
    E = (dump["slot"] + 3 + G_ + 1) * L.SMS
    for o in seg.out:
        if o[1] >= E: break
        if o[2] == "s" and o[5] >= BIG: E = min(E, o[1] + 30); break
    if q:
        arm = int(tau0 // L.SMS); qcut = (arm + 6) * L.SMS
        n = sum(1 for o in seg.out if tau0 <= o[1] < qcut and o[2] != "n")
        if n < 2: E = min(E, qcut)
    return E


def holder_stop(seg, bal0, hth, E):
    """30 ms after the trade after which no wallet (not ours) holds >= hth % (balances walked from the check)"""
    if hth <= 0: return E
    thr = hth * 1e13
    bal = dict(bal0)
    if not any(v >= thr for v in bal.values()): return -1.0          # no holder at the check: no window
    for o in seg.out:
        if o[1] >= E: break
        for ow, (a, b_) in o[7]["own"].items():
            if ow in L.OURS: continue
            bal[ow] = b_
        if not any(v >= thr for v in bal.values()): return min(E, o[1] + 30)
    return E


def stop_t2(seg, trig, E):
    for o in seg.out:
        if o[1] >= E: break
        if o[4] == trig["wallet"] and o[5] > 0: E = min(E, o[1] + 30); break
    qcut = (trig["slot"] + 5) * L.SMS
    n = sum(1 for o in seg.out if o[1] < qcut and o[2] != "n" and o[4] != trig["wallet"])
    if n < 2: E = min(E, qcut)
    return E


def summ(res, seg, clk, H_list, sin):
    """mean over reps: filled share, curve pnl at each H, fails, mean fill cc"""
    n = len(res); f = [x for x in res if x[0]]
    o = {"p": len(f) / n, "fails": sum(x[4] for x in res) / n}
    if f:
        o["fcc"] = sum(x[2] for x in f) / len(f)
        for j, H in enumerate(H_list):
            v = 0.0
            for x in f:
                sk = max(clk.y2key(x[2] + H), x[1] + 1)
                v += seg.sell_value(x[1], sin, x[3], sk) - sin
            o[f"c{j}"] = v / n               # expected curve pnl per window (filled share included), lamports
        v = 0.0; pos = 0
        for x in f:
            sk = max(clk.y2key(x[2] + H_list[0]), x[1] + 1)
            v += seg.sell_value(x[1], sin, x[3], sk, fewer=True) - sin
        o["c2"] = v / n                      # -20 % followers stress at the run's own exit
        o["pos"] = sum(1 for x in f if seg.sell_value(x[1], sin, x[3], max(clk.y2key(x[2] + H_list[0]), x[1] + 1)) - sin > 0) / len(f)
    else:
        for j in range(len(H_list) + 1): o[f"c{j}"] = 0.0
        o["pos"] = 0.0
    return o


def run_sims(seg, clk, specs, pool, unseen, H_list, seed):
    out = {}
    dr = L.draws(pool, unseen, zlib.crc32(seed.encode()), REPS)
    for name, tau0, E, spend in specs:
        if E is None or E <= tau0: out[name] = {"p": 0.0, "fails": 0.0, "c0": 0.0, "c1": 0.0, "c2": 0.0, "pos": 0.0, "noarm": True}; continue
        res = L.sim(seg, clk, tau0, E, spend, 0.12, None, dr)
        out[name] = summ(res, seg, clk, H_list, L.sol_in_of(spend))
        out[name]["E"] = E - tau0
    return out


def real_replay(seg, clk, c, w):
    """REAL tries of a live window: which try fills (sig) on this tape"""
    fill = None; lf = w.get("fill") or {}
    fk_live = L.key(lf["slot"], lf["idx"]) if lf.get("idx") is not None else None
    landed = []
    for t in w["tries"]:
        Ld = t.get("land") or {}
        if Ld.get("res") in (None, "unseen") or Ld.get("idx") is None: continue
        landed.append((L.key(Ld["slot"], Ld["idx"]), t, Ld))
    landed.sort(key=lambda x: x[0])
    for k, t, Ld in landed:
        ok = Ld["res"] in ("6042", "ok") or (Ld["res"] == "ata_exists" and fk_live is not None and k > fk_live)
        if not ok or Ld["slot"] > (t.get("deadline") or 1e18): continue
        Tl = float(seg.T_before_keys(np.array([k]))[0]); Vl = L.K / Tl
        tok = math.floor(Tl * L.sol_in_of(t["spend"]) / (Vl + L.sol_in_of(t["spend"])))
        if tok >= (t["min_out"] or 0): fill = t["sig"]; break
    return fill


def phase2(b):
    clk = G["clk"]; P = G["P"]; cal = P["cal"]; Hc = P["H_cur"]
    cs = P["cands"].get(b, [])
    if not cs: return b, 0
    tapes = L.load_bucket(b)
    lw = {}
    for r in sorted({c["run"] for c in cs if c["live"]}):
        R = pickle.load(open(f"{L.D}/rec_{r}.pkl", "rb"))
        for w in R["wins"]:
            if L.bucket(w["mint"]) == b: lw[(r, w["ses"], w["w"])] = w
    out = []
    for c in cs:
        r = c["run"]; cr = cal[r]; a = c["anc"]
        tp = tapes.get(c["mint"])
        o = {k: c[k] for k in ("c", "run", "mint", "why", "live", "rec")}
        o["anc"] = {k: a.get(k) for k in ("sig", "slot", "idx", "t", "pct", "sol", "tok", "age_slots", "seller", "wallet", "drop_pct", "vsol", "vtok")}
        o["live_pnl"] = c.get("live_pnl"); o["live_fill"] = c.get("live_fill")
        if not tp or a.get("slot") not in clk.maxi: o["err"] = "no_tape"; out.append(o); continue
        ka = next((k for k, x in enumerate(tp["rows"]) if x["sig"] == a.get("sig")), None)
        if ka is None: o["err"] = "no_anchor"; out.append(o); continue
        rows = tp["rows"]
        if rows[-1]["s"] < a["slot"] + 30: o["err"] = "tape_end"; out.append(o); continue
        seg = L.Seg(tp, ka, clk, 80)
        ca = clk.cc(a["slot"], a["idx"]); o["off"] = a["t"] / 1e6 - ca
        o["creator"] = rows[0]["sg"] if rows[0]["cpre"] == 0 else None
        o["tape_from"] = rows[0]["s"]
        H_list = [cr["H"], Hc]
        if c["c"] == "re":
            s0 = a["slot"]; chk = L.key(s0 + 2, 99999)
            hold = L.holders_at(tp, chk)
            hs = sorted(hold.items(), key=lambda kv: -kv[1])
            o["h"] = [(w, round(v / 1e13, 3)) for w, v in hs[:6] if v >= 1e13]
            top = hs[0][0] if hs else None
            coh = sum(1 for w, v in hold.items() if w in COH and w != top)
            wf, wd = whale_hist(top, s0 + 3) if top else (-1.0, 0)
            o["r5p"] = {"coh": coh, "wh_fol": wf, "wh_dumps": wd, "all4": coh == 0 and wf < 4.0}
            o["seller_cr"] = (a.get("seller") == o["creator"])
            o["bots_tok"] = sorted({L.BOTS[x["sg"]] for x in rows[:ka + 1] if x["sg"] in L.BOTS} | {L.BOTS[ow] for x in rows[:ka + 1] for ow in x["own"] if ow in L.BOTS})
            o["bots_win"] = sorted({L.BOTS[x[7]["sg"]] for x in seg.out if x[7]["sg"] in L.BOTS and x[0] < L.key(s0 + 30, 0)})
            o["bots_glob"] = bots_glob(s0)
            # sims
            rs = cr["re_spend"] or 650000000
            tau0 = (s0 + 3) * L.SMS + cr["d_re"]
            bal0 = {w: v for w, v in hold.items()}
            specs = []
            for (g, hth, q, sp, nm) in [(20, 6, True, rs, "m0"), (20, 3, True, rs, "h3"), (20, 0, True, rs, "h0"), (10, 6, True, rs, "g10"), (30, 6, True, rs, "g30"),
                                        (40, 6, True, rs, "g40"), (10, 0, True, rs, "g10h0"), (30, 0, True, rs, "g30h0"), (20, 6, False, rs, "noq"), (20, 0, False, rs, "h0noq"),
                                        (20, 6, True, 300000000, "s30"), (20, 6, True, 650000000, "s65"), (20, 6, True, 450000000, "s45"), (20, 0, True, 450000000, "h0s45"),
                                        (20, 3, True, 450000000, "h3s45")]:
                E = stop_re(seg, clk, a, tau0, g, hth, q)
                E = holder_stop(seg, bal0, hth, E)
                specs.append((nm, tau0, E if E > 0 else None, sp))
            pl_, un_ = G["leff"].get((r, "re"), (cr["pool"], cr["unseen"]))
            o["sims"] = run_sims(seg, clk, specs, pl_, un_, H_list, a["sig"])
        else:
            s0 = a["slot"]; whale = a.get("wallet")
            kt = L.key(s0, a["idx"])
            prev = [x for x in rows[:ka] if x["cpost"] != x["cpre"]]
            o["since_last"] = (s0 - prev[-1]["s"]) if prev else 9999
            o["n120"] = sum(1 for x in prev if x["s"] >= s0 - 562)
            o["nb50"] = len({x["buyer"] for x in rows[:ka + 1] if x["s"] >= s0 - 49 and x["cpost"] < x["cpre"] and x["buyer"] and x["buyer"] not in L.OURS})
            hold = L.holders_at(tp, rows[ka - 1]["k"] if ka > 0 else -1)
            o["coh"] = sum(1 for w, v in hold.items() if w in COH and w != whale)
            o["wh_fol"], o["wh_dumps"] = whale_hist(whale, s0)
            o["bots_tok"] = sorted({L.BOTS[x["sg"]] for x in rows[:ka + 1] if x["sg"] in L.BOTS})
            sp_own = (cr["spend"] or 550000000)
            tau0 = ca + cr["d_t2"]
            E = stop_t2(seg, a, (s0 + 11) * L.SMS)
            specs = [("own", tau0, E, sp_own), ("cur", tau0, E, 550000000)]
            pl_, un_ = G["leff"].get((r, "t2"), (cr["pool"], cr["unseen"]))
            o["sims"] = run_sims(seg, clk, specs, pl_, un_, H_list, a["sig"])
        if c["live"]:
            w = lw.get((r,) + tuple(c["live"]))
            if w:
                o["real_fill"] = real_replay(seg, clk, c, w)
                o["live_fill_sig"] = (w.get("fill") or {}).get("sig")
                cl = w.get("close") or {}
                o["live_curve"] = cl.get("curve_pnl"); o["live_rounds"] = cl.get("rounds")
                fl = w.get("fill")
                if fl: o["live_fill_t"] = fl["t"]
                sl = cl.get("sell_land")
                if fl and fl.get("idx") is not None and sl and cl.get("rounds") == 1 and fl.get("tokens"):
                    fk = L.key(fl["slot"], fl["idx"]); sk = L.key(sl[0], sl[1]); sin_ = cl.get("sol_in_curve") or fl.get("sol_in")
                    o["live_stress"] = (seg.sell_value(fk, sin_, fl["tokens"], sk, fewer=True) - seg.sell_value(fk, sin_, fl["tokens"], sk)) / 1e9
                o["live_fees"] = sum(1 for t in w["tries"] if (t.get("land") or {}).get("res") not in (None, "unseen") and t["sig"] != (fl or {}).get("sig")) * L.FAIL / 1e9
        out.append(o)
    SD = f"{L.D}/" + os.environ.get("T2W_SIMDIR", "sim"); os.makedirs(SD, exist_ok=True)
    pickle.dump(out, open(f"{SD}/b{b:02d}.pkl", "wb"))
    return b, len(out)


if __name__ == "__main__":
    nw = int(sys.argv[1])
    if not os.path.exists(f"{L.D}/dumpbook.pkl"):
        book = collections.defaultdict(list)
        with Pool(nw) as p:
            for res in p.imap_unordered(phase1, range(L.NB)):
                for w, s, n in res: book[w].append((s, n))
        book = {w: sorted(v) for w, v in book.items()}
        pickle.dump(book, open(f"{L.D}/dumpbook.pkl", "wb"))
        print("dump book sellers", len(book), "dumps", sum(len(v) for v in book.values()), flush=True)
    bs = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else list(range(L.NB))
    with Pool(nw, initializer=init) as p:
        for b, n in p.imap_unordered(phase2, bs):
            print("bucket", b, n, flush=True)
    print("done")
