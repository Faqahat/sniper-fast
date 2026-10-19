# READ-ONLY: for each token we bought in the live test, our entry/exit price vs how far it ran after our sell.
import sys, re, json, concurrent.futures as cf
sys.path.insert(0, "/root/indep")
from common import rpc, events
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
L = open(sys.argv[1], errors="replace").read()
fires = re.findall(r"FIRE slot=(\d+) mint=(\w+)", L)
buys = re.findall(r"BUY\s+sig=(\w+)", L)
sells = re.findall(r"SELL sig=(\w+)", L)


def tx(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not isinstance(t, dict) or "meta" not in t:
        return None
    tr, _ = events(t["meta"].get("logMessages"))
    return t.get("blockTime"), t["slot"], tr


def px(e):
    return e["vsol"] / e["vtok"] if e["vtok"] else 0


# map our buy/sell to mints
ours = {}
for s in buys + sells:
    r = tx(s)
    if not r:
        continue
    bt, slot, tr = r
    for e in tr:
        if e["user"] == ME:
            d = ours.setdefault(e["mint"], {})
            if e["buy"]:
                d["entry"], d["bt"] = (e["sol"] / e["tok"]) if e["tok"] else 0, bt
            else:
                d["exit"], d["sbt"] = (e["sol"] / e["tok"]) if e["tok"] else 0, bt


def path(mint, t0):
    """all trades on the mint from create to create+600 s (page signatures newest->oldest)"""
    sigs, before = [], None
    for _ in range(30):
        p = {"limit": 1000}
        if before:
            p["before"] = before
        r = rpc("getSignaturesForAddress", [mint, p])
        if not isinstance(r, list) or not r:
            break
        sigs += r
        before = r[-1]["signature"]
        if len(r) < 1000:
            break
    win = [s for s in sigs if s.get("err") is None and s.get("blockTime") and s["blockTime"] <= t0 + 600]
    pts = []
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(lambda s: tx(s["signature"]), win[-1500:]):
            if r:
                bt, slot, tr = r
                for e in tr:
                    if e["mint"] == mint:
                        pts.append((bt, px(e)))
    latest = None
    if sigs:
        r = tx(sigs[0]["signature"])
        if r:
            ee = [e for e in r[2] if e["mint"] == mint]
            latest = px(ee[-1]) if ee else None
    return pts, latest, len(sigs)


print(f"{'mint':10} {'our exit':>9} {'peak30s':>8} {'peak1m':>8} {'peak5m':>8} {'peak10m':>8} {'now':>8} {'#txs':>6}   (all as x of OUR ENTRY price)")
for slot, mint in fires:
    d = ours.get(mint)
    if not d or not d.get("entry"):
        print(f"{mint[:10]} our trade not found")
        continue
    t0 = d["bt"]
    pts, latest, n = path(mint, t0)
    e = d["entry"] * 1e-9 * 1e6  # sol/tok in same units as vsol/vtok (lamports/raw)
    e = d["entry"]
    def pk(sec):
        v = [p for bt, p in pts if t0 <= bt <= t0 + sec]
        return max(v) / e if v else 0
    # px() is vsol/vtok (lamports per raw token); entry is sol/tok from the same event units
    ex = (d.get("exit") or 0) / e
    print(f"{mint[:10]} {ex:9.2f} {pk(30):8.2f} {pk(60):8.2f} {pk(300):8.2f} {pk(600):8.2f} {((latest or 0) / e):8.2f} {n:6}")
