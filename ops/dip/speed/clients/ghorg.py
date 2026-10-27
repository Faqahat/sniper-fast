#!/usr/bin/env python3
"""List an org's/user's public GitHub repos (unauthenticated REST API, read-only)."""
import json, sys, urllib.request
for org in sys.argv[1:]:
    out = []
    for kind in ("orgs", "users"):
        url = f"https://api.github.com/{kind}/{org}/repos?per_page=100&sort=pushed"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "research"})
        try:
            out = json.load(urllib.request.urlopen(req, timeout=20)); break
        except Exception as e:
            err = e
    print("===", org, len(out) if out else err)
    for r in out or []:
        print(" ", r["full_name"], "|", r["pushed_at"][:10], "|", r["stargazers_count"], "| size_kb", r["size"], "|", r["default_branch"], "|", (r["description"] or "")[:90])
