package ui

import "charm.land/bubbles/v2/key"

// keyMap: every binding, with its help text (the help bar and the ? screen are generated from it).
type keyMap struct {
	Tabs, Next, Prev                key.Binding
	Up, Down, PgUp, PgDn, Home, End key.Binding
	Enter, Back                     key.Binding
	Filter, Search, Wrap            key.Binding
	Scope, Session, Unit            key.Binding
	Pause, Price, Faster, Slower    key.Binding
	Anim, Mute, Help, Quit          key.Binding
	tab                             int
	detail                          bool
}

func newKeyMap() keyMap {
	nb := key.NewBinding
	k, h := key.WithKeys, key.WithHelp
	return keyMap{
		Tabs:    nb(k("1", "2", "3", "4", "5", "6", "7"), h("1-7", "tabs")),
		Next:    nb(k("tab"), h("tab", "next tab")),
		Prev:    nb(k("shift+tab"), h("shift+tab", "previous tab")),
		Up:      nb(k("up", "k"), h("↑/k", "up")),
		Down:    nb(k("down", "j"), h("↓/j", "down")),
		PgUp:    nb(k("pgup", "b"), h("pgup", "page up")),
		PgDn:    nb(k("pgdown", "space"), h("pgdn", "page down")),
		Home:    nb(k("home", "g"), h("home", "top")),
		End:     nb(k("end", "G"), h("end", "bottom / follow")),
		Enter:   nb(k("enter"), h("enter", "details")),
		Back:    nb(k("esc"), h("esc", "back")),
		Filter:  nb(k("f"), h("f", "filter")),
		Search:  nb(k("/"), h("/", "find mint")),
		Wrap:    nb(k("w"), h("w", "wrap")),
		Scope:   nb(k("s"), h("s", "run/today")),
		Session: nb(k("S"), h("S", "session")),
		Unit:    nb(k("u"), h("u", "$/SOL")),
		Pause:   nb(k("p"), h("p", "pause")),
		Price:   nb(k("r"), h("r", "price")),
		Faster:  nb(k("+", "="), h("+/-", "rate")),
		Slower:  nb(k("-", "_")),
		Anim:    nb(k("a"), h("a", "animations")),
		Mute:    nb(k("m"), h("m", "mute")),
		Help:    nb(k("?"), h("?", "help")),
		Quit:    nb(k("q", "ctrl+c"), h("q", "quit")),
	}
}

// ShortHelp is the footer's help bar: what matters on this tab.
func (k keyMap) ShortHelp() []key.Binding {
	if k.detail {
		return []key.Binding{k.Back, k.Unit, k.Quit}
	}
	switch k.tab {
	case 3: // trades
		return []key.Binding{k.Up, k.Enter, k.Filter, k.Search, k.Unit, k.Help, k.Quit}
	case 5: // log
		return []key.Binding{k.Up, k.End, withHelp(k.Filter, "f", "important/all"), k.Wrap, k.Help, k.Quit}
	}
	return []key.Binding{k.Tabs, k.Scope, k.Unit, k.Pause, k.Mute, k.Help, k.Quit}
}

// FullHelp is the ? screen, in columns.
func (k keyMap) FullHelp() [][]key.Binding {
	return [][]key.Binding{
		{k.Tabs, k.Next, k.Prev, k.Up, k.Down, k.PgUp, k.PgDn, k.Home, k.End},
		{k.Enter, k.Back, withHelp(k.Filter, "f", "filter trades / log"), k.Search, k.Wrap, k.Scope, k.Session, k.Unit},
		{k.Pause, k.Price, k.Faster, k.Anim, k.Mute, k.Help, k.Quit},
	}
}

func withHelp(b key.Binding, keys, desc string) key.Binding {
	b.SetHelp(keys, desc)
	return b
}
