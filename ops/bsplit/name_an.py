# Do token NAME / SYMBOL character patterns separate winners from losers? Fit on the overnight run ('night'),
# test on today's 'fresh' run. Realistic PnL (sell +1 s, 2 SOL) under landing models OURS and LANDX, from forward_proof.
import sys, runpy, io, contextlib, json, re, statistics as st, itertools, unicodedata


def load(tag):
    sys.argv = ["forward_proof.py", tag]
    with contextlib.redirect_stdout(io.StringIO()):
        g = runpy.run_path("/root/race/forward_proof.py", run_name="__main__")
    names = {}
    for l in open(f"/root/race/{tag}_onchain.jsonl"):
        try:
            r = json.loads(l)
        except Exception:
            continue
        b = r.get("b") or {}
        names[r.get("mint")] = (b.get("name") or "", b.get("symbol") or "")
    rows = []
    for o in g["F"]:
        nm, sy = names.get(o["mint"], ("", ""))
        o["name"], o["sym"] = nm, sy
        o["pn_ours"] = g["ev"](o, g["EXITS"]["time 1s"], "a OURS")(2.0)
        o["pn_landx"] = g["ev"](o, g["EXITS"]["time 1s"], "c LANDX")(2.0)
        rows.append(o)
    return rows, g


COMMON = ["wojak", "cat", "dog", "inu", "ai", "trump", "pepe", "frog", "coin", "sol", "meme", "elon", "baby", "the", "chill", "moon"]


def feats(o):
    n, s = o["name"], o["sym"]
    letters = [c for c in n if c.isalpha()]
    f = {
        "name_len<=4": len(n) <= 4, "name_len5-8": 5 <= len(n) <= 8, "name_len9-12": 9 <= len(n) <= 12, "name_len>12": len(n) > 12,
        "sym_len<=3": len(s) <= 3, "sym_len4-5": 4 <= len(s) <= 5, "sym_len>=6": len(s) >= 6,
        "name_has_space": " " in n, "name_words>=3": len(n.split()) >= 3,
        "name_all_upper": bool(letters) and all(c.isupper() for c in letters), "name_all_lower": bool(letters) and all(c.islower() for c in letters),
        "name_has_digit": any(c.isdigit() for c in n), "name_non_ascii": any(ord(c) > 127 for c in n),
        "name_emoji": any(unicodedata.category(c) == "So" for c in n), "name_punct": any(c in "!?.,-_$#@&*'\"/:" for c in n),
        "sym_eq_name": s.lower() == n.lower(), "sym_in_name": bool(s) and s.lower() in n.lower(),
        "sym_has_digit": any(c.isdigit() for c in s), "sym_starts_$": s.startswith("$"),
        "double_letter": bool(re.search(r"(.)\1", n.lower())), "vowel_ratio<0.25": bool(letters) and sum(c.lower() in "aeiou" for c in letters) / len(letters) < 0.25,
    }
    for w in COMMON:
        f["word_" + w] = w in n.lower().split() or (len(w) >= 4 and w in n.lower())
    return f


def stats(v):
    if not v:
        return "n=0"
    ex = sorted(v)[:-3] if len(v) > 15 else v
    return f"n={len(v):4} mean {st.mean(v):+.2%} med {st.median(v):+.2%} ex3 {st.mean(ex):+.2%}"


night, _ = load("night")
fresh, _ = load("fresh")
print(f"night {len(night)} launches, fresh {len(fresh)}; names found night {sum(bool(o['name']) for o in night)}, fresh {sum(bool(o['name']) for o in fresh)}")
for label, flt in [("ALL base launches", lambda o: True),
                   ("RULE #2 (bundle 3-5 SOL & lunar)", lambda o: 3.0 <= o["gsol"] <= 5.0 and o.get("ctip_label") == "lunar")]:
    N = [o for o in night if flt(o)]
    Fr = [o for o in fresh if flt(o)]
    print(f"\n===== {label}: night {len(N)}, fresh {len(Fr)} =====")
    for mdl in ("pn_ours", "pn_landx"):
        print(f"-- model {mdl}: baseline night {stats([o[mdl] for o in N])} | fresh {stats([o[mdl] for o in Fr])}")
    keys = list(feats(N[0]).keys()) if N else []
    rows = []
    tried = 0
    for k in keys:
        for keep in (False, True):          # keep=False: REMOVE launches with the feature; keep=True: keep only them
            tried += 1
            fn = (lambda o, k=k, keep=keep: feats(o)[k] == keep)
            sn = [o["pn_landx"] for o in N if fn(o)]
            sf = [o["pn_landx"] for o in Fr if fn(o)]
            if len(sn) < 25 or len(sf) < 25:
                continue
            base_n = st.mean(o["pn_landx"] for o in N)
            base_f = st.mean(o["pn_landx"] for o in Fr)
            rows.append((st.mean(sn) - base_n, st.mean(sf) - base_f, ("keep only " if keep else "remove ") + k, sn, sf))
    rows.sort(key=lambda x: -x[0])
    print(f"name/symbol rules tried: {tried} (LANDX model; lift vs that set's baseline, fit on NIGHT, judged on FRESH)")
    print(f"  {'rule':34} {'night lift':>10} {'FRESH lift':>10} | night / fresh")
    for a, b, nm, sn, sf in rows[:12]:
        print(f"  {nm:34} {a:+10.2%} {b:+10.2%} | {stats(sn)} / {stats(sf)}")
    both = [r for r in rows if r[0] > 0.005 and r[1] > 0.005]
    print(f"  rules improving BOTH night and fresh by >0.5 pt: {len(both)} -> " + ", ".join(r[2] for r in both[:10]))
    # length ranges the owner asked about (name length between a and b chars)
    print("  name-length windows (keep only lengths a..b), LANDX mean night / fresh:")
    for a, b in itertools.product([1, 2, 3, 4], [8, 10, 12, 16]):
        sn = [o["pn_landx"] for o in N if a <= len(o["name"]) <= b]
        sf = [o["pn_landx"] for o in Fr if a <= len(o["name"]) <= b]
        if len(sn) >= 25 and len(sf) >= 25:
            print(f"    {a:2}..{b:2}: night {st.mean(sn):+.2%} (n={len(sn)}) | fresh {st.mean(sf):+.2%} (n={len(sf)})")
