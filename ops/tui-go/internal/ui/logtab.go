package ui

import (
	"fmt"
	"regexp"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

var rxRealSign = regexp.MustCompile(`(?:pnl=|REALIZED \S+ )([-+][\d.]+)`)

func (m *Model) logStyle(s string) lipgloss.Style {
	t := m.th
	switch {
	case strings.Contains(s, "KILL") || strings.Contains(s, "panicked"):
		return t.Bad
	case strings.Contains(s, "Error") || strings.Contains(s, "FAILED"):
		return t.Warn
	case strings.Contains(s, "REALIZED"):
		if x := rxRealSign.FindStringSubmatch(s); x != nil {
			if strings.HasPrefix(x[1], "+") {
				return t.Pos
			}
			return t.Neg
		}
		return t.Val
	case strings.Contains(s, "DIP FIRE") || strings.Contains(s, "FILL"):
		return t.Acc
	case strings.Contains(s, "QUIET") || strings.Contains(s, "STOPPED") || strings.Contains(s, "SIGNAL") || strings.Contains(s, "refused") || strings.Contains(s, "UNHEALTHY"):
		return t.Warn
	case strings.HasPrefix(s, "===") || strings.Contains(s, "START BALANCE") || strings.HasPrefix(s, "DIP LIVE"):
		return t.B
	}
	return t.Val
}

// scrLog: the engine log's tail (important lines or all) in a viewport; End follows the tail, w wraps.
func (m *Model) scrLog(w, bh int) string {
	t := m.th
	M := m.ctx.Src.Model
	ring := M.LogImp
	if m.logAll {
		ring = M.LogRing
	}
	rows := max(1, bh-1)
	n := ring.Len()
	m.logOff = max(0, min(m.logOff, max(0, n-1)))
	need := rows + m.logOff
	start := max(0, n-need-rows)
	tw := 12
	var ls []string
	for i := start; i < n; i++ {
		it := ring.At(i)
		ns, exact := M.LogTime(it)
		ts := ""
		if ns != 0 {
			if exact {
				ts = core.T12(ns, true)
			} else {
				ts = "~" + core.T12(ns, false)
			}
		}
		pre := t.Dim.Render(padLeft(ts, tw-1) + " ")
		text := to12(it.Text)
		st := m.logStyle(it.Text)
		if m.logWrap {
			for j, l := range core.WrapText(text, max(10, w-tw), 2) {
				if j == 0 {
					ls = append(ls, pre+st.Render(l))
				} else {
					ls = append(ls, strings.Repeat(" ", tw)+st.Render(l))
				}
			}
		} else {
			ls = append(ls, pre+st.Render(text))
		}
	}
	m.vp.SetWidth(w)
	m.vp.SetHeight(rows)
	m.vp.SetContentLines(ls)
	total := len(ls)
	off := max(0, total-rows-m.logOff)
	m.vp.SetYOffset(off)
	mode := "important"
	if m.logAll {
		mode = "all lines"
	}
	left := t.AccB.Render("LOG ") + t.Acc.Render(mode) + t.Lbl.Render(fmt.Sprintf("  (%s)", core.IC(int64(n))))
	follow := t.Lbl.Render("following")
	if m.logOff > 0 {
		follow = t.Warn.Render(fmt.Sprintf("%d up", m.logOff))
	}
	right := follow
	if w >= 60 {
		right += t.Dim.Render("   f all/important  w wrap  end follow")
	}
	head := lr(left, right, w)
	if n == 0 {
		msg := "no log lines"
		if !m.logAll {
			msg += " marked important yet (f: show all)"
		}
		return head + "\n" + t.Lbl.Render(msg)
	}
	return head + "\n" + m.vp.View()
}

// ------------------------------------------------------------------------------------------------- splash

// splash: the full REWIND logo centered, a spinner with the load's progress and a gradient bar.
func (m *Model) splash(w, h int) string {
	t := m.th
	src := m.ctx.Src
	label := "pump.fun dip bot"
	run := "run"
	if src.HasRun {
		label = strings.ToLower(src.Region) + " " + m.g("·", "|") + " run " + fmt.Sprint(src.Run)
		run = "run " + fmt.Sprint(src.Run)
	}
	var logo string
	switch {
	case m.ascii || t.Mono:
		logo = lipgloss.NewStyle().Bold(true).Render("R E W I N D") + "\n" + t.Lbl.Render(label)
	case w >= 90:
		logo = m.logoBlock(w, 3, true, label, "", true)
	case w >= 44:
		logo = m.logoBlock(w, 3, false, label, "", true)
	default:
		logo = m.logoBlock(w, 2, false, label, "", true)
	}
	frac := m.loadFrac()
	done := float64(src.DoneBytes()) / 1e6
	tot := float64(m.loadTotal) / 1e6
	sp := m.spin.View()
	if m.ascii {
		sp = "*"
	}
	status := sp + " " + t.Val.Render(fmt.Sprintf("loading %s %s %.0f%%", run, m.g("·", "|"), frac*100))
	if mb := t.Lbl.Render(fmt.Sprintf("   %s / %s MB", core.FC(done, 1), core.FC(tot, 1))); ansi.StringWidth(status+mb) <= w-2 {
		status += mb
	}
	bw := max(10, min(60, w-8))
	bar := m.bar(frac, bw, t.Pink, t.Violet, t.Indigo)
	noteS := "read-only " + m.g("·", "|") + " chunked, the CPU is yielded between chunks " + m.g("·", "|") + " q quits"
	if ansi.StringWidth(noteS) > w-2 {
		noteS = "read-only " + m.g("·", "|") + " q quits"
	}
	note := t.Dim.Render(noteS)
	under := lipgloss.JoinVertical(lipgloss.Center, "", status, "", bar, "", note)
	underB := lipgloss.PlaceHorizontal(w, lipgloss.Center, under)
	all := logo + "\n" + underB
	return lipgloss.Place(w, h, lipgloss.Center, lipgloss.Center, block(all, w, 0))
}
