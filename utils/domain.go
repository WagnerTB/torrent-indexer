package utils

import (
	"regexp"
	"strings"
)

var domainTLDs = []string{
	"com", "net", "org", "info", "biz", "co", "io", "xyz", "me", "tv", "cc", "us",
	"online", "site", "la", "se", "to", "br", "mx", "ru", "in", "club", "link",
	"download", "top", "win", "vip", "pw", "ws", "mobi", "name", "pro", "app",
	"dev", "one", "shop", "store", "blog", "cloud", "host", "space", "website",
	"press", "wiki", "games", "film", "movies", "pt", "nu", "st", "is", "gg",
	"im", "am", "fm", "world", "life", "news", "today", "network", "solutions",
	"tech", "digital", "media", "studio", "video", "watch", "show", "movie",
}

var domainPattern = regexp.MustCompile(
	`(?i)\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:` + strings.Join(domainTLDs, "|") + `)\b`,
)

var twoLevelTLDs = map[string]struct{}{
	"com.br": {}, "com.pt": {}, "co.uk": {}, "com.au": {}, "co.nz": {}, "co.za": {},
}

func normalizeDomain(domain string) string {
	labels := strings.Split(domain, ".")
	if len(labels) < 2 {
		return domain
	}
	if len(labels) >= 3 {
		suffix := labels[len(labels)-2] + "." + labels[len(labels)-1]
		if _, ok := twoLevelTLDs[suffix]; ok {
			return strings.Join(labels[len(labels)-3:], ".")
		}
	}
	return strings.Join(labels[len(labels)-2:], ".")
}

// ExtractDomains returns unique, lower-case domains found in a release title.
func ExtractDomains(title string) []string {
	matches := domainPattern.FindAllString(title, -1)
	if len(matches) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(matches))
	domains := make([]string, 0, len(matches))
	for _, match := range matches {
		domain := strings.ToLower(match)
		domain = strings.TrimPrefix(domain, "www.")
		domain = strings.TrimSuffix(domain, ".")
		domain = normalizeDomain(domain)
		if domain == "" {
			continue
		}
		if _, ok := seen[domain]; ok {
			continue
		}
		seen[domain] = struct{}{}
		domains = append(domains, domain)
	}
	return domains
}

// IsKnownWebsiteDomain reports whether the domain belongs to a website already
// listed in the indexer's known-website cleanup list.
func IsKnownWebsiteDomain(domain string) bool {
	domain = strings.ToLower(strings.TrimPrefix(domain, "www."))
	for _, sld := range commonWebsiteSLDs {
		for _, tld := range commonTLDs {
			suffix := strings.ToLower(sld) + tld
			if domain == suffix || strings.HasSuffix(domain, "."+suffix) {
				return true
			}
		}
	}
	return false
}
