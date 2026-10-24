#!/usr/bin/env python3
# READ-ONLY, offline. Loads every token with a usable market path (collector windows R1/R2 + paths fetched from CK), checks that
# replaying the wallet's ACTUAL sells reproduces its real PnL, then exposes helpers to replay candidate exit rules.
import sys, os, json, collections, statistics, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from sim import simulate

def raw_tx(w, sig):
    for c in (f"{LEDGER}/txc_{w}", f"{EXITS}/cache/txc_{w}"):
        p = os.path.join(c, sig + ".json")
        if os.path.exists(p): return json.load(open(p))
    return None

def patch_own(rows, rt, w, m):
    """getSignaturesForAddress(before=last sell) leaves out the last sell itself: insert any missing own leg from the local raw
    tx cache, at the chain position where its pre-trade curve state continues the previous row (constant-product check)."""
    W = WALLETS[w]; rows = list(rows)
    have = {t["sig"] for t in rows if t["user"] == W}
    for l in rt["legs"]:
        if l["side"] not in ("buy", "sell") or l["sig"] in have: continue
        t = raw_tx(w, l["sig"])
        if not t: return None
        ev = [e for e in decode_events(t) if e["mint"] == m and e["user"] == W]
        if not ev: return None
        for j, e in enumerate(ev):
            pre = pre_state(e["buy"], e["sol"], e["tok"], e["vsol"], e["vtok"])
            row = dict(s=t["slot"], i=10**6, j=j, bt=t.get("blockTime"), sig=l["sig"], payer=W, user=W, buy=e["buy"], sol=e["sol"], tok=e["tok"], vsol=e["vsol"], vtok=e["vtok"], creator=e["creator"])
            k_ins = None
            for k, x in enumerate(rows):
                if x["s"] == t["slot"] and abs(x["vsol"] - pre[0]) < 1e6: k_ins = k + 1
            if k_ins is None: k_ins = sum(1 for x in rows if x["s"] <= t["slot"])
            rows.insert(k_ins, row)
    return rows

def load_cases(include_fetched=True):
    CI = json.load(open(os.path.join(EXITS, "cache", "create_info.json")))
    RT = {w: {r["mint"]: r for r in json.load(open(f"{EXITS}/roundtrips_{w}.json"))["tokens"]} for w in WALLETS}
    cases = []
    for a in json.load(open(f"{EXITS}/align.json")):
        if a["coverage"]["missing"]: continue
        tr, _ = trades_of(a["mint"])
        cases.append(dict(w=a["w"], mint=a["mint"], rt=RT[a["w"]][a["mint"]], tr=tr, dev={a["signer"], a["creator"]} - {None}, src="collector",
                          cfg=f"{a['w']}:{(a['signer'] or a['creator'])[:6]}"))
    if include_fetched:
        pd = os.path.join(EXITS, "cache", "paths")
        for f in sorted(os.listdir(pd)):
            d = json.load(open(os.path.join(pd, f))); m = d["mint"]; w = d["w"]; rt = RT[w].get(m)
            if not rt or not d["rows"] or d.get("capped"): continue        # capped = market trades missing after 400 txs: skip
            rows = patch_own(d["rows"], rt, w, m)
            if rows is None: continue
            d["rows"] = rows
            dev = {d["rows"][0].get("creator")} | ({CI[m]["user"], CI[m]["creator"]} if m in CI else set())
            signer = CI[m]["user"] if m in CI else (rt.get("creator") or d["rows"][0].get("creator"))
            cases.append(dict(w=w, mint=m, rt=rt, tr=d["rows"], dev=dev - {None}, src="fetched", capped=d["capped"], cfg=f"{w}:{signer[:6]}"))
    return cases

def run(cases, rule, **kw):
    out = []
    for c in cases:
        try: s = simulate(c["rt"], WALLETS[c["w"]], c["tr"], c["dev"], rule, **kw)
        except StopIteration: continue
        out.append((c, s))
    return out

def corr(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x)); sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else float("nan")

if __name__ == "__main__":
    cases = load_cases()
    print("cases:", len(cases), collections.Counter((c["w"], c["src"]) for c in cases))
    res = run(cases, {}, actual=True)
    act = [c["rt"]["pnl"] for c, s in res]; sim = [s["pnl"] for c, s in res]
    print(f"ACTUAL-schedule replay: actual PnL {sum(act):+.3f} vs replayed {sum(sim):+.3f}; corr {corr(act, sim):.4f}; "
          f"max abs diff {max(abs(a - b) for a, b in zip(act, sim)):.4f}; forced closes {sum(s['forced'] for c, s in res)}")
    bad = sorted(res, key=lambda cs: -abs(cs[0]["rt"]["pnl"] - cs[1]["pnl"]))[:5]
    for c, s in bad: print("   ", c["w"], c["mint"][:8], c["src"], round(c["rt"]["pnl"], 4), round(s["pnl"], 4), len(s["sells"]), c["rt"]["n_sells"])
