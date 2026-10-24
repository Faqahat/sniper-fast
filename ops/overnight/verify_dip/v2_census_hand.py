#!/usr/bin/env python3
# Claim 5 hand-check (READ-ONLY RPC getTransaction; endpoint from ~/.config/sniper/ck_rpc_url, never printed): 5 census round trips
# each of DYXDDrZC... and HkQ7hMjy..., chosen at random (seed 5) among trips the census counts. For the buy tx and every sell tx:
# the wallet's SOL balance change (pre/post balances: includes pump fees, tx fee, tips, ATA rent) and its token change for the mint,
# plus the TradeEvent of that wallet. Compared with the census's cost (= SOL in x 1.0125) and back (= SOL out x 0.9875).
import os, json, gzip, random, time, base64, urllib.request
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TD = bytes.fromhex("bddb7fd34ee661ee")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if r.get("result") is not None: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
    return None
def look(sig, wallet, mint):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not t: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    i = keys.index(wallet) if wallet in keys else None
    dsol = (t["meta"]["postBalances"][i] - t["meta"]["preBalances"][i]) / 1e9 if i is not None else None
    def tb(lst):
        return sum(int(b["uiTokenAmount"]["amount"]) for b in (lst or []) if b.get("owner") == wallet and b.get("mint") == mint)
    dtok = tb(t["meta"].get("postTokenBalances")) - tb(t["meta"].get("preTokenBalances"))
    ev = []
    for l in (t["meta"].get("logMessages") or []):
        if l.startswith("Program data: "):
            x = l[14:].strip(); x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 97 and b58enc(raw[8:40]) == mint and b58enc(raw[57:89]) == wallet:
                ev.append(dict(sol=int.from_bytes(raw[40:48], "little") / 1e9, tok=int.from_bytes(raw[48:56], "little"), buy=raw[56]))
    return dict(dsol=dsol, dtok=dtok, fee=t["meta"]["fee"] / 1e9, payer=msg["accountKeys"][0] == wallet, err=t["meta"].get("err"), ev=ev, slot=t["slot"])
if __name__ == "__main__":
    R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/census_v2.jsonl.gz", "rt")]
    rnd = random.Random(5); out = []
    for U in ("DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"):
        pool = [r for r in R if r["u"] == U and not r["nosell"]]
        for r in rnd.sample(pool, 5):
            b = look(r["bsig"], U, r["m"]); ss = [look(s[0], U, r["m"]) for s in r["sells"]]
            out.append(dict(trip=r, buy=b, sells=ss))
            sd = sum(x["dsol"] for x in ss if x and x["dsol"] is not None)
            st = sum(x["dtok"] for x in ss if x)
            print(f"{U[:8]} {r['m'][:8]} buy {r['bsig'][:10]} dt {r['dt']:5.1f} ms hold {r['hold']:4d} slots sells {len(r['sells'])} (full {r['full']}, sell tx shared with other trips: see json)")
            print(f"   census: cost {r['cost']:.5f} back {r['back']:.5f} P&L {r['back'] - r['cost']:+.5f} | tokens bought {r['tok']} sold-attributed {r['sold']} | collector tx costs {r['txc']:.5f}")
            print(f"   chain : buy wallet dSOL {b['dsol']:+.5f} dTOK {b['dtok']} (event SOL {b['ev'][0]['sol'] if b['ev'] else None}, fee {b['fee']:.6f}, payer {b['payer']}) |"
                  f" sells wallet dSOL {sd:+.5f} dTOK {st} | net {b['dsol'] + sd:+.5f}")
            for s_, x in zip(r["sells"], ss):
                if x: print(f"      sell {s_[0][:10]} took {s_[2]} of its {s_[3]} tokens | dSOL {x['dsol']:+.5f} dTOK {x['dtok']} events {[(e['sol'], e['tok']) for e in x['ev']]}")
    json.dump(out, open("/home/moiz/sniper/ops/overnight/verify_dip/v2_out/census_hand.json", "w"))
