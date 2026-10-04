"""blockctx windows and deduplication; R4 on a synthetic block with a single-pool closer, a failed attempted closer
and a persisted gap; the coverage denominator D1 u D2."""
import unittest

from helpers import TmpDir, gen, synth_ctx, synth_segment

from arbx_report import blockctx, quote
from arbx_report.reports import r0_quality, r4_attribution, r5_latency


class BlockCtx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TmpDir()
        root = cls.tmp.__enter__()
        cls.seg = synth_segment(root)
        cls.built = blockctx.build(cls.seg)
        cls.rows = {r["attempt"]: r for r in cls.built["rows"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def test_windows(self):
        # [trigger slot, max(landed slot, last verdict slot, trigger + 4)] + 1
        self.assertEqual(self.rows[0]["window"], {"from_slot": 1000, "to_slot": 1005})
        self.assertEqual(self.rows[1]["window"], {"from_slot": 1003, "to_slot": 1008})
        self.assertEqual(self.rows[2]["window"], {"from_slot": 1006, "to_slot": 1011})
        self.assertEqual(self.rows[3]["window"], {"from_slot": 1008, "to_slot": 1013})

    def test_shared_slots_built_once(self):
        self.assertEqual(self.built["slot_refs"], 30)
        self.assertEqual(self.built["slots_processed"], 14)

    def test_block_order_and_positions(self):
        r1 = self.rows[1]
        s1003 = [s for s in r1["slots"] if s["slot"] == 1003][0]
        self.assertEqual([t["sig"] for t in s1003["txs"]], [gen.S["T1"], gen.S["F1"], gen.S["S1"]])
        self.assertEqual([t["idx"] for t in s1003["txs"]], [5, 6, 7])
        self.assertEqual(r1["trigger"], {"slot": 1003, "idx": 5})
        self.assertEqual(self.rows[0]["ours"], {"slot": 1000, "idx": 40})
        self.assertEqual(s1003["kind"], "jito")

    def test_complete_flags(self):
        self.assertTrue(self.rows[0]["complete"])
        self.assertTrue(self.rows[2]["complete"])
        self.assertFalse(self.rows[3]["complete"])  # slot 1013 has no slot-index line
        self.assertIn(1013, self.built["gap_slots"])
        self.assertEqual(self.rows[0]["src"], "recorded")

    def test_file_rows_have_spec_fields(self):
        fr = blockctx.file_rows(self.built)[1]
        self.assertEqual(set(fr), {"attempt", "route_accounts", "window", "slots", "trigger", "ours", "closer", "src", "complete"})
        tx = fr["slots"][0]["txs"][0]
        self.assertEqual(set(tx), set(blockctx.FILE_TX_FIELDS))


class FillGaps(unittest.TestCase):
    def test_gap_slot_filled_from_cached_block(self):
        import json
        import os
        from arbx_report import chain
        with TmpDir() as root:
            seg = synth_segment(root)
            ch = chain.Chain(os.path.join(seg.dir, "chain-cache"), None, offline=True)
            built = blockctx.build(seg, ch, fill_gaps=True)  # offline, nothing cached: the gap stays
            self.assertEqual(built["gap_slots"], [1013])
            p = ch._cache_path("getBlock", "1013-full")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                json.dump({"blockhash": "x", "transactions": []}, f)
            built = blockctx.build(seg, ch, fill_gaps=True)
            rows = {r["attempt"]: r for r in built["rows"]}
            self.assertEqual(built["gap_slots"], [])
            self.assertEqual(built["gaps_filled"], 1)
            self.assertTrue(rows[3]["complete"])
            self.assertEqual(rows[3]["src"], "mixed")
            self.assertEqual(rows[0]["src"], "recorded")


class Attribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TmpDir()
        root = cls.tmp.__enter__()
        cls.seg = synth_segment(root)
        cls.ctx = synth_ctx()
        cls.sec = r4_attribution.run(cls.seg, cls.ctx)
        cls.res = {r["attempt"]: r for r in cls.sec["data"]["rows"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def test_our_win_closes_its_own_gap(self):
        self.assertEqual(self.res[0]["result"], "closed")
        self.assertEqual(self.res[0]["closer"]["kind"], "ours")

    def test_single_pool_closer_and_failed_attempted_closer(self):
        r = self.res[1]
        self.assertEqual(r["result"], "closed")
        c = r["closer"]
        self.assertEqual((c["sig"], c["kind"], c["slot"], c["idx"]), (gen.S["S1"], "user_swap", 1003, 7))
        self.assertEqual(c["relative"], {"same_slot": True, "idx_after_trigger": 2, "slots_after_trigger": 0})
        self.assertEqual([a["sig"] for a in r["attempted_closers"]], [gen.S["F1"]])
        self.assertEqual(c["ms_after_trigger_poh"], 1.25)  # same slot: same leader's PoH clock
        self.assertTrue(c["seen_before_our_send"])
        self.assertEqual(c["rung"], 2)  # idx+2 after its opener (the trigger)
        self.assertEqual(self.sec["data"]["closer_rung"], {"2 idx+2..5": 1})

    def test_rung_ladder(self):
        from arbx_report import blockctx as b
        self.assertEqual(b.rung((10, 5), (10, 6)), 1)
        self.assertEqual(b.rung((10, 5), (10, 6), same_bundle=True), 0)
        self.assertEqual(b.rung((10, 5), (10, 10)), 2)
        self.assertEqual(b.rung((10, 5), (10, 11)), 3)
        self.assertEqual(b.rung((10, 5), (11, 0)), 4)
        self.assertEqual(b.rung((10, 5), (13, 0)), 5)
        self.assertIsNone(b.rung((10, 5), (10, 4)))

    def test_persisted_gap(self):
        self.assertEqual(self.res[2]["result"], "persisted")
        self.assertIsNone(self.res[2]["closer"])
        self.assertEqual(self.res[3]["result"], "persisted_incomplete")

    def test_without_pricer_only_wins_are_attributed(self):
        ctx = synth_ctx(pricer=quote.ArbxQuote("/nonexistent/arbx"))
        sec = r4_attribution.run(self.seg, ctx)
        res = {r["attempt"]: r for r in sec["data"]["rows"]}
        self.assertFalse(sec["complete"])
        self.assertEqual(res[0]["closer"]["kind"], "ours")
        self.assertEqual(res[1]["result"], "needs_quote")

    def test_summary_and_latency_use_closers(self):
        d = self.sec["data"]
        self.assertEqual(d["by_result"], {"closed": 2, "persisted": 1, "persisted_incomplete": 2})
        self.assertEqual(d["closer_kind"], {"ours": 1, "user_swap": 1})
        self.assertEqual(d["attempted_closers"], 1)
        ctx = dict(self.ctx, r4_rows=d["rows"])
        lat = r5_latency.run(self.seg, ctx)["data"]["poh_ms_after_trigger"]
        self.assertEqual(lat["closers"]["p50"], 1.25)
        self.assertEqual(lat["ours"]["p50"], 11.5)


class Coverage(unittest.TestCase):
    def test_denominator_d1_union_d2(self):
        with TmpDir() as root:
            seg = synth_segment(root)
            ctx = synth_ctx()
            sec = r0_quality.run(seg, ctx)
            cov = sec["data"]["exec_coverage"]
            # D1: txns of account writes (T0, O0, T1, S1, T2, W2, T3, Y3); D2: slot-index tracked (adds F1, O2, Z9)
            self.assertEqual(cov["denominator"], {"d1_account_txn": 8, "d2_slotidx_tracked": 11, "union": 11})
            self.assertEqual(cov["within_10min_with_idx"]["have"], 11)
            self.assertEqual(cov["within_10min_with_idx"]["pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
