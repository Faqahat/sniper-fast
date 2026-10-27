#!/usr/bin/env python3
# SPEED TRUTH step 3 (read-only): one full timeline per live attempt (fills AND failed buys) on two clocks:
#  - our server's wall clock (engine records): dump first seen (shreds) -> executed feed -> decision -> first write per path -> our tx seen
#  - the chain's block-position clock (raw recording): dump (slot, idx) -> rivals -> the trade that pushed the price past our +5 % guard -> us
# Output: OUT/timeline.json (one row per attempt)
import json, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

OFFSET = {}          # server -> CLOCK_REALTIME - CLOCK_MONOTONIC (ns), from the writes bracketed by t_p1 .. t_fire (width < 0.15 ms)
INSTANT_IDX = 3      # a rival buy <= 3 txs after the dump in its slot (<= 1.6 ms on the block clock) = "instant" (same burst / bundle)


def offsets(att):
    lo, hi = collections.defaultdict(lambda: -1e30), collections.defaultdict(lambda: 1e30)
    for a in att:
        w = a["writes"]
        if not w: continue
        tp1 = a["t_fire"] - a["lat_us"]["fire"] * 1000
        lo[a["srv"]] = max(lo[a["srv"]], tp1 - min(x["t0"] for x in w))
        hi[a["srv"]] = min(hi[a["srv"]], a["t_fire"] - max(x["t1"] for x in w))
    return {s: (lo[s] + hi[s]) / 2 for s in lo}, {s: (hi[s] - lo[s]) / 1e3 for s in lo}


def out_tokens(vsol, vtok, spend, fr):
    xin = int(spend / (1.0 + fr))
    return vtok * xin // (vsol + xin)


def main():
    att = json.load(open(f"{tl.OUT}/attempts_engine.json"))
    txs = json.load(open(f"{tl.OUT}/chain_txs.json"))
    sstat = {int(k): v for k, v in json.load(open(f"{tl.OUT}/slot_stats.json")).items()}
    off, width = offsets(att)
    print("clock offsets (realtime - monotonic) per server, bracket width us:", {k: round(v, 1) for k, v in width.items()})
    by_sig = {t["sig"]: t for t in txs}
    by_mint = collections.defaultdict(list)
    for t in txs:
        for m in t["mints"]: by_mint[m].append(t)
    rows = []
    for a in att:
        r = dict(a)
        srv = a["srv"]; mint = a["mint"]
        tm = a["timing"]
        # ---------------- wall clock (ns -> ms relative to the dump's first sighting on any feed)
        t_first = tm.get("dump_first_rx") or a["t_dump_rx"]
        W = {}
        W["exec_wait"] = (a["t_dump_rx"] - t_first) / 1e6
        W["decision"] = a["decision_us"] / 1e3
        W["fire"] = (a["t_fire"] - t_first) / 1e6
        wr = {}
        for w in a["writes"] or []:
            t0 = (w["t0"] + off[srv] - t_first) / 1e6; t1 = (w["t1"] + off[srv] - t_first) / 1e6
            wr[w["path"]] = dict(t0=t0, t1=t1, kind=w["kind"], st=w["st"])
        W["writes"] = wr
        W["first_write"] = min((x["t0"] for x in wr.values()), default=None)
        W["last_write"] = max((x["t1"] for x in wr.values()), default=None)
        W["seen"] = (tm["buy_first_rx"] - t_first) / 1e6 if tm.get("buy_first_rx") else None
        W["fire_to_seen"] = tm.get("fire_to_seen_ms")
        W["send_to_seen"] = (W["seen"] - W["first_write"]) if (W["seen"] is not None and W["first_write"] is not None) else None
        acks = {}
        for x in a["acks"]:
            acks.setdefault(x["path"], x)
        W["acks"] = acks
        r["W"] = W
        # ---------------- chain clock
        C = dict(found_dump=False, found_ours=False)
        d = by_sig.get(a["dump_sig"])
        if d:
            C["found_dump"] = True
            sd, idd = d["s"], d["i"]
            # the dump trade inside the tx = the one whose post-state is the engine's dump_vsol / dump_vtok (else the biggest sell)
            jd = next((j for j, e in enumerate(d["tr"]) if e["mint"] == mint and e["vsol"] == a["dump_vsol"] and e["vtok"] == a["dump_vtok"]), None)
            if jd is None:
                sells = [(e["sol"], j) for j, e in enumerate(d["tr"]) if e["mint"] == mint and not e["buy"]]
                jd = max(sells)[1] if sells else 0
            de = d["tr"][jd] if d["tr"] else None
            C.update(dump_slot=sd, dump_idx=idd, dump_j=jd, dump_signer=d["signer"], dump_user=de["user"] if de else None, dump_sol=de["sol"] if de else None,
                     dump_tips=d["tips"], block_n=sstat.get(sd, [None, None])[1] + 1 if sd in sstat else None)
            fr = ((de["fbps"] + de["cbps"]) if de else 0)
            fr = max(fr, 1) / 1e4
            spend = a["spend"]
            # our landed tx (any variant)
            ours = [by_sig[s] for s in a["sigs"] if s in by_sig]
            C["ours_landed_n"] = len(ours)
            if ours:
                o = min(ours, key=lambda t: (t["s"], t["i"]))
                C["found_ours"] = True
                path = None
                for v in a["per_path"] or []:
                    if v.get("sig") == o["sig"]: path = v["path"]
                if path is None and not a["nonce"]: path = "multi(" + "+".join(sorted({p for p, _ in o["tips"]})) + ")"
                C.update(our_slot=o["s"], our_idx=o["i"], our_ok=o["err"] is None, our_err=o["err"], our_fee=o["fee"], our_cup=o["cup"], our_cu=o["cu"],
                         our_tips=o["tips"], our_path=path, our_sig=o["sig"], our_block_n=sstat.get(o["s"], [None, None])[1] + 1 if o["s"] in sstat else None)
            # every tx on the token from the dump to 2 slots after ours (or dump + 3)
            end_s = (C.get("our_slot") or sd + 1) + 2
            win = [t for t in by_mint.get(mint, []) if (t["s"], t["i"]) >= (sd, idd) and t["s"] <= end_s]
            # curve states in chain order: (s, i, j) -> post-trade (vsol, vtok); the guard check for OUR buy at each state.
            # OUR OWN buy is taken out (a what-if landing elsewhere must not see our own price impact): the states after it are
            # shifted back by what our buy added (virtual SOL in, virtual tokens out)
            states = []; dv = dt_ = 0; prev = None
            for t in win:
                if t["err"] is not None: continue
                for j, e in enumerate(t["tr"]):
                    if e["mint"] != mint: continue
                    if (t["s"], t["i"], j) < (sd, idd, jd): prev = e; continue
                    if t["ours"] and e["buy"] and prev is not None:
                        dv += e["vsol"] - prev["vsol"]; dt_ += prev["vtok"] - e["vtok"]; prev = e; continue
                    prev = e
                    e2 = dict(e, vsol=e["vsol"] - dv, vtok=e["vtok"] + dt_) if (dv or dt_) else e
                    states.append((t["s"], t["i"], j, e2, t))
            mo = a["min_out"]
            def passes(e): return out_tokens(e["vsol"], e["vtok"], spend, fr) >= mo
            ev = []        # (s, i, j, pass_after, trade, tx)
            for s, i, j, e, t in states: ev.append((s, i, j, passes(e), e, t))
            C["guard_at_dump"] = ev[0][3] if ev else None     # sanity: the post-dump state must pass (it defines min_out)
            # the guard after every trade on the token from the dump on: (ms after the dump on the block clock, passes after it, out / min_out)
            C["gseq"] = [(x[0], x[1], x[2], x[3], round(out_tokens(x[4]["vsol"], x[4]["vtok"], spend, fr) / mo, 5), x[4]["user"], x[4]["buy"], x[4]["sol"]) for x in ev]
            # state just before our tx
            if C.get("found_ours"):
                pos = (C["our_slot"], C["our_idx"])
                before = [x for x in ev if (x[0], x[1]) < pos]
                C["pred_pass"] = before[-1][3] if before else None
                st = before[-1][4] if before else None
                C["pred_out_ratio"] = (out_tokens(st["vsol"], st["vtok"], spend, fr) / mo) if st else None
                # the crossing: the last pass->fail flip before our tx (needed to land before it)
                cross = None; prev = True
                for x in before:
                    if prev and not x[3]: cross = x
                    prev = x[3]
                if cross and not C["pred_pass"]:
                    s, i, j, _, e, t = cross
                    C.update(cross_slot=s, cross_idx=i, cross_user=e["user"], cross_buy=e["buy"], cross_sol=e["sol"], cross_tips=t["tips"],
                             cross_ms=tl.bpos(s, i) - tl.bpos(sd, idd), need_earlier_ms=tl.bpos(*pos) - tl.bpos(s, i))
                # the first flip after the dump (for every attempt), and for fills the next flip after our landing (margin)
                first = next((x for x in ev if not x[3]), None)
                if first: C.update(first_cross_ms=tl.bpos(first[0], first[1]) - tl.bpos(sd, idd), first_cross_slot=first[0] - sd, first_cross_user=first[4]["user"])
                C["our_ms"] = tl.bpos(*pos) - tl.bpos(sd, idd)
                bn_d = C["block_n"]; bn_o = C["our_block_n"]
                C["our_ms_real"] = (tl.bpos(pos[0], pos[1], bn_o) - tl.bpos(sd, idd, bn_d)) if (bn_d and bn_o) else None
                C["slot_delta"] = pos[0] - sd
            # rivals: every other buy on the token after the dump, up to the end of the slot after ours
            riv = []
            for t in win:
                if (t["s"], t["i"]) <= (sd, idd) or t["ours"]: continue
                b = [e for e in t["tr"] if e["mint"] == mint and e["buy"]]
                if t["err"] is None and not b: continue          # a sell / other
                if t["err"] is not None and not (set(t["ixn"] or []) & {"Buy", "BuyExactSolIn", "BuyExactQuoteIn", "BuyExactQuoteInV2", "BuyV2", "BuyV3"}) and "6042" not in json.dumps(t["err"]) and "6002" not in json.dumps(t["err"]): continue
                user = b[0]["user"] if b else t["signer"]
                riv.append(dict(s=t["s"], i=t["i"], ms=tl.bpos(t["s"], t["i"]) - tl.bpos(sd, idd), ds=t["s"] - sd, di=t["i"] - idd if t["s"] == sd else None,
                                user=user, ok=t["err"] is None, err=t["err"], sol=sum(e["sol"] for e in b), tips=t["tips"], cup=t["cup"], fee=t["fee"],
                                ahead=(C.get("found_ours") and (t["s"], t["i"]) < (C["our_slot"], C["our_idx"])),
                                pass_after=None))
            C["rivals"] = riv
            # sells after the dump before us (other dumps / exits)
            C["n_sells_before_us"] = sum(1 for t in win if C.get("found_ours") and (t["s"], t["i"]) < (C["our_slot"], C["our_idx"]) and (t["s"], t["i"]) > (sd, idd)
                                         and t["err"] is None and any(e["mint"] == mint and not e["buy"] for e in t["tr"]))
            # guard state at fixed landing delays (block clock), for the what-if: would our buy pass if it landed at d ms?
            gw = {}
            for dms in (0, 2, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 75, 100, 150, 212, 300):
                tgt = tl.bpos(sd, idd) + dms
                bef = [x for x in ev if tl.bpos(x[0], x[1]) <= tgt]
                gw[dms] = bef[-1][3] if bef else True
            C["guard_at_ms"] = gw
            # the longest landing delay that still passes (first flip), on the block clock
        r["C"] = C
        # leaders
        L = dict(dump_leader=a["leader"], dump_client=a["client"], dump_class=tl.client_class(a["client"]))
        sdump = C.get("dump_slot", a["dump_slot"])
        L["sched_leader_dump"] = tl.leader(sdump)
        L["turn_pos"] = tl.turn_pos(sdump)
        L["rtt"] = tl.leader_rtt(a["leader"], srv) if a["leader"] else None
        L["geo"] = tl.leader_geo(a["leader"]) if a["leader"] else None
        if C.get("found_ours"):
            lo = tl.leader(C["our_slot"])
            L.update(our_leader=lo, our_client=tl.leader_client(lo), same_leader=(lo == a["leader"]))
        L["next_leader"] = tl.leader(sdump + 1); L["next_same"] = L["next_leader"] == a["leader"]
        r["L"] = L
        rows.append(r)
    json.dump(rows, open(f"{tl.OUT}/timeline.json", "w"))
    ok = [r for r in rows if r["C"].get("found_ours")]
    print(f"attempts {len(rows)} | dump found {sum(r['C']['found_dump'] for r in rows)} | our tx found {len(ok)} | "
          f"multi-landed {sum(1 for r in rows if r['C'].get('ours_landed_n', 0) > 1)}")
    # validation: the engine's fill/fail vs the chain's, and the curve model's guard prediction vs the chain's result
    agree = sum(1 for r in ok if r["C"]["our_ok"] == r["filled"]); print(f"engine filled == chain ok: {agree}/{len(ok)}")
    pr = [r for r in ok if r["C"].get("pred_pass") is not None]
    print(f"guard model predicts the chain result: {sum(1 for r in pr if r['C']['pred_pass'] == r['C']['our_ok'])}/{len(pr)} "
          f"(post-dump state passes: {sum(1 for r in rows if r['C'].get('guard_at_dump'))}/{sum(1 for r in rows if r['C'].get('guard_at_dump') is not None)})")
    bad = [r for r in pr if r["C"]["pred_pass"] != r["C"]["our_ok"]]
    for r in bad[:12]:
        c = r["C"]; print("   mismatch", r["base"], r["mint"][:8], "ok", c["our_ok"], "pred", c["pred_pass"], "ratio", round(c["pred_out_ratio"] or 0, 4), "err", str(c["our_err"])[:50])


if __name__ == "__main__":
    main()
