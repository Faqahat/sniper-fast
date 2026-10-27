#!/usr/bin/env python3
# competitors2/fires.py -- READ-ONLY. Our fires (runs r5..r10 FRA + ams_r9/r10) against the chain: for every fire, all txs on
# the mint between the dump and our buy, the curve replayed from the dump's post-trade reserves with OUR min_out to find the
# tx that pushed the price past our +5% guard ("crosser"), and every rival that landed ahead of us.
# Out: /home/moiz/sniper-data/competitors2/fires.json + printed per-wallet table.
import json, gzip, collections, statistics, sys, datetime
RACES = "/home/moiz/sniper-data/competitors2/races.jsonl.gz"
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
pk = lambda ns: datetime.datetime.fromtimestamp(ns / 1e9 + 5 * 3600, datetime.UTC).strftime("%m-%d %H:%M:%S")
def ok(r): return r["err"] is None
def relay(r): return "+".join(sorted({t[0] for t in r["tips"]})) or "none"
def tipsum(r): return sum(t[1] for t in r["tips"])
def out_tokens(x, v, t): return t - v * t // (v + x)

fires = []
for l in gzip.open(RACES, "rt"):
    R = json.loads(l)
    if not R["fires"]: continue
    for f in R["fires"]:
        A = R["after"]; k = next((j for j, a in enumerate(A) if a["sig"] == f["buy_sig"]), None)
        if k is None: continue
        us = A[k]; dtr = R["dump"]["tr"]
        # solve the engine's net SOL input x from min_out at the dump's post-trade state (min_out = out(x) / 1.05)
        v0, t0 = dtr[4], dtr[5]; T = f["min_out"] * 1.05
        x = int(v0 * t0 / (t0 - T) - v0) if t0 > T else None
        state = (v0, t0); cross = None; ahead = []; attempts = []
        for j, a in enumerate(A[:k]):
            if a["w"] in US: continue
            attempts.append(a)
            if ok(a) and a["tr"]:
                state = (a["tr"][4], a["tr"][5])
                if a["side"] == "B": ahead.append(a)
                if cross is None and x and out_tokens(x, *state) < f["min_out"]: cross = a
        margin = None
        if x: margin = out_tokens(x, *state) / f["min_out"] - 1      # >0: our min_out still satisfied at our turn
        same = us["s"] == R["s"]
        fires.append(dict(run=f["run"], region=f["region"], t=pk(f["t_fire"]), mint=R["m"], S=R["s"], leader=R["leader"],
            client=R["li"].get("client"), kind=R["li"].get("kind"), city=R["li"].get("city"), route=f["route"], fill=f["fill"],
            us_err=us["err"], us_ds=us["s"] - R["s"], us_di=(us["i"] - R["dump"]["i"]) if same else None, us_i=us["i"], dump_i=R["dump"]["i"],
            margin=margin, f2s=f["f2s"], cross=(cross["w"] if cross else None), cross_sig=(cross["sig"] if cross else None),
            ahead=[dict(w=a["w"], ds=a["s"] - R["s"], di=(a["i"] - R["dump"]["i"]) if a["s"] == R["s"] else None, relay=relay(a),
                        tip=tipsum(a), cup=a["cup"], cul=a["cul"], cu=a["cu"], sig=a["sig"], sol=(a["tr"][0] if a["tr"] else None)) for a in ahead],
            attempts=[dict(w=a["w"], ds=a["s"] - R["s"], di=(a["i"] - R["dump"]["i"]) if a["s"] == R["s"] else None, ok=ok(a), err=a["err"],
                           side=a["side"], relay=relay(a), cup=a["cup"]) for a in attempts],
            us_cup=us["cup"], us_cul=us["cul"], us_cu=us["cu"], us_tip=tipsum(us), us_relay=relay(us), sell=R.get("sell"), dump_sig=R["sig"],
            buy_sig=f["buy_sig"], tape=f["tape"], t_dump_rx=f["t_dump_rx"], buy_first_rx=f["buy_first_rx"]))
json.dump(fires, open("/home/moiz/sniper-data/competitors2/fires.json", "w"))

F = [f for f in fires if not f["fill"]]; G = [f for f in fires if f["fill"]]
print(f"fires with chain rows: {len(fires)}  failed {len(F)}  filled {len(G)}")
print("our tx error codes on failed fires:", collections.Counter(f["us_err"] for f in F).most_common())
print("replay check (margin<0 means guard should fail): failed with margin<0:", sum(1 for f in F if f["margin"] is not None and f["margin"] < 0),
      "/", len(F), "; filled with margin>=0:", sum(1 for f in G if f["margin"] is not None and f["margin"] >= 0), "/", len(G))
print("failed fires where a crosser was found:", sum(1 for f in F if f["cross"]))
for lab, X in (("FAILED", F), ("FILLED", G)):
    print(f"\n{lab}: our landing: same slot {sum(1 for f in X if f['us_ds'] == 0)}/{len(X)}, median di (same slot) "
          f"{statistics.median([f['us_di'] for f in X if f['us_di'] is not None] or [0])}; rival ok buys ahead median "
          f"{statistics.median([len(f['ahead']) for f in X]) if X else 0}, dist {collections.Counter(min(len(f['ahead']), 9) for f in X).most_common()}")

# per-wallet table over FAILED fires
W = collections.defaultdict(lambda: dict(ahead=0, cross=0, first=0, att=0, di=[], ds0=0, n=0, relays=collections.Counter(), cups=[], fail_reg=collections.Counter(), cul=[]))
for f in F:
    seen = set()
    for j, a in enumerate(f["ahead"]):
        w = W[a["w"]]
        if a["w"] in seen: continue
        seen.add(a["w"]); w["ahead"] += 1; w["relays"][a["relay"]] += 1; w["cups"].append(a["cup"] or 0); w["cul"].append(a["cul"] or 0)
        w["fail_reg"][f["region"]] += 1
        if a["di"] is not None: w["di"].append(a["di"]); w["ds0"] += 1
        if j == 0: w["first"] += 1
    if f["cross"]: W[f["cross"]]["cross"] += 1
    for a in {a["w"]: a for a in f["attempts"]}.values(): W[a["w"]]["att"] += 1
print(f"\nWHO BEAT US on {len(F)} failed fires (ahead = landed an ok buy between the dump and our buy; cross = the buy that pushed price past our +5%):")
print(f"{'wallet':10s} ahead cross first  att  sameslot  med_di  relays (ahead buys)                  cup_med   cul_med  FRA/AMS")
for w, d in sorted(W.items(), key=lambda x: (-x[1]["ahead"], -x[1]["cross"]))[:30]:
    if d["ahead"] == 0: continue
    print(f"{w[:9]:10s} {d['ahead']:5d} {d['cross']:5d} {d['first']:5d} {d['att']:4d}  {d['ds0']:3d}/{d['ahead']:<3d}  "
          f"{(statistics.median(d['di']) if d['di'] else -1):6.0f}  {', '.join(f'{k} {v}' for k, v in d['relays'].most_common(3)):36s} "
          f"{statistics.median(d['cups']) / 1e6:6.2f}M {statistics.median(d['cul']):8.0f}  {d['fail_reg']['FRA']}/{d['fail_reg']['AMS']}")
