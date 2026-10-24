# Narrative heat: how many OTHER launches share the token's name (normalised) within 30 min before the group's buy, vs random tokens at a
# random later moment. Also: did the group buy a sibling first, and how many siblings appeared in the last 2 min before its buy.
import json, re, collections, statistics, pickle, gzip, random, bisect
MS = set(l.strip() for l in open("../g3/mints.txt") if l.strip())
PRE = {o["m"]: o for o in pickle.load(gzip.open("pre.pkl.gz", "rb"))}
norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
L = []; BY = collections.defaultdict(list)
for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426", "run_20261024_1425"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        k = norm(c.get("name"))
        if k: BY[k].append(c["bt"]); L.append(c)
for k in BY: BY[k].sort()
def sib(name, t, win):
    v = BY.get(norm(name), []); return bisect.bisect_right(v, t) - bisect.bisect_left(v, t - win)
g = []
for m, o in PRE.items():
    c = next((x for x in L if x["mint"] == m), None)
    if not c: continue
    t = int(o["gb"]["bt"]); g.append((sib(c["name"], t, 1800) - 1, sib(c["name"], t, 120), sib(c["name"], t, 86400) - 1, c["name"]))
random.seed(3); r = []
for c in random.sample(L, 3000):
    t = c["bt"] + random.choice([30, 120, 360, 1200])
    r.append((sib(c["name"], t, 1800) - 1, sib(c["name"], t, 120), sib(c["name"], t, 86400) - 1))
for lab, v in (("GROUP buys", g), ("random tokens", r)):
    a = [x[0] for x in v]; b = [x[1] for x in v]; d = [x[2] for x in v]
    print(f"{lab:14s} n={len(v):4d} | same-name launches in the 30 min before: median {statistics.median(a):.0f}, share >=3: {sum(x >= 3 for x in a)/len(a):.0%}, >=10: {sum(x >= 10 for x in a)/len(a):.0%} "
          f"| in the last 2 min: share >=2: {sum(x >= 2 for x in b)/len(b):.0%} | same name in 24 h: median {statistics.median(d):.0f}")
print("\ngroup tokens with the most same-name launches in the 30 min before its buy:", sorted([(x[0], x[3][:22]) for x in g], reverse=True)[:12])
