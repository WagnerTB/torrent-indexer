package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"github.com/felipemarinho97/torrent-indexer/logging"
	"github.com/felipemarinho97/torrent-indexer/magnet"
	"github.com/felipemarinho97/torrent-indexer/schema"
	goscrape "github.com/felipemarinho97/torrent-indexer/scrape"
	"github.com/felipemarinho97/torrent-indexer/utils"
)

var baixarapido = IndexerMeta{
	Label:       "baixarapido",
	URL:         utils.GetIndexerURLFromEnv("INDEXER_BAIXARAPIDO_URL", "https://baixarapido.com/"),
	SearchURL:   "index.php?busca=",
	PagePattern: "index.php?busca=%s&pagina=%s",
}

func (i *Indexer) HandlerBaixarapidoIndexer(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	metadata := baixarapido

	defer func() {
		i.metrics.IndexerDuration.WithLabelValues(metadata.Label).Observe(time.Since(start).Seconds())
		i.metrics.IndexerRequests.WithLabelValues(metadata.Label).Inc()
	}()

	ctx := r.Context()
	q := r.URL.Query().Get("q")
	page := r.URL.Query().Get("page")

	// The site search uses index.php?busca=<query>. Pagination is not exposed
	// consistently on the search page, so it is best-effort.
	encodedQuery := url.QueryEscape(q)
	targetURL := fmt.Sprintf("%s%s%s", metadata.URL, metadata.SearchURL, encodedQuery)
	if page != "" && page != "1" {
		targetURL = fmt.Sprintf("%s&pagina=%s", targetURL, url.QueryEscape(page))
	}

	logging.InfoWithRequest(r).Str("target_url", targetURL).Msg("Processing indexer request")
	resp, err := i.requester.GetDocument(ctx, targetURL)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		err = json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		if err != nil {
			logging.ErrorWithRequest(r).Err(err).Msg("Failed to encode error response")
		}
		i.metrics.IndexerErrors.WithLabelValues(metadata.Label).Inc()
		return
	}
	defer resp.Close()

	doc, err := goquery.NewDocumentFromReader(resp)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		err = json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		if err != nil {
			logging.ErrorWithRequest(r).Err(err).Msg("Failed to encode error response")
		}
		i.metrics.IndexerErrors.WithLabelValues(metadata.Label).Inc()
		return
	}

	var links []string
	doc.Find(`div[itemprop="itemListElement"]`).Each(func(_ int, s *goquery.Selection) {
		link, exists := s.Find(`a[itemprop="url"]`).Attr("href")
		if !exists || strings.TrimSpace(link) == "" {
			return
		}
		if strings.HasPrefix(link, "/") {
			link = strings.TrimSuffix(metadata.URL, "/") + link
		}
		links = append(links, strings.TrimSpace(link))
	})
	links = utils.StableUniq(links)

	if len(links) == 0 {
		_ = i.requester.ExpireDocument(ctx, targetURL)
		logging.DebugWithRequest(r).Str("url", targetURL).Msg("No links found, expiring cache")
	}

	indexedTorrents := utils.ParallelFlatMap(links, func(link string) ([]schema.IndexedTorrent, error) {
		return getTorrentsBaixarapido(ctx, i, link, targetURL)
	})

	// The same magnet can be linked from different catalog pages (for example
	// "Matrix" and "Matrix Imax Open Matte"). Keep one entry per infohash,
	// filling missing metadata from later duplicates.
	byInfoHash := make(map[string]int, len(indexedTorrents))
	uniqueTorrents := make([]schema.IndexedTorrent, 0, len(indexedTorrents))
	for _, torrent := range indexedTorrents {
		if torrent.InfoHash == "" {
			continue
		}
		if idx, ok := byInfoHash[torrent.InfoHash]; ok {
			current := &uniqueTorrents[idx]
			if current.Size == "" && torrent.Size != "" {
				current.Size = torrent.Size
			}
			if current.Year == "" && torrent.Year != "" {
				current.Year = torrent.Year
			}
			if len(current.Audio) == 0 && len(torrent.Audio) > 0 {
				current.Audio = torrent.Audio
			}
			if current.IMDB == "" && torrent.IMDB != "" {
				current.IMDB = torrent.IMDB
			}
			continue
		}
		byInfoHash[torrent.InfoHash] = len(uniqueTorrents)
		uniqueTorrents = append(uniqueTorrents, torrent)
	}
	indexedTorrents = uniqueTorrents

	postProcessedTorrents := indexedTorrents
	for _, processor := range i.postProcessors {
		postProcessedTorrents = processor(i, r, postProcessedTorrents)
	}

	w.Header().Set("Content-Type", "application/json")
	err = json.NewEncoder(w).Encode(Response{
		Results:      postProcessedTorrents,
		Count:        len(postProcessedTorrents),
		IndexedCount: len(indexedTorrents),
	})
	if err != nil {
		logging.Error().Err(err).Msg("Failed to encode response")
	}
}

func getTorrentsBaixarapido(ctx context.Context, i *Indexer, link, referer string) ([]schema.IndexedTorrent, error) {
	var indexedTorrents []schema.IndexedTorrent
	doc, err := getDocument(ctx, i, link, referer)
	if err != nil {
		return nil, err
	}

	title := strings.TrimSpace(doc.Find(`h1 span[itemprop="name"]`).First().Text())
	if title == "" {
		title = strings.TrimSpace(doc.Find("h1").First().Text())
		title = strings.Replace(title, "Torrent", "", -1)
		title = strings.TrimSpace(title)
	}

	date := getPublishedDateFromMeta(doc)

	var audio []schema.Audio
	var year string
	var sizes []string
	doc.Find("table tr").Each(func(_ int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if text == "" {
			return
		}
		audio = append(audio, findAudioFromText(text)...)
		if year == "" {
			year = findYearFromText(text, title)
		}
		sizes = append(sizes, findSizesFromText(text)...)
	})
	// Some pages do not use a table for the metadata.
	bodyText := doc.Find("body").Text()
	if year == "" {
		year = findYearFromText(bodyText, title)
	}
	if len(audio) == 0 {
		audio = findAudioFromText(bodyText)
	}
	if len(sizes) == 0 {
		sizes = findSizesFromText(bodyText)
	}
	sizes = utils.StableUniq(sizes)

	imdbLink := ""
	doc.Find(`a[href*="imdb.com"]`).EachWithBreak(func(_ int, s *goquery.Selection) bool {
		href, _ := s.Attr("href")
		if resolved, err := getIMDBLink(href); err == nil {
			imdbLink = resolved
			return false
		}
		return true
	})

	var magnetLinks []string
	doc.Find(`a[href^="magnet:"]`).Each(func(_ int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if exists && strings.TrimSpace(href) != "" {
			magnetLinks = append(magnetLinks, strings.TrimSpace(href))
		}
	})
	magnetLinks = utils.StableUniq(magnetLinks)

	if len(magnetLinks) == 0 {
		return indexedTorrents, nil
	}

	// Sizes are not always one-to-one with magnets (for example a page with
	// one magnet and both 720p/1080p sizes). Use the best available value
	// instead of discarding all sizes.
	sizeFor := func(idx int) string {
		if len(sizes) == 0 {
			return ""
		}
		if len(sizes) == len(magnetLinks) && idx < len(sizes) {
			return sizes[idx]
		}
		if len(sizes) == 1 {
			return sizes[0]
		}
		if idx < len(sizes) {
			return sizes[idx]
		}
		return sizes[len(sizes)-1]
	}

	for idx, magnetLink := range magnetLinks {
		parsedMagnet, err := magnet.ParseMagnetUri(magnetLink)
		if err != nil {
			logging.Error().Err(err).Str("magnet_link", magnetLink).Msg("Failed to parse magnet URI")
			continue
		}

		releaseTitle := strings.TrimSpace(parsedMagnet.DisplayName)
		if releaseTitle == "" {
			releaseTitle = title
		}
		infoHash := parsedMagnet.InfoHash.String()
		trackers := parsedMagnet.Trackers
		magnetAudio := getAudioFromTitle(releaseTitle, audio)

		peer, seed, err := goscrape.GetLeechsAndSeeds(ctx, i.redis, i.metrics, infoHash, trackers)
		if err != nil {
			logging.Error().Err(err).Str("info_hash", infoHash).Msg("Failed to get leechers and seeders")
		}

		mySize := sizeFor(idx)
		if mySize == "" {
			go func(magnetLink string) {
				_, _ = i.magnetMetadataAPI.FetchMetadata(ctx, magnetLink)
			}(magnetLink)
		}

		processedTitle := appendAudioISO639_2Code(title, magnetAudio)
		indexedTorrents = append(indexedTorrents, schema.IndexedTorrent{
			Title:         releaseTitle,
			OriginalTitle: processedTitle,
			Details:       link,
			Year:          year,
			IMDB:          imdbLink,
			Audio:         magnetAudio,
			MagnetLink:    magnetLink,
			Date:          date,
			InfoHash:      infoHash,
			Trackers:      trackers,
			LeechCount:    peer,
			SeedCount:     seed,
			Size:          mySize,
		})
	}

	return indexedTorrents, nil
}
