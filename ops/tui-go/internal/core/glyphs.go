package core

// Glyphs: the single-width symbols used in text (the Python version's G table). --ascii switches to ASCII.
type Glyphs struct {
	ASCII                                                          bool
	On, Sep, Arrow, Dash, Hr, Vr, Bar, Bar0, Spark, Ell, X, Ok, No string
	Up, Down, Tri, Dia, Ge, Minus                                  string
}

var uniGlyphs = Glyphs{On: "●", Sep: "·", Arrow: "→", Dash: "–", Hr: "─", Vr: "│", Bar: "━", Bar0: "─", Spark: "▁▂▃▄▅▆▇█",
	Ell: "…", X: "×", Ok: "✓", No: "✗", Up: "▲", Down: "▼", Tri: "▸", Dia: "◆", Ge: "≥", Minus: "-"}

var ascGlyphs = Glyphs{ASCII: true, On: "*", Sep: "|", Arrow: "->", Dash: "-", Hr: "-", Vr: "|", Bar: "=", Bar0: "-",
	Spark: "_.:-=+*#", Ell: "~", X: "x", Ok: "ok", No: "x", Up: "^", Down: "v", Tri: ">", Dia: "+", Ge: ">=", Minus: "-"}

// G is the active glyph set.
var G = uniGlyphs

// SetASCII switches every glyph to ASCII (--ascii, or a non-UTF-8 terminal).
func SetASCII(on bool) {
	if on {
		G = ascGlyphs
	} else {
		G = uniGlyphs
	}
}

// BadgeASCII: the snapshot's badge marks.
var BadgeASCII = map[string]string{"on": "+", "off": "-", "part": "~", "na": "."}
