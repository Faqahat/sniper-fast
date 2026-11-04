package core

// FILTERS (the owner, 10-30: "a page where i can see how many winners and losers we skipped live, with their reason and
// an overview how much each filter +- saved us or cost us"): what each pre-send filter blocked and what those blocks
// would have made. A port of ops/strategies/presend/prevent/forward/filters_report.py (the table, to the 1e-9 SOL) and
// of loss_brief.py's per-position rules (group risk, holder clock, bad creator).
//
//   LIVE filters (they changed what the engine did), scored on the shadow's paper (row c: every T2 trigger, the
//   standard 0.88x limit, its own fills; P&L scaled to the live size = PAPER ESTIMATE):
//     quiet / create_slot / young_age / lone_whale   a skipped T2 trigger (presend_live_skip, not a re-arm, with
//                                                     "trig") -> the shadow window on the same trigger sig
//                                                     (presend_arm.w) -> presend_exit row c net_cheap (else pnl) x
//                                                     live size / shadow size; blocked = every skip, W/L = the ones
//                                                     whose shadow window filled
//     deeper limit                                    a T2 window with an attempt at drop > 0.125 that never filled
//                                                     live, scored via the shadow window of its trigger; its "deep"
//                                                     fills (bought >= 15% down) are counted apart, and their real
//                                                     P&L vs the shadow paper is the deeper limit's gain
//   LOG-ONLY rules (log, would-have) on the run's real fills (presend_live_realized, keyed (w, mint)):
//     bad creator (gcr; with the ledger seed), safe sell timer (ann.st_block), group risk (ann.grp_block, else the
//     risky holders summed >= 6%), holder clock approx (a holder >= 6% with >= 5 holds and h3 >= 0.3), ctx85 (only
//     when no deeper limit ran)
//
// The records are kept as they come (whole file, every session, like the script); the table is computed on demand
// and cached per records version.

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// GcrSeedDefaults: where the bad-creator ledger seed is looked for when --gcr-seed is not given (the node's, the
// local copy's).
var GcrSeedDefaults = []string{"/root/dip/gcr_seed.json", "/home/moiz/sniper-data/prevent/forward/gcr_seed.json"}

const noW = int64(-1 << 62) // a record without "w" (Python None)

// FKey is a live position's key (w, mint).
type FKey struct {
	W    int64
	Mint string
}

type fHolder struct {
	W    string   `json:"w"`
	Pct  *float64 `json:"pct"`
	N    *float64 `json:"n"`
	H3   *float64 `json:"h3"`
	Risk *float64 `json:"risk"`
	Hz3  *float64 `json:"hz3"`
}

type fAnn struct {
	Creator  *string         `json:"creator"`
	CrPct    *float64        `json:"cr_pct"`
	StBlock  any             `json:"st_block"`
	Ctx85    any             `json:"ctx85"`
	GrpBlock json.RawMessage `json:"grp_block"`
	GrpPct   *float64        `json:"grp_pct"`
	Holders  []fHolder       `json:"holders"`
	Guard    json.RawMessage `json:"guard"` // dip30: the landing guard {block, pct, set: [{w, sign_pct, land_pct}]}
}

// fGuard: dip30's landing guard on a fill: the wallets chosen at signing, their holdings at our landing summed (pct)
// and its would-block.
type fGuard struct {
	Block any      `json:"block"`
	Pct   *float64 `json:"pct"`
	Set   []struct {
		W       string   `json:"w"`
		SignPct *float64 `json:"sign_pct"`
		LandPct *float64 `json:"land_pct"`
	} `json:"set"`
}

// guard: the landing guard when the fill logged it (nil = the field is absent: a run before dip30).
func (a *fAnn) guard() *fGuard {
	if len(a.Guard) == 0 || string(a.Guard) == "null" {
		return nil
	}
	var g fGuard
	if json.Unmarshal(a.Guard, &g) != nil {
		return nil
	}
	return &g
}

// LandingGuard: the landing guard's would-block (ann.guard.block).
func (a *fAnn) LandingGuard() bool {
	g := a.guard()
	return g != nil && fTruthy(g.Block)
}

type fTrig struct {
	Sig  string          `json:"sig"`
	Mint string          `json:"mint"`
	T    json.RawMessage `json:"t"`
}

type fRec struct {
	Ev       string          `json:"ev"`
	W        *int64          `json:"w"`
	Mint     string          `json:"mint"`
	Sig      string          `json:"sig"`
	Row      *string         `json:"row"`
	Kind     *string         `json:"kind"`
	Why      *string         `json:"why"`
	T        json.RawMessage `json:"t"`
	NetCheap json.RawMessage `json:"net_cheap"`
	Pnl      json.RawMessage `json:"pnl"`
	Spend    *float64        `json:"spend"`
	Entry    *struct {
		SolIn *float64 `json:"sol_in"`
	} `json:"entry"`
	Trig *fTrig          `json:"trig"`
	Dump *fTrig          `json:"dump"` // a re-arm's dump (dip36: its blocklist skips)
	Ann  json.RawMessage `json:"ann"`
	Deep any             `json:"deep"`
	F3   *fF3            `json:"f3"` // dip32 (--presend-live-f3-log) on an arm
	// dip34/35 log-only arm fields: the equal-size group (--presend-live-eqgrp-log), the creator gate's record (cr.would with
	// --presend-live-cr-log on); dip35 presend_live_fam: the bundle family read
	Eqgrp *struct {
		Flag bool     `json:"flag"`
		N    *float64 `json:"n"`
		Pct  *float64 `json:"pct"`
		Sum  *float64 `json:"sum"`
	} `json:"eqgrp"`
	Cr *struct {
		Would *string  `json:"would"`
		N     *float64 `json:"n"`
		Sum   *float64 `json:"sum"`
	} `json:"cr"`
	Fam *float64 `json:"fam"`
	Hit *bool    `json:"hit"`
	// dip36 presend_live_fpnb (FP-NOBOT, log-only): the stage ("arm" / "send" / "fill"), its would-block, score and threshold
	Stage *string  `json:"stage"`
	Block *bool    `json:"block"`
	Score *float64 `json:"score"`
	Thr   *float64 `json:"thr"`
	// dip36 live gate: presend_live_fpnb_window (withheld sends of a window, filled or not)
	Withheld *float64 `json:"withheld"`
	Filled   *bool    `json:"filled"`
	Skip2    *struct {
		Score *float64 `json:"score"`
		Thr   *float64 `json:"thr"`
		Skip  *bool    `json:"skip"`
	} `json:"skip2"` // dip36 skip2 (log-only) on the FP-NOBOT records
	RecvN  *float64 `json:"recv_n"`
	CsPct  *float64 `json:"cs_pct"`
	FamErr *string  `json:"err"`
}

// fGateWin: a window the dip36 no-bot gate withheld sends of (presend_live_fpnb_window)
type fGateWin struct {
	k        FKey
	kind     string
	withheld int
	filled   bool
	t        int64
}

// fLog35: the dip34/35 log-only verdicts of one live position (keyed like the arm)
type fLog35 struct {
	eq, cr, fam bool
	eqWhy       string
	crWhy       string
	famWhy      string
	fpnb        bool // dip36: FP-NOBOT would have blocked the send that filled (stage "fill")
	fpnbSet     bool
	fpnbWhy     string
	skip2       bool // dip36: SKIP-2 per-send would have skipped the send that filled
	skip2Set    bool
	skip2Why    string
}

// fF3: dip32's log-only arm fields: QUIET3-A (T2 quiet token + whale with <= 3 dumps) and the fresh holders (TAIL G3 at >= 35%).
type fF3 struct {
	Q3a     bool     `json:"q3a"`
	N120    *float64 `json:"n_120s"`
	WhDumps *float64 `json:"wh_dumps"`
	Fresh   *float64 `json:"fresh"`
	FreshN  *float64 `json:"fresh_n"`
}

func (r *fRec) w() int64 {
	if r.W == nil {
		return noW
	}
	return *r.W
}

// fLedgerEv: the bad-creator ledger's inputs in record order (an armed window's annotation, a realized position), so
// the flags can be replayed from any seed.
type fLedgerEv struct {
	arm     bool
	k       FKey
	hasAnn  bool // the arm had a non-null "ann"
	truthy  bool // that "ann" is a non-empty object (Python: `if a`)
	creator string
	crPct   float64
	pnl     float64
}

type fSkip struct {
	why, sig, mint string
	t              int64
	ra             bool // dip36: a re-arm skip (rearm_blocklist; no shadow window: unscored)
}

// FMove: the price move over a shadow window (the engine's presend_disarm "move", 11-03+): the highest / lowest price
// (% vs the trigger's post price) over the token's trades inside the window, and how many trades.
type FMove struct {
	Max float64 `json:"max_pct"`
	Min float64 `json:"min_pct"`
	N   int     `json:"n"`
}

type fFill struct {
	k    FKey
	ann  *fAnn
	deep bool
	t    int64
}

type fArm struct {
	mint string
	t    int64
}

// FiltAcc gathers the records the filters table needs.
type FiltAcc struct {
	ver       int64
	shW       map[string]int64   // shadow: trigger sig -> w
	shExit    map[int64]*float64 // shadow w -> row c P&L (SOL; nil = no value)
	shSize    map[int64]float64  // shadow w -> row c size (SOL; the first fill)
	skips     []fSkip
	raSkips   int64
	liveSig   map[int64]string // live T2 w -> its trigger sig
	liveArm   map[int64]fArm   // live T2 w -> mint, time (the latest arm)
	kind      map[FKey]string
	ledger    []fLedgerEv
	deepW     map[int64]bool
	deepOrd   []int64
	fills     map[int64]bool
	fillAnn   map[FKey]*fFill
	fillOrd   []FKey
	real      map[FKey]float64
	realOrd   []FKey
	liveSize  float64
	hasSize   bool
	anyAnn    bool
	anyGuard  bool             // a fill logged the landing guard (dip30+)
	armF3     map[FKey]*fF3    // dip32: an arm's log-only "f3"
	log35     map[FKey]*fLog35 // dip34/35: eqgrp flag / cr.would / fam hit
	anyEq     bool             // an arm carried "eqgrp" (dip34 --presend-live-eqgrp-log)
	anyCrLog  bool             // an arm carried "cr" (the creator gate's record)
	anyFam    bool             // a presend_live_fam record (dip35)
	anyFpnb   bool             // a presend_live_fpnb fill record (dip36)
	anySkip2  bool             // a fill record with "skip2" (dip36)
	fpWin     []fGateWin       // dip36 live gate: windows with withheld sends
	fpHeld    int              // dip36 live gate: presend_live_fpnb_withheld records (sends withheld)
	moves     map[int64]*FMove // shadow w -> the window's price move (presend_disarm "move"; absent before 11-03)
	q3Live    bool             // QUIET3-A runs live (run_start presend_live.quiet3a, or a "quiet3_a" skip)
	cache     *FiltReport
	cacheVer  int64
	cacheSeed string
}

func newFiltAcc() *FiltAcc {
	return &FiltAcc{shW: map[string]int64{}, shExit: map[int64]*float64{}, shSize: map[int64]float64{}, liveSig: map[int64]string{},
		liveArm: map[int64]fArm{}, kind: map[FKey]string{}, deepW: map[int64]bool{}, fills: map[int64]bool{},
		fillAnn: map[FKey]*fFill{}, real: map[FKey]float64{}, armF3: map[FKey]*fF3{}, log35: map[FKey]*fLog35{}, moves: map[int64]*FMove{}}
}

var (
	fDropKey  = []byte(`"drop":`)
	fWKey     = []byte(`"w":`)
	fEvPrefix = []byte("presend_")
	fMoveKey  = []byte(`"move":`)
	fQ3aKey   = []byte(`"quiet3a":`)
)

// feed takes one record (ev = its "ev"); only the presend_* records the table uses.
func (F *FiltAcc) feed(ev, line []byte) {
	if !bytes.HasPrefix(ev, fEvPrefix) {
		if string(ev) == "run_start" && bytes.Contains(line, fQ3aKey) { // QUIET3-A live: its log row can never fire
			var r struct {
				PL *struct {
					Q3a any `json:"quiet3a"`
				} `json:"presend_live"`
			}
			if json.Unmarshal(line, &r) == nil && r.PL != nil && fTruthy(r.PL.Q3a) && !F.q3Live {
				F.q3Live = true
				F.ver++
			}
		}
		return
	}
	switch string(ev) {
	case "presend_disarm": // the shadow window's end: only its price move (11-03+), by substring first (one per window)
		if !bytes.Contains(line, fMoveKey) {
			return
		}
		var r struct {
			W    *int64 `json:"w"`
			Move *FMove `json:"move"`
		}
		if json.Unmarshal(line, &r) != nil || r.W == nil || r.Move == nil {
			return
		}
		F.ver++
		F.moves[*r.W] = r.Move
		return
	case "presend_attempt": // by substring (many): a T2 try at the deeper limit (drop > 0.125)
		i := bytes.Index(line, fDropKey)
		if i < 0 || bytes.Contains(line, kindRearm) {
			return
		}
		d, ok := floatAt(line[i+len(fDropKey):])
		if !ok || !(d > 0.125) {
			return
		}
		w := noW
		if j := bytes.Index(line, fWKey); j >= 0 {
			if x, ok := numAfter(line[j:], `"w":`); ok {
				w = x
			}
		}
		F.ver++
		if !F.deepW[w] {
			F.deepW[w] = true
			F.deepOrd = append(F.deepOrd, w)
		}
		return
	case "presend_arm", "presend_exit", "presend_fill", "presend_live_skip", "presend_live_arm", "presend_live_fill",
		"presend_live_realized", "presend_live_fam", "presend_live_fpnb", "presend_live_fpnb_window":
	case "presend_live_fpnb_withheld": // dip36 live gate: one withheld send (counted only)
		F.ver++
		F.fpHeld++
		return
	default:
		return
	}
	var r fRec
	if err := json.Unmarshal(line, &r); err != nil {
		var te *json.UnmarshalTypeError
		if !errors.As(err, &te) { // a wrong type skips that field only (the rest decoded); bad JSON skips the record
			return
		}
	}
	F.ver++
	w := r.w()
	switch r.Ev {
	case "presend_arm":
		F.shW[r.Sig] = w
	case "presend_exit":
		if r.Row != nil && *r.Row == "c" {
			var p *float64 // Python d.get("net_cheap", d.get("pnl", 0.0)): a key present as null is None
			if len(r.NetCheap) > 0 {
				if x, ok := rawFloat(r.NetCheap); ok {
					p = &x
				}
			} else if x, ok := rawFloat(r.Pnl); ok {
				p = &x
			} else if len(r.Pnl) == 0 {
				z := 0.0
				p = &z
			}
			F.shExit[w] = p
		}
	case "presend_fill":
		if (r.Row == nil || *r.Row == "c") && r.Entry != nil {
			if _, ok := F.shSize[w]; !ok {
				s := 0.0
				if r.Entry.SolIn != nil {
					s = *r.Entry.SolIn / 1e9
				}
				F.shSize[w] = s
			}
		}
	case "presend_live_skip":
		if (r.Kind != nil && *r.Kind == "rearm") || r.Trig == nil {
			if r.Kind != nil && *r.Kind == "rearm" {
				F.raSkips++
				// dip36: the re-arm's blocklist skips go in the LIVE "blocklist" row (counted; no paper outcome)
				if r.Why != nil && *r.Why == "rearm_blocklist" && r.Dump != nil {
					F.skips = append(F.skips, fSkip{why: "blocklist", sig: "", mint: r.Mint, t: rawInt(r.Dump.T), ra: true})
				}
			}
			return
		}
		why := "?"
		if r.Why != nil && *r.Why != "" {
			why = *r.Why
		}
		F.skips = append(F.skips, fSkip{why: why, sig: r.Trig.Sig, mint: r.Trig.Mint, t: rawInt(r.Trig.T)})
		if why == "quiet3_a" {
			F.q3Live = true
		}
	case "presend_live_arm":
		mint := r.Mint
		if mint == "" && r.Trig != nil {
			mint = r.Trig.Mint
		}
		k := FKey{w, mint}
		kd := "t2"
		if r.Kind != nil {
			kd = *r.Kind
		}
		F.kind[k] = kd
		if r.F3 != nil {
			F.armF3[k] = r.F3
		}
		if r.Eqgrp != nil || r.Cr != nil {
			x := F.l35(k)
			if r.Eqgrp != nil {
				F.anyEq = true
				x.eq = r.Eqgrp.Flag
				x.eqWhy = fmt.Sprintf("%.0f equal holders ~%.2f%% each (sum %.1f%%)", fz(r.Eqgrp.N), fz(r.Eqgrp.Pct), fz(r.Eqgrp.Sum))
			}
			if r.Cr != nil {
				F.anyCrLog = true
				x.cr = r.Cr.Would != nil && *r.Cr.Would == "loss"
				x.crWhy = fmt.Sprintf("creator's earlier positions %.0f, realized %+.3f SOL", fz(r.Cr.N), fz(r.Cr.Sum))
			}
		}
		if kd == "t2" && r.Trig != nil {
			F.liveSig[w] = r.Trig.Sig
			F.liveArm[w] = fArm{mint: mint, t: rawInt(r.Trig.T)}
			if !F.hasSize {
				sp := 0.0
				if r.Spend != nil {
					sp = *r.Spend / 1e9
				}
				if sp != 0 {
					F.liveSize, F.hasSize = sp, true
				}
			}
		}
		if a := parseAnn(r.Ann); a != nil {
			F.anyAnn = true
			ev := fLedgerEv{arm: true, k: k, hasAnn: true, truthy: annTruthy(r.Ann)}
			if a.Creator != nil {
				ev.creator = *a.Creator
			}
			if a.CrPct != nil {
				ev.crPct = *a.CrPct
			}
			F.ledger = append(F.ledger, ev)
		}
	case "presend_live_fam": // dip35: the bundle family read at the arm (may land after the fill: keyed like the arm)
		if r.FamErr != nil && *r.FamErr != "" {
			return
		}
		F.anyFam = true
		x := F.l35(FKey{w, r.Mint})
		x.fam = r.Hit != nil && *r.Hit
		x.famWhy = fmt.Sprintf("fam %.1f%% (create-slot %.1f%%, %.0f transfer-fed wallets)", fz(r.Fam), fz(r.CsPct), fz(r.RecvN))
	case "presend_live_fpnb_window": // dip36 live gate: a window's end with its withheld sends
		if r.Withheld != nil && *r.Withheld > 0 {
			k := "T2"
			if r.Kind != nil && *r.Kind == "rearm" {
				k = "RA"
			}
			F.fpWin = append(F.fpWin, fGateWin{k: FKey{w, r.Mint}, kind: k, withheld: int(*r.Withheld), filled: r.Filled != nil && *r.Filled, t: rawInt(r.T)})
		}
	case "presend_live_fpnb": // dip36: FP-NOBOT's score at the send that decided the fill (stage "fill"; keyed like the arm)
		if r.Stage == nil || *r.Stage != "fill" || r.Score == nil {
			return
		}
		F.anyFpnb = true
		x := F.l35(FKey{w, r.Mint})
		if r.Skip2 != nil && r.Skip2.Score != nil && !x.skip2Set {
			F.anySkip2 = true
			x.skip2Set = true
			x.skip2 = r.Skip2.Skip != nil && *r.Skip2.Skip
			x.skip2Why = fmt.Sprintf("skip2 score %.3f vs %.3f", fz(r.Skip2.Score), fz(r.Skip2.Thr))
		}
		if x.fpnbSet { // a second fill of the position: the first one decided it
			return
		}
		x.fpnbSet = true
		x.fpnb = r.Block != nil && *r.Block
		k := "?"
		if r.Kind != nil {
			k = *r.Kind
		}
		x.fpnbWhy = fmt.Sprintf("no-bot score %.3f vs %.3f (%s)", fz(r.Score), fz(r.Thr), k)
	case "presend_live_fill":
		F.fills[w] = true
		k := FKey{w, r.Mint}
		if _, ok := F.fillAnn[k]; !ok {
			a := parseAnn(r.Ann)
			if a != nil {
				F.anyAnn = true
				if a.guard() != nil {
					F.anyGuard = true
				}
			} else {
				a = &fAnn{}
			}
			F.fillAnn[k] = &fFill{k: k, ann: a, deep: fTruthy(r.Deep), t: rawInt(r.T)}
			F.fillOrd = append(F.fillOrd, k)
		}
	case "presend_live_realized":
		k := FKey{w, r.Mint}
		p, _ := rawFloat(r.Pnl)
		p /= 1e9
		if _, ok := F.real[k]; !ok {
			F.realOrd = append(F.realOrd, k)
		}
		F.real[k] = p
		F.ledger = append(F.ledger, fLedgerEv{k: k, pnl: p})
	}
}

// floatAt parses the number at the start of b (JSON).
func floatAt(b []byte) (float64, bool) {
	j := 0
	for j < len(b) && (b[j] == '-' || b[j] == '+' || b[j] == '.' || b[j] == 'e' || b[j] == 'E' || (b[j] >= '0' && b[j] <= '9')) {
		j++
	}
	f, err := strconv.ParseFloat(string(b[:j]), 64)
	return f, err == nil
}

func rawInt(r json.RawMessage) int64 {
	if len(r) == 0 {
		return 0
	}
	if i, err := strconv.ParseInt(string(r), 10, 64); err == nil {
		return i
	}
	f, _ := strconv.ParseFloat(string(r), 64)
	return int64(f)
}

// fTruthy is Python's bool() of a value decoded by encoding/json (numbers as float64).
func fTruthy(v any) bool {
	if f, ok := v.(float64); ok {
		return f != 0
	}
	return Truthy(v)
}

func rawFloat(r json.RawMessage) (float64, bool) {
	if len(r) == 0 || string(r) == "null" {
		return 0, false
	}
	f, err := strconv.ParseFloat(string(r), 64)
	return f, err == nil
}

func parseAnn(r json.RawMessage) *fAnn {
	if len(r) == 0 || string(r) == "null" {
		return nil
	}
	var a fAnn
	if json.Unmarshal(r, &a) != nil {
		return nil
	}
	return &a
}

func annTruthy(r json.RawMessage) bool {
	s := strings.TrimSpace(string(r))
	return s != "{}" && s != "" && s != "null"
}

func (F *FiltAcc) crLiveSkips() int {
	n := 0
	for _, s := range F.skips {
		if s.why == "cr_loss" {
			n++
		}
	}
	return n
}

func (F *FiltAcc) l35(k FKey) *fLog35 {
	x := F.log35[k]
	if x == nil {
		x = &fLog35{}
		F.log35[k] = x
	}
	return x
}

func fz(p *float64) float64 { // Python (x or 0)
	if p == nil {
		return 0
	}
	return *p
}

// GroupRisk: the group-risk rule (the engine's ann.grp_block when logged, else several holders that each look like
// the safe sell timer's risky holder (>= 5 holds at risk, hz3 >= 0.3) summed >= 6% at landing).
func (a *fAnn) GroupRisk() bool {
	if len(a.GrpBlock) > 0 {
		var v any
		_ = json.Unmarshal(a.GrpBlock, &v)
		return fTruthy(v)
	}
	s := 0.0
	for _, h := range a.Holders {
		if fz(h.Risk) >= 5 && fz(h.Hz3) >= 0.3 {
			s += fz(h.Pct)
		}
	}
	return s >= 6.0
}

// HolderClock: the holder clock (approx): a holder >= 6% with >= 5 holds and h3 >= 0.3.
func (a *fAnn) HolderClock() bool {
	for _, h := range a.Holders {
		if fz(h.Pct) >= 6 && fz(h.N) >= 5 && fz(h.H3) >= 0.3 {
			return true
		}
	}
	return false
}

// ------------------------------------------------------------------------------------------------- the report

// FiltRow is one filter's line of the table (SOL).
type FiltRow struct {
	Key, Name, Type, Note string // Type "LIVE" | "LOG"
	NA                    bool   // the run does not log this rule (the landing guard before dip30): n/a, not 0
	Blocked, WinN, LoseN  int
	WinSol, LoseSol       float64
}

// Net is what the filter saved (> 0) or cost (< 0): minus what its blocks would have made.
func (r FiltRow) Net() float64 {
	if r.WinN+r.LoseN == 0 {
		return 0
	}
	return -(r.WinSol + r.LoseSol)
}

// FiltItem is one blocked / skipped item (the skip list). A LIVE item is one skip / refusal (one filter); a LOG item is
// one real fill with EVERY log rule that would have blocked it (Rules / Names, in the table's order).
type FiltItem struct {
	T        int64 // ns (0 = unknown)
	Live     bool
	Filter   string   // the row's Key (a LOG item: its first rule)
	Name     string   // the filter's name (a LOG item: every rule's, comma separated)
	Rules    []string // the rows' Keys that blocked it
	Names    []string // their short names (the list)
	GuardPct float64  // a LOG item caught by the landing guard: the set's holdings at landing (%)
	Kind     string   // "T2" | "RA"
	Mint     string
	W        int64
	Scored   bool     // a value: the shadow window filled (LIVE) / the fill realized (LOG)
	Sol      float64  // would-have P&L (LIVE: paper at the live size; LOG: the real P&L)
	Sig      string   // LIVE: the trigger's key for the unique totals (its sig; "w<N>" for a window with no logged trigger)
	Why      []string // LOG: each rule's reason numbers, parallel to Rules ("holder 5ThrZRSQ 7.5%, hz3 0.91")
	Move     *FMove   // LIVE: the shadow window's price move (nil = no shadow window or the record has no "move")
}

// Info is the flagged-by line: every rule that would have blocked the fill with its reason numbers, e.g. "safe sell
// timer (holder 5ThrZRSQ 7.5%, hz3 0.91) . group risk (11.1% = 5ThrZRSQ 7.5% + 85YwZaQa 3.6%)". The dot in Trades, the
// x key and the Filters list all read this one item.
func (it FiltItem) Info() string {
	parts := make([]string, len(it.Rules))
	for i, r := range it.Rules {
		nm := r
		if i < len(it.Names) {
			nm = it.Names[i]
		}
		parts[i] = nm
		if i < len(it.Why) && it.Why[i] != "" {
			parts[i] += " (" + it.Why[i] + ")"
		}
	}
	return strings.Join(parts, " \u00b7 ")
}

// FiltTotal sums rows of one type.
type FiltTotal struct {
	Blocked, WinN, LoseN int
	WinSol, LoseSol, Net float64
}

// FiltReport is the table, the deeper limit's gain and the item list.
type FiltReport struct {
	Any         bool // the run has something to show
	Rows        []FiltRow
	NReal       int
	RealSum     float64
	Seed        string // the bad-creator seed file used ("" = none: this run's fills only)
	SeedN       int
	Deep        bool    // the deeper limit ran (a T2 try at drop > 0.125)
	DeepWindows int     // T2 windows that ran deep
	DeepFills   int     // fills marked deep
	DeepReal    float64 // their real P&L
	DeepRealN   int     // of them realized
	DeepPaper   float64 // their shadow paper (0 where the shadow did not fill)
	DeepPaperN  int     // of them with a shadow fill
	DeepGain    float64 // real - paper over the realized deep T2 fills
	DeepRAN     int     // realized deep re-arm fills (no shadow: not in the gain)
	DeepRAReal  float64
	DeepNet     float64 // the deeper limit's blocks net + the gain
	RearmSkips  int64
	Live, Log   FiltTotal // the plain sums of the rows (a trigger / fill counted once per row that has it)
	// the unique totals (owner 10-31): LiveU = each skipped / refused trigger once (by trigger sig), LogU = each real
	// fill once (any LOG rule), All = both (disjoint: a skipped trigger never became a fill)
	LiveU, LogU, All FiltTotal
	LiveDup, LogDup  int // row entries the unique totals folded away (sum of the rows - unique)
	LogMulti         int // real fills flagged by 2+ LOG rules
	Items            []FiltItem
	byFill           map[FKey]int
	LiveSize         float64
	HasLiveSize      bool
	HasGuard         bool // the run logs the landing guard (dip30+)
	Q3Live           bool // QUIET3-A ran live: its LOG row (q3a) is left out when it marked nothing
}

// LogRuleName: a LOG rule's name in the skip list (no "(new)" / "(approx)").
func LogRuleName(key string) string {
	switch key {
	case "gcr":
		return "bad creator"
	case "st":
		return "safe sell timer"
	case "ctx85":
		return "ctx85"
	case "q3a":
		return "QUIET3-A"
	case "fresh":
		return "fresh holders"
	case "grp":
		return "group risk"
	case "hc":
		return "holder clock"
	case "guard":
		return "landing guard"
	case "fpnb":
		return "no-bot filter"
	case "skip2":
		return "skip2 per-send"
	}
	return key
}

// Has: the item was blocked by the rule / filter with key k.
func (it FiltItem) Has(k string) bool {
	for _, r := range it.Rules {
		if r == k {
			return true
		}
	}
	return it.Filter == k
}

// Row returns the row with key k.
func (r *FiltReport) Row(k string) (FiltRow, bool) {
	for _, x := range r.Rows {
		if x.Key == k {
			return x, true
		}
	}
	return FiltRow{}, false
}

type seedEnt struct {
	N   float64 `json:"n"`
	Sum float64 `json:"sum"`
}

var (
	seedCache   = map[string]map[string][2]float64{}
	seedCacheMt = map[string]int64{}
)

// LoadGcrSeed reads a ledger seed ({creator: {n, sum}}); nil when unreadable. Cached by path + mtime.
func LoadGcrSeed(path string) map[string][2]float64 {
	st, err := os.Stat(path)
	if err != nil {
		return nil
	}
	if m, ok := seedCache[path]; ok && seedCacheMt[path] == st.ModTime().UnixNano() {
		return m
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var raw map[string]seedEnt
	if json.Unmarshal(b, &raw) != nil {
		return nil
	}
	m := make(map[string][2]float64, len(raw))
	for c, d := range raw {
		m[c] = [2]float64{d.N, d.Sum}
	}
	seedCache[path], seedCacheMt[path] = m, st.ModTime().UnixNano()
	return m
}

// ResolveGcrSeed: the seed path to use: explicit ("none" = no seed), else the first default that exists.
func ResolveGcrSeed(explicit string) string {
	if explicit == "none" {
		return ""
	}
	if explicit != "" {
		return explicit
	}
	for _, p := range GcrSeedDefaults {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

var liveFilters = []struct{ why, name string }{{"quiet", "QUIET"}, {"create_slot", "create-slot skip"}, {"young_age", "age-1 skip"},
	{"lone_whale", "10-sec skip"}}

// optLiveFilters: dip31/32 skips, shown only when the run made one (older runs' tables unchanged).
var optLiveFilters = []struct{ why, name string }{{"breaker", "circuit breaker"}, {"cr_loss", "creator loss (T2)"}, {"cr_unfollowed", "creator unfollowed (T2)"}, {"quiet3_a", "QUIET3-A (live)"},
	{"blocklist", "blocklist"}}

// Report computes the table (cached while no record came and the seed is the same).
func (F *FiltAcc) Report(seedPath string) *FiltReport {
	if F.cache != nil && F.cacheVer == F.ver && F.cacheSeed == seedPath {
		return F.cache
	}
	R := F.compute(seedPath)
	F.cache, F.cacheVer, F.cacheSeed = R, F.ver, seedPath
	return R
}

func (F *FiltAcc) paper(w int64, ok bool) (float64, bool) {
	if !ok {
		return 0, false
	}
	p := F.shExit[w]
	if p == nil {
		return 0, false
	}
	if F.hasSize {
		if s := F.shSize[w]; s != 0 {
			return *p * (F.liveSize / s), true
		}
	}
	return *p, true
}

func (F *FiltAcc) compute(seedPath string) *FiltReport {
	R := &FiltReport{RearmSkips: F.raSkips, LiveSize: F.liveSize, HasLiveSize: F.hasSize}
	// the bad-creator ledger, replayed in record order from the seed
	led := map[string][2]float64{}
	if seedPath != "" {
		if s := LoadGcrSeed(seedPath); s != nil {
			R.Seed, R.SeedN = seedPath, len(s)
			for c, x := range s {
				led[c] = x
			}
		}
	}
	type armA struct {
		truthy  bool
		creator string
		crPct   float64
	}
	armAnn := map[FKey]armA{}
	gcr := map[FKey]bool{}
	gcrWhy := map[FKey]string{}
	for _, e := range F.ledger {
		if e.arm {
			armAnn[e.k] = armA{e.truthy, e.creator, e.crPct}
			x := led[e.creator]
			gcr[e.k] = e.creator != "" && e.crPct >= 3 && x[0] >= 2 && x[1] <= -0.05
			if gcr[e.k] {
				gcrWhy[e.k] = fmt.Sprintf("creator %s, %.1f%% of the curve, ledger %d fills %s SOL", shortW(e.creator), e.crPct, int(x[0]), fmtSigned(x[1], 3))
			}
			continue
		}
		if a, ok := armAnn[e.k]; ok && a.truthy && a.creator != "" && a.crPct >= 3 {
			x := led[a.creator]
			led[a.creator] = [2]float64{x[0] + 1, x[1] + e.pnl}
		}
	}
	for _, k := range F.realOrd {
		R.RealSum += F.real[k]
	}
	R.NReal = len(F.real)
	kindOf := func(k FKey) string {
		if F.kind[k] == "rearm" {
			return "RA"
		}
		return "T2"
	}
	tally := func(row *FiltRow, v float64) {
		if v > 0 {
			row.WinN++
			row.WinSol += v
		} else {
			row.LoseN++
			row.LoseSol += v
		}
	}
	// LIVE skips
	byWhy := map[string]*FiltRow{}
	for _, f := range optLiveFilters {
		byWhy[f.why] = &FiltRow{Key: f.why, Name: f.name, Type: "LIVE", Note: "paper; blocked = triggers skipped, W/L = the ones that would have filled"}
	}
	for _, f := range liveFilters {
		byWhy[f.why] = &FiltRow{Key: f.why, Name: f.name, Type: "LIVE", Note: "paper; blocked = triggers skipped, W/L = the ones that would have filled"}
	}
	for _, s := range F.skips {
		row := byWhy[s.why]
		w, ok := F.shW[s.sig]
		v, vok := F.paper(w, ok)
		if row != nil {
			row.Blocked++
			if vok {
				tally(row, v)
			}
			var mv *FMove
			if ok {
				mv = F.moves[w]
			}
			kd := "T2"
			if s.ra {
				kd = "RA"
			}
			R.Items = append(R.Items, FiltItem{T: s.t, Live: true, Filter: s.why, Name: row.Name, Rules: []string{s.why}, Names: []string{row.Name}, Kind: kd,
				Mint: s.mint, W: noW, Scored: vok, Sol: v, Sig: s.sig, Move: mv})
		}
	}
	for _, f := range liveFilters {
		R.Rows = append(R.Rows, *byWhy[f.why])
	}
	for _, f := range optLiveFilters {
		if byWhy[f.why].Blocked > 0 {
			R.Rows = append(R.Rows, *byWhy[f.why])
		}
	}
	// dip36 LIVE no-bot gate: windows whose sends it withheld (blocked = never filled; the ones that filled later in the note)
	if len(F.fpWin) > 0 || F.fpHeld > 0 {
		row := FiltRow{Key: "fpnb_live", Name: "no-bot filter", Type: "LIVE"}
		later, laterSol := 0, 0.0
		for _, g := range F.fpWin {
			if g.filled {
				later++
				laterSol += F.real[g.k]
				continue
			}
			row.Blocked++
			R.Items = append(R.Items, FiltItem{T: g.t, Live: true, Filter: "fpnb_live", Name: row.Name, Rules: []string{"fpnb_live"}, Names: []string{row.Name},
				Kind: g.kind, Mint: g.k.Mint, W: g.k.W, Sig: fmt.Sprintf("w%d", g.k.W)})
		}
		row.Note = fmt.Sprintf("%d sends withheld; %d windows never filled, %d filled later (real P&L %s)", F.fpHeld, row.Blocked, later, fmtSigned(laterSol, 3))
		R.Rows = append(R.Rows, row)
	}
	// LIVE deeper limit
	if len(F.deepW) > 0 {
		R.Deep = true
		R.DeepWindows = len(F.deepW)
		row := FiltRow{Key: "deeper", Name: "deeper limit", Type: "LIVE"}
		for _, w := range F.deepOrd {
			if F.fills[w] {
				continue
			}
			row.Blocked++
			sig, has := F.liveSig[w]
			sw, inSh := F.shW[sig]
			var v float64
			var vok bool
			var mv *FMove
			if has && inSh {
				v, vok = F.paper(sw, true)
				if vok {
					tally(&row, v)
				}
				mv = F.moves[sw]
			}
			a := F.liveArm[w]
			tsig := sig
			if !has {
				tsig = "w" + strconv.FormatInt(w, 10)
			}
			R.Items = append(R.Items, FiltItem{T: a.t, Live: true, Filter: "deeper", Name: row.Name, Rules: []string{"deeper"}, Names: []string{row.Name}, Kind: "T2",
				Mint: a.mint, W: w, Scored: vok, Sol: v, Sig: tsig, Move: mv})
		}
		var dreal float64
		for _, k := range F.fillOrd {
			f := F.fillAnn[k]
			if !f.deep {
				continue
			}
			R.DeepFills++
			dreal += F.real[k]
			r, rok := F.real[k]
			if !rok {
				continue
			}
			if kindOf(k) != "T2" { // a re-arm window has no shadow: its deep fills are shown apart, not in the gain
				R.DeepRAN++
				R.DeepRAReal += r
				continue
			}
			R.DeepRealN++
			R.DeepReal += r
			sig, has := F.liveSig[k.W]
			sw, inSh := F.shW[sig]
			p, pok := F.paper(sw, has && inSh)
			if pok {
				R.DeepPaperN++
				R.DeepPaper += p
			}
			R.DeepGain += r - p
		}
		row.Note = fmt.Sprintf("paper estimate, T2; %d windows ran deep, %d still filled deeper (real P&L %s)", len(F.deepW), R.DeepFills, fmtSigned(dreal, 3))
		R.DeepNet = row.Net() + R.DeepGain
		R.Rows = append(R.Rows, row)
	}
	// LOG rules on the real fills: one row per rule; one list item per fill with every rule that caught it
	logItem := map[FKey]int{}
	var logItems []FiltItem
	preWhy := func(key string, k FKey) string {
		if key == "gcr" {
			return gcrWhy[k]
		}
		if x := F.log35[k]; x != nil {
			switch key {
			case "crlog":
				return x.crWhy
			case "eqgrp":
				return x.eqWhy
			case "fam":
				return x.famWhy
			case "fpnb":
				return x.fpnbWhy
			case "skip2":
				return x.skip2Why
			}
		}
		x := F.armF3[k]
		if x == nil {
			return ""
		}
		if key == "q3a" {
			return fmt.Sprintf("token trades in 120 s %.0f, whale's dumps %.0f", fz(x.N120), fz(x.WhDumps))
		}
		return fmt.Sprintf("fresh holders %.1f%% (%.0f wallets)", fz(x.Fresh), fz(x.FreshN))
	}
	logrule := func(key, name string, keys []FKey, note string) {
		row := FiltRow{Key: key, Name: name, Type: "LOG", Note: note}
		for _, k := range keys {
			v, ok := F.real[k]
			if !ok {
				continue
			}
			row.Blocked++
			tally(&row, v)
			short := LogRuleName(key)
			if i, ok := logItem[k]; ok {
				it := &logItems[i]
				it.Rules = append(it.Rules, key)
				it.Names = append(it.Names, short)
				it.Why = append(it.Why, logWhy(key, F.fillAnn[k], preWhy(key, k)))
				it.Name = strings.Join(it.Names, ", ")
			} else {
				t := int64(0)
				if f := F.fillAnn[k]; f != nil {
					t = f.t
				}
				logItem[k] = len(logItems)
				logItems = append(logItems, FiltItem{T: t, Filter: key, Name: short, Rules: []string{key}, Names: []string{short}, Kind: kindOf(k),
					Mint: k.Mint, W: k.W, Scored: true, Sol: v, Why: []string{logWhy(key, F.fillAnn[k], preWhy(key, k))}})
			}
			if key == "guard" {
				if f := F.fillAnn[k]; f != nil {
					if g := f.ann.guard(); g != nil {
						logItems[logItem[k]].GuardPct = fz(g.Pct)
					}
				}
			}
		}
		R.Rows = append(R.Rows, row)
	}
	var ks []FKey
	for _, k := range F.realOrd {
		if gcr[k] {
			ks = append(ks, k)
		}
	}
	gcrName, gcrNote := "bad creator", "real fills"
	if R.Seed == "" {
		gcrName, gcrNote = "bad creator (run only)", "real fills; no ledger seed: this run's own fills only"
	}
	logrule("gcr", gcrName, ks, gcrNote)
	pick := func(f func(a *fAnn) bool) []FKey {
		var out []FKey
		for _, k := range F.fillOrd {
			if f(F.fillAnn[k].ann) {
				out = append(out, k)
			}
		}
		return out
	}
	logrule("st", "safe sell timer", pick(func(a *fAnn) bool { return fTruthy(a.StBlock) }), "real fills (needs the safe on-chain check to be real)")
	if len(F.deepW) == 0 {
		logrule("ctx85", "ctx85 (deeper limit, log)", pick(func(a *fAnn) bool { return fTruthy(a.Ctx85) }), "real fills")
	}
	logrule("grp", "group risk (new)", pick((*fAnn).GroupRisk), "real fills; risky holders of any size summed >= 6%")
	logrule("hc", "holder clock (approx)", pick((*fAnn).HolderClock), "real fills")
	// dip32 (--presend-live-f3-log): QUIET3-A and the fresh holders, from the arm's "f3", on the real fills
	if len(F.armF3) > 0 {
		pickF3 := func(f func(x *fF3) bool) []FKey {
			var out []FKey
			for _, k := range F.realOrd {
				if x := F.armF3[k]; x != nil && f(x) {
					out = append(out, k)
				}
			}
			return out
		}
		logrule("q3a", "QUIET3-A (log)", pickF3(func(x *fF3) bool { return x.Q3a }), "real fills; T2 quiet token + whale with <= 3 dumps")
		if F.q3Live { // QUIET3-A ran live (11-03): the log row can then never fire; dropped unless it marked a fill anyway
			if r := R.Rows[len(R.Rows)-1]; r.Key == "q3a" && r.Blocked == 0 {
				R.Rows = R.Rows[:len(R.Rows)-1]
			}
		}
		logrule("fresh", "fresh holders >= 35% (log)", pickF3(func(x *fF3) bool { return fz(x.Fresh) >= 35 }), "real fills; attack guard (TAIL G3)")
	}
	// dip34/35 (log-only): the creator ledger with --presend-live-cr-log on, the equal-size group, the bundle family (fam)
	pick35 := func(f func(x *fLog35) bool) []FKey {
		var out []FKey
		for _, k := range F.realOrd {
			if x := F.log35[k]; x != nil && f(x) {
				out = append(out, k)
			}
		}
		return out
	}
	if F.anyCrLog {
		logrule("crlog", "creator loss (log)", pick35(func(x *fLog35) bool { return x.cr }), "real fills; creator ledger verdict, nothing skipped")
		if r := R.Rows[len(R.Rows)-1]; r.Key == "crlog" && r.Blocked == 0 && F.crLiveSkips() > 0 {
			R.Rows = R.Rows[:len(R.Rows)-1] // the ledger ran live: its log row is empty by design
		}
	}
	if F.anyEq {
		logrule("eqgrp", "equal-size group (log)", pick35(func(x *fLog35) bool { return x.eq }), "real fills; >= 3 holders with the same bag")
	}
	if F.anyFam {
		logrule("fam", "bundle family fam (log)", pick35(func(x *fLog35) bool { return x.fam }), "real fills; launch-slot + transfer-fed holders >= 26.8%")
	}
	// dip36 (log-only): FP-NOBOT at the send that decided the fill (covered, warm, score >= thr)
	if F.anyFpnb {
		logrule("fpnb", "no-bot filter (log)", pick35(func(x *fLog35) bool { return x.fpnb }), "real fills; FP-NOBOT no-follower score >= thr at the deciding send")
	}
	// dip36 (log-only): SKIP-2 per-send at the send that decided the fill (covered, score < thr)
	if F.anySkip2 {
		logrule("skip2", "skip2 per-send (log)", pick35(func(x *fLog35) bool { return x.skip2 }), "real fills; SKIP-2 logistic score < thr at the deciding send")
	}
	// dip30 LANDING GUARD (log only): the wallets chosen at signing still hold >= the guard's % at our landing
	if F.anyGuard {
		logrule("guard", "landing guard (new)", pick((*fAnn).LandingGuard), "real fills; the signing-time set still holding at landing")
	} else {
		R.Rows = append(R.Rows, FiltRow{Key: "guard", Name: "landing guard (new)", Type: "LOG", NA: true, Note: "n/a (dip30+)"})
	}
	R.Items = append(R.Items, logItems...)
	for _, r := range R.Rows {
		t := &R.Log
		if r.Type == "LIVE" {
			t = &R.Live
		}
		t.Blocked += r.Blocked
		t.WinN += r.WinN
		t.LoseN += r.LoseN
		t.WinSol += r.WinSol
		t.LoseSol += r.LoseSol
		t.Net += r.Net()
	}
	R.uniqueTotals(logItems)
	R.HasGuard = F.anyGuard
	R.Q3Live = F.q3Live
	R.Any = len(F.skips) > 0 || len(F.deepW) > 0 || F.anyAnn
	sort.SliceStable(R.Items, func(i, j int) bool { return R.Items[i].T > R.Items[j].T })
	R.byFill = map[FKey]int{}
	for i, it := range R.Items {
		if !it.Live {
			R.byFill[FKey{it.W, it.Mint}] = i
		}
	}
	return R
}

// NFlagged: the real positions at least one LOG rule would have blocked.
func (R *FiltReport) NFlagged() int {
	if R == nil {
		return 0
	}
	return len(R.byFill)
}

// Flag: the LOG item of a real position (w, mint) = every rule that would have blocked it; false = no rule would have.
// The one source of truth for the Trades dot, the info key and the Filters list.
func (R *FiltReport) Flag(w int64, mint string) (FiltItem, bool) {
	if R == nil {
		return FiltItem{}, false
	}
	i, ok := R.byFill[FKey{w, mint}]
	if !ok {
		return FiltItem{}, false
	}
	return R.Items[i], true
}

// uniqueTotals: LIVE = each trigger once (the rows count a trigger once per row: the same sig skipped under two reasons,
// or skipped and also a refused deeper window, would be twice; on r40 / r42 the five LIVE rows turn out disjoint, so
// LiveDup is 0 there, but the dedupe by sig is what guarantees it), LOG = each real fill once, ALL = both. The two
// sets are disjoint (a skipped trigger never became a fill), so ALL is their plain sum.
func (R *FiltReport) uniqueTotals(logItems []FiltItem) {
	type tv struct {
		v  float64
		ok bool
	}
	seen := map[string]*tv{}
	var order []string
	rowN := 0
	for _, it := range R.Items {
		if !it.Live {
			continue
		}
		rowN++
		key := it.Sig
		if key == "" {
			key = "item:" + it.Filter + ":" + it.Mint + ":" + strconv.FormatInt(it.T, 10)
		}
		if x, ok := seen[key]; ok {
			if !x.ok && it.Scored {
				x.v, x.ok = it.Sol, true
			}
			continue
		}
		seen[key] = &tv{it.Sol, it.Scored}
		order = append(order, key)
	}
	add := func(t *FiltTotal, v float64) {
		if v > 0 {
			t.WinN++
			t.WinSol += v
		} else {
			t.LoseN++
			t.LoseSol += v
		}
	}
	for _, k := range order {
		R.LiveU.Blocked++
		if x := seen[k]; x.ok {
			add(&R.LiveU, x.v)
		}
	}
	R.LiveU.Net = -(R.LiveU.WinSol + R.LiveU.LoseSol)
	R.LiveDup = R.Live.Blocked - R.LiveU.Blocked
	for _, it := range logItems {
		R.LogU.Blocked++
		add(&R.LogU, it.Sol)
		if len(it.Rules) > 1 {
			R.LogMulti++
		}
	}
	R.LogU.Net = -(R.LogU.WinSol + R.LogU.LoseSol)
	R.LogDup = R.Log.Blocked - R.LogU.Blocked
	R.All = FiltTotal{Blocked: R.LiveU.Blocked + R.LogU.Blocked, WinN: R.LiveU.WinN + R.LogU.WinN, LoseN: R.LiveU.LoseN + R.LogU.LoseN,
		WinSol: R.LiveU.WinSol + R.LogU.WinSol, LoseSol: R.LiveU.LoseSol + R.LogU.LoseSol}
	R.All.Net = -(R.All.WinSol + R.All.LoseSol)
}

func shortW(w string) string {
	if len(w) > 8 {
		return w[:8]
	}
	return w
}

// risky: a holder like the safe sell timer's risky one (>= 5 holds at risk, hz3 >= 0.3).
func (h fHolder) risky() bool { return fz(h.Risk) >= 5 && fz(h.Hz3) >= 0.3 }

// logWhy: one LOG rule's reason numbers for a fill (from its annotation; gcr's is the ledger line captured at arm time).
func logWhy(key string, f *fFill, gcrWhy string) string {
	if key == "gcr" {
		return gcrWhy
	}
	if key == "q3a" || key == "fresh" || key == "fpnb" || key == "skip2" { // dip32: preformatted from the arm's "f3" (passed in gcrWhy's place); dip36 fpnb
		return gcrWhy
	}
	if f == nil || f.ann == nil {
		return ""
	}
	a := f.ann
	hold := func(h fHolder) string { return fmt.Sprintf("%s %.1f%%", shortW(h.W), fz(h.Pct)) }
	switch key {
	case "st": // the biggest risky holder, else the one with the highest hz3
		var best *fHolder
		for i := range a.Holders {
			h := &a.Holders[i]
			if h.risky() && (best == nil || fz(h.Pct) > fz(best.Pct)) {
				best = h
			}
		}
		if best == nil {
			for i := range a.Holders {
				h := &a.Holders[i]
				if best == nil || fz(h.Hz3) > fz(best.Hz3) {
					best = h
				}
			}
		}
		if best == nil {
			return "engine flag, no holder logged"
		}
		return fmt.Sprintf("holder %s, hz3 %.2f", hold(*best), fz(best.Hz3))
	case "hc":
		var best *fHolder
		for i := range a.Holders {
			h := &a.Holders[i]
			if fz(h.Pct) >= 6 && fz(h.N) >= 5 && fz(h.H3) >= 0.3 && (best == nil || fz(h.Pct) > fz(best.Pct)) {
				best = h
			}
		}
		if best == nil {
			return ""
		}
		return fmt.Sprintf("holder %s, h3 %.2f", hold(*best), fz(best.H3))
	case "grp":
		var parts []string
		sum := 0.0
		for _, h := range a.Holders {
			if h.risky() {
				parts = append(parts, hold(h))
				sum += fz(h.Pct)
			}
		}
		if a.GrpPct != nil && *a.GrpPct > 0 {
			sum = *a.GrpPct
		}
		switch len(parts) {
		case 0:
			return fmt.Sprintf("%.1f%% risky holders", sum)
		case 1:
			return fmt.Sprintf("%.1f%% = %s", sum, parts[0])
		}
		return fmt.Sprintf("%.1f%% = %s", sum, strings.Join(parts, " + "))
	case "guard":
		g := a.guard()
		if g == nil {
			return ""
		}
		s := fmt.Sprintf("guard set %.1f%% at landing", fz(g.Pct))
		if len(g.Set) > 1 {
			var ps []string
			for _, x := range g.Set {
				ps = append(ps, fmt.Sprintf("%s %.1f%%", shortW(x.W), fz(x.LandPct)))
			}
			s += " = " + strings.Join(ps, " + ")
		}
		return s
	case "ctx85":
		return "ctx85 flag"
	}
	return ""
}

// fmtSigned is Python's format(x, '+.Nf').
func fmtSigned(x float64, prec int) string {
	s := strconv.FormatFloat(x, 'f', prec, 64)
	if !strings.HasPrefix(s, "-") {
		s = "+" + s
	}
	return s
}

// FiltTableLines: the table in filters_report.py's format (header + one line per row), for the text snapshot and the
// parity test.
func (R *FiltReport) TableLines() []string {
	out := []string{fmt.Sprintf("%-26s %-4s %7s | %16s | %16s | %9s", "filter", "type", "blocked", "would win", "would lose", "net saved")}
	for _, r := range R.Rows {
		if r.NA {
			out = append(out, fmt.Sprintf("%-26s %-4s %7s   (%s: not logged by this run)", r.Name, r.Type, "n/a", strings.TrimSuffix(strings.TrimPrefix(r.Note, "n/a ("), ")")))
			continue
		}
		out = append(out, fmt.Sprintf("%-26s %-4s %7d | %4d %10s | %4d %10s | %9s   (%s)", r.Name, r.Type, r.Blocked, r.WinN, padL(fmtSigned(r.WinSol, 3), 10),
			r.LoseN, padL(fmtSigned(r.LoseSol, 3), 10), padL(fmtSigned(r.Net(), 3), 9), r.Note))
	}
	return out
}

func padL(s string, n int) string {
	if len(s) >= n {
		return s
	}
	return strings.Repeat(" ", n-len(s)) + s
}

// filtersText: the text snapshot's section (dip24+ runs with something to show).
func filtersText(v *View, ctx *Ctx) []string {
	R := v.Filt
	if R == nil || !R.Any || !filtersShown(v) {
		return nil
	}
	name := filepath.Base(ctx.Src.JSONL)
	seed := "bad creator: no ledger seed, this run's fills only"
	if R.Seed != "" {
		seed = "bad creator ledger seed " + R.Seed + " (" + strconv.Itoa(R.SeedN) + " creators)"
	}
	out := []string{"filters   " + name + ": " + strconv.Itoa(R.NReal) + " positions realized " + fmtSigned(R.RealSum, 3) + " SOL; LIVE = changed what the engine did (paper estimate), LOG = log only, would-have (real fills); " + seed}
	for _, l := range R.TableLines() {
		out = append(out, "          "+l)
	}
	if R.Deep {
		out = append(out, "          deeper limit: "+strconv.Itoa(R.DeepFills)+" deep fills, "+strconv.Itoa(R.DeepRealN)+" T2 realized "+fmtSigned(R.DeepReal, 3)+
			" vs shadow paper "+fmtSigned(R.DeepPaper, 3)+" ("+strconv.Itoa(R.DeepPaperN)+" filled at 0.88x) = gain "+fmtSigned(R.DeepGain, 3)+
			"; NET = blocks "+fmtSigned(func() float64 { r, _ := R.Row("deeper"); return r.Net() }(), 3)+" + gain = "+fmtSigned(R.DeepNet, 3)+" SOL")
		if R.DeepRAN > 0 {
			out = append(out, "          (+ "+strconv.Itoa(R.DeepRAN)+" re-arm deep fills, real "+fmtSigned(R.DeepRAReal, 3)+": no shadow, not in the gain)")
		}
	}
	tl := func(t FiltTotal) string {
		return strconv.Itoa(t.Blocked) + " blocked, would win " + strconv.Itoa(t.WinN) + " " + fmtSigned(t.WinSol, 3) + ", would lose " + strconv.Itoa(t.LoseN) + " " +
			fmtSigned(t.LoseSol, 3) + ", net saved " + fmtSigned(t.Net, 3)
	}
	out = append(out, "          LIVE total (unique triggers): "+tl(R.LiveU)+dupNote(R.LiveDup, "a trigger under 2+ LIVE rows"))
	out = append(out, "          LOG total (unique fills):     "+tl(R.LogU)+dupNote(R.LogDup, "a fill flagged by 2+ rules; "+strconv.Itoa(R.LogMulti)+" fills"))
	out = append(out, "          ALL total:                    "+tl(R.All)+" (LIVE is paper, LOG is real fills; the sets are disjoint; estimate)")
	if R.RearmSkips > 0 {
		out = append(out, "          re-arm skips: "+IC(R.RearmSkips)+" (no shadow window: not scored)")
	}
	// the latest LOG blocks: a real fill and every log rule that would have blocked it
	n := 0
	for _, it := range R.Items {
		if it.Live || n >= 5 {
			continue
		}
		if n == 0 {
			out = append(out, "          latest LOG blocks (would have been blocked by):")
		}
		n++
		res := "LOSE"
		if it.Sol > 0 {
			res = "WIN "
		}
		out = append(out, "            "+T12(float64(it.T), true)+"  "+it.Kind+"  "+it.Mint+"  "+res+" "+fmtSigned(it.Sol, 4)+"  "+it.Name)
	}
	return out
}

func dupNote(n int, what string) string {
	if n <= 0 {
		return " (rows do not overlap)"
	}
	return " (rows sum " + strconv.Itoa(n) + " more: " + what + ")"
}

// filtersShown: the snapshot's filters section is for dip24+ runs (older runs keep the Python dipmon v1's output).
func filtersShown(v *View) bool {
	return v.RA.On || v.AB.On || (v.D24 != nil && v.D24.Any()) || (v.Filt != nil && (v.Filt.Deep || v.Model.Filt.anyAnn))
}

// filtersJSON: the JSON snapshot's "filters" (SOL floats).
func filtersJSON(v *View, d *JObj) {
	R := v.Filt
	if R == nil || !R.Any || !filtersShown(v) {
		return
	}
	o := &JObj{}
	o.Set("seed", optStr(R.Seed))
	o.Set("seed_creators", int64(R.SeedN))
	o.Set("positions", int64(R.NReal))
	o.Set("realized_sol", PyFloat(R.RealSum))
	rows := make([]any, 0, len(R.Rows))
	for _, r := range R.Rows {
		x := &JObj{}
		x.Set("key", r.Key)
		x.Set("name", r.Name)
		x.Set("type", r.Type)
		if r.NA { // not logged by this run: no numbers
			for _, k := range []string{"blocked", "win_n", "win_sol", "lose_n", "lose_sol", "net_saved_sol"} {
				x.Set(k, nil)
			}
		} else {
			x.Set("blocked", int64(r.Blocked))
			x.Set("win_n", int64(r.WinN))
			x.Set("win_sol", PyFloat(r.WinSol))
			x.Set("lose_n", int64(r.LoseN))
			x.Set("lose_sol", PyFloat(r.LoseSol))
			x.Set("net_saved_sol", PyFloat(r.Net()))
		}
		x.Set("note", r.Note)
		x.Set("na", r.NA)
		rows = append(rows, x)
	}
	o.Set("rows", rows)
	if R.Deep {
		dp := &JObj{}
		dp.Set("windows", int64(R.DeepWindows))
		dp.Set("fills", int64(R.DeepFills))
		dp.Set("t2_realized", int64(R.DeepRealN))
		dp.Set("real_sol", PyFloat(R.DeepReal))
		dp.Set("shadow_filled", int64(R.DeepPaperN))
		dp.Set("shadow_paper_sol", PyFloat(R.DeepPaper))
		dp.Set("gain_sol", PyFloat(R.DeepGain))
		dp.Set("rearm_realized", int64(R.DeepRAN))
		dp.Set("rearm_real_sol", PyFloat(R.DeepRAReal))
		dp.Set("net_sol", PyFloat(R.DeepNet))
		o.Set("deep", dp)
	} else {
		o.Set("deep", nil)
	}
	tot := func(t FiltTotal) *JObj {
		x := &JObj{}
		x.Set("blocked", int64(t.Blocked))
		x.Set("win_n", int64(t.WinN))
		x.Set("win_sol", PyFloat(t.WinSol))
		x.Set("lose_n", int64(t.LoseN))
		x.Set("lose_sol", PyFloat(t.LoseSol))
		x.Set("net_saved_sol", PyFloat(t.Net))
		return x
	}
	items := []any{}
	for _, it := range R.Items {
		if !it.Scored {
			continue // the unscored (no shadow fill) ones: counted in the rows' "blocked"
		}
		x := &JObj{}
		x.Set("t", PyFloat(float64(it.T)/1e9))
		x.Set("type", map[bool]string{true: "LIVE", false: "LOG"}[it.Live])
		rs := make([]any, len(it.Rules))
		for i, r := range it.Rules {
			rs[i] = r
		}
		x.Set("rules", rs)
		x.Set("name", it.Name)
		x.Set("kind", it.Kind)
		x.Set("mint", it.Mint)
		if it.W != noW {
			x.Set("w", it.W)
		} else {
			x.Set("w", nil)
		}
		x.Set("sol", PyFloat(it.Sol))
		items = append(items, x)
	}
	o.Set("items", items)
	o.Set("guard_logged", R.HasGuard)
	o.Set("live_total", tot(R.LiveU)) // unique triggers
	o.Set("log_total", tot(R.LogU))   // unique fills
	o.Set("all_total", tot(R.All))
	o.Set("live_total_rowsum", tot(R.Live))
	o.Set("log_total_rowsum", tot(R.Log))
	o.Set("live_dup", int64(R.LiveDup))
	o.Set("log_dup", int64(R.LogDup))
	o.Set("rearm_skips", R.RearmSkips)
	d.Set("filters", o)
}
