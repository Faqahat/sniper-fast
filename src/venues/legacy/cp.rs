//! LEGACY (tests only, see `legacy/mod.rs`): the engine's constant-product maths before WP-16. Raydium AMM v4,
//! Raydium CPMM, PumpSwap: snapshot from raw accounts, exact-in quote, post-trade reserves.
//!
//! Reserve and fee rules (per program):
//! - AMM v4: r = vault - need_take_pnl; fee = ceil(in*num/den) taken off the input; the whole input stays in the vault.
//! - CPMM: r = vault - (protocol + fund + creator fees owed); trade fee (and the creator fee when it is charged on the
//!   input) comes off the input; protocol/fund shares of the trade fee become "owed" (leave the effective reserve),
//!   the LP share stays. A creator fee charged on the output is skimmed from the gross output and stays owed.
//! - PumpSwap: r0 = base vault, r1 = quote vault, plus a virtual quote reserve in the price; fees by market-cap tier
//!   (fee config), each component rounded up separately; LP fee stays in the pool, protocol and creator fees leave.
use crate::venues::{ceil_div, i64_at, pk_at, token_amount, u64_at, PoolMeta, Venue};
use std::sync::Arc;

#[derive(Debug, Clone, Copy, Default)]
pub struct PumpFees { pub lp: u64, pub protocol: u64, pub creator: u64 }

#[derive(Debug, Clone, Default)]
pub struct PumpFeeCfg {
    pub flat: PumpFees,
    pub tiers: Vec<(u128, PumpFees)>,
    pub stable_tiers: Vec<(u128, PumpFees)>,
}

/// PumpSwap fee config account (pfeeUxB6… program, PDA ["fee_config", PumpSwap]): flat fees @41, then u32-length tier
/// vectors of {threshold u128, fees}, twice (SOL tiers, stable tiers).
pub fn decode_pump_fee_cfg(d: &[u8]) -> Option<PumpFeeCfg> {
    let mut o = 41usize;
    let fees = |o: &mut usize| -> Option<PumpFees> {
        let f = PumpFees { lp: u64_at(d, *o)?, protocol: u64_at(d, *o + 8)?, creator: u64_at(d, *o + 16)? };
        *o += 24;
        Some(f)
    };
    let tiers = |o: &mut usize| -> Option<Vec<(u128, PumpFees)>> {
        let n = crate::venues::u32_at(d, *o)? as usize;
        *o += 4;
        if n > 64 { return None; }
        let mut v = Vec::with_capacity(n);
        for _ in 0..n {
            let th = crate::venues::u128_at(d, *o)?;
            *o += 16;
            v.push((th, fees(o)?));
        }
        Some(v)
    };
    let flat = fees(&mut o)?;
    let t = tiers(&mut o)?;
    let st = tiers(&mut o)?;
    Some(PumpFeeCfg { flat, tiers: t, stable_tiers: st })
}

#[derive(Debug, Clone)]
pub enum Fee {
    AmmV4 { num: u128, den: u128 },
    /// rates in 1e6 units; `creator_on`: 0 both tokens (input), 1 only token0, 2 only token1
    Cpmm { trade: u128, protocol: u128, fund: u128, creator: u128, creator_on: u8 },
    Pump { cfg: Arc<PumpFeeCfg>, canonical: bool, creator_fee: bool, supply: u128 },
}

#[derive(Debug, Clone)]
pub struct CpSnap {
    pub venue: Venue,
    pub r0: u128,
    pub r1: u128,
    /// PumpSwap virtual quote reserve, added to the quote side of the price. SIGNED: some pools hold a negative value
    /// (2026-10-03: FFcYgSSg had -1,081,491; read as u64 it priced the token ~5e6x too dear, so every quote on it was wrong)
    pub virt: i128,
    pub fee: Fee,
    pub slot: u64,
}

impl CpSnap {
    /// the quote side of the price: the vault plus the (signed) virtual reserve, never below 1
    pub fn r1v(&self) -> u128 { (self.r1 as i128 + self.virt).max(1) as u128 }
}

pub struct Accounts<'a> { pub pool: &'a [u8], pub vault0: &'a [u8], pub vault1: &'a [u8], pub extra: Vec<&'a [u8]> }

/// Build a snapshot from raw accounts. `Err` explains why the pool can't be quoted right now.
pub fn snapshot(m: &PoolMeta, a: &Accounts, slot: u64, now_unix: i64, pump_cfg: Option<&Arc<PumpFeeCfg>>) -> Result<CpSnap, &'static str> {
    let v0 = token_amount(a.vault0).ok_or("vault0-short")? as u128;
    let v1 = token_amount(a.vault1).ok_or("vault1-short")? as u128;
    let p = a.pool;
    let sub = |x: u128, y: u128| x.saturating_sub(y);
    let snap = match m.venue {
        Venue::RayAmmV4 => {
            if p.len() < 752 { return Err("ammv4-short"); }
            let status = u64_at(p, 0).unwrap();
            if !matches!(status, 1 | 6 | 7) { return Err("ammv4-status"); }
            if status == 7 && i64_at(p, 224).unwrap() > now_unix { return Err("ammv4-not-open"); }
            let (num, den) = (u64_at(p, 176).unwrap() as u128, u64_at(p, 184).unwrap() as u128);
            if den == 0 || num >= den { return Err("ammv4-fee"); }
            CpSnap { venue: m.venue, r0: sub(v0, u64_at(p, 192).unwrap() as u128), r1: sub(v1, u64_at(p, 200).unwrap() as u128),
                virt: 0, fee: Fee::AmmV4 { num, den }, slot }
        }
        Venue::RayCpmm => {
            if p.len() < 413 { return Err("cpmm-short"); }
            if (p[329] >> 2) & 1 == 1 { return Err("cpmm-swap-disabled"); }
            let cfg = a.extra.first().ok_or("cpmm-no-config")?;
            if cfg.len() < 116 { return Err("cpmm-config-short"); }
            let enabled = p[390] == 1;
            let owed0 = u64_at(p, 341).unwrap() as u128 + u64_at(p, 357).unwrap() as u128 + u64_at(p, 397).unwrap() as u128;
            let owed1 = u64_at(p, 349).unwrap() as u128 + u64_at(p, 365).unwrap() as u128 + u64_at(p, 405).unwrap() as u128;
            CpSnap { venue: m.venue, r0: sub(v0, owed0), r1: sub(v1, owed1), virt: 0, slot, fee: Fee::Cpmm {
                trade: u64_at(cfg, 12).unwrap() as u128, protocol: u64_at(cfg, 20).unwrap() as u128, fund: u64_at(cfg, 28).unwrap() as u128,
                creator: if enabled { u64_at(cfg, 108).unwrap() as u128 } else { 0 }, creator_on: p[389] } }
        }
        Venue::PumpSwap => {
            if p.len() < 253 { return Err("pump-short"); }
            if p[243] == 1 { return Err("pump-mayhem"); }
            if p[244] == 1 { return Err("pump-cashback"); }
            if p.len() > 270 && p[270] == 1 { return Err("pump-holder-reward"); }
            if m.t1 != *crate::venues::WSOL { return Err("pump-quote-not-sol"); }
            let cfg = pump_cfg.ok_or("pump-no-fee-config")?;
            let mint = a.extra.first().ok_or("pump-no-mint")?;
            let supply = u64_at(mint, 36).ok_or("pump-mint-short")? as u128;
            let creator_fee = pk_at(p, 211).map_or(false, |k| k != [0u8; 32]);
            CpSnap { venue: m.venue, r0: v0, r1: v1, virt: i64_at(p, 245).unwrap() as i128, slot,
                fee: Fee::Pump { cfg: cfg.clone(), canonical: m.flag, creator_fee, supply } }
        }
        Venue::Dlmm | Venue::DammV2 => return Err("not-cp"),
    };
    if snap.r0 == 0 || snap.r1 == 0 { return Err("empty-reserves"); }
    Ok(snap)
}

/// PumpSwap fee components (bps) at the snapshot's market cap
fn pump_fees(s: &CpSnap) -> Option<(u128, u128, u128)> {
    let Fee::Pump { cfg, canonical, creator_fee, supply } = &s.fee else { return None };
    let f = if !canonical { cfg.flat } else {
        if cfg.tiers.is_empty() { return None; }
        let mc = s.r1v() * supply / s.r0.max(1);
        let mut f = cfg.tiers[0].1;
        for i in (1..cfg.tiers.len()).rev() { if mc >= cfg.tiers[i].0 { f = cfg.tiers[i].1; break; } }
        f
    };
    let c = if *creator_fee { f.creator as u128 } else { 0 };
    let total = f.lp as u128 + f.protocol as u128 + c;
    if total == 0 || total >= 1_000 { return None; }
    Some((f.lp as u128, f.protocol as u128, c))
}

#[derive(Debug, Clone, Copy)]
pub struct CpOut { pub out: u64, pub r0: u128, pub r1: u128 }

/// Exact-in quote and the effective reserves after the swap.
pub fn quote(s: &CpSnap, zero_for_one: bool, amount_in: u64) -> Option<CpOut> {
    if amount_in == 0 { return None; }
    let a = amount_in as u128;
    let (r_in, r_out) = if zero_for_one { (s.r0, s.r1) } else { (s.r1, s.r0) };
    let (out, d_in, d_out) = match &s.fee {
        Fee::AmmV4 { num, den } => {
            let net = a - ceil_div(a * num, *den);
            let out = r_out * net / (r_in + net);
            (out, a, out)
        }
        Fee::Cpmm { trade, protocol, fund, creator, creator_on } => {
            let on_input = *creator > 0 && match creator_on { 0 => true, 1 => zero_for_one, 2 => !zero_for_one, _ => true };
            let trade_fee = ceil_div(a * trade, 1_000_000);
            let creator_in = if on_input { ceil_div(a * creator, 1_000_000) } else { 0 };
            let net = a.checked_sub(trade_fee + creator_in)?;
            let gross = r_out * net / (r_in + net);
            let creator_out = if !on_input && *creator > 0 { ceil_div(gross * creator, 1_000_000) } else { 0 };
            let owed = trade_fee * protocol / 1_000_000 + trade_fee * fund / 1_000_000 + creator_in;
            (gross - creator_out, a - owed, gross)
        }
        Fee::Pump { .. } => {
            let (lp, pr, cr) = pump_fees(s)?;
            if zero_for_one {
                // sell: base in, quote out; fees skimmed from the gross quote output
                let gross = s.r1v() * a / (s.r0 + a);
                let (f_lp, f_pr, f_cr) = (ceil_div(gross * lp, 10_000), ceil_div(gross * pr, 10_000), ceil_div(gross * cr, 10_000));
                let out = gross.checked_sub(f_lp + f_pr + f_cr)?;
                if gross > s.r1 { return None; }
                (out, a, gross - f_lp)
            } else {
                // buy_exact_quote_in: the spendable quote covers the effective input plus fees
                let eff = a * 10_000 / (10_000 + lp + pr + cr);
                let out = s.r0 * eff / (s.r1v() + eff);
                (out, eff + ceil_div(eff * lp, 10_000), out)
            }
        }
    };
    if out == 0 || out >= r_out || out > u64::MAX as u128 { return None; }
    let (n_in, n_out) = (r_in + d_in, r_out.checked_sub(d_out)?);
    let (r0, r1) = if zero_for_one { (n_in, n_out) } else { (n_out, n_in) };
    Some(CpOut { out: out as u64, r0, r1 })
}

/// Exact-out (pump `buy`: base_amount_out) as an equivalent exact input
pub fn input_for_output(s: &CpSnap, zero_for_one: bool, want: u64) -> Option<u64> {
    crate::venues::solve_exact_in(want, |x| quote(s, zero_for_one, x).map(|q| q.out))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snap(fee: Fee) -> CpSnap { CpSnap { venue: Venue::RayAmmV4, r0: 1_000_000_000, r1: 5_000_000_000, virt: 0, fee, slot: 0 } }

    #[test]
    fn ammv4_matches_the_integer_formula() {
        let s = snap(Fee::AmmV4 { num: 25, den: 10_000 });
        let q = quote(&s, true, 1_000_000).unwrap();
        let net = 1_000_000u128 - ceil_div(1_000_000 * 25, 10_000);
        assert_eq!(q.out as u128, 5_000_000_000u128 * net / (1_000_000_000 + net));
        assert_eq!(q.r0, 1_001_000_000, "the whole input stays in the vault");
        assert_eq!(q.r1, 5_000_000_000 - q.out as u128);
    }

    #[test]
    fn cpmm_owed_fees_leave_the_reserve() {
        let s = CpSnap { venue: Venue::RayCpmm, fee: Fee::Cpmm { trade: 2_500, protocol: 120_000, fund: 40_000, creator: 0, creator_on: 0 }, ..snap(Fee::AmmV4 { num: 0, den: 1 }) };
        let q = quote(&s, false, 10_000_000).unwrap();
        let tf = ceil_div(10_000_000 * 2_500, 1_000_000); // 25,000
        let owed = tf * 120_000 / 1_000_000 + tf * 40_000 / 1_000_000; // 3,000 + 1,000
        assert_eq!(q.r1, 5_000_000_000 + 10_000_000 - owed);
    }

    #[test]
    fn exact_out_inverts_the_quote() {
        let s = snap(Fee::AmmV4 { num: 25, den: 10_000 });
        let want = 4_000_000;
        let x = input_for_output(&s, true, want).unwrap();
        assert!(quote(&s, true, x).unwrap().out >= want);
        assert!(quote(&s, true, x - 1).unwrap().out < want);
    }
}
