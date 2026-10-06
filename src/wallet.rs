//! The trading keypair, from the current bot's keystore: ~/.nexus-v2-<profile>-wallet.enc (the encrypted base58
//! secret key) and .pass (the passphrase, used byte for byte). Format (arbed src/providers/wallet/crypto.ts):
//! `v2:` + hex(salt 16 | iv 12 | tag 16 | ciphertext), key = scrypt(pass, salt, N=16384, r=8, p=1, 32 bytes),
//! AES-256-GCM; older unversioned blobs use a 16-byte IV. The files are only read, never copied or written.
//!
//! Secrets in memory (review WP-07 #15, OD-7): a typed or piped passphrase is read with read(2) straight into one
//! mlock'd page (`Pass`), never through a std buffer or a growing `String`. The passphrase, the scrypt key (`Key`), the
//! AES key schedule (the `aes` crate's `zeroize`) and the decrypted secret key (`SecretText`) are wiped with volatile
//! writes when they go, on every path. Not covered: the scrypt crate's own work buffers, which are freed, not wiped. The
//! process is non-dumpable and writes no core (`harden_process`).
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

/// Zeros the compiler keeps: volatile writes (a plain fill before a free can be removed as a dead store)
pub fn wipe(b: &mut [u8]) {
    for x in b.iter_mut() { unsafe { std::ptr::write_volatile(x, 0) } }
    std::sync::atomic::compiler_fence(std::sync::atomic::Ordering::SeqCst);
}

/// `wipe` over a vector's whole allocation (its spare capacity too), then empty it
fn wipe_vec(v: &mut Vec<u8>) {
    let p = v.as_mut_ptr();
    for i in 0..v.capacity() { unsafe { std::ptr::write_volatile(p.add(i), 0) } }
    std::sync::atomic::compiler_fence(std::sync::atomic::Ordering::SeqCst);
    v.clear();
}

/// A secret text: a keystore's plaintext (the base58 secret key) or a .pass file's passphrase. Wiped when it goes
pub struct SecretText(String);
impl std::ops::Deref for SecretText {
    type Target = str;
    fn deref(&self) -> &str { &self.0 }
}
impl Drop for SecretText { fn drop(&mut self) { wipe_vec(unsafe { self.0.as_mut_vec() }) } }

/// 32 key bytes (scrypt's), wiped whenever they go: on every path, an early return included (review WP-07 #15)
struct Key([u8; 32]);
impl Drop for Key { fn drop(&mut self) { wipe(&mut self.0) } }

/// scrypt(pass, salt, 2^log_n, r=8, p=1) into the caller's `key` (never moved, so no copy of it is left behind)
fn derive(pass: &[u8], salt: &[u8], log_n: u8, key: &mut Key) -> Result<()> {
    let params = scrypt::Params::new(log_n, 8, 1, 32).map_err(|e| anyhow::anyhow!("scrypt: {e}"))?;
    scrypt::scrypt(pass, salt, &params, &mut key.0).map_err(|e| anyhow::anyhow!("scrypt: {e}"))
}

/// a decrypted plaintext as text (wiped when it is not text)
fn text(plain: Vec<u8>) -> Result<SecretText> {
    match String::from_utf8(plain) {
        Ok(s) => Ok(SecretText(s)),
        Err(e) => {
            wipe_vec(&mut e.into_bytes());
            bail!("keystore plaintext is not text")
        }
    }
}

/// A new keystore blob: `v3:<log2 N>:` + hex(salt 16 | iv 12 | tag 16 | ciphertext), key = scrypt(pass, salt, N, r=8,
/// p=1, 32 bytes), AES-256-GCM; the plaintext is the base58 secret key (what `keypair` reads).
pub fn encrypt(secret_b58: &str, pass: &[u8], log_n: u8) -> Result<String> {
    let mut rnd = [0u8; 28];
    use std::io::Read;
    std::fs::File::open("/dev/urandom")?.read_exact(&mut rnd)?;
    let (salt, iv) = rnd.split_at(16);
    let mut key = Key([0u8; 32]);
    derive(pass, salt, log_n, &mut key)?;
    let sealed = Aes256Gcm::new_from_slice(&key.0)?.encrypt(Nonce::from_slice(iv), secret_b58.as_bytes()).map_err(|_| anyhow::anyhow!("encrypt failed"))?;
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

/// decrypt one keystore blob to its plaintext (arbed's decryptKey, plus v3); the scrypt key is wiped on every path
pub fn decrypt(blob: &str, pass: &[u8]) -> Result<SecretText> {
    let blob = blob.trim();
    if let Some(rest) = blob.strip_prefix("v3:") {
        let (n, hex) = rest.split_once(':').context("v3 keystore: no cost field")?;
        let log_n: u8 = n.parse().context("v3 keystore: bad cost")?;
        let buf = unhex(hex)?;
        if buf.len() < 16 + 12 + 16 { bail!("keystore blob too short"); }
        let (salt, rest) = buf.split_at(16);
        let (iv, rest) = rest.split_at(12);
        let (tag, ct) = rest.split_at(16);
        let mut key = Key([0u8; 32]);
        derive(pass, salt, log_n, &mut key)?;
        let mut sealed = ct.to_vec();
        sealed.extend_from_slice(tag);
        let plain = Aes256Gcm::new_from_slice(&key.0)?.decrypt(Nonce::from_slice(iv), sealed.as_slice()).map_err(|_| anyhow::anyhow!("keystore: wrong passphrase or damaged file"))?;
        return text(plain);
    }
    let (v2, hex) = match blob.strip_prefix("v2:") { Some(h) => (true, h), None => (false, blob) };
    let buf = unhex(hex)?;
    let iv_len = if v2 { 12 } else { 16 };
    if buf.len() < 16 + iv_len + 16 { bail!("keystore blob too short"); }
    let (salt, rest) = buf.split_at(16);
    let (iv, rest) = rest.split_at(iv_len);
    let (tag, ct) = rest.split_at(16);
    let mut key = Key([0u8; 32]);
    derive(pass, salt, 14, &mut key)?;
    let mut sealed = ct.to_vec();
    sealed.extend_from_slice(tag);
    let plain = if v2 {
        Aes256Gcm::new_from_slice(&key.0)?.decrypt(Nonce::from_slice(iv), sealed.as_slice())
    } else {
        AesGcm::<Aes256, U16>::new_from_slice(&key.0)?.decrypt(aes_gcm::Nonce::<U16>::from_slice(iv), sealed.as_slice())
    }.map_err(|_| anyhow::anyhow!("keystore: wrong passphrase or damaged file"))?;
    text(plain)
}

/// the keypair from a decrypted base58 secret key (64 bytes: secret then public); the decoded bytes are wiped
pub fn keypair(secret_b58: &str) -> Result<SigningKey> {
    let mut b = bs58::decode(secret_b58.trim()).into_vec().context("secret key is not base58")?;
    let key = keypair_of(&b);
    wipe_vec(&mut b);
    key
}

fn keypair_of(b: &[u8]) -> Result<SigningKey> {
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
    let key = {
        let pass = read_pass()?;
        keypair(&decrypt(&blob, pass.as_bytes())?)?
    };
    let got = bs58::encode(key.verifying_key().as_bytes()).into_string();
    if got != cfg.wallet { bail!("{} holds {got}, but the config's wallet is {}", cfg.wallet_keystore, cfg.wallet); }
    Ok(key)
}

/// The passphrase buffer's size: one page (a longer passphrase is refused)
pub const PASS_CAP: usize = 4096;

/// one page, page-aligned: locking and unlocking it touches no other data
#[repr(C, align(4096))]
struct Page([u8; PASS_CAP]);

/// A passphrase (review WP-07 #15, OD-7): read with read(2) straight into one mlock'd page, so no std buffer and no
/// growing `String` leaves a copy behind; wiped (volatile) and unlocked when it goes. Never in argv, the environment or
/// a file
pub struct Pass { page: Box<Page>, len: usize }

impl Pass {
    /// an empty passphrase in a locked page (a page that cannot be locked is an error: nothing is read then)
    fn new() -> Result<Pass> {
        let p = Pass { page: Box::new(Page([0u8; PASS_CAP])), len: 0 };
        p.lock()?;
        Ok(p)
    }
    /// lock the page; again in a forked child, which does not inherit the lock (`arbx campaign --detach`)
    pub fn lock(&self) -> Result<()> {
        if unsafe { libc::mlock(self.page.0.as_ptr().cast(), PASS_CAP) } != 0 {
            bail!("the passphrase's page cannot be locked in memory (mlock: {}): raise the memlock limit (ulimit -l)", std::io::Error::last_os_error());
        }
        Ok(())
    }
    pub fn as_bytes(&self) -> &[u8] { &self.page.0[..self.len] }
    pub fn len(&self) -> usize { self.len }
    pub fn is_empty(&self) -> bool { self.len == 0 }
    /// one more byte (false: the page is full)
    fn push(&mut self, b: u8) -> bool {
        if self.len == PASS_CAP { return false; }
        self.page.0[self.len] = b;
        self.len += 1;
        true
    }
    /// wipe the whole page and empty it
    fn clear(&mut self) {
        wipe(&mut self.page.0);
        self.len = 0;
    }
}

impl PartialEq for Pass { fn eq(&self, o: &Pass) -> bool { self.as_bytes() == o.as_bytes() } }

impl Drop for Pass {
    fn drop(&mut self) {
        self.clear();
        unsafe { libc::munlock(self.page.0.as_ptr().cast(), PASS_CAP); }
    }
}

/// The first line of `fd` into a locked page: read(2) one byte at a time, so nothing past the newline is consumed and no
/// buffer but the page holds it; trailing `\r`s dropped. A line longer than the page is read to its end first (no tail
/// is left for whatever reads the descriptor next: the shell, after a terminal), then refused
fn read_line_fd(fd: libc::c_int) -> Result<Pass> {
    let mut p = Pass::new()?;
    let mut over = false;
    loop {
        let mut b = 0u8;
        let n = unsafe { libc::read(fd, (&mut b as *mut u8).cast(), 1) };
        if n < 0 {
            let e = std::io::Error::last_os_error();
            if e.kind() == std::io::ErrorKind::Interrupted { continue; }
            return Err(e).context("reading the passphrase");
        }
        if n == 0 || b == b'\n' { break; }
        if !p.push(b) { over = true; }
    }
    while p.len > 0 && p.page.0[p.len - 1] == b'\r' {
        p.len -= 1;
        p.page.0[p.len] = 0;
    }
    if over { bail!("the passphrase is longer than {PASS_CAP} bytes"); }
    Ok(p)
}

/// the passphrase: stdin's first line when it is piped (`ssh cherry 'arbx run ...' < pass` from your own machine, or
/// `arbx campaign`'s pipe to a sending segment), else asked on the terminal with echo off. Either way read(2) into a
/// locked page (`Pass`)
pub fn read_pass() -> Result<Pass> {
    if unsafe { libc::isatty(0) } == 1 { return prompt_pass("keystore passphrase (hidden): "); }
    read_pass_fd(0)
}

/// `read_pass` from a descriptor that is not a terminal (an empty line is no passphrase)
fn read_pass_fd(fd: libc::c_int) -> Result<Pass> {
    let p = read_line_fd(fd)?;
    if p.is_empty() { bail!("no passphrase on stdin"); }
    Ok(p)
}

/// no core dumps, and other (non-root) processes cannot attach to or read this one's memory
pub fn harden_process() {
    unsafe {
        libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0);
        let r = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
        libc::setrlimit(libc::RLIMIT_CORE, &r);
    }
}

/// WP-07 (`arbx campaign`): the passphrase given once unlocks the config's `wallet_keystore` to the config's wallet (the
/// campaign then hands it to each sending segment over a pipe: never argv, the environment or a file)
pub fn check_pass(cfg: &crate::config::Config, pass: &[u8]) -> Result<()> {
    let blob = std::fs::read_to_string(&cfg.wallet_keystore).with_context(|| format!("reading {}", cfg.wallet_keystore))?;
    let key = keypair(&decrypt(&blob, pass)?)?;
    let got = bs58::encode(key.verifying_key().as_bytes()).into_string();
    if got != cfg.wallet { bail!("{} holds {got}, but the config's wallet is {}", cfg.wallet_keystore, cfg.wallet); }
    Ok(())
}

/// Load ~/.nexus-v2-<profile>-wallet.{enc,pass} and check it is `expect` (the config's wallet).
pub fn load(profile: &str, expect: &str) -> Result<SigningKey> {
    let home = std::env::var("HOME").context("HOME")?;
    let base = format!("{home}/.nexus-v2-{profile}-wallet");
    let enc = std::fs::read_to_string(format!("{base}.enc")).with_context(|| format!("reading {base}.enc"))?;
    let pass = SecretText(std::fs::read_to_string(format!("{base}.pass")).with_context(|| format!("reading {base}.pass"))?);
    let key = keypair(&decrypt(&enc, pass.as_bytes())?)?;
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

/// Read a passphrase from the terminal with echo off (never from argv or the environment): read(2) into a locked page
/// (`Pass`). The terminal's settings are put back whatever happens; a terminal whose echo cannot be turned off is refused
pub fn prompt_pass(prompt: &str) -> Result<Pass> {
    use std::io::Write;
    let tty = std::fs::OpenOptions::new().read(true).write(true).open("/dev/tty").context("no terminal to ask the passphrase on")?;
    let fd = std::os::unix::io::AsRawFd::as_raw_fd(&tty);
    let mut t: libc::termios = unsafe { std::mem::zeroed() };
    if unsafe { libc::tcgetattr(fd, &mut t) } != 0 { bail!("the terminal's settings cannot be read: echo cannot be turned off"); }
    let old = t;
    t.c_lflag &= !libc::ECHO;
    if unsafe { libc::tcsetattr(fd, libc::TCSANOW, &t) } != 0 { bail!("the terminal's echo cannot be turned off"); }
    let mut w = &tty;
    let r = write!(w, "{prompt}").and_then(|_| w.flush()).context("writing the prompt").and_then(|_| read_line_fd(fd));
    unsafe { libc::tcsetattr(fd, libc::TCSANOW, &old); }
    writeln!(w)?;
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    /// a v3 blob written by tools/encrypt-keystore.mjs (the offline script) decrypts here
    #[test]
    fn decrypts_the_offline_scripts_keystore() {
        let v: serde_json::Value = serde_json::from_str(include_str!("../testdata/keystore-v3.json")).unwrap();
        let key = keypair(&decrypt(v["blob"].as_str().unwrap(), v["pass"].as_str().unwrap().as_bytes()).unwrap()).unwrap();
        assert_eq!(key.verifying_key().as_bytes().len(), 32);
        assert!(decrypt(v["blob"].as_str().unwrap(), b"wrong passphrase!!").is_err());
    }

    #[test]
    fn v3_round_trip() {
        let k = SigningKey::from_bytes(&[7u8; 32]);
        let mut b = k.to_bytes().to_vec(); b.extend_from_slice(k.verifying_key().as_bytes());
        let s = secret_to_b58(&serde_json::to_string(&b).unwrap()).unwrap();
        let blob = encrypt(&s, b"correct horse", 10).unwrap();
        assert!(blob.starts_with("v3:10:"));
        assert_eq!(keypair(&decrypt(&blob, b"correct horse").unwrap()).unwrap().verifying_key(), k.verifying_key());
        assert!(decrypt(&blob, b"wrong").is_err());
    }

    /// arbed's formats decrypt through the wiped key (review WP-07 #15 touched both paths): v2 (a 12-byte IV) and the
    /// unversioned blobs (a 16-byte IV), scrypt 2^14
    #[test]
    fn arbeds_v2_and_unversioned_blobs_decrypt() {
        let (secret, pass) = ("the base58 secret", b"arbed's passphrase");
        let (salt, iv12, iv16) = ([3u8; 16], [5u8; 12], [6u8; 16]);
        let mut key = [0u8; 32];
        scrypt::scrypt(pass, &salt, &scrypt::Params::new(14, 8, 1, 32).unwrap(), &mut key).unwrap();
        let blob = |iv: &[u8], sealed: Vec<u8>| {
            let (ct, tag) = sealed.split_at(sealed.len() - 16);
            [&salt[..], iv, tag, ct].concat().iter().map(|x| format!("{x:02x}")).collect::<String>()
        };
        let v2 = format!("v2:{}", blob(&iv12, Aes256Gcm::new_from_slice(&key).unwrap().encrypt(Nonce::from_slice(&iv12), secret.as_bytes()).unwrap()));
        let old = blob(&iv16, AesGcm::<Aes256, U16>::new_from_slice(&key).unwrap().encrypt(aes_gcm::Nonce::<U16>::from_slice(&iv16), secret.as_bytes()).unwrap());
        for b in [&v2, &old] {
            assert_eq!(&*decrypt(b, pass).unwrap(), secret);
            assert!(decrypt(b, b"wrong").is_err());
        }
    }

    /// a pipe holding `bytes`, its write end closed (the reader sees EOF after them)
    fn pipe_with(bytes: &[u8]) -> libc::c_int {
        let mut fds = [0 as libc::c_int; 2];
        assert_eq!(unsafe { libc::pipe(fds.as_mut_ptr()) }, 0);
        assert_eq!(unsafe { libc::write(fds[1], bytes.as_ptr().cast(), bytes.len()) }, bytes.len() as isize);
        unsafe { libc::close(fds[1]) };
        fds[0]
    }

    /// what is left in a pipe, and close it
    fn rest(fd: libc::c_int) -> Vec<u8> {
        let mut out = Vec::new();
        let mut buf = [0u8; 256];
        loop {
            let n = unsafe { libc::read(fd, buf.as_mut_ptr().cast(), buf.len()) };
            if n <= 0 { break; }
            out.extend_from_slice(&buf[..n as usize]);
        }
        unsafe { libc::close(fd) };
        out
    }

    /// this process's locked memory (kB, /proc/self/status VmLck)
    fn locked_kb() -> u64 {
        let s = std::fs::read_to_string("/proc/self/status").unwrap();
        s.lines().find_map(|l| l.strip_prefix("VmLck:")).and_then(|v| v.trim().trim_end_matches("kB").trim().parse().ok()).unwrap()
    }

    /// Review WP-07 #15: a piped passphrase (`arbx campaign`'s pipe to a segment, `ssh … < pass`) is read with read(2)
    /// into a locked page: the first line only, so nothing after it is consumed; `\r`s dropped; wiped when it goes. An
    /// empty line is no passphrase. One longer than the page is refused, but only after it is read to its newline
    #[test]
    fn a_piped_passphrase_is_read_into_a_locked_page() {
        let before = locked_kb();
        let r = pipe_with(b"correct horse battery\r\nNEXT");
        let mut p = read_pass_fd(r).unwrap();
        assert_eq!(p.as_bytes(), b"correct horse battery");
        assert!(locked_kb() >= before + 4, "the page is locked: {} kB, {before} kB before", locked_kb());
        assert_eq!(rest(r), b"NEXT", "nothing past the newline was read");
        p.clear();
        assert!(p.is_empty() && p.page.0.iter().all(|b| *b == 0), "wiped");
        drop(p);
        assert_eq!(locked_kb(), before, "unlocked when it goes");
        // EOF without a newline: what was there
        let r = pipe_with(b"no newline");
        assert_eq!(read_pass_fd(r).unwrap().as_bytes(), b"no newline");
        let _ = rest(r);
        // an empty line, or nothing: no passphrase
        for input in [&b"\nsecond line"[..], b"", b"\r\n"] {
            let r = pipe_with(input);
            assert!(read_pass_fd(r).err().unwrap().to_string().contains("no passphrase"), "{input:?}");
            let _ = rest(r);
        }
        // the page's size: accepted; one byte more: refused, the line read to its end (the next line stays)
        let mut full = vec![b'y'; PASS_CAP];
        full.extend_from_slice(b"\nNEXT");
        let r = pipe_with(&full);
        let p = read_pass_fd(r).unwrap();
        assert!(p.len() == PASS_CAP && p.as_bytes() == &full[..PASS_CAP]);
        assert_eq!(rest(r), b"NEXT");
        drop(p);
        let mut long = vec![b'x'; PASS_CAP + 1];
        long.extend_from_slice(b"\nNEXT");
        let r = pipe_with(&long);
        assert!(read_pass_fd(r).err().unwrap().to_string().contains("longer than 4096"));
        assert_eq!(rest(r), b"NEXT");
    }
}
