package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"github.com/felipemarinho97/torrent-indexer/logging"
	"github.com/felipemarinho97/torrent-indexer/magnet"
	"github.com/felipemarinho97/torrent-indexer/schema"
	goscrape "github.com/felipemarinho97/torrent-indexer/scrape"
	"github.com/felipemarinho97/torrent-indexer/utils"
)

var torrent_dos_filmes = IndexerMeta{
	Label:       "torrent_dos_filmes",
	URL:         utils.GetIndexerURLFromEnv("INDEXER_TORRENT_DOS_FILMES_URL", "https://torrentdosfilmes.se/"),
	SearchURL:   "?s=",
	PagePattern: "category/dublado/page/%s",
}

func (i *Indexer) HandlerTorrentDosFilmesIndexer(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	metadata := torrent_dos_filmes

	defer func() {
		i.metrics.IndexerDuration.WithLabelValues(metadata.Label).Observe(time.Since(start).Seconds())
		i.metrics.IndexerRequests.WithLabelValues(metadata.Label).Inc()
	}()

	ctx := r.Context()
	// supported query params: q, season, episode, page, filter_results
	q := r.URL.Query().Get("q")
	page := r.URL.Query().Get("page")

	// URL encode query param
	q = url.QueryEscape(q)
	url := metadata.URL
	if q != "" {
		url = fmt.Sprintf("%s%s%s", url, metadata.SearchURL, q)
	} else if page != "" {
		url = fmt.Sprintf(fmt.Sprintf("%s%s", url, metadata.PagePattern), page)
	}

	logging.InfoWithRequest(r).Str("target_url", url).Msg("Processing indexer request")
	resp, err := i.requester.GetDocument(ctx, url)
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
	doc.Find(".post").Each(func(i int, s *goquery.Selection) {
		link, _ := s.Find("div.title > a").Attr("href")
		links = append(links, link)
	})

	// if no links were indexed, expire the document in cache
	if len(links) == 0 {
		_ = i.requester.ExpireDocument(ctx, url)
	}

	// extract each torrent link
	indexedTorrents := utils.ParallelFlatMap(links, func(link string) ([]schema.IndexedTorrent, error) {
		return getTorrentsTorrentDosFilmes(ctx, i, link, url)
	})

	// Apply post-processors
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

func getTorrentsTorrentDosFilmes(ctx context.Context, i *Indexer, link, referer string) ([]schema.IndexedTorrent, error) {
	var indexedTorrents []schema.IndexedTorrent
	doc, err := getDocument(ctx, i, link, referer)
	if err != nil {
		return nil, err
	}

	article := doc.Find("article")
	title := strings.Replace(article.Find(".title > h1").Text(), " – Download", "", -1)
	title = strings.Replace(title, " - Download", "", -1)
	textContent := article.Find("div.content")
	date := getPublishedDateFromMeta(doc)

	var systemAdsLinks []string
	systemAdsLinksStr := textContent.Find("a[href*=\"systemads.net\"]")
	systemAdsLinksStr.Each(func(i int, s *goquery.Selection) {
		systemAdsLink, _ := s.Attr("href")
		systemAdsLinks = append(systemAdsLinks, systemAdsLink)
	})

	var audio []schema.Audio
	var year string
	var size []string
	article.Find("div.content p").Each(func(i int, s *goquery.Selection) {
		text := s.Text()

		audio = append(audio, findAudioFromText(text)...)
		y := findYearFromText(text, title)
		if y != "" {
			year = y
		}
		size = append(size, findSizesFromText(text)...)
	})

	imdbLink := ""
	article.Find("div.content a").Each(func(i int, s *goquery.Selection) {
		link, _ := s.Attr("href")
		_imdbLink, err := getIMDBLink(link)
		if err == nil {
			imdbLink = _imdbLink
		}
	})

	size = utils.StableUniq(size)

	var magnetLinks []string
	textContent.Find("a[href^=\"magnet\"]").Each(func(i int, s *goquery.Selection) {
		magnetLink, _ := s.Attr("href")
		magnetLinks = append(magnetLinks, magnetLink)
	})

	// Older pages used systemads links that redirect to the magnet. Keep it as
	// a fallback for pages that don't expose the magnet directly.
	if len(magnetLinks) == 0 {
		for _, systemAdsLink := range systemAdsLinks {
			links, err := followSystemAdsLink(ctx, i, systemAdsLink, link)
			if err != nil {
				logging.Error().Err(err).Str("systemads_link", systemAdsLink).Msg("Failed to follow systemads redirect")
				continue
			}
			magnetLinks = append(magnetLinks, links...)
		}
	}

	if len(magnetLinks) == 0 {
		return indexedTorrents, nil
	}

	if len(size) == 1 && len(magnetLinks) == 1 {
		// only one size and one magnet link - use the single size
	} else if len(size) == 0 || len(magnetLinks) != len(size) {
		size = make([]string, len(magnetLinks))
	}

	var chanIndexedTorrent = make(chan schema.IndexedTorrent)

	for it, magnetLink := range magnetLinks {
		it := it
		go func(it int, magnetLink string) {
			magnet, err := magnet.ParseMagnetUri(magnetLink)
			if err != nil {
				logging.Error().Err(err).Str("magnet_link", magnetLink).Msg("Failed to parse magnet URI")
				chanIndexedTorrent <- schema.IndexedTorrent{}
				return
			}
			releaseTitle := magnet.DisplayName
			infoHash := magnet.InfoHash.String()
			trackers := magnet.Trackers
			magnetAudio := getAudioFromTitle(releaseTitle, audio)

			peer, seed, err := goscrape.GetLeechsAndSeeds(ctx, i.redis, i.metrics, infoHash, trackers)
			if err != nil {
				logging.Error().Err(err).Str("info_hash", infoHash).Msg("Failed to get leechers and seeders")
			}

			processedTitle := processTitle(title, magnetAudio)

			var mySize string
			if it < len(size) {
				mySize = size[it]
			}
			if mySize == "" {
				go func() {
					_, _ = i.magnetMetadataAPI.FetchMetadata(ctx, magnetLink)
				}()
			}

			ixt := schema.IndexedTorrent{
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
			}
			chanIndexedTorrent <- ixt
		}(it, magnetLink)
	}

	for i := 0; i < len(magnetLinks); i++ {
		it := <-chanIndexedTorrent
		if it.MagnetLink != "" {
			indexedTorrents = append(indexedTorrents, it)
		}
	}

	return indexedTorrents, nil
}

func followSystemAdsLink(ctx context.Context, i *Indexer, systemAdsLink, referer string) ([]string, error) {
	resp, err := i.requester.GetDocument(ctx, systemAdsLink, referer)
	if err != nil {
		return nil, err
	}
	defer resp.Close()

	doc, err := goquery.NewDocumentFromReader(resp)
	if err != nil {
		return nil, err
	}

	var magnetLinks []string
	doc.Find("a[href^=\"magnet\"]").Each(func(i int, s *goquery.Selection) {
		magnetLink, _ := s.Attr("href")
		magnetLinks = append(magnetLinks, magnetLink)
	})

	if len(magnetLinks) > 0 {
		return magnetLinks, nil
	}

	redirectURL := findRedirectInHTML(doc)
	if redirectURL != "" {
		logging.Debug().Str("redirect", redirectURL).Msg("Found redirect URL in systemads page, following")
		if utils.IsMagnetLink(redirectURL) {
			return []string{redirectURL}, nil
		}
		resp2, err := i.requester.GetDocument(ctx, redirectURL, systemAdsLink)
		if err == nil {
			defer resp2.Close()
			doc2, err := goquery.NewDocumentFromReader(resp2)
			if err == nil {
				doc2.Find("a[href^=\"magnet\"]").Each(func(i int, s *goquery.Selection) {
					magnetLink, _ := s.Attr("href")
					magnetLinks = append(magnetLinks, magnetLink)
				})
			}
		}
	}

	return magnetLinks, nil
}

func findRedirectInHTML(doc *goquery.Document) string {
	metaContent, _ := doc.Find("meta[http-equiv=\"refresh\"]").Attr("content")
	if metaContent != "" {
		re := regexp.MustCompile(`(?i)url=(.+)`)
		match := re.FindStringSubmatch(metaContent)
		if len(match) > 1 {
			return strings.TrimSpace(match[1])
		}
	}

	html, _ := doc.Html()
	re := regexp.MustCompile(`window\.location\s*=\s*["']([^"']+)["']`)
	match := re.FindStringSubmatch(html)
	if len(match) > 1 {
		return strings.TrimSpace(match[1])
	}

	re = regexp.MustCompile(`document\.location\s*=\s*["']([^"']+)["']`)
	match = re.FindStringSubmatch(html)
	if len(match) > 1 {
		return strings.TrimSpace(match[1])
	}

	return ""
}
