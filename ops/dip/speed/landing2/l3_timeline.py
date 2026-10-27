#!/usr/bin/env python3
# LANDING2 step 3 (read-only): one timeline per nonce-era fire, on three clocks.
#  WALL (our server, ns): dump first sighting (any feed) -> executed feed -> fire -> first write per path -> relay ack -> our tx first seen
#  BLOCK (chain, getBlock real sizes): dump (slot, idx / N) -> every rival buy -> our tx; 212 ms per slot (engine-measured 212.2)
#  FEED (exec-feed tape): rivals' trades as our executed feed delivered them, vs the dump's arrival on the same feed
# + leader client, TPU front (own / Jito relayer / BAM node / Harmonic relay), window slot, dump position quartile, guard what-ifs.
# Output: OUT/timeline.json
import json, collections, sys, os

OUT = "/home/moiz/sniper-data/landing2"
SMS = 212.0
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
PROS = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7hMjy", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqiUUX",
        "G9G3dCBGjM1chfZJHvb722zzzm9FQfZi4KbLVGncGeTy": "G9G3dCBG", "5w8xtjc649Z628jVvJkwQE5p9aMhV2cUSWr8RVV9BieU": "5w8xtjc6",
        "6n2cCJrrEAi4SZbBquj9mffUGAFXhDBmFeQEi3maSRcx": "6n2cCJrr", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC4ngp",
        "9k78QZywYyqUZvZrk1tDuE9qPUbZAz2aFbjUneihdgFX": "9k78QZyw", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC",
        "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx": "CZ77onJz", "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx": "6VzXcLk9"}
COHORT = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/cohort_R1.json")))
BUYIX = {"Buy", "BuyExactSolIn", "BuyExactQuoteIn", "BuyExactQuoteInV2", "BuyV2", "BuyV3"}
INSTANT_IDX = 3


def client_class(c):
    if not c: return "?"
    if "Harmonic" in c: return "harmonic"
    if c == "FireBAM": return "firebam"
    if "Bam" in c or "BAM" in c: return "bam"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    if c == "Rakurai": return "rakurai"
    return "other"


def front(l):
    """the leader's TPU front from its gossip record: relayer (Jito :11228), bam-node, harmonic-relay, own"""
    if not l or not l.get("tpu_quic") or not l["tpu_quic"][0]: return "?"
    c = l.get("client") or ""; ip, port = l["tpu_quic"]; g = (l.get("gossip") or [None])[0]
    if "Bam" in c or c == "FireBAM": return "bam-node"
    if "Harmonic" in c: return "harmonic-relay" if ip != g else "own"
    if port == 11228: return "relayer"
    return "own" if ip == g else "other-host"


def out_tokens(vsol, vtok, spend, fr):
    xin = int(spend / (1.0 + fr))
    return vtok * xin // (vsol + xin)


def main():
    fires = json.load(open(f"{OUT}/fires_engine.json"))
    txs = json.load(open(f"{OUT}/chain_txs.json"))
    sstat = {int(k): v for k, v in json.load(open(f"{OUT}/slot_stats.json")).items()}
    bsz = {int(k): v for k, v in json.load(open(f"{OUT}/block_sizes.json")).items() if isinstance(v, int)}
    tg = json.load(open(f"{OUT}/targets.json"))["leaders"]
    sch = json.load(open("/home/moiz/sniper-data/competitors2/schedule_1067.json"))
    ids, sl0, sl = sch["ids"], sch["start"], sch["slot_leader"]
    lead = lambda s: ids[sl[s - sl0]] if 0 <= s - sl0 < len(sl) and sl[s - sl0] is not None else None

    def size(s):
        if s in bsz: return bsz[s], "real"
        if s in sstat: return sstat[s][1] + 1, "maxidx"
        return None, None

    def bclock(s, i):          # block-position clock, real block size (fallback: max pump index + 1, then 400)
        n, _ = size(s)
        return s * SMS + i / max(n or 400, i + 1) * SMS

    def b400(s, i): return s * SMS + i / max(400, i + 1) * SMS

    # monotonic -> realtime offset per server: intersect the brackets [t_p1 - min t0, t_fire - max t1] over fires
    lo, hi = collections.defaultdict(lambda: -1e30), collections.defaultdict(lambda: 1e30)
    for a in fires:
        w = a["writes"]
        if not w: continue
        tp1 = a["t_fire"] - a["lat_us"]["fire"] * 1000
        lo[a["srv"]] = max(lo[a["srv"]], tp1 - min(x["t0"] for x in w))
        hi[a["srv"]] = min(hi[a["srv"]], a["t_fire"] - max(x["t1"] for x in w))
    off = {s: (lo[s] + hi[s]) / 2 for s in lo}
    print("mono->real offset bracket width (us):", {s: round((hi[s] - lo[s]) / 1e3, 1) for s in lo})
    by_sig = {t["sig"]: t for t in txs}
    by_mint = collections.defaultdict(list)
    for t in txs:
        for m in t["mints"]: by_mint[m].append(t)
    rows = []
    for a in fires:
        r = {k: a[k] for k in ("srv", "run", "base", "mint", "dump_sig", "buy_sig", "leader", "client", "route", "paths", "spend", "filled", "result",
                               "decision_us", "lat_us", "tips", "dev")}
        tm = a["timing"]; srv = a["srv"]; mint = a["mint"]
        t_first = tm.get("dump_first_rx") or a["t_dump_rx"]
        W = dict(first_feed=tm.get("dump_first_feed"), exec_wait=(a["t_dump_rx"] - t_first) / 1e6, decision=a["decision_us"] / 1e3,
                 fire=(a["t_fire"] - t_first) / 1e6)
        wr = {}
        tips = {v["path"]: v.get("tip") for v in a["per_path"] or []}
        for w in a["writes"] or []:
            wr[w["path"]] = dict(t0=(w["t0"] + off[srv] - t_first) / 1e6, t1=(w["t1"] + off[srv] - t_first) / 1e6, kind=w["kind"], st=w["st"], tip=tips.get(w["path"]))
        W["writes"] = wr
        W["first_write"] = min((x["t0"] for x in wr.values()), default=None)
        W["last_write"] = max((x["t1"] for x in wr.values()), default=None)
        W["seen"] = (tm["buy_first_rx"] - t_first) / 1e6 if tm.get("buy_first_rx") else None
        W["seen_feed"] = tm.get("buy_first_feed")
        W["send_to_seen"] = (W["seen"] - W["first_write"]) if (W["seen"] is not None and W["first_write"] is not None) else None
        acks = {}
        for x in a["acks"]: acks.setdefault(x["path"], dict(ack_ms=x["ack_ms"], status=x["status"]))
        W["acks"] = acks
        if tm.get("clock2"): W["clock2"] = tm["clock2"]
        r["W"] = W
        # ---------------- chain
        C = dict(found_dump=False, found_ours=False)
        d = by_sig.get(a["dump_sig"])
        if d:
            C["found_dump"] = True
            sd, idd = d["s"], d["i"]
            de_l = [e for e in d["tr"] if e["mint"] == mint and not e["buy"]]
            de = max(de_l, key=lambda e: e["sol"]) if de_l else None
            jd = d["tr"].index(de) if de else 0
            nd, nsrc = size(sd)
            C.update(dump_slot=sd, dump_idx=idd, dump_n=nd, dump_n_src=nsrc, dump_pos=(idd / nd) if nd else None, dump_sol=de["sol"] if de else None,
                     dump_user=de["user"] if de else None, dump_tips=d["tips"])
            fr = max((de["fbps"] + de["cbps"]) if de else 0, 1) / 1e4
            ours = [by_sig[s] for s in a["sigs"] if s in by_sig]
            C["ours_landed_n"] = len(ours)
            if ours:
                o = min(ours, key=lambda t: (t["s"], t["i"]))
                path = next((v["path"] for v in a["per_path"] or [] if v.get("sig") == o["sig"]), None)
                no, osrc = size(o["s"])
                C.update(found_ours=True, our_slot=o["s"], our_idx=o["i"], our_n=no, our_n_src=osrc, our_ok=o["err"] is None, our_err=o["err"],
                         our_cup=o["cup"], our_fee=o["fee"], our_tips=o["tips"], our_path=path, our_tip=tips.get(path), our_sig=o["sig"],
                         slot_delta=o["s"] - sd, our_ms=bclock(o["s"], o["i"]) - bclock(sd, idd), our_ms_b400=b400(o["s"], o["i"]) - b400(sd, idd))
                # the slot's remaining time at the dump (block clock) -> spill analysis
            C["left_ms"] = (1 - idd / max(nd or 400, idd + 1)) * SMS
            end_s = (C.get("our_slot") or sd + 1) + 2
            win = [t for t in by_mint.get(mint, []) if (t["s"], t["i"]) >= (sd, idd) and t["s"] <= end_s]
            # curve states after the dump, our own buy's impact removed (what-if landings must not see it)
            states = []; dv = dt_ = 0; prev = None
            for t in win:
                if t["err"] is not None: continue
                for j, e in enumerate(t["tr"]):
                    if e["mint"] != mint: continue
                    if (t["s"], t["i"], j) < (sd, idd, jd): prev = e; continue
                    if t["ours"] and e["buy"] and prev is not None:
                        dv += e["vsol"] - prev["vsol"]; dt_ += prev["vtok"] - e["vtok"]; prev = e; continue
                    prev = e
                    states.append((t["s"], t["i"], j, dict(e, vsol=e["vsol"] - dv, vtok=e["vtok"] + dt_) if (dv or dt_) else e))
            mo = a["min_out"]
            ev = [(s, i, j, out_tokens(e["vsol"], e["vtok"], a["spend"], fr) >= mo, e) for s, i, j, e in states]
            C["guard_at_dump"] = ev[0][3] if ev else None
            if C.get("found_ours"):
                pos = (C["our_slot"], C["our_idx"])
                before = [x for x in ev if (x[0], x[1]) < pos]
                C["pred_pass"] = before[-1][3] if before else None
                first = next((x for x in ev if not x[3]), None)
                if first: C.update(first_cross_ms=bclock(first[0], first[1]) - bclock(sd, idd), first_cross_user=first[4]["user"], first_cross_slot=first[0] - sd)
            # what-if: would the guard pass if our buy landed d ms after the dump (block clock, real sizes)?
            gw = {}
            for dms in (0, 2, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 100, 150, 212, 300):
                tgt = bclock(sd, idd) + dms
                bef = [x for x in ev if bclock(x[0], x[1]) <= tgt]
                gw[dms] = bef[-1][3] if bef else True
            C["guard_at_ms"] = gw
            # the exact guard sequence on the block clock: (ms after the dump, passes after that trade) -> what-ifs at any delay
            C["gms"] = [(round(bclock(x[0], x[1]) - bclock(sd, idd), 3), x[3]) for x in ev]
            # rivals: every other buy attempt on the token after the dump (ok, or failed with a buy instruction / slippage error)
            riv = []
            for t in win:
                if (t["s"], t["i"]) <= (sd, idd) or t["ours"]: continue
                b = [e for e in t["tr"] if e["mint"] == mint and e["buy"]]
                if t["err"] is None and not b: continue
                if t["err"] is not None and not (set(t["ixn"] or []) & BUYIX) and "6042" not in json.dumps(t["err"]) and "6002" not in json.dumps(t["err"]): continue
                user = b[0]["user"] if b else t["signer"]
                riv.append(dict(s=t["s"], i=t["i"], ms=bclock(t["s"], t["i"]) - bclock(sd, idd), ds=t["s"] - sd, di=(t["i"] - idd) if t["s"] == sd else None,
                                user=user, ok=t["err"] is None, sol=sum(e["sol"] for e in b), tips=t["tips"], cup=t["cup"],
                                ahead=bool(C.get("found_ours") and (t["s"], t["i"]) < (C["our_slot"], C["our_idx"]))))
            C["rivals"] = riv
        r["C"] = C
        # ---------------- feed clock (executed feed tape): rivals' first trade arrival vs the dump's arrival on the same feed
        F = {}
        for x in a.get("tape") or []:
            if not x["buy"] or x["user"] in OURS: continue
            ms = (x["t"] - a["t_dump_rx"]) / 1e6
            if ms <= 0 or (x["slot"], x["idx"]) <= (C.get("dump_slot", 0), C.get("dump_idx", 0)): continue
            F.setdefault(x["user"], ms)
        r["F"] = F
        r["our_feed_ms"] = ((tm["buy_first_rx"] - t_first) / 1e6) if tm.get("buy_first_rx") else None
        # ---------------- leader
        sdump = C.get("dump_slot", a["dump_slot"])
        ld = a["leader"]; k = 0
        while k < 8 and lead(sdump - k - 1) == ld: k += 1
        r["L"] = dict(cls=client_class(a["client"]), front=front(tg.get(ld)), window_slot=k + 1, sched_ok=lead(sdump) == ld,
                      our_leader=lead(C["our_slot"]) if C.get("found_ours") else None)
        rows.append(r)
    json.dump(rows, open(f"{OUT}/timeline.json", "w"))
    ok = [r for r in rows if r["C"].get("found_ours")]
    print(f"fires {len(rows)} | dump found {sum(r['C']['found_dump'] for r in rows)} | our tx found {len(ok)} | sched leader ok {sum(r['L']['sched_ok'] for r in rows)}")
    print(f"engine filled == chain ok: {sum(1 for r in ok if r['C']['our_ok'] == r['filled'])}/{len(ok)}")
    pr = [r for r in ok if r["C"].get("pred_pass") is not None]
    print(f"guard model == chain: {sum(1 for r in pr if r['C']['pred_pass'] == r['C']['our_ok'])}/{len(pr)} | post-dump state passes "
          f"{sum(1 for r in rows if r['C'].get('guard_at_dump'))}/{sum(1 for r in rows if r['C'].get('guard_at_dump') is not None)}")
    print("block size source (dump):", collections.Counter(r["C"].get("dump_n_src") for r in rows), "(ours):", collections.Counter(r["C"].get("our_n_src") for r in ok))


if __name__ == "__main__":
    main()
