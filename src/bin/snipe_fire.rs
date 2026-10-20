//! snipe_fire — build + SIGN a pump.fun launch-sniper BUY (or a self-transfer latency probe), and by DEFAULT
//! print the signed transaction and EXIT WITHOUT SENDING.
//!
//! SAFETY: this binary is dry by default. It transmits a transaction ONLY when BOTH `--live` and
//! `--max-sol <cap>` are given AND the spend is within the cap. Without `--live` it signs, prints and exits.
//! It never unlocks the real wallet unless a keystore is configured and a passphrase is supplied on stdin/tty.
//!
//! Usage:
//!   snipe_fire --self-probe [--config probe.toml] [--throwaway]
//!   snipe_fire --mint <PK> [--creator <PK>] [--bonding-curve <PK>] [--spend-lamports N]
//!              [--min-tokens-out N] [--cu-limit N] [--cu-price-micro N] [--no-ata]
//!              [--nonce <PK> --nonce-auth <PK>] [--config probe.toml] [--throwaway]
//!              [--live --max-sol <cap>]
//!
//! probe.toml (minimal — NOT the full arb config; parsed field-by-field so the live schema skew can't break it):
//!   wallet          = "<expected pubkey>"        # optional; verified against the keystore
//!   wallet_keystore = "/path/to/keystore.enc"    # optional; v3 keystore, passphrase read from stdin/tty
//!   rpc_url         = "https://..."              # optional; for the blockhash and (live) status polling
//!   [[send]] name=.. kind=.. url=.. ...          # optional; only used with --live

use anyhow::{bail, Context, Result};
use arbx::snipe::Launch;
use arbx::snipe_build::{self, BuyPlan};
use arbx::tx::{self, b58, pk, Pk};
use arbx::{build, config, rpc, send, wallet};
use ed25519_dalek::SigningKey;

fn arg(flag: &str) -> Option<String> {
    let a: Vec<String> = std::env::args().collect();
    a.iter().position(|x| x == flag).and_then(|i| a.get(i + 1).cloned())
}
fn has(flag: &str) -> bool { std::env::args().any(|x| x == flag) }
fn arg_u64(flag: &str, default: u64) -> u64 { arg(flag).and_then(|s| s.parse().ok()).unwrap_or(default) }
fn arg_pk(flag: &str) -> Option<Pk> { arg(flag).map(|s| pk(&s)) }

#[derive(Default, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Probe {
    #[serde(default)]
    wallet: Option<String>,
    #[serde(default)]
    wallet_keystore: Option<String>,
    #[serde(default)]
    rpc_url: Option<String>,
    #[serde(rename = "send", default)]
    sends: Vec<config::SendPath>,
}

/// random throwaway signing key (dry-run proof without the owner's passphrase).
fn throwaway_key() -> Result<SigningKey> {
    use std::io::Read;
    let mut seed = [0u8; 32];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut seed)?;
    Ok(SigningKey::from_bytes(&seed))
}

/// unlock the keystore named in the probe config (passphrase from stdin/tty), verifying against `expect`.
fn keystore_key(path: &str, expect: Option<&str>) -> Result<SigningKey> {
    wallet::harden_process();
    let blob = std::fs::read_to_string(path).with_context(|| format!("reading {path}"))?;
    let pass = wallet::read_pass()?;
    let key = wallet::keypair(&wallet::decrypt(&blob, pass.as_bytes())?)?;
    let got = b58(&key.verifying_key().to_bytes());
    if let Some(w) = expect {
        if got != w { bail!("{path} holds {got}, but the config's wallet is {w}"); }
    }
    Ok(key)
}

fn main() -> Result<()> {
    use base64::Engine as _;
    let b64 = base64::engine::general_purpose::STANDARD;

    // Load provider secrets (e.g. CONSTANTK_TOKEN) into the process env, like the live binary does, so a
    // [[send]] url with ${...} expands. --env-file overrides; default tries the live .env then cwd .env.
    let envf = arg("--env-file").unwrap_or_else(|| "/root/arbx/.env".to_string());
    let _ = dotenvy::from_filename(&envf).or_else(|_| dotenvy::dotenv());

    let self_probe = has("--self-probe");
    let throwaway = has("--throwaway");
    let live = has("--live");

    // minimal probe config (optional)
    let probe: Probe = match arg("--config") {
        Some(p) => toml::from_str(&std::fs::read_to_string(&p).with_context(|| format!("reading {p}"))?)
            .with_context(|| format!("parsing {p} as a minimal probe config"))?,
        None => Probe::default(),
    };

    // --- wallet / keypair -------------------------------------------------------------------------------------
    let key: SigningKey = if throwaway {
        eprintln!("snipe_fire: using an in-memory THROWAWAY keypair (dry-run proof; the real wallet unlock is the owner's step)");
        throwaway_key()?
    } else if let Some(ks) = probe.wallet_keystore.as_deref().filter(|s| !s.is_empty()) {
        keystore_key(ks, probe.wallet.as_deref())?
    } else {
        eprintln!("snipe_fire: no wallet_keystore configured; using a THROWAWAY keypair (pass --config with wallet_keystore to use the real wallet, or --throwaway to silence this)");
        throwaway_key()?
    };
    let user: Pk = key.verifying_key().to_bytes();
    eprintln!("snipe_fire: payer = {}", b58(&user));

    // --- rpc (optional) ---------------------------------------------------------------------------------------
    let rpc = probe.rpc_url.as_deref().filter(|s| !s.is_empty()).map(|u| rpc::Rpc::new(u.to_string()));
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;

    // --- build the instruction list ---------------------------------------------------------------------------
    let nonce = match (arg_pk("--nonce"), arg_pk("--nonce-auth")) {
        (Some(n), Some(a)) => Some((n, a)),
        (Some(n), None) => Some((n, user)), // default authority = payer
        _ => None,
    };

    let (ixs, launch, spend_lamports): (Vec<build::Ix>, Option<Launch>, u64) = if self_probe {
        // 1-lamport self-transfer with a compute budget: proves build+sign+(optionally)send latency, spends ~nothing.
        let cu = arg_u64("--cu-limit", 450) as u32;
        let mut ixs = vec![build::cu_limit_ix(cu)];
        let price = arg_u64("--cu-price-micro", 0);
        if price > 0 { ixs.push(build::cu_price_ix(price)); }
        // A jito-bundle send needs a tip to a Jito tip account. With --jito-tip <lamports> the probe's
        // spend IS that tip (it lands the bundle); otherwise a 1-lamport self-transfer (for no-tip paths).
        let jtip = arg_u64("--jito-tip", 0);
        if jtip > 0 {
            let tip_acct = pk("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"); // a known Jito tip account (send::JitoBundle set)
            ixs.push(build::transfer_ix(user, tip_acct, jtip));
            (ixs, None, jtip)
        } else {
            ixs.push(build::transfer_ix(user, user, 1));
            (ixs, None, 1)
        }
    } else {
        let mint = arg_pk("--mint").context("a buy needs --mint (or use --self-probe)")?;
        let creator = arg_pk("--creator").unwrap_or(mint);
        let launch = match arg_pk("--bonding-curve") {
            Some(bc) => Launch { mint, bonding_curve: bc, assoc_bonding_curve: snipe_build::assoc_bonding_curve(&bc, &mint), creator, dev_buy_lamports: 0, is_create_v2: true,
                is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: [0u8; 32] },
            None => snipe_build::launch_from_target(mint, creator),
        };
        let p = BuyPlan {
            spend_lamports: arg_u64("--spend-lamports", 1_000_000), // 0.001 SOL default
            min_tokens_out: arg_u64("--min-tokens-out", 0),
            cu_limit: arg_u64("--cu-limit", 120_000) as u32,
            cu_price_micro: arg_u64("--cu-price-micro", 0),
            create_ata: !has("--no-ata"),
            track_volume: true,
            nonce,
            wrap: has("--wrap"), // (build fix 2026-10-20: the field was added to BuyPlan after this cold one-shot)
        };
        let spend = p.spend_lamports;
        (snipe_build::buy_message_ixs(user, &launch, &p), Some(launch), spend)
    };

    // --- blockhash (durable nonce, or recent) -----------------------------------------------------------------
    let sysvar_recent = pk("SysvarRecentB1ockHashes11111111111111111111");
    let (blockhash, keep_static, bh_note): ([u8; 32], Vec<Pk>, String) = if let Some((n, _)) = nonce {
        // durable nonce: the message blockhash MUST be the nonce account's stored value, and the nonce account +
        // RecentBlockhashes sysvar must stay static (the runtime checks the nonce before tables load).
        let rpc = rpc.as_ref().context("--nonce needs an rpc_url (to read the nonce account's stored value)")?;
        let v = rt.block_on(async { rpc.accounts(&[n]).await })?;
        let acct = v.1.into_iter().next().flatten().context("nonce account not found on chain")?;
        let stored = build::nonce_value(&acct.data).context("account is not an initialized durable nonce")?;
        (stored, vec![n, sysvar_recent], format!("durable nonce {} (stored value)", b58(&n)))
    } else if let Some(rpc) = rpc.as_ref() {
        let (bh, _) = rt.block_on(async { rpc.latest_blockhash().await })?;
        (bh, vec![], "recent blockhash (getLatestBlockhash)".into())
    } else {
        eprintln!("snipe_fire: no rpc_url -> using a ZERO placeholder blockhash (dry-run only; a real send needs --config with rpc_url)");
        ([0u8; 32], vec![], "ZERO placeholder (no rpc_url)".into())
    };

    // --- compile + sign ---------------------------------------------------------------------------------------
    let msg = build::compile_v0(user, &ixs, blockhash, &[], &keep_static).map_err(|e| anyhow::anyhow!(e))?;
    let raw = build::sign(&msg, &key);
    let sig = send::first_signature(&raw).context("signed tx has no signature")?;

    // --- decoded summary --------------------------------------------------------------------------------------
    println!("\n===== snipe_fire DRY BUILD ({}) =====", if self_probe { "self-probe 1-lamport transfer" } else { "pump buy_exact_sol_in" });
    println!("payer          {}", b58(&user));
    println!("blockhash      {}", bh_note);
    println!("instructions   {}", ixs.len());
    for (i, ix) in ixs.iter().enumerate() {
        let tag = if ix.program == *arbx::snipe::PUMP && ix.data.len() >= 8 && ix.data[..8] == snipe_build::BUY_EXACT_SOL_IN_DISC { " <- buy_exact_sol_in" }
            else if ix.program == tx::COMPUTE_BUDGET { " (compute budget)" }
            else if ix.program == *arbx::pda::ATA_PROGRAM { " (ata create-idempotent)" }
            else if ix.program == *arbx::pda::SYSTEM_PROGRAM { " (system)" } else { "" };
        println!("  ix[{i}] program={} accounts={} data={}B{}", b58(&ix.program), ix.accounts.len(), ix.data.len(), tag);
    }
    if let Some(l) = &launch {
        let buy = snipe_build::buy_ix(user, l, spend_lamports, 0, true);
        println!("\nbuy_exact_sol_in: spend={} lamports ({:.6} SOL), min_tokens_out={}, 16 accounts (IDL order):",
            spend_lamports, spend_lamports as f64 / 1e9, arg_u64("--min-tokens-out", 0));
        let names = ["global", "fee_recipient", "mint", "bonding_curve", "associated_bonding_curve", "associated_user",
            "user", "system_program", "token_program(2022)", "creator_vault", "event_authority", "program",
            "global_volume_accumulator", "user_volume_accumulator", "fee_config", "fee_program"];
        for (i, m) in buy.accounts.iter().enumerate() {
            let flags = format!("{}{}", if m.writable { "W" } else { "r" }, if m.signer { "S" } else { " " });
            println!("  [{:>2}] {:<2} {:<26} {}", i, flags, names.get(i).copied().unwrap_or("?"), b58(&m.key));
        }
    }
    println!("\nsignature      {sig}");
    println!("tx size        {} bytes (limit {})", build::tx_bytes(&msg), build::MAX_TX_BYTES);
    println!("signed base64  {}", b64.encode(&raw));

    // --- SEND (gated) -----------------------------------------------------------------------------------------
    if !live {
        println!("\nDRY RUN: not sending (no --live). To send later, the owner runs it with --live --max-sol <cap>.");
        return Ok(());
    }

    // live path — hard-gated
    let max_sol: f64 = arg("--max-sol").and_then(|s| s.parse().ok()).context("--live requires --max-sol <cap> (a hard SOL cap)")?;
    let cap_lamports = (max_sol * 1e9) as u64;
    if spend_lamports > cap_lamports {
        bail!("REFUSED: spend {} lamports exceeds --max-sol cap {} lamports ({:.6} SOL)", spend_lamports, cap_lamports, max_sol);
    }
    if throwaway { bail!("REFUSED: refusing to --live with a throwaway keypair"); }
    if probe.sends.is_empty() { bail!("REFUSED: --live needs [[send]] paths in --config"); }
    let rpc = rpc.as_ref().context("--live needs an rpc_url (to poll the land slot)")?;

    println!("\nLIVE: spend {} lamports within cap {} — sending via {} path(s) ...", spend_lamports, cap_lamports, probe.sends.len());
    rt.block_on(async {
        let send_slot = rpc.slot().await.unwrap_or(0);
        let opts = send::PathsOpts { queue_ms: 0, payer: Some(user) };
        let (paths, notes) = send::Paths::new(&probe.sends, opts, arbx::rec::Rec::off(), true).await?;
        for n in &notes { eprintln!("send note: {n}"); }
        let prio = send::Prio { band: 0, crowd: 0, ev: 0 };
        let path = paths.list.first().context("no usable send path was built")?;
        match path.send(&raw, prio, None).await {
            Ok(r) => println!("sent via {}: sig={} status={:?} reply={}", path.name, r.sig, r.status, r.reply),
            Err(e) => bail!("send refused: {e}"),
        }
        // poll the land slot
        let sig_bytes = {
            let mut s = [0u8; 64];
            s.copy_from_slice(&bs58::decode(&sig).into_vec()?);
            s
        };
        for _ in 0..40 {
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            if let Ok(v) = rpc.statuses(&[sig_bytes]).await {
                if let Some(Some((land, ok))) = v.into_iter().next() {
                    println!("LANDED slot={land} (sent at slot {send_slot}, delta {}) ok={ok}", land as i64 - send_slot as i64);
                    return anyhow::Ok(());
                }
            }
        }
        println!("not seen after 20 s; check {sig}");
        anyhow::Ok(())
    })?;
    Ok(())
}
