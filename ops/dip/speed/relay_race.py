#!/usr/bin/env python3
# Relay race on dip triggers (owner 10-24 19:55 PKT, a screenshot claiming "winners on Jito leaders use soyas": check it).
# For every candidate dump of the 10-23/24 recording (sel/dayexit_r3 + _r7 rows: the big sells the IMIT1 envelope sees),
# list every buy of that mint landing after the dump in the dump's slot S and S+1 (raw collector chunks), in block order:
# signer, relay (tip accounts -> ops/agents/tipmap.json), priority, ok / err. Leader of S from the epoch-1066 schedule; its
# kind from our live fire events (exact client) else data/validators-meta.json (jito / bam flags, 10-07 snapshot).
# Out: per leader kind, the relay of the FIRST buyer after the dump; per relay, how often it is among the first 3; the top
# dip bots' relay use per leader kind and their rank. -> relay_race.json + printed tables.  READ-ONLY, local data only.
import json, gzip, os, collections, statistics
from multiprocessing import Pool
TX = "/home/moiz/sniper-data/collect/run_20261023_1426/txs"
SEL = "/home/moiz/sniper/ops/overnight/sel"; SP = "/home/moiz/sniper/ops/dip/speed"
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
sc = json.load(open(f"{SP}/leaders/schedule_cur.json"))
def lead(s):
    i = s - sc["start"]; return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
KIND = {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "bam", "HarmonicAgave": "harmonic", "HarmonicFiredancer": "harmonic",
        "Firedancer": "firedancer", "Frankendancer": "firedancer", "Agave": "agave"}
kind = {v: ("bam" if f.get("bam") else "jito" if f.get("jito") else "agave/other")
        for v, f in json.load(open("/home/moiz/sniper/data/validators-meta.json"))["validators"].items()}
for fn in os.listdir(SP):
    if fn.startswith("dip_") and fn.endswith(".jsonl"):
        for l in open(f"{SP}/{fn}"):
            if '"fire"' in l:
                e = json.loads(l)
                if e.get("ev") == "fire" and e.get("leader") and e.get("client"): kind[e["leader"]] = KIND.get(e["client"], e["client"])
EV = {}
for w in ("r3", "r7"):
    for r in json.load(open(f"{SEL}/dayexit_{w}.json"))["rows"]: EV[(r["m"], r["s"])] = dict(m=r["m"], s=r["s"], t=r["t"], sell=r["sell"], dev=r.get("dev"))
chunks = sorted(int(f.split("_")[1].split(".")[0]) for f in os.listdir(TX))
byc = collections.defaultdict(list)
for k, e in EV.items():
    for c in chunks:
        if c - 300 <= e["t"] <= c + 330: byc[c].append(k)
def relay(r):
    t = r.get("tips") or []
    if isinstance(t, str): t = json.loads(t.replace("'", '"'))
    n = sorted({TIP.get(a, "other_tip") for a, _ in t}); return "+".join(n) if n else "no tip"
def work(c):
    keys = byc[c]; mints = {}
    for k in keys: mints.setdefault(k[0], []).append(k[1])
    out = collections.defaultdict(list)
    try:
        for l in gzip.open(f"{TX}/txs_{c}.jsonl.gz", "rt"):
            hit = [m for m in mints if m in l]
            if not hit: continue
            r = json.loads(l); s = int(r["s"]); ix = " ".join(r.get("ixn") or [])
            side = "B" if "Buy" in ix else ("S" if "Sell" in ix else None)
            if side is None: continue
            who = (r.get("signers") or ["?"])[0]
            sd = dict((a, int(d)) for a, d in (r.get("sd") or []))
            rec = dict(sig=r["sig"], s=s, i=int(r["i"]), who=who, side=side, ok=(not r.get("err") or r.get("err") == "None"),
                       rel=relay(r), cup=int(r.get("cup") or 0), sol=abs(sd.get(who, 0)) / 1e9)
            for m in hit:
                for S in mints[m]:
                    if s in (S, S + 1): out[(m, S)].append(rec)
    except (EOFError, OSError):
        pass
    return dict(out)
if __name__ == "__main__":
    acc = collections.defaultdict(dict)
    with Pool(8) as p:
        for part in p.imap_unordered(work, sorted(byc)):
            for k, recs in part.items():
                for r in recs: acc[k][r["sig"]] = r
    races = []
    for k, d in acc.items():
        e = EV[k]; rows = sorted(d.values(), key=lambda r: (r["s"], r["i"]))
        sells = [r for r in rows if r["s"] == e["s"] and r["side"] == "S" and r["ok"]]
        if not sells: continue
        dump = min(sells, key=lambda r: abs(r["sol"] - e["sell"]))
        if abs(dump["sol"] - e["sell"]) > 0.15 * e["sell"]: continue
        k0 = rows.index(dump); buys = [r for r in rows[k0 + 1:] if r["side"] == "B"]
        okb = [r for r in buys if r["ok"]]
        ld = lead(e["s"])
        races.append(dict(m=e["m"], s=e["s"], dev=e["dev"], leader=ld, kind=kind.get(ld, "unknown"), dump_i=dump["i"],
                          buys=[dict(who=r["who"], rel=r["rel"], s1=r["s"] - e["s"], di=r["i"] - dump["i"] if r["s"] == e["s"] else None,
                                     ok=r["ok"], cup=r["cup"], sol=round(r["sol"], 3)) for r in buys]))
    json.dump(races, open(f"{SP}/relay_race.json", "w"))
    print(f"races {len(races)} (of {len(EV)} dumps); by leader kind:", dict(collections.Counter(r["kind"] for r in races)))
    print("\n1) FIRST successful buy after the dump: its relay, per leader kind (share)")
    for kd in ("jito", "bam", "harmonic", "firedancer", "agave/other", "agave", "unknown"):
        R = [r for r in races if r["kind"] == kd]; F = collections.Counter()
        for r in R:
            ok = [b for b in r["buys"] if b["ok"]]
            if ok: F[ok[0]["rel"]] += 1
        n = sum(F.values())
        if n: print(f"  {kd:12s} n={n:3d}: " + ", ".join(f"{k} {100 * v / n:.0f}%" for k, v in F.most_common(7)))
    print("\n2) per relay: buys after dumps, share of them that were among the first 3 successful buys (jito leaders | others)")
    for kd in ("jito", "rest"):
        T = collections.Counter(); TOP = collections.Counter()
        for r in races:
            if (r["kind"] == "jito") != (kd == "jito"): continue
            ok = [b for b in r["buys"] if b["ok"]]
            for j, b in enumerate(ok): T[b["rel"]] += 1; TOP[b["rel"]] += j < 3
        print(f"  {kd}: " + "; ".join(f"{k} {TOP[k]}/{v} ({100 * TOP[k] / v:.0f}%)" for k, v in T.most_common(9)))
    print("\n3) the bots most often in the first 3 buys: relay use per leader kind, median rank (1 = first)")
    W = collections.Counter()
    for r in races:
        for j, b in enumerate([b for b in r["buys"] if b["ok"]][:3]): W[b["who"]] += 1
    for who, n in W.most_common(12):
        per = collections.defaultdict(collections.Counter); rk = []
        for r in races:
            ok = [b for b in r["buys"] if b["ok"]]
            for j, b in enumerate(ok):
                if b["who"] == who: per[r["kind"]][b["rel"]] += 1; rk.append(j + 1)
        tag = " (US)" if who in US else ""
        print(f"  {who[:8]}{tag}: top-3 {n}x, median rank {statistics.median(rk):.0f}; " +
              " | ".join(f"{kd}: " + ", ".join(f"{k} {v}" for k, v in c.most_common(3)) for kd, c in per.items()))
    print("\n4) soyas vs helius on jito leaders: rank of their successful buys")
    for rel in ("soyas", "helius", "no tip", "nozomi", "astralane", "jito"):
        rk = [j + 1 for r in races if r["kind"] == "jito" for j, b in enumerate([b for b in r["buys"] if b["ok"]]) if b["rel"] == rel]
        if rk: print(f"  {rel:9s} n={len(rk):4d}  median rank {statistics.median(rk):.0f}  first-place {sum(1 for x in rk if x == 1)}")
