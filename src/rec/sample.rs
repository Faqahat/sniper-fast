//! Deterministic sampling of a stream's high-volume rows (plan addendum I-9, PLAN WP-08; review WP-08 #2).
//!
//! cmp2's rivals.jsonl (the 28-minute side-by-side shadow run) held 849,585 rows, 1.29 GB/h raw and 238 MB/h at zstd-3;
//! 744,411 of them (88%) were `why = venues` rows: any transaction touching two venue programs. Keeping 1 in 10 of those
//! rows (`[record] rivals_venues_sample`) and every `pools` and `known` row leaves 179,899 rows: 266 MB/h raw, 54 MB/h at
//! zstd-3 (MEASUREMENT §5).
//!
//! A row is kept by its transaction's signature ([`keep_1_in`]: splitmix64 of the signature's first 8 bytes,
//! little-endian, modulo the rate), never by arrival order or a random draw: a replay, a re-run of the same segment
//! and another bot recording the same transactions keep the same rows, so their recordings stay comparable. Every kept
//! row carries the rate and the running counts (`sample: {one_in, kept, seen}`), and manifest.json `sampling` holds the
//! totals, so readers weight a kept row by `one_in` and know exactly how many were left out.
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};

/// Whether the row of the transaction whose signature is `sig` is kept when keeping 1 in `one_in` (`one_in` <= 1 keeps
/// every row; a signature shorter than 8 bytes counts as zeros)
pub fn keep_1_in(sig: &[u8], one_in: u32) -> bool {
    if one_in <= 1 { return true; }
    let mut b = [0u8; 8];
    for (d, s) in b.iter_mut().zip(sig) { *d = *s; }
    let mut z = u64::from_le_bytes(b).wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^= z >> 31;
    z % one_in as u64 == 0
}

/// A sampled population's counts after a row (what a kept row carries as `sample`, and manifest.json `sampling.<name>`)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize)]
pub struct Kept {
    /// 1 row in this many is kept
    pub one_in: u32,
    /// rows kept so far (this one included)
    pub kept: u64,
    /// rows of the population seen so far, kept or not (this one included)
    pub seen: u64,
}

/// One sampled population (rivals.jsonl's `why = venues` rows)
pub struct Sampler { one_in: u32, seen: AtomicU64, kept: AtomicU64 }

impl Sampler {
    pub fn new(one_in: u32) -> Sampler { Sampler { one_in: one_in.max(1), seen: AtomicU64::new(0), kept: AtomicU64::new(0) } }
    /// One row of the population, of the transaction `sig`: Some(the counts after it) when it is kept, None when it is
    /// left out
    pub fn take(&self, sig: &[u8]) -> Option<Kept> {
        let seen = self.seen.fetch_add(1, Relaxed) + 1;
        if !keep_1_in(sig, self.one_in) { return None; }
        let kept = self.kept.fetch_add(1, Relaxed) + 1;
        Some(Kept { one_in: self.one_in, kept, seen })
    }
    /// the counts so far
    pub fn counts(&self) -> Kept { Kept { one_in: self.one_in, kept: self.kept.load(Relaxed), seen: self.seen.load(Relaxed) } }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The rule: 1 keeps all; the share kept is 1 / rate within a few percent on random-looking signatures; the choice
    /// depends on the signature alone (the same signature always gets the same answer, at any count); known answers pin
    /// the rule the I-9 sizing script used (splitmix64 of the first 8 bytes, little-endian)
    #[test]
    fn one_in_n_by_the_signature() {
        let sig = |n: u64| -> [u8; 64] { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.wrapping_mul(0x2545_F491_4F6C_DD1D).to_le_bytes()); s };
        assert!((0..1_000).all(|n| keep_1_in(&sig(n), 1) && keep_1_in(&sig(n), 0)));
        let kept = (0..100_000u64).filter(|n| keep_1_in(&sig(*n), 10)).count();
        assert!((9_500..=10_500).contains(&kept), "{kept} of 100,000 kept at 1 in 10");
        assert_eq!(keep_1_in(&[0u8; 64], 10), keep_1_in(&[0u8; 64], 10));
        // splitmix64(0) = 0xE220A8397B1DCDAF (its first output for seed 0): 16,294,208,416,658,607,535 % 10 = 5
        assert!(!keep_1_in(&[0u8; 64], 10) && keep_1_in(&[0u8; 64], 5));
        assert_eq!(keep_1_in(&[0u8; 4], 5), keep_1_in(&[0u8; 64], 5), "a short signature counts as zeros");
        let s = Sampler::new(10);
        let mut last = None;
        for n in 0..1_000u64 {
            match s.take(&sig(n)) {
                Some(k) => { assert!(keep_1_in(&sig(n), 10)); assert_eq!((k.one_in, k.seen), (10, n + 1)); last = Some(k); }
                None => assert!(!keep_1_in(&sig(n), 10)),
            }
        }
        let c = s.counts();
        assert_eq!((c.seen, Some(c.kept)), (1_000, last.map(|k| k.kept)));
        assert_eq!(Sampler::new(0).take(&sig(1)), Some(Kept { one_in: 1, kept: 1, seen: 1 }), "0 is read as 1: keep all");
    }

    /// Review WP-08 #1 and #2 through the engine (`record_rival`, fed shred-time arrivals with `Engine::step`): with
    /// `[record] rivals_venues_sample = 4`, the `why = venues` rows written are exactly the transactions whose signature
    /// the rule keeps, each with `sample {one_in, kept, seen}`; manifest.json `sampling.rivals_venues` has the totals;
    /// `pools` rows are all kept (`sample` null); a signer whose venues row was left out is still learned (its next
    /// transaction is a `known` row); a Glaive tip is named (the catalogue reaches rivals.jsonl); with 1 every row is
    /// kept, unmarked
    #[test]
    fn rivals_jsonl_samples_venues_rows_by_signature() {
        use crate::feeds::{Arrival, Event};
        use crate::venues::{PoolMeta, Venue};
        let pk = |s: &str| crate::tx::pk(s);
        let (pump, dlmm, glaive) = (pk("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"), pk("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"),
            pk("GLaivinAWh21NaJMhtExtD5G2gZs1xnvaYVZmwqobWZL"));
        let pool = |n: u8| PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: [7; 32], t1: *crate::venues::WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false };
        let sig = |n: u64| -> [u8; 64] { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.wrapping_mul(0x9E37_79B9_7F4A_7C15).to_le_bytes()); s[8] = 1; s };
        let signer = |n: u64| -> crate::tx::Pk { let mut k = [0u8; 32]; k[..8].copy_from_slice(&(n + 1_000).to_le_bytes()); k[31] = 0xEE; k };
        // a transaction touching PumpSwap and DLMM (a `venues` row) that tips Glaive 7,000 lamports; or two watched
        // pools (`pools`); or one venue only (`known` if its signer is)
        let tx = |n: u64, s: crate::tx::Pk, programs: Vec<crate::tx::Pk>| {
            let mut keys = vec![s, [0u8; 32], glaive];
            keys.extend(programs);
            let mut d = 2u32.to_le_bytes().to_vec();
            d.extend(7_000u64.to_le_bytes());
            let ixs = vec![crate::tx::Ix { program: 1, accounts: vec![0, 2], data: d }];
            Arrival { feed: 0, slot: 100, t_rx: 1_000 + n, t_decoded: 1_000 + n, executed: None, poh: None, raw: Default::default(),
                tx: crate::tx::Tx { sig: sig(n), keys, ixs, num_signers: 1, ..Default::default() } }
        };
        let run = |one_in: u32| {
            let dir = std::env::temp_dir().join(format!("arbx-rivals-sample-{one_in}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
            let rec = crate::rec::start(crate::rec::Opts { dir: dir.clone(), run: "t".into(), producer: "p".into(),
                cfg: crate::config::RecordCfg { rivals_venues_sample: one_in, ..Default::default() }, feeds: vec!["shred".into()], monitor: false,
                echo: Some(Box::new(std::io::sink())) }).unwrap();
            let mut reg = crate::pools::Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
            for (i, n) in [1u8, 2].into_iter().enumerate() { reg.by_pool.insert([n; 32], i); reg.pools.push(pool(n)); }
            let mut e = crate::engine::Engine::new_offline(std::sync::Arc::new(reg), crate::store::Store::default(), crate::config::StrategyCfg::default());
            e.set_rec(rec.clone());
            for n in 0..200 { e.step(Event::Tx(tx(n, signer(n), vec![pump, dlmm])), 10_000 + n, &mut |_: &str| {}); }
            for n in 200..210 { e.step(Event::Tx(tx(n, signer(n), vec![[1u8; 32], [2u8; 32]])), 10_000 + n, &mut |_: &str| {}); }
            // the signer of the first venues row the rule leaves out (or keeps, at 1 in 1), on one venue only: `known`
            let out = (0..200).find(|n| !keep_1_in(&sig(*n), one_in)).unwrap_or(0);
            e.step(Event::Tx(tx(500, signer(out), vec![pump])), 20_000, &mut |_: &str| {});
            rec.close();
            let rows = crate::rec::read_jsonl(&dir, "rivals").unwrap();
            let manifest: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(dir.join("manifest.json")).unwrap()).unwrap();
            let _ = std::fs::remove_dir_all(&dir);
            (rows, manifest, out)
        };
        let (rows, manifest, out) = run(4);
        let venues: Vec<&serde_json::Value> = rows.iter().filter(|r| r["why"] == "venues").collect();
        let want: Vec<String> = (0..200).filter(|n| keep_1_in(&sig(*n), 4)).map(|n| bs58::encode(sig(n)).into_string()).collect();
        assert!((30..=70).contains(&want.len()), "about 1 in 4 of 200: {}", want.len());
        assert_eq!(venues.iter().map(|r| r["sig"].as_str().unwrap().to_string()).collect::<Vec<_>>(), want);
        for (i, r) in venues.iter().enumerate() {
            let n = (0..200).find(|n| bs58::encode(sig(*n)).into_string() == r["sig"].as_str().unwrap()).unwrap();
            assert_eq!(r["sample"], serde_json::json!({ "one_in": 4, "kept": i as u64 + 1, "seen": n + 1 }), "{r}");
            assert_eq!(r["tips"], serde_json::json!([[bs58::encode(glaive).into_string(), 7_000, "glaive"]]), "the catalogue names Glaive");
        }
        assert_eq!(manifest["sampling"]["rivals_venues"], serde_json::json!({ "one_in": 4, "kept": want.len(), "seen": 200 }));
        let pools: Vec<&serde_json::Value> = rows.iter().filter(|r| r["why"] == "pools").collect();
        assert!(pools.len() == 10 && pools.iter().all(|r| r["sample"].is_null()), "pools rows are never sampled");
        let known: Vec<&serde_json::Value> = rows.iter().filter(|r| r["why"] == "known").collect();
        assert_eq!(known.len(), 1, "the left-out row's signer was still learned");
        assert_eq!(known[0]["signer"].as_str(), Some(bs58::encode(signer(out)).into_string().as_str()));
        assert!(!want.contains(&bs58::encode(sig(out)).into_string()));
        // 1: every row, unmarked
        let (rows, manifest, _) = run(1);
        assert_eq!(rows.iter().filter(|r| r["why"] == "venues" && r["sample"].is_null()).count(), 200);
        assert_eq!(manifest["sampling"]["rivals_venues"], serde_json::json!({ "one_in": 1, "kept": 200, "seen": 200 }));
    }
}
