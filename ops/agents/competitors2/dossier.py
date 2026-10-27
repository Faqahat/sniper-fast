#!/usr/bin/env python3
# competitors2/dossier.py -- READ-ONLY. One dossier per competitor wallet from the race records (all 21.6k dumps):
# reaction stats, relays of LANDED (ok) txs by leader kind with tip sizes, priority / CU limit vs used, error codes,
# copies per dump, pre-positioning, own programs, leaders where it is first most often; joined with the RPC tx shapes
# (txshape.jsonl: size, nonce, ALT, loaded-data limit, cost units) and the feed timing (timing_wallets.json).
# usage: python3 -I dossier.py  -> /home/moiz/sniper-data/competitors2/dossier.json + dossier.txt
import json, gzip, collections, statistics, os
D2 = "/home/moiz/sniper-data/competitors2"
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "US-FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "US-AMS"}
F = json.load(open(f"{D2}/fires.json"))
# wallet list: everyone ahead of us >= 3 times or crossing us >= 2, plus the universe's top first-buyers
cnt = collections.Counter(); crs = collections.Counter()
for f in F:
    if f["fill"]: continue
    for w in {a["w"] for a in f["ahead"]}: cnt[w] += 1
    if f["cross"]: crs[f["cross"]] += 1
UW = json.load(open(f"{D2}/universe_wallets.json"))
top_first = [w for w, d in sorted(UW["all"].items(), key=lambda x: -x[1]["first"])[:25]]
top_picks = [w for w, d in sorted(UW["picks"].items(), key=lambda x: -x[1]["first"])[:15]]
WL = list(dict.fromkeys([w for w, n in cnt.most_common() if n >= 3] + [w for w, n in crs.items() if n >= 2] + top_first + top_picks + list(US)))
WS = set(WL)
def q(x, p): x = sorted(x); return x[min(len(x) - 1, int(p * len(x)))] if x else None
def med(x): return statistics.median(x) if x else None
def relay(r): return "+".join(sorted({t[0] for t in r["tips"]})) or "none"
st = {w: dict(att=0, ok=0, first=0, s0=0, s1=0, di=[], pre=0, copies=[], err=collections.Counter(), okrel=collections.defaultdict(collections.Counter),
              tipamt=collections.defaultdict(list), cup=[], cul=[], cu=[], cbnone=0, own=collections.Counter(), ixn=collections.Counter(), ns=collections.Counter(),
              kind_att=collections.Counter(), kind_first=collections.Counter(), kind_di=collections.defaultdict(list), lead_att=collections.Counter(),
              lead_first=collections.Counter(), pre_n=[], size_hint=[], fail_cost=[], h2h=[0, 0], sell_after=[]) for w in WL}
lead_kind = {}
for l in gzip.open(f"{D2}/races.jsonl.gz", "rt"):
    R = json.loads(l); S = R["s"]; dumper = R["dump"]["w"]; kind = R["li"].get("kind", "?"); ld = R["leader"]; lead_kind[ld] = kind
    pre = collections.Counter(b["w"] for b in R["before"] if b["s"] >= S - 1 and b["w"] in WS)
    att = {}; cp = collections.Counter()
    for a in R["after"]:
        if a["s"] > S + 1 or a["w"] == dumper or a["w"] not in WS: continue
        if a["side"] not in ("B", "O") or (a["side"] == "O" and a["err"] is None): continue
        cp[a["w"]] += 1; att.setdefault(a["w"], a)
    oks = [a for a in R["after"] if a["s"] <= S + 1 and a["side"] == "B" and a["err"] is None and a["w"] != dumper]
    firstok = oks[0]["w"] if oks else None
    usa = [a for a in R["after"] if a["w"] in US and a["s"] <= S + 1]
    for w, a in att.items():
        d = st[w]; d["att"] += 1; d["kind_att"][kind] += 1; d["lead_att"][ld] += 1
        if a["err"] is None and a["side"] == "B": d["ok"] += 1
        if a["s"] == S: d["s0"] += 1; d["di"].append(a["i"] - R["dump"]["i"]); d["kind_di"][kind].append(a["i"] - R["dump"]["i"])
        else: d["s1"] += 1
        if pre[w]: d["pre"] += 1; d["pre_n"].append(pre[w])
        d["copies"].append(cp[w])
        if a["err"]: d["err"][a["err"]] += 1; d["fail_cost"].append(a["fee"] or 0)
        d["cup"].append(a["cup"] or 0); d["cul"].append(a["cul"] or 0); d["cu"].append(a["cu"] or 0); d["cbnone"] += a["cup"] is None
        for p in a["own"]: d["own"][p] += 1
        d["ixn"][" ".join(x for x in a["ixn"] if x)[:80]] += 1; d["ns"][a["ns"]] += 1
        if w == firstok: d["first"] += 1; d["kind_first"][kind] += 1; d["lead_first"][ld] += 1
        if usa and w not in US:
            u = usa[0]; d["h2h"][0 if (a["s"], a["i"]) < (u["s"], u["i"]) else 1] += 1
    # relays / tips of every LANDED buy by these wallets in S..S+1 (not only the first attempt)
    for a in oks:
        if a["w"] in WS:
            r = relay(a); st[a["w"]]["okrel"][kind][r] += 1
            for t in a["tips"]: st[a["w"]]["tipamt"][t[0]].append(t[1])
# RPC tx shapes
shape = collections.defaultdict(list)
if os.path.exists(f"{D2}/txshape.jsonl"):
    for l in open(f"{D2}/txshape.jsonl"):
        t = json.loads(l)
        if t.get("missing") or t.get("decode_error"): continue
        shape[t["signers"][0]].append(t)
TW = json.load(open(f"{D2}/timing_wallets.json")) if os.path.exists(f"{D2}/timing_wallets.json") else {}
out = {}; lines = []
for w in WL:
    d = st[w]
    if d["att"] == 0: continue
    T = shape.get(w, [])
    rel = {k: dict(v.most_common(5)) for k, v in d["okrel"].items()}
    nok = sum(sum(v.values()) for v in d["okrel"].values())
    relall = collections.Counter()
    for v in d["okrel"].values(): relall.update(v)
    colo = [(l, d["lead_first"][l], n) for l, n in d["lead_att"].items() if n >= 8 and d["lead_first"][l] / n >= 0.4]
    tm = TW.get(w, {})
    o = dict(wallet=w, tag=US.get(w, ""), ahead_of_us_in_failed=cnt.get(w, 0), crossed_our_guard=crs.get(w, 0), attempts=d["att"],
             ok_rate=round(d["ok"] / d["att"], 3), first=d["first"], same_slot=round(d["s0"] / d["att"], 3), di_p25=q(d["di"], .25), di_med=med(d["di"]),
             pre_rate=round(d["pre"] / d["att"], 3), pre_txs_med=med(d["pre_n"]), copies_mean=round(statistics.mean(d["copies"]), 2),
             h2h_vs_us=d["h2h"], err_top=dict(d["err"].most_common(4)), fail_fee_med=med(d["fail_cost"]),
             cup_p10=q(d["cup"], .1), cup_med=med(d["cup"]), cup_p90=q(d["cup"], .9), cul_med=med(d["cul"]), cu_med=med(d["cu"]), no_cb=d["cbnone"],
             okrel_all={k: round(v / nok, 3) for k, v in relall.most_common(6)} if nok else {}, okrel_by_kind=rel,
             tip_med={k: med(v) for k, v in d["tipamt"].items() if len(v) >= 3},
             kind_att=dict(d["kind_att"]), kind_first=dict(d["kind_first"]), kind_di_med={k: med(v) for k, v in d["kind_di"].items()},
             own=dict(d["own"].most_common(4)), ixn=dict(d["ixn"].most_common(3)), signers=dict(d["ns"]),
             colo_leaders=sorted(colo, key=lambda x: -x[1])[:6],
             ms_med=(med(tm.get("all", [])) if tm else None), ms_n=len(tm.get("all", [])) if tm else 0,
             ms_by_kind={k: med(v) for k, v in tm.items() if k in ("bam", "harmonic", "jito", "fd") and v} if tm else {},
             rpc_n=len(T), size_med=med([t["size"] for t in T]), nonce_share=(round(sum(t["nonce"] for t in T) / len(T), 2) if T else None),
             alt_share=(round(sum(1 for t in T if t["nalt"]) / len(T), 2) if T else None), ver=dict(collections.Counter(t["ver"] for t in T)),
             ldl=dict(collections.Counter(t["cb"].get("ldl") for t in T).most_common(2)), cost_med=med([t.get("cost") for t in T if t.get("cost")]),
             tips_per_tx=dict(collections.Counter(len(t["tips"]) for t in T)), ix_pattern=dict(collections.Counter(" ".join(t["ixs"]) for t in T).most_common(2)),
             nonce_accts=len({t["nonce_acct"] for t in T if t["nonce"]}))
    out[w] = o
json.dump(out, open(f"{D2}/dossier.json", "w"), indent=1)
for w, o in out.items():
    print(f"\n### {w} {o['tag']}  ahead-of-us {o['ahead_of_us_in_failed']}/92 failed, crossed {o['crossed_our_guard']}")
    for k in ("attempts", "ok_rate", "first", "same_slot", "di_p25", "di_med", "pre_rate", "pre_txs_med", "copies_mean", "h2h_vs_us", "err_top", "fail_fee_med",
              "cup_p10", "cup_med", "cup_p90", "cul_med", "cu_med", "no_cb", "okrel_all", "okrel_by_kind", "tip_med", "kind_first", "kind_di_med", "own", "ixn",
              "signers", "colo_leaders", "ms_med", "ms_n", "ms_by_kind", "rpc_n", "size_med", "nonce_share", "alt_share", "ver", "ldl", "cost_med", "tips_per_tx",
              "ix_pattern", "nonce_accts"):
        print(f"   {k}: {o[k]}")
