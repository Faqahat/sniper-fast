#!/usr/bin/env python3
# per fire: our feed's receipt times of every trade on the mint after the dump (tape events) vs our fire / our buy seen
import json, collections, statistics as st
D = "/home/moiz/sniper/ops/dip/speed"
rt = json.load(open(f"{D}/leaders/leader_rtt_new.json"))["leaders"]
FC = {r["buy_sig"]: r for r in json.load(open("/home/moiz/sniper/ops/agents/freshaudit/out/fire_chain.json"))}
rows = []
for n in range(1, 6):
    ev = [json.loads(l) for l in open(f"{D}/dip_r{n}.jsonl")]
    tape = collections.defaultdict(list)
    for e in ev:
        if e["ev"] == "tape": tape[e["mint"]].append(e)
    tim = {e["buy_sig"]: e for e in ev if e["ev"] == "timing"}
    for f in (e for e in ev if e["ev"] == "fire"):
        tm = tim.get(f["buy_sig"], {}); fc = FC.get(f["buy_sig"], {})
        t0 = tm.get("dump_first_rx")
        if not t0: continue
        d = fc.get("dump") or {}; o = fc.get("ours") or {}
        comp = []
        for t in tape[f["mint"]]:
            if t["user"] == "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": continue
            if (t["slot"], t["idx"]) <= (d.get("s", 0), d.get("i", -1)): continue
            if t["slot"] > f["slot"] + 1: break
            comp.append(dict(s=t["slot"] - f["slot"], i=t["idx"], user=t["user"], buy=t["buy"], sol=t["sol"] / 1e9, ms=(t["t"] - t0) / 1e6,
                             ahead=(t["slot"], t["idx"]) < (o.get("s", 10**12), o.get("i", 0))))
        rows.append(dict(run=n, mint=f["mint"], res=fc.get("result"), client=f.get("client"), rtt=rt.get(f.get("leader"), {}).get("rtt"),
                         fire_ms=(f["t_fire"] - t0) / 1e6, seen_ms=((tm.get("buy_first_rx") or 0) - t0) / 1e6, exec_lag=tm.get("exec_lag_ms"),
                         ds=o.get("s", 0) - d.get("s", 0), oi=o.get("i"), di=d.get("i"), comp=comp, pre=fc.get("pre_ratio")))
json.dump(rows, open("/home/moiz/sniper/ops/agents/freshaudit/out/tape_timing.json", "w"))
print("fires with timing", len(rows))
# first competitor BUY seen (any wallet) vs ours
W = collections.defaultdict(list)
for r in rows:
    fb = [c for c in r["comp"] if c["buy"]]
    for c in fb:
        if c["s"] == 0: W[c["user"][:8]].append(c["ms"])
    first = fb[0]["ms"] if fb else None
    print(f"r{r['run']} {r['mint'][:6]} {r['res'][:6]:<6} rtt={r['rtt']} {r['client']:<18} fire+{r['fire_ms']:.1f} ours_seen+{r['seen_ms']:.1f} ds={r['ds']} first_comp_buy+{first if first is None else round(first,1)} "
          f"n_buys_seen_before_ours={sum(1 for c in fb if c['ms'] < r['seen_ms'])} pre={r['pre'] and round(r['pre'],3)}")
print()
print("same-slot competitor buy seen-ms after dump (median, n) by wallet:")
for w, v in sorted(W.items(), key=lambda kv: -len(kv[1]))[:30]:
    print(f"  {w} n={len(v)} med={st.median(v):.1f} min={min(v):.1f} p25={sorted(v)[len(v)//4]:.1f}")
ours = [r["seen_ms"] for r in rows if r["ds"] == 0]
print("OURS same-slot seen-ms: n", len(ours), "med", round(st.median(ours), 1), "min", round(min(ours), 1), "p25", round(sorted(ours)[len(ours)//4], 1))
fm = [r["fire_ms"] for r in rows]
print("OURS fire-ms after dump first seen: med", round(st.median(fm), 2), "p90", round(sorted(fm)[int(0.9*len(fm))], 2))
