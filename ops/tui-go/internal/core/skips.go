package core

// skips.go (v5.1, 11-12, owner: "a page inside Trades, off by default, called Skips: like the trade table but for every token
// skipped, next to which filter blocked it (live), paper values, everything"). One row per presend_live_skip record (every why,
// including the ones the Filters table does not list) plus every window the per-try gates withheld that never filled (the
// Filters report's LIVE items with a window). Paper = the trigger's shadow window (row c) at the live size, calibrated when a
// calibration table is loaded; a re-arm skip has no shadow window ("-").

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

// SkipRow is one skipped trigger / withheld window.
type SkipRow struct {
	T        int64  // ns (0 = unknown)
	Kind     string // "T2" | "RA"
	Mint     string
	Why      string // the engine's why (or the Filters key of a withheld window)
	Name     string // a readable filter name
	Cat      string // "filter" | "busy" (another window / position / ATA in the way) | "not a setup" (no holder, too old, ...)
	Detail   string // the record's numbers: trigger / dump, the ledger or wallet that blocked it
	Withheld bool   // a window that armed but every try was withheld (rival gate, bot depth, FP-NOBOT, fleet, blocklist per-send)
	HasPaper bool
	Paper    float64 // the shadow window's P&L at the live size (SOL)
	HasCal   bool
	Cal      float64 // calibrated (expected live) P&L
	Move     *FMove  // the shadow window's price move
	// dip46 probes on this skipped window (real on-chain tries with an impossible min-out): how many landed and how many of them
	// would have filled at our limit. ProbeN > 0 && ProbeWould == 0: the trade would not have happened (nothing saved or lost).
	ProbeN, ProbeWould int
	// the first would-fill probe priced on the later probes' own curve samples (TP / SL 20%, else the 5-slot exit, else the
	// window's last sample): an approximation, shown only when there is no shadow paper
	HasProbePnl bool
	ProbePnl    float64
	Shadow      bool // the trigger has a shadow window (a T2 skip): no shadow fill = the price never reached our limit ("no dip")
}

type skipRec struct {
	t                    int64
	kind, why, mint, sig string
	detail               string
}

// SkipAcc keeps every presend_live_skip record (the Filters accumulator keeps only the ones its table scores).
type SkipAcc struct {
	recs []skipRec
	ver  int64
}

func newSkipAcc() *SkipAcc { return &SkipAcc{} }

type skPart struct {
	Wallet string          `json:"wallet"`
	Seller string          `json:"seller"`
	Mint   string          `json:"mint"`
	Sig    string          `json:"sig"`
	T      json.RawMessage `json:"t"`
	Pct    *float64        `json:"pct"`
	Sol    *float64        `json:"sol"`
	Drop   *float64        `json:"drop_pct"`
	AgeSl  *int64          `json:"age_slots"`
}

type skRaw struct {
	Why     *string `json:"why"`
	Kind    *string `json:"kind"`
	Mint    string  `json:"mint"`
	Trig    *skPart `json:"trig"`
	Dump    *skPart `json:"dump"`
	Holders []struct {
		W   string  `json:"w"`
		Pct float64 `json:"pct"`
	} `json:"holders"`
	HlWallet *string  `json:"hl_wallet"`
	HlN      *int64   `json:"hl_n"`
	HlSum    *float64 `json:"hl_sum"`
	HlPct    *float64 `json:"hl_pct"`
	WhWallet *string  `json:"wh_wallet"`
	WhN      *int64   `json:"wh_n"`
	WhSum    *float64 `json:"wh_sum"`
	BlWallet *string  `json:"bl_wallet"`
	BlRole   *string  `json:"bl_role"`
	BlPct    *float64 `json:"bl_pct"`
	Fresh    *float64 `json:"fresh"`
	FreshN   *int64   `json:"fresh_n"`
	ML       *struct {
		N     int64   `json:"n"`
		Worst float64 `json:"worst"`
		Would bool    `json:"would_block"`
	} `json:"mint_ledger"`
	Cr *struct {
		N     int64   `json:"n"`
		Sum   float64 `json:"sum"`
		Would string  `json:"would"`
	} `json:"cr"`
	Deferred *string         `json:"deferred"`
	T        json.RawMessage `json:"t"`
}

func (S *SkipAcc) feed(ev, line []byte) {
	if string(ev) != "presend_live_skip" {
		return
	}
	var r skRaw
	if json.Unmarshal(line, &r) != nil || r.Why == nil {
		return
	}
	rec := skipRec{why: *r.Why, mint: r.Mint, kind: "T2"}
	if r.Kind != nil && *r.Kind == "rearm" {
		rec.kind = "RA"
	}
	var d []string
	if r.Trig != nil {
		if rec.mint == "" {
			rec.mint = r.Trig.Mint
		}
		rec.sig, rec.t = r.Trig.Sig, rawInt(r.Trig.T)
		s := "whale " + shortW(r.Trig.Wallet)
		if r.Trig.Pct != nil {
			s += fmt.Sprintf(" %.1f%%", *r.Trig.Pct)
		}
		if r.Trig.Sol != nil {
			s += fmt.Sprintf(" (%.2f◎)", *r.Trig.Sol/1e9)
		}
		if r.Trig.AgeSl != nil {
			s += fmt.Sprintf(" age %d", *r.Trig.AgeSl)
		}
		d = append(d, s)
	}
	if r.Dump != nil {
		if rec.mint == "" {
			rec.mint = r.Dump.Mint
		}
		if rec.t == 0 {
			rec.t = rawInt(r.Dump.T)
		}
		s := "dump " + shortW(r.Dump.Seller)
		if r.Dump.Pct != nil {
			s += fmt.Sprintf(" %.1f%%", *r.Dump.Pct)
		}
		if r.Dump.Sol != nil {
			s += fmt.Sprintf(" (%.2f◎)", *r.Dump.Sol/1e9)
		}
		if r.Dump.Drop != nil {
			s += fmt.Sprintf(" -%.0f%%", *r.Dump.Drop)
		}
		if r.Dump.AgeSl != nil {
			s += fmt.Sprintf(" age %d", *r.Dump.AgeSl)
		}
		d = append(d, s)
	}
	if rec.t == 0 {
		rec.t = rawInt(r.T)
	}
	if len(r.Holders) > 0 {
		hs := make([]string, 0, 3)
		for i, h := range r.Holders {
			if i == 3 {
				hs = append(hs, fmt.Sprintf("+%d", len(r.Holders)-3))
				break
			}
			hs = append(hs, fmt.Sprintf("%s %.1f%%", shortW(h.W), h.Pct))
		}
		d = append(d, "holders "+strings.Join(hs, ", "))
	}
	if r.HlWallet != nil && *r.HlWallet != "" {
		s := "holder " + shortW(*r.HlWallet)
		if r.HlPct != nil {
			s += fmt.Sprintf(" %.1f%%", *r.HlPct)
		}
		if r.HlN != nil {
			s += fmt.Sprintf(": %d with us", *r.HlN)
		}
		if r.HlSum != nil {
			s += fmt.Sprintf(" %+.3f◎", *r.HlSum)
		}
		d = append(d, s)
	}
	if r.WhWallet != nil && r.WhN != nil && *r.WhN > 0 && (rec.why == "wh_loss" || rec.why == "rearm_wh_loss") {
		s := fmt.Sprintf("whale ledger %s: %d with us", shortW(*r.WhWallet), *r.WhN)
		if r.WhSum != nil {
			s += fmt.Sprintf(" %+.3f◎", *r.WhSum)
		}
		d = append(d, s)
	}
	if r.BlWallet != nil && *r.BlWallet != "" {
		s := "blocklisted " + shortW(*r.BlWallet)
		if r.BlRole != nil && *r.BlRole != "" {
			s += " (" + *r.BlRole
			if r.BlPct != nil && *r.BlPct > 0 {
				s += fmt.Sprintf(" %.1f%%", *r.BlPct)
			}
			s += ")"
		}
		d = append(d, s)
	}
	if r.Fresh != nil && rec.why == "fresh_holders" {
		s := fmt.Sprintf("fresh holders %.0f%%", *r.Fresh)
		if r.FreshN != nil {
			s += fmt.Sprintf(" (%d)", *r.FreshN)
		}
		d = append(d, s)
	}
	if r.ML != nil && (r.ML.Would || rec.why == "mint_ledger") {
		d = append(d, fmt.Sprintf("mint ledger %d, worst %+.3f◎", r.ML.N, r.ML.Worst/1e9))
	}
	if r.Cr != nil && (r.Cr.Would != "" || rec.why == "cr_loss") {
		d = append(d, fmt.Sprintf("creator %d with us %+.3f◎", r.Cr.N, r.Cr.Sum))
	}
	if r.Deferred != nil && *r.Deferred != "" {
		d = append(d, "deferred "+*r.Deferred)
	}
	rec.detail = strings.Join(d, " · ")
	S.recs = append(S.recs, rec)
	S.ver++
}

// skipNames: readable names for the engine's whys (the Filters table's names where it has one).
var skipNames = map[string]string{
	"quiet": "QUIET", "create_slot": "create-slot", "young_age": "age-1", "lone_whale": "10-sec (lone whale)",
	"breaker": "circuit breaker", "cr_loss": "creator loss", "cr_unfollowed": "creator unfollowed", "quiet3_a": "QUIET3-A",
	"blocklist": "blocklist", "rearm_blocklist": "blocklist", "wh_loss": "whale loss", "rearm_wh_loss": "whale loss",
	"holder_loss": "holder loss", "rearm_holder_loss": "holder loss", "m2_unseen": "M2 unseen", "rearm_m2_unseen": "M2 unseen",
	"mint_ledger": "mint ledger", "fanout_live": "fan-out", "grp_t2": "group at signing", "rearm_cap": "re-arm cap",
	"fresh_holders": "fresh holders", "rearm_fresh_holders": "fresh holders", "rearm_r5": "re-arm R5", "pause_window": "pause window",
	"rearm_age": "re-arm: token too old", "rearm_no_holder": "re-arm: no 6% holder left", "no_launch_accounts": "no launch accounts",
	"blocked_armed": "busy: window armed", "blocked_position": "busy: position open", "blocked_ata_open": "busy: ATA open",
	"rearm_blocked_live_armed": "busy: window armed", "rearm_blocked_rearm_armed": "busy: re-arm armed",
	"rearm_blocked_position": "busy: position open", "rearm_blocked_ata_open": "busy: ATA open",
	// the per-try gates' windows (Filters keys)
	"rgate_live": "rival gate", "botdepth_live": "bot depth", "fpnb_live": "FP-NOBOT", "rfleet_live": "re-arm fleet",
	"skip2_live": "SKIP-2", "deeper": "deeper limit",
}

func skipCat(why string) string {
	switch {
	case strings.HasPrefix(why, "blocked_"), strings.HasPrefix(why, "rearm_blocked_"):
		return "busy"
	case why == "rearm_age", why == "rearm_no_holder", why == "no_launch_accounts":
		return "not a setup"
	}
	return "filter"
}

// SkipWhyName: the readable name of a why.
func SkipWhyName(why string) string {
	if n, ok := skipNames[why]; ok {
		return n
	}
	return strings.ReplaceAll(why, "_", " ")
}

// withheldKeys: the Filters report's LIVE items that are windows the per-try gates withheld (never filled).
var withheldKeys = map[string]bool{"rgate_live": true, "botdepth_live": true, "fpnb_live": true, "rfleet_live": true, "skip2_live": true}

// Rows: every skip, newest first. F supplies the shadow paper, R the withheld windows and the calibration.
func (S *SkipAcc) Rows(F *FiltAcc, R *FiltReport, P *V5Acc) []SkipRow {
	out := make([]SkipRow, 0, len(S.recs)+16)
	var cal *Calib
	size := 0.0
	if R != nil {
		cal, size = R.Calib, R.LiveSize
	}
	for _, r := range S.recs {
		row := SkipRow{T: r.t, Kind: r.kind, Mint: r.mint, Why: r.why, Name: SkipWhyName(r.why), Cat: skipCat(r.why), Detail: r.detail}
		if F != nil && r.kind == "T2" && r.sig != "" {
			if w, ok := F.shW[r.sig]; ok {
				row.Shadow = true
				if v, vok := F.paper(w, true); vok {
					row.HasPaper, row.Paper = true, v
					if c, cok := cal.Apply(v, "T2", size); cok {
						row.HasCal, row.Cal = true, c
					}
				}
				row.Move = F.moves[w]
			}
		}
		out = append(out, row)
	}
	if R != nil {
		for _, it := range R.Items {
			if !it.Live || it.W == noW || !(withheldKeys[it.Filter] || (it.Filter == "blocklist" && it.W != noW)) {
				continue
			}
			why := it.Filter
			row := SkipRow{T: it.T, Kind: it.Kind, Mint: it.Mint, Why: why, Name: SkipWhyName(why), Cat: "filter", Withheld: true,
				Detail: fmt.Sprintf("window w%d armed; every try withheld, never filled", it.W), HasPaper: it.Scored, Paper: it.Sol,
				HasCal: it.Cal, Cal: it.CalSol, Move: it.Move, Shadow: it.Move != nil || it.Scored}
			if why == "blocklist" {
				row.Name = "blocklist (per send)"
			}
			out = append(out, row)
		}
	}
	if P != nil && len(P.lands) > 0 { // the probes of each skipped window: same mint, the skip's filter, landed within the window's time
		by := map[string][]*v5Land{}
		for _, l := range P.lands {
			if l.res != "unseen" {
				by[l.mint] = append(by[l.mint], l)
			}
		}
		// each probe landing belongs to ONE row: the latest skip of that mint + filter at or before it (2 s slack), within 20 s
		got := map[int][]*v5Land{}
		rowsOf := map[string][]int{}
		for i := range out {
			rowsOf[out[i].Mint] = append(rowsOf[out[i].Mint], i)
		}
		for mint, ls := range by {
			for _, l := range ls {
				best := -1
				for _, i := range rowsOf[mint] {
					r := &out[i]
					if l.t < r.T-int64(2e9) || l.t > r.T+int64(20e9) {
						continue
					}
					pf := probeFilter(r.Why)
					if !(l.filter == pf || strings.HasPrefix(l.filter, pf)) {
						continue
					}
					if best < 0 || r.T > out[best].T {
						best = i
					}
				}
				if best >= 0 {
					got[best] = append(got[best], l)
				}
			}
		}
		for i, ws := range got {
			r := &out[i]
			r.ProbeN = len(ws)
			for _, l := range ws {
				if l.wouldFill {
					r.ProbeWould++
				}
			}
			if r.ProbeWould > 0 {
				r.ProbePnl, r.HasProbePnl = probePnl(ws)
			}
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].T > out[j].T })
	return out
}

// probeFilter: the probe records' filter name of a skip's why (arm-time skips: the why itself, re-arm prefix off; the per-try
// gates' windows: "<gate>_withheld").
func probeFilter(why string) string {
	switch why {
	case "rgate_live":
		return "rival_gate_withheld"
	case "botdepth_live":
		return "botdepth_withheld"
	case "fpnb_live":
		return "fpnb_withheld"
	case "rfleet_live":
		return "rearm_fleet_withheld"
	case "skip2_live":
		return "skip2_withheld"
	}
	return strings.TrimPrefix(why, "rearm_")
}

// SkipsTotals: for a set of rows, how many had a paper value, its wins / losses and the paper / calibrated sums.
type SkipsTotals struct {
	N, Scored, WinN, LoseN int
	NoFill                 int // no dip: the shadow window never filled, or probes landed and none would have filled
	ProbeN                 int // skips priced from their probes (no shadow paper)
	Probe                  float64
	Paper, Cal             float64
	CalN                   int
}

func SumSkips(rows []SkipRow) SkipsTotals {
	var t SkipsTotals
	for _, r := range rows {
		t.N++
		if r.HasPaper {
			t.Scored++
			t.Paper += r.Paper
			if r.Paper > 0 {
				t.WinN++
			} else {
				t.LoseN++
			}
		}
		if r.NoDip() {
			t.NoFill++
		}
		if !r.HasPaper && r.HasProbePnl {
			t.ProbeN++
			t.Probe += r.ProbePnl
		}
		if r.HasCal {
			t.CalN++
			t.Cal += r.Cal
		}
	}
	return t
}

// probePnl prices a window's first would-fill probe on the curve states the window's later probes saw (each landing's "pre"
// reserves): sell at the first sample worth >= 1.2x or <= 0.8x the spend, else at the first sample 5+ slots after the fill, else
// at the last sample. Costs: the probe's fee and the usual sell cost. false = no later sample.
func probePnl(ws []*v5Land) (float64, bool) {
	sort.SliceStable(ws, func(a, b int) bool {
		if ws[a].slot != ws[b].slot {
			return ws[a].slot < ws[b].slot
		}
		return ws[a].idx < ws[b].idx
	})
	var f *v5Land
	for _, l := range ws {
		if l.wouldFill && l.wouldTok > 0 && l.spend > 0 {
			f = l
			break
		}
	}
	if f == nil {
		return 0, false
	}
	out, ok := 0.0, false
	for _, l := range ws {
		if !l.hasPre || l.preVtok <= 0 || l.slot < f.slot || l == f || (l.slot == f.slot && l.idx <= f.idx) {
			continue
		}
		v := pcProceeds(l.preVtok, f.wouldTok)
		out, ok = v, true
		if v >= 1.2*f.spend || v <= 0.8*f.spend || l.slot >= f.slot+5 {
			break
		}
	}
	if !ok {
		return 0, false
	}
	return (out - f.spend - f.fee - pcSellFx) / 1e9, true
}

// NoDip: no shadow paper and the evidence says the price never reached our limit: real probes landed and none would have filled,
// or (no probe would have filled and) the trigger's shadow window never filled.
func (r SkipRow) NoDip() bool {
	return !r.HasPaper && r.ProbeWould == 0 && (r.ProbeN > 0 || r.Shadow)
}
