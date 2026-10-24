#!/usr/bin/env python3
# sssssDdM BUY ATTEMPTS (read-only): every buy tx it sent (landed OK or failed, from the raw scan sssss/attempts.jsonl) placed
# on the token's tape in the day arrays by (slot, index). For each attempt: the trigger = last non-fleet trade before it
# (causal features at that trade), delay (slots, tx index, modelled ms), the price right before the attempt vs right after
# the trigger (= the slippage it faced), trades that landed between the trigger and the attempt, and whether it held the
# token already. Failed buys (Custom 6002 = slippage) show what it TRIED to buy, i.e. its full decision set.
# -> sssss/att_<run>.json (list of dicts) ; prints the slippage-failure curve and trigger mix
import sys, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize.json")).items()}
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
WDK = zlib.crc32(SIBS[0].encode())

def run_day(run):
    E.load([run]); d = E.DAYS[run]; F = d["F"]; FI = d["FI"]
    mint2t = {m["m"]: t for t, m in enumerate(d["M"]["meta"])}
    nt = len(d["M"]["meta"]); cnt = np.bincount(d["tok"], minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    isfleet = np.isin(d["uid"], FLEET)
    A = [json.loads(l) for l in open(f"{OUT}/attempts.jsonl")]
    A = [a for a in A if a["run"] == run and a["k"] == "buy"]
    out = []; miss = 0
    for a in A:
        t = mint2t.get(a["mint"])
        if t is None: miss += 1; continue
        lo, hi = int(off[t]), int(off[t] + cnt[t])
        S = d["s"][lo:hi]; I = d["i"][lo:hi]
        key = S.astype(np.int64) * 100000 + I
        kk = int(a["s"]) * 100000 + int(a["i"])
        p = lo + int(np.searchsorted(key, kk, side="left"))          # first trade at/after the attempt
        own = p < hi and key[p - lo] == kk and d["uid"][p] == UID      # the landed buy itself
        if not a["err"] and not own: miss += 1; continue
        q = p - 1                                                      # state right before the attempt
        if q < lo: continue
        j = q
        while j >= lo and isfleet[j]: j -= 1
        if j < lo: continue
        # holding? (its own net position in this token before the attempt)
        mine = np.flatnonzero(d["uid"][lo:p] == UID) + lo
        posn = float(sum(d["tokn"][m] * (1 if d["buy"][m] else -1) for m in mine)) if len(mine) else 0.0
        wd = np.flatnonzero(d["uid"][lo:p] == WDK) + lo
        posw = float(sum(d["tokn"][m] * (1 if d["buy"][m] else -1) for m in wd)) if len(wd) else 0.0
        arr_att = int(a["s"]) * E.SMS + int(a["i"]) / max(SS.get(int(a["s"]), 400), int(a["i"]) + 1) * E.SMS
        pj = float(d["vsol"][j] / d["vtok"][j]); pq = float(d["vsol"][q] / d["vtok"][q])
        # biggest non-fleet buy / sell in the attempt's slot before it and in the previous 3 slots
        b0 = s0 = b3 = s3 = 0.0; nb0 = ns0 = 0; m = q
        while m >= lo and d["s"][m] >= int(a["s"]) - 3:
            if not isfleet[m]:
                v = float(d["sol"][m]) / 1e9
                if d["buy"][m]:
                    b3 = max(b3, v)
                    if d["s"][m] == int(a["s"]): b0 = max(b0, v); nb0 += 1
                else:
                    s3 = max(s3, v)
                    if d["s"][m] == int(a["s"]): s0 = max(s0, v); ns0 += 1
            m -= 1
        out.append(dict(ok=0 if a["err"] else 1, err=a["err"], s=int(a["s"]), i=int(a["i"]), tok=t, k_own=int(p) if own else None, j=int(j), q=int(q),
                        trig_side="B" if d["buy"][j] else "S", trig_sol=round(float(d["sol"][j]) / 1e9, 4), trig_move=round(float(F[j, FI["move"]]), 2),
                        trig_wt=int(d["wt"][j]), dslot=int(int(a["s"]) - d["s"][j]), didx=int(int(a["i"]) - d["i"][j]) if d["s"][j] == int(a["s"]) else None,
                        n_between=int(q - j), slip=round(pq / pj, 5), b0=round(b0, 3), s0=round(s0, 3), nb0=nb0, ns0=ns0, b3=round(b3, 3), s3=round(s3, 3),
                        holding=bool(posn > 1e6), wdk_holding=bool(posw > 1e6), fee=a["fee"], tip=a["tip"], relay=a["relay"],
                        curve=round(float(d["vsol"][q]) / 1e9, 3)))
    json.dump(out, open(f"{OUT}/att_{run}.json", "w"))
    del E.DAYS[run]
    return out, miss, len(A)

def pct(x, ps=(10, 25, 50, 75, 90)):
    x = sorted(v for v in x if v is not None)
    return [round(x[min(len(x) - 1, int(p / 100 * len(x)))], 4) for p in ps] if x else None

if __name__ == "__main__":
    for run in sys.argv[1:] or ["R2", "R3", "R1", "R4"]:
        out, miss, na = run_day(run)
        ok = [o for o in out if o["ok"]]; fl = [o for o in out if not o["ok"]]
        print(f"\n===== {run}: buy attempts {na}, placed {len(out)} (not in day arrays {miss}); ok {len(ok)}, failed {len(fl)} ({len(fl) / max(1, len(out)):.0%})")
        print(f"  slippage faced (price before attempt / after trigger): ok {pct([o['slip'] for o in ok])} | failed {pct([o['slip'] for o in fl])}")
        for lo, hi in ((0, 1.0001), (1.0001, 1.01), (1.01, 1.02), (1.02, 1.03), (1.03, 1.05), (1.05, 1.08), (1.08, 1.15), (1.15, 9)):
            g = [o for o in out if lo <= o["slip"] < hi]
            if g: print(f"    slip {lo:.4f}-{hi:.4f}: n {len(g):5d} fail rate {np.mean([1 - o['ok'] for o in g]):.0%}")
        print(f"  trigger side ok {collections.Counter(o['trig_side'] for o in ok)} failed {collections.Counter(o['trig_side'] for o in fl)}")
        print(f"  dslot ok {collections.Counter(min(o['dslot'], 3) for o in ok)} failed {collections.Counter(min(o['dslot'], 3) for o in fl)}")
        print(f"  trades between trigger and attempt: ok {pct([o['n_between'] for o in ok])} failed {pct([o['n_between'] for o in fl])}")
        print(f"  holding already: ok {sum(o['holding'] for o in ok)} failed {sum(o['holding'] for o in fl)}; wdk holding: ok {sum(o['wdk_holding'] for o in ok)} failed {sum(o['wdk_holding'] for o in fl)}")
        print(f"  relay/tip: ok {collections.Counter(o['relay'] for o in ok)} failed {collections.Counter(o['relay'] for o in fl)}")
        print(f"  fee: ok {collections.Counter(o['fee'] for o in ok).most_common(3)} failed {collections.Counter(o['fee'] for o in fl).most_common(3)}")
        print(f"  same-slot max buy before: ok {pct([o['b0'] for o in ok])} failed {pct([o['b0'] for o in fl])}")
        bt = collections.defaultdict(list)
        for o in out: bt[o["tok"]].append((o["s"], o["i"], o["ok"]))
        rep = 0; rep_after_fail = 0
        for v in bt.values():
            v.sort()
            for x, y in zip(v, v[1:]):
                if y[0] - x[0] <= 3: rep += 1; rep_after_fail += (x[2] == 0)
        print(f"  attempts within 3 slots after a previous attempt on the same token: {rep} ({rep / len(out):.0%}); of them after a FAILED one: {rep_after_fail}")
