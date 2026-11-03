#!/usr/bin/env python3
"""RIVALS85 step 1 [MEASURED on live fills + decoded chain tapes, read-only]: for every LIVE T2 fill of AMS r34..r39:
  the flag (GUARDS d15_if_h1: a wallet other than the T2 whale, not us, held >= 6% of supply at the filling try's signing AND the fill's
  depth = 1 - p_pre / p_sign < 15%; r34..r38 from GUARDS feats.pkl, r39 from the engine's own log "ann.ctx85"),
  the dump = the biggest sell (not ours) between the try's signing position and our landing position,
  every competitor buy after that dump in the dump's slot or the next slot (competitor = the named list (prefix match) or an auto-detected
  pro of r0_pros.py, never us / the dump seller / the T2 whale), before or after our buy (block position),
  and each competitor's outcome = its first sell of that token after its buy: hold, price ratio net of the pump fee (1.25% each way).
Out: /home/moiz/sniper-data/rivals85/fills.pkl
usage: r1_fills.py"""
import json, pickle, sys, bisect, collections, importlib.util
import numpy as np

D = "/home/moiz/sniper-data"
OUT = f"{D}/rivals85"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
NAMED = ["8yYMhuYo", "haqqiUUX", "HkQ7hMjy", "DYXDDrZC", "77shyvx7", "ssssswdk", "sssssDdM", "GKd5EMzR", "DF7eRXHn", "omegoMAe",
         "AEgTuy8L", "EMKY7r6U", "8PgC4ngp", "2VggYpPu", "EprLoV21", "9pQQc1xy", "BUkpShoE", "26yW9pNF", "dKMjeGJ4", "CVPz447t"]
FEE = 0.0125
SLOT_S = 0.2135   # measured mean slot time on these tapes (tab38f: 32.7k slots in 7021 s)


def key(s, i, j=0): return s * 16777216 + i * 64 + j


def load_r39():
    spec = importlib.util.spec_from_file_location("g1", "/home/moiz/sniper/ops/strategies/presend/prevent/guards/g1_fills.py")
    g1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(g1)
    fills, _, _ = g1.scan("AMS", 39, f"{OUT}/r39.jsonl")
    ann = {}
    for l in open(f"{OUT}/r39.jsonl"):
        if '"ev":"presend_live_fill"' in l:
            r = json.loads(l); ann[r["sig"]] = r.get("ann") or {}
    out = []
    for f in fills:
        if f["kind"] != "t2": continue
        a = ann.get(f["sig"], {})
        f["ob6"] = a.get("ob6"); f["depth_eng"] = a.get("depth"); f["flag"] = bool(a.get("ctx85"))
        f["other6"] = (a.get("ob6") or 0) >= 6
        f["sell_land"] = (f.get("close") or {}).get("sell_land") or (f["sells"][0] if f["sells"] else None)
        out.append(f)
    return out


def tape_r39(mints):
    want = set(mints); rows = collections.defaultdict(set)
    for tab in (f"{D}/multiarm/tab39", f"{OUT}/tab39x"):
        T = np.load(f"{tab}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{tab}/ids.json")); gid = {k: i for i, k in enumerate(ids)}
        g = np.array([gid[m] for m in want if m in gid], dtype=np.uint32)
        sel = np.nonzero(np.isin(np.asarray(T["mint"]), g))[0]
        for x in T[sel]:
            rows[ids[int(x["mint"])]].add((int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]))
    return {m: sorted(v) for m, v in rows.items()}


def analyse(f, rows, comp, named_of):
    """one fill: the dump, the competitor buys in the dump's slot + next, their first sells; our own outcome"""
    o = {k: f.get(k) for k in ("run", "mint", "whale", "slot", "idx", "t", "p_sign", "p_pre", "spend", "sol_in", "tokens", "pnl", "flag", "other6", "sell_land", "path", "client", "sat")}
    o["depth"] = 1 - f["p_pre"] / f["p_sign"] if f.get("p_pre") and f.get("p_sign") else None
    o["tape"] = bool(rows)
    if not rows: return o
    keys = [key(r[0], r[1], r[2]) for r in rows]
    L = key(f["slot"], f["idx"], 0)
    li = bisect.bisect_left(keys, L)
    o["ours_on_tape"] = any(rows[x][0] == f["slot"] and rows[x][1] == f["idx"] and rows[x][8] in OURS for x in range(max(0, li - 2), min(len(rows), li + 3)))
    sp = f.get("sign_pos") or [f["slot"] - 2, 0, 0]
    S = key(sp[0], sp[1], sp[2]) + 1
    si = bisect.bisect_left(keys, S)
    sells = [x for x in range(si, li) if not rows[x][3] and rows[x][8] not in OURS]
    if not sells:   # fallback: the last sell (not ours) in the 3 slots before our buy
        sells = [x for x in range(li - 1, -1, -1) if rows[x][0] >= f["slot"] - 3 and not rows[x][3] and rows[x][8] not in OURS][:1]
        o["dump_fallback"] = True
    if not sells: o["dump"] = None; return o
    di = max(sells, key=lambda x: rows[x][4])
    d = rows[di]
    o["dump"] = {"slot": d[0], "idx": d[1], "seller": d[8], "sol": d[4] / 1e9, "is_whale": d[8] == f.get("whale"), "n_sells": len(sells),
                 "sol_all": sum(rows[x][4] for x in sells) / 1e9}
    # all buys after the dump in the dump's slot and the next slot
    end = key(d[0] + 2, 0, 0)
    wbuys = [x for x in range(di + 1, len(rows)) if keys[x] < end and rows[x][3] and rows[x][8] not in OURS]
    o["n_buyers_win"] = len({rows[x][8] for x in wbuys}); o["sol_buyers_win"] = sum(rows[x][4] for x in wbuys) / 1e9
    o["last_slot_on_tape"] = rows[-1][0]
    per = collections.defaultdict(list)
    for x in wbuys:
        u = rows[x][8]
        if u in comp and u != d[8] and u != f.get("whale"): per[u].append(x)
    cts = []
    for u, xs in per.items():
        x0 = xs[0]
        ex = next((y for y in range(x0 + 1, len(rows)) if rows[y][8] == u and not rows[y][3]), None)
        bx = [x for x in xs if ex is None or x < ex]
        bsol = sum(rows[x][4] for x in bx); btok = sum(rows[x][5] for x in bx)
        c = {"w": u, "named": named_of.get(u), "n_buys": len(bx), "sol": bsol / 1e9, "slot": rows[x0][0], "idx": rows[x0][1],
             "before_us": keys[x0] < L, "same_slot_as_dump": rows[x0][0] == d[0], "px": bsol / btok if btok else None}
        if ex is not None and btok:
            e = rows[ex]
            c["exit_slot"] = e[0]; c["exit_idx"] = e[1]; c["hold_slots"] = e[0] - rows[x0][0]
            c["exit_px"] = e[4] / e[5] if e[5] else None
            c["exit_frac"] = e[5] / btok
            if c["exit_px"]:
                c["ratio"] = c["exit_px"] * (1 - FEE) / (c["px"] * (1 + FEE))
                c["pnl_est"] = c["sol"] * (1 + FEE) * (c["ratio"] - 1)
            # did it exit before our sell landed?
            sl = f.get("sell_land")
            c["exit_before_our_sell"] = bool(sl) and key(e[0], e[1], e[2]) < key(sl[0], sl[1], 0)
        else:
            c["censored"] = True
        cts.append(c)
    o["comp"] = cts
    # our own price ratio on the same basis (curve prices, 1.25% each way), from the sell landing(s)
    if f.get("sol_in") and f.get("tokens"):
        o["our_px"] = f["sol_in"] / f["tokens"]
        sl = f.get("sells") or ([f["sell_land"]] if f.get("sell_land") else [])
        so = sum(x[3] for x in sl if x and x[3])
        if so: o["our_ratio_px"] = (so / f["tokens"]) * (1 - FEE) / (o["our_px"] * (1 + FEE))
        if sl and sl[0]: o["our_hold_slots"] = sl[0][0] - f["slot"]
    return o


if __name__ == "__main__":
    P = json.load(open(f"{OUT}/pros.json"))
    pros = set(P["union_pros"])
    # every wallet seen in the fill tapes that matches a named prefix
    feats = pickle.load(open(f"{D}/prevent/guards/feats.pkl", "rb"))
    F = []
    for x in feats:
        if x["run"] in ("A34", "A35", "A36", "A37", "A38") and x["kind"] == "t2":
            y = dict(x)
            y["other6"] = any(u != x["whale"] for u in (x.get("H6_S") or {}))
            dep = 1 - x["p_pre"] / x["p_sign"] if x.get("p_pre") and x.get("p_sign") else None
            y["flag"] = bool(y["other6"] and dep is not None and dep < 0.15)
            F.append(y)
    r39 = load_r39()
    for x in r39: x["run"] = "A39"
    print("fills r34..r38", len(F), "r39 t2", len(r39), flush=True)
    tapes = pickle.load(open(f"{D}/prevent/guards/tapes_fills.pkl", "rb"))
    tapes = {m: v for m, v in tapes.items() if m in {f["mint"] for f in F}}
    tapes.update(tape_r39({f["mint"] for f in r39}))
    allw = set()
    for v in tapes.values():
        for r in v: allw.add(r[8])
    named_of = {}
    for w in allw:
        for p in NAMED:
            if w.startswith(p): named_of[w] = p
    for w in pros:
        for p in NAMED:
            if w.startswith(p): named_of[w] = p
    comp = (pros | set(named_of)) - OURS
    print("named matched", sorted(set(named_of.values())), "missing", sorted(set(NAMED) - set(named_of.values())), "comp set", len(comp), flush=True)
    res = [analyse(f, tapes.get(f["mint"]), comp, named_of) for f in F + r39]
    meta = {"named_full": {p: sorted(w for w, q in named_of.items() if q == p) for p in NAMED}, "n_pros_union": len(pros), "n_comp": len(comp)}
    pickle.dump({"fills": res, "meta": meta}, open(f"{OUT}/fills.pkl", "wb"))
    c = collections.Counter((o["run"], o["tape"], o.get("ours_on_tape"), o.get("dump") is not None) for o in res)
    for k in sorted(c): print(k, c[k])
