//! Compiled-in constants: program ids, constant config keys, discriminators, and the default positions of each
//! kind's state accounts inside the leg's own account list (DESIGN.md §4.3). The defaults equal the engine's leg
//! builder (`src/build.rs::leg`); the engine and this crate share them through this module.
use crate::desc::{Kind, LegDesc};
use crate::error::{DescCode, DescError};

/// pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA
pub const PUMPSWAP: [u8; 32] = [12, 20, 222, 252, 130, 94, 198, 118, 148, 37, 8, 24, 187, 101, 64, 101, 244, 41, 141, 49, 86, 213, 113, 180, 212, 248, 9, 12, 24, 233, 168, 99];
/// ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw (PumpSwap GlobalConfig = PDA["global_config"])
pub const PUMP_GLOBAL_CONFIG: [u8; 32] = [137, 11, 166, 68, 254, 31, 85, 170, 25, 241, 28, 210, 210, 236, 20, 211, 35, 59, 110, 10, 75, 234, 238, 247, 43, 105, 133, 142, 33, 225, 112, 214];
/// 5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx (FeeConfig = PDA["fee_config", PumpSwap] under the pump fee program)
pub const PUMP_FEE_CONFIG: [u8; 32] = [65, 36, 110, 204, 125, 120, 254, 129, 228, 23, 115, 164, 105, 101, 65, 153, 55, 146, 58, 7, 100, 71, 151, 223, 111, 62, 181, 20, 66, 96, 16, 203];
/// pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ
pub const PUMP_FEE_PROGRAM: [u8; 32] = [12, 53, 255, 169, 5, 90, 142, 86, 141, 168, 247, 188, 7, 86, 21, 39, 76, 241, 201, 44, 164, 31, 64, 0, 156, 81, 106, 164, 20, 194, 124, 112];
/// 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P (pump.fun: the canonical pool-authority PDA's program)
pub const PUMP_FUN: [u8; 32] = [1, 86, 224, 246, 147, 102, 90, 207, 68, 219, 21, 104, 191, 23, 91, 170, 81, 137, 203, 151, 245, 210, 255, 59, 101, 93, 43, 182, 253, 109, 24, 176];
/// CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C
pub const RAY_CPMM: [u8; 32] = [169, 42, 90, 139, 79, 41, 89, 82, 132, 37, 80, 170, 147, 253, 91, 149, 181, 172, 230, 168, 235, 146, 12, 147, 148, 46, 67, 105, 12, 32, 236, 115];
/// 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
pub const RAY_AMM_V4: [u8; 32] = [75, 217, 73, 196, 54, 2, 195, 63, 32, 119, 144, 237, 22, 163, 82, 76, 161, 185, 151, 92, 241, 33, 162, 169, 12, 255, 236, 125, 248, 182, 138, 205];
/// LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo
pub const DLMM: [u8; 32] = [4, 233, 225, 47, 188, 132, 232, 38, 201, 50, 204, 233, 226, 100, 12, 206, 21, 89, 12, 28, 98, 115, 176, 146, 87, 8, 186, 59, 133, 32, 176, 188];
/// cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG
pub const DAMM_V2: [u8; 32] = [9, 45, 33, 53, 101, 122, 21, 156, 43, 135, 212, 182, 106, 112, 219, 142, 151, 82, 56, 159, 247, 106, 175, 32, 108, 237, 6, 58, 56, 249, 90, 237];
/// TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
pub const TOKEN_PROGRAM: [u8; 32] = [6, 221, 246, 225, 215, 101, 161, 147, 217, 203, 225, 70, 206, 235, 121, 172, 28, 180, 133, 237, 95, 91, 55, 145, 58, 140, 245, 133, 126, 255, 0, 169];
/// TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb
pub const TOKEN_2022: [u8; 32] = [6, 221, 246, 225, 238, 117, 143, 222, 24, 66, 93, 188, 228, 108, 205, 218, 182, 26, 252, 77, 131, 185, 13, 39, 254, 189, 249, 40, 216, 161, 139, 252];
/// So11111111111111111111111111111111111111112
pub const WSOL: [u8; 32] = [6, 155, 136, 87, 254, 171, 129, 132, 251, 104, 127, 99, 70, 24, 192, 53, 218, 196, 57, 220, 26, 235, 59, 85, 152, 160, 240, 0, 0, 0, 0, 1];
/// 9pan9bMn5HatX4EJdBwg9VgCa7Uz5HL8N1m5D3NdXejP (Token-2022 native mint)
pub const T22_NATIVE: [u8; 32] = [131, 13, 252, 159, 222, 95, 230, 184, 170, 124, 4, 164, 118, 233, 30, 138, 198, 187, 38, 74, 173, 144, 250, 25, 201, 223, 73, 216, 92, 62, 91, 94];
/// EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
pub const USDC: [u8; 32] = [198, 250, 122, 243, 190, 219, 173, 58, 61, 101, 243, 106, 171, 201, 116, 49, 177, 187, 228, 194, 210, 246, 224, 228, 124, 166, 2, 3, 69, 47, 93, 97];

/// sha256("account:Pool")[..8]: PumpSwap Pool and DAMM v2 Pool
pub const DISC_POOL: [u8; 8] = [241, 154, 109, 4, 17, 177, 109, 188];
/// sha256("account:GlobalConfig")[..8] (PumpSwap)
pub const DISC_GLOBAL_CONFIG: [u8; 8] = [149, 8, 156, 202, 160, 252, 176, 217];
/// sha256("account:FeeConfig")[..8] (pump fee program)
pub const DISC_FEE_CONFIG: [u8; 8] = [143, 52, 146, 187, 219, 123, 76, 155];
/// sha256("account:PoolState")[..8] (Raydium CPMM)
pub const DISC_POOL_STATE: [u8; 8] = [247, 237, 227, 245, 215, 195, 222, 70];
/// sha256("account:AmmConfig")[..8] (Raydium CPMM)
pub const DISC_AMM_CONFIG: [u8; 8] = [218, 244, 33, 104, 203, 203, 43, 111];
/// sha256("account:LbPair")[..8]
pub const DISC_LB_PAIR: [u8; 8] = [33, 11, 49, 98, 181, 101, 177, 13];
/// sha256("account:BinArray")[..8]
pub const DISC_BIN_ARRAY: [u8; 8] = [92, 142, 92, 220, 5, 148, 70, 181];

/// arbx-exec allowlist indexes (ALLOWLIST_B58 order; append-only there)
pub const ALLOW_DLMM: u8 = 0;
pub const ALLOW_PUMPSWAP: u8 = 3;
pub const ALLOW_CPMM: u8 = 6;
pub const ALLOW_AMM_V4: u8 = 7;
pub const ALLOW_DAMM_V2: u8 = 8;

/// Default positions (index into the leg's own account list, i.e. after the output account and the program), in
/// the kind's state order. DLMM lists lb_pair, mint_x, mint_y and the first bin array; the arrays follow it.
pub const POS_PUMP_BUY: [u8; 7] = [0, 2, 3, 4, 7, 8, 21];
pub const POS_PUMP_SELL: [u8; 7] = [0, 2, 3, 4, 7, 8, 19];
pub const POS_CPMM: [u8; 6] = [3, 2, 6, 7, 10, 11];
pub const POS_AMM_V4: [u8; 3] = [1, 3, 4];
pub const POS_DLMM: [u8; 4] = [0, 6, 7, 16];
pub const POS_DAMM_V2: [u8; 3] = [1, 6, 7];

/// The leg accounts each kind's engine layout has (DESIGN.md §1.2; PumpSwap: without its variable tail)
pub const fn min_leg_accounts(k: Kind) -> usize {
    match k { Kind::PumpBuy => 23, Kind::PumpSell => 21, Kind::RayCpmm => 13, Kind::RayAmmV4 => 8, Kind::Dlmm => 17, Kind::DammV2 => 14 }
}

/// The default position list of a kind (EXPLICIT_POS gives the same number of entries)
pub const fn default_positions(k: Kind) -> &'static [u8] {
    match k {
        Kind::PumpBuy => &POS_PUMP_BUY,
        Kind::PumpSell => &POS_PUMP_SELL,
        Kind::RayCpmm => &POS_CPMM,
        Kind::RayAmmV4 => &POS_AMM_V4,
        Kind::Dlmm => &POS_DLMM,
        Kind::DammV2 => &POS_DAMM_V2,
    }
}

/// Max state accounts of one leg: DLMM 3 + 5 bin arrays; PumpSwap 7
pub const MAX_STATE: usize = 8;

/// The positions of a leg's state accounts, in the kind's state order (DLMM: lb_pair, mint_x, mint_y, then every bin
/// array). A fixed-capacity list: no allocation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Positions { buf: [u8; MAX_STATE], len: u8 }

impl Positions {
    pub fn as_slice(&self) -> &[u8] { self.buf.get(..self.len as usize).unwrap_or(&[]) }
    pub fn len(&self) -> usize { self.len as usize }
    pub fn is_empty(&self) -> bool { self.len == 0 }
}

impl IntoIterator for Positions {
    type Item = u8;
    type IntoIter = core::iter::Take<core::array::IntoIter<u8, MAX_STATE>>;
    fn into_iter(self) -> Self::IntoIter { self.buf.into_iter().take(self.len as usize) }
}

/// The leg's state-account positions: the explicit list when the descriptor carries one, else the defaults; DLMM's
/// bin arrays expanded from the first one. Positions above 255 (an explicit first bin array near the top) are
/// refused as `DescCode::Position`.
pub fn positions(d: &LegDesc) -> Result<Positions, DescError> {
    let base: &[u8] = match &d.positions { Some(p) => p.get(..d.kind.n_positions()).unwrap_or(&[]), None => default_positions(d.kind) };
    let mut out = Positions { buf: [0; MAX_STATE], len: 0 };
    let push = |out: &mut Positions, v: u8| -> Result<(), DescError> {
        let slot = out.buf.get_mut(out.len as usize).ok_or(DescError::block(DescCode::Position))?;
        *slot = v;
        out.len += 1;
        Ok(())
    };
    if d.kind == Kind::Dlmm {
        let first = *base.get(3).ok_or(DescError::block(DescCode::PosCount))?;
        for &p in base.get(..3).unwrap_or(&[]) { push(&mut out, p)?; }
        for i in 0..d.n_bin_arrays {
            let p = first.checked_add(i).ok_or(DescError::block(DescCode::Position))?;
            push(&mut out, p)?;
        }
    } else {
        for &p in base { push(&mut out, p)?; }
    }
    Ok(out)
}

/// Every position must address one of the leg's `n_accounts` accounts (the shell calls this before resolving them)
pub fn check_positions(d: &LegDesc, n_accounts: usize) -> Result<Positions, DescError> {
    let p = positions(d)?;
    if p.as_slice().iter().any(|&i| i as usize >= n_accounts) { return Err(DescError::block(DescCode::Position)); }
    Ok(p)
}
