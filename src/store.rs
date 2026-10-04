//! Account store: the latest bytes of every followed account (pools, vaults, configs, mints, DLMM bin arrays),
//! updated by the state stream, plus the per-pool snapshot builders the engine quotes against.
use crate::pools::{Registry, PUMP_FEE_CONFIG};
use crate::tx::Pk;
use crate::venues::{cp, dlmm, i32_at, PoolMeta, Venue};
use rustc_hash::FxHashMap as HashMap;
use std::sync::Arc;

/// An account's latest bytes. `data` is shared with the recorder's accounts.bin record of the same update (WP-03: one
/// allocation per update, never copied on the engine thread)
pub struct Acct { pub data: Arc<[u8]>, pub slot: u64, pub t: u64, pub txn: Option<[u8; 64]> }

#[derive(Default)]
pub struct Store {
    pub accts: HashMap<Pk, Acct>,
    pub pump_cfg: Option<Arc<cp::PumpFeeCfg>>,
    /// DLMM pool -> bin array index -> array account (the arrays we follow)
    pub dlmm_arrays: HashMap<Pk, Vec<(i64, Pk)>>,
    pub updates: u64,
    pub stale_dropped: u64,
}

pub enum Snap<'a> {
    Cp(cp::CpSnap),
    Dlmm { pair: &'a [u8], arrays: HashMap<i64, &'a [u8]>, slot: u64 },
    /// DAMM v2: everything is in the pool account (price, liquidity, the whole fee schedule)
    Damm(crate::venues::dammv2::DammPool, u64),
}

impl Store {
    /// Apply an update; returns false if it is older than what we hold.
    pub fn update(&mut self, key: Pk, data: Arc<[u8]>, slot: u64, t: u64, txn: Option<[u8; 64]>) -> bool {
        if self.is_stale(&key, slot) { self.stale_dropped += 1; return false; }
        if key == *PUMP_FEE_CONFIG { self.pump_cfg = cp::decode_pump_fee_cfg(&data).map(Arc::new); }
        self.accts.insert(key, Acct { data, slot, t, txn });
        self.updates += 1;
        true
    }

    /// Whether `update` would refuse an update of `key` at `slot` (the journal's ACCOUNT verdict, WP-03; no change)
    pub fn is_stale(&self, key: &Pk, slot: u64) -> bool { self.accts.get(key).is_some_and(|a| a.slot > slot) }

    pub fn get(&self, k: &Pk) -> Option<&Acct> { self.accts.get(k) }

    /// Snapshot of a pool from the latest accounts. `Err` = why it can't be quoted.
    pub fn snapshot<'a>(&'a self, m: &PoolMeta, now_unix: i64) -> Result<Snap<'a>, &'static str> {
        let pool = self.accts.get(&m.pool).ok_or("no-pool-account")?;
        match m.venue {
            Venue::Dlmm => {
                let mut arrays = HashMap::default();
                if let Some(list) = self.dlmm_arrays.get(&m.pool) {
                    for (i, k) in list { if let Some(a) = self.accts.get(k) { arrays.insert(*i, &a.data[..]); } }
                }
                Ok(Snap::Dlmm { pair: &pool.data, arrays, slot: pool.slot })
            }
            Venue::DammV2 => crate::venues::dammv2::decode(&pool.data)
                .map(|mut p| { if m.flag { p.transfer_fee_known_zero = true; } Snap::Damm(p, pool.slot) }).ok_or("damm-undecodable"),
            _ => {
                let v0 = self.accts.get(&m.vault0).ok_or("no-vault0")?;
                let v1 = self.accts.get(&m.vault1).ok_or("no-vault1")?;
                let extra: Vec<&[u8]> = m.extra.iter().filter_map(|k| self.accts.get(k).map(|a| &a.data[..])).collect();
                if extra.len() != m.extra.len() { return Err("no-extra-account"); }
                // the snapshot's slot is the newest part's; parts more than 2 slots apart are not trusted together
                let (lo, hi) = (pool.slot.min(v0.slot).min(v1.slot), pool.slot.max(v0.slot).max(v1.slot));
                if hi - lo > 2 && m.venue != Venue::PumpSwap { return Err("parts-skewed"); }
                let a = cp::Accounts { pool: &pool.data, vault0: &v0.data, vault1: &v1.data, extra };
                cp::snapshot(m, &a, hi, now_unix, self.pump_cfg.as_ref()).map(Snap::Cp)
            }
        }
    }

    /// the DLMM pools whose active bin left the followed span; returns (pool, new array list) to re-follow
    pub fn dlmm_drift(&self, reg: &Registry) -> Vec<(Pk, Vec<(i64, Pk)>)> {
        let mut out = Vec::new();
        for m in reg.pools.iter().filter(|m| m.venue == Venue::Dlmm) {
            let Some(p) = self.accts.get(&m.pool) else { continue };
            let Some(active) = i32_at(&p.data, 76) else { continue };
            let c = dlmm::array_index(active);
            let held = self.dlmm_arrays.get(&m.pool);
            let ok = held.map_or(false, |l| l.iter().any(|(i, _)| *i == c - 1) && l.iter().any(|(i, _)| *i == c + 1));
            if !ok { out.push((m.pool, crate::pools::dlmm_arrays(&m.pool, active))); }
        }
        out
    }
}
