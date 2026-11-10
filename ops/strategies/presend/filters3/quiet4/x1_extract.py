#!/usr/bin/env python3
"""QUIET4 step 1 [MEASURED, read-only]: one streamed pass over a run's pre-send records -> compact pickle.
  pos   : every closed LIVE position with its real realized P&L (presend_live_realized), its arm record's signing-time fields
          (trigger whale / re-arm dumper, creator, quiet, v2, f3, cr, tags, holders of a re-arm), the fill-time holder annotation
          (ann.holders at our fill: used ONLY for after-the-fact labels and the 'bad holder' study, flagged as fill-time), and the
          hold tape label (followed = another wallet bought between our first buy and our last sell landing, quiet3's definition)
  skips : every presend_live_skip (why, kind, t, mint, whale, pct, sol, creator, quiet, f3, cr)
  sh    : the shadow's T2 triggers (presend_arm: t, mint, whale, pct, sol, quiet, v2) + row c's paper result (net_cheap; None = no fill)
usage: x1_extract.py RUN FILE   -> /home/it/sniper-data/filters3/quiet4/ex_RUN.pkl"""
import sys, json, pickle, collections
OUT = "/home/it/sniper-data/filters3/quiet4"


def main(run, fn):
    me = None; cfg = {}
    arms = collections.defaultdict(list); closes = []; realized = collections.defaultdict(list)
    tape = collections.defaultdict(dict); fills = {}; skips = []; sh = {}; shc = {}
    for raw in open(fn, "rb"):
        if b'"ev":"presend_' not in raw and b'"ev":"run_start"' not in raw: continue
        if b'"ev":"presend_attempt' in raw or b'"ev":"presend_wide_' in raw or b'"ev":"presend_live_ata' in raw: continue
        d = json.loads(raw); ev = d["ev"]
        if ev == "run_start":
            me = me or d.get("wallet"); cfg = cfg or (d.get("presend_live") or {})
        elif ev == "presend_live_arm":
            tr = d.get("trig") or d.get("dump") or {}
            arms[(d.get("mint") or tr.get("mint"), d.get("kind") or "T2", d.get("w"))].append(d)
        elif ev == "presend_live_close": closes.append(d)
        elif ev == "presend_live_realized": realized[(d["mint"], d.get("pid"))].append(d)
        elif ev == "presend_live_tape": tape[d["mint"]][(d["slot"], d["idx"], d.get("j", 0))] = d
        elif ev == "presend_live_fill": fills[(d["mint"], d.get("w"), d.get("kind") or "T2")] = d
        elif ev == "presend_live_skip":
            tr = d.get("trig") or d.get("dump") or {}
            skips.append({"why": d.get("why"), "kind": d.get("kind") or "T2", "t": tr.get("t"), "mint": d.get("mint") or tr.get("mint"),
                          "whale": tr.get("wallet") or tr.get("seller"), "pct": tr.get("pct"), "sol": tr.get("sol"), "age": tr.get("age_slots"),
                          "creator": (d.get("ann") or {}).get("creator"), "cr_pct": (d.get("ann") or {}).get("cr_pct"),
                          "quiet": d.get("quiet") or d.get("r5"), "f3": d.get("f3"), "v2": d.get("v2"), "cr": d.get("cr"), "holders": d.get("holders")})
        elif ev == "presend_arm":
            sh[(d["mint"], d["w"])] = {"t": d["t"], "mint": d["mint"], "whale": d.get("wallet"), "pct": d.get("pct"), "sol": d.get("sol"),
                                       "age": d.get("age_slots"), "quiet": d.get("quiet"), "v2": d.get("v2"), "c": None}
        elif ev == "presend_exit" and d.get("row") == "c":
            shc[(d["mint"], d["w"])] = d.get("net_cheap")
    for k, v in shc.items():
        if k in sh: sh[k]["c"] = v
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
        fol_users = sorted({x["user"] for x in hold if x["buy"] and x["user"] not in excl})
        sellers = collections.Counter()
        for x in hold:
            if not x["buy"]: sellers[x["user"]] += x["sol"] / 1e9
        fl = fills.get((c["mint"], c.get("w"), kind)) or {}
        ann = arm.get("ann") or {}
        pos.append({"run": run, "t0": tr.get("t") or b0["t"], "buy_t": b0["t"], "known": max(b0["t"] + 3 * 10**9, sell_t), "mint": c["mint"],
                    "kind": kind, "w": c.get("w"), "pid": c.get("pid"), "pnl": rl["pnl"] / 1e9, "followed": bool(fol_users), "fol_users": fol_users,
                    "hold_sellers": dict(sellers), "whale": whale, "trig_pct": tr.get("pct"), "trig_sol": tr.get("sol"), "trig_age": tr.get("age_slots"),
                    "trig_slot": tr.get("slot"), "creator": ann.get("creator"), "cr_pct": ann.get("cr_pct"), "nb50": ann.get("nb50"),
                    "quiet": arm.get("quiet") or arm.get("r5"), "v2": arm.get("v2"), "f3": arm.get("f3"), "cr": arm.get("cr"), "tags": arm.get("tags"),
                    "arm_holders": arm.get("holders"), "fill_holders": (fl.get("ann") or {}).get("holders"), "fill_slot": fl.get("slot"),
                    "spend": arm.get("spend")})
    pos.sort(key=lambda p: p["t0"])
    pickle.dump({"run": run, "me": me, "cfg": cfg, "pos": pos, "skips": skips, "sh": sorted(sh.values(), key=lambda x: x["t"])},
                open(f"{OUT}/ex_{run}.pkl", "wb"))
    print(run, "positions", len(pos), "net", round(sum(p["pnl"] for p in pos), 3), "skips", len(skips), "shadow", len(sh), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
