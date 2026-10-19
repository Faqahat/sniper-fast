import json
from collections import Counter
F = json.load(open("/root/sep/features.json"))
rows = sorted(F.values(), key=lambda r: r["slot"])

def name_lower(r):
    nm = r.get("name")
    return True if nm is None else nm.islower()
def is_round(r):
    return r["dev"] % 1_000_000_000 == 0

print("LABELED BAND TABLE (sorted by slot) — name shown")
print(f"{'mint':<9} {'lab':<4} {'dev':>5} {'host':<17} {'name':<26} low rnd")
for r in rows:
    print(f"{r['mint'][:8]:<9} {r['label']:<4} {r['dev']/1e9:>5.2f} {str(r.get('uri_host'))[:16]:<17} "
          f"{str(r.get('name'))[:25]:<26} {'L' if name_lower(r) else '.'}   {'R' if is_round(r) else '.'}")

print("\n=== RECOMMENDED RULE  (REJECT if name all-lowercase/unparseable  OR  dev is exact N.0 SOL) ===")
def keep(r):
    return (not name_lower(r)) and (not is_round(r))
kept = [r for r in rows if keep(r)]
rej  = [r for r in rows if not keep(r)]
print("KEEP :", Counter(r["label"] for r in kept))
print("REJECT:", Counter(r["label"] for r in rej))
print("\nwinners LOST to the rule (false rejects):")
for r in rej:
    if r["label"] == "WIN":
        print(f"   {r['mint'][:8]} {r.get('name')!r} dev={r['dev']/1e9} low={name_lower(r)} round={is_round(r)}")
print("losers KEPT by the rule (false keeps):")
for r in kept:
    if r["label"] == "LOSE":
        print(f"   {r['mint'][:8]} {r.get('name')!r} dev={r['dev']/1e9}")

# save summary json
summ = {
    "band": "dev_buy 0.8-3.0 SOL, URI-host trusted",
    "counts": {"WIN": 26, "LOSE": 13, "MID": 3},
    "recommended_rule": "REJECT if (name all-lowercase or create unparseable) OR (dev_buy is exact multiple of 1.0 SOL)",
    "in_sample": {"keptW": sum(1 for r in kept if r["label"]=="WIN"),
                  "keptL": sum(1 for r in kept if r["label"]=="LOSE")},
}
json.dump(summ, open("/root/sep/summary.json","w"), indent=2)
print("\nsaved /root/sep/summary.json")
