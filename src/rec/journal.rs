//! journal.bin (MEASUREMENT §4.13; PLAN WP-03 item 11): the engine's input journal. Every input the engine handles is
//! written here at its dequeue point, with the one clock value (`t_engine_ns`) the engine used for every decision made
//! while handling it, and every timer evaluation (`Engine::timers`) is a TIMER record. Fed back in the same order
//! into `Engine::new_offline` (`replay`), a journal gives the same state and the same decisions (the determinism
//! contract of §4.13). Only the engine thread writes it (and `arbx run`'s boot, before the engine starts), so `seq` is
//! the file order.
//!
//! Record: `u8 kind | u32 body_len | u64 seq | u64 t_engine_ns | body` (`body_len` counts the body only). Account
//! updates are journaled by their accounts.bin `aseq` with the store's verdict; the boot snapshot's are journaled
//! with `t_engine_ns` 0 (applied to the store before the engine starts, as `arbx run` does).
use super::accounts::AcctRecord;
use super::{Rec, Record, JOURNAL};
use crate::feeds::entries::Poh;
use crate::feeds::{grpc, Arrival, Event, InputKind, RawTx};
use crate::tx::Pk;
use anyhow::{bail, Context, Result};
use prost::Message as _;
use rustc_hash::FxHashMap as HashMap;
use std::sync::Arc;

pub const J_TX_FIRST: u8 = 1;
pub const J_TX_COPY: u8 = 2;
pub const J_ACCOUNT: u8 = 3;
pub const J_SLOT: u8 = 4;
pub const J_BLOCK_META: u8 = 5;
pub const J_ALT: u8 = 6;
pub const J_INPUT: u8 = 7;
pub const J_TICK: u8 = 8;
pub const J_STATUS: u8 = 9;
pub const J_TIMER: u8 = 10;
pub const J_GAP: u8 = 12;

/// TX_FIRST `enc`
pub const ENC_WIRE: u8 = 0;
pub const ENC_PB: u8 = 1;

/// The journal's producer handle (engine thread)
#[derive(Clone, Default)]
pub struct Journal { rec: Rec }

impl Journal {
    pub fn new(rec: Rec) -> Journal { Journal { rec } }
    pub fn off() -> Journal { Journal { rec: Rec::off() } }
    pub fn is_on(&self) -> bool { self.rec.is_on() }

    /// one record: the framing here, the body by `body` on the replay writer. `size`: the payload bytes `body` holds
    fn put(&self, kind: u8, t: u64, size: u64, body: impl FnOnce(&mut Vec<u8>) + Send + 'static) {
        if !self.rec.is_on() { return; }
        let seq = self.rec.next_seq(JOURNAL);
        self.rec.emit_seq_sized(JOURNAL, seq, size, Record::enc(move |o| {
            o.push(kind);
            let at = o.len();
            o.extend([0u8; 4]);
            o.extend(seq.to_le_bytes());
            o.extend(t.to_le_bytes());
            let b0 = o.len();
            body(o);
            let n = (o.len() - b0) as u32;
            o[at..at + 4].copy_from_slice(&n.to_le_bytes());
        }));
    }

    /// TX_FIRST: a transaction in full (its bytes as delivered, the addresses its feed loaded, its PoH position). Also
    /// used for a later copy that carries loaded addresses: the engine learns lookup-table entries from it
    pub fn tx_first(&self, t: u64, a: &Arrival) {
        if !self.rec.is_on() { return; }
        let (enc, bytes): (u8, Raw) = match &a.raw {
            RawTx::Wire(b) => (ENC_WIRE, Raw::Wire(b.clone())),
            RawTx::Pb(p) => (ENC_PB, Raw::Pb(p.clone())),
            // a synthetic arrival (no bytes kept): its parsed form, re-encoded (legacy / v0 wire format)
            RawTx::None => (ENC_WIRE, Raw::Wire(crate::tx::to_wire(&a.tx).map(Arc::from).unwrap_or_else(|| Arc::from(&[][..])))),
        };
        let (feed, slot, t_rx, t_dec) = (a.feed, a.slot, a.t_rx, a.t_decoded);
        let executed: i8 = match a.executed { None => -1, Some(false) => 0, Some(true) => 1 };
        let loaded = a.tx.loaded.clone();
        let poh = a.poh;
        let size = match &bytes { Raw::Wire(b) => b.len() as u64, Raw::Pb(_) => 1_232 } + loaded.as_ref().map_or(0, |(w, r)| 32 * (w.len() + r.len()) as u64);
        self.put(J_TX_FIRST, t, size, move |o| {
            o.extend(feed.to_le_bytes());
            o.extend(slot.to_le_bytes());
            o.extend(t_rx.to_le_bytes());
            o.extend(t_dec.to_le_bytes());
            o.push(executed as u8);
            o.push(enc);
            let at = o.len();
            o.extend([0u8; 4]);
            match &bytes { Raw::Wire(b) => o.extend_from_slice(b), Raw::Pb(p) => { let _ = p.encode(o); } }
            let n = (o.len() - at - 4) as u32;
            o[at..at + 4].copy_from_slice(&n.to_le_bytes());
            match &loaded {
                Some((w, r)) => {
                    o.push(1);
                    o.extend((w.len() as u16).to_le_bytes());
                    for k in w { o.extend_from_slice(k); }
                    o.extend((r.len() as u16).to_le_bytes());
                    for k in r { o.extend_from_slice(k); }
                }
                None => o.push(0),
            }
            put_poh(o, poh.as_ref());
        });
    }

    /// TX_COPY: a later copy (timing as the engine uses it; WP-03 appends its PoH position when it has one, which the
    /// engine keeps if the first copy had none)
    pub fn tx_copy(&self, t: u64, a: &Arrival) {
        let (sig, feed, t_rx, poh) = (a.tx.sig, a.feed, a.t_rx, a.poh);
        self.put(J_TX_COPY, t, 0, move |o| {
            o.extend_from_slice(&sig);
            o.extend(feed.to_le_bytes());
            o.extend(t_rx.to_le_bytes());
            put_poh(o, poh.as_ref());
        });
    }

    /// ACCOUNT: an account update by its accounts.bin `aseq`, with the store's verdict
    pub fn account(&self, t: u64, aseq: u64, stale: bool) {
        self.put(J_ACCOUNT, t, 0, move |o| { o.extend(aseq.to_le_bytes()); o.push(stale as u8); });
    }

    pub fn slot(&self, t: u64, slot: u64, parent: Option<u64>, status: i32, t_recv: u64) {
        self.put(J_SLOT, t, 0, move |o| {
            o.extend(slot.to_le_bytes());
            o.extend(parent.unwrap_or(u64::MAX).to_le_bytes());
            o.extend(status.to_le_bytes());
            o.extend(t_recv.to_le_bytes());
        });
    }

    /// BLOCK_META (`height` u64::MAX: unknown)
    pub fn block_meta(&self, t: u64, b: &grpc::BlockMeta) {
        let (slot, hash, height, parent, tr) = (b.slot, b.blockhash, b.block_height.unwrap_or(u64::MAX), b.parent_slot, b.t);
        self.put(J_BLOCK_META, t, 0, move |o| {
            o.extend(slot.to_le_bytes());
            o.extend_from_slice(&hash);
            o.extend(height.to_le_bytes());
            o.extend(parent.to_le_bytes());
            o.extend(tr.to_le_bytes());
        });
    }

    /// ALT: a lookup table fetched off the hot path (found or not)
    pub fn alt(&self, t: u64, table: Pk, addrs: Option<Arc<Vec<Pk>>>) {
        let size = addrs.as_ref().map_or(0, |a| 32 * a.len() as u64);
        self.put(J_ALT, t, size, move |o| {
            o.extend_from_slice(&table);
            o.push(addrs.is_some() as u8);
            let a = addrs.as_deref().map(|v| &v[..]).unwrap_or(&[]);
            o.extend((a.len().min(u16::MAX as usize) as u16).to_le_bytes());
            for k in a.iter().take(u16::MAX as usize) { o.extend_from_slice(k); }
        });
    }

    /// INPUT: an input from another subsystem (or the engine's own engine_init / decision-point gate records). `data`
    /// is shared, not copied: it is serialized on the recorder's writer (review WP-03 N3)
    pub fn input(&self, t: u64, kind: InputKind, data: Arc<serde_json::Value>) { self.input_sized(t, kind, data, 0) }

    /// INPUT with the payload's approximate size (a large one, engine_init's signer statistics, counts against the
    /// journal queue's byte cap)
    pub fn input_sized(&self, t: u64, kind: InputKind, data: Arc<serde_json::Value>, size: u64) {
        let d = data;
        self.put(J_INPUT, t, size, move |o| {
            o.push(kind as u8);
            let at = o.len();
            o.extend([0u8; 4]);
            let _ = serde_json::to_writer(&mut *o, &*d);
            let n = (o.len() - at - 4) as u32;
            o[at..at + 4].copy_from_slice(&n.to_le_bytes());
        });
    }

    /// TICK: housekeeping wrote a status line here (status only)
    pub fn tick(&self, t: u64) { self.put(J_TICK, t, 0, |_| {}); }

    /// STATUS: a feed's status message (ignored by replay): `u16 feed | UTF-8 text`
    pub fn status(&self, t: u64, feed: u16, msg: &str) {
        let m = msg.to_string();
        self.put(J_STATUS, t, m.len() as u64, move |o| { o.extend(feed.to_le_bytes()); o.extend_from_slice(m.as_bytes()); });
    }

    /// TIMER: `timers_at(t, what)` ran here (`what`: `engine::TIMER_FLUSH` | `engine::TIMER_HK`)
    pub fn timer(&self, t: u64, what: u8) { self.put(J_TIMER, t, 0, move |o| { o.extend(t.to_le_bytes()); o.push(what); }); }
}

enum Raw { Wire(Arc<[u8]>), Pb(Arc<grpc::PbTransaction>) }

fn put_poh(o: &mut Vec<u8>, poh: Option<&Poh>) {
    match poh {
        Some(p) => { o.push(1); o.extend(p.slot.to_le_bytes()); o.extend(p.hashes.to_le_bytes()); o.extend(p.ticks.to_le_bytes()); o.extend(p.hpt.to_le_bytes()); }
        None => o.push(0),
    }
}

// ------------------------------------------------------------------ reader

/// One journal record
#[derive(Clone, Debug)]
pub struct JRec { pub seq: u64, pub t_engine: u64, pub body: JBody }

#[derive(Clone, Debug)]
pub enum JBody {
    TxFirst { feed: u16, slot: u64, t_rx: u64, t_decoded: u64, executed: Option<bool>, enc: u8, bytes: Vec<u8>, loaded: Option<(Vec<Pk>, Vec<Pk>)>, poh: Option<Poh> },
    TxCopy { sig: [u8; 64], feed: u16, t_rx: u64, poh: Option<Poh> },
    Account { aseq: u64, stale: bool },
    Slot { slot: u64, parent: Option<u64>, status: i32, t: u64 },
    BlockMeta { slot: u64, blockhash: [u8; 32], height: Option<u64>, parent_slot: u64, t: u64 },
    Alt { table: Pk, addrs: Option<Vec<Pk>> },
    Input { kind: u8, data: serde_json::Value },
    Tick,
    Status { feed: u16, msg: String },
    /// `what`: what the evaluation was allowed to do (`engine::TIMER_*`; a record without it: everything)
    Timer { t: u64, what: u8 },
    Gap { first_lost_seq: u64, n_lost: u64 },
}

struct Cur<'a> { b: &'a [u8], p: usize }
impl<'a> Cur<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> { let x = self.b.get(self.p..self.p + n).context("truncated journal record")?; self.p += n; Ok(x) }
    fn arr<const N: usize>(&mut self) -> Result<[u8; N]> { Ok(self.take(N)?.try_into().unwrap()) }
    fn u8(&mut self) -> Result<u8> { Ok(self.take(1)?[0]) }
    fn u16(&mut self) -> Result<u16> { Ok(u16::from_le_bytes(self.arr()?)) }
    fn u32(&mut self) -> Result<u32> { Ok(u32::from_le_bytes(self.arr()?)) }
    fn u64(&mut self) -> Result<u64> { Ok(u64::from_le_bytes(self.arr()?)) }
    fn poh(&mut self) -> Result<Option<Poh>> {
        if self.p >= self.b.len() || self.u8()? == 0 { return Ok(None); }
        Ok(Some(Poh { slot: self.u64()?, hashes: self.u64()?, ticks: self.u32()?, hpt: self.u64()? }))
    }
    fn keys(&mut self) -> Result<Vec<Pk>> { let n = self.u16()? as usize; (0..n).map(|_| self.arr::<32>()).collect() }
}

fn body(kind: u8, b: &[u8]) -> Result<JBody> {
    let mut c = Cur { b, p: 0 };
    Ok(match kind {
        J_TX_FIRST => {
            let (feed, slot, t_rx, t_decoded) = (c.u16()?, c.u64()?, c.u64()?, c.u64()?);
            let executed = match c.u8()? as i8 { -1 => None, 0 => Some(false), _ => Some(true) };
            let enc = c.u8()?;
            let n = c.u32()? as usize;
            let bytes = c.take(n)?.to_vec();
            let loaded = if c.u8()? == 1 { Some((c.keys()?, c.keys()?)) } else { None };
            JBody::TxFirst { feed, slot, t_rx, t_decoded, executed, enc, bytes, loaded, poh: c.poh()? }
        }
        J_TX_COPY => JBody::TxCopy { sig: c.arr()?, feed: c.u16()?, t_rx: c.u64()?, poh: c.poh()? },
        J_ACCOUNT => JBody::Account { aseq: c.u64()?, stale: c.u8()? != 0 },
        J_SLOT => { let slot = c.u64()?; let p = c.u64()?; JBody::Slot { slot, parent: (p != u64::MAX).then_some(p), status: c.u32()? as i32, t: c.u64()? } }
        J_BLOCK_META => {
            let (slot, blockhash) = (c.u64()?, c.arr()?);
            let h = c.u64()?;
            JBody::BlockMeta { slot, blockhash, height: (h != u64::MAX).then_some(h), parent_slot: c.u64()?, t: c.u64()? }
        }
        J_ALT => { let table = c.arr()?; let found = c.u8()? != 0; let a = c.keys()?; JBody::Alt { table, addrs: found.then_some(a) } }
        J_INPUT => { let k = c.u8()?; let n = c.u32()? as usize; JBody::Input { kind: k, data: serde_json::from_slice(c.take(n)?).unwrap_or(serde_json::Value::Null) } }
        J_TICK => JBody::Tick,
        J_STATUS => { let feed = c.u16()?; JBody::Status { feed, msg: String::from_utf8_lossy(&b[2.min(b.len())..]).into_owned() } }
        J_TIMER => JBody::Timer { t: c.u64()?, what: if c.p < b.len() { c.u8()? } else { crate::engine::TIMER_ALL } },
        J_GAP => JBody::Gap { first_lost_seq: c.u64()?, n_lost: c.u64()? },
        k => bail!("unknown journal record kind {k}"),
    })
}

/// Read one journal.bin file (decompressed): its header and records
pub fn parse(b: &[u8]) -> Result<(serde_json::Value, Vec<JRec>)> {
    if b.get(..8) != Some(&super::JOURNAL_MAGIC[..]) { bail!("not a journal.bin file"); }
    let fmt = u16::from_le_bytes([b[8], b[9]]);
    if fmt != 2 { bail!("journal.bin format {fmt}"); }
    let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
    let header = serde_json::from_slice(b.get(12..12 + hlen).context("header")?)?;
    let mut p = 12 + hlen;
    let mut out = Vec::new();
    while p < b.len() {
        let h = b.get(p..p + 21).context("truncated journal header")?;
        let kind = h[0];
        let n = u32::from_le_bytes(h[1..5].try_into().unwrap()) as usize;
        let seq = u64::from_le_bytes(h[5..13].try_into().unwrap());
        let t_engine = u64::from_le_bytes(h[13..21].try_into().unwrap());
        p += 21;
        let bb = b.get(p..p + n).context("truncated journal body")?;
        p += n;
        out.push(JRec { seq, t_engine, body: body(kind, bb).with_context(|| format!("journal seq {seq}"))? });
    }
    Ok((header, out))
}

/// Every journal.bin file of a run directory, in order
pub fn read_dir(dir: &std::path::Path) -> Result<Vec<JRec>> {
    let mut all = Vec::new();
    for b in super::read_files(dir, "journal")? { all.extend(parse(&b)?.1); }
    Ok(all)
}

// ------------------------------------------------------------------ replay

/// The event an account record was, as the feed handed it to the engine
pub fn account_event(r: &AcctRecord) -> Event {
    Event::Account { slot: r.slot, pubkey: r.pubkey, owner: r.owner, lamports: r.lamports, data: Arc::from(&r.data[..]), t: r.t_recv, txn: r.txn,
        write_version: r.write_version, is_startup: r.is_startup, src: r.src, aseq: r.aseq }
}

/// The arrival a TX_FIRST record was (its transaction decoded from the journaled bytes)
pub fn arrival(feed: u16, slot: u64, t_rx: u64, t_decoded: u64, executed: Option<bool>, enc: u8, bytes: &[u8], loaded: &Option<(Vec<Pk>, Vec<Pk>)>,
    poh: Option<Poh>) -> Result<Arrival> {
    let (tx, raw) = match enc {
        ENC_WIRE => {
            let (mut tx, _) = crate::tx::parse_wire(bytes).context("TX_FIRST: undecodable wire bytes")?;
            if loaded.is_some() { tx.loaded = loaded.clone(); }
            (tx, RawTx::Wire(Arc::from(bytes)))
        }
        ENC_PB => {
            let pb = grpc::PbTransaction::decode(bytes).context("TX_FIRST: undecodable protobuf transaction")?;
            let sig = pb.signatures.first().cloned().unwrap_or_default();
            let (lw, lr): (Vec<Vec<u8>>, Vec<Vec<u8>>) = match loaded { Some((w, r)) => (w.iter().map(|k| k.to_vec()).collect(), r.iter().map(|k| k.to_vec()).collect()), None => (vec![], vec![]) };
            let tx = grpc::tx_from_pb(&sig, false, &pb, &lw, &lr).context("TX_FIRST: protobuf transaction without a message")?;
            (tx, RawTx::Pb(Arc::new(pb)))
        }
        e => bail!("TX_FIRST: unknown enc {e}"),
    };
    Ok(Arrival { feed, slot, t_rx, t_decoded, executed, tx, poh, raw })
}

/// A record of the boot section: the leading records written before the engine's first input, with `t_engine_ns` 0
/// (the boot snapshot's ACCOUNT records and the engine_init record). A GAP record carries the writer's clock instead
/// (review WP-03 N4): one among them does not end the section
fn boot_rec(r: &JRec) -> bool { r.t_engine == 0 || matches!(r.body, JBody::Gap { .. }) }

/// The boot snapshot (ACCOUNT records journaled with `t_engine_ns` 0, before the first engine input) applied to a
/// store as `arbx run` applies it, with the DLMM arrays it then follows
pub fn boot_store(journal: &[JRec], accounts: &HashMap<u64, AcctRecord>, reg: &crate::pools::Registry) -> crate::store::Store {
    let mut store = crate::store::Store::default();
    for r in journal.iter().take_while(|r| boot_rec(r)) {
        if let JBody::Account { aseq, .. } = r.body {
            if let Some(a) = accounts.get(&aseq) { store.update(a.pubkey, Arc::from(&a.data[..]), a.slot, a.t_recv, a.txn); }
        }
    }
    crate::engine::initial_dlmm_arrays(reg, &mut store);
    store
}

/// The run's engine_init record (INPUT 10 in the boot section; review WP-03 #2): None for a journal not written by
/// `Engine::run` (or one whose record was lost)
pub fn engine_init(journal: &[JRec]) -> Option<crate::engine::EngineInit> {
    journal.iter().take_while(|r| boot_rec(r)).find_map(|r| match &r.body {
        JBody::Input { kind, data } if *kind == InputKind::EngineInit as u8 => crate::engine::EngineInit::from_json(data),
        _ => None,
    })
}

/// The engine a replay starts from (the path WP-04 / WP-09 replays take): the boot snapshot applied to a store
/// (`boot_store`), an offline engine on `cfg` (the run's `[strategy]`, checked against the record's hash), and the
/// run's engine_init record applied (its `min_tip` and signer statistics). An error when the journal has no
/// engine_init record or `cfg` is not the run's
pub fn replay_engine(reg: Arc<crate::pools::Registry>, cfg: crate::config::StrategyCfg, journal: &[JRec], accounts: &HashMap<u64, AcctRecord>)
    -> Result<(crate::engine::Engine, crate::engine::EngineInit)> {
    let init = engine_init(journal).context("the journal has no engine_init record (INPUT 10): it was not written by `Engine::run` of WP-03 or later")?;
    let mut e = crate::engine::Engine::new_offline(reg.clone(), boot_store(journal, accounts, &reg), cfg);
    e.apply_init(&init)?;
    Ok((e, init))
}

/// What a replay did
#[derive(Debug, Default, Clone, PartialEq)]
pub struct ReplayStats {
    pub events: u64,
    pub timers: u64,
    /// account records the journal names but accounts.bin does not hold (a gap)
    pub missing_accounts: u64,
    /// ACCOUNT records whose journaled verdict differs from the replayed store's
    pub verdict_mismatches: u64,
    /// journal gaps (replay refuses to compare decisions inside them)
    pub gaps: Vec<(u64, u64)>,
    /// INPUT records not fed to the engine: settlements (the executor's, WP-05 / WP-09) and unknown kinds
    pub skipped: u64,
    /// decision-point gate records (`src` "decision"): what the run's send checks saw, for a replay with an executor
    pub gate_observed: u64,
}

/// Feed a journal (after its boot records) into `eng` exactly as the run handed it its inputs: each record's event
/// with its `t_engine_ns`, each TIMER at its time
pub fn replay(eng: &mut crate::engine::Engine, journal: &[JRec], accounts: &HashMap<u64, AcctRecord>) -> Result<ReplayStats> {
    let mut st = ReplayStats::default();
    let mut status = |_: &str| {};
    let mut boot = true;
    for r in journal {
        if let JBody::Gap { first_lost_seq, n_lost } = r.body { st.gaps.push((first_lost_seq, n_lost)); continue; }
        // the boot section is applied by `boot_store` / `replay_engine`
        if boot && r.t_engine == 0 { continue; }
        boot = false;
        let t = r.t_engine;
        let ev = match &r.body {
            JBody::TxFirst { feed, slot, t_rx, t_decoded, executed, enc, bytes, loaded, poh } =>
                Event::Tx(arrival(*feed, *slot, *t_rx, *t_decoded, *executed, *enc, bytes, loaded, *poh)?),
            JBody::TxCopy { sig, feed, t_rx, poh } => {
                let tx = crate::tx::Tx { sig: *sig, ..Default::default() };
                Event::Tx(Arrival { feed: *feed, slot: 0, t_rx: *t_rx, t_decoded: *t_rx, executed: None, tx, poh: *poh, raw: RawTx::None })
            }
            JBody::Account { aseq, stale } => match accounts.get(aseq) {
                Some(a) => {
                    if eng.store.is_stale(&a.pubkey, a.slot) != *stale { st.verdict_mismatches += 1; }
                    account_event(a)
                }
                None => { st.missing_accounts += 1; continue; }
            },
            JBody::Slot { slot, parent, status, t } => Event::Slot { slot: *slot, status: *status, t: *t, parent: *parent, dead_error: None },
            JBody::BlockMeta { slot, blockhash, height, parent_slot, t } => Event::BlockMeta(grpc::BlockMeta { slot: *slot, blockhash: *blockhash,
                parent_slot: *parent_slot, parent_blockhash: [0; 32], block_height: *height, block_time: None, executed_transaction_count: 0, entries_count: 0, t: *t,
                bank_id: None }),
            JBody::Alt { table, addrs } => Event::Alt { table: *table, addrs: addrs.clone().map(Arc::new) },
            JBody::Input { kind, data } => match InputKind::from_u8(*kind) {
                // a settlement belongs to the executor, which an offline engine does not have (WP-05 / WP-09 replay it);
                // engine_init belongs to the boot section
                Some(InputKind::Settled) | Some(InputKind::EngineInit) | None => { st.skipped += 1; continue; }
                // what a send check saw, journaled by the engine while handling the input before it: not an input
                Some(InputKind::Gate) if data["src"].as_str() == Some("decision") => { st.gate_observed += 1; continue; }
                Some(k) => Event::Input { kind: k, data: Arc::new(data.clone()) },
            },
            JBody::Timer { t, what } => { eng.timers_at(*t, *what, &mut status); st.timers += 1; continue; }
            JBody::Gap { .. } => continue,
            JBody::Tick | JBody::Status { .. } => continue,
        };
        eng.step(ev, t, &mut status);
        st.events += 1;
    }
    Ok(st)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::StrategyCfg;
    use crate::engine::Engine;
    use crate::feeds::src;
    use crate::pools::{pair_key, Registry};
    use crate::rec::accounts::{self, AcctRec, AcctUpdate, Roles};
    use crate::store::Store;
    use crate::tx::Tx;
    use crate::venues::{PoolMeta, Venue, WSOL};

    const MINT: Pk = [7u8; 32];
    const T0: u64 = 1_791_000_000_000_000_000;

    fn ammv4_pool() -> Vec<u8> {
        let mut p = vec![0u8; 752];
        p[0..8].copy_from_slice(&1u64.to_le_bytes());
        p[176..184].copy_from_slice(&25u64.to_le_bytes());
        p[184..192].copy_from_slice(&10_000u64.to_le_bytes());
        p
    }
    fn vault(amount: u64) -> Vec<u8> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v }
    fn meta(n: u8) -> PoolMeta {
        PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
    }
    fn registry() -> Arc<Registry> {
        let (a, b) = (meta(1), meta(2));
        let mut reg = Registry { pools: vec![a.clone(), b.clone()], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        reg.by_pool.insert(a.pool, 0);
        reg.by_pool.insert(b.pool, 1);
        reg.pairs.insert(pair_key(&MINT, &WSOL), vec![0, 1]);
        Arc::new(reg)
    }
    /// a transaction by a signer touching `pool` (no venue instruction: not a decoded swap), with its wire bytes
    fn tx(sig: u8, pool: Pk) -> (Tx, Arc<[u8]>) {
        let t = Tx { sig: [sig; 64], num_signers: 1, num_ro_signed: 0, num_ro_unsigned: 1, keys: vec![[0x52; 32], pool, [0x53; 32]],
            ixs: vec![crate::tx::Ix { program: 2, accounts: vec![0, 1], data: vec![1, 2, 3] }], ..Default::default() };
        let w = crate::tx::to_wire(&t).unwrap();
        (crate::tx::parse_wire(&w).unwrap().0, Arc::from(&w[..]))
    }

    /// PLAN WP-03 acceptance, journal determinism: a run's inputs (account updates with their aseq, transactions and
    /// their later copies, stale updates, slots, a lookup table, an input, timers; state triggers that open
    /// opportunities) are journaled; the same journal fed twice into `Engine::new_offline` gives the same state digest
    /// and the same decisions, and both equal the run's own
    #[test]
    fn a_journal_replays_deterministically() {
        let d = std::env::temp_dir().join(format!("arbx-journal-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec!["a".into(), "b".into()],
            monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap();
        let reg = registry();
        let acct = AcctRec::new(rec.clone(), Arc::new(Roles::new(reg.watch_roles())));
        let cfg = StrategyCfg { state_triggers: true, budget_caps_sol: vec![0.5, 2.0], ..StrategyCfg::default() };
        let rec_acct = |key: Pk, data: &Arc<[u8]>, slot: u64, t: u64, txn: Option<[u8; 64]>, src: u8| -> u64 {
            acct.record(&AcctUpdate { pubkey: key, slot, write_version: if src == 0 { t } else { 0 }, t_recv: t, src, is_startup: false, txn, lamports: 1, owner: [3; 32], data })
        };
        // the boot snapshot, as `arbx run` takes it (accounts.bin src rpc_boot; ACCOUNT records with t_engine 0)
        let boot_j = Journal::new(rec.clone());
        let mut store = Store::default();
        for (n, sol) in [(1u8, 1_000u64), (2, 1_010)] {
            let m = meta(n);
            for (k, data) in [(m.pool, ammv4_pool()), (m.vault0, vault(1_000_000_000_000_000)), (m.vault1, vault(sol * 1_000_000_000))] {
                let data: Arc<[u8]> = data.into();
                let aseq = rec_acct(k, &data, 10, T0, None, src::RPC_BOOT);
                boot_j.account(0, aseq, store.is_stale(&k, 10));
                store.update(k, data, 10, T0, None);
            }
        }
        crate::engine::initial_dlmm_arrays(&reg, &mut store);
        let mut e = Engine::new_offline(reg.clone(), store, cfg.clone());
        e.set_rec(rec.clone());
        // what `run` journals first (min_tip, signer statistics, the strategy's hash)
        e.journal_init();
        let mut status = |_: &str| {};
        let mut t = T0 + 1_000_000;
        let mut tick = || { t += 1_000_003; t };
        for n in 0..60u64 {
            let m = meta(1 + (n % 2) as u8);
            let s = [n as u8 + 100; 64];
            let slot = 11 + n / 4;
            // a gap every 5th transaction: the moved pool 3% off its pair
            let sol = if n % 5 == 0 { 1_030 + n } else { 1_000 + n % 7 };
            for (k, data) in [(m.vault1, vault(sol * 1_000_000_000)), (m.vault0, vault(999_000_000_000_000 - n * 1_000_000_000))] {
                let data: Arc<[u8]> = data.into();
                let tt = tick();
                let aseq = rec_acct(k, &data, slot, tt, Some(s), src::GRPC);
                let te = tick();
                e.step(Event::Account { slot, pubkey: k, owner: [3; 32], lamports: 1, data, t: tt, txn: Some(s), write_version: tt, is_startup: false, src: src::GRPC, aseq },
                    te, &mut status);
            }
            // the transaction itself from a shred feed (its bytes; every 7th without them), and a later copy from another
            let (x, raw) = tx(n as u8 + 100, m.pool);
            let raw = if n % 7 == 3 { RawTx::None } else { RawTx::Wire(raw) };
            let tr = tick();
            let te = tick();
            e.step(Event::Tx(Arrival { feed: 0, slot, t_rx: tr, t_decoded: tr + 10, executed: None, tx: x.clone(), poh: None, raw }), te, &mut status);
            let (tr, te) = (tick(), tick());
            e.step(Event::Tx(Arrival { feed: 1, slot, t_rx: tr, t_decoded: 0, executed: Some(true), tx: x, poh: None, raw: RawTx::None }), te, &mut status);
            if n % 10 == 9 {
                // a late update from an older slot (stale), slot statuses, an input, a lookup table
                let data: Arc<[u8]> = vault(5).into();
                let tt = tick();
                let aseq = rec_acct(m.vault0, &data, 1, tt, None, src::GRPC);
                let te = tick();
                e.step(Event::Account { slot: 1, pubkey: m.vault0, owner: [3; 32], lamports: 1, data, t: tt, txn: None, write_version: tt, is_startup: false, src: src::GRPC, aseq },
                    te, &mut status);
                for st in [0, 3, 1] { let (a, b) = (tick(), tick()); e.step(Event::Slot { slot, status: st, t: a, parent: Some(slot - 1), dead_error: None }, b, &mut status); }
                let te = tick();
                e.step(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(serde_json::json!({ "start": slot, "leaders": [] })) }, te, &mut status);
                let te = tick();
                e.step(Event::Alt { table: [n as u8; 32], addrs: Some(Arc::new(vec![[1; 32], [2; 32]])) }, te, &mut status);
            }
            // the queue empties: the timers flush the state triggers
            let te = tick();
            e.timers(te, &mut status);
        }
        // the watch windows end, and housekeeping's status line
        let te = tick() + 20_000_000_000;
        e.timers(te, &mut status);
        let (digest, decisions) = (e.digest(), e.decision_digest());
        assert_ne!(decisions, 0, "the run opened opportunities");
        rec.close();
        // moves.log carries the updates' write versions now (WP-03)
        let mv = crate::rec::read_text(&d, "moves").unwrap();
        assert_eq!(mv.len(), 60, "one line per (transaction, pool)");
        assert!(mv.iter().all(|l| l.split(' ').nth(5).is_some_and(|w| w.parse::<u64>().is_ok_and(|w| w > T0))), "{}", mv[0]);
        let j = read_dir(&d).unwrap();
        let a = accounts::read_dir(&d).unwrap();
        assert!(a.gaps.is_empty());
        let by: HashMap<u64, AcctRecord> = a.records.into_iter().map(|r| (r.aseq, r)).collect();
        assert_eq!(j.iter().take_while(|r| r.t_engine == 0).count(), 7, "the boot snapshot and engine_init");
        assert!(j.iter().any(|r| matches!(r.body, JBody::TxCopy { .. })) && j.iter().any(|r| matches!(r.body, JBody::Alt { .. })));
        let mut seen = Vec::new();
        for _ in 0..2 {
            let (mut r, init) = replay_engine(reg.clone(), cfg.clone(), &j, &by).unwrap();
            assert_eq!((init.min_tip, init.executor), (0, false));
            let st = replay(&mut r, &j, &by).unwrap();
            assert_eq!((st.missing_accounts, st.verdict_mismatches, st.gaps.len()), (0, 0, 0), "{st:?}");
            assert_eq!(st.timers, 61);
            seen.push((r.digest(), r.decision_digest()));
        }
        assert_eq!(seen[0], seen[1], "the same journal twice: the same state and decisions");
        assert_eq!(seen[0], (digest, decisions), "and the run's own");
        let _ = std::fs::remove_dir_all(&d);
    }

    /// the digest sees one input more or less (a journal missing an input would not replay to the run's state)
    #[test]
    fn the_digest_sees_a_missing_input() {
        let reg = registry();
        let mk = || {
            let mut s = Store::default();
            for (n, sol) in [(1u8, 1_000u64), (2, 1_010)] {
                let m = meta(n);
                s.update(m.pool, ammv4_pool().into(), 10, 1, None);
                s.update(m.vault0, vault(1_000_000_000_000_000).into(), 10, 1, None);
                s.update(m.vault1, vault(sol * 1_000_000_000).into(), 10, 1, None);
            }
            Engine::new_offline(reg.clone(), s, StrategyCfg { state_triggers: true, ..StrategyCfg::default() })
        };
        let (mut a, mut b) = (mk(), mk());
        let mut status = |_: &str| {};
        assert_eq!(a.digest(), b.digest());
        let m = meta(2);
        let ev = || Event::Account { slot: 11, pubkey: m.vault1, owner: [3; 32], lamports: 1, data: vault(1_030_000_000_000).into(), t: 5, txn: Some([9; 64]),
            write_version: 1, is_startup: false, src: 0, aseq: 0 };
        a.step(ev(), T0, &mut status);
        assert_ne!(a.digest(), b.digest());
        b.step(ev(), T0, &mut status);
        assert_eq!(a.digest(), b.digest());
    }

    /// review WP-03 #2 (regression): a journal written by the real `Engine::run` replays to the run. The engine is built
    /// as `arbx run` builds it (`Engine::new`): `min_tip` 1,000 (stage 0's jito-bundle tip), a signer statistics file,
    /// state triggers, and a DLMM pool whose active bin leaves its held arrays before the first timer (the reviewer's
    /// case: the run's 2 s drift check is not due within its 0.6 s, a replay whose timer anchors start at 0 ran it at its
    /// first TIMER). The other inputs arrive through the channel while it runs. Its journal, replayed through
    /// `replay_engine`, gives the run's state digest, decision digest and DLMM arrays; a plain `new_offline` (no
    /// engine_init: min_tip 0, no statistics) does not
    #[test]
    fn a_journal_written_by_run_replays_to_the_run() {
        let d = std::env::temp_dir().join(format!("arbx-journal-run-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec!["a".into(), "b".into()],
            monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap();
        let dl = PoolMeta { venue: Venue::Dlmm, pool: [5; 32], t0: [8; 32], t1: *WSOL, vault0: [6; 32], vault1: [9; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![[4; 32]], flag: false };
        let mut reg = Arc::try_unwrap(registry()).ok().unwrap();
        reg.pools.push(dl.clone());
        reg.by_pool.insert(dl.pool, 2);
        let reg = Arc::new(reg);
        let acct = AcctRec::new(rec.clone(), Arc::new(Roles::new(reg.watch_roles())));
        let dlmm_pool = |active: i32| -> Arc<[u8]> { let mut p = vec![0u8; 904]; p[76..80].copy_from_slice(&active.to_le_bytes()); p.into() };
        let t0 = crate::feeds::clock::now_ns();
        // the boot snapshot (accounts.bin src rpc_boot; ACCOUNT records with t_engine 0)
        let boot_j = Journal::new(rec.clone());
        let mut store = Store::default();
        let mut boot: Vec<(Pk, Arc<[u8]>)> = vec![(dl.pool, dlmm_pool(0))];
        for (n, sol) in [(1u8, 1_000u64), (2, 1_010)] {
            let m = meta(n);
            boot.extend([(m.pool, ammv4_pool().into()), (m.vault0, vault(1_000_000_000_000_000).into()), (m.vault1, vault(sol * 1_000_000_000).into())]);
        }
        for (k, data) in boot {
            let aseq = acct.record(&AcctUpdate { pubkey: k, slot: 10, write_version: 0, t_recv: t0, src: src::RPC_BOOT, is_startup: false, txn: None, lamports: 1, owner: [3; 32], data: &data });
            boot_j.account(0, aseq, store.is_stale(&k, 10));
            store.update(k, data, 10, t0, None);
        }
        crate::engine::initial_dlmm_arrays(&reg, &mut store);
        let held0 = store.dlmm_arrays[&dl.pool].clone();
        // the cross-run statistics file as the run finds it
        const SIGNER: Pk = [0x52; 32];
        let stats = d.join("signer-stats.json");
        std::fs::write(&stats, serde_json::json!({ crate::tx::b58(&SIGNER): [1, 9], crate::tx::b58(&[0x61; 32]): [5, 0] }).to_string()).unwrap();
        let cfg = StrategyCfg { state_triggers: true, budget_caps_sol: vec![0.5, 2.0], signer_stats_file: stats.display().to_string(), ..StrategyCfg::default() };
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        let (tx_ch, rx) = crossbeam_channel::unbounded();
        let (wtx, _wrx) = tokio::sync::watch::channel(Vec::new());
        let mut e = Engine::new(reg.clone(), store, cfg.clone(), vec!["a".into(), "b".into()], 1_000, Arc::new(crate::feeds::Interest::default()), rec.clone(),
            crate::rpc::Rpc::race(vec![]), rt.handle().clone(), tx_ch.clone(), wtx).unwrap();
        e.set_acct_rec(acct.clone());
        // queued before the engine starts (as the state stream's updates queue during the boot): the DLMM pool's active
        // bin moves far out of its held arrays
        {
            let data = dlmm_pool(100_000);
            let t = crate::feeds::clock::now_ns();
            let aseq = acct.record(&AcctUpdate { pubkey: dl.pool, slot: 11, write_version: t, t_recv: t, src: src::GRPC, is_startup: false, txn: Some([1; 64]), lamports: 1, owner: [3; 32], data: &data });
            tx_ch.send(Event::Account { slot: 11, pubkey: dl.pool, owner: [3; 32], lamports: 1, data, t, txn: Some([1; 64]), write_version: t, is_startup: false, src: src::GRPC, aseq }).unwrap();
        }
        // the inputs, from another thread with pauses (the queue empties between transactions: the flushes run then)
        let mk_tx = tx;
        let feeder = {
            let (tx, acct) = (tx_ch.clone(), acct.clone());
            std::thread::spawn(move || {
                let send = |key: Pk, data: Arc<[u8]>, slot: u64, txn: Option<[u8; 64]>| {
                    let t = crate::feeds::clock::now_ns();
                    let aseq = acct.record(&AcctUpdate { pubkey: key, slot, write_version: t, t_recv: t, src: src::GRPC, is_startup: false, txn, lamports: 1, owner: [3; 32], data: &data });
                    tx.send(Event::Account { slot, pubkey: key, owner: [3; 32], lamports: 1, data, t, txn, write_version: t, is_startup: false, src: src::GRPC, aseq }).unwrap();
                };
                for n in 0..40u64 {
                    let m = meta(1 + (n % 2) as u8);
                    let s = [n as u8 + 100; 64];
                    let slot = 12 + n / 4;
                    let sol = if n % 5 == 0 { 1_030 + n } else { 1_000 + n % 7 };
                    send(m.vault1, vault(sol * 1_000_000_000).into(), slot, Some(s));
                    send(m.vault0, vault(999_000_000_000_000 - n * 1_000_000_000).into(), slot, Some(s));
                    let (x, raw) = mk_tx(n as u8 + 100, m.pool);
                    let t = crate::feeds::clock::now_ns();
                    tx.send(Event::Tx(Arrival { feed: 0, slot, t_rx: t, t_decoded: t, executed: None, tx: x, poh: None, raw: RawTx::Wire(raw) })).unwrap();
                    tx.send(Event::Slot { slot, status: 0, t, parent: Some(slot - 1), dead_error: None }).unwrap();
                    if n % 10 == 9 { tx.send(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(serde_json::json!({ "start": slot, "leaders": [] })) }).unwrap(); }
                    std::thread::sleep(std::time::Duration::from_millis(3));
                }
            })
        };
        let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let s2 = stop.clone();
        std::thread::spawn(move || { std::thread::sleep(std::time::Duration::from_millis(600)); s2.store(true, std::sync::atomic::Ordering::Relaxed); });
        let end = e.run(&rx, &stop, u64::MAX, |_| {});
        assert_eq!(end, crate::engine::RunEnd::Stopped);
        feeder.join().unwrap();
        let live = (e.digest(), e.decision_digest(), e.store.dlmm_arrays[&dl.pool].clone());
        assert_eq!(live.2, held0, "no drift check within 2 s of the run's first input");
        assert_ne!(live.1, 0, "the run opened opportunities");
        rec.close();
        let j = read_dir(&d).unwrap();
        let a = accounts::read_dir(&d).unwrap();
        let by: HashMap<u64, AcctRecord> = a.records.into_iter().map(|r| (r.aseq, r)).collect();
        // the timers' journaled scopes: idle evaluations do everything, after-input ones only flush
        let whats: std::collections::BTreeSet<u8> = j.iter().filter_map(|r| match r.body { JBody::Timer { what, .. } => Some(what), _ => None }).collect();
        assert!(whats.contains(&crate::engine::TIMER_ALL) && whats.contains(&crate::engine::TIMER_FLUSH), "{whats:?}");
        let (mut r, init) = replay_engine(reg.clone(), cfg.clone(), &j, &by).unwrap();
        assert_eq!((init.min_tip, init.executor, init.signer_stats.get(&SIGNER).copied(), init.signer_stats.len()), (1_000, false, Some((1, 9)), 2));
        let st = replay(&mut r, &j, &by).unwrap();
        assert_eq!((st.missing_accounts, st.verdict_mismatches, st.gaps.len()), (0, 0, 0), "{st:?}");
        r.finish();
        assert_eq!((r.digest(), r.decision_digest(), r.store.dlmm_arrays[&dl.pool].clone()), live, "run vs replay");
        // the engine_init record is what makes it so: without it (min_tip 0, no statistics) the replay differs
        let mut plain = Engine::new_offline(reg.clone(), boot_store(&j, &by, &reg), cfg.clone());
        replay(&mut plain, &j, &by).unwrap();
        plain.finish();
        assert_ne!(plain.decision_digest(), live.1, "min_tip is in every opportunity's net");
        assert_ne!(plain.digest(), live.0, "and the signer statistics in the state");
        // and a replay on another [strategy] is refused
        let other = StrategyCfg { min_profit_lamports: cfg.min_profit_lamports + 1, ..cfg.clone() };
        assert!(replay_engine(reg.clone(), other, &j, &by).err().unwrap().to_string().contains("[strategy]"));
        // the statistics file was neither read nor rewritten by the replays: the run's own finish wrote it
        let _ = std::fs::remove_dir_all(&d);
    }

    /// review WP-03 #7b: a burst that keeps the queue non-empty is handled with no timer evaluation in between: no
    /// state flush prices a transaction whose other updates are still queued, and no housekeeping delays the next input
    #[test]
    fn a_burst_runs_no_timer_until_the_queue_empties() {
        let d = std::env::temp_dir().join(format!("arbx-journal-burst-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![],
            monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap();
        let reg = registry();
        let mut store = Store::default();
        for (n, sol) in [(1u8, 1_000u64), (2, 1_010)] {
            let m = meta(n);
            store.update(m.pool, ammv4_pool().into(), 10, 1, None);
            store.update(m.vault0, vault(1_000_000_000_000_000).into(), 10, 1, None);
            store.update(m.vault1, vault(sol * 1_000_000_000).into(), 10, 1, None);
        }
        let mut e = Engine::new_offline(reg, store, StrategyCfg { state_triggers: true, ..StrategyCfg::default() });
        e.set_rec(rec.clone());
        let (tx, rx) = crossbeam_channel::unbounded();
        for n in 0..3_000u64 {
            let m = meta(1 + (n % 2) as u8);
            let s = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&(n + 1).to_le_bytes()); s };
            for (k, data) in [(m.vault1, vault((1_000 + n % 40) * 1_000_000_000)), (m.vault0, vault(1_000_000_000_000_000 - n))] {
                tx.send(Event::Account { slot: 11, pubkey: k, owner: [3; 32], lamports: 1, data: data.into(), t: n, txn: Some(s), write_version: n, is_startup: false, src: 0, aseq: n }).unwrap();
            }
        }
        drop(tx);
        let stop = std::sync::atomic::AtomicBool::new(false);
        assert_eq!(e.run(&rx, &stop, u64::MAX, |_| {}), crate::engine::RunEnd::Disconnected);
        rec.close();
        let j = read_dir(&d).unwrap();
        let last_input = j.iter().rposition(|r| matches!(r.body, JBody::Account { .. })).unwrap();
        assert_eq!(j.iter().filter(|r| matches!(r.body, JBody::Account { .. })).count(), 6_000);
        let timers: Vec<usize> = j.iter().enumerate().filter(|(_, r)| matches!(r.body, JBody::Timer { .. })).map(|(i, _)| i).collect();
        assert!(timers.iter().all(|i| *i > last_input), "a timer at {:?} before the last input {last_input}", timers.first());
        let _ = std::fs::remove_dir_all(&d);
    }

    /// review WP-03 N4: a GAP among the boot records (it carries the writer's clock, not 0) does not end the boot section
    #[test]
    fn a_gap_among_the_boot_records_keeps_the_boot_section() {
        let rec_at = |seq: u64, t: u64, body: JBody| JRec { seq, t_engine: t, body };
        let init = crate::engine::EngineInit { min_tip: 7, strategy_sha256: "x".into(), ..Default::default() };
        let j = vec![rec_at(0, 0, JBody::Account { aseq: 0, stale: false }), rec_at(3, 1_791_000_000_000_000_000, JBody::Gap { first_lost_seq: 1, n_lost: 2 }),
            rec_at(4, 0, JBody::Input { kind: InputKind::EngineInit as u8, data: init.json() }), rec_at(5, 5, JBody::Timer { t: 5, what: crate::engine::TIMER_ALL })];
        assert_eq!(engine_init(&j).map(|i| i.min_tip), Some(7));
        let reg = registry();
        let mut e = Engine::new_offline(reg.clone(), Store::default(), StrategyCfg::default());
        let st = replay(&mut e, &j, &HashMap::default()).unwrap();
        assert_eq!((st.events, st.timers, st.skipped, st.gaps.clone()), (0, 1, 0, vec![(1, 2)]), "the boot records are not replayed as events; the gap is reported");
    }
}
