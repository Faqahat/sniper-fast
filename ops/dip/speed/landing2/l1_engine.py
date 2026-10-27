#!/usr/bin/env python3
# LANDING2 step 1 (read-only): every nonce-era live fire from the engine's own records.
# Runs: FRA r11-r16, AMS r11-r14 + r17 (AMS r15/r16 had pre-send attempts only; those are in l5_presend.py).
# Joins fire + timing (+clock2 on r16) + pick + buy_land / buy_failed + close + land_poll + tape (the executed feed's trades on
# the token, our feed clock for rivals) + the .log FAST-ACK lines (per-path relay ack + HTTP status).
# Output: /home/moiz/sniper-data/landing2/fires_engine.json
import json, re, collections, sys, os

RUNS_DIR = "/home/moiz/sniper-data/runs"
OUT = "/home/moiz/sniper-data/landing2"
RUNS = [("FRA", n, f"fra/runs/dip_r{n}") for n in (11, 13, 14, 15, 16)] + [("AMS", n, f"ams/runs/dip_ams_r{n}") for n in (11, 12, 13, 14, 17)]
ACK = re.compile(r"FAST-ACK tag=(\d+) path=([\w-]+) ack_ms=([\d.]+) status=(\S+) reply=(.*)")
SIG = re.compile(r'"(?:result|signature)"\s*:\s*"([1-9A-HJ-NP-Za-km-z]{30,90})')


def parse_log(fn):
    tags = collections.defaultdict(list)
    for line in open(fn, errors="replace"):
        m = ACK.search(line)
        if not m: continue
        sm = SIG.search(m.group(5)); code = re.search(r"\d+", m.group(4))
        tags[int(m.group(1))].append((m.group(2), float(m.group(3)), int(code.group()) if code else None, sm.group(1) if sm else None))
    return tags


def main():
    rows = []
    for srv, run, base in RUNS:
        fires, tim, picks, land, fail, close, poll, tape = {}, {}, {}, {}, {}, {}, {}, collections.defaultdict(list)
        rs = None
        for l in open(f"{RUNS_DIR}/{base}.jsonl"):
            try: r = json.loads(l)
            except Exception: continue
            e = r.get("ev")
            if e == "run_start": rs = r
            elif e == "fire": fires[r["buy_sig"]] = r
            elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
            elif e == "pick": picks[(r["mint"], r["sig"])] = r
            elif e == "buy_land": land.setdefault(r["mint"], []).append(r)
            elif e == "buy_failed": fail.setdefault(r["mint"], []).append(r)
            elif e == "close": close[r["buy_sig"]] = r
            elif e == "land_poll": poll[r["sig"]] = r
            elif e == "tape": tape[r["mint"]].append(r)
        tags = parse_log(f"{RUNS_DIR}/{base}.log")
        sig2fire = {}
        for bs, f in fires.items():
            sig2fire[bs[:30]] = bs
            for v in (f.get("nonce") or {}).get("per_path", []):
                if v.get("sig"): sig2fire[v["sig"][:30]] = bs
        acks = collections.defaultdict(list)
        for tag, lst in tags.items():
            owner = next((sig2fire[s[:30]] for _, _, _, s in lst if s and s[:30] in sig2fire), None)
            if owner: acks[owner] += [dict(tag=tag, path=p, ack_ms=a, status=st) for p, a, st, _ in lst]
        n0 = len(rows)
        for bs, f in sorted(fires.items(), key=lambda kv: kv[1]["t_fire"]):
            c = close.get(bs, {}); t = tim.get(bs, {})
            vars_ = (f.get("nonce") or {}).get("variants") or []
            per_path = (f.get("nonce") or {}).get("per_path") or []
            all_sigs = sorted({v["sig"] for v in vars_ if v.get("sig")} | {bs})
            bl = next((x for x in land.get(f["mint"], []) if x["t"] >= f["t_fire"] - 1e9 and x["sig"] in all_sigs), None)
            bf = next((x for x in fail.get(f["mint"], []) if x["t"] >= f["t_fire"] - 1e9 and x["sig"] in all_sigs), None)
            pk = picks.get((f["mint"], f["dump_sig"]), {})
            lp = next((poll[s] for s in all_sigs if s in poll), None)
            tp = [dict(user=x["user"], buy=x["buy"], sol=x["sol"], slot=x["slot"], idx=x["idx"], t=x["t"], sig=x.get("sig")) for x in tape.get(f["mint"], [])
                  if f["t_dump_rx"] - 2e9 <= x["t"] <= f["t_dump_rx"] + 3e9]
            rows.append(dict(
                srv=srv, run=run, base=base, mint=f["mint"], dump_sig=f["dump_sig"], buy_sig=bs, sigs=all_sigs,
                dump_slot=f["slot"], dump_idx=pk.get("idx"), leader=f.get("leader"), client=f.get("client"), route=f.get("route"),
                paths=pk.get("paths") or [w["path"] for w in f.get("writes", [])], dev=f.get("dev"), spend=f.get("spend"), min_out=f.get("min_out"),
                tips=f.get("tips"), score=pk.get("score"), t_dump_rx=f["t_dump_rx"], t_fire=f["t_fire"], decision_us=f["decision_us"],
                lat_us=f.get("lat_us"), writes=f.get("writes"), per_path=per_path, variants=vars_, timing={k: v for k, v in t.items() if k not in ("ev",)},
                acks=acks.get(bs, []), result=c.get("result"), filled=bl is not None,
                land=dict(slot=bl["slot"], idx=bl["idx"], sig=bl["sig"], rx_ms_after_dump=bl.get("rx_ms_after_dump"), slots_after=bl.get("slots_after_dump"),
                          paths=(bl.get("variant") or {}).get("paths"), fee=bl.get("fee"), t=bl["t"]) if bl else None,
                fail=dict(slot=bf["slot"], sig=bf["sig"], paths=(bf.get("variant") or {}).get("paths"), t=bf["t"]) if (bf and not bl) else None,
                poll=dict(ok=lp.get("ok"), err=lp.get("err"), land_slot=lp.get("land_slot"), via=lp.get("via")) if lp else None,
                tape=tp, run_cfg=dict(guard=(rs or {}).get("guard"), shred=(rs or {}).get("shred"), clock2=(rs or {}).get("clock2"))))
        print(f"{base:22s} fires {len(rows) - n0:3d} filled {sum(r['filled'] for r in rows[n0:]):3d} acks {sum(1 for r in rows[n0:] if r['acks']):3d} "
              f"timing {sum(1 for r in rows[n0:] if r['timing']):3d} clock2 {sum(1 for r in rows[n0:] if r['timing'].get('clock2')):3d}")
    json.dump(rows, open(f"{OUT}/fires_engine.json", "w"))
    print("fires", len(rows))


if __name__ == "__main__":
    main()
