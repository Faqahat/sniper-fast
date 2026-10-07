"""WP-11: `arbx-report experiments` over a synthetic two-segment campaign with two experiments at once (X4 tip share
x size cap, a 3 x 2 factorial): per arm attempts, landings and wins with intervals, net per attempt and per win,
tips / gross, the meme and common wins by the route's mint, the balance by band and trigger kind and over the
decisions, each arm against its control per decision and per send, the factorial's cells; money from the ledger across
the segments as the Rust side counts it (no `dup` line, nothing at or before the campaign's start: the previous
campaign's `pre_run` trade is out, a later segment's `pre_run` record of our own late landing is in; R1 too); X2's
two-sided trend test."""
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


def attempt(a: int, sig: str, band: int, kind: str, mint: str, arms: dict, leader: str = "jito", assigned: dict | None = None) -> dict:
    x = {"attempt": a, "decision": 100 + a, "opp": a, "t_ns": gen.T0_NS + a, "kind": "canary", "sent": True,
         "trigger": {"txn": gen.sg(f"trig{a}"), "slot": 1000, "kind": kind}, "route": {"mint": mint, "buy_venue": "Dlmm", "sell_venue": "PumpSwap"},
         "size_lamports": 50_000_000, "band": band, "experiments": arms,
         "tip": {"lamports": 1000, "arm": arms.get("x4_share"), "policy": "bam_floor" if leader == "bam" else "share_of_edge"},
         "leader": {"kind": leader}, "tx": {"sig": sig}, "copies": [{"path": "jito-bundle", "sig": sig}]}
    if assigned is not None:
        x["experiments_assigned"] = assigned
    return x


def ledger_line(sig: str, a, ok: bool, net: int, gross: int, tip: int, **kw) -> dict:
    cats = [{"cat": "trade_gross", "lamports": gross}, {"cat": "tip", "lamports": -tip}, {"cat": "fee_win", "lamports": -5000}] if ok else \
        [{"cat": "fee_fail", "lamports": -5000}]
    r = {"sig": sig, "slot": 1000, "attempt": a, "kind": "route", "ok": ok, "fee": 5000, "tip": tip if ok else 0, "trade_gross": gross if ok else 0,
         "trade_net": net, "equity_delta": net, "liquid_delta": net, "wallet_sol": net, "wsol": 0, "rent_locked": 0, "rent_reclaimed": 0,
         "rent_nonrecoverable": 0, "categories": cats, "pre_run": False}
    r.update(kw)
    return r


def segment(root: str, name: str, k0: int, spec: list, extra_ledger: list, snapshot_slot=None, status: list | None = None) -> str:
    """a canary segment: one attempt per spec row (x4 arm index, size arm index, band, kind, mint, outcome, net)"""
    d = os.path.join(root, name)
    os.makedirs(d)
    start = gen.T0_NS + k0 * HOUR
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"schema": "arbx.meta/2.0", "run": {"segment": name, "started_ns": start, "mode": "canary"}}, f)
    with open(os.path.join(d, "stop.json"), "w") as f:
        json.dump({"schema": "arbx.stop/1.0", "ended_ns": start + HOUR, "reason": "deadline"}, f)
    gen.write_plain(d, "events.jsonl", "events", "1.0", [{"t_ns": start, "kind": "warmup_ready", "subsystem": "engine", "feed": None, "detail": {}}])
    if snapshot_slot is not None:
        gen.write_plain(d, "snapshots.jsonl", "snapshots", "1.0", [{"t_ns": start + 1, "slot": snapshot_slot, "slot_mismatch": False, "sol": 10 ** 9, "wsol": 10 ** 8}])
    gen.write_plain(d, "experiments.jsonl", "experiments", "1.0", [
        {"t_ns": start, "experiment": "x4", "event": "config", "key": "x4_share", "arms": X4, "control": X4[0], "weights": [1.0] * 3, "seed": 7,
         "scope": {"max_band": 2, "kinds": ["commit", "quiescent", "timeout", "fork"], "venues": []}, "unit": "decision"},
        {"t_ns": start, "experiment": "size", "event": "config", "key": "size_max_sol", "arms": SIZE, "control": SIZE[0], "weights": [1.0] * 2, "seed": 7,
         "scope": {"max_band": 4, "kinds": ["commit", "quiescent", "timeout", "fork"], "venues": []}, "unit": "decision"}])
    attempts, outcomes, ledger, decisions = [], [], [], []
    for i, (xi, si, band, kind, mint, final, net) in enumerate(spec):
        sig = gen.sg(f"{name}-{i}")
        arms = {"size_max_sol": SIZE[si]}
        if band <= 2:
            arms["x4_share"] = X4[xi]
        attempts.append(attempt(i, sig, band, kind, mint, arms, leader="bam" if i % 3 == 2 else "jito", assigned={"x4_share": X4[xi], "size_max_sol": SIZE[si]}))
        outcomes.append({"attempt": i, "final": final, "sig": sig})
        if final == "landed_ok":
            ledger.append(ledger_line(sig, i, True, net, net + 6000, 1000))
        elif final == "landed_fail":
            ledger.append(ledger_line(sig, i, False, -5000, 0, 0))
        for line in ledger[-1:]:
            line["slot"] = 1_100 + 10 * k0 + i
        decisions.append({"decision": 100 + i, "kind": kind, "routes": [], "experiments": {"x4_share": X4[xi], "size_max_sol": SIZE[si]}})
    gen.write_zjsonl(d, "attempts", "2.2", attempts)
    gen.write_zjsonl(d, "outcomes", "2.1", outcomes)
    gen.write_zjsonl(d, "ledger", "1.0", ledger + extra_ledger)
    gen.write_zjsonl(d, "decisions", "1.2", decisions)
    if status is not None:
        gen.write_plain(d, "status.jsonl", "status", "2.2", status)
    return d


# (x4 arm, size arm, band, kind, mint, final, net): the wins' nets are distinct so each sum is checkable
P1 = [(0, 0, 0, "commit", USDC, "landed_ok", 2_000), (1, 0, 1, "commit", MEME, "landed_ok", 7_000), (2, 1, 2, "quiescent", MEME, "landed_ok", 30_000),
      (0, 1, 0, "commit", USDC, "not_landed_expired", 0), (1, 1, 1, "commit", USDC, "landed_fail", -5_000), (2, 0, 0, "timeout", MEME, "not_landed_expired", 0),
      (0, 0, 1, "commit", CAKE_LOOKALIKE, "landed_ok", 4_000), (1, 0, 3, "commit", USDC, "landed_ok", 50_000), (2, 1, 0, "commit", USDC, "not_landed_refused", 0)]
P2 = [(0, 1, 2, "commit", MEME, "landed_ok", 11_000), (1, 1, 0, "commit", USDC, "not_landed_expired", 0), (2, 0, 1, "fork", USDC, "landed_ok", 3_000),
      (0, 0, 0, "commit", USDC, "not_landed_expired", 0), (1, 0, 2, "commit", MEME, "not_landed_expired", 0), (2, 1, 1, "commit", MEME, "landed_ok", 9_000)]


# p1's attempt 3 was final not landed in p1, but landed late (+1,500): only p2's pre-run fetch recorded it
LATE = {("p1", 3): ("landed_ok", 1_500)}


class Experiments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TmpDir()
        root = cls.tmp.__enter__()
        cls.root = os.path.join(root, "camp")
        os.makedirs(cls.root)
        # the campaign starts at p1's first snapshot (slot 1,000). p1 carries the previous campaign's last trade (pre_run,
        # slot 900, not ours) and p2 a dup of p1's first win: neither counts; p2's pre-run record of p1's late landing (slot
        # 1,150, after the start) counts, as in spend.json
        prev = ledger_line(gen.sg("previous-campaign"), None, True, 99_999, 105_999, 1000, pre_run=True, slot=900)
        cls.p1 = segment(cls.root, "c-p1", 0, P1, [prev], snapshot_slot=1_000)
        dup = ledger_line(gen.sg("c-p1-0"), 0, True, 2_000, 8_000, 1000, pre_run=True, dup=True, slot=1_100)
        late = ledger_line(gen.sg("c-p1-3"), None, True, 1_500, 7_500, 1000, pre_run=True, slot=1_150)
        cls.p2 = segment(cls.root, "c-p2", 1, P2, [dup, late], snapshot_slot=1_200)
        with open(os.path.join(cls.root, "campaign.json"), "w") as f:
            json.dump({"schema": "arbx.campaign/1.1", "name": "camp", "segments": [{"name": "c-p1"}, {"name": "c-p2"}]}, f)
        cls.camp = model.Campaign.open(cls.root)
        cls.sec = r10_experiments.run(cls.camp, synth_ctx())
        cls.d = cls.sec["data"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def rows(self, pred):
        """the spec rows as they ended (LATE's late landing applied)"""
        out = []
        for seg, spec in (("p1", P1), ("p2", P2)):
            for i, r in enumerate(spec):
                if (seg, i) in LATE:
                    r = r[:5] + LATE[(seg, i)]
                if pred(r):
                    out.append(r)
        return out

    def test_per_arm_money_from_the_ledger(self):
        x4 = self.d["experiments"]["x4"]
        self.assertEqual((x4["control"], x4["control_why"], x4["control_warning"]), ("0.1", "experiments.jsonl `control` (the first arm configured)", None))
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
        self.assertEqual(total, sum(r[6] for r in self.rows(lambda r: True)), "the late landing in, the previous campaign's trade out")
        self.assertEqual((self.d["money"]["lines_before_start_of_our_attempts"], self.d["money"]["ledger_without_outcome"]), (0, 1))
        # net per hour, capacity-bound (review #1): the arm's net per send times the run's sends per hour (15 sends in 2 h)
        self.assertEqual(self.d["sends_per_hour"], 7.5)
        a = size["arms"]["0.2"]
        self.assertEqual(a["net_per_hour"], stats._clean(a["net_total"] / a["attempts"] * 7.5))

    def test_meme_and_common_by_mint(self):
        a = self.d["experiments"]["x4"]["arms"]["0.1"]
        # x4 0.1's wins: USDC (2,000), the late USDC landing (1,500), the CAKE look-alike (4,000; a meme by mint), the pump
        # meme (11,000)
        self.assertEqual((a["wins_meme"], a["wins_common"], a["net_meme"], a["net_common"]), (2, 2, 15_000, 3_500))
        self.assertEqual(a["wins_common_by_token"], {"USDC": 2})
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
        self.assertEqual(vs["per_send"]["win_rate"], stats.two_proportions(a["wins"], a["attempts"], c["wins"], c["attempts"]))
        self.assertEqual(vs["per_send"]["net_per_attempt_diff"], stats._clean(a["net_per_attempt"] - c["net_per_attempt"]))
        self.assertEqual(set(vs["per_send"]["sends_per_arm_for_win_rate"]), {"+30%", "-30%", "+50%", "-50%"})
        # per decision (the randomized unit): every decision of the arm, sent or not (decisions.jsonl's counts)
        self.assertEqual(self.d["experiments"]["x4"]["decisions_src"], "decisions.jsonl")
        self.assertEqual((a["decisions"], c["decisions"]), (5, 5))
        pd = vs["per_decision"]
        self.assertEqual(pd["wins"], stats.two_proportions(a["wins"], 5, c["wins"], 5))
        self.assertEqual(pd["net_per_1k_decisions"], [stats._clean(1000 * a["net_total"] / 5), stats._clean(1000 * c["net_total"] / 5)])
        lo, hi = pd["net_per_1k_decisions_diff_ci95"]
        self.assertTrue(lo <= pd["net_per_1k_decisions_diff"] <= hi)
        self.assertEqual(self.d["experiments"]["size"]["control"], "0.05")

    def test_factorial_cells(self):
        f = self.d["factorial"]["size x x4"]
        self.assertEqual(sum(c["attempts"] for c in f.values()), len(self.rows(lambda r: r[2] <= 2)))
        cell = f["size=0.2 x4=0.35"]
        rs = self.rows(lambda r: r[1] == 1 and r[0] == 2 and r[2] <= 2)
        self.assertEqual((cell["attempts"], cell["wins"], cell["net_total"]), (len(rs), sum(r[5] == "landed_ok" for r in rs), sum(r[6] for r in rs)))

    def test_r1_counts_from_the_campaign_start(self):
        seg = model.Segment(self.p1)
        self.assertEqual((seg.start_slot, seg.own_start_slot), (1_000, 1_000))
        sec = r1_money.run(seg, synth_ctx())
        self.assertEqual(sec["data"]["trading"]["trade_net"], sum(r[6] for r in P1), "the previous campaign's +99,999 is not this segment's")
        self.assertEqual(sec["data"]["ledger"]["before_start_skipped"], {"n": 1, "pre_run": 1, "equity_delta": 99_999, "trade_net": 99_999})
        self.assertTrue(any("pre_run" in c for c in sec["caveats"]))
        self.assertEqual(len(seg.ledger_by_sig), len(seg.ledger) + 1, "the recompute still finds the pre-run transaction's line")
        # p2 opened alone finds its campaign's start (campaign.json beside it) and counts the late landing it recorded
        p2 = model.Segment(self.p2)
        self.assertEqual((p2.start_slot, p2.own_start_slot), (1_000, 1_200))
        self.assertEqual(r1_money.run(p2, synth_ctx())["data"]["trading"]["trade_net"], sum(r[6] for r in P2) + 1_500)
        money = runner._campaign_money_v2(self.camp.segments)
        self.assertEqual(money["trade_net"], sum(r[6] for r in P1 + P2) + 1_500)

    def test_the_cli_reads_a_campaign_directory(self):
        from arbx_report import __main__ as cli
        out = os.path.join(self.root, "rep")
        self.assertEqual(cli.main(["experiments", self.root, "--out", out]), 0)
        with open(os.path.join(out, "experiments.json")) as f:
            doc = json.load(f)
        self.assertEqual((doc["kind"], doc["sections"][0]["data"]["segments"]), ("experiments", ["c-p1", "c-p2"]))
        self.assertEqual(doc["sections"][0]["data"]["experiments"]["x4"]["arms"]["0.2"]["attempts"], 4)


class Control(unittest.TestCase):
    """Review #3: the control is experiments.jsonl's `control` (the first arm); a record without one takes the run's
    config.toml value when it is an arm, and otherwise there is no control and nothing is compared (never a guess); a
    control that is not the config's value is warned about"""

    def seg(self, root: str, line: dict, cfg_toml: str | None) -> model.Segment:
        d = os.path.join(root, f"s{abs(hash((json.dumps(line, sort_keys=True), cfg_toml))) % 10_000}")
        os.makedirs(d)
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump({"schema": "arbx.meta/2.0", "run": {"segment": "s", "started_ns": gen.T0_NS, "mode": "canary"}}, f)
        gen.write_plain(d, "experiments.jsonl", "experiments", "1.0", [line])
        attempts = [attempt(i, gen.sg(f"c{i}"), 1, "commit", USDC, {"x4_share": [0.1, 0.2, 0.35][i % 3]}) for i in range(9)]
        gen.write_zjsonl(d, "attempts", "2.2", attempts)
        if cfg_toml is not None:
            with open(os.path.join(d, "config.toml"), "w") as f:
                f.write(cfg_toml)
        return model.Segment(d)

    def test_never_guessed(self):
        base = {"t_ns": gen.T0_NS, "experiment": "x4", "event": "config", "key": "x4_share", "arms": [0.1, 0.2, 0.35], "weights": [1.0] * 3,
                "scope": {"max_band": 2}}
        tips = "[tips]\nshares = [0.2, 0.2, 0.2, 0.6, 0.7]\n"
        with TmpDir() as root:
            e = r10_experiments.run(self.seg(root, base, None), synth_ctx())
            x = e["data"]["experiments"]["x4"]
            self.assertEqual((x["control"], x["vs_control"]), (None, {}), "no control, nothing compared")
            self.assertTrue(any("no control" in c for c in e["caveats"]), e["caveats"])
            x = r10_experiments.run(self.seg(root, base, tips), synth_ctx())["data"]["experiments"]["x4"]
            self.assertEqual((x["control"], x["control_why"]), ("0.2", "the configured value (the run's config.toml)"))
            e = r10_experiments.run(self.seg(root, {**base, "control": 0.1}, tips), synth_ctx())
            self.assertEqual(e["data"]["experiments"]["x4"]["control"], "0.1", "the record's control wins")
            self.assertTrue(any("is not the run's configured value 0.2" in c for c in e["caveats"]), e["caveats"])


class Splits(unittest.TestCase):
    """Review #4, #10, #11, #12: per arm by leader kind and tip policy, X4 against its control on Jito-led sends, every
    attempt attributed by its assigned arm per decision, X4's go on the drop's 95% upper bound, a win without a mint
    `unknown`"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = TmpDir()
        root = cls.tmp.__enter__()
        cls.camp = os.path.join(root, "camp")
        os.makedirs(cls.camp)
        segment(cls.camp, "c-p1", 0, P1, [], snapshot_slot=1_000)
        segment(cls.camp, "c-p2", 1, P2, [], snapshot_slot=1_200)
        cls.d = r10_experiments.run(model.Campaign.open(cls.camp), synth_ctx())["data"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def test_leader_kind_and_tip_policy(self):
        a = self.d["experiments"]["x4"]["arms"]["0.2"]
        self.assertEqual(sum(v["attempts"] for v in a["by_leader_kind"].values()), a["attempts"])
        self.assertEqual(set(a["by_tip_policy"]) <= {"share_of_edge", "bam_floor"}, True)
        self.assertEqual(a["by_leader_kind"].get("bam", {}).get("attempts", 0), a["by_tip_policy"].get("bam_floor", {}).get("attempts", 0))
        vs = self.d["experiments"]["x4"]["vs_control"]["0.35"]
        self.assertIn("per_send_jito_led", vs)

    def test_assigned_arms_per_decision(self):
        x4 = self.d["experiments"]["x4"]
        # the band-3 attempt (x4 out of scope) is in no applied arm but in its assigned arm (0.2) per decision
        applied = sum(a["attempts"] for a in x4["arms"].values())
        assigned = sum(a["assigned"]["attempts"] for a in x4["arms"].values())
        self.assertEqual((applied, assigned), (14, 15))
        self.assertEqual(x4["arms"]["0.2"]["assigned"]["net_total"] - x4["arms"]["0.2"]["net_total"], 50_000, "the band-3 win, by assignment")

    def test_x4_go_on_the_upper_bound(self):
        r = r10_experiments._rel_drop(30, 1000, 40, 1000)
        self.assertEqual(r["drop"], 0.25)
        lo, hi = r["ci95"]
        self.assertTrue(lo < 0.25 < hi and hi > 0.2, r)
        rows = [{"experiments": {"x4_share": arm}, "leader": "jito", "landed": i < k} for arm, k in ((0.2, 400), (0.35, 395)) for i in range(1000)]
        e = {"key": "x4_share", "control": "0.2", "arms": {"0.2": {"attempts": 1000, "land_rate": 0.4, "land_rate_ci95": None, "net_per_attempt": 0, "net_per_attempt_ci95": None,
                                                                "lost_auction": 0},
                                                         "0.35": {"attempts": 1000, "land_rate": 0.395, "land_rate_ci95": None, "net_per_attempt": 0,
                                                                  "net_per_attempt_ci95": None, "lost_auction": 0}}, "vs_control": {}}
        x = r10_experiments.x4_rule(e, rows)["arms"]["0.35"]
        self.assertTrue(x["go"] and x["land_drop_jito_led"]["ci95"][1] < 0.2, x)
        few = [{"experiments": {"x4_share": arm}, "leader": "jito", "landed": i < k} for arm, k in ((0.2, 40), (0.35, 39)) for i in range(100)]
        x = r10_experiments.x4_rule(e, few)["arms"]["0.35"]
        self.assertFalse(x["go"], "the same 1% drop on 100 sends: its upper bound is past 20%")

    def test_unknown_mint(self):
        self.assertEqual((tokens.classify(None), tokens.classify(""), tokens.classify(USDC), tokens.classify(MEME)), ("unknown", "unknown", "common", "meme"))


class StatusCounters(unittest.TestCase):
    """Review #1, #2: the engine's per-arm counters (status.jsonl `experiments`) give the decisions per arm and the
    canary_wait refusals without decisions.jsonl, which is never held in memory; the canary's binding send slot is
    called out"""

    def test_status_counters_and_the_canary_slot(self):
        st = [{"seq": 0, "t_ns": gen.T0_NS + 1, "exec": {"counts_total": {"reject_canary_wait": 40}, "sent_total": 9},
               "experiments": {"x4_share": {"0.2": {"decisions": 100, "opportunities": 20, "sent": 3, "would_send": 0, "refused": {"canary_wait": 15}},
                                            "0.1": {"decisions": 98, "opportunities": 18, "sent": 3, "would_send": 0, "refused": {"canary_wait": 12}},
                                            "0.35": {"decisions": 102, "opportunities": 22, "sent": 3, "would_send": 0, "refused": {"canary_wait": 13}}},
                               "size_max_sol": {"0.05": {"decisions": 150, "opportunities": 30, "sent": 4, "would_send": 0, "refused": {}},
                                                "0.2": {"decisions": 150, "opportunities": 30, "sent": 5, "would_send": 0, "refused": {}}}}}]
        with TmpDir() as root:
            camp = os.path.join(root, "camp")
            os.makedirs(camp)
            segment(camp, "c-p1", 0, P1, [], snapshot_slot=1_000, status=st)
            # decisions.jsonl must not be loaded whole: the status counters are read instead (and the stream would be)
            orig = model.Segment.decisions
            model.Segment.decisions = property(lambda self: (_ for _ in ()).throw(AssertionError("decisions.jsonl loaded whole")))
            try:
                sec = r10_experiments.run(model.Campaign.open(camp), synth_ctx())
            finally:
                model.Segment.decisions = orig
            x4 = sec["data"]["experiments"]["x4"]
            self.assertEqual(x4["decisions_src"], "status.jsonl experiments")
            self.assertEqual((x4["arms"]["0.2"]["decisions"], x4["arms"]["0.2"]["canary_wait"], x4["arms"]["0.1"]["opportunities"]), (100, 15, 18))
            self.assertEqual(x4["balance"]["decisions"]["counts"], {"0.2": 100, "0.1": 98, "0.35": 102})
            self.assertEqual(sec["data"]["canary_wait"], {"refusals": 40, "sends": 9})
            self.assertTrue(any("send slot binds" in c for c in sec["caveats"]), sec["caveats"])

    def test_decisions_are_streamed(self):
        with TmpDir() as root:
            camp = os.path.join(root, "camp")
            os.makedirs(camp)
            segment(camp, "c-p1", 0, P1, [], snapshot_slot=1_000)
            orig = model.Segment.decisions
            model.Segment.decisions = property(lambda self: (_ for _ in ()).throw(AssertionError("decisions.jsonl loaded whole")))
            try:
                x4 = r10_experiments.run(model.Campaign.open(camp), synth_ctx())["data"]["experiments"]["x4"]
            finally:
                model.Segment.decisions = orig
            self.assertEqual(x4["decisions_src"], "decisions.jsonl")
            self.assertEqual(x4["balance"]["decisions"]["counts"], {"0.1": 3, "0.2": 3, "0.35": 3})


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
