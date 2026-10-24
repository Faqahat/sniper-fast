#!/usr/bin/env python3
# Dip events with TIMED entries: a tx's arrival ~ its position in the block (index / block size x 212 ms, block size from
# core/slotsize2.json), like rp.place_proxy. Our buy lands L ms after the big sell's arrival: every trade with an earlier proxy
# arrival is ahead of us. L = 0 (right after the sell), 20, 35, 50, 75, 100, 150 ms.
# Same events and features as dipbuy.py (sell >= 1 SOL, age 1-120 s); exits: 8 slots, 12 slots, tp1.05 (cap 30 slots).
# Costs: pump fees + TXC per tx (default 0.0008) + PEN fill penalty (default 0). -> dip/events_timed.jsonl.gz
import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"
import rp
from multiprocessing import Pool
B = 0.5; TXC = float(os.environ.get("TXC", "0.0008")); PEN = float(os.environ.get("PEN", "0")); MIN_SELL = 1.0e9; MAX_AGE = 120
LATS = (0, 20, 35, 50, 75, 100, 150); SMS = rp.SLOT_MS
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
HK = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
def arr(t): return t["s"] * SMS + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * SMS
SLIPIMP = os.environ.get("SLIPIMP") == "1"
if SLIPIMP:
    import hashlib
    _rows = json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"]
    SLACK = sorted(sl for _, sl, _ in _rows)              # empirical slack of decoded follower limits (verifier a8)
def slack(sig):
    h = int(hashlib.sha256(("dip" + sig).encode()).hexdigest()[:8], 16) / 2 ** 32
    return SLACK[min(len(SLACK) - 1, int(h * len(SLACK)))]
def rt_fixed(tr, ke, fr, H):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = tr[ke - 1]["s"]; frs = fr
    for t in tr[ke:]:
        if t["s"] >= s_in + H: break
        if t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue    # this follower's min-tokens-out fails after our buy
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)
def rt_tp(tr, ke, fr, tp=1.05, hmax=30):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = tr[ke - 1]["s"]; frs = fr; trig = None; cost = B + TXC
    for t in tr[ke:]:
        if trig is not None and t["s"] > trig: break
        if t["s"] >= s_in + hmax: break
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
        if trig is None and ((V * q // (T + q)) * (1 - frs) / 1e9 - TXC) / cost >= tp: trig = t["s"]
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - cost
def work(key):
    run, b = key; out = []; hk = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem"): continue
        S = c["slot"]; st = rp.structure(tr, c); busy = -1
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; pbp = ge["vsol"] / ge["vtok"]
        for k, t in enumerate(tr):
            # HkQ7hMjy speed check: its buy right after a big sell -> proxy delay
            if t["user"] == HK and t["buy"] and k > 0 and not tr[k - 1]["buy"] and tr[k - 1]["sol"] >= MIN_SELL:
                hk.append(round(arr(t) - arr(tr[k - 1]), 2))
            if (not t["buy"]) or t["sol"] < 2e9 or t.get("syn") or k < st["g_end"] or t["user"] in st["insiders"]: continue
            age = (t["s"] - S) * SMS / 1000
            if age < 1 or age > MAX_AGE or t["vsol"] >= 100e9 or t["s"] <= busy: continue
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            p_before = (t["vsol"] - t["sol"]) / (t["vtok"] + t["tok"]); p_after = t["vsol"] / t["vtok"]
            w20 = [x for x in tr[max(0, k - 60):k] if t["s"] - x["s"] <= 20]
            peak = max(x["vsol"] / x["vtok"] for x in tr[:k + 1])
            # richer causal features (state up to and including the sell)
            su = t["user"]; sb = [x for x in tr[:k] if x["user"] == su]
            s_tok_b = sum(x["tok"] for x in sb if x["buy"]); s_tok_s = sum(x["tok"] for x in sb if not x["buy"])
            s_sol_b = sum(x["sol"] for x in sb if x["buy"]); s_sol_s = sum(x["sol"] for x in sb if not x["buy"]) + t["sol"]
            held = max(s_tok_b - s_tok_s, 1)
            fb = next((x for x in sb if x["buy"]), None)
            big_before = [x for x in tr[st["g_end"]:k] if (not x["buy"]) and x["sol"] >= MIN_SELL]
            def pr(x): return x["vsol"] / x["vtok"]
            j5 = next((j for j in range(k - 1, -1, -1) if t["s"] - tr[j]["s"] >= 5), None); j20 = next((j for j in range(k - 1, -1, -1) if t["s"] - tr[j]["s"] >= 20), None)
            p_pre = (t["vsol"] - t["sol"]) / (t["vtok"] + t["tok"])
            w3 = [x for x in tr[max(0, k - 30):k] if t["s"] - x["s"] <= 3]
            insb = sum(x["tok"] for x in tr[:k] if x["user"] in st["insiders"] and x["buy"]); inss = sum(x["tok"] for x in tr[:k] if x["user"] in st["insiders"] and not x["buy"])
            xf = dict(s_frac=round(min(t["tok"] / held, 2.0), 3), s_pnl=round((s_sol_s - s_sol_b) / 1e9, 3), s_nb=sum(1 for x in sb if x["buy"]),
                      s_entry=(fb["s"] - S) if fb else -1, s_in_bundle=int(su in st["insiders"]), n_big=len(big_before),
                      since_big=(t["s"] - big_before[-1]["s"]) if big_before else 999, ret5=round(p_pre / pr(tr[j5]), 4) if j5 is not None else 1.0,
                      ret20=round(p_pre / pr(tr[j20]), 4) if j20 is not None else 1.0, peak_mult=round(peak / pbp, 4), b3=round(sum(x["sol"] for x in w3 if x["buy"]) / 1e9, 3),
                      nb3=sum(1 for x in w3 if x["buy"]), sellers20=len({x["user"] for x in w20 if not x["buy"]}), uniq_buyers=len({x["user"] for x in tr[:k] if x["buy"]}),
                      ins_sold=round(inss / insb, 3) if insb else 0.0, net_flow=round((sum(x["sol"] for x in tr[:k] if x["buy"]) - sum(x["sol"] for x in tr[:k] if not x["buy"])) / 1e9, 3))
            row = dict(m=m, run=run, bt=c["bt"], age=round(age, 2), sell=round(t["sol"] / 1e9, 3), seller=t["user"][:8], ins=t["user"] in st["insiders"], xf=xf,
                       drop=round(p_after / p_before, 4), vsol=round(t["vsol"] / 1e9, 2), nb=sum(1 for x in tr[:k] if x["buy"]), ns=sum(1 for x in tr[:k] if not x["buy"]),
                       pb=round(p_after / pbp, 4), dd=round(p_after / peak, 4), b20=round(sum(x["sol"] for x in w20 if x["buy"]) / 1e9, 3),
                       s20=round(sum(x["sol"] for x in w20 if not x["buy"]) / 1e9, 3), u20=len({x["user"] for x in w20 if x["buy"]}),
                       dev=round(sum(x["sol"] for x in tr[:st["g_end"]] if x["buy"]) / 1e9, 3), glued=len(st["glued"]),
                       first_big=not any((not x["buy"]) and x["sol"] >= MIN_SELL for x in tr[st["g_end"]:k]), pnl={}, ahead={}, px={})
            a0 = arr(t)
            for Lm in LATS:
                ke = k + 1
                while ke < len(tr) and arr(tr[ke]) < a0 + Lm: ke += 1
                if ke >= len(tr): continue
                row["ahead"][str(Lm)] = ke - k - 1
                row["px"][str(Lm)] = round((tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after, 4)
                row["pnl"][str(Lm)] = {"8": round(rt_fixed(tr, ke, fr, 8), 5), "12": round(rt_fixed(tr, ke, fr, 12), 5), "tp": round(rt_tp(tr, ke, fr), 5)}
            out.append(row); busy = t["s"] + 20
    return out, hk
if __name__ == "__main__":
    res = []; HKD = []
    with Pool(8) as p:
        for o, h in p.imap_unordered(work, sorted(byb), chunksize=2): res += o; HKD += h
    with gzip.open(os.environ.get("DIP_OUT", "/home/moiz/sniper/ops/overnight/dip/events_whale.jsonl.gz"), "wt") as f:
        for r in res: f.write(json.dumps(r) + "\n")
    print("events", len(res))
    if HKD:
        HKD.sort(); n = len(HKD)
        print(f"HkQ7hMjy buys right after a big sell: {n}; proxy delay after the sell (ms): p10 {HKD[n // 10]} p25 {HKD[n // 4]} median {HKD[n // 2]} p75 {HKD[3 * n // 4]} p90 {HKD[9 * n // 10]}")
    for Lm in LATS:
        v = [r["pnl"][str(Lm)]["8"] for r in res if str(Lm) in r["pnl"]]; a = [r["ahead"][str(Lm)] for r in res if str(Lm) in r["ahead"]]
        print(f"  L={Lm:3d} ms: n {len(v)} mean(H8) {statistics.mean(v):+.4f} | trades ahead of us: median {statistics.median(a)} mean {statistics.mean(a):.2f}")
