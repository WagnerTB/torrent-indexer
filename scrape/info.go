package goscrape

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/felipemarinho97/torrent-indexer/cache"
	"github.com/felipemarinho97/torrent-indexer/logging"
	"github.com/felipemarinho97/torrent-indexer/monitoring"
	"github.com/felipemarinho97/torrent-indexer/utils"
)

const (
	peersCachePrefix   = "peers:v2:"
	peersCacheTTL      = 24 * time.Hour
	peersEmptyCacheTTL = 10 * time.Minute
	peersScrapeTimeout = 3 * time.Second
	peerTrackerTimeout = 1500 * time.Millisecond
	maxTrackersPerHash = 50
)

type peers struct {
	Seeders  int `json:"seed"`
	Leechers int `json:"leech"`
}

func peersCacheKey(infoHash string) string {
	return peersCachePrefix + infoHash
}

func getPeersFromCache(ctx context.Context, r *cache.Redis, infoHash string) (int, int, error) {
	peersCache, err := r.Get(ctx, peersCacheKey(infoHash))
	if err != nil {
		return 0, 0, err
	}

	var cachedPeers peers
	if err := json.Unmarshal(peersCache, &cachedPeers); err != nil {
		return 0, 0, err
	}
	return cachedPeers.Leechers, cachedPeers.Seeders, nil
}

func setPeersToCache(ctx context.Context, r *cache.Redis, infoHash string, peer, seed int) error {
	cachedPeers := peers{
		Seeders:  seed,
		Leechers: peer,
	}
	peersJSON, err := json.Marshal(cachedPeers)
	if err != nil {
		return err
	}

	ttl := peersCacheTTL
	if seed == 0 && peer == 0 {
		ttl = peersEmptyCacheTTL
	}

	return r.SetWithExpiration(ctx, peersCacheKey(infoHash), peersJSON, ttl)
}

func GetLeechsAndSeeds(ctx context.Context, r *cache.Redis, m *monitoring.Metrics, infoHash string, trackers []string) (int, int, error) {
	leech, seed, err := getPeersFromCache(ctx, r, infoHash)
	if err != nil {
		m.CacheMisses.WithLabelValues("peers").Inc()
		logging.Debug().Str("info_hash", infoHash).Msg("Unable to get peers from cache")
	} else {
		m.CacheHits.WithLabelValues("peers").Inc()
		logging.Debug().Str("info_hash", infoHash).Int("leech", leech).Int("seed", seed).Msg("Retrieved peers from cache")
		return leech, seed, nil
	}

	additionalTrackers := getAdditionalTrackers(ctx, r)
	allTrackers := make([]string, 0, len(trackers)+len(additionalTrackers))
	allTrackers = append(allTrackers, trackers...)
	allTrackers = append(allTrackers, additionalTrackers...)
	allTrackers = utils.StableUniq(allTrackers)

	// The scraper only supports UDP trackers. Filter out HTTP(S) trackers
	// before spawning goroutines for them.
	udpTrackers := make([]string, 0, len(allTrackers))
	for _, tracker := range allTrackers {
		if strings.HasPrefix(tracker, "udp://") {
			udpTrackers = append(udpTrackers, tracker)
		}
	}
	if len(udpTrackers) > maxTrackersPerHash {
		udpTrackers = udpTrackers[:maxTrackersPerHash]
	}
	if len(udpTrackers) == 0 {
		return 0, 0, fmt.Errorf("no UDP trackers available for infohash: %s", infoHash)
	}

	type trackerResult struct {
		seeders  int
		leechers int
		err      error
	}

	results := make(chan trackerResult, len(udpTrackers))
	scrapeCtx, cancel := context.WithTimeout(ctx, peersScrapeTimeout)
	defer cancel()

	for _, tracker := range udpTrackers {
		go func(tracker string) {
			scraper, err := New(tracker)
			if err != nil {
				results <- trackerResult{err: err}
				return
			}

			scraper.SetTimeout(peerTrackerTimeout)
			scraper.SetRetryLimit(1)

			res, err := scraper.Scrape([]byte(infoHash))
			if err != nil {
				results <- trackerResult{err: err}
				return
			}

			results <- trackerResult{
				seeders:  int(res[0].Seeders),
				leechers: int(res[0].Leechers),
			}
		}(tracker)
	}

	maxSeeders, maxLeechers := 0, 0
	gotResponse := false
	received := 0

	for received < len(udpTrackers) {
		select {
		case <-scrapeCtx.Done():
			received = len(udpTrackers)
		case result := <-results:
			received++
			if result.err != nil {
				continue
			}
			gotResponse = true
			if result.seeders > maxSeeders {
				maxSeeders = result.seeders
			}
			if result.leechers > maxLeechers {
				maxLeechers = result.leechers
			}
		}
	}

	if !gotResponse {
		return 0, 0, fmt.Errorf("unable to get peers from trackers for infohash: %s", infoHash)
	}

	cacheCtx, cacheCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cacheCancel()

	if err := setPeersToCache(cacheCtx, r, infoHash, maxLeechers, maxSeeders); err != nil {
		logging.Error().Err(err).Str("info_hash", infoHash).Msg("Failed to cache peer data")
	} else {
		logging.Debug().Str("info_hash", infoHash).Int("leech", maxLeechers).Int("seed", maxSeeders).Msg("Retrieved peers from trackers")
	}

	return maxLeechers, maxSeeders, nil
}
