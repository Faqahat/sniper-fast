"""pos helpers (read-only)."""
import pickle, sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/pos"
DAYS = list(range(0, 7))


def load():
    Z = pickle.load(open(f"{OUT}/p1.pkl", "rb"))
    B, LO, T = Z["buys"], Z["lots"], Z["trips"]
    for t in T:
        t["day"] = L.day_of(t["bt0"])
        t["gross"] = t["out"] + t.get("mark", 0.0) - t["cost"]
        t["net"] = t["gross"] - t["txc"]
        t["hold_s"] = (t["close_cc"] - t["cc0"]) / 1000 if t["close_cc"] else None
        t["probe"] = t["cost"] <= 0.05
    for l in LO:
        b = B[l["b"]]
        mk = l.get("mark", 0.0)
        l["gross"] = l["out"] + mk - l["cost"]
        l["net"] = l["gross"] - l["txc"] - l["sell_txc"]
        # pro-rata: open-at-end tokens marked like FIFO (share of trip mark)
        l["pgross"] = l["pout"] + (mk if l.get("mark") else 0.0) - l["cost"]
        l["pnet"] = l["pgross"] - l["txc"] - l["sell_txc"]
        l["cgross"] = l["cout"] + l.get("cmark", 0.0) - l["cost"]
        l["cnet"] = l["cgross"] - l["txc"] - l["csell_txc"]
        l["chold_s"] = (l["cclose_cc"] - l["cc"]) / 1000 if l.get("cclose_cc") else None
        l["day"] = L.day_of(b["bt"])
        l["hold_s"] = (l["close_cc"] - l["cc"]) / 1000 if l.get("close_cc") else None
        l["probe"] = l["cost"] <= 0.05
    return B, LO, T


def boot_sum(v, n=2000, seed=1, q=(5, 95)):
    v = np.asarray(v, float)
    if not len(v): return (0.0, 0.0)
    r = np.random.default_rng(seed); s = r.choice(v, (n, len(v))).sum(1) if len(v) < 20000 else np.array([v[r.integers(0, len(v), len(v))].sum() for _ in range(n)])
    return tuple(float(np.percentile(s, x)) for x in q)


def boot_mean(v, n=2000, seed=1, q=(5, 95)):
    v = np.asarray(v, float)
    if not len(v): return (0.0, 0.0)
    r = np.random.default_rng(seed); s = np.array([v[r.integers(0, len(v), len(v))].mean() for _ in range(n)])
    return tuple(float(np.percentile(s, x)) for x in q)


class Out:
    def __init__(s, path): s.path = path; s.lines = []
    def __call__(s, *a):
        x = " ".join(str(v) for v in a); print(x, flush=True); s.lines.append(x)
    def save(s): open(s.path, "w").write("\n".join(s.lines) + "\n")


pkt = L.pkt
day_name = L.day_name
