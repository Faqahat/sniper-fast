#!/usr/bin/env python3
"""Senders, ours and the rivals' (run ON CHERRY). usage: senders.py <segment> [<segment> ...]   e.g. w5h-p6 w5h-p7
A. ours: per path: copies, send-call ms, keep-alive RTT, races won (which copy landed), send->seen, ms after trigger
B. our bundles: Jito verdicts, by resend (+0/+100/+250 ms) and by leader kind
C. the rivals: per sender service (tip account; none = no tip): arbitrage-like txs, signers, success, profitable wins,
   SOL, ms after trigger (wins), tip / CU price, nonce share; which service wins under which leader kind
D. the top winning bots: path mix, wins per path, tips, CU prices, spray (txs per win)
Leader kinds come from runs/long-1-leaders.json (client, Jito/BAM, city, RTT from Cherry) + getSlotLeaders now."""
import json, sys, os, collections, subprocess, urllib.request, time
os.chdir("/root/arb-lab")
SEGS = [s.rstrip("/") for s in sys.argv[1:]]
WSOL = "So11111111111111111111111111111111111111112"; MRIYA = "MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X"
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
q = lambda v, p: (round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None)
def lines(seg, name):
    p = f"runs/{seg}/{name}"
    if os.path.exists(p):
        with open(p) as f: yield from f
    elif os.path.exists(p + ".zst"):
        pr = subprocess.Popen(["zstd", "-dc", p + ".zst"], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        yield from pr.stdout; pr.wait()
def jl(seg, name):
    for l in lines(seg, name):
        try: yield json.loads(l)
        except Exception: pass
def rpc(m, p):
    for i in range(3):
        try:
            r = urllib.request.Request("https://rpc.haandigital.eu/", json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                       {"content-type": "application/json", "Authorization": "Bearer " + env["HAAN_API_KEY"]})
            return json.load(urllib.request.urlopen(r, timeout=30)).get("result")
        except Exception: time.sleep(1 + i)
VENUE = {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
         "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
         "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
         "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
NEUTRAL = {"ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
           "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}
def not_arb(progs):
    p = {x for x in progs if x not in NEUTRAL}
    return not p or p <= VENUE

# ---------------------------------------------------------------- load
ours_copies, ours_out, ours_att, keep, bund, opps = [], {}, {}, collections.defaultdict(list), {}, {}
rivals, execd = [], {}
slot_lo, slot_hi = 1 << 62, 0
for seg in SEGS:
    for x in jl(seg, "attempts.jsonl"): ours_att[(seg, x["attempt"])] = x
    for x in jl(seg, "outcomes.jsonl"): ours_out[(seg, x["attempt"])] = x
    for x in jl(seg, "copies.jsonl"): x["seg"] = seg; ours_copies.append(x)
    for x in jl(seg, "keepalive.jsonl"):
        if x.get("ms") is not None and not x.get("error"): keep[x["path"]].append(x["ms"])
    for x in jl(seg, "bundles.jsonl"): bund[x.get("sig")] = x.get("outcome")
    for x in jl(seg, "opportunities.jsonl"): opps[(seg, x["id"])] = x
    for x in jl(seg, "exec.jsonl"):
        execd[x["sig"]] = x
        if x.get("slot"): slot_lo = min(slot_lo, x["slot"]); slot_hi = max(slot_hi, x["slot"])
    for x in jl(seg, "rivals.jsonl"):
        if not_arb(x.get("progs") or []): continue
        x["seg"] = seg; rivals.append(x)
# leaders: slot -> identity -> kind
L = {}
s = slot_lo
while s <= slot_hi:
    n = min(5000, slot_hi - s + 1)
    for i, k in enumerate(rpc("getSlotLeaders", [s, n]) or []): L[s + i] = k
    s += n
INFO = json.load(open("runs/long-1-leaders.json")).get("info", {})
def lkind(slot):
    k = L.get(slot); i = INFO.get(k) if k else None
    if not i: return "unknown", "unknown"
    kind = "BAM" if i.get("bam") else "Jito" if i.get("jito") else "non-Jito"
    rtt = i.get("rtt_ms")
    where = "same DC (<1ms)" if rtt is not None and rtt < 1 else "Frankfurt/near (<5ms)" if rtt is not None and rtt < 5 else "Europe (<30ms)" if rtt is not None and rtt < 30 else "far (>=30ms)" if rtt is not None else "?"
    return kind, where
print(f"segments {SEGS}: slots {slot_lo}..{slot_hi}, leaders known {len(L)}, leader info for {sum(1 for v in set(L.values()) if v in INFO)}/{len(set(L.values()))} distinct leaders")

# ---------------------------------------------------------------- A. ours
print("\n[A] OUR PATHS")
P = collections.defaultdict(lambda: {"sent": 0, "ok": 0, "ms": [], "raced": 0, "won": 0, "seen": [], "after": [], "lk": collections.Counter()})
by_att = collections.defaultdict(list)
for c in ours_copies:
    if not c.get("t_sent"): continue
    p = P[c["path"]]; p["sent"] += 1; p["ok"] += bool(c.get("ok"))
    if c.get("ms") is not None: p["ms"].append(c["ms"])
    by_att[(c["seg"], c["attempt"])].append(c)
for key, cs in by_att.items():
    o = ours_out.get(key, {}); a = ours_att.get(key, {})
    paths = {c["path"] for c in cs}
    for pn in paths: P[pn]["raced"] += 1
    if not o.get("landed"): continue
    lsig = o.get("sig"); lp = next((c["path"] for c in cs if c.get("sig") == lsig), None)
    if not lp: continue
    p = P[lp]; p["won"] += 1
    for cc in o.get("copies") or []:
        if cc.get("sig") == lsig and cc.get("send_to_seen_ms") is not None: p["seen"].append(cc["send_to_seen_ms"])
    op = opps.get((key[0], a.get("opp"))) or {}
    t0 = min((op.get("arrivals") or {}).values() or [0])
    if t0 and o.get("seen_by"): p["after"].append((min(o["seen_by"].values()) - t0) / 1e6)
    p["lk"][lkind(o.get("slot"))[0] + " / " + lkind(o.get("slot"))[1]] += 1
print("  path         | copies | accepted | send call ms p50/p90 | keep-alive RTT p50 | in races | landed first | send->seen p50/p90 | landed ms after trigger p50 | leaders we landed with")
for n, p in sorted(P.items(), key=lambda x: -x[1]["won"]):
    print(f"  {n:12} | {p['sent']:6} | {p['ok']:8} | {q(p['ms'], .5)}/{q(p['ms'], .9)} | {q(keep.get(n, []), .5)} | {p['raced']:5} | {p['won']:4} ({p['won'] / max(1, p['raced']):.0%}) | {q(p['seen'], .5)}/{q(p['seen'], .9)} | {q(p['after'], .5)} | {dict(p['lk'].most_common(3))}")
# our landed-or-not by the leader at the trigger slot (TPU attempts)
lt = collections.defaultdict(lambda: [0, 0])
for key, a in ours_att.items():
    if a.get("path_arm") != "tpu": continue
    o = ours_out.get(key, {})
    if not any(c.get("t_sent") for c in by_att.get(key, [])): continue
    k = lkind(a.get("slot"))
    lt[k][0] += 1; lt[k][1] += bool(o.get("landed"))
print("  our TPU sends by the leader at the trigger: leader kind / where | sent | landed (any result)")
for k, v in sorted(lt.items(), key=lambda x: -x[1][0]): print(f"    {k[0]:8} / {k[1]:22} | {v[0]:4} | {v[1]:4} ({v[1] / max(1, v[0]):.0%})")

# ---------------------------------------------------------------- B. our bundles
print("\n[B] OUR BUNDLES (Jito verdict per bundle sent)")
bv = collections.Counter(); bres = collections.defaultdict(collections.Counter); blk = collections.defaultdict(collections.Counter)
for key, a in ours_att.items():
    rs = {r.get("sig"): f"+{r.get('after_ms')}ms" for r in a.get("bundle_resends") or []}
    for c in by_att.get(key, []):
        if c["path"] != "jito-bundle": continue
        v = bund.get(c.get("sig"), "no verdict"); o = ours_out.get(key, {})
        if o.get("landed") and o.get("sig") == c.get("sig"): v = "LANDED"
        bv[v] += 1; bres[rs.get(c.get("sig"), "first")][v] += 1; blk[lkind(a.get("slot"))[0]][v] += 1
print(f"  all: {dict(bv)}")
for k, v in bres.items(): print(f"  {k:8}: {dict(v)}")
print(f"  by leader kind at the trigger: { {k: dict(v) for k, v in blk.items()} }")

# ---------------------------------------------------------------- C. rivals by sender service
print("\n[C] RIVALS BY SENDER SERVICE (arbitrage-like txs touching our pools)")
def svc(x):
    t = [tt[2] or "unknown-tip" for tt in (x.get("tips") or [])]
    return "+".join(sorted(set(t))) if t else "no tip"
def gain(e):
    if not e or not e.get("ok"): return None
    if {k for k, v in (e.get("tok") or {}).items() if k != WSOL and v != "0"}: return None
    g = e.get("sol", 0) + int((e.get("tok") or {}).get(WSOL, "0"))
    return g if g > 0 else None
S = collections.defaultdict(lambda: {"txs": 0, "signers": set(), "landed": 0, "ok": 0, "wins": 0, "sol": 0.0, "tip": [], "cu": [], "nonce": 0, "lk": collections.Counter()})
B = collections.defaultdict(lambda: {"txs": 0, "wins": 0, "sol": 0.0, "svc": collections.Counter(), "svc_win": collections.Counter(), "tip": [], "cu": [], "nonce": 0, "cul": []})
for x in rivals:
    s_ = svc(x); e = execd.get(x["sig"]); g = gain(e)
    st = S[s_]; st["txs"] += 1; st["signers"].add(x.get("signer")); st["nonce"] += bool(x.get("nonce"))
    if e: st["landed"] += 1; st["ok"] += bool(e.get("ok"))
    tip = sum(tt[1] or 0 for tt in (x.get("tips") or []))
    if tip: st["tip"].append(tip)
    st["cu"].append(x.get("cu_price") or 0)
    b = B[x.get("signer")]; b["txs"] += 1; b["svc"][s_] += 1; b["nonce"] += bool(x.get("nonce")); b["cu"].append(x.get("cu_price") or 0); b["cul"].append(x.get("cu_limit") or 0)
    if tip: b["tip"].append(tip)
    if g:
        st["wins"] += 1; st["sol"] += g / 1e9; b["wins"] += 1; b["sol"] += g / 1e9; b["svc_win"][s_] += 1
        k = lkind(e.get("slot")); st["lk"][k[0]] += 1
tot_w = sum(v["wins"] for v in S.values()) or 1
print("  service                  | txs    | signers | landed | ok%  | wins | win/tx | SOL won | tip p50 | cu_price p50 | nonce% | wins by leader kind")
for n, st in sorted(S.items(), key=lambda x: -x[1]["sol"])[:14]:
    print(f"  {n[:24]:24} | {st['txs']:6} | {len(st['signers']):7} | {st['landed']:6} | {100 * st['ok'] // max(1, st['landed']):3}% | {st['wins']:4} | {st['wins'] / max(1, st['txs']):.4f} | {st['sol']:7.3f} | {q(st['tip'], .5)} | {q(st['cu'], .5)} | {100 * st['nonce'] // max(1, st['txs'])}% | {dict(st['lk'])}")

# ---------------------------------------------------------------- D. the top winning bots
print("\n[D] TOP WINNING BOTS: how they send")
print("  signer   | txs   | wins | SOL    | txs/win | paths used (txs)                         | paths that won                 | tip p50 | cu_price p50 | CU limit p50 | nonce%")
for sg, b in sorted(B.items(), key=lambda x: -x[1]["sol"])[:15]:
    print(f"  {sg[:8]}{'*' if sg == MRIYA else ' '}| {b['txs']:5} | {b['wins']:4} | {b['sol']:6.3f} | {b['txs'] / max(1, b['wins']):7.1f} | {str(dict(b['svc'].most_common(3)))[:40]:40} | {str(dict(b['svc_win'].most_common(3)))[:30]:30} | {q(b['tip'], .5)} | {q(b['cu'], .5)} | {q(b['cul'], .5)} | {100 * b['nonce'] // max(1, b['txs'])}%")
print("  (* = MriyaNN8)")

# ---------------------------------------------------------------- E. the winners of OUR opportunities, by sender
print("\n[E] WINNERS OF OUR OPPORTUNITIES (rival txs that took a gap we priced): sender, tip, priority, timing, leader")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
s8 = lambda s: b58d(s)[:8].hex()
RV = {x["sig"]: x for x in rivals}
W = []
for seg in SEGS:
    caps = list(jl(seg, "caps.jsonl"))
    ep, lastk = [], {}
    for c in caps:
        k = (c["buy"], c["sell"]); e = lastk.get(k)
        if e and c["slot"] - e["slot_last"] <= 5: e["slot_last"] = c["slot"]; e["ids"].append(c["id"]); continue
        e = {"buy": c["buy"], "sell": c["sell"], "slot": c["slot"], "slot_last": c["slot"], "ids": [c["id"]], "pair": f'{c["buy_venue"]}>{c["sell_venue"]}'}
        ep.append(e); lastk[k] = e
    moves = collections.defaultdict(list)
    for l in lines(seg, "moves.log"):
        p = l.split()
        if len(p) >= 4: moves[p[2]].append((int(p[1]), p[0]))
    ours = {c.get("sig") for c in ours_copies if c["seg"] == seg}
    seen = set(); took = []
    for e in ep:
        for pool in (e["buy"], e["sell"]):
            for slot, sg in moves.get(pool, []):
                if e["slot"] <= slot <= e["slot_last"] + 5 and sg not in ours and sg not in seen and gain(execd.get(sg)):
                    seen.add(sg); took.append((e, sg))
    first = {}
    for l in lines(seg, "txarr.log"):
        p = l.split(maxsplit=3)
        if len(p) >= 3: first.setdefault(p[0], int(p[2]))
    poh = {}
    need = {s8(sg) for _, sg in took} | {s8(opps.get((seg, e["ids"][0]), {}).get("trigger") or "1") for e, _ in took}
    for l in lines(seg, "poh.log"):
        p = l.split()
        if len(p) == 3 and p[0] in need and p[0] not in poh: poh[p[0]] = int(p[1]) * 400 + float(p[2])
    for e, sg in took:
        trig = opps.get((seg, e["ids"][0]), {}).get("trigger")
        ms = None
        if trig and trig != sg:
            a, b = poh.get(s8(trig)), poh.get(s8(sg))
            if a is not None and b is not None: ms = b - a
            else:
                ta, tb = first.get(s8(trig)), first.get(s8(sg))
                if ta and tb: ms = (tb - ta) / 1e6
        x = RV.get(sg, {}); ex = execd.get(sg, {})
        tips = [(tt[2] or "unknown-tip", tt[1] or 0) for tt in (x.get("tips") or [])]
        W.append({"sig": sg, "signer": ex.get("signer") or x.get("signer"), "profit": gain(ex) / 1e9, "svc": "+".join(sorted({t[0] for t in tips})) or "no tip",
                  "tip": sum(t[1] for t in tips), "cu_price": x.get("cu_price") or 0, "cu_limit": x.get("cu_limit") or 0, "fee": ex.get("fee") or 0,
                  "ms": ms, "lk": lkind(ex.get("slot")), "nonce": bool(x.get("nonce")), "pair": e["pair"], "feed": x.get("feed")})
print(f"  {len(W)} rival wins on our gaps, {sum(w['profit'] for w in W):.3f} SOL")
G = collections.defaultdict(list)
for w in W: G[w["svc"]].append(w)
print("  sender          | wins | SOL    | bots | ms after trigger p25/p50/p75 | tip p25/p50/p75 (lamports) | tip % of profit p50 | cu_price p50 | priority fee p50 | leader kinds (wins)")
for n, ws in sorted(G.items(), key=lambda x: -sum(w["profit"] for w in x[1])):
    ms = [w["ms"] for w in ws if w["ms"] is not None]; tips = [w["tip"] for w in ws if w["tip"]]
    share = [100 * w["tip"] / 1e9 / w["profit"] for w in ws if w["tip"] and w["profit"]]
    prio = [w["cu_price"] * w["cu_limit"] / 1e6 for w in ws]
    print(f"  {n[:15]:15} | {len(ws):4} | {sum(w['profit'] for w in ws):6.3f} | {len({w['signer'] for w in ws}):4} | {q(ms, .25)}/{q(ms, .5)}/{q(ms, .75)} | {q(tips, .25)}/{q(tips, .5)}/{q(tips, .75)} | {q(share, .5)} | {q([w['cu_price'] for w in ws], .5)} | {q(prio, .5)} | {dict(collections.Counter(w['lk'][0] for w in ws))}")
print("  by leader kind: which sender wins")
LK = collections.defaultdict(collections.Counter)
for w in W: LK[w["lk"][0] + " / " + w["lk"][1]][w["svc"]] += 1
for k, v in sorted(LK.items(), key=lambda x: -sum(x[1].values())): print(f"    {k:32} {dict(v.most_common(4))}")
print("  the 20 biggest rival wins on our gaps:")
for w in sorted(W, key=lambda w: -w["profit"])[:20]:
    print(f"    {w['signer'][:8]}{'*' if w['signer'] == MRIYA else ' '} +{w['profit']:.4f} SOL {w['pair']:16} {w['svc']:14} tip {w['tip']:>9} cu_price {w['cu_price']:>9} prio {w['cu_price'] * w['cu_limit'] // 1_000_000:>7} ms {w['ms'] and round(w['ms'], 1)} leader {w['lk'][0]}/{w['lk'][1]} nonce {w['nonce']} feed {w['feed']}")
