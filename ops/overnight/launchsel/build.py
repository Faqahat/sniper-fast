#!/usr/bin/env python3
# LAUNCH SELECTION dataset (owner 10-23 23:40 PKT). Every recorded launch (R1 + R2 + R3), several DECISION points after the create
# (0 = create only, 1 s, 3 s, 10 s, 30 s): features from what is visible by then (no look-ahead), our 0.5 SOL buy LANDING 60 ms
# after the decision, outcomes with pump fees + 0.0008 SOL per tx (plain curve replay, no follower slippage limits):
#   fixed holds 5 s / 30 s / 2 min / 10 min; TP/SL ladders (TP +30%/SL -20%/2 min, TP +50%/SL -25%/5 min, TP +100%/SL -30%/10 min,
#   TP +200%/SL -40%/10 min); max multiple within 5 min; runner (>= 2x within 5 min); instant dump (<= -30% within 30 s);
#   dead (< 3 outside buys in the 30 s after our buy).   -> launchsel/launches.jsonl.gz (one row per launch x decision point)
import os, sys, json, gzip, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "1"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
B = 0.5e9; TXC = 0.0008; LAND = 60.0; SMS = 212.0
DEC = (0, 1, 3, 10, 30)
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(s, i): return s * SMS + i / max(SS.get(s, 400), i + 1) * SMS
L = rp.load_launches()
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
TGT = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"}
D = "/home/moiz/sniper-data/collect"; RUNS = ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426")
EN = {}
for run in RUNS:
    for l in open(f"{D}/{run}/enrich.jsonl"):
        try: e = json.loads(l)
        except Exception: continue
        j = ((e.get("meta") or {}).get("json") or {}); txt = json.dumps(j).lower()
        EN[e["mint"]] = dict(prior_creates=len(e.get("creator_recent_creates") or []), prior_n=e.get("creator_prior_n") or 0, funder=e.get("funder"),
                             jito=int(bool(e.get("jito_create"))), tw=int("twitter" in j or "x.com/" in txt or "twitter.com/" in txt), tg=int("telegram" in j or "t.me/" in txt),
                             web=int(bool(j.get("website"))), desc_len=len(j.get("description") or ""), img_host=((e.get("hosts") or {}).get("image") or ""),
                             meta_ok=int(bool(j)))
# creator / funder history inside our own data (only launches >= 30 min earlier count, their outcome = max curve SOL in our data)
OUT = {}
by_creator = collections.defaultdict(list); by_funder = collections.defaultdict(list)
for m, c in L.items():
    cr = c.get("creator") or c.get("user"); by_creator[cr].append((c["bt"], m))
    f = (EN.get(m) or {}).get("funder")
    if f: by_funder[f if isinstance(f, str) else json.dumps(f)].append((c["bt"], m))
byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
def first_pass(key):
    o = {}
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        if tr: o[m] = max(t["vsol"] for t in tr) / 1e9
    return o
def hist(lst, bt, m):
    prev = [x for x in lst if x[0] <= bt - 1800 and x[1] != m]
    mx = [OUT.get(x[1], 0) for x in prev]
    return len(prev), sum(1 for v in mx if v >= 114), (max(mx) if mx else 0)
def work(key):
    rows = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem") or "InitializeMayhemState" in (c.get("ixn") or []): continue
        cr = c.get("creator") or c.get("user"); st = rp.structure(tr, c); ins = st["insiders"]; e = EN.get(m, {})
        a_c = arr(c["slot"], c.get("idx") or 0); S0 = c["slot"]
        fkey = e.get("funder"); fkey = fkey if isinstance(fkey, str) or fkey is None else json.dumps(fkey)
        ch = hist(by_creator[cr], c["bt"], m); fh = hist(by_funder[fkey], c["bt"], m) if fkey else (0, 0, 0)
        dev_buy = sum(t["sol"] for t in tr if t["user"] == cr and t["buy"] and t["s"] == S0) / 1e9
        static = dict(m=m, run=c["run"], bt=c["bt"], dev_buy=round(dev_buy, 3), create_fee=(c.get("fee") or 0) / 1e9, name_len=len(c.get("name") or ""),
                      sym_len=len(c.get("symbol") or ""), cr_prev=ch[0], cr_grad=ch[1], cr_best=round(ch[2], 1), fu_prev=fh[0], fu_grad=fh[1], fu_best=round(fh[2], 1),
                      **{k: v for k, v in e.items() if k not in ("funder",)}, has_funder=int(bool(fkey)))
        A = [arr(t["s"], t["i"]) for t in tr]
        for d in DEC:
            td = a_c + d * 1000.0
            vis = [t for t, a in zip(tr, A) if a <= td]
            ke = next((k for k, a in enumerate(A) if a >= td + LAND), None)
            if ke is None or ke == 0: continue
            buys = [t for t in vis if t["buy"]]; sells = [t for t in vis if not t["buy"]]
            outb = [t for t in buys if t["user"] != cr and t["user"] not in ins]
            ub = {t["user"] for t in outb}; bsol = sum(t["sol"] for t in buys) / 1e9; ssol = sum(t["sol"] for t in sells) / 1e9
            per = collections.Counter()
            for t in buys: per[t["user"]] += t["sol"]
            top = max(per.values()) / 1e9 if per else 0
            last1 = [t for t, a in zip(tr, A) if td - 1000 < a <= td]
            vs_now = (vis[-1]["vsol"] if vis else tr[0]["vsol"]) / 1e9
            pb = tr[max(st["g_end"], 1) - 1]["vsol"] / tr[max(st["g_end"], 1) - 1]["vtok"]
            p_now = (vis[-1]["vsol"] / vis[-1]["vtok"]) if vis else pb
            peak = max([t["vsol"] / t["vtok"] for t in vis] + [p_now])
            f = dict(static, d=d, n_buys=len(buys), n_sells=len(sells), uniq_out=len(ub), out_sol=round(sum(t["sol"] for t in outb) / 1e9, 3), buy_sol=round(bsol, 3),
                     sell_sol=round(ssol, 3), net=round(bsol - ssol, 3), bs_ratio=round(bsol / (ssol + 0.01), 2), top_share=round(top / (bsol + 1e-9), 3) if bsol else 0,
                     max_buy=round(top, 3), bundle_n=len(st["glued"]), ins_n=len(ins), ins_sold=int(any((not t["buy"]) and t["user"] in ins for t in vis)),
                     dev_sold=int(any((not t["buy"]) and t["user"] == cr for t in vis)), coh_n=len({t["user"] for t in buys if t["user"] in COH}),
                     coh_sol=round(sum(t["sol"] for t in buys if t["user"] in COH) / 1e9, 3), tgt_n=len({t["user"] for t in buys if t["user"] in TGT}),
                     slot01_out=len({t["user"] for t in outb if t["s"] <= S0 + 1}), buys_1s=sum(1 for t in last1 if t["buy"]), sells_1s=sum(1 for t in last1 if not t["buy"]),
                     vsol=round(vs_now, 2), chg=round(p_now / pb, 3), dd=round(p_now / peak, 3), since_last=round((td - A[len(vis) - 1]) / 1000, 2) if vis else 99,
                     sold_absorbed=round((sum(t["sol"] for t in outb if t["s"] > (sells[0]["s"] if sells else 1e18)) / 1e9), 3))
            # outcome: our 0.5 SOL lands at A[ke]
            fr = ((tr[ke - 1]["fbps"] or 95) + (tr[ke - 1]["cbps"] or 30)) / 1e4
            V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]; X = int(B / (1 + fr)); q = T * X // (V + X); V += X; T -= q
            cost = B / 1e9 + TXC; a_in = A[ke]; frs = fr
            def val(): return (V * q / (T + q)) * (1 - frs) / 1e9 - TXC
            res = {}; mx5 = val() / cost; mn30 = mx5; tp_state = {}; outside30 = 0
            LAD = {"tp30_sl20_2m": (0.3, 0.2, 120), "tp50_sl25_5m": (0.5, 0.25, 300), "tp100_sl30_10m": (1.0, 0.3, 600), "tp200_sl40_10m": (2.0, 0.4, 600)}
            HOLD = {"h5s": 5, "h30s": 30, "h2m": 120, "h10m": 600}
            pend = {}
            for k in range(ke, len(tr)):
                t = tr[k]; a = A[k]; el = (a - a_in) / 1000
                for nm, h in HOLD.items():
                    if nm not in res and el >= h: res[nm] = val() - cost
                for nm, (s_out) in list(pend.items()):
                    if t["s"] > s_out: res[nm] = val() - cost; del pend[nm]
                if t["buy"]:
                    dq = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= dq
                    if el <= 30 and t["user"] != cr: outside30 += 1
                else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
                frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
                r = val() / cost
                if el <= 300: mx5 = max(mx5, r)
                if el <= 30: mn30 = min(mn30, r)
                for nm, (tp, sl, cap) in LAD.items():
                    if nm in res or nm in pend: continue
                    if el >= cap: res[nm] = val() - cost
                    elif r >= 1 + tp or r <= 1 - sl: pend[nm] = t["s"]          # sell lands in the next slot
                if V >= 114e9 or el > 620: break
            end = val() - cost
            for nm in list(HOLD) + list(LAD): res.setdefault(nm, end)
            f.update(res={k: round(v, 4) for k, v in res.items()}, mx5=round(mx5, 3), runner=int(mx5 >= 2), dump=int(mn30 <= 0.7), dead=int(outside30 < 3))
            rows.append(f)
    return rows
if __name__ == "__main__":
    with Pool(8) as p:
        for o in p.imap_unordered(first_pass, sorted(byb), chunksize=4): OUT.update(o)
    n = 0
    with gzip.open("/home/moiz/sniper/ops/overnight/launchsel/launches.jsonl.gz", "wt") as fo, Pool(8) as p:
        for rows in p.imap_unordered(work, sorted(byb), chunksize=2):
            for r in rows: fo.write(json.dumps(r) + "\n"); n += 1
    print("rows", n, "launches", len(L))
