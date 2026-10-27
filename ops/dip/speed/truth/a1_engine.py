#!/usr/bin/env python3
# SPEED TRUTH step 1 (read-only): every live attempt from the engine's own records (FRA r10-r15, AMS r9-r14).
# Joins fire + timing + pick + buy_land / buy_failed + close + land_poll + the .log FAST-ACK lines (per path ack, HTTP status).
# Output: OUT/attempts_engine.json (one row per fire).
import json, re, collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

ACK = re.compile(r"FAST-ACK tag=(\d+) path=([\w-]+) ack_ms=([\d.]+) status=(\S+) reply=(.*)")
SIG = re.compile(r'"(?:result|signature)"\s*:\s*"([1-9A-HJ-NP-Za-km-z]{30,90})')


def parse_log(fn):
    """FAST-ACK lines grouped by tag: [(path, ack_ms, status, sig_or_None)], plus the order of 'DIP FIRE' lines"""
    tags = collections.defaultdict(list); fire_lines = []
    unhealthy = []      # (line_no, text) of SEND-PATH UNHEALTHY / RECOVERED lines
    for n, line in enumerate(open(fn, errors="replace")):
        m = ACK.search(line)
        if m:
            sm = SIG.search(m.group(5))
            st = m.group(4)
            code = re.search(r"\d+", st)
            tags[int(m.group(1))].append((m.group(2), float(m.group(3)), int(code.group()) if code else None, sm.group(1) if sm else None))
            continue
        if "DIP FIRE " in line:
            fire_lines.append(n)
        if "SEND-PATH" in line and ("UNHEALTHY" in line or "RECOVERED" in line):
            unhealthy.append((n, line.strip()[:160]))
    return tags, fire_lines, unhealthy


def main():
    rows = []
    for srv, run, base in tl.RUNS:
        jf = f"{tl.LIVE}/{base}.jsonl"
        fires, tim, picks, land, fail, close, poll = {}, {}, {}, {}, {}, {}, {}
        run_start = None
        for l in open(jf):
            try: r = json.loads(l)
            except Exception: continue
            e = r.get("ev")
            if e == "run_start": run_start = r
            elif e == "fire": fires[r["buy_sig"]] = r
            elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
            elif e == "pick": picks[(r["mint"], r["sig"])] = r
            elif e == "buy_land": land[r["mint"]] = land.get(r["mint"], []) + [r]
            elif e == "buy_failed": fail[r["mint"]] = fail.get(r["mint"], []) + [r]
            elif e == "close": close[r["buy_sig"]] = r
            elif e == "land_poll": poll[r["sig"]] = r
        tags, _, unhealthy = parse_log(f"{tl.LIVE}/{base}.log")
        # tag -> fire: any acked signature that is one of the fire's variant signatures (or its one buy sig before nonce)
        sig2fire = {}       # 30-char signature prefix -> fire (the log truncates replies)
        for bs, f in fires.items():
            sig2fire[bs[:30]] = bs
            for v in (f.get("nonce") or {}).get("per_path", []):
                if v.get("sig"): sig2fire[v["sig"][:30]] = bs
        acks = collections.defaultdict(list)
        for tag, lst in tags.items():
            owner = next((sig2fire[s[:30]] for _, _, _, s in lst if s and s[:30] in sig2fire), None)
            if owner: acks[owner] += [dict(tag=tag, path=p, ack_ms=a, status=st) for p, a, st, _ in lst]
        for bs, f in sorted(fires.items(), key=lambda kv: kv[1]["t_fire"]):
            c = close.get(bs, {}); t = tim.get(bs, {})
            vars_ = (f.get("nonce") or {}).get("variants") or []
            per_path = (f.get("nonce") or {}).get("per_path") or []
            all_sigs = sorted({v["sig"] for v in vars_ if v.get("sig")} | {bs})
            # this fire's landing record (same mint, after the fire)
            bl = next((x for x in land.get(f["mint"], []) if x["t"] >= f["t_fire"] - 1e9 and x["sig"] in all_sigs), None)
            bf = next((x for x in fail.get(f["mint"], []) if x["t"] >= f["t_fire"] - 1e9), None)
            pk = picks.get((f["mint"], f["dump_sig"]), {})
            lp = next((poll[s] for s in all_sigs if s in poll), None)
            row = dict(srv=srv, run=run, base=base, nonce=bool(f.get("nonce")), mint=f["mint"], dump_sig=f["dump_sig"], buy_sig=bs, sigs=all_sigs,
                       dump_slot=f["slot"], dump_idx=c.get("dump_idx", pk.get("idx")), leader=f.get("leader"), client=f.get("client"),
                       route=f.get("route"), paths=pk.get("paths") or [w["path"] for w in f.get("writes", [])], dev=f.get("dev"), spend=f.get("spend"),
                       min_out=f.get("min_out"), tips=f.get("tips"), deadline=f.get("deadline"),
                       dump_vsol=c.get("dump_vsol"), dump_vtok=c.get("dump_vtok"), score=f.get("score", pk.get("score")), age=pk.get("age"),
                       t_dump_rx=f["t_dump_rx"], t_fire=f["t_fire"], decision_us=f["decision_us"], lat_us=f.get("lat_us"),
                       writes=f.get("writes"), per_path=per_path, variants=vars_,
                       timing={k: t.get(k) for k in ("dump_first_rx", "dump_first_feed", "dump_exec_rx", "exec_lag_ms", "reaction_ms", "buy_first_rx",
                                                     "buy_first_feed", "fire_to_seen_ms", "dump_poh", "buy_poh", "land_ms_poh", "slot_ms", "buy_sig_seen")},
                       acks=acks.get(bs, []),
                       result=c.get("result"), filled=bl is not None,
                       land=dict(slot=bl["slot"], idx=bl["idx"], sig=bl["sig"], rx_ms_after_dump=bl["rx_ms_after_dump"], slots_after=bl["slots_after_dump"],
                                 paths=(bl.get("variant") or {}).get("paths"), fee=bl.get("fee"), t=bl["t"]) if bl else None,
                       fail=dict(slot=bf["slot"], sig=bf["sig"], paths=(bf.get("variant") or {}).get("paths"), t=bf["t"]) if (bf and not bl) else None,
                       poll=dict(ok=lp.get("ok"), err=lp.get("err"), land_slot=lp.get("land_slot"), via=lp.get("via")) if lp else None,
                       run_cfg=dict(guard=(run_start or {}).get("guard"), m2=((run_start or {}).get("m2") or {}).get("mode")))
            rows.append(row)
        print(f"{base:14s} fires {len(fires):3d} | filled {sum(1 for r in rows if r['base'] == base and r['filled'])} | acks mapped {sum(1 for r in rows if r['base'] == base and r['acks'])} | SEND-PATH health lines {len(unhealthy)}")
    json.dump(rows, open(f"{tl.OUT}/attempts_engine.json", "w"))
    print("attempts", len(rows), "->", f"{tl.OUT}/attempts_engine.json")


if __name__ == "__main__":
    main()
