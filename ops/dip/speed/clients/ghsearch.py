#!/usr/bin/env python3
"""Search GitHub repos (unauthenticated REST API). Prints name | updated | stars | description. Read-only."""
import json, sys, urllib.request, urllib.parse
for q in sys.argv[1:]:
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": q, "per_page": 15})
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "research"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as e:
        print("===", q, "ERR", e); continue
    print("===", q, d.get("total_count"))
    for r in d.get("items", []):
        print(" ", r["full_name"], "|", r["pushed_at"][:10], "|", r["stargazers_count"], "|", (r["description"] or "")[:110])
