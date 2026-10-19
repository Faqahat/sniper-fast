# READ-ONLY. Fetch token metadata JSON (uri) for each 9X buy: website / twitter / telegram / description -> does it explain size k?
import sys, json, re, urllib.request, collections, statistics as st
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc
F = [json.loads(l) for l in open("/root/comp/wal/9X_feat.jsonl")]
F = [f for f in F if "dev" in f]
GW = ["https://ipfs.io/ipfs/", "https://cloudflare-ipfs.com/ipfs/", "https://gateway.pinata.cloud/ipfs/", "https://dweb.link/ipfs/"]


def uri_of(m):
    a = rpc("getAccountInfo", [m, {"encoding": "jsonParsed"}])
    try:
        for ex in a["value"]["data"]["parsed"]["info"].get("extensions", []):
            if ex.get("extension") == "tokenMetadata":
                return ex["state"]["uri"]
    except Exception:
        pass
    return None


def get(u):
    urls = [u]
    mm = re.search(r"/ipfs/([A-Za-z0-9]+)", u or "")
    if mm: urls += [g + mm.group(1) for g in GW]
    for x in urls:
        try:
            with urllib.request.urlopen(urllib.request.Request(x, headers={"user-agent": "Mozilla/5.0"}), timeout=8) as r:
                return json.loads(r.read()[:200000])
        except Exception:
            continue
    return None


def work(f):
    u = uri_of(f["mint"])
    j = get(u) if u else None
    out = dict(mint=f["mint"], uri=u, ok=j is not None)
    if isinstance(j, dict):
        ext = j.get("extensions") if isinstance(j.get("extensions"), dict) else {}
        g = lambda k: (j.get(k) or ext.get(k) or "")
        out.update(twitter=str(g("twitter"))[:120], website=str(g("website"))[:120], telegram=str(g("telegram"))[:120],
                   desc_len=len(str(j.get("description") or "")), created_on=str(j.get("createdOn") or "")[:40], keys=sorted(j.keys())[:20])
    return out


with ThreadPoolExecutor(6) as ex:
    M = {o["mint"]: o for o in ex.map(work, F)}
json.dump(M, open("/root/comp/wal/9X_meta.json", "w"))
print("metadata ok", sum(o["ok"] for o in M.values()), "/", len(M))


def tw_kind(t):
    t = t.lower()
    if not t: return "none"
    if "/status/" in t: return "tweet"
    if "/i/communities" in t or "communities" in t: return "community"
    if "x.com" in t or "twitter.com" in t: return "account"
    return "other"


for f in F:
    o = M.get(f["mint"], {})
    f["tw"] = tw_kind(o.get("twitter", "")); f["web"] = bool(o.get("website")); f["tg"] = bool(o.get("telegram"))
    f["desc"] = o.get("desc_len", -1); f["con"] = o.get("created_on", "")
    f["metaok"] = o.get("ok", False)
grp = lambda k: "k1-2" if k <= 2 else ("k3-4" if k <= 4 else "k5+")
print(f"\n{'group':6} {'n':>3} {'meta':>4} {'tweet%':>6} {'acct%':>5} {'comm%':>5} {'none%':>5} {'web%':>5} {'tg%':>4} {'desc_med':>8}  pnl_avg  win%")
for gname in ("k1-2", "k3-4", "k5+"):
    g = [f for f in F if grp(f["k"]) == gname and f["metaok"]]
    if not g: continue
    pc = lambda c: sum(c(f) for f in g) / len(g) * 100
    print(f"{gname:6} {len(g):3} {len(g):4} {pc(lambda f: f['tw'] == 'tweet'):6.0f} {pc(lambda f: f['tw'] == 'account'):5.0f} {pc(lambda f: f['tw'] == 'community'):5.0f} {pc(lambda f: f['tw'] == 'none'):5.0f}"
          f" {pc(lambda f: f['web']):5.0f} {pc(lambda f: f['tg']):4.0f} {sorted(f['desc'] for f in g)[len(g) // 2]:8}  {st.mean(f['pnl_pct'] for f in g) * 100:+6.1f}  {pc(lambda f: f['pnl_pct'] > 0):4.0f}")
print("\ncreatedOn by group:")
c = collections.defaultdict(collections.Counter)
for f in F: c[f["con"][:30]][grp(f["k"])] += 1
for k, v in sorted(c.items(), key=lambda kv: -sum(kv[1].values()))[:8]: print(f"  {k or '-':30} {dict(v)}")
print("\nrows:")
for f in sorted(F, key=lambda f: (f["k"], f["bt"])):
    o = M.get(f["mint"], {})
    print(f"  k={f['k']:2} {f['name'][:18]:18} tw={f['tw']:9} web={'Y' if f['web'] else '-'} tg={'Y' if f['tg'] else '-'} desc={f['desc']:4} {o.get('website', '')[:40]:40} {o.get('twitter', '')[:55]}")
