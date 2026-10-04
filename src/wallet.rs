//! The trading keypair, from the current bot's keystore: ~/.nexus-v2-<profile>-wallet.enc (the encrypted base58
//! secret key) and .pass (the passphrase, used byte for byte). Format (arbed src/providers/wallet/crypto.ts):
//! `v2:` + hex(salt 16 | iv 12 | tag 16 | ciphertext), key = scrypt(pass, salt, N=16384, r=8, p=1, 32 bytes),
//! AES-256-GCM; older unversioned blobs use a 16-byte IV. The files are only read, never copied or written.
use aes_gcm::aead::{consts::U16, Aead, KeyInit};
use aes_gcm::{aes::Aes256, AesGcm, Aes256Gcm, Nonce};
use anyhow::{bail, Context, Result};
use ed25519_dalek::SigningKey;

fn unhex(s: &str) -> Result<Vec<u8>> {
    if s.len() % 2 != 0 { bail!("odd hex length"); }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).context("not hex")).collect()
}

/// scrypt cost of new keystores: 2^17 (8x arbed's 2^14), about 0.3 s and 128 MB per guess
pub const V3_LOG_N: u8 = 17;

/// A new keystore blob: `v3:<log2 N>:` + hex(salt 16 | iv 12 | tag 16 | ciphertext), key = scrypt(pass, salt, N, r=8,
/// p=1, 32 bytes), AES-256-GCM; the plaintext is the base58 secret key (what `keypair` reads).
pub fn encrypt(secret_b58: &str, pass: &str, log_n: u8) -> Result<String> {
    let mut rnd = [0u8; 28];
    use std::io::Read;
    std::fs::File::open("/dev/urandom")?.read_exact(&mut rnd)?;
    let (salt, iv) = rnd.split_at(16);
    let mut key = [0u8; 32];
    scrypt::scrypt(pass.as_bytes(), salt, &scrypt::Params::new(log_n, 8, 1, 32).map_err(|e| anyhow::anyhow!("scrypt: {e}"))?, &mut key).map_err(|e| anyhow::anyhow!("scrypt: {e}"))?;
    let sealed = Aes256Gcm::new_from_slice(&key)?.encrypt(Nonce::from_slice(iv), secret_b58.as_bytes()).map_err(|_| anyhow::anyhow!("encrypt failed"))?;
    key.fill(0);
    let (ct, tag) = sealed.split_at(sealed.len() - 16);
    let mut out = Vec::with_capacity(16 + 12 + 16 + ct.len());
    out.extend_from_slice(salt); out.extend_from_slice(iv); out.extend_from_slice(tag); out.extend_from_slice(ct);
    Ok(format!("v3:{log_n}:{}", out.iter().map(|b| format!("{b:02x}")).collect::<String>()))
}

/// a secret key as solana-keygen writes it (JSON array of 64 numbers) or base58, to base58
pub fn secret_to_b58(input: &str) -> Result<String> {
    let t = input.trim();
    let bytes: Vec<u8> = if t.starts_with('[') { serde_json::from_str(t).context("not a JSON byte array")? } else { bs58::decode(t).into_vec().context("not base58")? };
    let s = bs58::encode(&bytes).into_string();
    keypair(&s)?;
    Ok(s)
}

/// decrypt one keystore blob to its plaintext (arbed's decryptKey, plus v3)
pub fn decrypt(blob: &str, pass: &str) -> Result<String> {
    let blob = blob.trim();
    if let Some(rest) = blob.strip_prefix("v3:") {
        let (n, hex) = rest.split_once(':').context("v3 keystore: no cost field")?;
        let log_n: u8 = n.parse().context("v3 keystore: bad cost")?;
        let buf = unhex(hex)?;
        if buf.len() < 16 + 12 + 16 { bail!("keystore blob too short"); }
        let (salt, rest) = buf.split_at(16);
        let (iv, rest) = rest.split_at(12);
        let (tag, ct) = rest.split_at(16);
        let mut key = [0u8; 32];
        scrypt::scrypt(pass.as_bytes(), salt, &scrypt::Params::new(log_n, 8, 1, 32).map_err(|e| anyhow::anyhow!("scrypt: {e}"))?, &mut key).map_err(|e| anyhow::anyhow!("scrypt: {e}"))?;
        let mut sealed = ct.to_vec();
        sealed.extend_from_slice(tag);
        let plain = Aes256Gcm::new_from_slice(&key)?.decrypt(Nonce::from_slice(iv), sealed.as_slice()).map_err(|_| anyhow::anyhow!("keystore: wrong passphrase or damaged file"))?;
        key.fill(0);
        return String::from_utf8(plain).context("keystore plaintext is not text");
    }
    let (v2, hex) = match blob.strip_prefix("v2:") { Some(h) => (true, h), None => (false, blob) };
    let buf = unhex(hex)?;
    let iv_len = if v2 { 12 } else { 16 };
    if buf.len() < 16 + iv_len + 16 { bail!("keystore blob too short"); }
    let (salt, rest) = buf.split_at(16);
    let (iv, rest) = rest.split_at(iv_len);
    let (tag, ct) = rest.split_at(16);
    let mut key = [0u8; 32];
    scrypt::scrypt(pass.as_bytes(), salt, &scrypt::Params::new(14, 8, 1, 32).unwrap(), &mut key).map_err(|e| anyhow::anyhow!("scrypt: {e}"))?;
    let mut sealed = ct.to_vec();
    sealed.extend_from_slice(tag);
    let plain = if v2 {
        Aes256Gcm::new_from_slice(&key)?.decrypt(Nonce::from_slice(iv), sealed.as_slice())
    } else {
        AesGcm::<Aes256, U16>::new_from_slice(&key)?.decrypt(aes_gcm::Nonce::<U16>::from_slice(iv), sealed.as_slice())
    }.map_err(|_| anyhow::anyhow!("keystore: wrong passphrase or damaged file"))?;
    Ok(String::from_utf8(plain).context("keystore plaintext is not text")?)
}

/// the keypair from a decrypted base58 secret key (64 bytes: secret then public)
pub fn keypair(secret_b58: &str) -> Result<SigningKey> {
    let b = bs58::decode(secret_b58.trim()).into_vec().context("secret key is not base58")?;
    if b.len() != 64 { bail!("secret key is {} bytes, not 64", b.len()); }
    let key = SigningKey::from_bytes(b[..32].try_into().unwrap());
    if key.verifying_key().as_bytes()[..] != b[32..] { bail!("secret key's public half does not match"); }
    Ok(key)
}

/// The trading key for a config: the v3 keystore file with a passphrase given at start (wallet_keystore), else the
/// current bot's ~/.nexus-v2-<profile>-wallet.{enc,pass}. Either way it must be the config's wallet.
pub fn load_cfg(cfg: &crate::config::Config) -> Result<SigningKey> {
    if cfg.wallet_keystore.is_empty() { return load(&cfg.wallet_profile, &cfg.wallet); }
    harden_process();
    let blob = std::fs::read_to_string(&cfg.wallet_keystore).with_context(|| format!("reading {}", cfg.wallet_keystore))?;
    let mut pass = read_pass()?;
    let r = decrypt(&blob, &pass);
    unsafe { pass.as_bytes_mut().fill(0); }
    let mut plain = r?;
    let key = keypair(&plain);
    unsafe { plain.as_bytes_mut().fill(0); }
    let key = key?;
    let got = bs58::encode(key.verifying_key().as_bytes()).into_string();
    if got != cfg.wallet { bail!("{} holds {got}, but the config's wallet is {}", cfg.wallet_keystore, cfg.wallet); }
    Ok(key)
}

/// the passphrase: stdin's first line when it is piped (`ssh cherry 'arb-lab run ...' < pass` from your own machine),
/// else asked on the terminal with echo off
fn read_pass() -> Result<String> {
    if unsafe { libc::isatty(0) } == 1 { return prompt_pass("keystore passphrase (hidden): "); }
    let mut line = String::new();
    std::io::BufRead::read_line(&mut std::io::stdin().lock(), &mut line)?;
    let p = line.trim_end_matches(['\n', '\r']).to_string();
    unsafe { line.as_bytes_mut().fill(0); }
    if p.is_empty() { bail!("no passphrase on stdin"); }
    Ok(p)
}

/// no core dumps, and other (non-root) processes cannot attach to or read this one's memory
fn harden_process() {
    unsafe {
        libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0);
        let r = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
        libc::setrlimit(libc::RLIMIT_CORE, &r);
    }
}

/// Load ~/.nexus-v2-<profile>-wallet.{enc,pass} and check it is `expect` (the config's wallet).
pub fn load(profile: &str, expect: &str) -> Result<SigningKey> {
    let home = std::env::var("HOME").context("HOME")?;
    let base = format!("{home}/.nexus-v2-{profile}-wallet");
    let enc = std::fs::read_to_string(format!("{base}.enc")).with_context(|| format!("reading {base}.enc"))?;
    let pass = std::fs::read_to_string(format!("{base}.pass")).with_context(|| format!("reading {base}.pass"))?;
    let key = keypair(&decrypt(&enc, &pass)?)?;
    let got = bs58::encode(key.verifying_key().as_bytes()).into_string();
    if got != expect { bail!("the {profile} keystore holds {got}, but the config's wallet is {expect}"); }
    Ok(key)
}

/// Read a line from the terminal WITH echo (confirmations: what you type is shown).
pub fn prompt_visible(prompt: &str) -> Result<String> {
    use std::io::{BufRead, Write};
    let tty = std::fs::OpenOptions::new().read(true).write(true).open("/dev/tty").context("no terminal to ask on")?;
    let mut w = &tty;
    write!(w, "{prompt}")?; w.flush()?;
    let mut line = String::new();
    std::io::BufReader::new(&tty).read_line(&mut line)?;
    Ok(line.trim_end_matches(['\n', '\r']).to_string())
}

/// Read a passphrase from the terminal with echo off (never from argv or the environment).
pub fn prompt_pass(prompt: &str) -> Result<String> {
    use std::io::{BufRead, Write};
    let tty = std::fs::OpenOptions::new().read(true).write(true).open("/dev/tty").context("no terminal to ask the passphrase on")?;
    let fd = std::os::unix::io::AsRawFd::as_raw_fd(&tty);
    let mut t: libc::termios = unsafe { std::mem::zeroed() };
    unsafe { libc::tcgetattr(fd, &mut t); }
    let old = t;
    t.c_lflag &= !libc::ECHO;
    unsafe { libc::tcsetattr(fd, libc::TCSANOW, &t); }
    let mut w = &tty;
    write!(w, "{prompt}")?; w.flush()?;
    let mut line = String::new();
    let r = std::io::BufReader::new(&tty).read_line(&mut line);
    unsafe { libc::tcsetattr(fd, libc::TCSANOW, &old); }
    writeln!(w)?;
    r?;
    Ok(line.trim_end_matches(['\n', '\r']).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// a v3 blob written by tools/encrypt-keystore.mjs (the offline script) decrypts here
    #[test]
    fn decrypts_the_offline_scripts_keystore() {
        let v: serde_json::Value = serde_json::from_str(include_str!("../testdata/keystore-v3.json")).unwrap();
        let key = keypair(&decrypt(v["blob"].as_str().unwrap(), v["pass"].as_str().unwrap()).unwrap()).unwrap();
        assert_eq!(key.verifying_key().as_bytes().len(), 32);
        assert!(decrypt(v["blob"].as_str().unwrap(), "wrong passphrase!!").is_err());
    }

    #[test]
    fn v3_round_trip() {
        let k = SigningKey::from_bytes(&[7u8; 32]);
        let mut b = k.to_bytes().to_vec(); b.extend_from_slice(k.verifying_key().as_bytes());
        let s = secret_to_b58(&serde_json::to_string(&b).unwrap()).unwrap();
        let blob = encrypt(&s, "correct horse", 10).unwrap();
        assert!(blob.starts_with("v3:10:"));
        assert_eq!(keypair(&decrypt(&blob, "correct horse").unwrap()).unwrap().verifying_key(), k.verifying_key());
        assert!(decrypt(&blob, "wrong").is_err());
    }

    /// a blob written by arbed's own encryptKey (testdata-keystore.json), passphrase "test pass\n" (kept byte for byte)
    #[test]
    fn decrypts_arbeds_keystore() {
        let v: serde_json::Value = serde_json::from_str(include_str!("testdata-keystore.json")).unwrap();
        let key = keypair(&decrypt(v["enc"].as_str().unwrap(), "test pass\n").unwrap()).unwrap();
        assert_eq!(bs58::encode(key.verifying_key().as_bytes()).into_string(), v["pubkey"].as_str().unwrap());
        assert!(decrypt(v["enc"].as_str().unwrap(), "test pass").is_err(), "the trailing newline is part of the passphrase");
    }
}
