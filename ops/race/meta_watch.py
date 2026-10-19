#!/usr/bin/env python3
# READ-ONLY public GETs, run beside a forward PAPER run. Tails the engine log; for every "RACE seen" launch it fetches the
# metadata URI, then the X/Twitter data behind it (api.fxtwitter.com), and records WHEN each piece was available:
#   t_seen  = when this watcher read the log line (~ms after the engine saw the create)
#   meta_ms = URI fetch time, tw_ms = tweet/profile fetch time, total_ms = from t_seen to everything known.
# This measures whether the off-chain signal is usable in time (same-slot needs ~<=100-300 ms) and records engagement AT
# LAUNCH TIME (likes/views/followers) for the forward test. Output: one JSON line per launch.
# usage: meta_watch.py <paper.log> <out.jsonl>
import sys, re, json, time, threading, urllib.request, os
from concurrent.futures import ThreadPoolExecutor

LOG, OUT = sys.argv[1], sys.argv[2]
lk = threading.Lock()
fh = open(OUT, "a")
pool = ThreadPoolExecutor(12)
seen = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            seen.add(json.loads(l)["mint"])
        except Exception:
            pass


def get(url, timeout=6.0):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; read-only)"})
        raw = urllib.request.urlopen(req, timeout=timeout).read(200000)
        return json.loads(raw), (time.time() - t) * 1000, None
    except Exception as ex:
        return None, (time.time() - t) * 1000, repr(ex)[:80]


def fetch_meta(uri):
    """ipfs.io / dweb.link refuse this server (403): rewrite /ipfs/<cid> URIs to ipfs.filebase.io, then pinata as fallback."""
    m = re.search(r"/ipfs/([A-Za-z0-9]+)", uri)
    if m:
        tries = ["https://ipfs.filebase.io/ipfs/" + m.group(1), "https://gateway.pinata.cloud/ipfs/" + m.group(1)]
    else:
        tries = [uri]
    tot, last = 0.0, None
    for u in tries:
        j, ms, err = get(u, timeout=3.0 if len(tries) > 1 and u == tries[0] else 6.0)
        tot += ms
        if isinstance(j, dict):
            return j, tot, None, u.split("/")[2]
        last = err
    return None, tot, last, tries[-1].split("/")[2]


def work(mint, uri, t_seen):
    rec = {"mint": mint, "uri": uri, "t_seen": t_seen}
    j, ms, err, gw = fetch_meta(uri) if uri.startswith("http") else (None, 0, "no-uri", "-")
    rec["meta_ms"], rec["meta_err"], rec["gw"] = round(ms), err, gw
    if isinstance(j, dict):
        rec["meta"] = {k: (str(v)[:200] if not isinstance(v, (int, float, bool)) else v) for k, v in j.items() if k in
                       ("name", "symbol", "twitter", "website", "telegram", "description", "createdOn", "showName", "image", "coin_community")}
        tw = str(j.get("twitter") or "")
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/status/(\d+)", tw)
        m2 = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/?(?:\?|$)", tw)
        if m:
            d, ms2, err2 = get("https://api.fxtwitter.com/status/" + m.group(2))
            tw_ = (d or {}).get("tweet") or {}
            a = tw_.get("author") or {}
            rec.update(tw_kind="status", tw_id=m.group(2), tw_ms=round(ms2), tw_err=err2, likes=tw_.get("likes"), retweets=tw_.get("retweets"),
                       replies=tw_.get("replies"), quotes=tw_.get("quotes"), views=tw_.get("views"), tw_ts=tw_.get("created_timestamp"),
                       author=a.get("screen_name"), followers=a.get("followers"), joined=a.get("joined"),
                       verified=(a.get("verification") or {}).get("verified"), vtype=(a.get("verification") or {}).get("type"), tw_ok=bool(tw_))
        elif m2 and m2.group(1).lower() not in ("i", "home", "search", "intent", "share"):
            d, ms2, err2 = get("https://api.fxtwitter.com/" + m2.group(1))
            u = (d or {}).get("user") or {}
            rec.update(tw_kind="profile", tw_ms=round(ms2), tw_err=err2, followers=u.get("followers"), joined=u.get("joined"),
                       verified=(u.get("verification") or {}).get("verified"), tw_ok=bool(u), author=m2.group(1))
        else:
            rec["tw_kind"] = "none" if not tw else "other"
    rec["total_ms"] = round((time.time() - t_seen) * 1000)
    with lk:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


f = open(LOG, errors="replace")
f.seek(0, 2) if os.environ.get("FROM_END") else None
idle = 0
while True:
    line = f.readline()
    if not line:
        time.sleep(0.02)
        idle += 1
        if idle > 50 * 60 * 20:   # 20 min with no new lines -> the run is over
            break
        continue
    idle = 0
    if "PAPER_RACE_DONE" in line:
        break
    if "RACE seen" not in line:
        continue
    m = re.search(r"mint=(\w+)", line)
    u = re.search(r" uri=(\S+)", line)
    if not m or m.group(1) in seen:
        continue
    seen.add(m.group(1))
    pool.submit(work, m.group(1), u.group(1) if u else "-", time.time())
pool.shutdown(wait=True)
print("meta_watch done", flush=True)
