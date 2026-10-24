# does in-block order among same-slot backrunners follow priority fee (cup), total fee, or tips? pairwise test per leader client
import json, gzip, collections
B = "/home/moiz/sniper/ops/agents/topearners/work/"
LB = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))
LEAD = LB["leaders"]; NODES = LB["nodes"]
res = collections.defaultdict(lambda: collections.Counter())
gapstat = collections.defaultdict(list)
for line in gzip.open(B + "races.jsonl.gz", "rt"):
    r = json.loads(line)
    if r["run"] != "R2": continue
    ld = LEAD.get(str(r["s"])); cls = NODES.get(ld, {}).get("client", "?") if ld else "?"
    same = [b for b in r["buys"] if b[1] == 0 and b[15] == 1]   # same slot as dump, single-event txs
    for a in range(len(same)):
        for c in range(a + 1, len(same)):
            x, y = same[a], same[c]          # x earlier than y
            if x[0] == y[0]: continue
            cx, cy = x[9] or 0, y[9] or 0
            if cx != cy: res[(cls, "cup")]["hi_first" if cx > cy else "lo_first"] += 1
            tx, ty = x[12] or 0, y[12] or 0
            if tx != ty: res[(cls, "tips")]["hi_first" if tx > ty else "lo_first"] += 1
            fx, fy = (x[8] or 0) + tx, (y[8] or 0) + ty
            if fx != fy: res[(cls, "fee+tip")]["hi_first" if fx > fy else "lo_first"] += 1
            # big gap vs small gap
            if cx and cy and (cx >= 3 * cy or cy >= 3 * cx):
                res[(cls, "cup_3x")]["hi_first" if cx > cy else "lo_first"] += 1
for k in sorted(res):
    c = res[k]; n = c["hi_first"] + c["lo_first"]
    if n >= 200: print(f"{k[0]:20s} {k[1]:8s} pairs={n:7d}  P(higher one is earlier)={c['hi_first']/n:.3f}")
