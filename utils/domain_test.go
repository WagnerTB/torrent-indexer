package utils

import "testing"

func TestExtractDomains(t *testing.T) {
	tests := map[string][]string{
		"..MKV.BAIXARAPIDO.COM-.WEB-DL.1080P.MKV":                 {"baixarapido.com"},
		"VAMOSTORRENT.COM...MP4.-LEGENDADO-..Gran Turismo (2023)": {"vamostorrent.com"},
		"Gran.Turismo.2023.1080p.WEB-DL.DUAL.5.1":                 nil,
		"www.Example.com and yts.mx":                              {"example.com", "yts.mx"},
		"sub.example.com":                                         {"example.com"},
		"pottersville.quanto.mais.selvagem.melhores.2017.1080p.nf.web-dl.dd5.1.x264-dual.comando1.com": {"comando1.com"},
		"BAIXARAPIDO.COM e baixarapido.com": {"baixarapido.com"},
	}
	for input, expected := range tests {
		got := ExtractDomains(input)
		if len(got) != len(expected) {
			t.Fatalf("ExtractDomains(%q) = %v, want %v", input, got, expected)
		}
		for index := range expected {
			if got[index] != expected[index] {
				t.Fatalf("ExtractDomains(%q) = %v, want %v", input, got, expected)
			}
		}
	}
}

func TestIsKnownWebsiteDomain(t *testing.T) {
	for domain, expected := range map[string]bool{
		"vamostorrent.com": true,
		"baixarapido.com":  true,
		"yts.mx":           true,
		"example.com":      false,
	} {
		if got := IsKnownWebsiteDomain(domain); got != expected {
			t.Errorf("IsKnownWebsiteDomain(%q) = %v, want %v", domain, got, expected)
		}
	}
}
