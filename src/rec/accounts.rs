//! accounts.bin (MEASUREMENT §4.12; PLAN WP-03 item 1): every watched-account update, stale ones included, each with
//! its segment-wide sequence number `aseq`. The producers (the state stream's feed task, the boot snapshot, the
//! engine's RPC re-fetches) call [`AcctRec::record`], which takes the next `aseq` and hands the record to the replay
//! writer under one lock, so the file is in `aseq` order; the `aseq` then travels in `Event::Account` and the journal
//! names the record by it (F25).
//!
//! The encoding runs on the replay writer against a per-file state ([`AccDict`], a `FileState`): a DICT record the
//! first time an account appears in a file, then FULL or XOR records (XOR: the data XOR the account's previous data in
//! this file, when the length is unchanged and the keyframe interval has not run out). Every file restarts its
//! dictionary and keyframes, so it decodes on its own (§1.3). [`parse`] reads a file back (tests, replay).
use super::{Rec, Record, ACCOUNTS};
use crate::feeds::clock::now_ns;
use crate::tx::Pk;
use anyhow::{bail, Context, Result};
use rustc_hash::FxHashMap as HashMap;
use std::sync::{Arc, Mutex, RwLock};

/// record kinds (§4.12)
pub const K_DICT: u8 = 1;
pub const K_FULL: u8 = 2;
pub const K_XOR: u8 = 3;
pub const K_MARK: u8 = 4;
pub const K_GAP: u8 = 6;

/// MARK kinds
pub const MARK_BOOT_BEGIN: u8 = 1;
pub const MARK_BOOT_END: u8 = 2;
pub const MARK_STREAM_RECONNECT: u8 = 3;
pub const MARK_WATCH_LIST_CHANGED: u8 = 4;
pub const MARK_FORK_REFETCH: u8 = 5;

/// account roles (DICT `role`)
pub mod role {
    pub const OTHER: u8 = 0;
    pub const POOL: u8 = 1;
    pub const VAULT: u8 = 2;
    pub const EXTRA: u8 = 3;
    pub const DLMM_BIN_ARRAY: u8 = 4;
    pub const MINT: u8 = 5;
    pub const CLOCK_SYSVAR: u8 = 6;
    pub const DLMM_BITMAP_EXT: u8 = 7;
    pub const PROGRAMDATA: u8 = 8;
    pub const WALLET: u8 = 9;
    pub const WALLET_TOKEN_ACCOUNT: u8 = 10;
    pub const PUMP_FEE_CONFIG: u8 = 11;
    /// exec.jsonl `watched[].role`
    pub fn name(r: u8) -> &'static str {
        match r { POOL => "pool", VAULT => "vault", EXTRA => "extra", DLMM_BIN_ARRAY => "dlmm_bin_array", MINT => "mint", CLOCK_SYSVAR => "clock_sysvar",
            DLMM_BITMAP_EXT => "dlmm_bitmap_ext", PROGRAMDATA => "programdata", WALLET => "wallet", WALLET_TOKEN_ACCOUNT => "wallet_token_account",
            PUMP_FEE_CONFIG => "pump_fee_config", _ => "other" }
    }
}

/// `pool_index` of an account that belongs to no pool
pub const NO_POOL: u32 = u32::MAX;

/// What a watched account is: its role and the pool it belongs to (index in the registry, pools.json `idx`)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RoleOf { pub role: u8, pub pool_index: u32 }

/// Every watched account's role, shared by the state stream (accounts.bin DICT), the transaction feeds (exec.jsonl v2
/// `watched`, `pools`) and the engine (it adds the DLMM bin arrays it starts following)
#[derive(Default)]
pub struct Roles { m: RwLock<HashMap<Pk, RoleOf>> }

impl Roles {
    pub fn new(list: impl IntoIterator<Item = (Pk, RoleOf)>) -> Roles {
        let mut m = HashMap::default();
        for (k, r) in list { m.entry(k).or_insert(r); }
        Roles { m: RwLock::new(m) }
    }
    pub fn get(&self, k: &Pk) -> Option<RoleOf> { self.m.read().unwrap_or_else(|e| e.into_inner()).get(k).copied() }
    /// add accounts (an existing entry keeps its role); returns the ones that were new
    pub fn add(&self, list: impl IntoIterator<Item = (Pk, RoleOf)>) -> Vec<Pk> {
        let mut m = self.m.write().unwrap_or_else(|e| e.into_inner());
        let mut new = Vec::new();
        for (k, r) in list { if let std::collections::hash_map::Entry::Vacant(e) = m.entry(k) { e.insert(r); new.push(k); } }
        new
    }
    pub fn len(&self) -> usize { self.m.read().unwrap_or_else(|e| e.into_inner()).len() }
    pub fn is_empty(&self) -> bool { self.len() == 0 }
    /// (role, pool index) for a DICT record: unknown accounts are `other` with no pool
    fn of(&self, k: &Pk) -> (u8, u32) { self.get(k).map_or((role::OTHER, NO_POOL), |r| (r.role, r.pool_index)) }
}

/// One account update, as its producer has it
pub struct AcctUpdate<'a> {
    pub pubkey: Pk,
    pub slot: u64,
    /// 0 for RPC reads
    pub write_version: u64,
    pub t_recv: u64,
    /// `feeds::src`
    pub src: u8,
    pub is_startup: bool,
    pub txn: Option<[u8; 64]>,
    pub lamports: u64,
    pub owner: Pk,
    pub data: &'a Arc<[u8]>,
}

/// The accounts.bin producer handle (cheap to share: `Arc`)
pub struct AcctRec { rec: Rec, roles: Arc<Roles>, lock: Mutex<()> }

impl AcctRec {
    /// The handle for `rec`'s accounts stream; installs the per-file encoder state
    pub fn new(rec: Rec, roles: Arc<Roles>) -> Arc<AcctRec> {
        rec.set_file_state(ACCOUNTS, Box::new(AccDict::default()));
        Arc::new(AcctRec { rec, roles, lock: Mutex::new(()) })
    }
    pub fn rec(&self) -> &Rec { &self.rec }
    pub fn roles(&self) -> &Arc<Roles> { &self.roles }

    /// Record one update; returns its `aseq` (0 without a recorder). Never blocks on the writer: a full queue drops the
    /// record (counted, and a GAP precedes the stream's next record)
    pub fn record(&self, u: &AcctUpdate) -> u64 {
        if !self.rec.is_on() { return 0; }
        let (role, pool_index) = self.roles.of(&u.pubkey);
        let every = self.rec.accounts_keyframe_every().max(1);
        let rec = Rec2 { pubkey: u.pubkey, role, pool_index, slot: u.slot, wv: u.write_version, t: u.t_recv, src: u.src,
            flags: (u.txn.is_some() as u8) | ((u.is_startup as u8) << 1), txn: u.txn, lamports: u.lamports, owner: u.owner, data: u.data.clone() };
        let size = u.data.len() as u64 + 160;
        // the aseq and the queue order are taken together: the file is in aseq order whatever thread records
        let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        let aseq = self.rec.next_seq(ACCOUNTS);
        self.rec.emit_seq_sized(ACCOUNTS, aseq, size, Record::stateful::<AccDict>(move |st, o| st.encode(aseq, &rec, every, o)));
        aseq
    }

    /// A MARK record (`mark`: MARK_*), naming `accts` (their DICT records come first when a file has not seen them)
    pub fn mark(&self, mark: u8, accts: &[Pk]) {
        if !self.rec.is_on() { return; }
        let t = now_ns();
        let list: Vec<(Pk, u8, u32)> = accts.iter().map(|k| { let (r, p) = self.roles.of(k); (*k, r, p) }).collect();
        let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        self.rec.emit(ACCOUNTS, Record::stateful::<AccDict>(move |st, o| {
            let ids: Vec<u32> = list.iter().map(|(k, r, p)| st.id(k, *r, *p, o)).collect();
            o.push(K_MARK);
            o.extend((13 + 4 * ids.len() as u32).to_le_bytes());
            o.extend(t.to_le_bytes());
            o.push(mark);
            o.extend((ids.len() as u32).to_le_bytes());
            for i in ids { o.extend(i.to_le_bytes()); }
        }));
    }
}

/// what the writer needs of one update
struct Rec2 { pubkey: Pk, role: u8, pool_index: u32, slot: u64, wv: u64, t: u64, src: u8, flags: u8, txn: Option<[u8; 64]>, lamports: u64, owner: Pk, data: Arc<[u8]> }

/// The per-file dictionary and keyframe state (writer side)
#[derive(Default)]
pub struct AccDict {
    ids: HashMap<Pk, u32>,
    /// per acct_id: its last data in this file, and records since its last FULL
    last: Vec<(Vec<u8>, u32)>,
}

impl super::FileState for AccDict {
    fn on_new_file(&mut self, _file_seq: u32, _out: &mut Vec<u8>) { self.ids.clear(); self.last.clear(); }
    fn as_any(&mut self) -> &mut dyn std::any::Any { self }
}

impl AccDict {
    /// the account's id in this file; a DICT record into `o` when it is new here
    fn id(&mut self, k: &Pk, role: u8, pool_index: u32, o: &mut Vec<u8>) -> u32 {
        if let Some(i) = self.ids.get(k) { return *i; }
        let i = self.ids.len() as u32;
        self.ids.insert(*k, i);
        self.last.push((Vec::new(), u32::MAX));
        o.push(K_DICT);
        o.extend(41u32.to_le_bytes());
        o.extend(i.to_le_bytes());
        o.extend_from_slice(k);
        o.push(role);
        o.extend(pool_index.to_le_bytes());
        i
    }

    fn encode(&mut self, aseq: u64, r: &Rec2, every: u32, o: &mut Vec<u8>) {
        let id = self.id(&r.pubkey, r.role, r.pool_index, o);
        let (prev, since) = &mut self.last[id as usize];
        // FULL: the account's first record in this file, a length change, or the keyframe interval run out
        let xor = *since != u32::MAX && prev.len() == r.data.len() && *since + 1 < every;
        o.push(if xor { K_XOR } else { K_FULL });
        let at = o.len();
        o.extend([0u8; 4]);
        o.extend(aseq.to_le_bytes());
        o.extend(id.to_le_bytes());
        o.extend(r.slot.to_le_bytes());
        o.extend(r.wv.to_le_bytes());
        o.extend(r.t.to_le_bytes());
        o.push(r.src);
        o.push(r.flags);
        if let Some(s) = &r.txn { o.extend_from_slice(s); }
        o.extend(r.lamports.to_le_bytes());
        o.extend_from_slice(&r.owner);
        o.extend(xxhash_rust::xxh3::xxh3_64(&r.data).to_le_bytes());
        o.extend((r.data.len() as u32).to_le_bytes());
        if xor { o.extend(r.data.iter().zip(prev.iter()).map(|(a, b)| a ^ b)); } else { o.extend_from_slice(&r.data); }
        let len = (o.len() - at - 4) as u32;
        o[at..at + 4].copy_from_slice(&len.to_le_bytes());
        prev.clear();
        prev.extend_from_slice(&r.data);
        *since = if xor { *since + 1 } else { 0 };
    }
}

// ------------------------------------------------------------------ reader

/// One decoded FULL or XOR record (XOR applied)
#[derive(Clone, Debug, PartialEq)]
pub struct AcctRecord {
    pub aseq: u64,
    pub pubkey: Pk,
    pub role: u8,
    pub pool_index: Option<u32>,
    pub slot: u64,
    pub write_version: u64,
    pub t_recv: u64,
    pub src: u8,
    pub is_startup: bool,
    pub txn: Option<[u8; 64]>,
    pub lamports: u64,
    pub owner: Pk,
    pub data: Vec<u8>,
    /// 2 FULL, 3 XOR
    pub kind: u8,
}

/// What one accounts.bin file holds
#[derive(Debug, Default)]
pub struct Parsed {
    pub header: serde_json::Value,
    pub records: Vec<AcctRecord>,
    /// (t_ns, mark, accounts)
    pub marks: Vec<(u64, u8, Vec<Pk>)>,
    /// (first_lost_aseq, n_lost)
    pub gaps: Vec<(u64, u64)>,
}

fn rd<const N: usize>(b: &[u8], p: &mut usize) -> Result<[u8; N]> {
    let x: [u8; N] = b.get(*p..*p + N).context("truncated record")?.try_into().unwrap();
    *p += N;
    Ok(x)
}
fn u32_(b: &[u8], p: &mut usize) -> Result<u32> { Ok(u32::from_le_bytes(rd(b, p)?)) }
fn u64_(b: &[u8], p: &mut usize) -> Result<u64> { Ok(u64::from_le_bytes(rd(b, p)?)) }

/// Read one accounts.bin file (decompressed): its header, records (XOR applied, `data_xxh3` checked), marks and gaps
pub fn parse(b: &[u8]) -> Result<Parsed> {
    if b.get(..8) != Some(&super::ACCOUNTS_MAGIC[..]) { bail!("not an accounts.bin file"); }
    let fmt = u16::from_le_bytes([b[8], b[9]]);
    if fmt != 2 { bail!("accounts.bin format {fmt}"); }
    let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
    let mut out = Parsed { header: serde_json::from_slice(b.get(12..12 + hlen).context("header")?)?, ..Default::default() };
    let mut p = 12 + hlen;
    let mut dict: HashMap<u32, (Pk, u8, u32)> = HashMap::default();
    let mut last: HashMap<u32, Vec<u8>> = HashMap::default();
    while p < b.len() {
        let kind = b[p];
        p += 1;
        let blen = u32_(b, &mut p)? as usize;
        let body = b.get(p..p + blen).context("truncated body")?;
        p += blen;
        let mut q = 0;
        match kind {
            K_DICT => {
                let id = u32_(body, &mut q)?;
                let k: Pk = rd(body, &mut q)?;
                let role = rd::<1>(body, &mut q)?[0];
                let pi = u32_(body, &mut q)?;
                dict.insert(id, (k, role, pi));
            }
            K_FULL | K_XOR => {
                let aseq = u64_(body, &mut q)?;
                let id = u32_(body, &mut q)?;
                let slot = u64_(body, &mut q)?;
                let wv = u64_(body, &mut q)?;
                let t = u64_(body, &mut q)?;
                let src = rd::<1>(body, &mut q)?[0];
                let flags = rd::<1>(body, &mut q)?[0];
                let txn = if flags & 1 != 0 { Some(rd::<64>(body, &mut q)?) } else { None };
                let lamports = u64_(body, &mut q)?;
                let owner: Pk = rd(body, &mut q)?;
                let h = u64_(body, &mut q)?;
                let n = u32_(body, &mut q)? as usize;
                let raw = body.get(q..q + n).context("truncated data")?;
                let data: Vec<u8> = if kind == K_XOR {
                    let base = last.get(&id).context("an XOR record without its base")?;
                    if base.len() != n { bail!("aseq {aseq}: XOR length {n} against a base of {}", base.len()); }
                    raw.iter().zip(base).map(|(a, b)| a ^ b).collect()
                } else { raw.to_vec() };
                if xxhash_rust::xxh3::xxh3_64(&data) != h { bail!("aseq {aseq}: data_xxh3 mismatch"); }
                let (pubkey, role, pi) = *dict.get(&id).with_context(|| format!("aseq {aseq}: unknown acct_id {id}"))?;
                last.insert(id, data.clone());
                out.records.push(AcctRecord { aseq, pubkey, role, pool_index: (pi != NO_POOL).then_some(pi), slot, write_version: wv, t_recv: t, src,
                    is_startup: flags & 2 != 0, txn, lamports, owner, data, kind });
            }
            K_MARK => {
                let t = u64_(body, &mut q)?;
                let m = rd::<1>(body, &mut q)?[0];
                let n = u32_(body, &mut q)?;
                let mut ks = Vec::new();
                for _ in 0..n { let id = u32_(body, &mut q)?; ks.push(dict.get(&id).map(|x| x.0).context("a MARK names an unknown acct_id")?); }
                out.marks.push((t, m, ks));
            }
            K_GAP => { let a = u64_(body, &mut q)?; let n = u64_(body, &mut q)?; out.gaps.push((a, n)); }
            k => bail!("unknown accounts.bin record kind {k}"),
        }
    }
    Ok(out)
}

/// Every accounts.bin file of a run directory, in order, merged (tests, replay)
pub fn read_dir(dir: &std::path::Path) -> Result<Parsed> {
    let mut all = Parsed::default();
    for (i, b) in super::read_files(dir, "accounts")?.iter().enumerate() {
        let p = parse(b).with_context(|| format!("accounts file {i}"))?;
        if i == 0 { all.header = p.header; }
        all.records.extend(p.records);
        all.marks.extend(p.marks);
        all.gaps.extend(p.gaps);
    }
    Ok(all)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// review WP-03 #11 (the reviewer's scratch test, adopted): 2,000 updates of one account with a keyframe every 8
    /// records, length changes and rotation every ~50 KB: every record decodes to its exact data across the files
    /// (each file restarts its dictionary and keyframes), FULL records come at the interval and at length changes, the
    /// MARKs (boot, watch list changed, stream reconnect) are read back with their accounts, and there is no gap
    #[test]
    fn keyframes_marks_and_rotation() {
        let d = std::env::temp_dir().join(format!("arbx-acc-rot-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        let cfg = crate::config::RecordCfg { rotate_mb: 0.05, accounts_keyframe_every: 8, ..Default::default() };
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg, feeds: vec![],
            monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap();
        let k: Pk = [4; 32];
        let acct = AcctRec::new(rec.clone(), Arc::new(Roles::new([(k, RoleOf { role: role::VAULT, pool_index: 3 })])));
        let mut want = Vec::new();
        acct.mark(MARK_BOOT_BEGIN, &[k]);
        for i in 0..2_000u64 {
            let len = if i % 97 == 50 { 170 } else { 165 };
            let mut v = vec![(i % 251) as u8; len];
            v[0..8].copy_from_slice(&i.to_le_bytes());
            let data: Arc<[u8]> = v.clone().into();
            let q = acct.record(&AcctUpdate { pubkey: k, slot: i, write_version: i, t_recv: i, src: 0, is_startup: false, txn: None, lamports: i, owner: [1; 32], data: &data });
            assert_eq!(q, i, "aseq in order");
            want.push(v);
            if i == 1_000 { acct.mark(MARK_STREAM_RECONNECT, &[]); }
            if i % 300 == 0 { std::thread::sleep(std::time::Duration::from_millis(5)); }
        }
        acct.mark(MARK_WATCH_LIST_CHANGED, &[k, [9; 32]]);
        rec.close();
        let files = crate::rec::read_files(&d, "accounts").unwrap();
        let a = read_dir(&d).unwrap();
        assert!(files.len() > 1, "rotated: {} files", files.len());
        assert_eq!(a.records.len(), 2_000);
        for (r, w) in a.records.iter().zip(&want) { assert_eq!(&r.data, w, "aseq {}", r.aseq); assert_eq!((r.slot, r.lamports), (r.aseq, r.aseq)); }
        let full = a.records.iter().filter(|r| r.kind == K_FULL).count();
        let xor = a.records.iter().filter(|r| r.kind == K_XOR).count();
        assert_eq!(full + xor, 2_000);
        assert!(full >= 2_000 / 8 && xor > full, "a keyframe at least every 8 records: {full} FULL, {xor} XOR");
        // the record after each length change is a FULL one
        for (i, r) in a.records.iter().enumerate().skip(1) {
            if r.data.len() != a.records[i - 1].data.len() { assert_eq!(r.kind, K_FULL, "aseq {}", r.aseq); }
        }
        let marks: Vec<(u8, usize)> = a.marks.iter().map(|m| (m.1, m.2.len())).collect();
        assert_eq!(marks, vec![(MARK_BOOT_BEGIN, 1), (MARK_STREAM_RECONNECT, 0), (MARK_WATCH_LIST_CHANGED, 2)]);
        assert!(a.gaps.is_empty());
        let _ = std::fs::remove_dir_all(&d);
    }
}
