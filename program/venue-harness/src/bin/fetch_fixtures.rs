//! Fixture fetcher (read-only public mainnet RPC, <= 2.5 req/s, everything cached on disk; nothing is ever sent).
//!
//!   cargo run --bin fetch-fixtures                 programs + every pool in fixtures/pool-list.json (skips cached)
//!   cargo run --bin fetch-fixtures -- --refresh    re-fetch everything
//!   cargo run --bin fetch-fixtures -- --programs   programs only        (--pools: pools only)
//!   cargo run --bin fetch-fixtures -- --check      upgrade watch: compare each program's last-deploy slot with the
//!                                                  manifest (45-byte header reads only; DESIGN §6.5)
//!   --rpc <url>                                    another read-only endpoint
//!
//! Programs: the program account, then (upgradeable loader) its ProgramData; the ELF is written to
//! fixtures/programs/<id>.so exactly as stored (after the 45-byte header, padding included) with MANIFEST.json.
//! Pools: three getMultipleAccounts calls: the pool (+ PumpSwap GlobalConfig), its mints (token programs), then every
//! account both swap directions name plus the Clock sysvar in ONE call, so the snapshot and the clock share a slot.
use serde::Deserialize;
use serde_json::json;
use solana_account::Account;
use solana_address::Address;
use solana_signer::Signer;
use std::collections::{BTreeMap, HashMap};
use venue_harness::fixture::{self, fixtures_dir, AccountSnap, ClockSnap, Manifest, PoolFixture, ProgramEntry, RentSnap};
use venue_harness::keys::{self, *};
use venue_harness::rpc::{now_utc, Rpc, MAINNET};
use venue_harness::venues::{self, *};

const LOADER_V4: Address = Address::from_str_const("LoaderV411111111111111111111111111111111111");

#[derive(Deserialize)]
struct PoolRow { venue: String, pool: String, label: String }

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let has = |f: &str| args.iter().any(|a| a == f);
    let url = args.iter().position(|a| a == "--rpc").and_then(|i| args.get(i + 1)).cloned().unwrap_or(MAINNET.into());
    let refresh = has("--refresh");
    let mut rpc = Rpc::new(&url);
    let res = if has("--check") { check_upgrades(&mut rpc) } else {
        let mut r = Ok(());
        if !has("--pools") { r = fetch_programs(&mut rpc, refresh); }
        if r.is_ok() && !has("--programs") { r = fetch_pools(&mut rpc, refresh); }
        r
    };
    eprintln!("{} RPC requests", rpc.requests);
    if let Err(e) = res { eprintln!("error: {e}"); std::process::exit(1); }
}

fn fetch_programs(rpc: &mut Rpc, refresh: bool) -> Result<(), String> {
    std::fs::create_dir_all(fixtures_dir().join("programs")).map_err(|e| e.to_string())?;
    let mut man = Manifest::load()?;
    for (name, id) in keys::PROGRAMS {
        let file = format!("{id}.so");
        let fpath = fixtures_dir().join("programs").join(&file);
        if !refresh && man.get(id).is_some() && fpath.exists() {
            // normalise an untrimmed cached dump (no RPC): record the on-chain size/hash, keep the ELF extent
            let d = std::fs::read(&fpath).map_err(|e| e.to_string())?;
            let end = fixture::elf_extent(&d).ok_or(format!("{name}: cached file is not an ELF"))?;
            if end < d.len() {
                if d[end..].iter().any(|b| *b != 0) { return Err(format!("{name}: non-zero bytes after the ELF extent")); }
                std::fs::write(&fpath, &d[..end]).map_err(|e| e.to_string())?;
                let e = man.programs.iter_mut().find(|p| p.program_id == id.to_string()).unwrap();
                (e.onchain_size, e.onchain_sha256) = (d.len(), fixture::sha256_hex(&d));
                (e.size, e.sha256) = (end, fixture::sha256_hex(&d[..end]));
                man.save()?;
                println!("program {name:<16} cached, trimmed {} -> {end} bytes", d.len());
            } else {
                let e = man.programs.iter_mut().find(|p| p.program_id == id.to_string()).unwrap();
                if e.onchain_size == 0 { (e.onchain_size, e.onchain_sha256) = (d.len(), fixture::sha256_hex(&d)); man.save()?; }
                println!("program {name:<16} cached");
            }
            continue;
        }
        let (slot, acc) = rpc.account(id)?;
        let acc = acc.ok_or(format!("{name}: program account not found"))?;
        if !acc.executable { return Err(format!("{name}: not executable")); }
        let (elf, programdata, deploy_slot, authority) = if acc.owner == BPF_LOADER_UPGRADEABLE {
            let pd = venues::pk_at(&acc.data, 4).ok_or("short program account")?;
            let (_, pda_acc) = rpc.account(&pd)?;
            let d = pda_acc.ok_or(format!("{name}: programdata {pd} not found"))?.data;
            if d.len() < 45 || d[..4] != [3, 0, 0, 0] { return Err(format!("{name}: bad programdata header")); }
            let auth = if d[12] == 1 { venues::pk_at(&d, 13).map(|k| k.to_string()) } else { None };
            (d[45..].to_vec(), Some(pd.to_string()), venues::u64_at(&d, 4), auth)
        } else if acc.owner == BPF_LOADER_2 || acc.owner.to_string().starts_with("BPFLoader1") {
            (acc.data.clone(), None, None, None)
        } else if acc.owner == LOADER_V4 {
            if acc.data.len() < 48 { return Err(format!("{name}: short loader-v4 account")); }
            (acc.data[48..].to_vec(), None, venues::u64_at(&acc.data, 0), venues::pk_at(&acc.data, 8).map(|k| k.to_string()))
        } else {
            return Err(format!("{name}: unknown loader {}", acc.owner));
        };
        let end = fixture::elf_extent(&elf).ok_or(format!("{name}: not an ELF"))?;
        if elf[end..].iter().any(|b| *b != 0) { return Err(format!("{name}: non-zero bytes after the ELF extent")); }
        std::fs::write(&fpath, &elf[..end]).map_err(|e| e.to_string())?;
        let e = ProgramEntry { name: name.to_string(), program_id: id.to_string(), loader: acc.owner.to_string(), programdata,
            last_deploy_slot: deploy_slot, upgrade_authority: authority, file, size: end, sha256: fixture::sha256_hex(&elf[..end]),
            onchain_size: elf.len(), onchain_sha256: fixture::sha256_hex(&elf), fetched_at: now_utc(), slot };
        println!("program {name:<16} {} bytes, loader {}, last deploy slot {:?}, sha256 {}", e.size, e.loader, e.last_deploy_slot, &e.sha256[..16]);
        man.programs.retain(|p| p.program_id != e.program_id);
        man.programs.push(e);
        man.save()?;
    }
    Ok(())
}

fn check_upgrades(rpc: &mut Rpc) -> Result<(), String> {
    let man = Manifest::load()?;
    let mut changed = 0;
    for p in &man.programs {
        let Some(pd) = &p.programdata else { println!("{:<16} (not upgradeable)", p.name); continue };
        let r = rpc.call("getAccountInfo", json!([pd, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 45}}]))?;
        let d = base64_decode(r["value"]["data"][0].as_str().unwrap_or(""));
        let slot = venues::u64_at(&d, 4);
        let same = slot == p.last_deploy_slot;
        if !same { changed += 1; }
        println!("{:<16} manifest {:?} chain {:?} {}", p.name, p.last_deploy_slot, slot, if same { "ok" } else { "UPGRADED: re-dump (--programs --refresh) and rerun the harness" });
    }
    if changed > 0 { Err(format!("{changed} program(s) upgraded since the dump")) } else { Ok(()) }
}

fn base64_decode(s: &str) -> Vec<u8> { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(s).unwrap_or_default() }

fn fetch_pools(rpc: &mut Rpc, refresh: bool) -> Result<(), String> {
    // the engine's venues (pool-list.json -> pools/) and WP-21's concentrated-liquidity venues (pool-list-clmm.json -> pools-clmm/)
    let mut rows: Vec<PoolRow> = serde_json::from_str(&std::fs::read_to_string(fixtures_dir().join("pool-list.json")).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let clmm = fixtures_dir().join("pool-list-clmm.json");
    if clmm.exists() {
        rows.extend(serde_json::from_str::<Vec<PoolRow>>(&std::fs::read_to_string(&clmm).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?);
    }
    for row in rows {
        let venue = Venue::parse(&row.venue).ok_or(format!("unknown venue {}", row.venue))?;
        let dir = fixtures_dir().join(fixture::pools_dir_name(venue));
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let pool = keys::parse(&row.pool)?;
        let path = dir.join(PoolFixture::file_name(venue, &pool));
        if !refresh && path.exists() { println!("pool {:<9} {} cached", venue.name(), row.pool); continue; }
        match fetch_pool(rpc, venue, &pool, &row.label) {
            Ok(fx) => {
                std::fs::write(&path, serde_json::to_string_pretty(&fx).unwrap() + "\n").map_err(|e| e.to_string())?;
                println!("pool {:<9} {} slot {} {} accounts ({} absent) -> {}", venue.name(), row.pool, fx.slot, fx.accounts.len(), fx.absent.len(),
                    path.file_name().unwrap().to_string_lossy());
            }
            Err(e) => println!("pool {:<9} {} SKIPPED: {e}", venue.name(), row.pool),
        }
    }
    Ok(())
}

fn put(view: &mut HashMap<Address, Account>, keys: &[Address], accs: Vec<Option<Account>>) {
    for (k, a) in keys.iter().zip(accs) { if let Some(a) = a { view.insert(*k, a); } }
}

fn fetch_pool(rpc: &mut Rpc, venue: Venue, pool: &Address, label: &str) -> Result<PoolFixture, String> {
    let user = keys::test_user().pubkey();
    // round 1: the pool (+ PumpSwap GlobalConfig, whose fee recipients the instruction names)
    let mut view: HashMap<Address, Account> = HashMap::new();
    let mut k1 = vec![*pool];
    if venue == Venue::PumpSwap { k1.push(PUMP_GLOBAL_CONFIG); }
    let (_, a) = rpc.multiple_accounts(&k1)?;
    put(&mut view, &k1, a);
    let pa = view.get(pool).ok_or("pool not found")?;
    if pa.owner != venue.program() { return Err(format!("owner {} is not {}", pa.owner, venue.name())); }
    let t = venues::pool_tokens(venue, &pa.data).ok_or("pool account too short")?;
    // round 2: the mints (their owners are the token programs the instruction and the ATAs use)
    let k2 = vec![t.t0, t.t1];
    let (_, a) = rpc.multiple_accounts(&k2)?;
    put(&mut view, &k2, a);
    // round 3+: everything, plus the Clock, in one call; repeat if the fresh state names a key we did not fetch
    let mut want = fixture_keys(venue, pool, &view, &user)?;
    for _ in 0..3 {
        let mut ks = want.clone();
        ks.push(RENT_SYSVAR);
        ks.push(CLOCK_SYSVAR);
        if ks.len() > 100 { return Err(format!("{} keys: more than one getMultipleAccounts", ks.len())); }
        let (slot, accs) = rpc.multiple_accounts(&ks)?;
        let clock_acc = accs.last().cloned().flatten().ok_or("no Clock")?;
        let clock = ClockSnap::decode(&clock_acc.data).ok_or("bad Clock")?;
        let rent = accs[accs.len() - 2].as_ref().and_then(|a| RentSnap::decode(&a.data)).ok_or("no Rent sysvar")?;
        let mut snap: HashMap<Address, Account> = HashMap::new();
        put(&mut snap, &want, accs[..want.len()].to_vec());
        let again = fixture_keys(venue, pool, &snap, &user)?;
        let missing: Vec<Address> = again.iter().filter(|k| !want.contains(k)).copied().collect();
        if !missing.is_empty() { want.extend(missing); continue; }
        live(venue, pool, &snap, &clock)?;
        // every built instruction must work on the snapshot alone
        for d in Dir::BOTH { build_swap(venue, pool, &snap, &user, d, 1, &BuildOpts::default())?; }
        let mut accounts: Vec<AccountSnap> = want.iter().filter_map(|k| snap.get(k).map(|a| AccountSnap::from_account(k, a))).collect();
        accounts.sort_by(|a, b| a.pubkey.cmp(&b.pubkey));
        let mut absent: Vec<String> = want.iter().filter(|k| !snap.contains_key(k)).map(|k| k.to_string()).collect();
        absent.sort();
        return Ok(PoolFixture { venue, pool: pool.to_string(), label: label.into(), fetched_at: now_utc(), slot, clock, rent: Some(rent),
            token0: t.t0.to_string(), token1: t.t1.to_string(), accounts, absent, notes: notes(venue, pool, &snap, &t) });
    }
    Err("account set did not converge".into())
}

fn amount(v: &HashMap<Address, Account>, k: &Address) -> u64 { v.get(k).and_then(|a| venues::token_amount(&a.data)).unwrap_or(0) }

/// the pool can swap now (otherwise the fixture is useless): vaults funded, status, open time
fn live(venue: Venue, pool: &Address, v: &HashMap<Address, Account>, clock: &ClockSnap) -> Result<(), String> {
    let d = &v[pool].data;
    let t = venues::pool_tokens(venue, d).unwrap();
    if !matches!(venue, Venue::Dlmm | Venue::DammV2 | Venue::RayClmm | Venue::Whirlpool) && (amount(v, &t.vault0) == 0 || amount(v, &t.vault1) == 0) {
        return Err("an empty vault".into());
    }
    match venue {
        Venue::RayAmmV4 => {
            let status = venues::u64_at(d, 0).unwrap();
            let open = venues::u64_at(d, 224).unwrap();
            if !(status == 1 || status == 6 || (status == 7 && clock.unix_timestamp as u64 >= open)) { return Err(format!("ammv4 status {status}")); }
            if mint_program(v, &t.t0) != TOKEN || mint_program(v, &t.t1) != TOKEN { return Err("ammv4 with a Token-2022 mint".into()); }
        }
        Venue::RayCpmm => {
            if d[329] >> 2 & 1 == 1 { return Err("cpmm swap disabled".into()); }
            if (clock.unix_timestamp as u64) < venues::u64_at(d, 373).unwrap() { return Err("cpmm not open".into()); }
        }
        Venue::Dlmm => {
            if d[82] != 0 { return Err(format!("dlmm status {}", d[82])); }
            if !(-512..=511).any(|i| dlmm_bitmap_bit(d, i)) && !v.contains_key(&dlmm_bitmap_extension(pool)) {
                return Err("dlmm: no bin array holds liquidity (empty bitmap, no extension)".into());
            }
        }
        Venue::DammV2 => {
            if d[481] != 0 { return Err(format!("damm pool_status {}", d[481])); }
            if d[360..376].iter().all(|b| *b == 0) { return Err("damm: zero liquidity".into()); }
        }
        Venue::PumpSwap => {}
        Venue::RayClmm => {
            // status bit 4: swap disabled; open_time: swaps need unix_timestamp > open_time
            if d[389] >> 4 & 1 == 1 { return Err("clmm swap disabled".into()); }
            if (clock.unix_timestamp as u64) <= venues::u64_at(d, 1080).unwrap() { return Err("clmm not open".into()); }
        }
        Venue::Whirlpool => {}
    }
    Ok(())
}

fn notes(venue: Venue, pool: &Address, v: &HashMap<Address, Account>, t: &venues::PoolTokens) -> BTreeMap<String, serde_json::Value> {
    let d = &v[pool].data;
    let mut n = BTreeMap::new();
    let dec = |m: &Address| v.get(m).and_then(|a| a.data.get(44).copied());
    n.insert("token_programs".into(), json!([mint_program(v, &t.t0).to_string(), mint_program(v, &t.t1).to_string()]));
    n.insert("decimals".into(), json!([dec(&t.t0), dec(&t.t1)]));
    n.insert("vault_amounts".into(), json!([amount(v, &t.vault0), amount(v, &t.vault1)]));
    match venue {
        Venue::PumpSwap => {
            n.insert("canonical_bump".into(), json!(pump_canonical_bump(d)));
            n.insert("mayhem".into(), json!(d.get(243)));
            n.insert("cashback".into(), json!(d.get(244)));
            n.insert("virtual_quote_reserves".into(), json!(d.get(245..261).map(|b| i128::from_le_bytes(b.try_into().unwrap()).to_string())));
            n.insert("creator_fee_bps".into(), json!(venues::u64_at(d, 261)));
            n.insert("pool_len".into(), json!(d.len()));
        }
        Venue::Dlmm => {
            let active = venues::i32_at(d, 76).unwrap();
            let fetched: Vec<i64> = dlmm_fixture_arrays(d).into_iter().filter(|i| v.contains_key(&dlmm_bin_array(pool, *i))).collect();
            let liquid: Vec<i64> = fetched.iter().copied().filter(|i| dlmm_bitmap_bit(d, *i)).collect();
            n.insert("active_id".into(), json!(active));
            n.insert("active_array".into(), json!(dlmm_array_index(active)));
            n.insert("bin_step".into(), json!(u16::from_le_bytes([d[80], d[81]])));
            n.insert("function_type".into(), json!(d[35]));
            n.insert("collect_fee_mode".into(), json!(d[36]));
            n.insert("bin_arrays_fetched".into(), json!(fetched));
            n.insert("bin_arrays_with_liquidity".into(), json!(liquid));
            n.insert("bitmap_extension".into(), json!(v.contains_key(&dlmm_bitmap_extension(pool))));
        }
        Venue::DammV2 => {
            n.insert("collect_fee_mode".into(), json!(d.get(484)));
            n.insert("base_fee_mode".into(), json!(d.get(16)));
            n.insert("token_amounts".into(), json!([venues::u64_at(d, 680), venues::u64_at(d, 688)]));
        }
        Venue::RayCpmm => {
            n.insert("creator_fee_on".into(), json!(d.get(389)));
            n.insert("enable_creator_fee".into(), json!(d.get(390)));
        }
        Venue::RayAmmV4 => {
            n.insert("status".into(), json!(venues::u64_at(d, 0)));
            n.insert("swap_fee".into(), json!([venues::u64_at(d, 176), venues::u64_at(d, 184)]));
        }
        Venue::RayClmm => {
            let ts = rayclmm_tick_spacing(d);
            let tick = rayclmm_tick_current(d);
            let cfg = venues::pk_at(d, 9).and_then(|k| v.get(&k)).map(|a| a.data.clone()).unwrap_or_default();
            let u32_ = |b: &[u8], o: usize| b.get(o..o + 4).map(|x| u32::from_le_bytes(x.try_into().unwrap()));
            let held: Vec<i32> = v.iter().filter(|(_, a)| a.owner == RAYCLMM && a.data.len() == 10_240 && a.data.get(8..40) == Some(pool.as_ref()))
                .filter_map(|(_, a)| venues::i32_at(&a.data, 40)).collect::<std::collections::BTreeSet<i32>>().into_iter().collect();
            n.insert("tick_spacing".into(), json!(ts));
            n.insert("tick_current".into(), json!(tick));
            n.insert("current_array".into(), json!(rayclmm_array_start(tick, ts)));
            n.insert("liquidity".into(), json!(d.get(237..253).map(|b| u128::from_le_bytes(b.try_into().unwrap()).to_string())));
            n.insert("sqrt_price_x64".into(), json!(d.get(253..269).map(|b| u128::from_le_bytes(b.try_into().unwrap()).to_string())));
            n.insert("status".into(), json!(d[389]));
            n.insert("fee_on".into(), json!(d[390]));
            n.insert("dynamic_fee".into(), json!(d[1096..1176].iter().any(|b| *b != 0)));
            n.insert("trade_fee_rate".into(), json!(u32_(&cfg, 47)));
            n.insert("protocol_fee_rate".into(), json!(u32_(&cfg, 43)));
            n.insert("fund_fee_rate".into(), json!(u32_(&cfg, 53)));
            n.insert("bitmap_extension".into(), json!(v.contains_key(&rayclmm_bitmap_extension(pool))));
            n.insert("tick_arrays_fetched".into(), json!(held));
        }
        Venue::Whirlpool => {
            let ts = whirl_tick_spacing(d);
            let tick = whirl_tick_current(d);
            let held: Vec<(i32, &str)> = v.iter().filter(|(_, a)| a.owner == WHIRLPOOL && a.data.len() >= 8 && a.data.len() != 653 && a.data.len() != 254)
                .filter_map(|(_, a)| {
                    let fixed = a.data.len() == 9_988;
                    venues::i32_at(&a.data, 8).map(|st| (st, if fixed { "fixed" } else { "dynamic" }))
                }).collect::<std::collections::BTreeSet<_>>().into_iter().collect();
            n.insert("tick_spacing".into(), json!(ts));
            n.insert("tick_current".into(), json!(tick));
            n.insert("current_array".into(), json!(whirl_array_start(tick, ts)));
            n.insert("fee_rate".into(), json!(u16::from_le_bytes([d[45], d[46]])));
            n.insert("protocol_fee_rate".into(), json!(u16::from_le_bytes([d[47], d[48]])));
            n.insert("fee_tier_index_seed".into(), json!(u16::from_le_bytes([d[43], d[44]])));
            n.insert("liquidity".into(), json!(d.get(49..65).map(|b| u128::from_le_bytes(b.try_into().unwrap()).to_string())));
            n.insert("sqrt_price".into(), json!(d.get(65..81).map(|b| u128::from_le_bytes(b.try_into().unwrap()).to_string())));
            n.insert("oracle".into(), json!(v.contains_key(&whirl_oracle(pool))));
            n.insert("tick_arrays_fetched".into(), json!(held));
        }
    }
    n
}
