package core

// D43Acc gathers the dip43 records (filled in below).
type D43Acc struct{ ver int64 }

func newD43Acc() *D43Acc { return &D43Acc{} }

func (D *D43Acc) feed(ev, line []byte) {}

// D43Report is what the views show.
type D43Report struct{}

func (D *D43Acc) Report() *D43Report { return nil }
