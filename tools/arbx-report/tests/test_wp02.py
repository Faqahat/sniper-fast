"""WP-02 segments (WP-02 review F3, F14): arbx from WP-02 writes attempts, bundles, outcomes, exec, triggers and
predictions as arb-lab's v1 record behind a `/1.1` header (MEASUREMENT §1.6, §7), beside v2 meta and status. The
toolkit reads them (major 1 is accepted for those streams) and maps them through `legacy.py` per stream; the renamed
outcome field `failed_fees_total_lamports` (and `failed_fees_delta_lamports`) maps like arb-lab's
`failed_fees_lamports`.
"""
import json
import lzma
import os
import unittest

import gen
from helpers import LEGACY_RAW, TmpDir, synth_ctx

from arbx_report import model, runner, streams


def v1_rows(stream: str) -> list:
    with lzma.open(os.path.join(LEGACY_RAW, "w5h-p1", f"{stream}.jsonl.xz"), "rt") as f:
        return [json.loads(l) for l in f if l.strip()]


def wp02_segment(root: str) -> str:
    """A segment as WP-02 writes it: meta v2, status v2 (plain, header first), the v1.1 streams behind headers"""
    d = os.path.join(root, "wp02-p1")
    os.makedirs(d)
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"schema": "arbx.meta/2.0", "run": {"segment": "wp02-p1", "started_ns": gen.T0_NS, "mode": "shadow"}, "wallet": {"pubkey": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}}, f)
    gen.write_plain(d, "status.jsonl", "status", "2.0", [{"seq": 0, "t_ns": gen.T0_NS + 10**10, "money": {"failed_fees_total_lamports": 15000}}])
    gen.write_plain(d, "events.jsonl", "events", "1.0", [{"t_ns": gen.T0_NS, "kind": "warmup_ready", "subsystem": "engine", "feed": None, "detail": {}}])
    outcomes = v1_rows("outcomes")
    for o in outcomes:  # WP-02's rename (review F14)
        if "failed_fees_lamports" in o:
            o["failed_fees_total_lamports"] = o.pop("failed_fees_lamports")
            o["failed_fees_delta_lamports"] = 0
    gen.write_zjsonl(d, "attempts", "1.1", v1_rows("attempts"))
    gen.write_zjsonl(d, "outcomes", "1.1", outcomes)
    gen.write_zjsonl(d, "bundles", "1.1", v1_rows("bundles"))
    gen.write_zjsonl(d, "copies", "1.1", v1_rows("copies"))
    gen.write_zjsonl(d, "exec", "1.1", [{"sig": "s1", "slot": 1, "idx": 3, "t": gen.T0_NS, "ok": True, "err": None, "why": None, "fee": 5000, "cu": 1,
                                          "signer": "x", "sol": -5000, "tok": {}}])
    gen.write_zjsonl(d, "triggers", "1.1", [{"slot": 1, "pool": "p", "venue": "PumpSwap"}])
    gen.write_zjsonl(d, "predictions", "1.1", [{"venue": "PumpSwap", "pool": "p", "exact": True}])
    return d


class Wp02Segment(unittest.TestCase):
    def test_v1_1_streams_are_read_through_the_legacy_mapping(self):
        with TmpDir() as root:
            seg = model.Segment(wp02_segment(root))
            self.assertFalse(seg.legacy, "meta v2: a v2 segment")
            for s in ("attempts", "outcomes", "bundles", "exec", "triggers", "predictions"):
                self.assertTrue(seg.v1(s), s)
                fi = streams.peek(seg.stream_files(s)[0])
                self.assertEqual((fi.major, fi.minor, fi.legacy), (1, 1, False), s)
            self.assertFalse(seg.v1("status"))
            raw = v1_rows("attempts")
            self.assertEqual(len(seg.attempts), len(raw))
            a = seg.attempts_by_id[raw[0]["attempt"]]
            self.assertEqual(a["route"]["buy_pool"], raw[0].get("buy_pool"), "the v2 shape, from the v1 record")
            o = next(o for o in seg.outcome_lines if o["legacy"]["failed_fees_lamports_running"] is not None)
            self.assertIn(o["final"], ("landed_ok", "landed_fail", "not_sent_v1", "not_landed_v1"))
            self.assertEqual(o["legacy"]["failed_fees_delta_lamports"], 0)
            self.assertEqual(next(seg.iter_exec())["signer_sol"], -5000)

    def test_the_segment_report_runs(self):
        with TmpDir() as root:
            seg = model.Segment(wp02_segment(root))
            doc = runner.segment(seg, synth_ctx())
            q = next(s for s in doc["sections"] if s["id"] == "R0")
            self.assertNotIn("unsupported_schema", q["data"], q["data"].get("unsupported_schema"))
            self.assertNotIn("unknown major", json.dumps(q))

    def test_an_unknown_major_is_still_refused(self):
        with TmpDir() as root:
            d = wp02_segment(root)
            gen.write_zjsonl(d, "attempts", "3.0", [{"attempt": 1}])
            with self.assertRaises(streams.SchemaError):
                model.Segment(d).attempts


if __name__ == "__main__":
    unittest.main()
