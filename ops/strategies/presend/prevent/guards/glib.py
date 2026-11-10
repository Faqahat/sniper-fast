"""GUARDS library: per-mint chain tapes (every decoded pump.fun trade of a mint, chain order) from the local decoded sources, and
per-wallet balance timelines (sum of the wallet's curve trades; transfers between wallets are NOT seen - a known limit).
Sources (MEASURED decodes of the 24/7 recorder):
  presend_quiet3/chain.npz      slots 460883322 .. 462708348  (10-24 19:25 -> 10-29 07:13 PKT)
  presend_young/ext/chain.npz   (small extension, 10-29 07:16 -> 09:11 PKT)
  presend_quiet4/tab37          slots 462707677 .. 463013393  (10-29 07:08 -> 10-30 01:20 PKT)
  prevent/guards/tab_tail       slots 463010350 .. 463023360  (10-30 01:10 -> 01:56 PKT; decoded here from the raw chunks)
  multiarm/tab38                slots 463021093 .. 463049835  (run 38)
  prevent/guards/tab_t38        slots 463048435 .. 463056317  (run 38 end, decoded here)"""
import json, bisect, collections
import numpy as np
SUP = 1e15
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
D = "/home/it/sniper-data"
CHAINS = [(f"{D}/presend_quiet3/chain.npz", f"{D}/presend_quiet3/ids.json"), (f"{D}/presend_young/ext/chain.npz", f"{D}/presend_young/ext/ids.json")]
TABS = [f"{D}/presend_quiet4/tab37", f"{D}/prevent/guards/tab_tail", f"{D}/multiarm/tab38", f"{D}/prevent/guards/tab_t38"]


def load_tapes(mints):
    """mint -> sorted list of (s, i, j, buy, sol, tok, vsol, vtok, user)"""
    want = set(mints); rows = collections.defaultdict(set)
    for npz, idsf in CHAINS:
        I = json.load(open(idsf)); ml = I["mint"]; ul = I["user"]
        mid = {m: k for k, m in enumerate(ml) if m in want}
        if not mid: continue
        z = np.load(npz); mint = z["mint"]
        sel = np.nonzero(np.isin(mint, np.array(list(mid.values()), dtype=mint.dtype)))[0]
        del mint
        cols = {}
        for k in ("s", "i", "j", "buy", "sol", "tok", "vsol", "vtok", "mint", "user"):
            a = z[k]; cols[k] = a[sel].copy(); del a
        inv = {v: k for k, v in mid.items()}
        for n in range(len(sel)):
            rows[inv[int(cols["mint"][n])]].add((int(cols["s"][n]), int(cols["i"][n]), int(cols["j"][n]), int(cols["buy"][n]), int(cols["sol"][n]), int(cols["tok"][n]),
                                                 int(cols["vsol"][n]), int(cols["vtok"][n]), ul[int(cols["user"][n])]))
    for tab in TABS:
        T = np.load(f"{tab}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{tab}/ids.json")); gid = {k: i for i, k in enumerate(ids)}
        g = np.array([gid[m] for m in want if m in gid], dtype=np.uint32)
        if len(g) == 0: continue
        mm = np.asarray(T["mint"]); sel = np.nonzero(np.isin(mm, g))[0]
        t = T[sel]
        for x in t:
            rows[ids[int(x["mint"])]].add((int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]))
    return {m: sorted(v) for m, v in rows.items()}


class Hold:
    """balances of every wallet on one mint along the chain order. key(s, i, j) = s * 2^24 + i * 64 + j"""
    def __init__(self, rows):
        self.rows = rows
        self.keys = [r[0] * 16777216 + r[1] * 64 + r[2] for r in rows]
        bal = collections.defaultdict(int); tl = collections.defaultdict(lambda: ([], []))
        self.big3_at = []   # for each trade index: nothing (computed on demand)
        for n, r in enumerate(rows):
            u = r[8]
            if u in OURS: continue
            bal[u] += r[5] if r[3] else -r[5]
            ks, bs = tl[u]; ks.append(self.keys[n]); bs.append(bal[u])
        self.tl = dict(tl)
        self.first_slot = rows[0][0] if rows else None

    @staticmethod
    def key(s, i, j=0): return s * 16777216 + i * 64 + j

    def bal_before(self, u, K):
        """wallet u's balance from its trades strictly before chain key K"""
        x = self.tl.get(u)
        if x is None: return 0
        k = bisect.bisect_left(x[0], K)
        return x[1][k - 1] if k > 0 else 0

    def holders_before(self, K, min_frac):
        """wallets (not ours) holding >= min_frac of supply from trades strictly before K: {wallet: balance}"""
        out = {}
        thr = min_frac * SUP
        for u, (ks, bs) in self.tl.items():
            k = bisect.bisect_left(ks, K)
            if k > 0 and bs[k - 1] >= thr: out[u] = bs[k - 1]
        return out
