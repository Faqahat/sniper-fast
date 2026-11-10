#!/usr/bin/env python3
"""APEX-FEES step 2: per-tx table for the create slot cs and cs+1 of every standard launch, with cost decomposition,
role (create / bundle / sniper / fail), rank among non-bundle create-slot buyers, leader + client, Jito-bundle info.
Out: /home/it/sniper-data/apex2/fees/T.pkl  (list of dicts, one per tx) + L.pkl (per launch)
Cost fields (lamports): base = 5000*nsig, prio = fee - base, tips = sum of tip transfers (landed txs only: failed tips revert),
  cupe = micro-lamports per CU: recorded cup if known, else prio*1e6/cul if cul known, else prio*1e6/cu (flag cupsrc)."""
import json, glob, gzip, os, pickle, collections, sys
FIELDS = ("run mint pick unseen wl cs ci so i rel role rank landed err signer user buyk sol nsig fee prio tips tipsa ntip lanes "
          "tipacc cupe cupsrc cup cul cu xp nb sig jb client leader bt ntr").split()

D = "/home/it/sniper-data/apex2/fees"; C = "/data/tapes/collect"; TAB = "/home/it/sniper-data/apex2/tab"
TIPMAP = json.load(open("/home/it/sniper/ops/rec/tipmap.json"))

def lane(a):
    v = TIPMAP.get(a)
    if v: return v
    if a.startswith("noz"): return "nozomi"
    return "other"

def leaders():
    L = {}
    for f in ("/home/it/sniper-data/launchsel/leaders.json", D + "/leaders_extra.json"):
        for k, v in json.load(open(f)).items():
            if v: L[int(k)] = v
    nodes = {n["pubkey"]: n.get("clientId") or "?" for n in json.load(open("/home/it/sniper-data/launchsel/nodes.json"))}
    for n in json.load(open(D + "/nodes_now.json")): nodes[n["pubkey"]] = n.get("clientId") or "?"
    def get(s):
        b = s - (s - 461690000) % 5000; v = L.get(b)
        if not v or s - b >= len(v): return None, "?"
        ld = v[s - b]; return ld, nodes.get(ld, "?")
    return get

def main():
    getl = leaders()
    picks = json.load(open(D + "/picks.json"))
    wl = {c["creator"] for c in json.load(open("/home/it/sniper-data/apex2/watchlist.json"))["creators"]}
    T = []; LA = []
    for rd in sorted(glob.glob(D + "/scan/run_*")):
        run = os.path.basename(rd)
        cr = json.load(open(f"{TAB}/{run}/creates.json"))
        enr = {}
        try:
            for l in open(f"{C}/{run}/enrich.jsonl"):
                try: j = json.loads(l)
                except Exception: continue
                jc = j.get("jito_create"); bs = set()
                if isinstance(jc, dict) and jc.get("txs"): bs = set(jc["txs"])
                early = {}
                for e in j.get("jito_early") or []:
                    b = e.get("bundle")
                    if isinstance(b, dict): early[e["sig"]] = (b.get("bundle_id"), b.get("tip"), b.get("validator"), len(b.get("txs") or []))
                    elif b is None: early[e["sig"]] = None
                enr[j["mint"]] = (bs, early, jc if isinstance(jc, dict) else None)
        except FileNotFoundError: pass
        rows = collections.defaultdict(list)
        for f in sorted(glob.glob(rd + "/*.jsonl.gz")):
            for l in gzip.open(f, "rt"):
                r = json.loads(l); rows[r["mint"]].append(r)
        for mint, rs in rows.items():
            c = cr.get(mint)
            if not c or not c.get("std"): continue
            rs.sort(key=lambda r: (r["s"], r["i"]))
            seen = set(); rr = []
            for r in rs:
                if r["sig"] in seen: continue
                seen.add(r["sig"]); rr.append(r)
            cs, ci = int(c["slot"]), int(c["idx"])
            ld0, cl0 = getl(cs); ld1, cl1 = getl(cs + 1)
            bset, early, jc = enr.get(mint, (set(), {}, None))
            pk = picks.get(mint)
            # bundle: contiguous landed buys right after the create (same rule as s1_sim.py)
            land_cs = {r["i"]: r for r in rr if r["s"] == cs and r["err"] is None}
            last = ci; bund = set()
            while (last + 1) in land_cs and land_cs[last + 1]["buy"]:
                last += 1; bund.add(last)
            rank = 0; users = set(); first = None
            for r in rr:
                landed = r["err"] is None
                base = 5000 * r["nsig"]; fee = int(r["fee"] or 0); prio = max(fee - base, 0)
                tips = sum(int(t[1]) for t in r["tips"]) if landed else 0
                lanes = sorted({lane(t[0]) for t in r["tips"]})
                if r.get("cup") is not None: cupe, src = r["cup"], "cup"
                elif r.get("cul"): cupe, src = prio * 1e6 / r["cul"], "cul"
                elif r.get("cu"): cupe, src = prio * 1e6 / max(r["cu"], 1), "cu"
                else: cupe, src = 0.0, "-"
                if r["s"] == cs and r["i"] == ci: role = "create"
                elif not landed: role = "fail"
                elif r["s"] == cs and r["i"] in bund: role = "bundle"
                elif r["buy"]: role = "buy"
                elif r["ssol"]: role = "sell"
                else: role = "noop"          # landed, touched the mint, no trade (bot guard no-op / late attempt)
                rk = None
                if role == "buy" and r["s"] == cs:
                    if r["user"] not in users:
                        rk = rank; rank += 1; users.add(r["user"])
                        if first is None: first = r["user"]
                jb = None
                if r["sig"] in bset: jb = "create_bundle"
                elif r["sig"] in early: jb = "bundle" if early[r["sig"]] else "no_bundle"
                I = sys.intern
                T.append((I(run), I(mint), pk is not None, bool(pk and pk[2]), c.get("creator") in wl, cs, ci, r["s"] - cs, r["i"],
                          r["i"] - ci, I(role), rk, landed, (I(r["err"]) if r["err"] else None), I(r["signer"]), I(r["user"]),
                          r["ixk"] & 7, r["sol"], r["nsig"], fee, prio, tips, sum(int(t[1]) for t in r["tips"]), len(r["tips"]),
                          I("+".join(lanes)), tuple(I(t[0]) for t in r["tips"]), cupe, I(src), r.get("cup"), r.get("cul"), r.get("cu"),
                          I("+".join(r["xp"])), I("+".join(r["nb"])), r["sig"], jb, I(cl0 if r["s"] == cs else cl1),
                          I((ld0 if r["s"] == cs else ld1) or "?"), r["bt"], int(r.get("ntr") or 0)))
            LA.append(dict(run=run, mint=mint, creator=c.get("creator"), cs=cs, ci=ci, pick=(pk is not None), unseen=bool(pk and pk[2]),
                           wl=(c.get("creator") in wl), client=cl0, leader=ld0, client1=cl1, nbund=len(bund), first=first,
                           nsnipe=rank, jc_tip=(jc or {}).get("tip"), jc_n=len((jc or {}).get("txs") or []), jc_val=(jc or {}).get("validator")))
        print(run, len(T), len(LA), flush=True)
    pickle.dump(dict(fields=FIELDS, rows=T), open(D + "/T.pkl", "wb")); pickle.dump(LA, open(D + "/L.pkl", "wb"))

if __name__ == "__main__":
    main()
