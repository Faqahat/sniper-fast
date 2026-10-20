# READ-ONLY report of a route probe (probe_routes.sh -> --probe-log JSONL): per send path and leader class, how fast a
# probe sent right after a create shows up in our shred feed (create->seen = what decides our position in the create
# slot; send->seen = the path + leader alone), and how often it lands in the create slot at all.
# usage: python3 probe_report.py <probe jsonl> [<probe jsonl> ...]
import sys, json, collections

rows = [json.loads(l) for f in sys.argv[1:] for l in open(f) if l.strip()]


def cls(c):
    if c in ("AgaveBam", "FireBAM"): return "bam"
    if (c or "").startswith("Harmonic"): return "harmonic"
    if c == "JitoLabs": return "jito"
    if c in ("Firedancer", "Frankendancer"): return "fd"
    if c == "Agave": return "agave"
    return "other" if c else "?"


def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None


def line(label, rs):
    seen = [r for r in rs if r.get("create_to_seen_ms") is not None]
    same = [r for r in seen if r.get("seen_slot") == r["create_slot"]]
    cts = [r["create_to_seen_ms"] for r in same]
    sts = [r["send_to_seen_ms"] for r in same]
    f = lambda x: "  -  " if x is None else f"{x:5.1f}"
    return (f"  {label:28} sent {len(rs):3}  seen {len(seen):3}  in create slot {len(same):3}  "
            f"create->seen p25 {f(q(cts, .25))} median {f(q(cts, .5))} p75 {f(q(cts, .75))}   send->seen median {f(q(sts, .5))}  "
            f"landed ok {sum(1 for r in rs if r.get('ok'))}")


spent = sum((r.get("tips_lamports") or 0) for r in rs) if (rs := [r for r in rows if r.get("ok")]) else 0
print(f"probes {len(rows)}, landed ok {len(rs)}, tips paid on landed probes {spent / 1e9:.4f} SOL")
print("\nBY PATH (all leader types)")
by = collections.defaultdict(list)
for r in rows: by[r["path"]].append(r)
for p, v in sorted(by.items(), key=lambda kv: q([r["create_to_seen_ms"] for r in kv[1] if r.get("create_to_seen_ms") is not None and r.get("seen_slot") == r["create_slot"]], .5) or 1e9):
    print(line(p, v))
print("\nBY LEADER CLASS x PATH")
by2 = collections.defaultdict(list)
for r in rows: by2[(cls(r.get("client")), r["path"])].append(r)
for (c, p), v in sorted(by2.items()):
    print(line(f"{c:9} {p}", v))
print("\nBY LEADER (validator) for the slow-suspect ones")
by3 = collections.defaultdict(list)
for r in rows: by3[(r.get("leader", "")[:8], cls(r.get("client")))].append(r)
for (ld, c), v in sorted(by3.items(), key=lambda kv: -len(kv[1]))[:12]:
    print(line(f"{ld} {c}", v) + "   paths " + ",".join(sorted({r['path'] for r in v})))
