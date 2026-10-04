"""Rule tests of MEASUREMENT §6.2 on the synthetic segment: land rate from attempts only, missing is not zero,
amended outcomes (last line wins), landed-only caveat, money from the ledger with counters as a cross-check,
trading hours, first verdicts with the result stream down, experiments."""
import os
import unittest

from helpers import TmpDir, gen, synth_ctx, synth_segment, write_jsonl

from arbx_report import model, runner
from arbx_report.reports import LANDED_ONLY_CAVEAT, r1_money, r2_funnel, r3_attempts, r8_predictions, r10_experiments


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TmpDir()
        cls.root = cls.tmp.__enter__()
        cls.seg = synth_segment(cls.root)
        cls.ctx = synth_ctx()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def test_land_rate_denominator_is_sent_attempts(self):
        den = self.seg.land_rate_denominator()
        self.assertEqual(den["attempts"], 5)
        self.assertEqual(den["sent"], 4)  # attempt 4 was signed but never sent (t_sent = 0)
        d = r3_attempts.run(self.seg, self.ctx)["data"]
        self.assertEqual(d["land_rate"]["landed"], 2)
        self.assertEqual(d["land_rate"]["denominator_sent_attempts"], 4)
        self.assertEqual(d["land_rate"]["rate"], 0.5)

    def test_amended_outcome_last_line_wins(self):
        self.assertEqual(self.seg.outcomes[3]["final"], "not_landed_expired")
        self.assertEqual(self.seg.amends, [{"attempt": 3, "from": "unsettled", "to": "not_landed_expired"}])

    def test_missing_is_not_zero(self):
        """A value that was not observed is excluded and counted, never treated as 0."""
        d = r3_attempts.run(self.seg, self.ctx)["data"]
        # time to first verdict: attempts without a verdict are absent, not 0 ms
        self.assertEqual(d["time_to_first_verdict_ms"]["n"], 4)
        self.assertGreater(d["time_to_first_verdict_ms"]["p50"], 0)
        # predictions: pre_state unknown is counted, not scored
        p = r8_predictions.run(self.seg, self.ctx)["data"]["by_venue"]["Dlmm"]
        self.assertEqual((p["scored"], p["pre_state_unknown"], p["exact"]), (1, 1, 1))
        self.assertEqual(p["exact_rate_pre_state"], 1.0)

    def test_landed_only_caveat_is_printed(self):
        sec = r3_attempts.run(self.seg, self.ctx)
        self.assertIn(LANDED_ONLY_CAVEAT, sec["caveats"])
        rr = sec["data"]["realised_over_expected_landed_only"]
        self.assertEqual(rr["beside_would_fail"]["would_fail_attempts"], 1)
        self.assertEqual(rr["caveat"], LANDED_ONLY_CAVEAT)

    def test_money_from_ledger_and_counter_cross_check(self):
        d = r1_money.run(self.seg, self.ctx)["data"]
        self.assertEqual(d["trading"]["trade_net"], 10_000)
        self.assertEqual(d["trading"]["trade_gross"], 50_000)
        self.assertEqual(d["ledger"]["summing_total"], d["ledger"]["equity_delta_sum"])
        self.assertEqual(d["equity"]["delta_total"], 10_000)
        self.assertEqual(d["recon"][0]["arithmetic"], "ok")
        self.assertTrue(all(x["difference"] == 0 for x in d["status_cross_check"]))
        self.assertEqual(d["toolkit_recompute"], {"compared": 2, "differences": [], "differences_n": 0})

    def test_wall_and_trading_hours(self):
        w = self.seg.window
        self.assertEqual(w["wall_hours"], round(6 / 3600, 4))
        self.assertEqual(w["trading_hours"], round(5.1 / 3600, 4))  # warm-up at 0.5 s, shadow 1.6-2.0 s

    def test_funnel_and_status_deltas(self):
        d = r2_funnel.run(self.seg, self.ctx)["data"]
        st = dict(d["stages"])
        self.assertEqual(st["evaluations (decisions)"], 7)
        self.assertEqual(st["attempts (signed)"], 5)
        self.assertEqual(st["sent (a copy with t_sent > 0 and ok)"], 4)
        self.assertEqual(d["rejection_reasons"], {"below_min_profit": 1, "inflight_same_state": 1})
        cc = {x["counter"]: x for x in d["status_cross_check"]}
        self.assertEqual(cc["counts_delta.attempt"]["difference"], 0)
        self.assertEqual(self.seg.decisions_by_id[1]["torn_suspect"], True)  # follow-up flag line merged

    def test_first_verdict_with_stream_down(self):
        with TmpDir() as root:
            seg = synth_segment(root)
            # drop attempt 1's verdict: its send (slot 1003) falls outside the stream outage (slot 1009)
            p = os.path.join(seg.dir, "bundles.000.jsonl.zst")
            rows = [b for b in seg.bundles if b["attempt"] != 1]
            os.remove(p)
            write_jsonl(os.path.join(seg.dir, "bundles.jsonl"), rows,
                        {"schema": "arbx.bundles/2.0", "run": "x", "file_seq": 0, "started_ns": 0, "producer": "t"})
            seg2 = model.Segment(seg.dir)
            fv = r2_funnel.first_verdicts(seg2)
            self.assertEqual(fv[1], "none_stream_up")
            self.assertEqual(fv[0], "accepted")

    def test_experiments(self):
        d = r10_experiments.run(self.seg, self.ctx)["data"]
        self.assertEqual(d["balance"]["x4_share"]["counts"], {"0.4": 2, "0.6": 3})
        x4 = d["x4"]
        self.assertEqual(x4["baseline"], "0.6")
        self.assertEqual(x4["arms"]["0.6"]["land_rate"], round(2 / 3, 6))
        self.assertEqual(x4["arms"]["0.4"]["land_rate"], 0.0)
        self.assertFalse(x4["arms"]["0.4"]["go"])
        self.assertFalse(d["x5"]["enough_data"])


class CampaignReport(unittest.TestCase):
    def test_campaign_sums_last_totals_and_joins_late_landings(self):
        with TmpDir() as root:
            gen.generate_campaign(os.path.join(root, "synth"))
            camp = model.Campaign.open(os.path.join(root, "synth"))
            self.assertEqual([s.name for s in camp.segments], ["synth-p1", "synth-p2"])
            doc = runner.campaign(camp, synth_ctx())
            d = doc["sections"][0]["data"]
            self.assertEqual(d["status_totals"]["counts_total.attempt"], {"value": 10, "segments": 2, "missing": 0})
            self.assertEqual(d["money_v2"]["trade_net"], 20_000)
            late = [x for x in d["late_landings"] if x["segment"] == "synth-p1"]
            self.assertEqual(late, [{"segment": "synth-p1", "attempt": 3, "sig": gen.S["O3"], "found_in": "synth-p2",
                                     "slot": 1020, "ok": False}])
            from arbx_report.__main__ import main
            out = os.path.join(root, "out")
            self.assertEqual(main(["campaign", os.path.join(root, "synth"), "--out", out]), 0)
            self.assertTrue(os.path.exists(os.path.join(out, "campaign.json")))

    def test_quality_reports_slow_streams(self):
        with TmpDir() as root:
            seg = synth_segment(root)
            from arbx_report.reports import r0_quality
            d = r0_quality.run(seg, synth_ctx())["data"]
            self.assertEqual(d["txfetch"]["slotidx/getBlock"]["rate_limited"], 1)
            self.assertEqual(d["keepalive"]["errors"], 1)
            self.assertEqual(d["probe"], {"accepted": ["accounts_full"], "refused": ["blocks_meta"]})
            self.assertEqual(d["slotidx"]["with_line"], {"have": 13, "pct": 92.857, "total": 14})


class Golden(unittest.TestCase):
    """The golden report.json of the synthetic segment is byte-identical on re-run and across machines."""
    GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "synth-report.json")

    def build(self, root) -> str:
        seg = synth_segment(root)
        seg.tip_accounts = {gen.TIP}
        doc = runner.segment(seg, synth_ctx())
        from arbx_report import render
        return render.dumps(doc)

    def test_identical_on_rerun_and_matches_golden(self):
        with TmpDir() as a, TmpDir() as b:
            one, two = self.build(a), self.build(b)
        self.assertEqual(one, two)
        if os.environ.get("ARBX_REPORT_UPDATE_GOLDEN"):
            os.makedirs(os.path.dirname(self.GOLDEN), exist_ok=True)
            with open(self.GOLDEN, "w") as f:
                f.write(one)
        with open(self.GOLDEN) as f:
            self.assertEqual(one, f.read(), "golden report changed: re-run with ARBX_REPORT_UPDATE_GOLDEN=1 and review the diff")

    def test_cli_writes_report_and_blockctx(self):
        from arbx_report.__main__ import main
        with TmpDir() as root:
            seg = synth_segment(root)
            out = os.path.join(root, "out")
            self.assertEqual(main(["segment", seg.dir, "--out", out, "--offline"]), 0)
            self.assertTrue(os.path.exists(os.path.join(out, "report.json")))
            self.assertTrue(os.path.exists(os.path.join(out, "report.md")))
            with open(os.path.join(out, "blockctx.jsonl")) as f:
                self.assertEqual(len(f.readlines()), 5)


if __name__ == "__main__":
    unittest.main()
