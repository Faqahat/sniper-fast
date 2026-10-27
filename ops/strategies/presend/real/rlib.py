#!/usr/bin/env python3
"""REAL replay core (read-only): the recorded chain tape, per token, and the live engine's T2 detector
(src/presend_live.rs Detector: same rules, chain order).
Clocks (ms):
  arr(s, i)   = the engine's block-position clock (dip_model::arrival: idx / max(400, idx + 1)); used ONLY where the engine
                uses it (a window's last slot, en_slot).
  cc(s, i)    = the chain clock of this replay: slot x 212 + idx / n_s x 212, n_s = the block's size seen in the recording
                (max tx index + 1). Blocks fill about linearly in time (MEASURED: consecutive tries land in index order,
                ~1 index per ms), so this is a better within-slot time than the 400 rule."""
import os, json, time, calendar
import numpy as np

TAB = "/home/moiz/sniper-data/presend_real/tab"
SMS = 212.0
SUPPLY = 1e15
HX = 30_000_000_000_000
UNTRADE_V = 100_000_000_000
WALLETS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")
pk = lambda s: calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
def pkt(t, f="%m-%d %H:%M"): return time.strftime(f, time.gmtime(int(t) + 18000))

def arr(s, i): return s * SMS + i / max(400.0, i + 1.0) * SMS

class Clock:
    """the chain clock alone (block sizes per slot): small, shared by the simulator's workers"""
    def __init__(self, slot0, bsize): self.slot0 = slot0; self.bsize = bsize
    def nblk(self, s):
        k = s - self.slot0
        if 0 <= k < len(self.bsize) and self.bsize[k] > 0: return int(self.bsize[k])
        return 0
    def cc(self, s, i):
        n = self.nblk(s)
        if n <= 0: n = 400
        return s * SMS + i / max(float(n), i + 1.0) * SMS
    def cc_inv(self, a):
        s = int(a // SMS); f = a / SMS - s
        n = self.nblk(s)
        if n <= 0: n = 400
        return s, f * n

class Tape:
    """the merged trade table, indexed per mint (chain order inside a mint)"""
    def __init__(self, tab=TAB, with_ours=True):
        T = np.load(f"{tab}/trades.npy")
        self.ids = json.load(open(f"{tab}/ids.json"))
        self.idx_of = None
        self.creates = json.load(open(f"{tab}/creates.json"))
        S = np.load(f"{tab}/slots.npy")
        self.slot0 = int(S["slot"][0]); n = int(S["slot"][-1]) - self.slot0 + 1
        self.bsize = np.zeros(n, np.int32)                      # block size per slot (0 = not recorded)
        self.bsize[S["slot"].astype(np.int64) - self.slot0] = S["maxi"].astype(np.int32) + 1
        self.bt = np.zeros(n, np.int64); self.bt[S["slot"].astype(np.int64) - self.slot0] = S["bt"]
        self.rec = self.bsize > 0
        o = np.argsort(T["mint"], kind="stable")
        self.T = T[o]
        m = self.T["mint"]
        b = np.flatnonzero(np.diff(m.astype(np.int64))) + 1
        starts = np.concatenate([[0], b]); ends = np.concatenate([b, [len(m)]])
        self.span = {int(m[a]): (int(a), int(e)) for a, e in zip(starts, ends)}
        # the probes' own pre-send fills and sells are removed from the tape (the replay puts its own buy in); every other trade,
        # including our other bots' trades, is the market as recorded
        self.our_ids = set()
        self.skip_sigh = set()
        if with_ours:
            import hashlib
            sh = lambda s: int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")
            for fn in ("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r17.jsonl"):
                for l in open(fn):
                    if '"presend_live_fill"' in l or '"presend_live_sell_land"' in l:
                        r = json.loads(l); self.skip_sigh.add(sh(r["sig"]))
        # columns as plain arrays (fast scalar access)
        self.s = self.T["slot"].astype(np.int64); self.i = self.T["idx"].astype(np.int64); self.j = self.T["j"].astype(np.int64)
        self.user = self.T["user"].astype(np.int64); self.buy = self.T["buy"].astype(bool)
        self.sol = self.T["sol"].astype(np.int64); self.tok = self.T["tok"].astype(np.int64)
        self.vsol = self.T["vsol"].astype(np.int64); self.vtok = self.T["vtok"].astype(np.int64)
        fb = self.T["fee_bps"].astype(np.int64); cb = self.T["cfee_bps"].astype(np.int64)
        self.fr = (np.where(fb != 0, fb, 95) + np.where(cb != 0, cb, 30)) / 1e4
        self.sigh = self.T["sigh"]
        self.blockt = self.T["bt"].astype(np.int64)

    def clock(self): return Clock(self.slot0, self.bsize)

    def slim(self):
        """drop the structured table (the column arrays stay): less memory before workers fork"""
        self.T = None

    def id_map(self):
        if self.idx_of is None: self.idx_of = {k: v for v, k in enumerate(self.ids)}
        return self.idx_of

    def nblk(self, s):
        k = s - self.slot0
        if 0 <= k < len(self.bsize) and self.bsize[k] > 0: return int(self.bsize[k])
        return 0

    def cc(self, s, i):
        n = self.nblk(s)
        if n <= 0: n = 400
        return s * SMS + i / max(float(n), i + 1.0) * SMS

    def cc_inv(self, a):
        """chain clock -> (slot, fractional index) in the recorded block of that slot"""
        s = int(a // SMS); f = a / SMS - s
        n = self.nblk(s)
        if n <= 0: n = 400
        return s, f * n

def float32(x): return float(np.float32(x))

def detect(tp, whale_pct=5.0, mints=None, keep_below=False):
    """the live T2 detector on every followed token (seen from its create; mayhem not followed; the non-standard-curve filter)
    -> list of trigger dicts (chain order per token). Also the whale's later sells (for the window end and V3/V4)."""
    out = []
    ids = tp.ids; idm = tp.id_map()
    todo = mints if mints is not None else tp.creates.keys()
    for mint in todo:
        c = tp.creates.get(mint)
        if c is None: continue
        if c.get("mayhem") or c.get("mayhem_ix"): continue
        mid = idm.get(mint)
        if mid is None or mid not in tp.span: continue
        a, e = tp.span[mid]
        s0 = c["slot"]; creator = idm.get(c.get("creator")); signer = idm.get(c.get("user"))
        bal = {}; became = set(); ins = set(); trig = {}
        n = 0
        for k in range(a, e):
            s = tp.s[k]
            if (s, tp.i[k]) < (s0, c["idx"]): continue          # before the create (should not happen)
            v = tp.vsol[k]; t = tp.vtok[k]
            if n < 50 and (v < 25_000_000_000 or v > 200_000_000_000 or t == 0): break
            n += 1
            u = tp.user[k]; b = tp.buy[k]
            bal[u] = bal.get(u, 0) + (tp.tok[k] if b else -tp.tok[k])
            if b and s == s0 and u != creator and u != signer: ins.add(u)
            if (not b) and u in trig:
                trig[u]["sells"].append(k)
            if b and v < UNTRADE_V and u not in became:
                ht = 1 if u == creator else 2 if u in ins else 3 if bal[u] >= HX else 0
                if ht: became.add(u)
                if ht == 3:
                    pct = float32(bal[u] / SUPPLY * 100.0)
                    if pct >= whale_pct:
                        d = dict(mint=mint, mid=mid, k=k, slot=int(s), idx=int(tp.i[k]), j=int(tp.j[k]), whale=int(u), pct=pct, bal=int(bal[u]),
                                 vsol=int(v), vtok=int(t), sol=int(tp.sol[k]), age_slots=int(s - s0), create_slot=int(s0),
                                 v2=bool(c.get("v2")), cashback=bool(c.get("cashback")), holder=bool(c.get("holder")),
                                 cfee=int(c.get("cfee_bps") or 0), sells=[], bt=int(tp.blockt[k]))
                        trig[u] = d; out.append(d)
                    elif keep_below:
                        out.append(dict(mint=mint, below=True, slot=int(s), idx=int(tp.i[k]), pct=pct))
    return out

def followed_mints(tp):
    """mints the live engine follows: seen from their create, not mayhem, and none of the first 50 trades at a curve < 25 or > 200
    SOL or with no virtual tokens (the detector's non-standard-curve rule; it also drops non-SOL-quoted curves)"""
    idm = tp.id_map(); out = set()
    for mint, c in tp.creates.items():
        if c.get("mayhem") or c.get("mayhem_ix"): continue
        mid = idm.get(mint)
        if mid is None or mid not in tp.span: continue
        a, e = tp.span[mid]; b = min(e, a + 50)
        v = tp.vsol[a:b]; t = tp.vtok[a:b]
        if ((v < 25_000_000_000) | (v > 200_000_000_000) | (t == 0)).any(): continue
        out.add(mid)
    return out
