#!/usr/bin/env python3
"""Write <run-dir>/catalog.json describing the Shreder trial dataset (streams, filters, time span, counts, sizes,
rx-clock notes, what each file holds, how to read it). Fast: uses the per-member .idx.jsonl files, not the data.
usage: make_catalog.py /home/moiz/sniper-data/preconf/<YYYYMMDD>
"""
import glob, json, os, sys, time

PKT = 5 * 3600


def pkt(ns):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ns / 1e9 + PKT)) + " PKT" if ns else None


def count_lines(p):
    n = 0
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            n += chunk.count(b"\n")
    return n


def load_manifest(d):
    m = {}
    p = os.path.join(d, "MANIFEST.sha256")
    if os.path.exists(p):
        for l in open(p):
            parts = l.strip().split(None, 1)
            if len(parts) == 2:
                m[parts[1].lstrip("*").removeprefix("./")] = parts[0]
    return m


def main():
    rd = sys.argv[1].rstrip("/")
    fra = os.path.join(rd, "fra")
    man = load_manifest(fra)
    events = []
    ep = os.path.join(fra, "events.jsonl")
    if os.path.exists(ep):
        for l in open(ep):
            try:
                events.append(json.loads(l))
            except Exception:
                pass
    start = next((e for e in events if e.get("ev") == "start"), {})
    streams = {}
    for idx in sorted(glob.glob(os.path.join(fra, "*_*_*.idx.jsonl"))):
        base = os.path.basename(idx)[: -len(".idx.jsonl")]
        name = base.split("_")[0]
        s = streams.setdefault(name, {"parts": [], "records": 0, "raw_bytes": 0, "gz_bytes": 0, "t0": None, "t1": None, "s0": None, "s1": None})
        n = ub = 0
        t0 = t1 = s0 = s1 = None
        for l in open(idx):
            try:
                m = json.loads(l)
            except Exception:
                continue
            n += m["n"]; ub += m["ulen"]
            t0 = m["t0"] if t0 is None else min(t0, m["t0"]); t1 = m["t1"] if t1 is None else max(t1, m["t1"])
            s0 = m["s0"] if s0 is None else min(s0, m["s0"]); s1 = m["s1"] if s1 is None else max(s1, m["s1"])
        rec = base + ".rec.gz"
        gz = os.path.getsize(os.path.join(fra, rec)) if os.path.exists(os.path.join(fra, rec)) else 0
        s["parts"].append({"file": rec, "index": os.path.basename(idx), "records": n, "raw_bytes": ub, "gz_bytes": gz,
                           "rx_first": pkt(t0), "rx_last": pkt(t1), "slots": [s0, s1], "sha256": man.get(rec)})
        s["records"] += n; s["raw_bytes"] += ub; s["gz_bytes"] += gz
        for k, v, f in (("t0", t0, min), ("t1", t1, max), ("s0", s0, min), ("s1", s1, max)):
            if v is not None:
                s[k] = v if s[k] is None else f(s[k], v)
    for name, s in streams.items():
        span = (s["t1"] - s["t0"]) / 1e9 if s["t0"] and s["t1"] else 0
        s["rx_span"] = [pkt(s["t0"]), pkt(s["t1"])]
        s["rate_per_s"] = round(s["records"] / span, 1) if span else None
        s["gz_ratio"] = round(s["raw_bytes"] / s["gz_bytes"], 2) if s["gz_bytes"] else None
        st = [e for e in events if e.get("st") == name]
        s["reconnects"] = max([e.get("rc", 0) for e in st if e.get("ev") == "status"] or [0])
        s["dropped_queue_full"] = max([e.get("dropped", 0) for e in st if e.get("ev") == "status"] or [0])
        s["parse_errors"] = max([e.get("perr", 0) for e in st if e.get("ev") == "status"] or [0])
        s["filter_fallback"] = any(e.get("ev") == "filter_fallback" for e in st)
        s["errors"] = [e.get("msg") for e in st if e.get("ev") == "error"][:20]
        s["connected_windows"] = "see events.jsonl: subscribed/stream_end/error per stream (c = connection epoch)"
        views = sorted(p for p in glob.glob(os.path.join(fra, f"{name}_*.jsonl")) if not p.endswith(".idx.jsonl"))
        s["pump_view"] = [{"file": os.path.basename(p), "lines": count_lines(p), "bytes": os.path.getsize(p),
                           "sha256": man.get(os.path.basename(p))} for p in views]
        for k in ("t0", "t1", "s0", "s1"):
            s.pop(k)
    clocks = {}
    for nm in ("clock_start.json", "clock_end.json"):
        p = os.path.join(fra, nm)
        if os.path.exists(p):
            c = json.load(open(p))
            b = c.get("bracket") or {}
            clocks[nm] = {"t": pkt(c.get("t")), "chrony_offset_ams_minus_fra_ms": c.get("chrony_offset_ams_minus_fra_ms"),
                          "fra_vs_ntp_ms": (c.get("fra_sync") or {}).get("offset_ms"), "ams_vs_ntp_ms": (c.get("ams_sync") or {}).get("offset_ms"),
                          "bracket_ams_minus_fra_ms": b.get("offset_ms"), "bracket_max_error_ms": b.get("max_error_ms"),
                          "ping_fra_ams_rtt_min_ms": (c.get("ping") or {}).get("rtt_min_ms")}
    final = [e for e in events if e.get("ev") == "done"]
    cat = {
        "dataset": "Shreder trial recording: preconf (pre-shred, connected leaders) + Binary (shred-reconstructed) transaction streams",
        "run_dir": rd,
        "recorded_on": "FRA 84.32.100.36 (Frankfurt), the only allowlisted IP; endpoint id (fingerprint, not the URL): " + str(start.get("endpoint_id")),
        "recorder": {"binary": "shreder_rec 0.2", "sha256": (open(os.path.join(fra, "binary.sha256")).read().split()[0] if os.path.exists(os.path.join(fra, "binary.sha256")) else None),
                     "streams_requested": start.get("streams"), "auth": start.get("auth"), "started": pkt(start.get("t")),
                     "done": final[-1] if final else None},
        "streams": streams,
        "rx_clock": ("rx_ns = CLOCK_REALTIME on FRA (chrony, NTP source ntp-nts-3.ps5.canonical.com, stratum 3), taken in the gRPC "
                     "receive task right after the protobuf message is decoded (before any disk work, which runs on a separate thread). "
                     "In a burst, consecutive messages from one TCP read are stamped ~1-2 us apart (sequential decode). ca_ns = the server's "
                     "created_at (Shreder's clock) — rx_ns - ca_ns mixes network delay with the clock offset between Shreder and FRA. "
                     "Cross-machine comparisons (AMS engine) need the offsets in clock (chrony + host-hub bracket) and are INFERRED."),
        "clock": clocks,
        "files": {
            "<stream>_<YYYYMMDD_HH>_<part>.rec.gz": "every message of the stream; concatenated gzip members (one per ~1 s); HH = PKT hour of rx; record layout below",
            "<stream>_<YYYYMMDD_HH>_<part>.idx.jsonl": "one line per gzip member: m, off (byte offset in .rec.gz), clen, ulen, n, q0/q1 seq, t0/t1 rx_ns, s0/s1 slot -> random access",
            "<stream>_<YYYYMMDD_HH>.jsonl": "pump view: messages whose static keys contain the pump.fun program (all messages for server-filtered streams); JSON per line",
            "events.jsonl": "connect/subscribe/error/stream_end/filter_fallback events and 30-s status per stream (rates, drops, reconnects, live pre-vs-bin lead)",
            "rec.log": "human-readable status lines", "stdout.log": "recorder stdout/stderr", "binary.sha256": "sha of the recorder binary used",
            "chrony_start.txt / chrony_end.txt": "chronyc tracking on FRA at start/stop", "clock_start.json / clock_end.json": "FRA/AMS clock offset + FRA->AMS ping (host-made)",
            "MANIFEST.sha256": "sha256 of every server file (verified after copy)",
            "../ck/": "Constant-K feed race (same machine, same clock): see ck/ files", "../engine/": "engine log snapshot (ENGINE_HOST says where it ran)",
        },
        "record_layout": ("little-endian struct '<IQqqQBBHI' (44 bytes) + tx: u32 rec_len (= 40 + tx_len), u64 seq (per stream, 1-based), "
                          "i64 rx_ns, i64 ca_ns (0 if absent), u64 slot, u8 flags (bit0 preconf flag from server, bit1 parse error, bit2 empty tx), "
                          "u8 n_proto_sigs, u16 reserved, u32 tx_len, tx = bincode VersionedTransaction (Solana wire format; first signature tx[1:65])"),
        "view_layout": ("{q: seq, t: rx_ns, ca: created_at ns, s: slot, sig: first sig base58, pf: preconf flag, c: connection epoch, v: -1 legacy / 0 v0, "
                        "pe: 1 if unparsable, p: [[kind, mint|null, user|null, a1, a2], ...] top-level pump instructions (kinds: buy/sell/bxs/bq3/sell3/sellx3/bq2/buy2/buy3/create/create_v2/amm_*/other:<disc>), "
                        "x: base64 raw tx (only with --jsonl-raw)}"),
        "how_to_read": ("python3 /home/moiz/sniper/ops/preconf/shreder/read_rec.py <run>/fra --stream bin --summary | --tsv ; in Python: "
                        "sys.path.insert(0,'/home/moiz/sniper/ops/preconf/shreder'); import read_rec; for r in read_rec.iter_stream('<run>/fra','pre'): ... "
                        "(r.seq, r.rx_ns, r.ca_ns, r.slot, r.flags, r.sig, r.tx); read_rec.parse_tx(r.tx) for keys/instructions. Address lookup tables are NOT resolved."),
        "caveats": ["Preconf covers only leaders connected to Shreder's preconf ingest; absent txs in other slots are expected.",
                    "Filters: 'all' = no account filter; if the server refused it, the recorder fell back to the broad program list (see streams.*.filter_fallback).",
                    "seq gaps = recorder queue overflow (dropped_queue_full) — should be 0.",
                    "The pump view uses static keys only; pump txs reached only via CPI with a lookup-table program id are in the dataset but not the view."],
        "generated": pkt(time.time_ns()),
    }
    ck = os.path.join(rd, "ck")
    if os.path.isdir(ck):
        cat["ck_files"] = sorted(os.listdir(ck))
    eng = os.path.join(rd, "engine")
    if os.path.isdir(eng):
        cat["engine_files"] = {f: os.path.getsize(os.path.join(eng, f)) for f in sorted(os.listdir(eng))}
    out = os.path.join(rd, "catalog.json")
    json.dump(cat, open(out, "w"), indent=1)
    print(f"catalog -> {out}")
    for n, s in streams.items():
        print(f"  {n}: {s['records']} records, {s['rate_per_s']}/s, gz {s['gz_bytes']/1e9:.2f} GB (raw {s['raw_bytes']/1e9:.2f} GB, x{s['gz_ratio']}), "
              f"rx {s['rx_span'][0]} .. {s['rx_span'][1]}, rc {s['reconnects']}, dropped {s['dropped_queue_full']}, fallback {s['filter_fallback']}")


if __name__ == "__main__":
    main()
