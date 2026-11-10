#!/usr/bin/env python3
"""CASEBOOK step 4: per-token decoded tape + decision-state event table + readable timeline.
usage: c4_tape.py RUN MINT [MINT...]
in : casebook/tapes/<run>/<mint>.raw.jsonl.gz, collect launches/enrich, own_<run>.jsonl, leaders
out: casebook/tapes/<run>/<mint>.ev.jsonl.gz   (one row per landed curve trade on the mint, 9pQQ's included, with state)
     casebook/tapes/<run>/<mint>.tl.txt        (timeline; failed txs summarised per slot)"""
import sys, json, gzip, base64, struct, collections, datetime, bisect, os
import numpy as np
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
D = "/home/it/sniper-data/rivals/9pQQ/casebook"; COL = "/data/tapes/collect"
STD = {"11111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "ComputeBudget111111111111111111111111111111", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
       "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "MemoSq4gqABAXiNsLV6bRuyiUe11pz7yfQq5f4UJmMs8", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo",
       "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "SysvarRent111111111111111111111111111111111"}
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
def evs(d, mint):
    out = []
    for e in d.get("ev") or []:
        try: b = base64.b64decode(e)
        except Exception: continue
        if b[:8].hex() != "bddb7fd34ee661ee" or len(b) < 129: continue
        if b58(b[8:40]) != mint: continue
        sol, tok = struct.unpack_from("<QQ", b, 40); buy = b[56] == 1; user = b58(b[57:89])
        vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, 97)
        out.append(dict(buy=buy, sol=sol, tok=tok, user=user, vsol=vsol, vtok=vtok))
    return out
LBASE = 1070 * 432000
_L = None
def leader(s):
    global _L
    if _L is None: _L = (np.load(f"{D}/leaders/slot_leader.npy"), np.load(f"{D}/leaders/names.npy"))
    k = s - LBASE
    return str(_L[1][_L[0][k]])[:6] if 0 <= k < len(_L[0]) and _L[0][k] >= 0 else "?"
def pkt(bt): return (datetime.datetime.utcfromtimestamp(bt) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M:%S")
def tipsum(d):
    t = d.get("tips") or []; ast = sum(v for a, v in t if a.startswith("astra")); return sum(v for _, v in t), len(t), ast
def own_global(run):
    rows = [json.loads(l) for l in open(f"{D}/own_{run}.jsonl")]
    ev = []  # (s, i, +1/-1)
    for r in rows:
        if r["err"] or r["kind"] == "other": continue
        ev.append((r["s"], r["i"], 1 if r["kind"] == "buy" else -1, r["mint"]))
    ev.sort(); keys = [(s, i) for s, i, _, _ in ev]; cum = np.cumsum([x for _, _, x, _ in ev])
    buys_s = sorted(s for s, i, x, _ in ev if x == 1)
    fails = sorted(r["s"] for r in rows if r["err"] and r["kind"] == "buy")
    return keys, cum, buys_s, fails
def build(run, mint, G):
    L = None
    for l in open(f"{COL}/{run}/launches.jsonl"):
        if mint in l:
            d = json.loads(l)
            if d["mint"] == mint: L = d; break
    raw = [json.loads(l) for l in gzip.open(f"{D}/tapes/{run}/{mint}.raw.jsonl.gz", "rt")]
    L0 = L["slot"] if L else raw[0]["s"]
    trades, fails, others = [], [], []
    for d in raw:
        sg = (d.get("signers") or [None])[0]; ix = d.get("ixn") or []
        progs = ",".join(sorted(p[:5] for p in (d.get("progs") or []) if p not in STD))
        ts, nt, ast = tipsum(d)
        if d.get("err") is not None:
            side = "B" if any(x.startswith("Buy") for x in ix) else ("S" if any(x.startswith("Sell") for x in ix) else "?")
            es = json.dumps(d["err"]); code = es.split('"Custom":')[1].split("}")[0] if '"Custom":' in es else es[:20]
            fails.append(dict(s=d["s"], i=d.get("i") or 0, u=sg, side=side, code=code, cup=d.get("cup") or 0, tip=ts, pr=progs))
            continue
        E = evs(d, mint)
        if not E: others.append(dict(s=d["s"], i=d.get("i") or 0, u=sg, ix=ix[:4])); continue
        for k, e in enumerate(E):
            trades.append(dict(s=d["s"], i=d.get("i") or 0, k=k, bt=d.get("bt"), sig=d["sig"][:10], u=e["user"], sg=sg, buy=e["buy"], sol=e["sol"] / 1e9,
                               tok=e["tok"], vsol=e["vsol"], vtok=e["vtok"], mc=e["vsol"] / e["vtok"] * 1e6, pr=progs, tip=ts, ntip=nt, ast=ast,
                               cup=d.get("cup") or 0, ne=len(E)))
    trades.sort(key=lambda t: (t["s"], t["i"], t["k"]))
    fails.sort(key=lambda t: (t["s"], t["i"]))
    keys, cum, buys_s, gfails = G
    # wallet trade counts so far (on this token) and per-slot failed counts
    fs = collections.defaultdict(list)
    for f in fails: fs[f["s"]].append(f)
    ucount = collections.Counter()
    own = [t for t in trades if t["u"] == W]
    rows = []; holding = False; last_own_sell = None; last_own_buy = None; n_trips = 0; hi450 = []
    last_exit_mc = None; entry_mc = None; peak = None
    for n, t in enumerate(trades):
        s = t["s"]
        prev = trades[max(0, n - 400):n]
        def win(k): return [x for x in prev if x["s"] >= s - k and x["u"] != W]
        w10, w3, w75 = win(10), win(3), win(75)
        def mc_at(k):
            xs = [x for x in prev if x["s"] <= s - k]
            return xs[-1]["mc"] if xs else (prev[0]["mc"] if prev else None)
        pre_mc = prev[-1]["mc"] if prev else None
        hi = max([x["mc"] for x in prev if x["s"] >= s - 450] or [t["mc"]])
        ob = [x for x in prev if x["u"] != W and x["buy"]]
        r = dict(n=n, s=s, i=t["i"], age=s - L0, bt=t["bt"], u=t["u"], own=t["u"] == W, buy=t["buy"], sol=round(t["sol"], 4), mc=round(t["mc"], 2),
                 pre_mc=round(pre_mc, 2) if pre_mc else None, vsol=round(t["vsol"] / 1e9, 2), pr=t["pr"], tip=t["tip"], ntip=t["ntip"], ast=t["ast"], cup=t["cup"],
                 ucnt=ucount[t["u"]], gap=(s - prev[-1]["s"]) if prev else None,
                 nf10=round(sum(x["sol"] * (1 if x["buy"] else -1) for x in w10), 3), nb10=sum(1 for x in w10 if x["buy"]), ns10=sum(1 for x in w10 if not x["buy"]),
                 nf75=round(sum(x["sol"] * (1 if x["buy"] else -1) for x in w75), 3), n75=len(w75),
                 ch10=round((pre_mc / mc_at(10) - 1) * 100, 1) if pre_mc and mc_at(10) else None,
                 ch50=round((pre_mc / mc_at(50) - 1) * 100, 1) if pre_mc and mc_at(50) else None,
                 dd450=round((t["mc"] / hi - 1) * 100, 1),
                 since_ob=(s - ob[-1]["s"]) if ob else None,
                 fail_slot=len([f for f in fs[s] if f["i"] < t["i"]]), fail_prev=len(fs[s - 1]),
                 failb_slot=len([f for f in fs[s] if f["i"] < t["i"] and f["side"] == "B"]),
                 hold=holding, ntrips=n_trips, since_sell=(s - last_own_sell) if last_own_sell else None,
                 vs_exit=round((t["mc"] / last_exit_mc - 1) * 100, 1) if last_exit_mc else None,
                 ret=round((t["mc"] / entry_mc - 1) * 100, 1) if holding and entry_mc else None,
                 since_buy=(s - last_own_buy) if holding else None,
                 g_open=int(cum[bisect.bisect_left(keys, (s, t["i"])) - 1]) if bisect.bisect_left(keys, (s, t["i"])) > 0 else 0,
                 g_buys10=bisect.bisect_left(buys_s, s) - bisect.bisect_left(buys_s, s - 10),
                 g_fail10=bisect.bisect_left(gfails, s) - bisect.bisect_left(gfails, s - 10),
                 lead=leader(s))
        if holding: peak = max(peak, t["mc"]); r["dd_peak"] = round((t["mc"] / peak - 1) * 100, 1)
        rows.append(r)
        ucount[t["u"]] += 1
        if t["u"] == W:
            if t["buy"]: holding = True; last_own_buy = s; entry_mc = t["mc"]; peak = t["mc"]
            else: holding = False; last_own_sell = s; n_trips += 1; last_exit_mc = t["pre_mc"] if False else (pre_mc or t["mc"])
    # label triggers: the last outside trade before each own action (same or previous slot)
    for n, r in enumerate(rows):
        if not r["own"]: continue
        j = n - 1
        while j >= 0 and rows[j]["own"]: j -= 1
        if j >= 0 and r["s"] - rows[j]["s"] <= 1:
            rows[j]["trig"] = "B" if r["buy"] else "S"
        r["trig_dslot"] = (r["s"] - rows[j]["s"]) if j >= 0 else None
    # own failed buys -> mark
    ownf = [f for f in fails if f["u"] == W]
    for f in ownf:
        j = max([n for n, r in enumerate(rows) if (r["s"], r["i"]) < (f["s"], f["i"])] or [-1])
        if j >= 0 and not rows[j]["own"] and f["s"] - rows[j]["s"] <= 1: rows[j]["ftrig"] = f["side"] + f["code"]
    with gzip.open(f"{D}/tapes/{run}/{mint}.ev.jsonl.gz", "wt") as fo:
        for r in rows: fo.write(json.dumps(r) + "\n")
    # timeline
    with open(f"{D}/tapes/{run}/{mint}.tl.txt", "w") as fo:
        fo.write(f"# {mint} run {run} launch slot {L0} {pkt(L['bt']) if L else ''} creator {(L or {}).get('creator','?')[:8]} name {(L or {}).get('name','?')!r}\n")
        fo.write(f"# trades {len(trades)} failed {len(fails)} other {len(others)}; MC in SOL; flags: >> own, *B/*S = trigger of own buy/sell, !F = trigger of own failed tx\n")
        lastslot = None
        for r, t in zip(rows, trades):
            if lastslot is not None and r["s"] != lastslot:
                for ss in range(lastslot, r["s"]):
                    ff = fs.get(ss)
                    if ff:
                        c = collections.Counter((f["side"], f["code"]) for f in ff)
                        fo.write(f"      fails s+{ss-L0}: " + " ".join(f"{a}{b}x{n}" for (a, b), n in c.most_common(5)) + (" [OWN FAIL]" if any(f['u'] == W for f in ff) else "") + "\n")
            lastslot = r["s"]
            flag = (">>" if r["own"] else "  ") + ("*" + r["trig"] if r.get("trig") else "  ") + ("!F" if r.get("ftrig") else "  ")
            fo.write(f"{flag} +{r['age']:<6} {r['i']:>4} {pkt(r['bt'])[6:]} {'B' if r['buy'] else 'S'} {r['sol']:8.3f} {r['u'][:6]} mc {r['mc']:7.1f} "
                     f"{('pr=' + r['pr']) if r['pr'] else ''} tip={r['tip']} cup={r['cup']} uc={r['ucnt']}"
                     + (f" HOLD ret {r['ret']}% dd {r.get('dd_peak')}" if r['hold'] else "") + f" L={r['lead']}\n")
    return rows, fails, L
if __name__ == "__main__":
    run = sys.argv[1]; G = own_global(run)
    for m in sys.argv[2:]:
        rows, fails, L = build(run, m, G)
        print(m[:8], "trades", len(rows), "own", sum(r["own"] for r in rows), "fails", len(fails))
