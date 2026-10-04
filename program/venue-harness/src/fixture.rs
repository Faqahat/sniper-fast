//! On-disk fixtures: program binaries (`fixtures/programs/<id>.so` + `MANIFEST.json`) and one JSON snapshot per pool
//! (`fixtures/pools/<venue>-<pool>.json`). A pool snapshot holds every account its swap instruction reads, taken by
//! ONE getMultipleAccounts call together with the Clock sysvar, so the accounts and the clock are from the same slot.
use crate::keys;
use crate::venues::Venue;
use base64::Engine as _;
use serde::{Deserialize, Serialize};
use solana_account::Account;
use solana_address::Address;
use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};

pub const DIR: &str = env!("CARGO_MANIFEST_DIR");
pub fn fixtures_dir() -> PathBuf { PathBuf::from(DIR).join("fixtures") }

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AccountSnap {
    pub pubkey: String,
    pub lamports: u64,
    pub owner: String,
    pub executable: bool,
    pub rent_epoch: u64,
    /// base64
    pub data: String,
}

impl AccountSnap {
    pub fn to_account(&self) -> Result<(Address, Account), String> {
        let data = base64::engine::general_purpose::STANDARD.decode(&self.data).map_err(|e| format!("{}: {e}", self.pubkey))?;
        Ok((keys::parse(&self.pubkey)?, Account { lamports: self.lamports, data, owner: keys::parse(&self.owner)?, executable: self.executable, rent_epoch: self.rent_epoch }))
    }
    pub fn from_account(k: &Address, a: &Account) -> Self {
        AccountSnap { pubkey: k.to_string(), lamports: a.lamports, owner: a.owner.to_string(), executable: a.executable, rent_epoch: a.rent_epoch,
            data: base64::engine::general_purpose::STANDARD.encode(&a.data) }
    }
}

/// The Clock sysvar as fetched (bincode layout: slot, epoch_start_timestamp, epoch, leader_schedule_epoch, unix_timestamp).
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct ClockSnap { pub slot: u64, pub epoch_start_timestamp: i64, pub epoch: u64, pub leader_schedule_epoch: u64, pub unix_timestamp: i64 }

impl ClockSnap {
    pub fn decode(d: &[u8]) -> Option<Self> {
        let u = |o: usize| d.get(o..o + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap()));
        Some(ClockSnap { slot: u(0)?, epoch_start_timestamp: u(8)? as i64, epoch: u(16)?, leader_schedule_epoch: u(24)?, unix_timestamp: u(32)? as i64 })
    }
    pub fn to_clock(&self) -> solana_clock::Clock {
        solana_clock::Clock { slot: self.slot, epoch_start_timestamp: self.epoch_start_timestamp, epoch: self.epoch,
            leader_schedule_epoch: self.leader_schedule_epoch, unix_timestamp: self.unix_timestamp }
    }
}

/// The Rent sysvar as fetched (mainnet lowered rent after LiteSVM's default; accounts created on chain since then
/// hold less than LiteSVM's default minimum, and Anchor's rent-exempt constraints would refuse them).
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
pub struct RentSnap { pub lamports_per_byte: u64, pub exemption_threshold: f64, pub burn_percent: u8 }

impl RentSnap {
    pub fn decode(d: &[u8]) -> Option<Self> {
        Some(RentSnap { lamports_per_byte: u64::from_le_bytes(d.get(0..8)?.try_into().ok()?),
            exemption_threshold: f64::from_le_bytes(d.get(8..16)?.try_into().ok()?), burn_percent: *d.get(16)? })
    }
    #[allow(deprecated)]
    pub fn to_rent(&self) -> solana_rent::Rent {
        solana_rent::Rent { lamports_per_byte: self.lamports_per_byte, exemption_threshold: self.exemption_threshold.to_le_bytes(), burn_percent: self.burn_percent }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PoolFixture {
    pub venue: Venue,
    pub pool: String,
    pub label: String,
    pub fetched_at: String,
    /// context slot of the snapshot call
    pub slot: u64,
    pub clock: ClockSnap,
    /// the Rent sysvar at the same slot (None in fixtures fetched before it was recorded: LiteSVM's default applies)
    #[serde(default)]
    pub rent: Option<RentSnap>,
    /// token 0 / token 1 in the program's own order (PumpSwap base/quote, CPMM mint0/mint1, AMM v4 coin/pc, DLMM x/y,
    /// DAMM v2 a/b)
    pub token0: String,
    pub token1: String,
    /// every account the swap instructions (both directions, the harness's test user) read that exists on chain
    pub accounts: Vec<AccountSnap>,
    /// keys the instructions name that did not exist at the snapshot (PDAs created on demand, event authorities, ...)
    pub absent: Vec<String>,
    /// free-form facts recorded by the fetcher (DLMM: active id, bin arrays fetched; PumpSwap: canonical, ...)
    #[serde(default)]
    pub notes: BTreeMap<String, serde_json::Value>,
}

/// Overwrite `bytes` at `offset` in account `key`'s data (state mutation; the account must be in the snapshot)
#[derive(Clone, Debug)]
pub struct Patch { pub key: Address, pub offset: usize, pub bytes: Vec<u8> }

impl Patch {
    pub fn new(key: Address, offset: usize, bytes: &[u8]) -> Self { Patch { key, offset, bytes: bytes.to_vec() } }
}

impl PoolFixture {
    pub fn apply(&mut self, patches: &[Patch]) -> Result<(), String> {
        for p in patches {
            let k = p.key.to_string();
            let a = self.accounts.iter_mut().find(|a| a.pubkey == k).ok_or(format!("patch: {k} not in the snapshot"))?;
            let (key, mut acc) = a.to_account()?;
            let end = p.offset + p.bytes.len();
            if end > acc.data.len() { return Err(format!("patch: {k} [{}..{end}] beyond {} bytes", p.offset, acc.data.len())); }
            acc.data[p.offset..end].copy_from_slice(&p.bytes);
            *a = AccountSnap::from_account(&key, &acc);
        }
        Ok(())
    }

    pub fn pool_key(&self) -> Address { keys::parse(&self.pool).unwrap() }
    pub fn token0_key(&self) -> Address { keys::parse(&self.token0).unwrap() }
    pub fn token1_key(&self) -> Address { keys::parse(&self.token1).unwrap() }
    pub fn account_map(&self) -> Result<HashMap<Address, Account>, String> {
        self.accounts.iter().map(|a| a.to_account()).collect()
    }
    pub fn load(path: &Path) -> Result<Self, String> {
        let s = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        serde_json::from_str(&s).map_err(|e| format!("{}: {e}", path.display()))
    }
    pub fn file_name(venue: Venue, pool: &Address) -> String { format!("{}-{}.json", venue.name(), pool) }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProgramEntry {
    pub name: String,
    pub program_id: String,
    /// owner of the program account: BPFLoader2 (ELF in the program account) or BPFLoaderUpgradeable
    pub loader: String,
    /// upgradeable programs: the ProgramData account and its last-deploy slot
    pub programdata: Option<String>,
    pub last_deploy_slot: Option<u64>,
    pub upgrade_authority: Option<String>,
    /// file under fixtures/programs: the ELF as stored on chain, cut at the ELF's own extent (the zero padding an
    /// upgradeable program carries up to its max length is dropped; `onchain_*` describe the untrimmed bytes)
    pub file: String,
    pub size: usize,
    pub sha256: String,
    #[serde(default)]
    pub onchain_size: usize,
    #[serde(default)]
    pub onchain_sha256: String,
    pub fetched_at: String,
    /// context slot of the fetch
    pub slot: u64,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Manifest { pub programs: Vec<ProgramEntry> }

impl Manifest {
    pub fn path() -> PathBuf { fixtures_dir().join("programs").join("MANIFEST.json") }
    pub fn load() -> Result<Self, String> {
        let p = Self::path();
        if !p.exists() { return Ok(Manifest::default()); }
        serde_json::from_str(&std::fs::read_to_string(&p).map_err(|e| e.to_string())?).map_err(|e| format!("{}: {e}", p.display()))
    }
    pub fn save(&self) -> Result<(), String> {
        std::fs::write(Self::path(), serde_json::to_string_pretty(self).unwrap() + "\n").map_err(|e| e.to_string())
    }
    pub fn get(&self, id: &Address) -> Option<&ProgramEntry> { self.programs.iter().find(|p| p.program_id == id.to_string()) }
}

/// Everything under fixtures/: the programs and every pool snapshot (keyed by pool address).
pub struct Fixtures {
    pub manifest: Manifest,
    pub pools: BTreeMap<Address, PoolFixture>,
}

impl Fixtures {
    pub fn load() -> Result<Self, String> { Self::load_from(&fixtures_dir()) }
    pub fn load_from(dir: &Path) -> Result<Self, String> {
        let manifest = Manifest::load()?;
        let mut pools = BTreeMap::new();
        let pdir = dir.join("pools");
        if pdir.exists() {
            let mut files: Vec<PathBuf> = std::fs::read_dir(&pdir).map_err(|e| e.to_string())?
                .filter_map(|e| e.ok().map(|e| e.path())).filter(|p| p.extension().is_some_and(|x| x == "json")).collect();
            files.sort();
            for f in files {
                let fx = PoolFixture::load(&f)?;
                pools.insert(fx.pool_key(), fx);
            }
        }
        Ok(Fixtures { manifest, pools })
    }
    pub fn pool(&self, k: &Address) -> Option<&PoolFixture> { self.pools.get(k) }
    /// the pool whose address starts with `prefix` (convenience for tests and the CLI)
    pub fn find(&self, prefix: &str) -> Option<&PoolFixture> { self.pools.values().find(|p| p.pool.starts_with(prefix) || p.label == prefix) }
}

pub fn program_elf(entry: &ProgramEntry) -> Result<Vec<u8>, String> {
    let p = fixtures_dir().join("programs").join(&entry.file);
    std::fs::read(&p).map_err(|e| format!("{}: {e}", p.display()))
}

pub fn sha256_hex(b: &[u8]) -> String {
    use sha2::Digest;
    sha2::Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect()
}

/// End of the ELF image: the furthest of the section header table, every program header's file range and every
/// non-NOBITS section. Bytes after it are the programdata's zero padding.
pub fn elf_extent(d: &[u8]) -> Option<usize> {
    let u16_ = |o: usize| d.get(o..o + 2).map(|b| u16::from_le_bytes([b[0], b[1]]) as usize);
    let u32_ = |o: usize| d.get(o..o + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap()));
    let u64_ = |o: usize| d.get(o..o + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap()) as usize);
    if d.get(..4) != Some(b"\x7fELF") || d.get(4) != Some(&2) { return None; }
    let (phoff, shoff) = (u64_(32)?, u64_(40)?);
    let (phentsize, phnum, shentsize, shnum) = (u16_(54)?, u16_(56)?, u16_(58)?, u16_(60)?);
    let mut end = shoff + shnum * shentsize;
    for i in 0..phnum { let h = phoff + i * phentsize; end = end.max(u64_(h + 8)? + u64_(h + 32)?); }
    for i in 0..shnum {
        let h = shoff + i * shentsize;
        if u32_(h + 4)? != 8 { end = end.max(u64_(h + 24)? + u64_(h + 32)?); }
    }
    (end <= d.len()).then_some(end)
}
