#!/usr/bin/env python3
# LANDING-PATH STUDY, step 2 (READ-ONLY, offline). From the step-1 scan records build, per launch:
#   - the creator side: creator / create user / create payer / create signers + the "glued bundle"
#     (OK buys at consecutive block indexes right after the create in slot S; if the create's Jito bundle is known
#      from enrich.jsonl, the bundle membership decides; else a known multi-launch sniper in the run breaks it)
#   - every OUTSIDE tx in S..S+DMAX: OK buys (one row each, with landing path = services of the tip accounts it paid),
#     failed txs (one row each; tips revert on failure so their path is unknown here), other OK txs (counted).
#   - position = number of OK outside buy txs ahead in chain order (0 = first outside buyer).
#   - leader (getSlotLeaders) + client (getClusterNodes now; fallback older snapshots) + region (leader_geo.json).
#   - create position in its block = create index / max tx index seen in that slot (lower bound of block size).
#   - arrival ms in our engine's clock (shadow scores obs lines, 10-22 17:10 UTC on): matched by mint + wallet prefix.
#   - qsol: SOL-quoted curve (TradeEvent virtual_sol_reserves > 0); for other quotes the event amounts are quote-token units.
# Output: work/rows_buys.jsonl.gz, work/rows_fail.jsonl.gz, work/launches.jsonl.gz, work/build_meta.json
# usage: python3 -I l2_build.py
import os, sys, json, gzip, glob, collections

W = "/home/moiz/sniper/ops/overnight/landing/work"
RUNS = {"R1": "/home/moiz/sniper-data/collect/run_20261021_2207", "R2": "/home/moiz/sniper-data/collect/run_20261022_1543"}
TAG2R = {os.path.basename(v): k for k, v in RUNS.items()}
DMAX = 3                        # analysis window: create slot S .. S+3
SHADOW = ["/home/moiz/sniper-data/collect/shadow/scores_v1.jsonl", "/home/moiz/sniper-data/collect/shadow/scores_v2.jsonl",
          "/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"]
BASE_FEE = 5000
I = sys.intern

# ---------------- reference data ----------------
cn_now = json.load(open(os.path.join(W, "rpc/clusternodes_now.json")))["nodes"]
cn_old = {x["pubkey"]: x.get("clientId") for x in json.load(open("/home/moiz/sniper-data/stakepaths/clusternodes.json"))["result"]}
geo = {x["pk"]: x for x in json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]}
LEAD = {int(k): v for k, v in json.load(open(os.path.join(W, "rpc/leaders.json"))).items()}
PROS = set(json.load(open("/home/moiz/sniper/ops/race/pros.json")))


def client_of(pk):
    c = (cn_now.get(pk) or {}).get("clientId") or (geo.get(pk) or {}).get("client") or cn_old.get(pk)
    return c or "?"


def client_group(c):
    if c in ("AgaveBam", "FireBAM"): return "BAM"
    if c in ("HarmonicAgave", "HarmonicFiredancer"): return "Harmonic"
    if c == "JitoLabs": return "Jito-Solana"
    if c in ("Firedancer", "Frankendancer"): return "Firedancer"
    if c == "Agave": return "Agave"
    if c in ("Rakurai", "Raiku"): return c
    return "other"


def region_of(pk):
    g = geo.get(pk)
    if not g or not g.get("cc"): return "?"
    cc = g["cc"]
    if cc == "DE": return "Frankfurt/DE"
    if cc in ("NL", "GB", "LT", "FR", "IE", "SE", "FI", "PL", "CH", "AT", "CZ", "ES", "IT"): return "EU-other"
    if cc in ("US", "CA"): return "N-America"
    if cc in ("JP", "SG", "HK", "KR"): return "Asia"
    return "other"


# ---------------- launches + enrich ----------------
launch = {}            # (R, mint) -> L
for R, rd in RUNS.items():
    with open(os.path.join(rd, "launches.jsonl")) as f:
        for line in f:
            try: L = json.loads(line)
            except Exception: continue
            if L.get("mint") and L.get("slot") is not None and L.get("err") is None:
                launch[(R, L["mint"])] = L
jc_sigs = {}; je_bundle = {}
for R, rd in RUNS.items():
    with open(os.path.join(rd, "enrich.jsonl")) as f:
        for line in f:
            try: e = json.loads(line)
            except Exception: continue
            jc = e.get("jito_create")
            if isinstance(jc, dict) and jc.get("txs"):
                jc_sigs[(R, e["mint"])] = set(jc["txs"])
            for x in e.get("jito_early") or []:
                b = x.get("bundle")
                if isinstance(b, dict) and b.get("bundle_id"):
                    je_bundle[x["sig"]] = (b["bundle_id"], len(b.get("txs") or []), b.get("tip"))
                elif b is None:
                    je_bundle.setdefault(x["sig"], None)
print("launches", len(launch), "jito create bundles", len(jc_sigs), "early lookups", len(je_bundle), flush=True)

# ---------------- slot max index ----------------
smax = {"R1": {}, "R2": {}}
for p in glob.glob(os.path.join(W, "scan/slots/*.json")):
    R = TAG2R[os.path.basename(p).split("__")[0]]
    for s, (mx, n) in json.load(open(p)).items():
        s = int(s)
        if mx > smax[R].get(s, -1): smax[R][s] = mx

# ---------------- scan records grouped by launch ----------------
recs = collections.defaultdict(dict)    # (R, mint) -> sig -> rec
for p in sorted(glob.glob(os.path.join(W, "scan/recs/*.jsonl.gz"))):
    R = TAG2R[os.path.basename(p).split("__")[0]]
    for line in gzip.open(p, "rt"):
        r = json.loads(line)
        if r["d"] > DMAX: continue
        k = (R, r["m"])
        if k not in launch: continue
        if r["sig"] in recs[k]: continue
        r["sg"] = [I(x) for x in r["sg"]]
        r["ixn"] = [I(x) for x in r["ixn"]]
        r["progs"] = [I(x) for x in r["progs"]]
        for e in r["ev"]: e[1] = I(e[1])
        del r["run"]; del r["m"]
        recs[k][r["sig"]] = r
print("launches with records", len(recs), "records", sum(len(v) for v in recs.values()), flush=True)


def ordered(k):
    return sorted(recs[k].values(), key=lambda r: (r["s"], r["i"]))


def adjacency_run(L, rs):
    S, cidx = L["slot"], L["idx"]
    by_idx = {r["i"]: r for r in rs if r["s"] == S}
    run = []; j = cidx + 1
    while j in by_idx:
        r = by_idx[j]
        if r["err"] is None and any(e[0] == 1 for e in r["ev"]):
            run.append(r); j += 1
        else:
            break
    return run


def base_creator_set(L, rs):
    cs = {L.get("creator"), L.get("user"), L.get("payer")}
    for r in rs:
        if r["sig"] == L["sig"]:
            cs |= set(r["sg"])
    cs.discard(None)
    return cs


# ---------------- pass 1: data-driven multi-launch sniper set ----------------
w_nonadj = collections.defaultdict(set); w_adj = collections.Counter(); w_creators = collections.defaultdict(set)
for k, L in launch.items():
    if k not in recs: continue
    rs = ordered(k)
    cs = base_creator_set(L, rs)
    run = adjacency_run(L, rs)
    run_sigs = {r["sig"] for r in run}
    for r in rs:
        if r["err"] is not None or r["sig"] == L["sig"]: continue
        evb = [e for e in r["ev"] if e[0] == 1 and e[1] not in cs]
        if not evb or r["sg"][0] in cs: continue
        w = r["sg"][0]
        if r["sig"] in run_sigs: w_adj[w] += 1
        else:
            w_nonadj[w].add(k); w_creators[w].add(L.get("creator"))
SNIPERS = {w for w, ks in w_nonadj.items() if len(ks) >= 10 and len(w_creators[w]) >= 5 and w_adj[w] <= 0.5 * (len(ks) + w_adj[w])}
BREAKERS = SNIPERS | PROS
print("data-driven sniper wallets", len(SNIPERS), "pros", len(PROS), flush=True)

# ---------------- engine arrival timelines (obs) ----------------
obs = {}
for p in SHADOW:
    with open(p) as f:
        for line in f:
            try: o = json.loads(line)
            except Exception: continue
            if o.get("type") != "obs" or o.get("mint") in obs: continue
            outs = []
            if o.get("outs") and o["outs"] != "-":
                for part in o["outs"].split(","):
                    try:
                        ms, sol, isb, w6 = part.split(":")
                        outs.append([float(ms), float(sol), int(isb), w6])
                    except ValueError:
                        pass
            obs[o["mint"]] = outs
print("obs timelines", len(obs), flush=True)

# ---------------- pass 2 ----------------
fb = gzip.open(os.path.join(W, "rows_buys.jsonl.gz"), "wt", compresslevel=3)
ff = gzip.open(os.path.join(W, "rows_fail.jsonl.gz"), "wt", compresslevel=3)
fl = gzip.open(os.path.join(W, "launches.jsonl.gz"), "wt", compresslevel=3)
stat = collections.Counter()
for k, L in launch.items():
    R, mint = k
    S, cidx = L["slot"], L["idx"]
    rs = ordered(k) if k in recs else []
    cs = base_creator_set(L, rs)
    run = adjacency_run(L, rs)
    jc = jc_sigs.get(k)
    glued = []
    if jc:
        glued = [r for r in run if r["sig"] in jc]
        stat["glued_by_jito_bundle"] += 1
    else:
        for r in run:
            if r["sg"][0] in BREAKERS or any(e[1] in BREAKERS for e in r["ev"] if e[0] == 1): break
            glued.append(r)
    gsigs = {r["sig"] for r in glued}
    run_sigs = {r["sig"] for r in run}
    for r in glued:
        cs.add(r["sg"][0]); cs |= {e[1] for e in r["ev"] if e[0] == 1}
    quote_sol = any(e[4] > 0 for r in rs for e in r["ev"])   # SOL-quoted curve: TradeEvent virtual_sol_reserves > 0 (same rule as select/b_launch.py)
    lead_S = LEAD.get(S); cl_S = client_of(lead_S) if lead_S else "?"
    mx = smax[R].get(S, -1)
    cfrac = (cidx / mx) if mx > 0 and cidx <= mx else None
    ob = obs.get(mint) if R == "R2" else None
    # wallet-ordered obs entries for matching
    obs_by_w = collections.defaultdict(list)
    if ob:
        for e in ob: obs_by_w[e[3]].append(e)
    used = set()
    pos = 0; wallets_seen = set(); n_fail = n_other = 0
    first_buy = None
    for r in rs:
        if r["sig"] == L["sig"] or r["sig"] in gsigs: continue
        payer = r["sg"][0] if r["sg"] else None
        if payer in cs: continue
        evb = [e for e in r["ev"] if e[0] == 1 and e[1] not in cs]
        ns = r["ns"] or 1
        fee = r["fee"] or 0
        v1 = r["cup"] is None and r["cul"] is None and fee > BASE_FEE * ns
        lead = LEAD.get(r["s"]); cl = client_of(lead) if lead else "?"
        common = dict(R=R, mint=mint, S=S, d=r["s"] - S, s=r["s"], i=r["i"], sig=r["sig"], payer=payer, ns=ns, fee=fee,
                      prio=max(0, fee - BASE_FEE * ns), cup=r["cup"], cul=r["cul"], cu=r["cu"], v1=v1, cfrac=cfrac,
                      lead=lead, client=cl, cgroup=client_group(cl), region=region_of(lead) if lead else "?",
                      lead_S=lead_S, cgroup_S=client_group(cl_S), adj=r["sig"] in run_sigs, nm=r["nm"], qsol=quote_sol)
        if r["err"] is None and evb:
            sol = sum(e[2] for e in evb)
            users = sorted({e[1] for e in evb})
            tips = r["tips"]
            svcs = sorted({t[0] for t in tips})
            tip_tot = sum(t[2] for t in tips)
            path = "none" if not svcs else (svcs[0] if len(svcs) == 1 else "multi:" + "+".join(svcs))
            jb = je_bundle.get(r["sig"], "na")
            # arrival ms match (engine obs): same wallet prefix, buy flag, closest sol among unused entries
            ms = None; mq = None; osol = None
            if ob is not None:
                cands = []
                for w6 in {payer[:6]} | {u[:6] for u in users}:
                    for e in obs_by_w.get(w6, []):
                        if id(e) in used or e[2] != 1: continue
                        cands.append(e)
                if cands:
                    solv = sol / 1e9
                    def score(e):
                        ratio = (e[1] / solv) if solv > 0 else 99
                        ok = 0.97 <= ratio <= 1.6 or abs(e[1] - solv) <= 0.0015
                        return (0 if ok else 1, e[0])
                    best = min(cands, key=score)
                    used.add(id(best)); ms = best[0]; osol = best[1]; mq = "sol_ok" if score(best)[0] == 0 else "sol_off"
            row = dict(common, kind="buy", sol=sol, users=users, tips=tips, svcs=svcs, path=path, tip=tip_tot, pos=pos,
                       wrank=len(wallets_seen), new_wallet=payer not in wallets_seen, jito_bundle=(None if jb == "na" else (jb is not None)),
                       ms=ms, mq=mq, osol=osol, progs=r["progs"], ixn=r["ixn"][:6])
            if first_buy is None: first_buy = row
            fb.write(json.dumps(row, separators=(",", ":")) + "\n"); stat["buy_rows"] += 1
            pos += 1; wallets_seen.add(payer)
        elif r["err"] is not None:
            buyix = any(x.startswith("Buy") or x == "PumpBuy" for x in r["ixn"])
            row = dict(common, kind="fail", err=r["err"], buyix=buyix, noix=not r["ixn"], pos_after=pos, ixn=r["ixn"][:6], progs=r["progs"])
            ff.write(json.dumps(row, separators=(",", ":")) + "\n"); stat["fail_rows"] += 1; n_fail += 1
        else:
            n_other += 1
    fl.write(json.dumps(dict(R=R, mint=mint, S=S, idx=cidx, name=L.get("name"), creator=L.get("creator"), cfrac=cfrac, smax=mx,
                             lead_S=lead_S, client_S=cl_S, cgroup_S=client_group(cl_S), n_glued=len(glued), n_run=len(run),
                             jito_create=bool(jc), qsol=quote_sol, n_buys=pos, n_fail=n_fail, n_other=n_other, has_obs=ob is not None,
                             first=(None if not first_buy else dict(path=first_buy["path"], d=first_buy["d"], payer=first_buy["payer"], ms=first_buy["ms"], sig=first_buy["sig"]))),
                        separators=(",", ":")) + "\n")
    stat["launches"] += 1
fb.close(); ff.close(); fl.close()
json.dump(dict(stat=stat, snipers=sorted(SNIPERS), n_pros=len(PROS)), open(os.path.join(W, "build_meta.json"), "w"))
print(dict(stat), flush=True)
