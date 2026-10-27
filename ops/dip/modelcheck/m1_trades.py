#!/usr/bin/env python3
# MODEL CHECK step 1 (read-only): real dip buys by the target bots (targets.txt) in the day arrays R1..R4, their real lots and
# the model's replays of each one.
#  dip buy = a target wallet's FIRST buy after a dump (sell >= 1 SOL, price move <= -2%, curve < 100 SOL, token >= 5 slots old),
#            landing <= 400 ms after it on the block-position clock (the latest such dump before the buy is its trigger).
#  real lot = exact-amount lot matching (full lot / half lot) else FIFO over the wallet's trades on that token (as ops/haqq/h7).
#  replays (mc_lib.replay = dd1 path() exactly; pump fees in, tx costs out):
#   I_real : the bot's buy removed, "ours" inserted at the same spot with the same SOL, the bot's lot sells removed, ours sold
#            at the same rows (identity check: entry + followers + exit all as the model computes them)
#   I_75   : same entry, our sells at 75 ms into the same slots as the real sells (the model's sell-landing assumption)
#   I_grid : same entry, the model's exit grid (c4, c6_tpnone_sl10, ...), bot's lot sells removed
#   X_grid : EXTRA buyer: ours inserted right before the bot's buy, the bot kept (the paper's situation for a buyer ahead of a
#            bot), model follower rule (random slack); flags whether the model dropped the bot's buy
#  + the model's own row for that dump (dd1 at 0.35 SOL, guard 1.05 via ratio, 35/50/75 ms, c4/c6), pick flags (IMIT1 top4, M2).
# -> /home/moiz/sniper-data/modelcheck/trades_<day>.jsonl.gz       usage: nice python3 -I m1_trades.py R2
import sys, os, json, gzip, zlib, time, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import mc_lib as M
WIN_MS = 400.0; MIN_DUMP = 1e9
TG = [l.strip() for l in open(os.path.join(HERE, "targets.txt")) if l.strip()]
TGU = {zlib.crc32(w.encode()): w for w in TG}

def pick_flags(day):
    """dd1 rows (all hours) -> per dump key: env, IMIT1 top4, M2 pick, in IMIT1 window, near flags, leader, model outputs @0.35"""
    import dd_lib as L, dd20_shadow_eval as D20
    z = np.load(f"{M.DDD}/dd1_{day}_s0.35_g1000.npz"); d = {k: z[k] for k in ("k", "bt", "s", "F", "X", "f1", "st", "ratio", "near_f", "near_a", "lead", "sin")}
    pn = z["pnl"]; d["p4"] = pn[:, :, M.E4].copy(); d["p6"] = pn[:, :, M.E6].copy(); del pn
    Xall = np.concatenate([d["F"], d["X"], d["f1"][:, None]], 1).astype(np.float32)
    f = lambda k: Xall[:, L.FNI[k]]
    env = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    B0 = json.load(open(f"{L.OUT}/m2_v3_reg4_top25.json")); cols = [L.FNI[x] for x in B0["fn"]]
    P, B = D20.bundle_scores(f"{L.OUT}/m2_v3_reg4_top25.json", Xall[:, cols]); thr = float(B["thr_default"])
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any():
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1); bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    a, b = L.WIN[day]; inwin = (bt >= L.pk(a)) & (bt < L.pk(b))
    top4 = env & (d["f1"] >= L.THR["top4"]); m2 = env & (P >= thr)
    out = {}
    for r, k in enumerate(d["k"].tolist()):
        out[k] = dict(env=bool(env[r]), top4=bool(top4[r]), m2=bool(m2[r]), m2s=float(P[r]), win=bool(inwin[r]), nf=bool(d["near_f"][r]), na=bool(d["near_a"][r]),
                      lead=int(d["lead"][r]), age_s=float(f("age_s")[r]), drop=float(f("drop_pct")[r]), since_buy=float(f("since_buy_s")[r]),
                      st=[int(x) for x in d["st"][r]], ratio=[round(float(x), 5) for x in d["ratio"][r]],
                      p4=[round(float(x), 6) for x in d["p4"][r]], p6=[round(float(x), 6) for x in d["p6"][r]], t=int(bt[r]))
    return out

def lots_for(tp, js):
    """exact-amount lot matching over the wallet's trade rows js (local indices, chain order) -> {buy idx: dict(tok, sells[(j, consumed)], rem)}"""
    lots = {}; live = []
    for j in js:
        if tp.B[j]:
            lo = dict(j=j, tok=tp.TK[j], rem=tp.TK[j], sells=[]); lots[j] = lo; live.append(lo); continue
        t = tp.TK[j]; hit = None
        for lo in live:
            if abs(lo["rem"] - t) <= 2: hit = lo; break
        if hit is None:
            for lo in live:
                if abs(lo["tok"] / 2 - t) <= 2 and abs(lo["rem"] - lo["tok"]) <= 2: hit = lo; break
        if hit is not None:
            c = min(t, hit["rem"]); hit["sells"].append((j, c)); hit["rem"] -= c
            if hit["rem"] <= 2: live.remove(hit)
            continue
        rem = t
        for lo in list(live):
            c = min(rem, lo["rem"])
            if c <= 0: continue
            lo["sells"].append((j, c)); lo["rem"] -= c; rem -= c
            if lo["rem"] <= 2: live.remove(lo)
            if rem <= 2: break
    return lots

def main(day):
    t0 = time.time()
    d = M.load_day(day); meta = d["meta"]
    PF = pick_flags(day); print(f"{day}: dd1 rows {len(PF)} ({time.time() - t0:.0f} s)", flush=True)
    uid = d["uid"]; isT = np.isin(uid, np.array(list(TGU), np.int64)) & (d["buy"] == 1)
    toks = np.unique(d["tok"][isT])
    out = gzip.open(f"{M.OUT}/trades_{day}.jsonl.gz", "wt"); nrow = 0; cnt = collections.Counter()
    for ti, t in enumerate(toks.tolist()):
        tp = M.Tape(d, t); o = tp.o; n = tp.n
        mv = d["move"][o:o + n]; age = d["age"][o:o + n]
        dump = [(not tp.B[j]) and tp.SOL[j] >= MIN_DUMP and mv[j] <= -2.0 and tp.V[j] < 100e9 and age[j] >= 5 for j in range(n)]
        byw = collections.defaultdict(list)
        for j in range(n):
            if tp.U[j] in TGU: byw[tp.U[j]].append(j)
        last_dump = -1; seen = set()            # (dump, wallet) already bought
        DJ = [j for j in range(n) if dump[j]]
        di = 0; cur = -1
        lots_cache = {}
        for j in range(n):
            while di < len(DJ) and DJ[di] < j: cur = DJ[di]; di += 1
            if not tp.B[j] or tp.U[j] not in TGU or cur < 0: continue
            j0 = cur; L_ = tp.A[j] - tp.A[j0]
            if L_ > WIN_MS: continue
            u = tp.U[j]; key = (j0, u)
            first = key not in seen; seen.add(key)
            if not first: cnt["add"] += 1; continue
            w = TGU[u]
            if u not in lots_cache: lots_cache[u] = lots_for(tp, byw[u])
            lot = lots_cache[u].get(j)
            if lot is None: cnt["nolot"] += 1; continue
            k = o + j0; pf = PF.get(k)
            # wallet held an open lot at the dump?
            held = any(lo["j"] < j0 and (lo["rem"] > 2 or any(s_ > j0 for s_, _ in lo["sells"])) for lo in lots_cache[u].values())
            # ahead of the bot
            ab = [x for x in range(j0 + 1, j) if tp.B[x]]
            pre_px = tp.V[j - 1] / tp.T[j - 1]; post = tp.V[j0] / tp.T[j0]
            sells = lot["sells"]; closed = lot["rem"] <= 2
            cost = tp.SOL[j] * (1 + tp.FR[j]) / 1e9
            proceeds = sum(c / tp.TK[s_] * tp.SOL[s_] * (1 - tp.FR[s_]) for s_, c in sells) / 1e9
            rem_tok = max(lot["rem"], 0.0)
            mtm = (tp.V[n - 1] * rem_tok / (tp.T[n - 1] + rem_tok)) * (1 - tp.FR[n - 1]) / 1e9 if rem_tok > 2 else 0.0
            row = dict(day=day, m=meta[t]["m"], w=w, k=int(k), jb=int(o + j), s0=tp.S[j0], i0=tp.I[j0], s=tp.S[j], i=tp.I[j], L=round(L_, 2),
                       dslot=tp.S[j] - tp.S[j0], dsol=round(tp.SOL[j0] / 1e9, 4), dmove=round(float(mv[j0]), 2), age_sl=int(age[j0]),
                       curve=round(tp.V[j0] / 1e9, 3), sol=round(tp.SOL[j] / 1e9, 6), tok=tp.TK[j], fr=tp.FR[j], cost=round(cost, 7),
                       ratio=round(pre_px / post, 5), n_ahead=j - j0 - 1, nb_ahead=len(ab), sol_ahead=round(sum(tp.SOL[x] for x in ab) / 1e9, 4),
                       tg_ahead=[TGU[tp.U[x]][:8] for x in ab if tp.U[x] in TGU], pro_ahead=sum(1 for x in ab if tp.U[x] in M.UPRO),
                       held=held, closed=closed, nsell=len(sells), sells=[(tp.S[s_], tp.I[s_], round(c / lot["tok"], 6)) for s_, c in sells],
                       hold_first=(tp.S[sells[0][0]] - tp.S[j]) if sells else None, hold_last=(tp.S[sells[-1][0]] - tp.S[j]) if sells else None,
                       proceeds=round(proceeds, 7), mtm=round(mtm, 7), real=round(proceeds + mtm - cost, 7), pf=pf)
            # ---- replays ----
            rm = {j: None}
            for s_, c in sells: rm[s_] = rm.get(s_, 0.0) + c
            frac = [(s_, c / lot["tok"]) for s_, c in sells]
            try:
                a = M.replay(tp, j0, j_ins=j, Xc=tp.SOL[j], fr_in=tp.FR[j], guard=None, rm=rm, real_sells=frac, want_grid=False)
                if a["status"] != 0: cnt[f"status{a['status']}"] += 1; continue
                row["I_real"] = round(a["real_exit"] - a["cost"], 7) if closed else None
                row["I_q"] = a["q"] / tp.TK[j]; row["I_drop"] = len(a["dropped"])
                b = M.replay(tp, j0, j_ins=j, Xc=tp.SOL[j], fr_in=tp.FR[j], guard=None, rm=rm,
                             slot_sells=[(tp.S[s_], M.SELL_LAT, c / lot["tok"]) for s_, c in sells], want_grid=False)
                row["I_75"] = round(b["slot_exit"] - b["cost"], 7) if closed else None
                # same, but the sell lands first in its slot (0 ms) and late (150 ms)
                b0 = M.replay(tp, j0, j_ins=j, Xc=tp.SOL[j], fr_in=tp.FR[j], guard=None, rm=rm,
                              slot_sells=[(tp.S[s_], 0.0, c / lot["tok"]) for s_, c in sells], want_grid=False)
                b2 = M.replay(tp, j0, j_ins=j, Xc=tp.SOL[j], fr_in=tp.FR[j], guard=None, rm=rm,
                              slot_sells=[(tp.S[s_], 150.0, c / lot["tok"]) for s_, c in sells], want_grid=False)
                row["I_0"] = round(b0["slot_exit"] - b0["cost"], 7) if closed else None
                row["I_150"] = round(b2["slot_exit"] - b2["cost"], 7) if closed else None
                g = M.replay(tp, j0, j_ins=j, Xc=tp.SOL[j], fr_in=tp.FR[j], guard=None, rm=rm, want_grid=True)
                row["I_c4"] = round(g["pnl"][M.E4], 7); row["I_c6"] = round(g["pnl"][M.E6], 7); row["I_sin"] = g["s_in"]
                row["I_c2"] = round(g["pnl"][M.EXI["c2_tpnone_slnone"]], 7); row["I_c9"] = round(g["pnl"][M.EXI["c9_tpnone_slnone"]], 7)
                row["I_c19"] = round(g["pnl"][M.EXI["c19_tpnone_slnone"]], 7)
                x = M.replay(tp, j0, j_ins=j, Xc=tp.SOL[j], fr_in=tp.FR[j], guard=None, rm={}, want_grid=True)
                row["X_c4"] = round(x["pnl"][M.E4], 7); row["X_c6"] = round(x["pnl"][M.E6], 7)
                row["X_botdrop"] = j in x["dropped"]; row["X_ndrop"] = len(x["dropped"])
                # sells of the bot's lot inside the c4 / c6 hold (the extra-buyer credit is lost when the bot sells before us)
                row["bot_sold_by_c4"] = sum(c for s_, c in sells if tp.S[s_] < g["s_in"] + 4 or (tp.S[s_] == g["s_in"] + 4 and tp.A[s_] - tp.S[s_] * M.SMS < M.SELL_LAT)) / lot["tok"]
            except AssertionError:
                cnt["assert"] += 1; continue
            out.write(json.dumps(row, separators=(",", ":")) + "\n"); nrow += 1; cnt["row"] += 1
        if (ti + 1) % 2000 == 0: print(f"  {day}: {ti + 1}/{len(toks)} tokens, {nrow} rows, {time.time() - t0:.0f} s", flush=True)
    out.close()
    print(f"{day}: DONE {nrow} rows {dict(cnt)} ({time.time() - t0:.0f} s)", flush=True)

if __name__ == "__main__":
    main(sys.argv[1])
