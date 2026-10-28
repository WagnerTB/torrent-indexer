package handler

import (
	"encoding/json"
	"encoding/xml"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"time"

	"github.com/felipemarinho97/torrent-indexer/schema"
	"github.com/felipemarinho97/torrent-indexer/utils"
)

type rss struct {
	XMLName xml.Name `xml:"rss"`
	Version string   `xml:"version,attr"`
	Atom    string   `xml:"xmlns:atom,attr"`
	Torznab string   `xml:"xmlns:torznab,attr"`
	Channel channel  `xml:"channel"`
}

type channel struct {
	Title string `xml:"title"`
	Items []item `xml:"item"`
}

type item struct {
	Title       string    `xml:"title"`
	GUID        string    `xml:"guid"`
	Link        string    `xml:"link"`
	PubDate     string    `xml:"pubDate"`
	Size        int64     `xml:"size"`
	Category    int       `xml:"category"`
	Enclosure   enclosure `xml:"enclosure"`
	Attrs       []attr    `xml:"http://torznab.schemaware.info/schema attr"`
}

type enclosure struct {
	URL    string `xml:"url,attr"`
	Length int64  `xml:"length,attr"`
	Type   string `xml:"type,attr"`
}

type attr struct {
	Name  string `xml:"name,attr"`
	Value string `xml:"value,attr"`
}

func (i *Indexer) HandlerTorznabAPI(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/xml")

	t := r.URL.Query().Get("t")
	q := r.URL.Query().Get("q")

	if t == "caps" {
		fmt.Fprint(w, `<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="torrent-indexer"/>
  <searching>
    <search available="yes" supportedParams="q"/>
    <tv-search available="yes" supportedParams="q"/>
    <movie-search available="yes" supportedParams="q"/>
  </searching>
  <categories>
    <category id="2000" name="Movies"/>
    <category id="5000" name="TV"/>
  </categories>
</caps>`)
		return
	}

	if q == "" && t != "caps" {
		q = "a"
		r.URL.RawQuery = fmt.Sprintf("t=%s&q=%s", t, q)
	}
	if t != "caps" && q == "" {
		fmt.Fprint(w, `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:torznab="http://torznab.schemaware.info/schema">
  <channel><title>torrent-indexer</title></channel>
</rss>`)
		return
	}

	results, indexerName := i.callIndexer(r)
	if len(results) == 0 {
		r2 := r.Clone(r.Context())
		r2.URL.RawQuery = "q=2024"
		results, _ = i.callIndexer(r2)
	}
	xml := convertToTorznab(indexerName, results)
	_, _ = w.Write(xml)
}

func (i *Indexer) callIndexer(r *http.Request) ([]schema.IndexedTorrent, string) {
	path := r.URL.Path
	indexerName := strings.TrimPrefix(path, "/api")
	indexerName = strings.TrimPrefix(indexerName, "/")
	indexerName = strings.TrimSuffix(indexerName, "/api")
	indexerName = strings.TrimSuffix(indexerName, "/")
	if indexerName == "" {
		indexerName = r.URL.Query().Get("indexer")
	}
	if indexerName == "" {
		indexerName = "rede_torrent"
	}

	handlerPath := fmt.Sprintf("/indexers/%s", indexerName)
	q := r.URL.Query().Get("q")
	targetURL := fmt.Sprintf("%s?q=%s", handlerPath, q)

	rr := httptest.NewRecorder()
	req, err := http.NewRequestWithContext(r.Context(), "GET", targetURL, nil)
	if err != nil {
		return nil, indexerName
	}

	mux := http.NewServeMux()
	mux.HandleFunc(handlerPath, func(w http.ResponseWriter, r *http.Request) {
		switch indexerName {
		case "rede_torrent":
			i.HandlerRedeTorrentIndexer(w, r)
		case "comando_torrents":
			i.HandlerComandoIndexer(w, r)
		case "bludv":
			i.HandlerBluDVIndexer(w, r)
		case "starck-filmes":
			i.HandlerStarckFilmesIndexer(w, r)
		case "vaca_torrent":
			i.HandlerVacaTorrentIndexer(w, r)
		case "torrent-dos-filmes":
			i.HandlerTorrentDosFilmesIndexer(w, r)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})
	mux.ServeHTTP(rr, req)

	var resp Response
	if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
		return nil, indexerName
	}

	return resp.Results, indexerName
}

func convertToTorznab(indexerName string, results []schema.IndexedTorrent) []byte {
	ch := channel{
		Title: indexerName,
		Items: make([]item, 0, len(results)),
	}

	for _, r := range results {
		if r.MagnetLink == "" {
			continue
		}

		title := r.Title
		if title == "" {
			title = r.OriginalTitle
		}

		sizeBytes := utils.ParseSize(r.Size)

		pubDate := r.Date.Format(time.RFC1123Z)
		if r.Date.IsZero() {
			pubDate = time.Now().Format(time.RFC1123Z)
		}

		category := 2000
		if r.Season != 0 || r.Episode != 0 || r.ReleaseType != "" {
			category = 5000
		}

		it := item{
			Title:    title,
			GUID:     r.InfoHash,
			Link:     r.Details,
			PubDate:  pubDate,
			Size:     sizeBytes,
			Category: category,
			Enclosure: enclosure{
				URL:    r.MagnetLink,
				Length: sizeBytes,
				Type:   "application/x-bittorrent",
			},
			Attrs: []attr{
				{Name: "magneturl", Value: r.MagnetLink},
				{Name: "category", Value: strconv.Itoa(category)},
				{Name: "seeders", Value: strconv.Itoa(r.SeedCount)},
				{Name: "peers", Value: strconv.Itoa(r.LeechCount + r.SeedCount)},
				{Name: "size", Value: strconv.FormatInt(sizeBytes, 10)},
				{Name: "imdb", Value: r.IMDB},
				{Name: "year", Value: r.Year},
			},
		}
		ch.Items = append(ch.Items, it)
	}

	rssDoc := rss{
		Version: "2.0",
		Atom:    "http://www.w3.org/2005/Atom",
		Torznab: "http://torznab.schemaware.info/schema",
		Channel: ch,
	}

	out, _ := xml.MarshalIndent(rssDoc, "", "  ")
	return []byte(xml.Header + string(out))
}
