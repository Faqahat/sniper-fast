#!/usr/bin/env node
// NEW WALLET + keystore in one step, offline (owner 10-24: create the Amsterdam edge wallet on the owner's own machine).
// Generates a fresh ed25519 Solana keypair in memory (Node's crypto, no packages, no network), asks the passphrase twice (no
// echo), writes the v3 keystore the bot reads (src/wallet.rs; same encryption code as tools/encrypt-keystore.mjs):
//   "v3:17:" + hex(salt 16 | iv 12 | tag 16 | ciphertext), key = scrypt(pass, salt, N=2^17, r=8, p=1, 32 bytes),
//   AES-256-GCM over the base58 64-byte secret key.
// usage:  node new-wallet-keystore.mjs wallet-ams.enc [--show-backup]
//   prints the wallet address; with --show-backup also the base58 secret ONCE (write it on paper, then clear the terminal).
import { writeFileSync, existsSync } from "node:fs";
import { generateKeyPairSync, scryptSync, randomBytes, createCipheriv, createDecipheriv, sign, verify } from "node:crypto";

const args = process.argv.slice(2);
const outFile = args.find((a) => !a.startsWith("--"));
const showBackup = args.includes("--show-backup");
if (!outFile) { console.error("usage: node new-wallet-keystore.mjs <out.enc> [--show-backup]"); process.exit(2); }
if (existsSync(outFile)) { console.error(`${outFile} exists: not overwriting`); process.exit(2); }

const A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function b58(bytes) {
  let n = 0n; for (const b of bytes) n = n * 256n + BigInt(b);
  let s = ""; while (n > 0n) { s = A[Number(n % 58n)] + s; n /= 58n; }
  for (const b of bytes) { if (b !== 0) break; s = "1" + s; }
  return s;
}

// the keypair: 32-byte seed + 32-byte public key (Solana's 64-byte secret key layout)
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const jwk = privateKey.export({ format: "jwk" });
const seed = Buffer.from(jwk.d, "base64url"), pub = Buffer.from(jwk.x, "base64url");
if (seed.length !== 32 || pub.length !== 32) { console.error("unexpected key sizes"); process.exit(1); }
const msg = randomBytes(32);
if (!verify(null, msg, publicKey, sign(null, msg, privateKey))) { console.error("key self-check failed"); process.exit(1); }
const secret = b58(Buffer.concat([seed, pub]));
const pubkey = b58(pub);
seed.fill(0);

async function ask(prompt) {
  if (!process.stdin.isTTY) {                       // tests: passphrase lines on stdin
    if (!ask.lines) ask.lines = (await import("node:fs")).readFileSync(0, "utf8").split("\n");
    return ask.lines.shift() ?? "";
  }
  process.stdout.write(prompt);
  process.stdin.setRawMode(true); process.stdin.resume();
  let s = "";
  return new Promise((res) => {
    const on = (buf) => {
      for (const c of buf.toString("utf8")) {
        if (c === "\r" || c === "\n") { process.stdin.setRawMode(false); process.stdin.pause(); process.stdin.off("data", on); process.stdout.write("\n"); return res(s); }
        if (c === "\u0003") process.exit(130);
        if (c === "\u007f") s = s.slice(0, -1); else s += c;
      }
    };
    process.stdin.on("data", on);
  });
}
const p1 = await ask("passphrase: "), p2 = await ask("again: ");
if (p1 !== p2) { console.error("the passphrases differ"); process.exit(1); }
if (p1.length < 16) { console.error("use a passphrase of at least 16 characters"); process.exit(1); }

const LOG_N = 17, salt = randomBytes(16), iv = randomBytes(12);
const k = scryptSync(Buffer.from(p1, "utf8"), salt, 32, { N: 1 << LOG_N, r: 8, p: 1, maxmem: 512 * 1024 * 1024 });
const c = createCipheriv("aes-256-gcm", k, iv);
const ct = Buffer.concat([c.update(secret, "utf8"), c.final()]), tag = c.getAuthTag();
const blob = `v3:${LOG_N}:` + Buffer.concat([salt, iv, tag, ct]).toString("hex");
const d = createDecipheriv("aes-256-gcm", k, iv); d.setAuthTag(tag);
if (Buffer.concat([d.update(ct), d.final()]).toString("utf8") !== secret) { console.error("self-check failed"); process.exit(1); }
writeFileSync(outFile, blob, { mode: 0o600 });
console.log(`wrote ${outFile} (scrypt 2^${LOG_N}): wallet ${pubkey}`);
if (showBackup) console.log(`BACKUP (base58 secret key; write it on paper, then clear this terminal): ${secret}`);
