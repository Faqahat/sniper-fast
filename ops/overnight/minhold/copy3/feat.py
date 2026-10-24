# shared helpers for the copy3 study (read-only): tape parsing, launch structure, snapshot features at a point in time
import json, gzip, glob, os, zlib, collections
SL = 0.212                      # seconds per slot
D = "/home/moiz/sniper-data/collect"
PA = {"R1": "phaseA", "R2": "phaseA_selfwd", "R3": "phaseA_r3"}
MAYHEM_AGENT = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
V0, T0 = 30_000_000_000, 1_073_000_000_000_000

def bucket(m): return zlib.crc32(m.encode()) % 256

def read_bucket_all(run, b, keep=None):
    """all successful trade rows in one bucket -> {mint: [rows sorted]}, failed rows {mint: [(s,i,sig,signer,ixn)]},
    slot max index {slot: max i}. keep: optional set of mints to keep failed rows for."""
    out = collections.defaultdict(list); fail = collections.defaultdict(list); seen = set(); mx = {}
    for f in glob.glob(os.path.join(D, PA[run], f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                k = line[2]
                if k not in "TX": continue
                r = json.loads(line)
                s, i = r[2], r[3]
                if i is not None and i > mx.get(s, -1): mx[s] = i
                if k == "X":
                    if keep is not None and r[1] in keep and r[12] == 1:
                        fail[r[1]].append((s, i, r[5], r[6] or "", [x for x in (r[13] or []) if isinstance(x, str)][:6]))
                    continue
                (_, m, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                if err or (sig, j) in seen: continue
                seen.add((sig, j))
                out[m].append(dict(s=s, i=i, j=j, bt=bt, sig=sig, payer=payer, user=user, buy=buy == 1, sol=sol, tok=tok, vsol=vsol, vtok=vtok,
                                   fbps=fbps or 95, cbps=cbps or 30, fee=fee, cup=cup, cul=cul, tips=tips))
        except (EOFError, OSError, zlib.error): pass
    for m in out: out[m].sort(key=lambda t: (t["s"], t["i"], t["j"]))
    return out, fail, mx

def is_mayhem(tr):
    return any(t["vsol"] > 200e9 or (t["vtok"] and t["vsol"] < 25e9) for t in tr[:50]) or any(t["user"] == MAYHEM_AGENT for t in tr[:200])

def structure(tr, c):
    """creator buy (create tx), glued create-slot bundle, insiders"""
    S = c["slot"]; creator = c.get("creator") or c.get("user"); signer = c.get("user")
    dev_sol = 0; glued = []; prev = c.get("idx")
    for k, t in enumerate(tr):
        if t["sig"] == c.get("sig"):
            if t["buy"]: dev_sol += t["sol"]
            continue
        if t["s"] == S and prev is not None and t["i"] in (prev, prev + 1) and t["buy"]: glued.append(t); prev = t["i"]
        elif t["s"] == S and prev is not None and t["i"] > prev + 1: break
        elif t["s"] > S: break
    ins = {creator, signer} | {t["user"] for t in glued}
    cs_users = {t["user"] for t in tr if t["s"] == S and t["buy"]} - {creator, signer}
    return dict(creator=creator, signer=signer, dev_sol=dev_sol / 1e9, bundle_n=len(glued), bundle_sol=sum(t["sol"] for t in glued) / 1e9,
                insiders=ins, cs_n=len(cs_users))

def px(V, T): return V / T if T else 0.0

def snapshot(tr, c, st, n, now_slot):
    """features of the token using only trades tr[:n] (all before the moment), at slot now_slot"""
    S = c["slot"]; past = tr[:n]
    V, T = (past[-1]["vsol"], past[-1]["vtok"]) if past else (V0, T0)
    p = px(V, T)
    def p_at(sec):
        lim = now_slot - sec / SL; V_, T_ = V0, T0
        for t in past:
            if t["s"] > lim: break
            V_, T_ = t["vsol"], t["vtok"]
        return px(V_, T_)
    def win(sec):
        lim = now_slot - sec / SL
        return [t for t in past if t["s"] >= lim]
    w10 = win(10); w60 = win(60); w3 = win(3)
    peak = max([px(t["vsol"], t["vtok"]) for t in past] or [p])
    cr = st["creator"]
    dev_b = sum(t["tok"] for t in past if t["user"] == cr and t["buy"]); dev_s = sum(t["tok"] for t in past if t["user"] == cr and not t["buy"])
    buyers = {t["user"] for t in past if t["buy"]}
    return dict(age=(now_slot - S) * SL, vsol=V / 1e9, ch3=p / p_at(3) - 1, ch10=p / p_at(10) - 1, ch60=p / p_at(60) - 1, dd_peak=p / peak - 1,
                peak_vsol=max([t["vsol"] for t in past] or [V]) / 1e9,
                n_tr=len(past), n_buyers=len(buyers), gap=(now_slot - past[-1]["s"]) * SL if past else (now_slot - S) * SL,
                b10=sum(t["sol"] for t in w10 if t["buy"]) / 1e9, s10=sum(t["sol"] for t in w10 if not t["buy"]) / 1e9, n10=len(w10),
                u10=len({t["user"] for t in w10 if t["buy"]}), b60=sum(t["sol"] for t in w60 if t["buy"]) / 1e9, s60=sum(t["sol"] for t in w60 if not t["buy"]) / 1e9,
                n60=len(w60), n3=len(w3), bigsell10=max([t["sol"] for t in w10 if not t["buy"]] or [0]) / 1e9, bigbuy10=max([t["sol"] for t in w10 if t["buy"]] or [0]) / 1e9,
                dev_sol=st["dev_sol"], bundle_n=st["bundle_n"], bundle_sol=st["bundle_sol"], cs_n=st["cs_n"],
                dev_sold=dev_s / dev_b if dev_b else 0.0)

def forward(tr, n, now_slot, p_now):
    """price path after the moment (no insertion): ratio of price at +10/30/60/120/300 s, max/min within 60 s"""
    res = {}
    V = T = None; k = n; mx60 = mn60 = p_now
    for sec in (10, 30, 60, 120, 300):
        lim = now_slot + sec / SL
        while k < len(tr) and tr[k]["s"] <= lim:
            V, T = tr[k]["vsol"], tr[k]["vtok"]; pk = px(V, T)
            if tr[k]["s"] <= now_slot + 60 / SL: mx60 = max(mx60, pk); mn60 = min(mn60, pk)
            k += 1
        res[f"f{sec}"] = (px(V, T) / p_now) if (V is not None and p_now) else 1.0
    res["mx60"] = mx60 / p_now if p_now else 1; res["mn60"] = mn60 / p_now if p_now else 1
    return res
