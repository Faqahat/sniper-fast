// Read-only: decode a spread sample of MriyaNN8's last-24h transactions into per-swap pool records (vault-keyed).
import { existsSync } from "node:fs";
const W = "MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X";
const RPC = process.env.RPC!; const D = import.meta.dir, CACHE = `${D}/cache`, OLD = `${D}/../mriya6/cache`;
const N_OK = Number(process.env.N_OK ?? 2000), N_FAIL = Number(process.env.N_FAIL ?? 500), CONC = Number(process.env.CONC ?? 6);
const rpc = async (m: string, p: unknown[]): Promise<any> => { for (let i = 0; i < 6; i++) { const r: any = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: m, params: p }) }).then((x) => x.json()).catch(() => null); if (r?.result !== undefined) return r.result; await Bun.sleep(700 * (i + 1)); } return null; };
const A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const b58 = (s: string) => { let n = 0n; for (const c of s) n = n * 58n + BigInt(A.indexOf(c)); const o: number[] = []; while (n > 0n) { o.unshift(Number(n & 255n)); n >>= 8n; } for (const c of s) { if (c === "1") o.unshift(0); else break; } return Buffer.from(o); };
const DEX: Record<string, string> = {
  LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo: "DLMM", cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG: "DAMMv2", Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB: "DAMMv1",
  whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc: "Whirl", CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK: "RayCLMM", CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C: "RayCPMM",
  "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "RayAMMv4", pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA: "PumpSwap", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "PumpCurve",
  LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj: "LaunchLab", dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN: "DBC", SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe: "SolFi",
  PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY: "Phoenix", HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq: "PancakeCLMM", REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2: "Byreal",
  JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4: "Jupiter", "2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3c": "Lifinity", obriQD1zbpyLz95G5n7nJe6a4DPjpFwa5XYPoNm113y: "Obric",
  ZERor4xhbUycZ6gb9ntrhqscUcZmAbQDjEAtCf4hbZY: "ZeroFi", TessVdML9pBGgG9yGks7o4HewRaXVAMuoVj4x83GLQH: "Tessera", GAMMA7meSFWaBXF25oSUgmGRwaW6sCMFLmBNiMSdbHVT: "Gamma",
  SV2EYYJyRz2YhfXwXnhNAevDEui5Q6yrfyo13WtupPF: "SolFiV2", HumidiFi: "HumidiFi", "9H6tua7jkLhdm3w8BvgpTn5LZNU7g4ZynDmCiNN3q6Rp": "HumidiFi",
};
const TOKEN_PROGS = new Set(["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]);
const WSOL = "So11111111111111111111111111111111111111112", USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";
const sigs = (await Bun.file(`${D}/sigs.jsonl`).text()).split("\n").filter(Boolean).map((l) => JSON.parse(l));
const ok = sigs.filter((s: any) => !s.err), bad = sigs.filter((s: any) => s.err);
const spread = (arr: any[], n: number) => { const step = Math.max(1, arr.length / n); const out: any[] = []; for (let i = 0; i < arr.length && out.length < n; i += step) out.push(arr[Math.floor(i)]); return out; };
const pick = [...spread(ok, N_OK), ...spread(bad, N_FAIL)];
const pathOf = (sig: string) => (existsSync(`${CACHE}/${sig}.json`) ? `${CACHE}/${sig}.json` : existsSync(`${OLD}/${sig}.json`) ? `${OLD}/${sig}.json` : null);
const todo = pick.filter((s) => !pathOf(s.sig)).map((s) => s.sig);
console.log(`sample ${pick.length} (${N_OK} ok + ${N_FAIL} failed); to fetch ${todo.length}`);
let done = 0;
await Promise.all(Array.from({ length: CONC }, async () => { while (todo.length) { const sig = todo.shift()!; const tx = await rpc("getTransaction", [sig, { maxSupportedTransactionVersion: 1, encoding: "jsonParsed", commitment: "confirmed" }]); if (tx) await Bun.write(`${CACHE}/${sig}.json`, JSON.stringify(tx)); if (++done % 250 === 0) console.log(`  fetched ${done}`); await Bun.sleep(60); } }));
const rows: any[] = [];
for (const s of pick) {
  const p = pathOf(s.sig); if (!p) continue;
  const tx: any = await Bun.file(p).json(); if (!tx) continue;
  const m = tx.meta, msg = tx.transaction.message;
  const keys: any[] = msg.accountKeys; const key = (i: number) => keys[i]?.pubkey; const writable = new Map<string, boolean>(keys.map((k: any) => [k.pubkey, !!k.writable]));
  const tokAcc = new Map<string, { mint: string; owner: string }>(); for (const b of [...(m.preTokenBalances ?? []), ...(m.postTokenBalances ?? [])]) tokAcc.set(key(b.accountIndex), { mint: b.mint, owner: b.owner });
  const isW = (a: string) => a === W || tokAcc.get(a)?.owner === W;
  // compute budget (v0 instructions or v1 transactionConfig)
  let cuPrice: number | null = null, cuLimit: number | null = null, prio: number | null = null;
  for (const i of msg.instructions) if (i.programId === "ComputeBudget111111111111111111111111111111" && i.data) { const d = b58(i.data); if (d[0] === 2) cuLimit = d.readUInt32LE(1); if (d[0] === 3) cuPrice = Number(d.readBigUInt64LE(1)); }
  if (msg.transactionConfig) { cuLimit = msg.transactionConfig.computeUnitLimit ?? cuLimit; prio = msg.transactionConfig.priorityFee ?? null; }
  const nsig = tx.transaction.signatures.length; const priority = m.fee - 5000 * nsig;
  // own program instruction (the arb), its data fields
  const own = msg.instructions.find((i: any) => !i.parsed && i.programId !== "ComputeBudget111111111111111111111111111111" && !DEX[i.programId]);
  const ownData = own?.data ? b58(own.data) : null;
  const amountField = ownData && ownData.length >= 9 ? Number(ownData.readBigUInt64LE(1)) : null;
  const minProfitField = ownData && ownData.length >= 23 ? Number(ownData.readBigUInt64LE(ownData.length - 23)) : null;
  // tips: SOL transfers from W to anyone (top-level or inner)
  const inner = (m.innerInstructions ?? []).flatMap((g: any) => g.instructions);
  const tips = [...msg.instructions, ...inner].filter((i: any) => i.program === "system" && i.parsed?.type === "transfer" && i.parsed.info.source === W && !isW(i.parsed.info.destination)).map((i: any) => ({ to: i.parsed.info.destination, lamports: i.parsed.info.lamports }));
  // swaps: DEX instruction at stackHeight 2, its token transfers at stackHeight >= 3
  const swaps: any[] = []; let cur: any = null;
  for (const i of inner) {
    if (i.stackHeight === 2) { cur = null; if (DEX[i.programId]) { cur = { venue: DEX[i.programId], program: i.programId, accounts: i.accounts ?? [], xfers: [] }; swaps.push(cur); } else if (!TOKEN_PROGS.has(i.programId) && i.programId !== "11111111111111111111111111111111" && i.programId !== "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL") { cur = { venue: `?${i.programId.slice(0, 6)}`, program: i.programId, accounts: i.accounts ?? [], xfers: [] }; swaps.push(cur); } continue; }
    if (cur && i.parsed && /^transfer(Checked)?$/.test(i.parsed.type) && (i.program === "spl-token" || i.program === "spl-token-2022")) {
      const src = i.parsed.info.source, dst = i.parsed.info.destination, amt = Number(i.parsed.info.amount ?? i.parsed.info.tokenAmount?.amount);
      cur.xfers.push({ src, dst, amt, mint: i.parsed.info.mint ?? tokAcc.get(src)?.mint ?? tokAcc.get(dst)?.mint });
    }
  }
  const swapRecs = swaps.map((sw) => {
    const inX = sw.xfers.filter((x: any) => isW(x.src) && !isW(x.dst)).sort((a: any, b: any) => b.amt - a.amt)[0];
    const outX = sw.xfers.filter((x: any) => !isW(x.src) && isW(x.dst)).sort((a: any, b: any) => b.amt - a.amt)[0];
    const vIn = inX?.dst, vOut = outX?.src;
    const poolGuess = sw.accounts.find((a: string) => writable.get(a) && !isW(a) && !tokAcc.has(a) && !DEX[a] && !TOKEN_PROGS.has(a)) ?? null;
    return { venue: sw.venue, program: sw.program, vIn, vOut, mintIn: inX?.mint ?? tokAcc.get(vIn)?.mint, mintOut: outX?.mint ?? tokAcc.get(vOut)?.mint, amtIn: inX?.amt, amtOut: outX?.amt, poolGuess, nAcc: sw.accounts.length };
  });
  // start mint and round-trip gross (first leg in, last leg out of the same mint)
  const startMint = swapRecs[0]?.mintIn ?? null; const last = swapRecs.at(-1);
  const gross = startMint && last?.mintOut === startMint && swapRecs[0].amtIn ? last.amtOut - swapRecs[0].amtIn : null;
  rows.push({ sig: s.sig, slot: s.slot, t: s.t, ok: !m.err, err: m.err ? JSON.stringify(m.err) : null, version: tx.version, fee: m.fee, priority, cuPrice, cuLimit, prio, cuUsed: m.computeUnitsConsumed, tips, ownProgram: own?.programId ?? null, ownLen: ownData?.length ?? null, amountField, minProfitField, startMint, gross, swaps: swapRecs, allKeys: m.err ? keys.map((k: any) => k.pubkey) : undefined });
}
await Bun.write(`${D}/rows2.jsonl`, rows.map((r) => JSON.stringify(r)).join("\n") + "\n");
const wins = rows.filter((r) => r.ok);
console.log(`rows ${rows.length}: ok ${wins.length}, failed ${rows.length - wins.length}; wins with swaps decoded ${wins.filter((r) => r.swaps.length).length}; round-trip gross known ${wins.filter((r) => r.gross !== null).length}`);
const vc: Record<string, number> = {}; for (const r of wins) for (const s of r.swaps) vc[s.venue] = (vc[s.venue] ?? 0) + 1; console.log("venues in wins:", JSON.stringify(Object.entries(vc).sort((a, b) => b[1] - a[1])));
