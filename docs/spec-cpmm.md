# Byte-exact spec: Raydium AMM v4, Raydium CPMM and PumpSwap in arbed

Repo: `/home/moiz/arbed/arbed`. Nothing was modified. All paths below are under `/home/moiz/arbed/arbed/`.

Path correction: the fee file is `src/venues/quote/fees.ts`. There is no `src/quote/`.

Data paths (`src/config/paths.ts:10-13`):
```ts
export const DATA_DIR = process.env.ARB_V2_DATA_DIR ?? resolve(import.meta.dir, "../../data");
export const REGISTRY_PATH = process.env.REGISTRY_PATH ?? join(DATA_DIR, "registry.json");
export const TEMPLATES_PATH = process.env.TEMPLATES_PATH ?? join(DATA_DIR, "templates.json");
export const PUMPFEE_PATH = process.env.PUMPFEE_PATH ?? join(DATA_DIR, "pumpfee.json");
```

---

## 0. Plumbing shared by all three venues

### 0.1 Venue table (`src/venues/venues.ts:87-108`, verbatim)
```ts
  { name: "RayCPMM", program: "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", family: "RayCPMM", kind: "cpmm",
    // pool + both vaults: the tradable reserve is vault balance MINUS fees owed, held in the pool
    subscriptions: 3, maxAccounts: 14, signer: 0, userAccts: [4, 5], order: "dir",
    discriminators: ["8fbe5adac41e33de"], inputAt8: ["8fbe5adac41e33de"], feeFromConfig: "cpmm" },
  { name: "PumpSwap", program: "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", family: "PumpSwap", kind: "cpmm",
    ...
    subscriptions: 3, maxAccounts: 30, signer: 1, userAccts: [5, 6], order: "mint",
    discriminators: ["33e685a4017f83ad", "c62e1552b4d9e870", "66063d1201daebea", "b712469c946da122"],
    // the other two PumpSwap variants exist but their byte-8 semantics were never verified
    inputAt8: ["33e685a4017f83ad", "c62e1552b4d9e870"],
    feeMeasured: true },
  { name: "RayAMMv4", program: "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", family: "RayAMMv4", kind: "cpmm",
    // pool (fee + need_take_pnl) + coin vault + pc vault. Encoded as swap_base_in_v2 (tag 16, 17-byte
    // data, 8 accounts, no OpenBook accounts): [0] spl-token [1] amm W [2] authority [3] coinVault W
    // [4] pcVault W [5] userSource W [6] userDest W [7] owner S. Vaults are coin/pc ordered, users by
    // direction. A 1-byte TAG, not an 8-byte discriminator: amount_in is the u64 at byte 1 and
    // minimum_out at byte 9, so bytes 8..16 straddle both fields -- inputAt8 MUST stay empty.
    // swap_base_in (tag 9) exists too, but takes 17-18 accounts including dead OpenBook ones.
    subscriptions: 3, maxAccounts: 18, signer: 7, userAccts: [5, 6], order: "dir",
    discriminators: ["10"], inputAt8: [], amountOffset: 1, inputTags: ["10"], feeFromPool: true },
```

**Orientation.** Registry rows are reoriented at boot to the decoder's mint order (`src/market/registry-orient.ts`). In every swap path, direction is `zeroForOne = reg.t0 === tin`. Per venue:
- RayAMMv4: t0 = coin, t1 = pc.
- RayCPMM: t0 = mint0, t1 = mint1.
- PumpSwap: t0 = base, t1 = quote.

### 0.2 Reserves: the Store's cpmm snapshot (`src/market/store.ts`)

Vault balance is read from the SPL token account (`store.ts:172-175`):
```ts
const tokenAmount = (raw: Buffer): bigint => {
  if (raw.length < 72) throw new Error(`token account too short: ${raw.length}`);
  return raw.readBigUInt64LE(64);
};
```

Pool-part value for a cpmm pool (`store.ts:228-229`):
```ts
            ? { feeOwed0: d.feeOwed0 ?? 0n, feeOwed1: d.feeOwed1 ?? 0n, status: d.status, ...(r.venue === "RayAMMv4" ? ammV4Part(d) : {}), ...(r.venue === "RayCPMM" ? cpmmCreatorPart(raw) : {}), ...(r.venue === "PumpSwap" ? pumpCreatorPart(raw) : {}) }
```

Snapshot (`store.ts:327-343`):
```ts
    } else if (r.kind === "cpmm") {
      const v0 = take("vault0"), v1 = take("vault1");
      if (!v0) return this.reject("missing:vault0");
      if (!v1) return this.reject("missing:vault1");
      // reserves must come from vaults and fees-owed captured at the SAME slot
      const owed0: bigint = poolPart.value.feeOwed0 ?? 0n, owed1: bigint = poolPart.value.feeOwed1 ?? 0n;
      const sub = (a: bigint, b: bigint) => (a > b ? a - b : 0n);
      snap.r0 = sub(v0.value as bigint, owed0);
      snap.r1 = sub(v1.value as bigint, owed1);
      if (snap.r0 <= 0n || snap.r1 <= 0n) return this.reject("empty-reserves");
      snap.status = poolPart.value.status;   // pipeline refuses a RayCPMM leg whose swap bit is disabled
      if (poolPart.value.cpmmCreator) snap.cpmmCreator = poolPart.value.cpmmCreator;
      if (poolPart.value.pumpCoinCreator) snap.pumpCoinCreator = poolPart.value.pumpCoinCreator;
      if (poolPart.value.pumpVirtualQuote !== undefined) snap.pumpVirtualQuote = poolPart.value.pumpVirtualQuote;
      // RayAMMv4: owed = need_take_pnl_coin/pc (decode.ts), subtracted above exactly like the chain's
      // calc_total_without_take_pnl_no_orderbook; fee and open time ride along from the same pool part.
      if (r.venue === "RayAMMv4") { snap.ammFeeNum = poolPart.value.ammFeeNum; snap.ammFeeDen = poolPart.value.ammFeeDen; snap.openTime = poolPart.value.openTime; }
```

Freshness limits come from `DEFAULT_LIMITS = { maxSkewSlots: 1, maxAgeSlots: 4 }` (`store.ts:132`), applied across all three parts (pool, vault0, vault1). Boot subscribes both vaults for `["RayCPMM", "PumpSwap", "RayAMMv4"]` (`src/market/boot.ts:221-226`).

### 0.3 The nexus-v2 wrapper and amount_offset

Instruction layout (`src/execution/nexus-v2.ts:6-9`):
```
 *  data:     [0] version 0x02  [1] n_legs  [2..10] amount_in u64  [10..18] min_profit u64 (>= 1)
 *            per leg: n_accounts u8, amount_offset u8, data_len u16
 *            then every leg's data, in order
 *  accounts: authority, quote account, then per leg: output account, program, leg accounts..
```

Per leg, the account order is: `outAccount` (W), `program` (RO), then the venue keys exactly as `buildSwap` produced them. The flags `NATIVE_IN 0x80` and `NATIVE_OUT 0x40` sit in the top bits of n_accounts. They are only used for PumpCurve, never for these three venues.

On chain, `patch_amount` writes the leg's input amount as a u64 LE at `data[offset..offset+8]` (`program/nexus-arb-v2/src/lib.rs:223-228`, called at :769). The allowlist is at lib.rs:674-680.

Offset selection (`src/execution/builder.ts:267-279`, verbatim):
```ts
export function legAmountOffset(venue: string, ix: TransactionInstruction): { offset: number } | { error: string } {
  const venueDef = VENUES.find((v) => v.name === venue);
  const isNonStandard = venueDef?.amountOffset !== undefined;
  const amountOffset = isNonStandard ? venueDef!.amountOffset! : AMOUNT_OFFSET;
  const verifiedTags: ReadonlySet<string> = isNonStandard ? new Set(venueDef!.inputTags ?? []) : INPUT_AT_8;
  const discLen = isNonStandard ? 1 : 8;
  const disc = Buffer.from(ix.data.subarray(0, discLen)).toString("hex");
  if (!verifiedTags.has(disc)) return { error: `amount-offset-unverified(${ix.programId.toBase58().slice(0, 6)}:${disc})` };
  if (amountOffset + 8 > ix.data.length) {
    return { error: `amount-offset-out-of-range(${ix.programId.toBase58().slice(0, 6)}:offset=${amountOffset},len=${ix.data.length})` };
  }
  return { offset: amountOffset };
}
```

Resulting amount_offset per venue:
- RayAMMv4: **1**
- RayCPMM: **8**
- PumpSwap: **8**, but only for `sell` and `buy_exact_quote_in`. A `buy` (66063d…) template is refused here.

**Min-out is always 1.** Every leg is built with `minOut: 1n` (`src/execution/attempt.ts:493-495`). Profit is enforced on chain by `check_profit` and `minProfitLamports`.

**Builder preamble shared by all venues** (`src/venues/encoders.ts:401-414`):
- Refuse a template whose program is not in `ALLOWLIST`.
- Refuse a template with more accounts than `MAX_ACCOUNTS_OF[venue]`: RayCPMM 14, PumpSwap 30, RayAMMv4 18.
- Then:
```ts
  const tplForward = tpl.dir === tin;                 // was the template already in our direction?
  const zeroForOne = reg.t0 === tin;
  const setSigner = (i: number) => { if (acc[i]) { acc[i]!.pubkey = payer; acc[i]!.isSigner = true; acc[i]!.isWritable = true; } };
```

**Template selection** (`src/execution/attempt.ts:110-114`):
```ts
  const templateOf = (row: any, tin: string, st: any) => {
    const t = templates[row.pool];
    if (t && row.venue === "DLMM" && !String(t.data).startsWith(DLMM_SWAP2)) return synthTemplate(row, tin, st) ?? t;
    return t ?? synthTemplate(row, tin, st);
  };
```

Leg state for these venues (`attempt.ts:105`):
```ts
export const plainLegState = (snap: any) => ({ r0: snap.r0, r1: snap.r1, pumpCoinCreator: snap.pumpCoinCreator, curve: snap.curve, slot: snap.slot });
```

`synthTemplate` (`encoders.ts:235-243`):
```ts
  if (reg.venue === "RayAMMv4") return rayAmmV4Template(reg);
  ...
  if (reg.venue === "RayCPMM") return cpmmTemplate(reg);
  ...
  if (reg.venue === "PumpSwap") return pumpSwapTemplate({ ...reg, pumpCoinCreator: st?.pumpCoinCreator ?? reg.pumpCoinCreator }, tin, reg.pumpGlobal);
```

### 0.4 Token programs, Token-2022, WSOL

**User token accounts** are always the payer's ATA, computed with the mint's recorded program (`src/execution/accounts.ts:25-32`):
```ts
  const ataOf = (mint: string): PublicKey => {
    ...
    const pk = getAssociatedTokenAddressSync(
      new PublicKey(mint), payer.publicKey, false, tokenProgramFor(mint), ASSOCIATED_TOKEN_PROGRAM_ID);
```
`tokenProgramFor` returns `mintProgram.get(mint) ?? TOKEN_PROGRAM_ID`. `mintProgram` is filled from the registry `t0Prog`/`t1Prog === "t22"` (`boot.ts:131-132`) or from hot-add.

**Transfer fees** are modelled outside the venue math, in `evaluateRoute` (`src/strategy/pipeline.ts:478-483`):
```ts
    const sent = leg.inFee ? Number(amountAfterTransferFee(BigInt(Math.floor(amt)), leg.inFee.bps, leg.inFee.maxFee)) : amt;
    ...
    const q = quoteLeg(leg.input, sent);
    ...
    const received = leg.outFee ? Number(amountAfterTransferFee(BigInt(q.out), leg.outFee.bps, leg.outFee.maxFee)) : q.out;
```
The fee function itself (`src/venues/quote/transfer-fee.ts:55-63`):
```ts
  const raw = (amount * BigInt(bps) + (MAX_BASIS_POINTS - 1n)) / MAX_BASIS_POINTS;
  return raw < maximumFee ? raw : maximumFee;
```
- bps and cap come from the registry `t0FeeBps`/`t1FeeBps`/`t0MaxFee`/`t1MaxFee` (`src/strategy/costs.ts:18-33`). A missing cap is treated as uncapped (u64 max).
- `MAX_MID_TRANSFER_FEE_BPS` defaults to 0 (`settings.ts:525`), so any route whose mid mint charges a fee is refused.

**Mints and vaults refused outright:**
- `src/market/pool-screen.ts:15-31` refuses Token-2022 mints with a transfer hook, NonTransferable, DefaultAccountState=Frozen, or Paused.
- It also refuses frozen vaults (token-account byte 108 == 2).
- Hot-add refuses any Token-2022 transfer-fee mint (`src/market/hot-add.ts:153`).

**Token program per venue:**
- RayAMMv4 refuses Token-2022 outright.
- RayCPMM sets token programs per side from `t0Prog`/`t1Prog`.
- PumpSwap takes them from template slots [11]/[12], or from `t0Prog`/`t1Prog` in the synthetic template.

**WSOL.** None of the three venues has native handling. `nativeFlags` returns false unless `venue === "PumpCurve"` (`src/venues/curves.ts:37-40`). WSOL is an ordinary SPL mint held in the payer's WSOL ATA, pre-funded with `arbed wrap` (`src/cli/ops/wrap-sol.ts`). There is no wrap, unwrap or close inside a trade.

**Mid-route ATAs** are created idempotently before the route instruction when the wallet neither holds the mint nor already has the account (`attempt.ts:431-443`):
```ts
      if (!needsAta(m)) return [];
      const prog = tokenProgramFor(m);
      return [createAssociatedTokenAccountIdempotentInstruction(payer.publicKey, ataOf(m), payer.publicKey, new PublicKey(m), prog, ASSOCIATED_TOKEN_PROGRAM_ID)];
```

### 0.5 CU budget (`src/execution/cu-budget.ts`)
```ts
export const CU_SAFETY_MARGIN = 1.10;
...
  RayAMMv4: { base: 20_000, perCrossing: 0, perStep: 0 },
  RayCPMM: { base: 35_000, perCrossing: 0, perStep: 0 },
  PumpSwap: { base: 100_000, perCrossing: 0, perStep: 0 },
...
export const V2_OVERHEAD_CU = 29_000;
export const CU_LIMIT_CEILING = 600_000;
export const CU_LIMIT_FLOOR = 30_000;
export const ATA_CREATE_CU = 30_000;
...
  const sum = legs.reduce((s, l) => s + legCu(l), V2_OVERHEAD_CU) + (opts?.ataCreations ?? 0) * ATA_CREATE_CU;
  const raw = Math.ceil(sum * CU_SAFETY_MARGIN);
  const units = clampAndRound(sum * CU_SAFETY_MARGIN);   // ceil to 1000, clamp [30k, 600k]
```
The comment at lines 23-24 gives the measured maxima: PumpSwap 91,041, RayAMMv4 15,479, RayCPMM 24,860, overhead 28,612.

### 0.6 Post-trade prediction, cpmm branch (shared; `src/strategy/predict.ts:96-103`, verbatim)
```ts
  if (input.kind === "cpmm") {
    const q = quoteLeg(input, amountIn);
    if (!q.exact || q.cpmmNetIn === undefined || q.cpmmGrossOut === undefined) return { ok: false, why: q.why ?? "cpmm-quote-inexact" };
    const netIn = BigInt(Math.round(q.cpmmNetIn)), gross = BigInt(Math.round(q.cpmmGrossOut));
    const r0 = input.zeroForOne ? s.r0! + netIn : s.r0! - gross;
    const r1 = input.zeroForOne ? s.r1! - gross : s.r1! + netIn;
    return { ok: true, snap: { ...s, r0, r1 } };
  }
```

Exact-output pending swaps are first converted to an input by bisection on `quoteLeg` (`predict.ts:34-47`):
```ts
export function solveExactIn(input: LegInput, amountOut: number): { ok: true; amountIn: number } | { ok: false; why: string } {
  if (!(amountOut > 0) || !Number.isSafeInteger(amountOut)) return { ok: false, why: "exact-out-bad-amount" };
  const outOf = (x: number) => { const q = quoteLeg(input, x); return q.exact ? q.out : NaN; };
  let hi = Math.max(1, amountOut), got = outOf(hi);
  for (let i = 0; i < 64 && got < amountOut; i++) { hi *= 2; if (hi > Number.MAX_SAFE_INTEGER) return { ok: false, why: "exact-out-unreachable" }; got = outOf(hi); }
  if (!(got >= amountOut)) return { ok: false, why: Number.isNaN(got) ? "exact-out-quote-inexact" : "exact-out-unreachable" };
  let lo = 0;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2), o = outOf(mid);
    if (Number.isNaN(o)) return { ok: false, why: "exact-out-quote-inexact" };
    if (o >= amountOut) hi = mid; else lo = mid;
  }
  return { ok: true, amountIn: hi };
}
```

### 0.7 Pending decode, shared parts (`src/strategy/pending.ts`)

`u64` returns NaN when the data is too short. `push` drops the swap unless pool, direction and a safe-integer amount are all known.
```ts
const u64 = (d: Uint8Array, at: number) => (d.byteLength >= at + 8 ? Number(Buffer.from(d.buffer, d.byteOffset, d.byteLength).readBigUInt64LE(at)) : NaN);
...
  const dirByAta = (reg: PendingReg | undefined, user: string | undefined, userIn: string | undefined): boolean | null => {
    if (!reg || !user || !userIn) return null;
    if (userIn === ataOf(user, reg.t0, reg.t0Prog ?? TOKEN_PROGRAM)) return true;
    if (userIn === ataOf(user, reg.t1, reg.t1Prog ?? TOKEN_PROGRAM)) return false;
    return null;
  };
  const push = (pool, zeroForOne, signer, amt, exactOut, sqrtPriceLimit?) => {
    if (!pool || zeroForOne === null || !ok(amt)) return;
    const reg = regOf(pool);
    if (!reg || reg.venue !== v.name) return;
    const sw: PendingSwap = exactOut ? { pool, venue: v.name, zeroForOne, amountIn: NaN, amountOut: amt, signer: signer ?? "" }
      : { pool, venue: v.name, zeroForOne, amountIn: amt, signer: signer ?? "" };
```

When a venue instruction names one of our pools but cannot be decoded, a placeholder `amountIn: NaN` entry is pushed (`pending.ts:84-87`) and the caller drops the whole transaction (`src/engine/run.ts:201-204`).

`fullyVisible` (`pending.ts:66-68`): a non-benign instruction of any other program must not name a readable (venue) program or an unresolved account.

---

## 1. Raydium AMM v4 (`675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`)

**Execution gate.** RayAMMv4 is gated by `VENUES_NEEDING_UPGRADE = new Set(["RayAMMv4", "DAMMv2"])`. It is not executable unless `PROGRAM_UPGRADED=1` (`src/config/settings.ts:41-43`).

### 1.1 Pool layout (`src/venues/decode.ts:88-105`, verbatim)
```ts
/** Raydium AMM v4 AmmInfo (752 bytes, #[repr(C)], raydium-io/raydium-amm program/src/state.rs):
 *    status@0 nonce@8 coinDecimals@32 pcDecimals@40 (all u64)
 *    Fees@128: tradeFeeNum@144 tradeFeeDen@152 swapFeeNum@176 swapFeeDen@184
 *    StateData@192: needTakePnlCoin@192 needTakePnlPc@200 poolOpenTime@224
 *    coinVault@336 pcVault@368 coinMint@400 pcMint@432 lpMint@464 openOrders@496 market@528
 *  t0 = coin, t1 = pc (on-chain order). swap_base_in_v2 prices off (vault - need_take_pnl) for each
 *  side (Calculator::calc_total_without_take_pnl_no_orderbook) with fee = ceil(in*swapNum/swapDen)
 *  taken off the input; OpenBook balances play no part. The pool account is NOT written by a swap
 *  (only vaults move), so need_take_pnl is as current as the pool account's last write. */
export const decRayAMMv4=(d:Buffer):Partial<PoolState>=>{
  if(d.length<752) throw new Error(`RayAMMv4 account too short: ${d.length}`);
  const swapFeeNum=u64(d,176), swapFeeDen=u64(d,184);
  return { kind:"cpmm", t0:pk(d,400), t1:pk(d,432), d0:Number(u64(d,32)), d1:Number(u64(d,40)),
    vault0:pk(d,336), vault1:pk(d,368), status:Number(u64(d,0)), nonce:Number(u64(d,8)),
    feeBps: swapFeeDen>0n ? Number(swapFeeNum)/Number(swapFeeDen)*1e4 : NaN,
    swapFeeNum, swapFeeDen, feeOwed0:u64(d,192), feeOwed1:u64(d,200), openTime:Number(u64(d,224)),
    lpMint:pk(d,464), openOrders:pk(d,496), market:pk(d,528) } as any;
};
```

Store extras (`store.ts:169-170`):
```ts
const ammV4Part = (d: any): { ammFeeNum: bigint; ammFeeDen: bigint; openTime: number } =>
  ({ ammFeeNum: d.swapFeeNum, ammFeeDen: d.swapFeeDen, openTime: d.openTime });
```

### 1.2 Reserves
```
r0 = coinVault.amount − need_take_pnl_coin(@192)
r1 = pcVault.amount − need_take_pnl_pc(@200)
```
Both are floored at 0 (store.ts code above). Only the swap fee (@176/@184) is used; the trade fee (@144/@152) is not.

### 1.3 Quote, exact-in only, integer-exact (`src/strategy/pipeline.ts`)

Status gate (`:74-76`):
```ts
export const RAYAMMV4_SWAP_STATUSES: ReadonlySet<number> = new Set([1, 6, 7]);
```

Math (`:78-93`):
```ts
/** Raydium AMM v4 swap_base_in_v2, integer-exact (processor.rs process_swap_base_in_v2 + math.rs):
 *    fee    = ceil(amountIn * swapFeeNum / swapFeeDen)
 *    netIn  = amountIn - fee
 *    out    = floor(rOut * netIn / (rIn + netIn))
 *  where rIn/rOut are vault balances minus need_take_pnl on each side. */
export function rayAmmV4NetIn(amountIn: bigint, feeNum: bigint, feeDen: bigint): bigint {
  if (feeDen <= 0n) return 0n;
  const fee = (amountIn * feeNum + feeDen - 1n) / feeDen;
  return amountIn - fee;
}
export function rayAmmV4SwapOut(amountIn: bigint, rIn: bigint, rOut: bigint, feeNum: bigint, feeDen: bigint): bigint {
  if (amountIn <= 0n || rIn <= 0n || rOut <= 0n || feeDen <= 0n) return 0n;
  const netIn = rayAmmV4NetIn(amountIn, feeNum, feeDen);
  if (netIn <= 0n) return 0n;
  return (rOut * netIn) / (rIn + netIn);
}
```

Leg branch (`:348-361`):
```ts
  if (s.venue === "RayAMMv4") {
    if (s.ammFeeNum === undefined || s.ammFeeDen === undefined || s.ammFeeDen <= 0n || s.ammFeeNum >= s.ammFeeDen) return { out: 0, exact: false, why: "ammv4-fee-missing" };
    if (typeof s.status !== "number" || !RAYAMMV4_SWAP_STATUSES.has(s.status)) return { out: 0, exact: false, why: `ammv4-swap-not-permitted(status=${s.status})` };
    if (s.status === 7 && (s.openTime ?? 0) > Date.now() / 1000) return { out: 0, exact: false, why: "ammv4-not-open-yet" };
    if (!(amountInRaw > 0) || !Number.isSafeInteger(Math.floor(amountInRaw))) return { out: 0, exact: false, why: "ammv4-bad-input" };
    const amtIn = BigInt(Math.floor(amountInRaw));
    const out = rayAmmV4SwapOut(amtIn, rIn, rOut, s.ammFeeNum, s.ammFeeDen);
    if (out <= 0n || out >= rOut) return { out: 0, exact: false, why: "ammv4-output-out-of-range" };
    return { out: Number(out), exact: true, feeRate1e6: Number((s.ammFeeNum * 1_000_000n) / s.ammFeeDen),
      cpmmNetIn: Number(rayAmmV4NetIn(amtIn, s.ammFeeNum, s.ammFeeDen)), cpmmGrossOut: Number(out) };
  }
```
Exact-out is not quoted directly; it goes through `solveExactIn` (§0.6). Unlike the other two venues, there is no 1/50-of-reserve floor here.

### 1.4 Swap instruction the bot builds

Constants and helpers (`src/venues/encoders.ts:71-87`):
```ts
export const RAYAMMV4_SWAP_BASE_IN_V2_TAG = 16;
export const RAYAMMV4_AMOUNT_OFFSET = 1;
const SPL_TOKEN = new PublicKey("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
export function rayAmmV4Authority(nonce?: number): PublicKey {
  const prog = new PublicKey(RAYAMMV4_PROGRAM), seed = Buffer.from("amm authority");
  if (typeof nonce === "number" && nonce >= 0 && nonce <= 255) return PublicKey.createProgramAddressSync([seed, Buffer.from([nonce])], prog);
  return PublicKey.findProgramAddressSync([seed], prog)[0];
}
export function rayAmmV4Template(reg: { t0: string }): Tpl {
  return { prog: RAYAMMV4_PROGRAM, data: "10" + "00".repeat(16), accts: [], dir: reg.t0, alts: [] };
}
```

Encoder branch (`encoders.ts:819-841`):
```ts
      if (tpl.prog !== RAYAMMV4_PROGRAM) { ...; return { error: `ammv4-program-${tpl.prog.slice(0, 8)}` }; }
      if (!reg.vault0 || !reg.vault1) { ...; return { error: "ammv4-no-vaults" }; }
      if (reg.t0Prog === "t22" || reg.t1Prog === "t22") return { error: "ammv4-token-2022-not-supported" };   // program asserts spl_token
      const fwd = tin === reg.t0 && tout === reg.t1, rev = tin === reg.t1 && tout === reg.t0;
      if (!fwd && !rev) { ...; return { error: "ammv4-mints-not-this-pool" }; }
      const keys = [
        { pubkey: SPL_TOKEN, isSigner: false, isWritable: false },
        { pubkey: new PublicKey(reg.pool), isSigner: false, isWritable: true },
        { pubkey: rayAmmV4Authority(reg.nonce), isSigner: false, isWritable: false },
        { pubkey: new PublicKey(reg.vault0), isSigner: false, isWritable: true },   // coin vault (t0), fixed order
        { pubkey: new PublicKey(reg.vault1), isSigner: false, isWritable: true },   // pc vault (t1), fixed order
        { pubkey: ataOf(tin), isSigner: false, isWritable: true },
        { pubkey: ataOf(tout), isSigner: false, isWritable: true },
        { pubkey: payer, isSigner: true, isWritable: true },
      ];
      const d = Buffer.alloc(17);
      d[0] = RAYAMMV4_SWAP_BASE_IN_V2_TAG;
      d.writeBigUInt64LE(amountIn, RAYAMMV4_AMOUNT_OFFSET); d.writeBigUInt64LE(minOut, 9);
```

Summary:
- **Data (17 bytes):** `[0]=0x10`, `[1..9] amount_in u64 LE`, `[9..17] min_out u64 LE` (always 1).
- **amount_offset:** 1.
- **Accounts:** 8, all derived from the registry row. Any template's accounts are ignored, including the 3 harvested ones.
- **Authority:** `create_program_address(["amm authority", [nonce]])`. The nonce comes from the registry row field `nonce` (150 of 153 rows, e.g. 254). Without it the bot falls back to `find_program_address(["amm authority"])`. The canonical authority is `5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1`.

### 1.5 Pending decode (`src/strategy/pending.ts:39-43`, `:119-127`)
```ts
// raydium-amm, not Anchor (1-byte tag). v2 (tags 16 in / 17 out): 8 accounts, pool @1, user_in @5, owner @7. v1 (tags 9 in
// / 11 out): 17 or 18 accounts (with or without target_orders), pool @1, user source len-3, owner len-1. Base-in: amount_in
// @1; base-out: max_in @1, amount_out @9.
const RAYAMMV4_TAGS: Record<number, { v2: boolean; exactOut: boolean }> = { 16: { v2: true, exactOut: false }, 17: { v2: true, exactOut: true },
  9: { v2: false, exactOut: false }, 11: { v2: false, exactOut: true } };
...
  if (v.family === "RayAMMv4") {
    const tag = RAYAMMV4_TAGS[ix.data[0] ?? -1];
    if (!tag || ix.data.byteLength < 17) return;
    const n = ix.accounts.length;
    if (tag.v2 ? n < 8 : n !== 17 && n !== 18) return;
    const pool = ix.accounts[1], user = ix.accounts[tag.v2 ? 7 : n - 1], userIn = ix.accounts[tag.v2 ? 5 : n - 3];
    push(pool, dirByAta(pool ? regOf(pool) : undefined, user, userIn), user, u64(ix.data, tag.exactOut ? 9 : 1), tag.exactOut);
    return;
  }
```
Direction requires the user's source account to be their canonical ATA of t0 (zeroForOne) or t1. Otherwise the swap is unreadable.

### 1.6 Prediction and CU
- Prediction is the cpmm branch of §0.6. Inputs: `cpmmNetIn = amountIn − ceil(fee)`, `cpmmGrossOut = out`.
- CU: `RayAMMv4: { base: 20_000 }`.

---

## 2. Raydium CPMM (`CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`)

### 2.1 Pool layout (`src/venues/decode.ts:72-86`, verbatim)
```ts
/** Raydium CPMM PoolState (637 bytes). Offsets were read off a live pool by scanning for the
 *  pubkeys a real SwapBaseInput instruction passed, not taken from an IDL:
 *    ammConfig@8 vault0@72 vault1@104 mint0@168 mint1@200 observation@296
 *    authBump@328 status@329 mint0Dec@331 mint1Dec@332
 *    protocolFee0@341 protocolFee1@349 fundFee0@357 fundFee1@365
 ... */
export const decRayCPMM=(d:Buffer):Partial<PoolState>=>({
  kind:"cpmm", t0:pk(d,168), t1:pk(d,200), d0:d[331], d1:d[332],
  vault0:pk(d,72), vault1:pk(d,104), ammConfig:pk(d,8), observation:pk(d,296),
  status:d[329], feeBps:25,
  feeOwed0:u64(d,341)+u64(d,357), feeOwed1:u64(d,349)+u64(d,365),
} as any);
```

Creator-fee gate (`src/venues/quote/cpmm-creator-fee.ts:47-50`, `:64-76`):
```ts
export const CPMM_CREATOR_FEE_ON_OFFSET = 389;
export const CPMM_ENABLE_CREATOR_FEE_OFFSET = 390;
export const CPMM_CREATOR_FEES_TOKEN0_OFFSET = 397;
export const CPMM_CREATOR_FEES_TOKEN1_OFFSET = 405;
...
  const raw = d[CPMM_CREATOR_FEE_ON_OFFSET]!;
  if (raw > CreatorFeeOn.OnlyToken1) throw new Error(`cpmm creator_fee_on out of range: ${raw}`);
  const flag = d[CPMM_ENABLE_CREATOR_FEE_OFFSET]!;
  if (flag > 1) throw new Error(`cpmm enable_creator_fee is not a bool: ${flag}`);
```
`enum CreatorFeeOn { BothToken = 0, OnlyToken0 = 1, OnlyToken1 = 2 }`.

AmmConfig (`src/venues/quote/fees.ts:83-93`):
```ts
export function decodeCpmmAmmConfig(d: Buffer): CpmmAmmConfig {
  if (d.length < 116) throw new Error(`cpmm AmmConfig too short: ${d.length}`);
  return {
    tradeFeeRate: Number(d.readBigUInt64LE(12)),
    protocolFeeRate: Number(d.readBigUInt64LE(20)),
    fundFeeRate: Number(d.readBigUInt64LE(28)),
    creatorFeeRate: Number(d.readBigUInt64LE(108)),
  };
}
export const cpmmRate1e6 = (c: CpmmAmmConfig): number => c.tradeFeeRate + c.creatorFeeRate;
```

### 2.2 Reserves
```
r0 = vault0 − (protocol_fees_token_0@341 + fund_fees_token_0@357)
r1 = vault1 − (protocol_fees_token_1@349 + fund_fees_token_1@365)
```
Creator fees @397/@405 are decoded but **not** subtracted (see §4).

### 2.3 Quote, exact-in (`src/strategy/pipeline.ts`)

Constants:
- `RAYCPMM_STATUS_SWAP_DISABLED_BIT = 2` (`:72`)
- `CPMM_MAX_RESERVE_DIVISOR = 50` (`:26`)

Leg branch (`:339-347`, `:375-390`):
```ts
  if (s.r0 === undefined || s.r1 === undefined) return { out: 0, exact: false, why: "cpmm-snapshot-incomplete" };
  const rIn = input.zeroForOne ? s.r0 : s.r1, rOut = input.zeroForOne ? s.r1 : s.r0;
  if (rIn <= 0n || rOut <= 0n) return { out: 0, exact: false, why: "cpmm-empty-reserves" };
  const status = (s as Snapshot & { status?: number }).status;
  if (s.venue === "RayCPMM" && typeof status === "number" && ((status >> RAYCPMM_STATUS_SWAP_DISABLED_BIT) & 1) === 1) {
    return { out: 0, exact: false, why: "cpmm-swap-disabled" };
  }
  ...
  const netIn = afterFee1e6(amountInRaw, input.feeRate1e6);
  const gross = Math.floor((Number(rOut) * netIn) / (Number(rIn) + netIn));
  if (gross * CPMM_MAX_RESERVE_DIVISOR > Number(rOut)) {
    return { out: 0, exact: false, why: `cpmm-trade-exceeds-1/${CPMM_MAX_RESERVE_DIVISOR}-of-reserve` };
  }
  const outRate = input.outputFeeRate1e6 ?? 0;
  const out = outRate > 0 ? Math.max(0, gross - Math.ceil((gross * outRate) / 1e6)) : gross;
  return { out, exact: true, feeRate1e6: input.feeRate1e6, cpmmNetIn: netIn, cpmmGrossOut: gross };
```

Input fee (`fees.ts:208-212`):
```ts
export function afterFee1e6(amountIn: number, rate1e6: number): number {
  if (!(rate1e6 >= 0)) throw new Error(`bad rate ${rate1e6}`);
  const fee = Math.ceil((amountIn * rate1e6) / RATE_1E6);
  return Math.max(0, amountIn - fee);
}
```

Fee rate actually used (`pipeline.ts:591-609`):
```ts
  let feeRate1e6: number | undefined = r.feeRate1e6;
  let outputFeeRate1e6 = 0;
  if (a.clmmConfig) {
    const cfg = decodeCpmmAmmConfig(a.clmmConfig.raw);
    if (snap.cpmmCreator) {
      const split = cpmmFeeSplit(snap.cpmmCreator, cfg, a.zeroForOne);
      feeRate1e6 = split.inputRate1e6;
      outputFeeRate1e6 = split.outputRate1e6;
    } else {
      feeRate1e6 = cpmmRate1e6(cfg);
    }
  }
```
- **No caller passes `clmmConfig`** (checked: `detect.ts:200`, `attempt.ts:123` and `:303`, `shadow.ts:72`). So the live rate is the registry's `Math.round(p.feeBps * 100)` (`boot.ts:127`), charged on the input with `outputFeeRate1e6 = 0`.
- Hot-added pools get `ac.tradeFeeRate + adjustCreatorFeeRate(pc, ac.creatorFeeRate)` (`hot-add.ts:239-243`), also charged on the input.

The unused output-side split (`cpmm-creator-fee.ts:101-110`):
```ts
  const creator = adjustCreatorFeeRate(pool, config.creatorFeeRate);
  return isCreatorFeeOnInput(pool, zeroForOne)
    ? { inputRate1e6: config.tradeFeeRate + creator, outputRate1e6: 0 }
    : { inputRate1e6: config.tradeFeeRate, outputRate1e6: creator };
```

### 2.4 Swap instruction (`swap_base_input`)

Encoder branch (`encoders.ts:786-817`):
```ts
      //   [0] payer  [1] authority PDA  [2] ammConfig  [3] poolState
      //   [4] userIn [5] userOut  [6] vaultIn [7] vaultOut
      //   [8] tokenProgIn [9] tokenProgOut  [10] mintIn [11] mintOut  [12] observation
      if (acc.length < 13) { ...; return { error: `cpmm-accounts-${acc.length}` }; }
      if (data.subarray(0, 8).toString("hex") !== "8fbe5adac41e33de") { ... return { error: `cpmm-disc-...` }; }   // SwapBaseOutput takes amount_OUT at byte 8
      if (data.length < 24) return { error: `cpmm-data-${data.length}` };
      setSigner(0);
      if (!reg.vault0 || !reg.vault1) { ...; return { error: "cpmm-no-vaults" }; }
      const inIs0 = tin === reg.t0;
      const progOf = (flag: string | undefined) => (flag === "t22" ? TOKEN_2022 : SPL_TOKEN);
      acc[6]!.pubkey = new PublicKey(inIs0 ? reg.vault0 : reg.vault1);
      acc[7]!.pubkey = new PublicKey(inIs0 ? reg.vault1 : reg.vault0);
      acc[8]!.pubkey = progOf(inIs0 ? reg.t0Prog : reg.t1Prog);
      acc[9]!.pubkey = progOf(inIs0 ? reg.t1Prog : reg.t0Prog);
      acc[10]!.pubkey = new PublicKey(tin); acc[11]!.pubkey = new PublicKey(tout);
      acc[4]!.pubkey = ataOf(tin); acc[5]!.pubkey = ataOf(tout);
      acc[4]!.isWritable = true; acc[5]!.isWritable = true;
      data.writeBigUInt64LE(amountIn, 8); data.writeBigUInt64LE(minOut, 16);
```

Synthetic template with IDL flags, used when no template was harvested (`encoders.ts:109-119`):
```ts
export const RAYCPMM_AUTHORITY = "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL";
export function cpmmTemplate(reg: { pool: string; t0: string; ammConfig?: string; observation?: string }): Tpl | undefined {
  if (!reg.ammConfig || !reg.observation) return undefined;
  ...
  return { prog: RAYCPMM_PROGRAM_ID, data: "8fbe5adac41e33de" + "00".repeat(16), dir: reg.t0, alts: [],
    accts: [m(ph, true), m(RAYCPMM_AUTHORITY, false), m(reg.ammConfig, false), m(reg.pool, true),
      m(ph, true), m(ph, true), m(ph, true), m(ph, true), m(ph, false), m(ph, false), m(ph, false), m(ph, false),
      m(reg.observation, true)] } as Tpl;
}
```

Summary:
- **Data (24 bytes):** `8fbe5adac41e33de | amount_in u64 @8 | min_out u64 @16`. amount_offset is 8.
- **Account sources:** [1] authority is a constant, the PDA `["vault_and_lp_mint_auth_seed"]` (encoders.ts:105). [2] is pool@8 and [12] is pool@296. In all 40 registry templates these three come from the harvested template.
- **Writable flags:** the harvested template's `isWritable` is message-level writability (`scripts/data/refresh-registry.ts:102-104`). That can mark the ammConfig or the mints W, and the encoder keeps those flags. The IDL flags are as in `cpmmTemplate` above: payer S/W, pool W, user and vault accounts W, observation W, everything else RO.

### 2.5 Pending decode (`pending.ts:34-35`, `:142-146`)
```ts
const CPMM_SWAP_BASE_INPUT = "8fbe5adac41e33de";
const CPMM_SWAP_BASE_OUTPUT = "37d96256a34ab4ad";   // max_amount_in @8, amount_out @16
...
  } else if (v.family === "RayCPMM" && (disc === CPMM_SWAP_BASE_INPUT || disc === CPMM_SWAP_BASE_OUTPUT)) {
    // accounts: [0] payer [1] authority [2] amm_config [3] pool_state [4] input_token [5] output_token
    // [6] input_vault [7] output_vault ...
    const pool = ix.accounts[3], reg = pool ? regOf(pool) : undefined, inVault = ix.accounts[6], exactOut = disc === CPMM_SWAP_BASE_OUTPUT;
    push(pool, reg && inVault === reg.vault0 ? true : reg && inVault === reg.vault1 ? false : null, ix.accounts[0], u64(ix.data, exactOut ? 16 : 8), exactOut);
```
This branch runs only if `ix.data.byteLength >= 16` (pending.ts:128).

### 2.6 Prediction and CU
- Prediction is §0.6, with `cpmmNetIn = afterFee1e6(...)` and `cpmmGrossOut = gross`, i.e. before the output-side skim.
- CU: `RayCPMM: { base: 35_000 }`.

### 2.7 Template example (data/templates.json, pool FxeRAf7v…)
```
{"prog":"CPMMoo8L…","data":"8fbe5adac41e33de0e6ef45f080000000000000000000000","dir":"oreoU2P8…","alts":[…2 ALTs]}
accts: 0 payer W | 1 GpMZbSM2… | 2 ammConfig W* | 3 pool W | 4 userIn W | 5 userOut W | 6 vaultIn W | 7 vaultOut W |
       8 Tokenkeg | 9 Tokenz | 10 mintIn W* | 11 mintOut W* | 12 observation W     (* message-level writability)
```

---

## 3. PumpSwap (`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`)

### 3.1 Pool layout

Decoder (`src/venues/decode.ts:65-70`):
```ts
/** PumpSwap Pool: disc@0 poolBump@8 index@9(u16) creator@11 baseMint@43 quoteMint@75
 *  lpMint@107 poolBaseTokenAccount@139 poolQuoteTokenAccount@171 lpSupply@203 */
export const decPumpSwap=(d:Buffer):Partial<PoolState>=>({
  kind:"cpmm", t0:pk(d,43), t1:pk(d,75), feeBps:30,
  vault0:pk(d,139), vault1:pk(d,171),
} as any);
```

Store part (`store.ts:149-154`):
```ts
const pumpCreatorPart = (raw: Buffer): { pumpCoinCreator?: string; pumpVirtualQuote?: bigint } => ({
  ...(raw.length >= 243 ? { pumpCoinCreator: new PublicKey(raw.subarray(211, 243)).toBase58() } : {}),
  ...(raw.length >= 253 ? { pumpVirtualQuote: raw.readBigUInt64LE(245) } : {}),
});
```

Fixed fee facts (`src/venues/quote/fees.ts:178-187`):
- creator @11
- coin_creator @211
- is_mayhem @243
- is_cashback @244
- is_holder_reward @270
- base-mint supply read at mint offset 36 (`hot-add.ts:252`)
```ts
export function pumpPoolFacts(pool: Buffer, baseSupply: bigint): PumpPoolFee & { why?: string } {
  const byte = (o: number) => (pool.length > o ? pool[o]! : 0);
  const base = new PublicKey(pool.subarray(43, 75)), quoteMint = new PublicKey(pool.subarray(75, 107)).toBase58();
  const [auth] = PublicKey.findProgramAddressSync([Buffer.from("pool-authority"), base.toBuffer()], PUMP_FUN_PROGRAM);
  const quote = quoteMint === PUMP_WSOL ? "sol" : quoteMint === PUMP_USDC ? "usdc" : "other";
  const mayhem = byte(243) === 1;
  const why = quote === "other" ? "quote-other" : byte(244) === 1 ? "cashback" : byte(270) === 1 ? "holder-reward" : undefined;
  return { canonical: auth.equals(new PublicKey(pool.subarray(11, 43))), quote, supply: mayhem ? PUMP_MAYHEM_SUPPLY : baseSupply,
    creatorFee: pool.length >= 243 && !pool.subarray(211, 243).equals(Buffer.alloc(32)), quotable: why === undefined, ...(why ? { why } : {}) };
}
```

Hot-add accepts pool sizes `[271, 300, 301]` (`hot-add.ts:77`) and requires the quote mint (@75) to be SOL, USDC or USDT.

GlobalConfig (`encoders.ts:141-149`):
```ts
/** GlobalConfig (949 bytes, disc 95089ccaa0fcb0d9): disable_flags u8 @56 (bit 3 buy, bit 4 sell),
 *  protocol_fee_recipients[8] @57, reserved_fee_recipient @385 + reserved_fee_recipients[7] @418 (mayhem pools),
 *  buyback_fee_recipients[8] @643. Default (unset) keys are dropped. */
  return { disableFlags: raw[56]!, protocolFeeRecipients: keys(57, 8), reservedFeeRecipients: [...keys(385, 1), ...keys(418, 7)], buybackFeeRecipients: keys(643, 8) };
```

FeeConfig is at `5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx`, the PDA `["fee_config", PumpSwap program id]` under `pfeeUxB6…`. Decoder (`fees.ts:122-129`):
```ts
export function decodePumpFeeConfig(raw: Buffer): PumpFeeConfig {
  let o = 41;
  const fees = (): PumpFees => { const f = { lp: Number(raw.readBigUInt64LE(o)), protocol: Number(raw.readBigUInt64LE(o + 8)), creator: Number(raw.readBigUInt64LE(o + 16)) }; o += 24; return f; };
  const tiers = () => { const n = raw.readUInt32LE(o); o += 4; const t = []; for (let i = 0; i < n; i++) { const threshold = raw.readBigUInt64LE(o) + (raw.readBigUInt64LE(o + 8) << 64n); o += 16; t.push({ threshold, fees: fees() }); } return t; };
  const flat = fees(), t = tiers(), st = tiers();
  const exotic = raw.length >= o + 24 ? fees() : { lp: 0, protocol: 0, creator: 0 };
  return { flat, tiers: t, stableTiers: st, exotic };
}
```

### 3.2 Reserves
- `decPumpSwap` sets no owed fees, so `r0 = base vault (@139).amount` and `r1 = quote vault (@171).amount`.
- The virtual quote reserve (u64 @245) is added only inside the quote, and for the market cap. It is not part of `r1`.

### 3.3 Fee and quote

Fee schedule (`fees.ts:133-163`):
```ts
export function pumpFeeSchedule(cfg: PumpFeeConfig, pool: Pick<PumpPoolFee, "canonical" | "quote">, marketCap: bigint): PumpFees {
  if (!pool.canonical) return cfg.flat;
  if (pool.quote === "other") return cfg.exotic.lp + cfg.exotic.protocol + cfg.exotic.creator ? cfg.exotic : cfg.flat;
  const tiers = pool.quote === "usdc" && cfg.stableTiers.length ? cfg.stableTiers : cfg.tiers;
  for (let i = tiers.length - 1; i > 0; i--) if (marketCap >= tiers[i]!.threshold) return tiers[i]!.fees;
  return tiers[0]!.fees;
}
export const pumpMarketCap = (baseReserve: bigint, quoteReserve: bigint, supply: bigint): bigint | null =>
  baseReserve > 0n ? (quoteReserve * supply) / baseReserve : null;
export function pumpFeeBps(cfg: PumpFeeConfig, pool: PumpPoolFee, marketCap: bigint): number {
  const f = pumpFeeSchedule(cfg, pool, marketCap);
  return f.lp + f.protocol + (pool.creatorFee ? f.creator : 0);
}
export function pumpRate1e6(m: PumpFeeModel | undefined | null, baseReserve: bigint, effQuoteReserve: bigint): number | null {
  if (!m?.pool.quotable || !m.cfg.tiers.length) return null;
  const { cfg, pool } = m;
  const mc = pumpMarketCap(baseReserve, effQuoteReserve, pool.supply);
  if (mc === null) return null;
  const bps = pumpFeeBps(cfg, pool, mc);
  return bps > 0 && bps < 1_000 ? bps * 100 : null;
}
```

Call site (`pipeline.ts:580-585`):
```ts
    const rate = snap.r0 !== undefined && snap.r1 !== undefined ? pumpRate1e6(a.pumpFee, snap.r0, snap.r1 + (snap.pumpVirtualQuote ?? 0n)) : null;
    if (rate === null) return { ok: false, reason: "pump-not-quotable" };
```

Quote (`pipeline.ts:365-374`, verbatim). This is exact-in only, `sell` (base in) or `buy_exact_quote_in` (quote in):
```ts
  if (s.venue === "PumpSwap") {
    const virt = Number(s.pumpVirtualQuote ?? 0n);
    const baseIn = input.zeroForOne;
    const effIn = Number(rIn) + (baseIn ? 0 : virt), effOut = Number(rOut) + (baseIn ? virt : 0);
    const netIn = baseIn ? amountInRaw : afterFee1e6(amountInRaw, input.feeRate1e6);
    const gross = Math.floor((effOut * netIn) / (effIn + netIn));
    if (gross * CPMM_MAX_RESERVE_DIVISOR > Number(rOut)) return { out: 0, exact: false, why: `cpmm-trade-exceeds-1/${CPMM_MAX_RESERVE_DIVISOR}-of-reserve` };
    const out = baseIn ? Math.max(0, gross - Math.ceil((gross * input.feeRate1e6) / 1e6)) : gross;
    return { out, exact: true, feeRate1e6: input.feeRate1e6, cpmmNetIn: netIn, cpmmGrossOut: gross };
  }
```
- Sell: no fee on the input; `out = gross − ceil(gross·rate/1e6)`.
- Buy: `netIn = in − ceil(in·rate/1e6)`.
- The 1/50 floor is checked against the real (non-virtual) output vault.

### 3.4 Swap instruction and the harvested template

**Program facts:**
- Discriminators: `sell 33e685a4017f83ad` (base_amount_in @8, min_quote_out @16; 24 bytes), `buy_exact_quote_in c62e1552b4d9e870` (spendable_quote_in @8, min_base_out @16, optional track_volume byte @24), `buy 66063d1201daebea` (base_amount_out @8, exact-out).
- Only the first two are in `INPUT_AT_8`, so amount_offset is 8 and a `buy` template fails `legAmountOffset`.

**What a template is.** `data/templates.json` is keyed by pool address. Each value is `{prog, data (hex, as harvested, including the trader's amounts), accts: [{pubkey, isWritable}], dir (the INPUT mint), alts: [lookup tables the source tx used], venue?, fromFailed?, dirMeasured?}`. The file holds 1,500 templates.

For PumpSwap:
- All 56 registry pools have one.
- 22 are `sell` with dir = base, 31 are `buy_exact_quote_in` with dir = quote, and 3 are `buy` with dir = quote.
- **Each pool therefore serves only one direction.**

**How it is harvested** (`scripts/data/refresh-registry.ts:89-117`). The harvester:
1. reads `getSignaturesForAddress(pool, {limit:12})`;
2. for each successful tx, scans top-level and inner instructions for the venue program that names the pool;
3. copies its account list with message-level writability and its hex data.

That harvester does not set `dir`. The existing `dir`, `dirMeasured` and `fromFailed` fields come from an earlier harvester, which derived `dir` from which vault grew (`src/strategy/detect.ts:100-104`). Direction gate (`detect.ts:105-112`):
```ts
    const pumpDirTrusted = (t: any) => !!t && (t.dirMeasured === true || t.fromFailed !== true);
    const pumpDirOk = (p: any, tin: string) => {
      if (p.venue !== "PumpSwap") return true;
      const t = templates[p.pool];
      if (!t) return !!(p.pumpGlobal && p.pumpCoinCreator);
      return pumpDirTrusted(t) && t.dir === tin;
    };
```

**Fixed account order.** These are the template slots that `buildSwap` and `pumpSwapTemplate` rely on (`encoders.ts:178-189`; confirmed against `runs/pumpswap-accounts-research.md`, 698 decoded swaps):
```
0 pool W | 1 user S,W | 2 global_config ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw | 3 base_mint | 4 quote_mint |
5 user_base_ata W | 6 user_quote_ata W | 7 pool_base_vault(@139) W | 8 pool_quote_vault(@171) W |
9 protocol_fee_recipient | 10 ATA(#9, quote_mint, quote_prog) W | 11 base_token_program | 12 quote_token_program |
13 System | 14 ATA program | 15 event_authority GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR | 16 program |
17 ATA(#18, quote_mint, quote_prog) W | 18 coin_creator_vault_authority = PDA["creator_vault", coin_creator@211]
buy only: 19 global_volume_accumulator C2aFPdENg4A2HQsmrd5rTw5TaYBX5Ku887cWjbFKtZpw | 20 user_volume_accumulator = PDA["user_volume_accumulator", user] W
then: fee_config 5PHirr8j… | fee_program pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ
tail: [cashback block if pool@244==1] + [pool_v2 = PDA["pool-v2", base_mint] if coin_creator != default] + [buyback_recipient, ATA(buyback, quote_mint, quote_prog) W]
```

**Encoder branch** (`encoders.ts:876-923`, verbatim core). It applies to both harvested and synthetic templates.
```ts
      if (!tplForward) return { error: "pump-direction-not-available" };
      if (acc.length < 9) return { error: `pump-accounts-${acc.length}` };
      setSigner(1);
      acc[5]!.pubkey = ataOf(reg.t0); acc[6]!.pubkey = ataOf(reg.t1);
      const pid = new PublicKey("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA");
      const ataOfOwner = (owner: PublicKey, prog: PublicKey, mint: PublicKey) =>
        PublicKey.findProgramAddressSync([owner.toBuffer(), prog.toBuffer(), mint.toBuffer()], ASSOCIATED_TOKEN_PROGRAM)[0];
      if (acc.length > 18) {
        const creator = st?.pumpCoinCreator as string | undefined;
        if (!creator) { ...; return { error: "pump-no-coin-creator" }; }
        const quoteMint = acc[4]!.pubkey, quoteProg = acc[12]!.pubkey;
        if (!ataOfOwner(acc[18]!.pubkey, quoteProg, quoteMint).equals(acc[17]!.pubkey)) {
          ...; return { error: "pump-creator-vault-layout" }; }
        const [auth] = PublicKey.findProgramAddressSync([Buffer.from("creator_vault"), new PublicKey(creator).toBuffer()], pid);
        acc[18]!.pubkey = auth; acc[17]!.pubkey = ataOfOwner(auth, quoteProg, quoteMint);
      }
      const [uva] = PublicKey.findProgramAddressSync([Buffer.from("user_volume_accumulator"), payer.toBuffer()], pid);
      const [theirs] = PublicKey.findProgramAddressSync([Buffer.from("user_volume_accumulator"),
        new PublicKey(tpl.accts[1]!.pubkey).toBuffer()], pid);
      const remap = new Map<string, PublicKey>([[theirs.toBase58(), uva]]);
      for (const mint of [acc[3]!.pubkey, acc[4]!.pubkey]) for (const prog of [SPL_TOKEN, TOKEN_2022])
        remap.set(ataOfOwner(theirs, prog, mint).toBase58(), ataOfOwner(uva, prog, mint));
      const [poolV2] = PublicKey.findProgramAddressSync([Buffer.from("pool-v2"), acc[3]!.pubkey.toBuffer()], pid);
      const v2At = acc.findIndex((x, i) => i >= 21 && x.pubkey.equals(poolV2));
      if (v2At > 21) {
        const traderSeeded = (k: PublicKey) => remap.has(k.toBase58());
        const keep = acc.filter((x, i) => !(i >= 21 && i < v2At && traderSeeded(x.pubkey)));
        if (keep.length !== acc.length) { ...; acc.splice(0, acc.length, ...keep); }
      }
      for (const s of acc) { const to = remap.get(s.pubkey.toBase58()); if (to) s.pubkey = to; }
      data.writeBigUInt64LE(amountIn, 8); data.writeBigUInt64LE(minOut, 16);
```

What is rewritten per trade, and what is reused from the template:
- **Rewritten:** signer [1]; user ATAs [5]/[6] (mint-ordered, base then quote); the creator-vault pair [17]/[18] from the **live** `coin_creator`; the user volume accumulator and its ATAs (remapped to the payer's).
- **Dropped:** any cashback block in front of pool_v2.
- **Reused verbatim:** [9]/[10] fee recipient, [2], [15], [19], fee_config/program, pool_v2 and the buyback pair. They are not re-read from GlobalConfig, and writable flags stay as harvested.
- **Data:** `track_volume` (byte 24) of a 25-byte buy is kept as harvested.

**Synthetic template**, used when a pool has no harvested one (hot-add only; `encoders.ts:163-192`):
```ts
  const fees = reg.pumpMayhem ? gc.reservedFeeRecipients : gc.protocolFeeRecipients;
  ...
  const sell = tin === reg.t0;
  const baseProg = progOf(reg.t0Prog), quoteProg = progOf(reg.t1Prog), quote = new PublicKey(reg.t1);
  const ata = (owner: PublicKey) => PublicKey.findProgramAddressSync([owner.toBuffer(), quoteProg.toBuffer(), quote.toBuffer()], ASSOCIATED_TOKEN_PROGRAM)[0].toBase58();
  const pick = new PublicKey(reg.pool).toBytes()[0]!;
  const feeRecipient = new PublicKey(fees[pick % fees.length]!), buyback = new PublicKey(gc.buybackFeeRecipients[pick % gc.buybackFeeRecipients.length]!);
  const [creatorAuth] = PublicKey.findProgramAddressSync([Buffer.from("creator_vault"), new PublicKey(reg.pumpCoinCreator).toBuffer()], pid);
  const ph = pid;
  const [uva] = PublicKey.findProgramAddressSync([Buffer.from("user_volume_accumulator"), ph.toBuffer()], pid);
  const accts = [m(reg.pool, true), m(ph.toBase58(), true), m(PUMPSWAP_GLOBAL_CONFIG, false), m(reg.t0, false), m(reg.t1, false),
    m(PUMPSWAP_PROGRAM_ID, true), m(PUMPSWAP_PROGRAM_ID, true),
    m(reg.vault0, true), m(reg.vault1, true), m(feeRecipient.toBase58(), false), m(ata(feeRecipient), true),
    m(baseProg.toBase58(), false), m(quoteProg.toBase58(), false), m(SYSTEM_PROGRAM, false), m(ASSOCIATED_TOKEN_PROGRAM.toBase58(), false),
    m(PUMPSWAP_EVENT_AUTHORITY, false), m(PUMPSWAP_PROGRAM_ID, false), m(ata(creatorAuth), true), m(creatorAuth.toBase58(), false),
    ...(sell ? [] : [m(PUMPSWAP_GLOBAL_VOLUME_ACCUMULATOR, false), m(uva.toBase58(), true)]),
    m(PUMP_FEE_CONFIG_ACCT, false), m(PUMP_FEE_PROGRAM, false),
    ...(reg.pumpCashback ? [m(ata(uva), true), ...(sell ? [m(uva.toBase58(), true)] : [])] : []),
    ...(reg.pumpCoinCreator !== DEFAULT_KEY ? [m(PublicKey.findProgramAddressSync([Buffer.from("pool-v2"), new PublicKey(reg.t0).toBuffer()], pid)[0].toBase58(), false)] : []),
    m(buyback.toBase58(), false), m(ata(buyback), true)];
  const data = (sell ? PUMPSWAP_SELL_DISC : PUMPSWAP_BUY_EXACT_QUOTE_IN_DISC) + "00".repeat(8) + "0100000000000000";
  return { prog: PUMPSWAP_PROGRAM_ID, data, accts, dir: tin, alts: [], dirMeasured: true } as Tpl;
```
- Account counts: a non-canonical pool has 23 accounts for sell and 25 for buy; a canonical pool without cashback has 24 and 26.
- min_out = 1 (`min_base_out = 0` fails with 6001).
- Hot-add refuses a pool if GlobalConfig `disable_flags & ((1<<3)|(1<<4))`, or if `pumpPoolFacts` says the pool is not quotable (cashback, holder-reward or other-quote; `hot-add.ts:247-261`).

**Template example** (pool F42tZnKP…: sell, canonical, no cashback, 24 accounts):
```
data 33e685a4017f83ad ac95249411000000 0100000000000000   dir = base mint Tqj8yF…pump
0 pool W 1 trader W 2 ADyA8hde… 3 Tqj8…pump 4 So111… 5 W 6 W 7 vault0 W 8 vault1 W 9 7hTckgnG… 10 X5QPJcpp… W
11 Tokenz… 12 Tokenkeg… 13 1111… 14 ATok… 15 GS4CU59F… 16 pAMM… 17 1rDQ5hu5… W 18 AFD4LQtN… 19 5PHirr8j… 20 pfeeUxB6…
21 pool_v2 5EHhDV5o… 22 buyback 9M4giFFM… 23 buyback ATA GAFuhgcd… W
```

**data/pumpfee.json** has the shape `{ feeConfig: {flat, tiers[25], stableTiers[25], exotic}, pools: {<pool>: {...}} }`, with 56 pools. Thresholds and supplies are strings. Examples:
- `flat {"lp":25,"protocol":5,"creator":0}`
- `tiers[0] {"threshold":"0","fees":{"lp":2,"protocol":93,"creator":30}}`
- `tiers[1] {"threshold":"420000000000",...}`
- Pool entry:
```
"4w2cysotX6czaUGmmWg13hDpY4QEMG2CzeKYEQyK9Ama": {"canonical":true,"quote":"sol","supply":"998747074330022","creatorFee":true,"quotable":true,
  "check":{"swaps":12,"feeMismatches":0,"nBuy":6,"nSell":6,"feeBpsSeen":[30],"priceErrBuyBps":-0.09,"priceErrSellBps":0}}
```
It is parsed by `parsePumpFeeFile` (`fees.ts:195-199`) and generated by `scripts/measure/pump-fee.ts`.

### 3.5 Pending decode (`pending.ts:45-47`, `:162-169`)
```ts
const PUMPSWAP_SELL = "33e685a4017f83ad";               // base_amount_in @8, exact input, base -> quote
const PUMPSWAP_BUY_EXACT_QUOTE_IN = "c62e1552b4d9e870"; // spendable_quote_in @8, exact input, quote -> base
const PUMPSWAP_BUY = "66063d1201daebea";                // base_amount_out @8, exact OUTPUT, quote -> base
...
  } else if (v.family === "PumpSwap" && (disc === PUMPSWAP_SELL || disc === PUMPSWAP_BUY_EXACT_QUOTE_IN || disc === PUMPSWAP_BUY)) {
    if (ix.accounts.length < 4) return;
    const pool = ix.accounts[0], reg = pool ? regOf(pool) : undefined;
    const baseIsT0 = reg ? ix.accounts[3] === reg.t0 : null;
    push(pool, baseIsT0 === null ? null : disc === PUMPSWAP_SELL ? baseIsT0 : !baseIsT0, ix.accounts[1], u64(ix.data, 8), disc === PUMPSWAP_BUY);
  }
```

### 3.6 Prediction and CU
- Prediction is §0.6. A sell moves `r0 += in` and `r1 −= gross`. A buy moves `r1 += in − ceil(fee)` and `r0 −= gross`. `pumpVirtualQuote` is unchanged.
- CU: `PumpSwap: { base: 100_000 }`.

---

## 4. Where the bot may not match the programs (worth checking before you port)

1. **RayCPMM fee source.** The live quote uses the registry `feeBps*100` on the input, because no caller passes `clmmConfig`. The creator-fee input/output split (`cpmmFeeSplit`, `outputFeeRate1e6`) is never reached in live paths.
2. **RayCPMM creator fees in reserves.** `creator_fees_token_0/1` (@397/@405) are decoded but not subtracted from the reserves. Check cp-swap's `vault_amount_without_fee` for the version you target.
3. **Float arithmetic.** The RayCPMM and PumpSwap quotes and `afterFee1e6` use f64 `Number` arithmetic. Products like `rOut * netIn` can exceed 2^53. RayAMMv4 is exact BigInt. Use u128 in Rust.
4. **PumpSwap fee rounding.**
   - The bot applies one `ceil` to the summed lp+protocol+creator rate.
   - On buys it uses `q·(1−f)`. The `priceErrBuyBps` values in pumpfee.json are −0.09 at 30 bps and −0.49 at 70 bps, which equals −f². That suggests the program uses `q/(1+f)`. This is an inference, not verified.
5. **PumpSwap virtual reserve width.** It is read as u64 at 245 and requires length ≥ 253. The research note (`runs/pumpswap-accounts-research.md`) lists `virtual_quote_reserves` as i128 at 245..261.
6. **PumpSwap harvested-template staleness and cashback.**
   - Harvested templates keep their fee recipient, buyback pair and GlobalConfig-derived keys as captured. If the program rotates recipients, the template goes stale; the research note gives an example where using the old `CebN…` now fails with 6013.
   - The encoder always drops the cashback block, but the research note says the block is mandatory for cashback coins. Cashback coins are refused upstream (`pumpPoolFacts` / `quotable`).
7. **Prediction excludes fees kept in the pool.** `predict.ts` adds `netIn`, the amount after the whole fee, to the input reserve.
   - Where the LP part of the fee stays in the vault and is not booked as owed, the real post-swap reserve grows by more than that. This applies to RayAMMv4's whole fee and to the LP part of RayCPMM/PumpSwap fees.
   - The bot's stated rationale is at predict.ts:14-18. Validate against shadow accuracy before you copy it.
8. **Writable flags are message-level.** Harvested `isWritable` reflects the whole transaction, not the instruction, so templates can mark accounts W that the IDL marks read-only.
9. **Unusable `buy` templates.** The 3 PumpSwap pools whose template is `buy` (66063d…) cannot build: `amount-offset-unverified`.
