#!/usr/bin/env python3
# READ-ONLY, offline: dKMjeG on every collected launch (R1 + R2 phase-A rows): its buys / sells / failed txs with exact
# chain position, outside buys ahead, entry price vs the post-bundle price P0, every sell's timing / share / price
# multiple / dev-or-bundle sell in the same or previous slot, plus a market outcome for EVERY launch (price vs P0 at
# +1 s / +5 s / +15 s / +60 s, peak in 60 s) so its picks can be compared with the average launch. -> coll.json
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
L = rp.load_launches(); O = rp.load_obs()
byb = collections.defaultdict(set)
for m, c in L.items():
    if c.get("bt"): byb[(c["run"], rp.bucket(m))].add(m)
HZ = {"1s": 5, "5s": 24, "15s": 71, "60s": 283}
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]); out = {}
    for m, tr in tra.items():
        c = L[m]; S = c["slot"]
        sol_q = all(t["vtok"] and 25e9 <= t["vsol"] <= 200e9 for t in tr[:50])
        st = rp.structure(tr, c); ge = st["g_end"]
        r = dict(run=run, bt=c.get("bt"), dep=c.get("user"), creator=st["creator"], solq=sol_q, ntr=len(tr), glued=len(st["glued"]),
                 dev=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 4),
                 gsol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 4), mayhem=int("InitializeMayhemState" in (c.get("ixn") or [])))
        if ge >= 1 and sol_q:
            P0 = tr[ge - 1]["vsol"] / tr[ge - 1]["vtok"]; r["mc0"] = round(P0 * 1e6, 3)
            px = {}; pk = 1.0; V, T = tr[ge - 1]["vsol"], tr[ge - 1]["vtok"]; hz = sorted(HZ.items(), key=lambda x: x[1]); hi = 0
            for t in tr[ge:]:
                d = t["s"] - S
                while hi < len(hz) and d > hz[hi][1]: px[hz[hi][0]] = round((V / T) / P0, 4); hi += 1
                V, T = t["vsol"], t["vtok"]
                if d <= 283 and T: pk = max(pk, (V / T) / P0)
            for k, _ in hz[hi:]: px[k] = round((V / T) / P0, 4) if T else None
            r["px"] = px; r["pk60"] = round(pk, 4); r["grad"] = int(max(t["vsol"] for t in tr) >= rp.GRAD_VSOL)
            # first outside buyers (rank list): who was first after the bundle
            ob = [t for t in tr[ge:] if t["buy"] and t["user"] not in st["insiders"]]
            r["first_out"] = ob[0]["user"][:6] if ob else None
        mine = [(k, t) for k, t in enumerate(tr) if t["user"] == W]
        fl = [(s, i) for s, i, u in fa.get(m, []) if u == W]
        if mine or fl:
            d = dict(fail=[[s - S, i] for s, i in fl])
            if fl and ge >= 1 and sol_q:
                # price state just before each failed tx (block order) vs P0 -> how far the price had run when it failed
                fx = []
                for s, i in fl:
                    prev = [t for t in tr if (t["s"], t["i"]) < (s, i)]
                    if prev and prev[-1]["vtok"]: fx.append(round((prev[-1]["vsol"] / prev[-1]["vtok"]) / P0, 4))
                d["fail_px"] = fx
                d["fail_ahead"] = [sum(1 for t in tr[ge:] if t["buy"] and t["user"] not in st["insiders"] and (t["s"], t["i"]) < (s, i)) for s, i in fl]
            buys = [(k, t) for k, t in mine if t["buy"]]; sells = [(k, t) for k, t in mine if not t["buy"]]
            if buys:
                k0, b0 = buys[0]
                d.update(bslot=b0["s"] - S, bidx=b0["i"], bsol=round(sum(t["sol"] for _, t in buys) / 1e9, 4), nbuys=len(buys),
                         btok=sum(t["tok"] for _, t in buys), bfee=b0["fee"], btips=b0["tips"], bpayer=b0["payer"][:6],
                         ahead=sum(1 for t in tr[ge:k0] if t["buy"] and t["user"] not in st["insiders"]),
                         ahead_tx=len({t["sig"] for t in tr[ge:k0] if t["user"] not in st["insiders"]}),
                         in_bundle=int(k0 < ge), sig=b0["sig"])
                if ge >= 1 and sol_q:
                    pin = sum(t["sol"] for _, t in buys) / sum(t["tok"] for _, t in buys)
                    d["entry_x"] = round(pin / P0, 4)                                   # avg fill price vs post-bundle price
                    d["pre_x"] = round((tr[k0 - 1]["vsol"] / tr[k0 - 1]["vtok"]) / P0, 4) if k0 >= 1 else 1.0
                    ins = st["insiders"]; tot = sum(t["tok"] for _, t in buys); sl = []
                    for k, t in sells:
                        same = any((not x["buy"]) and x["user"] in ins and x["s"] == t["s"] and x["i"] < t["i"] for x in tr[k0:k])
                        prevs = any((not x["buy"]) and x["user"] in ins and x["s"] == t["s"] - 1 for x in tr[k0:k])
                        outs_before = sum(1 for x in tr[k0 + 1:k] if x["user"] not in ins and x["user"] != W and not x["buy"])
                        pk_before = max([(x["vsol"] / x["vtok"]) for x in tr[k0:k] if x["vtok"]] or [pin])
                        sl.append(dict(ds=t["s"] - b0["s"], frac=round(t["tok"] / tot, 4), x=round((t["sol"] / t["tok"]) / pin, 4) if t["tok"] else None,
                                       sol=round(t["sol"] / 1e9, 4), ins_same=int(same), ins_prev=int(prevs), out_sells_before=outs_before,
                                       pkx_before=round(pk_before / pin, 4), px_before=round((tr[k - 1]["vsol"] / tr[k - 1]["vtok"]) / pin, 4) if tr[k - 1]["vtok"] else None,
                                       fee=t["fee"], tips=t["tips"]))
                    d["sells"] = sl
                    d["left_tok"] = tot - sum(t["tok"] for _, t in sells)
            if O.get(m):
                a = [x for x in O[m]["outs"] if x[3] == "dKMjeG"]
                if a: d["ms"] = [list(x[:3]) for x in a[:6]]
            r["dk"] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json", "w"))
    dk = {m: v for m, v in res.items() if "dk" in v}
    print("launches", len(res), "| dK touched", len(dk), "| filled", sum(1 for v in dk.values() if "bslot" in v["dk"]),
          "| failed-only", sum(1 for v in dk.values() if "bslot" not in v["dk"]))
