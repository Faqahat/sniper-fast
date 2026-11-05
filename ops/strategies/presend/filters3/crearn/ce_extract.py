#!/usr/bin/env python3
"""CR-EARNBACK extract: one run's pre-send records -> a compact pickle (read-only on the run file).
usage: ce_extract.py rNN SRC.jsonl -> /home/moiz/sniper-data/filters3/crearn/ex_rNN.pkl
Keeps: live positions the creator_seed.py way (creator, pnl, followed, known = last sell landing + 2 s), every live arm (t0, sig, creator,
logged cr), every live skip (T2 + re-arm: why, t0, sig, creator if logged, cr), the shadow (presend_arm sig -> w, row c fill sol_in,
row c exit net_cheap + exit time), a mint -> creator map (every record with ann.creator)."""
import sys, json, pickle, collections
run, src = sys.argv[1], sys.argv[2]
out = f"/home/moiz/sniper-data/filters3/crearn/ex_{run}.pkl"
LAG = 2 * 10**9
me = None; rs_t = None; spend = None
arms = collections.defaultdict(list); closes = []; real = collections.defaultdict(list); tape = collections.defaultdict(list)
skips = []; sh_arm = {}; sh_fill = {}; sh_exit = {}; mcre = {}; arm_list = []; seq = 0
for l in open(src, errors="replace"):
    if '"ev":"presend_' not in l and '"ev":"run_start"' not in l: continue
    if '"ev":"presend_attempt' in l or '"ev":"presend_wide' in l or '"ev":"presend_live_ata' in l: continue
    d = json.loads(l); e = d["ev"]; seq += 1
    a = d.get("ann") or {}
    if a.get("creator"):
        m = d.get("mint") or (d.get("trig") or {}).get("mint")
        if m: mcre[m] = a["creator"]
    if e == "run_start":
        if me is None: me = d.get("wallet"); rs_t = d.get("t"); spend = (d.get("presend_live") or {}).get("spend")
    elif e == "presend_live_arm":
        d["_seq"] = seq
        arms[(d.get("w"), d.get("mint") or (d.get("trig") or {}).get("mint"))].append(d)
        tr = d.get("trig") or d.get("dump") or {}
        arm_list.append({"w": d.get("w"), "mint": d.get("mint") or tr.get("mint"), "kind": d.get("kind", "t2"), "t0": tr.get("t"),
                         "sig": tr.get("sig"), "creator": a.get("creator"), "cr": d.get("cr"), "spend": d.get("spend"), "seq": seq,
                         "t_dec": (tr.get("t") + int(d["arm_ms_after_dump"] * 1e6)) if d.get("arm_ms_after_dump") is not None and tr.get("t") else tr.get("t")})
    elif e == "presend_live_close": closes.append(d)
    elif e == "presend_live_realized": real[(d["mint"], d.get("pid"))].append(d)
    elif e == "presend_live_tape": tape[d["mint"]].append(d)
    elif e == "presend_live_skip":
        kind = d.get("kind") or ("t2" if "trig" in d else "rearm")
        tr = d.get("trig") if kind == "t2" else d.get("dump")
        tr = tr or {}
        skips.append({"why": d.get("why"), "kind": kind, "t0": tr.get("t"), "sig": tr.get("sig"), "mint": d.get("mint") or tr.get("mint"),
                      "creator": a.get("creator"), "cr": d.get("cr"), "seq": seq,
                      "t_dec": (tr.get("t") + (d["check_slot"] - tr["slot"]) * 400_000_000) if d.get("check_slot") and tr.get("slot") and tr.get("t") else tr.get("t"), "holders": [h.get("w") for h in d.get("holders") or []]})
    elif e == "presend_arm":
        sh_arm[d["sig"]] = {"w": d["w"], "mint": d.get("mint"), "t": d.get("t"), "a": d.get("a")}
    elif e == "presend_fill" and d.get("row", "c") == "c" and "entry" in d:
        if d["w"] not in sh_fill: sh_fill[d["w"]] = d["entry"].get("sol_in", 0) / 1e9
    elif e == "presend_exit" and d.get("row") == "c":
        sh_exit[d["w"]] = {"net_cheap": d.get("net_cheap", d.get("pnl", 0.0)), "xt": d.get("xt"), "hold_slots": d.get("hold_slots")}

used = collections.Counter(); pos = []
for c in closes:
    k = (c["mint"], c.get("pid")); r = real[k][used[k]] if used[k] < len(real[k]) else None; used[k] += 1
    if r is None: continue
    al = arms.get((c.get("w"), c["mint"]))
    if not al: continue
    a = al[-1]
    tr = a.get("trig") or a.get("dump") or {}
    excl = {me, "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
    if a.get("kind") != "rearm" and tr.get("wallet"): excl.add(tr["wallet"])
    if a.get("kind") == "rearm" and (a.get("dump") or {}).get("user"): excl.add(a["dump"]["user"])
    if a.get("kind") == "rearm" and (a.get("dump") or {}).get("seller"): excl.add(a["dump"]["seller"])
    for h in a.get("holders") or []: excl.add(h["w"])
    b0 = min(c["buys"], key=lambda b: (b["slot"], b["idx"])); first = (b0["slot"], b0["idx"])
    sl = c.get("sell_lands") or ([c["sell_land"]] if c.get("sell_land") else [])
    last = max(((x[0], x[1]) for x in sl), default=(first[0] + 3, 1 << 62))
    lt = max((x[2] for x in sl if len(x) > 2 and x[2]), default=b0["t"] + 3 * 10**9)
    fol = any(x["buy"] and x["user"] not in excl and first < (x["slot"], x["idx"]) <= last for x in tape[c["mint"]])
    crl = r.get("cr") or {}
    pos.append({"t0": tr.get("t") or b0["t"], "known": lt + LAG, "creator": (a.get("ann") or {}).get("creator") or crl.get("creator"),
                "pnl": r["pnl"], "fol": crl.get("followed", fol), "mint": c["mint"], "run": run, "kind": a.get("kind", "t2"),
                "sig": tr.get("sig"), "w": a.get("w"), "spend": a.get("spend"), "arm_cr": a.get("cr")})
# shadow paper per trigger sig: net_cheap (SOL, at the shadow's size), sol_in, exit time (ns)
paper = {}
for sig, sa in sh_arm.items():
    w = sa["w"]; x = sh_exit.get(w); si = sh_fill.get(w)
    tx = None
    if x and x.get("xt") is not None and sa.get("a") is not None and sa.get("t") is not None: tx = int(sa["t"] + (x["xt"] - sa["a"]) * 1e6)
    paper[sig] = {"filled": bool(x and si), "net": x["net_cheap"] if x else 0.0, "sol_in": si, "t_exit": tx, "t_arm": sa.get("t")}
pickle.dump({"run": run, "rs_t": rs_t, "spend": spend, "pos": pos, "arms": arm_list, "skips": skips, "paper": paper, "mcre": mcre},
            open(out, "wb"), protocol=4)
print(run, "pos", len(pos), round(sum(p["pnl"] for p in pos) / 1e9, 4), "arms", len(arm_list), "skips", len(skips),
      "cr skips", sum(1 for s in skips if "cr_loss" in (s["why"] or "")), "shadow arms", len(sh_arm), "paper filled", sum(p["filled"] for p in paper.values()))
