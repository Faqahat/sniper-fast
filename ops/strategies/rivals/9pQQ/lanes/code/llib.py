"""LANES shared loader + curve maths. Tape columns: s i bt u m tok sol cpre cpost cup tip fl ps nt ; failed fs fi fu fm fside fcode."""
import json, numpy as np
D = "/home/it/sniper-data/rivals/9pQQ/lanes"; COLLECT = "/data/tapes/collect"
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"; OURS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
RUNS = ["run_20261028_1405", "run_20261029_1400", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]
DAY = dict(zip(RUNS, ["10-28", "10-29", "10-30", "10-31", "11-02"]))
V = 73_000_000_000_000; TOTAL = 10**15; K = 30_000_000_000 * 1_073_000_000_000_000
def vsol(c): return K / (c + V)
def ebuy(c, x):
    vt = np.asarray(c, dtype=float) + V; vs = K / vt; return vt * x / (vs + x)
def esell(c, t):
    vt = np.asarray(c, dtype=float) + V; vs = K / vt; return vs * t / (vt + t)
class T: pass
def load(run, curve_only=True, failed=False):
    z = np.load(f"{D}/tape_{run}.npz")
    t = T(); t.users = z["users"]; t.mints = z["mints"]; t.psets = z["psets"]
    fl = z["fl"]; keep = (fl & 1) == 1 if curve_only else slice(None)
    for k in ["s", "i", "bt", "u", "m", "tok", "sol", "cpre", "cpost", "cup", "tip", "ps", "nt"]:
        setattr(t, k, z[k][keep])
    t.cpre = np.where(t.cpre < 100e12, TOTAL, t.cpre); t.cpost = np.where(t.cpost < 100e12, TOTAL, t.cpost)
    t.ms = np.searchsorted(t.m, np.arange(len(t.mints) + 1))
    if failed:
        for k in ["fs", "fi", "fu", "fm", "fside", "fcode"]: setattr(t, k, z[k])
        t.fms = np.searchsorted(t.fm, np.arange(len(t.mints) + 1))
    t.mix = {m: k for k, m in enumerate(t.mints)}; t.wid = int(np.searchsorted(t.users, W))
    return t
def launches(run):
    L = {}
    for l in open(f"{COLLECT}/{run}/launches.jsonl"):
        d = json.loads(l); ix = d.get("ixn") or []
        may = ("MayhemState" in ix) if isinstance(ix, str) else any("Mayhem" in x for x in ix)
        L[d["mint"]] = dict(slot=d["slot"], bt=d["bt"], creator=d.get("creator"), may=may)
    return L
