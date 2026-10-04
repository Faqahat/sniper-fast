#!/usr/bin/env python3
"""Offline checks of the legacy fixtures (PLAN WP-00b): integrity, and that the fixtures reproduce the known answers.

Run from the repository root (standard library only, no network):
    python3 -m unittest testdata/legacy/test_legacy_fixtures.py
    python3 testdata/legacy/test_legacy_fixtures.py

What it checks:
- every file in fixtures.sha256 exists and matches; no fixture file is unlisted; raw.sha256 agrees;
- every signature in signatures.json has a wallet transaction, and that transaction carries that signature;
- each case's `chain` values recomputed from its wallet transaction, its `record` agreeing with the chain, and its
  ledger line in expected.json (MEASUREMENT §4.42: categories sum to equity_delta, identities hold);
- res-pnl's p1-p10 decomposition, liquid balances and ledger sums recomputed from raw/ and wallet/;
- wallet-synthesis §2's bundle-arm figures recomputed from the chain and from the v1 records (raw/ and wins/);
- the exec.jsonl v1 slice and the per-pool bot counts.
"""
import base64
import collections
import hashlib
import json
import lzma
import os
import re
import sys
import unittest

sys.dont_write_bytecode = True
LEGACY = os.path.dirname(os.path.abspath(__file__))
TESTDATA = os.path.dirname(LEGACY)
WALLET_DIR = os.path.join(TESTDATA, "wallet")
NOT_FIXTURE = re.compile(r"(^|/)(README\.md|[^/]*\.py|__pycache__(/.*)?|fixtures\.sha256)$")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
SYSTEM = "11111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"


def load(path):
    with open(path) as f:
        return json.load(f)


SIGS = load(os.path.join(LEGACY, "signatures.json"))
EXP = load(os.path.join(LEGACY, "expected.json"))
WALLET = SIGS["wallet"]
NONREC = {x["account"]: x["kind"] for x in SIGS["nonrecoverable_accounts"]}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def xz_lines(path):
    with lzma.open(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def v1(seg, name):
    """A v1 record file: the full copy in raw/ if present, else the wins-only subset in wins/."""
    for d in ("raw", "wins"):
        p = os.path.join(LEGACY, d, seg, f"{name}.jsonl.xz")
        if os.path.exists(p):
            return xz_lines(p)
    raise FileNotFoundError(f"{seg}/{name}")


def b58(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return b"\0" * (len(s) - len(s.lstrip("1"))) + (n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"")


def compact_u16(b, p):
    v = shift = 0
    while True:
        x = b[p]
        p += 1
        v |= (x & 0x7F) << shift
        shift += 7
        if not x & 0x80:
            return v, p


class Tx:
    """A getTransaction (base64) fixture, decoded far enough for the ledger: signatures, keys, instructions."""

    _cache = {}

    @classmethod
    def get(cls, sig):
        if sig not in cls._cache:
            cls._cache[sig] = cls(sig)
        return cls._cache[sig]

    def __init__(self, sig):
        self.res = load(os.path.join(WALLET_DIR, f"{sig}.json"))
        self.meta = self.res["meta"]
        raw = base64.b64decode(self.res["transaction"][0])
        nsig, p = compact_u16(raw, 0)
        self.signatures = [b58(raw[p + 64 * i:p + 64 * i + 64]) for i in range(nsig)]
        msg = raw[p + 64 * nsig:]
        q = (1 if msg[0] & 0x80 else 0) + 3
        nkeys, q = compact_u16(msg, q)
        keys = [b58(msg[q + 32 * i:q + 32 * i + 32]) for i in range(nkeys)]
        q += 32 * nkeys + 32
        nix, q = compact_u16(msg, q)
        self.ixs = []
        for _ in range(nix):
            prog = msg[q]
            q += 1
            na, q = compact_u16(msg, q)
            accs = list(msg[q:q + na])
            q += na
            nd, q = compact_u16(msg, q)
            self.ixs.append((prog, accs, msg[q:q + nd]))
            q += nd
        loaded = self.meta.get("loadedAddresses") or {}
        self.keys = keys + loaded.get("writable", []) + loaded.get("readonly", [])
        for group in self.meta.get("innerInstructions") or []:
            for ix in group["instructions"]:
                self.ixs.append((ix["programIdIndex"], ix["accounts"], b58dec(ix["data"])))

    def wallet_amounts(self, which):
        out = {}
        for t in self.meta.get(which) or []:
            if t.get("owner") == WALLET:
                out[(t["accountIndex"], t["mint"])] = int(t["uiTokenAmount"]["amount"])
        return out

    def view(self):
        """The wallet's raw changes, by the conventions in expected.json."""
        m = self.meta
        wi = self.keys.index(WALLET)
        ok = m["err"] is None
        pre, post = self.wallet_amounts("preTokenBalances"), self.wallet_amounts("postTokenBalances")
        wsol, tokens = 0, {}
        for k in set(pre) | set(post):
            d = post.get(k, 0) - pre.get(k, 0)
            if k[1] == WSOL:
                wsol += d
            elif d:
                tokens[k[1]] = tokens.get(k[1], 0) + d
        token_rows = {t["accountIndex"]: t for t in m.get("postTokenBalances") or []}
        nonce_init = {accs[0] for prog, accs, data in self.ixs if self.keys[prog] == SYSTEM and data[:4] == b"\x06\0\0\0"}
        created = []
        for i, (a, b) in enumerate(zip(m["preBalances"], m["postBalances"])):
            if i == wi or a != 0 or b == 0:
                continue
            c = {"account": self.keys[i], "lamports": b}
            if i in token_rows:
                t = token_rows[i]
                amount = int(t["uiTokenAmount"]["amount"])
                c.update(kind="token_account", program=t["programId"], mint=t["mint"], recoverable=True,
                         rent=b - amount if t["mint"] == WSOL else b)
            elif self.keys[i] in NONREC:
                c.update(kind=NONREC[self.keys[i]], recoverable=False, rent=b)
            elif i in nonce_init:
                c.update(kind="nonce_account", recoverable=True, rent=b)
            else:
                c.update(kind="other", recoverable=None, rent=b)
            created.append(c)
        new = {c["account"] for c in created}
        own = {self.keys[t["accountIndex"]] for t in (m.get("preTokenBalances") or []) + (m.get("postTokenBalances") or [])
               if t.get("owner") == WALLET}
        tips = []
        if ok:
            for prog, accs, data in self.ixs:
                if self.keys[prog] == SYSTEM and len(data) == 12 and data[:4] == b"\x02\0\0\0":
                    src, dst = self.keys[accs[0]], self.keys[accs[1]]
                    if src == WALLET and dst != WALLET and dst not in new and dst not in own:
                        tips.append({"account": dst, "lamports": int.from_bytes(data[4:], "little")})
        return {"wallet_index": wi, "ok": ok, "err": m["err"], "meta_fee": m["fee"], "fee": m["fee"] if wi == 0 else 0,
                "wallet_sol": m["postBalances"][wi] - m["preBalances"][wi], "wsol": wsol, "tokens": tokens,
                "tip": tips[0] if len(tips) == 1 else (tips or None), "created": created}


def ledger(kind, v):
    """MEASUREMENT §4.42 (revision 2) ledger line of one transaction, by the conventions in expected.json."""
    fee = v["fee"]
    tip = v["tip"]["lamports"] if isinstance(v["tip"], dict) else sum(t["lamports"] for t in v["tip"] or [])
    locked = sum(c["rent"] for c in v["created"] if c["recoverable"] is True)
    nonrec = sum(c["rent"] for c in v["created"] if c["recoverable"] is False)
    liquid = v["wallet_sol"] + v["wsol"]
    equity = liquid + sum(v["tokens"].values()) + locked
    gross = (equity + fee + tip + nonrec if v["ok"] else 0) if kind == "route" else 0
    net = gross - fee - tip if kind == "route" else 0
    cats = []
    if kind == "route" and v["ok"]:
        cats += [("trade_gross", gross), ("tip", -tip), ("fee_win", -fee), ("rent_nonrecoverable", -nonrec)]
    elif kind == "route":
        cats += [("fee_fail", -fee)]
    else:
        cats += [("fee_other", -fee), ("transfer_in", max(0, equity + fee)), ("transfer_out", min(0, equity + fee))]
    return {"kind": kind, "ok": v["ok"], "wallet_sol": v["wallet_sol"], "wsol": v["wsol"], "tokens": {}, "fee": fee, "tip": tip,
            "rent_locked": locked, "rent_reclaimed": 0, "rent_nonrecoverable": nonrec, "liquid_delta": liquid, "equity_delta": equity,
            "trade_gross": gross, "trade_net": net, "categories": [{"cat": c, "lamports": x} for c, x in cats if x], "stranded": []}


def all_sigs(x, out):
    if isinstance(x, dict):
        for k, v in x.items():
            out.add(v) if k == "sig" and isinstance(v, str) else all_sigs(v, out)
    elif isinstance(x, list):
        for v in x:
            all_sigs(v, out)
    return out


class Integrity(unittest.TestCase):
    def manifest(self, path, base):
        out = {}
        with open(path) as f:
            for line in f:
                h, rel = line.rstrip("\n").split("  ", 1)
                out[os.path.normpath(os.path.join(base, rel))] = h
        return out

    def test_sha256_of_every_fixture(self):
        listed = self.manifest(os.path.join(LEGACY, "fixtures.sha256"), TESTDATA)
        self.assertGreater(len(listed), 200)
        for path, h in listed.items():
            self.assertEqual(sha256(path), h, os.path.relpath(path, TESTDATA))
        on_disk = set()
        for base in (LEGACY, WALLET_DIR):
            for root, dirs, files in os.walk(base):
                for fn in files:
                    rel = os.path.relpath(os.path.join(root, fn), TESTDATA).replace(os.sep, "/")
                    if not NOT_FIXTURE.search(rel):
                        on_disk.add(os.path.normpath(os.path.join(TESTDATA, rel)))
        self.assertEqual(on_disk, set(listed), "fixture files and fixtures.sha256 differ")
        for path, h in self.manifest(os.path.join(LEGACY, "raw.sha256"), os.path.join(LEGACY, "raw")).items():
            self.assertEqual(listed.get(path), h, path)

    def test_every_json_and_xz_fixture_loads(self):
        for root, _, files in os.walk(LEGACY):
            for fn in files:
                p = os.path.join(root, fn)
                if fn.endswith(".json"):
                    load(p)
                elif fn.endswith(".jsonl.xz"):
                    self.assertTrue(xz_lines(p), p)

    def test_wallet_files_match_their_signatures(self):
        sigs = all_sigs(SIGS, set())
        files = {fn[:-5] for fn in os.listdir(WALLET_DIR) if fn.endswith(".json")}
        self.assertEqual(sigs, files)
        slots = {}
        for row in SIGS["cases"] + SIGS["landed"]["rows"] + SIGS["wins_w5h2_w5h3"]["rows"]:
            slots[row["sig"]] = (row["slot"], row["idx"])
        for sig in sigs:
            tx = Tx.get(sig)
            self.assertEqual(tx.signatures[0], sig)
            self.assertIn(WALLET, tx.keys)
            self.assertEqual((tx.res["slot"], tx.res.get("transactionIndex")), slots[sig], sig)


class Cases(unittest.TestCase):
    def test_chain_values(self):
        for c in SIGS["cases"]:
            with self.subTest(case=c["id"]):
                v = Tx.get(c["sig"]).view()
                self.assertEqual(v, c["chain"])
                r = c["record"]
                if r and r.get("landed"):
                    self.assertEqual(r["ok"], v["ok"])
                    self.assertEqual(r["fee_lamports"], v["fee"])
                    self.assertEqual(r["profit_lamports"], v["wallet_sol"] + v["wsol"])
                    self.assertEqual(r["tip_paid_lamports"], v["tip"]["lamports"] if v["tip"] else 0)
                    if v["ok"]:
                        self.assertEqual(r["round_trip_on_chain"], v["wsol"])

    def test_ledger_lines(self):
        self.assertEqual(set(EXP["cases"]), {c["id"] for c in SIGS["cases"]})
        for c in SIGS["cases"]:
            with self.subTest(case=c["id"]):
                want = EXP["cases"][c["id"]]
                got = ledger(c["kind"], c["chain"])
                self.assertEqual({"sig": c["sig"], **got}, want)
                self.assertEqual(sum(x["lamports"] for x in want["categories"]), want["equity_delta"])
                self.assertEqual(want["liquid_delta"], want["wallet_sol"] + want["wsol"])
                self.assertEqual(want["equity_delta"] - want["liquid_delta"], want["rent_locked"] - want["rent_reclaimed"])

    def test_named_rent_amounts(self):
        e = EXP["cases"]
        self.assertEqual((e["bundle_win_accumulator_create"]["rent_nonrecoverable"], e["bundle_win_accumulator_create"]["rent_locked"]),
                         (1346200, 1513840))
        self.assertEqual(e["bundle_win_ata_create"]["rent_locked"], 1488440)
        self.assertEqual(e["bundle_win_token2022_create"]["rent_locked"], 1513840)
        self.assertEqual(e["bolt_direct_win"]["liquid_delta"], 27459627)
        self.assertEqual(e["bolt_direct_win"]["equity_delta"], 28973467)
        self.assertEqual(e["landed_fail_compete_bid"]["equity_delta"], -1305030)


class ResPnl(unittest.TestCase):
    R = EXP["res_pnl_p1_p10"]
    LANDED = SIGS["landed"]["rows"]

    def test_landed_list_matches_records(self):
        for seg in SIGS["landed"]["segments"]:
            outcomes = {o["sig"] for o in v1(seg, "outcomes") if o.get("landed")}
            rows = [r for r in self.LANDED if r["seg"] == seg]
            self.assertEqual({r["sig"] for r in rows if r["recorded"]}, outcomes, seg)
            copies = {c["sig"]: a["attempt"] for a in v1(seg, "attempts") for c in a["copies"]}
            for r in rows:
                self.assertEqual(copies.get(r["sig"]), r["attempt"], r["sig"])
                self.assertEqual(Tx.get(r["sig"]).view()["ok"], r["ok"])
        slots = [(r["slot"], r["idx"]) for r in self.LANDED]
        self.assertEqual(slots, sorted(slots))
        self.assertEqual((slots[0][0], slots[-1][0]), (SIGS["landed"]["slot_from"], SIGS["landed"]["slot_to"]))

    def test_segments(self):
        for seg, want in self.R["segments"].items():
            with self.subTest(seg=seg):
                att, out = v1(seg, "attempts"), v1(seg, "outcomes")
                landed = [o for o in out if o.get("landed")]
                wins = [o for o in landed if o["ok"]]
                unrec = [r for r in self.LANDED if r["seg"] == seg and not r["recorded"]]
                created = [c for o in wins for c in Tx.get(o["sig"]).view()["created"]]
                got = {
                    "sent": len(att), "landed": len(landed) + len(unrec), "wins": len(wins),
                    "landed_failed": len(landed) - len(wins) + len(unrec),
                    "failed_fees_recorded": sum(o["fee_lamports"] for o in landed if not o["ok"]),
                    "failed_fees_unrecorded": sum(Tx.get(r["sig"]).view()["fee"] for r in unrec),
                    "win_fees": sum(o["fee_lamports"] for o in wins), "tips": sum(o["tip_paid_lamports"] for o in wins),
                    "gross_round_trip_wins": sum(o["round_trip_on_chain"] for o in wins),
                    "new_token_accounts": sum(c["kind"] == "token_account" for c in created),
                    "rent_token_accounts": sum(c["rent"] for c in created if c["kind"] == "token_account"),
                    "rent_pump": sum(c["rent"] for c in created if c["kind"] == "pump_user_volume_accumulator"),
                    "profit_lamports": sum(o["profit_lamports"] for o in wins),
                }
                got["trading_net_ex_rent"] = (got["profit_lamports"] + got["rent_token_accounts"] + got["rent_pump"]
                                              - got["failed_fees_recorded"] - got["failed_fees_unrecorded"])
                self.assertEqual(got, want)
                st = v1(seg, "status")[-1]["exec"]["sending"]
                self.assertEqual((st["sent"], st["landed"], st["wins"], st["failed_fees_lamports"], st["profit_lamports"], st["tips_lamports"],
                                  st["fees_lamports"]),
                                 (len(att), len(landed), len(wins), got["failed_fees_recorded"], got["profit_lamports"], got["tips"],
                                  sum(o["fee_lamports"] for o in landed)))
                self.assertEqual(st["in_flight"], self.R["in_flight_at_stop"].get(seg, 0))

    def test_totals(self):
        t = self.R["total"]
        self.assertEqual({k: sum(s[k] for s in self.R["segments"].values()) for k in t}, t)
        self.assertEqual((t["trading_net_ex_rent"], t["profit_lamports"], t["rent_token_accounts"] + t["rent_pump"]),
                         (-2337448, -16201607, 16383000))
        self.assertEqual(self.R["rent_total"], t["rent_token_accounts"] + t["rent_pump"])
        self.assertEqual(self.R["trades_net_on_wins"], t["gross_round_trip_wins"] - t["tips"] - t["win_fees"])
        eras = self.R["eras"]
        segs = self.R["segments"]
        self.assertEqual(eras["tpu_p1_p6_trading_net"], sum(segs[f"w5h-p{i}"]["trading_net_ex_rent"] for i in range(1, 7)))
        self.assertEqual(eras["bundle_p7_p10_trading_net"], sum(segs[f"w5h-p{i}"]["trading_net_ex_rent"] for i in range(7, 11)))

    def test_wins_residuals_and_accuracy(self):
        resid = collections.defaultdict(list)
        within, predicted = 0, 0
        for seg in self.R["segments"]:
            for o in v1(seg, "outcomes"):
                if o.get("landed") and o["ok"]:
                    r = o["profit_lamports"] - (o["round_trip_on_chain"] - o["fee_lamports"] - o["tip_paid_lamports"])
                    resid[str(r)].append(f"{seg}#{o['attempt']}")
                    within += abs(o["round_trip_on_chain"] - o["round_trip_predicted"]) <= 2
                    predicted += o["round_trip_predicted"]
        self.assertEqual({k: sorted(v) for k, v in resid.items()}, self.R["wins_residual"])
        q = self.R["quote_accuracy"]
        self.assertEqual((within, predicted), (q["wins_within_2"], q["predicted_round_trip"]))

    def test_fee_split(self):
        split = collections.Counter()
        for r in self.LANDED:
            tx = Tx.get(r["sig"])
            base = 5000 * len(tx.signatures)
            kind = "win" if r["ok"] else "fail"
            split[f"{kind}_base"] += base
            split[f"{kind}_priority"] += tx.meta["fee"] - base
        self.assertEqual(dict(split), self.R["fees_split"])

    def test_liquid_balance_and_ledger_sums(self):
        def liquid(sig, when):
            tx = Tx.get(sig)
            bal = tx.meta["preBalances" if when == "pre" else "postBalances"]
            w, ws = tx.keys.index(WALLET), tx.keys.index(SIGS["wsol_account"])
            amt = [int(t["uiTokenAmount"]["amount"]) for t in tx.meta["preTokenBalances" if when == "pre" else "postTokenBalances"]
                   if t["accountIndex"] == ws][0]
            return bal[w] + amt, bal[w] + bal[ws]
        (a0, b0), (a1, b1) = liquid(self.LANDED[0]["sig"], "pre"), liquid(self.LANDED[-1]["sig"], "post")
        L = self.R["liquid"]
        self.assertEqual((a0, a1, a1 - a0), (L["basis_token_amount"]["start"], L["basis_token_amount"]["end"], L["basis_token_amount"]["delta"]))
        self.assertEqual((b0, b1, b1 - b0),
                         (L["basis_account_lamports"]["start"], L["basis_account_lamports"]["end"], L["basis_account_lamports"]["delta"]))
        sums = collections.Counter()
        for r in self.LANDED:
            line = ledger("route", Tx.get(r["sig"]).view())
            self.assertEqual(sum(c["lamports"] for c in line["categories"]), line["equity_delta"])
            for k in ("trade_net", "equity_delta", "liquid_delta", "rent_locked", "rent_nonrecoverable", "trade_gross", "fee", "tip"):
                sums[k] += line[k]
        want = dict(self.R["ledger_sums_landings"])
        want.pop("note")
        self.assertEqual(dict(sums), want)
        self.assertEqual(sums["liquid_delta"], L["sum_liquid_delta_landings"])
        self.assertEqual(sums["trade_net"], self.R["total"]["trading_net_ex_rent"])


class WalletSynthesis(unittest.TestCase):
    W = EXP["wallet_synthesis_s2"]
    ROWS = SIGS["wins_w5h2_w5h3"]["rows"]

    def chain_sum(self, rows):
        a = collections.Counter()
        for r in rows:
            v = Tx.get(r["sig"]).view()
            self.assertTrue(v["ok"])
            a["wins"] += 1
            a["gross_round_trip"] += v["wsol"]
            a["tips"] += v["tip"]["lamports"] if v["tip"] else 0
            a["fees"] += v["fee"]
            a["rent_locked"] += sum(c["rent"] for c in v["created"])
            a["net_wallet_change"] += v["wallet_sol"] + v["wsol"]
        a["net_ex_rent"] = a["net_wallet_change"] + a["rent_locked"]
        return dict(a)

    def test_bundle_arm_from_chain(self):
        bundle = [r for r in self.ROWS if r["class"] == "bundle_win"]
        self.assertEqual(self.chain_sum([r for r in bundle if r["seg"].startswith("w5h2")]), self.W["w5h2_bundle_wins"])
        self.assertEqual(self.chain_sum([r for r in bundle if r["seg"].startswith("w5h3")]), self.W["w5h3_bundle_wins"])
        self.assertEqual(self.chain_sum([r for r in self.ROWS if r["class"] == "direct_win"]), self.W["w5h2_bolt_win"])
        s = self.chain_sum(bundle)
        self.assertEqual((s["wins"], s["net_ex_rent"], s["net_wallet_change"]),
                         (self.W["bundle_arm"]["wins"], self.W["bundle_arm"]["net_ex_rent"], self.W["bundle_arm"]["net_with_rent"]))
        kinds = collections.Counter(c["rent"] for r in self.ROWS for c in Tx.get(r["sig"]).view()["created"])
        ra = self.W["rent_accounts"]
        self.assertEqual((kinds[1513840], kinds[1488440], sum(k * n for k, n in kinds.items())),
                         (ra["token2022_1513840"], ra["spl_1488440"], ra["total"]))

    def test_bundle_arm_from_records(self):
        tip_rule = exact = within_12 = 0
        for r in self.ROWS:
            o = [x for x in v1(r["seg"], "outcomes") if x["attempt"] == r["attempt"]]
            a = [x for x in v1(r["seg"], "attempts") if x["attempt"] == r["attempt"]]
            self.assertEqual((len(o), len(a)), (1, 1), r)
            o, a = o[0], a[0]
            v = Tx.get(r["sig"]).view()
            self.assertEqual((o["sig"], o["ok"], o["landed"], a["path_arm"]), (r["sig"], True, r["path"], r["arm"]))
            self.assertEqual((o["round_trip_on_chain"], o["fee_lamports"], o["tip_paid_lamports"], o["profit_lamports"]),
                             (v["wsol"], v["fee"], v["tip"]["lamports"], v["wallet_sol"] + v["wsol"]))
            if r["class"] == "bundle_win":
                tip_rule += o["tip_paid_lamports"] == (7 * (a["expected_profit"] - 5000)) // 10
                exact += o["round_trip_on_chain"] == o["round_trip_predicted"]
                within_12 += abs(o["round_trip_on_chain"] - o["round_trip_predicted"]) <= 12
        rec = self.W["bundle_wins_records"]
        self.assertEqual((tip_rule, exact, within_12), (rec["tip_is_floor_0_7_expected_minus_5000"], rec["round_trip_exact"], rec["round_trip_within_12"]))


class Other(unittest.TestCase):
    def test_exec_slice(self):
        e = EXP["exec_slice"]
        lines = xz_lines(os.path.join(TESTDATA, e["file"]))
        self.assertEqual(len(lines), e["lines"])
        self.assertEqual(sorted({x["slot"] for x in lines}), e["slots"])
        for x in lines:
            self.assertEqual(set(x), {"cu", "err", "fee", "idx", "ok", "sig", "signer", "slot", "sol", "t", "tok", "why"})
        ours = sorted({x["sig"] for x in lines} & {r["sig"] for r in SIGS["landed"]["rows"]})
        self.assertEqual(ours, e["our_landings_present"])
        for x in lines:
            if x["sig"] in ours:
                v = Tx.get(x["sig"]).view()
                self.assertEqual((x["signer"], x["fee"], x["sol"], x["ok"]), (WALLET, v["fee"], v["wallet_sol"], v["ok"]))

    def test_pool_bots(self):
        pb = load(os.path.join(LEGACY, "pool-bots.json"))
        want = EXP["pool_bots"]
        crowded = [p for p, n in pb["pools"].items() if n >= want["crowded_min_bots"]]
        self.assertEqual(len(crowded), want["crowded_pools"])
        self.assertEqual(sorted(crowded), sorted(x["pool"] for x in pb["crowded"]))
        self.assertTrue(all(pb["pools"][x["pool"]] == x["bots"] for x in pb["crowded"]))
        self.assertEqual(pb["bins"], want["bins"])


if __name__ == "__main__":
    unittest.main()
