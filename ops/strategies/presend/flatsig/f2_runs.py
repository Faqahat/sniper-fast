#!/usr/bin/env python3
"""FLATSIG step 2 [MEASURED, read-only]: one streamed pass over a run's engine log -> compact pickle (logic = QUIET4 x1_extract.py,
extended with the trigger's exact chain position (slot, idx), the arm time, and every shadow T2 window with its row-c paper result).
  pos   : every closed LIVE position with its real realized P&L (presend_live_realized) + arm-record fields + our first buy (slot, idx, t)
          + post-hoc tape label (presend_live_tape: other wallets' trades between our first buy and our last sell landing)
  skips : every presend_live_skip (why, kind, trigger slot/idx/t, mint, whale)
  sh    : the shadow's T2 triggers (presend_arm) + row c's paper exit (net_cheap; None = no fill) + row c fill slot/idx
usage: f2_runs.py RUN FILE -> /home/it/sniper-data/flatsig/runs/ex_RUN.pkl"""
import sys, json, pickle, collections, os
OUT = "/home/it/sniper-data/flatsig/runs"


def main(run, fn):
    os.makedirs(OUT, exist_ok=True)
    me = None; cfg = {}; starts = []
    arms = collections.defaultdict(list); closes = []; realized = collections.defaultdict(list)
    tape = collections.defaultdict(dict); fills = {}; skips = []; sh = {}; shc = {}; shf = {}
    for raw in open(fn, "rb"):
        if b'"ev":"presend_' not in raw and b'"ev":"run_start"' not in raw: continue
        if b'"ev":"presend_attempt' in raw or b'"ev":"presend_wide_' in raw or b'"ev":"presend_live_ata' in raw: continue
        try: d = json.loads(raw)
        except Exception: continue
        ev = d["ev"]
        if ev == "run_start":
            me = me or d.get("wallet"); cfg = cfg or (d.get("presend_live") or {}); starts.append(d.get("t"))
        elif ev == "presend_live_arm":
            tr = d.get("trig") or d.get("dump") or {}
            arms[(d.get("mint") or tr.get("mint"), d.get("kind") or "T2", d.get("w"))].append(d)
        elif ev == "presend_live_close": closes.append(d)
        elif ev == "presend_live_realized": realized[(d["mint"], d.get("pid"))].append(d)
        elif ev == "presend_live_tape": tape[d["mint"]][(d["slot"], d["idx"], d.get("j", 0))] = d
        elif ev == "presend_live_fill": fills[(d["mint"], d.get("w"), d.get("kind") or "T2")] = d
        elif ev == "presend_live_skip":
            tr = d.get("trig") or d.get("dump") or {}
            skips.append({"why": d.get("why"), "kind": d.get("kind") or "T2", "t": tr.get("t"), "slot": tr.get("slot"), "idx": tr.get("idx"),
                          "mint": d.get("mint") or tr.get("mint"), "whale": tr.get("wallet") or tr.get("seller"), "pct": tr.get("pct"),
                          "sol": tr.get("sol"), "age": tr.get("age_slots"), "creator": (d.get("ann") or {}).get("creator"),
                          "quiet": d.get("quiet") or d.get("r5"), "f3": d.get("f3"), "v2": d.get("v2"), "w": d.get("w")})
        elif ev == "presend_arm":
            sh[(d["mint"], d["w"])] = {"t": d["t"], "slot": d.get("slot"), "idx": d.get("idx"), "mint": d["mint"], "whale": d.get("wallet"),
                                       "pct": d.get("pct"), "sol": d.get("sol"), "age": d.get("age_slots"), "vsol": d.get("vsol"),
                                       "quiet": d.get("quiet"), "v2": d.get("v2"), "w": d["w"], "c": None, "cfill": None}
        elif ev == "presend_fill" and d.get("row") == "c":
            m = d.get("m") or {}
            shf[(d["mint"], d["w"])] = (m.get("slot"), m.get("idx"), m.get("t"), d.get("seller_is_whale"), m.get("sol"), m.get("user"))
        elif ev == "presend_exit" and d.get("row") == "c":
            shc[(d["mint"], d["w"])] = d.get("net_cheap")
    for k, v in shc.items():
        if k in sh: sh[k]["c"] = v
    for k, v in shf.items():
        if k in sh: sh[k]["cfill"] = v
    used = collections.Counter(); pos = []
    for c in closes:
        key = (c["mint"], c.get("pid")); rl = realized[key][used[key]] if used[key] < len(realized[key]) else None; used[key] += 1
        if rl is None: continue
        kind = c.get("kind") or "T2"; b0 = min(c["buys"], key=lambda b: (b["slot"], b["idx"]))
        arm = None
        for a in arms[(c["mint"], kind, c.get("w"))]:
            if ((a.get("trig") or a.get("dump") or {}).get("t") or 0) <= b0["t"]: arm = a
        if arm is None: continue
        tr = arm.get("trig") or arm.get("dump") or {}
        whale = tr.get("wallet") if kind == "T2" else tr.get("seller")
        excl = {me}
        if kind == "T2" and tr.get("wallet"): excl.add(tr["wallet"])
        for h in arm.get("holders") or []: excl.add(h["w"])
        sl = c.get("sell_lands") or ([c["sell_land"]] if c.get("sell_land") else [])
        endp = max(((x[0], x[1]) for x in sl), default=(b0["slot"] + 3, 1 << 30))
        sell_t = max((x[2] for x in sl if len(x) > 2 and x[2]), default=0)
        first = (b0["slot"], b0["idx"])
        hold = [x for x in tape[c["mint"]].values() if x["user"] != me and first < (x["slot"], x["idx"]) <= endp]
        fol = [(x["slot"], x["idx"], x["user"], x["sol"] / 1e9, x["t"]) for x in hold if x["buy"] and x["user"] not in excl]
        sells = [(x["slot"], x["idx"], x["user"], x["sol"] / 1e9, x["t"]) for x in hold if not x["buy"]]
        fl = fills.get((c["mint"], c.get("w"), kind)) or {}
        ann = arm.get("ann") or {}
        pos.append({"run": run, "t0": tr.get("t") or b0["t"], "arm_t": arm.get("t"), "buy_t": b0["t"], "buy_slot": b0["slot"], "buy_idx": b0["idx"],
                    "known": max(b0["t"] + 3 * 10**9, sell_t), "end": endp, "mint": c["mint"], "kind": kind, "w": c.get("w"), "pid": c.get("pid"),
                    "pnl": rl["pnl"] / 1e9, "fol": fol, "sells": sells, "whale": whale, "trig_pct": tr.get("pct"), "trig_sol": tr.get("sol"),
                    "trig_age": tr.get("age_slots"), "trig_slot": tr.get("slot"), "trig_idx": tr.get("idx"), "trig_vsol": tr.get("vsol"),
                    "creator": ann.get("creator"), "cr_pct": ann.get("cr_pct"), "nb50": ann.get("nb50"), "nb": arm.get("nb"),
                    "quiet": arm.get("quiet") or arm.get("r5"), "v2": arm.get("v2"), "f3": arm.get("f3"), "q4": arm.get("q4"), "tags": arm.get("tags"),
                    "seen": arm.get("seen"), "eqgrp": arm.get("eqgrp"), "arm_holders": arm.get("holders"), "spend": arm.get("spend"),
                    "fill_slot": fl.get("slot"), "fill_idx": fl.get("idx"), "slots_after_trigger": fl.get("slots_after_trigger")})
    pos.sort(key=lambda p: p["t0"])
    pickle.dump({"run": run, "me": me, "cfg": cfg, "starts": starts, "pos": pos, "skips": skips,
                 "sh": sorted(sh.values(), key=lambda x: x["t"])}, open(f"{OUT}/ex_{run}.pkl", "wb"))
    print(run, "positions", len(pos), "net", round(sum(p["pnl"] for p in pos), 3), "skips", len(skips), "shadow", len(sh), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
