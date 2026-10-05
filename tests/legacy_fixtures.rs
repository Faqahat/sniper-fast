//! Offline checks of the legacy fixtures (PLAN WP-00b): testdata/legacy/ and testdata/wallet/ (and WP-09's scenario
//! inputs, testdata/scenarios/capture.json and accounts.json, in the same manifest).
//!
//! - every fixture file matches testdata/legacy/fixtures.sha256, none is unlisted, and raw.sha256 agrees;
//! - every JSON fixture parses, and every signature in signatures.json has its getTransaction fixture;
//! - each ledger case's chain values are recomputed from its transaction, and its expected ledger line keeps the
//!   MEASUREMENT §4.42 identities (summing categories = equity_delta);
//! - the liquid change and the rent over the 119 w5h-p1..p10 landings equal res-pnl's numbers.
//!
//! The known-answer recomputation from the v1 records (xz) is in testdata/legacy/test_legacy_fixtures.py.

use base64::Engine as _;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

const SYSTEM: &str = "11111111111111111111111111111111";
const WSOL: &str = "So11111111111111111111111111111111111111112";

fn testdata() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata")
}

fn read_json(p: &Path) -> Value {
    let s = std::fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    serde_json::from_str(&s).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn sha256_hex(p: &Path) -> String {
    let b = std::fs::read(p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    Sha256::digest(&b).iter().map(|x| format!("{x:02x}")).collect()
}

/// `<sha256>  <path>` lines; paths resolved against `base`.
fn manifest(path: &Path, base: &Path) -> BTreeMap<PathBuf, String> {
    std::fs::read_to_string(path)
        .unwrap()
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            let (h, rel) = l.split_once("  ").expect("manifest line");
            (normalize(&base.join(rel)), h.to_string())
        })
        .collect()
}

fn normalize(p: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in p.components() {
        match c {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                out.pop();
            }
            c => out.push(c),
        }
    }
    out
}

/// Documentation and code are not fixtures.
fn is_fixture(p: &Path) -> bool {
    let name = p.file_name().unwrap().to_string_lossy();
    !(name == "README.md" || name == "fixtures.sha256" || name.ends_with(".py") || p.components().any(|c| c.as_os_str() == "__pycache__"))
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    for e in std::fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        if p.is_dir() {
            walk(&p, out);
        } else {
            out.push(p);
        }
    }
}

fn fixture_files() -> BTreeSet<PathBuf> {
    let mut all = Vec::new();
    walk(&testdata().join("legacy"), &mut all);
    walk(&testdata().join("wallet"), &mut all);
    // the WP-09 scenario inputs (tools/capture-fixtures.py `SCENARIO_INPUTS`; their expected outputs are not fixtures)
    all.extend(["capture.json", "accounts.json"].iter().map(|f| testdata().join("scenarios").join(f)).filter(|p| p.exists()));
    all.into_iter().filter(|p| is_fixture(p)).map(|p| normalize(&p)).collect()
}

fn all_sigs(v: &Value, out: &mut BTreeSet<String>) {
    match v {
        Value::Object(m) => {
            for (k, x) in m {
                match (k.as_str(), x) {
                    ("sig", Value::String(s)) => {
                        out.insert(s.clone());
                    }
                    _ => all_sigs(x, out),
                }
            }
        }
        Value::Array(a) => a.iter().for_each(|x| all_sigs(x, out)),
        _ => {}
    }
}

fn compact_u16(b: &[u8], mut p: usize) -> (usize, usize) {
    let (mut v, mut shift) = (0usize, 0);
    loop {
        let x = b[p];
        p += 1;
        v |= ((x & 0x7f) as usize) << shift;
        shift += 7;
        if x & 0x80 == 0 {
            return (v, p);
        }
    }
}

/// A getTransaction (encoding base64, JSON meta) fixture, decoded far enough for the ledger.
struct Tx {
    meta: Value,
    signatures: Vec<String>,
    keys: Vec<String>,
    /// (program index, account indexes, data) of top-level and inner instructions
    ixs: Vec<(usize, Vec<usize>, Vec<u8>)>,
}

impl Tx {
    fn load(sig: &str) -> Tx {
        let res = read_json(&testdata().join("wallet").join(format!("{sig}.json")));
        assert_eq!(res["transaction"][1], "base64", "{sig}");
        let raw = base64::engine::general_purpose::STANDARD.decode(res["transaction"][0].as_str().unwrap()).unwrap();
        let (nsig, p) = compact_u16(&raw, 0);
        let signatures = (0..nsig).map(|i| bs58::encode(&raw[p + 64 * i..p + 64 * i + 64]).into_string()).collect();
        let msg = &raw[p + 64 * nsig..];
        let mut q = if msg[0] & 0x80 != 0 { 1 } else { 0 } + 3;
        let (nkeys, q2) = compact_u16(msg, q);
        q = q2;
        let mut keys: Vec<String> = (0..nkeys).map(|i| bs58::encode(&msg[q + 32 * i..q + 32 * i + 32]).into_string()).collect();
        q += 32 * nkeys + 32;
        let (nix, q2) = compact_u16(msg, q);
        q = q2;
        let mut ixs = Vec::new();
        for _ in 0..nix {
            let prog = msg[q] as usize;
            q += 1;
            let (na, q2) = compact_u16(msg, q);
            let accs = msg[q2..q2 + na].iter().map(|&x| x as usize).collect();
            let (nd, q3) = compact_u16(msg, q2 + na);
            ixs.push((prog, accs, msg[q3..q3 + nd].to_vec()));
            q = q3 + nd;
        }
        let meta = res["meta"].clone();
        for which in ["writable", "readonly"] {
            for k in meta["loadedAddresses"][which].as_array().into_iter().flatten() {
                keys.push(k.as_str().unwrap().to_string());
            }
        }
        for g in meta["innerInstructions"].as_array().into_iter().flatten() {
            for ix in g["instructions"].as_array().unwrap() {
                let accs = ix["accounts"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap() as usize).collect();
                let data = bs58::decode(ix["data"].as_str().unwrap()).into_vec().unwrap();
                ixs.push((ix["programIdIndex"].as_u64().unwrap() as usize, accs, data));
            }
        }
        Tx { meta, signatures, keys, ixs }
    }

    fn bal(&self, which: &str, i: usize) -> i64 {
        self.meta[which][i].as_i64().unwrap()
    }

    /// Token amounts of `owner`'s accounts of `mint` (WSOL: the quote).
    fn token_amount(&self, which: &str, owner: &str, mint: &str) -> i64 {
        self.meta[which]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|t| t["owner"] == owner && t["mint"] == mint)
            .map(|t| t["uiTokenAmount"]["amount"].as_str().unwrap().parse::<i64>().unwrap())
            .sum()
    }

    fn wallet_index(&self, wallet: &str) -> usize {
        self.keys.iter().position(|k| k == wallet).expect("wallet in keys")
    }

    /// Accounts created here (pre 0, post > 0), other than the wallet: (key, lamports).
    fn created(&self, wallet: &str) -> Vec<(String, i64)> {
        let wi = self.wallet_index(wallet);
        let n = self.meta["preBalances"].as_array().unwrap().len();
        (0..n)
            .filter(|&i| i != wi && self.bal("preBalances", i) == 0 && self.bal("postBalances", i) > 0)
            .map(|i| (self.keys[i].clone(), self.bal("postBalances", i)))
            .collect()
    }

    /// System transfers from the wallet in an ok transaction to accounts neither created here nor wallet token accounts.
    fn tips(&self, wallet: &str) -> Vec<(String, i64)> {
        if !self.meta["err"].is_null() {
            return vec![];
        }
        let created: BTreeSet<String> = self.created(wallet).into_iter().map(|c| c.0).collect();
        let own: BTreeSet<String> = ["preTokenBalances", "postTokenBalances"]
            .iter()
            .flat_map(|w| self.meta[*w].as_array().cloned().unwrap_or_default())
            .filter(|t| t["owner"] == wallet)
            .map(|t| self.keys[t["accountIndex"].as_u64().unwrap() as usize].clone())
            .collect();
        self.ixs
            .iter()
            .filter(|(p, _, d)| self.keys[*p] == SYSTEM && d.len() == 12 && d[..4] == [2, 0, 0, 0])
            .filter_map(|(_, a, d)| {
                let (src, dst) = (&self.keys[a[0]], &self.keys[a[1]]);
                let lamports = i64::from_le_bytes(d[4..12].try_into().unwrap());
                (src == wallet && dst != wallet && !created.contains(dst) && !own.contains(dst)).then(|| (dst.clone(), lamports))
            })
            .collect()
    }
}

fn i(v: &Value) -> i64 {
    v.as_i64().unwrap_or_else(|| panic!("not an integer: {v}"))
}

#[test]
fn every_fixture_matches_its_sha256() {
    let td = testdata();
    let listed = manifest(&td.join("legacy/fixtures.sha256"), &td);
    assert!(listed.len() > 200, "fixtures.sha256 lists {} files", listed.len());
    for (p, h) in &listed {
        assert_eq!(&sha256_hex(p), h, "{}", p.display());
    }
    let on_disk = fixture_files();
    let listed_set: BTreeSet<PathBuf> = listed.keys().cloned().collect();
    assert_eq!(on_disk, listed_set, "fixture files and fixtures.sha256 differ");
    for (p, h) in manifest(&td.join("legacy/raw.sha256"), &td.join("legacy/raw")) {
        assert_eq!(listed.get(&p), Some(&h), "raw.sha256: {}", p.display());
    }
}

#[test]
fn every_json_fixture_parses_and_every_signature_has_its_transaction() {
    for p in fixture_files() {
        if p.extension().is_some_and(|e| e == "json") {
            read_json(&p);
        }
    }
    let sigs_doc = read_json(&testdata().join("legacy/signatures.json"));
    let wallet = sigs_doc["wallet"].as_str().unwrap();
    let mut sigs = BTreeSet::new();
    all_sigs(&sigs_doc, &mut sigs);
    let files: BTreeSet<String> = std::fs::read_dir(testdata().join("wallet"))
        .unwrap()
        .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
        .filter_map(|n| n.strip_suffix(".json").map(str::to_string))
        .collect();
    assert_eq!(sigs, files);
    for sig in &sigs {
        let tx = Tx::load(sig);
        assert_eq!(&tx.signatures[0], sig);
        tx.wallet_index(wallet);
    }
}

#[test]
fn ledger_cases_match_their_transactions() {
    let sigs_doc = read_json(&testdata().join("legacy/signatures.json"));
    let expected = read_json(&testdata().join("legacy/expected.json"));
    let wallet = sigs_doc["wallet"].as_str().unwrap();
    let cases = sigs_doc["cases"].as_array().unwrap();
    assert_eq!(cases.len(), expected["cases"].as_object().unwrap().len());
    for c in cases {
        let id = c["id"].as_str().unwrap();
        let sig = c["sig"].as_str().unwrap();
        let tx = Tx::load(sig);
        let ch = &c["chain"];
        // chain values from the transaction
        let wi = tx.wallet_index(wallet);
        assert_eq!(wi as i64, i(&ch["wallet_index"]), "{id}");
        let fee = if wi == 0 { i(&tx.meta["fee"]) } else { 0 };
        assert_eq!(fee, i(&ch["fee"]), "{id} fee");
        assert_eq!(tx.bal("postBalances", wi) - tx.bal("preBalances", wi), i(&ch["wallet_sol"]), "{id} wallet_sol");
        let wsol = tx.token_amount("postTokenBalances", wallet, WSOL) - tx.token_amount("preTokenBalances", wallet, WSOL);
        assert_eq!(wsol, i(&ch["wsol"]), "{id} wsol");
        assert_eq!(tx.meta["err"].is_null(), ch["ok"].as_bool().unwrap(), "{id} ok");
        let tips = tx.tips(wallet);
        match &ch["tip"] {
            Value::Null => assert!(tips.is_empty(), "{id} tips {tips:?}"),
            t => assert_eq!(tips, vec![(t["account"].as_str().unwrap().to_string(), i(&t["lamports"]))], "{id} tip"),
        }
        let created: Vec<(String, i64)> =
            ch["created"].as_array().unwrap().iter().map(|x| (x["account"].as_str().unwrap().to_string(), i(&x["lamports"]))).collect();
        assert_eq!(tx.created(wallet), created, "{id} created");
        // the expected ledger line (MEASUREMENT §4.42)
        let e = &expected["cases"][id];
        assert_eq!(e["sig"], c["sig"], "{id}");
        let (liquid, equity) = (i(&e["liquid_delta"]), i(&e["equity_delta"]));
        assert_eq!(e["categories"].as_array().unwrap().iter().map(|x| i(&x["lamports"])).sum::<i64>(), equity, "{id} categories");
        assert_eq!(liquid, i(&ch["wallet_sol"]) + i(&ch["wsol"]), "{id} liquid");
        assert_eq!(equity - liquid, i(&e["rent_locked"]) - i(&e["rent_reclaimed"]), "{id} equity");
        let rent = |rec: bool| -> i64 {
            ch["created"].as_array().unwrap().iter().filter(|x| x["recoverable"] == rec).map(|x| i(&x["rent"])).sum()
        };
        assert_eq!((i(&e["rent_locked"]), i(&e["rent_nonrecoverable"])), (rent(true), rent(false)), "{id} rent");
        assert_eq!(i(&e["fee"]), fee, "{id}");
        let tip = tips.iter().map(|t| t.1).sum::<i64>();
        assert_eq!(i(&e["tip"]), tip, "{id}");
        if e["kind"] == "route" {
            let gross = if e["ok"] == true { equity + fee + tip + rent(false) } else { 0 };
            assert_eq!((i(&e["trade_gross"]), i(&e["trade_net"])), (gross, gross - fee - tip), "{id} trade");
        } else {
            assert_eq!((i(&e["trade_gross"]), i(&e["trade_net"])), (0, 0), "{id} trade");
        }
    }
    let acc = &expected["cases"]["bundle_win_accumulator_create"];
    assert_eq!((i(&acc["rent_nonrecoverable"]), i(&acc["rent_locked"])), (1_346_200, 1_513_840));
}

#[test]
fn landings_reproduce_res_pnl_liquid_change_and_rent() {
    let sigs_doc = read_json(&testdata().join("legacy/signatures.json"));
    let expected = read_json(&testdata().join("legacy/expected.json"));
    let wallet = sigs_doc["wallet"].as_str().unwrap();
    let rows = sigs_doc["landed"]["rows"].as_array().unwrap();
    assert_eq!(rows.len(), 119);
    let (mut liquid, mut rent, mut wins) = (0i64, 0i64, 0);
    for r in rows {
        let tx = Tx::load(r["sig"].as_str().unwrap());
        let wi = tx.wallet_index(wallet);
        assert_eq!(wi, 0);
        assert_eq!(tx.meta["err"].is_null(), r["ok"].as_bool().unwrap());
        liquid += tx.bal("postBalances", wi) - tx.bal("preBalances", wi);
        liquid += tx.token_amount("postTokenBalances", wallet, WSOL) - tx.token_amount("preTokenBalances", wallet, WSOL);
        rent += tx.created(wallet).iter().map(|c| c.1).sum::<i64>();
        wins += tx.meta["err"].is_null() as usize;
    }
    let rp = &expected["res_pnl_p1_p10"];
    assert_eq!(liquid, i(&rp["liquid"]["sum_liquid_delta_landings"]));
    assert_eq!(liquid, -18_720_448);
    assert_eq!(rent, i(&rp["rent_total"]));
    assert_eq!(rent, 16_383_000);
    assert_eq!(wins as i64, i(&rp["total"]["wins"]));
}
