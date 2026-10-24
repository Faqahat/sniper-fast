# index gap (dump -> attempt) for ALL same-slot buy attempts (ok + failed), per wallet; R2 also by leader client.
import json, gzip, collections, sys, bisect
B = "/home/moiz/sniper/ops/agents/topearners/work/"
TOP = [l.strip() for l in open(B + sys.argv[1]) if l.strip()] + ["2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"]
LB = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json")); LEAD = LB["leaders"]; NODES = LB["nodes"]
dumps = collections.defaultdict(list)
for line in gzip.open(B + "races.jsonl.gz", "rt"):
    r = json.loads(line); dumps[r["m"]].append((r["s"], r["i"], r["user"], r["sol"]))
for m in dumps: dumps[m].sort()
D_all = collections.defaultdict(list); D_cls = collections.defaultdict(list); D_ok = collections.defaultdict(list)
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line); w = x["w"]
    if w not in TOP or x["kind"] not in ("buy", "unk") or not x["mints"]: continue
    D = dumps.get(x["mints"][0])
    if not D: continue
    k = bisect.bisect_left(D, (x["s"], x["i"]))
    if k == 0: continue
    p = D[k - 1]
    if p[0] != x["s"] or p[2] == w: continue
    di = x["i"] - p[1]
    D_all[w].append(di)
    if x["ok"]: D_ok[w].append(di)
    ld = LEAD.get(str(p[0]))
    if ld: D_cls[(w, NODES.get(ld, {}).get("client", "?"))].append(di)
def q(v, ps=(10, 25, 50, 75)):
    v = sorted(v)
    return "/".join(str(v[min(len(v) - 1, int(p / 100 * len(v)))]) for p in ps) if v else "-"
for w in TOP:
    print(f"{w[:10]} same-slot attempts n={len(D_all[w]):5d} di p10/25/50/75={q(D_all[w]):18s} ok-only={q(D_ok[w])}")
    s = []
    for c in ("AgaveBam", "JitoLabs", "HarmonicAgave", "Firedancer", "HarmonicFiredancer"):
        v = D_cls.get((w, c), [])
        if len(v) >= 30: s.append(f"{c}:{q(v,(25,50))}")
    if s: print("        ", "  ".join(s))
