"""WP-05 segments: attempts.jsonl 2.0 holds would-sends beside the sends (PLAN-ADDENDUM I-7: a shadow run, a dry run, or
a closed SendGate records every decision that passed all checks but the gate, with `sent` false). A would-send is no
attempt: it never reaches a land rate, a funnel's signed attempts or a leader table; the toolkit keeps it apart
(`Segment.would_sends`).
"""
import json
import os
import unittest

import gen
from helpers import TmpDir

from arbx_report import model


def wp05_segment(root: str) -> str:
    """A WP-05 segment: meta v2, attempts 2.0 with two sends (one without `sent`, as earlier v2 writers) and two
    would-sends (a shadow one, a dry run's)"""
    d = os.path.join(root, "wp05-p1")
    os.makedirs(d)
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"schema": "arbx.meta/2.0", "run": {"segment": "wp05-p1", "started_ns": gen.T0_NS, "mode": "live"}}, f)
    gen.write_plain(d, "attempts.jsonl", "attempts", "2.0", [
        {"attempt": 3, "kind": "live", "sent": True, "t_ns": gen.T0_NS + 3},
        {"attempt": 1, "kind": "live", "sent": False, "not_sent": "gate_shadow:control", "t_ns": gen.T0_NS + 1},
        {"attempt": 0, "kind": "live", "t_ns": gen.T0_NS},
        {"attempt": 2, "kind": "dry_run", "sent": False, "not_sent": "dry_run", "dry_run": {"checks_ok": True}, "t_ns": gen.T0_NS + 2},
    ])
    return d


class WouldSends(unittest.TestCase):
    def test_would_sends_are_not_attempts(self):
        with TmpDir() as root:
            seg = model.Segment(wp05_segment(root))
            self.assertFalse(seg.v1("attempts"))
            self.assertEqual([a["attempt"] for a in seg.attempts], [0, 3], "sends only, in attempt order")
            self.assertEqual(sorted(seg.attempts_by_id), [0, 3])
            self.assertEqual([(a["attempt"], a["not_sent"]) for a in seg.would_sends], [(1, "gate_shadow:control"), (2, "dry_run")])
            self.assertEqual(seg.land_rate_denominator()["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
