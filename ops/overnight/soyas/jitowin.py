#!/usr/bin/env python3
# HOW DO THE WINNERS ON JITO LEADERS GET THERE SO FAST? (read-only, R3 collector tapes + raw txs + RPC leader schedule / gossip)
# Race = a >= 1 SOL sell on a token < 60 s old; winner = first buy after it by another wallet (within 400 ms). Grouped by the
# client of the slot leader the winner landed in. Per winner: delay after the dump (block-position ms), same slot or not, tip
# services, CU price / limit, programs. Then per leader city (where are they?) and per top bot (one region or many?). Ours too.
import os, sys, json, gzip, glob, time, urllib.request, collections, statistics
from multiprocessing import Pool
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=120)).get("result")
        except Exception: time.sleep(1 + i)
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "OURS-FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "OURS-AMS"}
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * 212.0
L = rp.load_launches(); byb = collections.defaultdict(set)
for m, c in L.items():
    if c["run"] == "R3": byb[("R3", rp.bucket(m))].add(m)
def races(key):
    out = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        S0 = L[m]["slot"]
        for k, d in enumerate(tr):
            if d["buy"] or d["sol"] < 1e9 or (d["s"] - S0) * 0.212 > 60: continue
            ours = {}
            win = None
            for t in tr[k + 1:]:
                dl = arr(t) - arr(d)
                if dl > 400: break
                if t["buy"] and t["user"] != d["user"]:
                    if win is None: win = (t, dl)
                    if t["user"] in OURS and t["user"] not in ours: ours[t["user"]] = (t["s"], t["sig"], dl)
            if win: out.append(dict(dump_s=d["s"], s=win[0]["s"], i=win[0]["i"], sig=win[0]["sig"], user=win[0]["user"], dl=win[1], same=win[0]["s"] == d["s"], ours=ours))
    return out
def raw(f, want):
    o = {}
    try:
        for line in gzip.open(f, "rt"):
            if '"sig"' not in line: continue
            j = line.find('"sig": "') if '"sig": "' in line else line.find('"sig":"')
            r = json.loads(line)
            if r["sig"] in want: o[r["sig"]] = dict(cup=r.get("cup"), cul=r.get("cul"), cu=r.get("cu"), tips=[(TIP.get(a, "other"), v) for a, v in (r.get("tips") or [])], progs=r.get("progs") or [])
    except (EOFError, OSError): pass
    return o
WANT = None
def rawg(f): return raw(f, WANT)
if __name__ == "__main__":
    R = []
    with Pool(8) as p:
        for o in p.imap_unordered(races, sorted(byb), chunksize=4): R += o
    print(f"races (>=1 SOL sell, token < 60 s, someone bought within 400 ms): {len(R)}", flush=True)
    WANT = {r["sig"] for r in R}
    files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261023_1426/txs/*.jsonl.gz"))
    RAW = {}
    with Pool(8) as p:
        for o in p.imap_unordered(rawg, files): RAW.update(o)
    es = rpc("getEpochSchedule", []); lead = {}
    slots = sorted({r["s"] for r in R})
    for s in slots[::15000] + [slots[-1]]:
        ep = (s - es["firstNormalSlot"]) // es["slotsPerEpoch"]; first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]
        if first not in lead: lead[first] = {first + i: k for k, v in (rpc("getLeaderSchedule", [s]) or {}).items() for i in v}
    LD = {}
    for v in lead.values(): LD.update(v)
    nodes = {n["pubkey"]: n for n in rpc("getClusterNodes", [])}
    def cl(i):
        c = (nodes.get(i or "") or {}).get("clientId") or ""
        return "BAM" if "Bam" in c or "BAM" in c else ("Harmonic" if "Harmonic" in c else ("Jito" if c in ("JitoLabs", "Rakurai") else ("Firedancer" if "dancer" in c.lower() else (c or "?"))))
    ips = {}
    for r in R:
        n = nodes.get(LD.get(r["s"]) or "") or {}; a = n.get("tpu") or n.get("gossip") or ""
        if a: ips[LD[r["s"]]] = a.rsplit(":", 1)[0]
    GEO = {}; u = sorted(set(ips.values()))
    for k in range(0, len(u), 100):
        for g in json.load(urllib.request.urlopen(urllib.request.Request("http://ip-api.com/batch?fields=query,city,countryCode,org", data=json.dumps(u[k:k + 100]).encode(), headers={"content-type": "application/json"}), timeout=60)): GEO[g["query"]] = g
        time.sleep(4)
    METRO = {"Frankfurt am Main": "Frankfurt", "Fechenheim": "Frankfurt", "Offenbach": "Frankfurt", "Emmen": "Amsterdam", "Haarlem": "Amsterdam", "Schiphol-Rijk": "Amsterdam", "Secaucus": "New York", "Newark": "New York", "Piscataway": "New York", "Elk Grove Village": "Chicago",
             "Slough": "London", "Ashburn": "Ashburn", "Reston": "Ashburn"}
    for r in R:
        ld = LD.get(r["s"]); g = GEO.get(ips.get(ld), {}); r["client"] = cl(ld); r["city"] = METRO.get(g.get("city"), g.get("city") or "?"); r["host"] = (g.get("org") or "?")[:18]
        x = RAW.get(r["sig"]) or {}; r["svc"] = "+".join(sorted({a for a, _ in x.get("tips", [])})) or "no tip"; r["tip"] = sum(v for _, v in x.get("tips", [])); r["cup"] = int(x.get("cup") or 0); r["cul"] = int(x.get("cul") or 0); r["progs"] = x.get("progs", [])
    json.dump(R, open("jitowin.json", "w"))
    med = lambda v: statistics.median(v) if v else float("nan")
    print("\n=== winners by leader client (all races)")
    for c in ("Jito", "BAM", "Harmonic", "Firedancer"):
        v = [r for r in R if r["client"] == c]
        if v: print(f"  {c:10s} races {len(v):6d} | winner delay med {med([r['dl'] for r in v]):5.1f} ms (p25 {sorted(r['dl'] for r in v)[len(v)//4]:.1f}) | same slot as dump {sum(r['same'] for r in v)/len(v):.0%} | "
                    f"no tip {sum(r['svc']=='no tip' for r in v)/len(v):.0%} | CU price med {med([r['cup'] for r in v]):.0f}")
    J = [r for r in R if r["client"] == "Jito"]
    print("\n=== JITO leaders: how the winning tx was sent (tip services on the winning tx)")
    sv = collections.Counter(r["svc"] for r in J)
    for s, n in sv.most_common(14):
        v = [r for r in J if r["svc"] == s]
        print(f"  {s[:34]:34s} wins {n:5d} ({n/len(J):4.0%}) | delay med {med([r['dl'] for r in v]):5.1f} ms | same slot {sum(r['same'] for r in v)/n:.0%} | tip med {med([r['tip'] for r in v])/1e9:.5f} | CU price med {med([r['cup'] for r in v]):.0f}")
    print("\n=== JITO leaders by city (where the leader is): winner delay")
    for city, n in collections.Counter(r["city"] for r in J).most_common(14):
        v = [r for r in J if r["city"] == city]
        tb = collections.Counter(r["user"][:8] for r in v).most_common(3)
        print(f"  {city[:16]:16s} races {n:5d} | winner delay med {med([r['dl'] for r in v]):5.1f} ms | same slot {sum(r['same'] for r in v)/n:.0%} | no tip {sum(r['svc']=='no tip' for r in v)/n:.0%} | top winners {tb}")
    print("\n=== top 15 winning bots on JITO leaders: delay per leader city (one region or many?)")
    cities = [c for c, _ in collections.Counter(r["city"] for r in J).most_common(6)]
    print("  bot        wins | " + " | ".join(f"{c[:9]:>9s}" for c in cities) + " | services")
    for u, n in collections.Counter(r["user"] for r in J).most_common(15):
        v = [r for r in J if r["user"] == u]
        cells = []
        for c in cities:
            w = [r["dl"] for r in v if r["city"] == c]
            cells.append(f"{med(w):5.0f}ms/{len(w):<3d}" if w else "        - ")
        print(f"  {u[:8]} {n:6d} | " + " | ".join(cells) + f" | {collections.Counter(r['svc'] for r in v).most_common(3)}")
    print("\n=== OURS: where we bought in these races (delay after the dump, by leader client)")
    for w, name in OURS.items():
        for c in ("Jito", "BAM", "Harmonic", "Firedancer"):
            v = [r["ours"][w][2] for r in R if w in r["ours"] and r["client"] == c]
            won = sum(1 for r in R if r["user"] == w and r["client"] == c)
            if v: print(f"  {name} {c:10s} our buys {len(v):3d} | our delay med {med(v):5.1f} ms | we were first {won} | winner delay med in those races {med([r['dl'] for r in R if w in r['ours'] and r['client']==c]):5.1f} ms")
