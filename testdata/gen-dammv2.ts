/**
 * Test vectors for src/venues/dammv2.rs (Meteora DAMM v2), written to testdata/dammv2-vectors.json.
 *
 * Run from the arbed checkout so its .env (RMR_RPC_URL) and node_modules resolve:
 *   cd /home/moiz/arbed/arbed
 *   bun ../arb-lab/testdata/gen-dammv2.ts quotes             # pools + TS quotes + real swap instructions
 *   bun ../arb-lab/testdata/gen-dammv2.ts chain 600 [snaps]  # watch real swaps for 600 s and add them
 * Each mode rewrites only its own sections of the JSON. The RPC URL carries an api key: it is read from the
 * environment, never printed, never written.
 *
 * quotes: the real pool accounts (fetched once, at one confirmed slot) plus two clearly-marked synthetic variants
 *   (a rate-limiter base fee written over a real OnlyB pool, and a layout-0 copy of a real pool: no live pool of
 *   either kind was found). For each pool, a handful of (slot, now) points (live, around the fee scheduler's
 *   period boundaries, before activation, across the dynamic fee's filter/decay windows) and a ladder of amounts
 *   per direction, quoted by arbed's quoteDammV2Exact. `post` is the pool state after the swap, which arbed does
 *   not model: computed here from the program source (state/pool.rs apply_swap_result, update_pre/post_swap),
 *   independently of the Rust port.
 * chain: real swaps. Pool accounts are polled at "confirmed"; a swap whose pool had no other successful
 *   transaction between the previous snapshot and the swap gives an exact pre-state, its EvtSwap2 event gives
 *   the inputs and the program's own outputs, and the next snapshot (when nothing else touched the pool) the
 *   exact post-state account.
 */
import { decodeDammV2Pool, quoteDammV2Exact, dammV2FeeOnInput, type DammV2Pool } from "../../arbed/src/venues/quote/dammv2.ts";
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

const OUT = new URL("./dammv2-vectors.json", import.meta.url).pathname;
const PROGRAM = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG";
const SWAP = "f8c69e91e17587c8", SWAP2 = "414b3f4ceb5b5b88";
const EVT_SWAP2 = "e445a52e51cb9a1d" + "bd4233a826507599";   // anchor event-cpi tag + sha256("event:EvtSwap2")[..8]

/* ------------------------------------------- rpc ------------------------------------------- */
const RPC = process.env.RMR_RPC_URL;
if (!RPC) throw new Error("RMR_RPC_URL is not set (run from the arbed checkout)");
const scrub = (s: string) => s.split(RPC).join("<rpc>").replace(/api[-_]?key=[^&\s"]+/gi, "api-key=<redacted>");
let rid = 0;
async function rpc(method: string, params: unknown[], tries = 5): Promise<any> {
  for (let t = 0; ; t++) {
    try {
      const r = await fetch(RPC!, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: ++rid, method, params }) });
      if (r.status === 429 || r.status >= 500) throw new Error(`http ${r.status}`);
      const j: any = await r.json();
      if (j.error) throw new Error(`rpc error ${JSON.stringify(j.error).slice(0, 200)}`);
      return j.result;
    } catch (e: any) {
      if (t >= tries) throw new Error(scrub(`${method} failed: ${e?.message ?? e}`));
      await new Promise((res) => setTimeout(res, 400 * (t + 1)));
    }
  }
}
async function pmap<T, R>(xs: T[], n: number, f: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(xs.length); let k = 0;
  await Promise.all(Array.from({ length: n }, async () => { while (k < xs.length) { const i = k++; out[i] = await f(xs[i]!); } }));
  return out;
}
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function b58decode(s: string): Buffer {
  let n = 0n; for (const c of s) { const v = B58.indexOf(c); if (v < 0) throw new Error("bad base58"); n = n * 58n + BigInt(v); }
  const out: number[] = []; while (n > 0n) { out.push(Number(n & 255n)); n >>= 8n; }
  for (const c of s) { if (c === "1") out.push(0); else break; }
  return Buffer.from(out.reverse());
}
async function txOf(sig: string): Promise<any | null> {
  try { return await rpc("getTransaction", [sig, { encoding: "json", maxSupportedTransactionVersion: 1, commitment: "confirmed" }], 3); }
  catch (e: any) { console.error(String(e.message).slice(0, 120)); return null; }
}
/** every instruction of a transaction (top level and inner) with its account keys resolved */
function instructions(tx: any): { program: string; accounts: string[]; data: Buffer }[] {
  const keys: string[] = [...tx.transaction.message.accountKeys, ...(tx.meta.loadedAddresses?.writable ?? []), ...(tx.meta.loadedAddresses?.readonly ?? [])];
  const ixs = [...tx.transaction.message.instructions, ...(tx.meta.innerInstructions ?? []).flatMap((x: any) => x.instructions)];
  return ixs.map((ix: any) => ({ program: keys[ix.programIdIndex]!, accounts: ix.accounts.map((i: number) => keys[i]!), data: b58decode(ix.data) }));
}

/* -------------------------------------- the pool set -------------------------------------- */
const REAL: Record<string, string> = {
  "8Pm2kZpnxD3hoMmt4bjStX2Pw2Z9abpbHzZxMPqxPmie": "SOL/USDC: fee_version 0, static base fee, narrow custom range, BothToken",
  "HBsza3g1Gx5HMNCCTJYdAAeeCXFUTA9ttccW6ynKSXPw": "exponential time scheduler (cliff 50%, 120 x 60 s), dynamic fee, BothToken",
  "J4rRzkbA56h9U4EpzQthErFCdjp1onFDH98ND5uJ4eH6": "exponential time scheduler (cliff 99%, 180 x 1 s), dynamic fee",
  "GJ7nshYXh81PgDjDnwPVGJ9f28juTxD235MyuifTQcQo": "OnlyB, SLOT-activated, token a Token-2022",
  "2fckuYXUrwbA9LHKMP1az5DTFstFrRjqqbBstz7yvVXL": "OnlyB, SLOT-activated, fee_version 0, plain SPL",
  "DHQS3bVsiBUGvnpLoRb35ucbUmS1yrVEDgShk3BNPZhQ": "OnlyB + dynamic fee, token a Token-2022",
  "mjnUT8dmif6g3KLx4bFScM2D7zKe9FS22ErXjCreBxn": "BothToken + dynamic fee (large accumulator), token b Token-2022",
  "KKyUyWncRfakBZh2M318BFfdR6332WWu1NePd9amQtj": "market-cap scheduler linear (mode 3), OnlyB, dynamic fee",
  "C8BUgLyzT1ayVVbho1cjXRu5Dyrxd7SRZdrWjXUSQHzh": "market-cap scheduler exponential (mode 4), BothToken, dynamic fee",
  "Gr8MuhQ38MCh7bmpQXfgroEwQK58xT42zZbhSmDgeN5e": "Compounding + market-cap exponential + dynamic fee",
  "AehDkxVKERzq4A8M5EXLkctj4QFPNyJBwUBphkQsrdVW": "Compounding (50% compounding fee) + dynamic fee",
  "HZ9TNkqCutCgJJA2gi5qUytdVbmf2bAwS7Xf8a3cngoE": "Compounding + exponential time scheduler, Token-2022 both sides",
  "Z8ZVsi9GDTSAUJpUni1Jbarh3aWM69FbLA1VwQM1SBK": "BothToken, static fee, token a Token-2022",
};
const RL_BASE = "21a9JHhUTQsWZWin32dLzAV9fMzU2h3STZygdSxRoL6s";   // OnlyB, dynamic fee, plain SPL, timestamp-activated
const V0_BASE = "8Pm2kZpnxD3hoMmt4bjStX2Pw2Z9abpbHzZxMPqxPmie";

const u64le = (x: bigint) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(x); return b; };
const s = (x: unknown) => typeof x === "bigint" ? x.toString() : x;
const jsonable = (o: any): any => JSON.parse(JSON.stringify(o, (_k, v) => s(v)));

/* ---------------------- post-swap state, written from the program source ---------------------- */
const ceilDiv = (n: bigint, d: bigint) => (n + d - 1n) / d;
function isqrt(n: bigint): bigint {
  if (n < 2n) return n;
  let x = 1n << BigInt(Math.ceil(n.toString(2).length / 2)), y = (x + n / x) >> 1n;
  while (y < x) { x = y; y = (x + n / x) >> 1n; }
  return x;
}
const deltaBin = (binStepU128: bigint, a: bigint, b: bigint) => {
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return ((((hi << 64n) / lo) - (1n << 64n)) / binStepU128) * 2n;
};
/** state/pool.rs: update_layout_version_if_needed, update_pre_swap, apply_swap_result (+ update_post_swap) */
function postState(p: DammV2Pool, raw: Buffer, aToB: boolean, amountIn: bigint, now: bigint, q: { out: bigint; feeNumerator: bigint; nextSqrtPrice: bigint }) {
  let a = p.tokenAAmount, b = p.tokenBAmount;
  const L = p.liquidity, P = p.sqrtPrice;
  if (p.layoutVersion === 0) {   // concentrated get_reserves_amount, rounded up
    a = ceilDiv(L * (p.sqrtMaxPrice - P), P * p.sqrtMaxPrice);
    b = ceilDiv(L * (P - p.sqrtMinPrice), 1n << 128n);
  }
  const dynOn = raw[56] !== 0;
  const rd = (o: number, n: number) => { let v = 0n; for (let i = n - 1; i >= 0; i--) v = (v << 8n) | BigInt(raw[o + i]!); return v; };
  let ref = rd(104, 16), vref = rd(136, 16), va = rd(120, 16), last = rd(80, 8);
  const filter = rd(74, 2), decay = rd(76, 2), rf = rd(78, 2), binStepU128 = rd(88, 16), maxVa = rd(64, 4);
  if (dynOn) {
    const elapsed = now > last ? now - last : 0n;
    if (elapsed >= filter) { ref = P; vref = elapsed < decay ? (va * rf) / 10_000n : 0n; }
  }
  const fee = q.feeNumerator, onInput = dammV2FeeOnInput(p.collectFeeMode, aToB);
  const inFee = onInput ? ceilDiv(amountIn * fee, 1_000_000_000n) : 0n;
  const actualIn = amountIn - inFee;
  let gross: bigint;
  const U64 = (1n << 64n) - 1n;
  if (p.collectFeeMode === 2) {
    const [rIn, rOut] = aToB ? [a, b] : [b, a];
    if (rIn + actualIn > U64) return { fail: "reserve-overflow" };   // safe_add in calculate_*_from_amount_in
    gross = (rOut * actualIn) / (rIn + actualIn);
  } else {
    const N = q.nextSqrtPrice;
    gross = aToB ? (L * (P - N)) >> 128n : (L * (N - P)) / (P * N);
  }
  const outFee = onInput ? 0n : ceilDiv(gross * fee, 1_000_000_000n);
  if (gross - outFee !== q.out) throw new Error(`post-state reference disagrees with the TS quote (${gross} - ${outFee} != ${q.out})`);
  const total = inFee + outFee;
  const protocol = (total * BigInt(raw[48]!)) / 100n;
  const compounding = p.compoundingFeeBps > 0 ? ((total - protocol) * BigInt(p.compoundingFeeBps)) / 10_000n : 0n;
  if (aToB) { a += actualIn; b -= gross; } else { b += actualIn; a -= gross; }
  if (a < 0n || b < 0n) return { fail: "reserve-underflow" };   // safe_sub in apply_swap_result
  b += compounding;
  if (a > U64 || b > U64) return { fail: "reserve-overflow" };   // safe_add in apply_swap_result
  const next = p.collectFeeMode === 2 ? isqrt((b << 128n) / a) : q.nextSqrtPrice;
  if (dynOn) {
    const d = deltaBin(binStepU128, next, ref);
    const v = vref + d * 10_000n;
    va = v < maxVa ? v : maxVa;
    if (deltaBin(binStepU128, P, next) > 0n) last = now;
  }
  return { sqrtPrice: next, tokenAAmount: a, tokenBAmount: b, sqrtPriceReference: ref, volatilityReference: vref,
    volatilityAccumulator: va, lastUpdateTimestamp: last };
}

/* ------------------------------------------ quotes ------------------------------------------ */
async function quotes(existing: any) {
  const names = Object.keys(REAL);
  const r = await rpc("getMultipleAccounts", [names, { encoding: "base64", commitment: "confirmed" }]);
  const slot0 = BigInt(r.context.slot);
  const now0 = BigInt(await rpc("getBlockTime", [r.context.slot]).catch(() => Math.floor(Date.now() / 1000)));
  const raws: Record<string, { raw: Buffer; note: string }> = {};
  r.value.forEach((a: any, i: number) => {
    if (!a || a.owner !== PROGRAM) throw new Error(`${names[i]} missing or not a cp-amm account`);
    raws[names[i]!] = { raw: Buffer.from(a.data[0], "base64"), note: REAL[names[i]!]! };
  });
  // synthetic 1: a deprecated rate-limiter base fee written over a real OnlyB pool (no live one was found)
  const rlBase = (await rpc("getAccountInfo", [RL_BASE, { encoding: "base64", commitment: "confirmed" }])).value;
  const rl = Buffer.from(rlBase.data[0], "base64");
  const rlRef = decodeDammV2Pool(rl).tokenBAmount / 2000n || 1_000_000n;
  rl.fill(0, 8, 40);
  u64le(10_000_000n).copy(rl, 8);              // cliff 1%
  rl[16] = 2;                                  // base_fee_mode RateLimiter
  rl.writeUInt16LE(50, 8 + 14);                // fee_increment_bps
  rl.writeUInt32LE(3_600, 8 + 16);             // max_limiter_duration (seconds: timestamp-activated)
  rl.writeUInt32LE(4_000, 8 + 20);             // max_fee_bps 40%
  u64le(rlRef).copy(rl, 8 + 24);               // reference_amount
  u64le(now0 - 600n).copy(rl, 472);            // activation_point: the limiter window is open "now"
  raws["synthetic:rate-limiter"] = { raw: rl, note: `SYNTHETIC: ${RL_BASE} with a rate-limiter base fee (cliff 1%, +0.5%/step, max 40%, 3600 s, reference ${rlRef}) and activation_point now-600` };
  // synthetic 2: layout version 0 (token amounts not tracked yet; the program derives them from the curve first)
  const v0 = Buffer.from(raws[V0_BASE]!.raw);
  v0[696] = 0;
  raws["synthetic:layout-v0"] = { raw: v0, note: `SYNTHETIC: ${V0_BASE} with layout_version 0` };

  const pools: Record<string, any> = {};
  const vecs: any[] = [];
  for (const [name, { raw, note }] of Object.entries(raws)) {
    const p = decodeDammV2Pool(raw);
    pools[name] = { note, b64: raw.toString("base64"), ts: jsonable(p) };
    const pts: [string, bigint, bigint][] = [["live", slot0, now0]];
    const at = p.activationType, ap = p.activationPoint, bf = p.baseFee;
    const atPoint = (label: string, point: bigint) => pts.push(at === 0 ? [label, point, now0] : [label, slot0, point]);
    if (ap > 0n) atPoint("before-activation", ap - 1n);
    if ((bf.mode === 0 || bf.mode === 1) && bf.periodFrequency > 0n) {
      const pf = bf.periodFrequency, n = BigInt(bf.numberOfPeriod);
      for (const [l, k] of [["period-0", 0n], ["period-1", pf], ["period-1-minus", pf - 1n], ["period-mid", (n / 2n) * pf + 1n], ["period-last", (n - 1n) * pf], ["period-end", n * pf], ["period-past", n * pf + 777n]] as const)
        atPoint(l, ap + k);
    }
    if (bf.mode === 3 || bf.mode === 4) { atPoint("mcap-at-activation", ap); atPoint("mcap-expired", ap + BigInt(bf.schedulerExpirationDuration) + 1n); }
    if (bf.mode === 2) { atPoint("limiter-end", ap + BigInt(bf.maxLimiterDuration)); atPoint("limiter-over", ap + BigInt(bf.maxLimiterDuration) + 1n); }
    if (p.dynamicFee) {
      const d = p.dynamicFee, last = d.lastUpdateTimestamp;
      for (const [l, dt] of [["dyn-within-filter", 0n], ["dyn-decay-window", BigInt(d.filterPeriod)], ["dyn-after-decay", BigInt(d.decayPeriod)]] as const)
        pts.push([l, slot0, last + dt]);
    }
    const t22 = p.tokenAFlag !== 0 || p.tokenBFlag !== 0;
    for (const [label, slot, now] of pts) {
      if (now < 0n) continue;
      const currentPoint = at === 0 ? slot : now;
      for (const aToB of [true, false]) {
        const r = aToB ? p.tokenAAmount : p.tokenBAmount;
        const base = r > 0n ? r : 1_000_000_000n;
        const ladder = new Set<bigint>([1n, 3n, 1000n, base / 1_000_000_000n, base / 1_000_000n, base / 10_000n, base / 1000n, base / 100n,
          base / 10n, base / 2n, base * 2n, base * 50n, (1n << 64n) - 1n]);
        for (let amountIn of ladder) {
          if (amountIn <= 0n) continue;
          if (amountIn >= 1n << 64n) amountIn = (1n << 64n) - 1n;
          for (const t22ok of t22 && label === "live" ? [true, false] : [true]) {
            const q = quoteDammV2Exact({ pool: p, amountIn, aToB, currentPoint, transferFeeKnownZero: t22ok });
            const v: any = { pool: name, point: label, slot, now, aToB, amountIn, t22ok, exact: q.exact };
            if (q.exact) {
              v.out = q.out; v.feeNumerator = q.feeNumerator; v.nextSqrtPrice = q.nextSqrtPrice;
              const post = postState(p, raw, aToB, amountIn, now, q);
              if ("fail" in post) { v.exact = false; v.why = `post-${post.fail}`; v.tsSaysExact = true; }
              else v.post = post;
            } else v.why = q.why;
            vecs.push(jsonable(v));
          }
        }
      }
    }
  }
  const instructions = await sampleInstructions();
  const ok = vecs.filter((v) => v.exact).length;
  console.error(`slot ${slot0}: ${Object.keys(pools).length} pools, ${vecs.length} quote vectors (${ok} exact), ${instructions.length} instructions`);
  return { ...existing, generated: new Date().toISOString(), slot: slot0.toString(), pools, quotes: vecs, instructions };
}

/** real swap / swap2 instructions (top level or inner), with their accounts, for decode_swap_ix */
async function sampleInstructions() {
  const sigs = (await rpc("getSignaturesForAddress", [PROGRAM, { limit: 400, commitment: "confirmed" }])).filter((x: any) => !x.err);
  const got = new Map<string, any>();   // one per (discriminator, mode)
  for (const sig of sigs.slice(0, 120).map((x: any) => x.signature)) {
    if (got.size >= 8) break;
    const tx = await txOf(sig);
    if (!tx) continue;
    for (const ix of instructions(tx)) {
      if (ix.program !== PROGRAM) continue;
      const disc = ix.data.subarray(0, 8).toString("hex");
      if (disc !== SWAP && disc !== SWAP2) continue;
      const mode = disc === SWAP ? 0 : ix.data[24]!;
      const key = `${disc}/${mode}/${got.size < 4 ? got.size : ""}`;
      if (got.has(key) || [...got.keys()].filter((k) => k.startsWith(`${disc}/${mode}/`)).length >= 2) continue;
      got.set(key, { sig, kind: disc === SWAP ? "swap" : "swap2", swapMode: mode, data: ix.data.toString("base64"), accounts: ix.accounts,
        pool: ix.accounts[1], amount0: ix.data.readBigUInt64LE(8).toString(), amount1: ix.data.readBigUInt64LE(16).toString() });
    }
  }
  return [...got.values()];
}

/* ------------------------------------------- chain ------------------------------------------- */
async function watchList(): Promise<string[]> {
  const sigs = (await rpc("getSignaturesForAddress", [PROGRAM, { limit: 1000, commitment: "confirmed" }])).filter((x: any) => !x.err);
  const count = new Map<string, number>();
  await pmap(sigs.filter((_: any, i: number) => i % 5 === 0).map((x: any) => x.signature), 3, async (sig: string) => {
    const tx = await txOf(sig);
    if (!tx) return;
    for (const ix of instructions(tx)) {
      if (ix.program !== PROGRAM) continue;
      const disc = ix.data.subarray(0, 8).toString("hex");
      if (disc === SWAP || disc === SWAP2) count.set(ix.accounts[1]!, (count.get(ix.accounts[1]!) ?? 0) + 1);
    }
  });
  const busy = [...count.entries()].sort((a, b) => b[1] - a[1]).map((x) => x[0]);
  // plus arbed's own DAMM v2 pools (data/registry.json, when run from the arbed checkout): liquid, varied fee setups
  let registry: string[] = [];
  try { registry = JSON.parse(readFileSync("data/registry.json", "utf8")).filter((r: any) => r.venue === "DAMMv2").map((r: any) => r.pool); }
  catch { /* not in the arbed checkout */ }
  return [...new Set([...Object.keys(REAL), ...busy.slice(0, 40), ...registry])].slice(0, 100);
}

async function capture(list: string[], secs: number, file: string) {
  const last = new Map<string, string>();
  const t0 = Date.now(); let prev = 0;
  while (Date.now() - t0 < secs * 1000) {
    try {
      const r = await rpc("getMultipleAccounts", [list, { encoding: "base64", commitment: "confirmed" }], 2);
      if (r.context.slot !== prev) {
        prev = r.context.slot;
        r.value.forEach((a: any, j: number) => {
          if (!a) return;
          const b = a.data[0] as string, pool = list[j]!;
          if (last.get(pool) !== b) { last.set(pool, b); appendFileSync(file, JSON.stringify({ pool, slot: prev, b64: b }) + "\n"); }
          else appendFileSync(file, JSON.stringify({ pool, slot: prev, same: 1 }) + "\n");
        });
      }
    } catch (e: any) { console.error(String(e.message).slice(0, 120)); }
    await new Promise((res) => setTimeout(res, 250));
  }
}

function parseEvent(d: Buffer) {
  if (d.length < 16 + 180 || d.subarray(0, 16).toString("hex") !== EVT_SWAP2) return null;
  const e = d.subarray(16);
  const u64 = (o: number) => e.readBigUInt64LE(o).toString();
  return {
    pool: (() => { const B = e.subarray(0, 32); let n = 0n; for (const x of B) n = (n << 8n) | BigInt(x); let s = ""; while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; } for (const x of B) { if (x === 0) s = "1" + s; else break; } return s; })(),
    tradeDirection: e[32]!, collectFeeMode: e[33]!, hasReferral: e[34]! !== 0,
    amount0: u64(35), amount1: u64(43), swapMode: e[51]!,
    includedFeeInputAmount: u64(52), excludedFeeInputAmount: u64(60), amountLeft: u64(68), outputAmount: u64(76),
    nextSqrtPrice: (e.readBigUInt64LE(84) | (e.readBigUInt64LE(92) << 64n)).toString(),
    claimingFee: u64(100), protocolFee: u64(108), compoundingFee: u64(116), referralFee: u64(124),
    includedTransferFeeAmountIn: u64(132), includedTransferFeeAmountOut: u64(140), excludedTransferFeeAmountOut: u64(148),
    currentTimestamp: u64(156), reserveA: u64(164), reserveB: u64(172),
  };
}

/** apply_swap_result's reserve bookkeeping, from the event's own amounts only */
function linksTo(pre: Buffer, ev: any): boolean {
  const preA = pre.readBigUInt64LE(680), preB = pre.readBigUInt64LE(688), cfm = pre[484]!;
  const aToB = ev.tradeDirection === 0, onInput = !aToB && (cfm === 1 || cfm === 2);
  const exIn = BigInt(ev.excludedFeeInputAmount), out = BigInt(ev.outputAmount), comp = BigInt(ev.compoundingFee);
  const fees = BigInt(ev.claimingFee) + comp + BigInt(ev.protocolFee) + BigInt(ev.referralFee);
  const grossOut = onInput ? out : out + fees;
  const [a, b] = aToB ? [preA + exIn, preB - grossOut + comp] : [preA - grossOut, preB + exIn + comp];
  return pre[696] === 1 && a === BigInt(ev.reserveA) && b === BigInt(ev.reserveB);
}
function sameAsEvent(post: Buffer, ev: any): boolean {
  const sp = post.readBigUInt64LE(456) | (post.readBigUInt64LE(464) << 64n);
  return post.readBigUInt64LE(680) === BigInt(ev.reserveA) && post.readBigUInt64LE(688) === BigInt(ev.reserveB) && sp === BigInt(ev.nextSqrtPrice);
}

const MAX_CHAIN = 120;
async function chain(existing: any, secs: number, snapFile?: string) {
  const file = snapFile ?? `${tmpdir()}/dammv2-snaps-${process.pid}.jsonl`;
  if (!snapFile || !existsSync(file)) {
    const list = await watchList();
    console.error(`watching ${list.length} pools for ${secs} s -> ${file}`);
    await capture(list, secs, file);
  }
  // per pool: every poll's (slot, state)
  const obs = new Map<string, { slot: number; b64: string }[]>();
  for (const line of readFileSync(file, "utf8").split("\n")) {
    if (!line) continue;
    const o = JSON.parse(line);
    const arr = obs.get(o.pool) ?? (obs.set(o.pool, []), obs.get(o.pool)!);
    arr.push({ slot: o.slot, b64: o.b64 ?? arr[arr.length - 1]?.b64 });
  }
  const vecs: any[] = [];
  let skipped = 0;
  // the most varied pools first: compounding, a fee scheduler, the dynamic fee, slot activation
  const score = (b64: string) => { const d = Buffer.from(b64, "base64"); return (d[484] === 2 ? 8 : 0) + (d[16] !== 0 ? 8 : 0) + (d[56] !== 0 ? 4 : 0) + (d[480] === 0 ? 2 : 0); };
  const pools = [...obs.entries()].filter(([, a]) => new Set(a.map((x) => x.b64)).size > 1)
    .sort((x, y) => score(y[1][0]!.b64) - score(x[1][0]!.b64));
  console.error(`${pools.length} pools changed`);
  for (const [pool, arr] of pools) {
    if (vecs.length >= MAX_CHAIN) break;
    const lo = arr[0]!.slot, hi = arr[arr.length - 1]!.slot;
    // every transaction naming the pool in the window, failed ones included (they do not write)
    const sigs: any[] = [];
    let before: string | undefined;
    for (let page = 0; page < 10; page++) {
      const r = await rpc("getSignaturesForAddress", [pool, { limit: 1000, before, commitment: "confirmed" }]);
      sigs.push(...r);
      if (r.length < 1000 || r[r.length - 1].slot < lo) break;
      before = r[r.length - 1].signature;
    }
    const ok = sigs.filter((x) => !x.err && x.slot > lo && x.slot <= hi);
    let perPool = 0;
    for (const t of ok) {
      if (perPool >= 6 || vecs.length >= MAX_CHAIN) break;
      // the last snapshot before the swap's slot, with no other successful transaction on the pool after it
      const preIdx = arr.findLastIndex((x) => x.slot < t.slot);
      if (preIdx < 0) continue;
      const pre = arr[preIdx]!;
      const others = ok.filter((x) => x.signature !== t.signature && x.slot > pre.slot && x.slot <= t.slot);
      if (others.length) continue;
      const tx = await txOf(t.signature);
      if (!tx || tx.meta.err) continue;
      const evs = instructions(tx).filter((ix) => ix.program === PROGRAM).map((ix) => parseEvent(ix.data)).filter((e) => e && e.pool === pool);
      if (evs.length !== 1) continue;
      const ev = evs[0]!;
      // The snapshot slot is the RPC's context slot, which a load-balanced endpoint can report one slot off. So the
      // pre-state is only accepted when the event's own numbers (no quote math involved) link it to the reserves the
      // program reports after the swap; the post-state only when it carries exactly those reserves and that price.
      if (!linksTo(Buffer.from(pre.b64, "base64"), ev)) { skipped++; continue; }
      // the post-state account: the first snapshot at or after the swap's slot, when nothing else touched the pool
      const postObs = arr.find((x) => x.slot >= t.slot);
      const clean = postObs && !ok.some((x) => x.signature !== t.signature && x.slot > t.slot && x.slot <= postObs.slot)
        && sameAsEvent(Buffer.from(postObs.b64, "base64"), ev);
      vecs.push({ pool, sig: t.signature, slot: String(t.slot), pre: pre.b64, preSlot: String(pre.slot),
        post: clean ? postObs!.b64 : null, postSlot: clean ? String(postObs!.slot) : null, ...ev });
      perPool++;
    }
  }
  const modes = vecs.reduce((m: any, v) => ((m[v.swapMode] = (m[v.swapMode] ?? 0) + 1), m), {});
  console.error(`${skipped} candidate swaps dropped: their snapshot was not the state just before the swap`);
  console.error(`${vecs.length} chain vectors (by swap mode ${JSON.stringify(modes)}), ${vecs.filter((v) => v.post).length} with the post-swap account`);
  return { ...existing, chainGenerated: new Date().toISOString(), chain: vecs };
}

/* ------------------------------------------- main ------------------------------------------- */
const mode = process.argv[2];
const existing = existsSync(OUT) ? JSON.parse(readFileSync(OUT, "utf8")) : {};
let next: any;
if (mode === "quotes") next = await quotes(existing);
else if (mode === "chain") next = await chain(existing, Number(process.argv[3] ?? 600), process.argv[4]);
else throw new Error("usage: gen-dammv2.ts quotes | chain <seconds> [snapshot file]");
writeFileSync(OUT, JSON.stringify(next, null, 0) + "\n");
console.error(`wrote ${OUT}`);
