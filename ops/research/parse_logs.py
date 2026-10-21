# READ-ONLY (host): every launch the engine WATCHED (base filter passed + close leader -> a "RACE seen" line) in a set of
# engine logs, with its create-time fields (RACE seen), the engine's glued-bundle decision (RACE decide), the feed
# timeline of outside txs (RACE obs outs), the create's position in its slot (DETECT feed=erpc poh_ms, the same value the
# GATE-CREATE-MS gate uses), and our FIRE / FAST-FIRE (route, client, tips) when it fired. Also each log's time span
# (first..last slot x the log's POH slot length) to normalise launches per hour.
# usage: python3 parse_logs.py <out.json> <label>=<engine log> [<label>=<engine log> ...]
import sys, re, json

OUT = sys.argv[1]
KV = re.compile(r"(\w+)=(\S*)")
launches = {}; spans = {}


def kv(line):
    return dict(KV.findall(line))


for arg in sys.argv[2:]:
    label, path = arg.split("=", 1)
    slot_ms = 217.0; first = last = None; poh = {}; n_base = 0; n_far = None
    rows = {}
    for line in open(path, errors="replace"):
        if "POH CLOCK" in line:
            m = re.search(r"-> ([\d.]+) ms a slot", line)
            if m: slot_ms = float(m.group(1))
        m = re.search(r" slot=(\d+)", line)
        if m and ("DETECT" in line or "RACE" in line):
            s = int(m.group(1)); first = s if first is None else min(first, s); last = s if last is None else max(last, s)
        if "DETECT" in line:
            d = kv(line)
            if d.get("first") == "1" and d.get("verdict") == "pass": n_base += 1
            if d.get("feed") == "erpc" and d.get("poh_ms", "-") not in ("-", ""):
                try: poh[d["mint"]] = float(d["poh_ms"])
                except ValueError: pass
            continue
        if "CLOSE-LEADER GATE: skipped" in line:
            m = re.search(r"skipped (\d+) far-leader", line)
            if m: n_far = int(m.group(1))
        if "RACE seen" in line:
            d = kv(line.split("RACE seen", 1)[1])
            k = (int(d["slot"]), d["mint"])
            r = rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))
            for f in ("dev", "dev_sized", "dev_cap", "kind", "cu_price", "cu_limit", "nsig", "nkeys", "luts", "nix", "tip", "name_len"):
                try: r[f] = int(d.get(f, 0))
                except ValueError: r[f] = None
            for f in ("host", "tip_to", "creator", "sym", "name", "uri", "v1", "t22", "static_ok"):
                r[f] = d.get(f)
        elif "RACE reject-static" in line:
            d = kv(line); k = (int(d["slot"]), d["mint"])
            rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))["reject_static"] = True
        elif "RACE decide" in line:
            d = kv(line); k = (int(d["slot"]), d["mint"])
            r = rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))
            r["decide"] = dict(bundle_n=int(d.get("bundle_n", 0)), bundle_sol=float(d.get("bundle_sol", 0)), closed=d.get("glued_closed"),
                               unknown=d.get("glued_unknown"), passed=d.get("pass") == "true", at_ms=float(d.get("at_ms", 0)))
        elif "RACE obs" in line:
            d = kv(line); k = (int(d["slot"]), d["mint"])
            r = rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))
            outs = []
            for o in (d.get("outs") or "-").split(","):
                p = o.split(":")
                if len(p) >= 4:
                    try: outs.append([float(p[0]), float(p[1]), p[2], p[3]])
                    except ValueError: pass
            r["obs"] = dict(outs=outs, first_ms=float(d.get("first_ms", -1)), bundle_n=int(d.get("bundle_n", 0)), bundle_sol=float(d.get("bundle_sol", 0)),
                            fired=d.get("fired") == "true", n100=int(d.get("n100", 0)), sol100=float(d.get("sol100", 0)))
        elif "GATE-CREATE-MS" in line:
            d = kv(line); k = (int(d["slot"]), d["mint"])
            r = rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))
            r["gate_create_ms"] = float(d["create_ms"]); r["gate_verdict"] = d.get("verdict")
        elif re.match(r"^\s+FIRE slot=", line):
            d = kv(line); k = (int(d["slot"]), d["mint"])
            r = rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))
            r["fire"] = dict(prio=int(d.get("fee_prio", 0)) / 1e9, tips=int(d.get("tips", 0)) / 1e9)
        elif "FAST-FIRE" in line:
            m = re.search(r"slot=(\d+) mint=(\w+).*?route:(\S+) leader=(\w+) client=(\w+) .*?tips=(\d+)", line)
            if m:
                k = (int(m.group(1)), m.group(2))
                r = rows.setdefault(k, dict(log=label, S=k[0], mint=k[1]))
                r["fastfire"] = dict(route=m.group(3), leader=m.group(4), client=m.group(5), tips=int(m.group(6)) / 1e9)
    for k, r in rows.items():
        if "host" not in r: continue            # a FIRE/obs line without its RACE seen (should not happen): skip
        r["create_ms"] = poh.get(r["mint"], r.get("gate_create_ms"))
        r["slot_ms"] = slot_ms
        if k in launches: continue              # the same launch in two logs: keep the first
        launches[k] = r
    hours = (last - first) * slot_ms / 1000 / 3600 if first else 0
    spans[label] = dict(path=path, first_slot=first, last_slot=last, slot_ms=slot_ms, hours=hours, n_seen=sum(1 for r in rows.values() if "host" in r),
                        n_base_pass=n_base, n_far_skipped=n_far)
    print(f"{label:12} {hours:5.2f} h  slots {first}-{last}  watched {spans[label]['n_seen']:4}  base-pass {n_base:5}  far-skipped {n_far}", flush=True)
json.dump(dict(spans=spans, launches=sorted(launches.values(), key=lambda r: r["S"])), open(OUT, "w"))
print(f"launches: {len(launches)} -> {OUT}")
