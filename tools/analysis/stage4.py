#!/usr/bin/env python3
"""Long run, stage 4: our own trades. Per attempt (attempts/outcomes/copies): the trigger, whether it really moved the
pool (moves.log, exec.jsonl), who moved our pools between the trigger and us (the taker: signer, ms after the trigger
on the PoH clock), our landed copy (path, ms after the trigger), and the verdict:
  win | phantom (the trigger failed: no gap) | taken (someone moved the pool first) | gone (nobody visible; the gap
  wasn't there at our price) | not landed.
Aggregates: race arm = which path's copy the leader took first; win arm wins; fee arms; takers by signer.
usage: stage4.py <segment dir> [...] -> ours.json, ours.jsonl"""
import json, sys, os, subprocess, gzip, collections, bisect

HERE = os.path.dirname(os.path.abspath(__file__))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
sig8 = lambda s: b58d(s)[:8].hex()
q = lambda v, p: (round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None)

def lines(seg, name):
    p = os.path.join(seg, name)
    if os.path.exists(p):
        with open(p) as f: yield from f
    elif os.path.exists(p + ".zst"):
        pr = subprocess.Popen(["bun", os.path.join(HERE, "unzst.js"), p + ".zst"], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        yield from pr.stdout
        pr.wait()

rows = []
for seg in [s.rstrip("/") for s in sys.argv[1:]]:
    A = {x["attempt"]: x for x in map(json.loads, lines(seg, "attempts.jsonl"))}
    O = {x["attempt"]: x for x in map(json.loads, lines(seg, "outcomes.jsonl"))}
    pools = {p for a in A.values() for p in (a["buy_pool"], a["sell_pool"])}
    movers = collections.defaultdict(list)
    move_t = {}
    trigset = {a["trigger"] for a in A.values()}
    for l in lines(seg, "moves.log"):
        p = l.split()
        if len(p) >= 4 and p[2] in pools: movers[p[2]].append(p[0])
        if len(p) >= 4 and p[0] in trigset and p[0] not in move_t: move_t[p[0]] = int(p[3])
    trig_ok = {}
    trigs = {a["trigger"] for a in A.values()}
    for l in lines(seg, "exec.jsonl"):
        if '"sig":"' not in l: continue
        s = l.split('"sig":"', 1)[1].split('"', 1)[0]
        if s in trigs: trig_ok[s] = json.loads(l)["ok"]
    want = {sig8(s): s for p in movers.values() for s in p} | {sig8(t): t for t in trigs} | {sig8(o["sig"]): o["sig"] for o in O.values() if o.get("sig")}
    poh = {}
    for l in lines(seg, "poh.log"):
        p = l.split()
        if len(p) == 3 and p[0] in want and p[0] not in poh: poh[p[0]] = int(p[1]) * 400 + float(p[2])
    at = lambda s: poh.get(sig8(s)) if s else None
    signer = {}
    jp = os.path.join(seg, "joined.jsonl.gz")
    if os.path.exists(jp):
        allm = {s for p in movers.values() for s in p}
        for l in gzip.open(jp, "rt"):
            j = json.loads(l)
            if j["sig"] in allm: signer[j["sig"]] = j["signer"]
    moved_pools = collections.defaultdict(set)
    for p, ss in movers.items():
        for s in ss: moved_pools[s].add(p)
    for i, a in sorted(A.items()):
        o = O.get(i, {})
        tp = at(a["trigger"])
        ours = o.get("sig") if o.get("landed") else None
        op = at(ours)
        takers = []
        if tp is not None:
            end = op if op is not None else tp + 2000
            for p in (a["buy_pool"], a["sell_pool"]):
                for s in movers.get(p, []):
                    x = at(s)
                    if x is not None and tp < x < end and s not in (ours, a["trigger"]): takers.append((x - tp, s, p))
        takers.sort()
        # the trigger touched one of our pools: had it succeeded, that pool's update would name it (moves.log)
        phantom = not moved_pools.get(a["trigger"]) and trig_ok.get(a["trigger"]) is not True
        verdict = "win" if o.get("ok") else "not landed" if not o.get("landed") else "phantom" if phantom else "taken" if takers else "gone"
        rows.append({"seg": os.path.basename(seg), "attempt": i, "path_arm": a.get("path_arm"), "fee_arm": a.get("fee_arm"), "cu_price": a.get("cu_price_micro"),
            "expected": a.get("expected_profit"), "copies": [c["path"] for c in a["copies"]], "landed": o.get("landed"), "code": o.get("code"),
            "fee": o.get("fee_lamports"), "profit": o.get("profit_lamports"),
            # a win's trading result without the (refundable) rent of a token account it opened
            "trade_profit": ((o.get("round_trip_on_chain") or 0) - (o.get("fee_lamports") or 0) - (o.get("tip_paid_lamports") or 0)) if o.get("ok") else None,
            "rent": (((o.get("round_trip_on_chain") or 0) - (o.get("fee_lamports") or 0) - (o.get("tip_paid_lamports") or 0)) - (o.get("profit_lamports") or 0)) if o.get("ok") else 0, "slots_after": o.get("slots_after_trigger"),
            "ours_ms": round(op - tp, 2) if (op is not None and tp is not None) else None, "verdict": verdict,
            "taker": ({"ms": round(takers[0][0], 2), "sig": takers[0][1], "signer": signer.get(takers[0][1])} if takers else None),
            "confirm_ms": round((move_t[a["trigger"]] - a["st"]["rx"]) / 1e6, 2) if a["trigger"] in move_t and a.get("st") else None,
            "buy": a["buy_venue"], "sell": a["sell_venue"], "source": f'{a.get("buy_source")}/{a.get("sell_source")}', "trigger_feed": a.get("trigger_feed")})

with open("ours.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
R = rows
race = [r for r in R if r["path_arm"] == "race" and r["landed"]]
summ = {
    "trades": len(R), "landed": sum(1 for r in R if r["landed"]), "wins": sum(1 for r in R if r["verdict"] == "win"),
    "profit_lamports": sum(r["profit"] or 0 for r in R if r["verdict"] == "win"), "fees_lamports": sum(r["fee"] or 0 for r in R),
    "trade_profit_lamports": sum(r["trade_profit"] or 0 for r in R if r["verdict"] == "win"), "rent_parked_lamports": sum(r["rent"] or 0 for r in R if r["verdict"] == "win"),
    "failed_fees_lamports": sum(r["fee"] or 0 for r in R if r["verdict"] != "win"),
    "verdicts": dict(collections.Counter(r["verdict"] for r in R)),
    "race_first_landed_by_path": dict(collections.Counter(r["landed"] for r in race).most_common()),
    "race_ms_by_path": {p: {"n": len(v), "p10": q(v, .1), "p50": q(v, .5)} for p, v in
        ((p, [r["ours_ms"] for r in race if r["landed"] == p and r["ours_ms"] is not None]) for p in {r["landed"] for r in race})},
    "by_arm": {f"{pa}/{fa}": {"n": len(v), "landed": sum(1 for r in v if r["landed"]), "wins": sum(1 for r in v if r["verdict"] == "win"),
        "ms_p50": q([r["ours_ms"] for r in v if r["ours_ms"] is not None], .5), "fee_p50": q([r["fee"] for r in v if r["fee"]], .5)}
        for (pa, fa), v in ((k, [r for r in R if (r["path_arm"], r["fee_arm"]) == k]) for k in {(r["path_arm"], r["fee_arm"]) for r in R})},
    "takers": dict(collections.Counter((r["taker"] or {}).get("signer") or "?" for r in R if r["verdict"] == "taken").most_common(15)),
    "taker_ms_p10_p50_p90": [q([r["taker"]["ms"] for r in R if r["taker"]], x) for x in (.1, .5, .9)],
    "ours_ms_when_taken_p50": q([r["ours_ms"] for r in R if r["verdict"] == "taken" and r["ours_ms"] is not None], .5),
    "trigger_confirm_ms_p10_p50_p90": [q([r["confirm_ms"] for r in R if r["confirm_ms"] is not None], x) for x in (.1, .5, .9)],
    "ours_ms_all_p10_p50_p90": [q([r["ours_ms"] for r in R if r["ours_ms"] is not None], x) for x in (.1, .5, .9)],
}
json.dump(summ, open("ours.json", "w"), indent=1)
print(json.dumps(summ, indent=1))
