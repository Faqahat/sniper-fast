//! Shared test helpers: a host PDA function, a deterministic RNG, synthetic account builders for every venue
//! (byte layouts of DESIGN.md §2), the mainnet fixtures, and a small harness that builds `LegIn`s and runs `plan`.
#![allow(dead_code)]
use arbx_sizing::layout as L;
use arbx_sizing::{AcctRef, Clock, Kind, LegDesc, LegIn};
use sha2::{Digest, Sha256};

pub type Pk = [u8; 32];

/* ------------------------------------------------ PDA ------------------------------------------------ */

pub fn create_program_address(seeds: &[&[u8]], program: &[u8; 32]) -> Option<[u8; 32]> {
    let mut h = Sha256::new();
    for s in seeds { h.update(s); }
    h.update(program);
    h.update(b"ProgramDerivedAddress");
    let out: [u8; 32] = h.finalize().into();
    if curve25519_dalek::edwards::CompressedEdwardsY(out).decompress().is_some() { None } else { Some(out) }
}

pub fn find_program_address(seeds: &[&[u8]], program: &[u8; 32]) -> ([u8; 32], u8) {
    for bump in (0..=255u8).rev() {
        let b = [bump];
        let mut s: Vec<&[u8]> = seeds.to_vec();
        s.push(&b);
        if let Some(k) = create_program_address(&s, program) { return (k, bump); }
    }
    panic!("no bump");
}

/* ------------------------------------------------ RNG ------------------------------------------------ */

/// xorshift64*, deterministic
pub struct Rng(pub u64);
impl Rng {
    pub fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545F4914F6CDD1D)
    }
    pub fn range(&mut self, lo: u64, hi: u64) -> u64 { if hi <= lo { lo } else { lo + self.next() % (hi - lo + 1) } }
    /// log-uniform in [lo, hi]
    pub fn log(&mut self, lo: u64, hi: u64) -> u64 {
        let (a, b) = ((lo.max(1) as f64).ln(), (hi.max(1) as f64).ln());
        let u = (self.next() >> 11) as f64 / (1u64 << 53) as f64;
        ((a + (b - a) * u).exp() as u64).clamp(lo, hi)
    }
    pub fn chance(&mut self, num: u64, den: u64) -> bool { self.next() % den < num }
    pub fn key(&mut self) -> Pk { let mut k = [0u8; 32]; for c in k.chunks_mut(8) { c.copy_from_slice(&self.next().to_le_bytes()); } k }
}

/* ------------------------------------------- byte writers ------------------------------------------- */

pub fn put(d: &mut [u8], o: usize, b: &[u8]) { d[o..o + b.len()].copy_from_slice(b); }
pub fn put_u64(d: &mut [u8], o: usize, v: u64) { put(d, o, &v.to_le_bytes()); }

/// An owned account
#[derive(Clone, Debug)]
pub struct Acct { pub key: Pk, pub owner: Pk, pub data: Vec<u8> }
impl Acct {
    pub fn view(&self) -> AcctRef<'_> { AcctRef { key: &self.key, owner: &self.owner, data: &self.data } }
}

pub fn token_account(key: Pk, mint: Pk, owner: Pk, amount: u64, t22: bool) -> Acct {
    let mut d = vec![0u8; 165];
    put(&mut d, 0, &mint);
    put(&mut d, 32, &owner);
    put_u64(&mut d, 64, amount);
    d[108] = 1;
    Acct { key, owner: if t22 { L::TOKEN_2022 } else { L::TOKEN_PROGRAM }, data: d }
}

/// A mint; `fee_bps`: a Token-2022 TransferFeeConfig with that (newer) fee
pub fn mint(key: Pk, supply: u64, t22: bool, fee_bps: Option<u16>) -> Acct {
    let mut d = vec![0u8; 82];
    put_u64(&mut d, 36, supply);
    d[44] = 6;
    d[45] = 1;
    if let Some(bps) = fee_bps {
        d.resize(166, 0);
        d[165] = 1;
        let mut v = vec![0u8; 108];
        put(&mut v, 106, &bps.to_le_bytes());
        d.extend_from_slice(&1u16.to_le_bytes());
        d.extend_from_slice(&(v.len() as u16).to_le_bytes());
        d.extend_from_slice(&v);
    }
    Acct { key, owner: if t22 { L::TOKEN_2022 } else { L::TOKEN_PROGRAM }, data: d }
}

/* --------------------------------------------- PumpSwap --------------------------------------------- */

#[derive(Clone, Debug)]
pub struct PumpSpec {
    pub base: u64,
    pub quote: u64,
    pub virt: i128,
    pub supply: u64,
    pub canonical: bool,
    pub coin_creator: bool,
    pub creator_fee_bps: u64,
    /// flat fees (lp, protocol, creator)
    pub flat: (u64, u64, u64),
    /// SOL tiers: (threshold, lp, protocol, creator)
    pub tiers: Vec<(u128, u64, u64, u64)>,
    pub quote_mint: Pk,
}

impl Default for PumpSpec {
    fn default() -> Self {
        PumpSpec { base: 70_000_000_000_000, quote: 300_000_000_000, virt: 0, supply: 1_000_000_000_000_000, canonical: true,
            coin_creator: true, creator_fee_bps: 0, flat: (25, 5, 0),
            tiers: vec![(0, 2, 93, 30), (420_000_000_000, 20, 5, 95), (98_240_000_000_000, 20, 5, 5)], quote_mint: L::WSOL }
    }
}

pub struct PumpAccts { pub pool: Acct, pub global: Acct, pub fee_cfg: Acct, pub base_mint: Acct, pub quote_mint: Acct, pub base_vault: Acct, pub quote_vault: Acct, pub bump: u8 }

pub fn pump_global() -> Acct {
    let mut g = vec![0u8; 949];
    put(&mut g, 0, &L::DISC_GLOBAL_CONFIG);
    put_u64(&mut g, 40, 20);
    put_u64(&mut g, 48, 5);
    put_u64(&mut g, 313, 5);
    put_u64(&mut g, 899, 5000);
    g[940] = 1;
    put_u64(&mut g, 941, 300);
    Acct { key: L::PUMP_GLOBAL_CONFIG, owner: L::PUMPSWAP, data: g }
}

pub fn pump_fee_config(flat: (u64, u64, u64), tiers: &[(u128, u64, u64, u64)], stable: &[(u128, u64, u64, u64)], exotic: (u64, u64, u64)) -> Acct {
    let mut f = vec![0u8; 4097];
    put(&mut f, 0, &L::DISC_FEE_CONFIG);
    let mut o = 41;
    for v in [flat.0, flat.1, flat.2] { put_u64(&mut f, o, v); o += 8; }
    for list in [tiers, stable] {
        put(&mut f, o, &(list.len() as u32).to_le_bytes());
        o += 4;
        for t in list {
            put(&mut f, o, &t.0.to_le_bytes());
            for (j, v) in [t.1, t.2, t.3].into_iter().enumerate() { put_u64(&mut f, o + 16 + 8 * j, v); }
            o += 40;
        }
    }
    for v in [exotic.0, exotic.1, exotic.2] { put_u64(&mut f, o, v); o += 8; }
    Acct { key: L::PUMP_FEE_CONFIG, owner: L::PUMP_FEE_PROGRAM, data: f }
}

pub fn pump(rng: &mut Rng, s: &PumpSpec) -> PumpAccts {
    let (pool_k, base_k, bv, qv) = (rng.key(), rng.key(), rng.key(), rng.key());
    let quote_k = s.quote_mint;
    let (auth, bump) = find_program_address(&[b"pool-authority", &base_k], &L::PUMP_FUN);
    let mut p = vec![0u8; 301];
    put(&mut p, 0, &L::DISC_POOL);
    put(&mut p, 11, &if s.canonical { auth } else { rng.key() });
    put(&mut p, 43, &base_k);
    put(&mut p, 75, &quote_k);
    put(&mut p, 139, &bv);
    put(&mut p, 171, &qv);
    if s.coin_creator { put(&mut p, 211, &rng.key()); }
    put(&mut p, 245, &s.virt.to_le_bytes());
    put_u64(&mut p, 261, s.creator_fee_bps);
    PumpAccts {
        pool: Acct { key: pool_k, owner: L::PUMPSWAP, data: p },
        global: pump_global(),
        fee_cfg: pump_fee_config(s.flat, &s.tiers, &s.tiers, (20, 5, 5)),
        base_mint: mint(base_k, s.supply, true, None),
        quote_mint: mint(quote_k, 0, false, None),
        base_vault: token_account(bv, base_k, pool_k, s.base, true),
        quote_vault: token_account(qv, quote_k, pool_k, s.quote, false),
        bump: if s.canonical { bump } else { 0 },
    }
}

impl PumpAccts {
    pub fn state(&self) -> Vec<Acct> {
        vec![self.pool.clone(), self.global.clone(), self.base_mint.clone(), self.quote_mint.clone(), self.base_vault.clone(), self.quote_vault.clone(), self.fee_cfg.clone()]
    }
    pub fn base_key(&self) -> Pk { self.base_mint.key }
    pub fn quote_key(&self) -> Pk { self.quote_mint.key }
}

/* ----------------------------------------------- CPMM ----------------------------------------------- */

pub struct CpmmSpec { pub r0: u64, pub r1: u64, pub trade: u64, pub creator: u64, pub enable_creator: bool, pub creator_on: u8, pub owed0: u64, pub owed1: u64 }

/// state accounts for direction `zfo` (pool, cfg, vault_in, vault_out, mint_in, mint_out), and the two mints
pub fn cpmm(rng: &mut Rng, s: &CpmmSpec, m0: Pk, m1: Pk, zfo: bool) -> Vec<Acct> {
    let (pk, ck, v0, v1) = (rng.key(), rng.key(), rng.key(), rng.key());
    let mut p = vec![0u8; 637];
    put(&mut p, 0, &L::DISC_POOL_STATE);
    put(&mut p, 8, &ck);
    put(&mut p, 72, &v0);
    put(&mut p, 104, &v1);
    put(&mut p, 168, &m0);
    put(&mut p, 200, &m1);
    put_u64(&mut p, 341, s.owed0);
    put_u64(&mut p, 349, s.owed1);
    p[389] = s.creator_on;
    p[390] = s.enable_creator as u8;
    let mut c = vec![0u8; 236];
    put(&mut c, 0, &L::DISC_AMM_CONFIG);
    put_u64(&mut c, 12, s.trade);
    put_u64(&mut c, 20, 120_000);
    put_u64(&mut c, 28, 40_000);
    put_u64(&mut c, 108, s.creator);
    let va = token_account(v0, m0, pk, s.r0 + s.owed0, false);
    let vb = token_account(v1, m1, pk, s.r1 + s.owed1, false);
    let (ma, mb) = (mint(m0, 0, false, None), mint(m1, 0, false, None));
    let pool = Acct { key: pk, owner: L::RAY_CPMM, data: p };
    let cfg = Acct { key: ck, owner: L::RAY_CPMM, data: c };
    if zfo { vec![pool, cfg, va, vb, ma, mb] } else { vec![pool, cfg, vb, va, mb, ma] }
}

/* --------------------------------------------- AMM v4 --------------------------------------------- */

pub fn ammv4(rng: &mut Rng, coin: u64, pc: u64, num: u64, den: u64, coin_mint: Pk, pc_mint: Pk) -> Vec<Acct> {
    let (pk, cv, pv) = (rng.key(), rng.key(), rng.key());
    let mut a = vec![0u8; 752];
    put_u64(&mut a, 0, 6);
    put_u64(&mut a, 176, num);
    put_u64(&mut a, 184, den);
    put(&mut a, 336, &cv);
    put(&mut a, 368, &pv);
    put(&mut a, 400, &coin_mint);
    put(&mut a, 432, &pc_mint);
    vec![Acct { key: pk, owner: L::RAY_AMM_V4, data: a }, token_account(cv, coin_mint, pk, coin, false), token_account(pv, pc_mint, pk, pc, false)]
}

/* ----------------------------------------------- DLMM ----------------------------------------------- */

#[derive(Clone, Debug)]
pub struct DlmmSpec {
    pub bin_step: u16,
    pub base_factor: u16,
    pub power: u8,
    pub vfc: u32,
    pub max_va: u32,
    pub va: u32,
    pub v_ref: u32,
    pub idx_ref: i32,
    pub last_ts: i64,
    pub filter: u16,
    pub decay: u16,
    pub reduction: u16,
    pub active: i32,
    pub function_type: u8,
    pub collect_fee_mode: u8,
    /// the pair's own bin-id bounds (StaticParameters @24/@28)
    pub min_bin: i32,
    pub max_bin: i32,
    /// bins: id -> (amount_x, amount_y, (open, processed, ask))
    pub bins: Vec<(i32, u64, u64, (u64, u64, u8))>,
}

impl Default for DlmmSpec {
    fn default() -> Self {
        DlmmSpec { bin_step: 100, base_factor: 20_000, power: 0, vfc: 7_500, max_va: 150_000, va: 0, v_ref: 0, idx_ref: 0, last_ts: 0,
            filter: 300, decay: 1200, reduction: 5000, active: 0, function_type: 2, collect_fee_mode: 0, min_bin: -443_636, max_bin: 443_636, bins: vec![] }
    }
}

/// Q64.64 price of a bin: (1 + bin_step/1e4)^id
pub fn dlmm_price(bin_step: u16, id: i32) -> u128 {
    let p = (1.0 + bin_step as f64 / 10_000.0).powi(id);
    (p * 18446744073709551616.0) as u128
}

/// (lb_pair, mint_x, mint_y, every bin array holding a bin of the spec) — arrays in index order
pub fn dlmm(rng: &mut Rng, s: &DlmmSpec, mx: Pk, my: Pk) -> (Acct, Acct, Acct, Vec<Acct>) {
    let pk = rng.key();
    let mut p = vec![0u8; 904];
    put(&mut p, 0, &L::DISC_LB_PAIR);
    put(&mut p, 8, &s.base_factor.to_le_bytes());
    put(&mut p, 10, &s.filter.to_le_bytes());
    put(&mut p, 12, &s.decay.to_le_bytes());
    put(&mut p, 14, &s.reduction.to_le_bytes());
    put(&mut p, 16, &s.vfc.to_le_bytes());
    put(&mut p, 20, &s.max_va.to_le_bytes());
    put(&mut p, 24, &s.min_bin.to_le_bytes());
    put(&mut p, 28, &s.max_bin.to_le_bytes());
    p[34] = s.power;
    p[35] = s.function_type;
    p[36] = s.collect_fee_mode;
    put(&mut p, 40, &s.va.to_le_bytes());
    put(&mut p, 44, &s.v_ref.to_le_bytes());
    put(&mut p, 48, &s.idx_ref.to_le_bytes());
    put(&mut p, 56, &s.last_ts.to_le_bytes());
    p[75] = 3;
    put(&mut p, 76, &s.active.to_le_bytes());
    put(&mut p, 80, &s.bin_step.to_le_bytes());
    put(&mut p, 88, &mx);
    put(&mut p, 120, &my);
    p[882] = 1;
    let mut arrays: std::collections::BTreeMap<i64, Vec<u8>> = Default::default();
    for &(id, ax, ay, (open, processed, ask)) in &s.bins {
        let idx = (id as i64).div_euclid(70);
        let a = arrays.entry(idx).or_insert_with(|| {
            let mut a = vec![0u8; 10_136];
            put(&mut a, 0, &L::DISC_BIN_ARRAY);
            put(&mut a, 8, &idx.to_le_bytes());
            a[16] = 2;
            put(&mut a, 24, &pk);
            for k in 0..70 { put(&mut a, 56 + k * 144 + 16, &dlmm_price(s.bin_step, (idx * 70 + k as i64) as i32).to_le_bytes()); }
            a
        });
        let o = 56 + (id as i64 - idx * 70) as usize * 144;
        put_u64(a, o, ax);
        put_u64(a, o + 8, ay);
        put_u64(a, o + 112, open);
        put_u64(a, o + 128, processed);
        a[o + 140] = ask;
    }
    // bitmap: arrays with any liquidity (amounts or limit orders)
    for (idx, a) in &arrays {
        let any = (0..70).any(|k| { let o = 56 + k * 144; a[o..o + 16].iter().any(|&b| b != 0) || a[o + 112..o + 136].iter().any(|&b| b != 0) });
        if any && (-512..512).contains(idx) {
            let bit = (*idx + 512) as usize;
            p[584 + bit / 8] |= 1 << (bit % 8);
        }
    }
    let arrs = arrays.into_iter().map(|(_, d)| Acct { key: rng.key(), owner: L::DLMM, data: d }).collect();
    (Acct { key: pk, owner: L::DLMM, data: p }, mint(mx, 0, false, None), mint(my, 0, false, None), arrs)
}

/// A DLMM leg's state accounts in the swap's array order: the active bin's array first, then onward in the swap
/// direction, at most 5 (the engine's rule; arrays behind the active one are not passed)
pub fn dlmm_state(pair: &Acct, mx: &Acct, my: &Acct, arrays: &[Acct], swap_for_y: bool) -> Vec<Acct> {
    let active = i32::from_le_bytes(pair.data[76..80].try_into().unwrap());
    let ai = (active as i64).div_euclid(70);
    let idx = |x: &Acct| i64::from_le_bytes(x.data[8..16].try_into().unwrap());
    let mut a: Vec<Acct> = arrays.iter().filter(|x| if swap_for_y { idx(x) <= ai } else { idx(x) >= ai }).cloned().collect();
    a.sort_by_key(idx);
    if swap_for_y { a.reverse(); }
    let mut v = vec![pair.clone(), mx.clone(), my.clone()];
    v.extend(a.into_iter().take(5));
    v
}

/* ------------------------------------------- harness ------------------------------------------- */

pub fn pda(seeds: &[&[u8]], program: &[u8; 32]) -> Option<[u8; 32]> { create_program_address(seeds, program) }

pub const CLOCK: Clock = Clock { slot: 453_207_209, unix_timestamp: 1_791_103_719, epoch: 1049 };

/// An owned leg: descriptor, state accounts, input mint
#[derive(Clone, Debug)]
pub struct OwnedLeg { pub desc: LegDesc, pub state: Vec<Acct>, pub input_mint: Pk }

impl OwnedLeg {
    pub fn new(kind: Kind, token0_in: bool, state: Vec<Acct>, input_mint: Pk) -> Self {
        let mut desc = LegDesc::new(kind, token0_in);
        // DLMM: every passed array, and the largest walk budget the descriptor allows
        if kind == Kind::Dlmm { desc.n_bin_arrays = (state.len() - 3) as u8; desc.max_bins = u8::MAX; }
        OwnedLeg { desc, state, input_mint }
    }
    pub fn pump(p: &PumpAccts, sell: bool) -> Self {
        let mut l = OwnedLeg::new(if sell { Kind::PumpSell } else { Kind::PumpBuy }, sell, p.state(), if sell { p.base_key() } else { p.quote_key() });
        l.desc.pump_bump = p.bump;
        l
    }
}

/// Borrowed views of owned legs, held together so `LegIn`s can point into them
pub struct Views<'a> { pub refs: Vec<Vec<AcctRef<'a>>> }

pub fn views(legs: &[OwnedLeg]) -> Views<'_> { Views { refs: legs.iter().map(|l| l.state.iter().map(|a| a.view()).collect()).collect() } }

pub fn leg_ins<'a>(legs: &'a [OwnedLeg], v: &'a Views<'a>) -> Vec<LegIn<'a>> {
    legs.iter().zip(&v.refs).map(|(l, r)| LegIn { desc: l.desc, program: l.desc.kind.program(), state: r, input_mint: &l.input_mint }).collect()
}

/// Parse one owned leg into an AnyLeg (panics on DescError / Abort)
pub fn any_leg<'a>(l: &'a OwnedLeg, refs: &'a [AcctRef<'a>]) -> arbx_sizing::AnyLeg<'a> {
    let li = LegIn { desc: l.desc, program: l.desc.kind.program(), state: refs, input_mint: &l.input_mint };
    arbx_sizing::AnyLeg::parse(&li, &CLOCK, pda).expect("desc").leg.expect("abort")
}

/* --------------------------------------------- fixtures --------------------------------------------- */

pub fn b64(s: &str) -> Vec<u8> {
    use base64::Engine;
    base64::engine::general_purpose::STANDARD.decode(s).unwrap()
}

pub fn hexkey(s: &str) -> Pk {
    let mut k = [0u8; 32];
    for i in 0..32 { k[i] = u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap(); }
    k
}

pub struct Mainnet { pub v: serde_json::Value }

impl Mainnet {
    pub fn load() -> Self { Self::load_from(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/mainnet-accounts.json")) }
    pub fn load_from(path: &str) -> Self { Mainnet { v: serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap() } }
    pub fn clock(&self) -> Clock {
        let c = &self.v["clock"];
        Clock { slot: c["slot"].as_u64().unwrap(), unix_timestamp: c["unix_timestamp"].as_i64().unwrap(), epoch: c["epoch"].as_u64().unwrap() }
    }
    pub fn acct(&self, b58: &str) -> Acct {
        let a = &self.v["accounts"][b58];
        assert!(!a.is_null(), "fixture missing {b58}");
        Acct { key: hexkey(a["hex"].as_str().unwrap()), owner: hexkey(a["owner_hex"].as_str().unwrap()), data: b64(a["data"].as_str().unwrap()) }
    }
    pub fn pool(&self, name: &str) -> &serde_json::Value { &self.v["pools"][name] }
    pub fn state(&self, name: &str) -> Vec<Acct> {
        self.pool(name)["state"].as_array().unwrap().iter().map(|k| self.acct(k.as_str().unwrap())).collect()
    }
}
