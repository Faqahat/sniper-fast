"""Counter semantics (summing _delta vs taking the last _total), the §4.42 ledger golden examples and identities,
the recon identity, and the statistics helpers."""
import base64
import struct
import unittest

import helpers  # noqa: F401  (path setup)

from arbx_report import counters, ledgercalc, solana, stats

W = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
WSOL_ACCT = "9tQ4Ytq8f5rGJUVd3cJvP9FKb4m8E2mAo2EG8nAAYrb5"
NEW_ATA = "6dTqf8z2zFJ7DwWG8SWvmCn9tYgYVj1n9TGiyGJ8Kb4R"
UVA = "BKPfj2HtknArpzzksCTUfpT2KRge2p4CzDe4JcKKp9HS"
TIP = "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"
ROUTE = "8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg"
F, T, G = 5000, 30_000, 120_000
R_SPL, R_2022, U, R_ATA = 2_039_280, 1_513_840, 1_346_200, 1_488_440


class Counters(unittest.TestCase):
    LINES = [
        {"seq": 0, "counts_total": {"attempt": 3}, "counts_delta": {"attempt": 3},
         "money": {"failed_fees_total_lamports": 100, "failed_fees_delta_lamports": 100, "equity_total_now": 50}},
        {"seq": 1, "counts_total": {"attempt": 5}, "counts_delta": {"attempt": 2},
         "money": {"failed_fees_total_lamports": 160, "failed_fees_delta_lamports": 60, "equity_total_now": 40}},
        {"seq": 2, "counts_total": {"attempt": 9}, "counts_delta": {"attempt": 4},
         "money": {"failed_fees_total_lamports": 160, "failed_fees_delta_lamports": 0, "equity_total_now": 45}},
    ]

    def test_total_is_last_delta_is_sum_gauge_never_summed(self):
        a = counters.aggregate(self.LINES)
        self.assertEqual(a["total"]["counts_total.attempt"], 9)
        self.assertEqual(a["delta"]["counts_delta.attempt"], 9)
        self.assertEqual(a["total"]["money.failed_fees_total_lamports"], 160)
        self.assertEqual(a["delta"]["money.failed_fees_delta_lamports"], 160)
        self.assertEqual(a["now"]["money.equity_total_now"], {"last": 45, "max": 50})
        self.assertTrue(a["seq"]["deltas_complete"])
        # the arb-lab mistake: summing a running total
        wrong = sum(x["money"]["failed_fees_total_lamports"] for x in self.LINES)
        self.assertNotEqual(wrong, a["total"]["money.failed_fees_total_lamports"])

    def test_seq_gap_flags_deltas_incomplete(self):
        a = counters.aggregate([self.LINES[0], self.LINES[2]])
        self.assertEqual(a["seq"]["gaps"], [[1, 1]])
        self.assertFalse(a["seq"]["deltas_complete"])
        self.assertEqual(a["seq"]["lost_lines"], 1)

    def test_campaign_sums_each_segments_last_total(self):
        a = counters.aggregate(self.LINES)
        b = counters.aggregate(self.LINES[:2])
        self.assertEqual(counters.campaign_total([a, b], "counts_total.attempt")["value"], 14)

    def test_legacy_status_failed_fees(self):
        lines = [{"t_ns": i, "exec": {"sending": {"failed_fees_lamports": v}}} for i, v in enumerate([0, 25600, 46000, 46000])]
        s = counters.legacy_status(lines)
        self.assertEqual(s["failed_fees_lamports"]["last_line"], 46000)
        self.assertEqual(s["failed_fees_lamports"]["sum_of_lines_WRONG"], 117600)


# ----------------------------------------------------------------------------------------------- ledger golden

def ix(prog_i, accts, data: bytes):
    return {"programIdIndex": prog_i, "accounts": accts, "data": solana.b58encode(data)}


def tx(keys, pre, post, ixs=(), inner=(), pre_tok=(), post_tok=(), err=None, fee=F):
    return solana.TxView({"slot": 1, "blockTime": 1, "meta": {
        "err": err, "fee": fee, "preBalances": list(pre), "postBalances": list(post),
        "preTokenBalances": list(pre_tok), "postTokenBalances": list(post_tok),
        "innerInstructions": [{"index": i, "instructions": list(v)} for i, v in inner]},
        "transaction": {"signatures": ["s" * 87], "message": {"accountKeys": list(keys), "instructions": list(ixs),
                                                               "header": {"numRequiredSignatures": 1}}}})


def tokrow(i, mint, owner, amount, prog=solana.TOKEN):
    return {"accountIndex": i, "mint": mint, "owner": owner, "programId": prog, "uiTokenAmount": {"amount": str(amount), "decimals": 9}}


def create(funder_i, new_i, lamports, owner):
    return struct.pack("<IQQ", 0, lamports, 165) + solana.b58decode(owner).rjust(32, b"\0")


def cats(row):
    return {c["cat"]: c["lamports"] for c in row["categories"] if c["lamports"]}


class LedgerGolden(unittest.TestCase):
    """MEASUREMENT §4.42 golden examples, computed from synthetic transactions."""
    KEYS = [W, WSOL_ACCT, NEW_ATA, UVA, TIP, solana.SYSTEM, solana.TOKEN, ROUTE, solana.ATA]
    SYS, TOK, RT, ATAP = 5, 6, 7, 8

    def route_tx(self, created=(), close_new=False, err=None):
        """A route win: WSOL +G, tip T, fee F, optional creations (inner System CreateAccount) and a close."""
        k = self.KEYS
        pre = [10 ** 10, 10 ** 9 + R_SPL, 0, 0, 10 ** 6, 1, 1, 1, 1]
        post = list(pre)
        ok = err is None
        rent_spent = sum(l for _, l in created) if ok else 0
        if ok:
            post[0] = pre[0] - F - T - rent_spent + (R_ATA if close_new else 0)
            post[1] = pre[1] + G
            post[4] = pre[4] + T
            for i, l in created:
                post[i] = 0 if (close_new and i == 2) else l
        else:
            post[0] = pre[0] - F
        inner_list = []
        for i, l in created:
            owner = solana.TOKEN_2022 if i == 2 else solana.PUMPSWAP
            inner_list.append(ix(self.SYS, [0, i], create(0, i, l, owner)))
        ixs = [ix(self.RT, [0, 1, 2, 3], b"\x01"), ix(self.SYS, [0, 4], struct.pack("<IQ", 2, T))]
        if close_new:
            ixs.append(ix(self.TOK, [2, 0, 0], bytes([9])))
        inner = [(0, inner_list)] if inner_list else []
        pre_tok = [tokrow(1, solana.WSOL, W, 10 ** 9)]
        post_tok = [tokrow(1, solana.WSOL, W, 10 ** 9 + (G if ok else 0))]
        if ok and any(i == 2 for i, _ in created) and not close_new:
            post_tok.append(tokrow(2, "MintX", W, 0, solana.TOKEN_2022))
        return tx(k, pre, post, ixs, inner, pre_tok, post_tok, err=err)

    def check(self, row, **want):
        for k, v in want.items():
            self.assertEqual(row[k], v, k)
        self.assertEqual(ledgercalc.check_identities(row), [])

    def test_ata_create_only(self):
        k = [W, NEW_ATA, solana.SYSTEM, solana.ATA]
        t = tx(k, [10 ** 10, 0, 1, 1], [10 ** 10 - R_SPL - F, R_SPL, 1, 1],
               [ix(3, [0, 1, 0, 2], b"\x01")], [(0, [ix(2, [0, 1], create(0, 1, R_SPL, solana.TOKEN))])],
               [], [tokrow(1, "MintX", W, 0)])
        r = ledgercalc.compute(t, W, route=False)
        self.check(r, wallet_sol=-R_SPL - F, wsol=0, rent_locked=R_SPL, rent_reclaimed=0, rent_nonrecoverable=0,
                   liquid_delta=-R_SPL - F, equity_delta=-F, kind="ata_create")
        self.assertEqual(cats(r), {"fee_other": -F})

    def test_route_win_create_and_close(self):
        r = ledgercalc.compute(self.route_tx(created=[(2, R_ATA)], close_new=True), W, route=True)
        self.check(r, wallet_sol=-F - T, wsol=G, rent_locked=R_ATA, rent_reclaimed=R_ATA, rent_nonrecoverable=0,
                   liquid_delta=G - F - T, equity_delta=G - F - T, trade_gross=G, trade_net=G - F - T, tip=T)
        self.assertEqual(cats(r), {"trade_gross": G, "tip": -T, "fee_win": -F})

    def test_route_win_with_accumulator_and_token2022_ata(self):
        """w5h-p6#69: the PumpSwap user volume accumulator is expensed, the Token-2022 ATA stays recoverable."""
        r = ledgercalc.compute(self.route_tx(created=[(2, R_2022), (3, U)]), W, route=True)
        self.check(r, wallet_sol=-F - T - U - R_2022, wsol=G, rent_locked=R_2022, rent_reclaimed=0, rent_nonrecoverable=U,
                   liquid_delta=G - F - T - U - R_2022, equity_delta=G - F - T - U, trade_gross=G)
        self.assertEqual(cats(r), {"trade_gross": G, "tip": -T, "fee_win": -F, "rent_nonrecoverable": -U})

    def test_route_win_leaving_ata_open(self):
        r = ledgercalc.compute(self.route_tx(created=[(2, R_ATA)]), W, route=True)
        self.check(r, wallet_sol=-F - T - R_ATA, wsol=G, rent_locked=R_ATA, rent_reclaimed=0, rent_nonrecoverable=0,
                   liquid_delta=G - F - T - R_ATA, equity_delta=G - F - T)
        self.assertEqual(cats(r), {"trade_gross": G, "tip": -T, "fee_win": -F})

    def test_failed_landed_route(self):
        r = ledgercalc.compute(self.route_tx(err={"InstructionError": [0, {"Custom": 1314390018}]}), W, route=True)
        self.check(r, wallet_sol=-F, wsol=0, rent_locked=0, liquid_delta=-F, equity_delta=-F, tip=0, trade_net=-F)
        self.assertEqual(cats(r), {"fee_fail": -F})

    def test_wrap(self):
        X = 7_000_000
        k = [W, WSOL_ACCT, solana.SYSTEM, solana.TOKEN]
        t = tx(k, [10 ** 10, R_SPL + 10 ** 9, 1, 1], [10 ** 10 - X - F, R_SPL + 10 ** 9 + X, 1, 1],
               [ix(2, [0, 1], struct.pack("<IQ", 2, X)), ix(3, [1], bytes([17]))], [],
               [tokrow(1, solana.WSOL, W, 10 ** 9)], [tokrow(1, solana.WSOL, W, 10 ** 9 + X)])
        r = ledgercalc.compute(t, W, route=False)
        self.check(r, wallet_sol=-X - F, wsol=X, liquid_delta=-F, equity_delta=-F, kind="wrap")
        self.assertEqual(cats(r), {"fee_other": -F})

    def test_unwrap(self):
        A = 5_000_000
        k = [W, WSOL_ACCT, solana.TOKEN]
        t = tx(k, [10 ** 10, R_SPL + A, 1], [10 ** 10 + A + R_SPL - F, 0, 1], [ix(2, [1, 0, 0], bytes([9]))], [],
               [tokrow(1, solana.WSOL, W, A)], [])
        r = ledgercalc.compute(t, W, route=False)
        self.check(r, wallet_sol=A + R_SPL - F, wsol=-A, rent_reclaimed=R_SPL, liquid_delta=R_SPL - F, equity_delta=-F,
                   kind="unwrap")
        self.assertEqual(cats(r), {"fee_other": -F})

    def test_base64_encoded_transaction(self):
        """testdata/wallet holds base64 transactions with JSON meta (WP-00b): keys come from the message."""
        keys = [W, TIP, solana.SYSTEM]
        msg = bytes([1, 0, 1]) + bytes([len(keys)]) + b"".join(solana.b58decode(k).rjust(32, b"\0") for k in keys) + bytes(32)
        data = struct.pack("<IQ", 2, T)
        msg += bytes([1]) + bytes([2, 2, 0, 1, len(data)]) + data
        raw = bytes([1]) + bytes(64) + msg
        v = solana.TxView({"slot": 5, "transaction": [base64.b64encode(raw).decode(), "base64"],
                           "meta": {"err": None, "fee": F, "preBalances": [10 ** 9, 10, 1], "postBalances": [10 ** 9 - F - T, 10 + T, 1],
                                    "preTokenBalances": [], "postTokenBalances": [], "innerInstructions": []}})
        self.assertEqual(v.keys, keys)
        r = ledgercalc.compute(v, W, route=True, tip_accounts={TIP})
        self.assertEqual((r["tip"], r["trade_gross"], r["equity_delta"]), (T, 0, -F - T))
        self.assertEqual(ledgercalc.check_identities(r), [])


class Recon(unittest.TestCase):
    def test_recon_identity(self):
        r = {"delta_equity": 10_000, "sum_entries": 9_000, "inventory_reval": 500, "residual": 500,
             "liquid": {"residual": 0}, "token_amounts": [{"ok": True}], "ok": True}
        self.assertEqual(ledgercalc.recon_check(r), [])
        bad = dict(r, residual=0)
        self.assertTrue(ledgercalc.recon_check(bad))
        miss = dict(r, residual=20_500, delta_equity=30_000, ok=True)
        self.assertTrue(any("tolerance" in x for x in ledgercalc.recon_check(miss)))


class Stats(unittest.TestCase):
    def test_quantiles_and_counts_agree(self):
        xs = [5, 1, 9, 3, 3, 7, 100]
        h = {}
        for x in xs:
            h[x] = h.get(x, 0) + 1
        for q in (0.0, 0.5, 0.9, 0.99, 1.0):
            self.assertEqual(stats.quantile(xs, q), stats.quantile_counts(h, q))
        self.assertIsNone(stats.quantile([], 0.5))

    def test_money_summary_flags_jackpot(self):
        s = stats.money_summary([10, 20, 30, 1000])
        self.assertTrue(s["jackpot_flag"])
        self.assertEqual(s["median"], 25)
        self.assertFalse(stats.money_summary([10, 20, 30])["jackpot_flag"])

    def test_tests(self):
        self.assertAlmostEqual(stats.fisher_exact(3, 1, 1, 3), 0.4857142857, places=6)
        self.assertLess(stats.binom_test(1, 100, 0.2, "less"), 1e-6)
        t = stats.cochran_armitage([(0, 40, 100), (10, 30, 100), (20, 20, 100)], "decreasing")
        self.assertLess(t["p"], 0.01)
        self.assertAlmostEqual(t["slope"], -0.01, places=6)
        mw = stats.mann_whitney(list(range(30)), list(range(10, 40)), "less")
        self.assertLess(mw["p"], 0.05)
        self.assertEqual(stats.bootstrap_ci([1, 2, 3, 4]), stats.bootstrap_ci([1, 2, 3, 4]))  # seeded


if __name__ == "__main__":
    unittest.main()
