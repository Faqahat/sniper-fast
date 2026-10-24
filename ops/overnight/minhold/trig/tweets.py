# Tweet links in token metadata -> tweet time (snowflake id), the X account, and the timing: tweet -> token launch -> group's first buy.
import json, os, re, collections, statistics, pickle, gzip, time
MS = set(l.strip() for l in open("../g3/mints.txt") if l.strip())
L = {}
for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426", "run_20261024_1425"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        L[c["mint"]] = c
PRE = {o["m"]: o for o in pickle.load(gzip.open("pre.pkl.gz", "rb"))}
RX = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")
def tw(body):
    try: d = json.loads(body)
    except Exception: d = {}
    for k in ("twitter", "website", "description"):
        mm = RX.search(str(d.get(k) or ""))
        if mm: return mm.group(1), int(mm.group(2)), k, d
    return None, None, None, d
rows = []
for f in os.listdir("meta"):
    m = f[:-5]; d = json.load(open("meta/" + f))
    if not d.get("ok") or m not in L: continue
    acct, tid, field, meta = tw(d["body"])
    rows.append(dict(m=m, grp=m in MS, acct=acct, tid=tid, tweet_ts=((tid >> 22) + 1288834974657) / 1000 if tid else None, launch=L[m]["bt"],
                     buy=int(PRE[m]["gb"]["bt"]) if m in PRE else None, src=(meta.get("createdOn") or meta.get("description") or "")[:40]))
for grp in (True, False):
    v = [r for r in rows if r["grp"] == grp]
    t = [r for r in v if r["tid"]]
    print(f"\n{'GROUP' if grp else 'RANDOM'} tokens with metadata: {len(v)} | with an X status link: {len(t)} ({len(t) / max(len(v), 1):.0%})")
    if t:
        d1 = [r["launch"] - r["tweet_ts"] for r in t]
        print(f"   tweet -> token launch: median {statistics.median(d1):.0f} s (p25 {sorted(d1)[len(d1)//4]:.0f}, p75 {sorted(d1)[3*len(d1)//4]:.0f})")
        if grp:
            d2 = [r["buy"] - r["tweet_ts"] for r in t if r["buy"]]; d3 = [r["buy"] - r["launch"] for r in t if r["buy"]]
            print(f"   tweet -> GROUP BUY: median {statistics.median(d2):.0f} s (p10 {sorted(d2)[len(d2)//10]:.0f}, p90 {sorted(d2)[9*len(d2)//10]:.0f}) | launch -> group buy median {statistics.median(d3):.0f} s")
        print("   X accounts:", collections.Counter(r["acct"] for r in t).most_common(12))
print("\nGROUP tokens, one per line (PKT times):")
for r in sorted([r for r in rows if r["grp"]], key=lambda r: r["buy"] or 0):
    tt = time.strftime('%m-%d %H:%M:%S', time.gmtime(r["tweet_ts"] + 18000)) if r["tweet_ts"] else "        -        "
    print(f"  {r['m'][:6]} {L[r['m']].get('name', '')[:22]:22s} tweet @{(r['acct'] or '-')[:16]:16s} {tt} | launch +{(r['launch'] - r['tweet_ts']) if r['tweet_ts'] else float('nan'):6.0f}s | group buy +{(r['buy'] - r['tweet_ts']) if (r['tweet_ts'] and r['buy']) else float('nan'):7.0f}s after tweet | src {r['src'][:25]}")
json.dump(rows, open("tweets.json", "w"))
