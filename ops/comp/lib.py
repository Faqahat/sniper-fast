# READ-ONLY offline helpers over /root/comp/tapes_*.jsonl
import json, collections, math, os
ROOT = os.environ.get("SNIPER_ROOT", "/root")
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
K = V0 * T0
SLOT_S = 0.4  # INFERRED: mean slot time used to convert slot deltas to seconds
NODES = {x["pubkey"]: x.get("clientId", "?") for x in json.load(open(ROOT + "/stakepaths/clusternodes.json"))["result"]}
W4 = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"

def pre_state(e):
    # e = [buy,user,sol,tok,vsol,vtok,rsol,fbps,fee,cbps,cfee,ts] or an ordered-event dict
    if isinstance(e, dict):
        return (e["vsol"] - e["sol"], e["vtok"] + e["tok"]) if e["buy"] else (e["vsol"] + e["sol"], e["vtok"] - e["tok"])
    return (e[4] - e[2], e[5] + e[3]) if e[0] else (e[4] + e[2], e[5] - e[3])

def order_launch(r):
    """returns list of event dicts in chain order + stats"""
    S = r["slot"]
    later = {x["sig"][:20]: x for x in (r.get("later") or [])}
    byslot = collections.defaultdict(list)
    for t in r.get("txs") or []:
        if t["ev"]:
            byslot[t["slot"]].append(t)
    out = []; fb = 0; cur = None
    for s in sorted(byslot):
        txs = byslot[s]
        if s == S:
            for t in txs:
                lt = later.get(t["sig"][:20])
                t["_d"] = lt["d"] if lt else None
            known = sorted([t for t in txs if t["_d"] is not None], key=lambda t: t["_d"])
            unk = [t for t in txs if t["_d"] is None]
            seq = known + unk
            fb += len(unk)
        else:
            seq = []; rest = list(txs)
            while rest:
                j = None
                if cur is not None:
                    for i, t in enumerate(rest):
                        if pre_state(t["ev"][0]) == cur: j = i; break
                if j is None:
                    fb += 1 if cur is not None else 0
                    j = min(range(len(rest)), key=lambda i: abs(pre_state(rest[i]["ev"][0])[0] - (cur[0] if cur else 0)))
                t = rest.pop(j); seq.append(t); cur = (t["ev"][-1][4], t["ev"][-1][5])
        for t in seq:
            for e in t["ev"]:
                out.append(dict(slot=t["slot"], d=t.get("_d") if t["slot"] == S else None, sig=t["sig"], payer=t["signers"][0], signers=t["signers"],
                                buy=e[0], user=e[1], sol=e[2], tok=e[3], vsol=e[4], vtok=e[5], fbps=e[7], fee=e[8], cbps=e[9], cfee=e[10],
                                cup=t["cup"], cul=t["cul"], txfee=t["fee"], tips=t["tips"], xf=t["xf"], nev=len(t["ev"]), dpay=t["dpay"]))
            if t["ev"]: cur = (t["ev"][-1][4], t["ev"][-1][5])
    return out, fb

def bundle_set(r):
    bw = set([r.get("creator"), r.get("user"), r.get("payer")] + list(r.get("signers") or []))
    for x in r.get("later") or []:
        if x.get("glued"):
            bw.add(x["payer"]); bw |= {e[1] for e in x.get("ev") or []}
    bw.discard(None)
    return bw

def post_bundle_state(r):
    gv = r.get("gv") or r.get("base") or V0
    return gv, K / gv

def load(path, need_txs=True):
    for l in open(path):
        try: r = json.loads(l)
        except Exception: continue
        if need_txs and "txs" not in r: continue
        yield r

def leader_client(r, slot):
    ld = r.get("leaders")
    if not ld: return "?"
    i = slot - r["slot"]
    if 0 <= i < len(ld): return NODES.get(ld[i], "?")
    return "?"

def landing_cost(e_like):
    """total landing cost lamports of a tx: meta fee + tips (known tip accounts)"""
    return (e_like["txfee"] or 0) + sum(x[1] for x in e_like["tips"] or [])
