// Step 1: crawl MriyaNN8's signatures back ~24 h (read-only, public RPC). Writes sigs.jsonl.
const W = "MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X";
const RPC = process.env.RPC ?? "https://api.mainnet-beta.solana.com";
const HOURS = Number(process.env.HOURS ?? 24);
const D = import.meta.dir;
const rpc = async (m: string, p: unknown[]): Promise<any> => {
  for (let i = 0; i < 8; i++) {
    const r: any = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: m, params: p }) }).then((x) => x.json()).catch(() => null);
    if (r?.result !== undefined) return r.result;
    await Bun.sleep(1500 * (i + 1));
  }
  throw new Error(`${m} failed`);
};
const out: any[] = [];
let before: string | undefined; const stop = Date.now() / 1000 - HOURS * 3600;
for (let page = 0; page < 120; page++) {
  const r = await rpc("getSignaturesForAddress", [W, { limit: 1000, ...(before ? { before } : {}) }]);
  if (!r.length) break;
  out.push(...r); before = r.at(-1).signature;
  const t = r.at(-1).blockTime;
  if (page % 5 === 0) console.log(`page ${page}: ${out.length} sigs, back to ${new Date(t * 1000).toISOString()}`);
  if (t < stop) break;
  await Bun.sleep(350);
}
const kept = out.filter((s) => s.blockTime >= stop);
await Bun.write(`${D}/sigs.jsonl`, kept.map((s) => JSON.stringify({ sig: s.signature, slot: s.slot, t: s.blockTime, err: s.err })).join("\n") + "\n");
const ok = kept.filter((s) => !s.err).length;
console.log(`kept ${kept.length} sigs over ${((kept[0].blockTime - kept.at(-1).blockTime) / 3600).toFixed(2)} h | ok ${ok} (${((100 * ok) / kept.length).toFixed(1)}%) | ${(kept.length / ((kept[0].blockTime - kept.at(-1).blockTime) / 60)).toFixed(1)} tx/min`);
const byHour = new Map<string, { n: number; ok: number }>();
for (const s of kept) { const h = new Date(s.blockTime * 1000).toISOString().slice(0, 13); const v = byHour.get(h) ?? { n: 0, ok: 0 }; v.n++; if (!s.err) v.ok++; byHour.set(h, v); }
console.log("hour (UTC) | txs | ok | ok%");
for (const [h, v] of [...byHour.entries()].sort()) console.log(`${h} | ${v.n} | ${v.ok} | ${((100 * v.ok) / v.n).toFixed(0)}%`);
const errs = new Map<string, number>(); for (const s of kept) if (s.err) { const k = JSON.stringify(s.err); errs.set(k, (errs.get(k) ?? 0) + 1); }
console.log("top errors:"); for (const [k, v] of [...errs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10)) console.log(`  ${v}  ${k}`);
