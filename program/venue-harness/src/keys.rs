//! Program ids, constant accounts and PDA helpers shared by the fetcher and the loader.
use solana_address::Address;

pub const PUMPSWAP: Address = Address::from_str_const("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA");
pub const PUMP_FEE_PROGRAM: Address = Address::from_str_const("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ");
pub const PUMP_FUN: Address = Address::from_str_const("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P");
pub const RAYCPMM: Address = Address::from_str_const("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C");
pub const RAYAMMV4: Address = Address::from_str_const("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8");
pub const DLMM: Address = Address::from_str_const("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo");
pub const DAMMV2: Address = Address::from_str_const("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG");

pub const TOKEN: Address = Address::from_str_const("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
pub const TOKEN_2022: Address = Address::from_str_const("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");
pub const ATA_PROGRAM: Address = Address::from_str_const("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL");
pub const SYSTEM: Address = Address::from_str_const("11111111111111111111111111111111");
pub const MEMO: Address = Address::from_str_const("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr");
pub const COMPUTE_BUDGET: Address = Address::from_str_const("ComputeBudget111111111111111111111111111111");
pub const WSOL: Address = Address::from_str_const("So11111111111111111111111111111111111111112");
pub const CLOCK_SYSVAR: Address = Address::from_str_const("SysvarC1ock11111111111111111111111111111111");
pub const RENT_SYSVAR: Address = Address::from_str_const("SysvarRent111111111111111111111111111111111");
pub const BPF_LOADER_2: Address = Address::from_str_const("BPFLoader2111111111111111111111111111111111");
pub const BPF_LOADER_UPGRADEABLE: Address = Address::from_str_const("BPFLoaderUpgradeab1e11111111111111111111111");

pub const PUMP_GLOBAL_CONFIG: Address = Address::from_str_const("ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw");
pub const PUMP_EVENT_AUTHORITY: Address = Address::from_str_const("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR");
pub const PUMP_GLOBAL_VOLUME_ACCUMULATOR: Address = Address::from_str_const("C2aFPdENg4A2HQsmrd5rTw5TaYBX5Ku887cWjbFKtZpw");
pub const PUMP_FEE_CONFIG: Address = Address::from_str_const("5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx");
pub const RAYCPMM_AUTHORITY: Address = Address::from_str_const("GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL");
pub const DLMM_EVENT_AUTHORITY: Address = Address::from_str_const("D1ZN9Wj1fRSUQfCjhvnu1hqDMT7hzjzBBpi12nVniYD6");
pub const DAMMV2_POOL_AUTHORITY: Address = Address::from_str_const("HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC");
pub const DAMMV2_EVENT_AUTHORITY: Address = Address::from_str_const("3rmHSu74h1ZcmAisVcWerTCiRDQbUrBKmcwptYGjHfet");

/// Every program the harness loads from `fixtures/programs` (venue programs, the pump fee program PumpSwap passes,
/// and mainnet's own token / ATA programs so CU matches mainnet; LiteSVM's bundled copies are the fallback).
pub const PROGRAMS: &[(&str, Address)] = &[
    ("PumpSwap", PUMPSWAP),
    ("PumpFees", PUMP_FEE_PROGRAM),
    ("RayCPMM", RAYCPMM),
    ("RayAMMv4", RAYAMMV4),
    ("DLMM", DLMM),
    ("DAMMv2", DAMMV2),
    ("SplToken", TOKEN),
    ("Token2022", TOKEN_2022),
    ("AssociatedToken", ATA_PROGRAM),
];

/// Program accounts never snapshotted as plain accounts (they are loaded as programs or are LiteSVM builtins).
pub fn is_program(k: &Address) -> bool {
    PROGRAMS.iter().any(|(_, p)| p == k) || [SYSTEM, MEMO, COMPUTE_BUDGET, BPF_LOADER_2, BPF_LOADER_UPGRADEABLE].contains(k)
}

pub fn pda(seeds: &[&[u8]], program: &Address) -> (Address, u8) { Address::find_program_address(seeds, program) }

pub fn ata(owner: &Address, mint: &Address, token_program: &Address) -> Address {
    pda(&[owner.as_ref(), token_program.as_ref(), mint.as_ref()], &ATA_PROGRAM).0
}

pub fn dlmm_bin_array(pair: &Address, index: i64) -> Address {
    pda(&[b"bin_array", pair.as_ref(), &index.to_le_bytes()], &DLMM).0
}
pub fn dlmm_bitmap_extension(pair: &Address) -> Address { pda(&[b"bitmap", pair.as_ref()], &DLMM).0 }
/// DLMM bin array index of a bin (70 bins per array, floor division)
pub fn dlmm_array_index(bin: i32) -> i64 { (bin as i64).div_euclid(70) }

/// The fixed test wallet (deterministic, so every user-derived PDA is stable across runs). Test-only key: it never
/// holds anything outside LiteSVM.
pub fn test_user() -> solana_keypair::Keypair { solana_keypair::Keypair::new_from_array([0x5a; 32]) }

pub fn b58(a: &Address) -> String { a.to_string() }
pub fn parse(s: &str) -> Result<Address, String> { s.trim().parse::<Address>().map_err(|e| format!("bad address {s}: {e}")) }
