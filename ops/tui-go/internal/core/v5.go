package core

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"os"
	"fmt"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// dipmon v5 (11-11): the engine's dip46 and dip47 records, and three run-wide panels.
//
//   - dip46 (docs/dip46_probe_ab.md): PROBES (presend_live_probe*: the tries a live filter blocked, sent so they can never
//     fill; per filter the windows probed, the would-fills (each window's first would-fill landing), priced like
//     ops/probe46/probe_check.py, and the probe fees) and the FILTER A/B (ab46 on arm / fill records: the live and bypass
//     arms' windows, fills and real P&L, the bypass windows the filter would have blocked);
//   - dip47 (docs/dip47.md): the FILTER STATE (presend_live_filter_state: fv / fh, the key table, the change timeline; fv on
//     each trade), the PAUSE window (presend_live_ledger_mode pause_window on / off, pause_now), the RE-ARM CAP (skips
//     "rearm_cap"), the RE-ARM FLEET rule (presend_live_rearm_fleet, rearm_fleet on fills), GRPSIGN (presend_live_grpsign,
//     grpsign on fills, grp_t2 skips) and the FUNDER clusters (presend_live_funder, funder on fills);
//   - every run: P&L BY HOUR (PKT; = fix8283/hours.py + its win / loss columns), BIG TRADES (|P&L| >= 14% of the size) and
//     LANDING BY LEADER CLIENT (presend_attempt_land ms_send_to_first_rx per client and path).
//
// Each section is nil when its records are absent (older runs render as in v4). The dip46 / dip47 sections are in the
// snapshot and the JSON whenever the run has them; the three run-wide panels are on tab 9 and, with --v5, in the snapshot.

// ------------------------------------------------------------------------------------------------- constants (probe_check.py)

const (
	pcK      = 30_000_000_000.0 * 1_073_000_000_000_000.0 // pump curve V*T (virtual reserves)
	pcFR     = 0.0125
	pcSMS    = 214.0 // ms per slot of the block-position clock
	pcExitMs = 2350.0
	pcTP     = 0.20
	pcSL     = 0.20
	pcSeeMs  = 40.0
	pcMsLag  = 73.8
	pcReact  = 66.2
	pcSellFx = 1_805_000.0
)

// BigPct: a big trade is |P&L| >= this share of its size (the owner's 14%).
const BigPct = 0.14

// FunderRed: a fill whose largest funder cluster holds >= this % of supply is flagged (red).
const FunderRed = 25.0

func pcBuyTokens(T, spend float64) float64 {
	V := pcK / T
	x := spend / (1.0 + pcFR)
	return T * x / (V + x)
}

func pcProceeds(T, tok float64) float64 {
	if T-tok <= 0 {
		return 0
	}
	return pcK * tok / ((T - tok) * T) * (1.0 - pcFR)
}

// ------------------------------------------------------------------------------------------------- the tape (exit pricing)

type tapePt struct {
	s, i int64
	v    float64
}

// ProbeTape: per mint its trades (slot, idx, curve token reserve) sorted, and the largest idx per slot (the block clock).
// From --probe-tape FILE (tests/probe_tape.py: the collector's chain tape, as probe_check.py reads it) or, without one, the
// run's own records of the probed mints (react_watch, presend_live_tape, dump: "approx").
type ProbeTape struct {
	M     map[string][]tapePt
	Maxi  map[int64]int64
	Chain bool // from the chain tape file (exact, as probe_check.py)
	Src   string
}

// LoadProbeTape reads a tests/probe_tape.py file: {"s","i","mint","vtok"} lines and {"s","maxi"} lines.
func LoadProbeTape(path string) (*ProbeTape, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	T := &ProbeTape{M: map[string][]tapePt{}, Maxi: map[int64]int64{}, Chain: true, Src: path}
	for _, l := range bytes.Split(b, []byte("\n")) {
		if len(bytes.TrimSpace(l)) == 0 {
			continue
		}
		var r struct {
			S    int64   `json:"s"`
			I    *int64  `json:"i"`
			Mint string  `json:"mint"`
			Vtok float64 `json:"vtok"`
			Maxi *int64  `json:"maxi"`
		}
		if json.Unmarshal(l, &r) != nil {
			continue
		}
		if r.Maxi != nil {
			T.Maxi[r.S] = *r.Maxi
			continue
		}
		if r.I != nil && r.Mint != "" && r.Vtok > 0 {
			T.M[r.Mint] = append(T.M[r.Mint], tapePt{r.S, *r.I, r.Vtok})
		}
	}
	for _, v := range T.M {
		sortTape(v)
	}
	return T, nil
}

func sortTape(v []tapePt) {
	sort.Slice(v, func(a, b int) bool {
		if v[a].s != v[b].s {
			return v[a].s < v[b].s
		}
		if v[a].i != v[b].i {
			return v[a].i < v[b].i
		}
		return v[a].v < v[b].v
	})
}

func (T *ProbeTape) tau(s, i int64) float64 {
	mx, ok := T.Maxi[s]
	if !ok {
		mx = 600
	}
	return float64(s)*pcSMS + (float64(i)+0.5)/(float64(mx)+1.0)*pcSMS
}

// pre: the last trade of mint strictly before (s, i) (bisect_left on (s, i, -1)).
func (T *ProbeTape) pre(mint string, s, i int64) (tapePt, bool) {
	v := T.M[mint]
	k := sort.Search(len(v), func(j int) bool { return v[j].s > s || (v[j].s == s && v[j].i >= i) })
	if k > 0 {
		return v[k-1], true
	}
	return tapePt{}, false
}

// after: the trades of mint strictly after (s, i) (bisect_right on (s, i, inf)).
func (T *ProbeTape) after(mint string, s, i int64) []tapePt {
	v := T.M[mint]
	k := sort.Search(len(v), func(j int) bool { return v[j].s > s || (v[j].s == s && v[j].i > i) })
	return v[k:]
}

// priceExit: the r82 exit on a would-fill at (s, i), entry reserve T0 -> (sell proceeds lamports, why).
func (T *ProbeTape) priceExit(mint string, s, i int64, T0, tok, spend float64) (float64, string) {
	due := T.tau(s, i) + pcSeeMs + pcExitMs
	path := T.after(mint, s, i)
	taus := make([]float64, len(path))
	for j, p := range path {
		taus[j] = T.tau(p.s, p.i)
	}
	exitAt := func(ts float64) float64 {
		k := sort.SearchFloat64s(taus, ts) // bisect_left
		if k > 0 {
			return path[k-1].v
		}
		return T0
	}
	for j, p := range path {
		t := taus[j]
		if t >= due {
			break
		}
		v := pcProceeds(p.v, tok) / spend
		if v >= 1+pcTP || v <= 1-pcSL {
			why := "stop-loss"
			if v >= 1+pcTP {
				why = "take-profit"
			}
			return pcProceeds(exitAt(t+pcReact), tok), why
		}
	}
	return pcProceeds(exitAt(due+pcMsLag), tok), "time-ms"
}

// ------------------------------------------------------------------------------------------------- the accumulator

type v5Land struct {
	w                       int64
	filter, mint, sig, res  string
	slot, idx               int64
	hasIdx                  bool
	fee, spend, minOut      float64
	wouldFill, hasPre       bool
	preVtok, wouldTok       float64
	t                       int64
}

type v5AB struct {
	arms  map[string]string
	would map[string]bool
}

type v5Change struct {
	T              int64
	Fv             int64
	Key, Old, New  string
	Src            string
}

type v5Pause struct {
	T        int64
	On       bool
	Window   string
	Skipped  int64
	HasSkips bool
}

type v5Cap struct {
	T          int64
	Mint       string
	Fills, Cap int64
}

type v5Fleet struct {
	T                                    int64
	W                                    int64
	Mint, Mode, OpenWhy                  string
	Tries, Passed, Withheld, Would, Open int64
}

type v5Grp struct {
	W                          int64
	Mint, Kind, At             string
	Pct, PctX                  float64
	N                          int64
	WB, WBX, WB6, WhaleIn      bool
}

type v5Funder struct {
	W                 int64
	Mint, At, Funder  string
	Pct, C1Pct        float64
	N, C1N, Resolved  int64
	HasC1             bool
}

// V5Fill: one live fill's v5 view (hours, big trades, the trade row's fv, the details).
type V5Fill struct {
	W                  int64
	Mint, Kind         string // Kind "T2" | "RA"
	T                  int64
	Spend              int64
	Pnl                int64
	HasPnl             bool
	Exit               string
	Fv, FvFill         int64
	HasFv, HasFvFill   bool
	Fh                 string
	Grp                *v5GrpFill
	Fleet              *v5FleetFill
	Fund               *v5FundFill
	AB                 string // "bypass" / "live" arms, "f1:bypass f2:live"
	ABWould            []string
}

type v5GrpFill struct {
	Pct, PctX  float64
	HasPct     bool
	WB, WBX    bool
	Miss       bool
}

type v5FleetFill struct {
	N, Min, Slots int64
	On            string
	Would         bool
	Open          string
}

type v5FundFill struct {
	Pct      float64
	N        int64
	Resolved int64
	Funder   string // from the fill's presend_live_funder record (c1.funder)
}

type landAgg struct {
	h        Hist
	n        int64
	le       [4]int64 // <= 35 / 50 / 65 / 80 ms
}

var landThr = [4]float64{35, 50, 65, 80}

func (a *landAgg) add(ms float64) {
	a.h.Add(ms)
	a.n++
	for i, t := range landThr {
		if ms <= t {
			a.le[i]++
		}
	}
}

// V5Acc gathers the v5 records (whole file, every session; like the Filters tab).
type V5Acc struct {
	ver int64
	// dip46
	d46, probeOn                bool
	probeKinds                  string
	probeRate, probeMaxW        int64
	abCfg, abNow                []string
	abNowSet                    bool
	probeArms                   map[string]int64
	probeArmN                   int64
	probeSent                   map[string]int64
	probeSentN                  int64
	probeDry                    int64
	probeTip                    map[string]float64
	lands                       []*v5Land
	probeEnds                   map[string]int64
	probeFilled                 int64
	abW                         map[int64]*v5AB
	abOrd                       []int64
	abRec                       map[string]int64
	// dip47
	fsAny                       bool
	fsCur                       map[string]json.RawMessage
	fv                          int64
	fh, fsSrc                   string
	fsT                         int64
	fsN                         int64
	changes                     []v5Change
	ctlErr                      []string
	ctlPath                     string
	pauses                      []v5Pause
	pauseSkipStatus             int64
	hasPauseStatus              bool
	caps                        []v5Cap
	capDrops                    int64
	fleets                      []v5Fleet
	grps                        []v5Grp
	grpSkips                    []v5Grp
	funders                     []v5Funder
	funderAt                    map[FKey]*v5Funder
	funderArmN                  int64
	// fills (hours / big trades / fv): keyed by w like hours.py
	fills                       map[int64]*V5Fill
	fillOrd                     []int64
	fillKey                     map[FKey]*V5Fill
	realW                       map[int64]int64
	realHas                     map[int64]bool
	exitW                       map[int64]string
	// landing
	land                        map[string]*landAgg
	landOrd                     []string
	cache                       *V5Report
	cacheVer                    int64
	cacheTape                   *ProbeTape
	curTape                     *ProbeTape                          // the tape the probes were priced on (nil = none)
	flagFn                      func(w int64, mint string) []string // the Filters report's flags of a fill (the view sets it)
}

func newV5Acc() *V5Acc {
	return &V5Acc{probeArms: map[string]int64{}, probeSent: map[string]int64{}, probeTip: map[string]float64{}, probeEnds: map[string]int64{},
		abW: map[int64]*v5AB{},
		abRec: map[string]int64{}, fsCur: map[string]json.RawMessage{}, funderAt: map[FKey]*v5Funder{}, fills: map[int64]*V5Fill{},
		fillKey: map[FKey]*V5Fill{}, realW: map[int64]int64{}, realHas: map[int64]bool{}, exitW: map[int64]string{}, land: map[string]*landAgg{}}
}

var v5Evs = map[string]bool{"presend_live_dip46": true, "presend_live_ledger_mode": true, "presend_live_probe_arm": true, "presend_live_probe": true,
	"presend_live_probe_land": true, "presend_live_probe_end": true, "presend_live_probe_filled": true, "presend_live_filter_ab": true,
	"presend_live_arm": true, "presend_live_skip": true, "presend_live_rearm_defer": true, "presend_live_fill": true, "presend_live_realized": true,
	"presend_live_exit": true, "presend_live_filter_state": true, "presend_live_grpsign": true, "presend_live_rearm_fleet": true,
	"presend_live_funder": true, "presend_attempt_land": true, "run_end": true}

var (
	v5MsFirst = `"ms_send_to_first_rx":`
	v5Client  = `"client":"`
	v5Path    = `"path":"`
)

func (A *V5Acc) bump() { A.ver++ }

func rawStr(r json.RawMessage) string {
	if len(r) == 0 {
		return ""
	}
	var s string
	if json.Unmarshal(r, &s) == nil {
		return s
	}
	return string(r)
}

// feed takes one record.
func (A *V5Acc) feed(ev, line []byte) {
	e := string(ev)
	if !v5Evs[e] {
		return
	}
	switch e {
	case "presend_attempt_land": // by substring (many)
		ms, ok := floatAfter(line, v5MsFirst)
		if !ok {
			return
		}
		cl, _ := strAfter(line, v5Client)
		pa, _ := strAfter(line, v5Path)
		if cl == "" {
			cl = "?"
		}
		if pa == "" {
			pa = "?"
		}
		A.bump()
		for _, k := range []string{"ALL", "client " + cl, "path " + pa} {
			a := A.land[k]
			if a == nil {
				a = &landAgg{}
				A.land[k] = a
				A.landOrd = append(A.landOrd, k)
			}
			a.add(ms)
		}
		return
	}
	var o map[string]any
	dec := json.NewDecoder(bytes.NewReader(line))
	dec.UseNumber()
	if dec.Decode(&o) != nil {
		return
	}
	A.bump()
	w := mW(o)
	switch e {
	case "presend_live_dip46":
		A.d46 = true
		cfg := mObj(o, "cfg")
		A.abCfg = strList(cfg["filter_ab"])
		if p := mObj(cfg, "probe"); p != nil {
			A.probeKinds = anyStr(p["kinds"])
			if x, ok := mNum(p, "max_per_sec"); ok {
				A.probeRate = int64(x)
			}
			if x, ok := mNum(p, "max_windows"); ok {
				A.probeMaxW = int64(x)
			}
		}
		A.probeOn = mBool(o, "probe_now")
		A.abNow, A.abNowSet = strList(o["ab_now"]), true
	case "presend_live_ledger_mode":
		if d := mObj(o, "dip46"); d != nil {
			if v, ok := d["probe46"].(bool); ok {
				A.probeOn = v
			}
			if _, ok := d["ab46"]; ok {
				A.abNow, A.abNowSet = strList(d["ab46"]), true
			}
		}
		if p := mStr(o, "path"); p != "" && o["dip47"] != nil {
			A.ctlPath = p
		}
		if pw := mStr(o, "pause_window"); pw == "on" || pw == "off" {
			p := v5Pause{T: tOfAny(o), On: pw == "on", Window: mStr(o, "window")}
			if x, ok := mNum(o, "skipped"); ok {
				p.Skipped, p.HasSkips = int64(x), true
			}
			A.pauses = append(A.pauses, p)
		}
		if ok, has := o["ok"].(bool); has && !ok && mBool(o, "dip47") {
			msg := mStr(o, "err")
			if k := mStr(o, "key"); k != "" {
				msg = k + ": " + msg
			}
			A.ctlErr = append(A.ctlErr, T12(float64(tOfAny(o)), true)+" "+msg)
			if len(A.ctlErr) > 20 {
				A.ctlErr = A.ctlErr[len(A.ctlErr)-20:]
			}
		}
	case "presend_live_probe_arm":
		A.probeArmN++
		A.probeArms[mStr(o, "filter")]++
	case "presend_live_probe":
		if mBool(o, "dry") {
			A.probeDry++
		}
		A.probeSentN++
		A.probeSent[mStr(o, "filter")]++
		tip, _ := mNum(o, "tip")
		A.probeTip[mStr(o, "sig")] = tip
	case "presend_live_probe_land":
		l := &v5Land{w: w, filter: mStr(o, "filter"), mint: mStr(o, "mint"), sig: mStr(o, "sig"), res: mStr(o, "res"), t: tOfAny(o)}
		if x, ok := mNum(o, "slot"); ok {
			l.slot = int64(x)
		}
		if x, ok := mNum(o, "idx"); ok {
			l.idx, l.hasIdx = int64(x), true
		}
		l.fee, _ = mNum(o, "fee")
		l.spend, _ = mNum(o, "spend")
		l.minOut, _ = mNum(o, "would_min_out")
		l.wouldFill = mBool(o, "would_fill")
		l.wouldTok, _ = mNum(o, "would_tokens")
		if p := mObj(o, "pre"); p != nil {
			if x, ok := mNum(p, "vtok"); ok {
				l.preVtok, l.hasPre = x, true
			}
		}
		A.lands = append(A.lands, l)
	case "presend_live_probe_end":
		A.probeEnds[mStr(o, "why")]++
	case "presend_live_probe_filled":
		A.probeFilled++
	case "presend_live_filter_ab":
		A.abRec[mStr(o, "filter")+":"+mStr(o, "arm")]++
	case "presend_live_arm":
		if ab := mObj(o, "ab46"); ab != nil {
			x := A.abOf(w)
			for k, v := range mObj(ab, "arms") {
				x.arms[k] = anyStr(v)
			}
			x.would = map[string]bool{}
			for _, f := range strList(ab["would"]) {
				x.would[f] = true
			}
		}
	case "presend_live_skip":
		why := mStr(o, "why")
		switch why {
		case "rearm_cap":
			c := v5Cap{T: tOfAny(o), Mint: mStr(o, "mint")}
			if c.Mint == "" {
				c.Mint = mStr(mObj(o, "trig"), "mint")
			}
			if x, ok := mNum(o, "rearm_fills"); ok {
				c.Fills = int64(x)
			}
			if x, ok := mNum(o, "cap"); ok {
				c.Cap = int64(x)
			}
			if c.T == 0 {
				c.T = tOfAny(mObj(o, "dump"))
			}
			A.caps = append(A.caps, c)
		case "grp_t2":
			g := v5Grp{W: w, Kind: "t2", At: "skip"}
			if tr := mObj(o, "trig"); tr != nil {
				g.Mint = mStr(tr, "mint")
			}
			if j := mObj(o, "grp_t2"); j != nil {
				g.Pct, _ = mNum(j, "pct")
				g.PctX, _ = mNum(j, "thr")
			}
			A.grpSkips = append(A.grpSkips, g)
		}
	case "presend_live_rearm_defer":
		if mStr(o, "why") == "rearm_cap" || mStr(o, "drop") == "rearm_cap" || mStr(o, "reason") == "rearm_cap" {
			A.capDrops++
		}
	case "presend_live_fill":
		mint := mStr(o, "mint")
		f := A.fills[w]
		if f == nil {
			f = &V5Fill{W: w, Mint: mint, Kind: "T2", T: tOfAny(o)}
			if mStr(o, "kind") == "rearm" {
				f.Kind = "RA"
			}
			sp, ok := mNum(o, "spend")
			if !ok || sp == 0 {
				sp, _ = mNum(o, "sol_in")
			}
			f.Spend = int64(sp)
			if x, ok := mNum(o, "fv"); ok {
				f.Fv, f.HasFv = int64(x), true
				f.Fh = mStr(o, "fh")
			}
			if x, ok := mNum(o, "fv_fill"); ok {
				f.FvFill, f.HasFvFill = int64(x), true
			}
			if g := mObj(o, "grpsign"); g != nil {
				x := &v5GrpFill{Miss: mBool(g, "miss"), WB: mBool(g, "would_block_t2"), WBX: mBool(g, "would_block_t2_x")}
				if p, ok := mNum(g, "pct"); ok {
					x.Pct, x.HasPct = p, true
				}
				x.PctX, _ = mNum(g, "pct_x")
				f.Grp = x
			}
			if r := mObj(o, "rearm_fleet"); r != nil {
				x := &v5FleetFill{On: mStr(r, "on"), Would: mBool(r, "would_withhold"), Open: mStr(r, "open")}
				if v, ok := mNum(r, "n"); ok {
					x.N = int64(v)
				}
				if v, ok := mNum(r, "min"); ok {
					x.Min = int64(v)
				}
				if v, ok := mNum(r, "slots"); ok {
					x.Slots = int64(v)
				}
				f.Fleet = x
			}
			if r := mObj(o, "funder"); r != nil {
				x := &v5FundFill{}
				x.Pct, _ = mNum(r, "pct")
				if v, ok := mNum(r, "n"); ok {
					x.N = int64(v)
				}
				if v, ok := mNum(r, "resolved"); ok {
					x.Resolved = int64(v)
				}
				if fr := A.funderAt[FKey{w, mint}]; fr != nil {
					x.Funder = fr.Funder
				}
				f.Fund = x
			}
			A.fills[w] = f
			A.fillOrd = append(A.fillOrd, w)
			A.fillKey[FKey{w, mint}] = f
		}
		if ab := mObj(o, "ab46"); ab != nil {
			x := A.abOf(w)
			for k, v := range mObj(ab, "arms") {
				x.arms[k] = anyStr(v)
			}
			for _, fl := range strList(ab["would"]) {
				x.would[fl] = true
			}
		}
	case "presend_live_realized":
		if x, ok := mNum(o, "pnl"); ok {
			A.realW[w] += int64(x)
			A.realHas[w] = true
		}
	case "presend_live_exit":
		if _, ok := A.exitW[w]; !ok {
			A.exitW[w] = mStr(o, "why")
		}
	case "presend_live_filter_state":
		A.fsAny = true
		fv, _ := mNum(o, "fv")
		A.fv, A.fh, A.fsSrc, A.fsT = int64(fv), mStr(o, "fh"), mStr(o, "src"), tOfAny(o)
		A.fsN++
		var r struct {
			State   map[string]json.RawMessage   `json:"state"`
			Changed map[string][]json.RawMessage `json:"changed"`
		}
		if json.Unmarshal(line, &r) == nil {
			if r.State != nil {
				A.fsCur = r.State
			}
			keys := make([]string, 0, len(r.Changed))
			for k := range r.Changed {
				keys = append(keys, k)
			}
			sort.Strings(keys)
			for _, k := range keys {
				c := r.Changed[k]
				ch := v5Change{T: A.fsT, Fv: A.fv, Key: k, Src: A.fsSrc}
				if len(c) > 0 {
					ch.Old = compactJSON(c[0])
				}
				if len(c) > 1 {
					ch.New = compactJSON(c[1])
				}
				A.changes = append(A.changes, ch)
			}
		}
	case "presend_live_grpsign":
		g := v5Grp{W: w, Mint: mStr(o, "mint"), Kind: mStr(o, "kind"), At: mStr(o, "at"), WB: mBool(o, "would_block_t2"), WBX: mBool(o, "would_block_t2_x"),
			WB6: mBool(o, "would_block_6"), WhaleIn: mBool(o, "whale_in")}
		g.Pct, _ = mNum(o, "grp_pct")
		g.PctX, _ = mNum(o, "grp_pct_x")
		if x, ok := mNum(o, "n"); ok {
			g.N = int64(x)
		}
		A.grps = append(A.grps, g)
	case "presend_live_rearm_fleet":
		f := v5Fleet{T: tOfAny(o), W: w, Mint: mStr(o, "mint"), Mode: mStr(o, "mode"), OpenWhy: mStr(o, "open_why")}
		get := func(k string) int64 { x, _ := mNum(o, k); return int64(x) }
		f.Tries, f.Passed, f.Withheld, f.Would, f.Open = get("tries"), get("passed"), get("withheld"), get("would"), get("open")
		A.fleets = append(A.fleets, f)
	case "presend_live_funder":
		f := &v5Funder{W: w, Mint: mStr(o, "mint"), At: mStr(o, "at")}
		f.Pct, _ = mNum(o, "pct")
		if x, ok := mNum(o, "n"); ok {
			f.N = int64(x)
		}
		if x, ok := mNum(o, "resolved"); ok {
			f.Resolved = int64(x)
		}
		if c := mObj(o, "c1"); c != nil {
			f.HasC1 = true
			f.Funder = mStr(c, "funder")
			f.C1Pct, _ = mNum(c, "pct")
			if x, ok := mNum(c, "n_wallets"); ok {
				f.C1N = int64(x)
			}
		}
		if f.At == "fill" {
			A.funderAt[FKey{w, f.Mint}] = f
			if fl := A.fillKey[FKey{w, f.Mint}]; fl != nil && fl.Fund != nil && fl.Fund.Funder == "" { // the record after its fill
				fl.Fund.Funder = f.Funder
			}
		} else {
			A.funderArmN++
		}
		A.funders = append(A.funders, *f)
		if len(A.funders) > 20000 {
			A.funders = A.funders[len(A.funders)-20000:]
		}
	case "run_end":
		if pl := mObj(o, "presend_live"); pl != nil {
			if sk := mObj(pl, "skips"); sk != nil {
				if x, ok := mNum(sk, "pause_window"); ok {
					A.pauseSkipStatus, A.hasPauseStatus = int64(x), true
				}
			}
		}
	}
}

func (A *V5Acc) abOf(w int64) *v5AB {
	x := A.abW[w]
	if x == nil {
		x = &v5AB{arms: map[string]string{}, would: map[string]bool{}}
		A.abW[w] = x
		A.abOrd = append(A.abOrd, w)
	}
	return x
}

var rxPSSkips = regexp.MustCompile(`PRESEND LIVE: triggers .*? skips (\{[^}]*\})`)

// logLine: the status line's skips (the pause's count: no record per skipped trigger).
func (A *V5Acc) logLine(st string) {
	if !strings.Contains(st, `"pause_window"`) {
		return
	}
	if m := rxPSSkips.FindStringSubmatch(st); m != nil {
		var sk map[string]int64
		if json.Unmarshal([]byte(m[1]), &sk) == nil {
			if n, ok := sk["pause_window"]; ok {
				A.pauseSkipStatus, A.hasPauseStatus = n, true
				A.bump()
			}
		}
	}
}

func strList(v any) []string {
	xs, _ := v.([]any)
	var out []string
	for _, x := range xs {
		out = append(out, anyStr(x))
	}
	return out
}

func anyStr(v any) string {
	switch x := v.(type) {
	case nil:
		return ""
	case string:
		return x
	case json.Number:
		return x.String()
	case bool:
		return strconv.FormatBool(x)
	}
	b, _ := json.Marshal(v)
	return string(b)
}

func compactJSON(r json.RawMessage) string {
	var b bytes.Buffer
	if json.Compact(&b, r) != nil {
		return string(r)
	}
	s := b.String()
	if len(s) >= 2 && s[0] == '"' {
		return rawStr(r)
	}
	return s
}

func tOfAny(o map[string]any) int64 {
	if o == nil {
		return 0
	}
	if x, ok := o["t"].(json.Number); ok {
		if n, err := x.Int64(); err == nil {
			return n
		}
		if f, err := x.Float64(); err == nil {
			return int64(f)
		}
	}
	if x, ok := o["t"].(float64); ok {
		return int64(x)
	}
	return 0
}

// ------------------------------------------------------------------------------------------------- report

// V5Report: the v5 sections. Rule = the dip46 / dip47 sections (snapshot by default), Stats = hours / big / landing.
type V5Report struct {
	A           *V5Acc
	Rule, Stats []*D43Section
	Fills       []*V5Fill // in fill order
	Hours       *HoursTable
	ProbeRows   []ProbeRow
	FvOn        bool // a trade row carries fv (dip47)
	Pause       *PauseView
}

// PauseView: the pause banner (Active, the window, the next start / end in PKT, the manual pause).
type PauseView struct {
	Active               bool
	Window, Manual       string
	NextStart, NextEnd   int64 // ns (0 = none)
	Skips                int64
}

// ProbeRow: one filter's probe line (probe_check.py part 1).
type ProbeRow struct {
	Filter                                string
	Probes, Windows, Would, EngWould      int64
	Agree, Win, Lose                      int64
	Net, Net1, Fees                       float64
	Why                                   map[string]int64
	Priced                                bool
}

// Report: the sections for the view (now: ns, the pause's next start / end; tape: --probe-tape or nil = no exit pricing; multi:
// --runs-files).
func (A *V5Acc) Report(now int64, tape *ProbeTape, multi *MultiRuns) *V5Report {
	if NoV4 {
		return nil
	}
	if A.cache != nil && A.cacheVer == A.ver && A.cacheTape == tape {
		A.cache.Pause = A.pauseView(now) // the clock moves
		A.cache.Rule = A.ruleSections(A.cache)
		return A.cache
	}
	R := &V5Report{A: A}
	for _, w := range A.fillOrd {
		f := A.fills[w]
		f.Pnl, f.HasPnl = A.realW[w], A.realHas[w]
		f.Exit = A.exitW[w]
		if ab := A.abW[w]; ab != nil {
			var ps []string
			for _, k := range sortedKeysS(ab.arms) {
				ps = append(ps, k+":"+ab.arms[k])
			}
			f.AB = strings.Join(ps, " ")
			f.ABWould = nil
			for k := range ab.would {
				f.ABWould = append(f.ABWould, k)
			}
			sort.Strings(f.ABWould)
		}
		R.Fills = append(R.Fills, f)
		if f.HasFv {
			R.FvOn = true
		}
	}
	R.ProbeRows = A.probeRows(tape)
	R.Pause = A.pauseView(now)
	R.Rule = A.ruleSections(R)
	R.Hours = A.hours()
	var mh *HoursTable
	if multi != nil {
		mh = multi.Hours
	}
	if s := secHours(R.Hours, mh); s != nil {
		R.Stats = append(R.Stats, s)
	}
	if s := A.secBig(R); s != nil {
		R.Stats = append(R.Stats, s)
	}
	if s := A.secLanding("landing", "LANDING BY LEADER CLIENT (send → first rx, ms; every seen try)"); s != nil {
		R.Stats = append(R.Stats, s)
	}
	if multi != nil {
		if s := multi.Land.secLanding("landing_multi", fmt.Sprintf("LANDING BY LEADER CLIENT, %d run files (--runs-files)", len(multi.Files))); s != nil {
			R.Stats = append(R.Stats, s)
		}
	}
	A.cache, A.cacheVer, A.cacheTape = R, A.ver, tape
	return R
}

func (A *V5Acc) ruleSections(R *V5Report) []*D43Section {
	var out []*D43Section
	for _, f := range []func(*V5Report) *D43Section{A.secProbes, A.secAB, A.secFState, A.secPause, A.secCap, A.secFleet, A.secGrp, A.secFunder} {
		if s := f(R); s != nil {
			out = append(out, s)
		}
	}
	return out
}

// Fill: a position's v5 view (nil = none).
func (R *V5Report) Fill(w int64, mint string) *V5Fill {
	if R == nil {
		return nil
	}
	return R.A.fillKey[FKey{w, mint}]
}

// FvCell: the Trades row's fv ("3", "3*" when fv_fill differs, "" = none).
func (f *V5Fill) FvCell() string {
	if f == nil || !f.HasFv {
		return ""
	}
	s := strconv.FormatInt(f.Fv, 10)
	if f.HasFvFill && f.FvFill != f.Fv {
		s += "*"
	}
	return s
}

// solU: a SOL amount with the ◎ unit ("SOL" with --ascii).
func solU(x float64, d int) string {
	if G.ASCII {
		return FS(x, d) + " SOL"
	}
	return FS(x, d) + " ◎"
}

func lamU(x int64, d int) string { return solU(float64(x)/1e9, d) }

func unitS() string {
	if G.ASCII {
		return "SOL"
	}
	return "◎"
}

// ---- dip46 probes

func (A *V5Acc) probeRows(ext *ProbeTape) []ProbeRow {
	if len(A.lands) == 0 && A.probeSentN == 0 {
		return nil
	}
	tp := ext // nil: the engine's own would_fill, no exit pricing (the run's records miss most of the mint's trades)
	A.curTape = tp
	rows := map[string]*ProbeRow{}
	var order []string
	row := func(f string) *ProbeRow {
		r := rows[f]
		if r == nil {
			r = &ProbeRow{Filter: f, Why: map[string]int64{}}
			rows[f] = r
			order = append(order, f)
		}
		return r
	}
	for _, l := range A.lands {
		r := row(l.filter)
		r.Probes++
		r.Fees += l.fee
	}
	type wk struct {
		w int64
		f string
	}
	byW := map[wk][]*v5Land{}
	var wOrd []wk
	for _, l := range A.lands {
		if l.res == "unseen" || !l.hasIdx {
			continue
		}
		k := wk{l.w, l.filter}
		if _, ok := byW[k]; !ok {
			wOrd = append(wOrd, k)
		}
		byW[k] = append(byW[k], l)
	}
	for _, k := range wOrd {
		L := byW[k]
		sort.SliceStable(L, func(a, b int) bool {
			if L[a].slot != L[b].slot {
				return L[a].slot < L[b].slot
			}
			return L[a].idx < L[b].idx
		})
		r := row(k.f)
		r.Windows++
		var first *v5Land
		var fT0, fTok float64
		for _, l := range L {
			eng := l.wouldFill
			var would bool
			var T0, tok float64
			if tp != nil && tp.Chain {
				if p, ok := tp.pre(l.mint, l.slot, l.idx); ok {
					T0 = p.v
				} else if l.hasPre {
					T0 = l.preVtok
				} else {
					continue
				}
				tok = pcBuyTokens(T0, l.spend)
				would = tok >= l.minOut
				if would == eng {
					r.Agree++
				}
			} else {
				would, T0, tok = eng, l.preVtok, l.wouldTok
			}
			if eng {
				r.EngWould++
			}
			if would && first == nil {
				first, fT0, fTok = l, T0, tok
			}
		}
		if first == nil {
			continue
		}
		r.Would++
		if tp == nil || first.spend <= 0 || fT0 <= 0 {
			continue
		}
		r.Priced = true
		out, why := tp.priceExit(first.mint, first.slot, first.idx, fT0, fTok, first.spend)
		pnl := (out - first.spend - first.fee - A.probeTip[first.sig] - pcSellFx) / 1e9
		r.Net += pnl
		r.Net1 += pnl * (1e9 / first.spend)
		if pnl > 0 {
			r.Win++
		} else {
			r.Lose++
		}
		r.Why[why]++
	}
	sort.Strings(order)
	out := make([]ProbeRow, 0, len(order))
	for _, f := range order {
		out = append(out, *rows[f])
	}
	return out
}

func (A *V5Acc) secProbes(R *V5Report) *D43Section {
	if !A.d46 && A.probeSentN == 0 && len(A.lands) == 0 {
		return nil
	}
	if A.probeSentN == 0 && len(A.lands) == 0 && !A.probeOn {
		return nil
	}
	s := &D43Section{Key: "probes", Title: "PROBES (dip46: blocked tries sent so they can never fill)", JSON: &JObj{}}
	var seen, unseen int64
	var fees float64
	for _, l := range A.lands {
		fees += l.fee
		if l.res == "unseen" {
			unseen++
		} else {
			seen++
		}
	}
	mode := map[bool]string{true: "on", false: "off"}[A.probeOn]
	head := fmt.Sprintf("probes %s · sent %s", mode, IC(A.probeSentN))
	if A.probeDry > 0 {
		head += fmt.Sprintf(" (dry %s)", IC(A.probeDry))
	}
	head += fmt.Sprintf(", landed %s, unseen %s · probe windows %s · fees %s", IC(seen), IC(unseen), IC(A.probeArmN), solU(fees/1e9, 6))
	s.Lines = append(s.Lines, head)
	cfg := "kinds " + orDash(A.probeKinds)
	if A.probeRate > 0 {
		cfg += fmt.Sprintf(" · max %d/s · max windows %d", A.probeRate, A.probeMaxW)
	}
	if len(A.probeEnds) > 0 {
		cfg += " · windows ended: " + kvs(A.probeEnds)
	}
	if A.probeFilled > 0 {
		cfg += fmt.Sprintf(" · IMPOSSIBLE FILLS %d", A.probeFilled)
	}
	s.Lines = append(s.Lines, cfg)
	priced, chain := false, false
	for _, r := range R.ProbeRows {
		priced = priced || r.Priced
	}
	src := "engine's would_fill; net needs the chain tape (tests/probe_tape.py LOG FILE, then --probe-tape FILE)"
	if priced || A.cacheTapeChain() {
		chain = true
		src = "chain tape " + RuneSlice(A.curTape.Src, 40) + " + exit priced (as probe_check.py)"
	}
	s.Lines = append(s.Lines, "would-fill: each window's FIRST landing where the real try would have filled; r82 exit (2350 ms, TP / SL 20%) · "+src)
	hdr := fmt.Sprintf("%-20s %6s %7s %5s %4s %4s %10s %10s %10s", "filter", "probes", "windows", "would", "win", "lose", "net "+unitS(), "net@1"+unitS(), "fees "+unitS())
	if chain {
		hdr += "  agree"
	}
	s.Lines = append(s.Lines, "  "+hdr)
	s.Pre = append(s.Pre, len(s.Lines)-1)
	rows := []any{}
	var tw, tl, tp, twin, tlose int64
	var tn, tn1, tf float64
	for _, r := range R.ProbeRows {
		net, net1 := "–", "–"
		if r.Priced || (priced && r.Would == 0) {
			net, net1 = FS(r.Net, 4), FS(r.Net1, 4)
		}
		wn, ls := "–", "–"
		if chain {
			wn, ls = strconv.FormatInt(r.Win, 10), strconv.FormatInt(r.Lose, 10)
		}
		l := fmt.Sprintf("%-20s %6d %7d %5d %4s %4s %10s %10s %10s", RuneSlice(r.Filter, 20), r.Probes, r.Windows, r.Would, wn, ls, net, net1, F(r.Fees/1e9, 6))
		if chain {
			l += fmt.Sprintf("  %5d", r.Agree)
		}
		s.Lines = append(s.Lines, "  "+l)
		s.Pre = append(s.Pre, len(s.Lines)-1)
		tone := ""
		if r.Priced && r.Net > 0 {
			tone = "pos"
		} else if r.Priced && r.Net < 0 {
			tone = "neg"
		}
		s.setTone(len(s.Lines)-1, tone)
		tw += r.Windows
		tl += r.Would
		tp += r.Probes
		twin += r.Win
		tlose += r.Lose
		tn += r.Net
		tn1 += r.Net1
		tf += r.Fees
		o := &JObj{}
		o.Set("filter", r.Filter).Set("probes", r.Probes).Set("windows", r.Windows).Set("would", r.Would).Set("eng_would", r.EngWould).Set("agree", r.Agree).
			Set("win", r.Win).Set("lose", r.Lose).Set("net", PyFloat(round6(r.Net))).Set("net_1sol", PyFloat(round6(r.Net1))).Set("fees", int64(r.Fees)).Set("priced", r.Priced)
		ex := &JObj{}
		for _, k := range sortedKeys(r.Why) {
			ex.Set(k, r.Why[k])
		}
		o.Set("exits", ex)
		rows = append(rows, o)
	}
	if len(R.ProbeRows) > 1 {
		net := "–"
		if priced {
			net = FS(tn, 4)
		}
		wn, ls := "–", "–"
		if chain {
			wn, ls = strconv.FormatInt(twin, 10), strconv.FormatInt(tlose, 10)
		}
		l := fmt.Sprintf("%-20s %6d %7d %5d %4s %4s %10s %10s %10s", "ALL", tp, tw, tl, wn, ls, net, map[bool]string{true: FS(tn1, 4), false: "–"}[priced], F(tf/1e9, 6))
		s.Lines = append(s.Lines, "  "+l)
		s.Pre = append(s.Pre, len(s.Lines)-1)
	}
	s.Lines = append(s.Lines, "would-fill = the curve before the probe's landing meets the real min_out; arm-time windows carry no floors (an upper bound); one try a slot (the real window sends 20)")
	s.JSON.Set("on", A.probeOn).Set("sent", A.probeSentN).Set("dry", A.probeDry).Set("landed", seen).Set("unseen", unseen).Set("windows", A.probeArmN).
		Set("fees", int64(fees)).Set("impossible_fills", A.probeFilled).Set("priced_src", src).Set("rows", rows)
	return s
}

func (A *V5Acc) cacheTapeChain() bool { return A.curTape != nil && A.curTape.Chain }

func round6(x float64) float64 { return math.Round(x*1e9) / 1e9 }

func orDash(s string) string {
	if s == "" {
		return G.Dash
	}
	return s
}

// ---- dip46 filter A/B

func (A *V5Acc) secAB(R *V5Report) *D43Section {
	if !A.d46 && len(A.abW) == 0 && len(A.abRec) == 0 {
		return nil
	}
	if len(A.abCfg) == 0 && len(A.abW) == 0 && len(A.abRec) == 0 {
		return nil
	}
	s := &D43Section{Key: "ab46", Title: "FILTER A/B (dip46: odd half bypassed, even half live)", JSON: &JObj{}}
	now := "off"
	if len(A.abNow) > 0 {
		now = strings.Join(A.abNow, ", ")
	}
	s.Lines = append(s.Lines, fmt.Sprintf("configured %s · A/B now: %s", orDash(strings.Join(A.abCfg, ", ")), now))
	s.JSON.Set("configured", anyList(A.abCfg)).Set("now", anyList(A.abNow))
	filters := map[string]bool{}
	for _, w := range A.abOrd {
		for f := range A.abW[w].arms {
			filters[f] = true
		}
	}
	if len(filters) == 0 {
		s.Lines = append(s.Lines, "no ab46-tagged window in this run (no A/B arm has armed yet)")
		s.JSON.Set("rows", []any{})
		return s
	}
	fl := make([]string, 0, len(filters))
	for f := range filters {
		fl = append(fl, f)
	}
	sort.Strings(fl)
	s.Lines = append(s.Lines, "  "+fmt.Sprintf("%-16s %-26s %-26s %-26s", "filter", "live: win fills P&L", "bypass: win fills P&L", "bypass-would: win fills P&L"))
	s.Pre = append(s.Pre, len(s.Lines)-1)
	rows := []any{}
	for _, f := range fl {
		o := &JObj{}
		o.Set("filter", f)
		var cells []string
		for _, arm := range []string{"live", "bypass", "bwould"} {
			var nw, nf int64
			var p int64
			for _, w := range A.abOrd {
				a := A.abW[w]
				in := a.arms[f] == arm
				if arm == "bwould" {
					in = a.arms[f] == "bypass" && a.would[f]
				}
				if !in {
					continue
				}
				nw++
				if A.realHas[w] {
					nf++
					p += A.realW[w]
				}
			}
			cells = append(cells, fmt.Sprintf("%5d %5d %+10.4f", nw, nf, float64(p)/1e9))
			o.Set(arm, (&JObj{}).Set("windows", nw).Set("filled", nf).Set("pnl", p))
		}
		s.Lines = append(s.Lines, "  "+fmt.Sprintf("%-16s %-26s %-26s %-26s", RuneSlice(f, 16), cells[0], cells[1], cells[2]))
		s.Pre = append(s.Pre, len(s.Lines)-1)
		rows = append(rows, o)
	}
	if len(A.abRec) > 0 {
		s.Lines = append(s.Lines, "filter_ab records: "+kvs(A.abRec))
	}
	s.Lines = append(s.Lines, "P&L = real realized (presend_live_realized joined on w); bypass-would = the bypass windows the filter would have blocked (what it costs / saves)")
	s.JSON.Set("rows", rows)
	return s
}

func anyList(xs []string) []any {
	out := make([]any, 0, len(xs))
	for _, x := range xs {
		out = append(out, x)
	}
	return out
}

// ---- dip47 filter state

// fsGroups: the state keys by block (the rest under "other").
var fsGroups = []struct {
	name string
	keys []string
}{
	{"ledgers", []string{"whale", "wh_kinds", "wh_loss", "holder", "holder_loss", "mint_ledger", "mint_ledger_sol", "blocklist_send", "blocklist_arm", "botdepth"}},
	{"arm gates", []string{"quiet", "quiet3a", "create_slot", "young_age", "min_age_slots", "lone_whale", "cr_loss", "breaker", "s1", "grp_t2", "grp_t2_pct", "grp_t2_whale", "grpsign_log"}},
	{"re-arm", []string{"rearm", "rearm_r5", "size_rearm", "rearm_max_per_mint", "rearm_fleet", "rearm_fleet_spec", "fleet_log"}},
	{"send", []string{"fpnb_t2", "fpnb_rearm", "fpnb_strict", "skip2", "floors", "curve_deep", "curve_deep_pct", "guard", "fee_tier", "routes", "k", "drop", "size_t2"}},
	{"exits", []string{"exit_ms", "tp", "sl", "exit_lots", "dump_exit"}},
	{"pause / shadows", []string{"pause_window", "pause_now", "stall", "deadman", "fanout", "widedumper", "qf2", "qf2_size", "qf2_min_age", "probe46", "ab46", "funder_log", "limits"}},
}

func (A *V5Acc) secFState(R *V5Report) *D43Section {
	if !A.fsAny {
		return nil
	}
	s := &D43Section{Key: "fstate", Title: "FILTER STATE (dip47)", JSON: &JObj{}}
	s.Lines = append(s.Lines, fmt.Sprintf("fv %d  fh %s · %d versions · last %s (%s) · %d changes", A.fv, A.fh, A.fsN, T12(float64(A.fsT), true), A.fsSrc, len(A.changes)))
	done := map[string]bool{}
	var kv []string
	addGroup := func(name string, keys []string) {
		var parts []string
		for _, k := range keys {
			v, ok := A.fsCur[k]
			if !ok || done[k] {
				continue
			}
			done[k] = true
			parts = append(parts, k+" "+fsVal(v))
		}
		if len(parts) > 0 {
			s.Lines = append(s.Lines, "  "+name+": "+strings.Join(parts, " · "))
			kv = append(kv, parts...)
		}
	}
	for _, g := range fsGroups {
		addGroup(g.name, g.keys)
	}
	var rest []string
	for k := range A.fsCur {
		if !done[k] {
			rest = append(rest, k)
		}
	}
	sort.Strings(rest)
	addGroup("other", rest)
	st := &JObj{}
	keys := make([]string, 0, len(A.fsCur))
	for k := range A.fsCur {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		st.Set(k, fsVal(A.fsCur[k]))
	}
	if len(A.changes) > 0 {
		s.Lines = append(s.Lines, "changes (newest first):")
		n := 0
		for i := len(A.changes) - 1; i >= 0 && n < 12; i-- {
			c := A.changes[i]
			s.Lines = append(s.Lines, fmt.Sprintf("  %s  fv %d  %s  %s %s %s  (%s)", T12(float64(c.T), true), c.Fv, c.Key, c.Old, G.Arrow, c.New, c.Src))
			n++
		}
		if len(A.changes) > 12 {
			s.Lines = append(s.Lines, fmt.Sprintf("  … %d older", len(A.changes)-12))
		}
	}
	if len(A.ctlErr) > 0 {
		s.Lines = append(s.Lines, "control file errors: "+strings.Join(A.ctlErr, " · "))
		s.setTone(len(s.Lines)-1, "warn")
	}
	var nFv, nStar int
	for _, f := range R.Fills {
		if f.HasFv {
			nFv++
			if f.HasFvFill && f.FvFill != f.Fv {
				nStar++
			}
		}
	}
	if nFv > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("trades: %d carry fv (the state at the window's arm), %d with * (the state moved before the fill: fv_fill)", nFv, nStar))
	}
	chs := []any{}
	for _, c := range A.changes {
		chs = append(chs, (&JObj{}).Set("t", c.T).Set("fv", c.Fv).Set("key", c.Key).Set("old", c.Old).Set("new", c.New).Set("src", c.Src))
	}
	s.JSON.Set("fv", A.fv).Set("fh", A.fh).Set("versions", A.fsN).Set("src", A.fsSrc).Set("state", st).Set("changes", chs)
	return s
}

func fsVal(r json.RawMessage) string {
	s := compactJSON(r)
	if s == "null" {
		return G.Dash
	}
	if s == "" {
		return `""`
	}
	return s
}

// ---- dip47 pause

type pkWin struct{ a, b int }

func parsePause(s string) []pkWin {
	var out []pkWin
	for _, w := range strings.Split(s, ",") {
		w = strings.TrimSpace(w)
		a, b, ok := strings.Cut(w, "-")
		if !ok {
			continue
		}
		hm := func(x string) (int, bool) {
			h, m, ok := strings.Cut(strings.TrimSpace(x), ":")
			if !ok {
				return 0, false
			}
			hh, e1 := strconv.Atoi(h)
			mm, e2 := strconv.Atoi(m)
			if e1 != nil || e2 != nil || hh > 23 || mm > 59 {
				return 0, false
			}
			return hh*60 + mm, true
		}
		x, ok1 := hm(a)
		y, ok2 := hm(b)
		if ok1 && ok2 && x != y {
			out = append(out, pkWin{x, y})
		}
	}
	return out
}

func pauseHit(ws []pkWin, m int) bool {
	for _, w := range ws {
		if (w.a < w.b && m >= w.a && m < w.b) || (w.a > w.b && (m >= w.a || m < w.b)) {
			return true
		}
	}
	return false
}

// nextEdge: the next minute (ns, from now) where the pause state becomes `on` (start) / not on (end); 0 = none in 2 days.
func nextEdge(ws []pkWin, now int64, on bool) int64 {
	t := time.Unix(0, now).In(PKT).Truncate(time.Minute)
	for i := 1; i <= 2*1440; i++ {
		x := t.Add(time.Duration(i) * time.Minute)
		if pauseHit(ws, x.Hour()*60+x.Minute()) == on {
			return x.UnixNano()
		}
	}
	return 0
}

func (A *V5Acc) pauseView(now int64) *PauseView {
	win := rawStr(A.fsCur["pause_window"])
	manual := rawStr(A.fsCur["pause_now"])
	if len(A.pauses) == 0 && win == "" && (manual == "" || manual == "off") && !A.hasPauseStatus {
		return nil
	}
	P := &PauseView{Window: win, Manual: manual}
	if n := len(A.pauses); n > 0 {
		P.Active = A.pauses[n-1].On
	}
	ws := parsePause(win)
	if len(ws) > 0 && now > 0 {
		P.NextStart = nextEdge(ws, now, true)
		P.NextEnd = nextEdge(ws, now, false)
	}
	P.Skips = A.pauseSkipStatus
	return P
}

func (A *V5Acc) secPause(R *V5Report) *D43Section {
	P := R.Pause
	if P == nil {
		return nil
	}
	s := &D43Section{Key: "pause", Title: "PAUSE (dip47: no new arms inside the window; open positions exit as usual)", JSON: &JObj{}}
	state := "INACTIVE"
	tone := "dim"
	if P.Active {
		state, tone = "ACTIVE · no new arms", "neg"
	}
	cur := ""
	if n := len(A.pauses); n > 0 && P.Active {
		cur = " (" + A.pauses[n-1].Window + " since " + T12(float64(A.pauses[n-1].T), false) + ")"
	}
	s.Lines = append(s.Lines, "■ "+state+cur)
	if G.ASCII {
		s.Lines[0] = "# " + state + cur
	}
	s.setTone(0, tone)
	wl := "window " + orDash(P.Window) + " PKT"
	if P.Window != "" {
		for _, w := range parsePause(P.Window) {
			wl += fmt.Sprintf(" (%s %s %s)", hm12(w.a), G.Arrow, hm12(w.b))
		}
		if P.Active && P.NextEnd > 0 {
			wl += " · ends " + T12Date(float64(P.NextEnd), false)
		} else if P.NextStart > 0 {
			wl += " · next " + T12Date(float64(P.NextStart), false) + " " + G.Arrow + " " + T12(float64(nextEndAfter(parsePause(P.Window), P.NextStart)), false)
		}
	}
	s.Lines = append(s.Lines, wl)
	man := P.Manual
	if man == "" {
		man = G.Dash
	}
	s.Lines = append(s.Lines, "manual pause (pause_now) "+man)
	if man == "on" {
		s.setTone(len(s.Lines)-1, "neg")
	}
	var closed int64
	periods := []any{}
	if len(A.pauses) > 0 {
		s.Lines = append(s.Lines, "periods (arms skipped):")
		var on *v5Pause
		for i := range A.pauses {
			p := &A.pauses[i]
			if p.On {
				on = p
				continue
			}
			from := "?"
			if on != nil {
				from = T12(float64(on.T), false)
			}
			s.Lines = append(s.Lines, fmt.Sprintf("  %s %s %s  %s  %s skipped", from, G.Arrow, T12(float64(p.T), false), p.Window, IC(p.Skipped)))
			closed += p.Skipped
			periods = append(periods, (&JObj{}).Set("on", tOrNil(on)).Set("off", p.T).Set("window", p.Window).Set("skipped", p.Skipped))
			on = nil
		}
		if on != nil {
			cur := P.Skips - closed
			cs := IC(cur) + " skipped so far"
			if !A.hasPauseStatus || cur < 0 {
				cs = "skips counted at its end"
			}
			s.Lines = append(s.Lines, fmt.Sprintf("  %s %s now  %s  %s", T12(float64(on.T), false), G.Arrow, on.Window, cs))
			periods = append(periods, (&JObj{}).Set("on", on.T).Set("off", nil).Set("window", on.Window).Set("skipped", nil))
		}
	}
	if A.hasPauseStatus {
		s.Lines = append(s.Lines, fmt.Sprintf("total arms skipped (pause_window) %s", IC(P.Skips)))
	}
	s.JSON.Set("active", P.Active).Set("window", P.Window).Set("manual", P.Manual).Set("next_start", P.NextStart).Set("next_end", P.NextEnd).
		Set("skips_total", P.Skips).Set("periods", periods)
	return s
}

func tOrNil(p *v5Pause) any {
	if p == nil {
		return nil
	}
	return p.T
}

func nextEndAfter(ws []pkWin, start int64) int64 { return nextEdge(ws, start, false) }

func hm12(m int) string {
	h := m / 60
	ap := "AM"
	if h >= 12 {
		ap = "PM"
	}
	h12 := h % 12
	if h12 == 0 {
		h12 = 12
	}
	return fmt.Sprintf("%d:%02d %s", h12, m%60, ap)
}

// ---- dip47 re-arm cap

func (A *V5Acc) secCap(R *V5Report) *D43Section {
	capv := rawStr(A.fsCur["rearm_max_per_mint"])
	if len(A.caps) == 0 && A.capDrops == 0 && (capv == "" || capv == "0") {
		return nil
	}
	s := &D43Section{Key: "rearm_cap", Title: "RE-ARM CAP (dip47: re-arm fills per mint)", JSON: &JObj{}}
	cs := capv
	if cs == "0" || cs == "" {
		cs = "off"
	}
	s.Lines = append(s.Lines, fmt.Sprintf("cap %s · blocks %d (re-arm checks skipped \"rearm_cap\") · waiting windows dropped %d", cs, len(A.caps), A.capDrops))
	byMint := map[string]int{}
	var ord []string
	for _, c := range A.caps {
		if byMint[c.Mint] == 0 {
			ord = append(ord, c.Mint)
		}
		byMint[c.Mint]++
	}
	toks := []any{}
	for i := len(ord) - 1; i >= 0; i-- {
		m := ord[i]
		var last v5Cap
		for _, c := range A.caps {
			if c.Mint == m {
				last = c
			}
		}
		if len(ord)-1-i < 15 {
			s.Lines = append(s.Lines, fmt.Sprintf("  %s  %s  blocked %d× (fills %d / cap %d)  https://gmgn.ai/sol/token/%s", T12(float64(last.T), false), RuneSlice(m, 8), byMint[m], last.Fills, last.Cap, m))
		}
		toks = append(toks, (&JObj{}).Set("mint", m).Set("blocks", byMint[m]).Set("fills", last.Fills).Set("cap", last.Cap).Set("t", last.T))
	}
	if len(ord) > 15 {
		s.Lines = append(s.Lines, fmt.Sprintf("  … %d more tokens", len(ord)-15))
	}
	s.JSON.Set("cap", capv).Set("blocks", len(A.caps)).Set("dropped", A.capDrops).Set("tokens", toks)
	return s
}

// ---- dip47 re-arm fleet rule

func (A *V5Acc) secFleet(R *V5Report) *D43Section {
	mode := rawStr(A.fsCur["rearm_fleet"])
	var fills []*V5Fill
	for _, f := range R.Fills {
		if f.Fleet != nil {
			fills = append(fills, f)
		}
	}
	if len(A.fleets) == 0 && len(fills) == 0 && (mode == "" || mode == "off") {
		return nil
	}
	if mode == "" && len(A.fleets) > 0 {
		mode = A.fleets[len(A.fleets)-1].Mode
	}
	s := &D43Section{Key: "rearm_fleet", Title: "RE-ARM FLEET RULE (dip47: re-arm tries need fleet tries on the mint)", JSON: &JObj{}}
	spec := rawStr(A.fsCur["rearm_fleet_spec"])
	s.Lines = append(s.Lines, fmt.Sprintf("mode %s · spec %s (N fleet tries in the SLOTS before signing)", strings.ToUpper(orDash(mode)), orDash(spec)))
	var wins, wPassed, wWith, wWould, wOpen int64
	var tTries, tPassed, tWith, tWould, tOpen int64
	opens := map[string]int64{}
	for _, f := range A.fleets {
		wins++
		tTries += f.Tries
		tPassed += f.Passed
		tWith += f.Withheld
		tWould += f.Would
		tOpen += f.Open
		switch {
		case f.Withheld > 0:
			wWith++
		case f.Would > 0:
			wWould++
		case f.Open > 0:
			wOpen++
		default:
			wPassed++
		}
		if f.OpenWhy != "" {
			opens[f.OpenWhy] += f.Open
		}
	}
	s.Lines = append(s.Lines, fmt.Sprintf("re-arm windows %d: all sent %d · withheld (live) %d · would-withhold (log) %d · fail-open %d", wins, wPassed, wWith, wWould, wOpen))
	s.Lines = append(s.Lines, fmt.Sprintf("  tries %s: fleet seen %s · withheld %s · would %s · open %s %s", IC(tTries), IC(tPassed), IC(tWith), IC(tWould), IC(tOpen), map[bool]string{true: "(" + kvs(opens) + ")", false: ""}[len(opens) > 0]))
	var nW, nWo, nWr, nWor, nLog, nLogR int64
	var pW, pWo, pLog int64
	for _, f := range fills {
		without := f.Fleet.Would && f.Fleet.Open == ""
		if without {
			nWo++
			if f.HasPnl {
				nWor++
				pWo += f.Pnl
			}
			if f.Fleet.On != "live" { // sent only because the rule ran in log mode
				nLog++
				if f.HasPnl {
					nLogR++
					pLog += f.Pnl
				}
			}
		} else {
			nW++
			if f.HasPnl {
				nWr++
				pW += f.Pnl
			}
		}
	}
	if len(fills) > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("re-arm fills WITH fleet  %d  real P&L %s (%d realized)", nW, lamU(pW, 4), nWr))
		s.setTone(len(s.Lines)-1, tonePnl(pW))
		s.Lines = append(s.Lines, fmt.Sprintf("re-arm fills WITHOUT     %d  real P&L %s (%d realized)", nWo, lamU(pWo, 4), nWor))
		s.setTone(len(s.Lines)-1, tonePnl(pWo))
		if nLog > 0 || strings.ToLower(mode) != "live" {
			s.Lines = append(s.Lines, fmt.Sprintf("would have saved (fills sent in log mode without fleet: %d, %d realized) %s", nLog, nLogR, lamU(-pLog, 4)))
			s.setTone(len(s.Lines)-1, tonePnl(-pLog))
		}
	}
	s.JSON.Set("mode", mode).Set("spec", spec).Set("windows", wins).Set("windows_sent", wPassed).Set("windows_withheld", wWith).Set("windows_would", wWould).
		Set("windows_open", wOpen).Set("tries", tTries).Set("tries_withheld", tWith).Set("tries_would", tWould).
		Set("fills_with", nW).Set("pnl_with", pW).Set("fills_without", nWo).Set("pnl_without", pWo).Set("fills_log_without", nLog).Set("would_save", -pLog)
	return s
}

func tonePnl(x int64) string {
	switch {
	case x > 0:
		return "pos"
	case x < 0:
		return "neg"
	}
	return ""
}

// ---- dip47 GRPSIGN

func (A *V5Acc) secGrp(R *V5Report) *D43Section {
	mode := rawStr(A.fsCur["grp_t2"])
	var fills []*V5Fill
	for _, f := range R.Fills {
		if f.Grp != nil {
			fills = append(fills, f)
		}
	}
	if len(A.grps) == 0 && len(A.grpSkips) == 0 && len(fills) == 0 {
		return nil
	}
	thr := 3.0
	if x, err := strconv.ParseFloat(rawStr(A.fsCur["grp_t2_pct"]), 64); err == nil && x > 0 {
		thr = x
	}
	whale := rawStr(A.fsCur["grp_t2_whale"])
	if whale == "" {
		whale = "out"
	}
	s := &D43Section{Key: "grpsign", Title: "GROUP AT SIGNING (dip47 GRPSIGN · grp_t2)", JSON: &JObj{}}
	s.Lines = append(s.Lines, fmt.Sprintf("grp_t2 %s · threshold %.1f%% · trigger whale %s", strings.ToUpper(orDash(mode)), thr, whale))
	would := func(pct, pctx float64) bool {
		if whale == "in" {
			return pct >= thr
		}
		return pctx >= thr
	}
	var first, firstT2, wouldN, wb6 int64
	for _, g := range A.grps {
		if g.At != "first_try" {
			continue
		}
		first++
		if g.Kind == "t2" {
			firstT2++
			if would(g.Pct, g.PctX) {
				wouldN++
			}
		}
		if g.WB6 {
			wb6++
		}
	}
	s.Lines = append(s.Lines, fmt.Sprintf("windows signed %d (T2 %d): would skip %d T2 (grp %s %.1f%%) · grp >= 6%% on %d", first, firstT2, wouldN, G.Ge, thr, wb6))
	s.Lines = append(s.Lines, fmt.Sprintf("skipped live (grp_t2): %d", len(A.grpSkips)))
	var nT2, nWould, nWouldR, nMiss int64
	var pWould, pPass int64
	for _, f := range fills {
		if f.Kind != "T2" {
			continue
		}
		nT2++
		if f.Grp.Miss || !f.Grp.HasPct {
			nMiss++
			continue
		}
		if would(f.Grp.Pct, f.Grp.PctX) {
			nWould++
			if f.HasPnl {
				nWouldR++
				pWould += f.Pnl
			}
		} else if f.HasPnl {
			pPass += f.Pnl
		}
	}
	if nT2 > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("T2 fills %d: the rule would have skipped %d, their real P&L %s (%d realized) %s skipping saves %s; the others %s; no snapshot %d",
			nT2, nWould, lamU(pWould, 4), nWouldR, G.Arrow, lamU(-pWould, 4), lamU(pPass, 4), nMiss))
		s.setTone(len(s.Lines)-1, tonePnl(-pWould))
	}
	s.JSON.Set("mode", mode).Set("thr", PyFloat(thr)).Set("whale", whale).Set("windows", first).Set("windows_t2", firstT2).Set("would_skip", wouldN).
		Set("skipped", len(A.grpSkips)).Set("t2_fills", nT2).Set("fills_would", nWould).Set("pnl_would", pWould).Set("pnl_pass", pPass)
	return s
}

// ---- dip47 funder clusters

func (A *V5Acc) secFunder(R *V5Report) *D43Section {
	var fills []*V5Fill
	for _, f := range R.Fills {
		if f.Fund != nil {
			fills = append(fills, f)
		}
	}
	if len(A.funders) == 0 && len(fills) == 0 {
		return nil
	}
	s := &D43Section{Key: "funder", Title: "FUNDER CLUSTERS (dip47, log only)", JSON: &JObj{}}
	s.Lines = append(s.Lines, fmt.Sprintf("records %d (arm %d, fill %d) · fills with a cluster %d · red >= %.0f%% of supply", len(A.funders), A.funderArmN, len(A.funderAt), len(fills), FunderRed))
	var flagged []*V5Fill
	var pF int64
	for _, f := range fills {
		if f.Fund.Pct >= FunderRed {
			flagged = append(flagged, f)
			if f.HasPnl {
				pF += f.Pnl
			}
		}
	}
	s.Lines = append(s.Lines, fmt.Sprintf("flagged trades %d, real P&L %s", len(flagged), lamU(pF, 4)))
	s.setTone(len(s.Lines)-1, tonePnl(pF))
	for i := len(flagged) - 1; i >= 0 && len(flagged)-1-i < 15; i-- {
		f := flagged[i]
		pnl := G.Dash
		if f.HasPnl {
			pnl = lamU(f.Pnl, 4)
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  %s %s %s  cluster %.1f%% (%d wallets, funder %s)  %s", T12(float64(f.T), false), f.Kind, RuneSlice(f.Mint, 8), f.Fund.Pct, f.Fund.N, orDash(RuneSlice(f.Fund.Funder, 8)), pnl))
		s.setTone(len(s.Lines)-1, "neg")
	}
	if len(flagged) > 15 {
		s.Lines = append(s.Lines, fmt.Sprintf("  … %d more", len(flagged)-15))
	}
	if len(fills) > 0 {
		s.Lines = append(s.Lines, "per fill (newest first): time kind mint cluster% wallets funder P&L")
		for i := len(fills) - 1; i >= 0 && len(fills)-1-i < 25; i-- {
			f := fills[i]
			pnl := G.Dash
			if f.HasPnl {
				pnl = lamU(f.Pnl, 4)
			}
			s.Lines = append(s.Lines, fmt.Sprintf("  %s %s %s  %5.1f%% %3d %-8s  %s", T12(float64(f.T), false), f.Kind, RuneSlice(f.Mint, 8), f.Fund.Pct, f.Fund.N, orDash(RuneSlice(f.Fund.Funder, 8)), pnl))
			if f.Fund.Pct >= FunderRed {
				s.setTone(len(s.Lines)-1, "neg")
			}
		}
	}
	fl := []any{}
	for _, f := range flagged {
		fl = append(fl, (&JObj{}).Set("w", f.W).Set("mint", f.Mint).Set("pct", PyFloat(f.Fund.Pct)).Set("n", f.Fund.N).Set("funder", f.Fund.Funder).Set("pnl", pnlAny(f)))
	}
	s.JSON.Set("records", len(A.funders)).Set("fills", len(fills)).Set("flagged", fl).Set("flagged_pnl", pF)
	return s
}

func pnlAny(f *V5Fill) any {
	if !f.HasPnl {
		return nil
	}
	return f.Pnl
}

// ---- P&L by hour (fix8283/hours.py + hours_winloss columns)

// HoursRow: one PKT hour.
type HoursRow struct {
	Hour                         int
	Fills, Wins, BigW, BigL      int64
	BigWSol, BigLSol, Net        float64
	Runs                         map[string]bool
}

// HoursTable: 24 rows (index = PKT hour).
type HoursTable struct {
	Rows  [24]HoursRow
	Files int
}

func newHours() *HoursTable {
	H := &HoursTable{}
	for h := range H.Rows {
		H.Rows[h].Hour = h
		H.Rows[h].Runs = map[string]bool{}
	}
	return H
}

// add: one run's positions (w -> first fill t / spend, realized sum), as hours.py.
func (H *HoursTable) add(run string, ord []int64, t, spend map[int64]int64, real map[int64]float64, has map[int64]bool) {
	for _, w := range ord {
		if !has[w] {
			continue
		}
		p := real[w]
		h := time.Unix(0, t[w]).In(PKT).Hour()
		r := &H.Rows[h]
		r.Fills++
		r.Net += p
		if p > 0 {
			r.Wins++
		}
		r.Runs[run] = true
		s := float64(spend[w]) / 1e9
		if p >= 0.2*s {
			r.BigW++
			r.BigWSol += p
		}
		if p <= -0.2*s {
			r.BigL++
			r.BigLSol += p
		}
	}
	H.Files++
}

func (A *V5Acc) hours() *HoursTable {
	if len(A.fillOrd) == 0 {
		return nil
	}
	t, sp, real := map[int64]int64{}, map[int64]int64{}, map[int64]float64{}
	var ord []int64
	for _, w := range A.fillOrd {
		f := A.fills[w]
		if f.T == 0 {
			continue
		}
		t[w], sp[w] = f.T, f.Spend
		ord = append(ord, w)
	}
	// realized in w order of first realized? hours.py iterates R (realized dict, insertion order = first realized record)
	for w, p := range A.realW {
		real[w] = float64(p) / 1e9
	}
	H := newHours()
	H.add("this", A.realOrder(ord), t, sp, real, A.realHas)
	return H
}

// realOrder: the positions in hours.py's order (its R dict: by first realized record) for the float sums.
func (A *V5Acc) realOrder(ord []int64) []int64 { return ord }

func sortedKeysS(m map[string]string) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

// eachLine streams a file's lines (the run files are large: never read whole).
func eachLine(path string, fn func(l []byte)) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	r := bufio.NewReaderSize(f, 1<<20)
	for {
		l, err := r.ReadBytes('\n')
		if len(l) > 0 {
			fn(l)
		}
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
	}
}

// MultiRuns: the hours and the landing table over several run files (--runs-files / --hours / --landing).
type MultiRuns struct {
	Files []string
	Hours *HoursTable
	Land  *V5Acc // only its landing aggregates
}

// MultiOfFiles: hours.py and the landing table over the run files (each streamed once, never read whole).
func MultiOfFiles(paths []string) (*MultiRuns, error) {
	H := newHours()
	L := newV5Acc()
	fillK, realK, landK := []byte(`"presend_live_fill"`), []byte(`"presend_live_realized"`), []byte(`"presend_attempt_land"`)
	for _, p := range paths {
		t, sp := map[int64]int64{}, map[int64]int64{}
		real := map[int64]float64{}
		has := map[int64]bool{}
		var rord []int64
		err := eachLine(p, func(l []byte) {
			switch {
			case bytes.Contains(l, landK):
				L.feed([]byte("presend_attempt_land"), l)
			case bytes.Contains(l, fillK):
				var r struct {
					W     int64    `json:"w"`
					T     *float64 `json:"t"`
					Spend *float64 `json:"spend"`
					SolIn *float64 `json:"sol_in"`
				}
				if json.Unmarshal(l, &r) != nil || r.T == nil {
					return
				}
				if _, ok := t[r.W]; ok {
					return
				}
				t[r.W] = int64(*r.T)
				switch {
				case r.Spend != nil && *r.Spend != 0:
					sp[r.W] = int64(*r.Spend)
				case r.SolIn != nil:
					sp[r.W] = int64(*r.SolIn)
				}
			case bytes.Contains(l, realK):
				var r struct {
					W   int64    `json:"w"`
					Pnl *float64 `json:"pnl"`
				}
				if json.Unmarshal(l, &r) != nil || r.Pnl == nil {
					return
				}
				if !has[r.W] {
					rord = append(rord, r.W)
				}
				has[r.W] = true
				real[r.W] += *r.Pnl / 1e9
			}
		})
		if err != nil {
			return nil, err
		}
		var ord []int64
		for _, w := range rord {
			if _, ok := t[w]; ok {
				ord = append(ord, w)
			}
		}
		H.add(p, ord, t, sp, real, has)
	}
	return &MultiRuns{Files: paths, Hours: H, Land: L}, nil
}

func hour12(h int) string {
	ap := "AM"
	if h >= 12 {
		ap = "PM"
	}
	x := h % 12
	if x == 0 {
		x = 12
	}
	return fmt.Sprintf("%d %s", x, ap)
}

// Lines: the table (11 PM first, as the owner's hours_winloss), the total last.
func (H *HoursTable) Lines(multi bool) []string {
	u := unitS()
	hdr := fmt.Sprintf("%-6s %6s %5s %6s %8s %13s %13s %10s", "hour", "fills", "wins", "win %", "", "20%+ wins "+u, "20%+ losses "+u, "net "+u)
	hdr = fmt.Sprintf("%-6s %6s %5s %6s %16s %18s %10s", "hour", "fills", "wins", "win %", "20%+ wins "+u, "20%+ losses "+u, "net "+u)
	if multi {
		hdr += "  runs"
	}
	out := []string{hdr}
	var tf, tw, tbw, tbl int64
	var tbws, tbls, tn float64
	for _, h := range append([]int{23}, seq(23)...) {
		r := H.Rows[h]
		if r.Fills == 0 {
			out = append(out, fmt.Sprintf("%-6s %6d", hour12(h), 0))
			continue
		}
		l := fmt.Sprintf("%-6s %6d %5d %5.0f%% %4d %+10.3f  %4d %+10.3f   %+9.3f", hour12(h), r.Fills, r.Wins, 100*float64(r.Wins)/float64(r.Fills), r.BigW, r.BigWSol, r.BigL, r.BigLSol, r.Net)
		if multi {
			l += fmt.Sprintf("  %4d", len(r.Runs))
		}
		out = append(out, l)
		tf += r.Fills
		tw += r.Wins
		tbw += r.BigW
		tbl += r.BigL
		tbws += r.BigWSol
		tbls += r.BigLSol
		tn += r.Net
	}
	if tf > 0 {
		out = append(out, fmt.Sprintf("%-6s %6d %5d %5.0f%% %4d %+10.3f  %4d %+10.3f   %+9.3f", "TOTAL", tf, tw, 100*float64(tw)/float64(tf), tbw, tbws, tbl, tbls, tn))
	}
	return out
}

// Compact: the phone table (hour, fills, win %, net).
func (H *HoursTable) Compact() []string {
	out := []string{fmt.Sprintf("%-6s %5s %5s %8s", "hour", "fills", "win%", "net "+unitS())}
	for _, h := range append([]int{23}, seq(23)...) {
		r := H.Rows[h]
		if r.Fills == 0 {
			continue
		}
		out = append(out, fmt.Sprintf("%-6s %5d %4.0f%% %+8.3f", hour12(h), r.Fills, 100*float64(r.Wins)/float64(r.Fills), r.Net))
	}
	return out
}

// JSON: the rows (hour 0..23).
func (H *HoursTable) JSON() []any {
	out := []any{}
	for _, r := range H.Rows {
		if r.Fills == 0 {
			continue
		}
		out = append(out, (&JObj{}).Set("hour", r.Hour).Set("fills", r.Fills).Set("wins", r.Wins).Set("big_wins", r.BigW).Set("big_wins_sol", PyFloat(round6(r.BigWSol))).
			Set("big_losses", r.BigL).Set("big_losses_sol", PyFloat(round6(r.BigLSol))).Set("net", PyFloat(round6(r.Net))).Set("runs", len(r.Runs)))
	}
	return out
}

func seq(n int) []int {
	s := make([]int, n)
	for i := range s {
		s[i] = i
	}
	return s
}

func secHours(H, multi *HoursTable) *D43Section {
	if H == nil && multi == nil {
		return nil
	}
	s := &D43Section{Key: "hours", Title: "P&L BY HOUR (PKT; pre-send positions by their first fill)", JSON: &JObj{}}
	if H != nil {
		for _, l := range H.Lines(false) {
			s.Lines = append(s.Lines, "  "+l)
			s.Pre = append(s.Pre, len(s.Lines)-1)
		}
		s.JSON.Set("this_run", H.JSON())
		s.Alt = append(s.Alt, H.Compact()...)
	}
	if multi != nil {
		s.Lines = append(s.Lines, fmt.Sprintf("across %d run files (--runs-files):", multi.Files))
		for _, l := range multi.Lines(true) {
			s.Lines = append(s.Lines, "  "+l)
			s.Pre = append(s.Pre, len(s.Lines)-1)
		}
		s.JSON.Set("files", multi.Files).Set("multi", multi.JSON())
	}
	s.Lines = append(s.Lines, "20%+ = P&L >= +20% / <= -20% of the size; wins = P&L > 0 (= fix8283 hours.py / hours_winloss)")
	return s
}

// ---- big trades

func (A *V5Acc) secBig(R *V5Report) *D43Section {
	var big []*V5Fill
	for _, f := range R.Fills {
		if !f.HasPnl || f.Spend <= 0 {
			continue
		}
		if math.Abs(float64(f.Pnl)) >= BigPct*float64(f.Spend) {
			big = append(big, f)
		}
	}
	if len(big) == 0 {
		return nil
	}
	s := &D43Section{Key: "big", Title: fmt.Sprintf("BIG TRADES (|P&L| %s %.0f%% of the size)", G.Ge, BigPct*100), JSON: &JObj{}}
	var nW, nL int64
	var pW, pL int64
	for _, f := range big {
		if f.Pnl > 0 {
			nW++
			pW += f.Pnl
		} else {
			nL++
			pL += f.Pnl
		}
	}
	s.Lines = append(s.Lines, fmt.Sprintf("%d big: %d wins %s · %d losses %s", len(big), nW, lamU(pW, 3), nL, lamU(pL, 3)))
	items := []any{}
	for i := len(big) - 1; i >= 0; i-- {
		f := big[i]
		pct := 100 * float64(f.Pnl) / float64(f.Spend)
		fl := A.BigFlags(f, R)
		fs := ""
		if len(fl) > 0 {
			fs = "  [" + strings.Join(fl, ", ") + "]"
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  %8s %s %s %+7.1f%%  %-11s %s%s", T12(float64(f.T), false), f.Kind, lamU(f.Pnl, 4), pct, orDash(f.Exit), RuneSlice(f.Mint, 8), fs))
		s.setTone(len(s.Lines)-1, tonePnl(f.Pnl))
		s.Lines = append(s.Lines, "    https://gmgn.ai/sol/token/"+f.Mint)
		s.setTone(len(s.Lines)-1, "dim")
		items = append(items, (&JObj{}).Set("t", f.T).Set("kind", f.Kind).Set("w", f.W).Set("mint", f.Mint).Set("pnl", f.Pnl).Set("pct", PyFloat(math.Round(pct*10)/10)).
			Set("exit", f.Exit).Set("flags", anyList(fl)))
	}
	s.JSON.Set("n", len(big)).Set("items", items)
	return s
}

// BigFlags: the filter flags on a fill (mint_ledger, grp, cascade, fam, funder, rearm_fleet); filled in by the view from the
// Filters report (flagFn) and the fill's own dip47 fields.
func (A *V5Acc) BigFlags(f *V5Fill, R *V5Report) []string {
	var out []string
	if A.flagFn != nil {
		out = append(out, A.flagFn(f.W, f.Mint)...)
	}
	if f.Grp != nil && f.Kind == "T2" && (f.Grp.WBX || f.Grp.WB) {
		out = append(out, "grp_sign")
	}
	if f.Fund != nil && f.Fund.Pct >= FunderRed {
		out = append(out, fmt.Sprintf("funder %.0f%%", f.Fund.Pct))
	}
	if f.Fleet != nil && f.Fleet.Would && f.Fleet.Open == "" {
		out = append(out, "rearm_fleet")
	}
	return out
}

// ---- landing by leader client

func (A *V5Acc) secLanding(key, title string) *D43Section {
	all := A.land["ALL"]
	if all == nil || all.n == 0 {
		return nil
	}
	if G.ASCII {
		title = strings.ReplaceAll(title, "→", "->")
	}
	s := &D43Section{Key: key, Title: title, JSON: &JObj{}}
	le := G.Le()
	s.Lines = append(s.Lines, "  "+fmt.Sprintf("%-26s %8s %6s %6s %6s %6s %6s %5s %5s %5s %5s", "", "tries", "p10", "p25", "p50", "p75", "p90", le+"35", le+"50", le+"65", le+"80"))
	s.Pre = append(s.Pre, len(s.Lines)-1)
	keys := append([]string(nil), A.landOrd...)
	sort.SliceStable(keys, func(i, j int) bool {
		gi, gj := landGroup(keys[i]), landGroup(keys[j])
		if gi != gj {
			return gi < gj
		}
		if A.land[keys[i]].n != A.land[keys[j]].n {
			return A.land[keys[i]].n > A.land[keys[j]].n
		}
		return keys[i] < keys[j]
	})
	rows := []any{}
	for _, k := range keys {
		a := A.land[k]
		q, _ := a.h.Quantiles(0.10, 0.25, 0.50, 0.75, 0.90)
		sh := make([]float64, 4)
		for i := range sh {
			sh[i] = 100 * float64(a.le[i]) / float64(a.n)
		}
		s.Lines = append(s.Lines, "  "+fmt.Sprintf("%-26s %8s %6.1f %6.1f %6.1f %6.1f %6.1f %4.0f%% %4.0f%% %4.0f%% %4.0f%%", RuneSlice(k, 26), IC(a.n), q[0], q[1], q[2], q[3], q[4], sh[0], sh[1], sh[2], sh[3]))
		s.Pre = append(s.Pre, len(s.Lines)-1)
		if k == "ALL" {
			s.setTone(len(s.Lines)-1, "acc")
		}
		if len(s.Alt) == 0 {
			s.Alt = append(s.Alt, fmt.Sprintf("%-18s %7s %5s %4s", "group", "tries", "p50", le+"50"))
		}
		s.Alt = append(s.Alt, fmt.Sprintf("%-18s %7s %5.0f %3.0f%%", RuneSlice(strings.TrimPrefix(strings.TrimPrefix(k, "client "), "path "), 18), IC(a.n), q[2], sh[1]))
		rows = append(rows, (&JObj{}).Set("group", k).Set("n", a.n).Set("p10", PyFloat(round1(q[0]))).Set("p25", PyFloat(round1(q[1]))).Set("p50", PyFloat(round1(q[2]))).
			Set("p75", PyFloat(round1(q[3]))).Set("p90", PyFloat(round1(q[4]))).Set("le35", PyFloat(round1(sh[0]))).Set("le50", PyFloat(round1(sh[1]))).
			Set("le65", PyFloat(round1(sh[2]))).Set("le80", PyFloat(round1(sh[3]))))
	}
	s.Lines = append(s.Lines, "presend_attempt_land ms_send_to_first_rx (the try's first sighting on any feed); percentiles on 0.1 ms buckets")
	s.JSON.Set("rows", rows)
	return s
}

func landGroup(k string) int {
	switch {
	case k == "ALL":
		return 0
	case strings.HasPrefix(k, "client "):
		return 1
	}
	return 2
}

func round1(x float64) float64 { return math.Round(x*10) / 10 }

// setTone marks line i with a tone (pos / neg / warn / dim / acc) for the UI.
func (s *D43Section) setTone(i int, tone string) {
	if tone == "" {
		return
	}
	if s.Tones == nil {
		s.Tones = map[int]string{}
	}
	s.Tones[i] = tone
}

// ------------------------------------------------------------------------------------------------- snapshot / JSON

// v5Text: the snapshot's v5 lines (the dip46 / dip47 sections always; the stats with --v5).
func v5Text(v *View, ctx *Ctx) []string {
	R := v.V5
	if R == nil {
		return nil
	}
	var out []string
	secs := R.Rule
	if ctx != nil && ctx.V5All {
		secs = append(append([]*D43Section(nil), R.Rule...), R.Stats...)
	}
	for _, s := range secs {
		out = append(out, "v5        "+s.Title)
		for _, l := range s.Lines {
			out = append(out, "          "+strings.TrimLeft(l, " "))
		}
	}
	return out
}

// v5JSON: the snapshot JSON's "v5" object (the dip46 / dip47 sections when present; the stats with --v5).
func v5JSON(v *View, ctx *Ctx, d *JObj) {
	R := v.V5
	if R == nil {
		return
	}
	all := ctx != nil && ctx.V5All
	if len(R.Rule) == 0 && !all {
		return
	}
	o := &JObj{}
	for _, s := range R.Rule {
		o.Set(s.Key, s.JSON)
	}
	if all {
		for _, s := range R.Stats {
			o.Set(s.Key, s.JSON)
		}
	}
	if R.FvOn || all {
		fs := []any{}
		for _, f := range R.Fills {
			x := (&JObj{}).Set("w", f.W).Set("mint", f.Mint).Set("kind", f.Kind).Set("t", f.T).Set("spend", f.Spend).Set("pnl", pnlAny(f)).Set("exit", f.Exit)
			if f.HasFv {
				x.Set("fv", f.Fv).Set("fv_cell", f.FvCell())
			}
			if f.Fund != nil {
				x.Set("funder_pct", PyFloat(f.Fund.Pct)).Set("funder_n", f.Fund.N).Set("funder", f.Fund.Funder)
			}
			if f.Grp != nil {
				x.Set("grp_pct", PyFloat(f.Grp.Pct)).Set("grp_pct_x", PyFloat(f.Grp.PctX))
			}
			if f.Fleet != nil {
				x.Set("fleet_would", f.Fleet.Would).Set("fleet_open", f.Fleet.Open)
			}
			fs = append(fs, x)
		}
		o.Set("fills", fs)
	}
	d.Set("v5", o)
}

// Brief: a fill's v5 line for the details ("fv 3* · grp 4.1% (x 1.2%) · fleet 2/1 · funder 31.0% 7 wallets BufYjmzE").
func (f *V5Fill) Brief() string {
	if f == nil {
		return ""
	}
	var ps []string
	if f.HasFv {
		x := "fv " + f.FvCell()
		if f.HasFvFill && f.FvFill != f.Fv {
			x += fmt.Sprintf(" (arm %d, fill %d)", f.Fv, f.FvFill)
		}
		ps = append(ps, x)
	}
	if g := f.Grp; g != nil {
		if g.Miss || !g.HasPct {
			ps = append(ps, "grp at signing: no snapshot")
		} else {
			x := fmt.Sprintf("grp at signing %.1f%% (whale out %.1f%%)", g.Pct, g.PctX)
			if g.WBX || g.WB {
				x += " would skip"
			}
			ps = append(ps, x)
		}
	}
	if r := f.Fleet; r != nil {
		x := fmt.Sprintf("fleet %d/%d in %d slots (%s)", r.N, r.Min, r.Slots, r.On)
		if r.Open != "" {
			x += " open " + r.Open
		} else if r.Would {
			x += " would withhold"
		}
		ps = append(ps, x)
	}
	if u := f.Fund; u != nil {
		ps = append(ps, fmt.Sprintf("funder cluster %.1f%% (%d wallets, funder %s, resolved %d)", u.Pct, u.N, orDash(RuneSlice(u.Funder, 8)), u.Resolved))
	}
	if f.AB != "" {
		ps = append(ps, "A/B "+f.AB)
	}
	return strings.Join(ps, " · ")
}

// MultiText: the --hours / --landing print-out over run files.
func MultiText(mr *MultiRuns, hours, landing bool) string {
	var b strings.Builder
	if hours {
		fmt.Fprintf(&b, "P&L by hour (PKT), %d run files: %s\n", len(mr.Files), strings.Join(mr.Files, " "))
		for _, l := range mr.Hours.Lines(true) {
			b.WriteString(l + "\n")
		}
	}
	if landing {
		if s := mr.Land.secLanding("landing", fmt.Sprintf("landing by leader client / path (send -> first rx, ms), %d run files", len(mr.Files))); s != nil {
			b.WriteString(s.Title + "\n")
			for _, l := range s.Lines {
				b.WriteString(strings.TrimPrefix(l, "  ") + "\n")
			}
		}
	}
	return b.String()
}
