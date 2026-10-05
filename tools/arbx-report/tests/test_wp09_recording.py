"""WP-09 (review WP-09 #1): a recording made by arbx itself, read by the toolkit. `fixtures/wp09-run/` holds the
pools.json, registry-run.json and accounts.bin of a scenario run written by the current code (the Rust test
`scenarios::harness::the_toolkit_fixture_is_this_codes_recording` checks they are what the code writes, and rewrites them
with ARBX_BLESS=1). pools.json is MEASUREMENT §4.29's list: blockctx maps accounts.bin `pool_index` to pools through it
and finds the route accounts in it. WP-09's first draft wrote an object instead, and blockctx then saw no pool at all.
registry-run.json, what a replay needs beside it, is listed as an input and refused nowhere."""
import json
import os
import unittest

from helpers import HERE

from arbx_report import blockctx, model, streams

FIX = os.path.join(HERE, "fixtures", "wp09-run")


class Wp09Recording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIX, "expected.json")) as f:
            cls.want = json.load(f)
        cls.seg = model.Segment(FIX)

    def test_pools_json_is_the_list_the_toolkit_reads(self):
        pools = self.seg.pools
        self.assertIsInstance(pools, list)
        self.assertEqual([p["pool"] for p in pools], self.want["pools"])
        self.assertEqual([p["idx"] for p in pools], list(range(len(pools))))
        for p in pools:
            for k in ("venue", "t0", "t1", "vault0", "vault1", "extra", "flag", "source", "tier", "pair_key"):
                self.assertIn(k, p)

    def test_blockctx_attributes_the_trade_to_its_pool(self):
        writers = blockctx.pool_writers(self.seg, {})
        self.assertIn(self.want["traded_pool"], writers, f"accounts.bin pool_index -> pools.json: {sorted(writers)}")
        self.assertIn(self.want["trade_txn"], {w[2] for w in writers[self.want["traded_pool"]]})
        self.assertLessEqual(set(writers), set(self.want["pools"]))

    def test_route_accounts_come_from_the_registry(self):
        p = {x["pool"]: x for x in self.seg.pools}
        buy, sell = self.want["pools"][0], self.want["traded_pool"]
        got = blockctx.route_accounts(self.seg, {"route": {"buy_pool": buy, "sell_pool": sell}})
        for k in (buy, sell, p[buy]["vault0"], p[buy]["vault1"], p[sell]["vault0"], p[sell]["vault1"], *p[buy]["extra"]):
            self.assertIn(k, got)

    def test_registry_run_is_listed_and_not_refused(self):
        self.assertIn("registry-run", streams.discover(FIX))
        files = {x["file"] for x in self.seg.inputs()}
        self.assertLessEqual({"pools.json", "registry-run.json"}, files)

    def test_the_pumpswap_global_config_has_its_role(self):
        # WP-16: the state stream follows PumpSwap's GlobalConfig (accounts.bin role 12), a part of every PumpSwap pool
        gc = "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"
        roles = {streams.ROLE_NAMES.get(r.role) for r in streams.iter_accounts(self.seg.stream_files("accounts"), keep_data=False) if r.acct == gc}
        self.assertEqual(roles, {"pump_global_config"})


if __name__ == "__main__":
    unittest.main()
