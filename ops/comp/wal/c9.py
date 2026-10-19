# READ-ONLY offline: 9X size unit k by token metadata class
import json, statistics as st
from collections import defaultdict
F = [json.loads(l) for l in open("/root/comp/wal/9X_feat.jsonl")]
F = [f for f in F if "dev" in f]
M = json.load(open("/root/comp/wal/9X_meta.json"))
MEDIA = ("x.com", "twitter.com", "youtube", "youtu.be", "instagram", "cnn.com", "gettyimages", "dexerto", "4chan", "otcdesks.cash", "usepaid",
         "tiktok", "reddit", "bbc", "reuters", "google")


def dom(u):
    u = (u or "").lower().split("://")[-1].split("/")[0]
    return u[4:] if u.startswith("www.") else u


def cls(f):
    o = M.get(f["mint"], {})
    if not o.get("ok"): return "no-meta (fetch failed)"
    w = dom(o.get("website")); t = (o.get("twitter") or "").lower()
    own_site = bool(w) and not any(m in w for m in MEDIA)
    acct = bool(t) and "/status/" not in t
    if own_site and acct: return "PROJECT: own site + X acct"
    if own_site: return "own site + tweet link"
    if acct: return "X account, no site"
    if "otcdesks" in w: return "otcdesks link (j7/Lunar)"
    if "/status/" in t: return "tweet-ref meme"
    return "bare (no links)"


G = defaultdict(list)
for f in F: G[cls(f)].append(f)
print(f"{'class':28} {'n':>3} {'k_med':>5} {'k_avg':>5} {'SOL_med':>7}  {'k list':34} pnl_avg pnl_med win%")
for c, g in sorted(G.items(), key=lambda kv: -st.mean(f["k"] for f in kv[1])):
    ks = sorted(f["k"] for f in g)
    print(f"{c:28} {len(g):3} {ks[len(ks) // 2]:5} {st.mean(ks):5.1f} {ks[len(ks) // 2] * 0.494:7.2f}  {str(ks)[:34]:34} {st.mean(f['pnl_pct'] for f in g) * 100:+6.1f} {st.median(f['pnl_pct'] for f in g) * 100:+6.1f} {sum(f['pnl_pct'] > 0 for f in g) / len(g) * 100:4.0f}")
g = G["no-meta (fetch failed)"]
print("no-meta: k when bundle>=9 SOL:", sorted(f["k"] for f in g if f["gsol"] >= 9), " others:", sorted(f["k"] for f in g if f["gsol"] < 9))
allb = [f for f in F if f["gsol"] >= 9]
print("all launches with creator bundle >=9 SOL:", sorted(f["k"] for f in allb), "pnl avg %+.1f%%" % (st.mean(f["pnl_pct"] for f in allb) * 100))
