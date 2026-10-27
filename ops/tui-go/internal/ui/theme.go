// Package ui is dipmon's Bubble Tea app: the REWIND look built on Lip Gloss (panels, the grid, adaptive colors,
// gradients, tables, the layer compositor), Bubbles (help + key map, spinner, progress, viewport, textinput),
// Harmonica springs (the hero number) and ntcharts (the P&L line).
package ui

import (
	"image/color"

	"charm.land/lipgloss/v2"
)

// Theme holds every color and style; built for a dark or light terminal (or monochrome).
type Theme struct {
	Dark, Mono bool

	// palette
	Bg, Fg, Label, Faint, Border, Accent, AccentSoft color.Color
	Green, Red, Yellow, GreenSoft, RedSoft           color.Color
	Pink, Violet, Indigo, Hatch                      color.Color
	Zebra, SelBg, PillBg                             color.Color
	Brand                                            []color.Color // pink -> violet -> indigo

	// styles
	Lbl, Dim, Val, B, Pos, Neg, PosB, NegB, Acc, AccB, Warn, Bad, Good lipgloss.Style
	Title, PanelTitle, Rule                                            lipgloss.Style
	TabOn, TabOff, Key, KeyDesc                                        lipgloss.Style
	Sel                                                                lipgloss.Style
}

func hex(s string) color.Color { return lipgloss.Color(s) }

// NewTheme builds the palette: calm grays, white values, green / red only for money and status, one violet accent.
func NewTheme(dark, mono bool) *Theme {
	t := &Theme{Dark: dark, Mono: mono}
	ld := lipgloss.LightDark(dark)
	t.Fg = ld(hex("#1F2330"), hex("#E8E6F0"))
	t.Label = ld(hex("#6B7080"), hex("#8A8FA3"))
	t.Faint = ld(hex("#A3A8B5"), hex("#5A5F72"))
	t.Border = ld(hex("#D3D6DE"), hex("#353A4A"))
	t.Accent = ld(hex("#6D3FE0"), hex("#B39DFF"))
	t.AccentSoft = ld(hex("#EDE7FF"), hex("#2A2442"))
	t.Green = ld(hex("#13804A"), hex("#4FD69C"))
	t.Red = ld(hex("#C0263A"), hex("#FF6B81"))
	t.Yellow = ld(hex("#A15C00"), hex("#F2C56B"))
	t.GreenSoft = ld(hex("#DDF5E8"), hex("#173A2C"))
	t.RedSoft = ld(hex("#FCE4E7"), hex("#40202A"))
	t.Pink = ld(hex("#D6359F"), hex("#FF5FD2"))
	t.Violet = ld(hex("#7A3FE0"), hex("#A35BFF"))
	t.Indigo = ld(hex("#4B3CC7"), hex("#6C5CE7"))
	t.Hatch = ld(hex("#C9BDF2"), hex("#46386E"))
	t.Zebra = ld(hex("#F4F3F8"), hex("#1C1E27"))
	t.SelBg = ld(hex("#E6DEFF"), hex("#352C55"))
	t.PillBg = ld(hex("#EDE7FF"), hex("#2C2546"))
	t.Brand = []color.Color{t.Pink, t.Violet, t.Indigo}
	if mono {
		nc := lipgloss.NoColor{}
		t.Fg, t.Label, t.Faint, t.Border, t.Accent, t.AccentSoft = nc, nc, nc, nc, nc, nc
		t.Green, t.Red, t.Yellow, t.GreenSoft, t.RedSoft = nc, nc, nc, nc, nc
		t.Pink, t.Violet, t.Indigo, t.Hatch, t.Zebra, t.SelBg, t.PillBg = nc, nc, nc, nc, nc, nc, nc
		t.Brand = []color.Color{nc}
	}
	s := lipgloss.NewStyle
	t.Lbl = s().Foreground(t.Label)
	t.Dim = s().Foreground(t.Faint)
	t.Val = s().Foreground(t.Fg)
	t.B = s().Foreground(t.Fg).Bold(true)
	t.Pos = s().Foreground(t.Green)
	t.Neg = s().Foreground(t.Red)
	t.PosB = t.Pos.Bold(true)
	t.NegB = t.Neg.Bold(true)
	t.Acc = s().Foreground(t.Accent)
	t.AccB = t.Acc.Bold(true)
	t.Warn = s().Foreground(t.Yellow)
	t.Bad = s().Foreground(t.Red).Bold(true)
	t.Good = s().Foreground(t.Green)
	t.Title = s().Foreground(t.Accent).Bold(true)
	t.PanelTitle = s().Foreground(t.Accent).Bold(true)
	t.Rule = s().Foreground(t.Border)
	t.TabOn = s().Foreground(t.Accent).Background(t.PillBg).Bold(true)
	t.TabOff = s().Foreground(t.Label)
	t.Key = s().Foreground(t.Accent)
	t.KeyDesc = s().Foreground(t.Label)
	t.Sel = s().Background(t.SelBg).Foreground(t.Fg)
	if mono {
		t.Lbl = s().Faint(true)
		t.Dim = s().Faint(true)
		t.Val = s()
		t.Pos = s().Bold(true)
		t.Neg = s().Bold(true).Underline(true)
		t.PosB, t.NegB = t.Pos, t.Neg
		t.Acc = s().Bold(true)
		t.AccB = t.Acc
		t.Warn = s().Bold(true)
		t.Bad = s().Bold(true).Reverse(true)
		t.Good = s()
		t.Title, t.PanelTitle = t.Acc, t.Acc
		t.Rule = s().Faint(true)
		t.TabOn = s().Reverse(true).Bold(true)
		t.TabOff = s().Faint(true)
		t.Key = s().Bold(true)
		t.KeyDesc = s().Faint(true)
		t.Sel = s().Reverse(true)
	}
	return t
}

// Money picks the money style for a lamport amount (green / red / plain).
func (t *Theme) Money(lam int64, ok bool, bold bool) lipgloss.Style {
	switch {
	case !ok || lam == 0:
		if bold {
			return t.B
		}
		return t.Val
	case lam > 0:
		if bold {
			return t.PosB
		}
		return t.Pos
	default:
		if bold {
			return t.NegB
		}
		return t.Neg
	}
}

// StateDot is a status dot: on (green) / part (yellow) / off (red) / na (dim).
func (t *Theme) StateDot(state string, ascii bool) string {
	switch state {
	case "on":
		if ascii {
			return t.Good.Render("+")
		}
		return t.Good.Render("●")
	case "part":
		if ascii {
			return t.Warn.Render("~")
		}
		return t.Warn.Render("●")
	case "off":
		if ascii {
			return t.Neg.Render("-")
		}
		return t.Neg.Render("●")
	}
	if ascii {
		return t.Dim.Render(".")
	}
	return t.Dim.Render("○")
}

// StatusStyle colors the run status.
func (t *Theme) StatusStyle(status string) lipgloss.Style {
	switch status {
	case "RUNNING":
		return t.Good.Bold(true)
	case "STOPPING", "NO END RECORD":
		return t.Warn.Bold(true)
	case "ENDED":
		return t.AccB
	case "ENGINE GONE":
		return t.Bad
	}
	return t.Lbl
}

// StatusState maps a run status to a dot state.
func StatusState(status string) string {
	switch status {
	case "RUNNING":
		return "on"
	case "STOPPING", "NO END RECORD":
		return "part"
	case "ENGINE GONE":
		return "off"
	}
	return "na"
}
