package ui

import (
	"strings"

	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// v5 (11-11): tab 9 "Stats": the dip46 / dip47 sections (probes, filter A/B, filter state, pause, re-arm cap, re-arm fleet,
// GRPSIGN, funder clusters) when the run has them, then P&L by hour, big trades and landing by leader client.

// tab9Shown: the tab bar shows "9 Stats" on a dip46 / dip47 run or while it is open (older runs' tab bars as in v4; 9 opens it).
func (m *Model) tab9Shown() bool {
	if m.tab == 8 {
		return true
	}
	return m.view != nil && m.view.V5 != nil && len(m.view.V5.Rule) > 0
}

// v5Panel: one section as a panel; table rows (Pre) are cut at the width, the rest wrapped; tones colour whole lines.
func (m *Model) v5Panel(s *core.D43Section, pw int) string {
	t := m.th
	inner := pw
	if pw >= 70 {
		inner = pw - 4
	}
	pre := map[int]bool{}
	for _, i := range s.Pre {
		pre[i] = true
	}
	var ls []string
	if pw < 70 && len(s.Alt) > 0 { // phones: the compact table
		for _, l := range s.Alt {
			ls = append(ls, t.Val.Render(ansi.Truncate(l, max(10, inner-1), m.g("…", "~"))))
		}
		return m.section(s.Title, "", ls, pw)
	}
	for i, l := range s.Lines {
		st := t.Val
		sub := strings.HasPrefix(l, "  ")
		if sub && !pre[i] {
			st = t.Lbl
		}
		switch s.Tones[i] {
		case "pos":
			st = t.Good
		case "neg":
			st = t.Neg
		case "warn":
			st = t.Warn
		case "dim":
			st = t.Dim
		case "acc":
			st = t.Acc
		}
		if pre[i] {
			ls = append(ls, st.Render(ansi.Truncate(strings.TrimPrefix(l, "  "), max(10, inner-1), m.g("…", "~"))))
			continue
		}
		ind, ww, x0 := 2, max(10, inner-1), l
		if sub {
			x0, ww = strings.TrimLeft(l, " "), max(10, inner-3)
		}
		for _, x := range core.WrapText(x0, ww, ind) {
			if sub {
				x = "  " + x
			}
			ls = append(ls, st.Render(x))
		}
	}
	return m.section(s.Title, "", ls, pw)
}

func (m *Model) scrV5(w, bh int) string {
	R := m.view.V5
	if R == nil {
		return m.section("STATS (v5)", "", []string{m.th.Lbl.Render("off (DIPMON_V3=1)")}, w)
	}
	var out []string
	for _, s := range R.Rule {
		out = append(out, m.v5Panel(s, w))
	}
	for _, s := range R.Stats {
		out = append(out, m.v5Panel(s, w))
	}
	if len(out) == 0 {
		return m.section("STATS (v5)", "", []string{m.th.Lbl.Render("no pre-send fills or tries yet")}, w)
	}
	return strings.Join(out, "\n")
}

// v5Of: a trade's v5 view (nil = none).
func (m *Model) v5Of(tr *core.Trade) *core.V5Fill {
	if tr == nil || tr.Kind != "PS" || !tr.W.Ok || m.view == nil {
		return nil
	}
	return m.view.V5.Fill(tr.W.W, tr.Mint)
}

// fvOn: the Trades table's fv column (dip47 runs: the fills carry the filter state's version).
func (m *Model) fvOn() bool { return m.view != nil && m.view.V5 != nil && m.view.V5.FvOn }

// blocksLine: one line under the header with every state that blocks new buys now ("" = none: the header as in v4).
func (m *Model) blocksLine(w int) string {
	v := m.view
	if v == nil || len(v.Blocks) == 0 {
		return ""
	}
	t := m.th
	var ps []string
	for _, b := range v.Blocks {
		st := t.Bad
		switch b.Sev {
		case "warn":
			st = t.Warn
		case "info":
			st = t.Lbl
		}
		ps = append(ps, st.Render(b.Text))
	}
	l := " " + t.Warn.Bold(true).Render(m.g("⏸", "||")) + " " + strings.Join(ps, t.Dim.Render(" "+m.g("·", "|")+" "))
	return ansi.Truncate(l, w, m.g("…", "~"))
}

// tradingKV: the Health tab's trading line (running runs only).
func (m *Model) tradingKV() string {
	v := m.view
	if v == nil || !v.Running {
		return ""
	}
	t := m.th
	if len(v.Blocks) == 0 {
		return m.kv("trading", 10, t.Good.Render("buying enabled (no breaker / pause / fee-budget pause / stop)"))
	}
	var ps []string
	for _, b := range v.Blocks {
		st := t.Bad
		if b.Sev == "warn" {
			st = t.Warn
		} else if b.Sev == "info" {
			st = t.Lbl
		}
		ps = append(ps, st.Render(b.Text))
	}
	return m.kv("trading", 10, strings.Join(ps, t.Dim.Render(" · ")))
}

// statusDot: the run status' dot and text; while running, the real trading state instead of RUNNING (v5).
func (m *Model) statusDot() (string, string) {
	t, v := m.th, m.view
	dot := t.StateDot(StatusState(v.Status), m.ascii)
	st := t.StatusStyle(v.Status).Render(v.Status)
	if v.TradeState != "" {
		ts, dst := t.Bad.Bold(true), "off"
		if v.TradeSev == "warn" {
			ts, dst = t.Warn.Bold(true), "part"
		}
		dot, st = t.StateDot(dst, m.ascii), ts.Render(v.TradeState)
	}
	return dot, st
}
