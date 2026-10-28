package handler

import (
	"net/http"
	"regexp"
	"strconv"

	"github.com/felipemarinho97/torrent-indexer/schema"
)

var (
	seasonEpisodeRe  = regexp.MustCompile(`(?i)\bS(\d{1,2})[\s._-]*E(\d{1,3})\b`)
	seasonXEpisodeRe = regexp.MustCompile(`(?i)\b(\d{1,2})x(\d{1,2})\b`)
	seasonWordRe     = regexp.MustCompile(`(?i)(?:temporada|season)\s*(\d{1,2})\b`)
	seasonOrdinalRe  = regexp.MustCompile(`(?i)\b(\d{1,2})\s*[ªa]?\s*temporada\b`)
	seasonOnlyRe     = regexp.MustCompile(`(?i)\bS(\d{1,2})\b`)
	episodeWordRe    = regexp.MustCompile(`(?i)\b(?:epis[oó]dio|ep\.?)\s*(\d{1,3})\b`)
	completeSeasonRe = regexp.MustCompile(`(?i)\b(?:temporada\s+completa|season\s+complete|complete\s+season|s[eé]rie\s+completa|complete\s+series)\b`)
)

func atoiIgnoreError(value string) int {
	parsed, _ := strconv.Atoi(value)
	return parsed
}

// ParseSeasonEpisode extracts season/episode information from a release title.
// It is intentionally best-effort: titles from different sites use different
// conventions and some releases are complete-season packs without an episode.
func ParseSeasonEpisode(title string) (season int, episode int, releaseType string) {
	if match := seasonEpisodeRe.FindStringSubmatch(title); len(match) > 0 {
		return atoiIgnoreError(match[1]), atoiIgnoreError(match[2]), "episode"
	}
	if match := seasonXEpisodeRe.FindStringSubmatch(title); len(match) > 0 {
		return atoiIgnoreError(match[1]), atoiIgnoreError(match[2]), "episode"
	}

	if match := seasonWordRe.FindStringSubmatch(title); len(match) > 0 {
		season = atoiIgnoreError(match[1])
	} else if match := seasonOrdinalRe.FindStringSubmatch(title); len(match) > 0 {
		season = atoiIgnoreError(match[1])
	} else if match := seasonOnlyRe.FindStringSubmatch(title); len(match) > 0 {
		season = atoiIgnoreError(match[1])
	}

	if match := episodeWordRe.FindStringSubmatch(title); len(match) > 0 {
		episode = atoiIgnoreError(match[1])
	}

	if completeSeasonRe.MatchString(title) {
		if season == 0 {
			return 0, 0, "series"
		}
		return season, 0, "season"
	}

	if episode > 0 {
		return season, episode, "episode"
	}
	if season > 0 {
		return season, 0, "season"
	}

	return 0, 0, ""
}

// ParseReleaseMetadata fills season/episode/release type for torrents that
// don't have it yet. It runs before the search indexer post-processor.
func ParseReleaseMetadata(_ *Indexer, _ *http.Request, torrents []schema.IndexedTorrent) []schema.IndexedTorrent {
	for i := range torrents {
		if torrents[i].Season != 0 || torrents[i].Episode != 0 || torrents[i].ReleaseType != "" {
			continue
		}

		season, episode, releaseType := ParseSeasonEpisode(torrents[i].Title)
		if season == 0 && episode == 0 && releaseType == "" {
			season, episode, releaseType = ParseSeasonEpisode(torrents[i].OriginalTitle)
		}

		torrents[i].Season = season
		torrents[i].Episode = episode
		torrents[i].ReleaseType = releaseType
	}
	return torrents
}
