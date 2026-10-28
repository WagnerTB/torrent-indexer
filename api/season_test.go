package handler

import "testing"

func TestParseSeasonEpisode(t *testing.T) {
	tests := []struct {
		name        string
		title       string
		wantSeason  int
		wantEpisode int
		wantType    string
	}{
		{"SxxExx", "The.Last.of.Us.S02E05.1080p.WEB-DL.DUAL.5.1", 2, 5, "episode"},
		{"SxxExx house", "House.of.the.Dragon.S03E01.1080p", 3, 1, "episode"},
		{"SxxExx thrones", "Game.of.Thrones.S06E10.720p", 6, 10, "episode"},
		{"portuguese ordinal", "Suits 6ª Temporada", 6, 0, "season"},
		{"portuguese ordinal with year", "Breaking Bad 2010 3ª Temporada", 3, 0, "season"},
		{"temporada word", "Temporada 2 Completa", 2, 0, "season"},
		{"complete series", "Série Completa", 0, 0, "series"},
		{"nxm", "2x05", 2, 5, "episode"},
		{"movie", "Matrix 3: Revolutions (2003)", 0, 0, ""},
		{"codec", "1080p WEB-DL x264", 0, 0, ""},
		{"audio codec", "5.1x264", 0, 0, ""},
		{"episode word", "Episódio 5", 0, 5, "episode"},
		{"season complete", "Season 2 Complete", 2, 0, "season"},
		{"season only", "S02", 2, 0, "season"},
		{"resolution", "1920x1080", 0, 0, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			season, episode, releaseType := ParseSeasonEpisode(tt.title)
			if season != tt.wantSeason || episode != tt.wantEpisode || releaseType != tt.wantType {
				t.Fatalf("ParseSeasonEpisode(%q) = (%d, %d, %q), want (%d, %d, %q)",
					tt.title, season, episode, releaseType, tt.wantSeason, tt.wantEpisode, tt.wantType)
			}
		})
	}
}
