"""Typed access to one segment (or campaign) and the joins every report uses:
attempt <-> decision <-> outcome (last line wins, amends kept) <-> ledger <-> blockctx <-> verdicts.

A `Segment` reads lazily and caches. arb-lab v1 segments go through `legacy.py` so reports see one shape.
"""
from __future__ import annotations

import os
import re
from functools import cached_property

from . import counters, legacy, solana, streams


def natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class Segment:
    def __init__(self, path: str, name: str | None = None, wallet_txs: list | None = None, chain_ledger: list | None = None):
        self.dir = os.path.abspath(path)
        self.name = name or os.path.basename(self.dir.rstrip("/"))
        self.files = streams.discover(self.dir)
        self._wallet_txs_extra = wallet_txs  # [TxView] given on the command line (legacy runs)
        self._chain_ledger_extra = chain_ledger  # research ledger rows (legacy runs)
        self.tip_accounts: set | None = None  # known tip accounts (data/sender-tip-accounts.json), set by the CLI
        self.notes: list = []

    # ------------------------------------------------------------------ files
    def has(self, stream: str) -> bool:
        return bool(self.files.get(stream))

    def stream_files(self, stream: str) -> list:
        return self.files.get(stream, [])

    @cached_property
    def meta(self) -> dict | None:
        p = os.path.join(self.dir, "meta.json")
        return streams.read_json(p, "meta") if os.path.exists(p) else None

    @cached_property
    def legacy(self) -> bool:
        if self.meta is not None:
            return legacy.is_v1_meta(self.meta)
        for s in ("status", "attempts", "outcomes"):
            fs = self.stream_files(s)
            if fs:
                return streams.peek(fs[0]).legacy
        return False

    def v1(self, stream: str) -> bool:
        """Whether `stream` holds arb-lab's v1 records: a v1 segment, or a v2 segment whose stream is still at major 1
        (arbx from WP-02 writes attempts, bundles, outcomes, exec, triggers and predictions as `/1.1` until the WP that
        brings their v2; MEASUREMENT §1.6, §7). Those records go through `legacy.py` (WP-02 review F3)."""
        if self.legacy:
            return True
        fs = self.stream_files(stream)
        return bool(fs) and streams.peek(fs[0]).major == 1

    def _json(self, fn: str, stream: str):
        p = os.path.join(self.dir, fn)
        return streams.read_json(p, stream) if os.path.exists(p) else None

    @cached_property
    def stop(self):
        return self._json("stop.json", "stop")

    @cached_property
    def manifest(self):
        return self._json("manifest.json", "manifest")

    @cached_property
    def probe(self):
        return self._json("probe.json", "probe")

    @cached_property
    def pools(self):
        return self._json("pools.json", "pools")

    def jsonl(self, stream: str) -> list:
        key = "_jsonl_" + stream
        if key not in self.__dict__:
            self.__dict__[key] = streams.read_jsonl(self.stream_files(stream), stream)
        return self.__dict__[key]

    # ------------------------------------------------------------------ identity
    @cached_property
    def wallet(self) -> str | None:
        m = self.meta or {}
        w = m.get("wallet")
        if isinstance(w, dict):
            return w.get("pubkey")
        return w if isinstance(w, str) else None

    @cached_property
    def feeds(self) -> list:
        m = self.meta or {}
        f = m.get("feeds") or []
        names = [x.get("name") if isinstance(x, dict) else x for x in f]
        for fi in self.stream_files("txarr"):
            streams.peek(fi)
        hdr = streams.txarr_feeds(self.stream_files("txarr"))
        return hdr or names

    # ------------------------------------------------------------------ core streams, normalized
    @cached_property
    def attempts(self) -> list:
        rows = self.jsonl("attempts")
        if self.v1("attempts"):
            rows = [legacy.attempt(a) for a in rows]
        return sorted(rows, key=lambda a: (a.get("attempt") is None, a.get("attempt") or 0))

    @cached_property
    def attempts_by_id(self) -> dict:
        return {a["attempt"]: a for a in self.attempts if a.get("attempt") is not None}

    @cached_property
    def outcome_lines(self) -> list:
        rows = self.jsonl("outcomes")
        return [legacy.outcome(o) for o in rows] if self.v1("outcomes") else rows

    @cached_property
    def outcomes(self) -> dict:
        """{attempt: final outcome}: the last line per attempt wins (§4.40 amend rule)."""
        out = {}
        for o in self.outcome_lines:
            if o.get("attempt") is not None:
                out[o["attempt"]] = o
        return out

    @cached_property
    def amends(self) -> list:
        seen = {}
        res = []
        for o in self.outcome_lines:
            a = o.get("attempt")
            if a in seen or o.get("amend"):
                res.append({"attempt": a, "from": (seen.get(a) or {}).get("final"), "to": o.get("final")})
            seen[a] = o
        return res

    @cached_property
    def copies(self) -> list:
        return self.jsonl("copies")

    @cached_property
    def copies_by_attempt(self) -> dict:
        d: dict = {}
        for c in self.copies:
            d.setdefault(c.get("attempt"), []).append(c)
        return d

    @cached_property
    def sig_to_attempt(self) -> dict:
        m = {}
        for a in self.attempts:
            for c in a.get("copies") or []:
                if c.get("sig"):
                    m[c["sig"]] = a["attempt"]
            tx = a.get("tx") or {}
            if tx.get("sig"):
                m[tx["sig"]] = a["attempt"]
        for c in self.copies:
            if c.get("sig") and c.get("attempt") is not None:
                m.setdefault(c["sig"], c["attempt"])
        for o in self.outcome_lines:
            if o.get("sig") and o.get("attempt") is not None:
                m.setdefault(o["sig"], o["attempt"])
        return m

    @cached_property
    def bundles(self) -> list:
        rows = self.jsonl("bundles")
        if self.v1("bundles"):
            rows = [legacy.bundle(b) for b in rows]
        b2a = {}
        for c in self.copies:
            if c.get("bundle"):
                b2a[c["bundle"]] = c.get("attempt")
        out = []
        for b in rows:
            if b.get("attempt") is None:
                att = b2a.get(b.get("bundle"))
                if att is None and b.get("sig"):
                    att = self.sig_to_attempt.get(b["sig"])
                if att is not None:
                    b = dict(b)
                    b["attempt"] = att
            out.append(b)
        return out

    @cached_property
    def verdicts_by_attempt(self) -> dict:
        """Every block-engine result per attempt in arrival order (v1 kept only the first in outcomes, but
        bundles.jsonl has them all)."""
        d: dict = {}
        for b in self.bundles:
            if b.get("attempt") is not None:
                d.setdefault(b["attempt"], []).append(b)
        for v in d.values():
            v.sort(key=lambda b: (b.get("t_ns") or 0))
        return d

    @cached_property
    def status(self) -> list:
        return self.jsonl("status")

    @cached_property
    def status_agg(self) -> dict:
        return counters.legacy_status(self.status) if self.legacy else counters.aggregate(self.status)

    @cached_property
    def decisions(self) -> list:
        """Decision lines with follow-up flag lines (`{decision, torn_suspect|fork_priced: true}`) merged in."""
        base: dict = {}
        order = []
        for d in self.jsonl("decisions"):
            i = d.get("decision")
            if i in base and len(d) <= 3 and ("torn_suspect" in d or "fork_priced" in d):
                for k in ("torn_suspect", "fork_priced"):
                    if k in d:
                        base[i][k] = d[k]
                continue
            base[i] = dict(d)
            order.append(i)
        return [base[i] for i in order]

    @cached_property
    def decisions_by_id(self) -> dict:
        return {d.get("decision"): d for d in self.decisions}

    @cached_property
    def ledger(self) -> list:
        return self.jsonl("ledger")

    @cached_property
    def ledger_by_sig(self) -> dict:
        return {r.get("sig"): r for r in self.ledger}

    @cached_property
    def wallet_rows(self) -> list:
        return list(streams.iter_exec(self.stream_files("wallet")))

    @cached_property
    def wallet_txs(self) -> list:
        """Our wallet's landed transactions as TxViews: the v2 wallet stream, or wallet fixtures given for v1 runs."""
        if self.has("wallet"):
            return [solana.TxView.from_exec(r) for r in self.wallet_rows]
        return list(self._wallet_txs_extra or [])

    @cached_property
    def chain_ledger(self) -> list:
        return [legacy.research_ledger_row(r) for r in (self._chain_ledger_extra or [])]

    @cached_property
    def slotidx(self) -> dict:
        return {r["slot"]: r for r in self.jsonl("slotidx") if "slot" in r}

    @cached_property
    def leaders(self) -> dict:
        d = {}
        for r in self.jsonl("leaders"):
            if "slot" in r:
                d[r["slot"]] = r
        return d

    @cached_property
    def events(self) -> list:
        return self.jsonl("events")

    def iter_exec(self):
        if self.v1("exec"):
            for e in streams.iter_jsonl(self.stream_files("exec"), "exec"):
                yield legacy.exec_row(e)
        else:
            yield from streams.iter_exec(self.stream_files("exec"))

    # ------------------------------------------------------------------ windows
    @cached_property
    def window(self) -> dict:
        """Wall hours = meta start -> stop end (§6.2 rule 9); trading hours = warm-up ready -> stop minus shadow
        periods (events). v1 has neither stop.json nor events: its end is the last status line."""
        m = self.meta or {}
        start = (m.get("run") or {}).get("started_ns") if isinstance(m.get("run"), dict) else m.get("started_ns")
        start_src = "meta.json"
        if start is None:
            ts = [s.get("t_ns") for s in self.status[:1] if s.get("t_ns")]
            ts += [a.get("t_ns") for a in self.attempts[:1] if a.get("t_ns")]
            start = min(ts) if ts else None
            start_src = "first status/attempt line (no meta.json): wall hours are a lower bound"
        end = (self.stop or {}).get("ended_ns")
        end_src = "stop.json"
        if end is None:
            ts = [s.get("t_ns") for s in self.status if s.get("t_ns")]
            ts += [o.get("t_ns") for o in self.outcome_lines if o.get("t_ns")]
            end = max(ts) if ts else None
            end_src = "last status/outcome line"
        wall = (end - start) / 3.6e12 if (start and end) else None
        trading = None
        trading_src = None
        if self.events:
            ready = next((e["t_ns"] for e in self.events if e.get("kind") == "warmup_ready"), None)
            if ready is not None and end:
                run = m.get("run") if isinstance(m.get("run"), dict) else {}
                mode = "live" if (run.get("mode", "live") in ("live", "canary") and not run.get("forced_shadow")) else "shadow"
                t = ready
                live_ns = 0
                for e in sorted(self.events, key=lambda e: e.get("t_ns") or 0):
                    if e.get("t_ns", 0) < ready or e.get("kind") != "gate_change":
                        continue
                    if mode == "live":
                        live_ns += e["t_ns"] - t
                    mode = (e.get("detail") or {}).get("to", mode)
                    t = e["t_ns"]
                if mode == "live":
                    live_ns += end - t
                trading = live_ns / 3.6e12
                trading_src = "events"
        return {"start_ns": start, "start_src": start_src, "end_ns": end, "end_src": end_src, "wall_hours": _r(wall),
                "trading_hours": _r(trading), "trading_src": trading_src}

    # ------------------------------------------------------------------ provenance
    def inputs(self) -> list:
        out = []
        for stream, fis in sorted(self.files.items()):
            for fi in fis:
                streams.peek(fi)
                out.append({"file": fi.name, "stream": stream, "bytes": fi.size, "sha256": streams.sha256_file(fi.path),
                            "schema": fi.schema or ("v1 (arb-lab)" if fi.legacy else None),
                            "records_read": fi.records or None, "partial_tail": fi.partial_tail or None,
                            "truncated_bytes": fi.truncated_bytes or None})
        for fn in ("meta.json", "stop.json", "manifest.json", "probe.json", "pools.json", "config.toml"):
            p = os.path.join(self.dir, fn)
            if os.path.exists(p) and not any(x["file"] == fn for x in out):
                out.append({"file": fn, "stream": fn.split(".")[0], "bytes": os.path.getsize(p),
                            "sha256": streams.sha256_file(p)})
        return sorted(out, key=lambda x: x["file"])

    # ------------------------------------------------------------------ joins
    def land_rate_denominator(self) -> dict:
        """§6.2 rule 4: attempts with at least one copy actually sent (t_sent > 0) and accepted (ok)."""
        sent = set()
        src = "copies"
        for c in self.copies:
            if (c.get("t_sent") or 0) > 0 and c.get("ok"):
                sent.add(c.get("attempt"))
        if not self.has("copies") and self.v1("outcomes"):
            # v1 segments copied without copies.jsonl: outcomes carry the copies (t_sent, accepted)
            src = "outcomes.copies (v1)"
            for a, o in self.outcomes.items():
                for c in ((o.get("legacy") or {}).get("copies") or []):
                    if (c.get("t_sent") or 0) > 0 and c.get("accepted"):
                        sent.add(a)
        return {"attempts": len(self.attempts), "sent": len(sent), "sent_ids": sent, "src": src}


def _r(x, nd=4):
    return None if x is None else round(x, nd)


def is_segment_dir(p: str) -> bool:
    if not os.path.isdir(p):
        return False
    names = os.listdir(p)
    return any(n.startswith(("attempts.", "meta.json", "status.", "outcomes.")) for n in names)


class Campaign:
    def __init__(self, segments: list, name: str, campaign_json: dict | None = None):
        self.segments = segments
        self.name = name
        self.campaign_json = campaign_json

    @classmethod
    def open(cls, path: str, match: str | None = None, wallet_txs: list | None = None,
             chain_ledger: list | None = None) -> "Campaign":
        """A campaign directory (campaign.json lists its segments) or any directory of segment directories
        (`match`: a regex on segment names, e.g. `^w5h2-p`)."""
        cj = streams.read_json(os.path.join(path, "campaign.json"), "campaign")
        if cj and cj.get("segments"):
            names = [s["name"] for s in cj["segments"]]
        else:
            names = [n for n in os.listdir(path) if is_segment_dir(os.path.join(path, n))]
        if match:
            rx = re.compile(match)
            names = [n for n in names if rx.search(n)]
        names = sorted(set(names), key=natural_key)
        segs = []
        for n in names:
            p = os.path.join(path, n)
            if not os.path.isdir(p):
                continue
            cl = [r for r in (chain_ledger or []) if r.get("seg") in (None, n)]
            segs.append(Segment(p, n, wallet_txs=wallet_txs, chain_ledger=cl))
        return cls(segs, (cj or {}).get("name") or os.path.basename(os.path.abspath(path)), cj)
