package core

// CALIBRATION (11-11, the gatecheck study: ~/sniper-studies/gatecheck/calib.py, report2.txt; gatecheck2/report3.txt): the
// paper fill model is badly optimistic (+157 SOL of model P&L where live made +13 on the same windows, r65-r82). The study
// maps a window's model P&L to its expected LIVE P&L by kind (T2 / re-arm) and P&L bucket (stable FIT r65-75 / TEST
// r76-82). The Filters tab's LIVE paper-scored rows apply it per blocked window (cal W / L / net) next to the raw paper.
//
// The table ships embedded (calib.json, exported from ~/sniper-data/gatecheck/calib.pkl by
// ~/sniper-data/dipmon-calib/export_calib.py); --calib FILE reads another, --calib none turns it off.

import (
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
)

//go:embed calib.json
var calibEmbedded []byte

// Calib: the per-window mapping. Bins are the bucket edges, bucket i = (Bins[i], Bins[i+1]] (pandas closed right); a
// value outside the edges goes to the end bucket. Cal[kind][i] = the mean live P&L (SOL) of a window whose model P&L at
// RefSpend[kind] fell in bucket i (0 counted where live never filled).
type Calib struct {
	Source   string               `json:"source"`
	Made     string               `json:"made"`
	Bins     []float64            `json:"bins"`
	RefSpend map[string]float64   `json:"ref_spend"`
	Cal      map[string][]float64 `json:"cal"`
	Path     string               `json:"-"` // "" = the embedded table
}

// ParseCalib decodes and checks a calibration table.
func ParseCalib(b []byte) (*Calib, error) {
	var c Calib
	if err := json.Unmarshal(b, &c); err != nil {
		return nil, err
	}
	if len(c.Bins) < 2 {
		return nil, errors.New("calib: fewer than 2 bin edges")
	}
	for i := 1; i < len(c.Bins); i++ {
		if !(c.Bins[i] > c.Bins[i-1]) {
			return nil, errors.New("calib: bin edges not increasing")
		}
	}
	if len(c.Cal["T2"]) == 0 {
		return nil, errors.New("calib: no T2 table")
	}
	for k, v := range c.Cal {
		if len(v) != len(c.Bins)-1 {
			return nil, fmt.Errorf("calib: %s has %d values for %d buckets", k, len(v), len(c.Bins)-1)
		}
	}
	return &c, nil
}

// LoadCalib: "" = the embedded table, "none" = off (nil), else the file.
func LoadCalib(path string) (*Calib, error) {
	switch path {
	case "none":
		return nil, nil
	case "":
		return ParseCalib(calibEmbedded)
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	c, err := ParseCalib(b)
	if c != nil {
		c.Path = path
	}
	return c, err
}

// DefaultCalib: the embedded table (nil only if it does not parse: a build error the tests catch).
var DefaultCalib, _ = ParseCalib(calibEmbedded)

// Apply: a window's expected live P&L (SOL) from its paper P&L (SOL at size SOL; size <= 0 = the reference spend) and kind
// ("T2" / "RA" / "rearm"). The paper is bucketed at the reference spend and the bucket's live mean scaled back to size.
// ok = false when the kind has no table.
func (c *Calib) Apply(paper float64, kind string, size float64) (float64, bool) {
	if c == nil {
		return 0, false
	}
	if kind == "RA" {
		kind = "rearm"
	}
	tab := c.Cal[kind]
	if len(tab) == 0 {
		return 0, false
	}
	ref := c.RefSpend[kind]
	sc := 1.0
	if ref > 0 && size > 0 {
		sc = size / ref
	}
	x := paper / sc
	i := 0
	for i < len(tab)-1 && x > c.Bins[i+1] {
		i++
	}
	return tab[i] * sc, true
}
