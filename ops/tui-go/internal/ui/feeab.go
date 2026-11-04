package ui

// dip37: the per-window priority-fee A/B on the Engine tab (shown only when the run's records carry fee_arm).

import (
	"strings"

	"charm.land/lipgloss/v2"

	"dipmon/internal/core"
)

// fabLines: per arm x leader group (the filling try's; failed tries by their own): fills, win %, mSOL per fill (realized + rent back over
// the positions with a realized P&L), failed tries and their fees, net (realized + rent back - failed fees).
func (m *Model) fabLines(w int) []string {
	t := m.th
	s := m.view.FAB
	if len(s.Rows) == 0 {
		return []string{t.Lbl.Render("no fee A/B records yet")}
	}
	ms := func(lam int64) string { return core.F(float64(lam)/1e6, 2) }
	hdr := []string{"arm", "leaders", "fills", "win", "mSOL/fill", "failed", "fees mSOL", "net mSOL"}
	if w < 60 {
		hdr = []string{"arm", "ldr", "fills", "win", "/fill", "fees", "net"}
	}
	var rows [][]string
	var nets []int64
	var tot []bool
	for _, r := range s.Rows {
		g := r.Grp
		if g == "" {
			g = "all"
		}
		win, pf := core.G.Dash, core.G.Dash
		if x, ok := r.WinPct(); ok {
			win = core.F(x, 0) + "%"
		}
		if x, ok := r.PerFill(); ok {
			pf = core.F(x/1e6, 2)
		}
		row := []string{r.Arm, g, core.IC(r.Fills), win, pf, core.IC(r.FailN), ms(r.FailFees), ms(r.Net())}
		if w < 60 {
			row = []string{r.Arm, g, core.IC(r.Fills), win, pf, ms(r.FailFees), ms(r.Net())}
		}
		rows = append(rows, row)
		nets = append(nets, r.Net())
		tot = append(tot, r.Grp == "")
	}
	right := map[int]bool{}
	for i := 2; i < len(hdr); i++ {
		right[i] = true
	}
	out := strings.Split(m.kvTable(hdr, rows, right, func(r, c int) lipgloss.Style {
		if c == len(hdr)-1 {
			return t.Money(nets[r], true, tot[r])
		}
		if c <= 1 {
			if tot[r] {
				return t.Val
			}
			return t.Lbl
		}
		return t.Val
	}), "\n")
	out = append(out, t.Dim.Render("leaders: fee = B's clients (fee-ordered), jito, other; failed = tries landed failed"))
	return out
}
