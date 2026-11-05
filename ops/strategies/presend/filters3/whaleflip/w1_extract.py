#!/usr/bin/env python3
"""WHALEFLIP step 1 [MEASURED, read-only]: every LIVE pre-send window that FILLED in runs r39..r48 (T2 and re-arm), with all its tries
(presend_attempt + presend_attempt_land), the engine's own crossing trade for the filling try (presend_attempt_land res ok: "x" =
the crossing trade, "d" = the dump, "between"), the fill, realized P&L, close, disarm, and the paper SHADOW's row-c label
(seller_is_whale, as grp/whale_flip.py). Also per run: every landed try's send->first_rx ms (landing delay pool) and its result.
Out: /home/moiz/sniper-data/filters3/whaleflip/fills_rNN.pkl
usage: w1_extract.py RUN [RUN ...]   (RUN = 39..48)"""
import sys, json, pickle, collections
R = "/home/moiz/sniper-data/filters3/runs/r{}.presend.jsonl"
SRC = {47: "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r47.jsonl",
       48: "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/grp/r48.jsonl"}
OUT = "/home/moiz/sniper-data/filters3/whaleflip"
KEEP = (b'"ev":"presend_', b'"ev":"run_start"', b'"ev":"run_end"')
AKEYS = ("t", "slot", "pos", "deadline", "lim", "min_out", "vsol", "vtok", "spend", "n", "path", "client", "tip", "bytes", "cu")
LKEYS = ("res", "slot", "idx", "first_rx", "t_send", "fee", "err", "ms_send_to_first_rx", "send_slot", "deadline", "t")


def scan(run):
    fn = SRC.get(run, R.format(run))
    ses = -1; cfg = []
    arms, atts, lands, fills, real, close, disarm, sells = {}, collections.defaultdict(list), {}, collections.defaultdict(list), collections.defaultdict(int), {}, {}, collections.defaultdict(list)
    sh_w, sh_f = {}, {}
    nreal = collections.Counter()
    with open(fn, "rb") as f:
        for raw in f:
            if not any(k in raw for k in KEEP): continue
            try: r = json.loads(raw)
            except Exception: continue
            e = r.get("ev")
            if e == "run_start":
                ses += 1; cfg.append({k: r.get(k) for k in ("presend_live", "t", "argv", "args") if k in r}); continue
            if e == "run_end": continue
            if ses < 0: ses = 0
            if e == "presend_arm": sh_w[r["sig"]] = (ses, r.get("w")); continue
            if e == "presend_fill":
                if r.get("row", "c") == "c": sh_f.setdefault((ses, r.get("w")), {k: r.get(k) for k in ("seller_is_whale", "m", "d_ms", "slots_after_trigger", "drop_pct", "s_in")})
                continue
            w = r.get("w")
            if e == "presend_live_arm":
                arms[(ses, w)] = {k: r.get(k) for k in ("kind", "mint", "trig", "dump", "holders", "en_slot", "arm_slot", "check_slot", "spend", "lim0", "drop", "k", "quiet", "ann", "gap")}
                arms[(ses, w)]["kind"] = r.get("kind") or "t2"
            elif e == "presend_attempt":
                atts[(ses, w)].append(dict({k: r.get(k) for k in AKEYS}, sig=r["sig"]))
            elif e == "presend_attempt_land":
                d = {k: r.get(k) for k in LKEYS}
                if r.get("res") == "ok":
                    for k in ("x", "d", "between", "after", "n_between", "ms_after_x_a", "ms_after_d_a"): d[k] = r.get(k)
                lands[r["sig"]] = d
            elif e == "presend_live_fill":
                fills[(ses, w)].append({k: r.get(k) for k in ("sig", "slot", "idx", "t", "lim", "min_out", "p_sign", "p_entry_pre", "p_entry_post", "sol_in", "tokens",
                                                                 "slots_after_trigger", "slots_after_send", "ann", "after_exit", "window_open", "n", "path", "client", "mint")})
            elif e == "presend_live_realized":
                real[(ses, w)] += r.get("pnl") or 0; nreal[(ses, w)] += 1
            elif e == "presend_live_close":
                close[(ses, w)] = {k: r.get(k) for k in ("exit_why", "sell_land", "sell_lands", "held_s", "curve_pnl", "rounds", "merged", "land", "buys", "exit_slot", "spend")}
            elif e == "presend_live_disarm":
                disarm[(ses, w)] = {k: r.get(k) for k in ("why", "slot", "t", "filled", "attempts", "armed_ms", "rearm")}
            elif e == "presend_live_sell_land":
                sells[(ses, w)].append({k: r.get(k) for k in ("slot", "idx", "t", "sol", "round", "fee")})
    out = []
    pool = []
    for key, tries in atts.items():
        for a in tries:
            L = lands.get(a["sig"])
            if L and L.get("first_rx") and a.get("t"):
                pool.append((L["res"], (L["first_rx"] - a["t"]) / 1e6, L.get("slot"), a.get("slot")))
    for key, fl in fills.items():
        a = arms.get(key)
        if a is None or key not in nreal: continue
        tries = []
        for x in atts.get(key, []):
            x = dict(x); x["land"] = lands.get(x["sig"]); tries.append(x)
        sh = None
        if a["kind"] == "t2" and a.get("trig"):
            sk = sh_w.get(a["trig"].get("sig"))
            if sk is not None: sh = sh_f.get(sk, "nofill")
        out.append({"run": run, "ses": key[0], "w": key[1], **a, "fills": fl, "tries": tries, "pnl": real[key] / 1e9, "n_real": nreal[key],
                    "close": close.get(key), "disarm": disarm.get(key), "sells": sells.get(key, []), "shadow": sh})
    return out, pool, cfg


if __name__ == "__main__":
    for a in sys.argv[1:]:
        run = int(a)
        o, pool, cfg = scan(run)
        pickle.dump({"fills": o, "pool": pool, "cfg": cfg}, open(f"{OUT}/fills_r{run}.pkl", "wb"))
        k = collections.Counter(x["kind"] for x in o)
        print(f"r{run}: filled windows {len(o)} {dict(k)} pnl {sum(x['pnl'] for x in o):+.3f} landed-try pool {len(pool)} sessions {len(cfg)}", flush=True)
