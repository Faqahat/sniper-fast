package core

import (
	"bytes"
	"encoding/json"
	"fmt"
	"slices"
	"strconv"
)

// ADDED WINDOWS (dip41 / dip42, log only; dipmon 3.3, recovered in v4): what the windows the engine only logged would have
// made. The wide dumper and QF2 (a whale's first 3..6% crossing) scored on the wide shadow's row c at the logged size; QF2's
// flag on the real T2 positions; Q1 (fresh-wallet buys, paper at its +4 / +9 slot horizons); the 2NUM family (fam2) present
// or absent on the real positions. Net = what they made (not "saved": nothing was blocked).

type addWin struct {
	sig  string
	size float64 // SOL
}

// AddAcc gathers the records of the added windows.
type AddAcc struct {
	ver int64
	// dip41 config (presend_live_widedumper_config) and the control file's modes
	cfg              bool
	wdN, q2N         float64
	wdScore, q2Score float64
	wdMode, q2Mode   string
	size             float64
	wd, q2           []addWin           // would-arm records
	wsig             map[string]int64   // wide shadow: sig -> w
	wexit            map[int64]*float64 // wide shadow w -> row c net_cheap
	wsize            map[int64]float64  // wide shadow w -> row c sol_in (SOL)
	q2Flag           map[FKey]bool      // T2 arm flagged by QF2 (pass && filt)
	q2Arms           int                // flagged T2 arms
	t2               map[FKey]bool      // T2 arms
	real             map[FKey]float64   // realized P&L (SOL)
	realOrd          []FKey
	fam2Pre          map[FKey]bool // realized position with the 2NUM family on the token before the dump
	fam2Cfg          bool
	fam2Slots        float64
	fam2Mode         string
	q1Cfg            bool
	q1Size           float64
	q1Hz             []int
	q1Trig, q1Warm   int
	q1Out            map[int]map[int64]float64 // horizon -> trigger id -> paper net (SOL); only outcomes with a paper
	q1Ids            map[int]map[int64]bool    // horizon -> ids with an outcome
}

func newAddAcc() *AddAcc {
	return &AddAcc{wsig: map[string]int64{}, wexit: map[int64]*float64{}, wsize: map[int64]float64{}, q2Flag: map[FKey]bool{},
		t2: map[FKey]bool{}, real: map[FKey]float64{}, fam2Pre: map[FKey]bool{}, q1Out: map[int]map[int64]float64{},
		q1Ids: map[int]map[int64]bool{}}
}

var addEvs = map[string]bool{"presend_live_widedumper_config": true, "presend_live_widedumper": true, "presend_live_qf2": true,
	"presend_wide_arm": true, "presend_wide_fill": true, "presend_wide_exit": true, "presend_live_arm": true, "presend_live_realized": true,
	"presend_live_fam2_config": true, "q1_config": true, "q1_trigger": true, "q1_outcome": true, "presend_live_ledger_mode": true}

var wouldArmTrue = []byte(`"would_arm":true`)

func (A *AddAcc) feed(ev, line []byte) {
	e := string(ev)
	if !addEvs[e] {
		return
	}
	if (e == "presend_live_widedumper" || e == "presend_live_qf2") && !bytes.Contains(line, wouldArmTrue) {
		return
	}
	var r struct {
		W     *int64          `json:"w"`
		Mint  string          `json:"mint"`
		Sig   string          `json:"sig"`
		Row   *string         `json:"row"`
		Kind  *string         `json:"kind"`
		Mode  *string         `json:"mode"`
		N     *float64        `json:"n"`
		Score *float64        `json:"score"`
		Size  *float64        `json:"size"`
		Slots *float64        `json:"slots"`
		Net   json.RawMessage `json:"net_cheap"`
		Pnl   json.RawMessage `json:"pnl"`
		Entry *struct {
			SolIn *float64 `json:"sol_in"`
		} `json:"entry"`
		Qf2 *struct {
			Mode  *string  `json:"mode"`
			N     *float64 `json:"n"`
			Score *float64 `json:"score"`
			Pass  *bool    `json:"pass"`
			Filt  *bool    `json:"filt"`
		} `json:"qf2"`
		Trig *struct {
			Mint string `json:"mint"`
		} `json:"trig"`
		Fam2 *struct {
			Pre *float64 `json:"pre"`
		} `json:"fam2"`
		Ok       *bool   `json:"ok"`
		WdMode   *string `json:"widedumper"`
		Horizons []int   `json:"horizons"`
		Warm     *bool   `json:"warm"`
		ID       *int64  `json:"id"`
		H        *int    `json:"h"`
		Paper    *struct {
			Net *float64 `json:"net"`
		} `json:"paper"`
	}
	if err := json.Unmarshal(line, &r); err != nil {
		return
	}
	A.ver++
	w := noW
	if r.W != nil {
		w = *r.W
	}
	switch e {
	case "presend_live_widedumper_config":
		A.cfg = true
		A.wdN, A.wdScore, A.size = fz(r.N), fz(r.Score), fz(r.Size)/1e9
		if r.Mode != nil {
			A.wdMode = *r.Mode
		}
		if q := r.Qf2; q != nil {
			A.q2N, A.q2Score = fz(q.N), fz(q.Score)
			if q.Mode != nil {
				A.q2Mode = *q.Mode
			}
		}
	case "presend_live_ledger_mode": // the control file's modes (a good read)
		if r.Ok != nil && *r.Ok {
			if r.WdMode != nil {
				A.wdMode = *r.WdMode
			}
		}
		var q struct {
			Q2 *string `json:"qf2"`
		}
		if r.Ok != nil && *r.Ok && json.Unmarshal(line, &q) == nil && q.Q2 != nil {
			A.q2Mode = *q.Q2
		}
	case "presend_live_widedumper":
		A.wd = append(A.wd, addWin{r.Sig, fz(r.Size) / 1e9})
	case "presend_live_qf2":
		A.q2 = append(A.q2, addWin{r.Sig, fz(r.Size) / 1e9})
	case "presend_wide_arm":
		A.wsig[r.Sig] = w
	case "presend_wide_fill":
		if (r.Row == nil || *r.Row == "c") && r.Entry != nil {
			if _, ok := A.wsize[w]; !ok {
				A.wsize[w] = fz(r.Entry.SolIn) / 1e9
			}
		}
	case "presend_wide_exit":
		if r.Row != nil && *r.Row == "c" {
			if x, ok := rawFloat(r.Net); ok {
				A.wexit[w] = &x
			} else if x, ok := rawFloat(r.Pnl); ok {
				A.wexit[w] = &x
			}
		}
	case "presend_live_arm":
		if r.Kind != nil && *r.Kind != "t2" {
			return
		}
		mint := r.Mint
		if mint == "" && r.Trig != nil {
			mint = r.Trig.Mint
		}
		k := FKey{w, mint}
		A.t2[k] = true
		if q := r.Qf2; q != nil && q.Pass != nil && *q.Pass && q.Filt != nil && *q.Filt {
			A.q2Arms++
			A.q2Flag[k] = true
		}
	case "presend_live_realized":
		k := FKey{w, r.Mint}
		p, _ := rawFloat(r.Pnl)
		if _, ok := A.real[k]; !ok {
			A.realOrd = append(A.realOrd, k)
		}
		A.real[k] = p / 1e9
		A.fam2Pre[k] = r.Fam2 != nil && fz(r.Fam2.Pre) > 0
	case "presend_live_fam2_config":
		A.fam2Cfg, A.fam2Slots = true, fz(r.Slots)
		if r.Mode != nil {
			A.fam2Mode = *r.Mode
		}
	case "q1_config":
		A.q1Cfg, A.q1Size, A.q1Hz = true, fz(r.Size)/1e9, r.Horizons
	case "q1_trigger":
		A.q1Trig++
		if r.Warm != nil && *r.Warm {
			A.q1Warm++
		}
	case "q1_outcome":
		if r.H == nil || r.ID == nil {
			return
		}
		h := *r.H
		if A.q1Ids[h] == nil {
			A.q1Ids[h] = map[int64]bool{}
			A.q1Out[h] = map[int64]float64{}
		}
		A.q1Ids[h][*r.ID] = true
		if r.Paper != nil && r.Paper.Net != nil {
			A.q1Out[h][*r.ID] = *r.Paper.Net / 1e9
		}
	}
}

// addLine: one row in the filters table's text format ("net" = what they made).
func addLine(name, typ string, n, wn int, ws float64, ln int, ls float64, note string) string {
	return fmt.Sprintf("%-26s %-4s %7d | %4d %10s | %4d %10s | %9s   (%s)", name, typ, n, wn, fmtSigned(ws, 3), ln, fmtSigned(ls, 3), fmtSigned(ws+ls, 3), note)
}

func fmtG(x float64) string { return strconv.FormatFloat(x, 'g', -1, 64) }

// Lines: the ADDED WINDOWS section's lines (nil when the run has none of them).
func (A *AddAcc) Lines() []string {
	var out []string
	if A.cfg {
		out = append(out, fmt.Sprintf("ADDED WINDOWS (dip41; net = what they made): wide dumper %s %s:%s | qf2 %s %s:%s", A.wdMode, fmtG(A.wdN), fmtG(A.wdScore),
			A.q2Mode, fmtG(A.q2N), fmtG(A.q2Score)))
		score := func(name string, ws []addWin) string {
			var wn, ln, sc, nowin int
			var wsum, lsum float64
			for _, x := range ws {
				w, ok := A.wsig[x.sig]
				if !ok {
					nowin++
					continue
				}
				p := A.wexit[w]
				if p == nil {
					continue
				}
				v := *p
				if s := A.wsize[w]; s != 0 {
					v = v * x.size / s
				}
				sc++
				if v > 0 {
					wn++
					wsum += v
				} else {
					ln++
					lsum += v
				}
			}
			return addLine(name, "LOG", len(ws), wn, wsum, ln, lsum, fmt.Sprintf("paper (the wide shadow's row c at %.3f SOL); would-arm %d, scored %d, no wide shadow window %d",
				A.size, len(ws), sc, nowin))
		}
		out = append(out, score("wide dumper (log)", A.wd), score("qf2 (log)", A.q2))
		var wn, ln, un int
		var wsum, lsum, usum float64
		for _, k := range A.realOrd {
			if !A.t2[k] {
				continue
			}
			v := A.real[k]
			if !A.q2Flag[k] {
				un++
				usum += v
				continue
			}
			if v > 0 {
				wn++
				wsum += v
			} else {
				ln++
				lsum += v
			}
		}
		out = append(out, addLine("qf2 on T2 (log)", "LOG", A.q2Arms, wn, wsum, ln, lsum, fmt.Sprintf("real T2 positions; flagged arms %d, realized %d; unflagged realized %d %s",
			A.q2Arms, wn+ln, un, fmtSigned(usum, 3))))
	}
	if A.q1Cfg {
		hz := A.q1Hz
		if len(hz) > 2 {
			hz = hz[len(hz)-2:]
		}
		s := fmt.Sprintf("%-26s %-4s %7d", "Q1 (log)", "LOG", A.q1Trig)
		for _, h := range hz {
			var wn, ln int
			var sum float64
			for _, v := range A.q1Out[h] {
				if v > 0 {
					wn++
				} else {
					ln++
				}
			}
			sum = sumSorted(A.q1Out[h])
			s += fmt.Sprintf(" | +%d: %3dW/%3dL %9s", h, wn, ln, fmtSigned(sum, 3))
		}
		last := 0
		if len(hz) > 0 {
			last = len(A.q1Ids[hz[len(hz)-1]])
		}
		s += fmt.Sprintf("   (paper %.2f SOL, nothing sent; triggers in the warm-up %d; outcomes %d / %d)", A.q1Size, A.q1Warm, last, A.q1Trig)
		out = append(out, s)
	}
	if A.fam2Cfg {
		var pn, an int
		var ps, as float64
		for _, k := range A.realOrd {
			if A.fam2Pre[k] {
				pn++
				ps += A.real[k]
			} else {
				an++
				as += A.real[k]
			}
		}
		out = append(out, fmt.Sprintf("%-26s REAL present %4d %10s | absent %4d %10s   (real positions by the 2NUM family on the token in the %.0f slots before the dump; fam2 %s)",
			"family present / absent", pn, fmtSigned(ps, 3), an, fmtSigned(as, 3), A.fam2Slots, A.fam2Mode))
	}
	return out
}

// sumSorted: a map's values summed in key order (deterministic float sums).
func sumSorted(m map[int64]float64) float64 {
	ks := make([]int64, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	slices.Sort(ks)
	s := 0.0
	for _, k := range ks {
		s += m[k]
	}
	return s
}
