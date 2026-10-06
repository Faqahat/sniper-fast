//! Leg dispatch: account checks (owner, discriminator, keys, direction) and the per-venue parse, then one enum the
//! planner quotes and models through. The checks run in this order for every kind:
//! 1. owner and discriminator of every state account, constant keys → `DescError`;
//! 2. account lengths and version bytes → `Abort::Layout` (a venue upgrade turns sizing off instead of mispricing);
//! 3. keys the pool names (vaults, mints, config, bin arrays) and the input mint → `DescError`;
//! 4. mint scans and venue state → `Abort` (fall back to the engine's amount).
use crate::desc::Kind;
use crate::error::{Abort, DescCode, DescError, Quote, QuoteErr};
use crate::layout as L;
use crate::math::key_at;
use crate::opt::{LegModel, Mob};
use crate::token::{mint_info, token_account, MintInfo};
use crate::venue::{ammv4, cpmm, dammv2, dlmm, pumpswap};
#[cfg(feature = "rayclmm")]
use crate::venue::raydium_clmm;
#[cfg(feature = "whirlpool")]
use crate::venue::orca_whirlpool;
use crate::{AcctRef, Clock, Fx, LegIn, PdaFn};

#[derive(Clone, Copy, Debug)]
pub enum AnyLeg<'a> {
    Pump(pumpswap::PumpLeg),
    Cpmm(cpmm::CpmmLeg),
    Amm(ammv4::AmmLeg),
    Dlmm(dlmm::DlmmLeg<'a>),
    Damm(dammv2::DammLeg),
    /// Raydium CLMM (PLAN-ADDENDUM WP-21; feature `rayclmm`)
    #[cfg(feature = "rayclmm")]
    RayClmm(raydium_clmm::RayClmmLeg<'a>),
    /// Orca Whirlpool (PLAN-ADDENDUM WP-21; feature `whirlpool`)
    #[cfg(feature = "whirlpool")]
    Whirl(orca_whirlpool::WhirlLeg<'a>),
}

/// What the pair checks need from a leg even when its state aborts: the pool key and, once the pool's own fields
/// could be read, the input and output mints.
#[derive(Clone, Copy, Debug)]
pub struct LegHead<'a> { pub pool: &'a [u8; 32], pub mints: Option<(&'a [u8; 32], &'a [u8; 32])> }

#[derive(Clone, Copy, Debug)]
pub struct Parsed<'a> { pub head: LegHead<'a>, pub leg: Result<AnyLeg<'a>, Abort> }

const fn de(code: DescCode, acct: usize) -> DescError { DescError::new(code, 0xFF, acct as u8) }

fn st<'b, 'a>(l: &'b LegIn<'a>, i: usize) -> Result<&'b AcctRef<'a>, DescError> { l.state.get(i).ok_or(de(DescCode::StateCount, i)) }

fn owned(a: &AcctRef, owner: &[u8; 32], disc: Option<&[u8; 8]>, i: usize) -> Result<(), DescError> {
    if a.owner != owner { return Err(de(DescCode::Owner, i)); }
    if let Some(d) = disc {
        if a.data.get(..8) != Some(&d[..]) { return Err(de(DescCode::Discriminator, i)); }
    }
    Ok(())
}

fn same(a: &AcctRef, want: Option<&[u8; 32]>, i: usize) -> Result<(), DescError> {
    if Some(a.key) != want { return Err(de(DescCode::Key, i)); }
    Ok(())
}

/// a vault: its key is the one the pool names and it holds `mint`
fn vault<'a>(a: &AcctRef<'a>, want: Option<&[u8; 32]>, mint: &[u8; 32], i: usize, spl_only: bool) -> Result<u64, DescError> {
    same(a, want, i)?;
    let t = token_account(a).ok_or(de(DescCode::NotTokenAccount, i))?;
    if t.mint != mint || (spl_only && t.t22) { return Err(de(DescCode::NotTokenAccount, i)); }
    Ok(t.amount)
}

/// a mint the pool names: Err = DescError; Ok(Err) = transfer fee / hook
fn mint(a: &AcctRef, want: Option<&[u8; 32]>, i: usize) -> Result<Result<MintInfo, Abort>, DescError> {
    same(a, want, i)?;
    mint_info(a).map_err(|_| de(DescCode::NotMint, i))
}

macro_rules! abort_if {
    ($head:expr, $r:expr) => {
        match $r { Ok(v) => v, Err(a) => return Ok(Parsed { head: $head, leg: Err(a) }) }
    };
}

impl<'a> AnyLeg<'a> {
    /// Check and parse one leg. Outer `Err`: an engine bug (ERR_SIZING_DESC). Inner `Err`: a state the model does not
    /// cover (fall back). The DescError's `leg` field is 0xFF; the planner fills it in.
    pub fn parse(l: &LegIn<'a>, clock: &Clock, pda: PdaFn) -> Result<Parsed<'a>, DescError> {
        let d = &l.desc;
        if l.program != d.kind.program() { return Err(de(DescCode::Program, 0xFF)); }
        let want_n = match d.kind {
            Kind::PumpBuy | Kind::PumpSell => 7,
            Kind::RayCpmm => 6,
            Kind::RayAmmV4 => 3,
            Kind::Dlmm => 3 + d.n_bin_arrays as usize,
            Kind::DammV2 => 3,
            Kind::RayClmm => 6 + d.n_bin_arrays as usize,
            Kind::Whirlpool => 9 + d.n_bin_arrays as usize,
        };
        if l.state.len() != want_n { return Err(de(DescCode::StateCount, 0xFF)); }
        let pool = st(l, 0)?;
        let mut head = LegHead { pool: pool.key, mints: None };
        let input_ok = |m_in: &[u8; 32]| if l.input_mint == m_in { Ok(()) } else { Err(de(DescCode::InputMint, 0xFF)) };
        match d.kind {
            Kind::PumpBuy | Kind::PumpSell => {
                let sell = d.kind == Kind::PumpSell;
                let (gc, fc) = (st(l, 1)?, st(l, 6)?);
                owned(pool, &L::PUMPSWAP, Some(&L::DISC_POOL), 0)?;
                owned(gc, &L::PUMPSWAP, Some(&L::DISC_GLOBAL_CONFIG), 1)?;
                same(gc, Some(&L::PUMP_GLOBAL_CONFIG), 1)?;
                owned(fc, &L::PUMP_FEE_PROGRAM, Some(&L::DISC_FEE_CONFIG), 6)?;
                same(fc, Some(&L::PUMP_FEE_CONFIG), 6)?;
                // a pool written before a trailing field existed is shorter: priced from the program's minimum up
                if !pumpswap::pool_len_ok(pool.data.len()) { return Ok(Parsed { head, leg: Err(Abort::Layout) }); }
                let p = pool.data;
                let (base, quote) = (key_at(p, pumpswap::off::BASE_MINT), key_at(p, pumpswap::off::QUOTE_MINT));
                let (Some(base), Some(quote)) = (base, quote) else { return Ok(Parsed { head, leg: Err(Abort::Layout) }) };
                let bm = mint(st(l, 2)?, Some(base), 2)?;
                let qm = mint(st(l, 3)?, Some(quote), 3)?;
                let b_amt = vault(st(l, 4)?, key_at(p, pumpswap::off::BASE_VAULT), base, 4, false)?;
                let q_amt = vault(st(l, 5)?, key_at(p, pumpswap::off::QUOTE_VAULT), quote, 5, false)?;
                let (m_in, m_out) = if sell { (base, quote) } else { (quote, base) };
                input_ok(m_in)?;
                head.mints = Some((m_in, m_out));
                if !cfg!(feature = "pumpswap") { return Ok(Parsed { head, leg: Err(Abort::Unsupported) }); }
                let bm = abort_if!(head, bm);
                abort_if!(head, qm);
                let canonical = pumpswap::is_canonical(p, d.pump_bump, pda);
                let leg = pumpswap::parse(p, gc.data, fc.data, bm.supply, quote, b_amt, q_amt, sell, canonical).map(AnyLeg::Pump);
                Ok(Parsed { head, leg })
            }
            Kind::RayCpmm => {
                let cfg = st(l, 1)?;
                owned(pool, &L::RAY_CPMM, Some(&L::DISC_POOL_STATE), 0)?;
                owned(cfg, &L::RAY_CPMM, Some(&L::DISC_AMM_CONFIG), 1)?;
                if pool.data.len() != cpmm::POOL_LEN || cfg.data.len() != cpmm::CONFIG_LEN { return Ok(Parsed { head, leg: Err(Abort::Layout) }); }
                let p = pool.data;
                same(cfg, key_at(p, cpmm::off::AMM_CONFIG), 1)?;
                let zfo = d.base_or_token0_in;
                let (m0, m1) = (key_at(p, cpmm::off::MINT0).ok_or(de(DescCode::Key, 0))?, key_at(p, cpmm::off::MINT1).ok_or(de(DescCode::Key, 0))?);
                let (v0, v1) = (key_at(p, cpmm::off::VAULT0), key_at(p, cpmm::off::VAULT1));
                let (m_in, m_out, v_in, v_out) = if zfo { (m0, m1, v0, v1) } else { (m1, m0, v1, v0) };
                let a_in = vault(st(l, 2)?, v_in, m_in, 2, false)?;
                let a_out = vault(st(l, 3)?, v_out, m_out, 3, false)?;
                let mi = mint(st(l, 4)?, Some(m_in), 4)?;
                let mo = mint(st(l, 5)?, Some(m_out), 5)?;
                input_ok(m_in)?;
                head.mints = Some((m_in, m_out));
                if !cfg!(feature = "cpmm") { return Ok(Parsed { head, leg: Err(Abort::Unsupported) }); }
                abort_if!(head, mi);
                abort_if!(head, mo);
                let (a0, a1) = if zfo { (a_in, a_out) } else { (a_out, a_in) };
                Ok(Parsed { head, leg: cpmm::parse(p, cfg.data, a0, a1, zfo, clock.unix_timestamp).map(AnyLeg::Cpmm) })
            }
            Kind::RayAmmV4 => {
                owned(pool, &L::RAY_AMM_V4, None, 0)?;
                // AmmInfo has no discriminator: the length is its identity
                if pool.data.len() != ammv4::AMM_LEN { return Err(de(DescCode::Discriminator, 0)); }
                let p = pool.data;
                let (cm, pm) = (key_at(p, ammv4::off::COIN_MINT).ok_or(de(DescCode::Key, 0))?, key_at(p, ammv4::off::PC_MINT).ok_or(de(DescCode::Key, 0))?);
                let coin = vault(st(l, 1)?, key_at(p, ammv4::off::COIN_VAULT), cm, 1, true)?;
                let pc = vault(st(l, 2)?, key_at(p, ammv4::off::PC_VAULT), pm, 2, true)?;
                let coin_in = d.base_or_token0_in;
                let (m_in, m_out) = if coin_in { (cm, pm) } else { (pm, cm) };
                input_ok(m_in)?;
                head.mints = Some((m_in, m_out));
                if !cfg!(feature = "ammv4") { return Ok(Parsed { head, leg: Err(Abort::Unsupported) }); }
                Ok(Parsed { head, leg: ammv4::parse(p, coin, pc, coin_in, clock.unix_timestamp).map(AnyLeg::Amm) })
            }
            Kind::Dlmm => {
                owned(pool, &L::DLMM, Some(&L::DISC_LB_PAIR), 0)?;
                if d.max_bins == 0 { return Err(de(DescCode::BinBudget, 0xFF)); }
                let n = d.n_bin_arrays as usize;
                let mut arrays: [&'a [u8]; dlmm::MAX_ARRAYS] = [&[]; dlmm::MAX_ARRAYS];
                for (k, slot) in arrays.iter_mut().enumerate().take(n) {
                    let a = st(l, 3 + k)?;
                    owned(a, &L::DLMM, Some(&L::DISC_BIN_ARRAY), 3 + k)?;
                    if key_at(a.data, dlmm::off::A_LB_PAIR) != Some(pool.key) { return Err(de(DescCode::Key, 3 + k)); }
                    *slot = a.data;
                }
                if pool.data.len() != dlmm::PAIR_LEN { return Ok(Parsed { head, leg: Err(Abort::Layout) }); }
                let p = pool.data;
                let (mx, my) = (key_at(p, dlmm::off::MINT_X).ok_or(de(DescCode::Key, 0))?, key_at(p, dlmm::off::MINT_Y).ok_or(de(DescCode::Key, 0))?);
                let ix = mint(st(l, 1)?, Some(mx), 1)?;
                let iy = mint(st(l, 2)?, Some(my), 2)?;
                let swap_for_y = d.base_or_token0_in;
                let (m_in, m_out) = if swap_for_y { (mx, my) } else { (my, mx) };
                input_ok(m_in)?;
                head.mints = Some((m_in, m_out));
                if !cfg!(feature = "dlmm") { return Ok(Parsed { head, leg: Err(Abort::Unsupported) }); }
                abort_if!(head, ix);
                abort_if!(head, iy);
                let arrays = arrays.get(..n).unwrap_or(&[]);
                Ok(Parsed { head, leg: dlmm::parse(p, arrays, swap_for_y, clock).map(|l| AnyLeg::Dlmm(l.with_budget(d.max_bins as u16))) })
            }
            Kind::DammV2 => {
                owned(pool, &L::DAMM_V2, Some(&L::DISC_POOL), 0)?;
                if pool.data.len() != dammv2::POOL_SIZE { return Ok(Parsed { head, leg: Err(Abort::Layout) }); }
                let p = pool.data;
                let k = dammv2::keys(p).ok_or(de(DescCode::Key, 0))?;
                let ia = mint(st(l, 1)?, Some(k.token_a_mint), 1)?;
                let ib = mint(st(l, 2)?, Some(k.token_b_mint), 2)?;
                let a_to_b = d.base_or_token0_in;
                let (m_in, m_out) = if a_to_b { (k.token_a_mint, k.token_b_mint) } else { (k.token_b_mint, k.token_a_mint) };
                input_ok(m_in)?;
                head.mints = Some((m_in, m_out));
                if !cfg!(feature = "dammv2") { return Ok(Parsed { head, leg: Err(Abort::Unsupported) }); }
                abort_if!(head, ia);
                abort_if!(head, ib);
                // both mints scanned: no transfer fee. The rate limiter in force refuses (dammv2::parse): the program then
                // needs the instructions sysvar, which the engine's leg does not pass (REVIEW.md F5)
                Ok(Parsed { head, leg: dammv2::parse(p, a_to_b, true, clock).map(AnyLeg::Damm) })
            }
            Kind::RayClmm => {
                owned(pool, &L::RAY_CLMM, Some(&L::DISC_POOL_STATE), 0)?;
                #[cfg(feature = "rayclmm")]
                { parse_ray_clmm(l, clock, head) }
                #[cfg(not(feature = "rayclmm"))]
                { Ok(Parsed { head, leg: Err(Abort::Unsupported) }) }
            }
            Kind::Whirlpool => {
                owned(pool, &L::WHIRLPOOL, Some(&L::DISC_WHIRLPOOL), 0)?;
                #[cfg(feature = "whirlpool")]
                { parse_whirlpool(l, clock, pda, head) }
                #[cfg(not(feature = "whirlpool"))]
                { let _ = pda; Ok(Parsed { head, leg: Err(Abort::Unsupported) }) }
            }
        }
    }

    /// EXACT: equals the venue program's integer output to the unit, or errs
    pub fn quote(&self, amount_in: u64) -> Result<Quote, QuoteErr> {
        // a variant whose feature is off is never constructed; the cfg! keeps its code out of the build
        let off = Err(QuoteErr::Abort(Abort::Unsupported));
        match self {
            AnyLeg::Pump(x) => if cfg!(feature = "pumpswap") { x.quote(amount_in) } else { off },
            AnyLeg::Cpmm(x) => if cfg!(feature = "cpmm") { x.quote(amount_in) } else { off },
            AnyLeg::Amm(x) => if cfg!(feature = "ammv4") { x.quote(amount_in) } else { off },
            AnyLeg::Dlmm(x) => if cfg!(feature = "dlmm") { x.quote(amount_in) } else { off },
            AnyLeg::Damm(x) => if cfg!(feature = "dammv2") { x.quote(amount_in) } else { off },
            #[cfg(feature = "rayclmm")]
            AnyLeg::RayClmm(x) => x.quote(amount_in),
            #[cfg(feature = "whirlpool")]
            AnyLeg::Whirl(x) => x.quote(amount_in),
        }
    }

    /// The locator's model: one Möbius curve, or DLMM's bins. Err while the analytic model does not apply (a DAMM v2
    /// leg parsed with the rate limiter in force, which [`dammv2::parse`] no longer produces: kept for the engine's
    /// off-chain use of `DammLeg`).
    pub fn model(&self) -> Result<LegModel<'_, 'a>, Abort> {
        let mob = |(a, b, c): (Fx, Fx, Fx), cap: Option<u64>| LegModel::Mobius(Mob::new(a, b, c, cap.map_or(Fx::INF, Fx::from_u64)));
        Ok(match self {
            AnyLeg::Pump(x) if cfg!(feature = "pumpswap") => mob(x.model(), x.cap_in()),
            AnyLeg::Cpmm(x) if cfg!(feature = "cpmm") => mob(x.model(), None),
            AnyLeg::Amm(x) if cfg!(feature = "ammv4") => mob(x.model(), None),
            AnyLeg::Dlmm(x) if cfg!(feature = "dlmm") => LegModel::Bins(x),
            AnyLeg::Damm(x) if cfg!(feature = "dammv2") => mob(x.model().ok_or(Abort::Damm(crate::error::DammWhy::RateLimiter))?, x.cap_in()),
            #[cfg(feature = "rayclmm")]
            AnyLeg::RayClmm(x) => LegModel::RayClmm(x),
            #[cfg(feature = "whirlpool")]
            AnyLeg::Whirl(x) => LegModel::Whirl(x),
            _ => return Err(Abort::Unsupported),
        })
    }

    /// The largest input known to quote Ok (None = unbounded). Exact for PumpSwap sell, DAMM v2 (range exit) and
    /// DLMM within its walk budget (a full exact walk: tests and the engine, not the planner).
    pub fn cap_in(&self) -> Option<u64> {
        match self {
            AnyLeg::Pump(x) if cfg!(feature = "pumpswap") => x.cap_in(),
            AnyLeg::Dlmm(x) if cfg!(feature = "dlmm") => x.cap_in(),
            AnyLeg::Damm(x) if cfg!(feature = "dammv2") => x.cap_in(),
            #[cfg(feature = "rayclmm")]
            AnyLeg::RayClmm(x) => x.cap_in(),
            #[cfg(feature = "whirlpool")]
            AnyLeg::Whirl(x) => x.cap_in(),
            _ => None,
        }
    }

    /// A DLMM leg (walks bins: no golden-section search over it, DESIGN.md §3.6)
    pub fn is_dlmm(&self) -> bool { matches!(self, AnyLeg::Dlmm(_)) }

    /// A leg whose exact quote walks (DLMM bins, CLMM swap steps): no golden-section search over it (DESIGN.md §3.6)
    pub fn walks(&self) -> bool {
        match self {
            AnyLeg::Dlmm(_) => true,
            #[cfg(feature = "rayclmm")]
            AnyLeg::RayClmm(_) => true,
            #[cfg(feature = "whirlpool")]
            AnyLeg::Whirl(_) => true,
            _ => false,
        }
    }

    /// The cap the planner uses without walking: exact where it is closed form, else None.
    pub fn cheap_cap(&self) -> Option<u64> {
        match self {
            AnyLeg::Pump(x) if cfg!(feature = "pumpswap") => x.cap_in(),
            AnyLeg::Damm(x) if cfg!(feature = "dammv2") => x.cap_in(),
            _ => None,
        }
    }
}

/// Raydium CLMM (kind 7): the pool (its PoolState checked by the caller), the AmmConfig it names, the vaults and mints of
/// the direction, then the leg's remaining accounts as the program reads them: each classified by its length (a
/// 10,240-byte tick array, the 1,832-byte bitmap extension), owned by the program with its discriminator and naming the
/// pool; an account of another length ends the list (the program stops reading there)
#[cfg(feature = "rayclmm")]
fn parse_ray_clmm<'a>(l: &LegIn<'a>, clock: &Clock, mut head: LegHead<'a>) -> Result<Parsed<'a>, DescError> {
    use raydium_clmm::{off, ARRAY_LEN, CONFIG_LEN, EXT_LEN, MAX_REMAINING, POOL_LEN};
    let d = &l.desc;
    let input_ok = |m_in: &[u8; 32]| if l.input_mint == m_in { Ok(()) } else { Err(de(DescCode::InputMint, 0xFF)) };
    let pool = st(l, 0)?;
    let cfg = st(l, 1)?;
    owned(cfg, &L::RAY_CLMM, Some(&L::DISC_AMM_CONFIG), 1)?;
    let mut rem: [&'a [u8]; MAX_REMAINING] = [&[]; MAX_REMAINING];
    let mut k = 0usize;
    for i in 0..(d.n_bin_arrays as usize).min(MAX_REMAINING) {
        let a = st(l, 6 + i)?;
        let disc = match a.data.len() { ARRAY_LEN => &L::DISC_TICK_ARRAY_STATE, EXT_LEN => &L::DISC_TICK_ARRAY_BITMAP_EXT, _ => break };
        owned(a, &L::RAY_CLMM, Some(disc), 6 + i)?;
        // TickArrayState.pool_id @8, TickArrayBitmapExtension.pool_id @8
        if key_at(a.data, off::A_POOL) != Some(pool.key) { return Err(de(DescCode::Key, 6 + i)); }
        if let Some(slot) = rem.get_mut(k) { *slot = a.data; k += 1; }
    }
    if pool.data.len() != POOL_LEN || cfg.data.len() != CONFIG_LEN { return Ok(Parsed { head, leg: Err(Abort::Layout) }); }
    let p = pool.data;
    same(cfg, key_at(p, off::AMM_CONFIG), 1)?;
    let zfo = d.base_or_token0_in;
    let (m0, m1) = (key_at(p, off::MINT0).ok_or(de(DescCode::Key, 0))?, key_at(p, off::MINT1).ok_or(de(DescCode::Key, 0))?);
    let (v0, v1) = (key_at(p, off::VAULT0), key_at(p, off::VAULT1));
    let (m_in, m_out, v_in, v_out) = if zfo { (m0, m1, v0, v1) } else { (m1, m0, v1, v0) };
    let a_in = vault(st(l, 2)?, v_in, m_in, 2, false)?;
    let a_out = vault(st(l, 3)?, v_out, m_out, 3, false)?;
    let (mi_acc, mo_acc) = (st(l, 4)?, st(l, 5)?);
    let mi = mint(mi_acc, Some(m_in), 4)?;
    let mo = mint(mo_acc, Some(m_out), 5)?;
    input_ok(m_in)?;
    head.mints = Some((m_in, m_out));
    abort_if!(head, mi);
    abort_if!(head, mo);
    match crate::token::mint_blocked(mi_acc.data).or(crate::token::mint_blocked(mo_acc.data)) {
        Some(crate::token::MintBlock::Paused) => return Ok(Parsed { head, leg: Err(Abort::Clmm(crate::error::ClmmWhy::MintPaused)) }),
        Some(crate::token::MintBlock::DefaultFrozen) => return Ok(Parsed { head, leg: Err(Abort::Clmm(crate::error::ClmmWhy::MintFrozen)) }),
        None => {}
    }
    let (a0, a1) = if zfo { (a_in, a_out) } else { (a_out, a_in) };
    let rem = rem.get(..k).unwrap_or(&[]);
    Ok(Parsed { head, leg: raydium_clmm::parse(p, cfg.data, rem, a0, a1, zfo, clock).map(|x| AnyLeg::RayClmm(x.with_budget(d.max_bins as u16))) })
}

/// Orca Whirlpool (kind 8): the whirlpool (checked by the caller), its mints and vaults, the 3 static and the
/// supplemental tick arrays (each initialized one owned by the program as a fixed or dynamic tick array of this pool; an
/// uninitialized one is the System program's, empty), and the Oracle (uninitialized: no adaptive fee). The program
/// takes an uninitialized tick array as zeroed when the account is the PDA of a start index the swap needs: those PDAs
/// are derived with `pda` (find_program_address: the bump from 255 down)
#[cfg(feature = "whirlpool")]
fn parse_whirlpool<'a>(l: &LegIn<'a>, clock: &Clock, pda: PdaFn, mut head: LegHead<'a>) -> Result<Parsed<'a>, DescError> {
    use orca_whirlpool::{needed_starts, off, start_seed, TickArrayIn, MAX_SUPPLEMENTAL, POOL_LEN};
    let d = &l.desc;
    let input_ok = |m_in: &[u8; 32]| if l.input_mint == m_in { Ok(()) } else { Err(de(DescCode::InputMint, 0xFF)) };
    let pool = st(l, 0)?;
    if pool.data.len() != POOL_LEN { return Ok(Parsed { head, leg: Err(Abort::Layout) }); }
    let p = pool.data;
    let (ma, mb) = (key_at(p, off::MINT_A).ok_or(de(DescCode::Key, 0))?, key_at(p, off::MINT_B).ok_or(de(DescCode::Key, 0))?);
    let (ma_acc, mb_acc) = (st(l, 1)?, st(l, 2)?);
    let ia = mint(ma_acc, Some(ma), 1)?;
    let ib = mint(mb_acc, Some(mb), 2)?;
    let va = vault(st(l, 3)?, key_at(p, off::VAULT_A), ma, 3, false)?;
    let vb = vault(st(l, 4)?, key_at(p, off::VAULT_B), mb, 4, false)?;
    // the tick arrays: 3 static + n supplemental
    const N: usize = 3 + MAX_SUPPLEMENTAL;
    let mut init: [Option<&'a [u8]>; N] = [None; N];
    let mut uninit: [Option<&'a [u8; 32]>; N] = [None; N];
    let n = (3 + d.n_bin_arrays as usize).min(N);
    for i in 0..n {
        let pos = if i < 3 { 5 + i } else { 9 + (i - 3) };
        let a = st(l, pos)?;
        if *a.owner == L::SYSTEM_PROGRAM && a.data.is_empty() {
            if let Some(s) = uninit.get_mut(i) { *s = Some(a.key); }
            continue;
        }
        if a.owner != &L::WHIRLPOOL { return Err(de(DescCode::Owner, pos)); }
        let dynamic = match a.data.get(..8) {
            Some(x) if x == &L::DISC_WHIRL_TICK_ARRAY[..] => false,
            Some(x) if x == &L::DISC_DYNAMIC_TICK_ARRAY[..] => true,
            _ => return Err(de(DescCode::Discriminator, pos)),
        };
        let wk = if dynamic { off::D_WHIRLPOOL } else { off::F_WHIRLPOOL };
        if key_at(a.data, wk) != Some(pool.key) { return Err(de(DescCode::Key, pos)); }
        if let Some(s) = init.get_mut(i) { *s = Some(a.data); }
    }
    let o = st(l, 8)?;
    let oracle = if *o.owner == L::SYSTEM_PROGRAM && o.data.is_empty() { None } else {
        owned(o, &L::WHIRLPOOL, Some(&L::DISC_ORACLE), 8)?;
        if key_at(o.data, off::O_WHIRLPOOL) != Some(pool.key) { return Err(de(DescCode::Key, 8)); }
        Some(o.data)
    };
    let a_to_b = d.base_or_token0_in;
    let (m_in, m_out) = if a_to_b { (ma, mb) } else { (mb, ma) };
    input_ok(m_in)?;
    head.mints = Some((m_in, m_out));
    abort_if!(head, ia);
    abort_if!(head, ib);
    match crate::token::mint_blocked(ma_acc.data).or(crate::token::mint_blocked(mb_acc.data)) {
        Some(crate::token::MintBlock::Paused) => return Ok(Parsed { head, leg: Err(Abort::Whirl(crate::error::WhirlWhy::MintPaused)) }),
        Some(crate::token::MintBlock::DefaultFrozen) => return Ok(Parsed { head, leg: Err(Abort::Whirl(crate::error::WhirlWhy::MintFrozen)) }),
        None => {}
    }
    // the entries the sequence builder sees: every initialized array; an uninitialized account where it is the PDA of a
    // start index the swap needs
    let mut ins: [TickArrayIn<'a>; N] = [TickArrayIn { start: 0, data: None }; N];
    let mut k = 0usize;
    for data in init.iter().flatten() {
        let Some(start) = crate::math::i32_at(data, off::A_START) else { continue };
        if let Some(s) = ins.get_mut(k) { *s = TickArrayIn { start, data: Some(data) }; k += 1; }
    }
    if uninit.iter().any(|u| u.is_some()) {
        let (Some(ts), Some(tick)) = (crate::math::u16_at(p, off::TICK_SPACING), crate::math::i32_at(p, off::TICK_CURRENT)) else {
            return Ok(Parsed { head, leg: Err(Abort::Layout) });
        };
        let (need, nn) = needed_starts(tick, ts, a_to_b);
        for &st0 in need.iter().take(nn) {
            if ins.iter().take(k).any(|e| e.data.is_some() && e.start == st0) { continue; }
            let mut buf = [0u8; 12];
            let seed = start_seed(st0, &mut buf);
            let key = (0..=255u8).rev().find_map(|b| pda(&[b"tick_array", pool.key, seed, &[b]], &L::WHIRLPOOL));
            if key.is_some_and(|key| uninit.iter().flatten().any(|u| **u == key)) {
                if let Some(s) = ins.get_mut(k) { *s = TickArrayIn { start: st0, data: None }; k += 1; }
            }
        }
    }
    let ins = ins.get(..k).unwrap_or(&[]);
    Ok(Parsed { head, leg: orca_whirlpool::parse(p, oracle, ins, va, vb, a_to_b, clock).map(|x| AnyLeg::Whirl(x.with_budget(d.max_bins as u16))) })
}
