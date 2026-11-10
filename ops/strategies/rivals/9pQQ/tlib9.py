"""9pQQ dissection: shared loaders. Read-only.
load_tape(run) -> Tape with numpy columns sorted by (mint, s, i) for curve trades only, plus per-mint offsets.
Price on the curve ~ 1/(cbal + 73e12)^2 (vSOL ~ 30 SOL * 1073e12 / (cbal+73e12) ... we use ratios only)."""
import glob, os, pickle, json
import numpy as np
TAPE = "/home/it/sniper-data/rivals/9pQQ/tape"
COLLECT = "/data/tapes/collect"
OUT = "/home/it/sniper-data/rivals/9pQQ"
RUNS = ["run_20261028_1405", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]
DAY = {"run_20261028_1405": "10-28", "run_20261030_1355": "10-30", "run_20261031_1350": "10-31", "run_20261102_1250": "11-02"}
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
OURS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
V = 73_000_000_000_000
TOTAL = 1_000_000_000_000_000           # 1e9 tokens * 1e6
def vsol(c):                             # virtual SOL reserve (lamports) from curve token balance (constant product k = 30 SOL * 1073e12)
    return 30e9 * 1073e12 / (c + V)
def price(c): return vsol(c) / (c + V)   # lamports per token unit

class Tape:
    pass

def load_tape(run, cache=True):
    pk = f"{OUT}/tape_{run}.npz"
    if cache and os.path.exists(pk):
        z = np.load(pk, allow_pickle=False)
        t = Tape()
        for k in z.files: setattr(t, k, z[k])
        t.cpre = np.where(t.cpre < 100e12, TOTAL, t.cpre)   # create+buy txs: the curve account did not exist before (pre 0)
        t.cpost = np.where(t.cpost < 100e12, TOTAL, t.cpost)
        t.mint_ix = {m: k for k, m in enumerate(t.mints)}
        t.user_ix = {u: k for k, u in enumerate(t.users)}
        return t
    A, US, MS = [], [], []
    for fn in sorted(glob.glob(f"{TAPE}/{run}/*.npz")):
        z = np.load(fn)
        a = z["a"]
        if len(a) == 0: continue
        a = a[(a[:, 11] & 1) == 1]                    # curve trades only
        A.append(a); US.append(z["users"]); MS.append(z["mints"])
    # global string tables
    allu = np.unique(np.concatenate(US)); allm = np.unique(np.concatenate(MS))
    out = []
    for a, u, m in zip(A, US, MS):
        a = a.copy()
        a[:, 3] = np.searchsorted(allu, u)[a[:, 3]]
        a[:, 4] = np.searchsorted(allm, m)[a[:, 4]]
        out.append(a)
    a = np.concatenate(out)
    o = np.lexsort((a[:, 1], a[:, 0], a[:, 4]))
    a = a[o]
    t = Tape()
    t.s, t.i, t.bt, t.u, t.m, t.tok, t.sol, t.cpre, t.cpost, t.cup, t.tip = [a[:, k].copy() for k in range(11)]
    t.users, t.mints = allu, allm
    starts = np.searchsorted(t.m, np.arange(len(allm) + 1))
    t.mstart = starts
    np.savez(pk, s=t.s, i=t.i, bt=t.bt, u=t.u, m=t.m, tok=t.tok, sol=t.sol, cpre=t.cpre, cpost=t.cpost, cup=t.cup, tip=t.tip,
             users=t.users, mints=t.mints, mstart=t.mstart)
    t.mint_ix = {mm: k for k, mm in enumerate(allm)}
    t.user_ix = {uu: k for k, uu in enumerate(allu)}
    return t

def launches(run):
    L = {}
    for l in open(f"{COLLECT}/{run}/launches.jsonl"):
        d = json.loads(l)
        ix = d.get("ixn") or []
        if isinstance(ix, str): may = "MayhemState" in ix
        else: may = any("Mayhem" in x for x in ix)
        L[d["mint"]] = dict(slot=d["slot"], bt=d["bt"], creator=d.get("creator"), may=may, name=d.get("name"), sym=d.get("symbol"))
    return L

def own(run): return pickle.load(open(f"{OUT}/own_{run}.pkl", "rb"))
