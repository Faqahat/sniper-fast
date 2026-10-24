#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA's exit triggers. Each sell carries a router flag (byte 2 = trigger type, byte 3 = urgent/high
# fee). For tokens inside our collector windows, look at what happened between its buy and its sell in chain order:
# peak / last spot price multiple vs its entry, insider (creator / bundle) sells, outside buys / sells, slots and the time
# since the last outside buy. Output: exits.txt / exits.json
import os, sys, json, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
L = rp.load_launches(); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
LED = {r["sig"]: r for r in json.load(open(os.path.join(HERE, "ledger_CWiNFA.json")))["txs"] if not r.get("missing")}
ms = [m for m, v in C.items() if v.get("buy") and v.get("sells") and m in L]
byb = collections.defaultdict(set)
for m in ms: byb[(C[m]["run"], rp.bucket(m))].add(m)
rows = []
for key, mm in byb.items():
    tra = rp.read_bucket(key[0], key[1], mm)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); v = C[m]
        kb = next((k for k, t in enumerate(tr) if t["sig"] == v["buy"]["sig"]), None)
        ks = next((k for k, t in enumerate(tr) if t["sig"] == v["sells"][0]["sig"]), None)
        if kb is None or ks is None: continue
        b = tr[kb]; p_in = b["sol"] / b["tok"]
        seg = tr[kb + 1:ks]
        mults = [(t["vsol"] / t["vtok"]) / p_in for t in seg if t["vtok"]]
        last_mult = mults[-1] if mults else (b["vsol"] / b["vtok"]) / p_in
        ins_sells = [t for t in seg if not t["buy"] and t["user"] in st["insiders"]]
        out_buys = [t for t in seg if t["buy"] and t["user"] not in st["insiders"]]
        out_sells = [t for t in seg if not t["buy"] and t["user"] not in st["insiders"]]
        s = tr[ks]; led = LED.get(s["sig"]) or {}
        first_ins = next((t for t in seg if not t["buy"] and t["user"] in st["insiders"]), None)
        tp_hit = next((t for t in seg if t["vtok"] and (t["vsol"] / t["vtok"]) / p_in >= 1.3), None)
        rows.append(dict(m=m, flags=(led.get("router") or {}).get("flags"), hold=s["s"] - b["s"], last_mult=round(last_mult, 4), peak=round(max(mults) if mults else 1.0, 4),
                         trough=round(min(mults) if mults else 1.0, 4), n_ins_sells=len(ins_sells), n_out_buys=len(out_buys), n_out_sells=len(out_sells),
                         slots_after_ins=(s["s"] - first_ins["s"]) if first_ins else None, slots_after_tp=(s["s"] - tp_hit["s"]) if tp_hit else None,
                         slots_since_last_out_buy=(s["s"] - out_buys[-1]["s"]) if out_buys else None, same_slot=s["s"] == b["s"],
                         ins_sell_same_slot_as_buy=any((not t["buy"]) and t["user"] in st["insiders"] and t["s"] == b["s"] for t in tr[kb + 1:])))
json.dump(rows, open(os.path.join(HERE, "exits.json"), "w"))
out = []
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))] if xs else None
NAMES = {"010000": "normal", "010101": "urgent, insider sold", "010500": "type 05", "010601": "type 06 (urgent)", "010701": "type 07 (urgent)", "010901": "type 09"}
for f, g in sorted(collections.defaultdict(list, {k: [r for r in rows if r["flags"] == k] for k in {r["flags"] for r in rows}}).items(), key=lambda kv: -len(kv[1])):
    if not g: continue
    out.append(f"== flag {f} ({NAMES.get(f, '?')}): {len(g)} tokens in the collector windows")
    out.append(f"   hold slots: p10 {q([r['hold'] for r in g], .1)} median {statistics.median(r['hold'] for r in g)} p90 {q([r['hold'] for r in g], .9)}; same slot as the buy {sum(r['same_slot'] for r in g)}")
    out.append(f"   price multiple vs its entry: last before sell median {statistics.median(r['last_mult'] for r in g):.3f} (min {min(r['last_mult'] for r in g):.3f}, max {max(r['last_mult'] for r in g):.3f}); "
               f"peak before sell median {statistics.median(r['peak'] for r in g):.3f}; trough median {statistics.median(r['trough'] for r in g):.3f}")
    out.append(f"   insider sold before its sell: {sum(r['n_ins_sells'] > 0 for r in g)}/{len(g)} (slots from the first insider sell to its sell: median {statistics.median([r['slots_after_ins'] for r in g if r['slots_after_ins'] is not None] or [None]) if any(r['slots_after_ins'] is not None for r in g) else '-'}); "
               f"insider sold in its buy slot: {sum(r['ins_sell_same_slot_as_buy'] for r in g)}")
    out.append(f"   price reached 1.3x before its sell: {sum(r['slots_after_tp'] is not None for r in g)}/{len(g)} (slots from first 1.3x to its sell, median {statistics.median([r['slots_after_tp'] for r in g if r['slots_after_tp'] is not None]) if any(r['slots_after_tp'] is not None for r in g) else '-'})")
    out.append(f"   outside buys between buy and sell median {statistics.median(r['n_out_buys'] for r in g)}, outside sells median {statistics.median(r['n_out_sells'] for r in g)}; "
               f"slots since the last outside buy median {statistics.median([r['slots_since_last_out_buy'] for r in g if r['slots_since_last_out_buy'] is not None] or [0])}")
# normal sells: is the hold a fixed time? hold vs number of buys
g = [r for r in rows if r["flags"] == "010000"]
if g:
    for lo, hi in ((0, 2), (3, 5), (6, 9), (10, 15), (16, 30), (31, 999)):
        x = [r for r in g if lo <= r["hold"] <= hi]
        if x: out.append(f"   normal sells, hold {lo}-{hi} slots: n {len(x)}, last mult median {statistics.median(r['last_mult'] for r in x):.3f}, peak median {statistics.median(r['peak'] for r in x):.3f}, slots since last outside buy median {statistics.median([r['slots_since_last_out_buy'] for r in x if r['slots_since_last_out_buy'] is not None] or [0])}")
open(os.path.join(HERE, "exits.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
