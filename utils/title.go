package utils

import (
	"regexp"
	"strings"
)

var (
	leadingTitleJunk  = regexp.MustCompile(`^[\s.\-_]+`)
	leadingMediaToken = regexp.MustCompile(`(?i)^(?:mkv|mp4|avi|m4v|mov|wmv|flv|ts|m2ts)[.\-_ ]+`)
	leadingVideoTag   = regexp.MustCompile(`(?i)^(?:legendado|dublado|nacional)[.\-_ ]+`)
)

// NormalizeReleaseTitle removes leading file-extension and language noise from
// release titles (for example "..MKV.-LEGENDADO-..Gran.Turismo...").
func NormalizeReleaseTitle(title string) string {
	title = strings.TrimSpace(title)
	for {
		next := leadingTitleJunk.ReplaceAllString(title, "")
		next = leadingMediaToken.ReplaceAllString(next, "")
		next = leadingVideoTag.ReplaceAllString(next, "")
		next = strings.TrimSpace(next)
		if next == title {
			return next
		}
		title = next
	}
}
