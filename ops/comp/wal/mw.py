# READ-ONLY. Fetch token metadata JSON (uri) for each 9X buy: website / twitter / telegram / description -> does it explain size k?
import sys, json, re, urllib.request, collections, statistics as st
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc
F = json.load(open(sys.argv[1]))
OUTM = sys.argv[2]
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


with ThreadPoolExecutor(8) as ex:
    M = {o["mint"]: o for o in ex.map(work, F)}
json.dump(M, open(OUTM, "w"))
print("metadata ok", sum(o["ok"] for o in M.values()), "/", len(M))


