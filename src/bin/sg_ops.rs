//! sg_ops (dip43 C3): deploy / verify / smoke-test / allowlist tool for the snipe-guard program (program/snipe-guard;
//! ops/guard/DEPLOY.md). Every command that sends a transaction refuses to run without --yes and prints what it will do first.
//! It reads ONLY the keypair files named on its command line (solana-keygen JSON); it never opens the engine's keystores (.enc) and
//! refuses keystore paths. Simulations (verify / smoke) need no key at all.
//!
//!   sg_ops info     [--so FILE] [--cluster C]                                  sha256, size, SOL the deploy locks
//!   sg_ops deploy   --cluster C --payer KP (--program-keypair KP | --program-keystore FILE.enc --program-id-expect PUBKEY) --upgrade-authority PUBKEY [--so FILE] [--init-allowlist-admin PUBKEY]
//!                   [--solana-bin PATH] [--yes]                                deploy (payer = temporary authority), optional
//!                                                                              allowlist init, hand the authority to the cold key, verify
//!   sg_ops verify   --cluster C --program-id ID [--so FILE] [--expect-authority PUBKEY]   on-chain bytes == the build
//!   sg_ops smoke    --cluster C --program-id ID [--wallet PUBKEY] [--payer PUBKEY]        simulate pass + aborts, decoded
//!   sg_ops allow-init   --cluster C --program-id ID --payer KP --authority KP --admin PUBKEY [--yes]
//!   sg_ops allow-add | allow-remove --cluster C --program-id ID --admin KP --wallet PUBKEY [--yes]
//!   sg_ops allow-admin  --cluster C --program-id ID --admin KP --new-admin PUBKEY [--yes]
//!   sg_ops allow-list   --cluster C --program-id ID
//!   sg_ops decode CODE                                                         a custom error code (hex 0x... or decimal) -> reason
//!   sg_ops codes                                                               the private code table (markdown)
//! --cluster: devnet | mainnet | testnet | localhost | an https URL. Default --so: program/snipe-guard/release/snipe_guard.so.
use anyhow::{bail, Context, Result};
use arbx::build;
use base64::Engine as _;
use ed25519_dalek::SigningKey;
use sha2::Digest;
use snipe_guard::client as sgc;
use snipe_guard::logic as sgl;

type Pk = [u8; 32];
const DEFAULT_SO: &str = "program/snipe-guard/release/snipe_guard.so";
const DEFAULT_SOLANA: &str = "/home/it/sniper-data/plan1110/onchain/toolchain/solana-release/bin/solana";
/// the feature that lets SBPF v3 programs deploy and run (agave-feature-set enable_sbpf_v3_deployment_and_execution)
const SBPF_V3_FEATURE: &str = "5cC3foj77CWun58pC51ebHFUWavHWKarWyR5UUik7dnC";
const LOADER_V3: &str = "BPFLoaderUpgradeab1e11111111111111111111111";
const AMS: &str = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR";

fn b58(k: &[u8]) -> String { bs58::encode(k).into_string() }
fn pk(s: &str) -> Result<Pk> {
    let v = bs58::decode(s.trim()).into_vec().with_context(|| format!("{s}: not base58"))?;
    <[u8; 32]>::try_from(v).map_err(|_| anyhow::anyhow!("{s}: not a 32-byte key"))
}
fn url_of(c: &str) -> String {
    match c {
        "devnet" => "https://api.devnet.solana.com".into(),
        "mainnet" | "mainnet-beta" => "https://api.mainnet-beta.solana.com".into(),
        "testnet" => "https://api.testnet.solana.com".into(),
        "localhost" => "http://127.0.0.1:8899".into(),
        u => u.to_string(),
    }
}
/// a solana-keygen JSON keypair; keystores of the engine are refused
fn keypair(path: &str) -> Result<SigningKey> {
    let low = path.to_ascii_lowercase();
    if low.ends_with(".enc") || low.contains("sniper-keys") || low.contains("keystore") {
        bail!("{path}: refusing to read an engine keystore (sg_ops only takes solana-keygen JSON keypairs you name for it)");
    }
    let txt = std::fs::read_to_string(path).with_context(|| format!("read {path}"))?;
    let v: Vec<u8> = serde_json::from_str(&txt).with_context(|| format!("{path}: not a solana-keygen JSON keypair"))?;
    if v.len() != 64 { bail!("{path}: {} bytes, a keypair has 64", v.len()); }
    let sk = SigningKey::from_bytes(v[..32].try_into().unwrap());
    if sk.verifying_key().to_bytes()[..] != v[32..] { bail!("{path}: the public half does not match the secret"); }
    Ok(sk)
}
fn pubkey(k: &SigningKey) -> Pk { k.verifying_key().to_bytes() }

/// The PROGRAM keypair from an engine-format encrypted keystore (v3 `.enc`), for `deploy --program-keystore` only: the passphrase is
/// asked on the terminal, the key must unlock to `--program-id-expect`, and it must NOT be one of our trading wallets. The keypair is
/// written to a fresh owner-only directory in RAM (/dev/shm) just for the `solana program deploy` call; the file is overwritten
/// with zeros and removed when this guard drops (also on any error).
struct RamKey { dir: std::path::PathBuf, file: std::path::PathBuf }
impl RamKey {
    fn from_keystore(enc: &str, expect: &Pk) -> Result<(SigningKey, RamKey)> {
        let pass = arbx::wallet::prompt_pass(&format!("passphrase for the PROGRAM keystore {enc} (hidden): "))?;
        Self::from_keystore_pass(enc, pass.as_bytes(), expect)
    }
    fn from_keystore_pass(enc: &str, pass: &[u8], expect: &Pk) -> Result<(SigningKey, RamKey)> {
        use std::io::Write;
        use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
        let blob = std::fs::read_to_string(enc).with_context(|| format!("read {enc}"))?;
        let secret = arbx::wallet::decrypt(&blob, pass)?;
        let sk = arbx::wallet::keypair(&secret)?;
        drop(secret);
        if pubkey(&sk) != *expect { bail!("{enc} unlocks to {}, not the expected program id {}", b58(&pubkey(&sk)), b58(expect)); }
        if sgl::is_compiled(&pubkey(&sk)) { bail!("{enc} unlocks to one of our TRADING wallets: refusing to use it as a program id"); }
        let dir = std::path::PathBuf::from(format!("/dev/shm/sg_ops_{}_{}", std::process::id(), arbx::fast::mono_ns()));
        std::fs::DirBuilder::new().mode(0o700).create(&dir).with_context(|| format!("create {}", dir.display()))?;
        let file = dir.join("program.json");
        let rk = RamKey { dir, file };
        let mut kb = sk.to_keypair_bytes();
        let json = format!("[{}]", kb.iter().map(|b| b.to_string()).collect::<Vec<_>>().join(","));
        kb.iter_mut().for_each(|b| *b = 0);
        let mut f = std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&rk.file).with_context(|| format!("create {}", rk.file.display()))?;
        f.write_all(json.as_bytes())?;
        f.sync_all()?;
        let mut json = json.into_bytes(); json.iter_mut().for_each(|b| *b = 0);
        Ok((sk, rk))
    }
    fn path(&self) -> String { self.file.display().to_string() }
}
impl Drop for RamKey {
    fn drop(&mut self) {
        if let Ok(m) = std::fs::metadata(&self.file) { let _ = std::fs::write(&self.file, vec![0u8; m.len() as usize]); }
        let _ = std::fs::remove_file(&self.file);
        let _ = std::fs::remove_dir(&self.dir);
    }
}
fn sha256_hex(b: &[u8]) -> String { sha2::Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect() }

struct Cx { rpc: arbx::rpc::Rpc, cluster: String, rt: tokio::runtime::Runtime }
impl Cx {
    fn call(&self, m: &str, p: serde_json::Value) -> Result<serde_json::Value> { self.rt.block_on(self.rpc.call(m, p)) }
    fn account(&self, k: &Pk) -> Result<Option<(Vec<u8>, Pk, u64, bool)>> {
        let v = self.call("getAccountInfo", serde_json::json!([b58(k), {"encoding": "base64", "commitment": "confirmed"}]))?;
        if v["value"].is_null() { return Ok(None); }
        let d = base64::engine::general_purpose::STANDARD.decode(v["value"]["data"][0].as_str().unwrap_or("")).context("account data")?;
        Ok(Some((d, pk(v["value"]["owner"].as_str().unwrap_or(""))?, v["value"]["lamports"].as_u64().unwrap_or(0), v["value"]["executable"].as_bool().unwrap_or(false))))
    }
    fn rent(&self, len: usize) -> Result<u64> { Ok(self.call("getMinimumBalanceForRentExemption", serde_json::json!([len]))?.as_u64().unwrap_or(0)) }
    fn slot(&self) -> Result<u64> { Ok(self.call("getSlot", serde_json::json!([{"commitment": "processed"}]))?.as_u64().unwrap_or(0)) }
    fn blockhash(&self) -> Result<Pk> {
        let v = self.call("getLatestBlockhash", serde_json::json!([{"commitment": "confirmed"}]))?;
        pk(v["value"]["blockhash"].as_str().context("no blockhash")?)
    }
    /// sign with every key we have (signer slots of keys we do not have stay zero: simulation only)
    fn wire(&self, payer: Pk, ixs: &[build::Ix], keys: &[&SigningKey]) -> Result<Vec<u8>> {
        let msg = build::compile_v0(payer, ixs, self.blockhash()?, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let b = &msg.bytes;
        // v0: [0x80, n_sig, n_ro_signed, n_ro_unsigned, compact n_keys, keys...]
        let n_sig = b[1] as usize;
        let mut out = vec![n_sig as u8];
        let key_at = |i: usize| -> Pk { b[5 + 32 * i..5 + 32 * (i + 1)].try_into().unwrap() };
        for i in 0..n_sig {
            let k = key_at(i);
            match keys.iter().find(|s| pubkey(s) == k) {
                Some(s) => { use ed25519_dalek::Signer; out.extend(s.sign(b).to_bytes()); }
                None => out.extend([0u8; 64]),
            }
        }
        out.extend(b);
        Ok(out)
    }
    fn simulate(&self, raw: &[u8]) -> Result<serde_json::Value> {
        let v = self.call("simulateTransaction", serde_json::json!([base64::engine::general_purpose::STANDARD.encode(raw),
            {"sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed"}]))?;
        Ok(v["value"].clone())
    }
    fn send(&self, raw: &[u8]) -> Result<String> {
        let sim = self.simulate(raw)?;
        if !sim["err"].is_null() { bail!("simulation failed: {} {}", sim["err"], decode_err(&sim["err"])); }
        let sig = self.call("sendTransaction", serde_json::json!([base64::engine::general_purpose::STANDARD.encode(raw), {"encoding": "base64", "preflightCommitment": "confirmed"}]))?;
        let sig = sig.as_str().context("no signature")?.to_string();
        for _ in 0..60 {
            std::thread::sleep(std::time::Duration::from_millis(1000));
            let s = self.call("getSignatureStatuses", serde_json::json!([[sig]]))?;
            let st = &s["value"][0];
            if !st.is_null() && matches!(st["confirmationStatus"].as_str(), Some("confirmed" | "finalized")) {
                if !st["err"].is_null() { bail!("{sig} failed: {} {}", st["err"], decode_err(&st["err"])); }
                return Ok(sig);
            }
        }
        bail!("{sig}: not confirmed in 60 s")
    }
}

/// {"InstructionError":[i,{"Custom":c}]} -> the decoded reason
fn decode_err(e: &serde_json::Value) -> String {
    let c = e.get("InstructionError").and_then(|x| x.get(1)).and_then(|x| x.get("Custom")).and_then(|x| x.as_u64());
    match c.and_then(|c| sgc::decode(c as u32).map(|f| (c, f))) { Some((c, f)) => format!("= {}", reason(&f, c as u32)), None => String::new() }
}
fn reason(f: &sgl::Fail, code: u32) -> String {
    let sub = sgc::sub_name(f.kind, f.idx).map(|s| format!(" {s}")).unwrap_or_else(|| if f.kind == sgl::K_FLOORS { format!(" holder #{}", f.idx) } else { String::new() });
    let gap = sgc::gap_text(f.kind, f.gap);
    format!("{}{}{}{} ({code:#010x})", sgc::kind_name(f.kind), sub, if f.kind == sgl::K_FLOORS { format!(", {} below", f.cnt) } else { String::new() },
        if gap.is_empty() { String::new() } else { format!(", {gap}") })
}

fn guard_ix(program: Pk, g: &sgc::Guard, wallet: Pk, list: Option<Pk>, wallet_signs: bool) -> build::Ix {
    let mut accounts: Vec<build::Meta> = g.accounts(wallet, list).into_iter().map(|(key, signer, writable)| build::Meta { key, signer, writable }).collect();
    if !wallet_signs { accounts[0].signer = false; }
    build::Ix { program, data: g.data(), accounts }
}
fn list_pda(program: &Pk) -> (Pk, u8) { arbx::pda::find_program_address(&[&sgl::AL_SEED], program) }
fn programdata_of(program: &Pk) -> Pk { arbx::pda::find_program_address(&[program], &pk(LOADER_V3).unwrap()).0 }

fn main() {
    if let Err(e) = run() { eprintln!("sg_ops: {e:#}"); std::process::exit(1); }
}

fn run() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let cmd = args.get(1).cloned().unwrap_or_default();
    let arg = |f: &str| args.iter().position(|x| x == f).and_then(|i| args.get(i + 1)).cloned();
    let has = |f: &str| args.iter().any(|x| x == f);
    let need = |f: &str| arg(f).with_context(|| format!("{cmd} needs {f}"));
    let so_path = arg("--so").unwrap_or_else(|| DEFAULT_SO.into());
    let cx = || -> Result<Cx> {
        let c = need("--cluster")?;
        Ok(Cx { rpc: arbx::rpc::Rpc::new(url_of(&c)), cluster: c, rt: tokio::runtime::Builder::new_current_thread().enable_all().build()? })
    };
    let yes = has("--yes");
    match cmd.as_str() {
        "decode" => {
            let s = args.get(2).context("decode CODE")?;
            let c = if let Some(h) = s.strip_prefix("0x") { u32::from_str_radix(h, 16)? } else { s.parse::<u32>()? };
            match sgc::decode(c) { Some(f) => println!("{}", reason(&f, c)), None => println!("{c:#010x}: not a snipe-guard code") }
        }
        "codes" => print_codes(),
        "info" => {
            let so = std::fs::read(&so_path).with_context(|| format!("read {so_path}"))?;
            println!("so {so_path}: {} bytes, sha256 {}", so.len(), sha256_hex(&so));
            if has("--cluster") {
                let cx = cx()?;
                let (pd, pa) = (cx.rent(45 + so.len())?, cx.rent(36)?);
                println!("{}: locks {:.6} SOL (programdata {:.6} + program {:.6}); a temporary buffer of the same size is refunded after the deploy", cx.cluster,
                    (pd + pa) as f64 / 1e9, pd as f64 / 1e9, pa as f64 / 1e9);
            }
        }
        "deploy" => {
            let cx = cx()?;
            let so = std::fs::read(&so_path).with_context(|| format!("read {so_path}"))?;
            let payer_path = need("--payer")?;
            let payer = keypair(&payer_path)?;
            // the program id: a solana-keygen JSON (--program-keypair) or, dip43 11-10, an engine-format keystore (--program-keystore FILE.enc
            // --program-id-expect PUBKEY): its passphrase is asked only with --yes; the dry plan shows the expected id
            let ks = arg("--program-keystore");
            let (prog_id, mut ram, mut prog_path) = match &ks {
                Some(_) => (pk(&need("--program-id-expect")?)?, None, String::new()),
                None => { let p = need("--program-keypair")?; (pubkey(&keypair(&p)?), None::<RamKey>, p) }
            };
            let cold = pk(&need("--upgrade-authority")?)?;
            let admin = arg("--init-allowlist-admin").map(|s| pk(&s)).transpose()?;
            let solana = arg("--solana-bin").unwrap_or_else(|| DEFAULT_SOLANA.into());
            let (pd, pa) = (cx.rent(45 + so.len())?, cx.rent(36)?);
            let bal = cx.call("getBalance", serde_json::json!([b58(&pubkey(&payer)), {"commitment": "confirmed"}]))?["value"].as_u64().unwrap_or(0);
            let feat = cx.account(&pk(SBPF_V3_FEATURE)?)?;
            println!("DEPLOY PLAN ({})", cx.cluster);
            println!("  program id         {}", b58(&prog_id));
            println!("  .so                {so_path}: {} bytes, sha256 {}", so.len(), sha256_hex(&so));
            println!("  payer              {} (balance {:.6} SOL; temporary upgrade authority during the deploy)", b58(&pubkey(&payer)), bal as f64 / 1e9);
            println!("  final authority    {} (cold; never needs to be online for this)", b58(&cold));
            println!("  SOL locked         {:.6} (programdata {:.6} + program {:.6}) + ~0.0002 fees; a buffer of ~{:.4} is refunded", (pd + pa) as f64 / 1e9, pd as f64 / 1e9, pa as f64 / 1e9, pd as f64 / 1e9);
            println!("  SBPF v3 feature    {} on this cluster", if feat.is_some() { "ACTIVE (account exists)" } else { "NOT FOUND" });
            if let Some(a) = admin { println!("  allowlist PDA      {} init with admin {} (+{:.6} SOL rent)", b58(&list_pda(&prog_id).0), b58(&a), cx.rent(sgl::AL_LEN)? as f64 / 1e9); }
            if feat.is_none() { bail!("the SBPF v3 feature account is missing on {}: the program cannot run there", cx.cluster); }
            if cx.account(&prog_id)?.is_some() { bail!("{} already exists on {}: use `solana program deploy --program-id` with the cold authority to UPGRADE (DEPLOY.md §upgrade)", b58(&prog_id), cx.cluster); }
            if bal < 2 * pd + pa + 10_000_000 { bail!("payer balance {:.6} SOL < {:.6} needed (buffer + programdata + fees)", bal as f64 / 1e9, (2 * pd + pa + 10_000_000) as f64 / 1e9); }
            if !yes { println!("dry: nothing sent. Re-run with --yes to deploy."); return Ok(()); }
            if let Some(enc) = &ks {
                let (_, rk) = RamKey::from_keystore(enc, &prog_id)?;
                prog_path = rk.path(); ram = Some(rk);
            }
            let url = url_of(&cx.cluster);
            let st = std::process::Command::new(&solana).args(["program", "deploy", "--url", &url, "--keypair", &payer_path, "--program-id", &prog_path,
                "--upgrade-authority", &payer_path, "--commitment", "confirmed", &so_path]).status().with_context(|| format!("run {solana}"))?;
            drop(ram.take());   // the program key is not needed after the deploy: wiped from RAM now
            if !st.success() { bail!("solana program deploy failed ({st})"); }
            if let Some(a) = admin { allow_init(&cx, &prog_id, &payer, &payer, a)?; }
            if cold != pubkey(&payer) {
                let st = std::process::Command::new(&solana).args(["program", "set-upgrade-authority", &b58(&prog_id), "--url", &url, "--keypair", &payer_path,
                    "--upgrade-authority", &payer_path, "--new-upgrade-authority", &b58(&cold), "--skip-new-upgrade-authority-signer-check"]).status()?;
                if !st.success() { bail!("set-upgrade-authority failed ({st}): the PAYER is still the upgrade authority; fix it by hand (DEPLOY.md)"); }
            }
            verify(&cx, &prog_id, &so, Some(cold))?;
            println!("DEPLOYED {} on {}: engine flag --presend-live-guard-program {}", b58(&prog_id), cx.cluster, b58(&prog_id));
        }
        "verify" => {
            let cx = cx()?;
            let so = std::fs::read(&so_path).with_context(|| format!("read {so_path}"))?;
            verify(&cx, &pk(&need("--program-id")?)?, &so, arg("--expect-authority").map(|s| pk(&s)).transpose()?)?;
        }
        "smoke" => {
            let cx = cx()?;
            smoke(&cx, pk(&need("--program-id")?)?, pk(&arg("--wallet").unwrap_or_else(|| AMS.into()))?, arg("--payer").map(|s| pk(&s)).transpose()?, arg("--allowlist").map(|s| pk(&s)).transpose()?)?;
        }
        "allow-list" => {
            let cx = cx()?;
            let p = pk(&need("--program-id")?)?;
            let (l, b) = list_pda(&p);
            println!("allowlist PDA {} (bump {b})", b58(&l));
            match cx.account(&l)? {
                None => println!("  not initialized (only the compiled wallets AMS/FRA/FRZ can use the program)"),
                Some((d, owner, lam, _)) => {
                    if owner != p { bail!("the PDA is owned by {}, not the program", b58(&owner)); }
                    let (admin, bump, ws) = sgc::al_read(&d).context("not an allowlist account")?;
                    println!("  admin {}  bump {bump}  rent {:.6} SOL  wallets {}/{}", b58(&admin), lam as f64 / 1e9, ws.len(), sgl::AL_MAX);
                    for w in ws { println!("  - {}", b58(&w)); }
                }
            }
            println!("  compiled in: AMS {} FRA {} FRZ {}", b58(&sgl::COMPILED[0]), b58(&sgl::COMPILED[1]), b58(&sgl::COMPILED[2]));
        }
        "allow-init" => {
            let cx = cx()?;
            let p = pk(&need("--program-id")?)?;
            let payer = keypair(&need("--payer")?)?;
            let auth = keypair(&need("--authority")?)?;
            let admin = pk(&need("--admin")?)?;
            println!("ALLOW-INIT on {}: PDA {} admin {} (payer {}, upgrade authority {})", cx.cluster, b58(&list_pda(&p).0), b58(&admin), b58(&pubkey(&payer)), b58(&pubkey(&auth)));
            if !yes { println!("dry: nothing sent. Re-run with --yes."); return Ok(()); }
            allow_init(&cx, &p, &payer, &auth, admin)?;
        }
        "allow-add" | "allow-remove" | "allow-admin" => {
            let cx = cx()?;
            let p = pk(&need("--program-id")?)?;
            let admin = keypair(&need("--admin")?)?;
            let (op, key) = match cmd.as_str() { "allow-add" => (sgl::OP_AL_ADD, pk(&need("--wallet")?)?), "allow-remove" => (sgl::OP_AL_REMOVE, pk(&need("--wallet")?)?),
                _ => (sgl::OP_AL_ADMIN, pk(&need("--new-admin")?)?) };
            let (l, _) = list_pda(&p);
            println!("{} {} on {} (list {}, admin {})", cmd.to_uppercase(), b58(&key), cx.cluster, b58(&l), b58(&pubkey(&admin)));
            if !yes { println!("dry: nothing sent. Re-run with --yes."); return Ok(()); }
            let ix = build::Ix { program: p, data: sgc::al_edit_data(op, key), accounts: vec![build::Meta { key: pubkey(&admin), signer: true, writable: true }, build::Meta { key: l, signer: false, writable: true }] };
            let sig = cx.send(&cx.wire(pubkey(&admin), &[ix], &[&admin])?)?;
            println!("done: {sig}");
        }
        _ => bail!("usage: sg_ops info|deploy|verify|smoke|allow-init|allow-add|allow-remove|allow-admin|allow-list|decode|codes (see the source header)"),
    }
    Ok(())
}

fn allow_init(cx: &Cx, p: &Pk, payer: &SigningKey, auth: &SigningKey, admin: Pk) -> Result<()> {
    let (l, bump) = list_pda(p);
    let lamports = cx.rent(sgl::AL_LEN)?;
    let ix = build::Ix { program: *p, data: sgc::al_init_data(bump, admin, lamports), accounts: vec![
        build::Meta { key: pubkey(payer), signer: true, writable: true }, build::Meta { key: l, signer: false, writable: true },
        build::Meta { key: pubkey(auth), signer: true, writable: false }, build::Meta { key: programdata_of(p), signer: false, writable: false },
        build::Meta { key: [0u8; 32], signer: false, writable: false }] };
    let sig = cx.send(&cx.wire(pubkey(payer), &[build::cu_limit_ix(60_000), ix], &[payer, auth])?)?;
    println!("allowlist initialized: PDA {} admin {} ({sig})", b58(&l), b58(&admin));
    Ok(())
}

/// the deployed bytes == the build: programdata[45..45+len] == the .so and the rest zero; the authority as expected
fn verify(cx: &Cx, p: &Pk, so: &[u8], expect_auth: Option<Pk>) -> Result<()> {
    let (pdata, owner, _, exec) = cx.account(p)?.with_context(|| format!("{}: no such account on {}", b58(p), cx.cluster))?;
    if owner != pk(LOADER_V3)? || !exec || pdata.len() < 36 || pdata[..4] != [2, 0, 0, 0] { bail!("{}: not an upgradeable-loader program", b58(p)); }
    let pd: Pk = pdata[4..36].try_into().unwrap();
    let (d, _, lam, _) = cx.account(&pd)?.context("no programdata account")?;
    if d.len() < 45 || d[..4] != [3, 0, 0, 0] { bail!("programdata {}: not a ProgramData account", b58(&pd)); }
    let slot = u64::from_le_bytes(d[4..12].try_into().unwrap());
    let auth = (d[12] == 1).then(|| <Pk>::try_from(&d[13..45]).unwrap());
    let elf = &d[45..];
    let same = elf.len() >= so.len() && &elf[..so.len()] == so && elf[so.len()..].iter().all(|b| *b == 0);
    println!("VERIFY {} on {}: programdata {} (deployed slot {slot}, {} bytes, {:.6} SOL)", b58(p), cx.cluster, b58(&pd), elf.len(), lam as f64 / 1e9);
    println!("  build    sha256 {} ({} bytes)", sha256_hex(so), so.len());
    println!("  on chain sha256 {} (first {} bytes){}", sha256_hex(&elf[..so.len().min(elf.len())]), so.len().min(elf.len()), if elf.len() > so.len() { format!(", {} trailing bytes {}", elf.len() - so.len(), if elf[so.len()..].iter().all(|b| *b == 0) { "all zero" } else { "NOT ZERO" }) } else { String::new() });
    println!("  upgrade authority {}", auth.map(|a| b58(&a)).unwrap_or_else(|| "NONE (final: immutable)".into()));
    if !same { bail!("VERIFY FAIL: the on-chain program is NOT this build"); }
    if let Some(e) = expect_auth { if auth != Some(e) { bail!("VERIFY FAIL: upgrade authority {} != expected {}", auth.map(|a| b58(&a)).unwrap_or_else(|| "none".into()), b58(&e)); } }
    println!("VERIFY PASS");
    Ok(())
}

/// post-deploy SMOKE: simulateTransaction only (sigVerify off, nothing sent, no key): one guarded try that passes and several that abort,
/// each with its expected decoded code. `wallet` = our trading wallet (default AMS, compiled in); `payer` = the fee payer (default the wallet).
/// CU printed = the guard + the CU-limit instruction (~150).
fn smoke(cx: &Cx, p: Pk, wallet: Pk, payer: Option<Pk>, list: Option<Pk>) -> Result<()> {
    let payer = payer.unwrap_or(wallet);
    let s = cx.slot()?;
    let gone = |b: u8| -> Pk { let mut k = [0u8; 32]; k[0] = 0x5e; k[1] = b; k[31] = 1; k };
    let other = { let mut k = [7u8; 32]; k[0] = 0x11; k };
    struct Case { name: &'static str, g: sgc::Guard, wallet: Pk, signs: bool, want: Option<(u8, u8)> }
    let cases = vec![
        Case { name: "PASS deadline +50, 2 floors of 0 on empty accounts, echo", g: sgc::Guard { deadline: Some(s + 50), floors: vec![(gone(1), 0), (gone(2), 0)], max_viol: 1, echo: true, ..Default::default() }, wallet, signs: true, want: None },
        Case { name: "ABORT deadline -50", g: sgc::Guard { deadline: Some(s.saturating_sub(50)), ..Default::default() }, wallet, signs: true, want: Some((sgl::K_DEADLINE, 0)) },
        Case { name: "ABORT 2 of 2 holders gone (G-A: more than 1 below)", g: sgc::Guard { deadline: Some(s + 50), floors: vec![(gone(1), 1), (gone(2), 1)], max_viol: 1, ..Default::default() }, wallet, signs: true, want: Some((sgl::K_FLOORS, 0)) },
        Case { name: "ABORT another signer", g: sgc::Guard { deadline: Some(s + 50), ..Default::default() }, wallet: other, signs: true, want: Some((sgl::K_AUTH, sgl::A_NO_LIST)) },
        Case { name: "ABORT our wallet not signing", g: sgc::Guard { deadline: Some(s + 50), ..Default::default() }, wallet, signs: false, want: Some((sgl::K_AUTH, sgl::A_NOT_SIGNER)) },
    ];
    println!("SMOKE {} on {} (simulation only; wallet {}, payer {}, slot {s})", b58(&p), cx.cluster, b58(&wallet), b58(&payer));
    let mut bad = 0;
    for c in cases {
        let ix = guard_ix(p, &c.g, c.wallet, if c.wallet == wallet { list } else { None }, c.signs);
        // the wallet that pays a try always signs it: the "not signing" case needs another fee payer (--payer, else another of our
        // compiled wallets, which hold SOL on mainnet)
        let fee_payer = if !c.signs && payer == c.wallet { sgl::COMPILED.iter().copied().find(|k| *k != c.wallet).unwrap_or(payer) } else { payer };
        let raw = cx.wire(fee_payer, &[build::cu_limit_ix(20_000), ix], &[])?;
        let v = cx.simulate(&raw)?;
        let err = &v["err"];
        let got = err.get("InstructionError").filter(|x| x.get(0).and_then(|i| i.as_u64()) == Some(1)).and_then(|x| x.get(1)).and_then(|x| x.get("Custom")).and_then(|x| x.as_u64())
            .and_then(|c| sgc::decode(c as u32).map(|f| (f, c as u32)));
        let ok = match (c.want, &got) {
            (None, _) => err.is_null(),
            (Some((k, i)), Some((f, _))) => f.kind == k && (k == sgl::K_DEADLINE || k == sgl::K_FLOORS || f.idx == i),
            _ => false,
        };
        let ret = v["returnData"]["data"][0].as_str().and_then(|d| base64::engine::general_purpose::STANDARD.decode(d).ok()).map(|b| format!(" echo {b:?}")).unwrap_or_default();
        println!("  {} {:<55} {} CU {}{}", if ok { "ok  " } else { "FAIL" }, c.name, v["unitsConsumed"], if err.is_null() { "passed".into() } else { format!("{err} {}", got.map(|(f, c)| reason(&f, c)).unwrap_or_default()) }, ret);
        if !ok { bad += 1; }
    }
    if bad > 0 { bail!("SMOKE FAIL: {bad} case(s)"); }
    println!("SMOKE PASS");
    Ok(())
}

fn print_codes() {
    println!("| kind | idx | meaning | example code (cnt 0, gap 0) |\n|---|---|---|---|");
    for kind in sgl::K_AUTH..=sgl::K_ADMIN {
        for idx in 0..16u8 {
            if let Some(s) = sgc::sub_name(kind, idx) { println!("| {} ({kind}) | {idx} | {s} | {:#010x} |", sgc::kind_name(kind), sgl::code(sgl::Fail::new(kind, idx))); }
        }
        if matches!(kind, sgl::K_DEADLINE | sgl::K_CURVE_HIGH | sgl::K_CURVE_DEEP | sgl::K_FLOORS) {
            for gap in 0..8u8 {
                let t = sgc::gap_text(kind, gap);
                if t == "?" || (gap == 0 && kind != sgl::K_FLOORS) { continue; }
                println!("| {} ({kind}) | {} | gap {gap}: {t} | {:#010x} |", sgc::kind_name(kind), if kind == sgl::K_FLOORS { "holder #" } else { "0" }, sgl::code(sgl::Fail { kind, idx: 0, cnt: if kind == sgl::K_FLOORS { 2 } else { 0 }, gap }));
            }
        }
    }
}

#[cfg(test)]
mod ramkey_tests {
    use super::*;
    /// a throwaway keystore unlocks to the expected id, the RAM file is a valid owner-only solana-keygen keypair, and it is gone after drop;
    /// a wrong expected id and a wrong passphrase are refused
    #[test]
    fn ramkey_roundtrip() {
        let sk = SigningKey::from_bytes(&[7u8; 32]);
        let secret = bs58::encode(sk.to_keypair_bytes()).into_string();
        let blob = arbx::wallet::encrypt(&secret, b"pw-test", 10).unwrap();
        let dir = std::env::temp_dir().join(format!("sgk_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let enc = dir.join("p.enc"); std::fs::write(&enc, blob).unwrap();
        let e = enc.to_str().unwrap();
        let (k, rk) = RamKey::from_keystore_pass(e, b"pw-test", &pubkey(&sk)).unwrap();
        assert_eq!(pubkey(&k), pubkey(&sk));
        let path = rk.path();
        assert!(path.starts_with("/dev/shm/"));
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
        let v: Vec<u8> = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(v, sk.to_keypair_bytes().to_vec());
        drop(rk);
        assert!(!std::path::Path::new(&path).exists());
        assert!(RamKey::from_keystore_pass(e, b"pw-test", &[1u8; 32]).is_err(), "wrong expected id");
        assert!(RamKey::from_keystore_pass(e, b"wrong", &pubkey(&sk)).is_err(), "wrong passphrase");
        std::fs::remove_dir_all(&dir).ok();
    }
}
