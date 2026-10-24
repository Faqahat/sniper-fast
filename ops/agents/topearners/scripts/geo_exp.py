# same-slot landing share of each wallet's buy attempts (ok + failed) by the dump-slot leader's location / client.
# attempts = buy-intent txs (ok buys + failed buy/unk txs) landing <= 5 slots after a >=1 SOL sell by another wallet.
import json, gzip, collections, sys, bisect
B = "/home/moiz/sniper/ops/agents/topearners/work/"
TOP = [l.strip() for l in open(B + sys.argv[1]) if l.strip()]
LB = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json")); LEAD = LB["leaders"]; NODES = LB["nodes"]
geo = {r["pk"]: r for r in json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_geo.json"))["rows"]}
rtt2 = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
def region(pk):
    g = geo.get(pk)
    if not g: return "?"
    c = (g.get("city") or ""); cc = g.get("cc") or ""
    if cc == "DE": return "DE-FRA"
    if cc == "NL": return "NL-AMS"
    if cc in ("GB", "LT", "SE", "FR", "IE", "FI", "PL", "CH", "AT", "CZ", "IT", "ES", "UA", "RO", "BG", "NO", "DK", "BE", "LU", "PT", "HU", "LV", "EE"): return "EU-other"
    if cc in ("US", "CA"): return "NA"
    if cc in ("JP", "SG", "HK", "KR", "TW", "IN", "AU", "VN", "TH", "ID", "MY", "PH", "CN"): return "ASIA"
    return "other"
def rttb(pk):
    g = geo.get(pk); r = (g or {}).get("rtt")
    if r is None: r = (rtt2.get(pk) or {}).get("rtt")
    if r is None: return "?"
    return "<2ms" if r < 2 else "2-12ms" if r < 12 else "12-50ms" if r < 50 else "50-120ms" if r < 120 else ">120ms"
dumps = collections.defaultdict(list)
for line in gzip.open(B + "races.jsonl.gz", "rt"):
    r = json.loads(line)
    if r["run"] == "R2": dumps[r["m"]].append((r["s"], r["i"], r["user"]))
for m in dumps: dumps[m].sort()
agg = {w: collections.defaultdict(lambda: [0, 0, 0, 0]) for w in TOP}   # key -> [attempts, same-slot ok, same-slot any, ok any]
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    w = x["w"]
    if w not in agg or x["kind"] not in ("buy", "unk") or not x["mints"]: continue
    D = dumps.get(x["mints"][0])
    if not D: continue
    k = bisect.bisect_left(D, (x["s"], x["i"]))
    if k == 0: continue
    p = D[k - 1]
    if x["s"] - p[0] > 5 or p[2] == w: continue
    ld = LEAD.get(str(p[0]))
    if not ld: continue
    cls = NODES.get(ld, {}).get("client", "?")
    same = x["s"] == p[0]
    for key in (("reg", region(ld)), ("rtt", rttb(ld)), ("cls", cls)):
        a = agg[w][key]; a[0] += 1; a[1] += same and x["ok"]; a[2] += same; a[3] += x["ok"]
for w in TOP:
    print("=" * 20, w[:10])
    for kind in ("reg", "rtt", "cls"):
        items = sorted(((k[1], v) for k, v in agg[w].items() if k[0] == kind and v[0] >= 40), key=lambda kv: -kv[1][0])
        print("  ", kind, "  ".join(f"{k}: n={v[0]} same={v[2]/v[0]:.2f} ok={v[3]/v[0]:.2f}" for k, v in items))
