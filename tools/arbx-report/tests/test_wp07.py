"""WP-07 review #11: a later segment's pre-run fetch writes a signature an earlier segment of the campaign already
recorded again, marked `dup: true`. The toolkit counts it once, in R1 and in the campaign roll-up, as the Rust side
(spend.json, `ledger::history`) does.
"""
import json
import os
import unittest

import gen
from helpers import TmpDir, synth_ctx

from arbx_report import model, runner


def fee_line(sig: str, slot: int, fee: int, dup: bool = False) -> dict:
    r = {"sig": sig, "slot": slot, "kind": "route", "ok": False, "fee": fee, "tip": 0, "wallet_sol": -fee, "wsol": 0, "liquid_delta": -fee,
         "equity_delta": -fee, "trade_gross": 0, "trade_net": -fee, "rent_locked": 0, "rent_reclaimed": 0, "rent_nonrecoverable": 0,
         "categories": [{"cat": "fee_fail", "lamports": -fee}], "pre_run": dup}
    if dup:
        r["dup"] = True
    return r


def segment(root: str, name: str, started: int, lines: list) -> str:
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"schema": "arbx.meta/2.0", "run": {"segment": name, "started_ns": started, "mode": "canary"}}, f)
    gen.write_plain(d, "ledger.jsonl", "ledger", "1.0", lines)
    return d


class DupLines(unittest.TestCase):
    def test_a_dup_line_is_counted_once(self):
        with TmpDir() as root:
            segment(root, "c-p1", gen.T0_NS, [fee_line("a", 100, 7_000), fee_line("b", 101, 5_000)])
            segment(root, "c-p2", gen.T0_NS + 10, [fee_line("b", 101, 5_000, dup=True), fee_line("c", 200, 6_000)])
            camp = model.Campaign.open(root)
            self.assertEqual([s.name for s in camp.segments], ["c-p1", "c-p2"])
            p2 = camp.segments[1]
            self.assertEqual(([r["sig"] for r in p2.ledger], [r["sig"] for r in p2.ledger_dup]), (["c"], ["b"]))
            money = runner._campaign_money_v2(camp.segments)
            self.assertEqual(money["summing_categories"]["fee_fail"], -18_000, "a, b and c once each: 7,000 + 5,000 + 6,000")
            self.assertEqual(money["trade_net"], -18_000)


if __name__ == "__main__":
    unittest.main()
