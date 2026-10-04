// Read-only: v5 = pools hot in the last 3 h first (>= 2 sampled wins), then the rest of v4; same columns + recency.
const SOL = 120, WSOL = "So11111111111111111111111111111111111111112", USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";
const R = "/tmp/claude-1000/-home-moiz-arbed/c4565feb-db8e-455c-9c2f-d33da2185fd7/scratchpad";
const RPC = process.env.RPC!;
const rpc = async (m: string, p: unknown): Promise<any> => { for (let i = 0; i < 4; i++) { const r: any = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: m, params: p }) }).then((x) => x.json()).catch(() => null); if (r?.result !== undefined) return r.result; await Bun.sleep(500 * (i + 1)); } return null; };
const SUP = new Set(["DLMM", "PumpSwap", "RayCLMM", "Whirl", "RayCPMM", "DAMMv2", "PancakeCLMM", "RayAMMv4", "PumpCurve", "LaunchLab", "DBC"]);
const usd = (m: string, raw: number) => (m === WSOL ? (raw / 1e9) * SOL : m === USDC || m === USDT ? raw / 1e6 : NaN);
const reg: any[] = await Bun.file("/home/moiz/arbed/arbed/data/registry.json").json(); const byVault = new Map<string, any>(); for (const p of reg) { byVault.set(p.vault0, p); byVault.set(p.vault1, p); }
const rows = (await Bun.file(`${import.meta.dir}/rows2.jsonl`).text()).split("\n").filter(Boolean).map((l) => JSON.parse(l)).filter((r) => r.ok && r.gross !== null && r.swaps.length);
const recent = new Map<string, any>();
for (const r of rows) { const net = usd(r.startMint, r.gross) - (r.fee / 1e9) * SOL; if (!Number.isFinite(net)) continue; const seen = new Set<string>();
  for (const s of r.swaps) { if (!s.vIn || !s.vOut || !SUP.has(s.venue) || !s.poolGuess) continue; if (byVault.get(s.vIn) ?? byVault.get(s.vOut)) continue; const k = s.poolGuess; if (seen.has(k)) continue; seen.add(k);
    const p = recent.get(k) ?? { venue: s.venue, pool: k, vaults: [s.vIn, s.vOut], mints: [s.mintIn, s.mintOut], wins: 0, net: 0, lastT: 0 }; p.wins++; p.net += net; p.lastT = Math.max(p.lastT, r.t); recent.set(k, p); } }
const v3lines = (await Bun.file(`${R}/mriya6/mriya-seed-pools-2026-10-02-v4.csv`).text()).split("\n").filter(Boolean);
const head = v3lines[0]!.split(","), v3 = v3lines.slice(1).map((l) => Object.fromEntries(l.split(",").map((x, i) => [head[i], x])));
const v3pools = new Set(v3.map((x: any) => x.pool));
const hot = [...recent.values()].filter((p) => p.wins >= 2).sort((a, b) => b.net - a.net);
const newHot = hot.filter((p) => !v3pools.has(p.pool));
// symbols for new tokens
const sym = new Map<string, string>(); for (const p of newHot) for (const m of p.mints) if (![WSOL, USDC, USDT].includes(m) && !sym.has(m)) { const a = await rpc("getAsset", { id: m }); sym.set(m, a?.content?.metadata?.symbol ?? m.slice(0, 6)); await Bun.sleep(60); }
const name = (m: string) => (m === WSOL ? "SOL" : m === USDC ? "USDC" : m === USDT ? "USDT" : sym.get(m) ?? m.slice(0, 6));
const ev2b = (await Bun.file(`${R}/run2b/2026-10-01T21-56-59-391Z/events.jsonl`).text()).split("\n").filter((l) => l.includes('"kind":"seed-pool"')).map((l) => JSON.parse(l));
const screen = new Map(ev2b.map((e: any) => [e.pool, `${e.result}${e.why ? ":" + e.why : ""}`]));
const now = Date.now() / 1000;
const out: string[][] = [];
// 1) hot now: every pool with >= 2 wins in the last 3 h (in v3 or new)
for (const p of hot) { const old = v3.find((x: any) => x.pool === p.pool); out.push([p.venue, p.pool, p.vaults[0], p.vaults[1], p.mints[0], p.mints[1], old?.pair ?? `${name(p.mints[0])}/${name(p.mints[1])}`, String(p.wins), p.net.toFixed(2), ((now - p.lastT) / 3600).toFixed(1), old ? "v4+hot" : "NEW-hot", screen.get(p.pool) ?? "new"]); }
// 2) the rest of v3, in its order, until 100
for (const x of v3 as any[]) { if (out.length >= 100) break; if (hot.some((p) => p.pool === x.pool)) continue; out.push([x.venue, x.pool, x.vault_a, x.vault_b, x.mint_a, x.mint_b, x.pair, "0", "0", x.last_win_hours_ago, "v4-only", x.run2b_screen]); }
const lines = ["venue,pool,vault_a,vault_b,mint_a,mint_b,pair,his_wins_3h_sample,his_net_usd_3h_sample,last_win_hours_ago,source,run2b_screen", ...out.slice(0, 100).map((r) => r.join(","))];
const file = `${import.meta.dir}/mriya-seed-pools-2026-10-03-v5.csv`; await Bun.write(file, lines.join("\n") + "\n");
const cnt = (k: string) => out.slice(0, 100).filter((r) => r[10] === k).length;
console.log(`last 3 h: ${rows.length} wins decoded; hot pools (>= 2 wins, not watched by us): ${hot.length}; of these NEW (not in v3): ${newHot.length}`);
console.log(`v4: ${Math.min(100, out.length)} pools -> ${file} | hot & already in v3 ${cnt("v4+hot")}, NEW hot ${cnt("NEW-hot")}, rest of v3 ${cnt("v4-only")}`);
console.log("new hot:", newHot.slice(0, 12).map((p) => `${p.venue} ${name(p.mints[0])}/${name(p.mints[1])} ${p.wins}w $${p.net.toFixed(0)}`).join(" | ") || "none");
const vv: Record<string, number> = {}; for (const r of out.slice(0, 100)) vv[r[0]!] = (vv[r[0]!] ?? 0) + 1; console.log("by venue:", JSON.stringify(vv));
