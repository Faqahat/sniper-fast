#!/usr/bin/env python3
"""Deep report of one live segment (run ON CHERRY): our trades, the gaps, the rivals, the infrastructure.
usage: seg.py <segment dir name under runs/, e.g. w5h-p1>   -> prints the report, writes runs/<seg>/report.json"""
import json, sys, os, collections, subprocess, urllib.request, time, concurrent.futures as cf
os.chdir("/root/arb-lab")
SEG = sys.argv[1].rstrip("/"); D = f"runs/{SEG}"
WSOL = "So11111111111111111111111111111111111111112"; MRIYA = "MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X"
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
q = lambda v, p: (sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
s8 = lambda s: b58d(s)[:8].hex()
def lines(name):
    p = f"{D}/{name}"
    if os.path.exists(p):
        with open(p) as f: yield from f
    elif os.path.exists(p + ".zst"):
        pr = subprocess.Popen(["zstd", "-dc", p + ".zst"], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        yield from pr.stdout; pr.wait()
def rpc(m, p):
    for i in range(3):
        try:
            r = urllib.request.Request("https://rpc.haandigital.eu/", json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                       {"content-type": "application/json", "Authorization": "Bearer " + env["HAAN_API_KEY"]})
            return json.load(urllib.request.urlopen(r, timeout=30)).get("result")
        except Exception: time.sleep(1 + i)
R = {}
st = [json.loads(l) for l in lines("status.jsonl")]
hours = max(1e-9, (st[-1]["t_ns"] - st[0]["t_ns"]) / 3.6e12) if st else 1e-9
last = st[-1] if st else {}
A = {x["attempt"]: x for x in map(json.loads, lines("attempts.jsonl"))}
O = {x["attempt"]: x for x in map(json.loads, lines("outcomes.jsonl"))}
opps = {x["id"]: x for x in map(json.loads, lines("opportunities.jsonl"))}
C = collections.defaultdict(list)
for x in map(json.loads, lines("copies.jsonl")): C[x["attempt"]].append(x)
print(f"===== {SEG}: {hours * 60:.1f} min =====")
# ---------------------------------------------------------------- 1. our trades
ex = last.get("exec", {}); sd = ex.get("sending", {})
print("\n[1] OUR TRADES")
print(f"  engine: { {k: v for k, v in last.get('counts', {}).items() if k.startswith(('opportunity', 'state', 'confirm', 'trigger_skip', 'below'))} }")
print(f"  exec:   {ex.get('counts')}")
print(f"  sent {sd.get('sent')}  landed {sd.get('landed')}  wins {sd.get('wins')}  failed fees {sd.get('failed_fees_lamports')}  profit(incl rent) {sd.get('profit_lamports')}  tips {sd.get('tips_lamports')}  new token accts {sd.get('new_token_accounts')}")
def verdict(o):
    if o.get("ok"): return "WIN"
    if o.get("landed"): return "landed-fail"
    e = json.dumps(o)
    if "sim_gated" in e: return "sim-gated"
    return "not landed"
# first arrival (ns) of every transaction (txarr.log): the timing fallback when the PoH clock is missing (ERPC down):
# same first feed for trigger and rival, so the difference keeps the order and most of the gap
first = {}
for l in lines("txarr.log"):
    p = l.split(maxsplit=3)
    if len(p) >= 3: first.setdefault(p[0], int(p[2]))
def rx_ms(a, b):
    ta, tb = first.get(s8(a)) if a else None, first.get(s8(b)) if b else None
    return (tb - ta) / 1e6 if (ta and tb) else None
rows = []
for i, a in A.items():
    o = O.get(i, {})
    po = o.get("poh") or {}
    if po.get("ours_ms_after_trigger") is None and o.get("seen_by") and a.get("st"):
        po = dict(po); po["ours_ms_after_trigger"] = (min(o["seen_by"].values()) - a["st"]["rx"]) / 1e6
    rows.append({"i": i, "arm": a.get("path_arm"), "kind": "state" if a.get("trigger_feed") == "state" else "decoded", "v": verdict(o),
                 "size": a.get("size_lamports", 0) / 1e9, "exp": a.get("expected_profit", 0), "landed": o.get("landed"),
                 "ms": po.get("ours_ms_after_trigger"), "deliv": o.get("round_trip_on_chain"), "fee": o.get("fee_lamports") or 0,
                 "tradep": ((o.get("round_trip_on_chain") or 0) - (o.get("fee_lamports") or 0) - (o.get("tip_paid_lamports") or 0)) if o.get("ok") else None,
                 "buy": a["buy_venue"], "sell": a["sell_venue"], "mint": a.get("mint", "")[:8], "pair": (a["buy_pool"], a["sell_pool"]),
                 "slot": a.get("slot"), "trigger": a.get("trigger"), "gate": next((v for v in o.values() if isinstance(v, str) and v.startswith("sim_gated")), None)})
R["ours"] = rows
print("  verdicts by arm x trigger kind:", dict(collections.Counter((r["arm"], r["kind"], r["v"]) for r in rows)))
w = [r for r in rows if r["v"] == "WIN"]
print(f"  WINS {len(w)}: trading profit {sum(r['tradep'] or 0 for r in w) / 1e9:.5f} SOL")
for r in w: print(f"    {r['arm']:6} {r['kind']:7} {r['buy']}>{r['sell']} {r['mint']} size {r['size']:.3f} exp {r['exp']} -> {r['tradep']} via {r['landed']} ms {r['ms'] and round(r['ms'], 1)}")
lf = [r for r in rows if r["v"] == "landed-fail"]
print(f"  landed failures {len(lf)}: fees {sum(r['fee'] for r in lf)}; by path {dict(collections.Counter(r['landed'] for r in lf))}; ms after trigger p50 {q([r['ms'] for r in lf if r['ms'] is not None], .5)}")
g = collections.Counter((r["gate"] or "").split(": ", 1)[-1][:30] for r in rows if r["v"] == "sim-gated")
print(f"  sim-gate reasons: {g.most_common(6)}")
print(f"  sizes sent (SOL) p10/p50/p90/max: {q([r['size'] for r in rows], .1)}/{q([r['size'] for r in rows], .5)}/{q([r['size'] for r in rows], .9)}/{max([r['size'] for r in rows], default=0)}")
print(f"  expected profit p50/p90/max (lamports): {q([r['exp'] for r in rows], .5)}/{q([r['exp'] for r in rows], .9)}/{max([r['exp'] for r in rows], default=0)}")
print(f"  venue pairs: {collections.Counter((r['buy'], r['sell']) for r in rows).most_common(6)}")
landed = [r for r in rows if r["landed"]]
print(f"  landed by path: {dict(collections.Counter(r['landed'] for r in landed))}; ours ms after trigger p10/p50/p90 {q([r['ms'] for r in landed if r['ms'] is not None], .1)}/{q([r['ms'] for r in landed if r['ms'] is not None], .5)}/{q([r['ms'] for r in landed if r['ms'] is not None], .9)}")
for r in lf[:8]:
    print(f"    fail {r['buy']}>{r['sell']} {r['mint']} size {r['size']:.3f} exp {r['exp']} deliv {r['deliv']} via {r['landed']} ms {r['ms'] and round(r['ms'], 1)}")
# ---------------------------------------------------------------- 2. gaps (budget tiers, deduped)
print("\n[2] GAPS WE PRICED (deduped episodes)")
caps = [json.loads(l) for l in lines("caps.jsonl")]
ep = []; lastk = {}
for c in caps:
    k = (c["buy"], c["sell"]); e = lastk.get(k)
    if e and c["slot"] - e["slot_last"] <= 5:
        e["slot_last"] = c["slot"]; e["ids"].append(c["id"])
        for i, x in enumerate(c["caps"]):
            if x[2] is not None and (e["caps"][i] is None or x[2] > e["caps"][i]): e["caps"][i] = x[2]
    else:
        e = {"buy": c["buy"], "sell": c["sell"], "pair": f'{c["buy_venue"]}>{c["sell_venue"]}', "mint": c["mint"], "slot": c["slot"], "slot_last": c["slot"], "ids": [c["id"]],
             "caps": [x[2] for x in c["caps"]]}
        ep.append(e); lastk[k] = e
tiers = [x[0] for x in caps[0]["caps"]] if caps else []
print(f"  {len(caps)} priced -> {len(ep)} episodes")
# ---------------------------------------------------------------- 3. rivals on our gaps
print("\n[3] RIVALS ON THE GAPS WE PRICED")
moves = collections.defaultdict(list)
for l in lines("moves.log"):
    p = l.split()
    if len(p) >= 4: moves[p[2]].append((int(p[1]), p[0]))
want = {s for v in moves.values() for _, s in v}
gain = {}
for l in lines("exec.jsonl"):
    if '"ok":true' not in l: continue
    x = json.loads(l)
    if x["sig"] in want and not {k for k, v in x["tok"].items() if k != WSOL and v != "0"}:
        gn = x["sol"] + int(x["tok"].get(WSOL, "0"))
        if gn > 0: gain[x["sig"]] = (gn, x["signer"], x["fee"])
oursigs = {c["sig"] for v in C.values() for c in v if c.get("sig")}
took = []
for e in ep:
    for pool in (e["buy"], e["sell"]):
        for slot, s in moves.get(pool, []):
            if e["slot"] <= slot <= e["slot_last"] + 5 and s in gain and s not in oursigs: took.append((e, s))
seen = set(); took = [(e, s) for e, s in took if not (s in seen or seen.add(s))]
# the winner of every opportunity we tried and lost: the first profitable rival move on its pools within 5 slots
dw = {}
for r in rows:
    if r["v"] == "WIN": continue
    op = opps.get(A[r["i"]].get("opp")) or {}
    ts = op.get("slot") or r["slot"]
    if not ts: continue
    cand = [(slot, s) for pool in r["pair"] for slot, s in moves.get(pool, []) if ts <= slot <= ts + 5 and s in gain and s not in oursigs and s != op.get("trigger")]
    if cand: dw[r["i"]] = min(cand)[1]
need8 = {s8(s): s for _, s in took}
for s in dw.values(): need8[s8(s)] = s
for r in rows:
    if r["trigger"]: need8[s8(r["trigger"])] = r["trigger"]
poh = {}
for l in lines("poh.log"):
    p = l.split()
    if len(p) == 3 and p[0] in need8 and p[0] not in poh: poh[p[0]] = int(p[1]) * 400 + float(p[2])
riv = {}
rs = {s for _, s in took} | set(dw.values())
for l in lines("rivals.jsonl"):
    x = json.loads(l)
    if x["sig"] in rs: riv[x["sig"]] = x
def size(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    m = t["meta"]; signer = t["transaction"]["message"]["accountKeys"][0]
    pre = {b["accountIndex"]: b for b in m["preTokenBalances"]}; post = {b["accountIndex"]: b for b in m["postTokenBalances"]}
    best = 0
    for k in set(pre) | set(post):
        b = pre.get(k) or post.get(k)
        if b["mint"] != WSOL or b.get("owner") == signer: continue
        d = abs(int((post.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"]) - int((pre.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"]))
        best = max(best, d)
    return best / 1e9
with cf.ThreadPoolExecutor(6) as exr: sizes = dict(zip(rs, exr.map(size, rs)))
trow = []
for e, s in took:
    gn, signer, fee = gain[s]; x = riv.get(s, {})
    trig = opps.get(e["ids"][0], {}).get("trigger")
    tp, rp = (poh.get(s8(trig)) if trig else None), poh.get(s8(s))
    ms = (rp - tp) if (tp is not None and rp is not None) else rx_ms(trig, s)
    trow.append({"signer": signer, "profit": gn / 1e9, "size": sizes.get(s) or 0, "ms": ms if trig != s else None,
                 "cu_price": x.get("cu_price"), "tips": [t[2] for t in (x.get("tips") or []) if t[2]], "nonce": bool(x.get("nonce")), "pair": e["pair"], "mint": e["mint"][:8],
                 "our_caps": e["caps"]})
R["rivals_on_gaps"] = trow
tot = sum(r["profit"] for r in trow)
print(f"  {len(trow)} rival wins on our gaps, {tot:.4f} SOL ({tot / hours:.2f} SOL/h)")
print("  by size band: " + "  ".join(f"{lo}-{hi}: {sum(r['profit'] for r in trow if lo <= r['size'] < hi):.3f} SOL ({sum(1 for r in trow if lo <= r['size'] < hi)} wins, ms p50 {q([r['ms'] for r in trow if lo <= r['size'] < hi and r['ms'] is not None], .5)})"
                             for lo, hi in ((0, .2), (.2, 2.1), (2.1, 4.2), (4.2, 8.4), (8.4, 1e9))))
by = collections.defaultdict(list)
for r in trow: by[r["signer"]].append(r)
print("  top rivals on our gaps: signer | wins | SOL | size p50/max | ms p50 | cu_price p50 | nonce | senders")
for sg, rr in sorted(by.items(), key=lambda x: -sum(r["profit"] for r in x[1]))[:12]:
    print(f"    {sg[:8]}{' (MRIYA)' if sg == MRIYA else ''} | {len(rr)} | {sum(r['profit'] for r in rr):.4f} | {q([r['size'] for r in rr], .5):.2f}/{max(r['size'] for r in rr):.1f} | {q([r['ms'] for r in rr if r['ms'] is not None], .5)} | {q([r['cu_price'] or 0 for r in rr], .5)} | {sum(r['nonce'] for r in rr)} | {dict(collections.Counter(t for r in rr for t in r['tips']))}")
# who beat our landed failures
beat = collections.Counter()
for r in lf:
    for pool in r["pair"]:
        for slot, s in moves.get(pool, []):
            if r["slot"] and r["slot"] <= slot <= r["slot"] + 3 and s in gain and s not in oursigs: beat[gain[s][1][:8]] += 1
print(f"  rivals who moved our pools right before our landed failures: {beat.most_common(8)}")
# reachable at our speed per budget
ours_ms = q([r["ms"] for r in landed if r["ms"] is not None], .5) or 100
print(f"  rival profit won SLOWER than our median ({ours_ms:.0f} ms) by size band (what faster sends could have taken): " +
      "  ".join(f"{lo}-{hi}: {sum(r['profit'] for r in trow if lo <= r['size'] < hi and (r['ms'] or 0) >= ours_ms):.3f}" for lo, hi in ((0, .2), (.2, 2.1), (2.1, 4.2), (4.2, 1e9))))
# ---------------------------------------------------------------- expectation scorecard
print("\n[*] SCORECARD vs the exp4 expectation for the $500 band (2.1-4.2 SOL): rivals 2.07 SOL/h, reachable at our speed 0.92 SOL/h")
for lo, hi, lab in ((0, .2, "under 0.2 (~$20)"), (.2, 2.1, "0.2-2.1 (~$250)"), (2.1, 4.2, "2.1-4.2 (~$500) <- target band"), (4.2, 1e9, "4.2+ (needs more capital)")):
    sel = [r for r in trow if lo <= r["size"] < hi]
    reach = sum(r["profit"] for r in sel if r["ms"] is not None and r["ms"] >= 50)
    mine = sum((r["tradep"] or 0) for r in w if lo <= r["size"] < hi) / 1e9
    print(f"  {lab:32} rivals took {sum(r['profit'] for r in sel) / hours:6.3f} SOL/h | reachable (winner >= 50 ms) {reach / hours:6.3f} SOL/h | WE captured {mine / hours:6.3f} SOL/h ({sum(1 for r in w if lo <= r['size'] < hi)} wins)")
print(f"  total captured this segment: {sum(r['tradep'] or 0 for r in w) / 1e9:.5f} SOL = {sum(r['tradep'] or 0 for r in w) / 1e9 / hours:.4f} SOL/h; paid failures {sum(r['fee'] for r in lf) / 1e9:.5f} SOL")

# ---------------------------------------------------------------- 4. the field this segment
print("\n[4] THE FIELD THIS SEGMENT (every arbitrage-like tx with a result)")
fw = collections.defaultdict(lambda: [0, 0, 0.0, collections.Counter(), 0])
res = {}
for l in lines("exec.jsonl"):
    if '"ok":true' not in l: continue
    x = json.loads(l)
    if {k for k, v in x["tok"].items() if k != WSOL and v != "0"}: continue
    gn = x["sol"] + int(x["tok"].get(WSOL, "0"))
    if gn > 0: res[x["sig"]] = (gn, x["signer"])
VENUE = {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
         "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
         "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
         "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
NEUTRAL = {"ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
           "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}
def not_arb(progs):
    p = {x for x in progs if x not in NEUTRAL}
    return not p or p <= VENUE   # an arbitrage bot runs its own program; venue-only = a trader, LP or fee claim
for l in lines("rivals.jsonl"):
    x = json.loads(l)
    if not_arb(x.get("progs") or []): continue
    f = fw[x["signer"]]; f[0] += 1
    if x["sig"] in res: f[1] += 1; f[2] += res[x["sig"]][0] / 1e9
    for t in x.get("tips") or []:
        if t[2]: f[3][t[2]] += 1
    if x.get("nonce"): f[4] += 1
top = sorted(fw.items(), key=lambda x: -x[1][2])[:12]
print(f"  {len(fw)} signers; top by measured profit (PumpSwap-touching only): signer | txs | wins | SOL | nonce% | senders")
for sg, f in top:
    print(f"    {sg[:8]}{' (MRIYA)' if sg == MRIYA else ''} | {f[0]} | {f[1]} | {f[2]:.4f} | {100 * f[4] // max(1, f[0])}% | {dict(f[3].most_common(4))}")
# ---------------------------------------------------------------- 5. infrastructure
print("\n[5] INFRASTRUCTURE")
out = open(f"runs/{SEG}.out").read().splitlines() if os.path.exists(f"runs/{SEG}.out") else []
for l in out[::-1]:
    if l.startswith("rpc final") or l.startswith("send final"): print("  " + l[:180])
for l in out:
    if "left out" in l or "panic" in l.lower(): print("  !! " + l[:200])
# ---------------------------------------------------------------- 6. who beat us, per opportunity
print("\n[6] OPPORTUNITIES WE TRIED AND LOST: who won each one, and how")
def t_first(op): return min((op.get("arrivals") or {}).values() or [0]) or None
def wms(r, s):
    op = opps.get(A[r["i"]].get("opp")) or {}; trig = op.get("trigger")
    tp, rp = (poh.get(s8(trig)) if trig else None), poh.get(s8(s))
    return (rp - tp) if (tp is not None and rp is not None) else rx_ms(trig, s)
def our_sent_ms(r):
    op = opps.get(A[r["i"]].get("opp")) or {}; t0 = t_first(op)
    ts = [c["t_sent"] for c in C.get(r["i"], []) if c.get("t_sent")]
    return (min(ts) - t0) / 1e6 if (ts and t0) else None
def sender(x):
    t = [(tt[2] or "unknown-tip", tt[1]) for tt in (x.get("tips") or [])]
    return t or [("no tip (direct TPU / RPC / own stake)", 0)]
lost = [r for r in rows if r["v"] != "WIN"]
dl = []
for r in lost:
    s = dw.get(r["i"])
    if not s: continue
    gn, signer, fee = gain[s]; x = riv.get(s, {})
    dl.append({"r": r, "sig": s, "signer": signer, "profit": gn / 1e9, "ms": wms(r, s), "ours_ms": our_sent_ms(r), "fee": fee, "cu_price": x.get("cu_price"),
               "senders": sender(x), "nonce": bool(x.get("nonce")), "size": sizes.get(s) or 0})
R["denied"] = [{k: v for k, v in d.items() if k != "r"} | {"attempt": d["r"]["i"], "our_verdict": d["r"]["v"], "our_exp": d["r"]["exp"]} for d in dl]
print(f"  {len(lost)} attempts lost; a profitable winner found for {len(dl)} ({len(dl) / max(1, len(lost)):.0%}). The rest: nobody profited on those pools within 5 slots (fake gap / quote error / closed by ordinary trading)")
print(f"  winner ms after trigger p25/p50/p75: {q([d['ms'] for d in dl if d['ms'] is not None], .25)}/{q([d['ms'] for d in dl if d['ms'] is not None], .5)}/{q([d['ms'] for d in dl if d['ms'] is not None], .75)}  |  our first send p25/p50/p75: {q([d['ours_ms'] for d in dl if d['ours_ms'] is not None], .25)}/{q([d['ours_ms'] for d in dl if d['ours_ms'] is not None], .5)}/{q([d['ours_ms'] for d in dl if d['ours_ms'] is not None], .75)}")
print(f"  of those, winner was later than our first send: {sum(1 for d in dl if d['ms'] is not None and d['ours_ms'] is not None and d['ms'] > d['ours_ms'])} (sendable races we still lost)")
bw = collections.defaultdict(list)
for d in dl: bw[d["signer"]].append(d)
print("  winners: signer | beat us | their SOL | ms p50 | our verdicts on those | sender (count) | tip p50 | cu_price p50 | nonce")
for sg, dd in sorted(bw.items(), key=lambda x: (-len(x[1]), -sum(d["profit"] for d in x[1])))[:15]:
    snd = collections.Counter(n for d in dd for n, _ in d["senders"])
    tips = [l for d in dd for _, l in d["senders"] if l]
    print(f"    {sg[:8]}{' (MRIYA)' if sg == MRIYA else ''} | {len(dd)} | {sum(d['profit'] for d in dd):.4f} | {q([d['ms'] for d in dd if d['ms'] is not None], .5)} | {dict(collections.Counter(d['r']['v'] for d in dd))} | {dict(snd.most_common(3))} | {q(tips, .5)} | {q([d['cu_price'] or 0 for d in dd], .5)} | {sum(d['nonce'] for d in dd)}")
print("  top lost attempts by our expected profit: ours (verdict, arm, venues, size, expected, first send ms) -> winner (signer, ms, profit, size, sender)")
for d in sorted(dl, key=lambda d: -(d["r"]["exp"] or 0))[:15]:
    r = d["r"]
    print(f"    {r['v']:11} {r['arm'] or '-':6} {r['buy']}>{r['sell']} {r['mint']} {r['size']:.3f} SOL exp {r['exp'] / 1e9:.5f} sent@{d['ours_ms'] and round(d['ours_ms'], 1)}ms -> {d['signer'][:8]} @{d['ms'] and round(d['ms'], 1)}ms +{d['profit']:.5f} SOL size {d['size']:.2f} via {d['senders'][0][0]}")
# ---------------------------------------------------------------- 7. send paths: ours vs theirs
print("\n[7] SEND PATHS: OURS vs THE WINNERS'")
BU = {x.get("sig"): x.get("outcome") for x in map(json.loads, lines("bundles.jsonl"))}
pth = collections.defaultdict(lambda: {"sent": 0, "ok": 0, "landed": 0, "seen": [], "after": [], "bundle": collections.Counter()})
for i, cs in C.items():
    o = O.get(i, {}); op = opps.get(A.get(i, {}).get("opp")) or {}; t0 = t_first(op)
    landed_sig = o.get("sig") if o.get("landed") else None
    for c in cs:
        if not c.get("t_sent"): continue
        p = pth[c["path"]]; p["sent"] += 1; p["ok"] += bool(c.get("ok"))
        if c.get("sig") in BU: p["bundle"][BU[c["sig"]]] += 1
        if landed_sig and c.get("sig") == landed_sig:
            p["landed"] += 1
            for cc in o.get("copies") or []:
                if cc.get("sig") == landed_sig and cc.get("send_to_seen_ms") is not None: p["seen"].append(cc["send_to_seen_ms"])
            if t0 and o.get("seen_by"): p["after"].append((min(o["seen_by"].values()) - t0) / 1e6)
print("  ours: path | copies sent | accepted | landed | send->seen ms p50 (landed) | landed ms after trigger p50 | bundle verdicts")
for name, p in sorted(pth.items(), key=lambda x: -x[1]["sent"]):
    print(f"    {name:12} | {p['sent']:5} | {p['ok']:5} | {p['landed']:3} | {q(p['seen'], .5)} | {q(p['after'], .5)} | {dict(p['bundle']) if p['bundle'] else ''}")
allw = [(gain[s], riv.get(s, {}), ms) for s, ms in [(s, None) for _, s in took]] if False else None
ws = collections.defaultdict(lambda: {"n": 0, "sol": 0.0, "ms": [], "tip": [], "cu": []})
for rr, (e, s) in zip(trow, took):
    for n, l in sender(riv.get(s, {})):
        w_ = ws[n]; w_["n"] += 1; w_["sol"] += rr["profit"]; w_["cu"].append(rr["cu_price"] or 0)
        if rr["ms"] is not None: w_["ms"].append(rr["ms"])
        if l: w_["tip"].append(l)
print("  theirs (every rival win on our gaps): sender | wins | SOL | ms after trigger p50 | tip p50 (lamports) | cu_price p50")
for n, w_ in sorted(ws.items(), key=lambda x: -x[1]["sol"]):
    print(f"    {n:38} | {w_['n']:4} | {w_['sol']:.4f} | {q(w_['ms'], .5)} | {q(w_['tip'], .5)} | {q(w_['cu'], .5)}")
json.dump(R, open(f"{D}/report.json", "w"))
