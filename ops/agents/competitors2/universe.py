#!/usr/bin/env python3
# competitors2/universe.py -- READ-ONLY. Dip races over every dump our engines logged (runs r5..r10 + ams_r9/r10 windows,
# 10-24 06:50 -> 23:34 PKT): per wallet, its FIRST buy attempt after each dump (slot S or S+1; ok or failed), position,
# same-slot rate, first-buyer rate, relay / priority / CU by leader kind, and whether it already had txs on that mint just
# before the dump (pre-positioned). Two universes: ALL dumps and PICKS (dumps our selector passed = the trades we want).
# Out: /home/moiz/sniper-data/competitors2/universe_wallets.json + printed tables.
import json, gzip, collections, statistics, sys
RACES = "/home/moiz/sniper-data/competitors2/races.jsonl.gz"
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
def relay(r): return "+".join(sorted({t[0] for t in r["tips"]})) or "none"
def med(x): return statistics.median(x) if x else None
def new(): return dict(att=0, ok=0, first=0, firstatt=0, top3=0, s0=0, di=[], pre=0, err=collections.Counter(), relay=collections.Counter(),
                       kind=collections.Counter(), kind_first=collections.Counter(), kind_relay=collections.defaultdict(collections.Counter),
                       kind_di=collections.defaultdict(list), cup=[], cul=[], cu=[], tip=[], own=collections.Counter(), ixn=collections.Counter(),
                       copies=[], ns=collections.Counter(), cb_none=0, beat_us=0, picks=0, pick_first=0, near=collections.Counter())
U = {"all": collections.defaultdict(new), "picks": collections.defaultdict(new)}
NR = collections.Counter(); first_by_kind = collections.defaultdict(collections.Counter); firstrel_by_kind = collections.defaultdict(collections.Counter)
for l in gzip.open(RACES, "rt"):
    R = json.loads(l); S = R["s"]; dumper = R["dump"]["w"]; kind = R["li"].get("kind", "?")
    pre_w = {b["w"] for b in R["before"] if b["s"] >= S - 1}
    att = {}; cnt = collections.Counter()
    for a in R["after"]:
        if a["s"] > S + 1 or a["w"] == dumper: continue
        if a["side"] not in ("B", "O"): continue
        if a["side"] == "O" and a["err"] is None: continue          # non-trade successful tx (e.g. no-op): skip
        cnt[a["w"]] += 1
        if a["w"] not in att: att[a["w"]] = a
    oks = [a for a in R["after"] if a["s"] <= S + 1 and a["side"] == "B" and a["err"] is None and a["w"] != dumper]
    firstok = oks[0]["w"] if oks else None; top3 = [a["w"] for a in oks[:3]]
    firstatt = next(iter(att), None)
    usk = next((a for a in R["after"] if a["w"] in US), None)
    for uni in ("all", "picks"):
        if uni == "picks" and not R.get("pas"): continue
        NR[uni] += 1; NR[uni + "_" + kind] += 1
        if uni == "all" and oks:
            first_by_kind[kind][firstok] += 1; firstrel_by_kind[kind][relay(oks[0])] += 1
        for w, a in att.items():
            d = U[uni][w]; d["att"] += 1; d["kind"][kind] += 1
            okb = a["err"] is None and a["side"] == "B"; d["ok"] += okb
            if a["err"]: d["err"][a["err"].split("@")[0]] += 1
            if a["s"] == S: d["s0"] += 1; d["di"].append(a["i"] - R["dump"]["i"]); d["kind_di"][kind].append(a["i"] - R["dump"]["i"])
            if w in pre_w: d["pre"] += 1
            d["relay"][relay(a)] += 1; d["kind_relay"][kind][relay(a)] += 1
            d["cup"].append(a["cup"] or 0); d["cul"].append(a["cul"] or 0); d["cu"].append(a["cu"] or 0); d["tip"].append(sum(t[1] for t in a["tips"]))
            if a["cup"] is None: d["cb_none"] += 1
            for p in a["own"]: d["own"][p[:8]] += 1
            d["ixn"][" ".join(x for x in a["ixn"] if x)[:60]] += 1
            d["copies"].append(cnt[w]); d["ns"][a["ns"]] += 1
            if w == firstok: d["first"] += 1; d["kind_first"][kind] += 1
            if w == firstatt: d["firstatt"] += 1
            if w in top3: d["top3"] += 1
            if usk and (a["s"], a["i"]) < (usk["s"], usk["i"]): d["beat_us"] += 1
            d["near"]["fra" if R["li"].get("near_fra") else ("ams" if R["li"].get("near_ams") else "far")] += 1

out = {}
for uni in ("all", "picks"):
    W = U[uni]; n = NR[uni]
    print(f"\n===== universe {uni}: {n} dumps (" + ", ".join(f"{k.split('_', 1)[1]} {v}" for k, v in sorted(NR.items()) if k.startswith(uni + "_")) + ")")
    print(f"{'wallet':10s} {'att':>5s} {'ok%':>4s} {'1st':>5s} {'1st%':>5s} {'top3':>5s} {'S0%':>4s} {'di_med':>6s} {'pre%':>4s} {'cpy':>4s} "
          f"{'cup_med':>7s} {'cul':>6s} {'cu':>6s} {'tip_med':>8s}  relays / own programs")
    rows = sorted(W.items(), key=lambda x: -x[1]["first"])[:40]
    for w, d in rows:
        tag = " (US)" if w in US else ""
        print(f"{w[:9]:10s} {d['att']:5d} {100 * d['ok'] / d['att']:4.0f} {d['first']:5d} {100 * d['first'] / n:5.1f} {d['top3']:5d} {100 * d['s0'] / d['att']:4.0f} "
              f"{(med(d['di']) if d['di'] else -1):6.0f} {100 * d['pre'] / d['att']:4.0f} {statistics.mean(d['copies']):4.1f} "
              f"{med(d['cup']) / 1e6:6.2f}M {med(d['cul']):6.0f} {med(d['cu']):6.0f} {med(d['tip']) / 1e9:8.5f}  "
              f"{', '.join(f'{k} {v}' for k, v in d['relay'].most_common(4))} | {', '.join(f'{k} {v}' for k, v in d['own'].most_common(2))}{tag}")
    out[uni] = {w: dict(att=d["att"], ok=d["ok"], first=d["first"], firstatt=d["firstatt"], top3=d["top3"], s0=d["s0"], di_med=med(d["di"]),
                        di_p25=(sorted(d["di"])[len(d["di"]) // 4] if d["di"] else None), pre=d["pre"], copies=statistics.mean(d["copies"]),
                        cup_med=med(d["cup"]), cul_med=med(d["cul"]), cu_med=med(d["cu"]), tip_med=med(d["tip"]), cb_none=d["cb_none"],
                        err=dict(d["err"]), relay=dict(d["relay"]), kind=dict(d["kind"]), kind_first=dict(d["kind_first"]),
                        kind_relay={k: dict(v) for k, v in d["kind_relay"].items()}, kind_di={k: med(v) for k, v in d["kind_di"].items()},
                        own=dict(d["own"]), ixn=dict(d["ixn"].most_common(5)), ns=dict(d["ns"]), beat_us=d["beat_us"], near=dict(d["near"]))
                for w, d in W.items() if d["att"] >= 5}
print("\n===== first successful buyer after the dump, by leader kind (all dumps): top wallets and relays")
for k, c in sorted(first_by_kind.items(), key=lambda x: -sum(x[1].values())):
    n = sum(c.values())
    print(f"  {k:9s} n={n:5d}  wallets: " + ", ".join(f"{(w or '?')[:8]} {100 * v / n:.0f}%" for w, v in c.most_common(8)))
    print(f"  {'':9s}          relays : " + ", ".join(f"{r} {100 * v / n:.0f}%" for r, v in firstrel_by_kind[k].most_common(8)))
json.dump(out, open("/home/moiz/sniper-data/competitors2/universe_wallets.json", "w"))
