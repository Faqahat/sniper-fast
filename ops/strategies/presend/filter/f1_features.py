#!/usr/bin/env python3
"""PRESEND FILTER, step 4: one row per armed live window of every studied run (never r26): its measured value, labels and
DECISION-TIME features. Writes /home/moiz/sniper-data/presend_filter/windows.json

KNOWABLE-WHEN (the rule for every feature; checked in check_time.py):
  ARM features use only chain rows strictly before the trigger tx in chain order (slot, idx, j), plus the trigger itself (it is the
  arm's cause: the arm record's trig). Chain-wide histories (whale / creator / bots) use only events whose whole outcome window ended
  in a slot before the trigger slot (event slot + 12 < trigger slot), or rows in earlier slots.
  ONCHAIN features (marked oc_) are the curve state our try executes on: the program can check them (an assertion), the engine cannot
  know them in advance.
  LABELS (marked y_) use trades after our buy: never used by a rule."""
import json, sys, time, collections, bisect
import numpy as np
from chainlib import Chain, B, SUPPLY
import lv, feat

RUNS = list(lv.RUNFILES)
OURS = set(lv.WALLET.values())


def main():
    t0 = time.time()
    C = Chain(); C.user_index()
    c = C.c
    S, I, J, BUY, SOL, TOK, VS, VT, U, BT, CUP, TIP, PROG, SIG = (c[k] for k in ("s", "i", "j", "buy", "sol", "tok", "vsol", "vtok", "user", "bt", "cup", "tip", "prog", "signer"))
    cr = json.load(open(f"{B}/creates.json"))
    E = np.load(f"{B}/events.npz")
    our_fail = {k: v[2] for k, v in json.load(open(f"{B}/our_fails.json")).items()}
    coh = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
    cohid = {C.wid[w] for w in coh if w in C.wid}
    # follower-bot list FROZEN before every studied run: follow-buys with bt < 10-25 22:00 PKT (1792948200)
    FROZEN = 1792948200
    fw, fm, fbt = E["fo_w"], E["fo_m"], E["fo_bt"]
    m = fbt < FROZEN
    cnt = collections.Counter(fw[m].tolist())
    toks = collections.defaultdict(set)
    for w, mk in zip(fw[m].tolist(), fm[m].tolist()): toks[w].add(mk)
    # each wallet's buys in the same period (for the share of follow-buys)
    nb_all = collections.Counter(U[(BUY == 1) & (BT < FROZEN)].tolist())
    fbots = {w for w, n in cnt.items() if n >= 20 and len(toks[w]) >= 10 and n / max(nb_all[w], 1) >= 0.2}
    print("follower bots (frozen before 10-25 22:00):", len(fbots), "| in cohort_train:", len(fbots & cohid), flush=True)
    # creator launch history
    cre_list = collections.defaultdict(list)
    for mint, x in cr.items(): cre_list[x["creator"]].append(x["slot"])
    for v in cre_list.values(): v.sort()
    # T2-like events by wallet (chain-wide)
    ev_by_w = collections.defaultdict(list)
    for k in range(len(E["tr_w"])): ev_by_w[int(E["tr_w"][k])].append(k)
    du_by_w = collections.defaultdict(list)
    for k in range(len(E["du_w"])): du_by_w[int(E["du_w"][k])].append(k)
    du_by_m = collections.defaultdict(list)
    for k in range(len(E["du_m"])): du_by_m[int(E["du_m"][k])].append(k)
    FX = feat.Ctx(C)
    out = []
    for run in RUNS:
        R = lv.load(run)
        Ws = lv.windows(R, our_failed=our_fail)
        region = run.split(":")[0]
        for x in Ws:
            tr = x["trig"]; mint = tr["mint"]
            rows = C.mint_rows(mint)
            row = dict(run=run, region=region, seg=x["seg"], w=x["w"], mint=mint, t=x["arm_t"], trig_slot=tr["slot"], trig_idx=tr["idx"], en_slot=x["en_slot"],
                       n_att=x["n_att"], fail_fee=x["fail_fee"], n_fail=x["n_fail"], filled=x["filled"], spend=x["spend"],
                       disarm_why=(x["disarm"] or {}).get("why"), age=tr["age_slots"], pct=tr["pct"], whale_sol=tr["sol"] / 1e9, vsol=tr["vsol"] / 1e9, whale=tr["wallet"])
            if x["filled"]:
                f = x["fill"]; cl = x["close"] or {}
                sl = cl.get("sell_lands") or ([cl["sell_land"]] if cl.get("sell_land") else [])
                sell = max((tuple(z[:2]) for z in sl), default=None)
                fa = x.get("fill_att") or {}
                row.update(net=x["net"], realized=x["realized"], rent_back=x["rent_back"], fill_slot=f["slot"], fill_idx=f["idx"], fill_t=f["t"],
                           fill_send_t=fa.get("t"), fill_send_slot=fa.get("slot"), fill_n=f.get("n"), slots_after_trigger=f.get("slots_after_trigger"),
                           exit_why=(x["exit"] or {}).get("why"), sell_pos=sell, client=f.get("client"),
                           oc_depth=1 - f["p_entry_pre"] / f["p_sign"] if f.get("p_sign") else None, oc_p_pre=f.get("p_entry_pre"))
            k = C.find(rows, tr["slot"], tr["idx"], tr.get("j", 0)) if len(rows) else None
            row["chain_ok"] = k is not None
            if k is None:
                out.append(row); continue
            whale = C.wid.get(tr["wallet"])
            feat.arm_feats(FX, rows, k, whale, mint, tr["slot"], row)
            S, BUY, SOL, U = C.c["s"], C.c["buy"], C.c["sol"], C.c["user"]; fbots = FX.fbots
            # ---- labels (after our buy): trades by others between our buy and our sell
            if x["filled"] and row.get("sell_pos"):
                fs, fi = row["fill_slot"], row["fill_idx"]; ss, si = row["sell_pos"]
                kb = C.before(rows, fs, fi, 0); ke = C.before(rows, ss, si, 0)
                mid = rows[kb:ke]
                mid = mid[~np.isin(U[mid], [C.wid.get(w) for w in OURS if w in C.wid])]
                row["y_nb"] = int(len(mid)); row["y_nbuy"] = int(BUY[mid].sum())
                row["y_buy_sol"] = float(SOL[mid][BUY[mid] == 1].sum()) / 1e9
                row["y_fb_buy"] = len(set(w_ for w_, b_ in zip(U[mid].tolist(), BUY[mid].tolist()) if b_ and w_ in fbots))
                # the dump our try filled behind: the trade just before our buy (ONCHAIN: its effect on the curve is visible to the program)
                if kb > 0:
                    d = rows[kb - 1]
                    row["y_dump_sol"] = float(SOL[d]) / 1e9; row["y_dump_is_whale"] = int(U[d] == whale); row["y_dump_buy"] = int(BUY[d])
            out.append(row)
        print(run, len(Ws), f"{time.time() - t0:.0f}s", flush=True)
    json.dump(out, open(f"{B}/windows.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("rows", len(out), "chain matched", sum(1 for r in out if r["chain_ok"]))


if __name__ == "__main__":
    main()
