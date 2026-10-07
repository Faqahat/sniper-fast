"""WP-11: `arbx-report experiments` over a synthetic two-segment campaign with two experiments at once (X4 tip share
x size cap, a 3 x 2 factorial): per arm attempts, landings and wins with intervals, net per attempt and per win,
tips / gross, the meme and common wins by the route's mint, the balance by band and trigger kind and over the
decisions, each arm against its control, the factorial's cells; money from the ledger across the segments, `pre_run`
and `dup` lines left out (in R1 too); X2's two-sided trend test."""
import json
import os
import unittest

import gen
from helpers import TmpDir, synth_ctx

from arbx_report import model, runner, stats, tokens
from arbx_report.reports import r1_money, r10_experiments

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
MEME = "75gGuxuqKhQQiHae8JKDQaetK3XguKf1rUJ1csispump"
CAKE_LOOKALIKE = "DAemPFNc3RtibBDKkUA4eL2Ns11q9VRdbpptmqm8DGqN"
X4 = [0.1, 0.2, 0.35]
SIZE = [0.05, 0.2]
HOUR = 3_600_000_000_000


def attempt(a: int, sig: str, band: int, kind: str, mint: str, arms: dict) -> dict:
    return {"attempt": a, "decision": 100 + a, "opp": a, "t_ns": gen.T0_NS + a, "kind": "canary", "sent": True,
            "trigger": {"txn": gen.sg(f"trig{a}"), "slot": 1000, "kind": kind}, "route": {"mint": mint, "buy_venue": "Dlmm", "sell_venue": "PumpSwap"},
            "size_lamports": 50_000_000, "band": band, "experiments": arms, "tip": {"lamports": 1000, "arm": arms.get("x4_share")},
            "leader": {"kind": "jito"}, "tx": {"sig": sig}, "copies": [{"path": "jito-bundle", "sig": sig}]}


def ledger_line(sig: str, a, ok: bool, net: int, gross: int, tip: int, **kw) -> dict:
    cats = [{"cat": "trade_gross", "lamports": gross}, {"cat": "tip", "lamports": -tip}, {"cat": "fee_win", "lamports": -5000}] if ok else \
        [{"cat": "fee_fail", "lamports": -5000}]
    r = {"sig": sig, "slot": 1000, "attempt": a, "kind": "route", "ok": ok, "fee": 5000, "tip": tip if ok else 0, "trade_gross": gross if ok else 0,
         "trade_net": net, "equity_delta": net, "liquid_delta": net, "wallet_sol": net, "wsol": 0, "rent_locked": 0, "rent_reclaimed": 0,
         "rent_nonrecoverable": 0, "categories": cats, "pre_run": False}
    r.update(kw)
    return r


def segment(root: str, name: str, k0: int, spec: list, extra_ledger: list) -> str:
    """a canary segment: one attempt per spec row (x4 arm index, size arm index, band, kind, mint, outcome, net)"""
    d = os.path.join(root, name)
    os.makedirs(d)
    start = gen.T0_NS + k0 * HOUR
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"schema": "arbx.meta/2.0", "run": {"segment": name, "started_ns": start, "mode": "canary"}}, f)
    with open(os.path.join(d, "stop.json"), "w") as f:
        json.dump({"schema": "arbx.stop/1.0", "ended_ns": start + HOUR, "reason": "deadline"}, f)
    gen.write_plain(d, "events.jsonl", "events", "1.0", [{"t_ns": start, "kind": "warmup_ready", "subsystem": "engine", "feed": None, "detail": {}}])
    gen.write_plain(d, "experiments.jsonl", "experiments", "1.0", [
        {"t_ns": start, "experiment": "x4", "event": "config", "key": "x4_share", "arms": X4, "weights": [1.0] * 3, "seed": 7,
         "scope": {"max_band": 2, "kinds": ["commit", "quiescent", "timeout", "fork"], "venues": []}, "unit": "decision"},
        {"t_ns": start, "experiment": "size", "event": "config", "key": "size_max_sol", "arms": SIZE, "weights": [1.0] * 2, "seed": 7,
         "scope": {"max_band": 4, "kinds": ["commit", "quiescent", "timeout", "fork"], "venues": []}, "unit": "decision"}])
    attempts, outcomes, ledger, decisions = [], [], [], []
    for i, (xi, si, band, kind, mint, final, net) in enumerate(spec):
        sig = gen.sg(f"{name}-{i}")
        arms = {"size_max_sol": SIZE[si]}
        if band <= 2:
            arms["x4_share"] = X4[xi]
        attempts.append(attempt(i, sig, band, kind, mint, arms))
        outcomes.append({"attempt": i, "final": final, "sig": sig})
        if final == "landed_ok":
            ledger.append(ledger_line(sig, i, True, net, net + 6000, 1000))
        elif final == "landed_fail":
            ledger.append(ledger_line(sig, i, False, -5000, 0, 0))
        decisions.append({"decision": 100 + i, "kind": kind, "routes": [], "experiments": {"x4_share": X4[xi], "size_max_sol": SIZE[si]}})
    gen.write_zjsonl(d, "attempts", "2.2", attempts)
    gen.write_zjsonl(d, "outcomes", "2.1", outcomes)
    gen.write_zjsonl(d, "ledger", "1.0", ledger + extra_ledger)
    gen.write_zjsonl(d, "decisions", "1.2", decisions)
    return d


# (x4 arm, size arm, band, kind, mint, final, net): the wins' nets are distinct so each sum is checkable
P1 = [(0, 0, 0, "commit", USDC, "landed_ok", 2_000), (1, 0, 1, "commit", MEME, "landed_ok", 7_000), (2, 1, 2, "quiescent", MEME, "landed_ok", 30_000),
      (0, 1, 0, "commit", USDC, "not_landed_expired", 0), (1, 1, 1, "commit", USDC, "landed_fail", -5_000), (2, 0, 0, "timeout", MEME, "not_landed_expired", 0),
      (0, 0, 1, "commit", CAKE_LOOKALIKE, "landed_ok", 4_000), (1, 0, 3, "commit", USDC, "landed_ok", 50_000), (2, 1, 0, "commit", USDC, "not_landed_refused", 0)]
P2 = [(0, 1, 2, "commit", MEME, "landed_ok", 11_000), (1, 1, 0, "commit", USDC, "not_landed_expired", 0), (2, 0, 1, "fork", USDC, "landed_ok", 3_000),
      (0, 0, 0, "commit", USDC, "not_landed_expired", 0), (1, 0, 2, "commit", MEME, "not_landed_expired", 0), (2, 1, 1, "commit", MEME, "landed_ok", 9_000)]


class Experiments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TmpDir()
        root = cls.tmp.__enter__()
        cls.root = os.path.join(root, "camp")
        os.makedirs(cls.root)
        # p1 carries the previous campaign's last trade (pre_run, not ours) and p2 a dup of p1's first win: neither counts
        prev = ledger_line(gen.sg("previous-campaign"), None, True, 99_999, 105_999, 1000, pre_run=True)
        cls.p1 = segment(cls.root, "c-p1", 0, P1, [prev])
        dup = ledger_line(gen.sg("c-p1-0"), 0, True, 2_000, 8_000, 1000, pre_run=True, dup=True)
        cls.p2 = segment(cls.root, "c-p2", 1, P2, [dup])
        cls.camp = model.Campaign.open(cls.root)
        cls.sec = r10_experiments.run(cls.camp, synth_ctx())
        cls.d = cls.sec["data"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def rows(self, pred):
        return [r for seg, spec in (("p1", P1), ("p2", P2)) for r in spec if pred(r)]

    def test_per_arm_money_from_the_ledger(self):
        x4 = self.d["experiments"]["x4"]
        self.assertEqual((x4["control"], x4["control_why"]), ("0.1", "the first arm configured"))
        for i, arm in enumerate(X4):
            rs = self.rows(lambda r: r[0] == i and r[2] <= 2)
            a = x4["arms"][str(arm)]
            wins = [r for r in rs if r[5] == "landed_ok"]
            nets = [r[6] for r in rs]
            self.assertEqual((a["attempts"], a["wins"], a["landed"]), (len(rs), len(wins), sum(r[5] in ("landed_ok", "landed_fail") for r in rs)), arm)
            self.assertEqual(a["net_total"], sum(nets), arm)
            self.assertEqual(a["net_per_attempt"], stats._clean(sum(nets) / len(rs)), arm)
            self.assertEqual(a["net_per_win"], stats._clean(sum(r[6] for r in wins) / len(wins)) if wins else None, arm)
            self.assertEqual(a["win_rate_ci95"], stats.wilson(len(wins), len(rs)))
            self.assertEqual(a["tips_over_gross"], round(len(wins) * 1000 / sum(r[6] + 6000 for r in wins), 6) if wins else None)
            self.assertEqual((a["wins_meme"], a["wins_common"]), (sum(tokens.classify(r[4]) == "meme" for r in wins), sum(tokens.classify(r[4]) == "common" for r in wins)))
        # the band-3 win (50,000) is in no X4 arm (out of its scope), but in its size arm
        self.assertEqual(sum(a["attempts"] for a in x4["arms"].values()), len(self.rows(lambda r: r[2] <= 2)))
        size = self.d["experiments"]["size"]
        self.assertEqual(size["arms"]["0.05"]["net_total"], sum(r[6] for r in self.rows(lambda r: r[1] == 0)))
        self.assertIn(50_000, [r[6] for r in self.rows(lambda r: r[1] == 0)])
        # the previous campaign's pre_run trade (+99,999) and p2's dup of p1's first win are in no arm's money
        total = sum(a["net_total"] for a in size["arms"].values())
        self.assertEqual(total, sum(r[6] for r in P1 + P2))
        self.assertEqual(self.d["money"]["pre_run_lines_of_our_attempts"], 0)
        # net per hour as if the whole run were on the arm: its net over its weight's share of the 2 trading hours
        self.assertEqual(size["arms"]["0.2"]["net_per_hour_whole_run"], stats._clean(size["arms"]["0.2"]["net_total"] / 0.5 / 2))

    def test_meme_and_common_by_mint(self):
        a = self.d["experiments"]["x4"]["arms"]["0.1"]
        # x4 0.1's wins: USDC (2,000), the CAKE look-alike (4,000; a meme by mint), the pump meme (11,000)
        self.assertEqual((a["wins_meme"], a["wins_common"], a["net_meme"], a["net_common"]), (2, 1, 15_000, 2_000))
        self.assertEqual(a["wins_common_by_token"], {"USDC": 1})
        self.assertIn(CAKE_LOOKALIKE, a["meme_lookalikes"])
        self.assertEqual((tokens.classify("4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL"), tokens.symbol("METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL")), ("common", "MET"))

    def test_balance_and_control(self):
        b = self.d["experiments"]["x4"]["balance"]
        self.assertEqual(b["sends"], {"0.1": 5, "0.2": 4, "0.35": 5})
        self.assertEqual(b["decisions"]["counts"], {"0.1": 5, "0.2": 5, "0.35": 5})
        self.assertEqual(b["decisions"]["by_kind"]["0.35"], {"commit": 2, "fork": 1, "quiescent": 1, "timeout": 1})
        self.assertEqual(b["by_band"]["0.2"], {"0": 1, "1": 2, "2": 1})
        self.assertEqual(set(b), {"decisions", "sends", "sends_chi2", "by_band", "by_kind", "band_independence", "kind_independence"})
        vs = self.d["experiments"]["x4"]["vs_control"]["0.35"]
        a, c = self.d["experiments"]["x4"]["arms"]["0.35"], self.d["experiments"]["x4"]["arms"]["0.1"]
        self.assertEqual(vs["win_rate"], stats.two_proportions(a["wins"], a["attempts"], c["wins"], c["attempts"]))
        self.assertEqual(vs["net_per_attempt_diff"], stats._clean(a["net_per_attempt"] - c["net_per_attempt"]))
        self.assertEqual(self.d["experiments"]["size"]["control"], "0.05")

    def test_factorial_cells(self):
        f = self.d["factorial"]["size x x4"]
        self.assertEqual(sum(c["attempts"] for c in f.values()), len(self.rows(lambda r: r[2] <= 2)))
        cell = f["size=0.2 x4=0.35"]
        rs = self.rows(lambda r: r[1] == 1 and r[0] == 2 and r[2] <= 2)
        self.assertEqual((cell["attempts"], cell["wins"], cell["net_total"]), (len(rs), sum(r[5] == "landed_ok" for r in rs), sum(r[6] for r in rs)))

    def test_r1_leaves_out_pre_run_lines(self):
        seg = model.Segment(self.p1)
        sec = r1_money.run(seg, synth_ctx())
        self.assertEqual(sec["data"]["trading"]["trade_net"], sum(r[6] for r in P1), "the previous campaign's +99,999 is not this segment's")
        self.assertEqual(sec["data"]["ledger"]["pre_run_skipped"], {"n": 1, "equity_delta": 99_999, "trade_net": 99_999})
        self.assertTrue(any("pre_run" in c for c in sec["caveats"]))
        self.assertEqual(len(seg.ledger_by_sig), len(seg.ledger) + 1, "the recompute still finds the pre-run transaction's line")
        money = runner._campaign_money_v2(self.camp.segments)
        self.assertEqual(money["trade_net"], sum(r[6] for r in P1 + P2))

    def test_the_cli_reads_a_campaign_directory(self):
        from arbx_report import __main__ as cli
        out = os.path.join(self.root, "rep")
        self.assertEqual(cli.main(["experiments", self.root, "--out", out]), 0)
        with open(os.path.join(out, "experiments.json")) as f:
            doc = json.load(f)
        self.assertEqual((doc["kind"], doc["sections"][0]["data"]["segments"]), ("experiments", ["c-p1", "c-p2"]))
        self.assertEqual(doc["sections"][0]["data"]["experiments"]["x4"]["arms"]["0.2"]["attempts"], 4)


class X2Trend(unittest.TestCase):
    """X2 (the direction fix): would-fail rising with the delay added is `go_speed` (speed matters); falling is
    `go_delay` (adopt the delay); the slope per 10 ms with its interval; two-sided"""

    def synth(self, root: str, rates: list) -> model.Segment:
        d = os.path.join(root, "x2")
        os.makedirs(d)
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump({"schema": "arbx.meta/2.0", "run": {"segment": "x2", "started_ns": gen.T0_NS, "mode": "canary"}}, f)
        attempts, bundles = [], []
        a = 0
        for delay, rate in zip([0, 10, 20], rates):
            for i in range(300):
                sig = gen.sg(f"x2-{a}")
                attempts.append(attempt(a, sig, 1, "commit", USDC, {"x2_delay_ms": delay}))
                bundles.append({"t_ns": gen.T0_NS + a, "bundle": f"b{a}", "attempt": a, "sig": sig,
                                "outcome": "would-fail" if i < rate * 300 else "accepted"})
                a += 1
        gen.write_zjsonl(d, "attempts", "2.2", attempts)
        gen.write_zjsonl(d, "bundles", "2.0", bundles)
        return model.Segment(d)

    def test_both_directions(self):
        with TmpDir() as root:
            up = r10_experiments.run(self.synth(os.path.join(root, "up"), [0.2, 0.3, 0.4]), synth_ctx())["data"]["x2"]["1"]
            self.assertEqual((up["go_speed"], up["go_delay"], up["slope_per_10ms"]), (True, False, 0.1))
            lo, hi = up["slope_per_10ms_ci95"]
            self.assertTrue(lo < 0.1 < hi and lo > 0.05, up["slope_per_10ms_ci95"])
            down = r10_experiments.run(self.synth(os.path.join(root, "down"), [0.4, 0.3, 0.2]), synth_ctx())["data"]["x2"]["1"]
            self.assertEqual((down["go_speed"], down["go_delay"], down["slope_per_10ms"]), (False, True, -0.1))
            flat = r10_experiments.run(self.synth(os.path.join(root, "flat"), [0.3, 0.3, 0.3]), synth_ctx())["data"]["x2"]["1"]
            self.assertEqual((flat["go_speed"], flat["go_delay"]), (False, False))
            self.assertEqual(flat["arms"][0]["n"], 300)


class Stats(unittest.TestCase):
    def test_sample_sizes_and_tests(self):
        # FT-007's 3.1% wins per send: +-50% needs 1,500-2,400 sends per arm, +-30% 4,600-6,200
        self.assertTrue(2_300 < stats.n_per_arm(0.031 * 1.5, 0.031) < 2_500)
        self.assertTrue(4_500 < stats.n_per_arm(0.031 * 0.7, 0.031) < 4_800)
        self.assertTrue(0.8 < stats.mde_rel(0.031, 1_000) < 0.85)
        t = stats.two_proportions(30, 1000, 45, 1000)
        self.assertTrue(t["p_less"] < 0.05 < t["p_two"])
        self.assertIsNone(stats.chi_square_independence({"a": {"0": 3}}))
        self.assertEqual(stats.chi_square_independence({"a": {"0": 50, "1": 50}, "b": {"0": 50, "1": 50}})["chi2"], 0)


if __name__ == "__main__":
    unittest.main()
