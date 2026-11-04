package core

// dip37 (engine 11-04, not released yet): the per-window priority-fee A/B of the pre-send tries (--presend-live-fee-ab on).
// Each window is arm A or B; a try on a listed (fee-ordered) leader of an arm-B window is signed with B's CU price / limit / tip, any
// other try with A's. With the A/B on the engine writes fee_arm ("A" / "B") and fee_grp ("fee" = a listed client, "jito" = JitoLabs,
// "other") on presend_attempt / presend_attempt_land / presend_live_fill / presend_live_realized. dipmon shows, per arm x leader group
// (the filling try's): fills, win %, mSOL per fill (realized + rent back, over the positions with a realized P&L), the failed tries'
// fees (presend_attempt_land res != ok, by THEIR arm x group) and the net (realized + rent - failed fees). Runs without the fields
// (every run before dip37, or the A/B off) have no block.

import "sort"

// FeeArms / FeeGrps: the engine's arm and leader-group names, in display order.
var (
	FeeArms = []string{"A", "B"}
	FeeGrps = []string{"fee", "jito", "other"}
)

// FeeABRec: a session's failed tries per (arm, group): [count, fees].
type FeeABRec struct {
	Any  bool
	Fail map[[2]string]*[2]int64
}

func (f *FeeABRec) fail(arm, grp string, fee int64) {
	if f.Fail == nil {
		f.Fail = map[[2]string]*[2]int64{}
	}
	c := f.Fail[[2]string{arm, grp}]
	if c == nil {
		c = &[2]int64{}
		f.Fail[[2]string{arm, grp}] = c
	}
	c[0]++
	c[1] += fee
}

// fabLand: a resolved try's fee fields (presend_attempt_land; only failed tries with a fee are passed in).
func (S *Sess) fabLand(line []byte, fee int64) {
	arm, ok := strAfter(line, `"fee_arm":"`)
	if !ok {
		return
	}
	grp, _ := strAfter(line, `"fee_grp":"`)
	S.FAB.Any = true
	S.FAB.fail(arm, grp, fee)
}

// FeeABRow: one arm x leader group (Grp "" = the arm's total).
type FeeABRow struct {
	Arm, Grp        string
	Fills           int64 // fill records (a merged second fill counts)
	Pos, Wins       int64 // positions with a realized P&L, of them > 0
	Pnl, Rent       int64 // their realized P&L, their accounts' rent back (lamports)
	FailN, FailFees int64 // failed tries and their fees
}

// Net: realized + rent back - failed-try fees (lamports; the run P&L's pre-send formula).
func (r FeeABRow) Net() int64 { return r.Pnl + r.Rent - r.FailFees }

// PerFill: (realized + rent back) per position with a realized P&L (lamports; false: none).
func (r FeeABRow) PerFill() (float64, bool) {
	if r.Pos == 0 {
		return 0, false
	}
	return float64(r.Pnl+r.Rent) / float64(r.Pos), true
}

// WinPct: the positions with a realized P&L > 0 (%; false: none).
func (r FeeABRow) WinPct() (float64, bool) {
	if r.Pos == 0 {
		return 0, false
	}
	return float64(r.Wins) / float64(r.Pos) * 100, true
}

// FeeABSum: the fee A/B of the sessions in scope (On: a record carried fee_arm).
type FeeABSum struct {
	On   bool
	Rows []FeeABRow // per arm: its groups with data, then the arm's total (Grp "")
}

// FeeABOf builds the fee A/B summary of sessions (their pre-send positions and failed tries).
func FeeABOf(sessions []*Sess) FeeABSum {
	var s FeeABSum
	cells := map[[2]string]*FeeABRow{}
	get := func(arm, grp string) *FeeABRow {
		k := [2]string{arm, grp}
		if c := cells[k]; c != nil {
			return c
		}
		c := &FeeABRow{Arm: arm, Grp: grp}
		cells[k] = c
		return c
	}
	for _, S := range sessions {
		if !S.FAB.Any {
			continue
		}
		s.On = true
		for k, v := range S.FAB.Fail {
			c := get(k[0], k[1])
			c.FailN += v[0]
			c.FailFees += v[1]
		}
		for _, tr := range S.PSList {
			if tr.FeeArm == "" {
				continue
			}
			c := get(tr.FeeArm, tr.FeeGrp)
			c.Fills += int64(max(tr.NFills, 1))
			if tr.HasPnl {
				c.Pos++
				c.Pnl += tr.Pnl
				if tr.Pnl > 0 {
					c.Wins++
				}
			}
			if tr.HasRent {
				c.Rent += tr.Rent
			}
		}
	}
	if !s.On {
		return s
	}
	arms := append([]string{}, FeeArms...)
	for k := range cells { // an arm name the engine may add later: shown after A / B
		if !contains(arms, k[0]) {
			arms = append(arms, k[0])
		}
	}
	sort.SliceStable(arms[len(FeeArms):], func(i, j int) bool { return arms[len(FeeArms)+i] < arms[len(FeeArms)+j] })
	for _, a := range arms {
		tot := FeeABRow{Arm: a}
		grps := append([]string{}, FeeGrps...)
		for k := range cells {
			if k[0] == a && !contains(grps, k[1]) {
				grps = append(grps, k[1])
			}
		}
		n := 0
		for _, g := range grps {
			c := cells[[2]string{a, g}]
			if c == nil {
				continue
			}
			s.Rows = append(s.Rows, *c)
			n++
			tot.Fills += c.Fills
			tot.Pos += c.Pos
			tot.Wins += c.Wins
			tot.Pnl += c.Pnl
			tot.Rent += c.Rent
			tot.FailN += c.FailN
			tot.FailFees += c.FailFees
		}
		if n > 0 {
			s.Rows = append(s.Rows, tot)
		}
	}
	return s
}

func contains(v []string, x string) bool {
	for _, y := range v {
		if y == x {
			return true
		}
	}
	return false
}
