#!/usr/bin/env python3
# Claim 1 check (READ-ONLY RPC: getTransaction only; the endpoint URL is read from ~/.config/sniper/ck_rpc_url and never printed).
# Fresh random sample of dip trigger txs, classified with an independent decoder:
#   A: 200 triggers from dipshadow/trig_sigs_all.jsonl whose sig is NOT in trig_tx.jsonl (so their label in direct_flags_prelim.json
#      comes from direct_rule.py's whitelist rule, never fitted on them) -> out-of-sample accuracy of the rule;
#   B: 100 out-of-fold picks (trig_sigs.jsonl, src oof_L35/oof_L75) that ARE in trig_tx.jsonl -> re-check of fetch_trig.py's truth.
# Decoder: static keys + ALT-loaded keys; pump TradeEvents from "Program data:" logs (or the self-CPI event ix); the trigger is the
# sell event with the event file's seller and SOL amount; "direct" = a TOP-LEVEL pump.fun instruction on the mint whose accounts
# include that seller; also records the discriminator, whether mint/seller come from an address lookup table, and the router.
# usage: python3 -I v2_fresh_cls.py  -> v2_out/fresh_cls.jsonl, summary on stdout
import os, json, random, time, base64, collections, urllib.request, concurrent.futures as cf
SH = "/home/moiz/sniper/ops/overnight/dipshadow"; OUTD = "/home/moiz/sniper/ops/overnight/verify_dip/v2_out"
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TD = bytes.fromhex("bddb7fd34ee661ee")            # TradeEvent discriminator
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
U64 = lambda b, o: int.from_bytes(b[o:o + 8], "little")
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if "result" in r and r["result"] is not None: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
    return None
def trade_events(t, keys):
    ev = []
    for l in (t["meta"].get("logMessages") or []):
        if l.startswith("Program data: "):
            x = l[14:].strip(); x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 89: ev.append(raw[8:])
    if not ev:
        for inn in (t["meta"].get("innerInstructions") or []):
            for ix in inn["instructions"]:
                if keys[ix["programIdIndex"]] == PUMP:
                    raw = b58dec(ix["data"])
                    if raw[8:16] == TD: ev.append(raw[16:])
    out = []
    for p in ev:
        out.append(dict(mint=b58enc(p[0:32]), sol=U64(p, 32), tok=U64(p, 40), buy=p[48], user=b58enc(p[49:81])))
    return out
def classify(e):
    t = rpc("getTransaction", [e["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not t: return dict(sig=e["sig"], ok=False)
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    static = msg["accountKeys"]; keys = static + la.get("writable", []) + la.get("readonly", [])
    m, seller = e["m"], e["user"]
    evs = trade_events(t, keys)
    trig = [x for x in evs if x["mint"] == m and not x["buy"] and x["user"] == seller]
    trig_exact = [x for x in trig if x["sol"] == e["sol"]]
    tops = []; router = None
    for k, ix in enumerate(msg["instructions"]):
        p = keys[ix["programIdIndex"]]; accs = [keys[a] for a in ix["accounts"]]
        if m not in accs: continue
        d = b58dec(ix["data"])
        if p == PUMP: tops.append(dict(k=k, disc=d[:8].hex(), nacc=len(accs), seller_in=seller in accs, a8=U64(d, 8) if len(d) >= 16 else None))
        elif router is None and p not in ("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
            router = p
    top_seller = [x for x in tops if x["seller_in"]]
    tok = trig_exact[0]["tok"] if trig_exact else None
    return dict(sig=e["sig"], ok=True, version=t.get("version"), err=t["meta"].get("err"), n_ev=len(evs), n_trig=len(trig), trig_exact=len(trig_exact),
                direct_any=bool(tops), direct_seller=bool(top_seller), discs=sorted({x["disc"] for x in tops}),
                a8_eq_tok=any(x["a8"] == tok for x in top_seller) if tok is not None else None,
                mint_in_alt=m not in static, seller_in_alt=seller not in static, router=router, signer=static[0], seller_signs=static[0] == seller,
                outer=[keys[ix["programIdIndex"]] for ix in msg["instructions"]])
if __name__ == "__main__":
    truth = {}
    for l in open(f"{SH}/trig_tx.jsonl"):
        r = json.loads(l); truth[r["sig"]] = r["kind"]
    flags = json.load(open("/home/moiz/sniper/ops/overnight/verify_dip/v2_snap/direct_flags_prelim.json"))
    rnd = random.Random(20261023)
    allev = [json.loads(l) for l in open(f"{SH}/trig_sigs_all.jsonl")]
    fresh = [e for e in allev if e.get("sig") and e["sig"] not in truth]
    A = rnd.sample(fresh, 200)
    picks = [json.loads(l) for l in open(f"{SH}/trig_sigs.jsonl")]
    picks = [e for e in picks if e.get("sig") and e["src"] in ("oof_L35", "oof_L75") and e["sig"] in truth]
    seen = set(); P = []
    for e in rnd.sample(picks, len(picks)):
        if e["sig"] in seen: continue
        seen.add(e["sig"]); P.append(e)
        if len(P) == 100: break
    jobs = [("A", e) for e in A] + [("B", e) for e in P]
    prev = {}
    if os.path.exists(f"{OUTD}/fresh_cls.jsonl"):
        for l in open(f"{OUTD}/fresh_cls.jsonl"):
            r = json.loads(l)
            if r.get("ok") and r.get("version") is not None: prev[(r["grp"], r["sig"])] = r
    print("fresh pool", len(fresh), "sample A", len(A), "picks pool", len(picks), "sample B", len(P), flush=True)
    res = []
    with cf.ThreadPoolExecutor(8) as ex:
        for (grp, e), r in zip(jobs, ex.map(lambda j: prev.get((j[0], j[1]["sig"])) or classify(j[1]), jobs)):
            r.update(grp=grp, m=e["m"], age=e["age"], flag=flags.get(f'{e["m"]}|{e["age"]}'), truth=truth.get(e["sig"]), src=e["src"], sol_ev=e["sol"])
            res.append(r)
    with open(f"{OUTD}/fresh_cls.jsonl", "w") as f:
        for r in res: f.write(json.dumps(r) + "\n")
    ok = [r for r in res if r["ok"]]
    print("fetched", len(ok), "of", len(res))
    for grp in ("A", "B"):
        g = [r for r in ok if r["grp"] == grp]
        print(f"\n== sample {grp}: n {len(g)} | trigger event found {sum(r['trig_exact'] > 0 for r in g)} | direct (top-level pump ix on mint) {sum(r['direct_any'] for r in g)}"
              f" | direct with the seller in that ix {sum(r['direct_seller'] for r in g)}")
        cm = collections.Counter((r["direct_seller"], r["flag"] if grp == "A" else (r["truth"] == "top")) for r in g)
        print("   (mine direct, label direct):", dict(cm))
        agree = sum(1 for r in g if r["direct_seller"] == bool(r["flag"] if grp == "A" else r["truth"] == "top"))
        print(f"   agreement {agree}/{len(g)}")
        print("   discriminators of direct:", collections.Counter(d for r in g if r["direct_seller"] for d in r["discs"]).most_common())
        print("   a8 == tokens sold (direct):", collections.Counter(r["a8_eq_tok"] for r in g if r["direct_seller"]))
        print("   mint via ALT (direct):", sum(r["mint_in_alt"] for r in g if r["direct_seller"]), " seller via ALT:", sum(r["seller_in_alt"] for r in g if r["direct_seller"]),
              " seller signs:", sum(r["seller_signs"] for r in g if r["direct_seller"]))
        print("   routers (routed):", collections.Counter(r["router"] for r in g if not r["direct_seller"]).most_common(8))
        for r in g:
            if r["direct_seller"] != bool(r["flag"] if grp == "A" else r["truth"] == "top"):
                print("   MISMATCH", r["sig"][:20], "mine", r["direct_seller"], "any", r["direct_any"], "label", r["flag"], r["truth"], "discs", r["discs"], "outer", [o[:8] for o in r["outer"]])
