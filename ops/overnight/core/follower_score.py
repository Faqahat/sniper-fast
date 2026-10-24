# deployer "follower score" (walk-forward): how much outside buying its PAST launches drew in their first ~1 s (from the
# launch table: f1s_px = price multiple 1 s after the bundle, f1s_bsol = outside buy SOL in 1 s). Select deployers whose
# past launches drew strong follow-on demand; trade with the guarded flip. Learn good deployers without copying anyone.
import json, gzip, collections, statistics, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); R = json.load(open("allres_static_0034.json"))
T = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l); T[r["mint"]] = (r.get("f1s_px"), r.get("f1s_bsol"), r.get("f1s_ub"))
lst = set(open("/home/moiz/sniper/ops/overnight/dryrun/deployer_list.txt").read().split())
seq = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
def run(min_n, key, thr, Lm, only_new=False):
    hist = collections.defaultdict(list); pend = []; out = collections.defaultdict(list)
    for bt, m in seq:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        c = L[m]; d = c["user"]; r = R.get(m); h = hist[d]
        if r and Lm in r and len(h) >= min_n and statistics.median(h) >= thr and not (only_new and d in lst):
            o = r[Lm]; v = o.get("0.5") if o["ok"] else -0.005
            if v is not None: out[r["run"]].append(v)
        t = T.get(m)
        if t and t[key] is not None: pend.append((bt + 60, d, t[key])); pend.sort(key=lambda z: z[0])
    return out
for Lm in ("75", "45"):
    print(f"=== {Lm} ms ===")
    for key, name, thrs in ((0, "median 1-s price multiple", (1.1, 1.2, 1.3, 1.5)), (1, "median outside buy SOL in 1 s", (2, 4, 6, 10))):
        for thr in thrs:
            for only_new in (False, True):
                o = run(2, key, thr, Lm, only_new)
                print(f"   {name} >= {thr:<4} (>= 2 past launches){' NEW deployers only' if only_new else '':20}: " + " | ".join(f"{run_} {sum(o[run_]):+7.2f} ({sum(1 for x in o[run_] if x != -0.005)}/{len(o[run_])})" for run_ in ("R1", "R2")))
