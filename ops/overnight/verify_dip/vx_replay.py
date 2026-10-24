#!/usr/bin/env python3
"""verify_dip / vx_replay: independent rebuild of the dip-backrun events, features and PnL from vx_extract output
(own code; does not import core/rp.py or dip/). Written from the claim's spec:
  event : successful SELL >= 1 SOL (curve SOL), after the glued bundle, age (slot - create slot) x 212 ms in [1, 120] s,
          vsol after the sell < 100 SOL, at most one event per launch per 20 slots ("busy").
  entry : our 0.5 SOL buy at proxy arrival arr(sell) + L; every trade with proxy arrival < that is ahead of us.
          arr = slot x 212 + idx / blocksize x 212, blocksize = max(max idx seen in slot + 1, idx + 1) (default 400).
  exit  : sell everything at slot buy_slot + 4, before the first trade of that slot whose in-slot position is >= SL ms.
  costs : pump fee + creator fee bps both ways, TXC per tx (applied later), follower slippage imputed (sha256("dip"+sig)).
Variants per event and L (gross PnL = SOL back - 0.5, before the per-tx cost):
  c    : claim spec (buy slot = slot of the last trade ahead of us, SL 75 ms, slippage imputed, sell at once if vsol >= 110)
  t    : buy slot = slot of our own proxy arrival (floor((arr(sell)+L)/212)), otherwise as c
  f0   : as c, our sell lands first in its slot (SL 0)       f150 : as c, SL 150 ms
  ns   : as c, no follower slippage (all followers kept)
  g    : as c, but no early sell at vsol >= 110: hold to the exit; flag if the curve completes before it
  tf0 / tf150 : variant t with SL 0 / 150
usage: python3 -I -B vx_replay.py <out.jsonl.gz> [SIZE=mine|claim]"""
import sys, os, json, gzip, zlib, hashlib, collections, glob
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.path.join(HERE, "work")
D = "/home/moiz/sniper-data/collect"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543"}
SMS = 212.0; B = 0.5; MIN_SELL = 1_000_000_000; MAX_AGE = 120.0; LATS = (0, 20, 25, 35, 45, 50, 75)
VT_DONE = 1_073_000_000_000_000 - 793_100_000_000_000
SOLQ = "11111111111111111111111111111111"
G = {}

def load_sizes(src):
    if src == "claim":
        return {int(k): v for k, v in json.load(open(os.path.join(HERE, "snap", "slotsize2.json"))).items()}
    S = {}
    for tag in RUNS:
        for k, v in json.load(gzip.open(os.path.join(WORK, tag, "smax.json.gz"), "rt")).items():
            k = int(k)
            if v + 1 > S.get(k, 0): S[k] = v + 1
    return S

def init(src):
    G["SS"] = load_sizes(src)
    rows = json.load(open(os.path.join(HERE, "snap", "a8_slack.json")))["rows"]
    G["SLACK"] = sorted(r[1] for r in rows)
    L = {}
    for tag, run in RUNS.items():
        for l in open(os.path.join(D, run, "launches.jsonl")):
            try: c = json.loads(l)
            except Exception: continue
            if c["mint"] not in L: c["run"] = tag; L[c["mint"]] = c
    G["L"] = L

def slack(sig):
    SL = G["SLACK"]; h = int(hashlib.sha256(("dip" + sig).encode()).hexdigest()[:8], 16) / 2 ** 32
    return SL[min(len(SL) - 1, int(h * len(SL)))]

def pos_ms(t):
    return t["i"] / max(G["SS"].get(t["s"], 400), t["i"] + 1) * SMS

def arr(t): return t["s"] * SMS + pos_ms(t)

def tape(rows):
    """successful TradeEvents in chain order, dedup (sig, event index); gap repair like the claim (synthetic net trade
    right before the first trade whose pre-state does not match the previous post-state, constant product kept)"""
    out = []; seen = set()
    for r in rows:
        if r[4]: continue
        key = (r[3], r[2])
        if key in seen: continue
        seen.add(key)
        out.append(dict(s=r[0], i=r[1], k=r[2], sig=r[3], payer=r[5], user=r[6], sol=r[7], tok=r[8], buy=r[9] == 1, vsol=r[10], vtok=r[11],
                        fbps=r[14], cbps=r[16], ixn=r[18], tflag=r[19], bcp=r[21], tips=r[25], cup=r[24], syn=False))
    out.sort(key=lambda t: (t["s"], t["i"], t["k"]))
    rep = []; prev = None; ngap = 0
    for t in out:
        pre = (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])
        if prev is not None and pre != prev and t["vtok"] and prev[1]:
            dv = pre[0] - prev[0]; dt = pre[1] - prev[1]
            if dt != 0 and abs(dv) > 1000 and abs((pre[0] * pre[1]) / (prev[0] * prev[1]) - 1) < 0.002:
                rep.append(dict(t, k=-1, sig="gap:" + t["sig"], payer="?", user="?", buy=dv > 0, sol=abs(dv), tok=abs(dt), vsol=pre[0], vtok=pre[1],
                                syn=True, tips=0))
                ngap += 1
        rep.append(t); prev = (t["vsol"], t["vtok"])
    return rep, ngap

def structure(tr, c):
    S = c["slot"]; ci = c.get("idx"); ins = {c.get("creator"), c.get("user")}; g_end = 0; prev = ci; glued = []
    for k, t in enumerate(tr):
        if t["sig"] == c.get("sig"): g_end = k + 1; continue
        if t["s"] == S and prev is not None and t["i"] in (prev, prev + 1) and t["buy"]: glued.append(t); prev = t["i"]; g_end = k + 1
        elif t["s"] == S and prev is not None and t["i"] > prev + 1: break
        elif t["s"] > S: break
    ins |= {t["user"] for t in glued}
    return g_end, glued, ins

def fbps(t): return ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4

def roundtrip(tr, ke, fr, s_buy, SL, slipimp=True, gradbreak=True, H=4):
    """our buy right before tr[ke] (after tr[ke-1]); sell at slot s_buy + H before the first trade there with position >= SL"""
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    E = s_buy + H; frs = fr; nf = 0; nd = 0; grad = False; nfs = 0; last = None
    for t in tr[ke:]:
        if t["s"] > E or (t["s"] == E and (SL <= 0 or pos_ms(t) >= SL)): break
        if t["buy"] and slipimp and not t["syn"]:
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): nd += 1; continue
            V += t["sol"]; T -= d; nf += 1
        elif t["buy"]:
            d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; nf += 1
        else:
            so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]; nfs += 1
        frs = fbps(t); last = t
        if V >= 110e9 and gradbreak: grad = True; break
        if T <= VT_DONE: grad = True; break
    so = V * q // (T + q)
    return so * (1 - frs) / 1e9 - B, dict(nf=nf, nd=nd, nfs=nfs, grad=grad, V=V, T=T, q=q, E=E, last=(last["sig"] if last else None))

def work(key):
    tag, b = key; L = G["L"]
    data = json.load(gzip.open(os.path.join(WORK, tag, f"b{b:03d}.json.gz"), "rt"))
    out = []; stats = collections.Counter()
    for m, d in data.items():
        c = L.get(m)
        if c is None or c["run"] != tag: stats["not_launch"] += 1; continue
        cr = d.get("c") or {}
        kind = "std" if (cr.get("quote") == SOLQ and cr.get("may") == 0 and cr.get("vsol0") == 30_000_000_000) else \
               ("mayhem" if cr.get("may") == 1 else ("nonsol" if cr.get("quote") not in (None, SOLQ) else ("nocreate" if not cr else "other")))
        stats["kind_" + kind] += 1
        tr, ngap = tape(d["t"])
        if not tr: continue
        claim_filter = not (min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9)
        S = c["slot"]; g_end, glued, ins = structure(tr, c)
        if g_end < 1: stats["no_gend"] += 1; continue
        ge = tr[g_end - 1]; pbp = ge["vsol"] / ge["vtok"]; busy = -1
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < MIN_SELL or t["syn"] or k < g_end: continue
            age = (t["s"] - S) * SMS / 1000
            if age < 1 or age > MAX_AGE or t["vsol"] >= 100e9 or t["s"] <= busy: continue
            fr = fbps(t)
            p_before = (t["vsol"] + t["sol"]) / (t["vtok"] - t["tok"]); p_after = t["vsol"] / t["vtok"]
            w20 = [x for x in tr[max(0, k - 60):k] if t["s"] - x["s"] <= 20]
            peak = max(x["vsol"] / x["vtok"] for x in tr[:k + 1])
            su = t["user"]; sb = [x for x in tr[:k] if x["user"] == su]
            s_tok_b = sum(x["tok"] for x in sb if x["buy"]); s_tok_s = sum(x["tok"] for x in sb if not x["buy"])
            s_sol_b = sum(x["sol"] for x in sb if x["buy"]); s_sol_s = sum(x["sol"] for x in sb if not x["buy"]) + t["sol"]
            held = max(s_tok_b - s_tok_s, 1); fb = next((x for x in sb if x["buy"]), None)
            big_before = [x for x in tr[g_end:k] if (not x["buy"]) and x["sol"] >= MIN_SELL]
            pr = lambda x: x["vsol"] / x["vtok"]
            j5 = next((j for j in range(k - 1, -1, -1) if t["s"] - tr[j]["s"] >= 5), None)
            j20 = next((j for j in range(k - 1, -1, -1) if t["s"] - tr[j]["s"] >= 20), None)
            w3 = [x for x in tr[max(0, k - 30):k] if t["s"] - x["s"] <= 3]
            insb = sum(x["tok"] for x in tr[:k] if x["user"] in ins and x["buy"]); inss = sum(x["tok"] for x in tr[:k] if x["user"] in ins and not x["buy"])
            xf = dict(s_frac=round(min(t["tok"] / held, 2.0), 3), s_pnl=round((s_sol_s - s_sol_b) / 1e9, 3), s_nb=sum(1 for x in sb if x["buy"]),
                      s_entry=(fb["s"] - S) if fb else -1, s_in_bundle=int(su in ins), n_big=len(big_before),
                      since_big=(t["s"] - big_before[-1]["s"]) if big_before else 999, ret5=round(p_before / pr(tr[j5]), 4) if j5 is not None else 1.0,
                      ret20=round(p_before / pr(tr[j20]), 4) if j20 is not None else 1.0, peak_mult=round(peak / pbp, 4),
                      b3=round(sum(x["sol"] for x in w3 if x["buy"]) / 1e9, 3), nb3=sum(1 for x in w3 if x["buy"]),
                      sellers20=len({x["user"] for x in w20 if not x["buy"]}), uniq_buyers=len({x["user"] for x in tr[:k] if x["buy"]}),
                      ins_sold=round(inss / insb, 3) if insb else 0.0,
                      net_flow=round((sum(x["sol"] for x in tr[:k] if x["buy"]) - sum(x["sol"] for x in tr[:k] if not x["buy"])) / 1e9, 3))
            same_tx = [x for x in tr if x["sig"] == t["sig"] and x is not t]
            row = dict(m=m, run=tag, bt=c["bt"], age=round(age, 2), s=t["s"], i=t["i"], sig=t["sig"], kind=kind, cf=claim_filter, ngap=ngap,
                       sell=round(t["sol"] / 1e9, 3), seller=t["user"][:8], seller_full=t["user"], ins=t["user"] in ins, xf=xf,
                       drop=round(p_after / p_before, 4), vsol=round(t["vsol"] / 1e9, 2), nb=sum(1 for x in tr[:k] if x["buy"]),
                       ns=sum(1 for x in tr[:k] if not x["buy"]), pb=round(p_after / pbp, 4), dd=round(p_after / peak, 4),
                       b20=round(sum(x["sol"] for x in w20 if x["buy"]) / 1e9, 3), s20=round(sum(x["sol"] for x in w20 if not x["buy"]) / 1e9, 3),
                       u20=len({x["user"] for x in w20 if x["buy"]}), dev=round(sum(x["sol"] for x in tr[:g_end] if x["buy"]) / 1e9, 3), glued=len(glued),
                       first_big=not any((not x["buy"]) and x["sol"] >= MIN_SELL for x in tr[g_end:k]),
                       multileg=len(same_tx), multileg_buy=sum(1 for x in same_tx if x["buy"]), ixn=t["ixn"], fr=fr,
                       pnl={}, ahead={}, px={}, info={})
            a0 = arr(t)
            for Lm in LATS:
                ke = k + 1
                while ke < len(tr) and arr(tr[ke]) < a0 + Lm: ke += 1
                if ke >= len(tr): continue
                s_in = tr[ke - 1]["s"]; s_true = int((a0 + Lm) // SMS)
                v = {}
                v["c"], inf = roundtrip(tr, ke, fr, s_in, 75.0)
                v["t"], _ = roundtrip(tr, ke, fr, s_true, 75.0)
                v["f0"], _ = roundtrip(tr, ke, fr, s_in, 0.0)
                v["f150"], _ = roundtrip(tr, ke, fr, s_in, 150.0)
                v["tf0"], _ = roundtrip(tr, ke, fr, s_true, 0.0)
                v["tf150"], _ = roundtrip(tr, ke, fr, s_true, 150.0)
                v["ns"], _ = roundtrip(tr, ke, fr, s_in, 75.0, slipimp=False)
                v["g"], ig = roundtrip(tr, ke, fr, s_in, 75.0, gradbreak=False)
                v["h8"], _ = roundtrip(tr, ke, fr, s_in, 75.0, H=8)
                row["pnl"][str(Lm)] = {kk: round(x, 6) for kk, x in v.items()}
                row["ahead"][str(Lm)] = ke - k - 1
                row["px"][str(Lm)] = round((tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after, 4)
                row["info"][str(Lm)] = dict(ke_sig=tr[ke]["sig"], prev_sig=tr[ke - 1]["sig"], s_in=s_in, s_true=s_true, grad=inf["grad"], grad_g=ig["grad"],
                                            nf=inf["nf"], nd=inf["nd"], nfs=inf["nfs"], E=inf["E"], last=inf["last"],
                                            Vin=tr[ke - 1]["vsol"], Tin=tr[ke - 1]["vtok"], Vout=inf["V"], Tout=inf["T"], q=inf["q"])
            out.append(row); busy = t["s"] + 20
    return out, stats

if __name__ == "__main__":
    OUT = sys.argv[1]; src = sys.argv[2] if len(sys.argv) > 2 else "mine"
    keys = [(tag, b) for tag in RUNS for b in range(256)]
    res = []; ST = collections.Counter()
    with Pool(8, initializer=init, initargs=(src,)) as p:
        for o, st in p.imap_unordered(work, keys, chunksize=4): res += o; ST.update(st)
    with gzip.open(OUT, "wt") as f:
        for r in res: f.write(json.dumps(r) + "\n")
    print("events", len(res), dict(ST))
