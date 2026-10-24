#!/usr/bin/env python3
# Tweet tokens: which ones draw buyers on their own, and can we trade them? Joins launch metadata (tweet link → author, tweet time)
# with per-launch outcomes (R1–R3 SOL curves). Rules are chosen on R1+R2 and tested on R3 (author history is built from R1+R2 only).
import json, re, gzip, pickle, collections, statistics
O = pickle.load(gzip.open("outcome.pkl.gz", "rb"))
RX = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")
M = {}
for l in open("meta.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    if not r.get("ok"): continue
    mm = RX.search(r.get("twitter", "")) or RX.search(r.get("website", "")) or RX.search(r.get("desc", ""))
    r["acct"] = mm.group(1).lower() if mm else None; r["tid"] = int(mm.group(2)) if mm else None
    r["tweet_ts"] = ((r["tid"] >> 22) + 1288834974657) / 1000 if r["tid"] else None
    M[r["m"]] = r
med = lambda v: statistics.median(v) if v else float("nan")
def summ(name, ms_, key="s75", hold="h10"):
    v = [O[m] for m in ms_ if m in O]
    if not v: print(f"  {name:38s} n=0"); return
    p = [x[key][hold] for x in v if x.get(key)]
    print(f"  {name:38s} n={len(v):6d} | others buy 60s med {med([x['buy60'] for x in v]):5.2f} SOL, 5m {med([x['buy300'] for x in v]):5.2f} | buyers 5m {med([x['buyers300'] for x in v]):4.0f} | "
          f"graduated {sum(x['grad'] for x in v)/len(v):5.1%} | buy@{key[1:]}ms 1 SOL, sell {hold[1:]}s: total {sum(p):+8.1f}, per token {sum(p)/max(len(p),1):+.3f}, up {sum(1 for x in p if x > 0)/max(len(p),1):.0%}")
tw = [m for m in O if m in M and M[m]["acct"]]; notw = [m for m in O if m not in M]
print(f"launches with SOL tapes: {len(O)} | with fetched metadata: {sum(1 for m in O if m in M)} | with an X status link: {len(tw)}\n")
print("=== 1. tweet tokens vs the rest (buy 75 ms after create, sell after 10 s)")
summ("tweet-link tokens (launcher metadata)", tw); summ("others (generic IPFS / no link)", notw)
for host in ("metadata.j7tracker.io", "meta.uxento.io", "m.rapidlaunch.io"):
    summ(f"  host {host}", [m for m in tw if M[m]["host"] == host])
print("\n=== 2. freshness: tweet -> launch delay")
for a, b, lab in ((-1e9, 15, "launched <15 s after the tweet"), (15, 120, "15 s – 2 min"), (120, 3600, "2 min – 1 h"), (3600, 1e12, "> 1 h (old tweet)")):
    summ(lab, [m for m in tw if a <= O[m]["bt"] - M[m]["tweet_ts"] < b])
print("\n=== 3. sibling order: tokens for the SAME tweet (by launch time)")
bytw = collections.defaultdict(list)
for m in tw: bytw[M[m]["tid"]].append(m)
first = []; later = []; lone = []
for tid, v in bytw.items():
    v.sort(key=lambda m: O[m]["bt"])
    if len(v) == 1: lone.append(v[0])
    else: first.append(v[0]); later += v[1:]
summ("only token for its tweet", lone); summ("first of several for the tweet", first); summ("2nd+ token for the tweet", later)
print("\n=== 4. top X accounts by number of tokens (all runs)")
ac = collections.Counter(M[m]["acct"] for m in tw)
for a, n in ac.most_common(15): summ(f"@{a}", [m for m in tw if M[m]["acct"] == a])
print("\n=== 5. OUT-OF-SAMPLE author rule: author's tokens on R1+R2 drew >= X SOL of buys in 60 s (median) -> buy its R3 tokens")
train = [m for m in tw if O[m]["run"] in ("R1", "R2")]; test = [m for m in tw if O[m]["run"] == "R3"]
hist = collections.defaultdict(list)
for m in train: hist[M[m]["acct"]].append(O[m]["buy60"])
for thr in (1, 3, 5, 10):
    good = {a for a, v in hist.items() if len(v) >= 2 and med(v) >= thr}
    sel = [m for m in test if M[m]["acct"] in good]
    for key in ("s75", "s200", "s2000"):
        for hold in ("h3", "h10", "h30", "h60", "tp50_60", "tp100_300"):
            pass
    print(f"  threshold {thr} SOL: {len(good)} authors qualify")
    for key in ("s75", "s200", "s2000"):
        for hold in ("h3", "h10", "h30", "tp50_60"):
            summ(f"    R3 picks, buy@{key[1:]}ms sell {hold}", sel, key, hold)
    summ("    R3 picks, PESSIMISTIC (drop 2 slots), sell h10", sel, "s75d", "h10")
print("\n=== 6. reference: buy EVERY tweet token on R3 at 75 ms")
for hold in ("h1", "h3", "h10", "h30", "h60", "h300", "tp50_60", "tp100_300", "sl20_300"):
    summ(f"  all R3 tweet tokens, sell {hold}", test, "s75", hold)
