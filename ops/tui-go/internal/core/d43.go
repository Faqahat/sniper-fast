package core

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"regexp"
	"slices"
	"sort"
	"strconv"
	"strings"
)

// dip43 .. dip43d (engine 11-10 / 11-11; dipmon v4): the snipe-guard and its Lighthouse A/B arm, the CURVE band (dip43d),
// the true-balance book's snapshots, the fee tier and the send accounting, the exit A/Bs (cheap timer sells, two-lot exit,
// exit timer) and the log-only shadows (FEED-STALL, dead-man, mint ledger, fan-out, FP strict, react-watch, exit shadow).
// Read from the records (docs/dip43_records.md) and the start banner lines (docs/dip43_flags.md). Every figure here is
// new in v4: a run without a dip43 record or banner has no D43 report (older runs' screens unchanged).
//
// The Engine tab, the snapshot and the JSON show the report as SECTIONS (a title and text lines): one more section (the
// dip44 farm floor) is one more func in D43Sections.

// NoV4 (DIPMON_V3=1): leave out everything v4 added on top of dipmon 3.3 (the dip43 sections, the registry's LOG rows) so
// the output can be checked against the dip42 oracle binary on any run (tests/parity.sh).
var NoV4 = os.Getenv("DIPMON_V3") == "1"

// D43Sections: the report's sections in display order; each returns nil when the run has nothing for it.
var D43Sections = []func(R *D43Report) *D43Section{secGuard, secBand, secTbal, secSend, secExits, secShadows}

// D43Section: one block of the dip43 report (Engine tab panel, snapshot lines, JSON object).
type D43Section struct {
	Key, Title string
	Lines      []string // plain text, already formatted ("label     value")
	JSON       *JObj
}

type d43Try struct {
	arm     string // "G" | "L" | "" (no guard on the try)
	cuPrice int64
	tierOn  bool
	curveHi float64 // the CURVE band's bound carried (0 = none)
	would   bool    // curve_would_hi (the band in log mode)
	w       int64
	kind    string
	floors  int64  // floors carried (-1 = no holders mode)
	reason  string // signed without floors: no_snapshot / stale / few_holders
}

type d43Arm struct {
	Tries, Landed, Fills, Wins int64
	Res                        map[string]int64
	Real                       int64 // realized lamports of its positions
	NReal                      int64
	FeeFailed                  int64
}

type d43Abort struct {
	N    int64
	Cnt  map[int64]int64 // holders below -> tries
	Gap  map[int64]int64 // gap bucket -> tries
	Fees int64
}

// D43Fill: one live fill's dip43 view (the Trades details / brief line).
type D43Fill struct {
	W                    int64
	Mint, Sig, Arm, Kind string
	Floors               int64   // floors the filling try carried (-1 = none / not logged)
	FloorReason          string  // no_snapshot / stale / few_holders
	CurveHi              float64 // the band's bound (curve token account, raw units; 0 = none)
	BandWould            bool    // the band ran in log mode (curve_would_hi)
	DepthPct             float64 // the price just before our buy vs the try's signing price (% under)
	HasDepth             bool
	GA, GD               string // CASCADE verdicts: "abort" / "pass" / "" (not logged)
	GABelow, GAN         int64
	MintLedger, Fanout   bool
	WouldHold            string // shadows43.would_hold (null = "")
	BhShort, T2ArmSlot   bool
	TimerArm, LotsArm    string
	ExitAB               string
	Pnl                  int64
	HasPnl               bool
}

// D43Acc gathers the dip43 records and banner lines.
type D43Acc struct {
	ver int64
	any bool
	// banners
	guardLine            string
	b43Lines, a43Lines   []string
	guardMode, guardSpec string
	guardAB              bool
	bandOn, bandLive     bool
	bandD                float64
	bandChanges          []d43Change
	exitLotsChanges      []d43Change
	cfg43, b43           json.RawMessage
	// tries
	tries                             map[string]*d43Try // sig -> try
	arms                              map[string]*d43Arm // "G" / "L" / ""
	floors                            map[int64]int64    // G tries by floors carried
	reasons                           map[string]int64   // G tries signed without floors, by reason
	ageMs                             []float64
	bandTry, bandWould                int64
	tierOn, tierOff, tierClient       int64
	cuTries, cuLanded, cuFee, cuFills map[int64]int64
	pathOrig                          int64
	results                           map[string]int64
	aborts                            map[string]*d43Abort
	deepW, deepMint                   map[string]bool // curve_deep aborts: windows ("w"), mints
	// fills / positions
	fills   []*D43Fill
	fillKey map[FKey]*D43Fill
	// true balances
	tbN, tbErr      int64
	tbMs, tbHolders []float64
	famN, famErr    int64
	famLag          []float64
	famDSlot        []float64
	fanActs         map[string]int64
	// send accounting
	notSent            map[string]int64
	nsWin              int64
	unseenN, unseenFee int64
	// exits
	exitSeen map[FKey]bool
	exitArms map[string]map[string]*d43ExitArm // A/B name -> arm -> stats
	lot2     map[string]int64
	lotSold  int64
	// shadows
	stallStarts, stallEnds        int64
	stallKinds                    map[string]int64
	stallMaxMs                    float64
	deadman                       map[string]int64
	blind                         map[string]int64
	mlEntries, mlPaper            int64
	mlWould                       map[string]int64 // arm / skip / fill would-blocks
	fanFlag                       map[string]int64
	strictN                       int64
	strictW                       map[int64]bool
	react                         int64
	shExitN                       int64
	shExitEst                     int64
	stopShadow                    int64
	wouldHold, bhShort, t2ArmSlot int64
	unseenRecs                    int64
	dumpExit                      map[string]int64 // dip43e: mode -> records (log = would-fire once per position)
	dumpMints                     map[string]bool
	cache                         *D43Report
	cacheVer                      int64
}

type d43Change struct {
	t        int64
	key, was string
	now      string
}

type d43ExitArm struct {
	N, Wins int64
	Pnl     int64
	NReal   int64
	keys    []FKey
}

func newD43Acc() *D43Acc {
	return &D43Acc{tries: map[string]*d43Try{}, arms: map[string]*d43Arm{}, floors: map[int64]int64{}, reasons: map[string]int64{},
		cuTries: map[int64]int64{}, cuLanded: map[int64]int64{}, cuFee: map[int64]int64{}, cuFills: map[int64]int64{}, results: map[string]int64{},
		aborts: map[string]*d43Abort{}, deepW: map[string]bool{}, deepMint: map[string]bool{}, fillKey: map[FKey]*D43Fill{}, fanActs: map[string]int64{},
		notSent: map[string]int64{}, exitSeen: map[FKey]bool{}, exitArms: map[string]map[string]*d43ExitArm{}, lot2: map[string]int64{},
		stallKinds: map[string]int64{}, deadman: map[string]int64{}, blind: map[string]int64{}, mlWould: map[string]int64{}, fanFlag: map[string]int64{},
		strictW: map[int64]bool{}, dumpExit: map[string]int64{}, dumpMints: map[string]bool{}}
}

var d43Evs = map[string]bool{"presend_attempt": true, "presend_attempt_land": true, "presend_live_fill": true, "presend_live_realized": true,
	"presend_live_exit": true, "presend_live_tbal_snap": true, "presend_live_fam": true, "presend_live_disarm": true, "presend_live_unseen_fee": true,
	"presend_live_feed_stall": true, "presend_live_deadman": true, "presend_live_blind": true, "presend_live_mint_ledger": true,
	"presend_live_arm": true, "presend_live_skip": true, "presend_live_fpnb_strict": true, "react_watch": true, "presend_live_shadow_exit": true,
	"presend_live_stop_shadow": true, "presend_live_ledger_mode": true, "presend_live_dip43": true, "presend_live_b43_start": true,
	"presend_live_lot_sold": true, "presend_live_dump_exit": true}

var (
	d43GuardKey = []byte(`"guard":{`)
	d43TierKey  = []byte(`"tier":{`)
	d43AbortKey = []byte(`"guard_abort":`)
	d43MLKey    = []byte(`"mint_ledger":{`)
	d43FanKey   = []byte(`"fanout":{`)
)

func (D *D43Acc) bump() { D.ver++; D.any = true }

// feed takes one record.
func (D *D43Acc) feed(ev, line []byte) {
	e := string(ev)
	if !d43Evs[e] {
		return
	}
	switch e {
	case "presend_attempt": // many: decoded only when the try carries a dip43 field
		if !bytes.Contains(line, d43GuardKey) && !bytes.Contains(line, d43TierKey) {
			return
		}
		var r struct {
			Sig     string   `json:"sig"`
			W       *int64   `json:"w"`
			Kind    string   `json:"kind"`
			Dry     bool     `json:"dry"`
			CuPrice *float64 `json:"cu_price"`
			PathO   *string  `json:"path_orig"`
			Guard   *struct {
				Arm    string   `json:"arm"`
				Mode   string   `json:"mode"`
				NF     *float64 `json:"n_floors"`
				Reason string   `json:"reason"`
				Age    *float64 `json:"age_ms"`
				Hi     *float64 `json:"curve_hi"`
				WHi    *float64 `json:"curve_would_hi"`
			} `json:"guard"`
			Tier *struct {
				On     bool `json:"on"`
				Client bool `json:"client"`
			} `json:"tier"`
		}
		if json.Unmarshal(line, &r) != nil || r.Dry {
			return
		}
		D.bump()
		t := &d43Try{cuPrice: int64(fz(r.CuPrice)), kind: r.Kind, w: noW, floors: -1}
		if r.W != nil {
			t.w = *r.W
		}
		if g := r.Guard; g != nil {
			t.arm = g.Arm
			if t.arm == "" {
				t.arm = "G"
				if g.Mode == "lighthouse" {
					t.arm = "L"
				}
			}
			if g.Hi != nil {
				t.curveHi = *g.Hi
				D.bandTry++
			} else if g.WHi != nil {
				t.curveHi, t.would = *g.WHi, true
				D.bandWould++
			}
			if g.Mode == "holders" {
				t.floors, t.reason = int64(fz(g.NF)), g.Reason
				D.floors[int64(fz(g.NF))]++
				if g.Reason != "" {
					D.reasons[g.Reason]++
				}
				if g.Age != nil {
					D.ageMs = append(D.ageMs, *g.Age)
				}
			}
		}
		if r.Tier != nil {
			if r.Tier.On {
				D.tierOn++
			} else {
				D.tierOff++
			}
			if r.Tier.Client {
				D.tierClient++
			}
		}
		if r.PathO != nil {
			D.pathOrig++
		}
		D.tries[r.Sig] = t
		D.arm(t.arm).Tries++
		D.cuTries[t.cuPrice]++
	case "presend_attempt_land":
		var r struct {
			Sig   string   `json:"sig"`
			Mint  string   `json:"mint"`
			W     *int64   `json:"w"`
			Res   string   `json:"res"`
			Fee   *float64 `json:"fee"`
			Abort *struct {
				Kind string   `json:"kind"`
				Cnt  *float64 `json:"cnt"`
				GapB *float64 `json:"gap_bucket"`
			} `json:"guard_abort"`
		}
		if bytes.Contains(line, d43AbortKey) || D.tries[sigOf(line)] != nil {
			if json.Unmarshal(line, &r) != nil {
				return
			}
		} else {
			return
		}
		t := D.tries[r.Sig]
		if t == nil && r.Abort == nil {
			return
		}
		D.bump()
		arm := ""
		if t != nil {
			arm = t.arm
		}
		a := D.arm(arm)
		a.Landed++
		a.Res[r.Res]++
		D.results[r.Res]++
		fee := int64(fz(r.Fee))
		if r.Res != "ok" && r.Res != "unseen" {
			a.FeeFailed += fee
			if t != nil {
				D.cuFee[t.cuPrice] += fee
			}
		}
		if t != nil {
			D.cuLanded[t.cuPrice]++
		}
		if x := r.Abort; x != nil && x.Kind != "" {
			k := x.Kind
			ab := D.aborts[k]
			if ab == nil {
				ab = &d43Abort{Cnt: map[int64]int64{}, Gap: map[int64]int64{}}
				D.aborts[k] = ab
			}
			ab.N++
			ab.Cnt[int64(fz(x.Cnt))]++
			ab.Gap[int64(fz(x.GapB))]++
			ab.Fees += fee
			if k == "curve_deep" {
				w := int64(-1)
				if r.W != nil {
					w = *r.W
				}
				D.deepW[strconv.FormatInt(w, 10)] = true
				D.deepMint[r.Mint] = true
			}
		}
	case "presend_live_fill":
		var o map[string]any
		if json.Unmarshal(line, &o) != nil {
			return
		}
		k := FKey{mW(o), mStr(o, "mint")}
		if D.fillKey[k] != nil { // a later fill of the same position (a merged buy): the first decided it
			return
		}
		f := &D43Fill{W: k.W, Mint: k.Mint, Sig: mStr(o, "sig"), Kind: "T2", Floors: -1}
		if mStr(o, "kind") == "rearm" {
			f.Kind = "RA"
		}
		dip43 := false
		if t := D.tries[f.Sig]; t != nil {
			f.Arm, f.CurveHi, f.BandWould, f.Floors, f.FloorReason = t.arm, t.curveHi, t.would, t.floors, t.reason
			D.arm(t.arm).Fills++
			D.cuFills[t.cuPrice]++
			dip43 = true
		}
		if ps, ok := mNum(o, "p_sign"); ok && ps > 0 {
			if pe, ok := mNum(o, "p_entry_pre"); ok && pe > 0 {
				f.DepthPct, f.HasDepth = (1-pe/ps)*100, true
			}
		}
		if c := mObj(o, "cascade"); c != nil {
			dip43 = true
			if ga := mObj(c, "ga"); ga != nil {
				f.GA = map[bool]string{true: "abort", false: "pass"}[mBool(ga, "abort")]
				b, _ := mNum(ga, "below")
				n, _ := mNum(ga, "n")
				f.GABelow, f.GAN = int64(b), int64(n)
			}
			if gd := mObj(c, "gd"); gd != nil {
				f.GD = map[bool]string{true: "abort", false: "pass"}[mBool(gd, "abort")]
			}
		}
		if ml := mObj(o, "mint_ledger"); ml != nil {
			dip43 = true
			f.MintLedger = mBool(ml, "would_block")
			if f.MintLedger {
				D.mlWould["fill"]++
			}
		}
		if fo := mObj(o, "fanout"); fo != nil {
			dip43 = true
			f.Fanout = mBool(fo, "flag")
			if f.Fanout {
				D.fanFlag["fill"]++
			}
		}
		if sh := mObj(o, "shadows43"); sh != nil {
			dip43 = true
			if s := mStr(sh, "would_hold"); s != "" {
				f.WouldHold = s
				D.wouldHold++
			}
			if bh := mObj(sh, "bh_short"); bh != nil && mBool(bh, "would") {
				f.BhShort = true
				D.bhShort++
			}
			if mBool(sh, "t2_armslot") {
				f.T2ArmSlot = true
				D.t2ArmSlot++
			}
		}
		if !dip43 {
			return
		}
		D.bump()
		D.fills = append(D.fills, f)
		D.fillKey[k] = f
	case "presend_live_realized":
		if len(D.fillKey) == 0 && len(D.exitSeen) == 0 {
			return
		}
		var r struct {
			W    *int64          `json:"w"`
			Mint string          `json:"mint"`
			Pnl  json.RawMessage `json:"pnl"`
		}
		if json.Unmarshal(line, &r) != nil || r.W == nil {
			return
		}
		k := FKey{*r.W, r.Mint}
		p, _ := rawFloat(r.Pnl)
		pl := int64(math.Round(p))
		if f := D.fillKey[k]; f != nil {
			D.bump()
			if f.HasPnl { // a re-realized position: replace its number
				a := D.arm(f.Arm)
				a.Real -= f.Pnl
				if f.Pnl > 0 {
					a.Wins--
				}
				a.NReal--
			}
			f.Pnl, f.HasPnl = pl, true
			a := D.arm(f.Arm)
			a.Real += pl
			a.NReal++
			if pl > 0 {
				a.Wins++
			}
		}
		for _, arms := range D.exitArms {
			for _, x := range arms {
				if slices.Contains(x.keys, k) {
					D.bump()
					x.Pnl += pl
					x.NReal++
					if pl > 0 {
						x.Wins++
					}
				}
			}
		}
	case "presend_live_exit":
		var o map[string]any
		if json.Unmarshal(line, &o) != nil {
			return
		}
		why := mStr(o, "why")
		if strings.HasPrefix(why, "lot2") {
			D.bump()
			D.lot2[why]++
			return
		}
		k := FKey{mW(o), mStr(o, "mint")}
		ts, lots, xab := mObj(o, "timer_sell"), mObj(o, "lots"), mObj(o, "exit_ab")
		if ts == nil && lots == nil && xab == nil {
			return
		}
		if D.exitSeen[k] {
			return
		}
		D.exitSeen[k] = true
		D.bump()
		add := func(ab, arm string) {
			if arm == "" {
				return
			}
			if D.exitArms[ab] == nil {
				D.exitArms[ab] = map[string]*d43ExitArm{}
			}
			x := D.exitArms[ab][arm]
			if x == nil {
				x = &d43ExitArm{}
				D.exitArms[ab][arm] = x
			}
			x.N++
			x.keys = append(x.keys, k)
		}
		if ts != nil {
			add("timer_sell", mStr(ts, "arm"))
		}
		if lots != nil {
			add("lots", mStr(lots, "arm"))
		}
		if xab != nil {
			add("exit_ab", mStr(xab, "arm"))
		}
		if f := D.fillKey[k]; f != nil {
			f.TimerArm, f.LotsArm, f.ExitAB = mStr(ts, "arm"), mStr(lots, "arm"), mStr(xab, "arm")
		}
	case "presend_live_dump_exit": // dip43e: the dump exit would fire (log) / fired (live)
		var r struct {
			Mint string `json:"mint"`
			Mode string `json:"mode"`
		}
		if json.Unmarshal(line, &r) == nil {
			D.bump()
			D.dumpExit[r.Mode]++
			D.dumpMints[r.Mint] = true
		}
	case "presend_live_lot_sold":
		D.bump()
		D.lotSold++
	case "presend_live_tbal_snap":
		var r struct {
			Ms  *float64 `json:"ms"`
			N   *float64 `json:"n"`
			Err any      `json:"err"`
		}
		if json.Unmarshal(line, &r) != nil {
			return
		}
		D.bump()
		D.tbN++
		if r.Err != nil {
			D.tbErr++
			return
		}
		if r.Ms != nil {
			D.tbMs = append(D.tbMs, *r.Ms)
		}
		if r.N != nil {
			D.tbHolders = append(D.tbHolders, *r.N)
		}
	case "presend_live_fam":
		var r struct {
			Err  any      `json:"err"`
			Lag  *float64 `json:"lag_ms"`
			Read *float64 `json:"read_slot"`
			Arm  *float64 `json:"arm_slot"`
			Fan  *struct {
				Act  string `json:"act"`
				Flag bool   `json:"flag"`
			} `json:"fanout"`
		}
		if json.Unmarshal(line, &r) != nil {
			return
		}
		D.ver++ // counted on every run (dip35+), shown only with the dip43 report
		D.famN++
		if r.Err != nil {
			D.famErr++
		}
		if r.Lag != nil {
			D.famLag = append(D.famLag, *r.Lag)
		}
		if r.Read != nil && r.Arm != nil {
			D.famDSlot = append(D.famDSlot, *r.Read-*r.Arm)
		}
		if r.Fan != nil {
			D.fanActs[r.Fan.Act]++
		}
	case "presend_live_disarm":
		if !bytes.Contains(line, []byte(`"not_sent":{`)) {
			return
		}
		var r struct {
			NS map[string]json.RawMessage `json:"not_sent"`
		}
		if json.Unmarshal(line, &r) != nil || r.NS == nil {
			return
		}
		D.bump()
		D.nsWin++
		for k, v := range r.NS {
			if x, ok := rawFloat(v); ok {
				D.notSent[k] += int64(x)
			}
		}
	case "presend_live_unseen_fee":
		var r struct {
			TotN *float64 `json:"total_unseen"`
			TotF *float64 `json:"total_fee_est"`
		}
		if json.Unmarshal(line, &r) != nil {
			return
		}
		D.bump()
		D.unseenRecs++
		D.unseenN, D.unseenFee = int64(fz(r.TotN)), int64(fz(r.TotF))
	case "presend_live_feed_stall":
		var r struct {
			Phase  string   `json:"phase"`
			Kind   string   `json:"kind"`
			Dur    *float64 `json:"dur_ms"`
			MaxSil *float64 `json:"max_silent_ms"`
		}
		if json.Unmarshal(line, &r) != nil {
			return
		}
		D.bump()
		if r.Phase == "end" {
			D.stallEnds++
			D.stallMaxMs = math.Max(D.stallMaxMs, fz(r.Dur))
		} else {
			D.stallStarts++
			D.stallKinds[r.Kind]++
		}
	case "presend_live_deadman":
		var r struct {
			Would string `json:"would"`
		}
		if json.Unmarshal(line, &r) == nil {
			D.bump()
			D.deadman[r.Would]++
		}
	case "presend_live_blind":
		var r struct {
			Act string `json:"act"`
		}
		if json.Unmarshal(line, &r) == nil {
			D.bump()
			D.blind[r.Act]++
		}
	case "presend_live_mint_ledger":
		D.bump()
		D.mlEntries++
		if bytes.Contains(line, []byte(`"paper":true`)) {
			D.mlPaper++
		}
	case "presend_live_arm", "presend_live_skip":
		ml, fo := bytes.Contains(line, d43MLKey), bytes.Contains(line, d43FanKey)
		if !ml && !fo {
			return
		}
		var r struct {
			ML *struct {
				Would bool `json:"would_block"`
			} `json:"mint_ledger"`
			Fan *struct {
				Flag bool `json:"flag"`
			} `json:"fanout"`
		}
		if json.Unmarshal(line, &r) != nil {
			return
		}
		D.bump()
		where := strings.TrimPrefix(e, "presend_live_")
		if r.ML != nil && r.ML.Would {
			D.mlWould[where]++
		}
		if r.Fan != nil && r.Fan.Flag {
			D.fanFlag[where]++
		}
	case "presend_live_fpnb_strict":
		D.bump()
		D.strictN++
		if w, ok := numAfter(line, `"w":`); ok {
			D.strictW[w] = true
		}
	case "react_watch":
		D.bump()
		D.react++
	case "presend_live_shadow_exit":
		D.bump()
		D.shExitN++
		if x, ok := numAfter(line, `"realized_est":`); ok {
			D.shExitEst += x
		}
	case "presend_live_stop_shadow":
		D.bump()
		D.stopShadow++
	case "presend_live_ledger_mode":
		if !bytes.Contains(line, []byte(`"dip43"`)) && !bytes.Contains(line, []byte(`"exit_lots"`)) {
			return
		}
		var r struct {
			Ok  bool            `json:"ok"`
			T   json.RawMessage `json:"t"`
			D43 map[string]any  `json:"dip43"`
			XL  *string         `json:"exit_lots"`
			Was map[string]any  `json:"was"`
		}
		if json.Unmarshal(line, &r) != nil || !r.Ok {
			return
		}
		D.bump()
		t := rawInt(r.T)
		was := map[string]any{}
		if w, ok := r.Was["dip43"].(map[string]any); ok {
			was = w
		}
		keys := make([]string, 0, len(r.D43))
		for k := range r.D43 {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			c := d43Change{t: t, key: k, now: fmt.Sprint(r.D43[k]), was: fmt.Sprint(was[k])}
			if k == "curve_deep" {
				D.bandChanges = append(D.bandChanges, c)
			} else {
				D.exitLotsChanges = append(D.exitLotsChanges, c)
			}
		}
		if r.XL != nil {
			D.exitLotsChanges = append(D.exitLotsChanges, d43Change{t: t, key: "exit_lots", now: *r.XL, was: fmt.Sprint(r.Was["exit_lots"])})
		}
	case "presend_live_dip43":
		D.bump()
		var r struct {
			Cfg json.RawMessage `json:"cfg"`
		}
		if json.Unmarshal(line, &r) == nil {
			D.cfg43 = r.Cfg
		}
	case "presend_live_b43_start":
		D.bump()
		D.b43 = append(json.RawMessage(nil), line...)
	}
}

func (D *D43Acc) arm(a string) *d43Arm {
	x := D.arms[a]
	if x == nil {
		x = &d43Arm{Res: map[string]int64{}}
		D.arms[a] = x
	}
	return x
}

var d43SigKey = []byte(`"sig":"`)

// sigOf: a record's "sig" by substring (the first one: an attempt_land's own sig sorts after its "between" / "after" lists'
// sig8 keys, which are not "sig").
func sigOf(line []byte) string {
	i := bytes.Index(line, d43SigKey)
	if i < 0 {
		return ""
	}
	rest := line[i+len(d43SigKey):]
	j := bytes.IndexByte(rest, '"')
	if j < 0 {
		return ""
	}
	return string(rest[:j])
}

var (
	rxGuardLine = regexp.MustCompile(`^GUARD \(dip43 snipe-guard\) (\S+)\s*(\S*)`)
	rxBand      = regexp.MustCompile(`CURVE BAND (LIVE|LOG)[^:]*: a try aborts when the price is >= (\d+(?:\.\d+)?)% under`)
)

// logLine: a dip43 banner line (the engine's start).
func (D *D43Acc) logLine(st string) {
	switch {
	case strings.HasPrefix(st, "GUARD (dip43 snipe-guard)"):
		D.bump()
		D.guardLine = Clean(st)
		if m := rxGuardLine.FindStringSubmatch(st); m != nil {
			D.guardMode = strings.TrimRight(m[1], ",;")
			if strings.Contains(m[2], ":") {
				D.guardSpec = strings.TrimRight(m[2], ",;")
			}
		}
		D.guardAB = strings.Contains(st, "A/B by window parity")
		D.bandOn, D.bandLive, D.bandD = false, false, 0
		if m := rxBand.FindStringSubmatch(st); m != nil {
			D.bandOn, D.bandLive = true, m[1] == "LIVE"
			D.bandD, _ = strconv.ParseFloat(m[2], 64)
		}
	case strings.HasPrefix(st, "DIP43-B B"):
		D.bump()
		D.b43Lines = upsertBanner(D.b43Lines, Clean(strings.TrimPrefix(st, "DIP43-B ")))
	case strings.HasPrefix(st, "DIP43E "): // dip43e: DUMP EXIT, WHALE LEDGER KINDS
		D.bump()
		D.a43Lines = upsertBanner(D.a43Lines, Clean(strings.TrimPrefix(st, "DIP43")))
	case strings.HasPrefix(st, "DIP43 A"):
		D.bump()
		D.a43Lines = upsertBanner(D.a43Lines, Clean(strings.TrimPrefix(st, "DIP43 ")))
	}
}

// upsertBanner keeps one line per item ("B1 ...", "A3 ..."): a restart's line replaces the earlier one.
func upsertBanner(ls []string, l string) []string {
	id, _, _ := strings.Cut(l, " ")
	for i, x := range ls {
		if xid, _, _ := strings.Cut(x, " "); xid == id {
			ls[i] = l
			return ls
		}
	}
	return append(ls, l)
}

// ------------------------------------------------------------------------------------------------------------- report

// D43Report: the figures the views show.
type D43Report struct {
	A        *D43Acc
	Sections []*D43Section
	Fills    []*D43Fill
}

// Report builds the sections (nil when the run has nothing dip43).
func (D *D43Acc) Report() *D43Report {
	if NoV4 || !D.any {
		return nil
	}
	if D.cache != nil && D.cacheVer == D.ver { // rebuilt only when a record came (the UI asks every refresh)
		return D.cache
	}
	R := &D43Report{A: D, Fills: D.fills}
	defer func() { D.cache, D.cacheVer = R, D.ver }()
	for _, f := range D43Sections {
		if s := f(R); s != nil {
			R.Sections = append(R.Sections, s)
		}
	}
	return R
}

// GuardItem: the config item of the snipe-guard and the CURVE band ("" = no guard banner): short and long forms.
func (R *D43Report) GuardItem() (string, string) {
	D := R.A
	if D.guardMode == "" {
		return "", ""
	}
	sh, fl := "sg "+D.guardMode, "snipe-guard "+D.guardMode
	if D.guardSpec != "" {
		fl += " " + D.guardSpec
	}
	if D.guardAB {
		sh += " A/B"
		fl += ", A/B G (odd windows) / L Lighthouse (even)"
	}
	if D.bandOn || len(D.bandChanges) > 0 {
		st := map[bool]string{true: "LIVE", false: "log"}[D.bandLive]
		if n := len(D.bandChanges); n > 0 {
			st = map[bool]string{true: "LIVE", false: "log"}[D.bandChanges[n-1].now == "live"]
		}
		sh += fmt.Sprintf(" band %.0f%% %s", D.bandD, st)
		fl += fmt.Sprintf("; CURVE band %.0f%% %s (control key curve_deep)", D.bandD, st)
	}
	return sh, fl
}

// Banners: the dip43 start lines (GUARD, DIP43-B B1-B6, DIP43 A1-A12), as the engine printed them.
func (R *D43Report) Banners() []string {
	if R == nil {
		return nil
	}
	var out []string
	if R.A.guardLine != "" {
		out = append(out, R.A.guardLine)
	}
	for _, l := range R.A.b43Lines {
		out = append(out, "DIP43-B "+l)
	}
	for _, l := range R.A.a43Lines {
		out = append(out, "DIP43 "+l)
	}
	return out
}

// Fill: a position's dip43 view (nil = none).
func (R *D43Report) Fill(w int64, mint string) *D43Fill {
	if R == nil {
		return nil
	}
	return R.A.fillKey[FKey{w, mint}]
}

func pctOf(n, d int64) string {
	if d <= 0 {
		return "-"
	}
	return fmt.Sprintf("%.1f%%", float64(n)*100/float64(d))
}

func quant(xs []float64, q float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	i := int(math.Round(q * float64(len(s)-1)))
	return s[i]
}

// kvs: a count map as "k n · k n", largest first (ties by key).
func kvs(m map[string]int64) string {
	type kv struct {
		k string
		n int64
	}
	var xs []kv
	for k, n := range m {
		if n != 0 {
			xs = append(xs, kv{k, n})
		}
	}
	sort.Slice(xs, func(i, j int) bool {
		if xs[i].n != xs[j].n {
			return xs[i].n > xs[j].n
		}
		return xs[i].k < xs[j].k
	})
	var ps []string
	for _, x := range xs {
		k := x.k
		if k == "" {
			k = "?"
		}
		ps = append(ps, k+" "+IC(x.n))
	}
	if len(ps) == 0 {
		return "none"
	}
	return strings.Join(ps, " · ")
}

func ikvs(m map[int64]int64) string {
	ks := make([]int64, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	slices.Sort(ks)
	var ps []string
	for _, k := range ks {
		ps = append(ps, fmt.Sprintf("%d: %s", k, IC(m[k])))
	}
	return strings.Join(ps, ", ")
}

func lamS(x int64) string { return Sol(x, true, 4, true) }

// feeS: a fee sum (6 decimals: a few failed tries are ~0.00001 SOL)
func feeS(x int64) string { return Sol(x, true, 6, true) }

func armName(a string) string {
	switch a {
	case "G":
		return "G snipe-guard"
	case "L":
		return "L Lighthouse"
	}
	return "- no guard"
}

// secGuard: the snipe-guard's mode and its A/B arms.
func secGuard(R *D43Report) *D43Section {
	D := R.A
	if D.guardLine == "" && len(D.arms) == 0 {
		return nil
	}
	if len(D.arms) == 1 && D.arms[""] != nil && D.guardLine == "" {
		return nil
	}
	s := &D43Section{Key: "guard", Title: "GUARD (snipe-guard A/B)", JSON: &JObj{}}
	mode := D.guardMode
	if mode == "" {
		mode = "?"
	}
	head := "mode " + mode
	if D.guardSpec != "" {
		head += " " + D.guardSpec + " (top N : floor : max leavers : min %)"
	}
	if D.guardAB {
		head += " · A/B by window parity: odd G snipe-guard, even L Lighthouse"
	}
	s.Lines = append(s.Lines, "guard     "+head)
	s.JSON.Set("mode", mode).Set("spec", D.guardSpec).Set("ab", D.guardAB)
	arms := &JObj{}
	for _, a := range []string{"G", "L", ""} {
		x := D.arms[a]
		if x == nil || (a == "" && x.Tries == 0) {
			continue
		}
		per1k := 0.0
		if x.Tries > 0 {
			per1k = float64(x.Fills) * 1000 / float64(x.Tries)
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  %-15s tries %s, fills %d (%.1f / 1k tries), realized %s (%d, %d W), deadline %s, unseen %s, guard_abort %s, failed fees %s",
			armName(a), IC(x.Tries), x.Fills, per1k, lamS(x.Real), x.NReal, x.Wins, pctOf(x.Res["deadline"], x.Tries), pctOf(x.Res["unseen"], x.Tries),
			pctOf(x.Res["guard_abort"], x.Tries), feeS(-x.FeeFailed)))
		o := &JObj{}
		o.Set("tries", x.Tries).Set("landed", x.Landed).Set("fills", x.Fills).Set("fills_per_1k", PyFloat(per1k)).Set("realized", x.Real).Set("realized_n", x.NReal).
			Set("wins", x.Wins).Set("failed_fees", x.FeeFailed)
		res := &JObj{}
		for _, k := range sortedKeys(x.Res) {
			res.Set(k, x.Res[k])
		}
		o.Set("results", res)
		arms.Set(map[string]string{"G": "G", "L": "L", "": "none"}[a], o)
	}
	s.JSON.Set("arms", arms)
	if len(D.aborts) > 0 {
		ab := &JObj{}
		var parts []string
		for _, k := range sortedKeysA(D.aborts) {
			x := D.aborts[k]
			parts = append(parts, fmt.Sprintf("%s %s (below %s; gap %s)", k, IC(x.N), ikvs(x.Cnt), ikvs(x.Gap)))
			o := &JObj{}
			o.Set("n", x.N).Set("fees", x.Fees)
			ab.Set(k, o)
		}
		s.Lines = append(s.Lines, "  aborts by kind: "+strings.Join(parts, " · "))
		s.JSON.Set("aborts", ab)
	}
	if len(D.floors) > 0 {
		var nf []string
		ks := make([]int64, 0, len(D.floors))
		for k := range D.floors {
			ks = append(ks, k)
		}
		slices.Sort(ks)
		var tot int64
		for _, k := range ks {
			tot += D.floors[k]
		}
		for _, k := range ks {
			nf = append(nf, fmt.Sprintf("%d: %s", k, pctOf(D.floors[k], tot)))
		}
		l := "  floors per G try (holders mode): " + strings.Join(nf, ", ")
		if len(D.reasons) > 0 {
			l += " · no floors: " + kvs(D.reasons)
		}
		if len(D.ageMs) > 0 {
			l += fmt.Sprintf(" · snapshot age p50 / p90 %.0f / %.0f ms", quant(D.ageMs, 0.5), quant(D.ageMs, 0.9))
		}
		s.Lines = append(s.Lines, l)
		fl := &JObj{}
		for _, k := range ks {
			fl.Set(strconv.FormatInt(k, 10), D.floors[k])
		}
		s.JSON.Set("floors", fl)
		rs := &JObj{}
		for _, k := range sortedKeys(D.reasons) {
			rs.Set(k, D.reasons[k])
		}
		s.JSON.Set("no_floors", rs)
	}
	return s
}

// secBand: the CURVE band (dip43d).
func secBand(R *D43Report) *D43Section {
	D := R.A
	if !D.bandOn && D.bandTry == 0 && D.bandWould == 0 && len(D.bandChanges) == 0 && D.aborts["curve_deep"] == nil {
		return nil
	}
	s := &D43Section{Key: "band", Title: "CURVE BAND (dip43d)", JSON: &JObj{}}
	state := "LOG"
	if D.bandLive {
		state = "LIVE"
	}
	if n := len(D.bandChanges); n > 0 {
		state = strings.ToUpper(D.bandChanges[n-1].now)
	}
	s.Lines = append(s.Lines, fmt.Sprintf("band      %s now (start %s) · abort when the price is >= %.0f%% under the try's signing price · tries with the band %s, log-only bound %s",
		state, map[bool]string{true: "LIVE", false: "LOG"}[D.bandLive], D.bandD, IC(D.bandTry), IC(D.bandWould)))
	for _, c := range D.bandChanges {
		s.Lines = append(s.Lines, fmt.Sprintf("  hot switch %s  curve_deep %s -> %s", T12(float64(c.t), true), c.was, c.now))
	}
	ab := D.aborts["curve_deep"]
	var n, fees int64
	if ab != nil {
		n, fees = ab.N, ab.Fees
	}
	mints := make([]string, 0, len(D.deepMint))
	for m := range D.deepMint {
		mints = append(mints, m)
	}
	sort.Strings(mints)
	l := fmt.Sprintf("  curve_deep aborts %s in %d windows, %d mints, their fees %s", IC(n), len(D.deepW), len(mints), feeS(-fees))
	if len(mints) > 0 {
		short := make([]string, len(mints))
		for i, m := range mints {
			short[i] = RuneSlice(m, 8)
		}
		l += " (" + strings.Join(short, ", ") + ")"
	}
	s.Lines = append(s.Lines, l)
	// the fills' landing depth vs the band
	var depth []string
	for _, f := range D.fills {
		if !f.HasDepth {
			continue
		}
		depth = append(depth, fmt.Sprintf("%s %.1f%%", RuneSlice(f.Mint, 6), f.DepthPct))
	}
	if len(depth) > 0 {
		s.Lines = append(s.Lines, "  fills: the price just before our buy vs the filling try's signing price: "+strings.Join(depth, ", ")+fmt.Sprintf(" under (band %.0f%%)", D.bandD))
	}
	s.JSON.Set("live", state == "LIVE").Set("start_live", D.bandLive).Set("d_pct", PyFloat(D.bandD)).Set("tries_band", D.bandTry).Set("tries_log_bound", D.bandWould).
		Set("aborts", n).Set("abort_windows", int64(len(D.deepW))).Set("abort_fees", fees)
	ms := make([]any, len(mints))
	for i, m := range mints {
		ms[i] = m
	}
	s.JSON.Set("abort_mints", ms)
	ch := make([]any, 0, len(D.bandChanges))
	for _, c := range D.bandChanges {
		o := &JObj{}
		o.Set("t", c.t).Set("was", c.was).Set("now", c.now)
		ch = append(ch, o)
	}
	s.JSON.Set("changes", ch)
	return s
}

// secTbal: the true-balance book's arm snapshots and the fam reads.
func secTbal(R *D43Report) *D43Section {
	D := R.A
	if D.tbN == 0 && D.famN == 0 {
		return nil
	}
	s := &D43Section{Key: "tbal", Title: "TRUE BALANCES (dip43 A3)", JSON: &JObj{}}
	s.Lines = append(s.Lines, fmt.Sprintf("tbal      arm snapshots %s, errors %s · read ms p50 / p90 %.1f / %.1f · holders p50 %.0f",
		IC(D.tbN), IC(D.tbErr), quant(D.tbMs, 0.5), quant(D.tbMs, 0.9), quant(D.tbHolders, 0.5)))
	l := fmt.Sprintf("  fam reads %s, errors %s · lag ms p50 / p90 %.0f / %.0f", IC(D.famN), IC(D.famErr), quant(D.famLag, 0.5), quant(D.famLag, 0.9))
	if len(D.famDSlot) > 0 {
		var before int64
		for _, x := range D.famDSlot {
			if x < 0 {
				before++
			}
		}
		l += fmt.Sprintf(" · read slot - arm slot p50 %+.0f (min %+.0f, max %+.0f; %d before the arm)", quant(D.famDSlot, 0.5), quant(D.famDSlot, 0), quant(D.famDSlot, 1), before)
	}
	s.Lines = append(s.Lines, l)
	s.JSON.Set("snapshots", D.tbN).Set("snapshot_errors", D.tbErr).Set("snapshot_ms_p50", PyFloat(quant(D.tbMs, 0.5))).Set("snapshot_ms_p90", PyFloat(quant(D.tbMs, 0.9))).
		Set("fam_reads", D.famN).Set("fam_errors", D.famErr).Set("fam_lag_ms_p50", PyFloat(quant(D.famLag, 0.5))).Set("fam_lag_ms_p90", PyFloat(quant(D.famLag, 0.9)))
	// CASCADE G-A on the fills
	var na, nab, nap int64
	var pa, pp int64
	for _, f := range D.fills {
		if f.GA == "" {
			continue
		}
		na++
		if f.GA == "abort" {
			nab++
			pa += f.Pnl
		} else {
			nap++
			pp += f.Pnl
		}
	}
	if na > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("  CASCADE G-A on %d fills: would abort %d (realized %s), pass %d (realized %s) · log only", na, nab, lamS(pa), nap, lamS(pp)))
		s.JSON.Set("ga_fills", na).Set("ga_abort", nab).Set("ga_abort_realized", pa).Set("ga_pass", nap).Set("ga_pass_realized", pp)
	}
	return s
}

// secSend: the fee tier, the CU-price classes, the send accounting, B1's flags.
func secSend(R *D43Report) *D43Section {
	D := R.A
	if len(D.b43Lines) == 0 && D.tierOn+D.tierOff == 0 && D.nsWin == 0 && D.unseenRecs == 0 {
		return nil
	}
	s := &D43Section{Key: "send", Title: "FEE TIER / SEND (dip43 B1 B2 A8)", JSON: &JObj{}}
	for _, l := range D.b43Lines {
		if strings.HasPrefix(l, "B1 ") || strings.HasPrefix(l, "B2 ") || strings.HasPrefix(l, "B5 ") {
			s.Lines = append(s.Lines, "  "+l)
		}
	}
	if D.tierOn+D.tierOff > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("  fee tier: tries at the tier price %s, at their own %s (on a tier client's slot %s)", IC(D.tierOn), IC(D.tierOff), IC(D.tierClient)))
		s.JSON.Set("tier_on", D.tierOn).Set("tier_off", D.tierOff).Set("tier_client", D.tierClient)
	}
	if len(D.cuTries) > 0 {
		ks := make([]int64, 0, len(D.cuTries))
		for k := range D.cuTries {
			ks = append(ks, k)
		}
		slices.Sort(ks)
		cu := &JObj{}
		for _, k := range ks {
			s.Lines = append(s.Lines, fmt.Sprintf("  CU price %8s uL: tries %s, landed %s, fills %d, failed fees %s", IC(k), IC(D.cuTries[k]), IC(D.cuLanded[k]), D.cuFills[k], feeS(-D.cuFee[k])))
			o := &JObj{}
			o.Set("tries", D.cuTries[k]).Set("landed", D.cuLanded[k]).Set("fills", D.cuFills[k]).Set("failed_fees", D.cuFee[k])
			cu.Set(strconv.FormatInt(k, 10), o)
		}
		s.JSON.Set("cu_price", cu)
	}
	if D.pathOrig > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("  re-routed tries (B1) %s", IC(D.pathOrig)))
		s.JSON.Set("rerouted", D.pathOrig)
	}
	if D.nsWin > 0 {
		ns := map[string]int64{}
		for k, v := range D.notSent {
			if k != "due" && k != "sent" {
				ns[k] = v
			}
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  send accounting (A8, %d windows): due %s, sent %s (%s); not sent: %s", D.nsWin, IC(D.notSent["due"]), IC(D.notSent["sent"]),
			pctOf(D.notSent["sent"], D.notSent["due"]), kvs(ns)))
		o := &JObj{}
		for _, k := range sortedKeys(D.notSent) {
			o.Set(k, D.notSent[k])
		}
		s.JSON.Set("not_sent", o)
	}
	if D.unseenRecs > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("  unseen tries %s, their fees est. %s (the records book them at 0: NOT in the run P&L above)", IC(D.unseenN), feeS(-D.unseenFee)))
		s.JSON.Set("unseen", D.unseenN).Set("unseen_fee_est", D.unseenFee)
	}
	return s
}

// secExits: the exit A/Bs (B3 two-lot, B4 cheap timer sells, B6 exit timer).
func secExits(R *D43Report) *D43Section {
	D := R.A
	if len(D.exitArms) == 0 && len(D.lot2) == 0 {
		return nil
	}
	s := &D43Section{Key: "exits", Title: "EXIT A/B (dip43 B3 B4 B6)", JSON: &JObj{}}
	for _, l := range D.b43Lines {
		if strings.HasPrefix(l, "B3 ") || strings.HasPrefix(l, "B4 ") || strings.HasPrefix(l, "B6 ") {
			if !strings.Contains(l, ": off") {
				s.Lines = append(s.Lines, "  "+l)
			}
		}
	}
	names := map[string]string{"timer_sell": "cheap timer sells (B4)", "lots": "two-lot exit (B3)", "exit_ab": "exit timer (B6)"}
	for _, ab := range []string{"timer_sell", "lots", "exit_ab"} {
		arms := D.exitArms[ab]
		if arms == nil {
			continue
		}
		var ps []string
		o := &JObj{}
		for _, a := range sortedKeysE(arms) {
			x := arms[a]
			ps = append(ps, fmt.Sprintf("%s %d exits, realized %s (%d, %d W)", a, x.N, lamS(x.Pnl), x.NReal, x.Wins))
			xo := &JObj{}
			xo.Set("exits", x.N).Set("realized", x.Pnl).Set("realized_n", x.NReal).Set("wins", x.Wins)
			o.Set(a, xo)
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  %-24s %s", names[ab], strings.Join(ps, " | ")))
		s.JSON.Set(ab, o)
	}
	if len(D.lot2) > 0 || D.lotSold > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("  lot 2 exits: %s · lot 1 sold %d", kvs(D.lot2), D.lotSold))
	}
	return s
}

// secShadows: the log-only dip43 shadows.
func secShadows(R *D43Report) *D43Section {
	D := R.A
	s := &D43Section{Key: "shadows", Title: "DIP43 SHADOWS (log only)", JSON: &JObj{}}
	if D.stallStarts+D.stallEnds > 0 || len(D.a43Lines) > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("feed stall episodes %d (%s), longest %.0f ms", D.stallStarts, kvs(D.stallKinds), D.stallMaxMs))
		s.JSON.Set("feed_stalls", D.stallStarts).Set("feed_stall_max_ms", PyFloat(D.stallMaxMs))
	}
	if len(D.deadman)+len(D.blind) > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("dead-man would: %s · blind tries: %s", kvs(D.deadman), kvs(D.blind)))
	}
	if D.mlEntries > 0 || len(D.mlWould) > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("mint ledger entries %d (%d paper) · would-block: %s", D.mlEntries, D.mlPaper, kvs(D.mlWould)))
		s.JSON.Set("mint_ledger_entries", D.mlEntries)
	}
	if len(D.fanFlag)+len(D.fanActs) > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("fan-out flags: %s · fam read acts: %s", kvs(D.fanFlag), kvs(D.fanActs)))
	}
	if D.strictN > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("FP strict would-blocks %s in %d windows", IC(D.strictN), len(D.strictW)))
		s.JSON.Set("fp_strict", D.strictN)
	}
	if D.wouldHold+D.bhShort+D.t2ArmSlot > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("fill shadows: FP would-hold %d, big-holder short %d, T2 arm-slot send %d", D.wouldHold, D.bhShort, D.t2ArmSlot))
	}
	if D.shExitN > 0 || D.stopShadow > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("exit shadow records %d (realized est. %s) · stop shadows %d", D.shExitN, lamS(D.shExitEst), D.stopShadow))
		s.JSON.Set("shadow_exits", D.shExitN)
	}
	if len(D.dumpExit) > 0 { // dip43e
		var n, pnl int64
		for _, f := range D.fills {
			if D.dumpMints[f.Mint] && f.HasPnl {
				n++
				pnl += f.Pnl
			}
		}
		s.Lines = append(s.Lines, fmt.Sprintf("dump exit (dip43e): %s · those positions realized %s (%d)", kvs(D.dumpExit), lamS(pnl), n))
		s.JSON.Set("dump_exit", D.dumpExit["log"]+D.dumpExit["live"])
	}
	if D.react > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("react-watch records %s", IC(D.react)))
		s.JSON.Set("react_watch", D.react)
	}
	if len(s.Lines) == 0 {
		return nil
	}
	return s
}

func sortedKeys(m map[string]int64) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

func sortedKeysA(m map[string]*d43Abort) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Slice(ks, func(i, j int) bool {
		if m[ks[i]].N != m[ks[j]].N {
			return m[ks[i]].N > m[ks[j]].N
		}
		return ks[i] < ks[j]
	})
	return ks
}

func sortedKeysE(m map[string]*d43ExitArm) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

// d43Text: the snapshot's dip43 lines.
func d43Text(v *View) []string {
	R := v.D43
	if R == nil {
		return nil
	}
	var out []string
	for _, s := range R.Sections {
		out = append(out, "dip43     "+s.Title)
		for _, l := range s.Lines {
			out = append(out, "          "+strings.TrimLeft(l, " "))
		}
	}
	// the fills' brief lines
	if len(R.Fills) > 0 {
		out = append(out, "dip43     fills (arm, floors, band, landing depth, CASCADE G-A, flags):")
		for _, f := range R.Fills {
			out = append(out, "          "+f.Brief())
		}
	}
	return out
}

// Brief: one fill's dip43 line ("RA 9FH3EfNw arm G floors 6 band 42% depth 12.3% G-A pass ...").
func (f *D43Fill) Brief() string {
	arm := f.Arm
	if arm == "" {
		arm = "-"
	}
	s := fmt.Sprintf("%s %s arm %s", f.Kind, RuneSlice(f.Mint, 8), arm)
	if f.Floors >= 0 {
		s += fmt.Sprintf(" floors %d", f.Floors)
	}
	if f.FloorReason != "" {
		s += " (" + f.FloorReason + ")"
	}
	if f.CurveHi > 0 {
		if f.BandWould {
			s += " band log"
		} else {
			s += " band on"
		}
	}
	if f.HasDepth {
		s += fmt.Sprintf(" depth %.1f%%", f.DepthPct)
	}
	if f.GA != "" {
		s += fmt.Sprintf(" G-A %s (%d/%d below)", f.GA, f.GABelow, f.GAN)
	}
	var fl []string
	if f.MintLedger {
		fl = append(fl, "mint-ledger")
	}
	if f.Fanout {
		fl = append(fl, "fan-out")
	}
	if f.WouldHold != "" {
		fl = append(fl, "FP-hold "+f.WouldHold)
	}
	if f.BhShort {
		fl = append(fl, "bh-short")
	}
	if f.TimerArm != "" {
		fl = append(fl, "timer "+f.TimerArm)
	}
	if f.LotsArm != "" {
		fl = append(fl, "lots "+f.LotsArm)
	}
	if f.ExitAB != "" {
		fl = append(fl, "exit-ab "+f.ExitAB)
	}
	if len(fl) > 0 {
		s += " · " + strings.Join(fl, ", ")
	}
	if f.HasPnl {
		s += " · " + lamS(f.Pnl)
	}
	return s
}

// d43JSON: the snapshot JSON's "dip43" object (only when the run has dip43 records).
func d43JSON(v *View, d *JObj) {
	R := v.D43
	if R == nil {
		return
	}
	o := &JObj{}
	for _, s := range R.Sections {
		o.Set(s.Key, s.JSON)
	}
	fs := make([]any, 0, len(R.Fills))
	for _, f := range R.Fills {
		x := &JObj{}
		x.Set("w", f.W).Set("mint", f.Mint).Set("kind", f.Kind).Set("arm", f.Arm).Set("floors", f.Floors).Set("floor_reason", f.FloorReason).
			Set("curve_hi", PyFloat(f.CurveHi)).Set("band_log", f.BandWould).Set("depth_pct", optF(f.DepthPct, f.HasDepth)).Set("ga", f.GA).Set("gd", f.GD).
			Set("mint_ledger", f.MintLedger).Set("fanout", f.Fanout).Set("would_hold", f.WouldHold).Set("timer_sell", f.TimerArm).Set("lots", f.LotsArm).
			Set("exit_ab", f.ExitAB)
		if f.HasPnl {
			x.Set("pnl", f.Pnl)
		} else {
			x.Set("pnl", nil)
		}
		fs = append(fs, x)
	}
	o.Set("fills", fs)
	d.Set("dip43", o)
}

func optF(x float64, ok bool) any {
	if !ok {
		return nil
	}
	return PyFloat(x)
}
