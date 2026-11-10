"""BIGLOSS shared helpers: load positions r37-r55, DEV/VAL/HOLDOUT split, hold sellers (outcome labels only), signing-time
holder rebuild (features), per-run tables."""
import json, collections, glob, os
D = "/home/it/sniper-data/bigloss"
SPLIT = 1793516400000000000  # 2026-11-01 12:00 PKT (record clock t, ns)
OURS8 = {"EgxfYgEb", "2g7rYv7y"}
SUP = 1e15
BIG = -0.04
PKT = 5 * 3600


def split_of(r, t):
    if r <= 41: return "DEV"
    if r == 42: return "DEV" if t < SPLIT else "VAL"
    return "HOLD"


def rkey(r, t):
    if r != 42: return f"r{r}"
    return "r42a" if t < SPLIT else "r42b"


def load(runs=range(37, 56)):
    out = []
    for r in runs:
        fn = f"{D}/pos/pos_r{r}.jsonl"
        if not os.path.exists(fn): continue
        for l in open(fn):
            d = json.loads(l)
            d["set"] = split_of(r, d["t"]); d["rk"] = rkey(r, d["t"])
            a = d.get("arm") or {}
            d["kind"] = a.get("kind") or "t2"
            d["t_arm"] = (a.get("trig") or {}).get("t") if d["kind"] == "t2" else (a.get("dump") or {}).get("t")
            out.append(d)
    out.sort(key=lambda d: d["t"])
    return out


def hour_pkt(t): return int(((t / 1e9) + PKT) // 3600 % 24)


def hold_trades(d):
    """other wallets' trades strictly between our buy and our (first) sell landing. Prefer obs hold_tape (8-char w), else tape."""
    f = d["fill"]; c = d.get("close") or {}
    sl = c.get("sell_land") or None
    me = (f["slot"], f.get("idx", 0))
    end = (sl[0], sl[1]) if sl and sl[0] else (f["slot"] + 1, 10 ** 6)
    src = (d.get("ht") or {}).get("trades")
    out = []
    if src:
        for x in src:
            w = (x.get("w") or "")[:8]
            k = (x["slot"], x.get("idx", 0))
            if w in OURS8 or k <= me or k >= end: continue
            out.append({"w": w, "buy": x["buy"], "sol": x["sol"] / 1e9, "slot": x["slot"], "idx": x.get("idx", 0), "tok": x.get("tok")})
    else:
        for x in d.get("tape") or []:
            w = (x.get("user") or "")[:8]
            k = (x["slot"], x.get("idx", 0))
            if w in OURS8 or k <= me or k >= end: continue
            out.append({"w": w, "buy": x["buy"], "sol": x["sol"] / 1e9, "slot": x["slot"], "idx": x.get("idx", 0), "tok": x.get("tok")})
    return out


def hold_sellers(d):
    s = collections.defaultdict(float); b = collections.defaultdict(float)
    for x in hold_trades(d):
        (b if x["buy"] else s)[x["w"]] += x["sol"]
    return s, b


def restore(at, L):
    """tokens (% supply) each wallet sold AFTER the filled attempt's signing (crossing dump + trades between), on the curve."""
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
            K2 = V * K / (V - s); add[(x.get("user") or "")[:8]] += (K2 - K) / SUP * 100.0; V, K = V - s, K2
    return add


def whale_of(d):
    a = d.get("arm") or {}
    if d["kind"] == "t2": return ((a.get("trig") or {}).get("wallet") or "")[:8]
    return ((a.get("dump") or {}).get("seller") or "")[:8]


def sign_holders(d):
    """holders >= ~2% at the filled attempt's signing: landing list + what sellers sold after signing put back (APPROX: buys
    after signing are not removed). Returns list of dict(w8, pct, age, n, gone)."""
    f = d["fill"]; fa = f.get("ann") or {}
    if fa.get("holders") is None: return None
    add = restore(d.get("att") or {}, d.get("land") or {})
    hs = []
    for h in fa["holders"]:
        w8 = h["w"][:8]
        hs.append({"w": w8, "pct": h["pct"] + add.pop(w8, 0.0), "age": h.get("age"), "n": h.get("n") or 0,
                   "hz3": h.get("hz3") or 0.0, "p50": h.get("p50") or 0, "risk": h.get("risk") or 0, "gone": False})
    for w8, pct in add.items():
        if pct >= 2.0 and w8 not in OURS8:
            hs.append({"w": w8, "pct": pct, "age": None, "n": None, "hz3": 0.0, "p50": 0, "risk": 0, "gone": True})
    return hs


def tok_age_fill(d):
    a = d.get("arm") or {}
    src = a.get("trig") if d["kind"] == "t2" else a.get("dump")
    ag = (src or {}).get("age_slots"); sl = (src or {}).get("slot")
    if ag is None or sl is None: return None
    return ag + (d["fill"]["slot"] - sl)


def summ(rows, key=lambda d: d["pnl"]):
    n = len(rows); w = sum(1 for d in rows if d["pnl"] > 0)
    return n, w, n - w, sum(key(d) for d in rows)
