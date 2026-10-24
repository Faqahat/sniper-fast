#!/usr/bin/env python3
# READ-ONLY, offline: everything the HTML page needs for CWiNFA's last N snipes that fall inside our collector data
# (ledger_CWiNFA.json = its own txs; coll_cw.json + trade rows = each launch's create block in chain order;
# arrival_ms.json = when our engine saw its tx). Output: snipes15.json
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"; RENT = 0.00203928
L = rp.load_launches(); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
LED = [r for r in json.load(open(os.path.join(HERE, "ledger_CWiNFA.json")))["txs"] if not r.get("missing")]
ARR = {r["m"]: r["ms"] for r in json.load(open(os.path.join(HERE, "arrival_ms.json")))}
by_sig = {r["sig"]: r for r in LED}
buys = [r for r in LED if (r.get("router") or {}).get("tag") == 2 and not r["err"] and r["ev"]]
picks = []
for b in reversed(buys):
    m = b["ev"][0]["mint"]
    if m in C and C[m].get("buy") and C[m]["buy"]["sig"] == b["sig"] and m in L: picks.append((b, m))
    if len(picks) >= N: break
out = []
byb = collections.defaultdict(set)
for b, m in picks: byb[(L[m]["run"], rp.bucket(m))].add(m)
TR = {}
for key, mm in byb.items(): TR.update(rp.read_bucket(key[0], key[1], mm))
for b, m in picks:
    c = L[m]; v = C[m]; tr = TR[m]; st = rp.structure(tr, c); g = st["g_end"]
    k0 = next(k for k, t in enumerate(tr) if t["sig"] == b["sig"])
    sells = [r for r in LED if (r.get("router") or {}).get("tag") == 3 and not r["err"] and r["ev"] and r["ev"][0]["mint"] == m]
    s0 = sells[0] if sells else None
    block = []
    for k, t in enumerate(tr[:k0 + 1]):
        if not t["buy"] and t["user"] != W: continue
        role = "dev (create)" if t["sig"] == c.get("sig") else ("dev bundle" if t in st["glued"] else ("CWiNFA" if t["user"] == W else ("insider" if t["user"] in st["insiders"] else "outside buyer")))
        block.append(dict(pos=k - (g - 1), slot_d=t["s"] - c["slot"], role=role, who=t["user"], sol=t["sol"] / 1e9, fee=(t["fee"] or 0) / 1e9, tips=(t["tips"] or 0) / 1e9, sig=t["sig"]))
    # the first few outside buys AFTER it (who followed)
    after = [dict(pos=k - (g - 1), slot_d=t["s"] - c["slot"], who=t["user"], sol=t["sol"] / 1e9, fee=(t["fee"] or 0) / 1e9, tips=(t["tips"] or 0) / 1e9, sig=t["sig"])
             for k, t in enumerate(tr[k0 + 1:], start=k0 + 1) if t["buy"] and t["user"] not in st["insiders"]][:5]
    ge = tr[g - 1]; p_b = ge["vsol"] / ge["vtok"]
    e = b["ev"][0]
    realized = b["sol_chg"] + sum(r["sol_chg"] for r in sells) + RENT
    out.append(dict(mint=m, name=c.get("name"), symbol=c.get("symbol"), uri=c.get("uri"), deployer=c.get("user"), creator=c.get("creator"), create_sig=c.get("sig"), S=c["slot"], create_bt=c.get("bt"),
                    dev_sol=v.get("dev"), bundle_sol=v.get("glued_sol"), bundle_legs=v.get("glued"),
                    buy_sig=b["sig"], buy_slot=b["slot"], buy_bt=b["bt"], slot_d=b["slot"] - c["slot"], version=b["v"], nonce=b["nonce"], cu=b["cu"], fee=b["fee"], tips=b["tips"],
                    min_out=b["router"]["min_out"], got=e["tok"], size=1.0, curve_sol=e["sol"] / 1e9, entry_mult=(e["sol"] / e["tok"]) / p_b,
                    ahead=v["buy"]["ahead_tx"], arrival_ms=ARR.get(m), block=block, after=after,
                    sell=dict(sig=s0["sig"], slot=s0["slot"], bt=s0["bt"], flags=s0["router"].get("flags"), fee=s0["fee"], tips=s0["tips"], hold_slots=s0["slot"] - b["slot"],
                              mult=((s0["ev"][0]["sol"] / s0["ev"][0]["tok"]) / (e["sol"] / e["tok"])) if s0 and s0["ev"][0]["tok"] else None) if s0 else None,
                    realized=realized))
json.dump(dict(wallet=W, snipes=out), open(os.path.join(HERE, "snipes15.json"), "w"), indent=1)
for s in out:
    print(f"{(s['symbol'] or '')[:10]:10} slot+{s['slot_d']} ahead {s['ahead']} ms {s['arrival_ms']} v{s['version']} tip {s['tips']} sell {s['sell']['flags'] if s['sell'] else None} hold {s['sell']['hold_slots'] if s['sell'] else None} -> {s['realized']:+.4f}")
