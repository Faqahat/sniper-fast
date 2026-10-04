"""Legacy (arb-lab v1) known-answer tests on the WP-00b fixtures in testdata/legacy/ (MEASUREMENT §6.5, PLAN WP-10).

- res-pnl's w5h p1-p10 decomposition: trading net -2,337,448; rent 16,383,000 (15,036,800 recoverable token-account
  rent + 1,346,200 PumpSwap accumulator); profit_lamports -16,201,607; liquid change -18,720,448.
- wallet-synthesis W §2/§3 figures for the two w5h2/w5h3 segments preserved in testdata (the bolt trade).
- Optional (env ARBX_REPORT_CHERRY=<scratch cherry root>): the full w5h2-p1..p11 + w5h3-p1..p2 campaign against W §2
  (24 wins, 986 failed landings, 24,367,491 failure fees, wallet change -14,834,557).
"""
import hashlib
import json
import os
import unittest

from helpers import LEGACY_RAW, REPO, WALLET_FIXTURE

from arbx_report import model, solana
from arbx_report.reports import r1_money, r2_funnel, r3_attempts

WALLET = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
WALLET_FIXTURE_SHA256 = "3687ee90e2750586a8178f98b128965a815752358c784855e329bc63077e45be"


def wallet_txs():
    """testdata/wallet/ (WP-00b) when present, else this toolkit's fixture of the same transactions."""
    d = os.path.join(REPO, "testdata", "wallet")
    if os.path.isdir(d) and any(f.endswith(".json") for f in os.listdir(d)):
        out = []
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                out += solana.load_tx_file(os.path.join(d, f))
        return out
    return solana.load_tx_file(WALLET_FIXTURE)


@unittest.skipUnless(os.path.isdir(LEGACY_RAW), "testdata/legacy/raw missing")
class Fixtures(unittest.TestCase):
    def test_sha256(self):
        with open(os.path.join(REPO, "testdata", "legacy", "raw.sha256")) as f:
            for line in f:
                h, p = line.split()
                with open(os.path.join(LEGACY_RAW, p), "rb") as g:
                    self.assertEqual(hashlib.sha256(g.read()).hexdigest(), h, p)
        with open(WALLET_FIXTURE, "rb") as g:
            self.assertEqual(hashlib.sha256(g.read()).hexdigest(), WALLET_FIXTURE_SHA256)


@unittest.skipUnless(os.path.isdir(LEGACY_RAW), "testdata/legacy/raw missing")
class ResPnlP1P10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.camp = model.Campaign.open(LEGACY_RAW, r"^w5h-p\d+$", wallet_txs=wallet_txs())
        for s in cls.camp.segments:
            s.__dict__["wallet"] = WALLET  # testdata has no meta.json (v1 meta holds config Debug strings)
        cls.m = r1_money.campaign_legacy(cls.camp.segments)

    def test_segments(self):
        self.assertEqual([s.name for s in self.camp.segments], [f"w5h-p{i}" for i in range(1, 11)])
        self.assertTrue(all(s.legacy for s in self.camp.segments))

    def test_recorded_decomposition(self):
        r = self.m["recorded"]
        self.assertEqual(r["gross_round_trip"], 632_807)
        self.assertEqual(r["tips"], 337_744)
        self.assertEqual(r["fees_win"], 113_670)
        self.assertEqual(r["fees_fail"], 2_497_246)
        self.assertEqual(r["rent_on_wins"], 16_383_000)
        self.assertEqual(r["profit_lamports_v1"], -16_201_607)
        self.assertEqual(r["wins"], 21)
        self.assertEqual(self.m["win_net"]["total"], 181_393)  # the trades themselves made +181,393 net

    def test_chain_corrected_trading_net(self):
        """The bot never recorded 2 landed failures (p1#2 7,301 and p2#8 14,294): res-pnl's -2,337,448."""
        self.assertEqual(self.m["chain_unrecorded"], {"fees_fail": 21_595, "landed": 2, "landed_failures": 2,
                                                      "trade_net": -21_595, "wins": 0})
        self.assertEqual(self.m["trade_net_chain_corrected"], -2_337_448)
        self.assertEqual(self.m["landed_failures_total"], 98)
        self.assertEqual(self.m["net_wallet_change"], -18_720_448)  # res-pnl C5

    def test_rent_split_from_chain(self):
        rec = nonrec = 0
        for s in self.camp.segments:
            ch = r1_money.legacy_money(s)["chain"]["rent"]
            rec += ch["locked_recoverable"]
            nonrec += ch["nonrecoverable"]
        self.assertEqual(rec, 15_036_800)
        self.assertEqual(nonrec, 1_346_200)
        self.assertEqual(rec + nonrec, 16_383_000)

    def test_per_segment_and_status_last_line(self):
        want = {"w5h-p2": (4, 1_318_650 + 14_294), "w5h-p6": (58, 755_198), "w5h-p7": (8, 0), "w5h-p10": (7, 0)}
        for s in self.camp.segments:
            m = r1_money.legacy_money(s)
            st = s.status_agg
            # the status line's running total equals the outcomes' sum (take the last line, never the sum)
            self.assertEqual(st["failed_fees_lamports"]["last_line"], m["recorded"]["fees_fail"], s.name)
            if s.name in want:
                landed, fails = want[s.name]
                self.assertEqual(m["recorded"]["landed"] + m["chain"]["unrecorded"]["landed"], landed, s.name)
                self.assertEqual(m["fees_fail_total"], fails, s.name)
        p10 = [s for s in self.camp.segments if s.name == "w5h-p10"][0]
        self.assertEqual(r1_money.legacy_money(p10)["recorded"]["rent_on_wins"], 6_004_560)

    def test_land_rate_uses_sent_copies(self):
        p1 = [s for s in self.camp.segments if s.name == "w5h-p1"][0]
        d = r3_attempts.run(p1, {})["data"]["land_rate"]
        # v1 status 'sent' (917) counted sim-gated attempts that never went out
        self.assertLess(d["denominator_sent_attempts"], 917)
        self.assertEqual(d["landed"], 13)
        f = r2_funnel.run(p1, {})["data"]
        self.assertGreater(f["not_sent_v1 (sim-gated, counted as 'sent' by v1 status)"], 0)


@unittest.skipUnless(os.path.isdir(LEGACY_RAW), "testdata/legacy/raw missing")
class WalletSynthesisSegments(unittest.TestCase):
    """W §2/§3 figures that the two preserved w5h2/w5h3 segments determine on their own."""

    def seg(self, name):
        return model.Segment(os.path.join(LEGACY_RAW, name))

    def test_bolt_trade_w5h2_p5(self):
        s = self.seg("w5h2-p5")
        bolt = s.outcomes[648]
        self.assertEqual(bolt["final"], "landed_ok")
        self.assertEqual(bolt["round_trip_on_chain"], 30_002_068)
        self.assertEqual(bolt["legacy"]["tip_paid_lamports"], 1_000_000)
        self.assertEqual(bolt["fee_lamports"], 28_601)
        self.assertEqual(bolt["legacy"]["rent_residual"], 1_513_840)
        self.assertEqual(bolt["legacy"]["profit_lamports"], 27_459_627)
        m = r1_money.legacy_money(s)
        self.assertTrue(m["win_net"]["jackpot_flag"])  # the window's only real profit was one lucky trade
        self.assertEqual(m["by_arm"]["direct"]["trade_net"], 28_973_467 - 1_920_788)
        self.assertEqual(m["by_arm"]["bundle"]["trade_net"], 12_794 - 5_455 - 5_000)

    def test_w5h3_p2(self):
        m = r1_money.legacy_money(self.seg("w5h3-p2"))["recorded"]
        self.assertEqual((m["wins"], m["landed_failures"], m["fees_fail"]), (1, 96, 2_647_202))
        self.assertEqual((m["gross_round_trip"], m["tips"], m["fees_win"]), (14_439, 6_607, 5_000))


CHERRY = os.environ.get("ARBX_REPORT_CHERRY")


@unittest.skipUnless(CHERRY and os.path.isdir(os.path.join(CHERRY or "", "root", "runs")),
                     "set ARBX_REPORT_CHERRY to the scratch copy of Cherry (root/runs, work/shared/derived)")
class WalletSynthesisCampaign(unittest.TestCase):
    """W §2: the whole w5h2-p1..p11 + w5h3-p1..p2 window, with the research chain ledger (all 1,010 signatures)."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(CHERRY, "work", "shared", "derived", "ledger-w5h2w5h3.jsonl")) as f:
            led = [json.loads(x) for x in f if x.strip()]
        runs = os.path.join(CHERRY, "root", "runs")
        cls.all = r1_money.campaign_legacy(model.Campaign.open(runs, r"^w5h[23]-p\d+$", chain_ledger=led).segments)
        cls.w2 = r1_money.campaign_legacy(model.Campaign.open(runs, r"^w5h2-p\d+$", chain_ledger=led).segments)
        cls.w3 = r1_money.campaign_legacy(model.Campaign.open(runs, r"^w5h3-p\d+$", chain_ledger=led).segments)

    def test_counts(self):
        self.assertEqual(self.all["wins_total"], 24)
        self.assertEqual(self.all["landed_failures_total"], 986)
        self.assertEqual(self.all["recorded"]["landed"], 994)
        self.assertEqual(self.all["chain_unrecorded"]["landed"], 16)

    def test_money(self):
        r = self.all["recorded"]
        self.assertEqual((r["gross_round_trip"], r["tips"], r["fees_win"]), (30_670_547, 1_390_292, 143_601))
        self.assertEqual(r["fees_fail"], 23_947_580)
        self.assertEqual(self.all["chain_unrecorded"]["fees_fail"], 419_911)
        self.assertEqual(self.all["fees_fail_total"], 24_367_491)
        self.assertEqual(r["rent_on_wins"], 19_603_720)
        self.assertEqual(self.all["trade_net_chain_corrected"], 4_769_163)
        self.assertEqual(self.all["net_wallet_change"], -14_834_557)
        self.assertEqual(self.w2["net_wallet_change"], -10_535_176)
        self.assertEqual(self.w3["net_wallet_change"], -4_299_381)
        self.assertEqual(self.w2["chain_unrecorded"]["fees_fail"], 332_506)
        self.assertEqual(self.w3["chain_unrecorded"]["fees_fail"], 87_405)

    def test_attempt_level_joins(self):
        """W §4/§6: 989 direct attempts (2 sim-gated, 987 sent); 1 win in 1,511 attempts of >= 1 SOL (bundle 0/901,
        direct 1/609 sent); direct failures seen p50 137 ms (p90 349) after the send."""
        from arbx_report import stats
        runs = os.path.join(CHERRY, "root", "runs")
        camp = model.Campaign.open(runs, r"^w5h[23]-p\d+$")
        c: dict = {}
        s2s = []
        for s in camp.segments:
            sent = s.land_rate_denominator()["sent_ids"]
            for a in s.attempts:
                arm = a["legacy"]["path_arm"]
                o = s.outcomes.get(a["attempt"]) or {}
                big = (a.get("size_lamports") or 0) >= 10 ** 9
                for k, hit in (("attempts", True), ("sent", a["attempt"] in sent), ("gated", o.get("final") == "not_sent_v1"),
                               ("wins", o.get("final") == "landed_ok")):
                    if hit:
                        c[(arm, k)] = c.get((arm, k), 0) + 1
                        if big:
                            c[(arm, k, ">=1SOL")] = c.get((arm, k, ">=1SOL"), 0) + 1
                if arm == "tpu" and o.get("final") == "landed_fail" and o.get("send_to_seen_ms") is not None:
                    s2s.append(o["send_to_seen_ms"])
        self.assertEqual((c[("tpu", "attempts")], c[("tpu", "gated")], c[("tpu", "sent")]), (989, 2, 987))
        self.assertEqual(c[("tpu", "attempts", ">=1SOL")] + c[("bundle", "attempts", ">=1SOL")], 1511)
        self.assertEqual((c[("bundle", "attempts", ">=1SOL")], c.get(("bundle", "wins", ">=1SOL"), 0)), (901, 0))
        self.assertEqual((c[("tpu", "sent", ">=1SOL")], c[("tpu", "wins", ">=1SOL")]), (609, 1))
        p = stats.pct(s2s)
        self.assertEqual((round(p["p50"]), round(p["p90"])), (137, 349))

    def test_arms(self):
        b, d = self.all["by_arm"]["bundle"], self.all["by_arm"]["direct"]
        self.assertEqual(b["trade_net"], 163_187)
        self.assertEqual(b["trade_net"] - b["rent"], -17_926_693)
        self.assertEqual(d["trade_net"], 4_605_976)
        self.assertEqual(d["trade_net"] - d["rent"], 3_092_136)
        self.assertEqual(d["wins"], 1)
        self.assertEqual(b["wins"], 23)


if __name__ == "__main__":
    unittest.main()
