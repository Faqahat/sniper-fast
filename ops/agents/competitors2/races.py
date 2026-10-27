#!/usr/bin/env python3
# competitors2/races.py -- READ-ONLY. Merge the per-chunk rows (extract.py) into one race record per dump:
# the dump tx, every tx on that mint after it (rest of slot S, S+1, S+2) and before it (S-2 .. S), the leader of S (epoch
# 1066 / 1067 schedules) with its client kind and RTT from FRA / AMS, and our fire (if any) with its outcome.
# Out: /home/moiz/sniper-data/competitors2/races.jsonl.gz
import json, os, glob, gzip, collections, sys
ROWS = "/home/moiz/sniper-data/competitors2/rows"; RUNS = "/home/moiz/sniper-data/competitors2/runs"
OUT = "/home/moiz/sniper-data/competitors2/races.jsonl.gz"
LD = "/home/moiz/sniper/ops/dip/speed/leaders"
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "AMS"}
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"}
KIND = {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "bam", "HarmonicAgave": "harmonic", "HarmonicFiredancer": "harmonic",
        "Firedancer": "fd", "Frankendancer": "fd", "Agave": "agave", "Rakurai": "rakurai"}

def schedules():
    S = []
    for f in (f"{LD}/schedule_cur.json", "/home/moiz/sniper-data/competitors2/schedule_1067.json"):
        d = json.load(open(f)); S.append((d["start"], d["ids"], d["slot_leader"]))
    def lead(s):
        for st, ids, sl in S:
            if 0 <= s - st < len(sl): return ids[sl[s - st]]
        return None
    return lead

def leader_info():
    fra = json.load(open(f"{LD}/leader_rtt_new.json"))["leaders"]
    ams = json.load(open("/home/moiz/sniper/ops/region/leader_rtt_ams.json"))["leaders"]
    geo = {r["pk"]: r for r in json.load(open(f"{LD}/leader_geo.json"))["rows"]}
    nf = set(open("/home/moiz/sniper/ops/region/near_leaders_fra.txt").read().split())
    na = set(open("/home/moiz/sniper/ops/region/near_leaders_ams.txt").read().split())
    client = {}
    for f in glob.glob(f"{RUNS}/*.jsonl"):
        for l in open(f):
            if '"fire"' in l:
                e = json.loads(l)
                if e.get("ev") == "fire" and e.get("client"): client[e["leader"]] = e["client"]
    def info(pk):
        c = client.get(pk) or (fra.get(pk) or {}).get("client") or (ams.get(pk) or {}).get("client") or (geo.get(pk) or {}).get("client") or "?"
        g = geo.get(pk) or {}
        return dict(client=c, kind=KIND.get(c, "other"), rtt_fra=(fra.get(pk) or {}).get("rtt"), rtt_ams=(ams.get(pk) or {}).get("rtt"),
                    city=g.get("city"), cc=g.get("cc"), near_fra=pk in nf, near_ams=pk in na)
    return info

def load_runs():
    D = {}; FIRES = collections.defaultdict(list)
    for f in sorted(glob.glob(f"{RUNS}/*.jsonl")):
        run = os.path.basename(f)[:-6]; region = "AMS" if "ams" in run else "FRA"
        ev = [json.loads(l) for l in open(f)]
        land = {e["sig"]: e for e in ev if e["ev"] == "buy_land"}
        tim = {e.get("buy_sig"): e for e in ev if e["ev"] == "timing"}
        tape = collections.defaultdict(list)
        for e in ev:
            if e["ev"] == "tape": tape[e["mint"]].append([e["sig"], e["t"], e.get("user"), e.get("buy"), e.get("slot"), e.get("idx")])
        for e in ev:
            if e["ev"] == "dump":
                D.setdefault(e["sig"], dict(sig=e["sig"], m=e["mint"], s=e["slot"], t=e["t"], sell=e["sell"], score=e.get("score"),
                                            pas=e.get("pass"), age=e.get("age"), dev=e.get("dev"), drop=e.get("drop_pct")))
            elif e["ev"] == "fire":
                T = tim.get(e["buy_sig"], {}); L = land.get(e["buy_sig"])
                FIRES[e["dump_sig"]].append(dict(run=run, region=region, buy_sig=e["buy_sig"], fill=bool(L), leader_fire=e["leader"],
                    client_fire=e["client"], route=e["route"], spend=e["spend"], min_out=e["min_out"], tips=e.get("tips"),
                    t_dump_rx=e["t_dump_rx"], t_fire=e["t_fire"], decision_us=e.get("decision_us"), writes=e.get("writes"),
                    f2s=T.get("fire_to_seen_ms"), buy_first_rx=T.get("buy_first_rx"), dump_first_rx=T.get("dump_first_rx"),
                    exec_lag=T.get("exec_lag_ms"), reaction=T.get("reaction_ms"),
                    tape=[x for x in tape[e["mint"]] if abs(x[1] - e["t_dump_rx"]) < 3e9]))
                D.setdefault(e["dump_sig"], dict(sig=e["dump_sig"], m=e["mint"], s=e["slot"], t=e["t_dump_rx"], sell=None, score=None,
                                                 pas=True, age=None, dev=e.get("dev"), drop=None))
    return D, FIRES

def slim(r):
    own = [p for p in r["progs"] if p not in STD]
    tr = r["tr"][-1] if r["tr"] else None
    return dict(s=r["s"], i=r["i"], sig=r["sig"], w=r["w"], ns=r["ns"], side=r["side"], err=r["err"], cup=r["cup"], cul=r["cul"],
                cu=r["cu"], fee=r["fee"], tips=r["tips"], own=own, ixn=r["ixn"][:8], tr=tr, ntr=len(r["tr"]), sdw=r["sdw"])

if __name__ == "__main__":
    lead = schedules(); info = leader_info(); D, FIRES = load_runs()
    bym = collections.defaultdict(list)
    for d in D.values(): bym[d["m"]].append(d)
    # 16 hash partitions of mints to bound memory
    NP = 4; nrace = 0; miss = 0
    with gzip.open(OUT + ".tmp", "wt", compresslevel=3) as out:
        for part in range(NP):
            rows = collections.defaultdict(dict)
            for f in sorted(glob.glob(f"{ROWS}/*.jsonl.gz")):
                for l in gzip.open(f, "rt"):
                    m = l[6:l.index('"', 6)]
                    if hash(m) % NP != part or m not in bym: continue
                    o = json.loads(l)
                    for r in o["rows"]: rows[m][r["sig"]] = r
            for m, dl in bym.items():
                if hash(m) % NP != part: continue
                R = sorted(rows.get(m, {}).values(), key=lambda r: (r["s"], r["i"]))
                pos = {r["sig"]: k for k, r in enumerate(R)}
                for d in dl:
                    k = pos.get(d["sig"])
                    if k is None: miss += 1; continue
                    S = d["s"]; dr = R[k]
                    if dr["s"] != S: S = dr["s"]
                    ld = lead(S); li = info(ld) if ld else {}
                    after = [slim(r) for r in R[k + 1:] if r["s"] <= S + 2]
                    before = [slim(r) for r in R[:k] if r["s"] >= S - 2]
                    rec = dict(d, s=S, dump=slim(dr), leader=ld, li=li, after=after, before=before, fires=FIRES.get(d["sig"], []))
                    out.write(json.dumps(rec, separators=(",", ":")) + "\n"); nrace += 1
            print(f"part {part}: races so far {nrace}, dump tx not found {miss}", flush=True)
    os.rename(OUT + ".tmp", OUT)
    print("done", nrace, "missing", miss)
