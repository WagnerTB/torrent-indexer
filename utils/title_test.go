package utils

import "testing"

func TestNormalizeReleaseTitle(t *testing.T) {
	tests := map[string]string{
		"..MKV.Gran.Turismo.2023.1080p.WEB-DL.DUAL.5.1 (brazilian, eng)":             "Gran.Turismo.2023.1080p.WEB-DL.DUAL.5.1 (brazilian, eng)",
		"...MP4.-LEGENDADO-..Gran Turismo (2023) [1080p] [YTS.MX] (eng)":             "Gran Turismo (2023) [1080p] [YTS.MX] (eng)",
		"..MKV.-LEGENDADO-..Gran.Turismo.2023.720p.WEBRip.900MB.x264-GalaxyRG (eng)": "Gran.Turismo.2023.720p.WEBRip.900MB.x264-GalaxyRG (eng)",
		"MKV.Gran.Turismo.2023.1080p.WEB-DL":                                         "Gran.Turismo.2023.1080p.WEB-DL",
		"Gran.Turismo.2023.1080p.REMUX.ENG":                                          "Gran.Turismo.2023.1080p.REMUX.ENG",
	}
	for input, expected := range tests {
		if got := NormalizeReleaseTitle(input); got != expected {
			t.Errorf("NormalizeReleaseTitle(%q) = %q, want %q", input, got, expected)
		}
	}
}
