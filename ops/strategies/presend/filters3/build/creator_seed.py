#!/usr/bin/env python3
"""dip32 CREATOR GATE: the state-file seed + a replay of the ENGINE's rule (read-only on the runs' presend.jsonl, in time order).
Per live position: creator (presend_live_arm ann.creator), realized P&L (presend_live_realized), FOLLOWED the engine's way (a buy by a
wallet not ours / not the T2 whale / not the re-arm's holders after our first buy (slot, idx) and at or before our last sell landing),
known at its last sell landing + 2 s (the realized lookup's lag; the engine adds it when the realized task answers).
Replay: at each position's arm time t0, the ledger of earlier KNOWN, KEPT positions decides "cr_loss" (n >= N and sum <= -SOL) and the
log-only "unf3" (QUIET3-B: the last <= 3 known in 24 h all not followed). A blocked position never enters the ledger.
Writes the engine's state format {"v": 1, "c": {creator: {"sum", "n", "h": [[t, pnl, followed]]}}} from EVERY position (the seed for
the next run: what the engine would hold had it run these runs with the gate on).
usage: creator_seed.py OUT.json N SOL RUN.presend.jsonl [RUN ...]"""
import sys, json, collections
out_p, N, SOL = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]); files = sys.argv[4:]
H24, KEEP, LAG = 24 * 3600 * 10**9, 10, 2 * 10**9

def positions(fn):
    me = None; arms = collections.defaultdict(list); closes = []; real = collections.defaultdict(list); tape = collections.defaultdict(list)
    for l in open(fn, errors="replace"):
        if '"ev":"presend_live_' not in l and '"ev":"run_start"' not in l: continue
        d = json.loads(l); e = d["ev"]
        if e == "run_start": me = me or d.get("wallet")
        elif e == "presend_live_arm": arms[(d.get("w"), d.get("mint") or (d.get("trig") or {}).get("mint"))].append(d)
        elif e == "presend_live_close": closes.append(d)
        elif e == "presend_live_realized": real[(d["mint"], d.get("pid"))].append(d)
        elif e == "presend_live_tape": tape[d["mint"]].append(d)
    used = collections.Counter(); out = []
    for c in closes:
        k = (c["mint"], c.get("pid")); r = real[k][used[k]] if used[k] < len(real[k]) else None; used[k] += 1
        if r is None: continue
        a = (arms.get((c.get("w"), c["mint"])) or [None])[-1]
        if a is None: continue
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
        out.append({"t0": tr.get("t") or b0["t"], "known": lt + LAG, "creator": (a.get("ann") or {}).get("creator"), "pnl": r["pnl"], "fol": fol,
                    "mint": c["mint"], "run": fn.split("/")[-1].split(".")[0], "kind": a.get("kind", "t2")})
    return out

ps = sorted((p for f in files for p in positions(f)), key=lambda p: p["t0"])
seed = collections.defaultdict(lambda: {"sum": 0, "n": 0, "h": []})          # every position (the next run's state)
led = collections.defaultdict(list)                                         # kept positions only (the replay)
res = collections.defaultdict(lambda: collections.Counter())
for p in ps:
    c = p["creator"]
    if c:
        prev = [q for q in led[c] if q["known"] < p["t0"]]
        n, s = len(prev), sum(q["pnl"] for q in prev)
        p["block"] = n >= N and s <= -SOL * 1e9
        rec = [q for q in prev if q["known"] + H24 >= p["t0"]][-3:]
        p["unf3"] = bool(rec) and all(not q["fol"] for q in rec)
    else: p["block"] = p["unf3"] = False
    R = res[p["run"]]; R["n"] += 1; R["net"] += p["pnl"]
    for tag in ("block", "unf3"):
        if p[tag]: R[tag + "_n"] += 1; R[tag + "_saved"] -= p["pnl"]; R[tag + "_win"] += p["pnl"] > 0
    if c and not p["block"]: led[c].append(p)
    if c:
        e = seed[c]; e["sum"] += p["pnl"]; e["n"] += 1; e["h"].append([p["known"], p["pnl"], p["fol"]]); e["h"] = e["h"][-KEEP:]
json.dump({"v": 1, "c": seed}, open(out_p, "w"))
print(f"seed: {len(seed)} creators from {sum(1 for p in ps if p['creator'])} positions with a creator (of {len(ps)}) -> {out_p}")
print(f"replay of the engine's rule cr_loss {N}:{SOL} (live) and unf3 (log), kept positions only, in time order:")
tot = collections.Counter()
for r in sorted(res, key=lambda r: int(r[1:])):
    R = res[r]; tot.update(R)
    print(f"  {r}: {R['n']:5d} pos net {R['net']/1e9:+7.3f} | cr_loss blocks {R['block_n']:3d} (winners {R['block_win']:3d}) saves {R['block_saved']/1e9:+6.3f} | unf3 would {R['unf3_n']:3d} saves {R['unf3_saved']/1e9:+6.3f}")
print(f"  ALL: {tot['n']} pos net {tot['net']/1e9:+.3f} | cr_loss blocks {tot['block_n']} (winners {tot['block_win']}) saves {tot['block_saved']/1e9:+.3f} | unf3 would {tot['unf3_n']} saves {tot['unf3_saved']/1e9:+.3f}")
