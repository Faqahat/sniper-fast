"""TAIL features of one live position at SIGNING (the filled attempt's signing; approximations marked).
EXACT at signing: arm record (trigger / re-arm dump, ann nb50/creator, quiet, v2), the filled attempt (pos, p, vsol, vtok), fill ann ob6
(= the window's largest other holder at that attempt's signing, the engine's own value).
APPROX (landing -> signing): fill ann holders (>= 2%, at our landing just before our buy) with the crossing dump `d` and the `between`
sellers added back (sold SOL / price before our buy) - these trades happen after signing; buys after signing are not removed (unknown)."""
import collections
SUP = 1e15
def tok_pct(sol, p): return (sol / p) / SUP * 100.0 if p and p > 0 else 0.0
def restore(at, L):
    """tokens (% of supply) each wallet sold AFTER signing (the crossing dump d + the trades between it and our buy), on the
    constant-product curve from the filled attempt's signing state (vsol, vtok); buys move the curve too"""
    add = collections.defaultdict(float)
    V, K = float(at.get("vsol") or 0), float(at.get("vtok") or 0)
    xs = [x for x in [L.get("d")] + list(L.get("between") or []) if x]
    xs.sort(key=lambda x: (x.get("slot", 0), x.get("idx", 0)))
    for x in xs:
        s = float(x.get("sol") or 0)
        if V <= 0 or K <= 0: break
        if x.get("buy"):
            K2 = V * K / (V + s); V, K = V + s, K2
        elif s < V:
            K2 = V * K / (V - s); add[x["user"][:8]] += (K2 - K) / SUP * 100.0; V, K = V - s, K2
    return add

def feats(d):
    a = d.get("arm") or {}; f = d["fill"]; fa = f.get("ann") or {}; at = d.get("att") or {}; L = d.get("land") or {}
    kind = a.get("kind") or "t2"
    tr = a.get("trig") or {}; du = a.get("dump") or {}
    whale = tr.get("wallet") if kind == "t2" else du.get("seller")
    F = {"kind": kind, "has_ann": fa.get("holders") is not None}
    F["w_pct"] = tr.get("pct") if kind == "t2" else du.get("pct")
    F["age"] = tr.get("age_slots") if kind == "t2" else du.get("age_slots")
    F["nb50"] = (a.get("ann") or {}).get("nb50")
    F["cr_pct"] = (a.get("ann") or {}).get("cr_pct", 0.0)
    F["creator"] = (a.get("ann") or {}).get("creator")
    F["whale"] = whale
    q = a.get("quiet") or {}
    F["coh_hold"] = q.get("coh_hold"); F["wh_dumps"] = q.get("wh_dumps"); F["wh_fol"] = q.get("wh_fol"); F["since_last"] = q.get("since_last")
    v2 = a.get("v2") or {}
    F["n60"] = v2.get("n_tr_60s"); F["dd120"] = v2.get("maxdd_120s")
    vsol, vtok = at.get("vsol"), at.get("vtok")
    F["vsol"] = (vsol or 0) / 1e9
    F["sold_pct"] = (1073e12 - vtok) / SUP * 100 if vtok else None
    pos = at.get("pos") or [None]
    trig_slot = tr.get("slot") if kind == "t2" else du.get("slot")
    F["sign_after_trig"] = (pos[0] - trig_slot) if (pos[0] and trig_slot) else None
    F["ob6"] = fa.get("ob6")
    F["depth"] = fa.get("depth")  # LANDING only
    F["grp_pct"] = fa.get("grp_pct")  # LANDING only
    if not F["has_ann"]: return F
    add = restore(at, L)
    hs = []
    for h in fa["holders"]:
        pct = h["pct"] + add.pop(h["w"][:8], 0.0)
        hs.append({"w": h["w"], "pct": pct, "age": h["age"], "n": h["n"] or 0, "risk": h.get("risk") or 0, "hz3": h.get("hz3") or 0.0})
    # sellers that are gone by landing (sold out between signing and our buy): add with unknown age / n
    # a seller gone by landing: only as much as the curve's sold supply leaves room for (a wallet that never bought on the
    # curve - tokens moved to it - was never in the engine's holder view)
    vt = (at.get("vtok") or 0)
    room = ((1073e12 - vt) / SUP * 100.0 if vt else 100.0) - sum(h["pct"] for h in hs)
    for w8, pct in sorted(add.items(), key=lambda kv: -kv[1]):
        pct = min(pct, max(0.0, room)); room -= pct
        if pct >= 2.0: hs.append({"w": w8, "pct": pct, "age": None, "n": None, "risk": 0, "hz3": 0.0, "gone": True})
    F["holders"] = hs
    oth = [h for h in hs if not (whale and h["w"][:8] == whale[:8])]
    wh = [h for h in hs if whale and h["w"][:8] == whale[:8]]
    F["whale_sign"] = wh[0]["pct"] if wh else 0.0
    F["whale_rem"] = (F["whale_sign"] / F["w_pct"]) if F.get("w_pct") else None
    F["whale_n"] = wh[0]["n"] if wh else None
    F["whale_fresh"] = bool(wh and wh[0]["n"] is not None and wh[0]["n"] <= 1)
    F["n_hold"] = len(oth)
    F["sum_oth"] = sum(h["pct"] for h in oth)
    fr = [h for h in oth if h["n"] is not None and h["n"] <= 1]
    F["n_fresh"] = len(fr); F["sum_fresh"] = sum(h["pct"] for h in fr)
    F["max_fresh"] = max([h["pct"] for h in fr], default=0.0)
    g = collections.defaultdict(float); gn = collections.Counter()
    for h in fr: g[h["age"]] += h["pct"]; gn[h["age"]] += 1
    F["bundle"] = max(g.values(), default=0.0)
    F["bundle_n"] = max(gn.values(), default=0)
    # same-age groups of ANY holders (incl. old wallets) excluding whale
    g2 = collections.defaultdict(float)
    for h in oth:
        if h["age"] is not None: g2[h["age"]] += h["pct"]
    F["samage"] = max(g2.values(), default=0.0)
    big = max(oth, key=lambda h: h["pct"], default=None)
    F["max_oth"] = big["pct"] if big else 0.0
    F["max_oth_n"] = big["n"] if big else None
    F["max_oth_age"] = big["age"] if big else None
    F["n_oth6"] = sum(1 for h in oth if h["pct"] >= 6)
    F["risky_sum"] = sum(h["pct"] for h in oth if h["risk"] >= 5 and h["hz3"] >= 0.3)
    bots = [h for h in oth if h["n"] is not None and h["n"] >= 10]
    F["sum_bot"] = sum(h["pct"] for h in bots); F["max_bot"] = max([h["pct"] for h in bots], default=0.0); F["n_bot"] = len(bots)
    F["sum_oth4"] = sum(h["pct"] for h in oth if h["pct"] >= 4)
    wa = wh[0]["age"] if wh else None
    F["co_whale"] = sum(h["pct"] for h in oth if wa is not None and h["age"] is not None and abs(h["age"] - wa) <= 1)
    F["listed_sum"] = sum(h["pct"] for h in hs)
    F["resid"] = (F["sold_pct"] - F["listed_sum"]) if F["sold_pct"] is not None else None
    return F

def outcome(d, OURS):
    """what happened INSIDE our hold (after-the-fact; used to label causes, never as a feature)"""
    f = d["fill"]; c = d.get("close") or {}
    sl = c.get("sell_land") or [None, None]
    me = (f["slot"], f["idx"])
    end = (sl[0], sl[1]) if sl[0] else (f["slot"] + 3, 10**6)
    sells = collections.defaultdict(float); buys = collections.defaultdict(float)
    for x in d.get("tape") or []:
        if x["user"] in OURS: continue
        k = (x["slot"], x["idx"])
        if k <= me or k >= end: continue
        (buys if x["buy"] else sells)[x["user"]] += x["sol"] / 1e9
    return sells, buys
