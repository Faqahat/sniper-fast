#!/usr/bin/env python3
# DEEP LOOK AT GUARD REVERTS (read-only): 2g (Frankfurt engine) and AMS (Amsterdam engine) failed buys in the last ~3.5 h.
# Per revert: our slot + block index, its leader (client, city, host, in Frankfurt's near list?), the dump we chased (last >= 1 SOL
# sell before us on the token), the trade that pushed the price past our min_out (who / how / fees / where), our margin, and two
# counterfactual replays at the run's exit: (1) "as if filled" at our real spot (= a looser guard), (2) "won the race" = landed just
# before the crossing buy (= a faster path). Collector tapes (R3) + RPC.
import os, sys, json, time, base64, urllib.request, collections, statistics, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/hkq7")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json")); SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
NEAR_FRA = {l.split()[0] for l in open("near_fra.txt") if l.strip() and not l.strip()[0].isdigit() and len(l.split()[0]) > 30}
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
BLK = {}
def block(slot):
    if slot not in BLK:
        b = rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); BLK[slot] = b["signatures"] if b else []
    return BLK[slot]
def txinfo(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    cup = 0; cul = 200000; tips = []; mint = None; spend = mn = None
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]; d = dec(ix["data"])
        if p == CB and d:
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cul = int.from_bytes(d[1:5], "little")
        elif p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and keys[ix["accounts"][1]] in TIP: tips.append(TIP[keys[ix["accounts"][1]]])
        elif p == PUMP and len(d) >= 24:
            cands = [keys[a] for a in ix["accounts"][:4]]
            mint = next((c for c in cands if c in L), cands[2] if len(cands) > 2 else None)          # old layout: mint = #2; v2 (quote mint) layout: mint = #1
            a1 = int.from_bytes(d[8:16], "little"); a2 = int.from_bytes(d[16:24], "little"); spend, mn = a1, a2
    s = block(t["slot"]); idx = s.index(sig) if sig in s else None
    return dict(slot=t["slot"], idx=idx, size=len(s), mint=mint, spend=spend, min_out=mn, prio=cup * cul / 1e15, svc="+".join(sorted(set(tips))) or "none", signer=keys[0],
                err=json.dumps(t["meta"]["err"]))
L = rp.load_launches()
es = rpc("getEpochSchedule", []); SCH = {}
def leader(slot):
    ep = (slot - es["firstNormalSlot"]) // es["slotsPerEpoch"]; first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]
    if ep not in SCH: s = rpc("getLeaderSchedule", [slot]) or {}; SCH[ep] = {first + i: k for k, v in s.items() for i in v}
    return SCH[ep].get(slot)
NODES = {n["pubkey"]: n for n in rpc("getClusterNodes", [])}
def client(i):
    c = (NODES.get(i or "") or {}).get("clientId") or ""
    return "BAM" if "Bam" in c or "BAM" in c else ("Harmonic" if "Harmonic" in c else ("Jito" if c in ("JitoLabs", "Rakurai") else ("Firedancer" if "dancer" in c.lower() else c or "?")))
GEO = {}
def geo(idents):
    ips = {}
    for i in idents:
        n = NODES.get(i or "") or {}; a = n.get("tpu") or n.get("gossip") or ""
        if a: ips[i] = a.rsplit(":", 1)[0]
    u = sorted(set(ips.values()) - set(GEO))
    for k in range(0, len(u), 100):
        for g in json.load(urllib.request.urlopen(urllib.request.Request("http://ip-api.com/batch?fields=query,city,org", data=json.dumps(u[k:k + 100]).encode(), headers={"content-type": "application/json"}), timeout=60)): GEO[g["query"]] = g
    return {i: GEO.get(ips.get(i), {}) for i in idents}
def ms(a, b): return (b[0] - a[0]) * 212.0 + (b[1] / max(b[2], 1) - a[1] / max(a[2], 1)) * 212.0
def fr(t): return ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
def replay(tr, ke, s_in, B, hold_slots, sl=0.10):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]; f = fr(tr[ke - 1]); X = int(B / (1 + f)); q = T * X // (V + X); V += X; T -= q
    cost = B / 1e9 + 0.0008; frs = f; s_out = s_in + hold_slots
    for t in tr[ke:]:
        if t["s"] >= s_out: break
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = fr(t); v = ((V * q / (T + q)) * (1 - frs) / 1e9 - 0.0008) / cost
        if s_out > t["s"] + 1 and v <= 1 - sl: s_out = t["s"] + 1
    return (V * q / (T + q)) * (1 - frs) / 1e9 - 0.0008 - cost
WALLETS = {"2g FRA": ("rev_2g.json", 19, time.time() - 3.5 * 3600), "AMS": ("rev_ams.json", 6, time.time() - 4 * 3600)}   # hold slots: FRA run 10 ~4 s, AMS 1.3 s
out = []
for wname, (f, hold, t0) in WALLETS.items():
    R = [r for r in json.load(open(f)) if not r["ok"] and r["signer"] and r["bt"] >= t0]
    with cf.ThreadPoolExecutor(8) as ex: I = list(ex.map(lambda r: txinfo(r["sig"]), R))
    byb = collections.defaultdict(set)
    for i in I:
        if i and i["mint"] in L: byb[(L[i["mint"]]["run"], rp.bucket(i["mint"]))].add(i["mint"])
    tapes = {}
    for k, msx in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], msx))
    for r, i in zip(R, I):
        if not i or "6042" not in i["err"] or i["idx"] is None: continue
        tr = tapes.get(i["mint"], []); me = (i["slot"], i["idx"])
        dk = max((k for k, t in enumerate(tr) if (t["s"], t["i"]) < me and not t["buy"] and t["sol"] >= 1e9), default=None)
        if dk is None: continue
        d = tr[dk]; dsz = len(block(d["s"])); dpos = (d["s"], d["i"], dsz)
        btw = [t for t in tr[dk + 1:] if (t["s"], t["i"]) < me]
        cross = next((t for t in btw if (lambda X: t["vtok"] * X // (t["vsol"] + X))(int(i["spend"] / (1 + fr(t)))) < i["min_out"]), None)
        ke_me = next((k for k, t in enumerate(tr) if (t["s"], t["i"]) > me), None)
        kc = tr.index(cross) if cross else None
        row = dict(wallet=wname, sig=r["sig"], mint=i["mint"], spend=i["spend"] / 1e9, slot=i["slot"], our_leader=leader(i["slot"]), dump_leader=leader(d["s"]),
                   slots_late=i["slot"] - d["s"], our_ms=ms(dpos, (i["slot"], i["idx"], i["size"])), our_prio=i["prio"], our_svc=i["svc"], n_between=len(btw),
                   move=((btw[-1]["vsol"] / btw[-1]["vtok"]) / (d["vsol"] / d["vtok"])) if btw else 1.0)
        if cross:
            ci = txinfo(cross["sig"]) or {}
            row.update(cross_user=cross["user"], cross_sol=cross["sol"] / 1e9, cross_ms=ms(dpos, (cross["s"], cross["i"], len(block(cross["s"])))), cross_prio=ci.get("prio"), cross_svc=ci.get("svc"))
        row["pnl_if_filled"] = replay(tr, ke_me, i["slot"], i["spend"], hold) if ke_me else None
        row["pnl_if_won_race"] = replay(tr, kc, cross["s"], i["spend"], hold) if kc else None
        out.append(row)
G = geo({r["our_leader"] for r in out} | {r["dump_leader"] for r in out})
for r in out:
    g = G.get(r["our_leader"], {}); r["city"] = g.get("city") or "?"; r["host"] = (g.get("org") or "?")[:20]; r["client"] = client(r["our_leader"]); r["near_fra"] = r["our_leader"] in NEAR_FRA
json.dump(out, open("revdeep.json", "w"), default=str)
med = lambda v: statistics.median(v) if v else float("nan")
for w in WALLETS:
    v = [r for r in out if r["wallet"] == w]
    if not v: continue
    print(f"\n######## {w}: {len(v)} guard reverts analysed")
    for r in sorted(v, key=lambda r: r["slot"]):
        print(f"  {r['mint'][:6]} {r['client']:10s} {r['city'][:14]:14s} near-FRA {'Y' if r['near_fra'] else 'n'} | same leader as dump {'Y' if r['our_leader'] == r['dump_leader'] else 'n'} +{r['slots_late']} slot | "
              f"we {r['our_ms']:6.1f} ms vs crossing {r.get('cross_ms', float('nan')):6.1f} ms ({str(r.get('cross_user', '?'))[:6]} {r.get('cross_svc', '?')}, prio {r.get('cross_prio') or 0:.5f}) | "
              f"price +{(r['move'] - 1) * 100:4.1f}% | if filled {r['pnl_if_filled'] if r['pnl_if_filled'] is not None else float('nan'):+.4f} | if won race {r['pnl_if_won_race'] if r['pnl_if_won_race'] is not None else float('nan'):+.4f}")
    a = [r["pnl_if_filled"] for r in v if r["pnl_if_filled"] is not None]; b = [r["pnl_if_won_race"] for r in v if r["pnl_if_won_race"] is not None]
    print(f"  SUM: as if filled (looser guard) {sum(a):+.3f} SOL ({sum(1 for x in a if x > 0)}/{len(a)} win) | if we had won the race {sum(b):+.3f} SOL ({sum(1 for x in b if x > 0)}/{len(b)} win)")
    print(f"  median: we landed {med([r['our_ms'] for r in v]):.1f} ms after the dump, the crossing buy {med([r['cross_ms'] for r in v if 'cross_ms' in r]):.1f} ms | "
          f"same slot as dump {sum(1 for r in v if r['slots_late'] == 0)}/{len(v)} | our leader in Frankfurt-near list {sum(r['near_fra'] for r in v)}/{len(v)}")
    print(f"  by client: {collections.Counter(r['client'] for r in v).most_common()} | by city: {collections.Counter(r['city'] for r in v).most_common(5)}")
    print(f"  crossing buy sent via: {collections.Counter(r.get('cross_svc') for r in v).most_common(5)} | prio med {med([r['cross_prio'] for r in v if r.get('cross_prio') is not None]):.5f} vs ours {med([r['our_prio'] for r in v]):.5f}")
