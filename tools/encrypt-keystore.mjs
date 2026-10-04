#!/usr/bin/env node
// Offline keystore encryption for arbx (the format arb-lab introduced). Run on the OFFLINE machine where the wallet was generated:
//   node encrypt-keystore.mjs <keypair.json from solana-keygen> <out.enc>
// It asks for the passphrase twice (no echo) and writes the v3 keystore arbx reads (src/wallet.rs):
//   "v3:17:" + hex(salt 16 | iv 12 | tag 16 | ciphertext), key = scrypt(pass, salt, N=2^17, r=8, p=1, 32 bytes),
//   AES-256-GCM over the base58 secret key. Needs only Node.js (or Bun); no network, no packages.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { scryptSync, randomBytes, createCipheriv, createDecipheriv } from "node:crypto";

const [, , inFile, outFile] = process.argv;
if (!inFile || !outFile) { console.error("usage: node encrypt-keystore.mjs <keypair.json> <out.enc>"); process.exit(2); }
if (existsSync(outFile)) { console.error(`${outFile} exists: not overwriting`); process.exit(2); }

const A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function b58(bytes) {
  let n = 0n; for (const b of bytes) n = n * 256n + BigInt(b);
  let s = ""; while (n > 0n) { s = A[Number(n % 58n)] + s; n /= 58n; }
  for (const b of bytes) { if (b !== 0) break; s = "1" + s; }
  return s;
}
const key = Uint8Array.from(JSON.parse(readFileSync(inFile, "utf8")));
if (key.length !== 64) { console.error(`key file holds ${key.length} bytes, not 64`); process.exit(1); }
const secret = b58(key);
const pubkey = b58(key.slice(32));

// passphrase: from the terminal with echo off; if stdin is not a terminal, its first line (for tests)
async function ask(prompt) {
  if (!process.stdin.isTTY) {
    if (!ask.lines) ask.lines = readFileSync(0, "utf8").split("\n");
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
// self-check: decrypt what we wrote
const d = createDecipheriv("aes-256-gcm", k, iv); d.setAuthTag(tag);
if (Buffer.concat([d.update(ct), d.final()]).toString("utf8") !== secret) { console.error("self-check failed"); process.exit(1); }
writeFileSync(outFile, blob, { mode: 0o600 });
console.log(`wrote ${outFile} (scrypt 2^${LOG_N}): wallet ${pubkey}`);
