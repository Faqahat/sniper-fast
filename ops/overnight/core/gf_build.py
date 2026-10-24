#!/usr/bin/env python3
# Generic-flow study, stage 2: decision points. For every launch (SOL-quoted, not mayhem) and decision time T seconds
# after the create, the features known at T and what a buy decided at T would have made.
#   entry  : decided at T, lands LAT slots later (~0.42 s, cheap send, no race), AFTER every trade in those slots
#   costs  : pump fees from the data, 0.0002 SOL per tx (base + small priority), no tips
#   exits  : time holds (decision + 0.42 s latency), take-profit / stop / trailing (price legs fill 2 slots after trigger)
#   each exit twice: real path, and with every buy by SNIPER / PRO wallets after our entry removed ("nosnip")
# usage: RP_PHASEA_R2=phaseA_gf python3 -I gf_build.py  -> gf_points.jsonl.gz
import sys, os, json, gzip, math, bisect, datetime, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
CORE = "/home/moiz/sniper/ops/overnight/core"
L = rp.load_launches(); LS = json.load(open(os.environ.get("GF_LS", f"{CORE}/gf_launches.json"))); W = json.load(open(f"{CORE}/gf_wallets.json"))
SINCE = float(os.environ.get("GF_SINCE", "0")); OUTP = os.environ.get("GF_OUT", f"{CORE}/gf_points.jsonl.gz")   # forward runs
SL = rp.SLOT_MS / 1000.0; LAT = 2; B = 0.5
TS = (1, 2, 3, 5, 8, 12, 20, 30, 45, 60, 90, 120, 180)
PRO_PFX = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO = set()
for p in PRO_PFX:
    c = [u for u in W if u.startswith(p)]
    if c: PRO.add(max(c, key=lambda u: W[u][0]))
DROP = SNIPER | PRO
ACTIVE = {u for u, v in W.items() if v[0] >= 20 and u not in DROP}
def cls(u): return 3 if u in PRO else 2 if u in SNIPER else 1 if u in ACTIVE else 0      # 0 casual, 1 active non-sniper, 2 sniper, 3 pro
PKT = datetime.timezone(datetime.timedelta(hours=5))
# deployer track record, walk-forward: only launches whose 300 s outcome was known before this launch
REC = {}
byd = collections.defaultdict(list)
for m, v in sorted(LS.items(), key=lambda kv: kv[1]["bt"]): byd[v["dep"]].append((v["bt"], v))
for m, v in LS.items():
    prev = [x for bt, x in byd[v["dep"]] if bt + 300 <= v["bt"]]
    n = len(prev)
    REC[m] = [n, round(sum(x["nb60"] for x in prev) / n, 2) if n else -1, round(sum(x["pk300"] for x in prev) / n, 3) if n else -1,
              round(sum(1 for x in prev if x["pk300"] >= 2) / n, 3) if n else -1, round(sum(x["m60"] for x in prev) / n, 3) if n else -1,
              round(sum(x["sb60"] for x in prev) / n, 3) if n else -1]
def RULES():
    r = []
    for h in (3, 5, 10, 20, 30, 60, 120, 300): r.append(rp.R(f"h{h}", [(1.0, ("t", h + LAT * SL))], h + 1))
    r.append(rp.R("tp1.2_sl.9_c60", [(1.0, ("x", 1.2)), (1.0, ("sl", 0.9))], 60))
    r.append(rp.R("tp1.3_sl.85_c120", [(1.0, ("x", 1.3)), (1.0, ("sl", 0.85))], 120))
    r.append(rp.R("tp1.5_sl.8_c300", [(1.0, ("x", 1.5)), (1.0, ("sl", 0.8))], 300))
    r.append(rp.R("tp2_sl.75_c300", [(1.0, ("x", 2.0)), (1.0, ("sl", 0.75))], 300))
    r.append(rp.R("tr1.15_12_c180", [(1.0, ("dd", 1.15, 0.12)), (1.0, ("sl", 0.85))], 180))
    return r
RU = RULES(); RN = [r["name"] for r in RU]
todo = [m for m in LS if LS[m]["bt"] >= SINCE]
byb = collections.defaultdict(set)
for m in todo: byb[(LS[m]["run"], rp.bucket(m))].add(m)
def win(tr, k0, k1):
    """trades with slot in (k0, k1]"""
    return [t for t in tr if k0 < t["s"] <= k1]
def feats(tr, c, st, ts, S, p_b):
    ins = st["insiders"]; upto = [t for t in tr if t["s"] <= ts]
    if not upto: return None
    px = lambda k: next((t["vsol"] / t["vtok"] for t in reversed(upto) if t["s"] <= k and t["vtok"]), p_b)
    p_t = px(ts); pk = max(t["vsol"] / t["vtok"] for t in upto if t["vtok"])
    f = dict(mb=round(p_t / p_b, 4), pk=round(pk / p_b, 4), ddp=round(p_t / pk, 4), vs=round(upto[-1]["vsol"] / 1e9, 2),
             r1=round(p_t / px(ts - int(1 / SL)), 4), r3=round(p_t / px(ts - int(3 / SL)), 4), r10=round(p_t / px(ts - int(10 / SL)), 4),
             gap=round((ts - upto[-1]["s"]) * SL, 2))
    out = [t for t in upto if t["user"] not in ins]
    for name, k in (("a", 10 ** 9), ("w1", int(1 / SL)), ("w3", int(3 / SL)), ("w10", int(10 / SL))):
        w = [t for t in out if t["s"] > ts - k]
        bs = [t for t in w if t["buy"]]; ss = [t for t in w if not t["buy"]]
        f[f"nb_{name}"] = len(bs); f[f"ns_{name}"] = len(ss); f[f"bs_{name}"] = round(sum(t["sol"] for t in bs) / 1e9, 3)
        f[f"ss_{name}"] = round(sum(t["sol"] for t in ss) / 1e9, 3); f[f"nub_{name}"] = len({t["user"] for t in bs})
    for k, nm in ((0, "cas"), (1, "act"), (2, "snp"), (3, "pro")):
        bs = [t for t in out if t["buy"] and cls(t["user"]) == k]; ss = [t for t in out if not t["buy"] and cls(t["user"]) == k]
        f[f"b_{nm}"] = round(sum(t["sol"] for t in bs) / 1e9, 3); f[f"nu_{nm}"] = len({t["user"] for t in bs}); f[f"s_{nm}"] = round(sum(t["sol"] for t in ss) / 1e9, 3)
    ib = sum(t["tok"] for t in tr if t["user"] in ins and t["buy"]); isd = sum(t["tok"] for t in upto if t["user"] in ins and not t["buy"])
    f["ins_sold"] = round(isd / ib, 3) if ib else -1
    sb = sum(t["tok"] for t in out if t["buy"] and cls(t["user"]) >= 2); ssd = sum(t["tok"] for t in out if not t["buy"] and cls(t["user"]) >= 2)
    f["snp_left"] = round(1 - ssd / sb, 3) if sb else -1
    f["maxb"] = round(max((t["sol"] for t in out if t["buy"]), default=0) / 1e9, 3); f["nb1"] = sum(1 for t in out if t["buy"] and t["sol"] >= 1e9)
    f["tips_b"] = sum(1 for t in out if t["buy"] and t.get("tips"))
    return f
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); rows = []
    for m, tr in tra.items():
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c); ls = LS[m]; p_b = ls["p_b"]
        g = tr[st["g_end"] - 1] if st["g_end"] >= 1 else None
        base = dict(dev=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 3), gl=len(st["glued"]),
                    gls=round(sum(t["sol"] for t in st["glued"]) / 1e9, 3), mcb=round(p_b * 1e6, 2),
                    hr=datetime.datetime.fromtimestamp(c["bt"], PKT).hour, rec=REC[m])
        slots = [t["s"] for t in tr]
        for T in TS:
            ts = S + math.ceil(T / SL)
            if T > 3 and not any(ts - int(5 / SL) < t["s"] <= ts and t["user"] not in st["insiders"] for t in tr): continue   # dead: no outside trade in 5 s
            f = feats(tr, c, st, ts, S, p_b)
            if f is None: continue
            land = ts + LAT; idx = bisect.bisect_right(slots, land)
            if idx < 1: continue
            o1 = rp.sim(tr, c, st, idx, B, RU, fee_buy_pct=0.0004, sell_fee_sol=0.0002, delay_slots=2, bslot=land)
            if not o1: continue
            o2 = rp.sim(tr, c, st, idx, B, RU, fee_buy_pct=0.0004, sell_fee_sol=0.0002, delay_slots=2, bslot=land, drop_after=DROP)
            o = {n: [round(o1[n]["ret"], 4), round(o2[n]["ret"], 4) if o2 else None, int(o1[n]["grad"])] for n in RN}
            # entry price vs price at decision (our latency cost) and buys after entry by class within 10 s
            pe = tr[idx - 1]["vsol"] / tr[idx - 1]["vtok"]
            aft = [t for t in tr[idx:] if t["s"] <= land + int(10 / SL) and t["buy"] and t["user"] not in st["insiders"]]
            x = dict(m=m, run=run, T=T, f=f, **base, slip_lat=round(pe / (f["mb"] * p_b), 4), o=o,
                     a10=[round(sum(t["sol"] for t in aft if cls(t["user"]) == k) / 1e9, 3) for k in range(4)])
            rows.append(x)
    return rows
if __name__ == "__main__":
    n = 0
    with gzip.open(OUTP, "wt") as fo, Pool(10) as p:
        for rows in p.imap_unordered(work, sorted(byb)):
            for r in rows: fo.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1
    print(f"decision points: {n}; snipers {len(SNIPER)}, pros {len(PRO)}, active {len(ACTIVE)}")
