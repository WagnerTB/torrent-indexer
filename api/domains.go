package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/felipemarinho97/torrent-indexer/logging"
	"github.com/felipemarinho97/torrent-indexer/utils"
	"github.com/redis/go-redis/v9"
)

const domainsRedisKey = "torrent-indexer:domains"

// DomainEntry is the stored report for a domain seen in release titles.
type DomainEntry struct {
	Domain    string   `json:"domain"`
	Count     int      `json:"count"`
	FirstSeen string   `json:"first_seen"`
	LastSeen  string   `json:"last_seen"`
	Known     bool     `json:"known"`
	Samples   []string `json:"samples"`
	Sources   []string `json:"sources"`
}

var domainsMu sync.Mutex

func (i *Indexer) recordDomains(r *http.Request, title string) {
	domains := utils.ExtractDomains(title)
	if len(domains) == 0 {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	source := requestIndexerName(r)
	sample := truncateRunes(title, 240)
	now := time.Now().UTC().Format(time.RFC3339)

	domainsMu.Lock()
	defer domainsMu.Unlock()

	for _, domain := range domains {
		entry := DomainEntry{
			Domain:  domain,
			Samples: []string{},
			Sources: []string{},
		}
		raw, err := i.redis.HGet(ctx, domainsRedisKey, domain)
		if err == nil {
			if unmarshalErr := json.Unmarshal(raw, &entry); unmarshalErr != nil {
				logging.Error().Err(unmarshalErr).Str("domain", domain).Msg("Failed to decode domain report entry")
			}
		} else if !errors.Is(err, redis.Nil) {
			logging.Error().Err(err).Str("domain", domain).Msg("Failed to read domain report entry")
			continue
		}

		entry.Domain = domain
		entry.Count++
		entry.LastSeen = now
		if entry.FirstSeen == "" {
			entry.FirstSeen = now
		}
		entry.Known = utils.IsKnownWebsiteDomain(domain)
		entry.Samples = appendUnique(entry.Samples, sample, 5)
		entry.Sources = appendUnique(entry.Sources, source, 5)

		payload, marshalErr := json.Marshal(entry)
		if marshalErr != nil {
			logging.Error().Err(marshalErr).Str("domain", domain).Msg("Failed to encode domain report entry")
			continue
		}
		if err := i.redis.HSet(ctx, domainsRedisKey, domain, payload); err != nil {
			logging.Error().Err(err).Str("domain", domain).Msg("Failed to store domain report entry")
		}
	}
}

// HandlerDomains returns domains seen in release titles. By default it lists
// only unknown domains; use ?unknown=0 to include known websites too.
func (i *Indexer) HandlerDomains(w http.ResponseWriter, r *http.Request) {
	if token := os.Getenv("DOMAINS_REPORT_TOKEN"); token != "" {
		if r.Header.Get("X-Domains-Token") != token && r.URL.Query().Get("token") != token {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	raw, err := i.redis.HGetAll(ctx, domainsRedisKey)
	if err != nil {
		http.Error(w, "failed to load domains", http.StatusInternalServerError)
		return
	}

	entries := make([]DomainEntry, 0, len(raw))
	unknown := 0
	for domain, value := range raw {
		var entry DomainEntry
		if err := json.Unmarshal([]byte(value), &entry); err != nil {
			continue
		}
		entry.Domain = domain
		entry.Known = utils.IsKnownWebsiteDomain(domain)
		if !entry.Known {
			unknown++
		}
		if entry.Samples == nil {
			entry.Samples = []string{}
		}
		if entry.Sources == nil {
			entry.Sources = []string{}
		}
		entries = append(entries, entry)
	}

	unknownOnly := r.URL.Query().Get("unknown") != "0"
	sort.Slice(entries, func(a, b int) bool {
		if entries[a].Count != entries[b].Count {
			return entries[a].Count > entries[b].Count
		}
		if entries[a].LastSeen != entries[b].LastSeen {
			return entries[a].LastSeen > entries[b].LastSeen
		}
		return entries[a].Domain < entries[b].Domain
	})

	if unknownOnly {
		filtered := entries[:0]
		for _, entry := range entries {
			if !entry.Known {
				filtered = append(filtered, entry)
			}
		}
		entries = filtered
	}

	limit := 100
	if value := r.URL.Query().Get("limit"); value != "" {
		if parsed, parseErr := strconv.Atoi(value); parseErr == nil {
			limit = parsed
		}
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 500 {
		limit = 500
	}
	if len(entries) > limit {
		entries = entries[:limit]
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"total":   len(raw),
		"unknown": unknown,
		"domains": entries,
	})
}

func requestIndexerName(r *http.Request) string {
	if r == nil {
		return "unknown"
	}
	path := strings.Trim(r.URL.Path, "/")
	if strings.HasPrefix(path, "indexers/") {
		name := strings.TrimPrefix(path, "indexers/")
		if name != "" {
			return name
		}
	}
	if name := r.URL.Query().Get("indexer"); name != "" {
		return name
	}
	return "unknown"
}

func appendUnique(values []string, value string, max int) []string {
	if value == "" {
		return values
	}
	for _, current := range values {
		if current == value {
			return values
		}
	}
	values = append(values, value)
	if len(values) > max {
		values = values[len(values)-max:]
	}
	return values
}

func truncateRunes(value string, max int) string {
	value = strings.TrimSpace(value)
	runes := []rune(value)
	if len(runes) <= max {
		return value
	}
	return string(runes[:max]) + "..."
}
