# READ-ONLY helper: build per-launch rows for a forward PAPER run (engine RACE log + onchain.py cache + engine dumped
# paths), in the same shape as race_ds.jsonl rows where it matters (dev_sol, dev_kind, glued, gsol, n_len, uri_host,
# cu_price, nsig, ctip_label, mint_pump, path, sv, base, ms_per_tx, labels, his, fired).
import sys, re, json, collections
sys.path.insert(0, "/root/race")
from race_lib import labels, path_pts, W, bad_events

ENGINE_T0_MS = 200.0   # calibrated: engine 250 ms curve polls vs chain trades, best fit at +200 ms after the create (217 ms slots)


def kv(line):
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


def build(LOG, OC, PATHS, verbose=True):
    pros = frozenset(json.load(open("/root/race/pros.json")))
    try:
        sys.path.insert(0, "/root/indep")
        from common import load_tipmap
        tm = load_tipmap()
    except Exception:
        tm = {}
    seen, dec, obs = {}, {}, {}
    t_first = t_last = None
    for l in open(LOG, errors="replace"):
        if "RACE seen" in l:
            d = kv(l)
            seen.setdefault(d["mint"], d)
        elif "RACE decide" in l:
            d = kv(l)
            dec[d["mint"]] = d
        elif "RACE obs" in l:
            d = kv(l)
            outs = []
            if d.get("outs", "-") != "-":
                for x in d["outs"].split(","):
                    p = x.split(":")
                    if len(p) >= 3:
                        outs.append((float(p[0]), float(p[1]), p[2] == "1", p[3] if len(p) > 3 else ""))
            d["outs_l"] = outs
            obs[d["mint"]] = d
    oc = {}
    for l in open(OC):
        try:
            r = json.loads(l)
            oc[r["mint"]] = r
        except Exception:
            pass
    eng = {}
    for l in open(PATHS):
        try:
            r = json.loads(l)
            eng[r["mint"]] = r
        except Exception:
            pass
    rows, miss = [], collections.Counter()
    for m, f in seen.items():
        r = oc.get(m)
        if not r or "csig" not in (r.get("b") or {}):
            miss["no block yet"] += 1
            continue
        b, s = r["b"], r.get("s")
        if not s or "sig_err" in s:
            miss["no s1"] += 1
            continue
        if not b.get("base") or bad_events(b, s):
            miss["non-SOL quote / zero-vsol events (excluded)"] += 1
            continue
        e = eng.get(m)
        if e and e.get("path") and max(rb for _, rb in e["path"]) >= 19.99:
            miss["engine curve read hit the 20x cap (garbage read, excluded)"] += 1
            continue
        o = labels(b, s, pros)
        o["mint"], o["slot"], o["bt"] = m, r["slot"], b.get("bt")
        o["dev_sol"] = int(f.get("dev", 0)) / 1e9
        o["dev_sized"] = int(f.get("dev_sized", 0)) / 1e9
        o["dev_eng"] = o["dev_sol"]                 # what the engine gated on (sized = gross ix amount, cap = curve estimate)
        o["dev_net"] = (b.get("dev") or 0) / 1e9    # chain: SOL in the create-tx trade events (net), = historical dev_sol
        k = int(f.get("kind", 0))
        o["kind"] = k
        o["dev_kind"] = "sized" if k == 1 else ("cap" if k >= 2 else "none")
        o["uri_host"] = f.get("host")
        o["n_len"] = int(f.get("name_len", 99))
        o["cu_price"] = int(f.get("cu_price", 0))
        o["nsig"] = int(f.get("nsig", 0))
        o["luts"] = int(f.get("luts", 0))
        tip, tip_to = int(f.get("tip", 0)), f.get("tip_to", "-")
        o["ctip_label"] = tm.get(tip_to, "none") if tip > 0 else "none"
        o["ctip"] = o["ctip_label"] != "none"
        o["mint_pump"] = m.endswith("pump")
        o["glued"], o["gsol"] = b.get("glued", 0), (b.get("gsol") or 0) / 1e9
        o["base"] = b.get("base")
        pts, mpt = path_pts(b, s)
        o["ms_per_tx"] = mpt
        if e and e.get("path"):
            last_t = pts[-1][0] if pts else 0
            for ms, rb in e["path"]:
                t = ENGINE_T0_MS + ms
                if t > max(last_t, 6 * 217.0):
                    pts.append([round(t), o["base"] * max(rb, 1e-6) ** 0.5])
        pts.sort(key=lambda z: z[0])
        o["path"] = pts
        o["has_path"] = bool(e)
        o["sv"] = [(x["d"], x["ev"][-1][4]) for x in b.get("later") or [] if x.get("ok") and x["ev"]]
        o["his"] = any(o["outS_his"]) or any(x.get("payer") == W or any(ev[1] == W for ev in x.get("ev") or []) for x in (s.get("rows") or []))
        dd = dec.get(m, {})
        o["fired"] = dd.get("pass") == "true"
        ob = obs.get(m, {})
        o["eng_outs"] = ob.get("outs_l", [])
        o["eng_bundle"] = int(ob.get("bundle_n", 0) or 0)
        o["mayhem"], o["in_rand"] = False, True
        rows.append(o)
    rows.sort(key=lambda o: o["slot"])
    if verbose:
        print(f"forward: RACE seen {len(seen)} | on-chain {len(oc)} | engine paths {len(eng)} | scored {len(rows)} | skipped {dict(miss)}")
    return rows
