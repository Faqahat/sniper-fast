#!/usr/bin/env python3
# READ-ONLY public GETs. For every launch in /root/nob/meta.jsonl (+ optional extra meta file) with an X/Twitter link:
#   status link  -> api.fxtwitter.com/status/<id>   (author followers/joined/verification, likes/retweets/views NOW)
#   profile link -> api.fxtwitter.com/<handle>      (followers, joined)
# Cached to /root/race/tweets.jsonl (one line per tweet id or handle). NOTE: engagement is as of the fetch, not the launch.
# usage: tweets_hist.py [extra_meta.jsonl ...]
import json, re, sys, os, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor

OUT = "/root/race/tweets.jsonl"
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["key"])
        except Exception:
            pass
keys = set()
for fn in ["/root/nob/meta.jsonl"] + sys.argv[1:]:
    for l in open(fn):
        try:
            r = json.loads(l)
        except Exception:
            continue
        tw = ((r.get("j") or {}).get("twitter") or "")
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/status/(\d+)", tw)
        if m:
            keys.add("s:" + m.group(2))
            continue
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/?(?:\?|$)", tw)
        if m and m.group(1).lower() not in ("i", "home", "search", "intent", "share"):
            keys.add("u:" + m.group(1).lower())
todo = sorted(k for k in keys if k not in done)
print("keys", len(keys), "todo", len(todo), flush=True)
lk = threading.Lock()
fh = open(OUT, "a")


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; read-only)"})
            return json.load(urllib.request.urlopen(req, timeout=10))
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                return {"code": 404}
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.0 * (i + 1))
    return {"code": -1}


def work(k):
    t = time.time()
    if k.startswith("s:"):
        d = get("https://api.fxtwitter.com/status/" + k[2:])
        tw = d.get("tweet") or {}
        a = tw.get("author") or {}
        rec = {"key": k, "ok": bool(tw), "code": d.get("code"), "likes": tw.get("likes"), "retweets": tw.get("retweets"), "replies": tw.get("replies"),
               "quotes": tw.get("quotes"), "views": tw.get("views"), "ts": tw.get("created_timestamp"), "media": bool(tw.get("media")),
               "author": a.get("screen_name"), "followers": a.get("followers"), "following": a.get("following"), "joined": a.get("joined"),
               "verified": ((a.get("verification") or {}).get("verified")), "vtype": ((a.get("verification") or {}).get("type"))}
    else:
        d = get("https://api.fxtwitter.com/" + k[2:])
        u = d.get("user") or {}
        rec = {"key": k, "ok": bool(u), "code": d.get("code"), "followers": u.get("followers"), "following": u.get("following"),
               "joined": u.get("joined"), "tweets": u.get("tweets"), "verified": ((u.get("verification") or {}).get("verified"))}
    rec["ms"] = round((time.time() - t) * 1000)
    rec["fetched"] = int(time.time())
    with lk:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


with ThreadPoolExecutor(6) as ex:
    list(ex.map(work, todo))
print("FINISHED", len(todo), flush=True)
